# ADR-006 — Account-Later Onboarding (Apple Moves from Front Door to Save Moment)

**Status:** Accepted (shipping dark behind `onboarding.v2` + `onboarding.landing` / `onboarding.apple_save_moment`)
**Date:** 2026-07-17
**Initiative:** Onboarding & conversion redesign (docs/plans/onboarding-conversion/plan.md v2.1); 3-round ux-design × pm-growth review, converged 2026-07-17. Amends the account-first posture of the account-auth plan (docs/plans/account-auth-plan-2026-07-11.md, P2.6).

---

## Context

P2.6 made Sign in with Apple the primary portal on SignInScreen, with Sleeper-username entry demoted. That decision established durable identity (`accounts` + `acct_*` account-only sessions) but placed the highest-friction step at the exact top of the funnel — before a new user has seen a single trade card.

Facts the redesign rests on:

- Sleeper "login" (`POST /api/extension/auth`) is a **public-API username read** — no password, no OAuth. It is identity-lite, not signup.
- Boards, likes, swipes, and tiers **already persist server-side keyed to the Sleeper user_id**, with or without an Apple bind. In-memory session loss (deploy/restart) is recovered by re-minting from the same username.
- `auth.enforce_verified_writes` is **false** (grace mode): unverified writes are allowed and logged.
- The trade engine produces cards from the consensus-seeded board with zero ranking effort — first value does not require an account.

## Decision

**Account-later, not account-less.** Apple remains the *only* durable, cross-device identity. It moves from the front door to the moment the user first has something durable to protect:

1. **Landing** (flag `onboarding.landing`): primary surface is the Sleeper username field. Apple appears as a quiet "Already have an account? Sign in with Apple" re-entry link — required, because P2.6 account-only users may have no Sleeper username to type; removing their door would strand the already-converted cohort.
2. **Save-moment prompt** (flag `onboarding.apple_save_moment`): the Apple modal fires on the first save-moment-class event — first liked trade or first Quick Set save. **Honest framing only** (cross-device / device-loss protection). "Save your board" framing is prohibited: boards persist regardless, and a discoverable false claim poisons every subsequent ask (push, future paywall).
3. **Ask policy:** max one automatic modal per save-moment class (first like, first Quick Set save, first mutual match), decline persisted (`ftf_onboarding_state`), never an immediate re-ask. Unbound users with ≥N swipes get one *non-modal* dismissible banner above the session-2 deck (iOS cannot render UI at backgrounding, so any "exit ask" is really a re-entry modal — rejected in review). An evergreen "Back up your board" row in Settings carries the ask thereafter.
4. **Bind target:** Apple binds to the (unverified) Sleeper username of the active session. Precondition: the first-run identity-confirm strip ("Trading as @username — not you?"), which catches valid-but-wrong-username sessions before a durable bind. SleeperConnect verification at the save moment was **rejected** (friction at the peak-conversion point); verification lives in Settings post-bind.

### Riders (binding constraints)

- **`auth.enforce_verified_writes` freeze:** this flag must NOT be flipped to true until save-moment Apple bind rate is measured and judged acceptable (via `apple_prompt_*` events). Flipping it earlier write-blocks the majority population this funnel deliberately creates (username-only users mid-hook). The account-auth plan's P3 timeline is subordinated to this rider.
- **Unbind/rebind path** (support pre-answer): if the true owner of a mistyped username appears, the operator remedy is: the squatter's Apple account is unbound from the Sleeper user_id (accounts table edit / future admin route), the squatter keeps an account-only (`acct_*`) board via reset, the owner signs in and may bind normally. With enforcement frozen there is no write-harm window; `bind_sleeper_user` stickiness is an operator-level override in this one case. Revisit as a self-serve flow if it occurs more than rarely.
- **Session-2 silent re-init:** the persisted last-username auto-re-init must keep the "not you?" affordance reachable (Settings) so a typo'd identity does not self-perpetuate.

## Consequences

- **Positive:** first value precedes the first friction; the Apple ask arrives with self-evident value (something worth keeping) and honest copy; the funnel's top is one text field; P2.6's substance (durable identity, sticky bind, device-loss restore) is preserved intact.
- **Negative / watch:** a larger population of unbound, unverified users exists at any time (accepted: their data already persists by username; measured by the session-2-return-unbound metric). Account-only Apple users remain unable to self-revalidate sessions (one-shot identity tokens) — unchanged from P2.6. If save-moment bind rate disappoints, the recourse ladder is: real capability at bind (multi-device sync surfaced in UI) → earlier non-modal exposure; **not** false loss-framing and not front-door restoration.
- SignInScreen's Apple-primary layout is superseded when `onboarding.landing` is enabled; until then current behavior is unchanged (all flags dark).

## Alternatives considered

- **Keep Apple-first (status quo):** rejected — maximum friction before any value; conversion architecture backwards for a product whose hook is one screen away.
- **Apple fully removed from session 1:** rejected — the save moment is peak motivation; deferring past it wastes the loss-aversion window, and account-only users need a session-1 door regardless.
- **Capability-gate the bind (notifications require Apple):** rejected — push tokens are device-bound, not account-bound; a synthetic wall reads as a dark pattern at the trust-critical moment.
- **Verification at bind:** rejected as above; Settings post-bind instead.
