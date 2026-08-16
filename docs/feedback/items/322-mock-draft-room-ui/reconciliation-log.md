# G2 reconciliation log — round 1 → round 2

> Disposition of every objection in [`review-round-1.md`](review-round-1.md)
> (2 blocking, 6 non-blocking), 2026-08-16. All accepted claims re-verified
> against `origin/main` @ `d3fe3ac` before incorporation. The critic's
> assessment of the author's three round-1 corrections (SCHEMA name, bodySm
> 13px, ranking_service import soundness) is accepted as confirmation — no
> action needed beyond the NB items below.

| ID | Objection | Disposition | Where |
|---|---|---|---|
| B-1 | §3's G2/G3 function-level disjointness claim factually wrong: G3 edits `state_payload()` itself (`settings_echo.ownership_source`), plus `mockDraft.ts`, `MockDraftScreen.tsx`, `test_mock_draft.py`, and both shared docs | **ACCEPTED — §3 rewritten.** Verified against G3's `prd.md` §4 (reserved regions: constants block :67–68, `build_settings` :995, `settings_echo` :1414 block) and mirrored its language. §3 now carries a file → region → owner table (five shared files, one shared function, non-overlapping regions) and the orchestrator's binding Phase-2 serialization: **G3 builds and merges first; G2 branches from the group branch after G3's merge and rebases its regions on G3's edits.** The disjointness claim is withdrawn; the claim is now serialization. §4's G3 bullet updated to match. Batch disjointness table to carry the corrected rows (orchestrator). |
| B-2 | T-S9 ("no `by ===` in any my-team predicate") contradicts `sinceUserPick` (:408–:413), which G2 leaves untouched — suite could never go green | **ACCEPTED — resolution (a), chosen deliberately.** T-S9 is scoped to the predicates G2 adds or changes (chip meta, sheet my-team, ticker mine-tint) and explicitly excludes `sinceUserPick`. Tradeoff stated rather than split: option (b) (re-derive off `picked_by_user_id` — "since your *team's* last pick") is arguably truer semantics but is a behavior change beyond the six items' literal text, so under the surgical-change principle it is **deferred**, not half-adopted via a test assertion. Consequence now stated in R-4 and T-F8: in manual mode every pick is `by: 'user'`, so `newest` is always 0 — header reads "Just picked", no new-pick tint, and T-F8 marks that expected, not a bug. The alternative is recorded in §4 (out of scope) as a named future item. |
| NB-1 | `picks[].tier` basis-independence unstated; a builder could wire `board_elo` in for `basis=my_board` | **ACCEPTED — incorporated.** §2 gains a Basis-independence row: tier computed from `ctx.consensus_elo` always, stable across basis toggles; accepted consequence (a My-board-badged player may chip-badge differently) stated as deliberate; explicit "must NOT wire `board_elo` in" instruction to the build agent. |
| NB-2 | R-1's no-sort rests on the unpinned "picks[] arrives ordered" assumption | **ACCEPTED — incorporated (defensive-sort option, per coordinator).** `tickerWindow` now sorts ascending by `pick_no` internally (pure, one line); R-1 states why. T-U1 gains a shuffled-input case with its own sabotage (drop the sort). Chosen over a T-P server-side ordering pin because it makes the guarantee local to the tested helper. |
| NB-3 | Filter+search composition as an inline-JSX AST assertion is fragile | **ACCEPTED — incorporated.** New pure helper `filterPool(rows, position, query)` (`mobile/src/utils/mockPool.ts`) owns the composition; R-11/R-13 updated; T-U2 tests the helper (plus an empty-query case); T-S6 now asserts the screen's undrafted render source is `filterPool` output with no inline predicates — a far sturdier structural check, same coverage. |
| NB-4 | `tier_for_elo` cited at :1286 (mid-docstring); def is at :1272 | **ACCEPTED — fixed.** Verified `def tier_for_elo(` at `ranking_service.py:1272` @ d3fe3ac (`@classmethod` at :1271); R-5 corrected and now notes the classmethod explicitly. (The earlier :1285 sighting was `origin/main` post-d3fe3ac — the file moved between the two.) |
| NB-5 | Extend `mock_draft_service.py`'s own header note (:41–:44) when the import lands, not just architecture.md | **ACCEPTED — incorporated.** R-5 now instructs the build to amend the INV-10 header block alongside the scope.md §4 architecture.md amendment, keeping "performs no I/O of any kind" honest at the point of first reading. |
| NB-6 | `minHeight ≥ 44` reads as a touch-target rule on non-tappable chips | **ACCEPTED — reworded.** R-8 keeps the value for vertical rhythm and two-line-content headroom and now says the chips are non-interactive and this is not a tap-target requirement. |

## Round-1 corrections, as assessed by the critic

All three confirmed sound (review § "Author's three corrections"). One
refinement folded back: `MOCK_DRAFT_SCHEMA` is the *mobile* pin
(`mockDraft.ts:26`, verified = 1) — PRD §7 note 1 updated to say the plan's
name referred to the client-side constant rather than being simply wrong.

## Net effect on scope

No path change (Polish stands), no new backend surface beyond the already-
specced `tier` key. Two new pure-helper files
(`mobile/src/utils/tickerWindow.ts`, `mobile/src/utils/mockPool.ts`) — both
were already implied by the test plan; now they are named requirements. The
only cross-group change is procedural: Phase 2 is serialized (G3 → G2), which
the orchestrator has decided and both PRDs now state in the same terms.
