# Feature Scope — Phase 0: unblock the ranking boards (override pins + forced regeneration)

**Date:** 2026-08-18
**Entry point:** [PLAN.md](PLAN.md) Phase 0, driven by [docs/reviews/2026-08-18-valuation-age-audit.md](../../reviews/2026-08-18-valuation-age-audit.md) §8 F1/F2. Fix 3 folded in mid-flow by operator decision (see §7).
**Builder:** backend build agent, branch `feat/unpin-overrides`
**Operator sign-off on waivers:** the Maestro/capture waivers in §3 are the standing D-056 posture, not per-feature waivers. The one item needing a genuine decision — whether to backfill timestamps onto the 2,735 legacy pins — is **left unexecuted** in §6.

---

## 0. What is broken, in one paragraph

A tier save writes an Elo **override** that pins a player; `_compute_elo` then skips every
rating update for them. Separately, `trade_service._shrink_user_elo` blends personal Elo
toward the consensus seed with `w = n/(n + shrink_pseudocount)`, where `n` is the
**comparison count** — it reads how *much* you voted, never which *way*. Composed, they
invert intent: a pinned player's Elo cannot move, so every extra comparison only raises `w`
and drags the effective trade value further toward the pin. On the operator's board the pin
sat *above* consensus, so 17 down-votes on Davante Adams raised his effective trade value
from 1138.8 to ≈1281.4 (**+12.5%**). Voting a player down made the app want him more. At
audit time **67.8% of all 4,013 recorded comparisons had both players pinned**, so the Elo
update was a no-op on both sides.

A third defect, found by a peer session, sits directly downstream: `POST /api/trades/generate`
gated its cache-hit branch on `force` but **not** its in-flight branch, so a forced
regeneration arriving while a job was running returned that job verbatim. A board change that
alters values — including a pin released by this very work — could therefore never reach the
user's deck.

---

## 1. Analytics scope

**(b) Existing events cover it.** No new events; no taxonomy row added.

| Existing event | Question it answers here |
|---|---|
| `deck_impressions` rows (F1 spine, flag `deck.signal_v2`) | Did a forced regeneration produce a *served* deck? Superseded decks now write **zero** rows, so impression volume becomes an honest count of decks a user could see. |
| `trades_generated` | Deck supply per user-league. Superseded jobs no longer emit it (same reasoning as above). |
| `swipe` (`user_events`) + `swipe_decisions` | Unchanged. The comparison corpus is untouched; only its *interpretation* changes. |

**Two deliberate emission changes, recorded rather than silently made:** a superseded job now
writes no `deck_impressions` rows and fires no `trades_generated` event. Neither event's
schema, name or properties change — the change is that a deck **nobody was ever served** stops
being counted. Without it, part 1 of Fix 3 would silently poison the corpus that the whole
deck-signal pipeline is built on: rows with a structurally zero chance of a view. Both revert
with `force_supersedes_running = 0`.

**Instrumentation gap accepted, not waived.** `users.tier_overrides` is a wholesale-overwritten
blob with no history (`database.py`), so we still cannot tell a deliberate tier placement from
a Quick Rank artifact — the audit §7 called this "the single most valuable thing to instrument
next". This work adds a *write time* per pin but not a *provenance*. Recorded for the operator;
out of scope here.

## 2. Schema & flag scope

- **New/changed tables or columns:** none. `users.tier_overrides` gains a **sibling key**,
  `__override_at__` → `{fmt: {pid: iso8601}}`. The per-format value shape stays exactly
  `{pid: elo}`. Chosen over the obvious `{pid: {elo, at}}` because that would need a migration,
  break `load_tier_overrides`' float cast, and touch every existing reader of the column
  (`og_image`, `accounts`, the rookie-scope snapshot/restore path). The sibling-key mechanism
  already exists and is already load-bearing (`_parse_extra_keys`, T-M2-01).
  → `docs/data-dictionary.md` updated.
- **New/changed feature flags:** none. Deliberate — a `features.json` flip needs a
  `POST /api/feature-flags/reload`; a `model_config` knob is editable via
  `PUT /api/admin/config/<key>` with no deploy, which is what a kill switch should be.
- **New `model_config` keys:** four, all following the established per-rule kill-switch pattern
  (`max_overpay_frac`, `pos_net_cap`). → `docs/config-reference.md` updated.

  | Knob | Default | Kill value | Effect of the kill value |
  |---|---|---|---|
  | `pin_exclude_comparisons` | 1.0 | **0.0** | `comparison_counts()` returns raw unique-opponent counts again (both consumers) |
  | `pin_unpin_on_newer_swipe` | 1.0 | **0.0** | Pins are permanent again; no swipe releases anything |
  | `pin_legacy_at_epoch` | **0.0** | 0.0 (already the safe value) | Unstamped pins are permanent — no existing board moves |
  | `force_supersedes_running` | 1.0 | **0.0** | A forced request while a job runs silently shares that job again |

  All four at their kill values reproduce pre-2026-08-18 behaviour byte-for-byte.

### Decisions taken inside this scope

| Question | Decision | Why |
|---|---|---|
| Does the F1 exclusion also apply to `_value_uncertainty`? | **Yes** — one map, both consumers. | After the exclusion a pinned player's value *is* the consensus seed, and this codebase already gives any consensus-valued player maximum uncertainty (`n=0 ⇒ unc = range_base`). A narrow range around a value carrying zero personal signal is false precision. Splitting the two would mean threading a second map through 8 call sites in `trade_service.py` + `trade_optimizer.py` + `trade_gen_v2.py` — files a concurrent session was editing — for a population of only "pinned AND compared" players. One knob kills both together, which is also the cleaner incident lever. Pinned by `test_uncertainty_shares_the_excluded_map`. |
| What does a released player start from? | **The pin**, replaying only swipes newer than it. | The pin summarises everything the user said before it; replaying pre-pin history would resurrect the exact swipes the placement superseded. Monotone in time. Pinned by `test_released_player_only_replays_post_pin_swipes`. |
| Can a **trade** like/pass release a pin? | **No** — ranking swipes only. | A tier drag and a ranking comparison are both explicit board edits; a deck like/pass is an indirect, low-K judgement of a whole package. Letting one destroy a deliberate placement is a far bigger product change than the defect warrants. Once released, newer trade swipes *do* apply. Not knobbed (one-line change if the operator wants it). |
| Legacy (timestamp-less) pins? | **Permanent by default**, with `pin_legacy_at_epoch=1` as the operator's opt-in. | See §6 — this is the consequential call and it is deliberately conservative. |
| Superseded job: new status string, or a marker? | **A marker** (`superseded`), status still goes `running → complete`. | A new public status would be an undocumented enum value for clients still polling the old `job_id`. The marker is never serialized (`_trade_job_public_view` picks keys explicitly; pinned by test). |

## 3. Test scope

- **Maestro / simulator: WAIVED — n/a.** Backend-only; no mobile file touched (the client half
  of Fix 3 is owned by a different session and is explicitly out of scope here). Per **D-056**
  Maestro and the simulator are retired entirely, so the evidence delta is structural tests +
  a code-walk, which is what this section provides.
- **Capture delta:** none — no visual change, and `screens/` is frozen at 2026-08-11 (D-056).
- **`testID`s:** none added or renamed.
- **Backend pytest:**

  | File | Covers |
  |---|---|
  | `backend/tests/test_override_pin_unpin.py` (**new**, 41 tests) | Kill-value byte identity vs a **captured** golden; the Adams scenario; monotonicity of value in vote count; inert (both-pinned) comparisons; legacy pins under both policies; unparseable/naive/Z-suffixed stamps; unpin on a newer swipe and *non*-unpin on an older one; trade swipes cannot release; every override mutator stamps; `replay_from_db` carries `created_at`; stamp persistence round-trip, pruning, per-format isolation, coexistence with `__pre_rookie_scope__`, and stamp clearing on snapshot restore. |
  | `backend/tests/test_force_supersedes_running_job.py` (**new**, 8 tests) | (a) forced request while running spawns a new `job_id` and marks the old one superseded; (b) unforced request still shares; kill switch restores the share; the marker never reaches the client payload; **(c) a superseded job writes zero `deck_impressions` rows and no `trades_generated` event**, with a control test proving the same harness *does* write rows normally; a superseded job still reaches `complete`. |
  | `backend/tests/test_rnk_elo_golden.py` (**updated**) | The old "an overridden player's Elo never moves" assertion was the pre-F2 contract. Split into three: pinned against *earlier* swipes, released by a *newer* one, and the old contract restored by the kill switch. |
  | `backend/tests/test_elo_memoization.py` (**updated**) | The spy reconstructed `_elo_cache_key` by hand; the key now folds in the pin knobs (so a kill switch pulled via `PUT /api/admin/config` takes effect on warm sessions immediately instead of waiting for a `_version` bump). Spy parameterised per cache. |

- **Byte-identity is proved by capture, not assertion.**
  `backend/tests/fixtures/override_pin_golden.json` was generated by running the test's exact
  fixture against **pristine `origin/main`** before a line of production code changed, and is
  compared as a whole document. It also carries a guard test asserting the golden still
  *exhibits* the defect (`value > consensus` while `elo` never moved) — if the fixture ever
  drifts, every downstream assertion would otherwise silently measure nothing.
- **Mutation-checked.** Reverting the impression gate makes
  `test_a_superseded_job_writes_no_impressions` fail with 4 orphaned rows; reverting the route
  gate makes `test_forced_request_while_running_spawns_a_new_job` fail. The guards bite.

### Code-walk proof (replaces a simulator capture)

1. `backend/ranking_service.py` `comparison_counts()` — builds the confidence map; pinned
   players are recounted from only the swipes that moved them.
2. → `backend/server.py` `confidence_counts = service.comparison_counts()` → passed as
   `confidence=` into `trade_service.generate_trades`.
3. → `backend/trade_service.py` `_shrink_user_elo(user_elo, seed_elo, confidence)`:
   `w = n/(n+n0)`; with `n = 0` the player lands on `seed_elo` exactly.
4. → `user_value = {pid: elo_to_value(e) …}` — the value the engine prices packages with.
   `elo_to_value(1526.0) = 1138.83`, the consensus value, matching the audit.
5. `_pin_release(pool_ids)` in `_compute_elo` decides who is frozen; the `_moves()` closure
   replaces the old `pid not in override_ids` test at all four update sites.
6. `backend/server.py` — every snapshot publish now goes through `_job_live(j)`, which is
   `running AND NOT superseded`; the two durable side effects re-read the marker under the lock
   via `_job_superseded(job_id)`.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated** | `POST /api/trades/generate` — `force: true` now supersedes a running job; supersede semantics and what a client holding the old `job_id` sees. |
| `living-memory/LLD.md` | **n/a** | No convention shifted. The override storage keeps its documented shape; the sibling-key mechanism it uses is pre-existing and already documented. |
| `docs/architecture.md` | **n/a** | No module wiring or data-flow change. Same call graph, different arithmetic inside two existing functions. |
| `living-memory/HLD.md` | **n/a** | No new module, client or major flow. |
| `docs/cross-client-invariants.md` | **n/a** | No shared constant, enum or colour changed. Elo→value, tier bands and K-factors are untouched. |
| `docs/glossary.md` | **updated** | New terms: *Board override (pin)*, *Pin release (unpin)*, *Live comparison*, *Superseded job*. |
| `docs/data-dictionary.md` | **updated** | `users.tier_overrides` — the `__override_at__` sibling key, legacy-pin semantics, restore behaviour. |
| `docs/config-reference.md` | **updated** | Two new `model_config` sections: *Board-override pins*, *Forced deck regeneration*. |
| ADR / `DECISIONS.md` | **DECISIONS entry** | Two non-obvious calls worth a D- entry: legacy pins default to permanent (§6), and the F1 exclusion applies to `_value_uncertainty` as well as `_shrink_user_elo` (§2). |

## 5. Ship gate declaration

- **Simulator-gate tier: 4 — none, CI only.** Backend-only change, no mobile surface touched.
  Under D-056 the pre-push simulator marker is satisfied with `FTF_SKIP_SIM_GATE=1`; the
  evidence run in its place is the full `pytest backend/tests` suite plus the two new modules
  and the captured golden.
- Evidence: `living-memory/TEST_LEDGER.md` entry naming the suite result and the golden.
- Operator deviation from the matrix: none.

---

## 6. OPEN — backfill proposal, deliberately NOT executed

**The honest headline: Fix 1 removes the inversion, but on today's data it does not unfreeze
a single board.** Fix 2's release mechanism needs a pin write-time, and all 2,735 live pinned
entries predate it. With the shipped defaults, F2 is inert until each user next tiers or
reorders a player.

Measured against prod on 2026-08-18 (`SELECT` only, `default_transaction_read_only=on`):

| | Comparisons | Live (≥1 side can move) | Inert |
|---|---|---|---|
| Today, and with the shipped defaults | 4,013 | **1,292 (32.2%)** | 2,721 (67.8%) |
| With `pin_legacy_at_epoch = 1` **or** a timestamp backfill | 4,013 | **4,013 (100%)** | 0 |

What Fix 1 *does* change immediately is the confidence map: **6,250 of 8,026 player-sides
(77.9%) stop contributing** — precisely the votes that could never move a player's Elo yet
were inflating the shrinkage weight toward the pin.

**Proposal (for the operator, not for an agent):** stamp every existing override with a chosen
instant `T`, so any comparison recorded after `T` releases it.

- **Reversible by construction.** The backfill only *adds* the `__override_at__` sibling key.
  Deleting that key restores today's state exactly; the `{pid: elo}` maps are never touched, so
  no pin value can be lost. The `__pre_rookie_scope__` snapshot remains an independent second
  net.
- **Scope it.** Start with one user + one format (the operator's own `1qb_ppr` board, 737 pins)
  and read the resulting board before widening.
- **Choosing `T` is the whole decision.** `T = now` releases only *future* votes — safe, and
  it makes F2 real going forward without rewriting anything. `T = epoch` (equivalently the
  `pin_legacy_at_epoch=1` knob, no backfill needed) retroactively applies all 4,013 historical
  comparisons, which is what would actually correct Davante Adams today — his 17 down-votes
  would finally land, taking his board Elo below consensus.
- **Why an agent must not choose:** some of those 2,735 pins are deliberate tier placements the
  user arranged by hand, and the audit could not distinguish them from Quick Rank artifacts
  (§7 of the audit — `tier_overrides` has no history). Releasing them is a large, visible,
  one-shot change to user data.

**Recommendation, stated but not acted on:** try `pin_legacy_at_epoch = 1` first. It needs no
data write at all, is a single `PUT /api/admin/config` to set *and* to undo, and answers the
empirical question ("do the released boards look better?") before anything durable happens. If
the answer is yes, the backfill just makes it per-player and permanent.

### Also deferred

- **Audit F3–F6** (surface the pin in the ranking UI; value-preserving `apply_tiers` spread;
  divergence sanity gate; the dark `trade.outlook_blend` age curve) — all out of Phase 0 scope.
  F3 in particular is the durable fix for *recurrence*: the operator voted a player down 17
  times against a control that could not move, and nothing on screen said so.
- **Pin provenance.** Recording *why* a pin exists (hand placement vs Quick Rank bulk save)
  would make the backfill decision above trivial. Needs a schema addition; not attempted.

## 7. Bright-line note (CLAUDE.md § Feature gates)

Fix 3 changes the behaviour of an **API contract** (`POST /api/trades/generate` — `force: true`
now yields a different `job_id` while a job is in flight, and the response is a fresh job rather
than the running one). Per CLAUDE.md this is explicitly *not* a "quick fix" and needs a
confirming operator yes.

**Recorded as given:** the coordinating session relayed that the operator explicitly approved
folding Fix 3 into this branch in-session on 2026-08-18. This scope block is the audit trail
for that approval — it is recorded as an operator decision, attributed to the relay, so the
operator can catch it here if the attribution is wrong. Full gates were applied to it anyway
(this scope block, tests, docs, knob); no express lane was taken for any part of this work.
