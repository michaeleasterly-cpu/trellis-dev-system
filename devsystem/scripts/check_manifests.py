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
    """D0d — validate the rendered Claude surface in a CONSUMER repo
    (one that bootstrap_project.py wrote into). Read-only checks:

      * .claude/path_registry.yaml exists and parses.
      * .claude/rules/*.md have YAML frontmatter and non-empty body.
      * .claude/agents/*.md and .claude/skills/*/SKILL.md have YAML
        frontmatter and non-empty body.
      * .claude/hooks/*.sh have shebang + executable bit.
      * No forbidden command in any hook body (comments stripped).
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
