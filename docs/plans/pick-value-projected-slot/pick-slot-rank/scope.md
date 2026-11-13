# Feature Scope — Projected pick labels as an exact 1..N ranking

**Date:** 2026-11-12
**Entry point:** direct ask. The operator was asked "Should projected pick labels become a 1-to-12 ranking, so each slot appears once?" and answered "Pick labels: yes. Make them exact". The operator was also told that pick values stay as they are.
**Builder:** subagent, worktree `.claude/worktrees/pick-rank`, branch `feat/projected-pick-rank`, cut from `origin/main` 53711036. Decision [D-257](../../../../living-memory/DECISIONS.md).
**Operator sign-off on waivers:** needed for two waivers: analytics (§1c) and the structural mobile guard (§3). Both are listed for the operator. Neither blocks the build, because no client code changed.

Summary: before this change, a projected pick's label slot was the team's expected slot rounded half-up (`round(Σ k·p[k])`). Under that rule two teams could both show 1.04, nobody showed 1.01, and every playoff lock showed 1.10. Now the label slot is the original team's **rank** when the league's teams are ordered by expected slot, ascending, so every slot 1..N appears exactly once. Ties, such as playoff locks that share the playoff slots' midpoint, are broken by expected win-equivalents, fewer first, so the stronger team picks later. The final tie-break is roster id. The price still reads the whole slot distribution and is byte-identical.

Parent feature: [pick-value-projected-slot/](../scope.md) ([design](../design.md)).

---

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [ ] **(b) Existing events cover it:** not claimed. No event carries the label slot.
- [x] **(c) WAIVED, no analytics needed.** This change does not add a user action or an event, and no event property changes. The label is display copy over a price that does not move. *Surface to the operator.*

## 2. Schema & flag scope

- **New/changed tables or columns:** none. The change reads `league_projection_runs.result_json` → `teams[].expected_record`, which the forecast has always written (`backend/league_projections/simulation.py:295`). Nothing is written.
- **New/changed feature flags:** none. The change stays behind `picks.projected_slot_value`, as before. With that flag off, or with no usable forecast, there is no label.
- **New env vars / `model_config` keys:** none. The rollback levers are unchanged. `pick_projection_weight` = 0 or the flag set off removes the projection, prices and labels together. Reverting this commit restores the rounded-mean label.

## 3. Evidence scope

- [ ] **Structural guard:** WAIVED. No mobile, web or extension file changed. The app prints `proj_name` verbatim and never derives a slot (`mobile/src/utils/projectedPick.ts:54-63`). The existing `mobile/tests/check-projected-pick-tag.js` already pins that the app neither composes nor parses the string. `PROJ_SLOT_RE` `^\d\.\d{2}$` accepts every rank up to 1.99.
- [x] **Unit tests:**
  - New file `backend/tests/test_pick_slot_rank.py` (21 tests). It pins:
    - the labels are a permutation of 1..N for 8, 10, 12 and 14 teams, with and without `expected_record`;
    - the ordering follows expected slot;
    - playoff locks are ordered by expected wins, best team last;
    - equal wins fall back to roster id;
    - the tie-breaks are never mixed within one run;
    - roster ids sort numerically;
    - a traded pick shows the original owner's rank;
    - values are byte-identical to `origin/main` 53711036 for a fixture forecast, and the label map is never priced;
    - an uncovered league or pick gets no label;
    - real `simulate()` output feeds the tie-break.
  - Updated: `test_pick_projection.py` (three old rounded-mean label pins removed and replaced by the new file) and `test_pick_projection_wiring.py` (label pins re-derived: top-3 1.01, bubble 1.11, contender 1.12; the real-slot-wins test now uses an order that disagrees with the projection).
  - Sabotage: 11 named sabotages, each red, then green on revert. They are listed in `living-memory/TEST_LEDGER.md` (2026-11-12).
- [x] **Code-walk proof:** [code-walk.md](code-walk.md), from the forecast row to the label on the app row, citing file:line.
- [x] **Manual TestFlight checklist** (the operator runs this once the backend has deployed; no app build is needed):
  1. Open League, then a Sleeper league that has a saved weekly forecast (League Projections shows a run of 3 or more completed weeks, less than 8 days old).
  2. Open three teams' **Picks** (team detail → Draft capital) and note each team's own 2027 1st with its **PROJECTED** tag. Expected: no two of the own-1st slots repeat.
  3. Open the team that sits top of the projected standings. Expected: its own 2027 1st reads **2027 1.<N>** (1.12 in a 12-team league), the last slot.
  4. Open the team that sits bottom of the projected standings. Expected: **2027 1.01**.
  5. Find a traded 2027 1st ("(from …)"). Expected: its slot equals the slot the ORIGINAL team's own pick would show, not the holder's.
  6. Note one projected pick's value before the deploy and check it after. Expected: the same number (the price did not move).
  7. Open a league with no forecast, or an ESPN or MFL league. Expected: picks read "2027 1st" with no PROJECTED tag, as before.
  8. Open Standings, then a team detail. The "Expected pick if this team misses" line is a different number (the conditional expected slot among non-playoff finishes). Expected: it is unchanged and does not have to match the label.
- [ ] **WAIVED:** no.
- `testID`s added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | The two projected-slot paragraphs (deck-card `give`/`receive` and `GET /api/league/picks`) now define `proj_slot` as the original team's rank in the league's projected order. No route was added or renamed. |
| `living-memory/LLD.md` | updated | One line under "### Specific patterns": one label-slot function, a rank and not a price. |
| `docs/architecture.md` | n/a because | No module wiring or data flow changed. The same two functions are on the same path, and `pick_projection` stays a pure leaf. |
| `living-memory/HLD.md` | n/a because | No architecture shift. |
| `docs/cross-client-invariants.md` | updated | § Projected slot value → "The display contract" rewritten to describe the rank rule, its tie-break, and that `proj_slot` is never priced. |
| `docs/glossary.md` | updated | "Projected slot / `· projected`" now defines the rank. |
| ADR or `DECISIONS.md` entry | updated | D-257. |

## 5. Ship gate declaration

- **CI green:** `backend-tests`, `mobile-typecheck` and `maestro-testid-lint` on the pushed sha. No mobile file changed. Locally, the 45 related backend test files plus the new file ran green on Python 3.12.3 (TEST_LEDGER 2026-11-12).
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` 2026-11-12.
- **TestFlight verification:** the operator runs the §3 checklist after deploy and logs it in TEST_LEDGER.
- **Express lane declared by the operator?** No. Full gates apply.

## Decisions taken in the build

- **Ordering key:** ascending expected slot `E = Σ k·p[k]` over the same distribution that sets the price (playoff probability spread evenly over the playoff slots). E is rounded to 1e-9 so float noise never sets an order.
- **Tie-break 1, expected win-equivalents (W + ½T from `expected_record`), fewer first.** The forecast already carries this per team. It has no projected playoff finish or title odds, and expected wins is its closest strength signal. It is used only when every team in the run has it, so one run never mixes two tie-breaks. Every run from the current model has it.
- **Tie-break 2, roster id**, numeric where possible.
- **`DECK_PIPELINE_VERSION` is not bumped (it stays 30).** The label is baked into stored deck cards (`player_to_dict` → `name`/`proj_slot`/`proj_name`). However, `pick_projection.py` and `pick_values.py` are both in `server._ENGINE_CODE_MODULES`, whose bytes hash into every stored page's `engine_version`. This change edits both files, so no page stored before the deploy is served after it. `server.py` is untouched, so `test_deck_pipeline_digest` stays green at v30. A bump would be redundant.
- **Nothing uses the label slot numerically.** `proj_slot` is a string on the wire (`ranking_service.Player.proj_slot`, `power_rankings.py:319`, `server.py:15512`). Nothing sorts, prices or deduplicates by it. `_projection_terms` (`pick_values.py:770`) never reads `projection.slots`, and `test_values_never_read_the_label_slots` pins that.

## Out of scope (unchanged on purpose)

- Pricing: `priced_pool_value` / `_projection_terms` / `factor` read the full distribution exactly as before.
- "Newest complete baseline run from any user" (`server._load_pick_projection_summary`).
- The forecast's max-PF draft-order assumption for non-playoff teams (`league_projections/simulation.py:279`), and the even spread of playoff probability over playoff slots.
- Coverage: round 1 of the forecast's draft season only, Sleeper only, behind the same gates.
- The Standings detail's "Expected pick if this team misses" (`conditional_expected_pick`), a different number that claims nothing about the label.
- Known limit: a near-lock (99.9 % playoff odds) has a fractionally lower E than a 100 % lock, so it ranks before the lock even with more expected wins. The ordering follows expected slot first, as specified.
