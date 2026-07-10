# Chalkline Component Library

Date: 2026-07-02
Tokens: [`design-system.md`](design-system.md). Live examples: [`web/style-guide.html`](../../web/style-guide.html).

Every component below maps to an existing class/component (web class · mobile component noted). New UI composes these; don't invent parallel variants.

---

## Buttons

Height 40px (36px compact), radius `--r-sm`, Archivo 600 14px, padding 0 16px. Focus: ice ring. Disabled: 45% opacity, no pointer.

| Variant | Spec | Replaces |
|---|---|---|
| **Primary** | ice fill, `--on-ice` text; hover `--ice-press` | `.auth-btn`, `.generate-btn`, `.submit-btn` |
| **Secondary** | transparent, 1px `--line-strong` border, chalk text; hover: border ice, text chalk | `.skip-btn` |
| **Like** | transparent, 1px `--pos` border, `--pos` text; hover: `--pos` fill, ink text | `.trade-like-btn` |
| **Pass** | transparent, 1px `--neg` border, `--neg` text; hover: `--neg` fill, ink text | `.trade-pass-btn` |
| **Ghost** | no border, `--chalk-dim` text; hover: chalk | `.notif-mark-all-btn`, inline actions |
| **Icon** | 32×32, radius `--r-sm` (not circular), icon `--chalk-dim`; hover: `--ink-3` fill | `.close-btn` |

## Badges & chips

Radius `--r-xs`, `label` type (11px Archivo 600 caps), 2px 6px padding. Construction: **solid 1px border in the encode color + chalk text on ink** — kills the old uniform `rgba(color,.15)` tint pattern.

| Component | Spec | Replaces |
|---|---|---|
| **PositionChip** | border+text in position color, e.g. `QB` | `.pos-badge` · `PositionChip` |
| **TierBadge** | border+text in tier color, tier name label | `.tier-badge` · `TierBadge` |
| **DepthBadge** | `--line-strong` border, chalk-dim text (`WR1`) | `.dc-badge` |
| **RookieBadge** | flare border, flare text, `RK` | `.rookie-badge` |
| **InjuryBadge** | `--warn` (Q/D) or `--neg` (Out/IR) border+text | `.inj-badge` |
| **ScorePill** | Plex Mono 500 13, chalk, no box — bare number; delta suffix in `--pos`/`--neg` | `.score-pill` |
| **ConsensusTag** | `label` type, chalk-faint, no border | `.consensus-tag` |
| **LikesYouPill** | `--r-pill`, flare border + flare `eye` icon + `They're interested` | `.likes-you-pill` |
| **CountBadge** | `--r-pill`, `--neg` fill, on-neg chalk, Plex Mono 11 | `.notif-badge` |

## Cards

`--ink-1` fill, 1px `--line` border, radius `--r-md`, padding `lg`. No shadow, no hover lift. Hover/selected: border `--line-strong` / ice.

| Component | Anatomy | Replaces |
|---|---|---|
| **PlayerCard** | 3px position rail (left, full height) · name in `title` · PositionChip + DepthBadge row · Elo in `data` · TierBadge. Selected (trio winner): ice border + ice tick top-right | `.card` · `PlayerCard` |
| **TradeCard** | Header: leaguemate + LikesYouPill · two columns `YOU SEND` / `YOU GET` (`label` headers with ice tick) separated by 1px `--line` vertical rule · player rows (mini PlayerCard rows) · FairnessMeter footer · Like/Pass buttons | `.trade-card` · `TradeCard`, `SuggestionCard` |
| **LeagueRow** | List row, not card: 1px hairline separator, league name `title`, meta `body-sm` chalk-dim, chevron. Hover `--ink-3` | `.league-item`, `.league-card` · `LeaguePill` |
| **MethodTile** | Card + icon (Chalkline set, 20px, chalk-dim) + `heading` title + `body-sm` desc. "NEW" = ice-border badge | `.rm-tile`, `.rm-badge` |

## Navigation

| Component | Spec | Replaces |
|---|---|---|
| **TopNav** | 56px bar, `--ink-0`, bottom hairline. Wordmark left (ice tick + `TRADE FINDER` condensed caps). Tabs: `label` type chalk-dim; active = chalk + 2px ice underline | `.header`, `.nav-tabs` |
| **PositionTabs** | Segmented row, radius `--r-sm` group, 1px `--line` border. Active segment: `--ink-3` fill + 2px underline in that position's color. Overall tab: ice underline (not purple) | `.tab`, `.overall-tab` |
| **FormatToggle** | PositionTabs construction, two segments (`1QB PPR` \| `SF TEP`), active underline always ice (action, not a data encoding). Sits directly above the position switcher on ranking screens (mobile Tiers + Trios). Defaults to the selected league's detected format; tapping is an explicit in-session override | mobile `FormatToggle` |
| **FilterTabs** | Ghost text `label` chalk-dim; active chalk + ice underline | `.rookie-filter-tab` |

## Sheets, modals, menus

`--ink-2` fill, top radius `--r-md` (sheets) or radius `--r-md` (menus/modals), 1px `--line` border, `--shadow-sheet`. Scrim: solid `rgba(9,10,8,0.78)` — **no blur**. Sheets slide with `--t-sheet`; 32×4px `--line-strong` grabber centered top.
Replaces: `.overlay`, `.rankings-panel`, `.rookie-overlay`/`.rookie-panel`, `.notif-panel`, `.account-menu`, `.celebration-overlay` · `OutlookSheet`, `LeagueSwitcherSheet`, `RookieDraftBoardSheet`, `FeedbackSheet`, `SwapPlayerSheet`.
Celebration: mascot illustration allowed here; ice tick + `heading`; still no confetti gradients.
Sectioned picker (`SwapPlayerSheet`, feedback #86): same sheet construction with a `SectionList` — tick-label section banners ("SUGGESTED SWAPS" / "FULL ROSTER"), position-group sub-labels in `label` type, rows = position chip + name/meta + right-aligned `data` value (suggested rows add a chalk-dim signed delta). Trigger affordance on the trade card: 28px square icon button (1px `--line-strong` border, radius `--r-xs`, `swap` glyph) in each player row's right slot; edited cards get a flare `EDITED` badge (informational, ADR-005) and hide the stale match-strength bar until the re-priced fairness lands.

## Meters & progress

All tracks: 4px height, `--ink-3`, radius 0 (square ends — chalk lines, not pills).

| Component | Spec | Replaces |
|---|---|---|
| **UnlockBar** | Segmented track; per-position fill in position color; hash marks (1px `--line` gaps) between segments; label row in `label` type with Plex Mono counts | `.unlock-bar-wrap`, `.progress-track` |
| **FairnessMeter** | Track + single fill: `--pos` ≥ balanced threshold, `--warn` middle, `--neg` lopsided; value as `data` Plex Mono right-aligned (`fairness_score` × 100, client-side — invariant) | `.trade-fairness` · fairness meter |
| **CoverageBar** | Same track; ice fill; caption `body-sm` chalk-dim | `.coverage-bar-*`, `.gate-pos-bar-*` |
| **StrengthBar** | Same track, position-color fill | `StrengthBar` |
| **Spinner** | 20px, 2px `--line` ring + ice arc | `.init-overlay` spinner |

## Forms

Inputs/selects: 44px, `--ink-2` fill (solid — replaces `rgba(255,255,255,0.05)`), 1px `--line-strong` border, radius `--r-sm`, chalk text, chalk-faint placeholder. Focus: ice border + ring. Error: `--neg` border + `body-sm` `--neg` message below.
Slider (`.fairness-slider`): 4px `--ink-3` track, square ice thumb 16×16 (radius `--r-xs`).
Replaces: `.auth-input`, `.league-select`.

## Feedback & status

| Component | Spec | Replaces |
|---|---|---|
| **Toast** | `--ink-2`, hairline border, `--shadow-sheet`, 3px left rail (ice info / `--pos` success / `--neg` error), `body` text, bottom slide `--t-base` | `.toast` · `Toast` |
| **NotificationRow** | Hairline-separated rows; icon (`match`/`check`/`x`) in status color; unread = flare 6px square dot (not circle) + `--ink-2` row fill | `.notif-row`, `.notif-unread-dot` |
| **ActivityRow** | Hairline rows: icon · `body` text · Plex Mono timestamp chalk-faint | `.activity-feed-*` · `ActivityFeed` |
| **EmptyState** | `heading` (condensed caps) + `body-sm` chalk-dim + one Primary/Secondary button. Mascot illustration optional. Actionable copy per voice charter | various |
| **Banner** | `--ink-2`, hairline, ice tick + `body-sm`, ghost dismiss | `InviteLeaguematesBanner`, `NewPartnersBanner` |

## Tier bins & boards

**TierBin** (`TierBin`, tiers screen): well of `--ink-0`, 1px dashed `--line-strong` border, radius `--r-md`; header = ice-tick label in tier color + Plex Mono count. Drag-over: border goes tier color solid.
**Tier tiles — dense/cozy row** (mobile `TiersScreen` player rows via `PlayerCard dense`, feedback #58; spec source `mockups/tier-density/cozy.html`): fixed **60px two-line row + 4px gap** (~8 rows/screen), `--ink-1` surface, hairline, radius `--r-md`, 3px position rail. Line 1 = name (Archivo semi 15, ellipsizes first) + team (11 chalk-dim) + RK/injury micro-tags (9px bordered, Badge construction). Line 2 = TierBadge for the tile's **current zone** (tier colors are data encodings — `cross-client-invariants.md`; the rail is NOT a tier signal; Unassigned tiles carry no TierBadge) + the #65 stat strip inline. Right cluster (#53/#54): positional rank prominent (Plex Mono semi 14 in the position color) stacked over the 0–10k value (Plex Mono 11 chalk-dim; derived client-side by inverting the documented seed-scale mapping `elo = 1200 + value/10000 × 600` — the user's board value, until #53/#54 ships a consensus value in the payload). Dropped at this density: PositionChip (redundant with rail + posRank) and age/experience meta. Active-drag / multi-select-selected ring = the card's own ice `selected` border (no wrapper border, keeping the pitch exact). Tier headers carry count next to the label + the tier's summed 0–10k value right-aligned (both Plex Mono chalk-dim).
**Rank board rows** (mobile `ManualRanksScreen`, feedback #53/#54 display half): the draggable Overall Ranks rows reuse the dense tile's right cluster — positional rank prominent (`QB1`/`RB4`, Plex Mono semi 14 in the position color) stacked over the 0–10k value (Plex Mono 11 chalk-dim). Raw Elo is not shown. Positional rank is derived client-side from the full local ordering (1-based index among same-position players), so the Overall view and a position-filtered view show the same `QB4`, and ranks update live during drag / jump-to-rank edits. The 0–10k value comes from the shared `valueForElo` helper (`mobile/src/utils/playerValue.ts` — inverse of the seed-scale mapping in `cross-client-invariants.md`), also used by the Tiers board.
**Tier step buttons** (mobile `TiersScreen`, feedback #90; layout per #58 cozy): per-tile Icon Buttons (32×32, radius `--r-sm`, `chevron-up`/`chevron-down` in chalk-dim, pressed `--ink-3` fill) **side-by-side** in a right-hand gutter — each button gets the full row height, and 32×32 visual + hitSlop 6 reaches the 44pt effective target (the old stacked pair only reached ~40pt). Move that single player one whole tier with the same rules as the multi-select "Tier up / Tier down" actions (up → bottom of higher tier, down → top of lower tier; clamps at Elite/Bench with the disabled state at 45% opacity; never into/out of Unassigned).
**Pool drag guard** (mobile `TiersScreen`, feedback #68): dragging a TIERED player into the Unassigned pool is rejected — the row snaps back with a warning haptic + toast. One-directional: Unassigned → tier drags still work. Matches the chevron/tier-move rule that tier stepping never crosses the pool boundary.
**Tile stat strip** (mobile `TileStats`, feedback #65; hosted on line 2 of the dense tile since #58): one compact row showing BOTH the user's and the consensus values, each introduced by a short text label — `You #4 ▲2 30d · Cons ADP 12` (labels 10px caps chalk-muted; trend glyph `▲`/`▼` in `--pos`/`--neg`, `–` muted when unavailable). The consensus segment shows rank only (no consensus 30d trend exists yet — feedback #61) and is omitted entirely when the consensus rank is unavailable. Replaces the FB4-61 "Consensus | You" segmented toggle, which is removed.
**Sticky tier banner** (mobile `TierStickyHeader`, FB4-63; gated per feedback #67): floats OVER the top edge of the board (overlay — appearing never shifts the list), non-interactive, frozen during drags. Hidden until the current section's own inline header scrolls off the top; hides again when the user scrolls back to the very top (the inline header already labels the section there).
**Board expand toggle** (mobile `TiersScreen`, feedback #81): Icon Button with the `expand`/`collapse` glyphs on the board bar; expanded state hides the chrome above the board (title row, format toggle, copy action, hint) while the position tabs, sticky tier banner and save bar stay.
**Rookie board**: FilterTabs + hairline table rows; rank numerals Plex Mono.

## Extension

Popup (320px): same tokens, `--ink-0` base; `FTF` wordmark short form. **ConnectedCard** → key-value hairline rows, keys `label` chalk-dim, values `data`/`body`. Injected sleeper.com badges (`.ftf-badge`) keep tier hex + left-border construction (invariant surface — restyle only via `cross-client-invariants.md` update).

## Auth screen (anti-template layout)

Left-aligned, not centered-hero: ice tick + `display` headline ("Rank your league. Find the trades both sides want.") · username input + Primary button in one row (desktop) · `body-sm` chalk-dim link row (smart-start URL, demo mode). No three-item icon/tagline row, no equation headline. Mascot may sit right of the fold on desktop.

## Screen coverage check

Every screen listed in the audit maps to the above: Login (Auth), League select (LeagueRow), Method select (MethodTile), Rank/trio (PlayerCard, PositionTabs, UnlockBar), Trade Finder (TradeCard, FairnessMeter, CoverageBar, slider), Matches (TradeCard match variant, VerdictPanel = Toast+EmptyState patterns), Activity/Trends (ActivityRow, TrendBar = StrengthBar), Tiers (TierBin), Rookie board (sheet + FilterTabs), Outlook (sheet + MethodTile-style options), Notifications (NotificationRow), Settings/Profile (hairline key-value rows + forms), Player detail (PlayerCard header + ActivityRow history).
