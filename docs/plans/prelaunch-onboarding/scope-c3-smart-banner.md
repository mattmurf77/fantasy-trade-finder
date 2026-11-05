# Feature Scope — C3: the App Store smart banner on the web

**Date:** 2026-10-27
**Entry point:** direct ask (head-eng → onboarding-eng 2026-10-27, from Product's pre-launch review C3, score 6: "No path from the website to the App Store"). It goes live at the 11-18 T0, once the app is live.
**Builder:** onboarding-eng
**Operator sign-off on waivers:** none needed beyond §1 (c).

**Two halves:**
- **This PR, the server half.** Every `/s/*` share landing (`_share_html` in `backend/server.py`) carries `<meta name="apple-itunes-app" content="app-id=<digits>">` once the new env var `IOS_INSTALL_URL` (the App Store listing URL) is set.
  - Unset, or without a 6–12 digit `/id…`, there's no banner. So it merges any time and stays inert.
  - Only the digits are emitted.
  - `/s/*` is also claimed by Universal Links (the AASA): with the app installed, the link opens the app, and the banner serves phones without it.
- **The static half**, `web/index.html`, rides the 11-18 web flip (#456), next to its `[APP STORE URL]` placeholders and with the same checker blocker.

## 1. Analytics scope
- [x] **(c) WAIVED:** the banner is Safari's own UI; it can't be instrumented, and App Store Connect reports its installs.

## 2. Schema & flag scope
- Tables and flags: none.
- **New env var `IOS_INSTALL_URL`** (`docs/config-reference.md`). It's set by release-lead at T0, on the operator's go, in the Render environment.
- **Rollback:** unset the var (no deploy).

## 3. Evidence scope
- [x] **Unit tests:** `backend/tests/test_share_package.py`, 3 new tests (5 cases) on a real `/s/p/<id>` landing:
  - no banner while unset or empty;
  - the banner, with the id, inside `<head>` once set;
  - no banner for a URL without an id, for the `[APP STORE URL]` placeholder, and for an injection-shaped value, which isn't echoed either.
  - **Sabotage 3/3 red,** restored byte-identical: the banner always on; any characters accepted as the id; the helper not called in the head.
- [x] **Code-walk:** all three `/s/*` routes (`share_tiers_page`, `share_trade_page`, `share_package_page`) return `_share_html(...)`, which renders the head once.
- [x] **Manual check (release-lead, after T0):** on an iPhone without the app, open a `/s/p/…` link in Safari. The App Store banner shows at the top and opens the listing. With the app installed, the link opens the app.
- `testID`s: n/a.

## 4. Docs scope
| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated** | the `/s/*` rows note the banner |
| `docs/config-reference.md` | **updated** | `IOS_INSTALL_URL` |
| `living-memory/LLD.md`, `docs/architecture.md`, `living-memory/HLD.md` | n/a | no convention or wiring change |
| `docs/cross-client-invariants.md` | n/a | no shared constant |
| `docs/glossary.md`, ADR | n/a | no new term or decision |

## 5. Ship gate declaration
- **CI:** `backend-tests`, `mobile-typecheck`, testid-lint and `web-structure` green.
- **Evidence:** a `living-memory/TEST_LEDGER.md` entry. **Go-live:** release-lead sets `IOS_INSTALL_URL` at T0.
- Express lane declared by the operator? No.
