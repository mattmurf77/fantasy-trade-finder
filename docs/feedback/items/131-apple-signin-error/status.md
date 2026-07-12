# #131 — Apple sign-in entitlement — status

## Build phase (mobile BUILD agent, 2026-07-12)

**Status: BUILT — awaiting QA (Maestro run), then R-8 codesign checkpoint and R-9 operator on-device checks.**

Implemented per `prd.md` (post-round-3, Planner-approved). No PRD deviations.

### Files touched

| File | Requirement | Change |
|---|---|---|
| `mobile/ios/DTFDynastyTradeFinder/DTFDynastyTradeFinder.entitlements` | R-1 | Added `com.apple.developer.applesignin` = `[Default]` — exactly the 4 pinned lines; `aps-environment` byte-untouched |
| `mobile/src/components/TopBar.tsx` | R-3 | One added prop line: `testID="topbar.settings"` on the Settings gear Pressable (the tap target itself) |
| `mobile/src/components/CLAUDE.md` | R-3 | Registered `signin.apple-btn`, `settings.link-apple-btn`, `topbar.settings` (new "Apple entitlement tranche" block); smoke-flow range note 01–10 → 01–11 |
| `mobile/.maestro/flows/smoke/11-apple-entitlement.yaml` | R-5 | New flow, byte-per the PRD: Part 1 regression sensor with the SETTLE probe (`optional: true` `extendedWaitUntil`, 3 s window) + DO-NOT-REMOVE comment; Part 2 reachability-only; version-pin header (expo-apple-authentication@8.0.8) |
| `docs/runbook.md` | R-7 | Appended "Bare workflow: `app.json` iOS config is silently ignored (feedback #131)" entry incl. the pinned-failure-copy line |

Not touched (by design): `SignInScreen.tsx`, `SettingsScreen.tsx`, backend, `app.json` (R-2 zero app-logic; R-6 version bump is orchestrator-owned).

### Build verification evidence

- `plutil -lint` on the entitlements file: **OK**
- `git diff` on the entitlements file: exactly the 4 added lines (indent-matched to file style); no whitespace/DOCTYPE churn; pre-existing no-trailing-newline preserved
- `git diff` on TopBar.tsx: exactly one added prop line
- `cd mobile && npx tsc --noEmit`: **clean (exit 0)**
- `maestro check-syntax` (maestro 2.5.1) on the new flow: **OK**; python yaml multi-doc parse: 2 docs, 21 steps
- Flow contains the SETTLE step with its DO-NOT-REMOVE comment (R-5 mechanical criterion); both failure-copy asserts are in Part 1 only (Part 2 has none)
- `grep -c "apple-btn" mobile/src/components/CLAUDE.md` = 2 (R-3 mechanical criterion)

### Remaining gates (not build-agent scope)

- [ ] QA: flow 11 green in the smoke matrix; smoke 01–10 still green
- [ ] R-6: version bump to 1.7.3 (four carriers) — batch orchestrator
- [ ] R-8: codesign entitlement check on the EAS production artifact + provisioning-profile regeneration (`eas credentials`)
- [ ] R-9: operator on-device checks (Sign-In sheet completes; Settings → Link Apple completes) on build ≥42
