# Feature Scope — Tip jar C1: keep the paywall config warm for the Settings tip row

**Date:** 2026-11-01
**Entry point:** monetization-pm's tip-jar plan §3 "C1" (PR #569's `docs/plans/tip-jar/plan.md`); head-eng's GO, 2026-11-01. Must make the 11-06 binary.
**Builder:** eng-mobile worker for engagement-eng
**Operator sign-off on waivers:** not needed. The only waivers are the analytics and unit-test rows, each with a reason below.

---

**What:** one always-mounted observer, `mobile/src/state/useWarmPaywallConfig.ts` (`<WarmPaywallConfig />`, mounted once under RootNav's `Main`), fetches `['paywall-config','ios']` for a verified session while `monetize.paywall` is on. It uses the same key and queryFn as PaywallScreen, TipJarScreen and `useTipsOffered`, so all four share one cache entry. `useTipsOffered` stays `enabled: false`, so the Settings hub stays zero-network. With this in place, the Settings tip row shows for a user who has never opened the paywall, whenever the server serves `tips[]`. When the session stops being verified (sign-out, a user change, demo, unverified), the observer removes the cached `['paywall-config']` entry. Otherwise a demo or unverified session started in the same process would read the previous session's `tips[]` (release-lead QA on #575).

**Known limit:** a cold-start `settings` deep link has no `Main` beneath it, so no warm observer runs until the user reaches the tabs, and the row stays hidden until then.

## 1. Analytics scope

- [x] **(c) WAIVED, no analytics needed because:** this adds no surface and no user action. It only keeps a cached read warm. The tip row's taps and the TipJar purchase events are already covered (plan §3 Analytics: `paywall_viewed {source:'tip_jar'}`, `paywall_purchase_*`).

## 2. Schema & flag scope

- New/changed tables or columns: none
- New/changed feature flags: none. The observer reads the existing `monetize.paywall`.
- New env vars / `model_config` keys: none here. Nothing shows until S1's server knob (`paywall_tips_enabled`, plan §3 Server) serves `tips[]`. That knob is the deploy-free rollback lever.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-tipjar.js`, new pins 8d-8g. 8d and 8e EXECUTE the hook (transpiled, with the real `subscriptionSession.ts`): same key and queryFn, 5-minute `staleTime`, focus refetch on, and `enabled` true only for flag on plus a verified session (flag off, unverified, unknown and demo are all disabled). 8f: the four `['paywall-config']` subscribers in `src/` share one key and queryFn. 8g: mounted once under RootNav `Main`, and no other file (no Settings file) references it. 8h (executed): a drop from verified to unverified, demo, unknown (a user change) or signed out removes `['paywall-config']` exactly once. Verified to verified never removes it, removal never happens while the observer is enabled, and repeated renders don't repeat it. The existing 8c (`useTipsOffered` stays `enabled: false`) is unchanged.
- [x] **Unit tests:** WAIVED, because there is no backend change.
- [x] **Code-walk proof:** in the PR body (cold start → observer fetch → `useTipsOffered` reads the warm cache → row; unverified → no fetch).
- [x] **Manual TestFlight checklist:**
  1. On a verified (Sign in with Apple) session that has never opened the paywall, with `monetize.paywall` on and tips served (`paywall_tips_enabled`=1, S1): cold-start the app, then open Settings. "Support Fleeced" shows within a few seconds.
  2. Stay in the app for 35 minutes, then open Settings again. The row still shows.
  3. With the row showing, set `paywall_tips_enabled` to 0. Background the app for more than 5 minutes, return, then open Settings. The row is gone without a cold start. That proves the focus refetch, and that the kill lever reaches live clients.
  4. Start from a killed app on a demo or unverified session. There is no tip row. The "no `/api/paywall/config` request" half can't be seen on TestFlight without a proxy; its evidence is the executed 8e plus the runtime model.
  5. With `monetize.paywall` off: no `/api/paywall/config` request. This also can't be seen on TestFlight without a proxy; the evidence is the executed 8e.
  6. On a verified session with the row showing: sign out, then enter demo in the same process (no kill), then open Settings. There is no tip row (8h).
- `testID`s added/renamed: none.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route or contract change. It reads the existing `/api/paywall/config`. |
| `living-memory/LLD.md` | n/a | No convention shift. This is one more observer of an existing query. |
| `docs/architecture.md` | n/a | No module wiring or data-flow change beyond a client cache read. |
| `living-memory/HLD.md` | n/a | No architecture shift. |
| `docs/cross-client-invariants.md` | n/a | No shared constant or enum. |
| `docs/glossary.md` | n/a | No new domain term. |
| ADR or `DECISIONS.md` entry | n/a | The placement follows the plan's own suggestion ("under `Main`"). Recorded in `mobile/src/state/CLAUDE.md` and `mobile/tests/README.md`. |

## 5. Ship gate declaration

- **CI green:** `backend-tests`, `mobile-typecheck` (including every `check-*.js`) and `maestro-testid-lint` must pass on the pushed sha.
- **Evidence recorded:** TEST_LEDGER entry from the lead at merge.
- **TestFlight verification:** the operator runs the §3 checklist on the 11-06 binary, after S1's knob serves tips.
- Express lane declared by the operator? no.
