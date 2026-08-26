# #395 + #396 — Lineup-impact superflex attribution & "WR3" slot label — Plan

Date: 2026-08-24 · Planner: Group C (fast-track bug path) · Branch context: `origin/main` @ ff153a0
Items: #395 (bug, v1.16.2, TradesHome — SF lineup attribution) · #396 (bug, v1.16.2, TradesHome — "WR3" in a 2-WR league)

**Plain-words verdict up front:** neither item is a broken optimizer. #395 is the engine
telling the truth in a confusing order — it always parks the best QB in the dedicated QB slot,
so trading him away shows a two-row cascade (QB *and* SF change) where the user expects one
row (his SF changes). #396 is a fabricated slot label: for ESPN/MFL/Fleaflicker leagues the
backend substitutes a hard-coded 3-WR template for the league's real lineup, so a league with
2 WR + a flex gets a literal "WR3" row. Fix one with a display-alignment pass, the other with
an honest template.

---

## 1. Reproduction (both reproduced on current code)

The whole pipeline: `POST /api/trade/evaluate` Mode B → `server._starter_impact`
(`backend/server.py:1167-1303`) → `power_rankings.optimal_starter_slots`
(`backend/power_rankings.py:120-131`, shared greedy fill `_fill_starter_slots` :50-96) →
label numbering (`backend/server.py:1285-1293`) → mobile deck-card renderer
`CardImpactBlock` (`mobile/src/components/TradeCard.tsx:831` →
`mobile/src/components/CardImpactBlock.tsx:108-160`, changed rows only) and the calculator's
full table `LineupImpactTable` (`mobile/src/components/InLeagueCalculator.tsx:1598-1690`).
Web/extension do not render `starter_impact` (git grep confirms mobile-only consumers).

### #395 repro — throwaway script (scratchpad, imports `backend.power_rankings` directly)

Template `QB RB RB WR WR TE FLEX SUPER_FLEX`; roster with Daniels (QB, 9000), Maye (QB, 6000),
Fannin (TE, 2800), filler RB/WR/TE. Output:

```
BEFORE:                      AFTER (Daniels traded):
  QB          daniels          QB          maye
  ...                          ...
  SUPER_FLEX  maye             SUPER_FLEX  fannin
CHANGED ROWS AS THE CARD SHOWS THEM:
  QB          daniels -> maye
  SUPER_FLEX  maye -> fannin
```

So Daniels **is** in the before-lineup (no exclusion bug), and the totals are right — the
greedy fill (`_fill_starter_slots`: dedicated slots first at `power_rankings.py:78-83`, then
flexes narrowest-first at :84-95) canonically assigns the *best* QB to the dedicated QB slot
and the second QB to SUPER_FLEX. The user's mental model (Maye at QB, Daniels at SF — likely
his actual Sleeper lineup) is a **value-identical** assignment: both QBs start either way, the
lineup total is the same number. The engine's choice is mathematically defensible, but the
card then renders a two-row cascade ("QB: Daniels › Maye", "SF: Maye › Fannin") that reads as
"the app thought Maye was my QB and now claims Fannin starts at SF" — exactly the report.
**Verdict: the math is right; the presentation manufactures a phantom QB change. Fix the
presentation.**

### #396 repro — the "WR3" label

`server._league_lineup_slots` (`backend/server.py:24126-24178`) resolves the slot template.
For `platform in ('espn','mfl','fleaflicker')` it does **not** use the league's real lineup —
it substitutes `_MOCK_DEFAULT_LINEUP = ["QB","RB","RB","WR","WR","WR","TE","FLEX"]`
(`backend/server.py:14588`, three WRs), plus a trailing `SUPER_FLEX` when
`default_scoring == 'sf_tep'` (:24171-24175). The label numbering at `server.py:1285-1293`
then emits `WR1/WR2/WR3`. Repro output against that template:

```
QB RB1 RB2 WR1 WR2 WR3 TE FLEX SUPER_FLEX   ← "WR3" exists whenever the league is platform-imported
```

A Sleeper league cannot produce this: `_sleeper_lineup_slots` (:24102-24123) uses the real
`roster_positions`, so a 2-WR + FLEX league labels `WR1 WR2 FLEX`. The reported league is
therefore almost certainly ESPN or MFL (the operator has both linked; #311's own comment
calls persisting real templates "the logged phase-2 follow-up"). The fabricated template also
means the player his real league starts at FLEX is displayed under a dedicated "WR3" slot —
matching "it's a flex position that's starting a WR" word for word.

*Secondary suspect, kept on file:* the #169 rank chip (`CardImpactBlock.tsx:155`,
`` `${position}${rank}` `` → "WR3 → WR12"; flag `trade.position_impact` is ON in
`config/features.json`) renders positional-rank strings that collide with slot-naming
convention. If the operator says the #396 league is Sleeper, this chip is the culprit and the
fix moves client-side (render "WR #3", or drop the position prefix on the second half). Verify
with the operator which league it was (one question, listed in the checklist).

## 2. Root causes

- **#395** — `backend/power_rankings.py:78-96` (canonical greedy: dedicated before flex) +
  `backend/server.py:1278-1298` (breakdown diffs the two canonical fills slot-by-slot with no
  attempt to minimize displayed churn). Not a correctness bug; a presentation/attribution bug.
- **#396** — `backend/server.py:24171-24175` substituting the 3-WR `_MOCK_DEFAULT_LINEUP`
  (`server.py:14588`) for platform leagues, flowing into labels at `server.py:1285-1293`.

## 3. Fix approach

### Fix A (#395) — churn-minimizing slot alignment, backend, display-only

New pure helper in `backend/power_rankings.py`:

```python
def align_starter_slots(eligible, before, after) -> tuple[list, list]
```

Given the two `optimal_starter_slots` outputs (parallel to `eligible`), repeatedly apply
same-side pairwise swaps — swap the contents of slots *i*,*j* on one side when every non-None
player involved is eligible for the destination slot (`LINEUP_SLOT_ELIGIBILITY`) and the swap
strictly increases the count of rows where `before[k].player_id == after[k].player_id` —
alternating sides until fixpoint (template ≤ ~12 slots, trivially bounded). Swaps permute
players among slots they already occupy as a set, so per-side totals, the starter *set*, and
`your_delta`/`their_delta`/`note` are all untouched by construction — only which row a change
is displayed on moves. Called from `_starter_impact` between the two fills and the labeling
(`backend/server.py:1281`). `optimal_starter_slots` itself and every other caller
(power-rankings starters split, `team_review` weakest-slot at `server.py:24617`, mock draft)
stay byte-identical.

Worked outcomes: the #395 shape re-displays as before `QB=Maye, SF=Daniels` → after
`QB=Maye, SF=Fannin` — **one** changed row, `SUPER FLEX: Daniels › Fannin`, which is exactly
the presentation the user asked for. The analogous WR case (trade a WR from a
`WR WR FLEX` league) collapses from three changed rows to one `FLEX` row. Forced cascades
(no second QB on the roster, TE not QB-eligible) still show as multi-row — honestly.

### Fix B (#396) — honest platform template, backend

Fast-track (this fix): give the platform branch its own constant —
`_PLATFORM_DEFAULT_LINEUP = ["QB","RB","RB","WR","WR","TE","FLEX","FLEX"]` (+`SUPER_FLEX`
for `sf_tep`) — used **only** at `server.py:24171-24175`. `_MOCK_DEFAULT_LINEUP` stays
untouched for the mock-draft call sites (:14759, :14807) — surgical change. Rationale: a
2-WR + 2-flex template is the modal dynasty shape; flex labels are *claims the app can
stand behind* (a flex can legally start a WR) whereas "WR3" asserts a dedicated slot the
league doesn't have. Slot values shift slightly for platform leagues (a 3rd RB / 2nd TE can
now start over a 3rd WR) — that is a strict accuracy improvement over forcing WR3.

Follow-up (logged, not this fix): persist each platform league's **real** template at import
— ESPN exposes `lineupSlotCounts` in settings; MFL's league export already reaches
`starters.position` limits (`backend/mfl_service.py:719-781`, `_max_qb_starters`) from which
dedicated-mins + flex-remainder derive. That is #311's own recorded phase-2.

Conditional (operator answer dependent): if the #396 league turns out to be Sleeper, Fix B is
moot for this item and the fix is instead `CardImpactBlock.tsx:155` — disambiguate the rank
chip (e.g. `WR #3 → #12`). Not built by default; awaiting the one verification question.

### Blast radius

`starter_impact.slots` consumers: deck card `CardImpactBlock` (changed rows), calculator
`LineupImpactTable` (full table) — both benefit, no mobile code change required (labels and
row pairing come from the server). Team Review's weakest-slot and platform-league power
rankings pick up Fix B's template via `_league_lineup_slots`; power rankings proper still
uses `_sleeper_lineup_slots` (deliberate #311 deferral, unchanged). Web/extension: no
consumers. API shape unchanged (same keys; labels/pairings only) → `docs/api-reference.md`
gets a semantics note, no contract break.

## 4. File ownership

| File | Change |
|---|---|
| `backend/power_rankings.py` | new pure `align_starter_slots` |
| `backend/server.py` | call alignment in `_starter_impact` (~:1281); `_PLATFORM_DEFAULT_LINEUP` + use at :24171-24175 |
| `backend/tests/test_power_rankings.py` | alignment unit tests |
| `backend/tests/test_trade_evaluate.py` | slots-breakdown tests for aligned display + platform template labels |
| `docs/api-reference.md` | `starter_impact.slots` semantics note (alignment; platform template) |
| `docs/feedback/items/395-lineup-impact-superflex/` | this plan + status |
| (conditional) `mobile/src/components/CardImpactBlock.tsx` | rank-chip disambiguation — only if operator says the #396 league is Sleeper |

## 5. Evidence plan (D-056)

**Unit tests (each proven red by a named sabotage):**

1. `test_align_starter_slots_superflex_cascade` — #395 shape; assert exactly one changed row
   after alignment and that the departing QB displays at `SUPER_FLEX` before. *Sabotage:* make
   `align_starter_slots` the identity → red (two changed rows).
2. `test_align_starter_slots_wr_flex_cascade` — `WR WR FLEX` template, trade the top WR;
   assert single `FLEX` changed row. *Sabotage:* identity alignment → red.
3. `test_align_preserves_totals_and_eligibility` — random-ish rosters: per-side value totals,
   starter sets, and eligibility-validity identical pre/post alignment. *Sabotage:* allow an
   eligibility-invalid swap (drop the eligibility check) → red.
4. `test_align_forced_cascade_untouched` — no second QB on roster; the cascade rows remain.
   *Sabotage:* over-eager alignment that swaps a TE into QB → red via eligibility assert.
5. `test_platform_template_has_no_wr3` — evaluate against a platform league (patch
   `_league_lineup_slots` seam per `test_trade_evaluate.py:634-637` pattern, or the leagues-row
   branch directly); assert slot labels are `WR1 WR2 … FLEX1 FLEX2` and `"WR3" not in labels`;
   sf_tep appends `SUPER_FLEX`. *Sabotage:* revert to `_MOCK_DEFAULT_LINEUP` → red.
6. Existing 113 tests in `test_power_rankings.py` + `test_trade_evaluate.py` stay green
   (baseline run 2026-08-24: 113 passed, 7.08s).

**Code-walk proof:** file:line trace `evaluate Mode B → _starter_impact (server.py:1278) →
align_starter_slots → labeling (1285-1293) → CardImpactBlock.tsx:108-160 changed-row filter`,
showing the #395 payload now carries one changed slot and the #396 payload carries no `WR3`.

**Operator TestFlight checklist (their leagues, v-next build):**

- [ ] Answer first: which league was #396 (Sleeper, ESPN, or MFL)? If Sleeper → switch to the
      conditional rank-chip fix before building.
- [ ] SF league, TradesHome: front a card (or calculator-evaluate) trading Jayden Daniels
      away. "Your starting lineup" shows **one** row — `SF: Jayden Daniels › <backup>` — and
      **no QB row** claiming Maye was displaced.
- [ ] Same trade in the In-league calculator: BEFORE column shows Daniels at SF, Maye at QB.
- [ ] #396 league: front a card touching a WR. No `WR3` slot label anywhere; the flex-started
      WR's row reads `FLEX` (calculator table may shorten per `SLOT_SHORT`).
- [ ] Sanity: lineup **totals/deltas** on both surfaces match the pre-fix build for the same
      trade (alignment must not move numbers).

## 6. Risks

- **Multiple flex/SF slots** (2×FLEX, 2×SUPER_FLEX): alignment swaps must handle duplicate
  slot keys (they operate on indices, not labels) and numbering must stay stable
  (`FLEX1/FLEX2`). Covered by test 5's two-FLEX template.
- **IDP / K / DEF slots:** outside `LINEUP_SLOT_ELIGIBILITY` (`power_rankings.py:38-47`),
  filtered before fill — no rows, unpriced players already omitted (#183). No change.
- **TE-premium (sf_tep):** values differ by format via the seed; alignment is value-neutral
  so format cannot skew it. Fix B keeps the `sf_tep → +SUPER_FLEX` branch.
- **Platform-league value shift (Fix B):** slot totals for ESPN/MFL/Fleaflicker impact
  summaries and Team Review weakest-slot move slightly (2WR+2FLEX vs 3WR+1FLEX). Strictly
  more-accurate direction, but note it in the ship message; goldens touching platform
  lineups (none found) would need re-derivation, not loosening.
- **Alignment fixpoint quality:** greedy pairwise swaps are not a proven global optimum for
  pathological rosters; acceptable — any swap applied is a strict improvement and worst case
  equals today's display. Bounded loop, ≤ ~12 slots.
- **User's real Sleeper lineup still ignored** (deliberate, `power_rankings.py:100-113` —
  stale/empty preseason). Alignment usually reconstructs the user's intuitive assignment, but
  a user who benches a stud on purpose will still see the value-optimal lineup. Unchanged
  posture; not in scope.
