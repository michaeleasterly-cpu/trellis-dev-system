"""D0c — audit_project.py drift detector sentinel.

Bootstrap a dummy consumer repo, run ``audit_project.py`` (expect
exit 0), mutate one rendered doc, run audit again (expect exit 1
with a drift message). Stdlib-only.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_BOOTSTRAP = _REPO / "devsystem" / "scripts" / "bootstrap_project.py"
_AUDIT = _REPO / "devsystem" / "scripts" / "audit_project.py"
_PROFILE = _REPO / "PROJECT_PROFILE.example.yaml"


def _bootstrap_into(target: Path) -> None:
    proc = subprocess.run(
        [
            sys.executable, str(_BOOTSTRAP),
            "--profile-file", str(_PROFILE),
            "--target-dir", str(target),
        ],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr


def _audit(target: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_AUDIT), "--target-dir", str(target)],
        capture_output=True, text=True, check=False,
    )


def test_audit_clean_on_fresh_bootstrap(tmp_path: Path) -> None:
    target = tmp_path / "dummy"
    _bootstrap_into(target)
    proc = _audit(target)
    assert proc.returncode == 0, (
        f"audit reported drift on fresh bootstrap:\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    assert "OK" in proc.stdout


def test_audit_detects_doc_drift(tmp_path: Path) -> None:
    target = tmp_path / "dummy"
    _bootstrap_into(target)
    # Mutate a rendered doc.
    mutated = target / "docs" / "MEMSTORE_HANDOFF.md"
    text = mutated.read_text(encoding="utf-8")
    mutated.write_text(text + "\n<!-- operator-injected drift -->\n", encoding="utf-8")
    proc = _audit(target)
    assert proc.returncode == 1, (
        f"audit failed to detect mutated doc; rc={proc.returncode}"
    )
    assert "drift" in proc.stderr.lower()
    assert "MEMSTORE_HANDOFF.md" in proc.stderr


def test_audit_detects_missing_rendered_doc(tmp_path: Path) -> None:
    target = tmp_path / "dummy"
    _bootstrap_into(target)
    # Delete a rendered doc.
    (target / "docs" / "SECURITY_GUIDANCE.md").unlink()
    proc = _audit(target)
    assert proc.returncode == 1
    assert "SECURITY_GUIDANCE.md" in proc.stderr
    assert "missing" in proc.stderr.lower()


def test_audit_refuses_target_without_project_profile(tmp_path: Path) -> None:
    target = tmp_path / "empty-target"
    target.mkdir()
    proc = _audit(target)
    assert proc.returncode == 2, (
        "audit should exit 2 on missing PROJECT_PROFILE.yaml"
    )
    assert "PROJECT_PROFILE" in proc.stderr


# ─────────────────────────────────────────────────────────────────────
# D0d — Claude surface drift detection
# ─────────────────────────────────────────────────────────────────────

def test_audit_detects_claude_rule_drift(tmp_path: Path) -> None:
    target = tmp_path / "dummy"
    _bootstrap_into(target)
    rule = target / ".claude" / "rules" / "heavy-lane.md"
    rule.write_text(
        rule.read_text(encoding="utf-8") + "\n<!-- drift -->\n",
        encoding="utf-8",
    )
    proc = _audit(target)
    assert proc.returncode == 1
    assert "heavy-lane.md" in proc.stderr
    assert "drift" in proc.stderr.lower()


def test_audit_detects_hook_exe_bit_drift(tmp_path: Path) -> None:
    target = tmp_path / "dummy"
    _bootstrap_into(target)
    hook = target / ".claude" / "hooks" / "block-git-checkout.sh"
    mode = hook.stat().st_mode & ~0o111
    hook.chmod(mode)
    proc = _audit(target)
    assert proc.returncode == 1
    assert "executable" in proc.stderr.lower()
    assert "block-git-checkout.sh" in proc.stderr


def test_audit_detects_missing_claude_artifact(tmp_path: Path) -> None:
    target = tmp_path / "dummy"
    _bootstrap_into(target)
    (target / ".claude" / "agents" / "spec-reviewer.md").unlink()
    proc = _audit(target)
    assert proc.returncode == 1
    assert "spec-reviewer.md" in proc.stderr


# ─────────────────────────────────────────────────────────────────────
# D0e — GitHub-surface drift detection
# ─────────────────────────────────────────────────────────────────────


def test_audit_detects_workflow_drift(tmp_path: Path) -> None:
    target = tmp_path / "dummy"
    _bootstrap_into(target)
    wf = target / ".github" / "workflows" / "claude-review-heavy-lane.yml"
    wf.write_text(
        wf.read_text(encoding="utf-8") + "\n# operator-injected drift\n",
        encoding="utf-8",
    )
    proc = _audit(target)
    assert proc.returncode == 1
    assert "claude-review-heavy-lane.yml" in proc.stderr
    assert "drift" in proc.stderr.lower()


def test_audit_detects_pr_template_drift(tmp_path: Path) -> None:
    target = tmp_path / "dummy"
    _bootstrap_into(target)
    pr = target / ".github" / "pull_request_template.md"
    pr.write_text(
        pr.read_text(encoding="utf-8") + "\n<!-- drift -->\n",
        encoding="utf-8",
    )
    proc = _audit(target)
    assert proc.returncode == 1
    assert "pull_request_template.md" in proc.stderr


def test_audit_detects_settings_json_drift(tmp_path: Path) -> None:
    target = tmp_path / "dummy"
    _bootstrap_into(target)
    settings = target / ".claude" / "settings.json"
    text = settings.read_text(encoding="utf-8")
    settings.write_text(text.replace("PreToolUse", "PreToolUseDRIFT"), encoding="utf-8")
    proc = _audit(target)
    assert proc.returncode == 1
    assert "settings.json" in proc.stderr
