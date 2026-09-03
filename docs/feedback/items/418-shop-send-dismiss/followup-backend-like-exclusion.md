# FB-418 follow-up (backend) — a sent offer is a LIKE, so it stops being offered

> **Status:** specced 2026-09-03, **BUILT 2026-09-03** on branch
> `feat/fb418-backend-like-exclusion` (from `f13dd96c`) — not merged, not deployed.
> Build docs: [`backend-prd.md`](backend-prd.md) (requirements, the four design
> answers, code-walk proof, red-proof table) · [`backend-scope.md`](backend-scope.md)
> (filled scope block; §6 records two deviations from this spec — the filter moved
> INTO the generators so the caps still fill, and the existing
> `trade.presentment_rules` gate is reused).
> Operator ruling on the #418 QA-B B-1 cost.
> **Ruling (verbatim):** *"needs a backend follow up. This should be treated the same as any
> other 'liked' trade."* → [D-178](../../../living-memory/DECISIONS.md)
> **Parent item:** [#418](prd.md) (mobile half, shipped in the same run — the tile leaves the
> pager for the session). This half removes the idea from the SERVER's answer.

## The gap, in one line

The deck already refuses to re-offer a package you liked. The shop and the anchored sweep do
not, because they never build the exclusion set.

## What is already true (verified 2026-09-03, `main` @ `ca5fac46`)

| Fact | Where |
|---|---|
| "Send this offer" writes a **real like row** — `save_trade_decision(..., decision="like")` plus `record_trade_signal` and `trade_service.record_decision(decision="like")`. A sent offer is not a lesser signal; it is the same row a swipe-right writes. | `backend/server.py:13309`, `:13319`, `:13327-13333` |
| The **model deck** excludes every package the caller has an un-retracted awaiting like on in this league, keyed `(frozenset(give), frozenset(receive))`, with **no time window** (G6 R4 [#336] — the 7-day window was the bug), plus `pending`/`accepted` matches. Failure is non-fatal: log + empty set. | `_load_presentment_exclusions`, `backend/server.py:5811-5838`; wired at `:5983` → `:6292` |
| `POST /api/trades/asset-ideas` (the shop window) applies the **D-067 dismiss cooldown** (passes only) and untouchables / not-interested — and **no like exclusion at all**. | `backend/server.py:12214-12216`, `:12310-12319` |
| `POST /api/trades/fair-packages` (the anchored Find-a-Trade sweep, #417's deck) applies **neither** — zero references to `exclusion_keys` in the route. | `backend/server.py:12442-12600` |

So: dismiss the idea and the server remembers; **send** the idea and the server offers it
again on the next fetch. That asymmetry is what the operator's ruling closes.

## The change

Build the same set the deck builds, in both idea routes, and drop matching ideas.

1. `asset-ideas`: call `_load_presentment_exclusions(g_user_id, league_id)` alongside the
   existing preference loads and filter the generated groups by the
   `(frozenset(give_player_ids), frozenset(receive_player_ids))` key, caller orientation —
   identical construction to `:5829-5833`, so the two surfaces cannot drift.
2. `fair-packages`: the same call and the same filter, applied after
   `generate_fair_packages` returns. Its docstring already frames it as *"asset-ideas' gate
   set applied to a fixed left-hand side"*, and this is one of those gates.
3. Prefer one shared helper over two copies of the filter — a `_drop_liked_ideas(ideas,
   exclusion_keys)` next to the loader, called by both routes.

**Deliberately inherited, not re-implemented:** no time window; retracted likes regenerate
(Q-G6-2 / #318, because `load_awaiting_trades` already drops them); matured matches already
subtracted; non-fatal failure posture (a broken load serves the unfiltered list rather than
an error).

## Consequences to state before building

- The mobile session-suppression set added by #418 becomes a **bridge**, not the only filter
  — exactly the role it plays for a dismiss today. Its code comment already says so and will
  need its one sentence corrected when this ships (`ShopOffersBody.tsx:321-327`).
- The **"Already queued"** re-✓ path stops being reachable from a fresh window: the idea is
  gone rather than re-offered and idempotently re-queued. `queueCalcTrade`'s
  `already_queued` branch stays for the in-session and deck paths.
- A sent-then-**retracted** like correctly comes back. There is no retraction UI on the shop
  surface; retraction lives in Awaiting.
- Shop counts shrink for users with many outstanding likes. Worth one prod read of the
  `shop_opened` → `visibleIdeas.length` distribution before and after.

## Gates when built (full gates — this is an API contract change) — DONE

- Scope block → [`backend-scope.md`](backend-scope.md). §1 (b) existing events named; §2 no
  schema, no NEW flag (the existing `trade.presentment_rules` is reused — deviation, §6), no
  `model_config` key; §4 `docs/api-reference.md` updated for both routes' response semantics,
  plus `docs/config-reference.md` for the flag's widened reach.
- pytest: 12 route tests across both surfaces. 7 proven RED against the unfixed routes; the
  5 posture/regression bars (dismiss unchanged, non-fatal load, flag-off byte-identity)
  proven red by targeted sabotage of the fix, since they cannot be red on the baseline.
  Table in [`backend-prd.md`](backend-prd.md) §7. Full suite 4599 passed / 1 skipped.
- The one mobile edit is the comment correction below — no behavior change, so no `check-*.js`
  delta (`check-shop-deck` stays 153 PASS, `tsc --noEmit` clean). Operator TestFlight check:
  send an offer, reopen the window, the idea is gone (3 steps in `backend-scope.md` §3).
