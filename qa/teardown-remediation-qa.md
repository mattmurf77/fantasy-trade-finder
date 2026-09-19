# Teardown Remediation — QA Tracker

QA status for the 30 flag-gated features (+ unflagged items) built on branch `teardown-remediation`. Companion to [`../FEATURES.md`](../FEATURES.md) (catalog) and [`accessibility-release-checklist.md`](accessibility-release-checklist.md).

**Static gates (whole wave):** ✅ backend pytest 967 · ✅ mobile `tsc --noEmit` · ✅ `npm run test:contrast` · ✅ features.json valid. Static gates prove *nothing breaks*; they do **not** exercise mobile runtime interaction — that's the Device column below.

**Device-QA legend:** ☐ pending · 🔄 in progress · ✅ passed on device · ❌ failed (→ Issue Log) · ⤴ needs re-verify after fix.

Run device QA with the `maestro-test` skill (whole-app smoke + per-feature flows) and manual passes for the gesture/scroll/notification items Maestro can't assert.

---

## Status by feature

| # | Feature | Flag | PRD | Static | Device | Verify on device |
|---|---|---|---|:--:|:--:|---|
| 1 | Sheet input protection | `ux.sheet_guard` | 01/01 | ✅ | ☐ | Type in Feedback/ESPN sheet → tap backdrop → reopen: draft intact. Empty sheet still 1-tap dismiss. |
| 2 | Rank tab destination | `ux.rank_tab_destination` | 01/02 | ✅ | ☐ | Tap Rank from another tab → lands on a rank surface (not a menu). "More ways to rank" header works. RankHome has back. |
| 3 | Re-tap active tab → top | `ux.retap_active_tab` | 01/05 | ✅ | ⤴ | **Was broken (Issue #1, fixed).** Scroll down Trades/Matches/League → tap active tab → scrolls to top. Trades w/ Portfolio pushed → pops first. |
| 4 | Deep-link router v2 | `ux.deeplink_router_v2` | 01/04 | ✅ | ☐ | Universal/`dtf://` links open correct screen; bad link → home + toast (no silent drop). |
| 5 | Universal links (entitlement) | *unflagged* | 01/03 | ✅ | ☐ | **Needs EAS rebuild.** Tap a shared `/u/…` or `/s/…` link w/ app installed → opens in-app. AASA served (curl the route). |
| 6 | Dynamic Type | `a11y.text_scaling` | 02/01 | ✅ | ☐ | iOS text size AX3 & AX5 → Tiers/Trades/Settings/tab bar: no clipping/overlap. (a11y checklist) |
| 7 | Reduce Motion | `a11y.reduce_motion` | 02/02 | ✅ | ☐ | iOS Reduce Motion on → card fling/toast/modals crossfade; deck pan still tracks finger. |
| 8 | Chalkline cleanup + floors | `visual.chalkline_cleanup` | 02/03-04 | ✅ | ☐ | FormatGate/Tiers header on-brand (no indigo); micro-text ≥11pt legible; borders visible. |
| 9 | Web Chalkline migration | *unflagged* | 02/05 | ✅ | ☐ | Web smoke: login/app/tiers/FAQ/privacy render on-brand, no console errors; focus rings visible; tabs announce. |
| 10 | Player context menu + twins | `ux.player_context_menu` | 03/02 | ✅ | ☐ | Long-press player → menu (info/untouchable/swap). Visible lock + ⓘ reach same actions. Hold-hint on deck. |
| 11 | Triage undo | `ux.swipe_undo` | 03/03 | ✅ | ☐ | Pass a card → "Undo" restores it, no server POST fired. Match dismiss undo. No double-swipe skip. |
| 12 | Touch polish | `ux.touch_polish` | 03/01,04 | ✅ | ☐ | FAB clears Tiers Save bar; chips/dots ≥44pt; drag lift haptic; ManualRanks scroll doesn't misfire drags. |
| 13 | Toast v2 (+ VO announce) | `ux.toast_v2` | 04/03 | ✅ | ☐ | Error toast stays ≥5s / tap-dismiss; success 1.5s. VoiceOver announces toasts (unflagged). |
| 14 | Interrupt coordinator + backoff | `ux.prompt_arbiter` | 04/04 | ✅ | ☐ | **High-risk combo.** Force session-2 + ≥5 swipes + no QuickSet + inferred outlook → only ONE surface shows. Primer not re-asked every session. |
| 15 | Empty-state CTAs | `ux.empty_state_ctas` | 04/05 | ✅ | ☐ | Matches/Portfolio/FreeAgents empties → primary button navigates (not Refresh). |
| 16 | In-app Help + ⓘ | `ux.help_surface` | 04/01 | ✅ | ☐ | Settings Help&FAQ opens; ⓘ on fairness meter + Matches opens explainer → "Read more" → web. |
| 17 | Outlook inline default | `ux.outlook_inline_default` | 04/02 | ✅ | ☐ | First Trades visit: no modal quiz; inline confirm banner; Edit opens sheet. Unlock caption shows reward. |
| 18 | Timezone sync | `notif.tz_sync` | 05/01 | ✅ | ☐ | Non-ET device → prefs.tz updates; quiet hours/digest fire in local time. Settings tz footer. |
| 19 | Notification tap routing v2 | `notif.tap_routing_v2` | 05/02 | ✅ | ☐ | **Device-only.** Tap push (app killed/bg/fg) → exact match. Morning bundle push → Matches. Bell shows server inbox after relaunch. |
| 20 | Denial recovery | `notif.denial_recovery` | 05/03 | ✅ | ☐ | Deny push → Settings shows banner → opens iOS Settings. |
| 21 | Re-engagement off by default | `notif.reengagement_default_off` | 05/04 | ✅ | ☐ | New user prefs: reengagement=0. (backend-testable; confirm no winback fires uninvited) |
| 22 | Honest winbacks | `notif.honest_winbacks` | 05/04 | ✅ | ☐ | Dormant user w/ 0 matches → no "matches waiting". Stops after 3 ignored. |
| 23 | Settings IA v2 | `account.settings_v2` | 06/04 | ✅ | ☐ | 5 groups; rank-pref applies immediately; Settings→FeedbackInbox/SleeperConnect dismisses Settings first (no stacked modals). |
| 24 | Data export | `account.data_export` | 06/02 | ✅ | ☐ | "Download my data" → share sheet w/ JSON. 403 verified-step-up → "Verify now". |
| 25 | Sleeper disconnect | `account.sleeper_disconnect` | 09/01 | ✅ | ☐ | Account row shows connected/expired; disconnect → confirm → token deleted. |
| 26 | Public-profile opt-in | `profiles.user_toggle` | 06/04 | ✅ | ☐ | `/u/<name>` 404s until toggle on (also needs global profiles.public_pages). |
| 27 | Persistent sessions | `auth.persistent_sessions` | 06/03 | ✅ | ☐ | **High-risk.** Restart backend / long gap → verified session survives. Unverified username-only still 4h. Signout/delete evict. Account-only 401 → Apple re-auth. |
| 28 | Share landing | `growth.share_landing` | 07/01 | ✅ | ☐ | Share liked trade → rich OG card in iMessage; opens /s/trade or /s/p. Calculator share (needs client wiring — see build report handoff). |
| 29 | Rating prompt | `growth.rating_prompt` | 07/02 | ✅ | ☐ | First successful Send-in-Sleeper (+gates) → StoreReview prompt; never session 1 / after feedback. |
| 30 | Board search | `ux.board_search` | 07/04 | ✅ | ☐ | ManualRanks/Tiers search → scrolls to + highlights player; drag still works. |
| 31 | What's-new | `ux.whats_new` | 07/04 | ✅ | ☐ | Fresh version → one tip on League, once; dismiss persists. |
| 32 | Rookie board entry | `league.rookie_board_entry` | 07/04 | ✅ | ☐ | League Explore "Rookie draft board" row opens sheet; data renders. |
| — | Accessibility sweep | *unflagged* | 08/01-02 | ✅ | ☐ | Full VoiceOver pass (headers rotor, trio cards, drag-row actions) — see `accessibility-release-checklist.md`. |
| — | Security: authz fixes | *unflagged* | 06/01 | ✅ | n/a | Covered by backend regression tests (league-prefs + rankings/submit). |
| — | Universal-links AASA / NetInfo / dedup / disclosure | *unflagged* | various | ✅ | ☐ | AASA rebuild; reconnect refetch; first-match single push; policy/FAQ read-through. |

---

## Cross-feature interaction watch-list (test with ALL flags on)

1. **Trades screen prompt stack** — `ux.prompt_arbiter` + `ux.outlook_inline_default` + coach marks + Apple save-moment + push primer. One surface at a time; deck never pushed off-screen (SE).
2. **Navigation ↔ notifications** — `ux.deeplink_router_v2` + `notif.tap_routing_v2`: cold-start push tap resolves through the same router; no double-navigation.
3. **Rank tab + re-tap** — `ux.rank_tab_destination` + `ux.retap_active_tab`: re-tap behavior on the Rank tab specifically.
4. **Rendering stack** — `a11y.text_scaling` + `visual.chalkline_cleanup` + `a11y.reduce_motion` together at AX5.
5. **Sessions** — `auth.persistent_sessions` across a real deploy + `account.data_export`/delete eviction.

---

## Issue Log

| # | Feature | Issue | Found | Status | Fix |
|---|---|---|---|---|---|
| 1 | Re-tap active tab (`ux.retap_active_tab`) | Re-tapping the active tab did nothing — TabNav fired `requestScrollToTop` but no screen registered a scroll handler (empty registry; cross-agent handoff missed). | 2026-07 operator device test | ✅ Fixed (commit `fix(ux.retap_active_tab): register scroll-to-top handlers…`) | Trades/Matches/League root screens register their scroller via `registerScrollToTop` in a flag-gated effect. tsc clean. **⤴ needs device re-verify.** |

_Add rows as device QA surfaces issues. Each fix should land flag-gated (or note if unflagged), re-run static gates, and flip the row's Device status to ⤴._
