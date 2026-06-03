# Trellis — Anthropic-canonical alignment (Phase 3)

## What this is for

"Canonical" means the official, recommended way Anthropic sets up Claude
Code — the patterns in their own docs and example repos. This doc checks
how closely the Trellis templates match those official patterns, and
records what Phase 3 changed to close the gaps. It is a reference doc;
read it if you want to know why the templates are shaped the way they
are, or before you change them.

This doc records how the Trellis dev-system templates line up against the
Anthropic-canonical Claude Code surface, and what Phase 3 changed. It is the
Phase-3 deliverable of a three-phase arc:

- **Phases 1 + 2** audited the donor repo (`short-term-trading-engine`, "STE")
  `.claude/**` surface against the Anthropic docs + `anthropics/claude-code`
  repos. Delivered as the STE audit
  `docs/audits/2026-06-04-anthropic-canonical-pattern-alignment-audit.md` (in
  the donor repo). That audit's §1 "Alignments" and §3 "Canonical surface worth
  pulling in" are the reference for what canon looks like; this doc cites it.
- **Phase 3** (this doc + the PR it ships with) propagates the *portable*
  findings into Trellis's bootstrap templates, which lagged the donor's
  hardened `.claude/**` surface.

Canonical references used here (from the STE audit + Anthropic docs):

- `permissions.deny` evaluation order is `deny → ask → allow`; rules are
  gitignore-style path patterns. Anthropic's
  `examples/settings/settings-strict.json` ships a deny list (plus
  `disableBypassPermissionsMode`) as the canonical strict starting point.
- `worktree.baseRef: "fresh"` (branch subagent worktrees from `origin/main`) +
  `worktree.bgIsolation: "worktree"`.
- `permissions.defaultMode: "default"`.
- `.claude-plugin/plugin.json` minimal shape `{name, description, version,
  author}` — from `anthropics/claude-code/plugins/code-review/.claude-plugin/plugin.json`.

---

## 1. Where the templates already ALIGN with canon

These were already canonical before Phase 3; listed so the alignment surface is
complete and so future edits don't regress them.

- **Slim CLAUDE.md split + path-scoped rules.** The dev system renders a slim
  project memory plus path-scoped `.claude/rules/*.md` (heavy-lane,
  security-guidance) with `paths:` frontmatter for autoload — STE audit §1.1 +
  §1.14.
- **Skill directory shape + model-invocability.** `security-review/SKILL.md`
  ships with YAML frontmatter and stays model-invocable (no
  `disable-model-invocation: true`) — STE audit §1.2.
- **Sub-agent profile shape.** `spec-reviewer` + `code-quality-reviewer` agent
  templates carry the canonical frontmatter (name/description/tools) — STE
  audit §1.3.
- **PreToolUse exit-2 blocking + SessionStart context injection.** The
  `block-git-checkout` / `block-pytest-subset-when-critical` PreToolUse hooks
  block via exit 2; the `session-start` hook injects context. Wired through
  `settings.json.template` `hooks` — STE audit §1.4 + §1.9.
- **Secret-scan workflow.** `devsystem/github/workflows/secret-scan.yml` runs
  pinned gitleaks at least-privilege; the dev system dogfoods its own copy and
  pins them in lockstep (`tests/test_repo_hardening_present.py`) — STE audit
  §1.12 neighborhood.

## 2. What THIS PR UPDATED

- **`devsystem/claude/settings.json.template` — `permissions` block.** Added
  `permissions.defaultMode: "default"` (explicit, per STE audit §3.2) and a
  `permissions.deny` list covering secret files (`.env*`, `secrets/**`,
  `~/.ssh`, `~/.aws`, `~/.gnupg`, `~/.netrc`, `~/.config/gh`) and destructive
  ops (`rm -rf` of root/home, `dd if=*`, `chmod -R 777`, `chown -R`). This is
  the Anthropic-canonical *second layer*: PreToolUse hooks can be bypassed via
  env-var overrides, but the `deny` list cannot, and it is evaluated first in
  the `deny → ask → allow` order. A one-line `$comment_permissions` key labels
  it. **`Bash(curl *)` / `Bash(wget *)` are deliberately excluded** — the donor
  just removed them because consumers legitimately use curl/wget; Trellis
  consumers are even more diverse, so blocking them would be wrong by default.
- **`devsystem/claude/settings.json.template` — `worktree` block.** Added
  `worktree.baseRef: "fresh"` (branch subagent worktrees from `origin/main`) +
  `worktree.bgIsolation: "worktree"` — STE audit §1.6.
- **`.claude-plugin/plugin.json` (repo root).** Created the minimal manifest
  `{name, description, version, author}`. This closes STE audit §3.4: it makes
  Trellis marketplace-discoverable as a reusable plugin once the `.claude/**`
  surface is consumed that way.
- **Sentinels.** Extended `tests/test_claude_surface_templates.py` to pin the
  new `settings.json.template` keys (`permissions.deny`, `permissions.defaultMode`,
  `worktree.baseRef`/`bgIsolation`) and added `tests/test_plugin_manifest_present.py`
  for the `plugin.json` presence + required keys, plus a presence check for this
  doc.
- **Security-guidance Layer-1 PostToolUse pattern-scan hook templates.** Added
  the three portable hook templates under `devsystem/claude/hooks/`:
  `security_pattern_scan.sh.template` (bash wrapper with a `.venv/bin/python` →
  `python3` → `python` fallback chain), `security_pattern_scan.py.template`
  (stdin-JSON entrypoint; advisory exit 0 always — PostToolUse cannot block
  retroactively), and `security_patterns_vendored.py.template` (the ~25 GENERIC
  Anthropic Layer-1 regex patterns: command injection, unsafe deserialization,
  XSS sinks, weak crypto, disabled TLS verification, unsafe XML/YAML/pickle/torch
  loads). **Only the generic Layer-1 patterns are portable** — the donor's
  domain-specific patterns (no-yfinance, no-Discord, hardcoded-Postgres-URL,
  inline `# noqa` bans, etc.) stay donor-only; the entrypoint loads any
  project-specific rules from an *optional, absent-by-default*
  `security_patterns_local.py`. The kill-switch env var is genericized to
  `DEVSYS_SECURITY_PATTERN_SCAN_DISABLE`. Wired into `settings.json.template`
  under `PostToolUse` with matcher `Edit|Write|MultiEdit|NotebookEdit`. The
  bootstrap renderer (`bootstrap_project.py` `_plan_claude_surface`) now renders
  `hooks/*.py` (verbatim) and `hooks/*.py.template` (rendered, NOT executable —
  they are invoked by the `.sh` wrapper, not run directly). Sentinel:
  `tests/test_security_hook_template_present.py`. This closes the §4 deferral
  below (STE audit §1.12).

The `defaultMode` choice is `"default"`, not `"plan"`. The STE audit (§3.2)
notes `"plan"` would be the structural complement to a discovery-first posture
but trades off fast-lane friction; Trellis is a generic scaffold for diverse
consumers, so the non-friction `"default"` is the right portable default. A
consumer wanting plan-mode can override it in their own rendered settings.

## 3. What stays DONOR-ONLY (intentionally NOT portable)

These encode the donor's trading-platform identity/risk semantics, not generic
dev discipline, and are deliberately excluded from Trellis templates:

- **`identity-path` rule** — encodes the STE `ticker + date → classification_id
  → CIK` identity chain and SEC-first authority. Trading-domain specific.
- **`discovery-first` rule + SWV / CIC gates** — scoped to STE's
  validators / ingestion / auditheal / selfheal / migrations / `scripts/ops.py`
  failure surface from a specific 2026-06-02 identity-substrate incident. The
  *shape* (advisory hook) is portable; the *content* is not.
- **ECR / DFCR planner-path hooks** (`gate-ecr-dfcr-edits.sh`) — gate edits to
  the engine-roster / data-feed-roster SoT. STE-specific governance.
- **`silent-failure-hunter` sub-agent** — vendored into STE and adapted to its
  silent-skip vocabulary; the generic dev system already ships spec-reviewer +
  code-quality-reviewer.

See STE audit §2.3–§2.7 for the per-item `STE_ORIGINAL` classifications.

## 4. DEFERRED portable pull-ins (not in this PR)

Genuinely portable, but deferred until there's a concrete reach for them:

- **`hookify` markdown-rule shape for future advisory hooks.** The donor's
  next-advisory-hook guidance (STE audit §3.3) is to author it as a hookify
  rule (YAML frontmatter `event:`/`action:`/`conditions:` + body) rather than
  another `.sh`. Applies to Trellis the same way — adopt on first reach, don't
  vendor proactively.
- **`bash_command_validator` Python shape for future Bash PreToolUse hooks.**
  The canonical `examples/hooks/bash_command_validator_example.py` shape
  (tuple list of `(regex, message)` + `validate_command()` + `sys.exit(2)`).
  Opportunistic: adopt if/when the current bash PreToolUse hooks start feeling
  brittle. STE audit §3.5.

---

*Phase-1+2 reference: `short-term-trading-engine`
`docs/audits/2026-06-04-anthropic-canonical-pattern-alignment-audit.md`.*
