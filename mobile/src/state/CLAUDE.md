# mobile/src/state/

Context-based state. Each file exports a hook + provider.

- `useSession.ts` — current Sleeper user / selected league
- `useFeatureFlags.ts` — flags fetched from `/api/flags`
- `useNotifications.ts` — in-app notification inbox state

No Redux/Zustand — keep it Context until pain demands more.
