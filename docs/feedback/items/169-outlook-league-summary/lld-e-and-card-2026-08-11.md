# #169 — LLD: frame E + card frame C

**Date:** 2026-08-11 · **Status:** planned · **rev 2** (post adversarial
review — 21 findings applied; reconciliation log in
[`prd-e-and-card-2026-08-11.md`](prd-e-and-card-2026-08-11.md) § Review log)
**Plan:** [`plan-e-and-card-2026-08-11.md`](plan-e-and-card-2026-08-11.md) ·
**HLD:** [`hld-e-and-card-2026-08-11.md`](hld-e-and-card-2026-08-11.md)

Line references are against `origin/main` @ `ab9368f` (2026-08-11) and drift
with rebases — anchor by symbol, not number.

---

## Table of Contents

- [§1 W1 — League Summary frame E](#1-w1--league-summary-frame-e)
- [§2 W2 — Card disposition move](#2-w2--card-disposition-move)
- [§3 W3 — Tests & flows](#3-w3--tests--flows)
- [§4 testID ledger](#4-testid-ledger)

---

## §1 W1 — League Summary frame E

### 1.1 New persisted hook — `mobile/src/state/outlookStrip.ts`

A **plain React hook + AsyncStorage** (NOT a zustand store — `useTradeQueue`
is zustand; the only part we borrow is its error-swallowing persist
contract):

```ts
// AsyncStorage key: `ftf_outlook_strip_${userId}` — user-scoped like
// useTradeQueue's `ftf_trade_queue_<user_id>` (useTradeQueue.ts:19), so two
// accounts on one device don't share strip state.
// Value: Record<string, true> — league_ids whose strip is EXPANDED.
// Absent key / absent league id = collapsed (the default). Collapsing
// deletes the league's entry rather than writing false — sparse record.
export function useOutlookStripExpanded(
  userId: string | null | undefined,
  leagueId: string | null | undefined,
): [boolean, (next: boolean) => void]
```

Hydrate on mount; optimistic local state; fire-and-forget writes with
swallowed errors (same posture as `useTradeQueue.ts`'s module-private
`persist()` at `:44`). `userId` comes from the same session store the screen
already reads. `@react-native-async-storage/async-storage` is already a
dependency (`mobile/package.json:26`, `^2.2.0`).

### 1.2 Mount-point change — `LeagueSummaryScreen.tsx:856-862`

```tsx
{oddsEnabled ? (
  outlookSupported ? (
    <OutlookStripAndSection query={outlookQuery} leagueId={leagueId} />
  ) : (
    <OutlookUnsupportedRow />
  )
) : null}
```

`leagueId` is in scope at the mount site (declared `:358`).
`OutlookStripAndSection` (new, same file, beside `SeasonOutlookSection`) owns
the strip/section switch so the mount site stays one expression.

### 1.3 Comparator extraction (the one section-internal change)

The projected-standings sort currently lives **inline** inside
`SeasonOutlookSection` (`:1801-1806`). W1 extracts it to a module-level
helper in the same file:

```ts
function orderOutlookTeams(teams: OutlookTeam[]): OutlookTeam[] // seed asc → playoff_pct desc → roster_id asc
```

…and the section calls it. **This is the only permitted change inside
`SeasonOutlookSection`, and it is render-identical** — same comparator, same
rows, every testID/band/cutline/caption unchanged. The strip uses the same
helper for "projected *Nth*", making strip-vs-section divergence structurally
impossible (PRD FR1.5 / A3 hang on this shared helper).

### 1.4 `OutlookStrip` — the collapsed one-liner

Contents, left → right (mock frame E, restated against real data):

| Slot | Source | Render |
|---|---|---|
| Label | static | `Season outlook` in the section's label voice — a plain `Text` with the label type + `semantic.warn` color and the 3×14 warn tick bar drawn as a sibling `View` (the same construction `TickLabel` uses, restated locally — `TickLabel` itself is NOT reused: its props are `{children, color}` only and it hardcodes `accessibilityRole="header"` (`chalkline/TickLabel.tsx:20`), wrong inside a button) |
| Your band chip | `you = data.teams.find(t => t.is_you)` → `playoffBand(you.odds.playoff_pct)` | exact reuse of `PLAYOFF_BAND_LABEL` / `PLAYOFF_BAND_COLOR` (`:1688/:1693`) + the section's chip construction (border-in-encode-color, label always shipped with color) |
| Seed phrase | `rank = orderOutlookTeams(data.teams).findIndex(t => t.is_you) + 1`; `n = data.teams.length` | `for the playoffs · projected {ordinal(rank)} of {n}` |
| Chevron | expansion state | `<Icon name={expanded ? 'chevron-up' : 'chevron-down'} size={14} color={chalk.dim} />` — the house disclosure precedent (`AdjustmentsDisclosure.tsx:66` icon-swap; chevrons never rotate in this app) |

Container: full-width Pressable row, warn-tinted per the mock
(`ink-1`-family bg, warn-tinted hairline border, `radii.sm`), padding
`space.sm`–`space.md`, mounted where the section mounts today.

Accessibility: the Pressable is the accessible unit —
`accessibilityRole="button"`, `accessibilityState={{ expanded }}`, label
`"Season outlook. {BandLabel} to make the playoffs. Projected {ordinal} of {n}."`
The chip inside is **not** separately accessible and carries **no testID**
(an accessible container collapses its subtree on iOS — flow-authoring law 3;
the band is asserted via the strip's accessibilityLabel at lighting time).

`ordinal()` — tiny local helper (1st/2nd/3rd/Nth, 11/12/13 exception). No
library.

### 1.5 Expand / collapse behavior

- Tap anywhere on the strip toggles; persists via §1.1; fires
  `track('outlook_strip_toggled', { league_id: leagueId, expanded: next }, 'LeagueSummary')`
  (`mobile/src/api/events.ts:188` — no-throw, queue-backed, itself gated on
  `analytics.client_events`). **Taxonomy first:** the same PR adds
  `"outlook_strip_toggled"` to `ALLOWED_CLIENT_EVENTS`
  (`backend/analytics_taxonomy.py`, NOT `FUNNEL_CRITICAL`), extends the
  existing taxonomy test with the allowlist assertion (sabotage-proven), and
  files the tracking-plan addendum
  (`docs/business/analytics/2026-07-17-tracking-plan-v2.md`). Match the
  screen-string convention of existing `track()` calls when passing the
  third arg.
- **Expanded:** strip stays mounted (it is the collapse affordance) and the
  unchanged `SeasonOutlookSection` renders directly beneath it.
- **Default collapsed** (absent storage entry). Per-league, per-user memory.

### 1.6 Degenerate states (all decided here, none left to the builder)

| State | Behavior |
|---|---|
| Query loading, no data | **Strip-height loading shell**: label + small `ActivityIndicator color={semantic.warn}`, no value text, not tappable. Replaces the section's full-height loading branch (`:1780-1789`) in the collapsed default, so the fold position doesn't jump when data lands (review finding 17). When the strip is expanded (persisted state), the section's own loading branch renders beneath the shell as today. |
| `!data \|\| teams.length === 0` (post-load) | `null`, exactly as today. |
| Payload has no `is_you` team | Render the full `SeasonOutlookSection` with **no strip** (today's behavior). The strip's content is "your" outlook; without an identified user row it has nothing true to say. |
| Non-Sleeper league | Unchanged — `OutlookUnsupportedRow`, no strip, no request. |
| Flag dark | Unchanged — whole subtree `null`, no fetch. |

### 1.7 What W1 must NOT touch

Everything inside `SeasonOutlookSection` / `OutlookRow` **except** the §1.3
sort extraction: ribbon, source caption, rows, cutline, `coverageCaption`,
band constants, `OUTLOOK_WEEK6_PERCENT_ENABLED` (`:1711`), the query gating
chain (`enabled: oddsEnabled && outlookSupported && !!leagueId`, `:449`),
every existing `league-summary.odds.*` testID.

---

## §2 W2 — Card disposition move

### 2.1 `TradeCard.tsx` — new prop

```ts
/** Deck disposition actions (#169 card frame C, operator-modified). When
 *  present, Pass/Like render inside the card directly beneath the player
 *  tile section. Only the deck's TOP card passes this — match variant,
 *  peek card, and read-only mounts never do. */
disposition?: {
  onPass: () => void;
  onLike: () => void;
  disabled?: boolean;
};
```

### 2.2 Render site

Immediately after the player-tile `split` view closes (`:512`), **before**
"Edit in calculator" (`:517`):

```tsx
{disposition ? (
  <View style={styles.dispositionRow}>
    <Pressable testID="trades.pass-btn" … />
    <Pressable testID="trades.like-btn" … />
  </View>
) : null}
```

- **Styles:** copy `dispositionRow`, `dispositionBtn`, `…BtnPass`,
  `…BtnPassPressed`, `…BtnLike`, `…BtnLikePressed` from
  `TradesScreen.tsx:6128-6158` unchanged (56×56, `radii.sm`, 1px border,
  centered row, `gap: space.xl`; row margins adjusted to card rhythm:
  `marginTop: space.sm`, no bottom margin). **`dispositionDisabled` does NOT
  move** — it is still consumed by the "Bad trade?" Pressable at
  `TradesScreen.tsx:4790` (review finding 5); TradeCard defines its own
  0.45-opacity disabled style.
- **Icons + pressed-state style functions:** verbatim from the current
  implementation.
- **Accessibility labels are renamed, not preserved** (review finding 4): the
  shipped `accessibilityLabel="Accept this trade"` (`:4761`) and the
  `accessibilityActions` label `'Accept this trade'` (`:5427`) violate the
  operator's Pass/Like vocabulary — both become **"Like this trade"** in W2.
  The pass-side label is checked and aligned the same way ("Pass on this
  trade").

### 2.3 `TradesScreen.tsx` — wire the top card, delete the old row

- `SwipableTopCard` (`:5343`) **already receives `onLike` / `onPass`**
  (`SwipableProps` `:5317-5318`, wired to `advance('like')` /
  `advance('pass')` at `:4641-4642` for the swipe gesture). Do NOT add a
  duplicate callback pair (review finding 6): thread **only**
  `dispositionDisabled?: boolean` (value: `swipeMutation.isPending` — the
  exact condition on both current buttons, `:4735-4754`) and let
  `SwipableTopCard` build `disposition={{ onPass, onLike, disabled }}` from
  its existing props when passing to `TradeCardComp` (`:5435`).
- The **peek card** (`:4624-4633`) and every other `TradeCardComp` mount get
  **no** `disposition` prop.
- Delete the `dispositionRow` block (`:4733-4768`) and the row/button styles
  (not `dispositionDisabled`, §2.2).
- **Stale text/comments to update in the same pass** (review finding 20):
  the comment at `:4780-4783` ("sits below the disposition row") loses its
  referent — rewrite it; the `deckHint` copy ("Swipe right to like · Swipe
  left to pass") stays — swipe semantics are unchanged and the copy is still
  true.
- Everything else in `deckWrap` (Queue, `SendInSleeperButton`, hints, "Bad
  trade?" flag, share-liked) keeps today's order.

### 2.4 Gesture-surface risk — mitigation, not a fallback

The buttons move inside `trades.card-top`'s `GestureDetector` pan surface.
The pan already carries a horizontal activation offset (±12), so child
Pressable taps without horizontal drag are expected to reach the buttons —
and the Tier-1 sim run **taps both buttons** (extended `06-trades-deck` +
re-derived `onboarding-tour@fresh`), which is the proof. **If taps are
swallowed on sim, STOP and escalate to the operator with the findings** — the
prior draft's "row outside the `Animated.View`" fallback is not real
(`GestureDetector` takes a single child `:5417-5449`, and the card border
lives inside `TradeCard` `:339`, so any out-of-gesture composition is a
visible structural change the operator hasn't seen). No silent fallback.

### 2.5 Unchanged by decision

`TradeValueBar` mount (guard `:533`, element `:534`) — stays put, now below
the disposition row; already the post-#243 component. The `match`-variant
action row (`:567-586`). The bare `SendInSleeperButton` row (`:588-596`).
No odds block is added anywhere on the card (decisions §8).

---

## §3 W3 — Tests & flows

### 3.1 `mobile/tests/check-card-disposition.js` (new) + runner

Static source check in the house pattern (`check-mock-mode-marker.js` et al):

1. `TradeCard.tsx` contains `trades.pass-btn` and `trades.like-btn`, both
   **after** the split section's close and **before** the `TradeValueBar`
   mount (index-order assertion on the source text).
2. `TradesScreen.tsx` no longer contains a `testID="trades.pass-btn"` /
   `"trades.like-btn"` usage (prop wiring/comments allowed).
3. `TradeCard.tsx` renders the row behind a `disposition ?` guard.

**Runner (review finding 11):** every `check-*.js` is an npm script
(`mobile/package.json:12-19`) — add `test:card-disposition`. CI does **not**
run mobile check scripts (`.github/workflows/ci.yml` runs `tsc` +
`testid-lint` only), so this is local evidence; PRD A6/A7 are marked local.

**Sabotage proof required (gate):** temporarily revert the W2 move (or flip
the guard) → script must FAIL → restore → passes. Log both runs in
TEST_LEDGER.

### 3.2 Maestro deltas (two flows, both positional)

**`flows/smoke/06-trades-deck.yaml` (extend):** the old flow reaches the
like button via `scrollUntilVisible … DOWN` (`:58-61`) because the row sat
*below* the deck — a plain `visible:` assert would pass identically before
and after the move (law 2: `visible:` counts off-screen ScrollView children —
review finding 2). The delta must be **positional**:

- after the existing `trades.card-top` assert, assert `trades.pass-btn` and
  `trades.like-btn` with `visibilityPercentage: 100` **without any scroll
  step** — on the old layout this fails (the row needed a scroll to reach:
  the `onboarding-tour@fresh.yaml:179-188` gotcha), on the new layout the
  in-card row is on-screen with the card top;
- then tap like (existing path); after the deck advances, assert
  `trades.card-top` again and **tap pass** on the next card — this makes the
  pass-tap smoke-suite evidence (PRD A5; review finding 3).

**`capture/onboarding-tour@fresh.yaml` (declared delta — review finding 2):**
its three disposition-tap blocks (`:189-193`, `:218-222`, `:354-358`) use
`scrollUntilVisible … DOWN` anchors derived from the old below-deck position.
Re-derive all three on-sim during the Tier-1 run (likely: the scroll steps
become no-ops or need removal; the gotcha comment at `:179-188` must be
rewritten — its remedy was *scroll into view*, not `extendedWaitUntil`;
review finding 16).

**Frame E gets no flow** — dark-flag waiver, same grounds as the signed
2026-08-10 waiver ([`status-outlook-v2-build-2026-08-10.md`](status-outlook-v2-build-2026-08-10.md)
§ Maestro waiver); the lighting-time flow additionally owes the strip states
(collapsed default → expand → persistence) and the strip's
accessibilityLabel assert (§1.4).

### 3.3 Capture delta (four screens — review finding 13)

`screen-freshness.sh` is source-hash based; `screens/manifest.json` maps the
three touched files to four screens. Decisions per screen:

| Screen | Source trigger | Decision |
|---|---|---|
| `trades` | `TradesScreen.tsx` + `TradeCard.tsx` | re-capture — real visual change |
| `matches` | `TradeCard.tsx` (match variant) | re-capture — expect **no** visual diff (no `disposition` prop); the capture refreshes the hash and doubles as A6 evidence |
| `sheets-trade-dna` | `TradesScreen.tsx` | re-capture — expect no visual diff |
| `league-summary` | `LeagueSummaryScreen.tsx` | re-capture — expect no visual diff (flag dark) |

Then run `screen-freshness.sh` and confirm clean.

---

## §4 testID ledger

| ID | Status |
|---|---|
| `trades.pass-btn`, `trades.like-btn` | **moved**, ids unchanged (cross-client invariant "Pass / Like") |
| `league-summary.odds.strip` | new — the strip Pressable (its band chip carries NO id — §1.4) |
| every existing `league-summary.odds.*` | unchanged |
| `trades.card-top`, `valuebar.why` | unchanged |

`testid-lint.sh` checks flow→source only (`:41-53`), so it exercises the
moved deck ids via the extended flows but **cannot see**
`league-summary.odds.strip` until the lighting-time flow exists (review
finding 21) — the strip id's first real check is that flow; until then its
only guard is code review.
