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
Replaces: `.overlay`, `.rankings-panel`, `.rookie-overlay`/`.rookie-panel`, `.notif-panel`, `.account-menu`, `.celebration-overlay` · `OutlookSheet`, `LeagueSwitcherSheet`, `RookieDraftBoardSheet`, `FeedbackSheet`.
Celebration: mascot illustration allowed here; ice tick + `heading`; still no confetti gradients.

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
**Tier tiles** (mobile `TiersScreen` player rows): every tile carries the TierBadge for its **current zone** (tier colors are data encodings — `cross-client-invariants.md`); the 3px position rail is NOT a tier signal. Unassigned tiles carry no TierBadge.
**Tier step buttons** (mobile `TiersScreen`, feedback #90): per-tile Icon Buttons (32×32, radius `--r-sm`, `chevron-up`/`chevron-down` in chalk-dim, pressed `--ink-3` fill) in a right-hand gutter; move that single player one whole tier with the same rules as the multi-select "Tier up / Tier down" actions (up → bottom of higher tier, down → top of lower tier; clamps at Elite/Bench with the disabled state at 45% opacity; never into/out of Unassigned).
**Board expand toggle** (mobile `TiersScreen`, feedback #81): Icon Button with the `expand`/`collapse` glyphs on the board bar; expanded state hides the chrome above the board (title row, format + stat toggles, copy action, hint) while the position tabs, sticky tier banner and save bar stay.
**Rookie board**: FilterTabs + hairline table rows; rank numerals Plex Mono.

## Extension

Popup (320px): same tokens, `--ink-0` base; `FTF` wordmark short form. **ConnectedCard** → key-value hairline rows, keys `label` chalk-dim, values `data`/`body`. Injected sleeper.com badges (`.ftf-badge`) keep tier hex + left-border construction (invariant surface — restyle only via `cross-client-invariants.md` update).

## Auth screen (anti-template layout)

Left-aligned, not centered-hero: ice tick + `display` headline ("Rank your league. Find the trades both sides want.") · username input + Primary button in one row (desktop) · `body-sm` chalk-dim link row (smart-start URL, demo mode). No three-item icon/tagline row, no equation headline. Mascot may sit right of the fold on desktop.

## Screen coverage check

Every screen listed in the audit maps to the above: Login (Auth), League select (LeagueRow), Method select (MethodTile), Rank/trio (PlayerCard, PositionTabs, UnlockBar), Trade Finder (TradeCard, FairnessMeter, CoverageBar, slider), Matches (TradeCard match variant, VerdictPanel = Toast+EmptyState patterns), Activity/Trends (ActivityRow, TrendBar = StrengthBar), Tiers (TierBin), Rookie board (sheet + FilterTabs), Outlook (sheet + MethodTile-style options), Notifications (NotificationRow), Settings/Profile (hairline key-value rows + forms), Player detail (PlayerCard header + ActivityRow history).
