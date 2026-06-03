"""D0g — sentinels for trellis-dev-system's own hardening surface.

These tests assert the dev system holds itself to the same secret-
handling and least-permission discipline its portable templates teach
consumers.

  * ``.github/workflows/secret-scan.yml`` exists.
  * Permissions are least-privilege (``contents: read`` plus the
    documented ``security-events: write`` for SARIF; no other write).
  * No deployment / docker / railway commands in the workflow body.
  * No GitHub token or secret value committed to the file.
  * The dev-system's own workflow stays byte-aligned with the portable
    consumer template it emits (the test compares the two and reports
    drift).
  * ``.gitleaks.toml`` keeps default rules enabled.
  * ``docs/REPO_HARDENING.md`` exists and names branch protection
    plus the two required checks.

Stdlib only.
"""
from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SECRET_SCAN_DEV = _REPO / ".github" / "workflows" / "secret-scan.yml"
_SECRET_SCAN_PORTABLE = (
    _REPO / "devsystem" / "github" / "workflows" / "secret-scan.yml"
)
_GITLEAKS_TOML = _REPO / ".gitleaks.toml"
_REPO_HARDENING = _REPO / "docs" / "REPO_HARDENING.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────
# secret-scan.yml (dev-system repo's own copy)
# ─────────────────────────────────────────────────────────────────────


def test_dev_system_secret_scan_workflow_exists() -> None:
    assert _SECRET_SCAN_DEV.is_file(), (
        f"missing {_SECRET_SCAN_DEV.relative_to(_REPO)}"
    )
    assert _read(_SECRET_SCAN_DEV).strip(), "empty"


def test_dev_system_secret_scan_least_permission() -> None:
    text = _read(_SECRET_SCAN_DEV)
    assert "contents: read" in text
    # SARIF upload to GitHub code-scanning legitimately needs this one
    # write scope, and only this one.
    assert "security-events: write" in text
    forbidden_writes = (
        "contents: write",
        "pull-requests: write",
        "issues: write",
        "actions: write",
        "deployments: write",
        "packages: write",
        "id-token: write",
    )
    for token in forbidden_writes:
        assert token not in text, (
            f"secret-scan must not request {token!r}"
        )


def test_dev_system_secret_scan_no_deploy_or_mutation() -> None:
    """Strip comment lines first; the doc-block legitimately mentions
    what the workflow forbids."""
    code_lines = [
        ln for ln in _read(_SECRET_SCAN_DEV).splitlines()
        if not ln.lstrip().startswith("#")
    ]
    code = "\n".join(code_lines).lower()
    for forbidden in (
        "docker run", "docker build", "docker compose",
        "railway up",
        "gh pr merge", "gh pr create",
        "git push", "git commit",
    ):
        assert forbidden not in code, (
            f"secret-scan body must not invoke {forbidden!r}"
        )


def test_dev_system_secret_scan_pins_gitleaks() -> None:
    text = _read(_SECRET_SCAN_DEV)
    m = re.search(r"GITLEAKS_VERSION=(\d+\.\d+\.\d+)", text)
    assert m, "secret-scan must pin GITLEAKS_VERSION=<semver>"
    # 8.x stream is the gitleaks generation we standardized on.
    assert m.group(1).startswith("8."), (
        f"gitleaks version drift: {m.group(1)} (expected 8.x)"
    )


def test_dev_system_secret_scan_no_committed_secrets() -> None:
    """The workflow file holds no GitHub PAT, no API key value, no
    raw bearer token. (``${{ secrets.* }}`` references *names* in the
    GitHub secret store, not values — those are allowed.)"""
    text = _read(_SECRET_SCAN_DEV)
    # Reject any bearer-token / PAT shape literal in the file.
    findings: list[str] = []
    for pattern in (
        r"ghp_[A-Za-z0-9]{20,}",          # GitHub PAT
        r"gho_[A-Za-z0-9]{20,}",          # GitHub OAuth
        r"github_pat_[A-Za-z0-9_]{20,}",  # GitHub fine-grained PAT
        r"sk-ant-[A-Za-z0-9\-_]{20,}",    # Anthropic API key
        r"AKIA[0-9A-Z]{16}",              # AWS access key
        r"Bearer\s+[A-Za-z0-9\.\-_]{20,}",  # raw bearer literal
    ):
        for m in re.finditer(pattern, text):
            findings.append(m.group(0))
    assert not findings, (
        f"secret-scan.yml contains committed-secret-shaped literal: "
        f"{findings}"
    )


def test_dev_system_secret_scan_aligned_with_portable_template() -> None:
    """The dev-system repo's own ``secret-scan.yml`` must stay aligned
    with the portable consumer-facing copy under
    ``devsystem/github/workflows/secret-scan.yml``. Lockstep alignment
    is the whole point of dogfooding — if they drift, the dev system
    is teaching a posture it doesn't follow itself.

    Allowed divergence: comment lines (each file's header documents
    its own role). Non-comment lines must match exactly.
    """
    assert _SECRET_SCAN_PORTABLE.is_file(), (
        "portable consumer template missing — D0e regressed?"
    )

    def _strip_comments(text: str) -> list[str]:
        return [
            ln for ln in text.splitlines()
            if not ln.lstrip().startswith("#")
        ]

    dev_lines = _strip_comments(_read(_SECRET_SCAN_DEV))
    portable_lines = _strip_comments(_read(_SECRET_SCAN_PORTABLE))
    assert dev_lines == portable_lines, (
        "dev-system secret-scan.yml has drifted from the portable "
        "consumer template. Re-align (or update both intentionally)."
    )


# ─────────────────────────────────────────────────────────────────────
# .gitleaks.toml
# ─────────────────────────────────────────────────────────────────────


def test_gitleaks_toml_exists_and_extends_defaults() -> None:
    assert _GITLEAKS_TOML.is_file()
    text = _read(_GITLEAKS_TOML)
    # Default rules must remain on. The TOML key is conventionally
    # ``useDefault = true`` under ``[extend]``.
    assert "useDefault = true" in text, (
        ".gitleaks.toml must keep default rules enabled "
        "(``useDefault = true`` under ``[extend]``)"
    )


def test_gitleaks_toml_no_real_credential_literal() -> None:
    text = _read(_GITLEAKS_TOML)
    for pattern in (
        r"ghp_[A-Za-z0-9]{20,}",
        r"sk-ant-[A-Za-z0-9\-_]{20,}",
        r"AKIA[0-9A-Z]{16}",
        r"postgres://[^/\s]+:[^@\s]+@",  # connstring with embedded creds
    ):
        m = re.search(pattern, text)
        assert m is None, (
            f".gitleaks.toml contains real-credential-shaped literal: "
            f"{m.group(0) if m else ''!r}"
        )


# ─────────────────────────────────────────────────────────────────────
# REPO_HARDENING.md
# ─────────────────────────────────────────────────────────────────────


def test_repo_hardening_doc_exists_and_names_protection() -> None:
    assert _REPO_HARDENING.is_file(), (
        f"missing {_REPO_HARDENING.relative_to(_REPO)}"
    )
    text = _read(_REPO_HARDENING)
    for needle in (
        "branch protection",
        "Require a pull request before merging",
        "Require status checks",
        "pytest + ruff + compile",
        "gitleaks",
        "Block force pushes",
    ):
        assert needle in text, (
            f"REPO_HARDENING.md must mention {needle!r}"
        )


def test_repo_hardening_doc_holds_no_credentials() -> None:
    text = _read(_REPO_HARDENING)
    for pattern in (
        r"ghp_[A-Za-z0-9]{20,}",
        r"gho_[A-Za-z0-9]{20,}",
        r"github_pat_[A-Za-z0-9_]{20,}",
        r"sk-ant-[A-Za-z0-9\-_]{20,}",
        r"AKIA[0-9A-Z]{16}",
        r"Bearer\s+[A-Za-z0-9\.\-_]{20,}",
    ):
        m = re.search(pattern, text)
        assert m is None, (
            f"REPO_HARDENING.md contains committed-secret literal: "
            f"{m.group(0) if m else ''!r}"
        )
