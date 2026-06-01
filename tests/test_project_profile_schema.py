"""D0a — PROJECT_PROFILE schema + example file sanity tests.

Stdlib-only. Validates the JSON Schema itself is well-formed and that
the example YAML carries every required top-level key (substring
presence — no PyYAML dependency in D0a per the operator spec).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SCHEMA = _REPO / "schemas" / "project_profile.schema.json"
_EXAMPLE = _REPO / "PROJECT_PROFILE.example.yaml"


def _load_schema() -> dict:
    assert _SCHEMA.is_file(), f"missing {_SCHEMA.relative_to(_REPO)}"
    return json.loads(_SCHEMA.read_text(encoding="utf-8"))


def _example_text() -> str:
    assert _EXAMPLE.is_file(), f"missing {_EXAMPLE.relative_to(_REPO)}"
    text = _EXAMPLE.read_text(encoding="utf-8")
    assert text.strip(), f"{_EXAMPLE.relative_to(_REPO)} is empty"
    return text


def test_schema_is_valid_json() -> None:
    data = _load_schema()
    assert "$schema" in data, "schema must declare its draft via $schema"
    assert data.get("type") == "object", "top-level schema must be an object"
    assert "required" in data and isinstance(data["required"], list)
    assert data["required"], "schema must list at least one required field"


def test_schema_pins_draft_07() -> None:
    """The schema is pinned to JSON Schema draft-07 so consumer
    projects can validate locally without pulling a draft-2020 schema
    validator into stdlib-only territory."""
    data = _load_schema()
    assert data["$schema"] == "http://json-schema.org/draft-07/schema#"


def test_schema_required_fields_match_d0_plan() -> None:
    data = _load_schema()
    expected = {
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
    }
    assert set(data["required"]) == expected, (
        f"required field set drift: extra="
        f"{set(data['required']) - expected} "
        f"missing={expected - set(data['required'])}"
    )


def test_schema_review_mode_is_claude_review_only_enum() -> None:
    """C0.4: the only legal review_mode is ``claude-review-only`` —
    auto-fix and auto-merge are operator-only and must not be a value
    the dev system can render."""
    data = _load_schema()
    enum = data["properties"]["review_mode"].get("enum")
    assert enum == ["claude-review-only"], (
        "review_mode must be a single-value enum locking in "
        "claude-review-only"
    )


def test_memory_policy_api_memstores_enabled_default_false() -> None:
    """The cloud memstore tier is OFF by default. Consumer projects
    opt in deliberately by setting api_memstores_enabled: true AND
    supplying their own dev_memstore_id + agent_memstore_id."""
    data = _load_schema()
    mem = data["properties"]["memory_policy"]
    assert "api_memstores_enabled" in mem["properties"]
    # The default-in-schema is enforced via the example file's value;
    # the conditional allOf in the schema enforces "if enabled, IDs
    # must be non-empty".
    text = _example_text()
    assert re.search(
        r"api_memstores_enabled:\s*false", text,
    ), "example must default api_memstores_enabled to false"


def test_example_yaml_contains_every_required_key() -> None:
    """Substring presence (stdlib-only). The example must surface every
    schema-required top-level key at column 0 so a consumer copying
    this file as a starting point gets every field."""
    text = _example_text()
    data = _load_schema()
    for key in data["required"]:
        # Match ``<key>:`` at column 0 (top-level YAML key).
        pattern = rf"^{re.escape(key)}\s*:"
        assert re.search(pattern, text, flags=re.MULTILINE), (
            f"example YAML missing top-level key {key!r}"
        )


def test_example_yaml_uses_placeholder_project_name() -> None:
    """The example file's project_name must be obvious-placeholder so
    a consumer cannot accidentally inherit the dev-system's own
    identity."""
    text = _example_text()
    m = re.search(r"^project_name:\s*(\S+)", text, flags=re.MULTILINE)
    assert m is not None, "could not parse project_name from example"
    value = m.group(1)
    assert value in {
        "my-project",
        "your-project",
        "PLACEHOLDER",
    }, f"example project_name {value!r} looks too specific"
