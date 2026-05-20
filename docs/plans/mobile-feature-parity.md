# Mobile Feature Parity Plan

**Goal:** Close the gaps where the web app has features the React Native mobile app doesn't. Eight independent bundles, each shippable in isolation.

**Guiding principles** (from [docs/coding-guidelines.md](../coding-guidelines.md)):

1. **Think before coding.** Each bundle below states its assumptions. If a subagent finds one wrong, surface it and stop — don't paper over.
2. **Simplicity first.** Reuse existing API endpoints whenever possible (the backend already serves the web app and has parity routes). Don't introduce new abstractions; copy mobile conventions.
3. **Surgical changes.** Touch only what your bundle requires. If a shared file (e.g. `TabNav.tsx`, `types.ts`) needs editing, edit the smallest surface and call it out in the PR body.
4. **Goal-driven execution.** Each bundle defines its own "done" criteria below.

**Cross-client invariants:** anything that crosses backend/web/mobile/extension boundaries must follow [docs/cross-client-invariants.md](../cross-client-invariants.md). The relevant ones for this work: tier colors/bands, scoring format strings (`1qb_ppr` / `sf_tep`), ranking method strings (`'trio' | 'manual' | 'tiers'`), notification type strings, team outlook modes, position color tokens.

**Mobile conventions** (from [mobile/CLAUDE.md](../../mobile/CLAUDE.md) + [mobile/src/CLAUDE.md](../../mobile/src/CLAUDE.md)):

- Data fetch → `api/` (no UI, no state mutation).
- Screen → `screens/`. One file per top-level route.
- Reusable presentational pieces → `components/`.
- Cross-cutting hooks → `hooks/`.
- Pure helpers → `utils/`.
- Design tokens (`colors`, `spacing`, `radius`, `fontSize`) → `theme/`. Never inline.
- State (zustand / React Query / context) → `state/`.
- Existing palette: `colors.bg / surface / text / muted / accent / border / green / red`. Use those, not new ones.

**Backend status:** every feature below has an existing backend route serving the web app. No new backend work is expected unless explicitly called out.

---

## Bundle 1 — Manual Rankings screen + Tier "Copy from <other format>"

### Scope

The web has a dedicated Manual Rankings page where users see all their ranked players in one flat table and drag rows to reorder them, or click a rank number to type a new one. Today mobile only has `OverallRanksScreen` — read-only. This bundle adds drag-reorder + rank-number editing.

Same bundle includes the Copy-from-format button on `TiersScreen` (already shipped on web in PR #39).

### Files

- `mobile/src/screens/OverallRanksScreen.tsx` — convert to interactive list, or add a new `ManualRanksScreen.tsx` route and keep Overall as the read-only "all positions glance"
- `mobile/src/api/rankings.ts` — add `reorderRankings(position, orderedIds)` calling `POST /api/rankings/reorder` (already exists server-side)
- `mobile/src/api/league.ts` — add `copyTiersFromFormat(fromFormat)` calling `POST /api/tiers/copy-from-format`
- `mobile/src/screens/TiersScreen.tsx` — add a "Copy from <other format>" button in the header
- `mobile/src/navigation/TabNav.tsx` — register the new ManualRanks sub-screen in `RankStack`

### API surface used

- `POST /api/rankings/reorder` with `{ position, ordered_ids: [...] }`
- `POST /api/tiers/copy-from-format` with `{ from_format, to_format }` and `X-Scoring-Format` header (see web PR #38 for why)
- `GET /api/rankings?position=XX` for the initial load

### UX

- Reorder uses `react-native-draggable-flatlist` (already approved by repo per other screens that use long-press drag). 220 ms long-press to start (matches `TiersScreen` convention).
- Tap the rank-number cell to edit inline; on blur, submit reorder.
- Position filter chips (ALL / QB / RB / WR / TE).
- Copy-from-format button on `TiersScreen` has a confirm dialog warning it's destructive (matches web behavior).
- Save status indicator (pending / saving / saved) in the header. Match the `LeagueScreen` autosave pattern (the toast helper or `useToast`).

### Done criteria

- [ ] Long-press + drag a row → released → autosave fires → on refresh the order persists.
- [ ] Tap a rank number → input becomes editable → on blur with a new number, the list reorders and saves.
- [ ] Copy-from-format on 1QB PPR with placements → switch to SF TEP → tier/rank preserved (Josh Allen at QB1 Elite stays QB1 Elite, ELO updates from 1680 → 1790).
- [ ] No regression on read-only Overall Ranks view (or keep both, decide on naming).

---

## Bundle 2 — Trends screen

### Scope

New screen at `mobile/src/screens/TrendsScreen.tsx`. Mirrors the web's Trends view: 30-day **Risers** and **Fallers** (biggest ELO deltas), a **Contrarian** meter (how much the user's ranks diverge from league consensus), and a **Consensus gap** report ("easiest sells" / "easiest buys").

### Files

- `mobile/src/screens/TrendsScreen.tsx` — new
- `mobile/src/api/rankings.ts` — add `getTrends(position?)` and `getContrarianGap(leagueId, position?)` calling the existing web endpoints (look up exact paths in `web/js/app.js` Trends section)
- `mobile/src/navigation/TabNav.tsx` — add Trends as a sub-screen of the Rank stack (mirrors web's "Rank Players → Trends" sub-nav), with an icon and label
- `mobile/src/components/TrendBar.tsx` — small reusable horizontal-bar component for ELO delta magnitude

### API surface used

Look up actual paths — likely:
- `GET /api/trends/risers-fallers?position=XX&days=30`
- `GET /api/trends/contrarian?league_id=XX&position=XX`
- `GET /api/trends/consensus-gap?league_id=XX&position=XX`

If the backend route names differ from what web uses, **stop and surface** instead of guessing.

### UX

- Three sections stacked vertically: Risers (top 10), Fallers (top 10), Contrarian gap.
- Each riser/faller row: player name, position chip, old rank → new rank, delta direction (↑ / ↓), magnitude bar.
- Position filter chips at the top (ALL / QB / RB / WR / TE).
- Pull-to-refresh.

### Done criteria

- [ ] Open Trends → see populated risers and fallers within ~1 s.
- [ ] Filter by position → list narrows.
- [ ] Contrarian gap section shows up to 5 "easiest sells" and 5 "easiest buys."
- [ ] Empty states (e.g. brand-new user with no history) are handled.

---

## Bundle 3 — Portfolio screen + Multi-league switcher

### Scope

**Portfolio** is the cross-league exposure view: across all of the user's synced leagues, how many leagues do you own each player in? Heatmap-style list.

**Multi-league switcher** is the Settings UI for switching the active league without going back through `LeaguePicker`. Also adds "Connect Another League" by Sleeper URL paste (ESPN / MFL are nice-to-have but out of scope here).

### Files

- `mobile/src/screens/PortfolioScreen.tsx` — new, registered under a Trades sub-route (next to Matches)
- `mobile/src/screens/SettingsScreen.tsx` — add Connect / Switch League sections
- `mobile/src/api/league.ts` — add `getPortfolio()` (verify endpoint) and `connectLeague(sleeperUrl)`
- `mobile/src/state/useSession.ts` — extend to track multiple leagues if not already
- `mobile/src/navigation/TabNav.tsx` — register the Portfolio sub-route

### API surface used

- `GET /api/portfolio` (or equivalent — find in `web/js/app.js`)
- `POST /api/leagues/connect` with `{ sleeper_url }`
- Existing `useSession` league-switch path

### UX

- Portfolio list: each row is `<player>` with a small badge "Own in N / M leagues" and a chip showing one of (Elite / Starter / Solid / Depth / Bench / Pool) per league it's in.
- Sort by exposure (most-owned first).
- Settings screen gets a "Switch League" pill (opens league sheet) and "Add another league" → URL paste field.

### Done criteria

- [ ] Portfolio shows players you own in 2+ leagues, with per-league tier chips.
- [ ] From Settings, switch league → tab nav refreshes for the new league.
- [ ] Paste a Sleeper URL → backend validates → league added → switcher updates.

---

## Bundle 4 — Trade card improvements

### Scope

On `TradesScreen` / its card component:

- **Trade reasons**: bulleted human-readable explanations on each card (gated by `trade_math.human_explanations` flag on web — flag stays).
- **Real vs estimated opponent badge**: small `●  real` / `○  est.` chip next to the opponent username, indicating whether the opponent's ELOs came from their actual saved rankings (FTF user) or were noise-randomized from consensus.
- **Player picker Select All**: in the existing give-side picker, add a Select All / Clear All toggle that respects the active position filter.
- **Equal-only checkbox**: force fairness slider to 1.0 in one tap. Bound to the existing slider.

### Files

- `mobile/src/components/TradeCard.tsx` (or wherever the card is rendered inside `TradesScreen`)
- `mobile/src/screens/TradesScreen.tsx`
- `mobile/src/state/useFlags.ts` (read the existing `useFlags` hook to gate trade reasons)

### API surface used

- `GET /api/trades/generate` already returns `reasons[]` per card when the flag is on, per `backend/trade_service.py:1278-1297`. Just consume it.
- The same endpoint already returns a confidence indicator on `target_username` — verify shape and surface it.

### UX

- Trade reasons render as bullet points under the give/receive split.
- Real/est badge: small dot + 4-letter chip next to the opponent username.
- Select All toggle: text button above the picker that flips selected = all-currently-visible.
- Equal-only checkbox: above the slider, flips slider to 1.0 and locks it (disabled state).

### Done criteria

- [ ] Each trade card with reasons enabled shows them; flag off hides them.
- [ ] Real/est badge appears next to opponent name on every card.
- [ ] Picker has working Select All that respects position filter.
- [ ] Checking Equal-only locks the slider to 1.0 and disables it; unchecking re-enables.

---

## Bundle 5 — Trade queue

### Scope

The web's `trades.queue_2k` flag adds a "Queue" tab and a Queue panel on the Trades view: instead of opening a single trade in Sleeper immediately, the user can queue up multiple matches and "Send All" later. Mobile equivalent: bottom-sheet "Queue" with the same staggered-open behavior.

### Files

- `mobile/src/screens/TradesScreen.tsx` — add Queue tab toggle, queue chips, "Send All"
- `mobile/src/state/useTradeQueue.ts` — new zustand store, persists in `AsyncStorage` per league
- `mobile/src/components/QueueChip.tsx` — small chip showing a queued trade
- `mobile/src/api/trades.ts` — no new endpoints needed; uses existing match → Sleeper deep-link flow

### UX

- Each trade card gets a "Queue" button alongside Pass / Interested.
- Tap "Queue" → chip appears in a bottom-anchored queue panel.
- "Send All" → opens each Sleeper trade-propose URL with a 500 ms stagger (matches web).
- Queue persists across app restarts via `AsyncStorage`.

### Done criteria

- [ ] Queue 3 trades → kill app → reopen → queue still has 3.
- [ ] "Send All" opens 3 Sleeper deep links with 500 ms gap.
- [ ] Switching league clears the queue (it's per-league).

---

## Bundle 6 — Rookie Draft Board

### Scope

Modal/screen showing a filterable list of rookies (position tabs, scrollable list). Useful during draft prep. Pure read view.

### Files

- `mobile/src/components/RookieDraftBoardSheet.tsx` — bottom-sheet modal
- `mobile/src/api/rankings.ts` — add `getRookies(season?)` if not present
- `mobile/src/screens/RankScreen.tsx` — add a small button or link that opens the sheet (matches the web pattern of a button on Trios)

### API surface used

- Confirm endpoint by checking `web/js/app.js`'s `openRookieBoard()` or similar.

### UX

- Tap the rookie-board button → sheet slides up.
- Position tabs (QB / RB / WR / TE / ALL).
- Scrollable rookie list with player name, team, position chip.

### Done criteria

- [ ] Button to open the sheet appears on RankScreen.
- [ ] Sheet displays rookies filtered by position.
- [ ] Sheet dismisses smoothly.

---

## Bundle 7 — League surfaces (activity feed, contrarian leaderboard, unlock badges, new partners banner)

### Scope

Beef up `LeagueScreen`. Today it shows the basics (members, scoring format, coverage). This bundle adds:

- **Activity feed** (flag `league.activity_feed` per web): last 20 narrative events (trades, tier saves, syncs) with timestamps.
- **Contrarian leaderboard**: rank leaguemates by how much their rankings diverge from consensus.
- **Per-leaguemate unlock badges** (flag `league.unlock_badges_per_member`): each member row gets a "✓ unlocked" / "in progress" chip.
- **New partners banner** (flag `trades.new_partners_alerts`): when a new leaguemate finishes ranking enough to unlock, show a dismissible banner on `TradesScreen`.

### Files

- `mobile/src/screens/LeagueScreen.tsx` — add the three new sections
- `mobile/src/screens/TradesScreen.tsx` — render the new-partners banner if present
- `mobile/src/api/league.ts` — `getActivityFeed(leagueId, limit?)`, `getContrarianLeaderboard(leagueId)`, `getNewPartners(leagueId)`
- `mobile/src/components/ActivityFeed.tsx`, `ContrarianLeaderboard.tsx`, `NewPartnersBanner.tsx`

### API surface used

- Existing web endpoints (look up exact paths from `web/js/app.js`).

### Done criteria

- [ ] Activity feed renders ≤ 20 most-recent events with relative timestamps.
- [ ] Contrarian leaderboard sorts members by divergence score.
- [ ] Each leaguemate row has an unlock-status chip.
- [ ] When a leaguemate newly unlocks, the banner appears on TradesScreen until dismissed (per-user/league localStorage key).

---

## Bundle 8 — Growth loop (smart-start, try-before-sync, referral, public profiles)

### Scope

- **Smart-start CTA** (flag `landing.smart_start_cta`): on SignInScreen, accept a Sleeper league URL as an alternative to username. Backend resolves the URL to a username + league.
- **Try-before-sync demo mode** (flag `landing.try_before_sync`): "Try the app on a sample league" link on sign-in, bypasses auth, loads `/api/session/demo`.
- **Referral tracking**: capture `?ref=<user_id>` from any deep-link / universal link on launch; store and forward on session_init so the backend records `invited_by`.
- **Public profile pages** (flag `profiles.public_pages`): a deep-link route `/u/<username>` that renders a public profile (their rankings stats, etc.). Likely needs a new screen.

### Files

- `mobile/src/screens/SignInScreen.tsx` — smart-start input + try-demo link
- `mobile/src/state/useSession.ts` — handle demo session, referral storage
- `mobile/src/screens/ProfileScreen.tsx` — new public profile route
- `mobile/src/navigation/RootNav.tsx` — register `/u/<username>` deep-link handler
- `mobile/App.tsx` — initialize Linking handler for deep-links

### API surface used

- `POST /api/session/demo` (exists; web uses it)
- `POST /api/session/init` with `invited_by` field
- `GET /api/profile/<username>` (verify path)

### Done criteria

- [ ] Sign-in screen accepts either Sleeper username OR a Sleeper league URL.
- [ ] "Try the app" link spawns a demo session and lands in the Trades view.
- [ ] Opening a `ftf://...?ref=USERID` deep-link captures the ref; sign-in then forwards it.
- [ ] Visiting `/u/<username>` (via deep-link) renders a public profile screen.

---

## Build process

1. **Each bundle gets its own subagent in its own worktree** (`isolation: "worktree"`), branched from the latest `origin/main`.
2. Subagent prompt mirrors this plan + the relevant CLAUDE.md guidance.
3. When all subagents complete, the coordinating agent merges each branch into a single integration branch one at a time, resolving conflicts.
4. The integration branch becomes one PR with all eight bundles included; deploy verifies each bundle independently.

## Risk mitigation

- **Shared file conflicts.** `TabNav.tsx`, `useSession.ts`, `types.ts`, `theme/` are touched by multiple bundles. Each subagent gets a "touch these shared files minimally and call out exactly what you added" instruction; merge picks the union.
- **Endpoint mismatches.** Each bundle has a "verify endpoint" step — if a subagent finds the web endpoint isn't where I claimed, they surface it and stop instead of guessing.
- **Backend dependencies.** None expected; if one surfaces, drop that piece and ship the rest.
- **Flag gating.** Existing flag system (`mobile/src/state/useFlags.ts`) handles this; bundles that depend on a flag wire it the same way as existing flag-gated features.

## Out of scope

- Push notifications on web — that's a major separate effort.
- ESPN / MyFantasyLeague league connect on mobile (Sleeper-only).
- K-factor dashboard (deferred; web-only growth-tooling).
- Animated transitions / advanced gesture work — match the existing screens' style.
