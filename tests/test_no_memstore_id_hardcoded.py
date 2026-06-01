"""D0a — sentinel: NO Anthropic memstore IDs are hardcoded in this repo.

Per the cloud-memory requirement from the D0a spec, the dev system
itself must never ship any consumer's memstore IDs. Sentinels enforce:
nowhere in the tracked tree may a string match the Anthropic memstore
ID shape (``memstore_<26-char alphanumeric>``).

Stdlib-only. Excludes this test file (which has to mention the regex
shape to do its job) and the docs/test-fixture surface that documents
the boundary policy in prose.
"""
from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]

# The Anthropic memstore ID shape (observed in the donor repo's
# documentation): ``memstore_`` + 24 base32-ish chars. We use a slightly
# wider regex (alphanumeric, 20+ chars) to catch any close variant a
# future contributor might paste.
_MEMSTORE_ID_RE = re.compile(r"\bmemstore_[A-Za-z0-9]{20,}\b")

# Files / directories where the *shape* of a memstore ID may legitimately
# appear in prose (this test file itself; the README's documentation of
# the policy). These are explicitly excluded from the scan.
_ALLOWLIST: tuple[str, ...] = (
    "tests/test_no_memstore_id_hardcoded.py",
)


def _scan_tracked_files() -> list[Path]:
    """Walk the repo tree and return paths to scan. Skips hidden git
    directories, virtualenvs, caches."""
    out: list[Path] = []
    for path in _REPO.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(_REPO)
        rel_str = str(rel)
        # Skip irrelevant directories.
        if any(part.startswith(".") and part not in (".github", ".gitignore")
               for part in rel.parts):
            continue
        if rel.parts and rel.parts[0] in {".git", ".venv", "venv",
                                          "__pycache__", ".pytest_cache",
                                          ".ruff_cache"}:
            continue
        if rel_str in _ALLOWLIST:
            continue
        out.append(path)
    return out


def test_no_memstore_id_in_any_tracked_file() -> None:
    findings: list[tuple[str, int]] = []
    for path in _scan_tracked_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for m in _MEMSTORE_ID_RE.finditer(text):
            # Report the path + line number; NEVER print the matched ID.
            line_no = text.count("\n", 0, m.start()) + 1
            findings.append((str(path.relative_to(_REPO)), line_no))
    assert not findings, (
        "Memstore-ID-shaped strings found in tracked files:\n  "
        + "\n  ".join(f"{p}:{ln}" for p, ln in findings)
        + "\nThe dev system must never ship a consumer's memstore IDs. "
        "If a future template needs a placeholder, render it from "
        "PROJECT_PROFILE.yaml at bootstrap time — never hardcode it."
    )


def test_allowlist_self_documents_the_regex() -> None:
    """This test file is allowlisted because it documents the regex
    shape. The allowlist must not silently grow."""
    assert _ALLOWLIST == (
        "tests/test_no_memstore_id_hardcoded.py",
    ), (
        "memstore-ID allowlist drifted; every additional entry must "
        "document why a literal memstore-ID-shape string appears in "
        "that file"
    )
