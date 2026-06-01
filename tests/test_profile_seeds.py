"""D0e — sentinels for the 4 profile seeds shipped under templates/.

Every profile seed must:

  * Parse with the dev-system's stdlib YAML parser.
  * Carry every key the example profile carries (canonical schema
    surface for consumers).
  * Pin ``schema_version: 1``.
  * Disable cloud memstores by default (``api_memstores_enabled: false``).
  * Leave both memstore IDs blank (the dev system does not ship STE
    memstore IDs).
  * Set ``review_mode: claude-review-only``.

Plus a per-seed sanity check: the named seed reflects the directory
name (e.g. python-railway seed has ``deployment: railway``).

Stdlib-only.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_TEMPLATES = _REPO / "templates"
_EXAMPLE = _REPO / "PROJECT_PROFILE.example.yaml"

sys.path.insert(0, str(_REPO / "devsystem" / "scripts"))
from bootstrap_project import parse_yaml  # noqa: E402

_EXPECTED_SEEDS: tuple[str, ...] = (
    "generic-python",
    "python-railway",
    "python-postgres",
    "fintech-research",
)


def _seed_keys() -> set[str]:
    """Schema keys every profile must define (anchored to the example)."""
    data = parse_yaml(_EXAMPLE.read_text(encoding="utf-8"))
    # ``output_paths`` may legitimately be present-and-empty; we still
    # require the key.
    return set(data.keys())


def test_all_four_seeds_present() -> None:
    for name in _EXPECTED_SEEDS:
        seed = _TEMPLATES / name / "PROJECT_PROFILE.yaml"
        assert seed.is_file(), f"missing profile seed: templates/{name}/PROJECT_PROFILE.yaml"


def test_every_seed_parses() -> None:
    for name in _EXPECTED_SEEDS:
        seed = _TEMPLATES / name / "PROJECT_PROFILE.yaml"
        data = parse_yaml(seed.read_text(encoding="utf-8"))
        assert isinstance(data, dict) and data, (
            f"{name}: parsed empty/None"
        )


def test_every_seed_carries_full_schema() -> None:
    required = _seed_keys()
    for name in _EXPECTED_SEEDS:
        seed = _TEMPLATES / name / "PROJECT_PROFILE.yaml"
        data = parse_yaml(seed.read_text(encoding="utf-8"))
        missing = required - set(data.keys())
        assert not missing, (
            f"{name}: missing required keys {sorted(missing)}"
        )


def test_every_seed_pins_schema_version_one() -> None:
    for name in _EXPECTED_SEEDS:
        seed = _TEMPLATES / name / "PROJECT_PROFILE.yaml"
        data = parse_yaml(seed.read_text(encoding="utf-8"))
        assert data.get("schema_version") == 1


def test_every_seed_disables_memstores_by_default() -> None:
    for name in _EXPECTED_SEEDS:
        seed = _TEMPLATES / name / "PROJECT_PROFILE.yaml"
        data = parse_yaml(seed.read_text(encoding="utf-8"))
        mem = data.get("memory_policy", {})
        assert mem.get("api_memstores_enabled") is False, (
            f"{name}: api_memstores_enabled must be false in the seed"
        )
        for key in ("dev_memstore_id", "agent_memstore_id"):
            assert not (mem.get(key) or ""), (
                f"{name}: {key} must be empty in the seed "
                "(consumer supplies their own if they ever flip enabled)"
            )


def test_every_seed_review_mode_claude_review_only() -> None:
    for name in _EXPECTED_SEEDS:
        seed = _TEMPLATES / name / "PROJECT_PROFILE.yaml"
        data = parse_yaml(seed.read_text(encoding="utf-8"))
        assert data.get("review_mode") == "claude-review-only"


def test_seed_deployment_matches_directory_name() -> None:
    expected = {
        "generic-python": ("none", "none"),       # (deployment, database)
        "python-railway": ("railway", "none"),
        "python-postgres": ("none", "postgres"),
        "fintech-research": ("railway", "postgres"),
    }
    for name, (deploy, db) in expected.items():
        seed = _TEMPLATES / name / "PROJECT_PROFILE.yaml"
        data = parse_yaml(seed.read_text(encoding="utf-8"))
        assert data.get("deployment") == deploy, (
            f"{name}: deployment {data.get('deployment')!r} != {deploy!r}"
        )
        assert data.get("database") == db, (
            f"{name}: database {data.get('database')!r} != {db!r}"
        )


def test_no_donor_repo_identifier_in_seeds() -> None:
    forbidden = (
        "memstore_01P5Di", "memstore_01MzLu",  # STE memstore IDs
        "tpcore", "short-term-trading-engine",
        "Alpaca", "FMP", "Tradier",            # vendor names
        "EDGE_VALIDATION_PLAN",
    )
    findings: list[tuple[str, str]] = []
    for name in _EXPECTED_SEEDS:
        seed = _TEMPLATES / name / "PROJECT_PROFILE.yaml"
        text = seed.read_text(encoding="utf-8")
        for pat in forbidden:
            if pat in text:
                findings.append((name, pat))
    assert not findings, (
        f"donor identifier(s) leaked into profile seeds: {findings}"
    )
