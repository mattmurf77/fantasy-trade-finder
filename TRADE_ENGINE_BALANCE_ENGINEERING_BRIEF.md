# Trade Engine: Personal Rankings With Market-Fairness Guardrails

**Status:** Proposed engineering change\
**Date:** 2026-09-04\
**Product surface:** Fleeced mobile app, primarily the Acquire trade deck\
**Scope:** Trade generation, scoring, deck composition, telemetry, and experiment rollout. The website is out of scope.

## Executive summary

Fleeced's primary differentiator is its ability to use each manager's personal rankings to find trades that ordinary consensus calculators cannot see. However, users still expect a proposed trade to be recognizable as plausible in the broader dynasty market.

The current implementation mixes these two concerns into one score:

```text
70% personal-ranking mismatch / mutual surplus
30% consensus fairness
```

For trades generated from two personal boards, the effective consensus-fairness floor can be as low as `0.55`. Later fit, tier, taste, diversity, and presentation layers can further change the ordering. Production data suggests that the underlying personal-ranking signal contains useful information, but the final composite score does not preserve it reliably.

The proposed design separates the responsibilities:

1. **Consensus answers whether a trade is market-plausible.** It is a hard eligibility guardrail, not the main ranking objective.
2. **Personal rankings answer which market-plausible trades are unusually attractive to these two managers.** Two-sided personal surplus becomes the primary ordering signal.
3. **Ranking confidence controls how far the engine may depart from consensus.** Weak or missing ranking evidence requires a tighter market band; strong evidence from both managers permits a controlled "conviction" trade.
4. **The main deck remains trustworthy.** Most cards are close to consensus fairness. A small, clearly labeled conviction lane contains the distinctive trades enabled by personal rankings.
5. **The new policy is tested as a separate experiment dimension; it does not replace a generator arm.** Keep `current`, `challenger`, and `gen_v2` generating. Compare decks using the existing policy with decks using the new personal/market policy while preserving the same underlying arm mix. Report the policy's result overall and separately for each generator.

The key product statement is:

> Fleeced does not need to ignore market value to be differentiated. Among trades the market considers plausible, it should identify the trades these two managers are uniquely positioned to prefer.

## Why this change is needed

### Current behavior

The live/current engine has the following relevant behavior:

- `mismatch_weight = 0.70`
- `fairness_weight = 0.30`
- `fairness_floor_divergence = 0.55`
- Personal Elo is shrunk toward consensus using `w = n / (n + 4)`, where `n` is the requesting user's comparison count for that player.
- That confidence shrinkage is asymmetric: the requesting user's board is shrunk, while a league-mate's published board does not carry equivalent confidence data and is generally used raw.
- The divergence path applies `min(requested_fairness_threshold, fairness_floor_divergence)`. This means a user's stricter `0.75` preference can become a looser `0.55` gate.
- Range-overlap logic can admit a card whose point-estimate consensus ratio is below the nominal threshold. Low confidence should make the engine more conservative, not make a market-imbalanced trade easier to admit.
- Targeted retries, relaxed generation, sweeteners, wildcards, and deck reordering add additional paths where policy intent can be diluted.

Relevant implementation areas on `origin/main` are:

- `backend/trade_service.py`: defaults, confidence shrinkage, divergence and consensus generation, targeted relaxation, and card scoring
- `backend/trade_optimizer.py`: v3 package search, fairness checks, and composite scoring
- `backend/server.py`: trade-job orchestration, deck ordering, impression logging, and API payloads
- `backend/bakeoff_profiles.py`: current experimental arms; do not modify the pinned historical `MODEL_A_PROFILE`
- `backend/database.py`: rankings, impressions, outcomes, pass reasons, matches, and model configuration
- `mobile/src/api/tradePregen.ts`: client fairness preference sent to generation
- Provider-send components and routes: proposal outcome attribution

**Repository warning:** the shared working checkout was at an August 15 commit during this analysis, while `origin/main` and the Render production schema were at September 3. Engineering must branch from a freshly fetched `origin/main`, per repository policy, rather than implementing against the stale checkout.

## Evidence from the production database

Production data was queried from Render Postgres on 2026-09-04 using a server-enforced read-only session. Credentials and raw identifiers were not exported.

### Available sample

| Data | Count |
|---|---:|
| Served deck impressions | 21,363 |
| Unique impression-linked like/pass decisions | 598 |
| Likes | 188 |
| Passes | 410 |
| Active legacy trade decisions | 1,407 |
| Explicit bad-trade flags | 18 |
| Users contributing rich impression-linked decisions | 5 |

This is enough to identify directional problems and design the next experiment. It is not enough to declare a permanent winning policy.

### Findings relevant to this change

1. **Personal-ranking surplus contains a useful signal.** Among the 231 decided divergence cards, the highest quartile of stored mutual-surplus score was liked `38.6%` of the time. The other quartiles were liked between `15.5%` and `25.9%`.

2. **The final composite does not preserve that signal.** Across those divergence cards, personal surplus had a weak positive relationship with likes, but the final base composite score had approximately zero correlation with likes. This points to scoring and downstream ordering, rather than the basic product thesis, as a likely problem.

3. **Consensus value alone does not explain rejection.** The most common structured decline is `value_giving` (the user does not want to give up that side). Divergence cards declined for this reason gave the viewer approximately `11%` more stored consensus package value on average. The market said the viewer was winning, but the selected outgoing player/package still made the offer undesirable.

4. **The extreme low-fairness tail performs poorly.** Retrospectively applying stricter minimum fairness floors to divergence decisions produced the following result:

| Proposed minimum | Decisions removed | Passes removed | Likes removed | Removed cards that were passes |
|---:|---:|---:|---:|---:|
| 0.60 | 22 | 18 | 4 | 81.8% |
| 0.65 | 30 | 25 | 5 | 83.3% |
| 0.70 | 40 | 30 | 10 | 75.0% |
| 0.75 | 52 | 40 | 12 | 76.9% |

`0.65` is therefore a reasonable experimental absolute floor: it removes five times as many passes as likes in the available sample. It is not evidence that every card at `0.65` is user-ready or that `0.65` is a permanent product default.

5. **There is no statistically proven winning model arm.** In the clean three-arm window beginning August 21, the like rates were approximately `48%` for current (`n=33`), `45%` for challenger (`n=74`), and `40%` for gen_v2 (`n=47`). The 95% Wilson intervals are wide and overlapping: current `32.5-64.8%`, challenger `33.8-55.9%`, and gen_v2 `27.6-54.7%`. Pairwise Fisher tests are nowhere near significance (`p=0.50` current versus gen_v2; `p=0.71` challenger versus gen_v2; `p=0.83` current versus challenger). Only five users decided cards, and user/time concentration is high. These results do not justify deleting, pausing, or declaring victory for any arm.

6. **`gen_v2` still carries useful information despite its lower point estimate.** It has been supply-constrained, but among its decided cards its personal-surplus and own-rank signals were more aligned with likes than the equivalent signals in current or challenger. That may make it a useful contributor lane even if it never becomes the sole deck generator. Removing it now would discard a genuinely different hypothesis before the sample can adjudicate it.

7. **Like rate is an incomplete target.** Users may like a one-sided offer precisely because it favors them. Proposal, mutual-match, and eventual acceptance rates are better measures of whether the balance is correct, but historical impression-linked proposal data is effectively absent.

## Target decision model

For a viewer giving package `G` and receiving package `R`, calculate all values once and retain them through generation, ranking, serving, and telemetry.

### Consensus plausibility

Use the same consensus package-pricing function as the manual calculator:

```text
market_ratio = min(consensus(G), consensus(R))
               / max(consensus(G), consensus(R))
```

This must include the existing package discounts, crown/stud adjustments, positional treatment, pick pricing, and roster-slot cost. Do not implement a second simplified sum for the policy gate.

### Two-sided personal opportunity

From the viewer's perspective:

```text
viewer_surplus = viewer_value(R) - viewer_value(G)
partner_surplus = partner_value(G) - partner_value(R)

viewer_gain_pct = viewer_surplus / max(viewer_value(G), epsilon)
partner_gain_pct = partner_surplus / max(partner_value(R), epsilon)

personal_opportunity = min(viewer_gain_pct, partner_gain_pct)
```

The primary score intentionally uses the weaker manager's gain. A trade that is excellent for one side and barely positive for the other should rank below a trade that is meaningfully positive for both.

The existing harmonic mutual-surplus score may remain as a secondary signal, provided it is normalized and directionally monotonic with two-sided benefit.

### Confidence-shrunk values

Apply the same confidence rule to both managers:

```text
effective_elo = confidence_weight * personal_elo
              + (1 - confidence_weight) * consensus_elo
```

For comparison-based rankings, retain the existing shape:

```text
confidence_weight = n / (n + shrink_pseudocount)
```

Initial confidence-source treatment should be configurable rather than hard-coded. Suggested starting values are:

| Ranking evidence | Initial confidence treatment |
|---|---:|
| Unchanged consensus seed | 0.00 |
| Pairwise/trio votes | `n / (n + 4)` |
| Cross-format copied ranking | 0.75 |
| Explicit tier, manual order, import, or anchor placement | 1.00 |

The exact source weights are experiment settings, not permanent truths. The important requirements are symmetry, explicit provenance, and fail-safe handling of missing data.

Package confidence should be a consensus-value-weighted mean across involved assets, so a low-value filler does not dominate the decision:

```text
package_confidence(board) =
    sum(consensus_value(asset) * confidence_weight(asset))
    / sum(consensus_value(asset))

trade_confidence = min(viewer_package_confidence, partner_package_confidence)
```

If the opponent has no real personal board, the trade is not a two-board divergence trade. Treat it as a one-board/consensus fallback and label it honestly.

## Market-fairness policy

### Initial experimental floors

Do not replace `0.55` with one global threshold. Introduce a policy floor based on the evidence available:

| Situation | Initial policy floor |
|---|---:|
| No opponent personal board | 0.85 |
| Two boards, weak or incomplete confidence | approximately 0.80 |
| Two well-supported boards | approximately 0.70-0.75 |
| Strong, high-confidence gain for both managers | may fall toward 0.65 |
| Absolute minimum for any finder card | 0.65 |

One configurable continuous implementation is:

```text
if opponent_has_no_real_board:
    policy_floor = one_board_floor                       # initially 0.85
else:
    policy_floor = clamp(
        two_board_base_floor                             # initially 0.80
        - confidence_discount * trade_confidence         # initially up to 0.10
        - surplus_discount * normalized_personal_strength, # initially up to 0.05
        absolute_floor,                                  # initially 0.65
        two_board_base_floor
    )
```

All constants must live in remotely configurable `model_config` rows. Suggested names:

- `market_floor_absolute`
- `market_floor_one_board`
- `market_floor_two_board_base`
- `market_floor_confidence_discount`
- `market_floor_surplus_discount`
- `personal_gain_min_frac`
- `conviction_deck_share`

### User fairness preference

The app's fairness preference may tighten the system policy, but it must never loosen it:

```text
effective_floor = max(policy_floor, user_requested_floor)
```

This corrects the current divergence behavior, which uses `min(...)` and can turn a stricter user request into a looser gate.

If the existing on/off control remains:

- **Fairness on:** request a core-market floor, initially `0.80`.
- **Fairness off / explore:** permit qualified conviction cards down to their dynamic floor, never directly to `0.50`.
- The UI should avoid promising that fairness is literally disabled. A label such as "Explore ranking edges" more accurately describes the behavior.

### Non-bypassable rule

The point-estimate `market_ratio` must clear `effective_floor`. Confidence intervals or uncertainty ranges may be displayed or used as a secondary ranking signal, but they must not rescue a point ratio below the hard floor.

The same evaluator must run after every mutation or alternate generation path:

- Normal v2/v3 generation
- Consensus fallback
- Targeted-player and position searches
- Relaxed fallback generation
- Sweetener insertion
- Swap/remove/edit operations that return a card to the deck
- Likes-you injection
- Wildcard/exploration insertion
- Weekly replenishment

No path may silently return to the old `0.55` behavior. If a targeted request cannot create a valid card, return an honest empty result or explain that the target cannot currently be packaged within the user's market settings.

## Candidate ranking

After eligibility is established:

1. Rank divergence cards primarily by `personal_opportunity`.
2. Use harmonic mutual surplus, lineup/need fit, explicit target preferences, and meaningful-player/tier importance as secondary signals.
3. Use consensus closeness only as a small tie-breaker inside the same deck lane; do not restore the current 70/30 blended objective under a new name.
4. Apply fatigue and diversity only after policy eligibility, and ensure they cannot make an ineligible card visible.
5. Add monotonicity tests: holding everything else constant, increasing the weaker side's personal gain must never lower the card's pre-presentation rank.

Consensus fallback cards cannot have two-sided personal opportunity because the partner board is absent. Rank those cards using market fairness, the viewer's personal gain, and roster fit, but do not describe them as proven mutual wins.

## Deck composition and presentation

Partition eligible cards into:

- **Core:** `market_ratio >= 0.80`
- **Conviction:** below `0.80` but at or above the dynamic floor, with two real, sufficiently confident boards and positive personal surplus for both managers
- **Consensus fallback:** the opponent has no usable personal board
- **Exploration:** an ordering treatment applied only to cards that already qualify for one of the safe groups above

For a normal ten-card deck, when sufficient candidates exist:

- The first three cards are Core cards.
- At least 70% of the deck is Core.
- At most two cards are Conviction cards.
- Conviction cards appear after the initial trust-building cards, approximately positions 4-6.
- At least 70% of the deck should be generated from two personal boards when valid divergence inventory exists.
- Consensus fallback fills missing inventory; it does not displace valid, high-quality divergence cards.
- Existing partner, centerpiece, position, and package-shape diversity remains in force.
- If safe supply is insufficient, return a smaller deck rather than weakening the guardrail.

The API should expose enough information for the mobile card to explain the trade without revealing another manager's exact private ranking:

- `market_fairness`
- `value_basis`: `two_board`, `one_board`, or `consensus`
- `confidence_band`: `high`, `medium`, or `low`
- `opportunity_label`: `core` or `conviction`
- A privacy-safe explanation such as "Both boards see a gain" or "You rank the return higher than the market"

For a Conviction card, explicitly show that the trade involves a market premium. Do not expose the opponent's precise values or individual ranking positions.

## Production database primer

Production runs on Render Postgres. Local `data/trade_finder.db` is a development database and must not be used to measure real behavior.

Credentials are stored in the gitignored root `secrets.local.env` as `DATABASE_URL_PROD`. Never print the URL, pass it literally on a command line, commit query output containing user data, or copy free-text feedback into a report. Production queries must be read-only:

```sql
BEGIN;
SET TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '30s';
-- SELECT statements only
ROLLBACK;
```

The repository's `backend/tools/prod_analytics.py` helper also opens a read-only, time-limited connection.

### Relevant tables

| Table | Purpose and cautions |
|---|---|
| `deck_impressions` | One row per card in final served order. `impression_id` is the primary attribution key. Newer rows contain asset IDs, consensus values, scores, model arm, policy version, and effective fairness threshold. A served card was not necessarily viewed. |
| `deck_outcomes` | Append-only `viewed`, `like`, `pass`, `not_interested`, `propose`, and `undo` actions joined by `impression_id`. Duplicate/late rows are legal; reporting must reduce them to an effective outcome and count distinct impressions. |
| `trade_decisions` | Older like/pass audit log with package asset IDs. It lacks a reliable impression key, model arm, and full score context. Use only as historical directional evidence. |
| `trade_pass_reasons` | Structured decline reason and detail, such as `value_giving`, `value_getting`, `fit_outlook`, or `other_player_keep`. Some older/local rows have no impression attribution. |
| `bad_trade_flags` | Explicit "the engine got this wrong" feedback. Treat it as a stronger negative signal than an ordinary pass. |
| `trade_matches` | Mirrored likes from two league-mates. This is a stronger downstream success measure than a one-sided like. |
| `member_rankings` | Latest published personal Elo per user, league, player, and scoring format. It is a replace-in-place snapshot, not historical state, and currently lacks adequate opponent confidence. |
| `player_value_history` | Daily consensus snapshots by player and scoring format. |
| `deck_candidate_sets` | Candidates available after generation/gating. It cannot reconstruct candidates killed before it was written. |

When analyzing outcomes:

- Exclude `league_demo` and ghost impressions.
- Require `viewed` when calculating view-based conversion.
- Resolve the most recent `like`, `pass`, or `undo` per impression.
- Count distinct impressions, not raw outcome rows; duplicate pass events have existed.
- Analyze `not_interested` and bad-trade flags separately from normal passes.
- Hash user and league IDs in analyst output.
- Cluster statistical uncertainty by user and deck job; cards from one user/deck are not independent observations.

## Required confidence persistence

The requesting user's live `RankingService` has comparison counts, but a league-mate's published `member_rankings` rows do not carry equivalent evidence. Add nullable fields to the published ranking snapshot:

- `comparison_count INTEGER`
- `confidence_weight FLOAT`
- `confidence_source VARCHAR`

Populate them in every ranking save/import path. Legacy rows with null confidence must be treated as low confidence, not as fully trusted.

Extend the generation input/`LeagueMember` representation to carry the opponent's confidence map. Both personal boards must then pass through the same effective-value function.

This schema change is additive. Do not backfill fabricated confidence for historical rows. Update `docs/data-dictionary.md` as required by repository policy.

## Required impression telemetry

The existing impression data preserves consensus package values and high-level scores, but it does not freeze the actual values used from each manager's perspective. Current `member_rankings` cannot reconstruct those values later because it stores only the latest board.

Add one nullable, SQLite-compatible column to `deck_impressions`:

```python
Column("valuation_json", Text)
```

`valuation_json` is an audit/replay snapshot, not a replacement for existing scalar columns. It must be created from values already computed during generation and frozen before serving:

```json
{
  "schema_version": 1,
  "scoring_format": "sf_tep",
  "basis": "divergence",
  "market": {
    "viewer_gives": 4200.0,
    "viewer_receives": 3900.0,
    "ratio": 0.929
  },
  "viewer_board": {
    "source": "personal",
    "gives_raw": 3500.0,
    "receives_raw": 4700.0,
    "gives_effective": 3700.0,
    "receives_effective": 4450.0,
    "effective_surplus": 750.0,
    "gain_pct": 0.203,
    "package_confidence": 0.78
  },
  "partner_board": {
    "source": "personal",
    "gives_raw": 3600.0,
    "receives_raw": 4800.0,
    "gives_effective": 3800.0,
    "receives_effective": 4600.0,
    "effective_surplus": 800.0,
    "gain_pct": 0.211,
    "package_confidence": 0.72
  },
  "mutual": {
    "personal_opportunity": 0.203,
    "harmonic_effective_surplus": 774.2
  },
  "policy": {
    "policy_version": "personal-market-v1",
    "requested_floor": 0.50,
    "policy_floor": 0.682,
    "effective_floor": 0.682,
    "eligibility_lane": "conviction",
    "relaxed": false,
    "value_model_version": "package-v2"
  },
  "assets": {
    "give": [
      {
        "id": "1234",
        "market_value": 4100.0,
        "viewer_raw_value": 3500.0,
        "viewer_effective_value": 3300.0,
        "viewer_confidence": 0.667,
        "partner_raw_value": 4700.0,
        "partner_effective_value": 4600.0,
        "partner_confidence": 0.80
      }
    ],
    "receive": []
  }
}
```

Direction semantics must remain viewer-centered:

- `viewer_gives` is the card's give side.
- `viewer_receives` is the card's receive side.
- The partner gives the card's receive side and receives the card's give side.
- Package totals are the final values used by the gate after package and roster adjustments, not simple asset sums.
- `raw` is the personal board before confidence shrinkage.
- `effective` is the value after confidence shrinkage and placement clamps.
- If the opponent has no real board, use `source: "consensus"` and leave opponent personal/confidence fields null. Do not manufacture a personal board by copying consensus.

Write the snapshot for served, shadow, and ghost impressions. Keep the write best-effort so telemetry can never fail trade generation, but expose a health counter for serialization/write failures.

Do not backfill `valuation_json`; the historical board state no longer exists and any backfill would be misleading.

## Proposal and outcome attribution

There are two distinct moments that must be measured:

1. **Suggestion time:** what values and policy caused the engine to serve the original card. This is the `deck_impressions.valuation_json` snapshot described above.
2. **Proposal time:** the exact package and values when the user successfully sends an offer. This may differ because the user swapped an asset, removed a piece, added a sweetener, or edited the trade in the calculator.

Do not treat the suggestion-time snapshot as the proposal-time truth when the package changed.

Every card-originated action must carry `impression_id` through:

- Acquire
- Matches and Awaiting Them
- Edit-in-calculator when launched from a card
- Sleeper, MFL, and ESPN send flows

Verify the recently added proposal-attribution path end to end. Append `deck_outcomes.action = "propose"` only after the provider confirms a successful proposal. An attempted or failed send is not a successful proposal.

Add a durable proposal record for the final sent package. A suggested SQLite/Postgres-compatible table is:

```text
trade_proposals
  id                       integer primary key
  proposal_event_id        string unique, generated before the provider call
  impression_id            string nullable
  match_id                 integer nullable
  user_id                  string
  league_id                string
  target_user_id           string nullable
  provider                 string                 # sleeper | espn | mfl
  provider_transaction_id  string nullable
  source                   string                 # deck | match | calculator
  give_asset_ids           text                   # JSON array, final package
  receive_asset_ids        text                   # JSON array, final package
  origin_trade_hash        string nullable
  final_trade_hash         string
  edited_from_source       integer                # 0 | 1
  valuation_json           text                   # frozen at confirmed send
  proposed_at              string                 # server UTC
```

`trade_proposals.valuation_json` should use the same schema and direction conventions as the impression snapshot, with these additional fields:

- `snapshot_stage: "proposal"`
- Consensus snapshot date/version used at send time
- Personal-board update timestamps used at send time
- Final viewer and partner raw/effective package values
- Final consensus package values and market ratio
- Final personal surpluses, gain percentages, and confidence weights
- The policy variant, model arm, and originating impression when available
- Whether the final package would qualify as Core, Conviction, Fallback, or ineligible under the finder policy

Recalculate this snapshot from the **final package** immediately before or after confirmed provider success; do not copy the original impression JSON. If the provider succeeds but the database write is retried, `proposal_event_id` and, where available, `provider_transaction_id` must make the write idempotent.

The proposal-time evaluation is initially telemetry, not a new restriction on manual behavior. A user may deliberately edit or construct a trade that the finder itself would not generate. Record `policy_eligible: false` and the reason; do not block a manually initiated send unless a separate product decision explicitly adds that behavior.

The live historical dataset contained no `propose` rows at the time of analysis. Treat a successful controlled TestFlight proposal that fails to produce an owned, non-stale impression-linked row as a release blocker.

Also verify whether the previously observed duplicate pass emission still reproduces. Prefer a client-generated event ID/idempotency key rather than imposing a uniqueness rule that would prevent a legitimate undo and later decision.

## Two-user timing and mirrored-card attribution

A mutual trade is not one simultaneous observation. It is a sequence:

```text
Manager A is served the concept
  -> A views it
  -> A likes it
  -> the mirrored concept becomes eligible for Manager B
  -> B may be served it minutes or days later
  -> B views, passes, likes, or never acts
  -> if B likes, a mutual match is created
```

Consensus values, rosters, personal rankings, and even experiment policy can change between those steps. The system must preserve each observation at its own timestamp rather than evaluating both users against whichever values happen to exist when an analyst later runs a query.

### Canonical trade-concept identity

The existing `trade_hash` is viewer-relative and is not sufficient to join mirrored cards. Add a nullable `trade_concept_id` to `deck_impressions` and new trade decisions. It must be identical for both perspectives of the same exact package.

Build it from a versioned canonical representation:

```text
low_user_id, high_user_id = sorted(viewer_user_id, partner_user_id)

low_user_gives = viewer give side if viewer is low_user_id,
                 otherwise viewer receive side
high_user_gives = the opposite asset side

trade_concept_id = hash(
    schema_version,
    league_id,
    low_user_id,
    high_user_id,
    sorted(low_user_gives),
    sorted(high_user_gives)
)
```

The hash must include league and both participants so identical asset packages in unrelated leagues do not collide. Keep the existing `trade_hash` for viewer-relative fatigue/dedup behavior; the two fields serve different purposes.

When a card is explicitly injected because another manager previously liked the mirror, also stamp `source_like_impression_id`. This distinguishes an organic independently generated mirror from a card shown because of the first manager's action.

### Timeline data

The existing event timestamps remain authoritative:

- `deck_impressions.served_at`: when this user received this version of the card
- first `deck_outcomes.viewed.acted_at`: when the card was actually exposed for at least the client threshold
- effective like/pass outcome `acted_at`: when the user decided
- `trade_matches.matched_at`: when the second compatible like created the match

Use server UTC timestamps for comparisons. Client timestamps may be retained for diagnostics but must not drive latency calculations without clock-skew handling.

Extend new `trade_decisions` writes with nullable `impression_id` and `trade_concept_id`. Extend `trade_matches` with:

```text
trade_concept_id
user_a_impression_id
user_b_impression_id
first_like_at
second_like_at
match_latency_seconds
match_valuation_json
```

The impression links are the source of truth; the timestamps/latency on `trade_matches` are denormalized audit fields that make the match stable even if event-query semantics later change. Legacy matches may leave the new fields null.

### Preserve values at each point in time

Each user's impression retains its own `valuation_json`, including that user's serve-time:

- Consensus package values and snapshot date/version
- Raw and effective personal values for both managers
- Ranking-confidence weights
- Board update timestamps
- Policy and generator attribution

When the second like creates a match, write `trade_matches.match_valuation_json` by re-evaluating the unchanged package under the then-current roster, consensus, and personal-board state. This third snapshot answers whether the concept was still valid when it became mutual. It must not overwrite either user's earlier impression snapshot.

The three records then answer different questions:

| Snapshot | Question |
|---|---|
| Manager A impression | Why did A see and like it at that time? |
| Manager B impression | Why did B see and like/pass it at that later time? |
| Match snapshot | Was the unchanged trade still valid and market-plausible when mutual interest formed? |

### Staleness and revalidation

Before serving a liked mirror to the second manager, revalidate:

- Both managers still own the required assets
- The league and rosters are current enough for the existing session policy
- The package still clears the second manager's active market-policy floor
- The concept has not expired, been dismissed, been proposed, or already matched

If it no longer qualifies, do not silently count the second manager as a rejection. Record a shadow/ineligibility reason such as `roster_changed`, `market_drift`, `expired`, or `already_resolved`.

A match may only be created from two compatible likes on the same canonical concept while the package remains valid. If revaluation fails the current finder policy but the product elects to honor an older like, record that fact explicitly in `match_valuation_json`; do not make it indistinguishable from a currently eligible match.

### Analysis rules for interaction lag

Never interpret "A liked and B did not" as a negative outcome without confirming B's exposure state. Report the funnel as:

```text
first user liked
  -> mirror was eligible
  -> mirror was generated
  -> mirror was served
  -> mirror was viewed
  -> second user passed / liked / did not decide
  -> mutual match
  -> proposal
```

At minimum, segment second-user behavior by interaction lag:

- Under 1 hour
- 1-24 hours
- 1-3 days
- 4-7 days
- More than 7 days / expired

Also report whether consensus or either personal board changed between the two impressions. A policy arm should not receive blame for a non-match caused by no exposure, a roster transaction, or material value drift.

For the policy experiment, preserve both dimensions for both users. Manager A and Manager B may have encountered the concept under different `policy_variant` values. Attribute a mutual result jointly and report same-policy and cross-policy pairs separately rather than crediting only the second like.

## Implementation shape

Introduce one shared policy evaluator used by every generator rather than copying threshold logic between `trade_service.py` and `trade_optimizer.py`. A small module such as `backend/trade_policy.py` may own:

```text
compute_market_ratio(...)
compute_package_confidence(...)
compute_personal_opportunity(...)
derive_policy_floor(...)
evaluate_trade_policy(...)
```

The evaluator should return an immutable result containing:

- Eligible or rejected
- Rejection reason
- Market ratio
- Requested, policy, and effective floors
- Viewer and partner effective surplus/gain
- Package confidence for each manager
- Personal-opportunity score
- Core/Conviction/Fallback classification
- The complete valuation snapshot used for telemetry

Generation may use cheap prefilters, but every card must pass the shared evaluator after its final package is assembled. This is particularly important after adding a sweetener or swapping an asset.

Ship behind a new feature flag such as:

```text
trade.personal_market_policy_v1
```

Flag-off behavior must be byte-for-byte equivalent to the existing policy for every generator arm. Do not create a fourth generator arm and do not overwrite or repurpose an existing profile. In particular, do not modify the pinned historical `MODEL_A_PROFILE`.

Treat generator and policy as orthogonal attribution dimensions:

| Dimension | Values | Question answered |
|---|---|---|
| `model_arm` | `current`, `challenger`, `gen_v2` | Which candidate generator produced the card? |
| `policy_variant` | `legacy`, `personal_market_v1` | Which eligibility/ranking/deck policy governed the job? |

The existing three arms continue to generate candidates inside both policy variants. The treatment applies the shared confidence, market-floor, personal-opportunity, and deck-composition evaluator to each arm's output. This design answers:

1. Does `personal_market_v1` improve results across the live portfolio of generators?
2. Does the policy help or hurt a particular generator?
3. Do `current` and `challenger`, which have the highest current point estimates, remain successful after the policy is applied?
4. Does `gen_v2` remain valuable as a smaller contributor lane despite its supply constraint?

Stamp `policy_variant` independently of `model_arm` on every served and shadow impression. A candidate rejected by the treatment must remain visible in shadow telemetry with its generator arm and rejection reason; otherwise the treatment will appear artificially precise because its discarded candidates vanish from the denominator.

## Tests

At minimum, add coverage for the following behaviors:

1. A one-board/consensus card at `0.84` is rejected when its floor is `0.85`; one at `0.85` is accepted.
2. Weak-confidence divergence cannot pass below approximately `0.80`.
3. Strong, high-confidence two-board opportunity may pass at `0.65`.
4. No finder card passes below the absolute `0.65` floor.
5. Increasing confidence or increasing the weaker manager's gain never tightens the dynamic floor.
6. Missing confidence fails safe.
7. The two managers' boards are confidence-shrunk symmetrically.
8. Wide uncertainty ranges cannot rescue a point ratio below the hard floor.
9. A stricter user preference tightens the floor; it can never loosen policy.
10. Relaxed fallback, sweeteners, swaps, likes-you cards, wildcards, and replenishment cannot bypass the evaluator.
11. Holding eligibility constant, increasing the weaker manager's personal gain cannot lower the card's pre-presentation ranking.
12. Sufficient high-quality divergence inventory is not displaced solely because consensus cards have a higher fairness score.
13. Deck Core/Conviction quotas and top-three rules hold.
14. Finder and calculator consensus package values remain identical.
15. Reversing the two managers and package direction preserves market ratio, eligibility, and personal-opportunity magnitude.
16. Every new impression contains a parseable valuation snapshot whose assets and sides match `assets_json`.
17. A confirmed provider proposal creates exactly one impression-linked `propose` outcome when it originated from a card.
18. A confirmed provider proposal creates exactly one idempotent `trade_proposals` row containing the final asset package and a proposal-time valuation snapshot.
19. Editing a card before send preserves the origin link while storing different origin/final hashes and recalculated final values.
20. Mirrored impressions for the same league, participants, and packages receive the same canonical `trade_concept_id` regardless of viewing direction.
21. A mutual match records both source impression IDs, both like times, the measured lag, and a match-time valuation snapshot.
22. A user who was never served or never viewed the mirror is not counted as a pass or failed counterparty decision.
23. A stale liked mirror is revalidated before serving and records a closed ineligibility reason if ownership, expiration, or value drift invalidates it.

Tests must cover both v2 and v3 paths and any server-side deck injection/replenishment path. Update the applicable backend test suites rather than relying only on a new isolated unit test.

## Rollout plan

### Phase 1: telemetry and confidence only

- Add confidence persistence and `valuation_json`.
- Add the shared evaluator in shadow mode.
- Do not change candidate eligibility or served order.
- Compare shadow values against current stored fairness and mismatch values.
- Require at least 99% of new divergence impressions to contain valid telemetry before moving on.

### Phase 2: dark replay and shadow generation

- Retrospectively test only stricter floors against historical impressions.
- Run shadow generation for policy changes that could create new candidates; historical served data cannot reveal candidates the old engine rejected.
- Run all three existing generators through both `legacy` and `personal_market_v1` against the same eligible league/board snapshots. Compare candidate supply, composition, and knockout reasons before changing serving.
- Stamp shadow/ghost rows with policy version and candidate provenance.
- Verify deck supply, generation latency, and the share of personalized cards.

### Phase 3: limited live experiment

- Keep `current`, `challenger`, and `gen_v2` in the underlying generator mix. Do not delete or pause an arm based on the present sample.
- Randomize the policy at the **deck-job level**, not the individual-card level. A control job uses the existing arm mix and legacy policy; a treatment job uses the same arm mix under `personal_market_v1`.
- With the current small user cohort, use a balanced within-user/league crossover schedule so each active user encounters both policies. Do not assign the five users permanently to separate policies.
- Do not mix legacy-policy and treatment-policy cards within one deck. Deck composition is part of the treatment and must be evaluated as a coherent experience.
- Start with the proposed dynamic policy and `0.65` absolute floor.
- Continue using the existing interleaved bake-off machinery **within** each deck to maintain explicit generator quotas, arm attribution, and candidate provenance.
- Ensure the generator mix is comparable between control and treatment jobs. A treatment card removed by policy must remain recorded as a shadow rejection rather than silently reducing that generator's denominator.
- Evaluate results within user and deck job before pooling them; do not treat cards from one deck as independent observations.
- Ramp treatment allocation only after each stage passes the guardrails below.
- All knobs remain remotely configurable for deploy-free rollback.

### Phase 4: promotion decision

Primary metrics:

- Confirmed proposal rate per viewed card and per generated deck
- Mutual-match rate
- Match acceptance/decline when enough data exists

Secondary metrics:

- Like rate among viewed/decided cards
- `value_giving` and `value_getting` decline rates
- Explicit bad-trade-flag rate
- Median and low-percentile market ratio
- Personal-opportunity distribution
- Percentage of cards using two real boards
- Empty-deck rate, cards per job, latency, and diversity

Do not promote based on pooled card-level significance alone. Report by user and use user/deck-job clustered uncertainty.

## Acceptance criteria

### Instrumentation readiness

- At least 99% of new divergence impressions contain parseable `valuation_json`.
- Snapshot asset IDs and directions exactly match `assets_json`.
- Recomputed market ratio matches stored consensus fairness within `0.001`.
- Recomputed personal/mutual scores match the values used during generation within documented rounding tolerance.
- At least 95% of likes/passes and 100% of confirmed direct proposals are linked to an owned, non-stale `impression_id`.
- Every confirmed provider send creates one idempotent `trade_proposals` record; its asset arrays and trade hash match the final provider request rather than the original suggestion.
- Proposal-time consensus and personal values are frozen from the board/value state used at send time and are never reconstructed from later rankings.
- At least 99% of new mirrored-card impressions carry a canonical `trade_concept_id`; mutual matches created from fully instrumented cards link both users' exact impressions.
- Match reporting separates never-eligible, never-served, never-viewed, undecided, passed, liked, stale, and invalidated states rather than treating every missing second like as rejection.
- Telemetry does not fail a trade job and adds no more than 5% to p95 generation latency.

### Policy correctness

- No served finder card has a market ratio below `market_floor_absolute`.
- A user setting can only tighten the effective floor.
- A card with no real opponent board uses the one-board floor and is never described as a proven mutual win.
- Core/Conviction composition rules hold when sufficient inventory exists.
- The new arm does not reduce the share of valid two-board cards by replacing them with consensus cards.

### Experiment graduation

- Confirmed proposal or mutual-match conversion improves, or is non-inferior while structured value-related declines fall.
- Likes/proposals per generated deck do not fall by more than 10%.
- Bad-trade-flag rate does not increase.
- Empty-deck rate does not increase by more than two percentage points.
- Generation latency stays within the current service budget.
- Results extend beyond the current five-user cohort. Do not call the policy conclusive before at least 100 viewed decisions per arm, 50 structured decline reasons per arm, and meaningful participation from multiple independent users/leagues.

## Non-goals

- Replacing or retraining the consensus data sources
- Building a machine-learned value model in this change
- Redesigning the ranking workflows
- Exposing another manager's exact private rankings
- Changing the manual calculator's market-value definition
- Modifying the website
- Automatically accepting or completing trades

## Required documentation updates when implemented

Because implementation changes schema, API semantics, configuration, and trade-engine behavior, the engineering change must also update:

- `docs/data-dictionary.md`
- `docs/api-reference.md`
- `docs/config-reference.md`
- `docs/architecture.md`
- `docs/cross-client-invariants.md` if fairness terminology or thresholds are shared with mobile
- A feature scope block under `docs/plans/`
- `living-memory/DECISIONS.md` for the constraint-versus-objective decision
- `living-memory/TEST_LEDGER.md` with automated and manual evidence
