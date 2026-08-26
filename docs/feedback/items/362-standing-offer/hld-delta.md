# HLD delta — #362 Standing offer

> Delta against [`docs/architecture.md`](../../../../docs/architecture.md) and
> [`living-memory/HLD.md`](../../../../living-memory/HLD.md). **A delta, not a rewrite** —
> the sections below are the only ones that change.
>
> Base: `origin/main` + `f68eddd`. Every `file:line` verified 2026-08-19.
> Mechanics are in [`lld-delta.md`](lld-delta.md); requirements in [`prd.md`](prd.md).

---

## 1. Why this item warrants an HLD delta at all

Most feedback items do not. This one does, for one reason:

**`standing_offers` is FTF's first cross-user broadcast object.**

Every existing trade-intent record in the system is *point-to-point and self-scoped*:

| Record | Who it is about | Who can act on it |
|---|---|---|
| `trade_decisions` (like/pass) | one exact package, one counterparty | that one counterparty, via the mirror test |
| `asset_preferences` (untouchable / target / not-interested) | the owner's own roster | nobody but the owner — it is a filter on the owner's own deck |
| `league_preferences` (outlook, positions) | the owner's own strategy | nobody but the owner |
| `trade_matches` | two named users | those two |

`standing_offers` is the first row a user writes that is **evaluated on behalf of other
users, repeatedly, over time, without any further action from its author**. One row
fans out to up to 11 decks and keeps doing so for 30 days.

That is a genuine data-flow addition — a *fan-out edge* the architecture did not previously
have — and it is why the privacy invariant (PRD R-19) and the injection ceiling (R-14) are
architectural constraints rather than product polish. Everything else about the item is
reuse.

---

## 2. Delta to `docs/architecture.md` § Data flow (`:5`)

Add one node and one edge. `standing_offers` is written by the swipe surface and read by
the deck generator **for a different user than the one who wrote it**:

```
TradesScreen (sender)                                _run_trade_job (recipient)
    │ POST /api/trades/standing-offer                        │
    ▼                                                        │
standing_offers ────────────── read, cross-user ─────────────┘
    ▲                                                  _inject_likes_you_cards_impl
    │ POST /api/trades/standing-offer/revoke
MatchesScreen (sender)
```

No other table gains an edge. `draft_picks` and `league_members` are read at validation
time only, both already-existing reads.

---

## 3. Delta to `docs/architecture.md` § "Request lifecycle (trade card — v2 engine)" step 5

Step 5 currently reads:

> **Likes-you injection** (`trade.likes_you`): cards whose mirror a league-mate already
> liked are flagged/synthesized and pinned to the top (cap 3). The R4 exclusion set also
> applies here (dedup only — the quality rules stay off this surface per Q21; the D-055
> user-gain floor remains its quality gate).

**Replace with:**

> **Likes-you injection** (`trade.likes_you`): the injector draws candidates from **two
> sources** and pins survivors to the top, capped at 3 total.
> **(a) Exact mirrors** — cards whose mirror a league-mate already liked
> (`trade_decisions`, 90-day window).
> **(b) Standing offers** (`trade.standing_offers`, #362) — a league-mate's generalised
> intent "I will send player P for any round-R pick, in seasons Y, from teams T", stored in
> `standing_offers` and live until `expires_at`. A standing offer yields a candidate for a
> viewer who is in the offer's team set and holds a matching owned pick.
> Mirrors are evaluated first; standing offers may take at most
> `standing_offer_inject_cap` of the 3 slots (default 2), and cap drops are counted per
> job, not evented.
> **Both sources then pass through the identical filter sequence** — untouchables (#95),
> not-interested (#163), `_past_decision_keys`, the R4 exclusion set (dedup only per Q21),
> and the D-055 user-gain floor, which remains the injector's only quality gate. Off ⇒ no
> standing-offer candidate is constructed and deck payloads are byte-identical.

Also add one bullet under the same lifecycle, after step 5:

> **Own-offer stamping** (`trade.standing_offers`): the deck owner's own live standing
> offers stamp `standing_offer_mine` on cards they cover, so the client can render the
> sender-side chip without a join. Display only — never reorders, boosts, or filters.

---

## 4. Delta to `docs/architecture.md` § Components (`:120`)

One row, in the `backend/database.py` neighbourhood of the table listing:

| Table | Purpose |
|---|---|
| `standing_offers` | #362 — a user's generalised, time-boxed, team-targeted intent to trade one player for any pick of a round. **The system's only cross-user broadcast record**: written by its author, evaluated on behalf of the selected league-mates by the likes-you injector until `revoked_at` or `expires_at`. |

---

## 5. Delta to `living-memory/HLD.md` § Key Flows (`:106`)

Add **Flow F**, after Flow E:

> ### Flow F — Standing offer (#362, flag `trade.standing_offers`)
> 1. A user right-swipes a 1-for-1 in which they receive a first-round pick. The like is
>    committed and the deck advances **before** anything else happens — the prompt can
>    never cost the user their like.
> 2. A gated sheet asks which other seasons and which other teams they would take a first
>    from. The season pills are derived from the league's real pick horizon
>    (`all_picks`, kept horizon-correct at the writer by D-091), never a fixed window.
>    Default selection is the source team and source season only; **All** is one tap.
> 3. `POST /api/trades/standing-offer` writes one `standing_offers` row, live for
>    `standing_offer_days` (30). At most one live row per
>    `(user, league, player, round)`, enforced at the writer.
> 4. For each selected league-mate's next deck, `_inject_likes_you_cards_impl` constructs
>    one candidate per offer — the viewer's matching owned pick out, the offered player in
>    — and runs it through the same filters as an exact mirror. Survivors render as the
>    shipped likes-you card plus a server-composed "Why you're seeing this" line.
> 5. The sender revokes from Matches → Standing offers, or the offer expires.
>
> **Invariant (privacy):** the recipient learns that **they** were selected. They never
> learn who else was selected and never who was excluded. `team_user_ids` is read only
> inside the match test and never appears on a recipient-facing payload; the reason line
> is composed from `(sender, player, round, seasons)` only. The one residual leak — two
> league-mates comparing notes can infer exclusion — is inherent to targeted broadcast and
> is accepted, not engineered around.

---

## 6. Delta to `living-memory/HLD.md` § Design Trade-offs at the System Level (`:154`)

One entry:

> **Broadcast intent is bounded by the user's own selection, not by a value model.**
> A standing offer says "any 1st", with no value band. That is not an approximation: in
> the shipped pricing model every first in a league carries *identical* engine value —
> `pick_pool_value` prices every league pick at the generic ladder's Mid rung of its round
> (`backend/pick_values.py:264-286`, upheld by D-090; per-slot pricing is unbuilt as
> Q-023) and D-079 set round-1 year decay to 1.00 (`backend/pick_values.py:159-163`). A
> band over a set of identical values would admit everything. The real instruments are the
> user's own season and team selection — Jon's "not xyz" is a hand-written roster-quality
> filter, and a better one than any we could infer — plus the D-055 user-gain floor on the
> receiving side, which standing offers inherit for free by reusing the injector loop.
> **If Q-023 is ever built, this trade-off is what to revisit.**

---

## 7. What deliberately does NOT change

Stated so a reviewer can confirm the blast radius by reading rather than by diffing.

| Area | Why it is untouched |
|---|---|
| **Trade generation** (`trade_service.py` v2, `trade_optimizer.py` v3) | a standing offer never enters enumeration, scoring, or the mutual-gain gate. It is an *injection*, downstream of generation, exactly like an exact mirror. |
| **Pick pricing** (`pick_values.py`, `tier_config.json`) | §6. No new tier math, no new constant, no change to `pick_pool_value` or the decay knobs. Q-023 stays unbuilt. |
| **Match / notification pipeline** | a standing-offer card is an ordinary card. Swiping it writes an ordinary `trade_decisions` row and reaches `check_for_match` on the ordinary path. There is no "standing offer accepted" state and no new notification type. |
| **`_LIKES_YOU_CAP`** | stays 3. The split is a knob (`standing_offer_inject_cap`), not a second constant. |
| **Recipient UI** | no new component. The flare "They're interested" pill (`mobile/src/components/TradeCard.tsx:375-378`) is reused unchanged; the only addition is one text line. |
| **Web and extension clients** | mobile only in v1; the flag gates the routes. |
| **`docs/cross-client-invariants.md`** | no shared constant, color, or enum crosses clients. The tier/position hexes this feature renders are already-governed data encodings it merely reuses. |

---

## 8. Failure modes this shape accepts

| Mode | Consequence | Why it is acceptable |
|---|---|---|
| A standing offer outlives the intent that created it | a user gets a card for a player the sender no longer wants to move | 30-day cap + revoke in Matches + roster containment kills it the moment the player leaves the roster |
| Standing offers crowd out organic mirrors | the deck's strongest signal (an exact package someone actually liked) loses slots | mirrors are evaluated **first**, and standing offers have a hard ceiling that is deploy-free reversible to 0 |
| Fan-out grows superlinearly if the feature catches on | more candidates than slots, silently | the drop counter makes it measurable; the ceiling makes it bounded. This is the specific reason the cap is a reservation and not just "cap 3" |
| Exclusion is inferable by two league-mates comparing notes | a private negative leaks socially | inherent to any targeted broadcast; no payload change prevents it. Named in the PRD rather than claimed away |

---

## 9. Decision to record

Recorded **item-scoped as D-362-1** (the D-306-1 / D-320-2 convention). Written
2026-08-19 as "next DECISIONS.md id D-093", but `origin/main` took D-093–D-097
before this branch shipped, so the decision lives here rather than colliding.

> ## D-362-1 — A Standing Offer Is Bounded by Round and by the User's Own Team Selection, Not by a Pick-Value Band
>
> **Status:** accepted · **Date:** 2026-08-19 · **Item:** #362
>
> The design lab proposed binding a standing offer to the originating pick's value ±1
> ladder tier. Rejected: the premise is false in the shipped pricing model. Every first in
> a league carries identical engine value — `pick_pool_value` prices every league pick at
> the generic ladder's Mid rung of its round (upheld by D-090; per-slot pricing is unbuilt
> as Q-023) and D-079 set round-1 year decay to 1.00. A band over identical values admits
> everything. The offer is therefore bounded by round (parsed from the pick id), by the
> seasons and teams the user selects, and by the pre-existing D-055 user-gain floor on the
> receiving side. Revisit only if Q-023 is built.
