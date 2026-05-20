# mobile/

React Native (Expo) app for Fantasy Trade Finder.

## Setup

```bash
npm install
npx expo start --tunnel
```

Then scan the QR with Expo Go (iOS/Android) or run on a simulator.

## Layout

- `App.tsx` — root component
- `src/api/` — Sleeper + FTF backend clients
- `src/screens/` — top-level screens (Sign in, League picker, Rank, Trades, Matches, Tiers, Overall, League)
- `src/components/` — reusable UI (PlayerCard, TradeCard, TierBadge, …)
- `src/navigation/` — React Navigation root + tabs
- `src/state/` — session, feature flags, notifications
- `src/hooks/`, `src/utils/`, `src/theme/`, `src/shared/` — supporting modules
- `assets/` — app icons + splash
