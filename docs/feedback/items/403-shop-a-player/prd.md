# PRD — #403 "Shop a player"

> Numbered requirements, success criteria, out-of-scope, guardrails, and the
> full D-056 test plan. Architecture: [`hld-delta.md`](hld-delta.md).
> Interfaces: [`lld-delta.md`](lld-delta.md). Scope block: [`scope.md`](scope.md).
> Round history and operator rulings: [`reconciliation-log.md`](reconciliation-log.md).

**Tree verified against:** `origin/main` @ `6e94ff71`.
**Work-type path:** Feature. **Bright line** (`CLAUDE.md` §Feature gates): this
touches an API contract and analytics, so an express declaration would need an
explicit confirming yes. None declared — full gates apply.

## Contents

- [0. Read this first](#0-read-this-first)
- [1. Open questions needing an operator ruling](#1-open-questions-needing-an-operator-ruling)
- [2. Requirements](#2-requirements)
- [3. Success criteria](#3-success-criteria)
- [4. Out of scope](#4-out-of-scope)
- [5. Guardrails](#5-guardrails)
- [6. Test plan](#6-test-plan)
- [7. File ownership](#7-file-ownership)
- [8. Sequencing](#8-sequencing)

---

## 0. Read this first

**The engine already ships.** `POST /api/trades/asset-ideas`
(`backend/server.py:12024`, flag `trade.asset_ideas` = **`true`**) already
returns tier-up / tier-down / same-value-position-swap ideas for one pinned
player. #403 is **a front door and a browser**, plus one narrow parameter. Any
requirement below that reads like a new generator is a misreading; there isn't
one. `hld-delta.md` §1 carries the mapping.

**Why the operator could not see it.** `AssetIdeasPanel` is imported by exactly
one file (`mobile/src/screens/TradesScreen.tsx:107`) and renders only when
`trade.finder_targeting` + `trade.asset_ideas` are on **and exactly one finder
target is pinned**. #403 was filed from `TradeCalculator`, where the live
feature is invisible. That is the actual problem this item solves.

## 1. Open questions needing an operator ruling

Each has a **specced recommended default**, so the build is not blocked on any
of them. O-1 is the one that genuinely wants an answer before merge.

### O-1 — "The like must not move the Elo board" contradicts the route it was ruled onto. **Bright line.**

Q-A ruled the like maps to `POST /api/trades/queue` **and** that it "must not
move the user's Elo board". **`/api/trades/queue` moves the Elo board.** It
calls `service.record_trade_signal(… decision="like")` at
`backend/server.py:13196` and `save_trade_swipes(k_factor = trade_k_like ×
fit_mult)` at `:13213`. `docs/api-reference.md:239` says the same in prose.
`plan.md`'s Q-A table described queue as the option that *doesn't* — which is
almost certainly what the ruling was made against.

| Option | Cost | Effect |
|---|---|---|
| **(A) Recommended — add `record_elo: false`** (`lld-delta.md` §5.2) | ~6 lines of backend, additive, default = today. **An API contract change, so it needs a confirming yes.** | Both halves of Q-A honored. The offer is real, idempotent and visible; the board does not learn from browsing. |
| (B) Drop `record_elo`, accept the movement | **Zero** backend diff. | The like teaches the board at `trade_k_like` (8.0). Defensible — a ✓ on a specific package is as deliberate as the calculator's ✓, which already does this — but it is not what the ruling said. |

**The build proceeds on (A).** If the operator prefers (B), delete the
`record_elo` rows from `lld-delta.md` §5 and §10 and R-6 becomes "n/a — ruled".

### O-2 — W1's only entry point is a long-press on the Matches screen

`TradesScreen.tsx` is #402's and contended, so #403 does not open it. The
consequence, stated plainly rather than buried: **in W1, "Shop a player" is
reachable only by long-pressing a player on Matches.** That is weak
discoverability for a feature whose headline problem is discoverability.
Options: accept it and take the deck mount in a follow-up; or serialize #403
behind #402 so W1 can add the deck row. Recommended default: **accept**, and
ship the deck row as a four-line patch handed to #402's agent
(`lld-delta.md` §4.4).

### O-3 — The shop dismiss moves Elo more often than the live deck pass does

`feedback.decline_reasons` is **`true`**, so the deck's ✕ routes to
`/api/trades/pass-reason`, where `pass_reason_elo_suppression` (default `1.0`)
writes Elo **only** on a `value_giving` answer. #403's dismiss goes through
`/api/trades/swipe`, which writes it unconditionally. Specced as Q-B ruled.
Recommended default: **accept the asymmetry** — a shop dismiss is a deliberate
per-card judgment with no reason UI to condition on. Non-blocking.

### O-4 — Spike S-2 (cross-position lateral yield)

`plan.md` S-2 asks whether a typical WR pin actually produces non-empty RB/TE
laterals once the ±10% band and the #108 gain gate are applied, or whether the
picker mostly shows "nothing found". Recommended: **run it before W2's picker
UI, not before W1** — W1 does not depend on it. ~30 min against the fixtures in
`backend/tests/test_asset_ideas.py`. **Spike S-1 (gesture isolation) is not
needed** — the design removes the pan entirely (`hld-delta.md` §3 D-2).

## 2. Requirements

Wave in brackets. Every requirement names its mechanical pass criterion.

### Entry and surface

**R-1 [W1] — A flag-gated entry point launches the shop surface for one player.**
A `PlayerMenuAction` row labeled **"Shop this player"** appears in
`PlayerContextMenu` when `trade.shop_asset` **and** `trade.asset_ideas` are
both on. Tapping it pushes `ShopAsset` with `{assetId, assetName, leagueId,
source}`. With either flag off the row is **not pushed into the actions
array** — the menu maps an identical list.
*Pass:* `check-shop-deck.js` A-5 · TestFlight steps 1, 8.

**R-2 [W1] — The shop surface is a root-stack pushed screen with
`gestureEnabled: false`.** Registered unconditionally (the flag gates the entry
point, not the route — `RootNav.tsx:762-766`). It mounts
`<FeedbackFAB activeScreen="ShopAsset" aboveTabBar={false} />` (#188).
`gestureEnabled: false` because iOS's interactive pop is a left-edge horizontal
drag that would otherwise intercept a page-back.
*Pass:* `check-shop-deck.js` A-9 · TestFlight step 4.

**R-3 [W1] — Three modes, single-select, one of them always active.**
`tier_up` → server group `upgrade`; `tier_down` → `downgrade`; `same_value` →
`lateral`. The mapping is **one exported constant** (`SHOP_MODE_GROUP` in
`mobile/src/utils/shopMode.ts`, zero runtime imports) so it can be executed and
asserted rather than pattern-matched. Default mode on open: `tier_up`.
*Pass:* `check-shop-deck.js` A-12 (executes the constant).

### The browser

**R-4 [W1] — Horizontal navigation between cards is non-destructive, and it is
not the deck's gesture.** Swiping left/right moves between the selected group's
ideas and changes nothing else. Implemented as a `FlatList horizontal
pagingEnabled`; **no `Gesture.Pan`, no `PanResponder`, no
`react-native-gesture-handler` import** in either new file. Reaching the end
does not consume, dispose of, or advance past anything.
*Pass:* `check-shop-deck.js` A-7 · TestFlight steps 3, 9.

**R-5 [W1] — A `1 / X` counter tracks the pager and cannot lie.**
`X` is the count of the exact list the pager renders (locally dismissed cards
excluded); the counter's expression and the pager's `data` prop derive from the
**same identifier**. Rendered as a `label`-type `TickLabel` in chalk-dim —
**not flare** (`design-system.md` § Ice/Flare division of labor).
*Pass:* `check-shop-deck.js` A-8 · TestFlight step 3.

### Decisions

**R-6 [W1] — Like queues a real offer.** The ✓ calls
`utils/queueCalcTrade.ts` → `POST /api/trades/queue` with the card's
`counterparty_user_id` / `give_player_ids` / `receive_player_ids`. It is
idempotent per (user, league, opponent, give SET, receive SET); a
`queued: false` refusal renders the shipped per-reason line from
`queueRefusalLine` (`queueCalcTrade.ts:31-49`), never a generic failure. No new
analytics event — `calc_trade_queued` with `screen: 'ShopAsset'`.
*Pass:* TestFlight steps 5, 6 · `check-shop-deck.js` A-3.

**R-7 [W1, pending O-1] — The like does not move the user's Elo board.**
The client sends `record_elo: false`; the route skips `record_trade_signal` and
`save_trade_swipes` while still writing the `trade_decisions` row that makes
the offer visible to the counterparty. Every existing caller that omits the key
is byte-identical.
*Pass:* `test_shop_queue_elo.py::test_queue_record_elo_false_writes_no_swipe`
and `::test_queue_record_elo_default_is_todays_behavior`.

**R-8 [W1] — Dismiss carries full deck-pass semantics.** Elo at `trade_k_pass`
and the permanent dismiss-cooldown, via `POST /api/trades/swipe`
`decision: 'pass'` with the card context and the `asset-idea:<key>` id that
`ideaToCard` already mints. Once committed, that package is not re-served
(D-067 binds the cooldown to every live service immediately,
`server.py:12640-12653`).
*Pass:* `check-shop-deck.js` A-3 · TestFlight steps 10, 12.

**R-9 [W1] — Undo, and the copy is true.** The dismiss POST is **held** for
`UNDO_HOLD_MS` (5000 ms). A "Dismissed · Undo" toast with the same `holdMs`
offers the take-back; tapping Undo clears the timer and **the request is never
sent**, so nothing needs reversing and the copy needs no caveat. At most one
pending dismiss: a second dismiss, a mode change, a refetch, navigation away or
unmount flushes the pending one first. Leaving the screen commits — a
disposition is never silently lost.
*Pass:* `check-shop-deck.js` A-4 · TestFlight steps 11, 12, 13.

### Position selection

**R-10 [W2] — The user picks the positions offered back, on `same_value` only.**
A multi-select chip row over `{QB, RB, WR, TE}` appears **only** in
`same_value` mode. The selection is sent as `swap_positions: string[]`. An
empty selection is the shipped #198 behavior and says so in a hint line.
Positions the user is **avoiding** (#360) are not offered.
*Pass:* `test_asset_ideas.py::test_avoided_position_beats_swap_selection` ·
TestFlight step 14.

**R-11 [W2] — `swap_positions` REPLACES the same-position predicate for
`lateral`, and touches nothing else.** It never filters over `lateral`'s
results — `lateral` is already hard-locked to the pin's position
(`trade_service.py:5205`, `:5291`), so a filter returns empty for every
position but the pin's. `upgrade` and `downgrade` are byte-identical under
every value of the field. Absent / `null` / `[]` ⇒ byte-identical to today.
An avoided position beats a selected one, producing an honest empty group and
never a silent override.
*Pass:* `test_swap_positions_absent_is_identical`,
`test_swap_positions_present_changes_lateral`,
`test_swap_positions_does_not_widen_upgrade_or_downgrade`,
`test_relaxed_refill_never_widens_positions`.

**R-12 [W2] — Invalid positions are a 400, not a silent empty.** Domain is
exactly `{QB, RB, WR, TE}` (`server.py:18609` `VALID_POSITIONS`); `"PICK"` is
rejected with the reason recorded in `lld-delta.md` §2.2. `" rb "` normalizes
to `RB` and succeeds.
*Pass:* `test_invalid_position_is_400` (parametrized, including the
must-succeed `[" rb "]` leg).

### Copy, look, hygiene

**R-13 — The group vocabulary is "Tier up" / "Tier down" / "Same value".**
Chosen from the operator's own words in both #403 and #402
(`reconciliation-log.md` § arbitration). **Provisional and open to attack in
the critique round.** "Tier up" / "Tier down" reuse the shipped
`TRADE_INTENT_LABEL` constant (`TradeDnaSheet.tsx:218-220`) rather than fresh
string literals, so the two items cannot diverge the way "Win-now moves" /
"Team-fit moves" once did. **#402 inherits this trio.**
*Pass:* `check-shop-deck.js` A-13 (the three literals appear exactly once each,
and the two tier labels are read from the shared constant).

**R-14 — Chalkline, no exceptions.** No emoji, no gradients, no
blur/glassmorphism, no Inter/Roboto/system stack, no radius > 8px except true
pills. **Ice** on the active mode chip and the Like button (ice = what you can
do); **flare nowhere** on this surface — the `1 / X` counter is chalk-dim
`label`, not a flare highlight. Position chips reuse `PositionChip`/`posColor`,
which are data encodings governed by `docs/cross-client-invariants.md` and are
never restyled.
*Pass:* `check-shop-deck.js` A-10 · code-walk proof §6.3.

**R-15 — Empty states are honest.** A group with zero ideas renders named copy
("No same-value ideas for {name} right now."), plus a second line naming the
position selection when one is active. Never a fabricated card, never an
endless spinner. With `trade.asset_ideas` off, the entry point does not render
at all.
*Pass:* TestFlight steps 7, 15.

**R-16 — `docs/glossary.md` records BOTH senses of "shop".** One entry naming
(a) **Shopping** = `trade_away_positions`, the league-level positional
preference in the Chasing / Shopping / Avoiding trio (`glossary.md:118`,
`:172`), and (b) **Shop a player** = the #403 asset-level surface — each
pointing at its own mechanism, so the collision is documented rather than
latent. Per Q-G.
*Pass:* ship-gate doc review (`scope.md` §4).

**R-17 — Flag OFF is byte-identical, in the source, not merely gated.**
`trade.shop_asset: false` ships. `swap_positions` and `record_elo` keys are
**omitted** from request bodies (not sent as `undefined`), no entry-point row
is pushed, the screen is never navigated to, and `AssetIdeasPanel`,
`FeaturedTradeWindow`, `TradeCard`, `ideaToCard` and the single-pin state
machine are not edited at all.
*Pass:* `check-shop-deck.js` A-5, A-6 · `test_swap_positions_absent_is_identical`
· `test_queue_record_elo_default_is_todays_behavior` · the ship-gate diff check
(§7) · TestFlight steps 1, 2.

**R-18 — No regression to the single-pin surface.**
`npm run test:single-pin-actions` stays green **and the file stays
unmodified**. Needing to edit it is a scope escalation back to the operator
(#241 / #288 / #298 / #317).
*Pass:* CI + the ship-gate diff check.

## 3. Success criteria

The feature is done when all of these hold on the pushed sha:

1. Flag off: `git diff origin/main` shows no change to any #402-owned file, and
   a full app pass finds no visible difference anywhere (TestFlight §A).
2. Flag on: the operator can launch the surface for one player, page through
   every idea in each of the three modes with the counter tracking, like one
   and see it appear in "Awaiting them", dismiss one and see it not come back,
   and undo a dismiss and see it come back — TestFlight §B, all steps pass.
3. Every requirement R-1…R-18 maps to at least one green automated assertion or
   a passed TestFlight step (the mapping is inline above and in §6.5).
4. CI green: `pytest backend/tests`, `npx tsc --noEmit`, the
   `mobile/tests/check-*.js` loop, `mobile/scripts/testid-lint.sh`.
5. `living-memory/TEST_LEDGER.md` names what ran and what it proved.
6. Every new behavioral test has been **observed red** under its named sabotage
   before being counted (§6.4).

## 4. Out of scope

| Not doing | Why |
|---|---|
| `direction: "receive"` ("what would he cost me?") | Q-C, Author call: "shop him around" is give-side, and all three of the report's options read as *what do I get for him*. One prop away later. |
| A tile grid presentation | Q-E: the report's `1/X`, left/right paging and per-card decision pair only cohere on the card reading. |
| A new generator, endpoint, or scoring path | The three groups already ship, gates and all (#108 / #141 / #163 / #360, pick injection, `opponent_user_id` scoping, the #189 relaxed refill). `docs/coding-guidelines.md` §2. |
| Widening `upgrade` / `downgrade` by position | Q-D. "Upgrade at WR" would stop meaning what it says. |
| Fixing the disabled ✓ in `FeaturedTradeWindow` | Real bug — `InLeagueCalculator` is mounted there without `onLikeTrade`, so the ✓ renders disabled (`FeaturedTradeWindow.tsx:78-87`, `InLeagueCalculator.tsx:1157`). It is on #402's surface. **Flag it, don't fix it** (`docs/coding-guidelines.md` §3). |
| Any edit to `TradesScreen.tsx` | #402 owns it. The deck entry-point row is supplied as a patch. |
| A reason UI on dismiss | The report asked for a plain dismiss button. `feedback.decline_reasons` is the deck's mechanism, not this surface's. |
| Web / extension | No asset-ideas surface exists there (`git grep -n "asset-ideas" -- web extension` → nothing). |
| An un-dismiss endpoint | Not needed: the undo cancels a write that has not happened. |

## 5. Guardrails

1. **Never open `mobile/src/screens/TradesScreen.tsx`.** 8,758 lines, #402's,
   and the home of five load-bearing invariants (#241 / #288 / #298 / #317 /
   the deck pan).
2. **Never edit `mobile/tests/check-single-pin-actions.js`.** Escalate instead.
3. **Import `ideaToCard` / `assetIdeaKey`; never re-implement the id.** A
   second identity function means a re-dismiss writes two rows.
4. **The predicate split is not optional.** Substituting `_lateral_pos_ok` for
   `_same_pos` in place widens `upgrade`. `lld-delta.md` §3.2.
5. **Register analytics events in the same commit as the emitter.**
   Unregistered props are silently dropped behind a 200.
6. **Never send `swap_positions` or `record_elo` as `undefined` or `[]`.**
   Omit the key.
7. **Do not add a `model_config` knob.** None is proposed; the band
   (`asset_ideas_lateral_band` 0.10) and cap (`asset_ideas_group_cap` 6) are
   reused as-is.
8. **Do not cite `mockups/polish-lab-2026-08/asset-ideas-layout*.html` as
   current behavior.** Mockups are never shipped code (`mockups/CLAUDE.md`).
9. **A worked example is a claim.** Every numeric example in these docs was
   recomputed against its own formula; anything added must be too.
10. **`npm ci` in a worktree.** Never symlink the main checkout's
    `mobile/node_modules` — it goes stale and produces phantom `tsc` errors.

## 6. Test plan

**D-056: Maestro and the simulator are retired.** No flow authoring, no flow
execution, no `screens/` captures. Evidence is: pytest + structural
`check-*.js` for anything mechanically checkable; a written **code-walk proof**
where a capture would have gone; and a **manual TestFlight checklist** for the
operator, which is the only runtime net mobile gets.

### 6.1 Backend unit tests (pytest)

`backend/tests/test_asset_ideas.py` (extend) and
`backend/tests/test_shop_queue_elo.py` (**NEW**). Every row names the sabotage
that makes it red; **no test asserts a hardcoded expected value that the
sabotage could satisfy.**

| # | Test | Asserts | Sabotage that makes it fail |
|---|---|---|---|
| **T-B1** | `test_swap_positions_absent_is_identical` | Three live calls — no kwarg, `swap_positions=None`, `swap_positions=[]` — are **deep-equal on all three groups**. No expected literal is written down, so it cannot be satisfied by hardcoding. | Delete `if not _swap: return _same_pos(pid)` from `_lateral_pos_ok` (an empty set then admits every position). |
| **T-B2** | `test_swap_positions_present_changes_lateral` | **The two-sided partner of T-B1.** For a WR pin with a cross-position band candidate in the fixture, `swap_positions=["RB"]`: `lateral` is (a) non-empty, (b) **disjoint** from the baseline `lateral`'s receive id sets, and (c) every receive headliner has position `RB`. | Make `_lateral_pos_ok` ignore `_swap` and always call `_same_pos`. T-B1 still passes; this one goes red — which is the point of the pair. |
| **T-B3** | `test_swap_positions_does_not_widen_upgrade_or_downgrade` | For `swap_positions` ∈ `[None, ["RB"], ["RB","TE"], ["QB","RB","WR","TE"]]`, `groups["upgrade"]` and `groups["downgrade"]` are deep-equal to the `None` baseline. | Use `_lateral_pos_ok` in the **upgrade** conjunct of the split gate — the exact mistake `lld-delta.md` §3.2 warns about. Nothing else catches it. |
| **T-B4** | `test_invalid_position_is_400` (parametrized, route level) | `["XX"]`, `[""]`, `["PICK"]`, `[1]`, `"RB"` (bare string), `True` → **400** with `error` ∈ `{invalid_position, swap_positions must be an array}`. **And** `[" rb "]` → **200** with RB-positioned laterals. | (i) Replace validation with `_normalize_avoid_positions`-style silent dropping → the 400 legs fail. (ii) Reject everything unconditionally → the `[" rb "]` leg fails. Two-sided by construction. |
| **T-B5** | `test_avoided_position_beats_swap_selection` | `avoid=["RB"], swap=["RB"]` ⇒ `lateral == []`. `avoid=["RB"], swap=["RB","TE"]` ⇒ `lateral` non-empty **and** contains no RB on the receive side. Two-sided: the empty leg alone would pass a build that returns empty always. | Move `avoid_ok` out of pool construction into a post-filter `_lateral_pos_ok` can bypass, or `or`-in the swap set. |
| **T-B6** | `test_relaxed_refill_never_widens_positions` | Force the strict band empty so the #189 refill fires (`relaxed: True`) with `swap=["RB"]`; every relaxed lateral's receive headliner is still RB. | Apply `_lateral_pos_ok` on the strict pass only and let the refill scan the raw pool. |
| **T-B7** | `test_queue_record_elo_false_writes_no_swipe` | Two queue calls on **distinct** packages, one `record_elo:false`. (a) both `queued: true`; (b) both wrote a `trade_decisions` row; (c) `swipe_decisions` gained rows for the default call **only**; (d) the involved players' ratings are **unchanged** across the `false` call and **changed** across the default one. | (i) Drop the `if record_elo:` guard → (d)'s unchanged leg fails. (ii) Also skip `save_trade_decision` → (b) fails. Two-sided: (d) requires the default leg to move. |
| **T-B8** | `test_queue_record_elo_default_is_todays_behavior` | With the key **absent**: same `trade_decisions` row as before the change, and a `swipe_decisions` row with `k_factor == trade_k_like * 1.0` (8.0 — an asset-idea card carries no `lane_shift`, so `fit_congruence_mult` returns 1.0, `server.py:12578`). | Flip the default (`record_elo = bool(body.get("record_elo"))`) — every existing caller silently stops teaching the board. |
| **T-B9** | `test_dismiss_cooldown_binds_for_asset_idea_card` | A pass on an `asset-idea:<key>` `trade_id` reaches the FB-46 reconstruction and adds `(frozenset(give), frozenset(receive))` to `_past_decision_keys` on **every** service in `sess["trade_svcs"]`. Pattern: `backend/tests/test_pass_cooldown.py:145`. | Narrow the D-067 loop back to `sess["trade_svc"]` alone — the card returns after a scoring-format switch (the original bug). |

### 6.2 Mobile structural suite — `mobile/tests/check-shop-deck.js` (**NEW**)

Dependency-free node, parsing the shipped source with the project's own
TypeScript (the `check-single-pin-actions.js` pattern). Runs in CI automatically
— `.github/workflows/ci.yml:44` globs `tests/check-*.js` — plus an
`npm run test:shop-deck` script for local use.

| # | Assertion | Sabotage that makes it fail | Why nothing else catches it |
|---|---|---|---|
| **A-1** | `shop.like-btn` and `shop.dismiss-btn` both exist somewhere under `mobile/src` (file-agnostic). | Delete either button. | — |
| **A-2** | **Uncrossed.** The element carrying `shop.like-btn` dispatches the like handler and `shop.dismiss-btn` the dismiss handler, and the two callee identifiers **differ**. | Cross them. | `tsc` cannot see it — both are `() => void`. The ✕ would queue a real offer to a league-mate. |
| **A-3** | The like handler reaches `queueCalcTrade` (not `swipeTrade`); the dismiss flush reaches `swipeTrade` with the literal `'pass'` (not `'like'`). | `decision: 'like'` on the dismiss path. | Silent catastrophe: dismissing teaches the board the opposite **and** queues an offer. Type-identical. |
| **A-4** | The dismiss handler **arms a timer before any network call** — no `mutate(` / `swipeTrade(` outside a `setTimeout` callback within `handleDismiss` — and references `UNDO_HOLD_MS`; the undo handler calls `clearTimeout` and contains **no** network call. | POST immediately and "undo" by re-adding the card locally. | This is exactly the dishonest-copy failure the item was warned about, and it is invisible to every other check: the UI looks identical. |
| **A-5** | The entry-point action object is inside a branch testing `trade.shop_asset` (directly or via the exported `shopEnabled` helper). | Push the row unconditionally. | OFF stops being byte-identical; no runtime test covers the OFF path. |
| **A-6** | `swap_positions` is added to a request body **only** inside a truthy-flag branch, via a conditional spread — never assigned `undefined` or `[]`. | `swap_positions: positions` unconditionally. | The OFF-state request body changes shape; `tsc` is happy (the field is optional). |
| **A-7** | Neither `ShopAssetScreen.tsx` nor `ShopCardPager.tsx` imports `react-native-gesture-handler`, nor contains `PanResponder` or `Gesture.Pan`. | Reimplement the pager with a pan. | Reintroduces the arbitration risk the design removed. |
| **A-8** | The counter's expression and the pager's `data` prop derive from the **same identifier**. | Counter reads the unfiltered `ideas.length` while the pager renders the locally-un-dismissed list. | The counter reads "3 / 7" on a 6-card pager. Nothing else notices. |
| **A-9** | `ShopAssetScreen.tsx` mounts `FeedbackFAB` with `activeScreen="ShopAsset"`. | Drop it. | #188 compliance. |
| **A-10** | Neither new file contains: an emoji codepoint, `LinearGradient`, `backdrop`/`blur`, a `borderRadius` numeric literal > 8 other than `999`, or `Inter`/`Roboto`/`System` as a font family. | Style the mode chips with a gradient or a 12px radius. | Chalkline prohibitions are enforced, not advisory. |
| **A-11** | `ShopCardPager.tsx` mounts `TradeCard` **without** a `disposition` prop. | Pass `disposition`. | The card would render its own like/pass row (`TradeCard.tsx:773`, `:803`) beside #403's — two competing decision surfaces, and the deck's semantics leaking onto a browse surface. |
| **A-12** | **Executed, not matched.** Transpile `mobile/src/utils/shopMode.ts` (zero runtime imports, the `ideaToCard.ts` convention) and run it: `SHOP_MODE_GROUP.tier_up === 'upgrade'`, `.tier_down === 'downgrade'`, `.same_value === 'lateral'`, and the three values are distinct. | Swap `tier_up → 'downgrade'`. | All three are string literals of the same union — `tsc` cannot tell them apart, and the UI would show tier-DOWN ideas under a "Tier up" chip. |
| **A-13** | The literals `'Tier up'`, `'Tier down'`, `'Same value'` each appear exactly once in the new files, and the two tier labels are read from `TRADE_INTENT_LABEL` rather than retyped. | Retype `'Tier Up'` inline. | This is the #402/#403 divergent-copy failure the brief names by prior example. |

**Regression, unmodified:** `npm run test:single-pin-actions` green, with
`check-single-pin-actions.js` byte-identical to `origin/main`.

### 6.3 Code-walk proof — the substitute for the missing captures

`screens/` is frozen at 2026-08-11 (D-056) and holds **no single-pin or
asset-ideas capture** — `screens/mobile/trades/` has only `empty`,
`empty--cold`, `error`, `format-gate`, `generating`, `loading`, `populated`
(`screens/manifest.json:1652-1725`), and the surface has moved since (#240,
#287, #317, #384). The PRD's "UI-touching items name their captures" rule
**cannot be satisfied**; the waiver and this substitute are written in
[`scope.md`](scope.md) §3.

**Trace 1 — entry tap → a card on screen.**

1. `MatchesScreen.tsx:1568` (mounted at `:1544`) `menuActionsFor` builds the action array; the
   flag-gated `{key:'shop'}` row is appended (`lld-delta.md` §4.4).
2. `MatchesScreen.tsx:1541` mounts `PlayerContextMenu` with that array.
3. `PlayerContextMenu.tsx:87` maps `actions` to rows; testID defaults to
   `player-menu.shop` (`:38-40`). **Flag off ⇒ the array is the same object
   shape it is today and this row does not exist.**
4. `onPress` → `navigation.navigate('ShopAsset', {...})` → the `<Stack.Screen>`
   registered in `RootNav.tsx` (`lld-delta.md` §4.1), `gestureEnabled: false`.
5. `ShopAssetScreen` fetches via `fetchAssetIdeas` (`api/trades.ts:386`) with
   `direction:'give'`; W1 omits `swap_positions` entirely.
6. `POST /api/trades/asset-ideas` (`server.py:12024`) → flag check `:12069` →
   `TradeService.generate_asset_ideas` (`trade_service.py:4976`) →
   `_generate_asset_ideas_impl` (`:4982`).
7. Response normalized by `normalizeAssetIdea` (`api/trades.ts:336-386`);
   `trade_id` is **absent** for asset ideas (`:317-322`), which is what makes
   step 10 use the synthetic id.
8. `ShopAssetScreen` selects one group via `SHOP_MODE_GROUP[mode]` and passes
   the flat array to `ShopCardPager` as `data`.
9. `ShopCardPager` renders `<TradeCard data={ideaToCard(idea, leagueId)}
   hideMatchStrength />` — the same call `FeaturedTradeWindow.tsx:92` makes,
   with **no** `disposition` prop, so `TradeCard` renders none of its own
   decision controls (`TradeCard.tsx:773`, `:803`).
10. `ideaToCard` (`utils/ideaToCard.ts:56`) sets
    `trade_id = idea.trade_id || 'asset-idea:' + assetIdeaKey(idea)`, and
    `assetIdeaKey` (`:27`) is `` `${counterparty}.${give.join('_')}-${receive.join('_')}` `` —
    deterministic, and exactly the FB-46 reconstruction context.

**Trace 2 — dismiss → undo → (nothing happened).**

1. `shop.dismiss-btn` `onPress` → `handleDismiss(idea)` (`lld-delta.md` §6.2).
2. Double-fire guard on `assetIdeaKey`; `flushPendingDismiss()` commits any
   older pending write (at-most-one, ordering).
3. The card is removed **optimistically** and `pendingDismissRef.current` is
   armed with `setTimeout(..., UNDO_HOLD_MS)`. **No network call is made on
   this path** (pinned by A-4).
4. `setToast({msg:'Dismissed', holdMs: UNDO_HOLD_MS, action:{label:'Undo'}})` —
   `Toast.tsx:51-66` holds for the same constant, so the affordance and the
   commit expire together.
5. **Undo tapped:** `clearTimeout(p.timer)`, ref cleared, card restored,
   `setIndex(p.restoreIndex)`, `track('shop_dismiss_undone')`. The server was
   never contacted; `swipe_decisions`, `trade_decisions` and the Elo board are
   untouched because **no write was ever attempted**. This is why the copy
   needs no caveat.
6. **Window expires instead:** `flushPendingDismissRef.current()` fires
   `swipeTrade({card, decision:'pass'})`.
7. `POST /api/trades/swipe` (`server.py:12527`) → `record_decision` raises
   `Unknown trade_id` → `_reconstruct_swipe_card` (`:12493`) rebuilds and
   registers the card from the echoed give/receive/target context (`:12562`).
8. `service.record_trade_signal(winner=give, loser=receive, 'pass', fit_mult)`
   (`:12608`). `fit_congruence_mult` returns **1.0** — the card carries no
   `lane_shift` (`:12578`) — so K is plain `trade_k_pass` (4.0,
   `ranking_service.py:58`).
9. **D-067 cooldown** (`:12640-12653`): `(frozenset(give), frozenset(receive))`
   is added to `_past_decision_keys` on **every** service in
   `sess["trade_svcs"]`, so the package is excluded immediately, in this
   session, across scoring formats.
10. `save_trade_decision` (`:12670`) persists the row; `save_trade_swipes`
    (`:12680`) persists `k_factor = trade_k_pass × 1.0`. `_compute_elo`
    (`ranking_service.py:1528-1538`) replays it: `ea = 1/(1+10^((rb−ra)/400))`,
    `Δwinner = k(1−ea)`, `Δloser = −k(1−ea)`.

**Trace 3 — Chalkline compliance (R-14).** Mode chips: subnav-pill construction
(`components.md` § Navigation) — 1px `--line`, `radii.xs`, active = **ice**
border + `--ink-2` well. Counter: `TickLabel`, `label` type, chalk-dim, **not**
`--flare` (`design-system.md` "flare never appears on a button or actionable
control's primary affordance", and the counter sits inside the decision
cluster). Like: `Button variant="primary"` = ice fill + `on-ice` text. Dismiss:
`variant="ghost"` + `x` glyph. Position chips: `PositionChip` with `posColor`
— QB `#F97316` / RB `#22C55E` / WR `#3B82F6` / TE `#A855F7`, **data encodings
governed by `docs/cross-client-invariants.md`, reused and never redefined**.
Card body: the shipped `TradeCard` (`components.md` § Cards). No new hue, no
gradient, no blur, no radius above 8 except the specced pills.

### 6.4 The sabotage protocol

**A test counts only after it has been observed red under its named sabotage.**
For each of T-B1…T-B9 and A-1…A-13: apply the sabotage in the row, run the
suite, record the failure, revert, re-run green. The pair (red under sabotage,
green after revert) is what goes in `living-memory/TEST_LEDGER.md` — not a pass
count.

**Two-sidedness is checked, not assumed.** T-B1/T-B2 are an explicit pair
(identical-when-absent ∧ different-when-present); T-B4 pairs its 400 legs with
a must-succeed `[" rb "]` leg; T-B5 pairs its empty case with a partial case;
T-B7 requires the default leg to move the board while the `false` leg does not.
A one-sided version of any of these is satisfiable by a build that always
returns empty, always 400s, or never writes.

### 6.5 Manual TestFlight checklist (the operator)

Written as a regression suite, because under D-056 it is the only runtime
evidence mobile gets. Preconditions: a real league with ≥3 league-mates;
`trade.asset_ideas`, `ux.player_context_menu`, `calc.merged_layout`,
`trade.likes_you` all **on** (they are today).

**§A — flag OFF (`trade.shop_asset: false`). Nothing may look different.**

| # | Steps | Expected |
|---|---|---|
| 1 | Matches tab → long-press any player on a match tile. | The menu opens with **exactly today's rows**. No "Shop this player". |
| 2 | Trades tab → pin exactly one player → let the deck build. | The featured window + Upgrade/Lateral/Downgrade list render exactly as before. Pass and Like on a deck card still work; the pin's "Previous trade" back-chip still works. |

**§B — flag ON (`trade.shop_asset: true` via `POST /api/feature-flags/reload`, no rebuild).**

| # | Steps | Expected |
|---|---|---|
| 3 | Matches → long-press a player you'd trade away → **"Shop this player"**. | The screen opens on **Tier up** with the player named at the top and a counter reading **1 / N**. |
| 4 | Swipe the card left, then right, then left again. Watch the counter. Then swipe right from card 1 and left from card N. | The counter tracks every page exactly (`2 / N`, `1 / N`, …). **No card is consumed, liked, or passed.** Card 1 does not page off the left edge; card N does not page off the right. The screen does **not** pop back to Matches on a left-edge swipe. |
| 5 | Tap the **feedback** button. | It opens, tagged to this screen. |
| 6 | On a card you'd actually offer, tap **✓ (Like)**. | A success toast. Matches tab → "Awaiting them" now lists that trade. |
| 7 | Tap **✓** on the **same** card again. | Success again, **no duplicate row** in "Awaiting them" (idempotent). |
| 8 | Find a card the counterparty's preferences would refuse (e.g. one containing a player they marked untouchable). Tap **✓**. | A toast naming **who** refused and **why** — e.g. "@name has someone in this trade marked untouchable." Never a generic "couldn't queue that". |
| 9 | **[if O-1 = option A]** After step 6, open the Ranks/board screen and check the two players' Elo. | **Unchanged** by the like. |
| 10 | Switch to **Tier down**, then **Same value**. | The pager reloads for each group; the counter resets to `1 / N` (or the honest empty state); the mode chip is ice-outlined. |
| 11 | Tap **✕ (Dismiss)** on a card. | It disappears, the counter drops by one, and a "**Dismissed · Undo**" toast appears. |
| 12 | Tap **Undo** within 5 seconds. | The card **comes back at its old position** and the counter is restored. Deck/Matches show no trace of a pass. |
| 13 | Dismiss another card and let the toast expire (>5 s). Then back out, relaunch the shop for the same player, same mode. | The dismissed card **does not come back**. |
| 14 | Dismiss a card, then immediately dismiss a second one **before** the first toast expires. | Both are gone; only the second offers Undo; nothing is double-recorded. Back out and relaunch: **both** stay gone. |
| 15 | Dismiss a card and immediately press the header back chevron. Relaunch. | The dismissed card is gone — leaving the screen **commits**, it does not lose the disposition. |
| 16 | **[W2]** Same value mode → select **RB** and **TE** → wait for the reload. | Every card's return side is an RB or a TE. Deselect all → the returns are the pin's own position again, and a hint line says so. |
| 17 | **[W2]** Select a single position for which nothing exists. | An honest empty state naming the mode **and** the selection — never a spinner and never a fabricated card. |
| 18 | Go back to the Trades tab, pin one player, and swipe a deck card left and right. | **The deck's own swipe still likes and passes.** (The one thing a pushed screen could plausibly have disturbed.) |
| 19 | Set `trade.shop_asset` back to `false` and reload flags **without rebuilding**. Repeat steps 1 and 2. | Byte-identical to §A. The kill switch works with no deploy. |

### 6.6 Web test section

**Not applicable, and this is a written waiver, not silence.** No `web/` file
references asset ideas (`git grep -n "asset-ideas" -- web extension` returns
nothing) and #403 adds none. No URL, action, or DOM assertion exists to write.

### 6.7 Ship gate

- CI green on the pushed sha: `pytest backend/tests` · `npx tsc --noEmit` ·
  the `mobile/tests/check-*.js` loop (`.github/workflows/ci.yml:44`) ·
  `mobile/scripts/testid-lint.sh`.
- **Ownership diff check:** `git diff --name-only origin/main` must contain
  none of `mobile/src/components/{AssetIdeasPanel,TradeCard,FeaturedTradeWindow}.tsx`,
  `mobile/src/utils/ideaToCard.ts`, `mobile/src/screens/TradesScreen.tsx`,
  `mobile/tests/check-single-pin-actions.js`.
- `living-memory/TEST_LEDGER.md` entry naming what ran and what it proved,
  including the sabotage results from §6.4.
- `FTF_SKIP_SIM_GATE=1` is the standing posture for `githooks/pre-push` (D-056);
  note the evidence run in its place.

## 7. File ownership

Disjoint from #402, and disjoint within #403's own waves.

**Agent M (mobile) — owns**

`mobile/src/screens/ShopAssetScreen.tsx` **NEW** ·
`mobile/src/components/ShopCardPager.tsx` **NEW** ·
`mobile/src/components/ShopPositionPicker.tsx` **NEW (W2)** ·
`mobile/src/utils/shopMode.ts` **NEW** ·
`mobile/tests/check-shop-deck.js` **NEW** + its `mobile/package.json` script ·
`mobile/src/navigation/RootNav.tsx` (param-list line + one `<Stack.Screen>`) ·
`mobile/src/screens/MatchesScreen.tsx` (one action row) ·
`mobile/src/api/trades.ts` (`fetchAssetIdeas` body type; `queueTradeForOpponent` arg) ·
`mobile/src/utils/queueCalcTrade.ts` (one threaded arg) ·
`mobile/src/components/CLAUDE.md` (two rows) ·
`docs/design/components.md` (a `ShopCardPager` row)

**Agent B (backend) — owns**

`backend/server.py` (`asset_trade_ideas` parse + kwarg; `queue_trade_for_opponent`
`record_elo`) · `backend/trade_service.py` (`_generate_asset_ideas_impl`) ·
`backend/tests/test_asset_ideas.py` · `backend/tests/test_shop_queue_elo.py` **NEW** ·
`backend/analytics_taxonomy.py` + `backend/analytics_queries.py`
(**both**, same commit as Agent M's emitter — M emits only names B registered) ·
`config/features.json` + `backend/feature_flags.py` `FLAG_KEYS` +
`backend/tests/fixtures/flags/*.json` · `docs/api-reference.md` ·
`docs/config-reference.md` · `docs/glossary.md` · `living-memory/LLD.md`

**Owned by #402 — do not edit** (import only)

`mobile/src/components/AssetIdeasPanel.tsx` · `mobile/src/components/TradeCard.tsx` ·
`mobile/src/components/FeaturedTradeWindow.tsx` · `mobile/src/utils/ideaToCard.ts` ·
`mobile/tests/check-single-pin-actions.js`

**Contended — #402 owns, #403 never opens**

`mobile/src/screens/TradesScreen.tsx`. The deck entry-point row is a four-line
patch handed to #402's agent (`lld-delta.md` §4.4), or a serialized follow-up.

**Cross-agent coupling, named:** Agent M's `track('shop_*')` calls and Agent
B's `ALLOWED_CLIENT_EVENTS` / `CLIENT_EVENT_PROPS` entries must land in the
**same commit**. Unregistered props are silently dropped behind a 200.

## 8. Sequencing

| Wave | Contents | Backend diff | Independently shippable? |
|---|---|---|---|
| **W1** | R-1…R-9, R-13…R-18. Entry point, screen, pager, `1/X`, like, dismiss + undo, flag, analytics, `check-shop-deck.js`. | Only `record_elo` (O-1 option A). Zero if option B. | **Yes** — answers most of the report. |
| **W2** | R-10…R-12. `swap_positions` on route + service, the picker, T-B1…T-B6. | Yes. | **Yes** — additive on top of W1. |

If scope is cut, cut W2. Run spike S-2 before W2's picker UI.
