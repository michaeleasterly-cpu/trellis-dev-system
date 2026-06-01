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


def main() -> int:
    failures: list[str] = []
    failures.extend(check_project_profile_example_parses())
    failures.extend(check_schema_pins_version_one())
    failures.extend(check_docs_templates_present())
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
