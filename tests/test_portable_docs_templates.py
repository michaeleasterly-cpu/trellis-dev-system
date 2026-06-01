"""D0b — portable docs template sentinels.

Pins that the 5 portable docs templates extracted from the donor repo
are present, generalized with the right placeholders, free of any
donor-repo identifier leak, and carry the load-bearing concepts
(cascade layers, finding taxonomy, lane vocabulary, ceiling
references, forbidden-content lists).

Stdlib-only (pathlib + re).
"""
from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_DOCS_DIR = _REPO / "devsystem" / "docs"

_TEMPLATES = {
    "DEV_PIPELINE_STANDARD": _DOCS_DIR / "DEV_PIPELINE_STANDARD.md.template",
    "MEMSTORE_HANDOFF": _DOCS_DIR / "MEMSTORE_HANDOFF.md.template",
    "MEMORY_MAINTENANCE": _DOCS_DIR / "MEMORY_MAINTENANCE.md.template",
    "SECURITY_GUIDANCE": _DOCS_DIR / "SECURITY_GUIDANCE.md.template",
    "CLAUDE_SESSION_OBSERVABILITY": _DOCS_DIR / "CLAUDE_SESSION_OBSERVABILITY.md.template",
}

# Donor-repo identifier shapes that must NOT appear in templates.
# `short-term-trading-engine` is forbidden in template bodies but
# allowed in the dev-system README's donor-relationship prose (that
# file is excluded by virtue of not being in _TEMPLATES).
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


def _text(name: str) -> str:
    path = _TEMPLATES[name]
    assert path.is_file(), f"missing template: {path.relative_to(_REPO)}"
    text = path.read_text(encoding="utf-8")
    assert text.strip(), f"empty template: {path.relative_to(_REPO)}"
    return text


# ─────────────────────────────────────────────────────────────────────
# Presence + structural sanity
# ─────────────────────────────────────────────────────────────────────

def test_all_five_portable_docs_templates_present() -> None:
    for name in _TEMPLATES:
        _text(name)


def test_no_donor_repo_identifier_leaks_into_any_template() -> None:
    """No donor-repo identifier (memstore IDs, Alpaca/FMP/SEC/FRED/
    Tradier, tpcore, EDGE_VALIDATION_PLAN, short-term-trading-engine)
    may appear in any template body."""
    findings: list[tuple[str, str, int]] = []
    for name, path in _TEMPLATES.items():
        text = path.read_text(encoding="utf-8")
        for pat in _DONOR_LEAK_PATTERNS:
            idx = text.find(pat)
            if idx >= 0:
                line = text.count("\n", 0, idx) + 1
                findings.append((name, pat, line))
    assert not findings, (
        "Donor-repo identifier leaked into template body:\n  "
        + "\n  ".join(
            f"{name} line {line}: {pat!r}" for name, pat, line in findings
        )
    )


# ─────────────────────────────────────────────────────────────────────
# Per-template placeholder + concept assertions
# ─────────────────────────────────────────────────────────────────────

def test_dev_pipeline_standard_names_three_lanes_and_placeholders() -> None:
    text = _text("DEV_PIPELINE_STANDARD")
    # The lane model must survive — fast / default / heavy.
    for lane in ("Fast lane", "Default lane", "Heavy lane"):
        assert lane in text, (
            f"DEV_PIPELINE_STANDARD template missing {lane!r}"
        )
    # Placeholders that drive heavy-lane content from PROJECT_PROFILE.
    for placeholder in (
        "{{ project_name }}",
        "{{ heavy_lane_paths_markdown }}",
        "{{ review_mode }}",
    ):
        assert placeholder in text, (
            f"DEV_PIPELINE_STANDARD template missing placeholder "
            f"{placeholder!r}"
        )


def test_memstore_handoff_has_4_tier_model_and_conditional_blocks() -> None:
    text = _text("MEMSTORE_HANDOFF")
    # 4-tier model.
    for marker in ("four-tier", "Tier", "memory boundary"):
        assert marker.lower() in text.lower(), (
            f"MEMSTORE_HANDOFF template missing concept {marker!r}"
        )
    # The two conditional block markers for renderer-driven section
    # selection (api_memstores_enabled false/true).
    for marker in (
        "<!-- BEGIN_API_MEMSTORES_DISABLED -->",
        "<!-- END_API_MEMSTORES_DISABLED -->",
        "<!-- BEGIN_API_MEMSTORES_ENABLED -->",
        "<!-- END_API_MEMSTORES_ENABLED -->",
    ):
        assert marker in text, (
            f"MEMSTORE_HANDOFF template missing conditional marker "
            f"{marker!r}"
        )
    # Cloud memstore IDs must be placeholders, never real IDs.
    for placeholder in (
        "{{ dev_memstore_id }}",
        "{{ agent_memstore_id }}",
        "{{ anthropic_beta_header }}",
        "{{ project_name }}",
        "{{ home_session_path }}",
        "{{ local_memory_limit_bytes }}",
    ):
        assert placeholder in text, (
            f"MEMSTORE_HANDOFF template missing placeholder "
            f"{placeholder!r}"
        )
    # Default-false stance must be explicit.
    assert "OFF by default" in text or "off by default" in text, (
        "MEMSTORE_HANDOFF template must state api_memstores_enabled "
        "is OFF by default"
    )
    # And the bootstrap-doesn't-call-API guarantee must be present.
    # Permit markdown bold / em emphasis between words by stripping
    # ``**`` markers before matching the phrase.
    text_no_emphasis = text.replace("**", "").replace("*", "")
    assert re.search(
        r"(?:does\s+not|never)\s+call(?:s)?\s+the\s+Anthropic\s+API",
        text_no_emphasis,
        re.IGNORECASE,
    ), "MEMSTORE_HANDOFF template must state bootstrap never calls the Anthropic API"


def test_memory_maintenance_template_references_size_placeholder() -> None:
    text = _text("MEMORY_MAINTENANCE")
    for placeholder in (
        "{{ project_name }}",
        "{{ home_session_path }}",
        "{{ local_memory_limit_bytes }}",
    ):
        assert placeholder in text, (
            f"MEMORY_MAINTENANCE template missing placeholder "
            f"{placeholder!r}"
        )
    # Structural-check procedure must survive.
    for concept in ("Trigger", "Procedure", "Acceptance"):
        assert concept in text, (
            f"MEMORY_MAINTENANCE template missing concept {concept!r}"
        )


def test_security_guidance_template_names_taxonomy_and_cascade() -> None:
    text = _text("SECURITY_GUIDANCE")
    # 3-layer cascade survives.
    lowered = text.lower()
    for layer in ("static", "claude review", "operator gate"):
        assert layer in lowered, (
            f"SECURITY_GUIDANCE template missing cascade layer {layer!r}"
        )
    # Finding taxonomy survives.
    for klass in ("BLOCKING", "NEEDS_OPERATOR_REVIEW", "ADVISORY"):
        assert klass in text, (
            f"SECURITY_GUIDANCE template missing finding class {klass!r}"
        )
    # Project-specific placeholders.
    for placeholder in (
        "{{ project_name }}",
        "{{ security_sensitive_paths_markdown }}",
        "{{ forbidden_assumptions_markdown }}",
        "{{ review_mode }}",
        "{{ home_session_path }}",
    ):
        assert placeholder in text, (
            f"SECURITY_GUIDANCE template missing placeholder "
            f"{placeholder!r}"
        )


def test_claude_session_observability_template_names_forbidden_data() -> None:
    text = _text("CLAUDE_SESSION_OBSERVABILITY")
    # The metadata-only / report-only character must survive.
    for concept in (
        "metadata-only",
        "report-only",
        "Never calls the Anthropic API",
        "Never writes to Anthropic memstores",
        "Never writes to the project database",
    ):
        assert concept in text, (
            f"CLAUDE_SESSION_OBSERVABILITY template missing concept "
            f"{concept!r}"
        )
    # No raw transcript / prompt / tool payload language survives.
    for forbidden_marker in (
        "raw transcript",
        "prompt",
        "tool_use",
    ):
        assert forbidden_marker in text.lower(), (
            f"CLAUDE_SESSION_OBSERVABILITY template missing "
            f"forbidden-data concept {forbidden_marker!r}"
        )
    # Project-specific placeholders.
    for placeholder in (
        "{{ project_name }}",
        "{{ home_session_path }}",
        "{{ operator_reports_path }}",
    ):
        assert placeholder in text, (
            f"CLAUDE_SESSION_OBSERVABILITY template missing placeholder "
            f"{placeholder!r}"
        )


# ─────────────────────────────────────────────────────────────────────
# Cross-template invariants
# ─────────────────────────────────────────────────────────────────────

def test_no_raw_anthropic_api_key_value_in_templates() -> None:
    """``ANTHROPIC_API_KEY`` may appear as an env-variable name in the
    MEMSTORE_HANDOFF curl examples (it's the standard documentation
    pattern), but no raw value (the env *name* without a $ or curly
    interpolation marker but FOLLOWED BY = and a real-looking value)
    may appear."""
    for name, path in _TEMPLATES.items():
        text = path.read_text(encoding="utf-8")
        # Forbid `ANTHROPIC_API_KEY=sk-...` literal assignment in any
        # template.
        bad = re.findall(
            r"ANTHROPIC_API_KEY\s*=\s*[A-Za-z0-9_\-]{8,}", text,
        )
        assert not bad, (
            f"{name} template contains a raw ANTHROPIC_API_KEY "
            "assignment-looking value (count={len(bad)})"
        )


def test_all_templates_use_project_name_placeholder() -> None:
    """Every portable template must reference the project name via
    the placeholder so a generated consumer doc never claims to be
    about the dev system itself."""
    for name in _TEMPLATES:
        text = _text(name)
        assert "{{ project_name }}" in text, (
            f"{name} template missing {{ project_name }} placeholder"
        )
