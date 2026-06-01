# Packet Void Dev System

A reusable, hand-portable scaffold for Claude-assisted development. Packages the Claude/dev workflow surfaces that proved durable in the `short-term-trading-engine` project (path registry, memory boundary, Claude-surface contract, security cascade, session/cost observability) and renders them into new repositories driven by a single `PROJECT_PROFILE.yaml`.

## What this repo is

This repo extracts the *workflow* from a working repo (`short-term-trading-engine`) so future projects can adopt the same Claude-Code review discipline, security-guidance cascade, manifest linter, sentinel tests, and observability tooling **without copy-pasting and silently drifting**.

What it is **not**:

- It does not contain trading logic, engine code, broker integrations, financial APIs, or any donor-repo domain content.
- It does not call the Anthropic API.
- It does not write to Anthropic memstores.
- It does not assume Docker.
- It does not run deploys. Railway is a supported deployment **profile**, but the tool itself never invokes `railway up`.

## Status: D0a skeleton only

D0a is the **skeleton-only** stage of the extraction sequence planned in the donor repo's `D0` plan:

| Stage | Scope | Status |
|---|---|---|
| **D0a** | Repo skeleton: README + LICENSE + PROJECT_PROFILE example + JSON Schema + empty `devsystem/` and `templates/` trees + minimal CI | **this PR** |
| D0b | Portable docs as templates (5 markdown templates) | deferred |
| D0c | Portable tests + scripts + `bootstrap_project.py` core | deferred |
| D0d | Portable rules + skills + hooks + agents | deferred |
| D0e | Workflows + PR template + profile seeds | deferred |
| D0f | Donor repo adopts the dev system (round-trip validation) | deferred until 2nd consumer |

No template content has been extracted yet — the `devsystem/` and `templates/` trees are intentionally empty (only `.gitkeep` placeholders). Future stages fill them in.

## How a future project will use it (after D0c)

```bash
# Author your PROJECT_PROFILE.yaml at the root of your new repo
cp /path/to/packetvoid-dev-system/PROJECT_PROFILE.example.yaml ./PROJECT_PROFILE.yaml
$EDITOR PROJECT_PROFILE.yaml

# Bootstrap (D0c+ — not implemented in D0a)
python /path/to/packetvoid-dev-system/devsystem/scripts/bootstrap_project.py \
    --profile generic-python \
    --profile-file PROJECT_PROFILE.yaml \
    --target-dir .
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
