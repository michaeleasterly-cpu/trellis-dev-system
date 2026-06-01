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
    out: list = []
    base_indent: int | None = None
    for raw in block_lines:
        if not raw.strip():
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
        value = stripped[2:].strip()
        out.append(_parse_scalar(_strip_inline_comment(value)))
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


def _markdown_bullets(items: list[str]) -> str:
    if not items:
        return "_(none configured)_"
    return "\n".join(f"- `{p}`" for p in items)


def _flat_substitutions(profile: dict) -> dict[str, str]:
    """Compute scalar + markdown-list substitutions from the profile."""
    mem = profile.get("memory_policy", {}) or {}
    op = profile.get("output_paths", {}) or {}
    review_mode = profile.get("review_mode", "claude-review-only")

    heavy_paths = list(profile.get("critical_paths", []) or [])
    heavy_paths.extend(profile.get("deployment_specific_paths", []) or [])
    sec_paths = list(profile.get("security_sensitive_paths", []) or [])
    forbidden = list(profile.get("forbidden_assumptions", []) or [])

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
        "heavy_lane_paths_markdown": _markdown_bullets(heavy_paths),
        "security_sensitive_paths_markdown": _markdown_bullets(sec_paths),
        "forbidden_assumptions_markdown": _markdown_bullets(forbidden),
        # Memstore enabled-block placeholders (only meaningful when
        # api_memstores_enabled is true; substitution always runs but
        # the values stay empty strings when disabled).
        "dev_memstore_id": str(mem.get("dev_memstore_id", "") or ""),
        "agent_memstore_id": str(mem.get("agent_memstore_id", "") or ""),
        "anthropic_beta_header": str(
            mem.get("anthropic_beta_header", "managed-agents-2026-04-01")
        ),
    }
    return flat


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


def bootstrap(
    *,
    profile_file: Path,
    target_dir: Path,
    dry_run: bool,
    force: bool,
) -> int:
    if not profile_file.is_file():
        raise SystemExit(f"profile file not found: {profile_file}")
    profile_text = profile_file.read_text(encoding="utf-8")
    try:
        profile = parse_yaml(profile_text)
    except ValueError as exc:
        raise SystemExit(f"PROJECT_PROFILE.yaml parse error: {exc}") from exc
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

    planned: list[tuple[Path, str]] = []
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
        planned.append((out_path, rendered))

    # Copy PROJECT_PROFILE.yaml verbatim so audit can reload it.
    profile_out = target_dir / "PROJECT_PROFILE.yaml"

    if dry_run:
        print(f"[dry-run] target: {target_dir}")
        for out_path, _ in planned:
            print(f"[dry-run] would write: {out_path}")
        print(f"[dry-run] would write: {profile_out}")
        return 0

    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "docs").mkdir(parents=True, exist_ok=True)
    for out_path, content in planned:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
    shutil.copyfile(profile_file, profile_out)

    print(
        f"bootstrap_project: rendered {len(planned)} doc(s) "
        f"into {target_dir}/docs and wrote PROJECT_PROFILE.yaml"
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
        "--profile-file",
        required=True,
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
        profile_file=args.profile_file,
        target_dir=args.target_dir,
        dry_run=args.dry_run,
        force=args.force,
    )


if __name__ == "__main__":
    sys.exit(main())
