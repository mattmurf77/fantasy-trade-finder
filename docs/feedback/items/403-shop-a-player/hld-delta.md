# HLD delta — #403 "Shop a player"

> A **delta against [`docs/architecture.md`](../../../architecture.md)**, not a
> rewrite. What changes in the shape of the system, which components are
> touched, how data flows through them, and the decisions taken with the
> alternatives rejected. Exact interfaces live in
> [`lld-delta.md`](lld-delta.md); numbered requirements in [`prd.md`](prd.md).

**Tree verified against:** `origin/main` @ `6e94ff71`. Every `file:line` below
was read in the current tree. Anything not in the tree is marked **NEW**.

## Contents

- [1. The shape of the change](#1-the-shape-of-the-change)
- [2. Components touched](#2-components-touched)
- [3. Decisions, with alternatives rejected](#3-decisions-with-alternatives-rejected)
- [4. Data flow](#4-data-flow)
- [5. What does not change](#5-what-does-not-change)
- [6. Architecture-doc impact](#6-architecture-doc-impact)

---

## 1. The shape of the change

**#403 is a front door and a browser for an engine that already ships.** It is
not a new generator, and a PRD that specs one is the expensive failure mode
this document exists to prevent.

`POST /api/trades/asset-ideas` (`backend/server.py:12024`, flag
`trade.asset_ideas` — **`true` in `config/features.json`, live**) already takes
one pinned asset and returns three groups — `upgrade` / `lateral` /
`downgrade` — built by `TradeService._generate_asset_ideas_impl`
(`backend/trade_service.py:4982`). Mapped onto the report:

| Report's words | Shipped group | Status |
|---|---|---|
| "trade options to **tier up**" | `upgrade` | exists |
| "**tier down**" | `downgrade` | exists |
| "**position specific swaps of similar value**" | `lateral`, hard-locked to the pin's own position (#198) | exists, but the position set is not user-selectable |

So the architecture delta is small and has exactly four parts:

1. **One optional request field** on an existing route (`swap_positions`),
   changing one predicate in one search branch. No new endpoint, no schema,
   no `model_config` key.
2. **One new client screen** — a horizontally paged card browser — which is a
   new *consumer* of an existing route, not a new tier.
3. **Two existing write routes gain a second caller.** The shop card's like
   calls `POST /api/trades/queue`; its dismiss calls `POST /api/trades/swipe`.
   Both already accept exactly the payload an asset idea can produce.
4. **One additive field on a write route** (`record_elo` on
   `/api/trades/queue`) to honor the operator's Q-A ruling in full — see
   §3 D-5, which is the one genuinely contested piece.

Nothing about the module graph in `docs/architecture.md` changes. `server.py`
still routes; `trade_service.py` still generates; `ranking_service.py` still
owns the board; the mobile client still consumes JSON over `api.post`.

## 2. Components touched

| Layer | Component | Touched how | New? |
|---|---|---|---|
| Backend route | `backend/server.py` → `asset_trade_ideas` (`:12024`) | parse + validate `swap_positions`, pass through | edit |
| Backend route | `backend/server.py` → `queue_trade_for_opponent` (`:13029`) | optional `record_elo` skips two write calls (D-5) | edit |
| Backend route | `backend/server.py` → `swipe_trade` (`:12527`) | **untouched** — #403 is a new *caller* of the existing FB-46 path | — |
| Backend service | `backend/trade_service.py` → `_generate_asset_ideas_impl` (`:4982`) | new kwarg; the give/receive lateral predicates split (`:5205`, `:5291`) | edit |
| Backend ranking | `backend/ranking_service.py` | **untouched** | — |
| Backend schema | `backend/database.py` | **untouched** — no table, column or `model_config` key | — |
| Analytics | `backend/analytics_taxonomy.py`, `backend/analytics_queries.py` | 4 new client events registered; `NON_INTENT_EVENTS` unchanged with reason recorded | edit |
| Mobile screen | `mobile/src/screens/ShopAssetScreen.tsx` | the pushed shop surface | **NEW** |
| Mobile component | `mobile/src/components/ShopCardPager.tsx` | the paged card browser + `1 / X` counter | **NEW** |
| Mobile component | `mobile/src/components/ShopPositionPicker.tsx` | W2 only; may fold into the screen | **NEW** |
| Mobile nav | `mobile/src/navigation/RootNav.tsx` | one `RootStackParamList` line (`:139` neighborhood) + one `<Stack.Screen>` | edit |
| Mobile API | `mobile/src/api/trades.ts` | `fetchAssetIdeas` body type (`:386-392`); `queueTradeForOpponent` optional arg (`:572`) | edit |
| Mobile host | `mobile/src/screens/MatchesScreen.tsx` | one `PlayerMenuAction` row in `menuActionsFor` (`:1568`) | edit |
| Mobile util | `mobile/src/utils/ideaToCard.ts` | **imported, never edited** — it already mints the id #403 needs | — |
| Mobile util | `mobile/src/utils/queueCalcTrade.ts` | one optional arg threaded through | edit |
| Test | `mobile/tests/check-shop-deck.js` + `mobile/package.json` script | structural guard | **NEW** |
| Test | `backend/tests/test_asset_ideas.py`, `backend/tests/test_shop_queue_elo.py` | unit coverage | edit / **NEW** |
| Web / extension | — | **not touched.** `git grep -n "asset-ideas" -- web extension` returns nothing; the web app has no asset-ideas surface. | — |

## 3. Decisions, with alternatives rejected

### D-1 — The shop surface is a root-stack **pushed screen**, not a sheet and not an inline block

**Decision.** `ShopAssetScreen`, registered unconditionally in
`RootNav.tsx` (the house rule: *the flag gates the entry point, not the route*,
stated at `RootNav.tsx:762-766` for `Receipts`), pushed with
`navigate('ShopAsset', {assetId, assetName, leagueId, source})`.

**Why.**

- **Gesture isolation is total and free.** A native-stack push puts the shop
  surface in its own view controller; `TradesScreen`'s deck pan
  (`TradesScreen.tsx:7926` neighborhood) is not in the same interactive tree.
  Combined with D-2 (no `Gesture.Pan` at all) the collision risk in
  `plan.md` R-1 stops existing rather than being mitigated.
- **`FeedbackFAB` #188 compliance is satisfied rather than exempted.** A
  root-stack push mounts `<FeedbackFAB activeScreen="ShopAsset"
  aboveTabBar={false} />`. A sheet would fall under the modal exception — i.e.
  the operator would lose the feedback affordance on the exact surface they
  are being asked to evaluate.
- **The content does not fit a sheet.** A full `TradeCard` (two columns, player
  rows, fairness meter — `docs/design/components.md` § Cards) plus a mode
  selector, a position picker, a `1 / X` counter and a decision row is a
  screen's worth of vertical space. A sheet that tall is a screen with a
  grabber on it.
- **Any host is one line.** Q-F stops being an architecture question and
  becomes a per-host `navigate()` call.

**Alternatives rejected.**

| Alternative | Rejected because |
|---|---|
| Bottom sheet (`PlayerContextMenu` construction) | Loses the FeedbackFAB (modal exception), cannot hold a full TradeCard, and its own swipe-down dismiss competes with vertical content scroll. |
| Inline block on `TradesScreen`, below the pin board | Puts a horizontal pager inside the screen that owns the like/pass pan — `plan.md` R-1 at full severity — and requires editing the contended 8,758-line file. Would have needed spike S-1. |
| Extend `AssetIdeasPanel` in place | `plan.md` §4.4, upheld: it is #402's file and it is pinned by `check-single-pin-actions.js` assertions 9a/9b (the #317 `pinIdeaResumed` contract) and coupled to `FeaturedTradeWindow`'s `featuredKey` / in-window inert-row protocol. |

### D-2 — The pager is a `FlatList horizontal pagingEnabled`, **not** a `Gesture.Pan`

**Decision.** One `FlatList`, `horizontal`, `pagingEnabled`, `snapToInterval`
= card width, `1 / X` driven off `onMomentumScrollEnd`.

**Why this is a decision and not an implementation detail.** `plan.md` §4.2
proposed a `Gesture.Pan()` pager and rated the resulting arbitration question
**High**, requiring spike S-1. A `FlatList` is a `ScrollView`: there is no
`Gesture.Pan` in #403's tree at all, so `react-native-gesture-handler`
arbitration never enters the picture and **S-1 is not needed**. This also
directly honors the report — *"different from the current ship to like
feature"* — because horizontal motion navigates and never decides.

`MEMORY.md` records a prior incident where five reviewers agreed on a wrong RN
navigation side-effect claim. The design here is chosen so that **no framework
side-effect claim has to be true** for it to work: paging is a scroll, and the
absence of a competing pan is mechanically checkable (`check-shop-deck.js`
A-7) rather than argued.

**Rejected:** a `Gesture.Pan` pager (needs an explicit
`Gesture.Exclusive` / `blocksExternalGesture` contract and a spike);
`react-native-pager-view` (a new dependency — `living-memory/DEPENDENCIES.md`
gate — for something core RN already does).

### D-3 — `swap_positions` **replaces** the #198 predicate for `lateral` only, and the two bands are split to make that possible

**Decision.** Per Q-D. The shipped gate at `trade_service.py:5205` is a single
predicate covering **both** the lateral band and the upgrade band
(`… and vc >= lo`). Replacing `_same_pos` in place would therefore widen
`upgrade` too, which Q-D explicitly forbids. The predicate is split by band —
upgrade keeps `_same_pos` verbatim, lateral consults the user's set. Full
interface, mirror, and a boundary-by-boundary equivalence proof:
`lld-delta.md` §3.2.

**Why replace and not filter.** `lateral` is *already* hard-locked to the pin's
own position (`pin_pos` at `:5091-5092`, `_same_pos` at `:5094-5095`, gate at
`:5205` give / `:5291` receive). A filter applied over that group's results
returns the empty set for every position other than the pin's — a control that
always shows "nothing found". This is `plan.md` R-4 and it is the single
easiest way to ship a dead feature.

**Interaction with #360 Avoiding.** An avoided position still wins. `avoid_ok`
is a **receive-pool exclusion at source** (`trade_service.py:5199`), so an
avoided asset never enters `pool` and `swap_positions` never sees it. A user
selecting a position they also avoid gets an **honest empty group**, never a
silent override — D-360-3(b) preserved without a line of new code. The client
must not *offer* avoided positions in the picker; the server must not depend
on the client doing so. (`trade.avoid_positions` is `false` today, so this is
latent, not live.)

**Rejected:** widening `upgrade`/`downgrade` too (not asked for; "Upgrade at
WR" would stop meaning what it says); relaxing rather than replacing (#198 is
explicit at `trade_service.py:5030-5037` that the position constraint is a
semantic, never a gate knob — the #189 refill widens the fairness band only).

### D-4 — **No** server-side flag gate on `swap_positions` — with a caveat

`plan.md` §9 left this contract call to the Author. **Decision: no
`trade.shop_asset` check inside `asset_trade_ideas`.**

**Why.** The gates `calc.merged_layout` puts on `/api/trades/queue`
(`_calc_queue_denied`, `server.py:12894-12905`) and `/api/trades/fair-packages`
exist because those routes are **the entire feature** — the ✓ cell and the
canvas sweep have no meaning without it, and the flag must be a complete kill
switch including the server. `swap_positions` is not a feature; it is one
optional parameter narrowing one search branch of a route that is already live
and already reachable. Gating it would add a second flag read to a hot
synchronous route and buy nothing: absent the field the route is byte-identical,
and present-with-flag-off the worst case is a *narrower* result set from an
already-public endpoint. No data is exposed that `direction`/`opponent_user_id`
do not already expose.

**The caveat the Planner did not raise.** The kill switch for #403 is
`trade.shop_asset` **on the client**. That is complete for the *surface* but
not for a client already in the field: a shipped build with the flag cached on
could keep sending `swap_positions` between a flag flip and the next
`revalidateFlags`. The blast radius of that is "one user briefly sees
cross-position laterals", which is acceptable. **If the operator wants a
server-side kill for the parameter, say so** — it is four lines
(`if not is_enabled("trade.shop_asset"): swap_positions = None`) and it is
strictly a policy call, not an engineering one. Recorded in `prd.md` §Open as
a non-blocking note rather than silently decided.

### D-5 — The like is `POST /api/trades/queue`, and the "no Elo" half of Q-A needs one additive field

**Decision.** Per Q-A the like maps to `POST /api/trades/queue` — idempotent
per (user, league, opponent, give SET, receive SET) via `_calc_queue_trade_id`
(`server.py:12907`), eligible for the counterparty's likes-you injection, and
refusing honestly with a named `reason` rather than half-recording. #403 reuses
`utils/queueCalcTrade.ts` verbatim so the refusal copy cannot drift.

**The contradiction.** Q-A also says the like "must not move the user's Elo
board." **`/api/trades/queue` moves it** — `service.record_trade_signal(…
decision="like", fit_mult=fit_mult)` at `server.py:13196` and
`save_trade_swipes(k_factor=_rs_c("trade_k_like") * fit_mult, …)` at `:13213`.
`plan.md`'s Q-A table presented queue as the option that *doesn't*, which is
most likely what the ruling was made against (`reconciliation-log.md` V-1).

**Resolution.** Honor both halves with the smallest possible change: an
additive `record_elo: bool = true` body field. Absent ⇒ every existing caller
is byte-identical. `false` ⇒ skip `record_trade_signal` and `save_trade_swipes`;
everything else — the mirror predicate, the idempotency probe,
`save_trade_decision`, the `trade_proposed` event, likes-you eligibility — runs
unchanged, because the offer is recorded in `trade_decisions` and that is the
table `find_live_trade_like` and the likes-you injector read.

**This is on the bright line** (`CLAUDE.md` §Feature gates: "a change touching
schema, **API contracts**, feature-flag surfaces, or analytics events is not a
quick fix"). `prd.md` §Open O-1 asks for the confirming yes, and specs the
zero-change fallback (drop `record_elo`, accept the Elo movement) so the build
is not blocked either way.

**Alternatives rejected.**

| Alternative | Rejected because |
|---|---|
| Pass `fit_mult = 0.0`, keeping both writes | Provably exact (`lld-delta.md` §5.3 worked example) and the bake-off's `elo_freeze_mult` proves K=0 is an exercised path — but it writes `swipe_decisions` rows that mean nothing. `swipe_decisions` **is** the Elo ledger; a K=0 row is a lie about what happened, and a future analyst counting swipes would count them. |
| A new `/api/trades/shop-queue` route | A second route re-implementing the six-branch mirror predicate (`_calc_queue_mirror_reason`, `server.py:12929`) that would drift from it. `docs/coding-guidelines.md` §2. |
| A pure local bookmark | Builds a fourth "like" concept the app then has to reconcile, and contradicts the ruling's "queue it as a **real offer**". |
| Ignore the "no Elo" half | Silently dropping half an operator ruling. |

### D-6 — The dismiss is a **deferred** `POST /api/trades/swipe` `decision:'pass'`, with undo cancelling the write

**Decision.** Per Q-B: full deck-pass semantics — Elo movement at `trade_k_pass`
and the permanent dismiss-cooldown — **held for `UNDO_HOLD_MS` (5000 ms)**
before the POST fires. Undo clears the timer; nothing was ever written.

**Why this is the answer and not a compromise.** The brief framed undo as the
hardest part of the spec, on the premise that Elo is path-dependent and that no
undo exists. Both premises are wrong (`reconciliation-log.md` V-2, V-3), and
the repo has already solved this problem three times:

| Shipped precedent | Where |
|---|---|
| Deck pass undo — the POST is *held*, `undoPass()` drops it | `TradesScreen.tsx:2163-2171` (the design note), `:2392-2440` (`undoPass`), `:4896-4903` (the hold), `:4988-4997` (the toast) |
| Match dismiss undo — same shape, with the design note stating the reasoning outright: *"the archive POST is DELAYED for UNDO_HOLD_MS rather than reversed (there is no un-dismiss endpoint)"* | `MatchesScreen.tsx:406-411`, `:495-509` |
| Awaiting-row dismiss undo | `MatchesScreen.tsx:530-552` |

**The honesty property this buys.** The brief's hard requirement — *the UI copy
must accurately describe what undo actually reverses* — is satisfied
unconditionally, because **nothing is reversed**. The dismiss has not happened
yet. "Dismissed · Undo" is literally true for the whole 5-second window, and
after it expires the affordance is gone. No hedged copy, no partial undo, no
"cooldown lifted but the rating stands."

**Server-side identity needs no new code.** `utils/ideaToCard.ts:56` already
mints `asset-idea:${assetIdeaKey(idea)}` for an idea with no server `trade_id`,
and `assetIdeaKey` (`:27`) is `counterparty.give_ids-receive_ids` — stable, and
exactly the context `_reconstruct_swipe_card` (FB-46, `server.py:12493`) needs.
The pass then runs the shipped path verbatim: `record_trade_signal` at
`server.py:12608`, the D-067 cooldown bind at `:12640-12653`, the
`trade_decisions` row, `save_trade_swipes` at `trade_k_pass`.

**Alternatives rejected.**

| Alternative | Rejected because |
|---|---|
| Write immediately; undo reverses the cooldown only, leaving the rating | The brief's own worst case. Requires copy that cannot say "undone", requires a new un-dismiss endpoint, and leaves the board permanently taught by a browsing gesture the user retracted. |
| Write immediately; snapshot the pre-state and restore | Technically possible (`_compute_elo` replays an ordered log, `ranking_service.py:1528-1538`, so it would be exact) — but it needs a delete path into `swipe_decisions` + `trade_decisions`, an account of intervening writes, and a cache invalidation. All of it to reach a state the deferred write reaches by doing nothing. |
| Session-local "next card please" with no server write | Contradicts Q-B outright. |

### D-7 — Two independently shippable waves

**W1 — front door + browser.** Entry point, screen, pager, `1 / X`, like,
dismiss + undo. **Zero backend diff except D-5's `record_elo`.**
**W2 — position selection.** `swap_positions` on route + service, the picker.

W1 alone answers most of the report. If scope is cut, cut W2. (`plan.md` §4.5,
upheld.)

## 4. Data flow

```
  MatchesScreen · PlayerContextMenu row "Shop this player"   [flag trade.shop_asset]
        │  navigate('ShopAsset', {assetId, assetName, leagueId, source})
        ▼
  ShopAssetScreen  ── mode: tier_up | tier_down | same_value
        │           ── positions: Set<Position>   (W2, same_value only)
        │
        │  fetchAssetIdeas({league_id, asset_id, direction:'give',
        │                   swap_positions?})            api/trades.ts:386
        ▼
  POST /api/trades/asset-ideas                          server.py:12024
        │  flag trade.asset_ideas (404 when off)              :12069
        │  validate swap_positions → 400 invalid_position     NEW
        ▼
  TradeService._generate_asset_ideas_impl(..., swap_positions)
        │                                            trade_service.py:4982
        │  receive pool ← avoid_ok (#360 exclusion at source)      :5199
        │  band split: upgrade keeps _same_pos  |  lateral consults the set
        │                                          :5205 (give) :5291 (recv)
        ▼
  {groups: {upgrade[], lateral[], downgrade[]}}
        │
        ▼
  ShopAssetScreen: flatten the ONE selected group → ideas[]
        │  ideaToCard(idea, leagueId)              utils/ideaToCard.ts:52
        ▼
  ShopCardPager  (FlatList horizontal pagingEnabled)
        │  header: TickLabel  "3 / 7"          ← onMomentumScrollEnd
        │  body:   <TradeCard hideMatchStrength />
        │  footer: [ Dismiss ]        [ Like ]
        │
        ├── Like ─────► queueCalcTrade({..., screen:'ShopAsset', recordElo:false})
        │                    └► POST /api/trades/queue        server.py:13027
        │                         gate calc.merged_layout           :12894
        │                         mirror predicate                  :12929
        │                         idempotency probe                 :13159
        │                         save_trade_decision → likes-you eligible
        │                         [record_elo:false ⇒ skip :13196 + :13213]
        │
        └── Dismiss ──► pendingDismissRef = {card, timer: 5000ms}
                        toast "Dismissed · Undo"
                          ├── Undo tapped  → clearTimeout, restore index. NO POST.
                          └── window ends / newer dismiss / unmount → flush
                                └► POST /api/trades/swipe {trade_id:'asset-idea:…',
                                     decision:'pass', give/receive/target ctx}
                                        _reconstruct_swipe_card (FB-46)  :12493
                                        record_trade_signal 'pass'       :12608
                                        D-067 cooldown bind          :12640-12653
                                        save_trade_decision + save_trade_swipes
```

**The one-way property worth naming.** Every arrow above is an existing route
with an existing contract. The only new *shapes* are `swap_positions` (request)
and `record_elo` (request). No new response field, no new table, no new
enum crossing a client boundary.

## 5. What does not change

Stated explicitly because "did not change" is the claim the OFF-state test
verifies.

- **`AssetIdeasPanel`, `FeaturedTradeWindow`, `TradeCard`, `ideaToCard`,
  `check-single-pin-actions.js`** — #402's files. #403 *imports* `ideaToCard`
  and `TradeCard`; it edits neither.
- **`TradesScreen.tsx`'s single-pin state machine** — `preSinglePinSnapshotRef`
  (#288), `singlePinDeckActive` keyed on `deck.length` (#298 assertion 7),
  `pinIdeaResumed` set only inside `handleSelectIdea` (#317 9a/9b),
  the `!singlePinDeckActive` gate on `FeaturedTradeWindow` (#241), and
  `advance()`'s disposition chain (#298 1–8). #403 does not open the file in
  W1 or W2. `npm run test:single-pin-actions` stays green **and unmodified**;
  needing to edit it is a scope escalation back to the operator.
- **The deck's like/pass gesture** (`TradesScreen.tsx:7926` neighborhood).
- **`RankingService`** — no math, no knob, no K factor.
- **Schema** — no table, no column, no `model_config` key.
  `asset_ideas_lateral_band` (0.10) and `asset_ideas_group_cap` (6) are reused
  as-is (`database.py:2473-2474`).
- **`upgrade` and `downgrade` semantics** under any `swap_positions`.
- **Web and extension.**

## 6. Architecture-doc impact

**`docs/architecture.md`: n/a.** No module is added, removed, or re-wired; no
data-flow edge changes direction. A new screen consuming an existing route is
inside the shape the document already describes.

**`living-memory/HLD.md`: n/a**, same reason.

**`living-memory/LLD.md`: updated** — `swap_positions` establishes a
convention (*a caller-supplied position set replaces a #198-style semantic
predicate for one band only, and is validated closed against
`POSITIONS`*) that the next positional parameter should follow.

**`docs/api-reference.md`: updated** — three entries: `/api/trades/asset-ideas`
(`:234`, the `swap_positions` field), `/api/trades/queue` (`:239`, the
`record_elo` field, if O-1 lands), and a note on `/api/trades/swipe` (`:238`)
that asset-idea cards reach it under an `asset-idea:<key>` id via FB-46.

Row-by-row docs table: [`scope.md`](scope.md) §4.
