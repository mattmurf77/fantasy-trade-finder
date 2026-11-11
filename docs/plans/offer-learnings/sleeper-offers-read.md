# Sleeper's private trade-offers read — what it returns

**Date:** 2026-11-10 · **Decision:** the operator approved adding this read ("I'm aligned on the
private read") · **How this was learned:** from the operator's own signed-in Sleeper web
session, read-only. The page made the calls with its own sign-in; no token was read, copied or
stored, and nothing was sent or changed. Only operation names, field names, status words and
counts were kept. No offer contents are in this file.

This is the capture the [trade-outcomes scope block](scope-trade-outcomes.md) said Part B
needed. It unblocks true decline detection, counters, and the consented import.

## The call

Sleeper's web app posts GraphQL to `https://sleeper.com/graphql`. The call is rejected
("Unauthorized") without the signed-in user's authorization header, the same credential
Send in Sleeper already holds for a linked user.

```
league_transactions_filtered(
  league_id: String!, type_filters: [String], status_filters: [String],
  roster_id_filters: [Int], leg_filters: [Int], limit: Int
): [LeagueTransaction]
```

Fields confirmed on a returned transaction: `transaction_id`, `type`, `status`, `leg`,
`created`, `status_updated`, `creator` (a user id), `roster_ids`, `consenter_ids`, `adds`,
`drops`, `draft_picks`, `waiver_budget`, `metadata`, `settings`, `player_map`.

`league_id`, `type_filters`, `status_filters` and `limit` were used as written above. The
names `roster_id_filters` and `leg_filters` are inferred from the page's own variable names
and were not exercised. Omitting `status_filters` returns every status. Asking for a status that does not exist
returns an empty list, not an error.

## What comes back for trades (`type_filters: ["trade"]`)

Across the operator's three leagues (170 trade transactions, 2026-01 to 2026-11):

| `status` | Count | What it is | How to tell |
|---|---|---|---|
| `proposed` | 4 | A pending offer | `consenter_ids` holds one roster; usually `settings.expires_at` |
| `complete` | 40 | An accepted trade | `consenter_ids` holds both rosters. Also public |
| `rejected` | 75 | **Declined by the other manager** | `metadata.rejecter_id` is a user id and is never the `creator` |
| `cancelled` | 51 | Withdrawn or lapsed | `metadata.rejecter_id` equals the `creator` on 39 (withdrawn by the proposer); absent on 12 (lapsed or invalidated) |

No transaction carried `declined`, `failed`, `expired`, `canceled`, `pending`, `countered`,
`withdrawn` or `vetoed`.

- **Counters are flagged.** `settings.is_counter` is set on a counter-offer (20 of the 170).
  Nothing links a counter to the offer it answers; the link has to be made by the same two
  rosters and timing (the counter's `created` at or just after the original's
  `status_updated`).
- **`settings.expires_at`** appears on 31, including all 4 pending offers.
- **Every `status_updated` is populated**, so the time of a decline is known.
- **Scope: only the signed-in user's own offers.** Every `proposed`, `rejected` and
  `cancelled` transaction involved the signed-in user's roster. The only transactions
  between other managers were `complete`, which the public API already shows. The read does
  not expose league-mates' private offers to each other.
- Two-team trades almost always (two three-team rejections seen). Picks appear on most; FAAB
  on one.
- A league id is per season, so one call covers the current league year.

## What this makes possible

| Need | Source |
|---|---|
| "The offer I sent was declined" | `status: rejected`, `creator` = me |
| "I withdrew it" (no revised-offer card) | `status: cancelled`, `rejecter_id` = me |
| "They countered" | a later transaction between the same two rosters with `settings.is_counter`, `creator` = them |
| "I declined their counter" (middle-ground card) | that counter with `status: rejected`, `rejecter_id` = me |
| "Still pending" (no card) | `status: proposed` |
| Offers made in Sleeper directly, not through the app | the same call, with the user's consent |

## Not established

- Whether the selection set above is complete; other fields may exist.
- How far back one call reaches beyond `limit` (the largest league returned 85 trades with
  no limit pressure).
- Whether Sleeper rate-limits this call, and what repeated polling looks like to them.
- ESPN and MFL: not looked at here. MFL documents a `pendingTrades` export.
- The risk is the same kind as Send in Sleeper: an unofficial interface, used with the
  user's own credential, at the user's account's risk.
