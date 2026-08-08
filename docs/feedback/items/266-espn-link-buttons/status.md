# #266 — Both link buttons dead on LeaguePicker when arriving via the Settings ESPN row

**Covered feedback IDs:** #266
**Branch:** worktree-agent (from `origin/main` @ 6c30dd2) · **Date:** 2026-08-08
**Status:** built; backend suite + mobile typecheck green; on-device confirmation
pending operator TestFlight pass.

## The bug (operator, verbatim)

> "The link an espn league button on the settings page is presenting two broken
> buttons. Both the link an espn league and mfl league buttons on the page after
> clicking the link an espn league button from the settings page. When clicking
> through link an mfl league button, both buttons work as expected."

## Root cause

The two Settings rows differ in exactly one thing: the ESPN row navigates with
`{ espnLink: true }` (`SettingsScreen` → `navigateFromSettings('LeaguePicker',
{ espnLink: true })`), which `LeaguePickerScreen` consumed in a mount-time
effect that called `setEspnOpen(true)` **synchronously on first commit**. The
MFL row navigates with no params and mounts the same screen quiescent.

That synchronous auto-open collides with the arrival transition. With
`account.settings_v2` on, `navigateFromSettings` dispatches `goBack()` (dismiss
the Settings **native modal**) and `navigate('LeaguePicker')` in the same tick —
the W2A modal-over-modal fix — so at the moment the effect runs, iOS is still
animating the modal dismissal + push. Presenting an RN `<Modal>`
(`EspnLinkSheet`) into that in-flight hierarchy wedges the presentation: the
modal host attaches against the dismissing controller and never appears on
screen, while RN's bookkeeping still believes `visible: true`.

From there both footer buttons are structurally dead:

- **"Link an ESPN league"** (`leagues.link-espn`) calls `setEspnOpen(true)` —
  but `espnOpen` is *already* `true` (stuck from the auto-open), so the tap is
  a state no-op and the Modal never gets the `false → true` presentation edge
  it needs to re-present.
- **"Link an MFL league"** (`leagues.link-mfl`) mounts `PlatformLinkSheet`'s
  own fresh Modal — which iOS refuses to present while the half-presented
  `EspnLinkSheet` Modal host is still claiming the presentation slot (the
  documented "iOS won't stack sibling RN Modals" constraint, the same one that
  forces `TradeDnaSheet`'s nested layers).

Via the MFL row nothing auto-opens, no Modal wedges, and both buttons work —
exactly the reported asymmetry. The recently shipped P-1 `connectLeague` merge
fix is unrelated (session-state list merging, no Modal interaction); the
Phase 1b `EspnLinkSheet` WebView changes (`hiddenForWebView`) are internal to
the sheet and only reachable after it is visibly open, so neither is the cause.

## Fix

`mobile/src/screens/LeaguePickerScreen.tsx` — the auto-open is deferred until
the screen's own navigation transition has settled:

- subscribe to the screen's `transitionEnd` event (skipping `closing: true`)
  and open the sheet there, so the Modal presents against a settled hierarchy;
- an 800 ms timeout is the fallback for arrivals that animate nothing (late
  `espn.link` flag hydration re-running the effect, cold-start deep link),
  where opening immediately is already safe;
- one-shot guard + full cleanup on unmount/effect re-run.

No testID, param, or flow-shape changes; the #130 contract ("Settings ESPN row
lands on LeaguePicker with the sheet open") is preserved — the sheet now slides
up right after the page lands instead of fighting the dismissal. The same
deferral also covers the other `espnLink: true` caller
(`league.espn-resync-signin` on LeagueScreen, a plain push).

## Verification

- `cd mobile && npx tsc --noEmit` — clean (exit 0).
- Full backend suite unaffected: 2041 passed / 1 skipped.
- Logic-level repro traced in code (above); native-wedge confirmation is
  device-side — operator QA path: Settings → "Link an ESPN league" → close the
  sheet → both footer buttons must open their sheets; repeat via the MFL row.
