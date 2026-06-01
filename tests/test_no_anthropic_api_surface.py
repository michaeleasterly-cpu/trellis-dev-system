"""D0a — sentinel: NO Anthropic API call surface in this repo.

The dev system never calls the Anthropic API and never writes to any
memstore. Bootstrap is a pure file-rendering operation. This sentinel
scans the tracked tree for Anthropic API URLs, beta-header strings,
and ANTHROPIC_API_KEY env-var references that would imply a runtime
caller is being staged in.

Allowed: documentation that explains the boundary (README, docs/) —
those files mention the API by name in prose without invoking it.

Stdlib-only.
"""
from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]

# Substrings that, if present in a code-shaped file, signal an actual
# API caller staging into the dev system. Docs that DOCUMENT the
# boundary are allowlisted by file extension below.
_API_INVOCATION_PATTERNS: tuple[str, ...] = (
    "api.anthropic.com",          # HTTPS endpoint
    "/v1/memory_stores/",         # memstore endpoint
    "/v1/messages",               # messages endpoint
    "/v1/complete",               # legacy completion endpoint
    "anthropic-version:",         # the beta-header *value* (lowercase)
    "anthropic-beta:",            # the beta-header *value* (lowercase)
)

# This test file mentions every forbidden substring above to do its job.
# Sibling sentinels that document the forbidden pattern shapes in their
# own bodies are allowlisted on the same principle:
#   * tests/test_portable_docs_templates.py — D0b template scanner
#     that forbids raw ANTHROPIC_API_KEY assignments in template bodies.
#   * tests/test_portable_scripts_contract.py — D0c devsystem-scripts
#     contract that documents the forbidden API-URL substrings in
#     ``_FORBIDDEN_RUNTIME_SUBSTRINGS``.
_ALLOWLIST: tuple[str, ...] = (
    "tests/test_no_anthropic_api_surface.py",
    "tests/test_portable_docs_templates.py",
    "tests/test_portable_scripts_contract.py",
    # D0d — the Claude-surface template sentinel documents the
    # forbidden hook-body patterns (including ``ANTHROPIC_API_KEY``)
    # in its ``_HOOK_FORBIDDEN_PATTERNS`` tuple. Same self-allowlist
    # principle as the other sibling sentinels.
    "tests/test_claude_surface_templates.py",
    # D0d — check_manifests.py runs the same hook-forbidden-command
    # scan at manifest-linter time and lists the forbidden patterns
    # (including ANTHROPIC_API_KEY) in its tuple. Same principle.
    "devsystem/scripts/check_manifests.py",
    # D0e — the Claude-review workflow template passes
    # ``${{ secrets.ANTHROPIC_API_KEY }}`` to the action's
    # ``anthropic_api_key:`` input. The token is fetched from the
    # GitHub secret store at workflow-run time; the file holds the
    # *name*, not the value. This is the legitimate, documented way
    # to wire the action — covered by the workflow's pinned
    # permissions block + the review-only allowedTools whitelist.
    "devsystem/github/workflows/claude-review-heavy-lane.yml.template",
)

# File extensions that are *prose* — allowed to mention these substrings
# in documentation context. Code-shaped files (.py, .sh, .yaml, .json,
# .toml) are NOT allowed to contain them.
#
# D0b extension: ``.md.template`` / ``.rst.template`` / ``.txt.template``
# are also prose — they render into prose markdown docs at bootstrap
# time. A template that documents the cloud-memstore curl protocol
# (under the ``api_memstores_enabled: true`` conditional block) is
# operator-readable documentation, not a runtime caller staged in.
_PROSE_EXTENSIONS: frozenset[str] = frozenset({".md", ".rst", ".txt"})
_PROSE_TEMPLATE_SUFFIXES: frozenset[str] = frozenset({
    ".md.template", ".rst.template", ".txt.template",
})


def _scan_targets() -> list[Path]:
    out: list[Path] = []
    for path in _REPO.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(_REPO)
        rel_str = str(rel)
        if any(part.startswith(".") and part not in (".github", ".gitignore")
               for part in rel.parts):
            continue
        if rel.parts and rel.parts[0] in {".git", ".venv", "venv",
                                          "__pycache__", ".pytest_cache",
                                          ".ruff_cache"}:
            continue
        if rel_str in _ALLOWLIST:
            continue
        # Prose extensions can mention the API in documentation.
        if path.suffix in _PROSE_EXTENSIONS:
            continue
        # D0b: prose-template suffixes (.md.template etc.) also count
        # as prose — they render into markdown docs at bootstrap time.
        if any(rel_str.endswith(s) for s in _PROSE_TEMPLATE_SUFFIXES):
            continue
        out.append(path)
    return out


def test_no_anthropic_api_surface_in_code_files() -> None:
    findings: list[tuple[str, int, str]] = []
    for path in _scan_targets():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        lowered = text.lower()
        for pat in _API_INVOCATION_PATTERNS:
            idx = lowered.find(pat)
            if idx >= 0:
                line_no = text.count("\n", 0, idx) + 1
                findings.append(
                    (str(path.relative_to(_REPO)), line_no, pat),
                )
    assert not findings, (
        "Anthropic API invocation surface found in code-shaped files:\n  "
        + "\n  ".join(
            f"{p}:{ln} matches {pat!r}" for p, ln, pat in findings
        )
        + "\nDev-system code must never call the Anthropic API; "
        "bootstrap is a pure file-rendering operation."
    )


def test_no_anthropic_api_key_env_reference_in_code() -> None:
    """``ANTHROPIC_API_KEY`` may appear in prose docs that describe the
    boundary, but never in code files that could imply a runtime
    caller staged in. Prose extensions are allowlisted by suffix."""
    findings: list[tuple[str, int]] = []
    for path in _scan_targets():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for m in re.finditer(r"\bANTHROPIC_API_KEY\b", text):
            line_no = text.count("\n", 0, m.start()) + 1
            findings.append((str(path.relative_to(_REPO)), line_no))
    assert not findings, (
        "ANTHROPIC_API_KEY referenced in code files:\n  "
        + "\n  ".join(f"{p}:{ln}" for p, ln in findings)
    )
