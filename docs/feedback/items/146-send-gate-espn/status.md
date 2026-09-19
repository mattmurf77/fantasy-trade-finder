# Status — 146-send-gate-espn

```project-status
{
  "status": "shipped",
  "updated": "2026-07-18",
  "summary": "#146 — Send-in-Sleeper button showing on ESPN league",
  "evidence": "Carried forward as the last documented disposition, not a fresh production audit. Prior index merge corrections take precedence over older pre-merge notes. Last documented index disposition: shipped 2026-07-18 — FB-146 Send-in-Sleeper ESPN gate — CHANGELOG 2026-07-18, v1.9.0. Prior row preserved at ../../../reviews/2026/2026-09-06-project-status-migration/feedback-index.md."
}
```

## Historical notes

The material below is retained evidence. Its former status wording does not override the record above.

# #146 — Send-in-Sleeper button showing on ESPN league

**Status:** built (branch `trade-engine-v2`), pending QA
**Type:** bug — Sleeper-only affordance leaking onto imported ESPN leagues
**Date:** 2026-07-17

## Problem

`SendInSleeperButton` (flag `trade.send_in_sleeper`, currently ON) proposes a
REAL Sleeper trade via `POST /api/sleeper/propose`. On an imported ESPN league
(flag `espn.link`, also ON) that action is meaningless — there's no Sleeper
league to send to — yet the button rendered on every trade surface.

## Fix — one central gate

Gate lives **inside `SendInSleeperButton` itself**
(`mobile/src/components/SendInSleeperButton.tsx`), not at the mounts: the
component subscribes to `useSession.leagues` and returns `null` when its
required `leagueId` prop matches a cached league with `platform === 'espn'`
(reactive twin of `api/espn.isEspnLeague`). Every mount must pass `leagueId`,
so future mounts inherit the gate automatically — it can't be forgotten.

Fail-open by design: a league id not in the cached list (demo league, stale
cache) keeps the button, identical to pre-#146 behavior. Matches inbox cards
are cross-league; gating on the card's own `league_id` (not the active league)
is what makes per-card correctness fall out for free.

## Mounts covered (no changes needed at any of them)

- `mobile/src/screens/TradesScreen.tsx:2122` — swipe-deck direct-send button
- `mobile/src/components/TradeCard.tsx:313` — match-variant CTA (MatchesScreen inbox, both segments)
- `mobile/src/components/TradeCard.tsx:325` — swipe-variant send row
- `mobile/src/components/InLeagueCalculator.tsx:399` — calculator In-league mode

## Adjacent Sleeper-only affordance audit

- **Queue / "Send All"** (`TradesScreen`, flag `trades.queue_2k`): queued
  trades store a `buildSleeperUrl()` deep link and "Send All" opens each on
  sleeper.com — same class of leak on ESPN leagues. Flag is OFF in
  `config/features.json`, so no live exposure; left unfixed (out of scope),
  flagged here for whoever flips the flag.
- **SleeperConnect prompts** (`VerifyAccountBanner`, Settings verify): these
  are ACCOUNT-level verification (the user's identity is still a Sleeper
  account even when an ESPN league is active) — correct on ESPN contexts, not
  a leak. The button's own "Connect Sleeper first" prompt is gated away with
  the button.

## Files

- `mobile/src/components/SendInSleeperButton.tsx` — the gate
- `mobile/src/components/CLAUDE.md` — component row updated

## Verification

- `cd mobile && npx tsc --noEmit` — clean
