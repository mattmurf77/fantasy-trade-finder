# #169 — Season outlook v2 build status

**Date:** 2026-08-10 · **Branch:** `outlook-league-summary-v2` (from `origin/main` @ `16b1dcb`)
**Scope:** the ship-first recommendation of
[`odds-surface-audit.md`](odds-surface-audit.md) § ranked build order item 1 —
frames **B + C1 + D** of `mockups/outlook-odds/league-summary-outlook-v2.html`,
plus the two preconditions bundled with it (non-Sleeper gate + explanatory row;
cross-client-invariants entries).
**Flag:** `outlook.odds`, **unchanged and still dark**. `config/features.json`
untouched; no flag default moved.
**Files:** `mobile/src/screens/LeagueSummaryScreen.tsx`,
`mobile/src/api/league.ts` (comments only),
`docs/cross-client-invariants.md`, `mobile/src/screens/CLAUDE.md`.
**Not touched:** `backend/` (a sibling agent owns the `server.py:19465`
platform-resolution defect), `web/`, `extension/`, `config/`.

## Table of contents

- [What the frames became in code](#what-the-frames-became-in-code)
- [The two-state switch](#the-two-state-switch)
- [What is deleted](#what-is-deleted)
- [Preconditions built](#preconditions-built)
- [The percentage option and its off-switch](#the-percentage-option-and-its-off-switch)
- [What flag-off preserves](#what-flag-off-preserves)
- [Operator questions this build did NOT decide](#operator-questions-this-build-did-not-decide)
- [Gates](#gates)
- [Maestro waiver](#maestro-waiver)

## What the frames became in code

`OddsSection` / `OddsRow` / `OddStat` are gone, replaced by
`SeasonOutlookSection` / `OutlookRow` / `OutlookUnsupportedRow` plus the band
helpers. Section header is now **"Season outlook"** (was "Playoff picture").

| Mockup frame | Code |
|---|---|
| **B** — weeks 0–5, bands only | `SeasonOutlookSection` with `meta.beta === true`: single-line rows (numeral · name + You badge · band chip), no records anywhere, dashed-equivalent cutline after `meta.playoff_slots`, ribbon "Projected · preseason · beta" |
| **C1** — week 6+, records + bands | Same section with `meta.beta === false`: each row gains `4-2 · proj 9-5`, ribbon shortens to "Projected". Bands persist — C1 is the built default, C2 is not |
| **D** — IDP coverage caption | `coverageCaption(meta)` → a warn-railed note below the list, `testID league-summary.odds.coverage-note` |

Three details worth naming because they are decisions, not transcription:

1. **Row order is computed, not taken from the payload.** The rows ARE the
   projected standings, so the section sorts by `odds.projected_seed` ascending
   (ties → `playoff_pct` desc → `roster_id` asc, so the order is deterministic
   across refetches). The payload's own ordering is `playoff_pct` desc, which
   is *nearly* the standings order — and "nearly" is exactly what would place a
   team below the cutline above one projected to finish ahead of it.
2. **The band chip is border-in-encode-color** (Chalkline `Badge`
   construction), and the label always ships with the color — color alone fails
   a color-blind read. `accessibilityLabel` reads "Likely to make the
   playoffs".
3. **The IDP caption names only the slot families actually present.** The
   mockup copy says "8 defensive/kicker slots"; the code derives
   `defensive` / `kicker` / `defensive/kicker` from `unpriced_slots[]` and
   singularizes, so a kicker-only league never reads "defensive". Everything
   else is the mockup's copy verbatim, in league terms rather than payload
   terms.

Projected losses are derived as `regular_season_weeks - round(projected_wins)`
(clamped), so the pair always sums to the regular season and reads on the scale
the platform's own standings use. Ties are not projected — the simulator
resolves every matchup — so a league with ties shows them in the current record
only.

## The two-state switch

**`meta.beta` is the only switch, and it is read in exactly one place**
(`const showRecords = !meta.beta`), which is then threaded to the row. The
backend already clears `beta` at `completed_weeks >= 6`
(`serialize.py::_BETA_UNTIL_COMPLETED_WEEKS`), so no new mechanism, threshold,
or client-side week arithmetic exists anywhere in this code.

| `meta.beta` | Weeks | Ribbon | Rows carry |
|---|---|---|---|
| `true` | 0–5 | Projected · preseason · beta | order + band chip |
| `false` | 6+ | Projected | order + `current · proj` records + band chip |

Withholding W-L before week 6 is the calibration verdict, not caution: a
projected record is the same false-precision point estimate as "71%" in a
different unit (audit reconciliation log #1).

## What is deleted

- **Title odds** — the `Title` `OddStat` is gone. `odds.title_pct` is still
  served and still on the client type, now carrying a comment saying no client
  may render it at any week in any form. It is absent, not caveated.
- **Raw percentages** — `pct()` (1%-precision) is gone. The only percentage
  formatter left is `roundedPct()`, reachable solely through the disabled
  operator option below.
- **`proj seed 3.2`** — the decimal projected seed never renders; the seed now
  expresses itself as the row's position in the list.
- **The two amber meters per team** — replaced by one chip. Twelve teams now
  fit alongside the top of the value chart instead of burying it.
- **`· N sims ·`** from the source caption, replaced by
  `· order = projected finish ·` (the caption's job is now to explain the
  ordering claim). The "top N make the playoffs" clause is suppressed when
  `playoff_slots` is 0.

## Preconditions built

**Non-Sleeper gate + explanatory row.** `backend/outlook/league_state.py`
implements Sleeper only; the others are `NotImplemented` stubs, and the League
tab is reachable for them, so today's total silence reads as a bug. The screen
now resolves the active league's platform from the cached league list — the
same mechanism `api/espn.ts:isEspnLeague` and `api/platformLink.ts` use — and:

- gates the query (`enabled: oddsEnabled && outlookSupported && !!leagueId`),
  so the app never fires a request the engine would 501 on;
- renders `OutlookUnsupportedRow` in the section's place: the "Season outlook"
  tick label plus one line — *"Season outlook needs schedule and scoring
  history — Sleeper leagues only for now."* No retry affordance, because there
  is nothing the user can do and offering one would imply there is.

**Unknown resolves to supported.** A league missing from the cached list, or a
server that didn't stamp `platform`, falls back to `sleeper` and still fetches.
The gate excludes only a *positively identified* non-Sleeper platform — the
`platform` field is documented as fully trustworthy only while `draft.room` is
on, and a guess must not be allowed to delete the section.

**Cross-client invariants.** `docs/cross-client-invariants.md` gains
§ "Playoff outlook bands (#169, flag `outlook.odds`)": the three band keys,
labels, thresholds (`>= 0.65` / `>= 0.35` / `< 0.35`, boundaries belonging to
the higher band), the pos/warn/neg semantic colors with hexes, the `meta.beta`
two-state rule, the `title_pct` prohibition, the 5%-rounding rule attached to
the percentage option, the `projected_seed` ordering rule, and the locations
table. Web parity is a later item and must read that section rather than
re-derive it.

## The percentage option and its off-switch

Frame **C2** (5%-rounded playoff percentage at week 6+) is built and **off**.

```ts
// mobile/src/screens/LeagueSummaryScreen.tsx
const OUTLOOK_WEEK6_PERCENT_ENABLED = false;   // ← the off-switch
const OUTLOOK_PERCENT_ROUNDING = 0.05;         // load-bearing if ever true
```

`OUTLOOK_WEEK6_PERCENT_ENABLED` is the exact and only switch. With it `false`
(shipped), `OutlookRow` always renders the band chip and `roundedPct()` is
never called. Flipping it to `true` swaps the chip for a 5%-rounded playoff
percentage — and only past the beta gate, because the option is ANDed with
`showRecord`, which *is* `!meta.beta`; there is no arrangement of payload
values that produces a percentage during weeks 0–5. Title odds stay banned
either way.

This constant is a placeholder for the operator's decision, not the decision.
The audit's recommendation stands: if C2 is ever wanted, make it a server-side
presentation flag so it reverts without a client build.

## What flag-off preserves

`outlook.odds` is absent from `LAUNCHED_FLAG_DEFAULTS`, so `useFlag` returns
false and:

- **Render:** `{oddsEnabled ? … : null}` — the whole subtree, section and
  unsupported row alike, is `null`. Byte-identical output to today.
- **Network:** `enabled: oddsEnabled && …` — `GET /api/league/outlook` is never
  called. Unchanged.
- **Re-renders:** the new platform check is selected as a **boolean**
  (`useSession((s) => … === 'sleeper')`), not as the leagues array, so the
  store's `Object.is` comparison means the screen re-renders only when the
  answer flips. With the flag dark that value cannot change what renders.
- **Everything else on the screen** — chart, ticks/deltas, drill-in, filters,
  basis toggle, home row — is untouched by this change.

## Operator questions this build did NOT decide

Left exactly as they were, per the audit's open-questions list:

- **Placement (Q3).** The section stays where the shipped dark code mounts it —
  between the basis toggle and the chart card — which is also where mockup
  frame B shows it. Frame **E** (collapsed strip) is a placement variant
  outside the approved B/C1/D scope and is **not built**.
- **Basis (Q5).** The section still follows the screen's basis toggle, as
  before. Pinning to consensus was recommended but not decided.
- **Two-tier vs single rule (Q4).** Built as two-tier (bands from week 0), the
  designed option. The conservative variant is one line — `if (meta.beta)
  return null` in `SeasonOutlookSection` — if the operator prefers it.
- **Band thresholds (Q2).** Built at 0.65 / 0.35 and now written into
  cross-client-invariants. Changing them is a two-constant edit plus that doc.

## Gates

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` (baseline, pre-change) | **2298 passed, 1 skipped** in 320.53s |
| `python3 -m pytest backend/tests -q` (post-change) | **2298 passed, 1 skipped** — green, unchanged (no backend files touched) |
| `cd mobile && npx tsc --noEmit` | clean, exit 0 |
| `mobile/scripts/testid-lint.sh` | `testid-lint OK`, exit 0 |

**testIDs** — every pre-existing id is kept, so nothing that referenced this
section can break: `league-summary.odds.section`,
`league-summary.odds.beta-ribbon`, `league-summary.odds.source`,
`league-summary.odds.row.<roster_id>`. Added:
`league-summary.odds.band.<roster_id>`, `league-summary.odds.cutline`,
`league-summary.odds.coverage-note`, `league-summary.odds.unsupported`, and
`league-summary.odds.pct.<roster_id>` (unreachable while the percentage option
is off).

## Maestro waiver

**No Maestro flow delta ships with this change. Waiver reason: the feature is
dark and cannot be exercised by the harness.** `outlook.odds` is absent from
`LAUNCHED_FLAG_DEFAULTS`, so in a hermetic sim run the section renders `null`
and the endpoint is never called — a flow asserting any of the ids above would
fail on every run, and a flow asserting their *absence* would pass identically
before and after this change, testing nothing. There is also no seeded
`/api/league/outlook` fixture in the harness, because the modeling backend is
dark. `mobile/scripts/testid-lint.sh` passes, so the ids are ready for a flow.

**The flow is owed at lighting time, not now.** Whoever turns `outlook.odds` on
writes it then, and it must cover: the weeks 0–5 state (band chips present,
**no** record text), the week 6+ state (records present), the cutline position
against `playoff_slots`, the IDP caption appearing only when
`affects_strength` is true, and the non-Sleeper explanatory row.
