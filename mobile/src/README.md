# mobile/src/

Source for the React Native app, organized by concern. Conventions and constraints: [CLAUDE.md](CLAUDE.md).

```
api/            26 HTTP client modules (client.ts is the only fetch wrapper)
components/     77 shared components
  chalkline/    design-system primitives (Text, Button, Card, Badge, Meter, Icon, TickLabel)
  analyst/      "The Analyst" mascot pose SVGs
  draft/        Draft Room / Mock Draft rows, chrome, sheets
data/           calcTypes.ts — CalcPlayer/CalcPos, the shared calculator asset shape
hooks/          6 cross-cutting hooks
navigation/     RootNav, TabNav, rankChooserModel, scrollToTop
observability/  sentry.ts
screens/        32 screens, one per route
shared/         types.ts — wire types
state/          19 modules: 12 zustand stores, 3 module buses, 2 persisted hooks,
                queryClient, guideTargets
theme/          chalkline.ts (tokens), colors.ts (data hexes), spacing.ts (legacy)
transport/      credentialVault.ts — the single SecureStore credential envelope
utils/          25 helpers
```

`transport/credentialVault.ts` (device-auth release 1, LLD §2.7) holds **one** SecureStore key, `ftf.platformCreds`, carrying a versioned envelope for every platform credential the device keeps — and it subsumes the legacy `sleeper.link.jwt` slot. Two Keychain copies of a 365-day full-account credential, one outside this module's accessibility/wipe logic, is exactly the failure it prevents. Every write pins `WHEN_UNLOCKED_THIS_DEVICE_ONLY` (excludes the item from iCloud Keychain backup), statically enforced by `../tests/check-keychain-accessible.js`. `readEnvelope` returns `null` on a `user_id` mismatch and does NOT wipe — only session establishment wipes (D-047 / OI-14), since a wipe triggered by any caller passing a stale id would be a self-inflicted DoS.

Every subdirectory carries its own `CLAUDE.md` with the annotated file map for that folder:

| Folder | Map |
|---|---|
| `api/` | [api/CLAUDE.md](api/CLAUDE.md) |
| `components/` | [components/CLAUDE.md](components/CLAUDE.md) · [components/chalkline/CLAUDE.md](components/chalkline/CLAUDE.md) · [components/analyst/CLAUDE.md](components/analyst/CLAUDE.md) |
| `hooks/` | [hooks/CLAUDE.md](hooks/CLAUDE.md) |
| `navigation/` | [navigation/CLAUDE.md](navigation/CLAUDE.md) |
| `screens/` | [screens/CLAUDE.md](screens/CLAUDE.md) |
| `shared/` | [shared/CLAUDE.md](shared/CLAUDE.md) |
| `state/` | [state/CLAUDE.md](state/CLAUDE.md) |
| `theme/` | [theme/CLAUDE.md](theme/CLAUDE.md) |
| `utils/` | [utils/CLAUDE.md](utils/CLAUDE.md) |

`data/` and `observability/` hold one file each and have no separate doc.

## Dependency direction (as built, not as idealized)

```
screens/ ──► state/ ──► api/ ──► api/client.ts
    │         ▲  │        │
    │         │  └────────┘  (api/events.ts + api/tradePregen.ts read the flag store;
    │         │               auth/espn/feedback/platformLink take type-only imports)
    ├──► components/ ──► theme/
    └──► utils/ ──► api/  (deepLinks, ratingPrompt, shareLinks, verification)
```

Firm rules:

- **`utils/` never imports React.** Sixteen of the 25 are additionally kept free of imports outside the folder so `../../tests/check-*.js` can transpile and run them under plain node — the file header says which. Check it before adding an import. Full split: [utils/README.md](utils/README.md).
- **`api/` never imports React or a component.**
- **`theme/` imports nothing.**

Soft rule with known exceptions: components are prop-driven and don't fetch. Ten self-contained widgets do own a `useQuery` — `InLeagueCalculator`, `LeaderboardsSection`, `MarketPulseStrip`, `MatchValueSection`, `OutlookBiasReceipt`, `RankChipBadge`, `RookieDraftBoardSheet`, `TopBar`, `TradeDnaSheet`, `draft/MockTeamSheet`. New components default to props; fetching inside one is a decision to justify, not the norm.
