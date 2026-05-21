# Perf audit — 2026-05-21

In response to feedback #12 ("app is slow to load data"). Audit was read-only;
the actionable items are tracked here for implementation in separate PRs.

## Top 5 wins (ROI ordered)

### #P1 — Mobile downloads 4.8 MB of player JSON it discards on every league pick
- **Symptom:** every league pick + every league switch waits 1.3 s wifi, 3–8 s cellular, on top of Render cold start.
- **Cause:** `mobile/src/api/sleeper.ts:46–48` + `mobile/src/api/auth.ts:114–123` — `warmPlayerCache()` calls `GET /api/sleeper/players` which serializes the full 4.8 MB filtered dict every call, even on cache hits. Mobile only wants the side effect (server-side cache hydration). Body is dropped on the floor.
- **Fix:** add `GET /api/sleeper/players/warm` (or `?warm=1`) on the backend returning `{ok, count}`. Point `warmPlayerCache()` at it. Web client untouched.
- **Effort:** small. **Impact:** large. **Risk:** very low.

### #P2 — No backend warm-up at app boot; user pays cold-start tax on first action
- **Symptom:** First tap after a multi-hour gap hits a sleeping Render dyno. Generic `ActivityIndicator` for 30–60 s with no copy. Users assume the app is broken.
- **Cause:** `App.tsx:43–61` boots local state in parallel but nothing forces a backend round-trip during splash. The 30–60 s cold start lands on `LeaguePickerScreen` / `TradesScreen` overlays labeled "Loading…" not "Waking up server."
- **Fix:** (a) fire-and-forget warm ping in `App.tsx:58` Promise.all (using the new #P1 endpoint). (b) Swap loading copy in `LeaguePickerScreen.tsx:88–90` + `TradesScreen.tsx:354–359` to "Waking up server — first request after a quiet period can take 30s." after 4s of waiting via `useEffect` timer.
- **Effort:** small. **Impact:** medium (perceived + real). **Risk:** very low.

### #P3 — LeagueScreen blocks on 5-6 parallel queries with no skeleton
- **Symptom:** Single centered spinner replaces the entire body until the slowest of `summary / coverage / members / activity / contrarian / unlocks` resolves. Even cached `league.league_name` doesn't render up front.
- **Cause:** `mobile/src/screens/LeagueScreen.tsx:43–91`, gate at line 188 `loading && !summary && !coverage`.
- **Fix:** (a) render hero card + section titles from `useSession((s)=>s.league)` immediately. (b) add `placeholderData: (prev) => prev` to each `useQuery`. (c) show skeleton chips ("—") in place of `ActivityIndicator`.
- **Effort:** small. **Impact:** medium. **Risk:** low.

### #P4 — MatchesScreen no skeleton + no placeholder
- **Symptom:** Tapping Matches shows only a spinner. List goes blank during refetch.
- **Cause:** `MatchesScreen.tsx:46–50` — `useQuery(['matches','all'])` has `staleTime` but no `placeholderData`, no skeleton.
- **Fix:** add `placeholderData: (prev) => prev` + 2-3 skeleton match cards under the chip row.
- **Effort:** small. **Impact:** medium. **Risk:** very low.

### #P5 — initLeagueSession's expensive leg is the 4.8 MB warm
- **Symptom:** League pick takes 5–10 s warm, 30–60 s cold.
- **Cause:** Folds into #P1 + #P2. Once warm is moved to boot, `initLeagueSession` drops to `max(rosters, users) + sessionInit` ≈ 5–10 s warm.
- **Fix:** no standalone change. Resolves with #P1 + #P2.

## Lower-priority findings (deferred)

- `RankScreen.tsx:57–61` — AsyncStorage read causes flicker on speed-mode toggle.
- `App.tsx:24–36` — `QueryClient` has no `gcTime` set (defaults to 5 min). Raising to ~30 min would give returning-from-background users instant content.
- `TradesScreen.tsx:185–213` — trade-status poll at 1.5 s with no backoff; aggressive on cellular.
- `useFeedback.hydrate` vs `retrySync` — verify they don't double-fire on AppState 'active'.
- `ProfileScreen.tsx:141` — RN `<Image>` for avatars, not `expo-image`. Bounded today; preempt if avatars get added to lists.

## Structural floor

No client-side change eliminates a true Render cold start. The $7/mo Render starter dyno (no sleep) is the only complete fix. Worth considering as the app gets more users — currently the cold start hits every solo tester.

## What was checked and found clean

- No N+1 fetches.
- No unbounded image lists.
- AsyncStorage reads in `useSession.bootstrap` already parallelized.
- App.tsx boot has no heavy synchronous work.
- TanStack queries set sensible `staleTime` / `enabled` gates.
- Hermes + new arch already on.
