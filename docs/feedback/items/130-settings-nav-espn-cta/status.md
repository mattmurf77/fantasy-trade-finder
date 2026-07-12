# #130 — Settings: back/close button + ESPN-link CTA — status

**State:** built (2026-07-12, branch `trade-engine-v2`). Awaiting QA/ship.

## (a) Explicit close control

Settings is a native-stack modal that only had swipe-to-dismiss. Added a
Chalkline Icon Button (32×32, radius sm, `x` glyph chalk-dim, pressed =
ink-3 fill — components.md Buttons spec, no emoji) as `headerRight` on the
Settings screen options in `mobile/src/navigation/RootNav.tsx`
(`HeaderClose`, testID `settings.close-btn`). The pattern is documented in
`docs/design/components.md` (Sheets, modals, menus) for future modal screens
— none of the existing modals (FeedbackInbox, SleeperConnect) had one either;
only Settings was reported, so only Settings changed.

## (b) ESPN-link CTA row

Flag-gated on `espn.link`. New hairline link row "Link an ESPN league" in
`mobile/src/screens/SettingsScreen.tsx` (below the Connect-another-league
card, testID `settings.link-espn`). Least-code coherent route: it navigates
to `LeaguePicker` with a new `{ espnLink: true }` param; `RootNav` passes it
as `autoOpenEspnLink`, and `LeaguePickerScreen` opens its existing
`EspnLinkSheet` on mount (flag-checked). The full existing import → team pick
→ session-init → Main flow is reused unchanged.

## Files

- `mobile/src/navigation/RootNav.tsx` — HeaderClose + Settings headerRight;
  `LeaguePicker` route param + prop pass-through
- `mobile/src/screens/SettingsScreen.tsx` — `espn.link` flag read + CTA row
- `mobile/src/screens/LeaguePickerScreen.tsx` — `autoOpenEspnLink` prop
- testID registry: `mobile/src/components/CLAUDE.md` (settings.close-btn,
  settings.link-espn)

`npx tsc --noEmit` clean.
