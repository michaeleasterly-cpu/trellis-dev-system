#!/usr/bin/env python3
"""D0c — Packet Void Dev System manifest linter (minimal baseline).

D0c scope is intentionally narrow:

  1. Validate ``PROJECT_PROFILE.example.yaml`` parses with the
     dev-system's stdlib parser and satisfies the required keys.
  2. Verify every ``devsystem/docs/*.md.template`` is present and
     non-empty.
  3. Verify the JSON Schema at ``schemas/project_profile.schema.json``
     parses and pins ``schema_version=1``.

Rules / skills / agents / hooks / workflows have not been extracted
yet (deferred to D0d–D0e), so this linter does not validate them.
When those land, this linter will grow to mirror the heavier
``check_manifests.py`` pattern from the donor repo (path-registry
sync, hook shebangs + forbidden commands, agent / skill frontmatter
+ forbidden authorizations, workflow allowedTools).

Stdlib only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from bootstrap_project import parse_yaml  # noqa: E402

_REPO = Path(__file__).resolve().parents[2]
_PROFILE_EXAMPLE = _REPO / "PROJECT_PROFILE.example.yaml"
_SCHEMA = _REPO / "schemas" / "project_profile.schema.json"
_DOCS_DIR = _REPO / "devsystem" / "docs"

_REQUIRED_PROFILE_KEYS = (
    "schema_version",
    "project_name",
    "language",
    "deployment",
    "database",
    "critical_paths",
    "claude_system_paths",
    "security_sensitive_paths",
    "forbidden_assumptions",
    "memory_policy",
    "review_mode",
    "output_paths",
)


def _err(path: Path, message: str) -> str:
    try:
        rel = path.resolve().relative_to(_REPO)
    except ValueError:
        rel = path
    return f"FAIL {rel}: {message}"


def check_project_profile_example_parses() -> list[str]:
    failures: list[str] = []
    if not _PROFILE_EXAMPLE.is_file():
        return [_err(_PROFILE_EXAMPLE, "missing PROJECT_PROFILE.example.yaml")]
    try:
        data = parse_yaml(_PROFILE_EXAMPLE.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [_err(_PROFILE_EXAMPLE, f"parse error: {exc}")]
    for key in _REQUIRED_PROFILE_KEYS:
        if key not in data:
            failures.append(
                _err(_PROFILE_EXAMPLE, f"missing required key: {key}")
            )
    return failures


def check_schema_pins_version_one() -> list[str]:
    failures: list[str] = []
    if not _SCHEMA.is_file():
        return [_err(_SCHEMA, "missing JSON Schema")]
    try:
        data = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [_err(_SCHEMA, f"invalid JSON: {exc}")]
    props = data.get("properties", {})
    sv = props.get("schema_version", {})
    if sv.get("const") != 1:
        failures.append(
            _err(
                _SCHEMA,
                "properties.schema_version.const must be 1",
            )
        )
    return failures


def check_docs_templates_present() -> list[str]:
    failures: list[str] = []
    if not _DOCS_DIR.is_dir():
        return [_err(_DOCS_DIR, "missing devsystem/docs/ directory")]
    expected = (
        "DEV_PIPELINE_STANDARD.md.template",
        "MEMSTORE_HANDOFF.md.template",
        "MEMORY_MAINTENANCE.md.template",
        "SECURITY_GUIDANCE.md.template",
        "CLAUDE_SESSION_OBSERVABILITY.md.template",
    )
    for name in expected:
        path = _DOCS_DIR / name
        if not path.is_file():
            failures.append(_err(path, "missing portable doc template"))
            continue
        if not path.read_text(encoding="utf-8").strip():
            failures.append(_err(path, "template is empty"))
    return failures


_HOOK_FORBIDDEN_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bgh\s+pr\s+merge\b", "gh pr merge"),
    (r"\bgh\s+api\s+.*--method\s+(PATCH|POST|PUT|DELETE)\b", "gh api mutation"),
    (r"\bgit\s+push\s+[^\n]*(--force|--force-with-lease|\s-f(\s|$))", "git push --force"),
    (r"curl\s+[^\n]*ANTHROPIC_API_KEY", "Anthropic API call from hook"),
    (r"/memory_stores/[^\s]+/memories", "memstore API endpoint"),
)


def _strip_shell_comments(text: str) -> str:
    out: list[str] = []
    for raw in text.splitlines():
        if raw.lstrip().startswith("#"):
            continue
        out.append(raw)
    return "\n".join(out)


def check_consumer_target(target_dir: Path) -> list[str]:
    """D0d/D0e — validate the rendered Claude + GitHub surface in a
    CONSUMER repo (one that bootstrap_project.py wrote into). Read-only
    checks:

      * .claude/path_registry.yaml exists and parses.
      * .claude/rules/*.md have YAML frontmatter and non-empty body.
      * .claude/agents/*.md and .claude/skills/*/SKILL.md have YAML
        frontmatter and non-empty body.
      * .claude/hooks/*.sh have shebang + executable bit.
      * No forbidden command in any hook body (comments stripped).
      * D0e — .claude/settings.json is valid JSON, references only
        existing hook scripts.
      * D0e — .github/workflows/claude-review-heavy-lane.yml has
        permissions.contents: read (NOT write), and its on.pull_request
        paths filter equals heavy_lane ∪ claude_system from the
        path_registry.
      * D0e — .github/pull_request_template.md contains a checkbox
        line for every heavy_lane path in the registry.
    """
    import re as _re
    findings: list[str] = []
    if not target_dir.is_dir():
        return [_err(target_dir, "consumer target dir not found")]
    claude_root = target_dir / ".claude"
    if not claude_root.is_dir():
        return [_err(claude_root, "missing .claude/ in consumer target")]
    registry = claude_root / "path_registry.yaml"
    if not registry.is_file():
        findings.append(_err(registry, "missing .claude/path_registry.yaml"))
    rules_dir = claude_root / "rules"
    if rules_dir.is_dir():
        for rule in sorted(rules_dir.glob("*.md")):
            text = rule.read_text(encoding="utf-8")
            if not text.startswith("---"):
                findings.append(_err(rule, "missing YAML frontmatter"))
                continue
            body_idx = text.find("\n---", 3)
            body = text[body_idx + 4:] if body_idx >= 0 else ""
            if not body.strip():
                findings.append(_err(rule, "empty body after frontmatter"))
    agents_dir = claude_root / "agents"
    if agents_dir.is_dir():
        for agent in sorted(agents_dir.glob("*.md")):
            text = agent.read_text(encoding="utf-8")
            if not text.startswith("---"):
                findings.append(_err(agent, "missing YAML frontmatter"))
                continue
            body_idx = text.find("\n---", 3)
            body = text[body_idx + 4:] if body_idx >= 0 else ""
            if not body.strip():
                findings.append(_err(agent, "empty body after frontmatter"))
    skills_dir = claude_root / "skills"
    if skills_dir.is_dir():
        for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
            text = skill_md.read_text(encoding="utf-8")
            if not text.startswith("---"):
                findings.append(_err(skill_md, "SKILL.md missing YAML frontmatter"))
                continue
            body_idx = text.find("\n---", 3)
            body = text[body_idx + 4:] if body_idx >= 0 else ""
            if not body.strip():
                findings.append(_err(skill_md, "SKILL.md body is empty"))
    hooks_dir = claude_root / "hooks"
    if hooks_dir.is_dir():
        for hook in sorted(hooks_dir.glob("*.sh")):
            text = hook.read_text(encoding="utf-8")
            try:
                first = text.splitlines()[0]
            except IndexError:
                findings.append(_err(hook, "empty hook file"))
                continue
            if not first.startswith("#!"):
                findings.append(_err(hook, "missing shebang on line 1"))
            mode = hook.stat().st_mode
            if not (mode & 0o111):
                findings.append(_err(hook, "not executable (chmod +x)"))
            scan_text = _strip_shell_comments(text)
            for pattern, label in _HOOK_FORBIDDEN_PATTERNS:
                m = _re.search(pattern, scan_text, _re.IGNORECASE)
                if m:
                    findings.append(
                        _err(hook, f"forbidden {label}: {m.group(0)!r}")
                    )
    findings.extend(_check_consumer_settings(claude_root))
    findings.extend(_check_consumer_workflows_and_pr(target_dir, claude_root))
    return findings


def _check_consumer_settings(claude_root: Path) -> list[str]:
    """Validate .claude/settings.json: JSON parses + every hook script
    it references exists."""
    findings: list[str] = []
    settings = claude_root / "settings.json"
    if not settings.is_file():
        return [_err(settings, "missing .claude/settings.json")]
    try:
        data = json.loads(settings.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [_err(settings, f"invalid JSON: {exc}")]
    hooks_block = data.get("hooks", {})
    if not isinstance(hooks_block, dict):
        return [_err(settings, "hooks block must be an object")]
    for event, entries in hooks_block.items():
        if not isinstance(entries, list):
            findings.append(
                _err(settings, f"hooks.{event} must be a list")
            )
            continue
        for entry in entries:
            for hook in entry.get("hooks", []) or []:
                cmd = str(hook.get("command", ""))
                marker = "$CLAUDE_PROJECT_DIR/"
                if marker not in cmd:
                    findings.append(
                        _err(
                            settings,
                            f"hook command must reference $CLAUDE_PROJECT_DIR: {cmd!r}",
                        )
                    )
                    continue
                rel = cmd.split(marker, 1)[1].strip()
                target = claude_root.parent / rel
                if not target.is_file():
                    findings.append(
                        _err(
                            settings,
                            f"references missing hook script {rel!r}",
                        )
                    )
    return findings


def _read_registry_paths(claude_root: Path) -> tuple[list[str], list[str], list[str]]:
    """Return (heavy_lane_paths, claude_system_paths, errors).

    Ad-hoc text scan rather than the full YAML parser, because the
    registry uses 2-level nesting (``groups.heavy_lane.paths``) that
    the stdlib parser doesn't model. We walk top-down: find
    ``groups:``; under it find ``heavy_lane:`` and ``claude_system:``;
    inside each find ``paths:`` and collect ``- path: "..."`` entries.
    """
    registry = claude_root / "path_registry.yaml"
    if not registry.is_file():
        return [], [], [_err(registry, "missing path_registry.yaml")]
    text = registry.read_text(encoding="utf-8")
    lines = text.splitlines()

    def _collect(group_name: str) -> list[str]:
        out: list[str] = []
        i = 0
        while i < len(lines):
            stripped = lines[i].strip()
            if stripped == f"{group_name}:":
                i += 1
                # Walk forward until we hit another top-level group
                # under groups: (i.e. a line at indent 2 ending with
                # `:` that isn't ``paths:``).
                while i < len(lines):
                    raw = lines[i]
                    s = raw.strip()
                    if not s or s.startswith("#"):
                        i += 1
                        continue
                    indent = len(raw) - len(raw.lstrip())
                    if indent <= 2 and s.endswith(":") and s != "paths:":
                        break
                    if s.startswith("- path:"):
                        _, _, value = s.partition(":")
                        v = value.strip()
                        if v.startswith('"') and v.endswith('"'):
                            v = v[1:-1]
                        if v:
                            out.append(v)
                    i += 1
                break
            i += 1
        return out

    heavy = _collect("heavy_lane")
    claude_sys = _collect("claude_system")
    return heavy, claude_sys, []


def _check_consumer_workflows_and_pr(
    target_dir: Path, claude_root: Path,
) -> list[str]:
    """Validate .github/workflows/* and pull_request_template.md against
    the registry. The Claude review workflow's path filter must equal
    heavy_lane ∪ claude_system; its permissions.contents must be
    ``read`` (never ``write``); its allowedTools must not contain any
    write/mutation surface. The PR template must contain a checkbox
    line for every heavy_lane path."""
    findings: list[str] = []
    heavy, claude_sys, errs = _read_registry_paths(claude_root)
    findings.extend(errs)
    expected_workflow_paths = list(heavy) + list(claude_sys)

    workflows_dir = target_dir / ".github" / "workflows"
    review_yml = workflows_dir / "claude-review-heavy-lane.yml"
    if not review_yml.is_file():
        findings.append(
            _err(review_yml, "missing claude-review-heavy-lane.yml")
        )
    else:
        text = review_yml.read_text(encoding="utf-8")
        # permissions.contents must NOT be write
        if "contents: write" in text:
            findings.append(
                _err(
                    review_yml,
                    "permissions.contents: write is forbidden (review-only)",
                )
            )
        # Hard rule for allowedTools — disallow any obvious mutation
        # tool surface in the Bash() entries.
        if "Bash(git commit" in text or "Bash(git push" in text:
            findings.append(
                _err(
                    review_yml,
                    "allowedTools must not include git mutation surface",
                )
            )
        # Extract every quoted path inside the ``on.pull_request.paths``
        # block. Cheap parse: pick lines between ``paths:`` and the next
        # zero-indent token.
        in_paths = False
        actual: list[str] = []
        for raw in text.splitlines():
            stripped = raw.strip()
            if not in_paths:
                if stripped == "paths:":
                    in_paths = True
                continue
            # Stop on the next sibling/parent key (a line whose first
            # non-space char is alphabetic at low indent).
            if stripped.startswith("#"):
                continue
            if stripped.startswith("- "):
                token = stripped[2:].strip()
                if token.startswith('"') and token.endswith('"'):
                    token = token[1:-1]
                actual.append(token)
                continue
            if stripped and not stripped.startswith("- ") and not raw.startswith(" "):
                break
            if stripped and stripped.endswith(":") and not stripped.startswith("- "):
                break
        if actual != expected_workflow_paths:
            findings.append(
                _err(
                    review_yml,
                    (
                        "paths filter drift: "
                        f"actual={actual!r} expected={expected_workflow_paths!r}"
                    ),
                )
            )

    secret_yml = workflows_dir / "secret-scan.yml"
    if not secret_yml.is_file():
        findings.append(
            _err(secret_yml, "missing secret-scan.yml")
        )

    ci_yml = workflows_dir / "ci.yml"
    if not ci_yml.is_file():
        findings.append(_err(ci_yml, "missing ci.yml"))

    pr_template = target_dir / ".github" / "pull_request_template.md"
    if not pr_template.is_file():
        findings.append(_err(pr_template, "missing pull_request_template.md"))
    else:
        text = pr_template.read_text(encoding="utf-8")
        for p in heavy:
            needle = f"- [ ] `{p}`"
            if needle not in text:
                findings.append(
                    _err(
                        pr_template,
                        f"missing heavy-lane checkbox for path {p!r}",
                    )
                )
    return findings


def main(argv: list[str] | None = None) -> int:
    import argparse as _argparse
    parser = _argparse.ArgumentParser(prog="check_manifests")
    parser.add_argument(
        "--target-dir",
        type=Path,
        default=None,
        help=(
            "Optional consumer-repo target. When supplied, the linter "
            "validates the consumer's rendered .claude/ surface "
            "(rules, agents, skills, hooks) instead of the dev system's "
            "own templates."
        ),
    )
    args = parser.parse_args(argv)

    failures: list[str] = []
    if args.target_dir is None:
        failures.extend(check_project_profile_example_parses())
        failures.extend(check_schema_pins_version_one())
        failures.extend(check_docs_templates_present())
    else:
        failures.extend(check_consumer_target(args.target_dir))
    if failures:
        for line in failures:
            print(line, file=sys.stderr)
        print(
            f"\ncheck_manifests: {len(failures)} defect(s) found",
            file=sys.stderr,
        )
        return 1
    print("check_manifests: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
