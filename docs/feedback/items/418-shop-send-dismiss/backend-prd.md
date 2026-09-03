# FB-418 backend follow-up — PRD: a sent offer is a LIKE on the idea routes

> **Status:** built 2026-09-03 on `feat/fb418-backend-like-exclusion` (from
> `f13dd96c`); **QA-resolution pass 2026-09-03** on
> `claude/new-user-feedback-06dabd` (from `77a4e33b`) closing QA-A A-1…A-5 and
> QA-B B-1/B-2/B-3/B-5/B-6/B-8/C-4 — see §10. Not merged, not deployed.
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
An excluded idea yields its slot to the next-best candidate **where one
exists**: the cap truncates a post-filter list, so the group refills from the
candidates that remain and still empties when the excluded idea was the only
one (QA-A A-2 — the earlier absolute phrasing overstated this; the mechanism
is right, the claim was not). It must not be possible to send three offers and
get 17 ideas where 20 were promised **while candidates 18–20 exist**.

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

### Requirements added by the QA-resolution pass (2026-09-03)

**R-10 — Parity is FULL: the routes take the deck's whole like memory.**
(QA-B B-1.) R4 is windowless but `load_awaiting_trades` subtracts a like the
moment ANY `trade_matches` row exists — status-unfiltered
(`database.py:8623-8636`) — while `load_matches_for_exclusion` re-adds only
`pending`/`accepted` (`:8562`). A **`declined`** offer therefore sat in
neither set and returned to the shop immediately, while the deck went on
suppressing it for `like_days = 7.0` (`server.py:19198-19199`) through
`past_decision_keys`. Both idea routes now also consult that `like_days` LIKE
subset.

*Which of the deck's like memories are imported, exactly:*

| The deck consults | Imported here? | Why |
|---|---|---|
| R4 #336 — un-retracted awaiting likes in this league, windowless | **Yes**, since the first build | `_load_presentment_exclusions` |
| R4 #336 — `pending`/`accepted` matches, windowless | **Yes**, since the first build | same loader |
| `past_decision_keys` — the `like_days` = 7 LIKE subset | **Yes, new** | `TradeService.recent_like_keys()`, unioned inside the same loader. This is the arm that covers a **declined** offer, and also a like whose counterparty `load_awaiting_trades` cannot resolve from the roster snapshot (A-3) or that fell off its 500-row read (A-4) |
| `past_decision_keys` — the `pass_cooldown_days` DISMISS subset | Already there, by its own route (D-067), not through this loader | `_dismissed_decision_keys`; unchanged, and deliberately still NOT on `fair-packages` |

*Deliberately NOT imported:* nothing else exists to import — the deck's like
memory is exactly those three arms. Two properties are inherited rather than
improved, on purpose, because parity is the ruling: (a) the `like_days` subset
is a **session snapshot** loaded at `session_init`, so a like made in the
current session is not in it — it is covered by R4's windowless awaiting set
until a match row appears, and the `declined` case (which requires a
counterparty action) is picked up from the next session, exactly as on the
deck; (b) no in-memory bind is added on `POST /api/trades/queue` (the D-067
dismiss bind at `server.py:12905` has no like counterpart), because adding one
would make the shop suppress MORE than the deck — a divergence, not parity.
Beyond `like_days` a declined offer regenerates on both surfaces (Q-G6-2).

**Pass criteria:** `test_a_declined_offer_stays_suppressed_like_the_deck` in
both `test_asset_ideas.py` and `test_fair_packages.py` — each drives a real
`create_trade_match` + two `record_match_disposition` calls to status
`declined`, asserts `_load_presentment_exclusions(user, league) == set()` (R4
genuinely holds nothing), and then asserts the idea is still absent.

**R-11 — The exclusion is visible to the client and the operator.**
(QA-B C-4 — the root cause of B-2/B-3/B-6 and of B-7's "ships
unmeasurable".) `POST /api/trades/asset-ideas` returns two ADDITIVE top-level
fields, `excluded_count: int` and `excluded_by_group: {upgrade, lateral,
downgrade}` (one entry per key present in `groups`; `excluded_count` is their
sum). `POST /api/trades/fair-packages` returns `excluded_count: int`. Both
routes log one line per request naming the exclusion-set size and the drop
count.

Two properties are load-bearing and pinned:
- The counts are what the exclusion **actually dropped** — distinct
  `(give-set, receive-set)` keys, per group — never the size of the exclusion
  set, most of whose keys have nothing to do with this pin. Counting keys
  rather than calls makes a candidate re-evaluated at several sites count
  once, and only the D-178 arm is counted: a D-067 dismiss is a different
  story, and the copy the client branches on says *"you already offered
  this"*.
- They read **0** with the flag off. Stated plainly: **adding the fields is
  the one thing that is not byte-identical in the rollback state.** It was
  scoped so that every field a pre-D-178 client reads is unchanged, and the
  new ones are inert there — a client can only ever ADD an explanation the
  server actually caused, never invent one during a revert.

**Pass criteria:** `test_route_reports_what_the_exclusion_dropped`,
`test_excluded_counts_are_zero_with_the_flag_off` (asset-ideas) and
`test_the_sweep_reports_what_the_exclusion_dropped` (fair-packages). Each
seeds a second, unrelated like that can never be a candidate for the pin/
anchor, so a `len(exclusion_keys)` implementation is RED.

**R-12 — The slot-yielding pre-filters are pinned.**
(QA-A A-1.) `_emit_best`'s variant filter (`trade_service.py:5591`) and the
downgrade-combo skip (`:5713`) are what make R-3 true for every
`_emit_best`-served group, and no test bound them: narrowing both to
dismiss-only while keeping the `_emit` backstop left the entire suite green.
**Pass criteria:**
`test_an_excluded_variant_yields_its_slot_to_the_runner_up` — a group with two
viable variants (`([P,S1],[U])` and `([P,S2],[U])`) where excluding the best
must serve the SECOND; RED under exactly that mutation, where the group comes
back empty.

**R-13 — The client's honest-copy defects are closed with the new counts.**
(QA-B B-5, B-3, B-2, B-6.)
- **B-5:** `handleLike` invalidates the `['shop-ideas', leagueId, assetId]`
  rows after a queued ✓, with `refetchType: 'none'` — the open pager must not
  rebuild under the user's thumb (P-1), while the next mount refetches. Closes
  the 60-second window in which `staleTime` outlived the screen-scoped
  `suppressed` set and re-showed the sent idea.
- **B-3:** the Same-value auto-widen no longer fires when the server's raw
  zero is exclusion-caused (`excluded_by_group.lateral > 0`), so the shop's one
  honest-notice line can no longer assert *"Nothing at {pos}"* about a pool
  the user emptied himself.
- **B-2 / B-6:** the shop's unfiltered empty and the single-pin panel's empty
  say *"You have offered every … here"* instead of blaming the market — and
  **only** when the group/panel is EMPTY as the server sent it AND its
  exclusion count is > 0. A group that refilled to its cap reads exactly as it
  does today.

**Pass criteria:** `check-shop-deck` k10 (the invalidation, its query key and
`refetchType: 'none'`, inside the queued branch); `tsc --noEmit` clean; all
three copy branches unreachable without a non-zero server count, by
construction.

## 4. Contract

**No request-shape change on either route. No new enum, no new error.** The
observable deltas are two: the answer can contain fewer ideas (one
already-offered package is absent rather than re-offered), and — added by the
QA-resolution pass, R-11 — the answer SAYS how many it dropped. Concretely:

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
- **New, additive (R-11):** `asset-ideas` gains `excluded_count: int` and
  `excluded_by_group: {upgrade: int, lateral: int, downgrade: int}`;
  `fair-packages` gains `excluded_count: int`. Always present, 0 when the flag
  is off or nothing matched, and never the size of the exclusion set. **Does
  this break the flag-off byte-identity claim?** For every EXISTING field, no
  — that is exactly how it was scoped, and the two flag-off tests compare the
  whole payload and stay green. For the payload as a whole, yes, and stated
  rather than papered over: two fields a pre-D-178 client never reads are now
  present in both states, reading 0 in the rollback state. The alternative —
  omitting them when the flag is off — was rejected: a field that appears and
  disappears is a second, undocumented signal about the flag, and the client
  would have to treat "absent" and "0" identically anyway.

`docs/api-reference.md` carries all of this on both rows.

## 5. The four design points, answered

### 5.1 Where the filter runs, relative to the cap

**Found.** Both surfaces cap:

- `asset-ideas` — `asset_ideas_group_cap` (6), applied per group at
  `trade_service.py:5848` (`out[group] = sorted(chosen, key=key)[:cap]`).
- `fair-packages` — `fair_packages_cap` (20), applied to the flat list at
  `trade_service.py:6058`.

The existing D-067 dismiss filter already sits at emission, *before* the
`asset-ideas` cap, precisely so "a dismissed variant yields its slot to the
next-best instead of silently consuming it" — **where a next-best exists**.
QA-A A-2: the cap truncates a post-filter list, so it refills from the
candidates that remain; a group whose only idea was excluded still empties
(`test_route_excludes_a_sent_offer` asserts exactly that for `lateral`). The
mechanism is right; the absolute phrasing was not, here and in
`docs/api-reference.md`, and both are now stated as what the code does.

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

Three inherited limitations worth stating. All three are **fail-open** (they
weaken the exclusion, re-offering an idea — the pre-D-178 behaviour) and all
three are shared with the deck, which has lived with them since the G6 wave.
Since the QA-resolution pass the `like_days` subset (R-10) covers a recent
like through all three, because it is cut from `load_trade_decisions` and needs
neither the roster snapshot nor the awaiting read — but only for `like_days`,
so they still bite beyond a week.

1. **The roster snapshot (QA-A A-3, disclosed here from the first build,
   restated with its prod shape).** `load_awaiting_trades` **drops** a like
   whose counterparty it cannot recover from the `league_members` roster
   snapshot (`database.py:8704`, `if not partner_id: continue`). The tests
   write that snapshot **synchronously**; production writes it from a
   **best-effort background daemon** at `session_init` (`server.py:19577`,
   inside a `try/except … continuing`). A session whose daemon upsert failed
   therefore silently loses that half of the exclusion in a way the tests can
   never see. The tests persist the snapshot through the production writer
   (`upsert_league_members`) precisely so they do not accidentally pass on a
   shape production never produces — but same-writer is not same-timing, and
   the timing is the part that can fail in prod.
2. **The 500-row cross-league cap (QA-A A-4 — not disclosed anywhere before
   this pass).** `load_awaiting_trades` selects the **500 most recent likes
   across ALL leagues** (`database.py:8613`, `.order_by(created_at.desc())
   .limit(500)`, no `league_id` predicate), and `_load_presentment_exclusions`
   filters to one league only *afterwards* (`server.py:5827-5828`). A user with
   heavy like volume in other leagues can therefore have this league's older
   likes truncated out of the set, silently. Pre-existing, shared with the
   deck, not introduced by D-178, and fail-open.
3. **The `league_id` asymmetry (QA-A A-6).** `asset-ideas` takes
   `league_id = body.get("league_id") or g_league.league_id` with no
   `league_mismatch` guard, unlike `fair-packages` and `/api/trades/queue`. A
   foreign `league_id` cannot produce *unfiltered* ideas — the generator's
   `self._leagues.get(league_id)` misses and returns empty groups — so it is
   not a D-178 defect; noted because D-178 adds a consumer of that unvalidated
   value, and because the `like_days` subset it now also consults is
   session-league-scoped by construction.

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

**QA-resolution pass, 2026-09-03 — six more tests, four named mutations.**
Baseline for these is the *fixed* code at `77a4e33b`, since each pins behaviour
that commit did not have; every one carries its mutation in its own docstring
and every mutation was run.

| # | Test | File | Proves | RED against (verified) |
|---|---|---|---|---|
| 13 | `test_an_excluded_variant_yields_its_slot_to_the_runner_up` | test_asset_ideas.py | R-12 / QA-A A-1 — the `_emit_best` variant pre-filter and the downgrade-combo skip are load-bearing | **Q-B**: both narrowed to `self._dismissed_decision_keys`, the `_emit` backstop left intact → the upgrade group comes back EMPTY. **1 failed, 106 passed** — and *only* this test, which is the point: the mutation was invisible to the whole suite before |
| 14 | `test_a_declined_offer_stays_suppressed_like_the_deck` | test_asset_ideas.py | R-10 / QA-B B-1 on the shop route | **B-1-off**: the route drops `trade_service=` from its `_load_presentment_exclusions` call (the shipped `77a4e33b` behaviour) → the declined package is re-offered. **2 failed, 105 passed** (both routes' copies) |
| 15 | `test_a_declined_offer_stays_suppressed_like_the_deck` | test_fair_packages.py | R-10 on the anchored sweep | **B-1-off** (same run as #14) |
| 16 | `test_route_reports_what_the_exclusion_dropped` | test_asset_ideas.py | R-11 — counts are DROPS, per group, not set size | **set-size**: `excluded_count = len(exclusion_keys)` → the second, unrelated like inflates the count to 2. **2 failed, 105 passed** |
| 17 | `test_the_sweep_reports_what_the_exclusion_dropped` | test_fair_packages.py | R-11 on the second route, incl. flag-off 0 | **set-size** (same run as #16) |
| 18 | `test_excluded_counts_are_zero_with_the_flag_off` | test_asset_ideas.py | R-11 — the fields are inert in the rollback state | **flag-gate removed** (`if True:` at both new call sites) → the sent offer is counted with the flag off. **4 failed, 103 passed** (these two plus both pre-existing byte-identity bars) |

Mobile, same pass: `check-shop-deck` **k10** (R-13's invalidation, its query
key and `refetchType: 'none'`, inside the queued branch) is RED with the
`invalidateQueries` call deleted — `no invalidateQueries call in the queued
branch` — and green with it restored.

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
  analytics task after the deploy, not part of this build. QA-B B-7 corrects
  the event: `shop_opened`'s allowed props are `{asset_position, source,
  give_count}` and carry no idea count; the event that carries one is
  `shop_mode_selected {mode, n_ideas}`, which fires on a chip tap only and so
  never samples the default mode on open. Read it with that bias noted, or
  take the server-side answer the new `excluded_count` log line now gives.

### Named follow-ups from the QA pass — deliberately NOT built here

These are carried out of the QA reports so they are not lost, and each needs
either a separate surface or an operator ruling.

| id | What | Why not here |
|---|---|---|
| **QA-B B-4** | A fair sweep emptied by likes lands the pushed anchored deck on the never-searched card (*"Hit 'Find a Trade' to start"* on a page whose Find-a-Trade button #417 hides). The fix is the `trades.canvas-results.fair-zero` card the in-canvas host already has (`TradesScreen.tsx:7927`), lifted into the classic ladder above the never-searched fallback. | A **#417-surface** item on the classic deck ladder, pre-existing (audit-Q5) and owned by that item's files. D-178 makes it more reachable; it does not create it. |
| **QA-B B-7** | The client analytics prop: add `already_queued` to `calc_trade_queued`'s allow-set (`analytics_taxonomy.py:1550`) and emit the value `queueCalcTrade.ts` already holds, so `{queued: true, already_queued: true}` on `ShopAsset` falling to ~0 measures the fix from the client end. | A taxonomy change — the bright line says it is not a quick fix, and it is a separate one-commit client change. The server-side half of B-7 IS built: the `excluded_count` log line answers the same question from the other end. |
| **QA-B B-9** | The bake-off arm inconsistency: an R4-bypassed arm gets decks that may contain a package their shop window refuses to show. Worth a line in the experiment's own notes. | Not a code change; belongs to the experiment's notes, not this build. |
| **QA-B C-1** | A narrower awaiting loader for this caller (the current one resolves counterparty names and fans out `league_members` across every league the user has likes in, all of which the exclusion set discards), scoped against per-chip-change frequency rather than per-shop-open. | Performance work with no measured trigger. §5.3 already names it as the honest fix *if* the read shows up in traces; building it speculatively is the wrong order. |
| **QA-B C-3** | A re-send affordance. The exclusion is windowless for an awaiting like, so a user who genuinely wants to re-send (they nudged the partner in chat) has no path from the shop — the only route back is retracting in Awaiting, which throws the original offer away. C-3's own suggestion is a *"you already offered this — view in Awaiting"* tile in place of the dropped idea. | **Needs an operator ruling.** It changes what the shop shows for an excluded idea, and the alternative reading — that a sent offer should simply be gone — is what D-178 just ruled. Not a decision to make inside a QA-resolution pass. |

## 9. Test plan (what a reviewer should re-run)

1. `python3 -m pytest backend/tests/test_asset_ideas.py backend/tests/test_fair_packages.py -q`
   → **107 passed** (101 at the first build, +6 from the QA-resolution pass).
2. `python3 -m pytest backend/tests -q` → **4605 passed, 1 skipped**.
3. `git checkout f13dd96c -- backend/server.py backend/trade_service.py`
   (tests kept), re-run step 1 → the 7 baseline-red tests in §7 fail. Restore.
   The six added in the QA pass are proven by their own named mutations
   instead (§7's second table), because the code they pin did not exist at
   `f13dd96c`.
4. `cd mobile && npm run test:shop-deck` → **154 PASS** (153 + k10);
   `npx tsc --noEmit` → clean; `bash scripts/testid-lint.sh` → OK.
5. Operator, post-deploy: the TestFlight checklist in
   [`backend-scope.md`](backend-scope.md) §3.

## 10. What the QA-resolution pass changed (2026-09-03)

Both QA agents returned **PASS** with no blocking defect; this pass closes
their findings rather than fixing a break.

| Finding | Verdict | Where it landed |
|---|---|---|
| QA-A **A-1** (live mutant: the slot-yielding pre-filters are unpinned) | Closed | R-12; `test_an_excluded_variant_yields_its_slot_to_the_runner_up` |
| QA-A **A-2** (the cap claim is stated absolutely) | Closed | R-3, §5.1 and `docs/api-reference.md` softened to what the code does |
| QA-A **A-3** (roster snapshot written by a best-effort daemon in prod) | Closed | §5.4 item 1 — restated with its prod shape |
| QA-A **A-4** (500-row cross-league like cap, undisclosed) | Closed | §5.4 item 2 — first disclosure |
| QA-A **A-5** (mobile comment asserts the server half unconditionally) | Closed | `ShopOffersBody.tsx` — the claim is now flag-conditional and names the rollback state |
| QA-A **A-6** (`league_id` asymmetry) | Noted | §5.4 item 3 |
| QA-B **B-1** (a declined offer comes straight back) | **Closed — this was the ruling** | R-10 |
| QA-B **B-2 / B-3 / B-6** (empty-state copy blames the market; the widen fabricates a cause) | Closed | R-13, on the back of R-11's counts |
| QA-B **B-4** | Out of scope, named | §8 — a #417-surface item |
| QA-B **B-5** (60-second cache hole) | Closed | R-13; `check-shop-deck` k10 |
| QA-B **B-7** (ships unmeasurable) | Half closed | The server-side half is R-11's log line; the client `already_queued` prop is named in §8 |
| QA-B **B-8** (stale comment at the source of the two sets) | Closed | `server.py` session build — the sentence D-178 reversed is gone |
| QA-B **B-9**, **C-1**, **C-3** | Out of scope, named | §8 (C-3 needs an operator ruling) |
| QA-B **C-2** (counts shrink unexplained) | Partly addressed | The copy in R-13 explains the EMPTY case; the "3 already offered" line under the chip row is not built — it would need a design pass, and C-3's tile would subsume it |
| QA-B **C-4** (nothing says an exclusion happened) | **Closed** | R-11 — the root cause of B-2/B-3/B-6/B-7's server half |
| QA-B **§4** (flag coupling) | Decision kept, cost named | The single gate stays; bought down with the log line (R-11) and the runbook warning. Recorded in [`backend-scope.md`](backend-scope.md) §6 and D-178's consequences |
