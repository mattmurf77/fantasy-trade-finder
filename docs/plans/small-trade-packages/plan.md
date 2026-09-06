# Small-player-package presentation — planner proposal

**Status:** proposed for separate author/reviewer, 2026-09-06; no runtime implementation or tests run. Baseline inspected: `4026ebc81eaae50b345b42421641125c5b8d413e`. Parent owns integration, index and decisions; this planner owns only this file. The author must create the mandatory completed `scope.md` before runtime work; the scope dispositions below are inputs, not a waiver of that gate.

## Outcome and evidence boundary

Make early automatically generated ideas easier to read by giving simpler **player** packages a small local ordering preference. Keep every already-selected eligible package, including larger packages, available. Change neither generator supply nor valuation/eligibility thresholds.

[Owner-scoped research](../../research/2026-09-06-trade-package-shapes.md): September 5 had 15 recorded viewed cards, nine with at least three players on a side and three with at least three on both sides. The monthly cohort was much less concentrated (30/164 and 6/164). Completed current-league trades averaged fewer players but frequently more total assets because picks are common. The owner completed a 3x4-player trade. Only six completed, positive-sided, player-only trades exist in the 2026 cohort; 4-versus-11 views before/after the policy transition cannot establish causation. These facts support a modest readability preference, not a hard cap, arm winner, acceptance-rate claim or new confidence/fairness threshold.

## Verified ordering and attribution seams

| Existing seam | What it means for this proposal |
|---|---|
| `bakeoff_runner.py:1452–1620`, `compose_deck`, `run_bakeoff` | Arms generate unchanged full lists, then group/arm drafting chooses the served set and credits the first picker. Do not move this preference into generation or pre-draft ordering: that changes selection, agreement credit and potentially arm allocation. |
| `bakeoff_runner.py:397`, `bypass_rerankers` | Fixed interleaving currently forbids post-generation reranking. A local same-slot-class permutation is an **explicit narrow exception requiring review**, not a claim that the existing contract already allows it. |
| `server.py:5451`, `_evaluate_deck_policy`; `trade_policy.py:1035`, `compose_deck` | Live policy filters, sorts by personal/mutual opportunity, then applies Core/Conviction/Fallback composition. Reordering before this would either be erased or change the chosen set. Operate only on its final survivors. |
| `server.py:7070–7085`, `7727–7742` | Live market/mutual policy withholds provisional cards through `final_checks_pending`, then publishes evaluated cards. Insert the preference **before that first evaluated publication**, not merely before the later impression write. |
| `bakeoff_runner.py:983`, `attribution_for`; `:1008`, `group_for` | Attribution is keyed by card object identity. Original `arm_rank` and `group_rank` can travel with the same object; they must not be rewritten to look like the new served order. |
| `server.py:4853–4919` | Impression `card_index` is final served position; `model_arm`, `arm_rank`, group metadata and `policy_variant` describe distinct concepts. Final serialization must use the same ordered list as the earliest evaluated publication. |
| `server.py:6523–6600`, `7549–7583` | F9's simple-shape partition is first-deck-only and bypassed for fixed bakeoff order. Extending it wholesale would also import its truncation/confidence rules; do not reuse that policy here. |

The slot vector to preserve is the **existing final post-policy deck**, not an invented restoration of the original interleaver order. Live policy already may change the latter. Preserving the final vector adds no new arm/lane allocation change, while acknowledging the within-arm exposure-order change.

## Proposed exact rule: disjoint six-position windows

This numeric bound is a conservative implementation proposal for review, **not an empirically fitted optimum**.

1. Capture one presentation mode at job kickoff. V1 applies only when the normal generated job has live market/mutual policy evaluation, the presentation knob is on, and there is no explicit send pin, receive pin or opponent selection. Demo, dark/shadow-only policy, and active ghost withholding return the original order. The normal zero-ghost setting is not changed.
2. Take the immutable post-policy survivor list and partition its absolute indices into non-overlapping windows `[0..5]`, `[6..11]`, etc.; a short final window is allowed. Never carry a card between windows.
3. Lock the **exact existing positions** of `likes_you`, `standing_offer_reason`, `wildcard`, `fatigue_retest`/legacy `retest`, or other existing explicitly fixed-slot cards. In a bakeoff run, missing source attribution is also locked, not assigned to a fake arm. Unknown/malformed asset classification and pure-pick-only packages are locked rather than rewarded for a guessed zero player count. Do not edit their source/interest state.
4. For each remaining card, define a slot class `(credited arm, group_key, lane_slot, card.lane, card.basis, policy_result.lane)`. Missing group metadata in the legitimate group-size-zero path remains `None`; it is not an error. A genuinely non-bakeoff job uses one internal source class, without stamping a fabricated `model_arm`. Require an actual per-card policy result. Keep these classes at every existing index.
5. Within each window **and identical slot class**, stably sort only its cards by `(max(give_player_count, receive_player_count), give_player_count + receive_player_count)`. Put them back into that class's original slots. Count actual player IDs/positions using the existing generic-pick parser and owned-pick schema; picks add no player-complexity units. Equal player complexity preserves input order even when pick counts differ. Mixed player/pick packages remain eligible for this rule; pure-pick-only cards stay locked.
6. Return the same card objects and multiset, with no add/drop, asset mutation, rescore, threshold or source-credit change. A card moves at most five **absolute** positions. No repeated sliding-window/bubble pass: repeated application to the same input must be idempotent.

The six-position window permits one same-arm exchange across a normal three-arm cycle without bringing a distant low-ranked card to the top. A stricter adjacent-only swap usually does nothing in alternating-arm decks; a global complexity sort changes arm positions, policy-lane lead regions and too much rank order. This windowed approach can therefore work with current object-keyed attribution, but its actual effect may be small when lane/group classes are sparse. If the offline test corpus shows no useful movement, report that and revisit the rule; do not silently widen the window or remove slot constraints.

Illustrative executable fixture: six Core/Value cards in source order A,B,C,A,B,C have player shapes `3x3, 1x4, 2x3, 1x1, 1x2, 1x1`. With otherwise identical per-arm slot classes, output is `1x1, 1x2, 1x1, 3x3, 1x4, 2x3`; arm sequence stays A,B,C,A,B,C. First-three total players falls from 16 to 7 and each moved card travels exactly three places. The original high-complexity cards remain in positions four through six.

## Generation, cache, replenishment and client boundary

One pure helper, called once in `_run_trade_job` after successful final policy composition and before the evaluated snapshot publication, covers normal `/api/trades/generate`, forced regeneration/Find More, session-init pregeneration (`server.py:21061`) and headless/synchronous replenishment (`:21888`) through `_kickoff_trade_job`. Do not separately rerank `/status` or cached serialized dictionaries; that would reapply the rule on a changing filtered list and falsify frozen impressions. Later #419 exact-disposition filtering may remove cards but must not be turned into a complexity reranker.

The helper must be harmless when the final deck is empty, short, all large, entirely locked, or policy context is unavailable. Preserve existing safety failures and all market/roster/intent checks. Attribute-only breaker annotation and the final signal writer consume the helper's returned list unchanged. Test signal logging disabled as well as enabled so the earliest publication cannot leak pre-preference order.

Explicit exclusions: pinned give/receive, named opponent, calculator edits/evaluate/queue/propose, synchronous `/fair-packages` and `/asset-ideas`, Win Now search/results, matches/Awaiting, manually assembled/shared offers, and mobile browse-session sibling order. No new client re-sort and no reordering of already retained screens. Empty-canvas requests using the ordinary organic generator are in scope; a supplied explicit selection is not.

## Rollback, cache identity and honest telemetry

Propose one Float-valued enable knob, **`simple_player_presentment`**, default **0**, with only `0=off` and `1=v1` interpreted; missing/invalid values fail to the original order. Window size is versioned code, not a second tunable policy surface. Release activation to 1 is a separately recorded parent action after evidence; setting 0 is the narrow rollback without disabling live market/roster policy or any generator arm.

Capture the effective mode/version once at `_kickoff_trade_job` and pass it through the job rather than rereading midway. Add it to completed-cache freshness and running-job reuse checks. A new request must not reuse a job captured under a different mode. Apply the same compatibility check to the separate session-init and replenishment cache probes, which currently rely mostly on TTL. Do not mutate old impression records or silently reorder an old job ID on polling. An existing display/explicit old-ID poll retains its captured order; rollout/rollback takes effect for fresh compatible generation, not by remotely rewriting an already viewed deck.

Existing events cover view/action chronology (`trades_generated`, `deck_card_viewed`, outcomes); no new event is proposed. Add a small frozen **existing-column** `features_json.presentation` record for in-scope enabled jobs: version, window size, original post-policy index and final index, plus give/receive player counts. Append the captured presentation version to the existing serving `policy_version` while preserving `/bo:<arm>` attribution and the separate valuation `policy_variant`. Do not recast the deterministic reorder as a new Thompson propensity: retain the actual recorded draw and mark the serving-policy change. Off/exempt jobs retain existing payload and feature behavior. Validate the writer's existing every-row/batch requirements.

This changes which same-arm card gets an earlier exposure, so before/after model-quality comparisons require the presentation-version slice even though per-position arm allocation remains invariant. No claim of experiment-neutral outcomes is made.

## Evidence required from the author/builder

All listed checks are **planned, not run**. New focused home: `backend/tests/test_small_trade_presentment.py`; extend actual worker/cache/impression and bakeoff harnesses without rewriting source goldens.

- Baseline RED: a real final-policy/worker harness serves the six-card fixture in the original order; enabling the helper must produce the exact expected order and reduce the measured first-three player load from 16 to 7. Sabotage removal of the helper restores RED with fixtures unchanged.
- Invariants/property fixtures: identical card multiset/objects/assets/values/eligibility; maximum absolute movement five; identical class vector at every index; stable equal-complexity order; idempotency; no cross-window movement. Assert Core/Conviction/Fallback lead/share constraints and all three source-arm counts and positions unchanged.
- Locked/excluded controls: source-interest, standing-offer, wildcard, actual fatigue-retest attributes, missing attribution, unknown assets, pure picks; every explicit-selection/manual route above. Same player complexity plus different pick counts never creates an ordering penalty. A mixed pick-heavy simpler-player card is not classified as player-heavy merely for its picks.
- Real worker outputs: normal/forced generation, both format contexts, pregen and replenishment; first evaluated publication, final result, cached response and old-ID status agree for that captured job, with signal logging on/off. #419 current-pass suppression survives; no resurrection to fill slots.
- Rollback/cache: mode 0 is baseline identity; 0→1 and 1→0 do not reuse incompatible completed/running/pregen/replenish caches. Original job remains internally consistent if the knob changes while held before publication.
- Telemetry: serialized card order equals legacy impression position and F1 `card_index`; original arm/group ranks, source-like attribution, policy valuation and actual propensity remain unchanged. Capture/version is job-consistent; special cards retain their positions. No new phantom candidate or action rows.
- Measure on synthetic fixed-output decks and any safely available recorded **served** snapshots: first-three/first-six player load, moved-card count, displacement, arm/lane invariance and unchanged availability, including no-op cases. Do not generate real-user trades to manufacture evidence. No success criterion based on the fifteen-card sample becoming an acceptance-rate target.
- Run relevant full backend/bakeoff/standing-offer suites and historical arm goldens; parent runs full backend, mobile typecheck and test-ID lint. D-056: no Maestro/simulator. Physical TestFlight checklist: organic generation shows the checked early order; large packages remain reachable; explicit selection stays intact; lane switching/Find More do not re-front committed passes; restored results retain their captured order.

## Scope and ownership for the author

No runtime file is edited by this planner. Suggested backend ownership is one helper (leaf module only if warranted), `server.py` narrow job/order/cache/writer seams, `trade_service.py` and `database.py` **new neutral knob defaults only**, and focused tests. Generator, ranking, market and roster math remain out of scope. Parent sequences `server.py` changes after #419 to avoid overlapping edits.

The author must complete `scope.md`: existing events plus explicitly named frozen presentation fields; no new table/column/flag/env; one default-off rollback knob; the behavioral/worker tests above and code-walk; no mobile runtime change, so no new mobile structural suite/test IDs are justified. Update API ordering/cache semantics (not wire shape), config reference, data dictionary for nested snapshot semantics, LLD/architecture and a decision explicitly narrowing the fixed-order contract. HLD/glossary are n/a because no new subsystem or user term. Parent owns plan index, decision ID, shared ledger and release evidence. No waiver, completed test, deployment or physical-device verification is implied by this plan.
