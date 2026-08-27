# Plan — #403 "Shop a player"

**Phase 1, Planner (subagent 1) output.** Author agent (subagent 2) writes
`hld-delta.md` / `lld-delta.md` / `prd.md` / `scope.md` from this.

**Tree verified against:** `origin/main` @ `30070f36` (worktree
`claude/new-feedback-71436e`, clean). Every `file:line` below was read in the
current tree during this round. Anything not yet in the tree is marked
**NEW**.

**Work-type path:** **Feature** (new user-visible capability + at least one
new request parameter). Full gate set applies unless the operator declares
express — and this item touches an API contract and analytics, so per
`CLAUDE.md` §Conventions it is on the **bright line**: an express declaration
here needs an explicit confirming yes.

---

## 1. Problem statement, in the operator's terms

> "I want to give users the option to **'shop' a player**. When launched, the
> user is offered a few options, trade options to **tier up, tier down,
> explore position specific swaps of similar value**. If position swap, the
> user should be able to **select the position (or positions)** we suggest in
> the swap ideas. I want a similar response to the current tier up/tier down
> UI which presents the ideas as **small tiles** … or **trade cards with a
> 1/X indication** … They can **swipe left and right on the cards to go back
> and forth between them (different from the current ship to like feature).
> Each card should have a **like/dismiss button**."

Plain reading: *pick one player, say what kind of move you want, and flip
through the resulting offers like a photo roll — deciding on each one without
the deck's swipe-to-decide gesture.*

The operator's own hedge — **"Idea, not design consideration quite yet"** —
is load-bearing. This plan's job is to say what is already built, what is
genuinely new, and what nobody has decided yet. It deliberately does not
invent answers to §2.

### The one-line finding

**The engine already exists and is live.** `POST /api/trades/asset-ideas`
(`backend/server.py:12024`, flag `trade.asset_ideas` = `true`) already returns
tier-up / tier-down / same-value-position-swap ideas for one pinned player.
**#403 is ~80% a re-presentation problem and one narrow engine parameter**, not
a new engine. Concretely: one optional request field, one entry point, one new
presentation component. A PRD that specs a new generator on top of this is the
expensive failure mode.

---

## 2. Open questions — genuinely unresolved by the report

These are **not** for the Author agent to decide. Each needs an operator
ruling (or an explicit "Author's call, flagged as an assumption") before build.

| # | Question | Why it can't be inferred | Cost of guessing wrong |
|---|---|---|---|
| **Q-A** | **What does "like" DO?** Three live meanings exist: (a) deck like → `POST /api/trades/swipe` `decision:'like'`, which **moves the user's Elo board** (`backend/server.py:12597-12605`, `trade_k_like`) and runs mutual-match detection; (b) calculator ✓ → `POST /api/trades/queue` (`backend/server.py:13027`), which records a like the **counterparty will see** in their likes-you injection, is idempotent, and refuses rather than half-recording; (c) a pure local bookmark, which does not exist today. | The report says "like/dismiss button", and separately says the surface is "different from the current ship to like feature" — which may mean only the *gesture* differs, or may mean the *semantics* do. | (a) silently retrains the ranking board from a browsing gesture; (c) builds a fourth like concept the app then has to reconcile. |
| **Q-B** | **What does "dismiss" DO?** A deck pass (`decision:'pass'`) moves Elo *and* writes a permanent dismiss-cooldown so that package is never re-served (`backend/server.py:12640-12653`). A shop-card dismiss could be that, or a session-local "next card please". | Same ambiguity. "Dismiss" in the report sits beside "like" as a symmetric pair, which reads like the deck pair — but the whole point of the ask is that this is *not* the deck. | An accidental permanent exclusion from browsing a card is unrecoverable in-session. |
| **Q-C** | **Does "shop" mean give-side only?** Fantasy usage ("shop him around") = trade away. The live endpoint supports both `direction:"give"` and `direction:"receive"` (`backend/server.py:12080` + the docstring at `:12042-12048`). | The report never says. "Tier up / tier down" reads naturally in either direction but means opposite things. | A receive-direction shop is a different product ("what would he cost me?"), and building both doubles the surface. |
| **Q-D** | **Positions: filter or re-target?** For a `give` pin, selecting "RB, TE" could mean (i) *narrow* the lateral group to RB/TE counterparts — but today lateral is hard-constrained to the pin's OWN position (`backend/trade_service.py:5205`), so for a WR pin an RB filter returns **zero**; or (ii) **replace** the #198 same-position constraint with the user's chosen set. Only (ii) produces results. | The report says "select the position (or positions) **we suggest** in the swap ideas" — ambiguous between "the positions we already suggested" (filter) and "the positions we should suggest" (re-target). | Reading (i) ships a control that always empties the list. |
| **Q-E** | **Tiles or cards — or both?** The report offers them as alternatives ("small tiles (so multiple offers presented at once) **or** trade cards with a 1/X indication"). | Explicitly an either/or in the source text. | Building both doubles the component work for one surface. |
| **Q-F** | **Where is "Shop" launched from?** The report was filed on screen `TradeCalculator`, which today has **no** access to asset ideas at all (see §3, row E). Candidates: the player long-press menu (`PlayerContextMenu`, generic action list, `mobile/src/components/PlayerContextMenu.tsx:33-42`), a roster row, the finder hub, or a control on the calculator itself. | Never stated. | An entry point on the wrong screen makes the feature undiscoverable. |
| **Q-G** | **Naming collision.** "**Shopping**" is already a shipped domain term meaning `trade_away_positions`, a league-level positional preference (`docs/glossary.md:118`, `docs/glossary.md:172`, `TradeDnaSheet` "Chasing / Shopping / Avoiding"). "Shop a player" would be a second, asset-level meaning of the same word. | The operator used the word naturally; the collision is ours, not theirs. | Two meanings of "shopping" in one product is a support and copy problem forever. Alternatives: "Shop this player" vs. renaming nothing and accepting context disambiguates. **Operator call.** |
| **Q-H** | **Copy: "tier up/down" vs "Upgrade/Downgrade".** Both vocabularies ship today: `trades.intent_modes` chips read **"Tier up" / "Tier down"** (`mobile/src/components/TradeDnaSheet.tsx:210-211`), while the asset-ideas panel reads **"Upgrade at WR" / "Downgrade ideas"** (`mobile/src/components/AssetIdeasPanel.tsx:41-43`). | The report says "tier up/tier down". | This is exactly the #402/#403 divergent-copy failure the brief warns about. **#402 decides — see §5.** |
| **Q-I** | **What is "the current tier up / tier down UI" the report wants matched?** Two candidates: the AssetIdeasPanel group list (which the report may be seeing), or the surface **#402 is about to build** below the trade chip. | #402 (filed 64 min earlier) is changing exactly this. | Matching the wrong one guarantees the two items ship divergent surfaces. **Resolve via #402.** |

---

## 3. What already exists vs what is new

**This is the most important section in this document.** Every "exists" claim
carries a verified `file:line`.

### 3a. The engine — EXISTS, LIVE, essentially complete

| Row | Report asks for | Status | Evidence |
|---|---|---|---|
| **A** | "trade options to **tier up**" | **EXISTS** — the `upgrade` group | Route `backend/server.py:12024`; impl `backend/trade_service.py:4982` (`_generate_asset_ideas_impl`); give-direction upgrade search `backend/trade_service.py:5211-5239`; client type `mobile/src/api/trades.ts:325-334` |
| **B** | "**tier down**" | **EXISTS** — the `downgrade` group (2–3 lesser pieces back, same-position headliners preferred) | `backend/trade_service.py:5240-5259`; ordering `backend/trade_service.py:5338-5348` |
| **C** | "explore **position specific swaps of similar value**" | **EXISTS but not user-selectable** — the `lateral` group is *already* position-specific, hard-constrained to the **pin's own** position (#198). `pin_pos` at `backend/trade_service.py:5091-5092`; the never-relaxed gate at `backend/trade_service.py:5205` (give) and `:5291` (receive). Band = `asset_ideas_lateral_band` 0.10 (`backend/trade_service.py:202`, `backend/database.py:2473`) | See cites |
| **D** | "user should be able to **select the position(s)**" | **NEW** — no request field, no service kwarg, no UI control accepts a position set. The current kwarg list is `backend/trade_service.py:4982-4999`; the route's body parse is `backend/server.py:12078-12092`. Neither takes positions. | See cites |
| **A′** | Flag state | `trade.asset_ideas: true` in `config/features.json`; 404 when off at `backend/server.py:12069` | verified |
| **A″** | Test coverage of the engine | **EXISTS** — `backend/tests/test_asset_ideas.py` (route + service, cap, determinism, `opponent_user_id` scoping, flag-off 404) | verified |

**Delta on the engine: exactly one optional parameter (row D).** Everything
else in the report's "when launched, the user is offered a few options" is
already computed and already served.

### 3b. The presentation — the real delta

| Row | Report asks for | Status | Evidence |
|---|---|---|---|
| **E** | An **entry point** ("when launched") | **NEW, and the biggest gap.** Asset ideas render **only** on `TradesScreen`, **only** when `trade.finder_targeting` + `trade.asset_ideas` are on **and exactly one finder target is pinned** (`mobile/src/screens/TradesScreen.tsx:1478-1486` (`singlePin`), `:1498` (`singlePinFeatured`)). There is no "shop this player" affordance anywhere. Today's three ways in: the player-mode target board (`TradesScreen.tsx:6046`), `Keep · more offers` on a 1-player side (`mobile/src/components/TradeCard.tsx:443` → `handleKeepSide` `TradesScreen.tsx:2880`), and the league-summary Offer/Target row action (`mobile/src/screens/LeagueSummaryScreen.tsx:1183-1185`). | verified |
| **E′** | Reachable from where #403 was filed (`TradeCalculator`) | **NO.** `AssetIdeasPanel` is imported by exactly one file, `mobile/src/screens/TradesScreen.tsx:107`. `TradeCalculatorScreen` never mounts it. `calc.inline_home` is **`false`** in `config/features.json`, so the calculator is still the pushed two-tab page, not part of the trades home. **The operator filed this from a screen where the live feature is invisible.** That alone may explain the "may already exist" question. | verified |
| **F** | "presents the ideas as **small tiles** … multiple offers at once" | **PARTIAL.** Today it is a **grouped vertical list of rows**, not tiles: `AssetIdeasPanel` renders three `Text` group headers over `IdeaRow`s (`mobile/src/components/AssetIdeasPanel.tsx:182-203`, row at `:64-144`). Each row = give ↔ receive names, position dots, counterparty, a signed diff chip, a chevron. Multiple offers *are* on screen at once. A horizontal tile-strip precedent exists elsewhere: `mobile/src/components/TradeBuildCanvas.tsx:158-193`. | verified |
| **G** | "**trade cards with a 1/X indication**" | **PARTIAL, wrong surface.** A `1 of X` counter exists — `Featured trade · ${deckIdx + 1} of ${sortedDeck.length}` at `mobile/src/screens/TradesScreen.tsx:6879`, testID `trades.single-pin-deck-count` — but it counts the **model deck** in single-pin mode, never the asset-idea groups. The asset-ideas surface has **no counter**. | verified |
| **H** | "**swipe left and right … to go back and forth** between them" | **NEW.** No horizontal pager exists for ideas. Today: tap a row → it loads into `FeaturedTradeWindow` above (`AssetIdeasPanel.tsx:197` → `handleSelectIdea` `TradesScreen.tsx:1613`), with a one-way `‹ Previous trade` history chip (`mobile/src/components/FeaturedTradeWindow.tsx:59-75`, capped by `FEATURED_HISTORY_CAP`). That is a back-stack, not a pager. | verified |
| **I** | "**different from the current ship to like feature**" | **CONFIRMED, and the operator is right to call it out.** The deck's only horizontal gesture is destructive: `Gesture.Pan()` at `mobile/src/screens/TradesScreen.tsx:7926-7947` — right past `SWIPE_THRESHOLD` (120, `:221`) = **like**, left = **pass**, then `advance()` (`:4688`) consumes the card. In #403's surface the same gesture must **navigate**, and the decision must be a button. These two gestures cannot coexist on one element. | verified |
| **J** | "Each card should have a **like / dismiss button**" | **NEW on this surface.** `AssetIdeasPanel` has zero decision controls — its rows only feature or open in the calculator (`TradesScreen.tsx:1545-1568` `handleOpenAssetIdea`). Worse: `trades.player_offers_calc` is **`true`**, so `FeaturedTradeWindow` renders the idea as an editable `InLeagueCalculator` (`FeaturedTradeWindow.tsx:78-87`) mounted **without** `onLikeTrade` / `onFindATrade` — and both controls disable on a missing handler (`mobile/src/components/InLeagueCalculator.tsx:1107` and `:1157`). **So today an asset idea cannot be liked from the featured window at all: the ✓ renders disabled.** The deck's own like/pass buttons exist but only on deck cards (`mobile/src/components/TradeCard.tsx:773`, `:803`). | verified |

### 3c. Scoreboard

| | Weight |
|---|---|
| **Already ships** | The whole three-group generator, its gates (#108 user-gain, #141 filler, untouchables, not-interested, #360 avoid), pick injection, `opponent_user_id` scoping, the relaxed-band refill, the per-idea `favors`/`gap` verdict (`backend/server.py:12184-12190`), the client type + normalizer (`mobile/src/api/trades.ts:298-330`, `:386-409`), and a grouped renderer |
| **Genuinely new** | (1) one optional **position-set** parameter on the lateral search; (2) an **entry point**; (3) a **pager presentation** with a 1/X counter and a non-destructive horizontal gesture; (4) **per-card like/dismiss controls** with decided semantics |

---

## 4. Recommended approach

**Frame it as: give the live asset-ideas engine a front door and a browser.**
Not a new engine.

### 4.1 Backend — one optional field, additive, default-identical

Add an optional `swap_positions: string[]` to `POST /api/trades/asset-ideas`
and a matching `swap_positions: list[str] | None = None` kwarg on
`_generate_asset_ideas_impl` (`backend/trade_service.py:4982`).

- **Absent / empty ⇒ byte-identical to today.** `pos_constrained` and
  `_same_pos` (`backend/trade_service.py:5091-5095`) are untouched.
- **Present ⇒ it *replaces* the #198 same-position predicate for the
  `lateral` group only** (per Q-D reading (ii) — needs the operator's yes).
  Upgrade and Downgrade keep today's semantics exactly; widening those was
  never asked for.
- **It is a semantic, never a gate knob** — same rule #198 already states at
  `backend/trade_service.py:5030-5037`: the #189 relaxed refill may widen the
  fairness band, never the position set.
- **Interaction with `avoid_positions` (#360):** an avoided position wins.
  `avoid_ok` is a receive-pool exclusion at source
  (`backend/trade_service.py:5194-5200`, `docs/glossary.md:118`), and #360's
  D-360-3(b) already rules that an exclusion beats a pin. A user selecting a
  position they also avoid gets an honest empty group, not a silent override.
  The **client** should not offer avoided positions in the picker; the
  **server** must not depend on the client doing so.
- **Validation:** unknown position strings → 400, not silent-empty. The
  route's existing style (`backend/server.py:12084-12087`) is explicit 400s.
- Update `model_config` docs only if a new knob appears — none is proposed.

**Estimated size: well under 100 lines including tests.**

### 4.2 Mobile — a new component, not a rewrite of `AssetIdeasPanel`

Add **NEW** `mobile/src/components/ShopDeck.tsx` (name provisional pending
Q-G): a horizontal pager over one flattened, ordered list of `AssetIdea`s,
with a `1 / X` `TickLabel` header, a mode selector, an optional position
picker, and per-card like/dismiss.

Why a new component rather than extending `AssetIdeasPanel`:

- `AssetIdeasPanel` is the **#402 surface** (§5). Two items editing it
  concurrently is the exact collision the brief warns about.
- It is pinned by `mobile/tests/check-single-pin-actions.js` assertions 9a/9b
  (the #317 `pinIdeaResumed` contract) and coupled to `FeaturedTradeWindow`'s
  `featuredKey` / IN-WINDOW inert-row protocol
  (`AssetIdeasPanel.tsx:66-80`, `TradesScreen.tsx:5334-5341`). Adding a pager
  and decision buttons into that contract is how #241/#298/#317 regress.
- A separate component can be mounted from a **new** host without touching
  `TradesScreen`'s single-pin state machine at all.

**Gesture rule (non-negotiable, from row I):** the pager's `Gesture.Pan()`
must never be a descendant of, or a sibling competing with, the deck's
like/pass pan (`TradesScreen.tsx:7926`). Cleanest guarantee: the shop surface
is a **modal/sheet or its own pushed screen**, so the two gestures are never
mounted in the same tree. This also solves Q-F's entry-point problem (any
screen can open a sheet) and keeps `FeedbackFAB` rules simple (modals/sheets
are an explicit exception per `CLAUDE.md` §Conventions).

**Chalkline compliance** (`docs/design/design-system.md`,
`docs/design/components.md`): reuse `Card` / `TickLabel` / `Icon` / `Text`
from `components/chalkline`; ice for the like affordance and the active
mode/position chip (ice = what you can do, `design-system.md:66`); the `1 / X`
counter is a `label`-type `TickLabel`, **not** flare — flare is informational
highlight only and never on an actionable control (`design-system.md:20`,
`:66`). Position chips reuse `PositionChip` / `posColor` so the position
encoding stays governed by `docs/cross-client-invariants.md`. No emoji, no
gradients, no blur, `radii.xs`/`radii.sm` only, true pills only where the
components doc already specs them.

### 4.3 Entry point (pending Q-F)

**Recommended default:** a `PlayerMenuAction` row on the existing
`PlayerContextMenu` (`mobile/src/components/PlayerContextMenu.tsx:33-42`) —
it is already a generic, caller-supplied action list mounted on the deck
(`TradesScreen.tsx:6969`) and Matches (`MatchesScreen.tsx:1284`, `:1390`), and
adding a row is additive per host. That gets a front door on the surfaces
where a user is already looking at a player, without an IA change. If the
operator wants it on `TradeCalculator` specifically (where #403 was filed),
that is a second, independent mount of the same sheet.

### 4.4 Alternatives considered and rejected

| Alternative | Why rejected |
|---|---|
| **Build a new "shop" generator / endpoint** | The three groups the report describes are `upgrade` / `lateral` / `downgrade`, already served and already tested (`backend/tests/test_asset_ideas.py`). A second generator would have to re-implement the #108/#141/#163/#360 gate set and would drift from it. `docs/coding-guidelines.md` §2. |
| **Extend `AssetIdeasPanel` in place with pager + buttons** | Collides with #402 on the same file, and entangles the new gesture with the #317/#241/#298 state contract that `check-single-pin-actions.js` pins. |
| **Reuse the deck (`SwipableTopCard`) with swipe re-mapped to navigation** | Directly contradicts the report ("different from the current ship to like feature") and would require branching `advance()` (`TradesScreen.tsx:4688`), the single most load-bearing function on the screen — it carries the double-fire guard, decline-reason deferral, `swipe_undo`, onboarding counters, guide beats and v2 accumulators. Off limits. |
| **Ship presentation only; skip the position picker** | Would drop the one thing in the report that is unambiguously not built (row D). Worth *sequencing* second, not dropping. |
| **Make `swap_positions` widen upgrade/downgrade too** | Not asked for; #198's position-centric semantics are a deliberate decision, and widening upgrade would make "upgrade at WR" mean something else. |
| **Reuse `POST /api/trades/fair-packages`** (`backend/server.py:12236`) | It anchors a give side and searches returns with **no** position semantics — it is the generalisation of the *downgrade* shape, not the tier-up/lateral one. Wrong tool. |

### 4.5 Suggested sequencing (two waves, both independently shippable)

- **W1 — front door + browser.** New entry point, `ShopDeck` pager with 1/X,
  like/dismiss with whatever Q-A/Q-B resolve to. Consumes today's endpoint
  unchanged. Zero backend diff.
- **W2 — position selection.** `swap_positions` on route + service, picker in
  the pager. One backend diff, one client diff.

W1 alone answers most of the report. If the operator wants scope cut, cut W2.

---

## 5. The #402 dependency

**#402 comes first and its decisions win on every shared surface.** There is
no `docs/feedback/items/402-*/` folder in the tree yet — #402's doc round has
not produced artifacts as of this writing, so this section states the
dependency rather than resolving it.

#402, verbatim: *"Let's change the 'more offers' button… When clicking 'more
offers' the user goes to below the trade chip where 'tier up', 'tier down'
options are presented in line."*

Today's "more offers" is `Keep · more offers` (`mobile/src/components/TradeCard.tsx:443`),
whose handler pins that whole side and **regenerates the model deck**
(`handleKeepSide`, `mobile/src/screens/TradesScreen.tsx:2881-2899`).

### What #403 MUST inherit from #402

| Inherited | Why |
|---|---|
| **Group copy** — "Tier up / Tier down" vs "Upgrade at WR / Downgrade". Both vocabularies ship (`TradeDnaSheet.tsx:210-211` vs `AssetIdeasPanel.tsx:41-43`). | #403 explicitly asks for "a similar response to the current tier up/tier down UI". Divergent copy on two surfaces built in the same batch is the documented prior failure. |
| **The tile/row visual treatment** of an idea | Same reason. #403 should render #402's tile, not a second one. |
| **The lateral group's label and whether it appears inline at all** | #402 mentions only tier up / tier down; #403 adds the position-swap third option. If #402 ships a two-option inline row, #403's third option must read as an extension, not a contradiction. |
| **Whatever #402 does to `AssetIdeasPanel` / `TradeCard`** | Those two files are #402's, not #403's (see §8). |

### What #403 can decide independently

- The **pager** (1/X, horizontal navigation gesture) — #402 is explicitly an
  *inline* presentation "below the trade chip"; a pager is a different surface.
- The **entry point** (Q-F) — #402's entry is the existing "more offers"
  button on a deck card; #403's is a new front door from a player.
- **`swap_positions`** and the position picker — #402 asks for neither.
- **Like/dismiss semantics** (Q-A/Q-B) — *unless* #402 also puts decision
  controls on its inline tiles, in which case #402 wins. **The orchestrator
  must check this before the Author agent writes the PRD.**

### Load-bearing logic neither item may disturb

`TradesScreen.tsx` pin / deck-snapshot machinery, all verified:

| What | Where | Why it's load-bearing |
|---|---|---|
| `preSinglePinSnapshotRef` — the pre-pin deck snapshot | declared `:515-528` (comment) / `:524-528` (the ref); captured `:2889`; restored `:2909-2929` (`handleClearPin`) | #288: `resetDeckForNewTargets` wipes deck/idx/job on every pin change; without the snapshot there is no way back to the found trade. Captured at **exactly one** entry point (a clean, unpinned deck) on purpose. |
| `singlePinDeckActive` keyed on `deck.length`, never `topCard` | `:1511-1512` | #298 assertion 7 — keying on `topCard` snaps the surface back to the featured window mid-session. |
| `pinIdeaResumed` set **only** inside `handleSelectIdea` | declared `:1506`; set `:1631` | #317 assertions 9a/9b — setting it from an effect is an automatic snap-back, the exact regression 7 exists to prevent. |
| `FeaturedTradeWindow` gated on `!singlePinDeckActive` | `:6606`, `:6621` | #241 — two trade summaries stacked is the "mystery second trade card". |
| The `advance()` disposition chain | `:4688`+, and `mobile/tests/check-single-pin-actions.js` assertions 1–8 | #298 — a pin must never strip accept/decline. |
| The deck's like/pass pan | `:7926-7947` | Row I — the gesture #403's pager must not collide with. |

**Rule for both items: `check-single-pin-actions.js` must stay green,
unmodified.** If a change requires editing that file, it is a scope escalation
and goes back to the operator.

---

## 6. Platforms touched

| Platform | Touched? | What |
|---|---|---|
| **Backend** (`backend/`) | **Yes, W2 only** | `swap_positions` on the route (`server.py`) + service (`trade_service.py`), validation, tests in `backend/tests/test_asset_ideas.py`. W1 touches nothing. |
| **Mobile** (`mobile/`) | **Yes** | New `ShopDeck` component + host, entry-point action row, `mobile/src/api/trades.ts` body type, new structural check, `testid-lint` compliance. |
| **Web** (`web/`) | **No** | The web app has no asset-ideas surface — `git grep` finds no `asset-ideas` reference under `web/`. Explicitly out of scope; the PRD needs **no** web test section. |
| **Extension** | **No** | — |
| **Schema** (`backend/database.py`) | **No** | No new table, column, or `model_config` key proposed. `asset_ideas_lateral_band` / `asset_ideas_group_cap` (`database.py:2473-2474`) are reused as-is. |
| **Analytics** | **Yes** | New events required (§7). Must be registered in `backend/analytics_taxonomy.py` **and** classified in `analytics_queries.NON_INTENT_EVENTS` **in the same commit as the emitter** (`CLAUDE.md` §Common tasks). Precedent props already registered: `trade_keep_side_tapped` / `trade_pin_cleared` at `analytics_taxonomy.py:343`, `:1303`, `:1305`. |

---

## 7. Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R-1 | **Gesture collision** — a horizontal pan inside a screen that already owns a like/pass pan (`TradesScreen.tsx:7926`). RN Gesture Handler will resolve it in a way neither item specified. | **High** | Mount the shop surface in a sheet/own screen so the two pans are never in one tree. If the operator insists on inline, an explicit `Gesture.Exclusive`/`blocksExternalGesture` contract must be specced in the LLD, not left to defaults. |
| R-2 | **#402/#403 copy + tile divergence** on the same vocabulary. | **High** | §5. #402 decides; #403 consumes. Orchestrator gates the Author round on #402's copy being known. |
| R-3 | **"Like" retrains the Elo board from a browsing gesture** (Q-A option (a)). | **High** | Do not build until Q-A is ruled. If (a) is chosen, it must be a deliberate, documented decision — `record_trade_signal` at `server.py:12597` is not reversible from the client. |
| R-4 | **Position picker returns empty every time** under Q-D reading (i). | **High** | Resolve Q-D before build; if (ii), the LLD must state the #198 constraint is *replaced*, not relaxed, for `lateral` only. |
| R-5 | **Regressing #241/#288/#298/#317** by touching `TradesScreen` single-pin state. | **High** | §5's table; `check-single-pin-actions.js` green and unmodified; new component + new host instead of editing the panel. |
| R-6 | **Third meaning of "shopping"** (Q-G). | Medium | Operator ruling; `docs/glossary.md` gets a row either way. |
| R-7 | **`TradesScreen.tsx` is 8,758 lines** and is the most-contended file in the repo. | Medium | Keep #403's mobile diff in new files; if a `TradesScreen` mount is unavoidable, it is one JSX mount + one handler, owned by exactly one agent (§8). |
| R-8 | **No ground-truth capture of the surface.** `screens/` is frozen at 2026-08-11 (D-056) and `screens/mobile/trades/` holds only `empty`, `empty--cold`, `error`, `format-gate`, `generating`, `loading`, `populated` (`screens/manifest.json:1647-1735`) — **no single-pin / asset-ideas capture exists**, and the surface has changed since (#240, #287, #317, #384). | Medium | The PRD's "UI-touching items name their captures" rule cannot be satisfied from `screens/`. Name this as an explicit **waiver with reason** in `scope.md` §3, and substitute a **code-walk proof** against `AssetIdeasPanel.tsx` + `FeaturedTradeWindow.tsx` + the mock precedents `mockups/polish-lab-2026-08/asset-ideas-layout{,-v2,-v3}.html`. Do **not** cite the mockups as current behavior (`mockups/CLAUDE.md`). |
| R-9 | **Unregistered analytics props are silently dropped** behind a 200. | Medium | Spec every event + prop against `analytics_taxonomy.py` in `scope.md` §analytics before build; same-commit registration. |
| R-10 | **The featured window's ✓ is already disabled** (row J) — a build agent may "fix" that in passing. | Low | Out of scope for #403 unless the operator says otherwise; flag it, don't fix it (`docs/coding-guidelines.md` §3). |

---

## 8. File-ownership proposal

Disjoint across build agents, and disjoint from #402. Shared docs get a named
owner.

### Agent M (Mobile) — owns

| File | New? |
|---|---|
| `mobile/src/components/ShopDeck.tsx` | **NEW** |
| `mobile/src/components/ShopPositionPicker.tsx` (W2; may fold into ShopDeck) | **NEW** |
| `mobile/tests/check-shop-deck.js` + its `npm run` script line in `mobile/package.json` | **NEW** |
| `mobile/src/api/trades.ts` — the `fetchAssetIdeas` body type only (`:386-392`) | edit |
| `mobile/src/components/CLAUDE.md` — one new row | edit |
| The chosen host file for the entry point (§4.3; **one** file, named at PRD time) | edit |

### Agent B (Backend) — owns (W2 only)

| File |
|---|
| `backend/server.py` — the `asset_trade_ideas` body parse + kwarg pass (`:12078-12170`) |
| `backend/trade_service.py` — `_generate_asset_ideas_impl` signature + the `lateral` predicate (`:4982-5300`) |
| `backend/tests/test_asset_ideas.py` |
| `backend/analytics_taxonomy.py` + `backend/analytics_queries.py` (same commit as Agent M's emitter — **coordinate**, or give both to Agent B and have M emit only names B registered) |
| `docs/api-reference.md` (asset-ideas entry) |
| `docs/config-reference.md` — **only if** a knob appears; none proposed |

### Owned by #402, NOT #403 — do not edit

`mobile/src/components/AssetIdeasPanel.tsx` ·
`mobile/src/components/TradeCard.tsx` ·
`mobile/src/components/FeaturedTradeWindow.tsx` ·
`mobile/src/utils/ideaToCard.ts` ·
`mobile/tests/check-single-pin-actions.js`

### Contended — single owner, declared

`mobile/src/screens/TradesScreen.tsx` — **#402 owns it.** If #403 needs a
mount there, #403 supplies the JSX + handler as a patch for #402's agent to
apply, or the two waves are serialized. Never both editing it in parallel.

### Shared docs — named owner

| Doc | Owner | Trigger |
|---|---|---|
| `docs/api-reference.md` | Agent B | route body change (W2) |
| `docs/glossary.md` | Agent B | Q-G: a "Shop a player" term entry |
| `docs/cross-client-invariants.md` | **n/a** — no cross-client value changes (position colors reused via `posColor`, not redefined) | — |
| `living-memory/LLD.md` | Agent B | if the position-set convention is a convention shift |
| `docs/architecture.md` / `living-memory/HLD.md` | **n/a** — no module rewiring; expect an explicit "n/a because" row in `scope.md` | — |
| `living-memory/DECISIONS.md` | Orchestrator | one D- entry per operator ruling on §2 |
| `living-memory/TEST_LEDGER.md` | Orchestrator | at ship |
| `docs/design/components.md` | Agent M | a new `ShopDeck` component row |

---

## 9. Flag proposal

**Name: `trade.shop_asset`** (namespace matches the sibling it extends,
`trade.asset_ideas`; avoid `trades.*`, which is the presentation namespace —
`trades.intent_modes`, `trades.player_offers_calc`, `trades.presentation_v2`).

Ships **`false`**.

| State | Meaning — precisely |
|---|---|
| **OFF (`false`, shipped default)** | **Byte-identical to today.** No entry-point row renders (the `PlayerMenuAction` is not pushed into the `actions` array, so `PlayerContextMenu` maps an unchanged list — `PlayerContextMenu.tsx:87`). `ShopDeck` is never mounted. `mobile/src/api/trades.ts` sends **no** `swap_positions` field, so `POST /api/trades/asset-ideas` receives the identical body it does today, `body.get("swap_positions")` is `None`, and `_generate_asset_ideas_impl` runs its current code path unchanged. `AssetIdeasPanel`, `FeaturedTradeWindow` and the whole single-pin state machine are untouched **in the source**, not merely gated. |
| **ON (`true`)** | The entry point renders on its host(s). Launching it opens the `ShopDeck` surface: mode selector (tier up / tier down / position swap — copy per Q-H), an optional position picker on the swap mode (W2), a horizontal pager over the flattened ideas with a `1 / X` counter, and per-card like/dismiss whose semantics are Q-A/Q-B. Client may send `swap_positions`. New analytics events emit. |

**Kill switch:** this key alone. `POST /api/feature-flags/reload` — no deploy,
no client build — reverts every surface. The client's flag read is a bare
`useFlag('trade.shop_asset')`.

**Prerequisite:** `trade.asset_ideas` must be `true` (it is). With it `false`
the route 404s (`backend/server.py:12069`) and `ShopDeck` has no data — the
PRD must state the degraded behavior (do not render the entry point) rather
than leaving an empty surface.

**Server-side guard question for the Author:** should `swap_positions` be
*additionally* gated on `trade.shop_asset` server-side (400/ignore when off),
the way `calc.merged_layout` gates `/api/trades/queue` and
`/api/trades/fair-packages`? Recommended **no**: the parameter is additive and
harmless, and gating it adds a second flag read to a hot route. **But it is a
contract decision — state it explicitly in the LLD either way.**

**Byte-identical-OFF verification (proposed check):** a structural assertion
in `check-shop-deck.js` that the `swap_positions` key is only ever added to
the request body inside a truthy-flag branch, plus a pytest that
`generate_asset_ideas(**kw)` with `swap_positions=None` returns a result equal
to the same call without the kwarg (the existing determinism test at
`backend/tests/test_asset_ideas.py:202` is the pattern).

---

## 10. Spike needs

| # | Spike | Question it answers | Why a spike and not a guess | Est. |
|---|---|---|---|---|
| **S-1** | **Gesture-isolation spike** (mobile, ~1h) | Can a horizontal pager coexist with the deck's like/pass pan if the shop surface is mounted inline, or does it require a modal/own-screen? | R-1 is high-severity and RN Gesture Handler arbitration is not readable from source alone. Also: `MEMORY.md` records a prior incident where five reviewers agreed on a wrong RN navigation claim — framework side-effect claims here need `node_modules` or a running build, not consensus. **If the answer is "modal", no spike is needed — take the modal.** So run this spike **only if** the operator insists on an inline mount. | 1h |
| **S-2** | **Lateral-yield sanity check** (backend, ~30min) | With `swap_positions` replacing the #198 predicate, does a typical WR pin actually produce non-empty RB/TE lateral ideas, or does the ±0.10 band (`trade_service.py:202`) plus the #108 gain gate empty it? | If cross-position laterals are structurally rare, the picker is a control that mostly shows "nothing found" — a product problem worth knowing before the UI is built. Run against the existing fixtures in `backend/tests/test_asset_ideas.py`. | 30m |
| **S-3** | *Not needed* | Engine correctness | Covered by the existing suite. | — |

---

## 11. Evidence plan sketch (D-056 — no Maestro, no simulator)

For the Author agent to expand in the PRD test plan and `scope.md` §3:

- **Unit / pytest:** `swap_positions` absent ⇒ identical output (two-sided:
  also assert a *present* set changes the lateral group, or the first
  assertion is vacuous); invalid position ⇒ 400; avoided ∩ selected ⇒ honest
  empty, never an override; upgrade/downgrade groups unchanged under any
  `swap_positions`. **Each with a named sabotage** that makes it fail.
- **Structural (`mobile/tests/check-shop-deck.js`, NEW):** the like button
  dispatches the like handler and the dismiss button the dismiss handler,
  **uncrossed** (the `check-single-pin-actions.js` assertion-2 pattern — tsc
  cannot see a crossed `() => void`); the pager's pan is not the deck's pan;
  the entry-point row is inside a flag-gated branch; the `1 / X` counter reads
  from the same list the pager indexes.
- **Regression, unmodified:** `npm run test:single-pin-actions` green.
- **Code-walk proof** in place of the missing captures (R-8): a file:line
  trace from entry-point tap → fetch → pager render → like → server effect.
- **Manual TestFlight checklist** for the operator: flag off ⇒ no entry point
  anywhere and the single-pin surface is unchanged; flag on ⇒ launch, page
  through with the counter tracking, like one and verify the recorded effect
  matches the Q-A ruling, dismiss one and verify the Q-B ruling, select two
  positions and verify the returned ideas match, and verify the deck's own
  swipe still likes/passes.
- **Ship gate:** CI green (`pytest backend/tests`, `tsc --noEmit`,
  `mobile/scripts/testid-lint.sh`) + a `living-memory/TEST_LEDGER.md` entry.
  `FTF_SKIP_SIM_GATE=1` is the standing posture for `githooks/pre-push`.

---

## 12. Handoff to the Author agent — required reading order

1. This plan's **§2** — do not resolve those questions unilaterally; carry
   them into the PRD as open items or as clearly labeled assumptions.
2. **§3** — the exists/new table is the scope boundary. Any requirement that
   re-specs a §3a row is out of scope.
3. **§5** — check for `docs/feedback/items/402-*/` before writing copy. If it
   still does not exist, write #403's copy as *"inherits #402; placeholder
   pending"* rather than inventing it.
4. `docs/templates/feature-scope.md` → `scope.md`, every section answered or
   **written**-waiver'd (silence is not a waiver). Skip its dead §Maestro
   delta and §Simulator-gate tier sections (`docs/CLAUDE.md`).
