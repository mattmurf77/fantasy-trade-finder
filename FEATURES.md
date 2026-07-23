# FTF Feature Catalog — Teardown Remediation Wave (2026-07)

Everything built on branch `teardown-remediation` from the app-teardown audit (37 PRDs in the gitignored `app-teardown-review/`). Each user-visible change is behind a **default-false flag** in `config/features.json`; flag-off behavior is byte-identical to pre-wave. A handful of items shipped **unflagged** by policy (security fixes, doc/legal corrections, inert accessibility annotations, plumbing/bug fixes).

- **Flags:** `config/features.json` → `_comment_teardown` block (30 flags). Reload backend at runtime via `POST /api/feature-flags/reload`; mobile picks up flags on next fetch/build.
- **Per-feature detail:** PRD in `app-teardown-review/<section>/prds/`; build report in `app-teardown-review/build/`.
- **QA status:** `qa/teardown-remediation-qa.md`.
- **Decisions/deferrals:** `docs/adr/adr-008-teardown-remediation-wave.md`.
- **Rollback:** flip the one flag → false. Unflagged items roll back only by revert (noted below).

Current flag state: **all 30 enabled** (operator flipped 2026-07, commit `config: enable all 30 teardown-remediation flags`).

---

## 1 · Navigation & IA

| Feature | Flag | PRD | Key files |
|---|---|---|---|
| Sheet input protection — Feedback/ESPN/Platform-link sheets keep typed drafts on dismiss; Keep-editing/Discard on dirty fields | `ux.sheet_guard` | 01/prd-01 | components/FeedbackSheet, EspnLinkSheet, PlatformLinkSheet |
| Rank tab is a real destination (not an action menu); "More ways to rank" header; re-tap→root | `ux.rank_tab_destination` | 01/prd-02 | navigation/TabNav, RankHomeScreen |
| Re-tap active tab → pop stack / scroll to top | `ux.retap_active_tab` | 01/prd-05 | navigation/{TabNav,scrollToTop}, Trades/Matches/League screens |
| One deep-link router (links + push + bell taps); buffered replay; unroutable → home+toast | `ux.deeplink_router_v2` | 01/prd-04 | navigation/RootNav, utils/deepLinks |
| Universal links (iOS associatedDomains + backend AASA route) | *unflagged (build-time)* | 01/prd-03 | mobile/app.json, backend/server.py `/.well-known/apple-app-site-association` |
| RankHome visible back control | *unflagged (bug fix)* | 01/prd-02 | navigation/TabNav |

## 2 · Visual & Layout

| Feature | Flag | PRD | Key files |
|---|---|---|---|
| Dynamic Type — Text primitive w/ per-tier maxFontSizeMultiplier caps + minHeight containers | `a11y.text_scaling` | 02/prd-01 | components/chalkline/Text, chalkline/Button, theme/chalkline |
| Reduce Motion — useReducedMotionSafe hook; transitions crossfade | `a11y.reduce_motion` | 02/prd-02 | hooks/useReducedMotionSafe, Toast, TabNav, TradesScreen |
| Legacy→Chalkline migration + 11pt floors + faint→dim + 3:1 border token | `visual.chalkline_cleanup` | 02/prd-03, 02/prd-04 | components/FormatGate, TierStickyHeader, TierTargetChips, TileStats, PlayerCard, TradeMeter, theme/* |
| Web Chalkline migration + focus-visible + aria-selected + prefers-reduced-motion | *unflagged (branch-only)* | 02/prd-05 | web/css/styles.css, web/*.html, web/js/app.js |

## 3 · Touch Interactions

| Feature | Flag | PRD | Key files |
|---|---|---|---|
| Player long-press context menu + visible twins (lock affordance, 44pt ⓘ) | `ux.player_context_menu` | 03/prd-02 | components/PlayerContextMenu, PlayerCard, TradeCard, TradesScreen, MatchesScreen |
| Triage undo — Passed/Dismissed toasts (POST parked 5s); calculator Clear undo; double-fire guard | `ux.swipe_undo` | 03/prd-03 | components/Toast, TradesScreen, MatchesScreen, TradeCalculatorScreen |
| Touch polish — 44pt targets, FAB above pinned bars, drag activation dist + pickup haptic, inbox row-delete | `ux.touch_polish` | 03/prd-01, 03/prd-04 | components/FeedbackFAB, chalkline/Button, SteerSlider, FormatToggle, TiersScreen, ManualRanksScreen, FeedbackInboxScreen |

## 4 · Instructional

| Feature | Flag | PRD | Key files |
|---|---|---|---|
| Toast v2 — tone-based durations + action slot (VoiceOver announce is *unflagged*) | `ux.toast_v2` | 04/prd-03 | components/Toast |
| Interrupt coordinator (one banner/tip/modal at a time) + primer backoff | `ux.prompt_arbiter` | 04/prd-04 | state/useInterruptCoordinator, TradesScreen, PushPrimingModal, AppleSaveMomentSheet |
| Empty-state CTAs do the action they name | `ux.empty_state_ctas` | 04/prd-05 | MatchesScreen, PortfolioScreen, FreeAgentsScreen |
| In-app Help & FAQ + ⓘ explainers | `ux.help_surface` | 04/prd-01 | components/HelpSheet, TradesScreen, MatchesScreen, SettingsScreen |
| Kill modal-quiz-before-value; inline outlook default + unlock reward caption | `ux.outlook_inline_default` | 04/prd-02 | TradesScreen, RankScreen, OutlookSheet |

## 5 · Notifications & Permissions

| Feature | Flag | PRD | Key files |
|---|---|---|---|
| Recipient timezone sync (quiet hours/digests were ET-for-all) | `notif.tz_sync` | 05/prd-01 | backend/server.py, database.py; SettingsScreen (tz footer) |
| Tap routing v2 — cold-start, exact-match, bundle_summary, bell hydration | `notif.tap_routing_v2` | 05/prd-02 | hooks/usePushNotifications, navigation/RootNav, TopBar, state/useNotifications |
| Denied-permission recovery (open iOS Settings) | `notif.denial_recovery` | 05/prd-03 | SettingsScreen |
| Re-engagement pushes off by default | `notif.reengagement_default_off` | 05/prd-04 | backend/database.py |
| Honest winbacks (check real matches; lifetime stop after 3 ignored) | `notif.honest_winbacks` | 05/prd-04 | backend/server.py |
| first_match/new_match double-push dedup; primer counter-offer copy fix | *unflagged (bug/honesty)* | 05/prd-04 | backend/server.py, components/PushPrimingModal |

## 6 · Account, Settings & Trust

| Feature | Flag | PRD | Key files |
|---|---|---|---|
| Settings IA v2 (5 groups) + instant rank-pref apply + modal-over-modal fix | `account.settings_v2` | 06/prd-04 | SettingsScreen |
| Data export ("Download my data", GDPR) | `account.data_export` | 06/prd-02 | backend/server.py `/api/account/export`, SettingsScreen |
| Sleeper disconnect control (policy promised it, was missing) | `account.sleeper_disconnect` | 09/prd-01 | SettingsScreen, api/sendInSleeper |
| Per-user public-profile opt-in (enumeration-safe) | `profiles.user_toggle` | 06/prd-04 | backend/server.py, database.py (users.profile_public), SettingsScreen |
| Persistent sessions (DB-backed, hashed, 90d verified; 4h posture kept for unverified) | `auth.persistent_sessions` | 06/prd-03 | backend/{server,database}.py, state/useSession, api/client, SignInScreen |
| **Security:** league/preferences + rankings/submit no longer accept spoofable user_id | *unflagged (security)* | 06/prd-01 | backend/server.py |
| Apple token revocation on delete; POST /api/session/signout | *unflagged* | 06/prd-02 | backend/{server,accounts}.py, state/useSession |
| Disclosure sync — policy/FAQ/Terms match real behavior; consent copy | *unflagged (legal)* | 09/prd-01, 09/prd-02 | web/{privacy,terms,faq}.html, SleeperConnectScreen |

## 7 · Growth & System

| Feature | Flag | PRD | Key files |
|---|---|---|---|
| Share landing — shares → rich OG pages (/s/trade, /s/p/…) | `growth.share_landing` | 07/prd-01 | backend/{server,og_image}.py, TradesScreen |
| Rating prompt at satisfaction moments | `growth.rating_prompt` | 07/prd-02 | utils/ratingPrompt, SendInSleeperButton |
| Board search (scroll-to+highlight) on big rank boards | `ux.board_search` | 07/prd-04 | ManualRanksScreen, TiersScreen |
| What's-new (version-keyed, once per version) | `ux.whats_new` | 07/prd-04 | hooks/useWhatsNew, LeagueScreen |
| Rookie draft board mounted as League Explore row | `league.rookie_board_entry` | 07/prd-04 | LeagueScreen, components/RookieDraftBoardSheet |
| NetInfo/onlineManager bridge (refetchOnReconnect now works) | *unflagged (plumbing)* | 07/prd-04 | mobile/App.tsx, state/queryClient |

## 8 · Accessibility (mostly unflagged, inert)

| Feature | Flag | PRD | Key files |
|---|---|---|---|
| Header traits, trio-card roles/state/labels, drag-row + deck accessibilityActions, 42-file role/label sweep | *unflagged (inert)* | 08/prd-01, 08/prd-02 | ~42 files across screens/ + components/ |
| Token-contrast CI guard (`npm run test:contrast`) | *unflagged* | 08/prd-03 | mobile/scripts/check-contrast.js |
| Accessibility release checklist | *unflagged (doc)* | 08/prd-03 | qa/accessibility-release-checklist.md |

## 9 · Docs & specs

Monetization PRDs (trial timeline, `trial_ending` push, billing grace, Founder $99–119); all 30 flags documented in `docs/config-reference.md` + quarterly ship-by/kill-by convention; ADR-008; `APPLE_*` env vars.

---

## Rollback quick-reference

- **Any flagged feature:** set its flag → false in `config/features.json`, reload/rebuild. No code revert needed.
- **Unflagged security fixes / bug fixes / doc corrections:** intentionally permanent; revert the specific commit if ever needed (see `git log` on the branch).
- **Web migration:** branch-only and unflagged; revert `web/` if the reskin needs to wait.

## Known runtime-QA risks (static tests can't cover)

Full-set flag interactions need device/Maestro QA — see `qa/teardown-remediation-qa.md`. Highest-risk combos: interrupt coordinator + prompt arbiter + outlook-inline on Trades; deep-link router + notification tap routing (cold start); Dynamic Type + Chalkline cleanup + Reduce Motion at AX sizes; persistent sessions across a real restart.
