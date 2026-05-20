# mobile/ — Notes for Claude

React Native / Expo app. Talks to the Flask backend over the network.

## Entry

- `App.tsx` — root component, wraps providers + nav
- `index.ts` — Expo entry shim
- `app.json` — Expo config
- `babel.config.js`, `tsconfig.json` — build config

## Source layout (`src/`)

| Dir | Purpose |
|---|---|
| `api/` | HTTP clients (Sleeper + FTF backend) |
| `components/` | Reusable presentational components |
| `hooks/` | Custom hooks (push notifications, etc.) |
| `navigation/` | React Navigation setup (root + tabs) |
| `screens/` | Top-level screens |
| `shared/` | Shared `types.ts` |
| `state/` | Context-based state (session, flags, notifications) |
| `theme/` | Design tokens (`colors`, `spacing`) |
| `utils/` | Pure helpers (`relativeTime`, `tierBands`) |

## Run

```bash
cd mobile
npm install
npx expo start --tunnel
```

The tunnel flag lets a phone on a different network reach your local Flask backend.

## Tier colors must match web + extension.
