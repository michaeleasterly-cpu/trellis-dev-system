# trellis-dev-system — repository hardening (D0g)

## What this is for

"Hardening" means locking down the repo so mistakes and secrets can't
slip in. This doc lists the automatic checks ("gates") that Trellis
runs on its own code, plus the recommended settings to protect the
`main` branch. Trellis hands the same secret-scanning gate to the
projects that adopt it, so it runs that gate on itself first —
"dogfooding," eating your own dog food, means using your own tool
before asking anyone else to.

This document describes the gates trellis-dev-system enforces on
itself and the branch-protection settings recommended once a second
consumer adopts the dev system. It is the dogfood counterpart to the
portable `secret-scan.yml` template the dev system emits to consumer
repos.

## Gates running in CI today

| Gate | Workflow | Trigger | Permissions |
|---|---|---|---|
| pytest + ruff + byte-compile | `.github/workflows/ci.yml` | push to `main`, PRs to `main` | `contents: read` |
| gitleaks (worktree + SARIF) | `.github/workflows/secret-scan.yml` | push to `main`, PRs to `main`, `workflow_dispatch` | `contents: read`, `security-events: write` |

The `security-events: write` permission on `secret-scan.yml` is the
documented minimum required to upload SARIF results to the GitHub
code-scanning surface; no other workflow asks for write access on any
resource.

### Why dogfood the consumer-facing template

`devsystem/github/workflows/secret-scan.yml` is the portable template
rendered into every consumer repo by `bootstrap_project.py`. Before
asking a second consumer to adopt it, the dev system repo itself runs
the same gate. A test (`tests/test_repo_hardening_present.py`)
asserts the two stay aligned: same gitleaks pin, same permissions
block, same scan flags.

### gitleaks configuration

`.gitleaks.toml` extends the gitleaks v8 defaults in full
(`useDefault = true`). The only allowlist covers sentinel-pattern
tuples in test files — strings the test suite scans for to prove
forbidden patterns never leak into rendered consumer output. No real
credential of any kind is allowlisted.

### What the gates are NOT

- No deployment automation. The dev system never runs `railway up`,
  `docker build`, `gh pr merge`, or any other state-mutating command
  in CI.
- No Anthropic API call. Bootstrap and audit are pure file-rendering
  operations. The `secret-scan` workflow does not call Anthropic.
- No Claude auto-fix. The Claude-review workflow template the dev
  system emits is review-only; the dev system repo does not adopt
  even that template for itself (the audience is dev-system
  maintainers, not consumers of dev-system PRs).
- No auto-merge.

## Recommended branch protection (not yet enabled)

Branch protection is **not enabled by this PR**. Enabling it is an
operator action because (a) GitHub branch-protection API mutations
should be authorized explicitly per repo, and (b) the operator may
want to time enabling protection to coincide with the second
consumer adopting the dev system, so locally-prepared PRs from the
extraction sequence aren't held back by a freshly-enabled gate.

When the operator chooses to enable protection on `main`, the
following posture matches the gates installed:

- **Require a pull request before merging.** Direct pushes to `main`
  are disabled. Approving review can be set to 0 reviewers (the
  operator is the sole maintainer for the foreseeable future) but the
  PR-required posture preserves CI as a forcing function and surfaces
  a diff for the operator to skim.
- **Require status checks to pass before merging.** Required checks:
  - `pytest + ruff + compile` (from `ci.yml`)
  - `gitleaks (worktree + SARIF)` (from `secret-scan.yml`)
- **Require branches to be up to date before merging.** Prevents a
  PR whose base diverged after the checks ran from sliding through.
- **Block force pushes to `main`.**
- **Block deletion of `main`.**
- **Do NOT** enable "Allow auto-merge". The whole dev-system
  philosophy is that human review is the dispositive gate; auto-merge
  defeats that.
- **Do NOT** enable "Allow squash auto-merge" with bypass; same
  reason.

The operator enables this via the GitHub web UI **Settings →
Branches → Add branch ruleset → main** or via the GitHub REST API
with a personal access token that has `repo` admin scope. This
document does not record any token or secret value; the operator
keeps PAT material in their own credential store.

### Re-enabling discipline if a second consumer adoption surfaces
gaps

If adopting the dev system into a second consumer repo reveals that
the gates above are too restrictive (for example a real second
consumer needs an additional CI job the dev system shouldn't run),
**add the new job in the consumer repo, not here**. The dev-system
repo is the source-of-truth for what the *portable* gates look like;
extending it should only happen if the change is genuinely portable
to every consumer.

## What CI does *not* test

- Workflow execution end-to-end (`actions/checkout` + Claude action +
  PR comment posting) is not exercised in CI; the `.template`
  workflows are only rendered into disposable tmpdirs and structurally
  checked.
- Branch protection settings are not asserted by CI. They exist as
  GitHub repo-level configuration, not as a tracked artifact.

## Cross-references

- Portable consumer template: `devsystem/github/workflows/secret-scan.yml`
- D0e PR adding the portable template:
  <https://github.com/michaeleasterly-cpu/trellis-dev-system/pull/5>
- D0f validation report (in conversation history) — confirmed all
  four profile bootstraps still pass.
