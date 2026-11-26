# Feature Scope — Paid launch: close the gaps between the built paywall and a launchable paid app

**Date:** 2026-11-21
**Entry point:** direct ask (operator, via the coordinating session): "build monetization via paid subscriptions into the app. Hide features behind the paid subscription requirement and prompt users to upgrade in the UI if they try to access a feature they cannot."
**Builder:** paid-launch builder session, branch `feat/paid-launch` (from `origin/main` `4a49ea89`)
**Operator sign-off on waivers:** pending. The waivers are listed in §6 and are passed to the operator by the coordinating session.

Companion docs in this folder:

- [code-walk-proof.md](code-walk-proof.md): the readiness verdict and the per-entry-point walk.
- [turn-on-runbook.md](turn-on-runbook.md): the ordered steps to turn enforcement on, and to roll it back.

- [What changes](#what-changes)
- [1. Analytics scope](#1-analytics-scope)
- [2. Schema & flag scope](#2-schema--flag-scope)
- [3. Evidence scope](#3-evidence-scope)
- [4. Docs scope](#4-docs-scope)
- [5. Ship gate declaration](#5-ship-gate-declaration)
- [6. Waivers](#6-waivers)
- [7. Not changed, by design](#7-not-changed-by-design)
- [8. Candidates to put behind Pro (for the operator)](#8-candidates-to-put-behind-pro-for-the-operator)

## What changes

The subscription system (entitlements, the server gate, the paywall, the VerifySheet, the deck preview,
Settings › Subscription) was already built and is dark. This change does not rebuild or re-gate anything.
The server's free/paid split is unchanged: **free** = connect leagues, rank, league views, standings and
forecast, the first deck page; **Pro** = finding and sending trades (the `GATED` rows of
`backend/paywall_gate.ROUTES`).

With enforcement on, some surfaces showed the user a failure message on top of the paywall, or a false
empty state behind it. This change fixes those, in the mobile app only:

| Gap (enforcement on, a non-subscriber) | Fix |
|---|---|
| Send in Sleeper / MFL / ESPN: the paywall opened **and** "Couldn't send. Something went wrong…" showed on top of it. On the verify 403, the button's own "Verify your account" alert also showed on top of the VerifySheet. | Each catch checks `gateSignalFor` first and shows nothing more (`SendInSleeperButton.tsx:308`, `SendInMflButton.tsx:166`, `SendInEspnButton.tsx:205`). |
| The calculator's ✓ (queue for the other manager): the paywall opened and the toast "Couldn't queue that. Try again." showed. | `queueCalcTrade` returns `toast: null` on a gate answer (`utils/queueCalcTrade.ts:86`). |
| Shop a player / More offers: "Couldn't sweep the league" + Try again showed behind the paywall. Try again looped back into the paywall. | The new `PaywallGateNotice` renders instead: the existing `mon.lock.find` line plus one Primary, "See plans" or "Continue" (`ShopOffersBody.tsx:868`). |
| The single-pin ideas panel: the false empty state "No defensible packages found around this asset right now." | The same notice (`AssetIdeasPanel.tsx`, fed by `TradesScreen.tsx:8119`). |
| After a purchase or Restore, Shop and the panel would keep the notice, offering See plans to a new subscriber. | Each refetches its sweep when `useEntitlements.pro` turns true while the notice shows. This is a refetch, not routing. |
| Every gated `useQuery` was retried once (`retry: 1`). A user who dismissed the paywall within the retry delay got it again. | `retryUnlessGated` keeps the one retry for everything except a 402 `pro_required` (`state/queryClient.ts:27`). |

`PaywallGateNotice` (`mobile/src/components/PaywallGateNotice.tsx`):

- It renders only after the server refused a request this surface made. It is never a pre-tap teaser and never a locked-feature card (legal R28.8 #5).
- Verify vs paywall is chosen from the server's answer and `isUnverifiedSession()` alone. It reads no entitlement field (R28.9 / D15).
- Every string is an existing `mon.*` key, verbatim.

All of it is null while `monetize.paywall` is off, because `gateSignalFor` returns null when the flag is off. So the dark behaviour is byte-identical. Production already runs `monetize.paywall` on (G-076), so these paths become live only when the server starts sending 402s, that is, at enforcement.

## 1. Analytics scope

- [x] **(b) Existing events cover it.** The server's `paywall_gate_hit` counts each refusal by route family, and the client's `paywall_viewed {source:'gate', gate, kind}` counts each paywall the router opens.
  - "See plans" on the new notice opens the paywall through `openPaywall({source:'gate'})`, so it fires the same `paywall_viewed`.
  - No event is added, changed or removed.
  - `calc_trade_queued` still records `{queued:false, reason:'error'}` on a 402. That is pinned by `check-paid-launch` 2d: giving it a `pro_required` reason would be a taxonomy change, which is a bright-line surface.

## 2. Schema & flag scope

- **Tables and columns:** none.
- **Feature flags:** none added or flipped. `config/features.json` and `backend/tests/fixtures/flags/release.json` are untouched, and `monetize.*` stays false in both.
- **Env vars and `model_config` keys:** none added. The rollback lever is the existing deploy-free knob `paywall_enforce_enabled` (see [turn-on-runbook.md](turn-on-runbook.md) §R).

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-paid-launch.js` (`npm run test:paid-launch`), 17 checks.
  - EXECUTED: `utils/queueCalcTrade.ts` (gate off → today's toast; gate on → no toast on a 402 or a verify 403; a 500 and server refusals keep their lines; the analytics row is unchanged); `state/queryClient.ts` (`retryUnlessGated`); `components/PaywallGateNotice.tsx` under a fake React (gate off → null; See plans → `openPaywall {source:'gate', kind, gate}`; a verify answer or an unverified session → Continue → `openVerify`).
  - [shape]: the three Send catches check the gate before any alert except the outcome-unknown one, which `check-send-timeout` D pins first; Shop's and the panel's gate branch comes before the generic branch; the notice mounts only on an error branch; the notice reads no entitlement field and holds no hard-coded copy.
  - **Sabotage, red then restored (8):** S1 queue gate return dropped (2a, 2b red); S2 retry predicate ignores 402 (5a); S3 MFL gate branch disabled (1a); S4 panel gate branch disabled (4a); S5 notice ignores unverified sessions (6c); S6 Shop gate branch disabled (4b); S7 Sleeper gate check removed (1a, 1b); S8 ESPN gate branch disabled (1a); S9 Shop's refetch-on-pro effect removed (7a).
- [x] **Unit tests (backend):** none added, because no gate or route changed. The existing `test_paywall_gate_allowlist.py` already fails CI on any Flask rule missing from `ROUTES` and pins the gated set exactly (`test_gated_set_is_pinned`). It passes on this branch: every one of today's rules is classified, and the 32 gated rules are the C2 list plus every `/api/overhauls*` and `/api/win-now/*` rule.
- [x] **Code-walk proof:** [code-walk-proof.md](code-walk-proof.md).
- [x] **Manual TestFlight checklist:** [turn-on-runbook.md](turn-on-runbook.md) §C. It builds on [`../../monetization/iap-enablement/sandbox-test-checklist.md`](../../monetization/iap-enablement/sandbox-test-checklist.md) and the launch scope's T1–T20 rather than repeating them.
- `testID`s added: `shop.gated`, `shop.gated-cta`, `trades.asset-ideas-gated`, `trades.asset-ideas-gated-cta`. `testid-lint` OK.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route or contract change. The 402 body and its `gate` enum are unchanged. |
| `living-memory/LLD.md` | n/a | No convention shift. A gate answer is still recognised through `gateSignalFor`, the existing seam. |
| `docs/architecture.md` / `living-memory/HLD.md` | n/a | No module wiring or data-flow change. |
| `docs/cross-client-invariants.md` | n/a | No shared constant changed. |
| `docs/glossary.md` | n/a | No new term. |
| ADR / `DECISIONS.md` | n/a | No new decision. The visible lock affordance is not built (§6 W3), and that is left to the operator. |
| `mobile/src/components/CLAUDE.md` | **updated** | `PaywallGateNotice` row. |
| `mobile/tests/README.md` | **updated** | `check-paid-launch` in the Monetization row. |
| `docs/plans/README.md` | **updated** | `monetization-launch/` row. |
| `living-memory/TEST_LEDGER.md` | **updated** | 2026-11-21 entry. |

## 5. Ship gate declaration

- **CI:** `pytest backend/tests`, `tsc --noEmit` and testid-lint must be green on the pushed sha. The local results are in TEST_LEDGER.
- **Evidence:** TEST_LEDGER 2026-11-21 "Paid launch".
- **TestFlight:** the operator runs [turn-on-runbook.md](turn-on-runbook.md) §C before raising the knob.
- **Express lane:** not declared, so the full gates apply.

## 6. Waivers

- **W1, the analytics change, is waived (§1).** Existing events cover it, and no event changes.
- **W2, a new backend test, is waived.** No backend file changed, and the allowlist test already proves the route coverage the operator's acceptance (a) needs.
- **W3, a visible Pro/lock mark on entry points before the tap, is NOT built.** The brief asked for it "where the design system and existing monetization copy support it". Neither does today:
  - There is no `lock` glyph in the Chalkline icon set (`components/chalkline/Icon.tsx`). Adding one is a design-system change.
  - There is no approved copy for a "Pro" tag. Every `mon.*` string is verbatim from marketing §9 with legal's rulings.
  - Legal R28.8 #5 forbids a locked-feature card (`check-paywall-gate` 4l).
  - Find a trade is **not** locked for a never-entitled user, because the first page is free. A lock on it would be false for exactly the users the preview is meant to convert.
  - The deck's D4 rule ("after a decline the paywall appears only in response to the user's own gated action") argues against an always-on badge.
  - What exists instead: the Send pre-check opens the paywall **before** the confirm step (`SendInSleeperButton.tsx:72`); the deck's preview end card states the lock in place; the new notice states it in place on Shop and the ideas panel.
  - This needs an operator, ux, legal and design call. See [code-walk-proof.md](code-walk-proof.md) §5.
- **W4, auto-resume of the original action after a purchase, is NOT built** (see code-walk §4). After a purchase the deck's page path resumes (`TradesScreen.tsx:5637`). Shop and the ideas panel now refetch on `pro`. A first search, a Send and the queue need a fresh tap. Sends are never re-sent by design (D18).
- **W5, polish for the surfaces the audit recommends cutting, is waived on purpose.** That covers Win Now, Team Overhaul, standing offers, ESPN send and Today's Trade. The walk confirms each fails safe: no Pro content is served, and the paywall opens. The remaining roughness is listed in code-walk §3.

## 7. Not changed, by design

- **The server gate table.** The allowlist test proves it is complete.
- **The routing rule in `usePaywallGate.ts`.** It still reads no entitlement field.
- **R28.9 / R28.14 (the unverified-session rules).** The notice routes through the same `isUnverifiedSession()` and the server's `verify` answer.
- **The billing-safety tests.**
- **The paywall copy.** The bullets name ESPN and Win Now. If the operator cuts either, `mon.pay.b3` and `mon.pay.b4` overclaim. That is a marketing and legal copy change, flagged in the runbook §A.

## 8. Candidates to put behind Pro (for the operator)

These are not built. Each one moves a feature that is free today, so it is the operator's product decision.

1. **`GET /api/trades/matches` and `/matches/all` (viewing Matches)** — currently free on purpose, so a lapsed or never-paid user who gets a "someone liked your trade" push can see it (T12). Gating the *detail* while keeping the push and the count free is the classic conversion hook: the match is the strongest moment of intent. The risk is legal/ux: it's a leaguemate's action surfaced to a non-payer.
2. **`POST /api/trade/evaluate`, the calculator's value comparison** — free today and the app's most-used tool. Gating it would make the free tier mostly ranking. I recommend keeping it free, because it is the top of the funnel. It is listed because it is the largest lever.
3. **`GET /api/league/team-review` / Team Review**: free today. It is a roster diagnosis whose "Find my trades" already leads into the gated deck. It is a natural Pro feature if the operator keeps it at launch, though the audit recommends cutting it.
4. **`GET /api/trends/consensus-gap`, `/trends/contrarian`, `/league/contrarian`**: the "where your board disagrees with the market" reads. They feed trade intent directly and are cheap to gate (pure reads). Note that `mon.lock.free` names "trends" as free, so gating these needs a copy change.
5. **`POST /api/leagues/<id>/projection-runs` (running a new forecast)**: the *read* of the forecast stays free per the operator's earlier decision 9, but on-demand re-runs cost compute. Gating the run while keeping the latest result free fits "free = view".
6. **Free-agent moves (`/api/league/free-agents/move`)**: free today and kept free deliberately (its own consent gates). It is listed only for completeness; I recommend keeping it free.
