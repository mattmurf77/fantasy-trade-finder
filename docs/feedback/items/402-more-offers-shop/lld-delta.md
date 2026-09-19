# LLD delta — #402/#403 "More offers = shop a player"

> Exact interfaces. Every endpoint below either **exists** with a `file:line`
> cite or is marked **NEW**. Request/response JSON carries field types and
> error shapes; client state changes and function-level touch points carry
> file paths. Architecture rationale is in [`hld-delta.md`](hld-delta.md);
> requirements and tests in [`prd.md`](prd.md).

**Tree verified against:** `origin/main` @ `6e94ff71`.

## Contents

- [0. Revision 2 (2026-08-27) — the ruled mechanism](#0-revision-2-2026-08-27--the-ruled-mechanism-this-section-wins-every-conflict-below)
- [1. Endpoint inventory](#1-endpoint-inventory)
- [2. `POST /api/trades/asset-ideas` — the `swap_positions` field](#2-post-apitradesasset-ideas--the-swap_positions-field)
- [3. `TradeService._generate_asset_ideas_impl` — the predicate split](#3-tradeservice_generate_asset_ideas_impl--the-predicate-split)
- [4. Mobile: the shop surface](#4-mobile-the-shop-surface)
- [5. The like path](#5-the-like-path)
- [6. The dismiss path and the undo contract](#6-the-dismiss-path-and-the-undo-contract)
- [7. Flag contract](#7-flag-contract)
- [8. Analytics interfaces](#8-analytics-interfaces)
- [9. testIDs](#9-testids)
- [10. Function-level touch points](#10-function-level-touch-points)

---

## 0. Revision 2 (2026-08-27) — the ruled mechanism. This section wins every conflict below.

Operator rulings (`rulings-2026-08-27.md`) replaced the surface and the entry
point after this document was written. §4 (pushed `ShopAssetScreen`, Matches
long-press) is **superseded**; this section is the buildable replacement.
Everything about the **generator** (§3, `swap_positions`), the **dismiss/undo**
(§6) and the **flag** (§7) carries over with only host renames.

### 0.1 Entry — fork inside `handleKeepSide` (`TradesScreen.tsx:2880`)

The give-side `Keep · more offers` tap becomes the shop entry. The fork sits
at the **top** of the existing handler so flag-off is the untouched path:

```ts
function handleKeepSide(card: TradeCard, side: 'give' | 'receive') {
  haptics.selection();
  if (side === 'give' && shopEnabled) {
    // #402/#403 — give-side "more offers" IS shop. No pin write, no deck
    // reset, no #288 snapshot: the deck underneath must not move.
    if (card.give_players.length === 1) {
      openShopStrip(card, card.give_players[0]);
    } else {
      setShopChooser(card);            // "Shop which player?" sheet (§0.2)
    }
    track('shop_opened', {
      asset_position: card.give_players[0]?.position,   // chooser re-emits
      source: 'more_offers',
      give_count: card.give_players.length,
    }, 'Trades');
    return;
  }
  // ── receive side, or flag off: today's path, byte-identical ──
  … existing body unchanged (snapshot, setSide, track, reset, generate) …
}
```

`shopEnabled = useFlag('trade.shop_asset') && useFlag('trade.asset_ideas')` —
same conjunction §4 specced. **Flag off ⇒ the early-return branch is dead and
the function body is today's, byte-for-byte after the `if`.** The
`trade_keep_side_tapped` event keeps firing only on the paths that still do
what its name says (receive side / flag off).

**Button label under the flag:** the give-side button reads **"More offers"**
(the "Keep ·" prefix describes the pin that no longer happens); receive side
keeps "Keep · more offers". Flag off keeps today's label on both. One design
call, logged in §0.5.

### 0.2 The chooser (give side > 1) — `PlayerContextMenu` construction

A bottom sheet titled **"Shop which player?"**, one row per give-side player
(PositionChip + name + consensus value), tap → `openShopStrip(card, player)`
and re-emit `shop_opened` with the picked position; Cancel → nothing. It is a
`Modal` sheet, **never navigation** (the deck stays mounted — same rule
`MockTeamSheet` documents). No FeedbackFAB (modal exception).

### 0.3 The strip — `mobile/src/components/ShopOffersStrip.tsx` (**NEW**, replaces `ShopAssetScreen`)

Mounted by `TradesScreen` **directly below the top deck card** while
`shopOpen`. Contract:

```ts
interface Props {
  leagueId: string;
  asset: Player;                       // the shopped give-side player
  onClose(): void;                     // ✕ in the strip header
  onQueued(desc: QueueToastDescriptor): void;  // host owns the toast
}
```

- **Header:** "Shopping {asset.name}" + close ✕. Close = unmount; the deck
  never moved, so nothing restores.
- **Mode chips:** Tier up / Tier down / Same value — single-select,
  `tier_up` default, mapping via the exported `SHOP_MODE_GROUP` constant
  (§4's `shopMode.ts` spec survives verbatim). Each chip carries its group's
  idea **count** from the response (an empty mode is navigable, not a dead
  end — promoted from the rev-1 mockup calls).
- **Pager:** `FlatList horizontal pagingEnabled` (HLD D-2 verbatim — no
  `Gesture.Pan`, no new dependency), `1 / X` as a chalk-dim `TickLabel`,
  `X` derived from the same array the `data` prop renders.
- **Tiles:** compact idea tiles — give → receive, counterparty handle,
  signed diff chip (the `AssetIdeasPanel` row vocabulary) — each with
  **✓ like** and **✕ dismiss**.
- **Like:** `utils/queueCalcTrade.ts` → `POST /api/trades/queue`, **as-is**
  (ruling A: Elo moves; `record_elo` not built; §5.2 void). Idempotent;
  refusals render `queueRefusalLine` copy; `calc_trade_queued` fires with
  `screen: 'Trades'`.
- **Dismiss:** §6 verbatim — deferred `POST /api/trades/swipe`
  `decision:'pass'`, `UNDO_HOLD_MS` 5000, at most one pending, unmount/close
  flushes (a disposition is never silently lost). `shop_dismiss_undone`
  screen prop becomes `'Trades'`.
- **Data:** the existing `POST /api/trades/asset-ideas` with
  `direction:'give'`; W1 sends no `swap_positions`; W2 adds the position
  chips inside the Same-value mode pane (§3's backend spec unchanged).
- **Empty modes:** the rev-1 empty-state designs carry (named copy per mode,
  "Clear positions" escape in W2).

### 0.4 Deck statics while shopping

While `shopOpen`, the top card's like/pass pan wrapper renders with
`enabled={false}` — the deck holds still; the strip's pager is the only
horizontal gesture on the screen. The card stays visible above the strip as
context (it is the trade being shopped around). Closing the strip re-enables
the pan. Mechanically assertable (`check-shop-deck.js` re-keys A-7/A-9 to
this: no `Gesture.Pan` in the strip, and the `enabled` expression must
reference the shop-open state).

### 0.5 Deltas to the rev-1 tables

| Rev-1 item | Rev-2 state |
|---|---|
| `ShopAssetScreen.tsx`, RootNav registration, `gestureEnabled:false`, FeedbackFAB mount | **Dead** — no pushed screen. |
| §4.4 Matches long-press row | **Dropped from the build** (secondary entry, future option; give-side guard still binds if revived). |
| `ShopPositionPicker.tsx` (W2) | Survives; folds into the strip's Same-value pane. |
| §5.2 `record_elo` + `server.py` rows in §10 | **Void** (ruling A). W1 backend diff: **zero**. |
| `shop_opened` props | `source` domain becomes `'more_offers'` (+ chooser re-emit); add `give_count: int`. Still INTENT. |
| `shop_mode_selected`, `shop_positions_selected`, `shop_dismiss_undone` | Unchanged; `screen` prop `'Trades'`. |
| File ownership §10 | `TradesScreen.tsx` moves from "NOT touched (#402's)" to **owned by this joint item** — the contention dissolved with the merge of the two items. |
| Open design calls | (a) give-side label "More offers" vs unchanged — **specced: relabel**; (b) chooser vs old-behavior fallback when give>1 — **specced: chooser**; (c) receive-side shop ("shop their player") — out of scope, noted for a future item. |

## 1. Endpoint inventory

| Method | Path | Status | Cite | #403 changes it? |
|---|---|---|---|---|
| POST | `/api/trades/asset-ideas` | **EXISTS** | `backend/server.py:12024`; impl `backend/trade_service.py:4982`; docs `docs/api-reference.md:234` | **yes** — one optional request field (§2), W2 |
| POST | `/api/trades/queue` | **EXISTS** | `backend/server.py:13027`; docs `docs/api-reference.md:239` | **yes** — one optional request field (§5.2), pending O-1 |
| POST | `/api/trades/swipe` | **EXISTS** | `backend/server.py:12527`; docs `docs/api-reference.md:238` | **no** — #403 is a new caller of the shipped FB-46 path (§6) |
| POST | `/api/events` | **EXISTS** | `docs/api-reference.md:797` | **no** — 4 new event *names* only (§8) |
| POST | `/api/feature-flags/reload` | **EXISTS** | `docs/config-reference.md` | **no** — the kill switch (§7) |

**No NEW endpoints.** If a build agent finds itself adding a route, it has left
the spec.

## 2. `POST /api/trades/asset-ideas` — the `swap_positions` field

**Wave W2.** Route body parse: `backend/server.py:12078-12092`.

### 2.1 Request

```jsonc
{
  "asset_id":           "string",              // required, unchanged
  "direction":          "give" | "receive",    // default "give", unchanged
  "league_id":          "string?",             // unchanged
  "fairness_threshold": 0.50,                  // float?, unchanged
  "opponent_user_id":   "string?",             // #250, unchanged

  // ── NEW (W2) ────────────────────────────────────────────────────────────
  "swap_positions":     ["RB", "TE"]           // string[] | null, OPTIONAL
}
```

**Type:** `list[str] | None`. Uppercase position tokens.
**Domain:** exactly `{"QB", "RB", "WR", "TE"}` — the shipped
`VALID_POSITIONS` set at `backend/server.py:18609`.

**Semantics:** it **replaces** the #198 same-position predicate for the
`lateral` group only. `upgrade` and `downgrade` are unaffected under every
value of this field. Absent, `null`, or `[]` ⇒ **byte-identical to today**.

### 2.2 Validation and error shapes

Checked in the route, before any service call, in this order. Cases 2–4 are
inserted immediately after the existing `direction` check at
`backend/server.py:12086-12087`.

| # | Condition | Response |
|---|---|---|
| 1 | key absent, `null`, or `[]` | treat as `None`; no error. `[]` means "no selection", not "no positions allowed" |
| 2 | not a `list` (note: `bool` is a subclass of `int`, not `list`, so `true` lands here — the #360 lesson at `server.py:17527`) | `400 {"error": "swap_positions must be an array"}` |
| 3 | any element is not a `str` | `400 {"error": "invalid_position", "value": <repr of the element, truncated to 32 chars>}` |
| 4 | any element, after `.strip().upper()`, is not in `VALID_POSITIONS` | `400 {"error": "invalid_position", "value": "<the normalized token>"}` |
| 5 | valid | normalize: `strip().upper()`, dedupe **preserving first-seen order**, pass as `list[str]` |

**Normalization is `strip().upper()`, so `" rb "` is accepted as `"RB"`.**

**`"PICK"` is rejected** (case 4) even though `_AVOID_POSITIONS`
(`server.py:17368`) accepts it for #360. Reason, recorded so it does not read
as an oversight: the lateral predicate compares
`getattr(players.get(pid), "position", None)` (`trade_service.py:5094-5095`),
and pick-ness in this repo is resolved through the canonical `is_pick_asset`
*before* reading `position` precisely because generic pick rungs carry a
deliberately fake position (the #360 note in `config/features.json`). Admitting
`"PICK"` here would reintroduce the raw-`position` read #360 removed. A
similar-value *pick* pin is already served: a PICK pin sets
`pos_constrained = False` (`trade_service.py:5092`) and all three groups fall
back to pure value bands.

**Why a 400 and not a silent drop.** `_normalize_avoid_positions`
(`server.py:17370`) deliberately drops unknown tokens with a log line — but
that is a *persisted preference* where dropping preserves the user's other
choices. `swap_positions` is a per-request parameter whose only job is to
change what comes back; a silently dropped token returns the pin's own
position's laterals and looks exactly like a picker that did nothing. The
route's own house style is explicit 400s (`server.py:12084-12087`).

### 2.3 Response

**Unchanged.** No new response field, in either flag state. `groups.lateral`
simply contains different ideas.

### 2.4 Client body type

`mobile/src/api/trades.ts:386-392`, `fetchAssetIdeas`:

```ts
export async function fetchAssetIdeas(body: {
  league_id: string;
  asset_id: string;
  direction: 'give' | 'receive';
  fairness_threshold?: number;
  opponent_user_id?: string;
  /** #403 W2 — replaces the #198 same-position predicate for the `lateral`
   *  group ONLY. Omitted entirely when `trade.shop_asset` is off or the user
   *  has selected nothing, so the request body is byte-identical to today. */
  swap_positions?: string[];
}): Promise<AssetIdeasResponse>
```

The body is forwarded verbatim by `api.post` (`trades.ts:393`), so **the key
must be omitted, not sent as `undefined`/`[]`**, for the OFF state to be
byte-identical over the wire. Pinned by `check-shop-deck.js` A-6.

## 3. `TradeService._generate_asset_ideas_impl` — the predicate split

### 3.1 Signature

`backend/trade_service.py:4982-4999`. One kwarg appended after
`avoid_positions` (keyword-only — the function is `*`-marked at `:4984`):

```python
    swap_positions: list[str] | None = None,   # #403 W2 — replaces the #198
                                               # same-position predicate for
                                               # the `lateral` group only.
```

`generate_asset_ideas` (`:4976`) forwards `**kwargs` and needs no change.

### 3.2 The predicate — read this twice

The helper goes beside `_same_pos` (`trade_service.py:5094-5095`):

```python
        _swap = {str(p).upper() for p in (swap_positions or ())}

        def _lateral_pos_ok(pid: str) -> bool:
            """#403 — which counterparts may fill the LATERAL band.

            Empty selection  ⇒ #198 verbatim (the pin's own position).
            Non-empty        ⇒ the user's set REPLACES it. Never a filter over
            _same_pos's results: `lateral` is already hard-locked to the pin's
            position, so intersecting the two is empty for every position but
            the pin's — a control that always shows "nothing found".
            """
            if not _swap:
                return _same_pos(pid)
            return getattr(players.get(pid), "position", None) in _swap
```

**The trap.** The shipped gate is **one predicate covering two bands**:

```python
# backend/trade_service.py:5205  (direction == "give")
if pos_constrained and not _same_pos(c) and vc >= lo:
    continue
```

`vc >= lo` is `lateral ∪ upgrade`. Substituting `_lateral_pos_ok` for
`_same_pos` in place would widen **`upgrade`** too — which Q-D forbids. The
bands must be split first:

```python
# give — REPLACES the single line at :5205
if pos_constrained and not _same_pos(c) and vc > hi:
    continue                      # Upgrade band — #198 verbatim, never widened
if pos_constrained and lo <= vc <= hi and not _lateral_pos_ok(c):
    continue                      # Lateral band — swap_positions applies HERE
```

```python
# receive — REPLACES the single line at :5291
if pos_constrained and not _same_pos(g) and vg < lo:
    continue                      # Upgrade headliner — #198 verbatim
if pos_constrained and lo <= vg <= hi and not _lateral_pos_ok(g):
    continue                      # Lateral band — swap_positions applies HERE
```

(The receive direction's bands are mirrored: `vg < lo` = tier UP into the pin,
`lo ≤ vg ≤ hi` = lateral, `vg > hi` = downgrade. So `vg <= hi` in the shipped
line is likewise `upgrade ∪ lateral`.)

### 3.3 Equivalence proof — `swap_positions` absent

With `_swap` empty, `_lateral_pos_ok ≡ _same_pos`. Worked at every boundary
with `band = 0.10`, `v_pin = 100.0` ⇒ `lo = 90.0`, `hi = 110.0`
(`trade_service.py:5083-5084`), for a **cross-position** candidate
(`_same_pos` false) with `pos_constrained` true:

| `vc` | shipped `vc >= lo` | new (A) `vc > hi` | new (B) `lo ≤ vc ≤ hi ∧ ¬ok` | shipped | new | same? |
|---|---|---|---|---|---|---|
| 85.0 | `85 ≥ 90` = F | `85 > 110` = F | `90 ≤ 85` = F | kept | kept | ✅ |
| 90.0 (= lo) | T | `90 > 110` = F | T ∧ T = T | skipped | skipped | ✅ |
| 100.0 | T | F | T | skipped | skipped | ✅ |
| 110.0 (= hi) | T | `110 > 110` = F | `90 ≤ 110 ≤ 110` = T | skipped | skipped | ✅ |
| 120.0 | T | T | — | skipped | skipped | ✅ |

For a **same-position** candidate: shipped `not _same_pos(c)` = F ⇒ never
skipped; (A) same conjunct = F; (B) `not _lateral_pos_ok(c)` = `not True` = F.
Never skipped in either. ✅

Receive mirror, same constants, cross-position `g`:

| `vg` | shipped `vg ≤ hi` | new (A′) `vg < lo` | new (B′) `lo ≤ vg ≤ hi ∧ ¬ok` | shipped | new | same? |
|---|---|---|---|---|---|---|
| 85.0 | T | `85 < 90` = T | — | skipped | skipped | ✅ |
| 90.0 | T | `90 < 90` = F | T | skipped | skipped | ✅ |
| 100.0 | T | F | T | skipped | skipped | ✅ |
| 110.0 | `110 ≤ 110` = T | F | `90 ≤ 110 ≤ 110` = T | skipped | skipped | ✅ |
| 130.0 | `130 ≤ 110` = F | F | `90 ≤ 130 ≤ 110` = F | kept | kept | ✅ |

**Byte-identical at every boundary in both directions.**

### 3.4 Worked example — `swap_positions` present

Pin = a WR, `v_pin = 100.0`, `lo/hi = 90/110`, `swap_positions = ["RB","TE"]`.

| Candidate | pos | `vc` | (A) `¬same ∧ vc>hi` | (B) `in band ∧ ¬_lateral_pos_ok` | outcome |
|---|---|---|---|---|---|
| RB | RB | 100.0 | `100>110` = F | in band; `RB ∈ {RB,TE}` ⇒ ok ⇒ ¬ok = F | **kept → `_emit(..., "lateral")`** |
| TE | TE | 95.0 | F | ok ⇒ F | **kept → lateral** |
| QB | QB | 100.0 | F | in band; `QB ∉ {RB,TE}` ⇒ ¬ok = T | **skipped** |
| WR (the pin's own position) | WR | 100.0 | F | in band; `WR ∉ {RB,TE}` ⇒ ¬ok = T | **skipped** |
| RB | RB | 130.0 | `¬same_pos(RB)` = T ∧ `130>110` = T | — | **skipped — upgrade stays WR-only** ✅ Q-D |
| WR | WR | 130.0 | `¬same_pos` = F | not in band | **kept → upgrade** (unchanged) |

Note row 4: with a non-empty selection the pin's **own** position is excluded
from `lateral` unless the user selects it. That is what "replaces" means, and
the client must therefore render the pin's position as a selectable chip
(§4.3) so "WR laterals plus RB laterals" is expressible.

### 3.5 Interaction with #360 `avoid_positions`

**No new code. An avoided position wins, structurally.** The give-direction
receive pool is built with `avoid_ok(p, players, _avoid)` at
`trade_service.py:5199` — an exclusion **at source**, so an avoided asset never
enters `pool` and `_lateral_pos_ok` never sees it.

| `avoid_positions` | `swap_positions` | `groups.lateral` |
|---|---|---|
| `[]` | `["RB","TE"]` | RB + TE laterals |
| `["RB"]` | `["RB","TE"]` | TE laterals only |
| `["RB"]` | `["RB"]` | **empty — honest, never an override** ✅ D-360-3(b) |

**Client rule:** `ShopPositionPicker` must not *offer* a position the user
avoids. **Server rule:** the server must not depend on the client doing so —
the table above holds either way. (`trade.avoid_positions` is `false` in
`config/features.json` today, so this is latent.)

### 3.6 Not a gate knob

`swap_positions` is a **semantic**, exactly as #198 states at
`trade_service.py:5030-5037`. The #189 relaxed refill re-evaluates candidates
against `min(fairness_threshold, relaxed_fairness_threshold)`
(`trade_service.py:5086`) — it widens the **fairness band** only and must never
widen the position set. Since `_lateral_pos_ok` is applied at pool-scan time,
before `_eval`, the refill structurally cannot relax it. **No code change is
needed to preserve this; a build agent must not add one.**

## 4. Mobile: the shop surface

### 4.1 Route — `mobile/src/navigation/RootNav.tsx`

Two edits. **Registered unconditionally**, per the house rule stated in-file at
`RootNav.tsx:762-766`: the flag gates the entry point, not the route, so an
in-flight push survives a flag revalidation instead of unmounting under the
user.

```ts
// RootStackParamList (near :139)
ShopAsset: {
  assetId:   string;
  assetName: string;
  leagueId:  string;
  /** analytics + back-target only; never branches behavior */
  source:    'matches' | 'deck' | 'calculator';
};
```

```tsx
<Stack.Screen
  name="ShopAsset"
  component={ShopAssetScreen}
  options={({ navigation }) => ({
    headerShown: true,
    title: 'Shop a player',
    headerTitle: () => <HeaderTitle>Shop a player</HeaderTitle>,
    headerStyle: { backgroundColor: ink.ink0 },
    headerTintColor: chalk.base,
    headerBackVisible: false,
    headerLeft: () => (
      <HeaderBack testID="shop.back-btn" onPress={() => /* same canGoBack
        pattern as Receipts, RootNav.tsx:774-782 */ null} />
    ),
    // #403 — the pager is a horizontally paging FlatList. iOS's interactive
    // pop gesture is a left-edge horizontal drag and would intercept a page
    // back. The header chevron is the back control.
    gestureEnabled: false,
  })}
/>
```

`gestureEnabled: false` is **required**, not stylistic. It is the one real
gesture conflict in the design, and it is resolved by configuration rather
than by arbitration.

### 4.2 `mobile/src/components/ShopCardPager.tsx` — **NEW**

```ts
interface ShopCardPagerProps {
  /** The ONE selected group, flattened and ordered as the server returned it. */
  ideas: AssetIdea[];
  leagueId: string;
  /** Controlled: the screen owns the index so undo can restore it. */
  index: number;
  onIndexChange: (i: number) => void;
  onLike:    (idea: AssetIdea) => void;
  onDismiss: (idea: AssetIdea) => void;
  /** Per-idea, keyed by assetIdeaKey — disables the pair while in flight. */
  busyKey: string | null;
}
```

Implementation contract, binding on the build agent:

- **One `FlatList`**, `horizontal`, `pagingEnabled`, `showsHorizontalScrollIndicator={false}`,
  `keyExtractor={(i) => assetIdeaKey(i)}` (imported from
  `mobile/src/utils/ideaToCard.ts:27` — **do not re-implement it**),
  `getItemLayout` from the measured card width so `scrollToIndex` is exact.
- **No `Gesture.Pan`, no `PanResponder`, no `react-native-gesture-handler`
  import anywhere in this file or `ShopAssetScreen.tsx`.** Pinned by
  `check-shop-deck.js` A-7.
- `onMomentumScrollEnd` → `onIndexChange(Math.round(x / width))`. Deriving the
  counter from scroll offset rather than from a second piece of state is what
  makes A-8 ("the counter reads the same list the pager indexes") checkable.
- Card body: `<TradeCard data={ideaToCard(idea, leagueId)} hideMatchStrength />`
  — the same call `FeaturedTradeWindow.tsx:92` makes. `TradeCard` is **#402's
  file and is imported, never edited**; it is mounted **without** a
  `disposition` prop, so it renders none of its own like/pass controls
  (`TradeCard.tsx:773`, `:803`) and #403's footer row is the only decision
  surface. This is also what keeps `check-single-pin-actions.js` assertions
  1–5 untouched.

### 4.3 `mobile/src/screens/ShopAssetScreen.tsx` — **NEW**

State:

```ts
const shopOn = useFlag('trade.shop_asset');           // read for degrade only
const [mode, setMode] = useState<ShopMode>('tier_up');
const [positions, setPositions] = useState<Set<Pos>>(new Set());  // W2
const [index, setIndex] = useState(0);
const pendingDismissRef = useRef<{
  idea: AssetIdea;
  key: string;                       // assetIdeaKey(idea)
  restoreIndex: number;
  timer: ReturnType<typeof setTimeout>;
} | null>(null);
```

`type ShopMode = 'tier_up' | 'tier_down' | 'same_value'`, mapped to server
groups by **one exported constant**, so the mapping cannot drift:

```ts
export const SHOP_MODE_GROUP = {
  tier_up:    'upgrade',
  tier_down:  'downgrade',
  same_value: 'lateral',
} as const;
```

Fetch: `useQuery(['shop-ideas', leagueId, assetId, swapKey], …)` calling
`fetchAssetIdeas({ league_id, asset_id: assetId, direction: 'give',
...(sendPositions ? { swap_positions: [...positions] } : {}) })`, where
`swapKey` is the sorted, joined selection so a picker change refetches and a
mode change does **not** (all three groups arrive in one response).
`setIndex(0)` on every successful fetch.

Layout, top to bottom (Chalkline — `docs/design/design-system.md`,
`docs/design/components.md`):

| Row | Construction |
|---|---|
| Pin identity | `PositionChip size="sm"` + `type.title` name + `type.bodySm` team/age. Mirrors the `PlayerContextMenu` header (`PlayerContextMenu.tsx:74-84`). |
| Mode selector | 3 chips, `PositionTabs`/subnav-pill construction (`components.md` § Navigation): 1px `--line` hairline, `radii.xs`, active = **ice** border + `--ink-2` well + chalk text. Ice because a mode chip is an action. Labels **"Tier up" · "Tier down" · "Same value"** (`reconciliation-log.md` arbitration). |
| Position picker (W2) | Visible **only** when `mode === 'same_value'`. Multi-select `PositionChip`s over `{QB,RB,WR,TE}`, ordered QB→RB→WR→TE, colors from `posColor` — a **data encoding governed by `docs/cross-client-invariants.md`, never restyled**. Selected = filled well + ice ring. The pin's own position is present and selectable (§3.4 row 4). Any position in `avoid_positions` is **omitted** (§3.5). Empty selection = the shipped #198 behavior and the picker shows a `type.bodySm` chalk-dim hint saying so. |
| Counter | `<TickLabel>{index + 1} / {ideas.length}</TickLabel>` — `label` type, chalk-dim. **Not flare**: flare is informational highlight and never sits on or beside an actionable control (`design-system.md` § Ice/Flare division of labor). |
| Pager | `ShopCardPager` |
| Decision row | Two `Button`s. Dismiss = `variant="ghost"`, `x` glyph, chalk-dim. Like = `variant="primary"` (**ice** fill, `on-ice` text), `check` glyph. Both from `components/chalkline`. |

**Empty state.** A group with zero ideas renders an honest empty — never a
fabricated card and never a spinner that never ends: `type.body` "No {mode
label} ideas for {name} right now." plus, when `mode === 'same_value'` and
`positions.size > 0`, a second `type.bodySm` chalk-dim line naming the
selection ("You picked RB and TE"). Precedent: the intent-mode toast
(`trades.intent_modes`, "No consolidation trades found right now.").

**Degrade.** `trade.asset_ideas` is a **prerequisite**: with it `false` the
route 404s (`server.py:12069`). The entry point must not render, so
`shopEnabled = useFlag('trade.shop_asset') && useFlag('trade.asset_ideas')`
lives in **one** exported helper the hosts call, not duplicated per host.
Should the screen be reached anyway (an in-flight push across a flag reload),
it renders the same honest empty rather than a spinner.

**FeedbackFAB (#188).** A root-stack push ⇒ the screen mounts
`<FeedbackFAB activeScreen="ShopAsset" aboveTabBar={false} />`. The decision
row is **not** a pinned bottom bar (it scrolls with the content), so
`setPinnedBottomBarHeight` is **not** called. If a build agent pins the row,
it must call it (`CLAUDE.md` §Conventions).

### 4.4 Entry point — `mobile/src/screens/MatchesScreen.tsx`

> **RULED 2026-08-27 — SUPERSEDED as the front door.** The operator ruled
> shop and #402's "more offers" are one concept: the primary entry is the
> **more offers** control, conditioned on the give side's player count, and
> #402/#403 are planned as one experience. Whether this long-press row
> survives as a secondary entry is open; if it does, it is guarded to the
> give side. See `rulings-2026-08-27.md` §B–C.

One `PlayerMenuAction` pushed into the array `menuActionsFor` returns
(`MatchesScreen.tsx:1568` (mounted at `:1544`)), inside a truthy-flag branch:

```ts
...(shopEnabled ? [{
  key: 'shop',
  label: 'Shop this player',
  hint: 'See tier-up, tier-down and same-value offers',
  onPress: () => {
    setMenuTarget(null);
    navigation.navigate('ShopAsset', {
      assetId: t.player.id, assetName: t.player.name,
      leagueId, source: 'matches',
    });
  },
}] : []),
```

testID defaults to `player-menu.shop` (`PlayerContextMenu.tsx:38-40`).
**Flag off ⇒ the array is unchanged and `PlayerContextMenu` maps an identical
list** (`PlayerContextMenu.tsx:87`). Pinned by `check-shop-deck.js` A-5.

**Not taken by #403:** the same row on `TradesScreen`'s deck menu
(`TradesScreen.tsx:7726`) — #402 owns that file. #403 supplies the four lines
above as a patch for #402's agent. See `prd.md` §Open O-2.

## 5. The like path

### 5.1 Client

`mobile/src/utils/queueCalcTrade.ts` — **reused, not reimplemented**, so the
six refusal lines (`queueRefusalLine`, `:31-49`) cannot drift between the
calculator's ✓ and the shop card.

```ts
await queueCalcTrade({
  leagueId,
  opponent: { userId: idea.counterparty_user_id, name: idea.counterparty_username },
  giveIds:    idea.give_player_ids,
  receiveIds: idea.receive_player_ids,
  screen: 'ShopAsset',
  recordElo: false,          // #403 — pending O-1
});
```

`recordElo?: boolean` is threaded to `queueTradeForOpponent`
(`mobile/src/api/trades.ts:572`) and included in the body **only when
`false`**, so every existing caller's request is byte-identical.

**No new analytics event for the like.** `calc_trade_queued` is reused with
`screen: 'ShopAsset'` — the D-158 precedent verbatim (*"the SAME shared
helpers both hosts call, with the screen name as the only difference"*).
Zero taxonomy change for this path.

**Optimistic UI:** none. The ✓ is a real network answer with six honest
refusal reasons; the button disables (`busyKey`) until the response lands, and
the toast is `queueCalcTrade`'s returned descriptor. `already_queued: true`
renders the same success copy — the offer *is* live.

### 5.2 Server — `record_elo` (pending O-1)

> **RULED 2026-08-27 — VOID.** The operator chose option (B): the like
> **does** move the Elo board. `record_elo` is not built; `/api/trades/queue`
> is consumed as-is, zero backend diff. See `rulings-2026-08-27.md` §A.
> This section is kept for the record only.

`backend/server.py:13029`, `queue_trade_for_opponent`. **Additive, optional,
default = today.**

```jsonc
{
  "league_id":          "string",    // required, unchanged
  "opponent_user_id":   "string",    // required, unchanged
  "give_player_ids":    ["string"],  // required non-empty, unchanged
  "receive_player_ids": ["string"],  // required non-empty, unchanged
  "record_elo":         true         // NEW, bool, optional, DEFAULT true
}
```

Parse beside the existing field reads (`server.py:13066-13084`):

```python
record_elo = body.get("record_elo")
record_elo = True if record_elo is None else bool(record_elo)
```

Two call sites become conditional. Nothing else in the route changes.

```python
# server.py:13196 — was unconditional
if record_elo:
    service.record_trade_signal(
        winner_ids = card.receive_player_ids,
        loser_ids  = card.give_player_ids,
        decision   = "like",
        fit_mult   = fit_mult,
    )
```

```python
# server.py:13212-13219 — was `if wrote_decision:`
if wrote_decision and record_elo:
    save_trade_swipes(...)
```

**What still runs when `record_elo` is false** — everything that makes the
like a *real offer*: `_calc_queue_denied` (`:12894`), the mirror predicate
`_calc_queue_mirror_reason` (`:12929`), `_calc_queue_trade_id` (`:12907`),
the `find_live_trade_like` idempotency probe (`:13159`),
`_reconstruct_swipe_card` + `record_decision`, **`save_trade_decision`**, and
the `trade_proposed` event with `source: "calc_queue"`. Likes-you eligibility
is unaffected because `find_live_trade_like` (`backend/database.py`, docstring
verified) and the injector both read `trade_decisions`, which is still
written.

**Response shape: unchanged.** `{queued, already_queued, trade_id}` /
`{queued: false, reason, detail?}`. `CALC_QUEUE_REASONS` (`server.py:12884`)
is unchanged — a closed cross-client enum, and #403 adds nothing to it.

**Prerequisite:** `calc.merged_layout` must stay `true`. `_calc_queue_denied`
404s `feature_disabled` when it is off (`server.py:12894-12905`), so flipping
it dark **also disables the shop card's like**. Stated in `scope.md` §2 and in
the TestFlight checklist.

### 5.3 Rejected alternative, recorded because it is provably exact

Passing `fit_mult = 0.0` instead of skipping the writes is *also* exact, and
`_bakeoff.elo_freeze_mult` (`backend/bakeoff_runner.py:373`) proves K=0 is an
exercised path. Worked against the shipped formula
(`ranking_service.py:1531-1538`), like on `give=[A@1500]`, `receive=[B@1600]`,
winner `w=B`, loser `l=A`, so `ra = ratings[B] = 1600`, `rb = ratings[A] = 1500`:

```
ea       = 1 / (1 + 10^((rb − ra)/400)) = 1 / (1 + 10^(−0.25))
10^(−0.25)                              = 0.5623413
ea                                      = 1 / 1.5623413 = 0.640065
1 − ea                                  = 0.359935

normal like  k = trade_k_like(8.0) × 1.0 = 8.0
  ΔB = 8.0 × 0.359935            = +2.8795
  ΔA = 8.0 × (0 − 0.359935)      = −2.8795

k = 0
  ΔB = 0 × 0.359935 = 0.0  →  `after == before` → early return  (:1500-1501)
  ΔA = 0 × (−0.359935) = 0.0 → same
```

`_apply`'s `track` argument is `False` for trade swipes (`:1536`, `:1538`), so
no comparison bookkeeping moves either. Exact in memory **and** on DB replay
(`_compute_elo` reads `k_factor` off the row at `:1208`).

**Rejected anyway:** it writes `swipe_decisions` rows with `k_factor = 0.0`.
That table **is** the Elo ledger, and a zero row is a lie about what happened
that a future analyst would count as a swipe. The offer's record belongs in
`trade_decisions`, where it is written. (`hld-delta.md` §3 D-5.)

## 6. The dismiss path and the undo contract

### 6.1 The full contract, stated once

| Question | Answer |
|---|---|
| **What does dismiss do?** | Full deck-pass semantics (Q-B): Elo at `trade_k_pass` (4.0, `ranking_service.py:58`) and the permanent dismiss-cooldown. |
| **What does undo reverse?** | **Nothing — because nothing has happened yet.** The POST is *held* for `UNDO_HOLD_MS`; Undo clears the timer and the request is never sent. |
| **Is the copy honest?** | Unconditionally. "Dismissed" is the optimistic UI state; the write is pending; "Undo" cancels it. No partial-undo caveat is needed, and none is written. |
| **Window** | `UNDO_HOLD_MS = 5000`, the value shipped in all three precedents (`TradesScreen.tsx:228`, `MatchesScreen.tsx:67`, `TradeCalculatorScreen.tsx:67`). The toast's `holdMs` is the **same constant**, so the affordance and the commit expire together (`Toast.tsx:51-66`). |
| **At most one pending** | Yes. A second dismiss, a mode change, a refetch, a navigation away, or unmount **flushes** the pending one first, then arms its own. Ordering and the at-most-one invariant are the same rules `pendingPassRef` states at `TradesScreen.tsx:2158-2162`. |
| **After the window** | The POST fires. There is no un-dismiss endpoint and #403 does not add one. |

### 6.2 Client mechanics — `ShopAssetScreen`

```ts
function flushPendingDismiss() {
  const p = pendingDismissRef.current;
  if (!p) return;
  pendingDismissRef.current = null;
  clearTimeout(p.timer);
  dismissMutation.mutate(p.idea);          // the real POST
}
const flushPendingDismissRef = useRef(flushPendingDismiss);
flushPendingDismissRef.current = flushPendingDismiss;   // latest-instance ref

function undoDismiss() {
  const p = pendingDismissRef.current;
  if (!p) return;
  pendingDismissRef.current = null;
  clearTimeout(p.timer);                    // ← the entire undo
  setLocallyRemoved((s) => { const n = new Set(s); n.delete(p.key); return n; });
  setIndex(p.restoreIndex);
  track('shop_dismiss_undone', { mode }, 'ShopAsset');
}

function handleDismiss(idea: AssetIdea) {
  haptics.selection();
  const key = assetIdeaKey(idea);
  if (pendingDismissRef.current?.key === key) return;   // double-fire guard
  flushPendingDismiss();                                // at-most-one
  const restoreIndex = index;
  setLocallyRemoved((s) => new Set(s).add(key));        // optimistic removal
  setIndex((i) => Math.min(i, Math.max(0, visibleCount - 2)));
  pendingDismissRef.current = {
    idea, key, restoreIndex,
    timer: setTimeout(() => flushPendingDismissRef.current(), UNDO_HOLD_MS),
  };
  setToast({ msg: 'Dismissed', tone: 'success', holdMs: UNDO_HOLD_MS,
             action: { label: 'Undo', onPress: undoDismiss } });
}

// Leaving the screen ends the window; the disposition must not be lost.
useEffect(() => () => { flushPendingDismissRef.current(); }, []);
```

The latest-instance ref and the unmount flush are not optional polish: they are
the two things `TradesScreen.tsx:2385-2390` and `:2444-2450` exist for, and
without them the pending write closes over a stale mutation or is silently
dropped on navigation.

### 6.3 The network call — an existing route, no new code

```ts
// mobile/src/api/trades.ts — the SHIPPED swipe caller, unchanged
await swipeTrade({ card: ideaToCard(idea, leagueId), decision: 'pass' });
```

`ideaToCard` (`mobile/src/utils/ideaToCard.ts:52`) already produces every field
FB-46 needs, including a stable identity — **imported, never edited**:

```ts
trade_id: idea.trade_id || `asset-idea:${assetIdeaKey(idea)}`
//                          ^ assetIdeaKey = `${counterparty}.${give}-${receive}`  (:27)
```

Asset ideas carry no server `trade_id` (`trades.ts:317-322` — the field is
populated only by `/api/trades/fair-packages`), so the synthetic id is used.
It is deterministic per (counterparty, give set, receive set), which is what
makes a re-dismiss one row rather than two.

**Server effects, all shipped, none modified** — `backend/server.py:12527`:

| Effect | Cite |
|---|---|
| Unknown `trade_id` ⇒ rebuild from the echoed context (FB-46) | `_reconstruct_swipe_card`, `:12493`; called at `:12562` |
| Elo: `record_trade_signal(winner=give, loser=receive, 'pass')` | `:12608-12613` |
| Persisted at `trade_k_pass × fit_mult` | `:12615-12616`, `save_trade_swipes` `:12680` |
| **Dismiss-cooldown, bound to every live service immediately (D-067)** | `:12640-12653` — key = `(frozenset(give_ids), frozenset(receive_ids))` |
| `trade_decisions` row ⇒ the cooldown survives restart | `save_trade_decision` `:12670` |
| Server event `match_swiped` | `:12685` |

`fit_congruence_mult` returns **1.0** for a card with no `lane_shift`
(`server.py:12578-12579` and the D-060 note at `:12565-12577`) — an asset-idea
card carries none, exactly like an FB-46 reconstruction, so the K is plain
`trade_k_pass`.

**Error handling.** A failed POST after the window closed refetches the group
so the card reappears rather than staying invisibly un-dismissed — the S-9
honesty rule `MatchesScreen.tsx:407-411` states for the same shape.

### 6.4 A discrepancy the operator should see

`feedback.decline_reasons` is **`true`**, so today's deck ✕ is replaced by
reason tiles routing to `POST /api/trades/pass-reason`, where
`pass_reason_elo_suppression` (default `1.0` = ON) writes the Elo signal
**only** on a `value_giving` answer (`docs/api-reference.md:240`). The shop
dismiss going through `/api/trades/swipe` therefore moves Elo **more often**
than the live deck pass does. Specced as ruled; raised in `prd.md` §Open O-3.

## 7. Flag contract

**Key: `trade.shop_asset`.** Ships **`false`**. Namespace matches the sibling
it extends (`trade.asset_ideas`), not the presentation namespace `trades.*`.

Registration is four places, all required or the key reads as permanently false
(the D-035 lesson recorded in `docs/feedback/items/318-awaiting-dismiss/scope.md`):
`config/features.json` · `backend/feature_flags.py` `FLAG_KEYS` (near
`ux.swipe_undo`, `:306`) · `docs/config-reference.md` · the client
`useFlag('trade.shop_asset')`. Test fixtures under
`backend/tests/fixtures/flags/` get the key too.

| State | Meaning, precisely |
|---|---|
| **OFF (shipped default)** | No entry-point row is pushed into any `actions` array, so `PlayerContextMenu` maps an **identical** list (`PlayerContextMenu.tsx:87`). `ShopAssetScreen` is registered but never navigated to. `swap_positions` is **omitted from the request body**, so `POST /api/trades/asset-ideas` receives a byte-identical body, `body.get("swap_positions")` is `None`, and `_generate_asset_ideas_impl` runs today's path (§3.3 proves the predicate split is equivalent). `record_elo` is likewise omitted, so `/api/trades/queue` behaves exactly as today for every existing caller. `AssetIdeasPanel`, `FeaturedTradeWindow`, `TradeCard`, `ideaToCard` and the single-pin state machine are untouched **in the source**, not merely gated. |
| **ON** | The `Shop this player` row renders on its host(s). The screen opens with the mode selector, the W2 picker on `same_value`, the pager + `1 / X`, and the like/dismiss pair. `swap_positions` may be sent. The four new events emit. |

**Prerequisites:** `trade.asset_ideas` (`true`) — 404 without it;
`ux.player_context_menu` (`true`) — the entry-point host;
`calc.merged_layout` (`true`) — the like's route 404s without it;
`ux.swipe_undo` is **not** a prerequisite (#403's undo is its own
`pendingDismissRef`, matching the #318 precedent of shipping the affordance
unconditionally).

**Kill switch:** this key alone, via `POST /api/feature-flags/reload` — no
deploy, no client build.

**Graduation:** the TestFlight checklist in `prd.md` §Test plan, run by the
operator, logged in `living-memory/TEST_LEDGER.md`.

## 8. Analytics interfaces

Four **NEW** client events. Registered in `backend/analytics_taxonomy.py`
`ALLOWED_CLIENT_EVENTS` (`:38`) **and** `CLIENT_EVENT_PROPS` (`:833`) **in the
same commit as the emitter** (`CLAUDE.md` §Common tasks). Unregistered props
are silently dropped behind a 200 — `plan.md` R-9.

| Event | Props (closed set) | Fires when | Client |
|---|---|---|---|
| `shop_opened` | `{asset_position: "QB"\|"RB"\|"WR"\|"TE", source: "matches"\|"deck"\|"calculator"}` | `ShopAssetScreen` mounts | mobile |
| `shop_mode_selected` | `{mode: "tier_up"\|"tier_down"\|"same_value", n_ideas: int}` | a mode chip is tapped | mobile |
| `shop_positions_selected` | `{n: int}` (**count only** — the selected set is user preference data and would raise prop cardinality for no analytic gain) | the W2 picker's selection settles into a fetch | mobile |
| `shop_dismiss_undone` | `{mode}` | Undo is tapped inside the window | mobile |

**`NON_INTENT_EVENTS` (`backend/analytics_queries.py:63`) is unchanged, and
that is the answer, not silence.** Intent is a **deny-list** (`INTENT_EVENTS =
(SERVER_FIRED | ALLOWED_CLIENT) − NON_INTENT`, `:335`), so all four are INTENT
by default. Each is a deliberate tap, including `shop_opened` (a menu row
press, not an impression) and `shop_dismiss_undone` (whose sibling
`swipe_undone` is likewise **not** in the non-intent set — verified:
`grep -n swipe_undone backend/analytics_queries.py` returns nothing). Adding
any of them to `NON_INTENT_EVENTS` would be wrong.

**Reused, no registration needed:** `calc_trade_queued` (`:619`, props
`{queued, reason}` at `:1503`) for the like; the server-fired `match_swiped`
for the dismiss.

## 9. testIDs

Grammar: domain ids, never list indexes (`utils/ideaToCard.ts:23-27`).

| testID | Element |
|---|---|
| `player-menu.shop` | the entry-point row (default from `PlayerContextMenu.tsx:38-40`) |
| `shop.back-btn` | header back |
| `shop.mode.tier-up` · `shop.mode.tier-down` · `shop.mode.same-value` | mode chips |
| `shop.pos.<POS>` | W2 picker chips (`QB`/`RB`/`WR`/`TE`) |
| `shop.counter` | the `1 / X` TickLabel |
| `shop.pager` | the FlatList |
| `shop.card.<assetIdeaKey>` | one card |
| `shop.like-btn` · `shop.dismiss-btn` | the decision pair |
| `shop.empty` | the honest empty state |

`mobile/scripts/testid-lint.sh` cross-checks **flow → source** only, and
`mobile/.maestro/` is frozen under D-056 — so it will pass these trivially.
It is a ship gate, not evidence for #403; the real pin is
`check-shop-deck.js`.

## 10. Function-level touch points

| File | Function / symbol | Change | Wave |
|---|---|---|---|
| `backend/server.py:12078-12092` | `asset_trade_ideas` body parse | parse + validate `swap_positions` (§2.2) | W2 |
| `backend/server.py:12160` area | the `generate_asset_ideas(...)` kwargs | pass `swap_positions=…` | W2 |
| `backend/server.py:13066` area | `queue_trade_for_opponent` body parse | parse `record_elo` | W1 (O-1) |
| `backend/server.py:13196` | `service.record_trade_signal(...)` | wrap in `if record_elo:` | W1 (O-1) |
| `backend/server.py:13212` | `if wrote_decision:` | `if wrote_decision and record_elo:` | W1 (O-1) |
| `backend/trade_service.py:4982-4999` | `_generate_asset_ideas_impl` signature | `+ swap_positions` kwarg | W2 |
| `backend/trade_service.py:5094-5095` | beside `_same_pos` | `+ _swap`, `+ _lateral_pos_ok` | W2 |
| `backend/trade_service.py:5205` | the give lateral/upgrade gate | split into two (§3.2) | W2 |
| `backend/trade_service.py:5291` | the receive mirror | split into two (§3.2) | W2 |
| `backend/analytics_taxonomy.py:38, :833` | `ALLOWED_CLIENT_EVENTS`, `CLIENT_EVENT_PROPS` | + 4 events | W1 |
| `backend/analytics_queries.py:63` | `NON_INTENT_EVENTS` | **unchanged, deliberately** (§8) | — |
| `mobile/src/navigation/RootNav.tsx:139` area | `RootStackParamList` | `+ ShopAsset` | W1 |
| `mobile/src/navigation/RootNav.tsx` | the `<Stack.Navigator>` body | `+ <Stack.Screen name="ShopAsset">` (§4.1) | W1 |
| `mobile/src/screens/ShopAssetScreen.tsx` | whole file | **NEW** | W1 |
| `mobile/src/components/ShopCardPager.tsx` | whole file | **NEW** | W1 |
| `mobile/src/components/ShopPositionPicker.tsx` | whole file | **NEW** | W2 |
| `mobile/src/api/trades.ts:386-392` | `fetchAssetIdeas` body type | `+ swap_positions?` | W2 |
| `mobile/src/api/trades.ts:572` | `queueTradeForOpponent` args | `+ recordElo?`, sent only when `false` | W1 (O-1) |
| `mobile/src/utils/queueCalcTrade.ts:53-70` | `queueCalcTrade` args | `+ recordElo?`, threaded | W1 (O-1) |
| `mobile/src/screens/MatchesScreen.tsx:1568` | `menuActionsFor` | `+` one flag-gated row (§4.4) | W1 |
| `mobile/src/components/CLAUDE.md` | component table | `+` two rows | W1 |
| `mobile/tests/check-shop-deck.js` | whole file | **NEW** | W1 |
| `mobile/package.json` scripts | | `+ "test:shop-deck"` | W1 |
| `backend/tests/test_asset_ideas.py` | | `+` the §2/§3 cases | W2 |
| `backend/tests/test_shop_queue_elo.py` | whole file | **NEW** | W1 (O-1) |

**Imported, never edited** (#402's files): `mobile/src/utils/ideaToCard.ts`
(`ideaToCard`, `assetIdeaKey`), `mobile/src/components/TradeCard.tsx`,
`mobile/src/components/AssetIdeasPanel.tsx`,
`mobile/src/components/FeaturedTradeWindow.tsx`,
`mobile/tests/check-single-pin-actions.js`.
**Not opened at all:** `mobile/src/screens/TradesScreen.tsx`.
