# mobile/src/state/

Cross-screen stores and coordination. What each module does and why is in [CLAUDE.md](CLAUDE.md).

## The three shapes

| Shape | Files | When to use it |
|---|---|---|
| **zustand store** (12) | `useSession`, `useFeatureFlags`, `useOnboardingState`, `useNotifications`, `useFeedback`, `useFinderTargets`, `useTradeQueue`, `useGuide`, `usePushPriming`, `useInterruptCoordinator`, `rookieScope`, `premiumImport` | State several screens read, and non-React modules need to reach imperatively |
| **module bus** (3) | `onboardingBus`, `espnConnectBus`, `rankImportBus` | A one-shot handoff between two surfaces on opposite sides of a `Modal` or navigation boundary, where neither params nor focus work |
| **plain hook + AsyncStorage** (2) | `outlookStrip`, `quicksetProgress` | Per-user/per-league persisted UI memory with no cross-screen reader |

`queryClient.ts` is neither — it is the single `QueryClient` instance, shared between `App.tsx`'s provider and non-React modules that invalidate caches imperatively (e.g. `useSession` swapping the active league outside any component tree). Defaults are tuned for a consumer mobile app: retry once, 30s `staleTime`, 30min `gcTime`, refetch on mount/focus/reconnect.

`guideTargets.ts` is a registry, not a store: screens register views by testID and the guide overlay measures them at show time.

`leagueSession.ts` is an internal initialization coordinator, instantiated by
`useSession`, not another persisted store. Every native init writer joins or
supersedes the same captured account/league/token generation. Acknowledged
same-token writers are serialized; an ambiguous dispatched timeout is not
server cancellation and blocks automatic re-entry until a new deliberate
action or replacement token. Readiness is never inferred from a busy boolean
or throttle alone. API builders return cache seeds; state publishes them only
after a current accepted initialization.

Win Now's full load has one 90-second budget before token preparation, shared
init, projection GET, and at most one exact `session_not_initialized` repair
and read replay. Canceling a reader detaches it without canceling another
reader's shared initialization. No write operation is automatically replayed
by this recovery path. Native storage operations already dispatched cannot
be canceled by later identity guards; those guards prevent stale in-memory,
cache and navigation publication, not an unconditional persistent-store
ordering guarantee.

## Persistence keys

| Store | Key |
|---|---|
| `useOnboardingState` | `ftf_onboarding_state_v1` |
| `useFeedback` | `ftf_inapp_feedback_v1` |
| `quicksetProgress` | `ftf_tiers_saved_cache_v1` |
| `useTradeQueue` | `ftf_trade_queue_<user_id>` |
| `outlookStrip` | `ftf_outlook_strip_<user_id>` (value = the league ids whose strip is EXPANDED; collapsing deletes the entry) |
| `premiumImport` | `ftf.premium_import.v1` — device-local "imported N weeks ago" stamps; schema-free by design, so losing it degrades to "no prior import", never to a wrong board |
| `useWhatsNew` (in `../hooks/`) | `ftf_whats_new_seen_version` |
| Session token / last username / device id | expo-secure-store, via `../api/client.ts` |
| Query cache | AsyncStorage via `PersistQueryClientProvider`, allow-list `PERSIST_KEYS` in `App.tsx`, 30min `maxAge` |

Persisted state is **user-scoped** (`<user_id>` in the key) so two accounts on one device never share it. Session-only state — `useFinderTargets`, `rookieScope` — is deliberately never persisted; a board filter or a pin list must not outlive its session.

## Adding a store

1. `create()` a zustand store in `useThing.ts`, or a module bus if the two ends are separated by a `Modal`.
2. Persist only if the state should survive a relaunch — and then scope the key by user id.
3. If the store must clear on league switch, subscribe to `useSession` (`useFinderTargets` is the pattern).
   A module bus is only for two surfaces separated by a `Modal` boundary, where neither navigation params nor focus can reach across — `espnConnectBus`, `rankImportBus`, `onboardingBus`. Nothing else.
4. Fetching goes in [`../api/`](../api/CLAUDE.md); pure math goes in [`../utils/`](../utils/CLAUDE.md). A store coordinates, it does not compute.
5. Add a bullet to [CLAUDE.md](CLAUDE.md).
