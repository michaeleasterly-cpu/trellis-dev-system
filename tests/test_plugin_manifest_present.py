"""Phase-3 — sentinels for the Anthropic-canonical alignment surface.

Pins:

  * ``.claude-plugin/plugin.json`` — the minimal plugin manifest that
    makes Trellis marketplace-discoverable (STE audit §3.4). Required
    keys: ``name`` / ``description`` / ``version`` / ``author``.
  * ``docs/ANTHROPIC_CANONICAL_ALIGNMENT.md`` — the Phase-3 deliverable
    doc, present and naming the four changes + the donor reference.

Stdlib-only.
"""
from __future__ import annotations

import json
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_PLUGIN_MANIFEST = _REPO / ".claude-plugin" / "plugin.json"
_ALIGNMENT_DOC = _REPO / "docs" / "ANTHROPIC_CANONICAL_ALIGNMENT.md"


def test_plugin_manifest_present_and_valid_json() -> None:
    assert _PLUGIN_MANIFEST.is_file(), (
        f"missing {_PLUGIN_MANIFEST.relative_to(_REPO)}"
    )
    data = json.loads(_PLUGIN_MANIFEST.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "plugin.json must be a JSON object"


def test_plugin_manifest_has_required_keys() -> None:
    data = json.loads(_PLUGIN_MANIFEST.read_text(encoding="utf-8"))
    for key in ("name", "description", "version", "author"):
        assert key in data, f"plugin.json missing required key {key!r}"
        assert str(data[key]).strip(), f"plugin.json {key!r} is empty"
    assert data["name"] == "trellis-dev-system", (
        f"plugin.json name drift: {data['name']!r}"
    )


def test_alignment_doc_present_and_names_changes() -> None:
    assert _ALIGNMENT_DOC.is_file(), (
        f"missing {_ALIGNMENT_DOC.relative_to(_REPO)}"
    )
    text = _ALIGNMENT_DOC.read_text(encoding="utf-8")
    assert text.strip(), "alignment doc is empty"
    for needle in (
        "permissions.deny",
        "permissions.defaultMode",
        "worktree.baseRef",
        "plugin.json",
        # Cites the phase-1+2 reference audit.
        "2026-06-04-anthropic-canonical-pattern-alignment-audit.md",
    ):
        assert needle in text, (
            f"ANTHROPIC_CANONICAL_ALIGNMENT.md must mention {needle!r}"
        )
