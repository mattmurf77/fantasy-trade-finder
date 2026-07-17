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
| **TradeCard** | Header: leaguemate + LikesYouPill · optional partner-fit line (FB-47, when `partner_fit` present): hint-tier row of 6px hollow chalk-dim square + `body-sm` copy ("They're deep at WR — a natural seller" / calibrated "Strong/Decent/Weak fit for your targets") · two columns `YOU SEND` / `YOU GET` (`label` headers with ice tick) separated by 1px `--line` vertical rule · player rows (mini PlayerCard rows) · FairnessMeter footer · Like/Pass buttons | `.trade-card` · `TradeCard`, `SuggestionCard` |
| **LeagueRow** | List row, not card: 1px hairline separator, league name `title`, meta `body-sm` chalk-dim, chevron. Hover `--ink-3` | `.league-item`, `.league-card` · `LeaguePill` |
| **MethodTile** | Card + icon (Chalkline set, 20px, chalk-dim) + `heading` title + `body-sm` desc. "NEW" = ice-border badge. "Recommended" (#119, one method max — the lowest-effort flow): flare `label` text tag beside the title (informational highlight, ADR-005) + ice border/icon on the card itself; same treatment on the Rank action-sheet row | `.rm-tile`, `.rm-badge` |

## Navigation

| Component | Spec | Replaces |
|---|---|---|
| **TopNav** | 56px bar, `--ink-0`, bottom hairline. Wordmark left (ice tick + `TRADE FINDER` condensed caps). Tabs: `label` type chalk-dim; active = chalk + 2px ice underline | `.header`, `.nav-tabs` |
| **PositionTabs** | Segmented row, radius `--r-sm` group, 1px `--line` border. Active segment: `--ink-3` fill + 2px underline in that position's color. Overall tab: ice underline (not purple) | `.tab`, `.overall-tab` |
| **FormatToggle** | PositionTabs construction, two segments (`1QB PPR` \| `SF TEP`), active underline always ice (action, not a data encoding). Sits directly above the position switcher on ranking screens (mobile Tiers + Trios). Defaults to the selected league's detected format; tapping is an explicit in-session override | mobile `FormatToggle` |
| **FilterTabs** | Ghost text `label` chalk-dim; active chalk + ice underline | `.rookie-filter-tab` |

## Sheets, modals, menus

`--ink-2` fill, top radius `--r-md` (sheets) or radius `--r-md` (menus/modals), 1px `--line` border, `--shadow-sheet`. Scrim: solid `rgba(9,10,8,0.78)` — **no blur**. Sheets slide with `--t-sheet`; 32×4px `--line-strong` grabber centered top.
Modal screens (native-stack `presentation: 'modal'`, e.g. Settings) carry an explicit header close control (feedback #130): the Icon Button variant (32×32, radius `--r-sm`, `x` glyph in chalk-dim, pressed = `--ink-3` fill) in `headerRight` — swipe-dismiss alone is not discoverable.
Replaces: `.overlay`, `.rankings-panel`, `.rookie-overlay`/`.rookie-panel`, `.notif-panel`, `.account-menu`, `.celebration-overlay` · `OutlookSheet`, `LeagueSwitcherSheet`, `RookieDraftBoardSheet`, `FeedbackSheet`, `SwapPlayerSheet`.
Celebration: mascot illustration allowed here; ice tick + `heading`; still no confetti gradients.
Sectioned picker (`SwapPlayerSheet`, feedback #86): same sheet construction with a `SectionList` — tick-label section banners ("SUGGESTED SWAPS" / "FULL ROSTER"), position-group sub-labels in `label` type, rows = position chip + name/meta + right-aligned `data` value (suggested rows add a chalk-dim signed delta). Suggested rows are band-capped (feedback #109): only candidates within ±15% of the outgoing player's consensus value qualify (max 6, sorted by closeness); zero qualifiers keeps the banner with a "no close-value swaps" hint instead of padding with distant values. Trigger affordance on the trade card: 28px square icon button (1px `--line-strong` border, radius `--r-xs`, `swap` glyph) in each player row's right slot; edited cards get a flare `EDITED` badge (informational, ADR-005) and hide the stale match-strength bar until the re-priced fairness lands.
Target picker (FB-47, flag `trade.finder_targeting`): the Find-a-Trade controls gain a **Target players** block — direction toggle (two `Trade away` / `Acquire` chips, subnav-pill construction: 1px hairline, radius `--r-xs`, active = `--ink-3` well + `--line-strong`) + `Add player` secondary button opening the calculator's `PlayerPickerModal` (search + position filters). Trade-away lists the user's roster; Acquire lists every leaguemate's valued players, each row carrying a chalk-dim `@owner` badge. Active targets render as removable chips (hairline chip + Plex Mono 10 `SEND`/`GET` prefix + name + 12px `x` icon); any change clears the deck so the next Find a Trade regenerates. Web mirrors this on the existing pinned-give picker: `.picker-dir-tab` toggle, acquire chips reuse `.player-chip` with `@owner` in the team slot, fit line = `.trade-fit-line`.

## Meters & progress

All tracks: 4px height, `--ink-3`, radius 0 (square ends — chalk lines, not pills).

| Component | Spec | Replaces |
|---|---|---|
| **UnlockBar** | Segmented track; per-position fill in position color; hash marks (1px `--line` gaps) between segments; label row in `label` type with Plex Mono counts | `.unlock-bar-wrap`, `.progress-track` |
| **FairnessMeter** | Track + single fill: `--pos` ≥ balanced threshold, `--warn` middle, `--neg` lopsided; value as `data` Plex Mono right-aligned (`fairness_score` × 100, client-side — invariant) | `.trade-fairness` · fairness meter |
| **CoverageBar** | Same track; ice fill; caption `body-sm` chalk-dim | `.coverage-bar-*`, `.gate-pos-bar-*` |
| **StrengthBar** | Same track, position-color fill | `StrengthBar` |
| **TradeMeter** (TestFlight #71; **unused since 1.5.4 #100**) | Tile-scale variant originally built for the Tiers dense 60px rows: 9px caps chalk-dim label (`TRADE` = tradeability, player you own; `GET` = acquirability, leaguemate-owned — label carries the meaning, never color alone) + 3px square-end `--ink-3` track, max-width 140, **flare** fill (informational highlight, ADR-005). Fill = the 0–1 score off the rankings payload; half bar = neutral. 1.5.4 #100 removed it from the Tiers tiles (and the dense PlayerCard's `meterSlot` line with it); the component and the `/api/rankings` tradeability/acquirability fields remain available for future surfaces | `TradeMeter` |
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
**Tier tiles — dense/cozy row** (mobile `TiersScreen` player rows via `PlayerCard dense`, feedback #58; spec source `mockups/tier-density/cozy.html`): fixed **60px two-line row + 4px gap** (~8 rows/screen), `--ink-1` surface, hairline, radius `--r-md`, 3px position rail. Line 1 = name (Archivo semi 15, ellipsizes first) + team (11 chalk-dim) + RK/injury micro-tags (9px bordered, Badge construction). Line 2 = TierBadge for the tile's **current zone** (tier colors are data encodings — `cross-client-invariants.md`; the rail is NOT a tier signal; Unassigned tiles carry no TierBadge) + the #65 stat strip inline. Right cluster (#53/#54): positional rank prominent (Plex Mono semi 14 in the position color) stacked over the 0–10k value (Plex Mono 11 chalk-dim; derived client-side by inverting the documented seed-scale mapping — since 2026-07-12 #117 the value-affine map in `data_loader.seed_elo_for_value`, mirrored by `mobile/src/utils/playerValue.ts` — the user's board value, until #53/#54 ships a consensus value in the payload). Dropped at this density: PositionChip (redundant with rail + posRank) and age/experience meta. Active-drag / multi-select-selected ring = the card's own ice `selected` border (no wrapper border, keeping the pitch exact). Tier headers carry count next to the label + the tier's summed 0–10k value right-aligned (both Plex Mono chalk-dim). (The 1.5.4 #103 pick-terms sublabel was retired 2026-07-11 — tier labels ARE pick terms on the pick-value ladder.) The Unassigned section (header + bin) is omitted entirely while the pool is empty (1.5.4 #105) and reappears whenever players return to the pool.
**Rank board rows** (mobile `ManualRanksScreen`, feedback #53/#54 display half): the draggable Overall Ranks rows reuse the dense tile's right cluster — positional rank prominent (`QB1`/`RB4`, Plex Mono semi 14 in the position color) stacked over the 0–10k value (Plex Mono 11 chalk-dim). Raw Elo is not shown. Positional rank is derived client-side from the full local ordering (1-based index among same-position players), so the Overall view and a position-filtered view show the same `QB4`, and ranks update live during drag / jump-to-rank edits. The 0–10k value comes from the shared `valueForElo` helper (`mobile/src/utils/playerValue.ts` — inverse of the seed-scale mapping in `cross-client-invariants.md`), also used by the Tiers board.
**Tier step buttons** (feedback #90 — **removed 1.5.4 #98**): the per-tile chevron Icon Button pair is gone from the tile rows. The no-drag paths for tier moves are multi-select's "Tier up / Tier down" buttons (FB-73), the tier-target chips (FB4-62), and the guided Quick set walk (#104) — same movement rules (up → bottom of higher tier, down → top of lower tier; clamps at the top tier ("4+ 1sts")/FA; never into/out of Unassigned).
**Pool drag guard** (mobile `TiersScreen`, feedback #68): dragging a TIERED player into the Unassigned pool is rejected — the row snaps back with a warning haptic + toast. One-directional: Unassigned → tier drags still work. Matches the tier-move rule that tier stepping never crosses the pool boundary. With the pool section hidden while empty (#105), a drop above the first tier header lands at the top of the first tier ("4+ 1sts") instead of the pool.
**Quick set walk** (mobile `QuickSetTiersScreen`, 1.5.4 #104; since #136 its finish prompt offers the Quick rank walk below): guided per-position tier assignment. Since #119 (2026-07-12) a first-class ranking method: entered from the Tiers header's "Quick set" ghost action (the slot the Anchors link held — #99), the rank-home chooser (leading card, "recommended" flare tag), the Rank tab's action sheet, or at launch via `rankingMethodPref: 'quickset'`. Walks the ladder top → bottom ("4+ 1sts" → FA, 8 steps since #117): step header = tier tick-label in tier color + `Tier N of 8` progress (tier labels read in pick terms since 2026-07-11 — the former #103 sublabel is folded into the name); body = 3-per-row grid of small tappable player chips (`--ink-1`, hairline, radius `--r-sm`, ≥48px tall: name Archivo semi 12, one line + ellipsis; meta row = TEAM (9px Archivo semi, chalk-dim, uppercase; "FA" fallback when teamless) + AGE (9px Plex Mono numeral, chalk-dim) + current-tier micro-label in its encode color, bare 6px gaps, no dot glyphs — #140, spec `mockups/quickset-cards/bottom-row.html`. The POS token is conditional (`SHOW_POSITION`, default off): these walks are position-scoped, so POS is dropped and its width funds TEAM + AGE; any cross-position reuse turns it back on). Tap toggles membership (ice border + `check` — two signals); footer = Back / Skip / primary "Save {Tier}" that commits ONE tier via `/api/tiers/save` (only the submitted pids change; deselected previously-saved-this-run pids go in `cleared_pids`) and advances. Players claimed by an earlier tier drop from later grids; finishing returns to the Tiers board, refreshed via query invalidation.
**Quick rank walk** (mobile `QuickRankScreen`, feedback #136): the within-tier ordering pass — same construction as the Quick set walk (position tabs, tick-label step header in the tier color + `Tier N of M` progress, 3-per-row chip grid, Back / Skip / primary Save footer) but the grid holds every player already IN the current tier and tapping stamps a **rank number badge** (click order) instead of a check: 16px square, radius `--r-xs`, 1px ice border, Plex Mono semi 10 ice numeral, sitting in the chip's top-right slot (selected chips also take the ice border — two signals). Its chip meta row reads TEAM + AGE (same #140 construction and conditional-POS rule as Quick set's; no tier label — the step header owns the tier). Tap again to unclick; later numbers renumber. Save posts the tier's players to `/api/rankings/reorder` (clicked order + unclicked appended in current order) and advances; the walk only visits tiers holding 2+ players. Progress reads `Tier N of M` over the rankable tiers, not the full ladder.
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
