# Feature Scope addendum — Max PF moves: most likely pick instead of the average

**Date:** 2026-11-14 · **Decision:** [D-263](../../../../living-memory/DECISIONS.md) ·
**Entry point:** direct ask (operator approved replacing the decimal average with the most likely
pick and its chance). **Parent scopes:** [scope.md](scope.md) (v1), [scope-v1-1.md](scope-v1-1.md).
Wire contract: [contract.md](contract.md) (most-likely-pick note at the top). Branch
`feat/maxpf-most-likely-pick`. Full gates (no express).

## Why

Each row read `Pick if you miss 1.9 → 1.4` and the baseline `pick 3.7 on average`. Those are
average pick positions (1.92 → 1.39), but they look like pick labels (1.09 → 1.04), which
contradicted the rest of the screen (the team was already projected top-3). A label-shaped
number must be a label.

## What changes

| Area | Change |
|---|---|
| Read (`maxpf_moves.compose`) | Adds `most_likely_pick`: `{slot, label, probability}` on the baseline, `{now, after}` of that shape on every row and combined entry. Derived from distributions the saved run already holds (no forecast re-run). Absent where the data is missing |
| App | C-BASE: `… If you miss the playoffs, most likely pick 1.03 (24%). …`; C-ROW-2 / C-COMB-2: `Most likely pick 1.03 (24%) → 1.02 (29%)` then ` · Value +169` as before. Both sides shown even when the labels match. No decimal average anywhere on the surface; a missing value leaves its part out |
| Unchanged | What is saved, `maxpf_moves.settings()` / `settings_hash`, the threshold (still on `pick_if_miss`), the sort, `core.VERSION`, `version: 1`. `pick_if_miss` is still served |

## Basis (verified)

- **Baseline:** `result.teams[viewer].pick_probabilities` has one entry per **non-playoff** slot
  (`simulation.py:164` `picks = n - playoff`; `:275-278` only the non-playoff teams are given
  slots) and is unconditional (`:301`, count / iterations, so it sums to the miss chance).
  Renormalising it to sum to 1 gives exactly `conditional_pick_probabilities` (`:302`), the
  basis of `conditional_expected_pick` = `pick_if_miss` (`:303`). No playoff slots to strip.
- **Row / combined "after":** `after_pick_probabilities` is `_after_teams`' `picks`
  (`maxpf_moves.py:326-329`): the same non-playoff slots, saved + paired difference, clamped at 0
  and rescaled to sum to `1 − after_playoff_probability`. Renormalised the same way, so now and
  after are both "given a miss".
- **Rule:** argmax, ties (within 1e-12) to the lower slot; label `pick_slots.slot_suffix(draft_round,
  slot)`, the formatter `label` already uses. Omitted when `pick_if_miss` (that side) is null, the
  distribution is absent (every saved v1/v1.1 block has it; the read still uses `.get`, so a
  malformed or older item is skipped, not an error) or sums to 0.

## Compatibility

Additive keys under `version: 1`; builds 191 and 192 read `pick_if_miss` by name and ignore the new
key. The new app reads only `most_likely_pick` for these lines. No schema, flag, route, setting or
analytics change.

## Evidence

- Backend: `backend/tests/test_maxpf_moves_most_likely.py` (7 tests: basis = the simulation's own
  conditional argmax, renormalising, ties, missing data, combined entries, no mutation and nothing
  saved, settings + hash pinned at `6c64a9ef…`). Updated: `test_maxpf_moves_combined.py`
  (`test_v1_keys_unchanged`, `test_read_serves_combined_with_values_and_keep` allow the additive
  key). `test_maxpf_moves_read.test_example_payload_matches_the_composer` now pins the §5.1
  example's `most_likely_pick` shape against the composer.
- App: `mobile/tests/check-max-pf-moves.js` H3, H8-H12, O3b/O3d and new group Q (no rendered line
  has "Pick if you miss", "on average" or a one-decimal pick; no copy string keeps the old
  wording).
- Sabotage results: in `living-memory/TEST_LEDGER.md` (2026-11-14 entry).
- **Code-walk:** the server value is built in `maxpf_moves.compose` (`maxpf_moves.py:595`
  baseline, `:608` rows, `:624` combined; rule at `:500`); the app line is
  `utils/maxPfMoves.ts` `baselineLine` (`:208`) and `pickLine` (`:254`) used by `rowLine2` /
  `combinedLine2`; `MaxPfMovesSection.tsx:191` / `:226` hide an empty line 2.
- **TestFlight checklist (operator, next build after merge):**
  1. Own Standings card → Max PF moves open: the baseline reads "If you miss the playoffs, most
     likely pick 1.0X (NN%)." and no "on average".
  2. Every row's second line starts "Most likely pick 1.0X (NN%) → 1.0Y (MM%)"; no "3.7"-style
     number anywhere in the section.
  3. A row whose labels match still shows both sides with their two percents.
  4. "Top 2 together" / "Top 3 together" lines use the same form.
  5. The value part (" · Value +N") is unchanged where pricing applies.

## Docs

| Doc | Status |
|---|---|
| `contract.md` | updated (note, §3.4, §3.5 + `PickChance`, §3.7, §5.1 example, §6.6, §10 C-BASE / C-ROW-2 / C-COMB-2, §11) |
| `docs/api-reference.md` | updated (served `most_likely_pick`) |
| `docs/cross-client-invariants.md` | updated (formatting rule, server-derived) |
| `docs/glossary.md` | updated (Most likely pick; Pick if you miss no longer shown) |
| `living-memory/LLD.md` | updated (one line: display values derivable from saved data are added on read) |
| `mobile/src/utils/CLAUDE.md`, `mobile/src/components/CLAUDE.md` | updated |
| `docs/data-dictionary.md` | n/a because nothing saved changes |
| `docs/config-reference.md` | n/a because no setting changes |
| `docs/architecture.md`, `living-memory/HLD.md` | n/a because no module wiring or data flow changes |

## Waivers

- **W1. No simulator capture** (D-056): structural suite, code-walk and the checklist above.
- **W2. Web and extension:** n/a, Max PF moves is mobile-only.
