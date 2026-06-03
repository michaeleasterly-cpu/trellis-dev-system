# Trellis — methodology log

Append-only record of methodology lessons surfaced during real-consumer work that should inform future dev-system templates, profile seeds, and consumer guidance. Each entry is dated and cites the originating consumer PR + the authoritative external doc(s).

The format is deliberately small: one heading per lesson, a *one-paragraph rationale*, a concrete recommendation for the dev system, and links. Resist the temptation to grow this into a wiki — long-form design lives in `docs/superpowers/specs/` or the consumer's own `docs/`; this file is a *log*, not a manual.

---

## 2026-06-02 — vulture whitelist entries should use import-style references, not bare names

**Surfaced by:** `short-term-trading-engine` PRs #425 (P1b implementation) + #426 (ruff hygiene).

**Authoritative source:** [vulture README — Whitelists](https://github.com/jendrikseipp/vulture#whitelists) — "*In a whitelist we simulate the usage of variables, attributes, etc.*"

**Lesson.** When a vulture allowlist file silences false positives on dataclass fields read via dot notation, the entry should be the **import-style pattern** the vulture maintainer documents:

```python
from some.module import SomeDataclass as _Whitelist
_Whitelist.field_a
_Whitelist.field_b
```

…not the auto-generated bare-name form:

```python
field_a  # unused variable (some/module.py:42)
field_b  # unused variable (some/module.py:58)
```

The import-style entries *rot loudly*: if `SomeDataclass` is renamed/deleted, the import fails on the next vulture run; if any field is renamed/deleted, the attribute access fails. Bare-name entries silently survive renames, leaving stale file:line comments behind that future readers can't trust. Same vulture semantics either way; strictly stronger rot signal.

**Recommendation for the dev system.**
- If we ever ship a portable `vulture_allowlist.py.template` (or a sample consumer profile that includes one), bake the import-style pattern into the seed.
- Mention this in `docs/REPO_HARDENING.md` adjacent to the gitleaks / pre-commit guidance — it's the same family of "tool-specific file the linter doesn't understand" governance.
- Don't ship a vulture template *yet*; add only when a second consumer hits this pattern. Single-consumer evidence is sufficient to log the lesson but not to template it.

---

## 2026-06-02 — ruff `extend-exclude` in `pyproject.toml` beats CI dir-list args

**Surfaced by:** `short-term-trading-engine` PR #426 (ruff hygiene follow-up to P1b).

**Authoritative source:** [ruff `extend-exclude`](https://docs.astral.sh/ruff/settings/#extend-exclude) + [ruff file discovery](https://docs.astral.sh/ruff/configuration/#file-discovery).

**Lesson.** When a repo contains a Python-syntactic file that should never be linted by ruff (e.g. `vulture_allowlist.py`, a type-stub-style `_typing.py`, an auto-generated `_pb2.py`), the canonical mechanism is `pyproject.toml [tool.ruff] extend-exclude = [...]`, **not** scoping the CI invocation to an explicit dir list.

The CI-dir-list pattern (`ruff check reversion/ vector/ tpcore/ scripts/ …`) appears to work — a missing dir name silently never gets linted — but it has a silent-leak failure mode: a new top-level Python file added at the repo root will *also* be silently unlinted until someone notices and updates the dir list. Linting intent should live in configuration, not CLI args.

The current STE `ci.yml` uses the dir-list pattern for historical reasons; PR #426 fixes one specific instance (`vulture_allowlist.py`). The portable `ci.yml.template` trellis-dev-system ships is already cleaner — it runs `python -m ruff check .` against the whole tree (no dir filter), which is the correct default because consumer projects start with `extend-exclude = []` and grow exclusions deliberately in `pyproject.toml`.

**Recommendation for the dev system.**
- **Keep the portable `ci.yml.template`'s current `ruff check .` posture.** It already follows ruff's documented default-correct pattern (walk the whole tree; let `pyproject.toml extend-exclude` carry intent).
- Add a one-paragraph note to `devsystem/docs/DEV_PIPELINE_STANDARD.md.template` (or `docs/REPO_HARDENING.md`) reminding consumers that *when they introduce a vulture allowlist, an auto-generated stub, or any other Python-syntactic-but-not-meant-to-lint file*, the right move is `extend-exclude` in `pyproject.toml`, not a CI dir-list workaround.
- Don't ship a `pyproject.toml` seed that includes an empty `extend-exclude = []` — keep the default implicit, since adding an exclude list is itself a signal worth seeing in code review.

---

## Format reminders for future entries

- Date in the heading: `YYYY-MM-DD — short imperative title`.
- Cite the *consumer PR* that surfaced the lesson (or the dev-system PR if it was an internal observation).
- Cite the *authoritative external doc* — README, official docs page, PEP. If there isn't one, mark the lesson `NEEDS_AUTHORITY_CHECK` and revisit.
- One-paragraph rationale. If you can't say it in one paragraph, it's not a methodology lesson; it's a design doc — write it under `docs/superpowers/specs/`.
- End with a *concrete dev-system recommendation*. The point of this log is to inform future PRs; entries without an actionable recommendation are noise.
- Don't delete or rewrite past entries. If a lesson is superseded, add a new entry that supersedes it and cross-link.
