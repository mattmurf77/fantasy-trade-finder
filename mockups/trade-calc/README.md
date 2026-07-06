# DTF Trade Calculator — iPhone mockup

Standalone Expo app mocking the **manual trade calculator**: hand-build a trade between
your team and a leaguemate, and get live fairness verdicts + fair-offer suggestions driven
by **both owners' ranking sets** (mock Elo boards standing in for real FTF rankings).

Deliberately excluded (mocked instead): Sleeper login, league sync, the ranking/Elo
builder, and the trade *finder*. See `APP_PLAN.md` for scope and mechanics, and
`../../docs/plans/manual-trade-calculator-plan.md` for the plan for the real,
server-authoritative version of this feature.

## Run it

```bash
npm install
npm start        # scan QR with Expo Go on iPhone
npm run web      # browser preview
```

## Ship to TestFlight

Uses the same EAS pipeline as `mobile/`:

```bash
npx eas init                 # links the project to the Expo account (one-time)
npx eas build -p ios --profile production
npx eas submit -p ios        # needs App Store Connect app for com.fantasytradefinder.tradecalc
```

Notes:
- Bundle id is `com.fantasytradefinder.tradecalc` (distinct from the main app) — create a
  matching app record in App Store Connect before `eas submit`.
- `eas.json` has `preview` (internal distribution / ad-hoc) and `production` profiles.

## Layout

- `src/data/mock.ts` — mock league: 4 rosters + per-owner value boards (consensus base ×
  positional lean × age bias × stable jitter)
- `src/logic/tradeMath.ts` — package value (consolidation premium), dual-perspective
  fairness verdict, fair-package suggestion search
- `src/components/` — trade side cards, verdict panel, suggestion cards, player picker
- `App.tsx` — single-screen composition
