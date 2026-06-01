"""D0c — portable scripts contract sentinel.

Pins:

  * ``devsystem/scripts/`` contains the expected D0c script set.
  * Each ``.py`` script is stdlib-only (no forbidden imports).
  * No Anthropic API URL, memstore endpoint, or runtime caller
    surface in any script. (Same allowlist pattern as the existing
    ``tests/test_no_anthropic_api_surface.py`` sentinel — this one
    is scoped specifically to ``devsystem/scripts/`` to catch a
    future regression there even if a wider scan is relaxed.)
  * Shell wrapper has a shebang and is executable.

Stdlib-only.
"""
from __future__ import annotations

import ast
import re
import stat
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SCRIPTS = _REPO / "devsystem" / "scripts"

_EXPECTED_PY_SCRIPTS = (
    "bootstrap_project.py",
    "audit_project.py",
    "check_manifests.py",
    "claude_session_report.py",
)
_EXPECTED_SH_SCRIPTS = (
    "run_claude_session_report.sh",
)

_FORBIDDEN_IMPORTS: frozenset[str] = frozenset({
    "requests", "httpx", "urllib3", "aiohttp", "anthropic",
    "asyncpg", "sqlalchemy", "psycopg", "psycopg2",
    "tpcore", "ops",
})

_FORBIDDEN_RUNTIME_SUBSTRINGS: tuple[str, ...] = (
    "api.anthropic.com",
    "/v1/memory_stores/",
    "/v1/messages",
    "/v1/complete",
    # Memstore-ID shapes (24+ alphanumeric chars after `memstore_`):
    # a consumer's real IDs must never be hardcoded into a dev-system
    # script. The session-report script's redaction-pattern panel
    # mentions the ``memstore_`` prefix only as a regex shape, not
    # an actual ID, so we use a tighter regex below.
)

# Tighter memstore-ID detector: forbid only the long-alphanumeric form
# (≥ 20 chars after the underscore). This avoids false-positives on
# regex *patterns* like ``memstore_[A-Za-z0-9]{20,}`` that legitimately
# appear in the session-report redactor.
_MEMSTORE_ID_HARDCODE_RE = re.compile(r"\bmemstore_[A-Za-z0-9]{20,}\b")


def _py_scripts() -> list[Path]:
    return [_SCRIPTS / name for name in _EXPECTED_PY_SCRIPTS]


def test_all_expected_scripts_present_and_executable() -> None:
    for name in _EXPECTED_PY_SCRIPTS + _EXPECTED_SH_SCRIPTS:
        path = _SCRIPTS / name
        assert path.is_file(), f"missing {path.relative_to(_REPO)}"
        if name.endswith((".py", ".sh")):
            first_line = path.read_text(encoding="utf-8").splitlines()[0]
            assert first_line.startswith("#!"), (
                f"{name} missing shebang"
            )
            mode = path.stat().st_mode
            assert mode & stat.S_IXUSR, f"{name} not executable"


def test_py_scripts_have_no_forbidden_imports() -> None:
    findings: list[tuple[str, str]] = []
    for path in _py_scripts():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        seen: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    seen.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module is not None:
                    seen.add(node.module.split(".")[0])
        leaks = seen & _FORBIDDEN_IMPORTS
        for leak in sorted(leaks):
            findings.append((path.name, leak))
    assert not findings, (
        f"devsystem scripts import forbidden modules: {findings}"
    )


def test_py_scripts_have_no_anthropic_api_invocation_surface() -> None:
    findings: list[tuple[str, str]] = []
    for path in _py_scripts():
        text = path.read_text(encoding="utf-8")
        for substring in _FORBIDDEN_RUNTIME_SUBSTRINGS:
            if substring in text:
                findings.append((path.name, substring))
    assert not findings, (
        f"devsystem scripts contain runtime API invocation surface: "
        f"{findings}"
    )


def test_py_scripts_have_no_hardcoded_memstore_ids() -> None:
    findings: list[tuple[str, str]] = []
    for path in _py_scripts():
        text = path.read_text(encoding="utf-8")
        for m in _MEMSTORE_ID_HARDCODE_RE.finditer(text):
            findings.append(
                (path.name, f"line ~{text.count(chr(10), 0, m.start()) + 1}"),
            )
    assert not findings, (
        f"devsystem scripts contain hardcoded memstore IDs: {findings}"
    )


def _strip_comments(text: str, *, is_shell: bool) -> str:
    """Strip Python and shell comments before scanning for an actual
    command invocation. Comments that document what a script forbids
    (``# no railway up``) must not false-positive the scanner."""
    out: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        # Trailing inline comment: split on ' #' for shell, '  #' for
        # Python by convention. Conservative: split on ' #'.
        if " #" in line:
            line = line.split(" #", 1)[0]
        out.append(line)
    return "\n".join(out)


def test_no_docker_or_railway_up_invocation_in_scripts() -> None:
    """Scripts must not issue ``docker`` build/run/compose commands
    or ``railway up`` from a dev-system surface. Comment lines are
    stripped first so a script documenting what it forbids (``# no
    railway up``) does not false-positive."""
    findings: list[tuple[str, str]] = []
    for name in _EXPECTED_PY_SCRIPTS + _EXPECTED_SH_SCRIPTS:
        path = _SCRIPTS / name
        scan_text = _strip_comments(
            path.read_text(encoding="utf-8"),
            is_shell=name.endswith(".sh"),
        )
        for pattern, label in (
            (r"\bdocker\s+(?:run|build|compose|exec)\b", "docker invocation"),
            (r"\brailway\s+up\b", "railway up"),
        ):
            if re.search(pattern, scan_text):
                findings.append((name, label))
    assert not findings, (
        f"devsystem scripts contain deploy-command invocations: "
        f"{findings}"
    )


def test_shell_wrapper_invokes_underlying_script_safely() -> None:
    wrapper = _SCRIPTS / "run_claude_session_report.sh"
    text = wrapper.read_text(encoding="utf-8")
    assert "set -euo pipefail" in text, (
        "wrapper must use strict mode"
    )
    assert "claude_session_report.py" in text, (
        "wrapper must invoke claude_session_report.py"
    )
