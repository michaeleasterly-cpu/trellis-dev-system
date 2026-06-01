"""D0c — bootstrap_project.py end-to-end sentinel.

Replaces the D0a xfail placeholder. Bootstraps a dummy consumer
project into ``tmp_path`` and asserts the rendering contract:

* All five D0b docs are rendered.
* No ``{{ placeholder }}`` survives.
* The api_memstores_disabled stub block is present in the rendered
  ``MEMSTORE_HANDOFF.md`` (default profile has
  ``api_memstores_enabled: false``).
* No donor-repo memstore IDs, no STE trading/platform identifiers.
* PROJECT_PROFILE.yaml is copied into the target verbatim.

Stdlib-only.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_BOOTSTRAP = _REPO / "devsystem" / "scripts" / "bootstrap_project.py"
_PROFILE = _REPO / "PROJECT_PROFILE.example.yaml"

_EXPECTED_DOCS = (
    "DEV_PIPELINE_STANDARD.md",
    "MEMSTORE_HANDOFF.md",
    "MEMORY_MAINTENANCE.md",
    "SECURITY_GUIDANCE.md",
    "CLAUDE_SESSION_OBSERVABILITY.md",
)

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


def _run_bootstrap(target_dir: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable, str(_BOOTSTRAP),
        "--profile-file", str(_PROFILE),
        "--target-dir", str(target_dir),
        *extra,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def test_bootstrap_script_present_and_runnable() -> None:
    """Counterpart to the D0a xfail placeholder, now passing."""
    assert _BOOTSTRAP.is_file(), f"missing {_BOOTSTRAP.relative_to(_REPO)}"
    src = _BOOTSTRAP.read_text(encoding="utf-8")
    assert src.startswith("#!"), "bootstrap_project.py must have a shebang"
    mode = _BOOTSTRAP.stat().st_mode
    assert mode & 0o111, "bootstrap_project.py must be executable"


def test_dry_run_writes_no_files(tmp_path: Path) -> None:
    target = tmp_path / "dummy"
    proc = _run_bootstrap(target, "--dry-run")
    assert proc.returncode == 0, proc.stderr
    assert not target.exists() or not any(target.iterdir())
    assert "dry-run" in proc.stdout.lower()


def test_real_bootstrap_renders_all_five_docs(tmp_path: Path) -> None:
    target = tmp_path / "dummy"
    proc = _run_bootstrap(target)
    assert proc.returncode == 0, proc.stderr
    docs_dir = target / "docs"
    assert docs_dir.is_dir(), "docs/ not created"
    for name in _EXPECTED_DOCS:
        path = docs_dir / name
        assert path.is_file(), f"missing rendered doc: {name}"
        text = path.read_text(encoding="utf-8")
        assert text.strip(), f"rendered doc is empty: {name}"


def test_no_unresolved_placeholder_survives(tmp_path: Path) -> None:
    """Every ``{{ var }}`` placeholder must have been substituted."""
    target = tmp_path / "dummy"
    _run_bootstrap(target)
    leftover_re = re.compile(r"\{\{\s*[A-Za-z0-9_]+\s*\}\}")
    findings: list[tuple[str, list[str]]] = []
    for name in _EXPECTED_DOCS:
        text = (target / "docs" / name).read_text(encoding="utf-8")
        leftovers = leftover_re.findall(text)
        if leftovers:
            findings.append((name, sorted(set(leftovers))))
    assert not findings, (
        f"unresolved placeholders survived rendering: {findings}"
    )


def test_disabled_memstore_stub_active_by_default(tmp_path: Path) -> None:
    """The example profile has ``api_memstores_enabled: false``. The
    rendered MEMSTORE_HANDOFF must contain the disabled-stub body and
    must NOT contain the enabled-block body."""
    target = tmp_path / "dummy"
    _run_bootstrap(target)
    handoff = (target / "docs" / "MEMSTORE_HANDOFF.md").read_text(
        encoding="utf-8",
    )
    assert "Cloud memstores are disabled for this project" in handoff, (
        "disabled-stub body missing from rendered MEMSTORE_HANDOFF.md"
    )
    # The enabled-block specifically lists the dev/agent memstore IDs
    # under MEMSTORE_ID variables — those must not survive when the
    # block was stripped.
    assert "MEMSTORE_ID=" not in handoff, (
        "enabled-block content leaked into rendered MEMSTORE_HANDOFF.md "
        "despite api_memstores_enabled: false"
    )
    # And no conditional-block markers survive either way.
    for marker in (
        "<!-- BEGIN_API_MEMSTORES_DISABLED -->",
        "<!-- END_API_MEMSTORES_DISABLED -->",
        "<!-- BEGIN_API_MEMSTORES_ENABLED -->",
        "<!-- END_API_MEMSTORES_ENABLED -->",
    ):
        assert marker not in handoff, (
            f"conditional-block marker {marker!r} survived rendering"
        )


def test_enabled_memstore_block_requires_ids(tmp_path: Path) -> None:
    """If a consumer flips ``api_memstores_enabled: true`` without
    supplying ``dev_memstore_id`` and ``agent_memstore_id``, bootstrap
    must fail closed — no half-rendered cloud-memory section, no
    placeholder leak."""
    # Author a synthetic profile with the flag enabled but IDs blank.
    bad_profile = tmp_path / "bad-profile.yaml"
    text = _PROFILE.read_text(encoding="utf-8")
    text = re.sub(
        r"api_memstores_enabled:\s*false",
        "api_memstores_enabled: true",
        text,
    )
    bad_profile.write_text(text, encoding="utf-8")
    target = tmp_path / "dummy-bad"
    proc = subprocess.run(
        [
            sys.executable, str(_BOOTSTRAP),
            "--profile-file", str(bad_profile),
            "--target-dir", str(target),
        ],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode != 0, (
        "bootstrap should have failed closed but exited 0"
    )
    assert (
        "dev_memstore_id" in proc.stderr
        or "memstore" in proc.stderr.lower()
    ), f"error message missing memstore-ID context: {proc.stderr!r}"


def test_no_donor_repo_identifier_leaks_into_dummy(tmp_path: Path) -> None:
    target = tmp_path / "dummy"
    _run_bootstrap(target)
    findings: list[tuple[str, str, int]] = []
    for sub in ("docs", ".claude"):
        sub_dir = target / sub
        if not sub_dir.is_dir():
            continue
        for path in sub_dir.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            for pat in _DONOR_LEAK_PATTERNS:
                idx = text.find(pat)
                if idx >= 0:
                    line_no = text.count("\n", 0, idx) + 1
                    findings.append(
                        (str(path.relative_to(target)), pat, line_no),
                    )
    assert not findings, (
        "donor identifier leaked into rendered dummy repo:\n  "
        + "\n  ".join(
            f"{name} line {ln}: {pat!r}" for name, pat, ln in findings
        )
    )


# ─────────────────────────────────────────────────────────────────────
# D0d — Claude surface rendering
# ─────────────────────────────────────────────────────────────────────

_EXPECTED_CLAUDE_TREE = (
    ".claude/path_registry.yaml",
    ".claude/settings.json",
    ".claude/rules/heavy-lane.md",
    ".claude/rules/security-guidance.md",
    ".claude/skills/security-review/SKILL.md",
    ".claude/hooks/block-git-checkout.sh",
    ".claude/hooks/session-start.sh",
    ".claude/hooks/block-pytest-subset-when-critical.sh",
    ".claude/agents/spec-reviewer.md",
    ".claude/agents/code-quality-reviewer.md",
)

_EXPECTED_GITHUB_TREE = (
    ".github/workflows/ci.yml",
    ".github/workflows/secret-scan.yml",
    ".github/workflows/claude-review-heavy-lane.yml",
    ".github/pull_request_template.md",
)


def test_bootstrap_renders_full_claude_surface(tmp_path: Path) -> None:
    target = tmp_path / "dummy"
    _run_bootstrap(target)
    for rel in _EXPECTED_CLAUDE_TREE:
        assert (target / rel).is_file(), (
            f"missing rendered Claude-surface artifact: {rel}"
        )


def test_rendered_hooks_are_executable(tmp_path: Path) -> None:
    target = tmp_path / "dummy"
    _run_bootstrap(target)
    for hook in (target / ".claude" / "hooks").glob("*.sh"):
        mode = hook.stat().st_mode
        assert mode & 0o111, f"rendered hook not executable: {hook.name}"


def test_no_unresolved_placeholder_in_rendered_claude_surface(
    tmp_path: Path,
) -> None:
    """The renderer-internal leftover check covers ``.md.template``
    files. This test additionally scans the rendered ``.claude/`` tree
    for any ``{{ word }}`` pattern (the same shape the renderer would
    have raised on). ``${{ secrets.* }}`` style GitHub Actions
    references DO NOT match because of the leading ``$`` AND because
    the content (``secrets.*``) contains non-alphanumeric chars."""
    target = tmp_path / "dummy"
    _run_bootstrap(target)
    leftover_re = re.compile(r"(?<!\$)\{\{\s*[A-Za-z0-9_]+\s*\}\}")
    findings: list[tuple[str, list[str]]] = []
    for path in (target / ".claude").rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        leftovers = leftover_re.findall(text)
        if leftovers:
            findings.append((str(path.relative_to(target)), sorted(set(leftovers))))
    assert not findings, (
        f"unresolved placeholders in rendered .claude/: {findings}"
    )


def test_rendered_path_registry_lists_critical_paths(tmp_path: Path) -> None:
    """A consumer's critical_paths must show up under
    ``groups.heavy_lane.paths`` in the rendered path registry."""
    target = tmp_path / "dummy"
    _run_bootstrap(target)
    registry = (target / ".claude" / "path_registry.yaml").read_text(
        encoding="utf-8",
    )
    # Example profile has critical_paths = src/auth/**, src/billing/**,
    # migrations/**, plus deployment_specific_paths railway.json + Procfile.
    for expected in (
        '- path: "src/auth/**"',
        '- path: "src/billing/**"',
        '- path: "migrations/**"',
        '- path: "railway.json"',
    ):
        assert expected in registry, (
            f"rendered path_registry missing: {expected}"
        )


def test_security_review_skill_copied_verbatim(tmp_path: Path) -> None:
    """The security-review skill is verbatim-copied (not a template).
    The rendered consumer copy must byte-match the dev-system source."""
    target = tmp_path / "dummy"
    _run_bootstrap(target)
    rendered = (
        target / ".claude" / "skills" / "security-review" / "SKILL.md"
    ).read_text(encoding="utf-8")
    source = (
        _REPO / "devsystem" / "claude" / "skills"
        / "security-review" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert rendered == source, "security-review skill diverged"


def test_project_profile_yaml_copied_into_target(tmp_path: Path) -> None:
    target = tmp_path / "dummy"
    _run_bootstrap(target)
    copied = target / "PROJECT_PROFILE.yaml"
    assert copied.is_file(), "PROJECT_PROFILE.yaml not copied into target"
    assert (
        copied.read_bytes() == _PROFILE.read_bytes()
    ), "PROJECT_PROFILE.yaml copied differs from source"


def test_bootstrap_renders_github_surface(tmp_path: Path) -> None:
    """D0e — workflow templates + PR template are rendered."""
    target = tmp_path / "dummy"
    _run_bootstrap(target)
    for rel in _EXPECTED_GITHUB_TREE:
        assert (target / rel).is_file(), (
            f"missing rendered GitHub-surface artifact: {rel}"
        )


def test_settings_json_parses_and_references_rendered_hooks(
    tmp_path: Path,
) -> None:
    """D0e — .claude/settings.json is valid JSON and every hook script
    it references exists in the rendered tree."""
    import json
    target = tmp_path / "dummy"
    _run_bootstrap(target)
    settings = target / ".claude" / "settings.json"
    assert settings.is_file()
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert "hooks" in data
    hooks_root = target / ".claude"
    referenced: list[str] = []
    for event, entries in data["hooks"].items():
        for entry in entries:
            for hook in entry.get("hooks", []) or []:
                cmd = hook["command"]
                marker = "$CLAUDE_PROJECT_DIR/"
                assert marker in cmd, f"{event} cmd missing marker: {cmd}"
                referenced.append(cmd.split(marker, 1)[1])
    for rel in referenced:
        assert (hooks_root.parent / rel).is_file(), (
            f"settings.json references missing hook: {rel}"
        )


def test_review_workflow_paths_filter_matches_registry(
    tmp_path: Path,
) -> None:
    """D0e — workflow path filter is heavy_lane ∪ claude_system."""
    target = tmp_path / "dummy"
    _run_bootstrap(target)
    workflow = (
        target / ".github" / "workflows" / "claude-review-heavy-lane.yml"
    ).read_text(encoding="utf-8")
    # Example profile critical paths must show up.
    for needle in (
        '- "src/auth/**"',
        '- "src/billing/**"',
        '- "migrations/**"',
        '- "railway.json"',
        '- ".claude/rules/**"',
        '- ".github/workflows/**"',
    ):
        assert needle in workflow, (
            f"workflow paths filter missing: {needle}"
        )


def test_pr_template_has_heavy_lane_checkboxes(tmp_path: Path) -> None:
    target = tmp_path / "dummy"
    _run_bootstrap(target)
    pr = (target / ".github" / "pull_request_template.md").read_text(
        encoding="utf-8",
    )
    for path in ("src/auth/**", "src/billing/**", "migrations/**", "railway.json"):
        assert f"- [ ] `{path}`" in pr, (
            f"PR template missing heavy-lane checkbox for {path!r}"
        )


# ─────────────────────────────────────────────────────────────────────
# D0e — --profile seed flag
# ─────────────────────────────────────────────────────────────────────


def test_profile_flag_renders_consumer_tree(tmp_path: Path) -> None:
    """``--profile generic-python`` (no --profile-file) renders a
    full consumer tree from the seed alone."""
    target = tmp_path / "dummy-seed"
    proc = subprocess.run(
        [
            sys.executable, str(_BOOTSTRAP),
            "--profile", "generic-python",
            "--target-dir", str(target),
        ],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    for rel in (
        "docs/DEV_PIPELINE_STANDARD.md",
        ".claude/path_registry.yaml",
        ".claude/settings.json",
        ".github/workflows/ci.yml",
        ".github/workflows/claude-review-heavy-lane.yml",
        ".github/pull_request_template.md",
        "PROJECT_PROFILE.yaml",
    ):
        assert (target / rel).is_file(), f"missing: {rel}"


def test_bootstrap_requires_profile_or_profile_file(tmp_path: Path) -> None:
    target = tmp_path / "dummy-empty"
    proc = subprocess.run(
        [
            sys.executable, str(_BOOTSTRAP),
            "--target-dir", str(target),
        ],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode != 0, "expected failure when no profile supplied"
    assert "profile" in proc.stderr.lower()


def test_force_required_to_overwrite_nonempty(tmp_path: Path) -> None:
    target = tmp_path / "dummy"
    # First bootstrap.
    proc1 = _run_bootstrap(target)
    assert proc1.returncode == 0
    # Second bootstrap without --force must fail.
    proc2 = _run_bootstrap(target)
    assert proc2.returncode != 0, "expected fail without --force"
    assert "force" in proc2.stderr.lower() or "non-empty" in proc2.stderr.lower()
    # With --force, it succeeds.
    proc3 = _run_bootstrap(target, "--force")
    assert proc3.returncode == 0, proc3.stderr
