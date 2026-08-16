# Feature Scope — Premium Rankings Import v1 (half sheet: Dynasty Nerds / DLF / CSV upload)

**Date:** 2026-08-15
**Entry point:** direct ask (operator, 2026-08-15) — building lane 1 + lane 2a of
[`../premium-rank-sets-addendum-2026-08-15.md`](../premium-rank-sets-addendum-2026-08-15.md) under [D-058]
**Builder:** orchestrating session + two opus build agents (backend, mobile), worktrees off fresh `origin/main`
**Operator sign-off on waivers:** yes — see §1(a) note, §3 (D-057), §5 (D-057)

**Placement decision (operator, 2026-08-15):** imported rankings are **the user's rankings** —
they seed/overwrite the user's own board through the existing import pipeline
(`match_rank_list` → import preview → `/api/rankings/import-apply` → `apply_reorder`), exactly
as CSV paste does today. The DP+KTC consensus baseline is untouched. "Replace consensus"
(a per-user value baseline) was considered and not chosen; revisit only as its own designed
feature. Provenance + non-destructive ordinal merge remain base-plan WS-A work — **this v1
inherits paste's current overwrite semantics**, which the operator already accepts for paste.

---

## 1. Analytics scope

**(a) New events specced** (registered + classified in the same taxonomy commit, per convention):

| Event | Properties | Fires when | Client |
|---|---|---|---|
| `rankings_preset_detected` | `source ∈ {dynasty_nerds, dlf}`, `via ∈ {browser, file}`, `set_confirmed` (bool: user changed the inferred set/format) | A premium CSV's header signature matches a preset and the confirmation step completes | mobile |
| `rankings_preset_fallback` | `via` | A file arrives with no matching signature → generic column-mapping UI | mobile |

`rankings_preset_confirm_changed` from the addendum is folded into `set_confirmed` on
`rankings_preset_detected` (one event, one funnel row — an-data-architect convention of not
splitting a single decision into two names). Existing `rankings_import_applied` continues to
fire on apply (base-plan D10 notes it is unregistered — registering it is base-plan work, not
duplicated here; if the taxonomy commit is cheap the backend agent MAY include it, flagged in
its report). Classification: both new events NON-INTENT (they describe pipeline mechanics
mid-flow, not user intent — the intent event remains the apply).

## 2. Schema & flag scope

- New/changed tables or columns: **none** (v1 is deliberately schema-free; staleness stamp is
  client-side storage; provenance is WS-A later)
- New/changed feature flags: **`ranks.source.dynasty_nerds`**, **`ranks.source.dlf`** — each
  gates its row in the half sheet; sheet renders premium rows only for flags ON. Both
  **default `false`** everywhere (config + compiled client default false — no `espn.link`-style
  fail-open). Added once as a single block: `config/features.json` + `FLAG_KEYS` in
  `backend/feature_flags.py` + the three fixture mirrors (`release`, `onboarding-v2`,
  `profiles-on` — G-034/known trap) + `docs/config-reference.md`. Graduation: operator flips
  after testing lane 2a on their own Dynasty Nerds account. Rollback lever: flags off →
  premium rows vanish from the sheet; manual CSV upload row is NOT flag-gated (it is plain
  file intake for the existing import).
- New env vars / `model_config` keys: **none**

## 3. Test scope

- **Maestro delta: n/a per [D-056]** (Maestro/simulator retired entirely, operator ruling
  2026-08-15). Replacements, mandatory: structural `check-*.js` suite for the half sheet
  (rows gated by flags, routing, testIDs), unit tests for preset parsers (DN fixture-based;
  DLF from fixture when acquired — **DLF preset does not ship until its fixture lands**,
  addendum §3.4), backend pytest for matcher-hint extension **plus paste-path regression**,
  and a written code-walk proof + operator TestFlight checklist for the browser-capture flow.
- `testID`s added: import-sheet rows + browser screen + confirmation step (named by the
  mobile agent; must pass `mobile/scripts/testid-lint.sh`)
- Capture delta: n/a per D-057
- Smoke-suite impact: n/a per D-057 (suites retired); paste import unit/route tests must stay green
- Backend pytest: `test_rankings_import.py` extended (hints, DN fixture, boundary cases)

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a expected | v1 reuses existing import routes unchanged; **if any agent adds/changes a route this flips to mandatory** |
| `living-memory/LLD.md` | updated | preset/intake convention (client-side parse, order-only, filename→format inference) |
| `docs/architecture.md` | n/a | no module wiring change (no new backend module) |
| `living-memory/HLD.md` | n/a | no architecture shift |
| `docs/cross-client-invariants.md` | updated | `source` enum values (`dynasty_nerds`, `dlf`) + flag names |
| `docs/glossary.md` | updated | "premium rank set", "assisted in-app-browser export" |
| ADR / `DECISIONS.md` | done | [D-058] (already recorded) |
| `docs/config-reference.md` | updated | two new flags |

## 5. Ship gate declaration

- **Simulator-gate tier: retired per [D-056]** — standing posture `FTF_SKIP_SIM_GATE=1`.
  Evidence instead: TEST_LEDGER entry with suite counts + structural-check results +
  code-walk proof; operator TestFlight checklist for the on-device browser-export pass
  (operator's own Dynasty Nerds account, per their 2026-08-15 offer).
- Operator deviation: none beyond D-057 (which is the standing rule, not a deviation).

## 6. Known deviations / open items surfaced to the operator

1. **Download capture passive JS bridge — DEVIATION TAKEN (built 2026-08-15).** Both sites
   build their CSVs client-side (`data:`/`blob:` URIs), which WKWebView's `onFileDownload`
   does not surface, so `PremiumRankingsBrowserScreen.tsx` ships `INJECTED_DOWNLOAD_CAPTURE`:
   a pass-through `URL.createObjectURL` wrapper + a capture-phase click listener that reads
   the href of the `<a download>` the **user** tapped, posting the bytes once, only within
   8s of a real user gesture, only when the text sniffs as a rankings CSV. It never clicks,
   navigates, fills, mutates the DOM, reads page text, or touches cookies/credentials —
   pinned structurally by `check-premium-import.js` §5 (no `injectJavaScript` calls, no
   timers, exactly two constant URLs). [D-058]'s "no script injection" is interpreted as
   **no automating the site**; this line is the operator's notice that the passive shim
   exists in shipped code.
2. **DLF fixture is not yet acquired** → DLF ships preset-dark (flag off, generic mapping
   still works for a hand-uploaded DLF CSV) until a real export pins its header shape.
3. Web client: out of scope v1 (backend intake is client-agnostic; follow-on).
