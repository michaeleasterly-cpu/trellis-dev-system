"""D0d — Claude-surface template sentinels.

Pins the dev-system's portable ``.claude/`` template set:

  * ``devsystem/claude/path_registry.yaml.template``
  * ``devsystem/claude/rules/heavy-lane.md.template``
  * ``devsystem/claude/rules/security-guidance.md.template``
  * ``devsystem/claude/skills/security-review/SKILL.md`` (verbatim)
  * ``devsystem/claude/hooks/block-git-checkout.sh`` (verbatim, +x)
  * ``devsystem/claude/hooks/session-start.sh.template`` (rendered, +x)
  * ``devsystem/claude/hooks/block-pytest-subset-when-critical.sh.template``
    (rendered, +x)
  * ``devsystem/claude/agents/spec-reviewer.md.template``
  * ``devsystem/claude/agents/code-quality-reviewer.md.template``

Assertions cover presence, no STE donor leak, expected placeholders,
shebangs on hooks, security-review skill model-invocability, and no
forbidden command authorizations in any hook body.

Stdlib-only.
"""
from __future__ import annotations

import json
import re
import stat
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_CLAUDE = _REPO / "devsystem" / "claude"

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


def _text(path: Path) -> str:
    assert path.is_file(), f"missing {path.relative_to(_REPO)}"
    body = path.read_text(encoding="utf-8")
    assert body.strip(), f"empty {path.relative_to(_REPO)}"
    return body


def _walk(*, suffix: str | None = None) -> list[Path]:
    return sorted(
        p for p in _CLAUDE.rglob("*")
        if p.is_file()
        and (suffix is None or p.name.endswith(suffix))
    )


# ─────────────────────────────────────────────────────────────────────
# Presence
# ─────────────────────────────────────────────────────────────────────

def test_path_registry_template_present() -> None:
    _text(_CLAUDE / "path_registry.yaml.template")


def test_heavy_lane_rule_template_present() -> None:
    _text(_CLAUDE / "rules" / "heavy-lane.md.template")


def test_security_guidance_rule_template_present() -> None:
    _text(_CLAUDE / "rules" / "security-guidance.md.template")


def test_security_review_skill_present_and_model_invocable() -> None:
    """Skill is verbatim-copied (not a template); must be
    model-invocable (no ``disable-model-invocation: true``)."""
    skill = _CLAUDE / "skills" / "security-review" / "SKILL.md"
    text = _text(skill)
    assert text.startswith("---"), "SKILL.md missing YAML frontmatter"
    closing = text.find("\n---", 3)
    assert closing >= 0
    frontmatter = text[: closing]
    assert "disable-model-invocation: true" not in frontmatter, (
        "security-review SKILL.md must remain model-invocable"
    )


def test_settings_template_present() -> None:
    _text(_CLAUDE / "settings.json.template")


# ─────────────────────────────────────────────────────────────────────
# settings.json.template — Phase-3 canonical keys (permissions + worktree)
# ─────────────────────────────────────────────────────────────────────

def _settings_json() -> dict:
    """Parse settings.json.template as JSON after stripping the only
    placeholder it carries (``{{ project_name }}``, inside a string)."""
    text = _text(_CLAUDE / "settings.json.template")
    # The sole placeholder lives inside a JSON string value, so a literal
    # substitution keeps the document valid JSON.
    text = text.replace("{{ project_name }}", "example-project")
    leftovers = re.findall(r"\{\{\s*[A-Za-z0-9_]+\s*\}\}", text)
    assert not leftovers, f"unexpected placeholders in settings template: {leftovers}"
    return json.loads(text)


def test_settings_template_valid_json_after_render() -> None:
    data = _settings_json()
    assert isinstance(data, dict)
    assert "hooks" in data, "settings template lost its hooks block"


def test_settings_template_permissions_deny_and_default_mode() -> None:
    data = _settings_json()
    perms = data.get("permissions")
    assert isinstance(perms, dict), "settings template missing permissions block"
    assert perms.get("defaultMode") == "default", (
        "permissions.defaultMode must be the explicit canonical 'default'"
    )
    deny = perms.get("deny")
    assert isinstance(deny, list) and deny, "permissions.deny must be a non-empty list"
    # Secret-file + destructive-op coverage (Anthropic-canonical second layer).
    required_deny = (
        "Read(./.env)",
        "Read(./.env.*)",
        "Edit(./.env)",
        "Write(./.env)",
        "Read(./secrets/**)",
        "Read(~/.ssh/**)",
        "Read(~/.aws/**)",
        "Read(~/.gnupg/**)",
        "Read(~/.netrc)",
        "Read(~/.config/gh/**)",
        "Bash(rm -rf /)",
        "Bash(rm -rf /*)",
        "Bash(rm -rf ~)",
        "Bash(rm -rf ~/*)",
        "Bash(rm -rf $HOME*)",
        "Bash(dd if=*)",
        "Bash(chmod -R 777 *)",
        "Bash(chown -R *)",
    )
    missing = [rule for rule in required_deny if rule not in deny]
    assert not missing, f"permissions.deny missing canonical rules: {missing}"


def test_settings_template_deny_excludes_curl_and_wget() -> None:
    """curl/wget are deliberately NOT denied — consumers legitimately use
    them; the donor just removed those entries. Guard against re-adding."""
    data = _settings_json()
    deny = data["permissions"]["deny"]
    for forbidden in ("Bash(curl *)", "Bash(wget *)"):
        assert forbidden not in deny, (
            f"{forbidden!r} must NOT be in permissions.deny (intentionally "
            "excluded for portability)"
        )


def test_settings_template_worktree_block() -> None:
    data = _settings_json()
    worktree = data.get("worktree")
    assert isinstance(worktree, dict), "settings template missing worktree block"
    assert worktree.get("baseRef") == "fresh", (
        "worktree.baseRef must be 'fresh' (branch subagent worktrees from origin/main)"
    )
    assert worktree.get("bgIsolation") == "worktree", (
        "worktree.bgIsolation must be 'worktree'"
    )


def test_settings_template_keeps_project_name_placeholder() -> None:
    text = _text(_CLAUDE / "settings.json.template")
    assert "{{ project_name }}" in text, (
        "settings template must keep the {{ project_name }} placeholder"
    )


def test_hook_block_git_checkout_present_and_executable() -> None:
    hook = _CLAUDE / "hooks" / "block-git-checkout.sh"
    text = _text(hook)
    assert text.startswith("#!"), "hook missing shebang"
    mode = hook.stat().st_mode
    assert mode & stat.S_IXUSR, "hook not executable"


def test_hook_session_start_template_present_and_shebanged() -> None:
    hook = _CLAUDE / "hooks" / "session-start.sh.template"
    text = _text(hook)
    assert text.startswith("#!"), "session-start template missing shebang"


def test_hook_block_pytest_subset_template_present_and_shebanged() -> None:
    hook = _CLAUDE / "hooks" / "block-pytest-subset-when-critical.sh.template"
    text = _text(hook)
    assert text.startswith("#!"), "block-pytest-subset template missing shebang"


def test_agents_present_with_frontmatter() -> None:
    for name in ("spec-reviewer.md.template", "code-quality-reviewer.md.template"):
        path = _CLAUDE / "agents" / name
        text = _text(path)
        assert text.startswith("---"), f"{name} missing YAML frontmatter"


# ─────────────────────────────────────────────────────────────────────
# Donor leak
# ─────────────────────────────────────────────────────────────────────

def test_no_donor_repo_leak_in_any_claude_template() -> None:
    findings: list[tuple[str, str]] = []
    for path in _walk():
        body = path.read_text(encoding="utf-8")
        for pat in _DONOR_LEAK_PATTERNS:
            if pat in body:
                findings.append((path.name, pat))
    assert not findings, (
        f"donor identifier leaked into Claude template: {findings}"
    )


# ─────────────────────────────────────────────────────────────────────
# Expected placeholders
# ─────────────────────────────────────────────────────────────────────

def test_heavy_lane_rule_uses_required_placeholders() -> None:
    text = _text(_CLAUDE / "rules" / "heavy-lane.md.template")
    for placeholder in (
        "{{ project_name }}",
        "{{ heavy_lane_paths_yaml }}",
        "{{ heavy_lane_paths_markdown }}",
        "{{ review_mode }}",
    ):
        assert placeholder in text, (
            f"heavy-lane template missing {placeholder!r}"
        )


def test_security_guidance_rule_uses_required_placeholders() -> None:
    text = _text(_CLAUDE / "rules" / "security-guidance.md.template")
    for placeholder in (
        "{{ project_name }}",
        "{{ security_sensitive_paths_yaml }}",
        "{{ review_mode }}",
    ):
        assert placeholder in text, (
            f"security-guidance template missing {placeholder!r}"
        )


def test_path_registry_template_uses_required_placeholders() -> None:
    text = _text(_CLAUDE / "path_registry.yaml.template")
    for placeholder in (
        "{{ project_name }}",
        "{{ heavy_lane_paths_yaml_with_why }}",
        "{{ claude_system_paths_yaml_with_why }}",
    ):
        assert placeholder in text, (
            f"path_registry template missing {placeholder!r}"
        )


def test_session_start_template_uses_required_placeholders() -> None:
    text = _text(_CLAUDE / "hooks" / "session-start.sh.template")
    for placeholder in (
        "{{ project_name }}",
        "{{ heavy_lane_paths_shell_summary }}",
        "{{ review_mode }}",
    ):
        assert placeholder in text, (
            f"session-start template missing {placeholder!r}"
        )


def test_block_pytest_subset_template_uses_required_placeholders() -> None:
    text = _text(_CLAUDE / "hooks" / "block-pytest-subset-when-critical.sh.template")
    for placeholder in (
        "{{ critical_subset_paths_regex }}",
        "{{ project_name }}",
    ):
        assert placeholder in text, (
            f"block-pytest-subset template missing {placeholder!r}"
        )


def test_agents_use_project_name_placeholder() -> None:
    for name in ("spec-reviewer.md.template", "code-quality-reviewer.md.template"):
        text = _text(_CLAUDE / "agents" / name)
        assert "{{ project_name }}" in text, (
            f"{name} missing project_name placeholder"
        )


# ─────────────────────────────────────────────────────────────────────
# Hook body — no forbidden authorizations
# ─────────────────────────────────────────────────────────────────────

_HOOK_FORBIDDEN_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bgh\s+pr\s+merge\b", "gh pr merge"),
    (r"\bgit\s+push\s+[^\n]*(--force|-f\s)", "git push --force"),
    (r"curl\s+[^\n]*ANTHROPIC_API_KEY", "Anthropic API call from hook"),
    (r"/memory_stores/[^\s]+/memories", "memstore mutation"),
)


def _strip_comments(text: str) -> str:
    out: list[str] = []
    for raw in text.splitlines():
        if raw.lstrip().startswith("#"):
            continue
        out.append(raw)
    return "\n".join(out)


def test_no_hook_invokes_forbidden_commands() -> None:
    findings: list[tuple[str, str]] = []
    hooks_dir = _CLAUDE / "hooks"
    for hook in sorted(
        list(hooks_dir.glob("*.sh")) + list(hooks_dir.glob("*.sh.template"))
    ):
        scan_text = _strip_comments(hook.read_text(encoding="utf-8"))
        for pattern, label in _HOOK_FORBIDDEN_PATTERNS:
            if re.search(pattern, scan_text, re.IGNORECASE):
                findings.append((hook.name, label))
    assert not findings, (
        f"hook bodies contain forbidden commands: {findings}"
    )
