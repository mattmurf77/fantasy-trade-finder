# Mobile Feature Parity — Architecture Detail

Companion to [mobile-feature-parity.md](mobile-feature-parity.md). This document captures the cross-bundle integration concerns: navigation graph, state stores, type extensions, shared files, and the API surface introduced.

---

## Navigation graph (after all 8 bundles land)

```
RootStack
├── SignIn ────────────────────── B8 adds: smart-start input, try-demo link
├── LeaguePicker
├── Main (TabNav)
│   ├── Rank (RankStack)
│   │   ├── Trios ────────────── B6 adds: rookie draft board sheet trigger
│   │   ├── Tiers ───────────── B1 adds: Copy-from-format button
│   │   ├── OverallRanks  ──── B1 makes this the read-only "Overall" view OR
│   │   ├── ManualRanks ─────── B1 adds: new screen with drag-reorder + rank edit
│   │   └── Trends ──────────── B2 adds: new screen
│   ├── Trades ────────────────── B4 adds: trade reasons, real/est badge,
│   │                              picker Select All, Equal-only checkbox
│   │                              B5 adds: queue tab + bottom sheet
│   │                              B7 adds: new-partners banner
│   ├── Matches
│   ├── Portfolio ────────────── B3 adds: new screen, registered as Trades sub-route
│   └── League ───────────────── B7 adds: activity feed, contrarian leaderboard,
│                                  per-member unlock badges
├── Settings (modal) ─────────── B3 adds: Switch League + Connect Another League
└── Profile (deep-link only) ── B8 adds: new `/u/:username` route
```

### Tab structure changes

- **Trades** becomes a small stack containing `TradesScreen` + `Portfolio` so the bottom-nav still surfaces four tabs but Portfolio is reachable via a sub-route nav pill (like the Rank tab's action sheet).
- **Rank** action sheet (existing) adds **Trends** as a fourth option; consider whether ManualRanks merges with OverallRanks or stays separate (recommendation: rename `OverallRanksScreen` → kept as read-only "Browse all," and `ManualRanksScreen` is the new editable one — same data, different mode).

---

## State stores

### Extend `useSession` (B3, B8)

```ts
type SessionState = {
  // existing
  user: User | null;
  league: League | null;
  hasToken: boolean;

  // B3 — multi-league support
  leagues: League[];                   // all leagues the user has connected
  switchLeague(leagueId: string): Promise<void>;
  connectLeague(sleeperUrl: string): Promise<void>;

  // B8 — referral + demo
  invitedBy?: string;                  // captured from deep-link ?ref=
  consumeReferral(): string | undefined; // read-and-clear on session_init
  startDemoSession(): Promise<void>;
};
```

### New `useTradeQueue` (B5)

```ts
type TradeQueueState = {
  byLeague: Record<string, QueuedTrade[]>;
  enqueue(leagueId: string, trade: QueuedTrade): void;
  dequeue(leagueId: string, tradeId: string): void;
  sendAll(leagueId: string): Promise<void>;
  clear(leagueId: string): void;
};
```

Persisted to `AsyncStorage` under key `ftf_trade_queue_<user_id>`.

### Reuse `useFlags` (B4, B5, B7, B8)

All four bundles read existing flags via the existing `useFlags` hook. No new flag plumbing.

---

## API client extensions

Group by file. Each entry is `<function name> — <method + path> — <bundle>`.

### `mobile/src/api/rankings.ts`

- `reorderRankings(position, orderedIds)` — `POST /api/rankings/reorder` — B1
- `getTrends(position?)` — `GET /api/trends/risers-fallers` — B2
- `getContrarianGap(leagueId, position?)` — `GET /api/trends/consensus-gap` — B2
- `getRookies(season?)` — `GET /api/rookies` — B6

### `mobile/src/api/league.ts`

- `copyTiersFromFormat(fromFormat, toFormat)` — `POST /api/tiers/copy-from-format` — B1
- `getPortfolio()` — `GET /api/portfolio` — B3
- `connectLeague(sleeperUrl)` — `POST /api/leagues/connect` — B3
- `getActivityFeed(leagueId, limit?)` — `GET /api/league/activity` — B7
- `getContrarianLeaderboard(leagueId)` — `GET /api/league/contrarian` — B7
- `getNewPartners(leagueId)` — `GET /api/league/new-partners` — B7

### `mobile/src/api/trades.ts`

No new endpoints — B4 and B5 consume existing fields on the existing `GET /api/trades/generate` response.

### `mobile/src/api/auth.ts`

- `resolveSmartStart(input)` — `POST /api/session/resolve-smart-start` with either a username or a Sleeper URL — B8
- `startDemoSession()` — `POST /api/session/demo` — B8
- `getPublicProfile(username)` — `GET /api/profile/:username` — B8

---

## Shared type extensions

`mobile/src/shared/types.ts` gets these unions / interfaces:

```ts
// B2 — Trends
export type TrendRow = {
  player: Player;
  position: Position;
  old_rank: number;
  new_rank: number;
  delta: number; // positive = riser, negative = faller
};

export type ContrarianGapEntry = {
  player: Player;
  user_elo: number;
  consensus_elo: number;
  gap: number; // > 0 = "easiest sell", < 0 = "easiest buy"
};

// B3 — Portfolio
export type PortfolioRow = {
  player: Player;
  exposure: { league_id: string; league_name: string; tier: Tier | 'pool' }[];
};

// B4 — Trade card extensions
export type TradeReason = string; // human-readable bullet
// TradeCard gets: reasons?: TradeReason[]; opponent_confidence: 'real' | 'estimated'

// B5 — Queue
export type QueuedTrade = {
  trade_id: string;
  league_id: string;
  match_id?: string;
  sleeper_url: string;
  give_summary: string;
  receive_summary: string;
  queued_at: string;
};

// B7 — League surfaces
export type ActivityEvent = {
  id: string;
  occurred_at: string;
  user_id: string;
  username: string;
  event_type: 'trade' | 'tier_save' | 'league_sync' | 'rank';
  summary: string;
};

export type ContrarianRow = {
  user_id: string;
  username: string;
  divergence_score: number;
};

export type NewPartnerEntry = {
  user_id: string;
  username: string;
  newly_unlocked_at: string;
};

// B8 — Smart start / demo / profile
export type SmartStartResolution =
  | { kind: 'username'; username: string }
  | { kind: 'league_url'; username: string; league_id: string }
  | { kind: 'invalid'; reason: string };

export type PublicProfile = {
  username: string;
  display_name?: string;
  avatar_url?: string;
  rank_count_by_position: Record<Position, number>;
  unlocked_formats: string[];
  joined_at: string;
};
```

---

## Shared file modification matrix

Which bundle touches which shared file, and how:

| File | B1 | B2 | B3 | B4 | B5 | B6 | B7 | B8 |
|---|---|---|---|---|---|---|---|---|
| `mobile/src/navigation/TabNav.tsx` | ManualRanks route | Trends route | Portfolio route | — | — | — | — | — |
| `mobile/src/navigation/RootNav.tsx` | — | — | — | — | — | — | — | Deep-link + Profile route |
| `mobile/src/state/useSession.ts` | — | — | Multi-league | — | — | — | — | Referral / demo |
| `mobile/src/state/useFlags.ts` | — | — | — | flag reads | flag reads | — | flag reads | flag reads |
| `mobile/src/shared/types.ts` | — | TrendRow / ContrarianGapEntry | PortfolioRow | reasons / opponent_confidence | QueuedTrade | — | ActivityEvent / etc. | SmartStartResolution / etc. |
| `mobile/src/api/rankings.ts` | reorder | trends, contrarian | — | — | — | rookies | — | — |
| `mobile/src/api/league.ts` | copy-tiers | — | portfolio, connect | — | — | — | activity / contrarian / new-partners | — |
| `mobile/src/api/auth.ts` | — | — | — | — | — | — | — | smart-start / demo / profile |
| `mobile/src/api/trades.ts` | — | — | — | (consumed fields only) | — | — | — | — |
| `mobile/src/screens/TradesScreen.tsx` | — | — | — | reasons / badge / picker / equal-only | queue tab / panel | — | new-partners banner | — |
| `mobile/src/screens/LeagueScreen.tsx` | — | — | switch button | — | — | — | activity / contrarian / unlock badges | — |
| `mobile/src/screens/RankScreen.tsx` | — | — | — | — | — | rookie board button | — | — |
| `mobile/src/screens/SignInScreen.tsx` | — | — | — | — | — | — | — | smart-start input / try-demo link |
| `mobile/src/screens/SettingsScreen.tsx` | — | — | switch / connect sections | — | — | — | — | — |
| `mobile/src/screens/TiersScreen.tsx` | copy-from-format button | — | — | — | — | — | — | — |
| `mobile/App.tsx` | — | — | — | — | — | — | — | Linking handler init |

Most rows have just one or two bundles touching them. The high-churn files are `TabNav.tsx` (3 bundles add routes), `types.ts` (6 bundles add types), `TradesScreen.tsx` (3 bundles), and `LeagueScreen.tsx` (2). Merge will dedupe additions into those files.

---

## Subagent invocation contract

Each subagent receives:

1. This document (architecture detail).
2. The matching bundle section from the plan document.
3. The relevant CLAUDE.md guidance (mobile/CLAUDE.md, mobile/src/CLAUDE.md, cross-client-invariants.md, coding-guidelines.md).
4. Explicit instructions to:
   - Branch from `origin/main` in an isolated worktree.
   - Stay in scope; if anything outside the bundle needs touching, surface and stop.
   - Verify each backend endpoint exists before consuming it (search `web/js/app.js` and `backend/server.py`).
   - Match existing mobile screen conventions (look at `LeagueScreen` or `TiersScreen` for a styling reference).
   - Run `npx tsc --noEmit` clean before signaling done.
   - Commit with a clear message and push the branch.

The coordinating agent (me) collects the branch names, then merges sequentially into a single integration branch, resolving conflicts as they appear (most conflicts will be in `types.ts` and `TabNav.tsx` — additive, easy).

---

## Done criteria for the whole effort

- Eight branches pushed, each green on `tsc --noEmit`.
- One integration branch with all eight merged, named `feat/mobile-parity-2026-04`.
- One PR opened against `main` summarizing all bundles.
- Each bundle's "Done criteria" from the plan document has a verification note in the PR body.
- No new backend routes introduced (or, if any are, they're called out with a separate backend PR).
