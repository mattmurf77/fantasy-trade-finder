# Sleeper Pending Trades — Feasibility Memo (2026-08-12)

> **This is the "#83 feasibility memo"** that [`competitor-top20/11-received-offer-analyzer.md`](competitor-top20/11-received-offer-analyzer.md) has been gated on since 2026-06-11, and the answer to the C2 deliverable left blank in [`sleeper-write-capture-runbook.md`](sleeper-write-capture-runbook.md). Also answers the open question in [`auth-multiplatform-plan-2026-06-11.md:298`](auth-multiplatform-plan-2026-06-11.md).
>
> **Question:** do open/pending Sleeper trade offers appear in the *public* `api.sleeper.app/v1` REST API?
>
> **Answer: No — and not by accident. Open offers are a private two-party object in Sleeper's product model.**

---

## The finding

**An open Sleeper proposal carries `status: "proposed"`, and that value exists only on the private GraphQL surface.**

This is confirmed from FTF's own live browser capture (`sleeper-write-capture-runbook.md:160`): the `propose_trade` mutation returns a transaction object where a fresh proposal is `status: "proposed"`. That literal appeared **zero times** across every public-API sweep below, and appears **zero times** in Sleeper's public documentation, which only ever shows `complete`.

### Empirical evidence — independent sweeps, all unauthenticated, all agreeing

| Sweep | Leagues | Trades observed | Non-`complete` trades |
|---|---|---|---|
| Session coordinator | 5 | 25 | **0** |
| Parity agent | 247 | ~1,259 | **0** |
| Research agent (A + B) | 252 | 1,677 | **0** |

Across independent runs, **well over 1,600 trades, not one in any state but `complete`.**

**The control that makes this meaningful:** the same payloads carried **781 `waiver` rows with `status: "failed"`**. So the endpoint is *not* blanket-filtered to completed rows — non-terminal statuses do publish. The absence is specific to trades.

### The mechanism — why, not just what

Sleeper's own support documentation explains it: an offer is visible to its recipient on **their own team's Trades tab**; it is not a league-wide event. Only on acceptance does a trade enter review and become a league-visible transaction. So an unaccepted offer is a **private two-party object**, and `api.sleeper.app/v1` — which is **identity-blind** (no auth parameter; full transaction history retrievable for leagues one is not a member of) — has no way to scope it to a viewer. There is no "members see more" variant to exploit. The distinction is not unauthenticated-vs-member; it is **v1 REST vs. `sleeper.com/graphql` + JWT**.

### `consenter_ids` is a false lead on the public API

Present and documented ("roster_ids of the people who agreed"), but useless for pending detection: because only completed trades publish, `consenter_ids` always already equals the full `roster_ids` set. No row was observed where it was a strict subset. On the *private* surface it would be meaningful — `roster_ids − consenter_ids` = who still owes a response, with `creator` giving direction — but that requires the JWT path.

### Third parties agree by omission

`ffscrapr` carries trade `status` through without filtering and has **no pending-trade concept** in source. `sleeper-api-wrapper`, `sleeper-go`, and `sleeper-client-typescript` all mirror the documented shape with no pending-offer method. A community catalog of *undocumented* Sleeper endpoints lists `sleeper.com/graphql` but **no trade-offer endpoint**. An external issue thread pursuing the same feature treats the status vocabulary as an unresolved blocker.

> **Epistemic warning:** several web searches confidently asserted "the API supports pending status." Every one traced back to an LLM summarizer with no primary source. Treat as unsupported.

## What this means for FTF

**The gating capability for Sleeper's entire respond side is read-pending, and it is token-only.**

The binding constraint is not mutation vocabulary — it is the **`transaction_id`**. Every respond operation needs one, and FTF's only source today is the id returned by its own `propose_trade`. FTF cannot learn the id of an **incoming** offer. So the already-built-but-unrouted `reject_trade` can only ever act on proposals FTF itself sent, and recovering an `accept` mutation would not change that.

Per the decision rule pre-committed in the #11 plan — *"if pending offers are token-only, then V1 is the product"* — **manual offer entry is the product.** An automatic received-offer inbox is reachable only by extending the ToS-adverse JWT/GraphQL surface.

**The risk asymmetry is the argument.** Reaching Sleeper inbox parity would mean doubling down on the reverse-engineered path to add a *read* that MFL provides through a sanctioned, documented export. That runs the wrong way.

### Recommended, in order

1. **Persist the `transaction_id`** that `POST /api/trades/propose` already receives and currently discards, then reconcile it against the existing public completed-transaction sweep in `sleeper_trades_service.py`. FTF can then tell a user "your offer was accepted" with **zero authenticated calls**. Most of the perceived lifecycle value, none of the risk. ~1 day.
2. **Route the existing `reject_trade` as revoke-our-own-offers only**, keyed off that id. Mirrors MFL's stated near-term use. No new capture. ~0.5 day.
3. **Build nothing else here** unless the operator accepts the ToS posture explicitly.

---

# ADDENDUM (same day) — the technical answer changed; the recommendation did not, it hardened

Two later research passes overturned parts of the above **on capability** while making the case against building **stronger**, for a reason that has nothing to do with capability.

## 1. Sleeper's full GraphQL schema is public — everything is reachable

A complete `__schema` introspection dump of `https://sleeper.com/graphql` (dated 2025-10-17, 329 mutations, 219 queries) is committed publicly on GitHub. Its `LeagueTransaction` type matches FTF's own live capture field-for-field, which is what makes it credible. It answers every open question with **server-supplied signatures**, not naming guesses:

```graphql
accept_trade(leg: Int!, league_id: Snowflake!, transaction_id: Snowflake!): LeagueTransaction   # "Accept Trade"
league_transactions_filtered(league_id: Snowflake!, type_filters: [String],
                             status_filters: [String], ...): [LeagueTransaction]                 # status_filters: ["proposed"]
```

- **`accept_trade` takes the identical triple as `reject_trade`.** No roster-limit drop list — Sleeper explicitly permits going over the roster limit through a trade, so drops are a separate later transaction. The asymmetry this memo worried about does not exist.
- **Read-pending IS reachable** via `league_transactions_filtered(status_filters:["proposed"])`. The `transaction_id` problem that gated the entire respond side is solved *on this surface*.
- **There is no `cancel_trade`.** `force_cancel_transaction` is labelled **commissioners only** by the server itself. Withdrawing one's own offer is most likely `reject_trade` on it — inferred, unproven.
- **Bonus:** `propose_trade` carries `reject_transaction_id` / `reject_transaction_leg`, i.e. counter-offer is atomic.
- **Corrections to FTF's captured signature:** there is **no `roster_ids` argument** (participants are derived server-side from `v_adds`/`v_drops`); `draft_picks` and `waiver_budget` are `[String]`, not object arrays; and `expires_at` exists but was never captured.

So: **full Sleeper lifecycle parity is technically straightforward.** Days of work, not weeks.

## 2. Why it should still not be built — Sleeper rewrote its Terms three weeks ago

[Sleeper Terms of Use](https://support.sleeper.com/en/articles/5486620-terms-of-use), **last updated 2026-07-24**. A Wayback comparison against the 2022-05-26 snapshot confirms this language is **new** — none of it existed before:

- **§11.1** prohibits users from providing "login credentials, access tokens, session identifiers" to any third party.
- **§11.3** prohibits any third party from accessing data "through any account, credential, or authentication mechanism belonging to a user, except pursuant to a separate written agreement executed by Sleeper" — and **pre-empts the obvious defence**, stating the user's own grant "does not constitute authorization from Sleeper."
- **§11.2** reserves the right to revoke sessions and technically block the third party, "whether or not that third-party is itself a user."
- The only sanctioned route is **§2.9 Approved Integration Partner** status via a written agreement. Sleeper's sanctioned Minis SDK has **no write surface** at all.

**This is not merely a reason to decline new work. It describes FTF's already-shipped, currently-live `trade.send_in_sleeper` feature**, which stores the user's JWT and replays it against `sleeper.com/graphql`. That feature predates this ToS revision. Its risk posture changed under it, three weeks ago, without anyone noticing.

That a competitor (Dynasty Daddy) operates the same pattern unchallenged is **not evidence of permission**.

## 3. Revised recommendation

The two zero-risk items below (persist `transaction_id`, reconcile against the public completed sweep) remain correct and should still be built — they touch only the sanctioned public API.

Everything on the GraphQL surface is a **business decision, not an engineering one** — and **the operator has resolved it.**

### RESOLVED 2026-08-12 — the operator states FTF has explicit agreement from Sleeper to use this surface

This is exactly the carve-out §11.3 names ("except pursuant to a separate written agreement executed by Sleeper") and §2.9's Approved Integration Partner concept. **The ToS objection above is therefore answered, and both the existing live `trade.send_in_sleeper` feature and any further GraphQL work are cleared to proceed.**

Two notes so this record stays useful rather than becoming a game of telephone:

- **A future session reading §2 above will otherwise re-raise this alarm.** Anyone who does should stop at this section: the terms question was raised, escalated, and answered by the operator on 2026-08-12.
- **Worth attaching the artifact.** A pointer to the agreement — its form, date, and counterparty at Sleeper — filed alongside this memo (or in `docs/business/`) would let the record stand on its own. Not a precondition for building; a durability improvement, and the kind of thing that matters if the question is ever asked from outside.

### Consequently, the recommendation flips

Sleeper full lifecycle parity is **viable and now the best-understood of the three platforms** — better than ESPN, where accept/reject payloads remain genuinely uncaptured. The public schema dump gives server-supplied signatures for everything:

| Capability | Path | Status |
|---|---|---|
| Read pending | `league_transactions_filtered(status_filters:["proposed"], type_filters:["trade"])` | **confirmed reachable** |
| Accept | `accept_trade(leg, league_id, transaction_id)` | **confirmed signature** |
| Reject | `reject_trade(...)` — same triple | **already built**, unrouted |
| Revoke own offer | no `cancel_trade` exists; `force_cancel_transaction` is **commissioners-only** per the server's own description | likely `reject_trade` on one's own offer — **inferred, unproven** |
| Counter-offer | `propose_trade(reject_transaction_id, reject_transaction_leg, …)` — atomic | **confirmed signature** |

Fix these in `backend/sleeper_write.py` when the work is picked up: there is **no `roster_ids` argument** (participants derive server-side from `v_adds`/`v_drops`); `draft_picks` and `waiver_budget` are `[String]`, not object arrays; and `expires_at` exists but was never captured.

The two zero-risk public-API items (persist `transaction_id`, reconcile against the completed sweep) are still worth doing first — they are cheap, independent, and useful regardless.

## The one experiment that could still overturn this

Create a trade offer in a dummy Sleeper league, **leave it pending**, then hit `GET https://api.sleeper.app/v1/league/<id>/transactions/1` unauthenticated. No credentials, no writes by FTF, no GraphQL.

The proposed-awaiting-response case is considered **settled**; this would be a belt-and-braces confirmation. The genuinely open sliver is the *accepted-and-in-review* window — short-lived, and zero-length in leagues with review disabled — which the sweeps could plausibly have missed.
