# Feature Scope — Tier-bounded voting (a pin confines a player to a tier, not to a value)

**Date:** 2026-08-18
**Entry point:** operator design decision, relayed 2026-08-18; [PLAN.md](PLAN.md) Phase 0 lineage. Supersedes parts of
[scope-phase0.md](scope-phase0.md), which shipped hours earlier as `e8ae476`.
**Driven by:** [docs/reviews/2026-08-18-valuation-age-audit.md](../../reviews/2026-08-18-valuation-age-audit.md) §3.4 / §5.1.
**Builder:** backend build agent, branch `feat/tier-bounded-pins`.

**The operator's words:** *"for deliberately placed players in tiers, the voting can just
rerank a player within his current set tier. So some adjustment is expected, but nothing
massive across a tier."*

---

## 0. What changes, in one paragraph

A tier save writes an Elo **override** that pins a player. Until now `_compute_elo` seeded him
from that override and then skipped every rating update — a total freeze — which composed
perversely with the trade layer's direction-blind confidence shrinkage and made 17 down-votes
on Davante Adams *raise* his effective trade value 12.5%. Phase 0 stopped that by discarding
those votes entirely (`n = 0`, priced at consensus) and by adding a release-on-newer-swipe
path. The operator's call replaces both with something better: the pin names the **tier** the
player was placed in, and his Elo then evolves from votes normally, **clamped to that tier's
band**. Bands in `backend/tier_config.json` are 165–205 Elo wide, so a player genuinely
re-ranks inside his tier and never crosses one.

```
placed_tier = tier_for_elo(pinned_elo, position, scoring_format)
lo, hi      = tier_bands_for(position, scoring_format)[placed_tier]
new         = current + k * (outcome - expected)
rating      = min(max(new, min(lo, pinned_elo)), max(hi, pinned_elo))
```

The band is widened to contain the pin (`min(lo, pin)` / `max(hi, pin)`) because
`tier_config.json` has small gaps between bands (1576–1579 sits between `second`.max 1575 and
`first_1`.min 1580), the top band's max is finite, and `apply_reorder` permutes raw seed Elos
that need not land inside any band. Without the widening the first vote to touch such a player
would snap him into the band — the clamp would move him on its own, which it must never do.

## 1. This thaws every existing pin, with no data write

**The clamp is computed at Elo-compute time from the pinned value the board already stores.**
There is no schema change, no migration, no backfill, no opt-in and no operator decision. All
**2,735** pinned entries in prod are covered the moment this deploys, and reverting is a single
`PUT /api/admin/config` that stops deriving the band — the stored data is byte-identical either
way.

That **resolves the pending decision in [scope-phase0.md](scope-phase0.md) §6** (whether to
stamp legacy pins with a chosen instant `T`, and whether to flip `pin_legacy_at_epoch`). Both
levers existed only to make Phase 0's *release* mechanism reach pins that carry no timestamp.
Tier-bounding needs no timestamp at all. The §6 proposal is left recorded rather than
withdrawn, since it remains the lever for the Phase 0 revert path.

### Measured on prod, 2026-08-18 (SELECT only, `default_transaction_read_only=on`)

Every board replayed through the real `RankingService._compute_elo` / `_pin_bounds`, both
knob settings, using `replay_from_db` so the persisted swipe order and K-factors are the
production ones. The "today" column reproduces the audit's 2,721-inert figure exactly, which
is the validation that the replay is faithful.

| | Recorded comparisons | Effective (≥1 side actually moves) | Inert |
|---|---|---|---|
| Today (freeze, Phase 0 defaults) | 4,013 | **1,292 (32.2%)** | 2,721 (67.8%) |
| **Tier-bounded** | 4,013 | **3,938 (98.1%)** | 75 (1.9%) |

| | Pinned entries | Players who actually move |
|---|---|---|
| Today | 2,735 | **0** |
| **Tier-bounded** | 2,735 | **667 (24.4%)** |

The ceiling on that second number is **739** — the pins that have ever appeared in a recorded
comparison at all (27.0% of 2,735; the other 73% were bulk-written by Quick Rank and never
voted on). So **667 of 739 = 90.3% of every pin the user has ever voted on now moves.** The 72
that still do not split into **47 pins below the lowest band** (`tier_for_elo → None`, i.e. the
#161 demotion Elo / anchor "no value" markers, deliberately frozen — see §3) and 25 that are
clamped hard at a band edge.

Per board:

| User | Format | Comparisons | Pins | Effective (today → bounded) | Movers |
|---|---|---|---|---|---|
| 313560442465169408 | 1qb_ppr | 1,428 | 737 | 91 → **1,388** | 260 |
| 313560442465169408 | sf_tep | 282 | 626 | 7 → **280** | 145 |
| 479505639769370624 | 1qb_ppr | 701 | 644 | 236 → **694** | 139 |
| 867830050538598400 (operator) | 1qb_ppr | 903 | 547 | 525 → **877** | 76 |
| 867830050538598400 (operator) | sf_tep | 296 | 123 | 30 → **296** | 47 |
| four boards with no pins | — | 403 | 0 | 403 → 403 | 0 |

### One honest correction to the audit

Replaying the operator's own board shows Davante Adams (`2133`) moving **1565.28 → 1530.15**
under tier-bounding — real movement, toward the `second` floor at 1400, ending well inside
[1400, 1575]. But his **effective trade value does not change**: all 18 of his 2026-08-17
comparisons are `decision_type = 'trade'` (deck like/pass), not `'rank'` (trio swipes), and
trade decisions have **never** contributed to `comparison_counts` for *any* player —
`_compute_stats` only walks `_swipes`. So his `n` is 0 both before and after, and he prices at
exactly the consensus seed 1138.8 either way.

The audit's §3.4 arithmetic assumed `n = 6` for him. That was reconstructed from SQL over
`swipe_decisions` without filtering `decision_type`, and the audit flagged its own confidence
on the number as medium-high for exactly this reason. **The mechanism the audit describes is
real and is fixed here** — it is what the unit tests exercise, and it is what the 353 → 1,666
jump in live *ranking* comparisons measures — but the specific +12.5% figure attributed to
Adams overstates his case. Worth recording so nobody re-derives it later and thinks the fix
failed.

## 2. Analytics scope

**(b) Existing events cover it.** No new events, no taxonomy row, no emission change of any
kind. Elo arithmetic is not instrumented; the only observable is the board itself.

| Existing event | Question it answers here |
|---|---|
| `swipe` (`user_events`) + `swipe_decisions` | Unchanged. The comparison corpus is untouched; only its *interpretation* changes. |
| `deck_impressions` (`features_json`) | Decks will churn as 667 players' personal Elos move. Impression volume and asset mix are the read on whether the churn is an improvement. |

**Instrumentation gap carried forward, not waived.** `users.tier_overrides` still has no
provenance, so a deliberate hand placement is indistinguishable from a Quick Rank bulk save
(audit §7). Tier-bounding makes this *less* urgent than Phase 0 did — the failure mode of
mis-trusting a bulk-written pin is now "he can only move inside a tier he may not have chosen"
rather than "he is frozen forever" — but it is still the single most valuable thing to
instrument next.

## 3. Schema & flag scope

- **New/changed tables or columns:** **none.** See §1 — this is the whole point.
- **New/changed feature flags:** none. Same reasoning as Phase 0: a `features.json` flip needs
  `POST /api/feature-flags/reload`, while a `model_config` knob is live-editable via
  `PUT /api/admin/config/<key>` with no deploy, which is what a kill switch should be.
- **New `model_config` keys:** one. Two existing keys change their **default**.
  → `docs/config-reference.md` updated.

  | Knob | Default | Kill value | Effect of the kill value |
  |---|---|---|---|
  | `pin_tier_bounded` | **1.0 (new)** | 0.0 | A pin freezes again — the pre-2026-08-18 contract |
  | `pin_exclude_comparisons` | 1.0 (unchanged) | 0.0 | `comparison_counts()` returns raw unique-opponent counts (both consumers) |
  | `pin_unpin_on_newer_swipe` | **1.0 → 0.0** | — | Superseded; kept as the Phase 0 revert path |
  | `pin_legacy_at_epoch` | 0.0 (unchanged) | — | Superseded; inert while F2 is off |

  `pin_tier_bounded=0` + `pin_unpin_on_newer_swipe=1` reproduces `origin/main` byte-for-byte.
  All four at `0.0` reproduces the pre-Phase-0 tree, which `test_override_pin_unpin.py`
  continues to gate against its own captured golden.

### Decisions taken inside this scope

| Question | Decision | Why |
|---|---|---|
| **`pin_exclude_comparisons` — revert or narrow?** | **Narrow it.** Keep it ON, with the rule generalised to what its docstring always said: count only the comparisons that actually *moved* the player. | See §4 — this is the consequential call. |
| What about a pin **below every band** (`tier_for_elo → None`)? | **Stays frozen**, and still scores `n = 0`. | Below 1150 is where `DEMOTED_ELO` (#161 — a player the user explicitly *passed over* in a Quick Set save) and the anchor wizard's "no value" answer put people. Those are deliberate "unranked, pending placement" markers, not tier placements; there is no tier to re-rank inside, and letting a stray comparison drag one back onto the board would undo an explicit user action. 47 such pins in prod. Pinned by `test_a_pin_below_every_band_stays_frozen`; the branch is a `continue`, not an exception, and a separate test asserts the rest of the board still computes. |
| A pin in a band **gap**, or above the top band's max? | **Widen the clamp to contain the pin.** | `apply_reorder` permutes raw seed Elos; `tier_config.json` has gaps and a finite top. Without widening, the clamp itself would move a player the moment anyone voted near him. With it, the invariant "only votes move a player" holds unconditionally. Pinned by two tests. |
| Interaction with F2 if the operator turns it back on? | **A released pin is unclamped.** | Release means the pin is *gone*; tier-bounding governs pins still in force. Any other rule would make the Phase 0 revert path only half a revert. Pinned by `test_a_released_pin_evolves_unclamped_when_f2_is_turned_back_on`. |
| Do **trade** like/pass signals move a bounded player? | **Yes** (they always did move un-pinned players) **but they do not build confidence** — unchanged from before. | `_compute_stats` has only ever counted ranking swipes, so trade decisions have never entered `comparison_counts` for anyone. Making them count would be a separate, larger product change. It is why the Adams case in §1 moves his Elo but not his price. |
| Where does the live-comparison map come from? | `_compute_elo` records, per pinned player, which opponents' ranking comparisons actually changed his rating; `comparison_counts` reads it. | One source of truth for "did this vote do anything", instead of a second replay loop that could drift from the first. Costs `comparison_counts` one `_compute_elo` call, which is memoized on the same key and which every caller already makes. |

## 4. The `pin_exclude_comparisons` decision, argued

Phase 0's F1 excluded pinned players from the confidence map because their votes were provably
inert. Under tier-bounding most of those votes are no longer inert, so the premise is gone and
the rule has to be re-decided.

**Reverting it outright is wrong.** The audited inversion — a direction-blind weight `w =
n/(n+n₀)` rising on votes that cannot move the rating — does not disappear under tier-bounding;
it *relocates to the band edges*. A user who keeps down-voting a player is precisely the user
who drives him to his tier floor, and every vote after that point would raise `w` and pull the
effective value back toward the floor-pinned Elo. If that floor sits above consensus (a player
placed in `first_1` whose consensus is a 3rd), the user's continued down-votes would once again
make the engine want him **more**. Reverting reinstates the exact defect for the exact
population most likely to hit it.

**Leaving it as Phase 0 wrote it is also wrong**, and this is the bigger error of the two: it
sets `n = 0` for every still-pinned player, so 78% of the operator's board priced at *exactly*
the consensus seed. That threw away the tier placement *and* the votes — an "honest" answer
only while the votes really were inert.

**So: narrow it.** Count a comparison when it changed the player's rating. That is the
generalisation of the rule Phase 0 wrote (its docstring already said "actually MOVED"), and it
partitions cleanly:

| Case | Counts? | Rationale |
|---|---|---|
| Vote moves a pinned player inside his band | **yes** | Real evidence; the board now reflects the vote, so the confidence should too |
| Vote moves him partway and the clamp absorbs the rest | **yes** | His rating changed |
| Vote pushes him further past the edge he already sits on | **no** | Nothing changed. Counting it raises confidence in a number the user was trying to lower |
| Vote on a pin with no band (unranked) | **no** | Frozen, exactly as before |
| Any comparison on an un-pinned player | **yes** | Untouched — the recount only ever visits pinned pids |

`_value_uncertainty` keeps sharing the map, for the same reason as Phase 0: confidence earned
from updates that changed nothing is false precision. One knob still turns both consumers off
together.

**Measured effect of the narrowing:** live ranking comparisons across prod rise from 353 to
1,666 — those 1,313 player-sides are votes Phase 0 was discarding that now legitimately weight
the user's own board.

### The residual, disclosed rather than buried

Sweeping the audited fixture by vote count, effective value goes
1138.8 → **1162.2** → 1142.3 → 1094.4 → 1004.0 (n = 0, 1, 2, 5, 17).

The step from n=0 to n=1 **rises 2.05%**. That is not the audited defect returning; it is the
shrinkage model working as specified. At n=0 the weight is 0, so the player prices at the pure
consensus seed and the tier placement counts for *nothing*. The first vote that moves him gives
his board weight 0.2 — and his board says he is worth a 2nd, which is more than consensus. Every
subsequent down-vote reverses it, monotonically, ending 11.8% *below* consensus. Direction is
respected throughout: at equal vote counts a down-voted player is always priced below an
up-voted one. Pinned by three tests
(`test_the_very_first_vote_raises_value_a_documented_residual`,
`test_more_downvotes_never_raise_value_once_the_board_has_weight`,
`test_downvotes_never_price_above_upvotes_at_the_same_vote_count`) so it cannot change silently.

The clean fix for the residual is to let a **tier placement itself carry confidence** rather
than starting a placed player at `n = 0` — that is a change to what `confidence` *means*, with
blast radius across `_shrink_user_elo`, `_value_uncertainty` and the fairness gate. Out of
scope here; recorded as a follow-up.

## 5. The band-edge question — recommendation

When a player is clamped at a band edge and further votes push him harder against it, those
votes do nothing. Three options were on the table:

- **(a) accept it silently** — rejected. It is the same "voting against a control that cannot
  move" the audit found, one tier down, and it would quietly re-open the inversion through the
  confidence weight.
- **(b) exclude only those votes from confidence counts** — **shipped**, as §4. It is the
  arithmetic floor under any of the three: it makes the engine stop *rewarding* the dead votes.
  On its own it is not enough, because the user still cannot see why nothing is happening.
- **(c) a UI affordance** — **recommended, and it is the real answer.** *"He's at the bottom of
  'worth a 2nd' — re-tier him to go lower."* Ideally shown on the ranking surface at the moment
  the vote lands, since that is when the user has the intent. The data is already server-side:
  the override map, `tier_for_elo`, and `tier_bands_for` are all exposed, and
  `GET /api/tier-config` already ships the bands to every client.

**Recommendation: (c), on top of the (b) that shipped.** (c) is a client change and is
explicitly **not built here** — this branch is backend-only. It is the natural home for
[audit F3](../../reviews/2026-08-18-valuation-age-audit.md#8-recommended-fixes-cheapest-high-confidence-first)
("surface the pin in the ranking UI"), which the operator already backlogged in `NEXT.md` as
the *"your vote can't move him"* cue — that cue should now read *"your vote can't move him
**further**"*, and should fire on the band edge rather than on the pin, because under
tier-bounding a pin no longer blocks anything by itself.

## 6. Test scope

- **Maestro / simulator: WAIVED — n/a.** Backend-only; no mobile, web or extension file
  touched. Per **D-056** Maestro and the simulator are retired entirely, so the evidence delta
  is structural tests + a code-walk, which is what this section provides.
- **Capture delta:** none — no visual change, and `screens/` is frozen at 2026-08-11 (D-056).
- **`testID`s:** none added or renamed.
- **Backend pytest:**

  | File | Covers |
  |---|---|
  | `backend/tests/test_pin_tier_bounded.py` (**new**, 33 tests) | Kill-value byte identity vs a **captured** golden + a guard that the golden still records the freeze; the Adams scenario (17 down-votes → materially down, never outside [1400, 1575]); clamp at both edges; a pin exactly on a band boundary; a pin in a band gap; a pin above the top band; unranked/None-tier pins (frozen, not crashed); a zero-vote pin is untouched by the clamp; a clamped player climbing back into the band; both scoring formats, plus a monkeypatched band proving the clamp reads the service's own format and the player's own position; the `pin_exclude_comparisons` narrowing in both directions and its `_value_uncertainty` sharing; monotonicity, the disclosed n=0→1 residual, and direction-awareness; the F2 interaction both ways; the knob in both memo keys; a no-pin board being bit-identical either way. |
  | `backend/tests/test_override_pin_unpin.py` (**updated**) | Its 41 tests gate the **Phase 0** contract, which is still reachable by knob and is the documented revert path. It now states that configuration explicitly instead of reading today's defaults, so it keeps testing what it was written to test. |
  | `backend/tests/test_elo_memoization.py` (**updated**) | Two tests asserted a pinned player's Elo *exactly*, which was the freeze contract. Split: the memo contract (cold == warm) plus "inside his band" under today's defaults, and a new test asserting exactness again under `pin_tier_bounded=0`. |

- **Byte-identity is proved by capture, not assertion.**
  `backend/tests/fixtures/pin_tier_bounded_golden.json` was generated by running the new test
  module's own `build_service`/`snapshot` — copied verbatim into a detached worktree of
  **pristine `origin/main`** (`9a20ca8`, the branch point; `git diff e8ae476..9a20ca8 -- backend/` is empty) —
  before a line of production code changed, and is compared as a whole document. A guard test
  asserts the golden still *exhibits* the freeze (every pinned player exactly on his pin, every
  pinned count 0, the un-pinned control moved), so the proof cannot rot into measuring nothing.
- **Mutation-checked**, each mutation applied to a clean tree:

  | Mutation | Result |
  |---|---|
  | Remove the clamp | 11 tests fail |
  | Don't widen the band to contain the pin | 2 fail (`…band_gap…`, `…above_the_top_band…`) |
  | Let an unranked pin float free | 1 fails (`…below_every_band_stays_frozen`) |
  | Count clamped-away votes as confidence | 3 fail (`…swallowed_by_the_clamp…`, `…uncertainty_shares…`, `…memo_also_tracks…`) |

- **Full suite:** `pytest backend/tests` → **3,314 passed, 1 skipped** (pre-existing skip), against a **3,280** baseline measured on `origin/main` `74620a7`. The +34 is this branch's own.

### Code-walk proof (replaces a simulator capture)

1. `ranking_service._pin_bounds(pool_ids, released)` — for each pin still in force, reads the
   player's position, calls `tier_for_elo(pin, pos, self._scoring_format)`, looks the band up in
   `tier_bands_for(...)` and stores `(min(lo, pin), max(hi, pin))`. `None` tier ⇒ omitted ⇒ the
   player is absent from `bounds` ⇒ frozen.
2. `_compute_elo` — `_moves(pid, ts)` now returns `pid in bounds` for a pinned, unreleased
   player (it returned `False` unconditionally). `_apply(pid, delta, other, track)` clamps and
   records `moved[pid].add(other)` only when the rating actually changed and only on the
   ranking loop, matching `_compute_stats`, which has only ever counted ranking swipes.
3. `_elo_moved` is stored beside `_elo_cache` under the same key, so a warm call cannot serve a
   stale map.
4. `comparison_counts()` → `self._compute_elo(pool)` → `counts[pid] = len(moved.get(pid, ()))`
   for pinned pids only. Un-pinned counts come from `_compute_stats` as before.
5. → `backend/server.py`: `confidence_counts = service.comparison_counts()` → passed as
   `confidence=` into `trade_service.generate_trades`.
6. → `trade_service._shrink_user_elo(user_elo, seed_elo, confidence)`: `w = n/(n+n₀)`; and
   `_value_uncertainty(pid, confidence)`: `range_base/sqrt(1+n)`.
7. → `user_value = {pid: elo_to_value(e) …}` — the value the engine prices packages with.
8. `_pin_cfg_key()` folds `pin_tier_bounded` into both memo keys, so a kill pulled via
   `PUT /api/admin/config` takes effect on warm sessions without waiting for a `_version` bump.

## 7. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/config-reference.md` | **updated** | § Board-override pins rewritten: the new knob, the two revert paths as a table, and both superseded knobs re-described as superseded rather than deleted. |
| `docs/glossary.md` | **updated** | New: *Tier-bounded voting*, *Band clamp*. Rewritten: *Board override (pin)*, *Pin release (unpin)* (now marked superseded), *Live comparison* (32.2% → 98.1%). |
| `docs/api-reference.md` | **n/a** | No route added, renamed, removed, or changed in shape. `PUT /api/admin/config/<key>` accepts the new key through the existing generic mechanism. |
| `docs/data-dictionary.md` | **n/a** | No table or column added, changed or removed. The `__override_at__` sibling key Phase 0 added is untouched and still documented there; it is simply not read while F2 is off. |
| `living-memory/LLD.md` | **n/a** | No convention shifted. Same call graph, same storage shape, different arithmetic inside two existing functions. |
| `docs/architecture.md` / `living-memory/HLD.md` | **n/a** | No module wiring, data flow, client or major flow change. |
| `docs/cross-client-invariants.md` | **n/a** | No shared constant, enum or colour changed. Tier bands, Elo→value and K-factors are read, not modified. Clients already fetch the same bands via `GET /api/tier-config`, so no client can drift from the clamp. |
| `docs/adr/` | **n/a** | Not an architectural choice — a scoring-rule change behind a live knob, which is what `DECISIONS.md` is for. |
| `living-memory/DECISIONS.md` | **updated** | D-076. |
| `living-memory/TEST_LEDGER.md` | **updated** | Suite result, the captured golden, the mutation matrix, and the prod replay. |
| `docs/plans/three-model-bakeoff/scope-phase0.md` | **not edited** | Left as the historical record of what shipped that morning. §6's open backfill decision is answered here in §1 rather than by rewriting it. |

## 8. Ship gate declaration

- **Simulator-gate tier: 4 — none, CI only.** Backend-only change, no mobile surface touched.
  Under D-056 the pre-push simulator marker is satisfied with `FTF_SKIP_SIM_GATE=1`; the
  evidence run in its place is the full `pytest backend/tests` suite, the two captured goldens,
  the four-mutation matrix, and the read-only prod replay in §1.
- Evidence: `living-memory/TEST_LEDGER.md`.
- Operator deviation from the matrix: none. No express lane was taken for any part of this work.

### Bright-line note (CLAUDE.md § Feature gates)

This changes **scoring math** — a value the trade engine prices packages with — for every user
with a pinned board, i.e. everyone who has completed Quick Rank. It is explicitly not a "quick
fix", so the full gates were applied: this scope block, 33 new tests plus two captured goldens,
the docs table above, and a live-editable kill switch. No schema, no API contract, no
feature-flag surface and no analytics event is touched, so the *bright line* itself is not
crossed; the design decision it implements came from the operator directly.

## 9. Deferred

- **(c) from §5 — the band-edge UI affordance.** Client work; the natural home for audit F3 and
  for the `NEXT.md` "your vote can't move him" cue, which should be re-scoped to the band edge.
- **Letting a tier placement carry confidence** (§4's residual). A change to what `confidence`
  means, touching `_shrink_user_elo`, `_value_uncertainty` and the fairness gate.
- **Trade like/pass building confidence.** They move Elo but have never counted toward `n`.
  Unchanged here, but it is why the operator's Adams case moves without re-pricing (§1).
- **Pin provenance** (audit §7) — hand placement vs Quick Rank bulk save is still
  indistinguishable. Less urgent than it was, still the highest-value instrumentation left.
- **Audit F4–F6** — value-preserving `apply_tiers` spread, the divergence sanity gate, and the
  dark `trade.outlook_blend` age curve. Untouched. F4 is worth re-reading in this light: the
  linear intra-tier spread is now the thing that decides where inside his band a player *starts*,
  which matters more than it did when the start was also the end.
