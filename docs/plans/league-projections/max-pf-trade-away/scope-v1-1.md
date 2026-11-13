# Feature Scope addendum — Max PF moves v1.1 (show every row, combined lines)

**Date:** 2026-11-13 · **Decision:** [D-261](../../../../living-memory/DECISIONS.md) ·
**Entry point:** direct ask. Operator, 2026-11-13 (verbatim): "My recommendation is to always
show the top moves with their numbers, add a line for the top two or three combined, and keep the
'none of these changes your pick on its own' sentence when that is true. Yes. I'm aligned".
**Parent scope:** [scope.md](scope.md) (v1). Wire contract: [contract.md](contract.md) (v1.1 note
at the top). Branch `feat/max-pf-moves-show-all`. Full gates (no express).

## Why

A live check on a real 12-team league: 6 of 12 teams, the operator's included, saw only "No single
player moves your projected pick by a visible amount." The operator's top row was a 62-point drop
leaving pick-if-you-miss at 5.90 → 5.88, because his max PF is about 84 points above the next
likely non-playoff team: no single player closes the gap, two together might.

## What changes

| Area | Change |
|---|---|
| Weekly job | After the rows, two combined entries: rows 1–2 and rows 1–3 removed **together** (exact re-solve, both lanes; not the sum of the single drops), each with one paired 5,000-run re-run sharing the rows' "before" run. Saved as `combined` in the block. A size larger than the row count is skipped. Failure or time-out of that step keeps the rows and drops only `combined` |
| Settings | `max_pf_moves.combined_sizes: [2, 3]` (validated: distinct, ascending, each 2 or 3; `[]` = off). It is part of `settings_hash`, so the hash moves with this release |
| Re-run | `batch._moves_missing` also flags a computed block whose `settings_hash` is not current, so `retry_missing_moves` re-runs every pre-v1.1 block. `not_eligible` stays settled |
| Read | Served block gains `combined` (always a list; `[]` outside `ready`/`no_moves`), each entry with read-time `pick_value` and `keep` (any member Keep). `version` stays 1; every v1 key and the `state` rules are unchanged. Rows were already served in `no_moves` (`maxpf_moves.compose` never stripped them); now pinned |
| App | Every row listed in `ready` and `no_moves`, rank order, 5 then Show all. C-NONE-ALONE "None of these changes your projected pick on its own." above the list when nothing listed passes (C-NO-MOVES stays for zero rows). One combined line per entry under the rows ("Top 2 together: R. Sato and D. Okafor  −55" / C-ROW-2's line 2), opening to top-3 and playoff chance only. No Find trades on a combined line |

## Who sees it

Every Sleeper user with `league.projections` + `league.max_pf_moves` on, on their own Standings
card, in `ready` or `no_moves`, on the new app build. Build 191 against the new server: unchanged
behaviour (§ Compatibility).

## Compatibility with installed build 191

Build 191 renders only when `version === 1` and a known `state` (both unchanged), lists rows with
`passes_threshold === true` in `ready` (unchanged data), shows C-NO-MOVES alone for `no_moves`
(unchanged), and ignores unknown keys (`combined`; TypeScript types are compile-time only and the
utils read named fields). Its `maxpf_moves_viewed` props are a subset of the new registration, so
they still land.

## Data

No schema change, no new table, no new column. `result_json.max_pf_moves` gains `combined` and
`settings.combined_sizes` (about 1.5 KB more on the fixture). Retention unchanged.

## Analytics

No new event. `maxpf_moves_viewed` gains optional `n_listed` (rows listed) and `any_pass` (a
listed row or combined entry passes); `n_moves` keeps its v1 meaning (passing rows listed, 0
unless `ready`). `maxpf_move_expanded` from a combined line sends `position: 'combined'`, `rank:
'combined_2' | 'combined_3'`. Registered in `backend/analytics_taxonomy.py` in the same commit;
classification unchanged (viewed is non-intent, expanded is intent).

## Risks

| Risk | Mitigation |
|---|---|
| Two more simulations per baseline slow the job | Measured on the 14-week fixture: 9.5 s → 10.6 s (+1.2 s), inside the 60 s budget; failure or budget hit keeps the rows |
| Users read the combined line as "trade both" advice | Same footer (largest possible change) and tone rules; no Find trades button on combined lines |
| Re-run load when every block's hash goes stale | Operator-only `retry_missing_moves`, bounded by the existing batch limit and leases; otherwise blocks refresh at the weekly slot |
| Listing non-passing rows looks like noise | C-NONE-ALONE says so plainly when nothing passes; numbers are shown as computed |

## Docs

| Doc | Status |
|---|---|
| `contract.md` | updated (v1.1 note, §3.1, §3.7, §4.1 note, §5.1 example, §6.3, §6.5, §9, §10, §12, §13.1, §14 #2) |
| `docs/api-reference.md` | updated (served `combined`, rows in `no_moves`) |
| `docs/data-dictionary.md` | updated (saved `combined`, `combined_sizes`) |
| `docs/config-reference.md` | updated (`combined_sizes`) |
| `docs/cross-client-invariants.md` | updated (listing rule, C-NONE-ALONE, combined lines) |
| `app-evidence.md` | updated (§8 v1.1 code-walk delta and TestFlight items) |
| `docs/architecture.md`, `living-memory/HLD.md` | n/a because no module wiring or data flow changes (one more step inside `maxpf_moves.compute`) |
| `living-memory/LLD.md` | updated (one line: additive fields under a fixed `version`) |
| `mobile/src/*/CLAUDE.md` | updated (utils, components, api rows) |
| `docs/glossary.md` | n/a because no new domain term |

## Waivers

- **W1. No `any_row_passes` top-level boolean.** The app derives it from `rows[].passes_threshold`
  and `combined[].passes_threshold`; a served copy could only disagree.
- **W2. No week detail and no hand-off on combined lines** (operator scope: "a line"); hand-off
  logged as a NEXT.md follow-up.
- **W3. No simulator or Maestro evidence** (D-056): structural suite + code-walk + TestFlight
  checklist in `app-evidence.md` §8.
