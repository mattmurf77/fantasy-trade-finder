# ADR-009 — Rookie Scope as a Post-Elo View Filter (and the Merged-Band Save)

**Status:** Accepted (shipping dark behind `ranks.rookie_subset`)
**Date:** 2026-08-06
**Initiative:** Rookie rankings + live draft support, milestone M2 (docs/plans/rookie-draft/ — plan.md FINAL/dual-agent converged, hld.md, lld.md §4.2/§4.3). Records the two decisions in that milestone that are not self-evident from the code.

---

## Context

Users want to rank the incoming rookie class on its own — during a rookie draft, a rookie class is the only thing they care about, and 5 rookies scattered through a 60-player RB board is not a usable surface.

The obvious implementation is "a rookie board". The constraints that kill it:

- **Tier bands are absolute Elo**, anchored to pick values (`backend/tier_config.json`, the #117 8-tier ladder). A rankings space that is not the main one breaks tier colors, trade values, #161 demotion, and adds a fifth cross-client invariant to mirror.
- **One board serves drafted and undrafted leagues at once.** Membership churn is what #207 Option A was written to avoid; a rookie who "leaves the rookie board" must not lose their value.
- **Rookie-vs-vet comparisons are the whole point.** A user ranks a rookie by asking what veteran they would trade for them. Those swipes exist in `swipe_decisions` and must keep counting.
- **`users.tier_overrides` is a wholesale-overwritten JSON blob with no history.** A prior filtering bug permanently destroyed a user's board. Any feature that writes a *partial* board is writing into that hazard.

## Decision

### 1. Scope is a post-Elo VIEW filter, never a pool filter

`?scope=rookie` narrows the **already-computed, already-enriched response list**, immediately before serialization. `RankingService._pool`, `_compute_elo`, `apply_reorder` and `apply_anchor` all continue to operate on the FULL position pool.

Concretely, on the rejected alternative: filtering the pool before `_compute_elo` would drop every rookie-vs-vet swipe from the replay, so a rookie's "rookie-board Elo" would silently diverge from their board Elo — two numbers, two tier labels, two trade values, for one player. The bar this decision buys is testable and tested: **for every rookie pid, scoped Elo == unscoped Elo, exactly** (`test_rookie_scope.py::test_m2_02_*`, which also asserts that a rookies-only pool genuinely produces different numbers, so the identity is not a tautology).

There is **one board per user per format.** Rookie scope is a lens on it.

Corollaries:

- The filter lives in `server.py` (the response layer), not in `ranking_service.py`. `ranking_service.py` gains exactly one new method (below).
- Scope is **never** a client-side filter: five clients mirror these invariants, and a client-side rule is a fifth place to drift.
- With the flag off, the query parameter is **not read at all** — not parsed, not validated, not logged. Flag-on and flag-off responses are byte-identical structurally, not by diffing.
- Generic pick rungs are **out of scope** (operator decision O10 — players only), even though they are pool members and draft-relevant. Revisit alongside M6 slot values.
- Trio *candidate selection* is scoped via the existing `skipped_player_ids` channel; the Elo updates a user's picks produce are unchanged full-board updates. Two lanes cannot honour that channel and are therefore disabled under scope: the `cross_pos` trio variety and the `swipe.qc_compliments` QC trio, both of which reach across the full pool by construction.
- A thin or not-yet-loaded class is a **typed 200** (`{empty:true, reason}`), not the unscoped path's 400. Sleeper's dump carries no rows for a class until ~late April, so "there are no rookies yet" is a designed state of this feature, not an error.

### 2. Scoped tier saves use the merged-band rule

A scoped board shows the user only part of a tier's membership. Two write shapes behave differently and the distinction is load-bearing:

- **Permutation-shaped writes** (`apply_reorder`, `apply_anchor`) were **already subset-safe** — they permute the submitted subset's own Elo multiset and write only submitted pids. They are deliberately NOT modified; a test pins them against a future "fix".
- **Tier saves are not**, because `apply_tiers` spreads a submitted list linearly across the band. Given a rookies-only list it pins the top rookie at the band ceiling, above every veteran incumbent the user never saw.

The rule (`RankingService.apply_tiers_subset`, new; `apply_tiers` untouched so the unscoped lane stays byte-identical): anchor the scoped pids by their current values clamped into the band, **merge** them into the band's existing full membership, spread linearly over the FULL merged list, and **persist the scoped pids only**.

This is the only construction satisfying both halves at once:

| Requirement | What breaks it |
|---|---|
| A scoped pid gets exactly the Elo an equivalent full-band save would give it | spreading over the scoped list alone (every rookie floats to the top of the band) |
| Every member the user never saw keeps its override byte-for-byte | persisting the whole merged list (rewrites untouched members) |

Both halves are tested; the equivalence bar is asserted literally, by running the unscoped `apply_tiers` over the computed merged order on a cloned service and diffing.

Riders on the scoped save:

- **`cleared_pids` / `demoted_pids` are scoped to the visible subset** (#161 under scope, operator decision O4). A demotion for a player the user could not see is ignored — that is the one path that can silently damage a board.
- **A scoped save never marks a position complete.** `tiers_saved` / `all_done` are completeness markers read by LeagueScreen's ranked count, `quicksetProgress`'s cache, the web celebration and #244 launch routing. One line, four surfaces; the route READS `get_tiers_saved` instead of writing `save_tiers_position`.
- **The `member_rankings` publish stays full-board.** Leaguemates' trade math reads it; scope must never reach it.
- **A one-time pre-scope snapshot** of the user's whole override blob is taken before the first scoped save, stored as a sibling key in the same column, with an operator restore procedure. This is an explicit **precondition for flipping the flag** — given the column's history, a partial-write feature without a recovery path is not shippable. It required fixing `save_tier_overrides`, which until now destroyed any non-format key on the next save.

## Consequences

- **Positive:** rookie scope is additive and cheap — one function before `jsonify`, one new ranking-service method, no new table, no migration, no second Elo space, no new cross-client invariant. Values are synced by construction rather than by a reconciliation job, which is what makes the consolidated cross-position rookie view (operator decision O1) free to build later. Rollback is a flag flip.
- **Negative / watch:** a partial save positions incumbents without rewriting them, so a scoped save can read as slightly out of order against stale neighbours until the next full-band save (RB-7 — inherent to any partial save, documented in the runbook rather than engineered around). The QC-compliment lane is silently absent under scope (deliberate degradation). `apply_tiers` and `apply_tiers_subset` now encode the same band arithmetic in two places — the equivalence test is what keeps them honest, and it must be kept if either is edited.
- **Deferred, named:** generic pick rungs under scope (O10 = no, revisit with M6); web parity (M7); the mobile shared scope control and consolidated rookie view (M2's client wave).
