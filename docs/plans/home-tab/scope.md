# Feature Scope — Home tab

**Date:** 2026-10-02
**Entry point:** direct ask
**Builder:** session 2026-10-02 (lead + two build agents); plan in [plan.md](plan.md)
**Operator sign-off on waivers:** not needed (no waivers)

---

## 1. Analytics scope

- [ ] (a) New events specced
- [x] **(b) Existing events cover it:**
  - `tab_selected` with `tab: 'home'` — how often the Home tab is tapped from the bar (`tab` is a free string prop; nothing to register).
  - `screen_viewed` (auto-emitted by RootNav on every route change) with `screen: 'Home'` — how many launches land on Home; and with `prev_screen: 'Home'` on the destination — which of the four options people choose.
- [ ] (c) Waived

## 2. Schema & flag scope

- New/changed tables or columns: **none**
- New/changed feature flags: **`nav.home_tab`**, default **true**, client-only (no route reads it). → `config/features.json`, `backend/feature_flags.py` `FLAG_KEYS`, `backend/tests/fixtures/flags/*.json`, `mobile/src/state/useFeatureFlags.ts` baked default, `docs/config-reference.md`. **Graduation criterion:** remove the flag once one TestFlight build has run the checklist below clean and the operator confirms Home stays the front door. `nav.trades_landing` is unchanged and remains the flag-off launch behavior.
- New env vars / `model_config` keys: **none**. Rollback lever: set `nav.home_tab` false + `POST /api/feature-flags/reload`; takes effect on each device's next launch.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-home-tab.js` (`npm run test:home-tab`) — pins: once-at-mount imperative flag read; Home registered first in the bar; `launchTab` trades-first carve-out + `initialTab` fallback; the four option labels / targets / testIDs; no `FeedbackFAB` in `HomeScreen`; `app/home` route; flag parity across `features.json`, baked default, fixtures, `FLAG_KEYS`.
- [x] **Unit tests:** no new pytest — the flag is client-only; existing flag-fixture tests must stay green with the new key.
- [x] **Code-walk proof:** recorded in `living-memory/TEST_LEDGER.md` with the ship entry.
- [x] **Manual TestFlight checklist:**
  1. Returning user (has swiped before), cold launch → app opens on **Home**; bar reads Home · Rank · Acquire · Draft · Matches · League with Home highlighted; no label is clipped or truncated on the smallest supported iPhone.
  2. Home shows "What would you like to do today?" and exactly four options: Rank, Find a Trade, See Matches, View my Leagues.
  3. Tap **Rank** → Rank tab opens on the usual rank surface, Rank highlighted in the bar. Tap Home in the bar → back on Home.
  4. Tap **Find a Trade** → Acquire tab (trade builder/finder). Tap **See Matches** → Matches. Tap **View my Leagues** → League tab rankings.
  5. Feedback button is visible on Home, exactly one of it.
  6. Fresh install / new account: sign in, pick a league → lands on **Find a Trade** with the analyst guide running as before (not Home). After the first swipe, kill and relaunch → lands on Home.
  7. Tap a match push notification from a killed app → opens Matches, not Home.
  8. Kill-switch: with `nav.home_tab` false and the app relaunched twice → no Home tab, app opens on Find a Trade as it does today.
- [ ] WAIVED
- `testID`s added: `tab.home`, `home.screen`, `home.option.rank`, `home.option.trades`, `home.option.matches`, `home.option.league`

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added or changed |
| `living-memory/LLD.md` | n/a | no schema/route/invariant convention shifted |
| `docs/architecture.md` | n/a | no module wiring or data flow change |
| `living-memory/HLD.md` | n/a | one static screen; architecture unchanged |
| `docs/cross-client-invariants.md` | n/a | no shared constants; web has no tab bar |
| `docs/glossary.md` | n/a | no new domain term |
| ADR or `DECISIONS.md` entry | updated | new D- entry: Home is the launch tab for returning users; narrows the 2026-08-28 trades-landing ruling |
| `docs/config-reference.md` | updated | `nav.home_tab` row |
| `mobile/src/navigation/{CLAUDE,README}.md`, `mobile/src/screens/{CLAUDE,README}.md` | updated | tab list, route tree, screen inventory |
