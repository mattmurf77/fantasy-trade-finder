# Reading the two-user funnel

**Date:** 2026-09-04 · **Scope block:** [scope.md](scope.md)

A mutual trade is a **sequence**, not one observation:

```
Manager A is served the concept
  → A views it
  → A likes it
  → the mirrored concept becomes eligible for Manager B
  → B may be served it minutes or days later
  → B views, passes, likes, or never acts
  → if B likes, a mutual match is created
```

Consensus values, rosters, personal boards and even the active policy can change between
those steps. **Never interpret "A liked and B did not" as a negative outcome without
first confirming B's exposure state.** Before this change that was not merely bad
practice — it was unavoidable, because a mirror that was never served left no row at all,
so every funnel query silently counted it as a rejection by B.

This file is the mapping that makes each state distinguishable. It is not a query
library; it is the definition an analyst has to hold.

## The nine states, and where each one lives

Anchor everything on the canonical `trade_concept_id` — **not** `trade_hash`, which is
viewer-relative and hashes A's card and B's mirror differently.

| State | How it is identified | Notes |
|---|---|---|
| **never eligible** | a `trade_policy_shadow` row for B's `(user_id, trade_concept_id)` with `reason` ∈ `roster_changed`, `already_resolved`, `expired`, `market_drift` | Written by `_mirror_skip_rows` from the likes-you injector. The concept existed but could not be offered. |
| **never generated** | A's like exists (`trade_decisions`), no `deck_impressions` row for B on that concept, **and** no shadow row | The generator simply never produced it for B. Distinct from "rejected": a rejection has a shadow row. |
| **rejected by policy** | a `trade_policy_shadow` row with `reason` ∈ `below_effective_floor`, `below_absolute_floor`, `no_two_sided_gain`, `deck_quota`, `core_share_shortfall` | The treatment's discarded candidates. **These are the denominator** — without them the policy looks precise no matter how much supply it destroyed. |
| **never served** | no `deck_impressions` row for B on that concept | Includes `is_ghost = 1` rows: a withheld ghost was logged, not shown. |
| **never viewed** | a `deck_impressions` row exists, but no `deck_outcomes` row with `action = 'viewed'` | The client fires `viewed` after a card is front-of-deck ≥500 ms. Served ≠ seen. |
| **undecided** | `viewed` exists, but no effective `like` / `pass` / `not_interested` | B saw it and moved on. **Not a rejection.** |
| **passed** | effective outcome resolves to `pass` (or `not_interested`, analyzed separately) | Resolve the **most recent** `like` / `pass` / `undo` per impression, and count **distinct impressions**, not raw outcome rows — duplicate pass events have existed in prod. |
| **liked** | effective outcome resolves to `like` | |
| **matched** | a `trade_matches` row carrying that `trade_concept_id` | `user_a_impression_id` / `user_b_impression_id` name the two cards; `first_like_at` / `second_like_at` / `match_latency_seconds` give the lag. |

## Interaction lag

Segment second-user behaviour by `match_latency_seconds` (or, where no match formed, by
B's `deck_impressions.served_at` minus A's like time), into the brief's five buckets:

`< 1h` · `1–24h` · `1–3d` · `4–7d` · `> 7d / expired`

Also report **whether consensus or either personal board changed between the two
impressions.** Both are answerable from the frozen snapshots without re-deriving
anything: `valuation_json.market.consensus_asof` and
`valuation_json.{viewer,partner}_board.board_updated_at`. A policy arm must not be blamed
for a non-match caused by no exposure, a roster transaction, or material value drift.

## The three snapshots answer three different questions

| Snapshot | Question |
|---|---|
| A's `deck_impressions.valuation_json` | Why did A see and like it *at that time*? |
| B's `deck_impressions.valuation_json` | Why did B see and like/pass it *at that later time*? |
| `trade_matches.match_valuation_json` | Was the unchanged trade still valid and market-plausible when mutual interest formed? |

The match snapshot re-evaluates the **unchanged package** under the then-current roster,
consensus and board state. It must never overwrite either user's earlier impression
snapshot — and if the product elects to honour an older like whose revaluation now fails
the current policy, that fact is recorded in the snapshot (`policy.eligible: false` plus a
reason) rather than being made indistinguishable from a currently-eligible match.

## Cross-policy pairs

For the experiment, **preserve both dimensions for both users.** A and B may have
encountered the same concept under different `policy_variant` values — a match is
attributed **jointly**, and same-policy and cross-policy pairs are reported separately.
Crediting only the second like would attribute a mutual outcome to whichever policy
happened to serve last.

## Standing hygiene rules (inherited, still apply)

- Exclude `league_demo` and ghost impressions.
- Require `viewed` when computing view-based conversion.
- Count **distinct impressions**, not raw outcome rows.
- Analyze `not_interested` and `bad_trade_flags` separately from ordinary passes — an
  explicit "the engine got this wrong" is a stronger negative signal.
- Hash user and league ids in any analyst output.
- **Cluster uncertainty by user and deck job.** Cards from one user's deck are not
  independent observations; the 2026-09-04 read had five deciding users, and pooled
  card-level significance would be badly overconfident.
