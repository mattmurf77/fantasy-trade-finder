# FB-418 backend follow-up — PRD: a sent offer is a LIKE on the idea routes

> **Status:** built 2026-09-03 on `feat/fb418-backend-like-exclusion` (from
> `f13dd96c`). Not merged, not deployed.
> **Ruling:** [D-178](../../../../living-memory/DECISIONS.md) — operator, verbatim:
> *"needs a backend follow up. This should be treated the same as any other
> 'liked' trade."*
> **Spec:** [`followup-backend-like-exclusion.md`](followup-backend-like-exclusion.md) ·
> **Scope block:** [`backend-scope.md`](backend-scope.md) ·
> **Mobile half (shipped separately):** [`prd.md`](prd.md)

## 1. The problem, in one line

Dismiss an idea and the server remembers; **send** it and the server offers it
again on the very next fetch, looking new.

## 2. Why that happened

| Fact | Where (this branch) |
|---|---|
| "Send this offer" writes a **real like row** — `record_decision(decision="like")` then `save_trade_decision(..., decision="like")`. A sent offer is not a lesser signal; it is the row a swipe-right writes. | `backend/server.py:13353`, `:13371` |
| The **model deck** excludes every package the caller has an un-retracted awaiting like on in this league — keyed `(frozenset(give), frozenset(receive))`, **no time window** (G6 R4 #336) — plus `pending`/`accepted` matches. Failure is non-fatal: log + empty set. | `_load_presentment_exclusions`, `backend/server.py:5811`; built per job at `:5983` |
| `POST /api/trades/asset-ideas` applied only the D-067 **dismiss** cooldown plus untouchables / not-interested — no like exclusion at all. | route at `backend/server.py:12143` |
| `POST /api/trades/fair-packages` applied **neither**. | route at `backend/server.py:12471` |

## 3. Requirements

**R-1 — Both idea routes drop ideas the caller has already offered.**
`POST /api/trades/asset-ideas` and `POST /api/trades/fair-packages` build the
exclusion set through `_load_presentment_exclusions(user_id, league_id)` — the
same function, not a copy — and omit every idea whose
`(frozenset(give_player_ids), frozenset(receive_player_ids))` key is in it.

**R-2 — The key is built in ONE place, in the caller's orientation.**
`give` = what the user sends, `receive` = what the user gets, exactly as
`_load_presentment_exclusions` builds `t["my_give"]` / `t["my_receive"]`. The
construction lives in `trade_service.presentment_key` and every consulting site
calls it. A surface that flipped the orientation would fail to match a liked
package against its own re-offer — silently, and only for users who had
actually sent something.

**R-3 — The filter runs before any cap, so a capped list still fills.**
An excluded idea yields its slot to the next-best candidate. It must not be
possible to send three offers and get 17 ideas where 20 were promised.

**R-4 — Group counts stay honest.** The excluded idea is absent from the
payload itself, so anything the client derives from the payload — the shop's
mode chip counts, its `1 / X` pager counter — is correct without any client
change.

**R-5 — Nothing about the like semantics is re-implemented.** No time window;
retracted likes regenerate (Q-G6-2 / #318 — `load_awaiting_trades` already
drops them); matured matches already subtracted; `declined` matches still
regenerate. All four are inherited by calling the existing loader.

**R-6 — A broken load is non-fatal.** `_load_presentment_exclusions` logs and
returns an empty set on any exception; the routes then serve the **unfiltered**
answer rather than erroring or returning nothing.

**R-7 — The dismiss cooldown is unchanged.** D-067 still excludes on
`asset-ideas` on its own, with no like row and no exclusion set, and still
binds through the live service the swipe route mutates in memory. D-178 widens
the predicate; it must not replace it.

**R-8 — No new flag, no new knob, no schema change.** The routes reuse the
existing `trade.presentment_rules` gate (see §5.5). Off ⇒ both routes are
byte-identical to pre-D-178.

**R-9 — The now-false mobile comment is corrected in the same commit.**
`mobile/src/components/ShopOffersBody.tsx` claimed there is *no* server-side
memory for a queued like. It says the opposite now. The three `#418` tag sites
`check-shop-deck.js` k8 requires are untouched.

## 4. Contract

**No request-shape change on either route. No new field, no new enum, no new
error.** The only observable delta is that the answer can contain fewer ideas:
one already-offered package is absent rather than re-offered. Concretely:

- `asset-ideas` — an idea missing from `groups.upgrade` / `groups.lateral` /
  `groups.downgrade`. The **"Already queued"** re-✓ path stops being reachable
  from a fresh shop window: the idea is gone rather than re-offered and
  idempotently re-queued. `queueCalcTrade`'s `already_queued` branch stays for
  the in-session and deck paths and is unchanged.
- `fair-packages` — an idea missing from the flat `ideas` list. Because the
  filter precedes the #189 strict/relaxed choice, a sweep whose *entire* strict
  band was already offered now correctly falls through to the widened band
  instead of returning a list of trades the user has already sent.
- Both — gated on `trade.presentment_rules`; a failed load serves unfiltered.

`docs/api-reference.md` carries this on both rows.

## 5. The four design points, answered

### 5.1 Where the filter runs, relative to the cap

**Found.** Both surfaces cap:

- `asset-ideas` — `asset_ideas_group_cap` (6), applied per group at
  `trade_service.py:5848` (`out[group] = sorted(chosen, key=key)[:cap]`).
- `fair-packages` — `fair_packages_cap` (20), applied to the flat list at
  `trade_service.py:6058`.

The existing D-067 dismiss filter already sits at emission, *before* the
`asset-ideas` cap, precisely so "a dismissed variant yields its slot to the
next-best instead of silently consuming it".

**Chosen.** The exclusion set is threaded into both generator impls as an
`exclusion_keys` kwarg and applied at the same emission points, never to the
returned list. In `_generate_asset_ideas_impl` the existing `_dismissed`
predicate was widened (and renamed `_suppressed`) so all three of its sites —
the `_emit` backstop (`:5540`), the `_emit_best` variant filter (`:5591`) and
the downgrade-combo skip (`:5713`) — cover likes with no second copy of the
rule. In `_generate_fair_packages_impl` the check is the first statement of
`_emit` (`:5992`), before the dedupe key is even claimed.

This is the one **deviation from the written spec**, which proposed a
`_drop_liked_ideas(ideas, keys)` helper in `server.py` applied to the return
values. That helper would necessarily run after the cap. Sharing is preserved
by construction rather than by co-location: one loader
(`server._load_presentment_exclusions`) and one key builder
(`trade_service.presentment_key:2185`) serve the deck, both idea routes and
the D-067 dismiss path. Pinned by `test_the_cap_still_fills_after_an_exclusion`
and `test_route_group_cap_refills_after_an_exclusion` — both RED on the
unfixed routes.

### 5.2 Group counts stay honest

Nothing renders an excluded idea because nothing returns one. The mobile shop
derives `visibleByMode`, its chip counts and its `1 / X` counter from the
payload, so removing the idea server-side removes it from all three at once.
No client change was needed or made; the session-suppression set #418 added
becomes a bridge between a send and the next fetch — the role it already plays
for a dismiss — instead of the only memory.

### 5.3 Cost of the extra loads

`_load_presentment_exclusions` costs two `engine.connect()` blocks:

- `load_awaiting_trades` (`database.py:8582`) — three indexed reads, each
  `LIMIT 500` (likes, matches, one fan-out `league_members` fetch for the
  leagues touched), plus JSON decoding of those rows.
- `load_matches_for_exclusion` (`database.py:8537`) — one read on the
  `ix_trade_matches_user_{a,b}_league` composite indexes, status-filtered.

`asset-ideas` already performs `service.get_rankings`, `load_asset_preferences`,
`load_league_preference`, `_owned_picks_available` and `_inject_owned_picks`
(itself a `draft_picks` read) on every call, and then runs a several-hundred-
evaluation sweep per league-mate. Two more indexed reads are a small fraction of
that, and the deck job — a much heavier path — has paid the same cost per job
since the G6 wave.

**Decision: one per-request build, no cache.** A cache is the wrong trade here
even at shop-open frequency: the whole point is that the set must reflect a
like the user recorded *seconds* ago, from possibly another surface or device.
A stale entry would re-offer exactly the package this ruling removes — the bug,
reintroduced as an optimization. If the read ever does show up in latency
traces, the honest fix is a narrower loader (the awaiting loader also resolves
counterparty names, which this caller discards), not a TTL.

### 5.4 Inherited, not re-implemented

| Property | Inherited from | Pinned by |
|---|---|---|
| No time window | `_load_presentment_exclusions` (R4 #336 removed the 7-day `since_days`) | the loader is called, never re-written |
| Retracted likes regenerate | `load_awaiting_trades`' `retracted_at IS NULL` filter (#318) | `test_a_retracted_like_comes_back`, `test_route_returns_a_retracted_like` |
| Matured matches subtracted; `pending`/`accepted` block, `declined` does not | `load_awaiting_trades` + `load_matches_for_exclusion` (Q-G6-2) | `test_a_live_match_excludes_the_same_way` |
| Non-fatal failure ⇒ serve unfiltered | the loader's own `try/except` | `test_a_broken_exclusion_load_serves_unfiltered`, `test_route_serves_unfiltered_when_the_load_breaks` |

One inherited limitation worth stating: `load_awaiting_trades` **drops** a like
whose counterparty it cannot recover from the `league_members` roster snapshot.
A stale member snapshot therefore weakens the exclusion (the idea is re-offered)
rather than breaking anything — fail-open, consistent with the rest of this
path. The tests persist that snapshot through the production writer
(`upsert_league_members`) precisely so they do not accidentally pass on a shape
production never produces.

### 5.5 Orientation, and the flag

**Orientation** is R-2 above: `presentment_key(give, receive)` in the caller's
frame, one constructor, used by the loader's consumers and by both new sites.

**The flag** is the second deviation from the written spec, which said "no
flag". None was **added**; the existing `trade.presentment_rules` gate is
reused, mirroring the deck's own call site at `server.py:5983`. Two reasons:

1. The ruling is a *parity* ruling — "treated the same as any other 'liked'
   trade". The deck's treatment of a liked trade is gated on that flag, so the
   same treatment carries the same switch.
2. `docs/config-reference.md` states that this flag is **"R4's only switch"**.
   Adding ungated R4-derived exclusion to two more routes would have made that
   sentence false without anyone noticing until they tried to kill R4.

The cost, stated plainly: killing `trade.presentment_rules` for an unrelated
reason (an R1/R2/R3/R5 misbehavior) would also drop the shop's like memory.
Both flag-off paths are pinned by tests, and the config-reference blast-radius
paragraph now names both routes.

## 6. Code-walk proof

**Send → next `asset-ideas` fetch → excluded.**

1. The shop's ✓ posts `POST /api/trades/queue`. The route reconstructs the card
   and records the like in memory (`server.py:13353`,
   `record_decision(decision="like")`), then persists it —
   `save_trade_decision(..., decision="like")`, `server.py:13371` — writing a
   `trade_decisions` row with `retracted_at` NULL.
2. The user re-opens the shop window; the client refetches
   `POST /api/trades/asset-ideas` (`server.py:12143`).
3. After the preference loads, the route builds the exclusion set:
   `server.py:12352-12362` — `if FLAGS.trade_presentment_rules:
   exclusion_keys = _load_presentment_exclusions(g_user_id, league_id)`.
4. `_load_presentment_exclusions` (`server.py:5811`) calls
   `load_awaiting_trades(user_id)` (`database.py:8582`), which selects
   `decision == "like" AND retracted_at IS NULL`, skips keys already matured
   into a match, resolves the counterparty from `league_members`, and returns
   the row written in step 1. The route's loop keeps this league's rows and
   adds `(frozenset(my_give), frozenset(my_receive))`; `load_matches_for_exclusion`
   (`database.py:8537`) adds `pending`/`accepted` matches.
5. The set is passed down: `server.py:12403`,
   `exclusion_keys = exclusion_keys or None` →
   `TradeService.generate_asset_ideas` → `_generate_asset_ideas_impl`.
6. Inside, `_excl_keys` is bound and `_suppressed` (`trade_service.py:5526`)
   returns True for any key in the dismiss set **or** the exclusion set.
7. Every candidate passes `_suppressed` before it can occupy a slot — the
   `_emit` backstop (`:5540`), the `_emit_best` variant filter (`:5591`), the
   downgrade-combo skip (`:5713`). The sent package returns early and never
   reaches `strict`/`relaxed`.
8. The group cap is applied afterwards (`:5848`), to the post-filter list, so
   the group refills to `asset_ideas_group_cap` from the next-best candidates.
9. The route serializes `groups` from what the generator returned
   (`server.py`, `_idea_row` over `groups.items()`): the sent idea is absent
   from the payload, and therefore from every count the client derives.

**Send → next `fair-packages` sweep → excluded.**

1. Same step 1 (the pushed fair deck's ✓ and the shop's ✓ are the same route;
   a deck swipe-like via `/api/trades/swipe` writes the same row).
2. Find a Trade on a filled canvas posts `POST /api/trades/fair-packages`
   (`server.py:12471`).
3. After owned-pick injection the route builds the same set with the same call
   under the same flag: `server.py:12604-12609`.
4. It is passed at `server.py:12623` into
   `generate_fair_packages` → `_generate_fair_packages_impl`.
5. `_emit`'s first statement (`trade_service.py:5992`) is
   `if presentment_key(give_anchor, recv_ids) in _excl_keys: return` — before
   the `seen` dedupe claim, before the strict/relaxed split.
6. `chosen = strict or relaxed` and the `fair_packages_cap` cut
   (`trade_service.py:6056-6058`) therefore operate on a post-filter list: the
   flat list still fills to the cap, and a sweep whose whole strict band was
   already offered correctly falls through to the widened #189 band.

## 7. Evidence — red-proof table

Baseline = the two production files at `f13dd96c` (`git checkout --` on
`backend/server.py` + `backend/trade_service.py`, tests kept). "Sabotage" = the
fix in place with one targeted clause broken, restored immediately after.

| # | Test | File | Proves | RED against |
|---|---|---|---|---|
| 1 | `test_route_excludes_a_sent_offer` | test_asset_ideas.py | (a) sent ⇒ absent, band + tier, other groups untouched | **baseline** |
| 2 | `test_route_returns_a_retracted_like` | test_asset_ideas.py | (b) retraction restores it | **baseline** |
| 3 | `test_route_group_cap_refills_after_an_exclusion` | test_asset_ideas.py | (d) cap refills, does not shrink | **baseline** |
| 4 | `test_a_sent_offer_is_gone_from_the_next_sweep` | test_fair_packages.py | (a) on the second route | **baseline** |
| 5 | `test_a_retracted_like_comes_back` | test_fair_packages.py | (b) on the second route | **baseline** |
| 6 | `test_the_cap_still_fills_after_an_exclusion` | test_fair_packages.py | (d) on the second route | **baseline** |
| 7 | `test_a_live_match_excludes_the_same_way` | test_fair_packages.py | the set is the DECK's set — a `pending` match excludes with no like row | **baseline** |
| 8 | `test_route_dismiss_behaviour_is_unchanged` | test_asset_ideas.py | (c) D-067 still excludes on its own | **sabotage S3** — `_suppressed` narrowed to `key in _excl_keys` only ⇒ 4 dismiss tests fail |
| 9 | `test_route_serves_unfiltered_when_the_load_breaks` | test_asset_ideas.py | (e) non-fatal ⇒ unfiltered, not 500 | **sabotage S2** — load hoisted out of the loader's try/except ⇒ `RuntimeError` escapes |
| 10 | `test_a_broken_exclusion_load_serves_unfiltered` | test_fair_packages.py | (e) on the second route | **sabotage S2** |
| 11 | `test_route_flag_off_is_byte_identical` | test_asset_ideas.py | R-8: `trade.presentment_rules` off ⇒ pre-D-178 behavior | **sabotage S1** — flag guard removed ⇒ excludes anyway |
| 12 | `test_flag_off_is_byte_identical` | test_fair_packages.py | R-8 on the second route | **sabotage S1** |

Tests 8–12 are posture/regression bars and **cannot** be red on the baseline —
the baseline is the behavior they pin. They are proven by sabotaging the fix
instead, which is the only honest red for a bar of that kind; each carries its
sabotage in its own docstring.

Fixture honesty: every like is written by the shipped `POST /api/trades/queue`
route, every retraction by the shipped `POST /api/trades/awaiting/dismiss`
(#318), and the `league_members` snapshot is persisted through
`upsert_league_members` — the production writer, called at `session_init` —
because without it `load_awaiting_trades` cannot resolve the counterparty and
drops the like, in tests and in prod alike.

**Suite:** `python3 -m pytest backend/tests -q` → **4599 passed, 1 skipped**
(415 s). Collection: 4600 on this branch vs **4588** on the baseline — exactly
the 12 tests added, none lost. (The 4565 figure quoted in the build brief is
stale; the baseline was re-measured by collecting with the test files reverted.)
Mobile: `npm run test:shop-deck` → **153 PASS**; `npx tsc --noEmit` → clean.

## 8. Out of scope

- **The D-067 dismiss cooldown on `fair-packages`.** That route consults
  neither cooldown today; D-178 rules on likes only. Widening dismisses to this
  surface is a separate ruling and is not made here.
- **Adding a cooldown window to the like exclusion.** Explicitly rejected by
  D-178: R4 (#336) removed exactly that window because an 8-day-old like still
  sitting in Awaiting legitimately regenerated the same card.
- **Any client change.** The mobile edit in this commit is a comment
  correction; no behavior, no test-id, no structural-suite delta.
- **Narrowing `load_awaiting_trades`** for this caller (it resolves counterparty
  names the exclusion set discards). Noted in §5.3 as the honest fix *if* the
  read ever shows up in traces; not done speculatively.
- **The prod volume read** the spec asks for — one `shop_opened` →
  `visibleIdeas.length` distribution before and after. That is an operator/
  analytics task after the deploy, not part of this build.

## 9. Test plan (what a reviewer should re-run)

1. `python3 -m pytest backend/tests/test_asset_ideas.py backend/tests/test_fair_packages.py -q`
   → 101 passed.
2. `python3 -m pytest backend/tests -q` → 4599 passed, 1 skipped.
3. `git checkout -- backend/server.py backend/trade_service.py` (tests kept),
   re-run step 1 → the 7 baseline-red tests in §7 fail. Restore.
4. `cd mobile && npm run test:shop-deck` → 153 PASS; `npx tsc --noEmit` → clean.
5. Operator, post-deploy: the 3-step TestFlight checklist in
   [`backend-scope.md`](backend-scope.md) §3.
