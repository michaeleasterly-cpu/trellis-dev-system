"""D0e — sentinels for the GitHub workflow + PR template surface.

These tests scan the dev-system source templates (not consumer
output) for the invariants the workflow surface must hold for every
consumer project:

  * claude-review-heavy-lane.yml.template — review-only authority:
    permissions.contents: read (never write); allowedTools restricted
    to commenting + read-only Bash; explicit "no auto-fix / no
    auto-merge / no deployment" prompt language.
  * secret-scan.yml — gitleaks job runs on PRs and main; uploads
    SARIF; permissions: contents: read + security-events: write.
  * ci.yml.template — generic Python CI; uses
    ``{{ python_version }}`` and ``{{ test_command }}`` placeholders;
    no Docker build, no railway deploy, no DB service hardcoded.
  * pull_request_template.md.template — declares Lane checkboxes,
    a touched-risk-paths section consumed by
    ``heavy_lane_paths_checklist``, and security/memory/deployment
    impact sections.

Stdlib-only.
"""
from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_WORKFLOWS = _REPO / "devsystem" / "github" / "workflows"
_REVIEW_T = _WORKFLOWS / "claude-review-heavy-lane.yml.template"
_SECRET_SCAN = _WORKFLOWS / "secret-scan.yml"
_CI_T = _WORKFLOWS / "ci.yml.template"
_PR_T = _REPO / "devsystem" / "github" / "pull_request_template.md.template"


def test_review_template_exists_and_nonempty() -> None:
    assert _REVIEW_T.is_file(), f"missing {_REVIEW_T.relative_to(_REPO)}"
    assert _REVIEW_T.read_text(encoding="utf-8").strip(), "empty"


def test_review_template_permissions_read_only() -> None:
    text = _REVIEW_T.read_text(encoding="utf-8")
    assert "contents: read" in text, (
        "review workflow must pin contents: read"
    )
    assert "contents: write" not in text, (
        "review workflow must NEVER request contents: write"
    )


def test_review_template_allowed_tools_review_only() -> None:
    text = _REVIEW_T.read_text(encoding="utf-8")
    # Must have an --allowedTools restriction at all.
    assert "--allowedTools" in text, (
        "review workflow must specify --allowedTools whitelist"
    )
    # And must not allow obvious mutation surface.
    for forbidden in (
        "Bash(git commit",
        "Bash(git push",
        "Bash(gh pr create",
        "Bash(gh pr merge",
    ):
        assert forbidden not in text, (
            f"review workflow allowedTools must NOT include {forbidden!r}"
        )


def test_review_template_prompt_pins_review_only_authority() -> None:
    text = _REVIEW_T.read_text(encoding="utf-8")
    # Collapse whitespace so phrases that span a line break (the
    # template wraps at ~60 cols inside the prompt block) still match.
    collapsed = " ".join(text.split())
    for needle in (
        "review/comment-only",
        "do NOT change code",
        "do NOT auto-merge",
        "do NOT auto-fix",
        "REVIEW ONLY",
    ):
        assert needle in collapsed, (
            f"review prompt must explicitly say {needle!r}"
        )


def test_review_template_uses_path_filter_placeholder() -> None:
    """The paths filter is generated from the registry; the template
    must hand the rendering off via ``{{ workflow_paths_yaml }}``."""
    text = _REVIEW_T.read_text(encoding="utf-8")
    assert "{{ workflow_paths_yaml }}" in text


def test_secret_scan_exists_and_uses_pinned_gitleaks() -> None:
    assert _SECRET_SCAN.is_file()
    text = _SECRET_SCAN.read_text(encoding="utf-8")
    # Pinned binary version, not @latest.
    assert re.search(r"GITLEAKS_VERSION=\d+\.\d+\.\d+", text), (
        "secret-scan.yml must pin a specific gitleaks version"
    )
    assert "security-events: write" in text, (
        "secret-scan.yml must request security-events: write for SARIF upload"
    )
    assert "contents: read" in text


def test_ci_template_is_generic_python() -> None:
    assert _CI_T.is_file()
    text = _CI_T.read_text(encoding="utf-8")
    assert "{{ python_version }}" in text
    assert "{{ test_command }}" in text
    # No deployment / heavy infra defaults. Strip ``#``-comment lines
    # first so the explanatory comment block ("no docker, no DB
    # service by default") doesn't false-positive the scan.
    code_lines = [
        ln for ln in text.splitlines()
        if not ln.lstrip().startswith("#")
    ]
    code_only = "\n".join(code_lines).lower()
    for forbidden in (
        "docker", "railway up", "kubectl", "docker compose",
    ):
        assert forbidden not in code_only, (
            f"ci.yml.template must not hardcode {forbidden!r}"
        )


def test_pr_template_has_lane_and_paths_block() -> None:
    assert _PR_T.is_file()
    text = _PR_T.read_text(encoding="utf-8")
    for needle in (
        "## Lane",
        "## Touched risk paths",
        "{{ heavy_lane_paths_checklist }}",
        "## Security-sensitive impact",
        "## Memory impact",
        "## Deployment impact",
    ):
        assert needle in text, f"PR template must contain {needle!r}"
