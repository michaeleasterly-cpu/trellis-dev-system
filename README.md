# Trellis

## What problem does this solve?

When you build software with Claude, you slowly invent a set of working habits: how code gets reviewed, how secrets stay out of the repo, how memory and notes are kept tidy, how you keep track of cost. Those habits are valuable, but they usually live in one project and never travel. Start a new project and you copy files by hand, tweak them, and watch them drift out of sync.

Trellis fixes that. It is a reusable starter kit (a "scaffold") for building software with Claude. It takes the Claude workflow pieces that worked well in one real project and turns them into templates you can drop into a brand-new repository. You fill in one settings file (`PROJECT_PROFILE.yaml`) and Trellis renders all the pieces into your new project for you — no hand-copying, no silent drift.

The habits Trellis packages:

- A **path registry**: one file that lists which parts of your code are high-risk. ("Registry" here just means a single authoritative list.) Everything else reads from this one list, so the rules can't disagree with each other.
- A **memory boundary**: clear rules for what Claude is allowed to remember, and where.
- A **Claude-surface contract**: a fixed shape for the `.claude/` files (rules, skills, hooks, agents) so they stay consistent.
- A **security cascade**: a layered review process for any change that touches something sensitive.
- **Session and cost observability**: a local-only report of how much Claude work a project used, with no private content saved.

## How it's organized

Trellis was extracted from a working repo called `short-term-trading-engine` (the "donor" repo). The goal is to let future projects adopt the same Claude-Code review discipline, security cascade, manifest linter, sentinel tests, and observability tooling **without copy-pasting and silently drifting**. ("Sentinel tests" are small tests that fail your build if a required file or rule goes missing — they stand guard. A "manifest linter" is a checker that confirms the listed files actually exist and match.)

What Trellis is **not**:

- It does not contain trading logic, engine code, broker integrations, financial APIs, or any donor-repo domain content.
- It does not call the Anthropic API.
- It does not write to Anthropic memstores. (A "memstore" is Anthropic's optional cloud memory for an assistant.)
- It does not assume Docker.
- It does not run deploys. Railway is a supported deployment **profile**, but the tool itself never invokes `railway up`.

## Status: D0g — repo hardening (dogfood secret-scan)

"Dogfood" means Trellis runs its own security gate on itself, the same one it hands to other projects.

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

Trellis now holds itself to the same secret-handling and least-permission discipline it teaches the projects that adopt it. See `docs/REPO_HARDENING.md` for the current gates, the gitleaks posture, and the recommended branch-protection ruleset for `main`.

## How a future project uses it

First, pick a starting template ("profile seed") that matches your project, and bootstrap it into a fresh, empty directory:

```bash
python /path/to/trellis-dev-system/devsystem/scripts/bootstrap_project.py \
    --profile generic-python \
    --target-dir ./my-new-repo
```

You can also override individual values with your own profile file:

```bash
cp /path/to/trellis-dev-system/PROJECT_PROFILE.example.yaml ./PROJECT_PROFILE.yaml
$EDITOR PROJECT_PROFILE.yaml
python /path/to/trellis-dev-system/devsystem/scripts/bootstrap_project.py \
    --profile python-railway \
    --profile-file PROJECT_PROFILE.yaml \
    --target-dir ./my-new-repo
```

Available seeds: `generic-python`, `python-railway`, `python-postgres`, `fintech-research`.

Bootstrapping (filling in the templates and writing them into your repo) produces:

- `docs/` — five portable docs (`DEV_PIPELINE_STANDARD`, `SECURITY_GUIDANCE`, `MEMORY_MAINTENANCE`, `MEMSTORE_HANDOFF`, `CLAUDE_SESSION_OBSERVABILITY`).
- `.claude/` — `path_registry.yaml`, `rules/`, `skills/security-review/`, `hooks/`, `agents/`, `settings.json` wiring the hooks.
- `.github/workflows/` — `ci.yml`, `secret-scan.yml`, `claude-review-heavy-lane.yml` with its `paths` filter pinned to the registry.
- `.github/pull_request_template.md` — lane checkboxes + heavy-lane-path checklist mirroring the registry.

You can check that a generated project is still in good shape at any time:

```bash
python /path/to/trellis-dev-system/devsystem/scripts/audit_project.py --target-dir ./my-new-repo
python /path/to/trellis-dev-system/devsystem/scripts/check_manifests.py --target-dir ./my-new-repo
```

## Memory boundary

The donor repo worked out clear rules for what Claude may remember and where, across four places ("tiers"). Trellis keeps those same rules. The four tiers run from `CLAUDE.md` (short rules loaded every session) to local `MEMORY.md`, to Anthropic's optional cloud memstores, down to the repo's own `docs/`, tests, and hooks (the final word).

The key points:

- **Anthropic's cloud memstores are off by default** (`memory_policy.api_memstores_enabled: false` in `PROJECT_PROFILE.yaml`). If a project turns them on, that project supplies its own `dev_memstore_id` and `agent_memstore_id` in its own `PROJECT_PROFILE.yaml`. **Trellis never ships any memstore IDs**, ever. A sentinel test enforces this (`tests/test_no_memstore_id_hardcoded.py`).
- **No bootstrap or audit step calls the Anthropic API or writes to any memstore.** Bootstrap only renders files. A sentinel test enforces this too (`tests/test_no_anthropic_api_surface.py`).
- There is a 24,400-byte size limit on the local `MEMORY.md` file. Trellis makes that limit configurable through `memory_policy.local_memory_limit_bytes`.

The cloud-memory docs that a project renders live in the templated `docs/MEMSTORE_HANDOFF.md`. When a project turns on `api_memstores_enabled`, that doc renders with the cloud-memory section and the project's own memstore IDs from its `PROJECT_PROFILE.yaml`.

## Authoritative external

- Claude Code docs: <https://code.claude.com/docs/en/>
- Anthropic Memory Stores API (beta): pinned by version header per consumer config; never called from this repo.

## License

MIT. See `LICENSE`.

## Acceptance authority

The author (operator of the donor `short-term-trading-engine` repo) is the final word on what counts as "portable." Content that is specific to the donor repo stays in the donor repo, no matter how generic it looks.
