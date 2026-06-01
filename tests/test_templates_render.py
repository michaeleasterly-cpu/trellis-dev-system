"""D0c — direct template-rendering sentinel.

Renders each D0b template against ``PROJECT_PROFILE.example.yaml``
via the bootstrap module's pure-function API (no subprocess) so we
can assert structural invariants per-template without subprocess
overhead.

Stdlib-only.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_DOCS_DIR = _REPO / "devsystem" / "docs"
_PROFILE = _REPO / "PROJECT_PROFILE.example.yaml"
_BOOTSTRAP = _REPO / "devsystem" / "scripts" / "bootstrap_project.py"


def _load_bootstrap():
    spec = importlib.util.spec_from_file_location(
        "_pvds_bootstrap", _BOOTSTRAP,
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_pvds_bootstrap"] = mod
    spec.loader.exec_module(mod)
    return mod


_LEFTOVER = re.compile(r"\{\{\s*[A-Za-z0-9_]+\s*\}\}")

_DONOR_LEAK_PATTERNS: tuple[str, ...] = (
    "memstore_01P5Di",
    "memstore_01MzLu",
    "Alpaca",
    "FMP",
    "SEC/FRED",
    "Tradier",
    "EDGE_VALIDATION_PLAN",
    "tpcore",
    "short-term-trading-engine",
)


def _profile() -> dict:
    mod = _load_bootstrap()
    return mod.parse_yaml(_PROFILE.read_text(encoding="utf-8"))


def _render_each() -> dict[str, str]:
    mod = _load_bootstrap()
    profile = _profile()
    rendered: dict[str, str] = {}
    for path in sorted(_DOCS_DIR.glob("*.md.template")):
        rendered[path.name] = mod.render_template(
            path.read_text(encoding="utf-8"), profile,
        )
    return rendered


def test_every_template_renders_without_error() -> None:
    rendered = _render_each()
    assert rendered, "no templates rendered"
    for name, text in rendered.items():
        assert text.strip(), f"{name} rendered to empty string"


def test_no_unresolved_placeholder_in_any_rendered_template() -> None:
    findings: dict[str, list[str]] = {}
    for name, text in _render_each().items():
        leftovers = _LEFTOVER.findall(text)
        if leftovers:
            findings[name] = sorted(set(leftovers))
    assert not findings, (
        f"unresolved placeholders after rendering: {findings}"
    )


def test_no_donor_leak_in_any_rendered_template() -> None:
    findings: list[tuple[str, str]] = []
    for name, text in _render_each().items():
        for pat in _DONOR_LEAK_PATTERNS:
            if pat in text:
                findings.append((name, pat))
    assert not findings, (
        f"donor identifier leaked through render: {findings}"
    )


def test_conditional_block_markers_do_not_survive_rendering() -> None:
    """No ``<!-- BEGIN_API_MEMSTORES_* -->`` marker should survive
    rendering — the renderer either strips a block whole (markers
    included) or keeps the body and strips just the markers."""
    markers = (
        "<!-- BEGIN_API_MEMSTORES_DISABLED -->",
        "<!-- END_API_MEMSTORES_DISABLED -->",
        "<!-- BEGIN_API_MEMSTORES_ENABLED -->",
        "<!-- END_API_MEMSTORES_ENABLED -->",
    )
    for name, text in _render_each().items():
        for marker in markers:
            assert marker not in text, (
                f"{name} retained marker {marker!r} after rendering"
            )


def test_disabled_block_active_when_api_memstores_disabled() -> None:
    """Default example profile is api_memstores_enabled: false. The
    rendered MEMSTORE_HANDOFF must include the disabled-stub
    boundary explanation."""
    rendered = _render_each()
    handoff = rendered["MEMSTORE_HANDOFF.md.template"]
    assert "Cloud memstores are disabled for this project" in handoff
    # And the enabled-block's curl examples must NOT have been kept.
    assert "MEMSTORE_ID=" not in handoff, (
        "enabled-block leaked into rendered MEMSTORE_HANDOFF"
    )


def test_enabled_block_requires_memstore_ids_or_renderer_fails() -> None:
    """If a consumer enables api_memstores_enabled without supplying
    dev_memstore_id / agent_memstore_id, the renderer must raise."""
    mod = _load_bootstrap()
    profile = _profile()
    profile["memory_policy"]["api_memstores_enabled"] = True
    profile["memory_policy"]["dev_memstore_id"] = ""
    profile["memory_policy"]["agent_memstore_id"] = ""
    handoff_template = (
        _DOCS_DIR / "MEMSTORE_HANDOFF.md.template"
    ).read_text(encoding="utf-8")
    raised = False
    try:
        mod.render_template(handoff_template, profile)
    except ValueError as exc:
        raised = True
        assert "memstore" in str(exc).lower(), (
            f"unexpected error message: {exc}"
        )
    assert raised, (
        "renderer should fail closed when api_memstores_enabled is "
        "true but IDs are blank"
    )


def test_enabled_block_renders_when_consumer_supplies_ids() -> None:
    """Symmetric: a consumer that DOES supply both IDs gets the
    enabled-block body with placeholders substituted."""
    mod = _load_bootstrap()
    profile = _profile()
    profile["memory_policy"]["api_memstores_enabled"] = True
    profile["memory_policy"]["dev_memstore_id"] = "memstore_consumer_dev_xx"
    profile["memory_policy"]["agent_memstore_id"] = "memstore_consumer_agent_yy"
    profile["memory_policy"]["anthropic_beta_header"] = "managed-agents-2026-04-01"
    handoff_template = (
        _DOCS_DIR / "MEMSTORE_HANDOFF.md.template"
    ).read_text(encoding="utf-8")
    rendered = mod.render_template(handoff_template, profile)
    # Enabled-block body must now be present.
    assert "MEMSTORE_ID=" in rendered
    assert "memstore_consumer_dev_xx" in rendered
    assert "memstore_consumer_agent_yy" in rendered
    # Disabled stub must be gone.
    assert (
        "Cloud memstores are disabled for this project" not in rendered
    )
