# Trellis

A reusable, hand-portable scaffold for Claude-assisted development. Packages the Claude/dev workflow surfaces that proved durable in the `short-term-trading-engine` project (path registry, memory boundary, Claude-surface contract, security cascade, session/cost observability) and renders them into new repositories driven by a single `PROJECT_PROFILE.yaml`.

## What this repo is

This repo extracts the *workflow* from a working repo (`short-term-trading-engine`) so future projects can adopt the same Claude-Code review discipline, security-guidance cascade, manifest linter, sentinel tests, and observability tooling **without copy-pasting and silently drifting**.

What it is **not**:

- It does not contain trading logic, engine code, broker integrations, financial APIs, or any donor-repo domain content.
- It does not call the Anthropic API.
- It does not write to Anthropic memstores.
- It does not assume Docker.
- It does not run deploys. Railway is a supported deployment **profile**, but the tool itself never invokes `railway up`.

## Status: D0g — repo hardening (dogfood secret-scan)

| Stage | Scope | Status |
|---|---|---|
| D0a | Repo skeleton: README + LICENSE + PROJECT_PROFILE example + JSON Schema + empty `devsystem/` and `templates/` trees + minimal CI | merged (PR #1) |
| D0b | Portable docs as templates under `devsystem/docs/` | merged (PR #2) |
| D0c | Portable scripts + bootstrap renderer + sentinel tests | merged (PR #3) |
| D0d | Portable Claude surface: `path_registry.yaml.template`, `heavy-lane`/`security-guidance` rule templates, `security-review` skill (verbatim), portable hooks + agent templates; `check_manifests.py --target-dir` validates a consumer's rendered `.claude/` surface. | merged (PR #4) |
| D0e | GitHub workflow templates (`claude-review-heavy-lane.yml.template` review-only, `secret-scan.yml` verbatim, `ci.yml.template` generic Python), `pull_request_template.md.template`, portable `.claude/settings.json.template`, and four profile seeds (`generic-python`, `python-railway`, `python-postgres`, `fintech-research`). Bootstrap gains `--profile <name>`; audit + check_manifests cover the new GitHub surface. | merged (PR #5) |
| D0f | Validation: all four profile seeds bootstrap into disposable consumer repos; audit/check_manifests/drift-detection all green. | passed (in-session report) |
| **D0g** | Repo hardening: dogfood the portable `secret-scan.yml` workflow in this repo itself; add `.gitleaks.toml` (defaults + sentinel-pattern allowlist); add `docs/REPO_HARDENING.md` with recommended branch-protection settings; sentinel test pins the dogfooded workflow to byte-alignment with the portable consumer copy. Branch protection is documented but **not yet enabled** — operator-only action. | **this PR** |
| D1 | First real consumer repo adopts the dev system | deferred |

The dev system now holds itself to the same secret-handling and least-permission discipline it teaches consumers. See `docs/REPO_HARDENING.md` for the current gates, the gitleaks posture, and the recommended branch-protection ruleset for `main`.

## How a future project uses it

Pick a named profile seed and bootstrap into a fresh directory:

```bash
python /path/to/trellis-dev-system/devsystem/scripts/bootstrap_project.py \
    --profile generic-python \
    --target-dir ./my-new-repo
```

Or override individual values with your own profile file:

```bash
cp /path/to/trellis-dev-system/PROJECT_PROFILE.example.yaml ./PROJECT_PROFILE.yaml
$EDITOR PROJECT_PROFILE.yaml
python /path/to/trellis-dev-system/devsystem/scripts/bootstrap_project.py \
    --profile python-railway \
    --profile-file PROJECT_PROFILE.yaml \
    --target-dir ./my-new-repo
```

Available seeds: `generic-python`, `python-railway`, `python-postgres`, `fintech-research`.

Bootstrapping produces:

- `docs/` — five portable docs (`DEV_PIPELINE_STANDARD`, `SECURITY_GUIDANCE`, `MEMORY_MAINTENANCE`, `MEMSTORE_HANDOFF`, `CLAUDE_SESSION_OBSERVABILITY`).
- `.claude/` — `path_registry.yaml`, `rules/`, `skills/security-review/`, `hooks/`, `agents/`, `settings.json` wiring the hooks.
- `.github/workflows/` — `ci.yml`, `secret-scan.yml`, `claude-review-heavy-lane.yml` with its `paths` filter pinned to the registry.
- `.github/pull_request_template.md` — lane checkboxes + heavy-lane-path checklist mirroring the registry.

Audit at any time:

```bash
python /path/to/trellis-dev-system/devsystem/scripts/audit_project.py --target-dir ./my-new-repo
python /path/to/trellis-dev-system/devsystem/scripts/check_manifests.py --target-dir ./my-new-repo
```

## Memory boundary

The donor repo's C0.1 + C0.2 + C0.4 + C0.5 work codified a 4-tier memory boundary (`CLAUDE.md` -> local `MEMORY.md` -> Anthropic API beta memstores -> repo docs/tests/hooks). The dev system preserves that boundary:

- **Anthropic API beta memstores are off by default** (`memory_policy.api_memstores_enabled: false` in `PROJECT_PROFILE.yaml`). When enabled by a consumer project, the consumer supplies its own `dev_memstore_id` and `agent_memstore_id` in its own `PROJECT_PROFILE.yaml` — **no memstore IDs are shipped by this repo**, ever. Sentinels enforce this (`tests/test_no_memstore_id_hardcoded.py`).
- **No bootstrap or audit step calls the Anthropic API or writes to any memstore.** Bootstrap is a pure file-rendering operation. Sentinels enforce this (`tests/test_no_anthropic_api_surface.py`).
- The 24 400-byte ceiling on local `MEMORY.md` from C0.1 is templated through `memory_policy.local_memory_limit_bytes`.

Cloud memory documentation that consumer projects render lives in the templated `docs/MEMSTORE_HANDOFF.md` (deferred to D0b). When a consumer enables `api_memstores_enabled`, that doc renders with the cloud-memory boundary section and the consumer's own memstore IDs from their `PROJECT_PROFILE.yaml`.

## Authoritative external

- Claude Code docs: <https://code.claude.com/docs/en/>
- Anthropic Memory Stores API (beta): pinned by version header per consumer config; never called from this repo.

## License

MIT. See `LICENSE`.

## Acceptance authority

The author (operator of the donor `short-term-trading-engine` repo) is the dispositive gate for what counts as "portable" — donor-repo-specific content stays in the donor repo regardless of how generic-looking it appears.
