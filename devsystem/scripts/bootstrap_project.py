#!/usr/bin/env python3
"""D0c — Packet Void Dev System bootstrap renderer.

Reads a PROJECT_PROFILE.yaml + the D0b docs templates under
``devsystem/docs/`` and renders them into a consumer project's
``docs/`` directory. Also writes the operator-supplied
PROJECT_PROFILE.yaml into the target repo so ``audit_project.py``
can detect drift later.

Stdlib only. No PyYAML. No Anthropic API. No memstore writes. No
deployment commands. No execution of any consumer-project code —
this is a pure file-rendering operation.

Usage:

    python devsystem/scripts/bootstrap_project.py \\
        --profile-file PROJECT_PROFILE.yaml \\
        --target-dir <path/to/new/repo> \\
        [--dry-run] [--force]

D0c scope: docs templates only. Scripts / rules / skills / agents /
hooks / workflows / PR template are deferred to D0d–D0e.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

_DEVSYSTEM_ROOT = Path(__file__).resolve().parents[2]
_DEVSYSTEM_DOCS = _DEVSYSTEM_ROOT / "devsystem" / "docs"

# ─────────────────────────────────────────────────────────────────────
# PROJECT_PROFILE.yaml — minimal stdlib parser
# ─────────────────────────────────────────────────────────────────────

# Supports the exact shape produced by PROJECT_PROFILE.example.yaml:
# * top-level scalar `key: value`
# * top-level list `key:` followed by indented `  - item` entries
# * top-level nested object `key:` followed by indented `  subkey: value`
# Does NOT support: multi-line `|` scalars, flow style `[a, b]` /
# `{a: b}`, anchors, references. Anything else fails closed.


def parse_yaml(text: str) -> dict:
    """Parse the PROJECT_PROFILE.yaml subset documented above. Raise
    ``ValueError`` on any unsupported syntax."""
    out: dict = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        # Strip pure-comment / blank lines.
        if not raw.strip() or raw.lstrip().startswith("#"):
            i += 1
            continue
        indent = len(raw) - len(raw.lstrip())
        if indent != 0:
            raise ValueError(
                f"line {i + 1}: top-level key must be at column 0; "
                f"got indent={indent}"
            )
        key, sep, rest = raw.strip().partition(":")
        if not sep:
            raise ValueError(f"line {i + 1}: expected `key: value`")
        key = key.strip()
        rest = _strip_inline_comment(rest).strip()
        if rest:
            out[key] = _parse_scalar(rest)
            i += 1
            continue
        # Look-ahead: list or nested object.
        i += 1
        block_lines: list[str] = []
        while i < len(lines):
            r = lines[i]
            if not r.strip() or r.lstrip().startswith("#"):
                i += 1
                continue
            r_indent = len(r) - len(r.lstrip())
            if r_indent == 0:
                break
            block_lines.append(r)
            i += 1
        if not block_lines:
            out[key] = None
            continue
        first_stripped = block_lines[0].strip()
        if first_stripped.startswith("- "):
            out[key] = _parse_list(block_lines)
        else:
            out[key] = _parse_object(block_lines)
    return out


def _strip_inline_comment(value: str) -> str:
    # Conservative inline-comment strip: only honour ``#`` after at
    # least one space (so URL fragments inside a quoted string survive).
    # Quoted scalars are stripped of quotes downstream.
    in_quotes = False
    quote_char = ""
    for idx, ch in enumerate(value):
        if in_quotes:
            if ch == quote_char:
                in_quotes = False
            continue
        if ch in ("'", '"'):
            in_quotes = True
            quote_char = ch
            continue
        if ch == "#" and idx > 0 and value[idx - 1].isspace():
            return value[:idx]
    return value


def _parse_scalar(rest: str) -> object:
    rest = rest.strip()
    # Inline empty collections — the only flow-style YAML we accept.
    # Without this, ``deployment_specific_paths: []`` would parse to
    # the literal string ``"[]"`` and downstream iteration would yield
    # the two characters ``[`` and ``]`` as bogus list items.
    if rest == "[]":
        return []
    if rest == "{}":
        return {}
    if (rest.startswith('"') and rest.endswith('"')) or (
        rest.startswith("'") and rest.endswith("'")
    ):
        return rest[1:-1]
    lowered = rest.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    try:
        return int(rest)
    except ValueError:
        pass
    try:
        return float(rest)
    except ValueError:
        pass
    return rest


def _parse_list(block_lines: list[str]) -> list:
    """Parse a YAML list block.

    Supports two D0d shapes:
      * plain scalar items:    ``- "src/auth/**"``
      * mapping items:         ``- path: "src/auth/**"``
                               ``  why: "auth surface"``

    Mapping items are detected when the text after ``- `` contains
    ``key: value``. Continuation lines for the mapping appear at the
    base indent + 2 (matching the column of the key after the dash).
    """
    out: list = []
    base_indent: int | None = None
    i = 0
    while i < len(block_lines):
        raw = block_lines[i]
        if not raw.strip():
            i += 1
            continue
        indent = len(raw) - len(raw.lstrip())
        if base_indent is None:
            base_indent = indent
        if indent != base_indent:
            raise ValueError(
                "list items must be at a consistent indent; got "
                f"{indent} != {base_indent} in {raw!r}"
            )
        stripped = raw.strip()
        if not stripped.startswith("- "):
            raise ValueError(
                f"expected `- value` list item; got {stripped!r}"
            )
        rest = stripped[2:].strip()
        # Detect mapping-item form: ``- key: value`` (a key followed by
        # a colon at the first non-quoted column).
        is_mapping_item = False
        if rest and not rest.startswith(("'", '"')):
            kp, sep, _ = rest.partition(":")
            if sep and " " not in kp and kp:
                is_mapping_item = True
        if is_mapping_item:
            # Collect this item's mapping lines: the head line (with
            # the dash) plus any subsequent lines at indent + 2.
            item_block: list[str] = [
                " " * (base_indent + 2) + rest
            ]
            j = i + 1
            while j < len(block_lines):
                nxt = block_lines[j]
                if not nxt.strip():
                    j += 1
                    continue
                nxt_indent = len(nxt) - len(nxt.lstrip())
                if nxt_indent == base_indent + 2:
                    item_block.append(nxt)
                    j += 1
                    continue
                if nxt_indent <= base_indent:
                    break
                raise ValueError(
                    "mapping-item continuation must be at "
                    f"{base_indent + 2} columns; got {nxt_indent} in "
                    f"{nxt!r}"
                )
            out.append(_parse_object(item_block))
            i = j
            continue
        # Plain scalar item.
        value = _strip_inline_comment(rest)
        out.append(_parse_scalar(value))
        i += 1
    return out


def _parse_object(block_lines: list[str]) -> dict:
    out: dict = {}
    base_indent: int | None = None
    i = 0
    while i < len(block_lines):
        raw = block_lines[i]
        if not raw.strip() or raw.lstrip().startswith("#"):
            i += 1
            continue
        indent = len(raw) - len(raw.lstrip())
        if base_indent is None:
            base_indent = indent
        if indent != base_indent:
            raise ValueError(
                "nested-object keys must be at a consistent indent; "
                f"got {indent} != {base_indent} in {raw!r}"
            )
        key, sep, rest = raw.strip().partition(":")
        if not sep:
            raise ValueError(
                f"nested-object line missing colon: {raw!r}"
            )
        key = key.strip()
        rest = _strip_inline_comment(rest).strip()
        if rest:
            out[key] = _parse_scalar(rest)
            i += 1
            continue
        # Nested object beyond what PROJECT_PROFILE needs — fail closed.
        raise ValueError(
            f"nested-object value for key {key!r} requires a scalar; "
            "deeper nesting is not supported in D0c"
        )
    return out


# ─────────────────────────────────────────────────────────────────────
# Conditional-block resolver + placeholder substitution
# ─────────────────────────────────────────────────────────────────────

_CONDITIONAL_LABELS = ("API_MEMSTORES_DISABLED", "API_MEMSTORES_ENABLED")


def resolve_conditional_blocks(
    text: str, api_memstores_enabled: bool,
) -> str:
    """Keep one of the ``<!-- BEGIN_<LABEL> -->``/``<!-- END_<LABEL> -->``
    blocks and strip the other entirely (markers and body)."""
    if api_memstores_enabled:
        keep, drop = "API_MEMSTORES_ENABLED", "API_MEMSTORES_DISABLED"
    else:
        keep, drop = "API_MEMSTORES_DISABLED", "API_MEMSTORES_ENABLED"
    # Drop the opposite block entirely.
    text = re.sub(
        rf"<!-- BEGIN_{drop} -->\s*\n.*?<!-- END_{drop} -->\s*\n?",
        "",
        text,
        flags=re.DOTALL,
    )
    # Strip just the markers of the kept block.
    text = re.sub(rf"<!-- BEGIN_{keep} -->\s*\n?", "", text)
    text = re.sub(rf"<!-- END_{keep} -->\s*\n?", "", text)
    return text


def _path_entries(
    profile: dict, key: str, default_why: str,
) -> list[dict[str, str]]:
    """Return normalized ``[{path, why}, ...]`` entries from a profile
    list field. Handles both shapes:

      * plain strings → ``{path: str, why: default_why}``
      * mappings      → ``{path: item.path, why: item.why or default_why}``
    """
    out: list[dict[str, str]] = []
    for item in profile.get(key, []) or []:
        if isinstance(item, dict):
            path_val = str(item.get("path", "")).strip()
            why_val = str(item.get("why") or default_why).strip()
        else:
            path_val = str(item).strip()
            why_val = default_why
        if path_val:
            out.append({"path": path_val, "why": why_val})
    return out


def _markdown_bullets(items: list[str]) -> str:
    if not items:
        return "_(none configured)_"
    return "\n".join(f"- `{p}`" for p in items)


def _frontmatter_paths_yaml(items: list[str], indent: int = 2) -> str:
    """Render a YAML frontmatter ``paths:`` list (caller writes the
    ``paths:`` line itself; this returns the indented bullet block)."""
    if not items:
        return f"{' ' * indent}# (no paths configured for this profile)"
    pad = " " * indent
    return "\n".join(f'{pad}- "{p}"' for p in items)


def _registry_yaml_with_why(
    entries: list[dict[str, str]], indent: int,
) -> str:
    """Render path-registry-style entries:

        <indent>- path: "..."
        <indent+2>why: "..."
    """
    if not entries:
        return f"{' ' * indent}# (no entries — set in PROJECT_PROFILE)"
    pad_dash = " " * indent
    pad_cont = " " * (indent + 2)
    out: list[str] = []
    for e in entries:
        path_escaped = e["path"].replace('"', '\\"')
        why_escaped = e["why"].replace('"', '\\"')
        out.append(f'{pad_dash}- path: "{path_escaped}"')
        out.append(f'{pad_cont}why: "{why_escaped}"')
    return "\n".join(out)


def _shell_summary(items: list[str]) -> str:
    """Render a comma-separated path list safe for shell heredocs."""
    if not items:
        return "(none)"
    return ", ".join(items)


def _critical_subset_regex(items: list[str]) -> str:
    """Convert each glob to a regex-safe path-prefix and join with `|`.

    For shell ``grep -E``: strip ``/**`` and trailing ``/`` so the
    prefix matches a directory-anchored path. Inner ``**`` segments
    collapse to ``.*``. Characters that have special meaning in
    extended regex are escaped where they appear outside the glob
    metacharacters."""
    if not items:
        return "(?!x)x"  # an alternation that matches nothing.
    out: list[str] = []
    for item in items:
        s = str(item).strip()
        # Drop a trailing ``/**`` first.
        if s.endswith("/**"):
            s = s[:-3]
        # Replace remaining ``**`` with ``.*``.
        s = s.replace("**", ".*")
        # Escape regex metas that aren't part of the glob.
        s = re.sub(r"([.+()|^$\[\]{}])", r"\\\1", s)
        # Restore the ``.*`` (the previous escape doubled the backslash).
        s = s.replace("\\.\\*", ".*")
        # Match the prefix anchored at ``/`` or string start.
        out.append("(?:^|/)" + s)
    return "|".join(f"({p})" for p in out)


def _just_paths(entries: list[dict[str, str]]) -> list[str]:
    return [e["path"] for e in entries]


def _flat_substitutions(profile: dict) -> dict[str, str]:
    """Compute scalar + markdown-list + YAML-list substitutions from
    the profile. All placeholders the dev system uses across the
    docs/template + Claude-surface set."""
    mem = profile.get("memory_policy", {}) or {}
    op = profile.get("output_paths", {}) or {}
    review_mode = profile.get("review_mode", "claude-review-only")

    heavy_entries = _path_entries(
        profile, "critical_paths", "critical project path"
    )
    heavy_entries.extend(
        _path_entries(
            profile,
            "deployment_specific_paths",
            "deployment-specific critical path",
        )
    )
    security_entries = _path_entries(
        profile,
        "security_sensitive_paths",
        "security-sensitive path",
    )
    claude_system_entries = _path_entries(
        profile,
        "claude_system_paths",
        "Claude extension-layer path",
    )
    forbidden = list(profile.get("forbidden_assumptions", []) or [])

    heavy_paths = _just_paths(heavy_entries)
    security_paths = _just_paths(security_entries)
    # claude_system_entries used in registry-with-why placeholder
    # only; no flat-path representation needed here.

    flat: dict[str, str] = {
        "project_name": str(profile.get("project_name", "")),
        "review_mode": str(review_mode),
        "home_session_path": str(profile.get("home_session_path", "")),
        "operator_reports_path": str(
            op.get("operator_reports", ".operator/reports/claude/")
        ),
        "local_memory_limit_bytes": str(
            mem.get("local_memory_limit_bytes", 24400)
        ),
        # Markdown-list placeholders (for docs templates).
        "heavy_lane_paths_markdown": _markdown_bullets(heavy_paths),
        "security_sensitive_paths_markdown": _markdown_bullets(
            security_paths
        ),
        "forbidden_assumptions_markdown": _markdown_bullets(forbidden),
        # YAML-list placeholders for rule frontmatter (indent 2).
        "heavy_lane_paths_yaml": _frontmatter_paths_yaml(heavy_paths, 2),
        "security_sensitive_paths_yaml": _frontmatter_paths_yaml(
            security_paths, 2
        ),
        # Registry-style placeholders for .claude/path_registry.yaml
        # (indent 6 — ``    paths:`` is at indent 4, items at 6).
        "heavy_lane_paths_yaml_with_why": _registry_yaml_with_why(
            heavy_entries, 6
        ),
        "claude_system_paths_yaml_with_why": _registry_yaml_with_why(
            claude_system_entries, 6
        ),
        # Shell-safe placeholders for hooks.
        "heavy_lane_paths_shell_summary": _shell_summary(heavy_paths),
        "critical_subset_paths_regex": _critical_subset_regex(heavy_paths),
        # D0e — workflow paths filter (union of heavy_lane +
        # claude_system at workflow indent 6) and PR-template
        # heavy-lane checkbox block.
        "workflow_paths_yaml": _frontmatter_paths_yaml(
            heavy_paths + _just_paths(claude_system_entries), 6
        ),
        "heavy_lane_paths_checklist": _checklist_paths(heavy_paths),
        # D0e — CI workflow knobs.
        "python_version": str(profile.get("python_version", "3.11")),
        "test_command": str(
            profile.get("test_command", "python -m pytest -q")
        ),
        # Memstore enabled-block placeholders (only meaningful when
        # api_memstores_enabled is true).
        "dev_memstore_id": str(mem.get("dev_memstore_id", "") or ""),
        "agent_memstore_id": str(mem.get("agent_memstore_id", "") or ""),
        "anthropic_beta_header": str(
            mem.get("anthropic_beta_header", "managed-agents-2026-04-01")
        ),
    }
    return flat


def _checklist_paths(items: list[str]) -> str:
    """Render the PR template's heavy-lane checkbox block."""
    if not items:
        return "- [ ] (no heavy_lane paths configured for this profile)"
    return "\n".join(f"- [ ] `{p}`" for p in items)


_UNRESOLVED_PATTERN = re.compile(r"\{\{\s*[A-Za-z0-9_]+\s*\}\}")


def render_template(template_text: str, profile: dict) -> str:
    """Render one template against ``profile``. Raises on unresolved
    placeholders or on missing memstore IDs when the enabled block
    was selected."""
    mem = profile.get("memory_policy", {}) or {}
    enabled = bool(mem.get("api_memstores_enabled", False))
    if enabled:
        for required in ("dev_memstore_id", "agent_memstore_id"):
            value = mem.get(required) or ""
            if not str(value).strip():
                raise ValueError(
                    f"PROJECT_PROFILE.memory_policy.api_memstores_enabled "
                    f"is true but {required!r} is missing or empty; "
                    "supply your own memstore IDs or set "
                    "api_memstores_enabled: false"
                )
    text = resolve_conditional_blocks(template_text, enabled)
    flat = _flat_substitutions(profile)
    for var, val in flat.items():
        text = text.replace("{{ " + var + " }}", val)
    leftovers = _UNRESOLVED_PATTERN.findall(text)
    if leftovers:
        unique = sorted(set(leftovers))
        raise ValueError(
            f"unresolved placeholders after rendering: {unique}"
        )
    return text


# ─────────────────────────────────────────────────────────────────────
# Bootstrap pipeline
# ─────────────────────────────────────────────────────────────────────

def _profile_assertions(profile: dict) -> None:
    """Defense-in-depth sanity asserts beyond the JSON Schema."""
    if profile.get("schema_version") != 1:
        raise ValueError(
            "PROJECT_PROFILE.schema_version must be 1"
        )
    if not profile.get("project_name"):
        raise ValueError("PROJECT_PROFILE.project_name is required")


def _list_templates() -> list[Path]:
    if not _DEVSYSTEM_DOCS.is_dir():
        raise SystemExit(
            f"devsystem docs dir not found: {_DEVSYSTEM_DOCS}"
        )
    return sorted(_DEVSYSTEM_DOCS.glob("*.md.template"))


def _target_doc_path(template: Path, target_dir: Path) -> Path:
    # devsystem/docs/FOO.md.template → <target>/docs/FOO.md
    rendered_name = template.name[: -len(".template")]
    return target_dir / "docs" / rendered_name


# ─────────────────────────────────────────────────────────────────────
# D0d — Claude-surface render plan
# ─────────────────────────────────────────────────────────────────────

_DEVSYSTEM_CLAUDE = _DEVSYSTEM_ROOT / "devsystem" / "claude"


def _plan_claude_surface(
    profile: dict, target_dir: Path,
) -> list[tuple[Path, str, bool]]:
    """Return ``(out_path, content, executable)`` triples for every
    Claude-surface artifact rendered into the target repo.

    Rendering rules:
      * ``devsystem/claude/path_registry.yaml.template`` →
        ``<target>/.claude/path_registry.yaml`` (rendered)
      * ``devsystem/claude/rules/*.md.template`` →
        ``<target>/.claude/rules/<name>.md`` (rendered)
      * ``devsystem/claude/skills/<name>/SKILL.md`` →
        ``<target>/.claude/skills/<name>/SKILL.md`` (verbatim copy;
        the security-review skill is content-portable as-is)
      * ``devsystem/claude/hooks/*.sh`` → verbatim, executable
      * ``devsystem/claude/hooks/*.sh.template`` → rendered, executable
      * ``devsystem/claude/agents/*.md.template`` → rendered
    """
    plan: list[tuple[Path, str, bool]] = []
    claude_root = target_dir / ".claude"
    if not _DEVSYSTEM_CLAUDE.is_dir():
        return plan

    # Path registry.
    registry_template = _DEVSYSTEM_CLAUDE / "path_registry.yaml.template"
    if registry_template.is_file():
        plan.append(
            (
                claude_root / "path_registry.yaml",
                render_template(
                    registry_template.read_text(encoding="utf-8"), profile,
                ),
                False,
            )
        )

    # D0e — .claude/settings.json (template; renders into the
    # consumer's .claude/settings.json wiring the portable hooks
    # into Claude Code's hook events).
    settings_template = _DEVSYSTEM_CLAUDE / "settings.json.template"
    if settings_template.is_file():
        plan.append(
            (
                claude_root / "settings.json",
                render_template(
                    settings_template.read_text(encoding="utf-8"), profile,
                ),
                False,
            )
        )

    rules_dir = _DEVSYSTEM_CLAUDE / "rules"
    if rules_dir.is_dir():
        for template in sorted(rules_dir.glob("*.md.template")):
            rendered_name = template.name[: -len(".template")]
            plan.append(
                (
                    claude_root / "rules" / rendered_name,
                    render_template(
                        template.read_text(encoding="utf-8"), profile,
                    ),
                    False,
                )
            )

    skills_dir = _DEVSYSTEM_CLAUDE / "skills"
    if skills_dir.is_dir():
        for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
            skill_name = skill_md.parent.name
            plan.append(
                (
                    claude_root / "skills" / skill_name / "SKILL.md",
                    skill_md.read_text(encoding="utf-8"),
                    False,
                )
            )

    hooks_dir = _DEVSYSTEM_CLAUDE / "hooks"
    if hooks_dir.is_dir():
        for hook in sorted(hooks_dir.glob("*.sh")):
            plan.append(
                (
                    claude_root / "hooks" / hook.name,
                    hook.read_text(encoding="utf-8"),
                    True,
                )
            )
        for template in sorted(hooks_dir.glob("*.sh.template")):
            rendered_name = template.name[: -len(".template")]
            plan.append(
                (
                    claude_root / "hooks" / rendered_name,
                    render_template(
                        template.read_text(encoding="utf-8"), profile,
                    ),
                    True,
                )
            )

    agents_dir = _DEVSYSTEM_CLAUDE / "agents"
    if agents_dir.is_dir():
        for template in sorted(agents_dir.glob("*.md.template")):
            rendered_name = template.name[: -len(".template")]
            plan.append(
                (
                    claude_root / "agents" / rendered_name,
                    render_template(
                        template.read_text(encoding="utf-8"), profile,
                    ),
                    False,
                )
            )
    return plan


# ─────────────────────────────────────────────────────────────────────
# D0e — GitHub workflows + PR template render plan
# ─────────────────────────────────────────────────────────────────────

_DEVSYSTEM_GITHUB = _DEVSYSTEM_ROOT / "devsystem" / "github"


def _plan_github_surface(
    profile: dict, target_dir: Path,
) -> list[tuple[Path, str, bool]]:
    """Return ``(out_path, content, executable)`` triples for the
    GitHub workflows + PR template.

      * ``devsystem/github/workflows/*.yml`` → verbatim copy into
        ``<target>/.github/workflows/<name>.yml``.
      * ``devsystem/github/workflows/*.yml.template`` → rendered.
      * ``devsystem/github/pull_request_template.md.template`` →
        ``<target>/.github/pull_request_template.md``.
    """
    plan: list[tuple[Path, str, bool]] = []
    github_root = target_dir / ".github"
    if not _DEVSYSTEM_GITHUB.is_dir():
        return plan

    workflows_dir = _DEVSYSTEM_GITHUB / "workflows"
    if workflows_dir.is_dir():
        for verbatim in sorted(workflows_dir.glob("*.yml")):
            plan.append(
                (
                    github_root / "workflows" / verbatim.name,
                    verbatim.read_text(encoding="utf-8"),
                    False,
                )
            )
        for template in sorted(workflows_dir.glob("*.yml.template")):
            rendered_name = template.name[: -len(".template")]
            plan.append(
                (
                    github_root / "workflows" / rendered_name,
                    render_template(
                        template.read_text(encoding="utf-8"), profile,
                    ),
                    False,
                )
            )

    pr_template = _DEVSYSTEM_GITHUB / "pull_request_template.md.template"
    if pr_template.is_file():
        plan.append(
            (
                github_root / "pull_request_template.md",
                render_template(
                    pr_template.read_text(encoding="utf-8"), profile,
                ),
                False,
            )
        )
    return plan


# ─────────────────────────────────────────────────────────────────────
# D0e — profile-seed loader + merge
# ─────────────────────────────────────────────────────────────────────

_TEMPLATES_DIR = _DEVSYSTEM_ROOT / "templates"


def _dump_scalar_yaml(value: object) -> str:
    """Render a scalar value as it should appear after ``key: ``.

    Always-quote strings — the parser tolerates quoted strings
    everywhere, and quoting them prevents round-trip drift where
    ``python_version: 3.11`` parses back as a float, or where a
    string starting with ``~`` parses as a YAML anchor.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if value is None:
        return "null"
    if isinstance(value, str):
        # Escape any embedded double quotes.
        escaped = value.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escaped}"'
    raise ValueError(
        f"_dump_scalar_yaml: unsupported scalar type {type(value)}"
    )


def _dump_profile_yaml(profile: dict) -> str:
    """Serialize the merged profile back into PROJECT_PROFILE.yaml
    shape. Stdlib-only; supports the same subset the parser supports
    (top-level scalars, lists of strings or {path, why} mappings, and
    one level of nested objects)."""
    lines: list[str] = []
    for key, value in profile.items():
        if isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
                continue
            lines.append(f"{key}:")
            for item in value:
                if isinstance(item, dict):
                    keys = list(item.keys())
                    if not keys:
                        continue
                    first_key = keys[0]
                    lines.append(
                        f"  - {first_key}: {_dump_scalar_yaml(item[first_key])}"
                    )
                    for k in keys[1:]:
                        lines.append(
                            f"    {k}: {_dump_scalar_yaml(item[k])}"
                        )
                else:
                    lines.append(f"  - {_dump_scalar_yaml(item)}")
        elif isinstance(value, dict):
            lines.append(f"{key}:")
            for sub_key, sub_val in value.items():
                lines.append(
                    f"  {sub_key}: {_dump_scalar_yaml(sub_val)}"
                )
        else:
            lines.append(f"{key}: {_dump_scalar_yaml(value)}")
    return "\n".join(lines) + "\n"


def _list_known_profiles() -> list[str]:
    if not _TEMPLATES_DIR.is_dir():
        return []
    return sorted(
        d.name for d in _TEMPLATES_DIR.iterdir()
        if d.is_dir() and (d / "PROJECT_PROFILE.yaml").is_file()
    )


def _load_profile_seed(name: str) -> dict:
    seed_path = _TEMPLATES_DIR / name / "PROJECT_PROFILE.yaml"
    if not seed_path.is_file():
        known = _list_known_profiles()
        raise SystemExit(
            f"unknown profile {name!r}; known: {known}"
        )
    return parse_yaml(seed_path.read_text(encoding="utf-8"))


def _merge_profiles(seed: dict, overlay: dict) -> dict:
    """Overlay scalar / list / object values onto the seed.

    Rules:
      * Scalars in overlay replace seed scalars.
      * Lists in overlay replace seed lists in full (no merge of
        items).
      * Nested objects (e.g. ``memory_policy``) are shallow-merged:
        overlay keys replace seed keys at one level.
    """
    out = dict(seed)
    for key, val in overlay.items():
        if (
            isinstance(val, dict)
            and isinstance(out.get(key), dict)
        ):
            merged = dict(out[key])
            merged.update(val)
            out[key] = merged
        else:
            out[key] = val
    return out


def bootstrap(
    *,
    profile_name: str | None,
    profile_file: Path | None,
    target_dir: Path,
    dry_run: bool,
    force: bool,
) -> int:
    """D0e — bootstrap entry point.

    Profile resolution:
      * ``--profile NAME`` alone        → load templates/<NAME>/PROJECT_PROFILE.yaml
      * ``--profile-file PATH`` alone   → load PATH
      * Both                            → load NAME seed first; overlay PATH values
      * Neither                         → SystemExit with usage hint
    """
    if profile_name is None and profile_file is None:
        raise SystemExit(
            "must supply --profile <name> or --profile-file <path>"
        )
    seed: dict = {}
    if profile_name is not None:
        seed = _load_profile_seed(profile_name)
    overlay: dict = {}
    if profile_file is not None:
        if not profile_file.is_file():
            raise SystemExit(f"profile file not found: {profile_file}")
        try:
            overlay = parse_yaml(profile_file.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise SystemExit(
                f"PROJECT_PROFILE.yaml parse error: {exc}"
            ) from exc
    profile = _merge_profiles(seed, overlay)
    _profile_assertions(profile)

    target_dir = target_dir.resolve()
    if (
        target_dir.exists()
        and any(target_dir.iterdir())
        and not force
        and not dry_run
    ):
        raise SystemExit(
            f"target dir {target_dir} is non-empty; pass --force to "
            "overwrite or pick a fresh path"
        )

    docs_planned: list[tuple[Path, str]] = []
    templates = _list_templates()
    if not templates:
        raise SystemExit(
            f"no *.md.template files under {_DEVSYSTEM_DOCS}; nothing to render"
        )
    for template in templates:
        rendered = render_template(
            template.read_text(encoding="utf-8"), profile,
        )
        out_path = _target_doc_path(template, target_dir)
        docs_planned.append((out_path, rendered))

    # D0d — also plan the Claude-surface artifacts.
    claude_planned = _plan_claude_surface(profile, target_dir)
    # D0e — workflows + PR template.
    github_planned = _plan_github_surface(profile, target_dir)

    # Copy the profile that audit_project.py will read on the next
    # run. Two cases:
    #   * profile_file only            → byte-equal copy (preserves
    #                                    comments, ordering, quoting)
    #   * --profile [+ profile_file]   → dump the merged in-memory
    #                                    profile (no source-file
    #                                    fidelity is possible across
    #                                    the merge)
    profile_out = target_dir / "PROJECT_PROFILE.yaml"
    if profile_name is None and profile_file is not None:
        effective_profile_yaml = profile_file.read_text(encoding="utf-8")
    else:
        effective_profile_yaml = _dump_profile_yaml(profile)

    if dry_run:
        print(f"[dry-run] target: {target_dir}")
        for out_path, _ in docs_planned:
            print(f"[dry-run] would write: {out_path}")
        for out_path, _, exe in claude_planned:
            tag = "(+x)" if exe else "   "
            print(f"[dry-run] would write {tag}: {out_path}")
        for out_path, _, _exe in github_planned:
            print(f"[dry-run] would write    : {out_path}")
        print(f"[dry-run] would write: {profile_out}")
        return 0

    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "docs").mkdir(parents=True, exist_ok=True)
    for out_path, content in docs_planned:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
    for out_path, content, exe in claude_planned:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        if exe:
            mode = out_path.stat().st_mode | 0o111
            out_path.chmod(mode)
    for out_path, content, exe in github_planned:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        if exe:
            mode = out_path.stat().st_mode | 0o111
            out_path.chmod(mode)
    profile_out.write_text(effective_profile_yaml, encoding="utf-8")

    n_total = len(docs_planned) + len(claude_planned) + len(github_planned)
    print(
        f"bootstrap_project: rendered {len(docs_planned)} doc(s) + "
        f"{len(claude_planned)} Claude-surface + "
        f"{len(github_planned)} GitHub-surface artifact(s) "
        f"({n_total} total) into {target_dir}"
    )
    return 0
    shutil.copyfile(profile_file, profile_out)

    print(
        f"bootstrap_project: rendered {len(docs_planned)} doc(s) + "
        f"{len(claude_planned)} Claude-surface artifact(s) "
        f"into {target_dir} and wrote PROJECT_PROFILE.yaml"
    )
    return 0


# ─────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bootstrap_project",
        description=(
            "Render Packet Void Dev System templates into a consumer "
            "project. See devsystem/docs/*.md.template and "
            "PROJECT_PROFILE.example.yaml."
        ),
    )
    parser.add_argument(
        "--profile",
        default=None,
        help=(
            "Named profile seed to load (e.g. ``generic-python``, "
            "``python-railway``, ``python-postgres``, "
            "``fintech-research``). When used alone, the seed becomes "
            "the project profile. When combined with --profile-file, "
            "the explicit file values overlay the seed."
        ),
    )
    parser.add_argument(
        "--profile-file",
        default=None,
        type=Path,
        help="Path to PROJECT_PROFILE.yaml for the consumer project.",
    )
    parser.add_argument(
        "--target-dir",
        required=True,
        type=Path,
        help="Where to render the consumer project skeleton.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned writes; do not touch disk.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing non-empty target dir.",
    )
    args = parser.parse_args(argv)
    return bootstrap(
        profile_name=args.profile,
        profile_file=args.profile_file,
        target_dir=args.target_dir,
        dry_run=args.dry_run,
        force=args.force,
    )


if __name__ == "__main__":
    sys.exit(main())
