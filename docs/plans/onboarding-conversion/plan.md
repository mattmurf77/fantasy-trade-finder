# Onboarding & Conversion Redesign — Value-First First Launch

*2026-07-17 — planning doc. Companion to the ranking-methods scorecard (see below). Not yet built.*

## Problem

First launch today: Apple sign-in (maximum friction) is the front door → LeaguePicker → Main → Rank tab presents a 5-way ranking-method chooser (maximum cognitive load) before the user has seen a single trade. The app's actual hook — trade suggestions for *your* team — arrives last. Nothing about the flow is designed around conversion.

Two facts make the fix cheap:

- **Sleeper "login" is username-only** (public API read, no password/OAuth — `POST /api/extension/auth`). It is not signup friction and shouldn't be treated as such.
- **The trade engine works off the consensus-seeded board with zero ranking effort**, and a full demo-league engine exists (`POST /api/session/demo`) behind the off flag `landing.try_before_sync`.

## Core inversion

| | Today | Proposed |
|---|---|---|
| First screen | Apple sign-in (primary) | Sleeper username ("See trades for your team") |
| First value | After auth + league + ranking chooser | Trade cards in <60s, consensus-seeded |
| Ranking ask | 5-way chooser up front | Contextual, one method (Quick Set), after ~3–5 swipes |
| Apple sign-in | Front door | Save moment — first liked trade or first Quick Set save |

## First-launch flow

1. **Landing** (replaces sign-in gate): one field — Sleeper username. Escape hatch: "Just looking? Browse a sample league" (flip `landing.try_before_sync` on). No Apple button here; copy makes clear no account is being created.
2. **League**: exactly one league → auto-select, skip LeaguePicker. Multiple → picker. Zero → demo league with banner.
3. **Hook** (<60s from cold open): land on **Trades tab** with cards pre-generated during league init. Swipes start immediately — and swipes already nudge Elo (K=8/4), so the user is ranking without knowing it.
4. **Contextual ranking ask** (min 2–5): after ~3–5 swipes or a pass, inline prompt: "These trades use consensus values. Fix them in 2 minutes →" deep-linking into **Quick Set for one position**, then bounce back to Trades so the board change visibly changes the suggestions (the aha). Sets `rankingMethodPref='quickset'` implicitly; the RankHome 5-way chooser never appears in session 1.
5. **Signup moment**: Apple prompt on first **liked trade** or first **Quick Set position saved** — "Save your board and liked trades." Loss-aversion-timed. Keep the existing deferred push-permission gate (Find-a-Trade unlock) *after* this so asks never stack.

## Ranking methods by journey point

| Journey point | Method | Rationale (scorecard weighted score) |
|---|---|---|
| Session 1, min 0–2 | Trade swipes (passive) | The hook is a ranking input (8.9) |
| Session 1, min 2–5 | Quick Set, one position | Best activation (7.6); visible payoff loop |
| Session 1 end / session 2 | Trio matchups | Habit loop 9/10 (7.7); prompt via existing push hook |
| Week 1, ~2 positions tiered | Quick Rank | Only meaningful once tiers exist; keep finish-prompt chain |
| Week 1–2, contextual | Pick Anchors | Offer when user disputes a trade value (5.9) |
| Never promoted | Tier drag, Manual ranks | RankMenu "More ways to rank" only (4.1 / 2.6) |
| On format switch | Copy-from-format | Already contextual |

## Scorecard reference

Categories (1–10; user's three priorities double-weighted: Ease of Completion 20%, Low Cognitive Load 20%, Time-to-Hook 20%, First-Session Activation 15%, Engagement 10%, Habit/Return 10%, Board Quality 5%):

| Method | Ease | Cog. load | Hook | Activation | Fun | Habit | Quality | Weighted |
|---|---|---|---|---|---|---|---|---|
| Quick Set | 9 | 7 | 8 | 9 | 6 | 5 | 7 | 7.6 |
| Trio matchups | 9 | 8 | 5 | 7 | 9 | 9 | 8 | 7.7 |
| Quick Rank | 8 | 6 | 4 | 5 | 6 | 6 | 7 | 5.9 |
| Pick Anchors | 7 | 5 | 6 | 5 | 6 | 5 | 8 | 5.9 |
| Tier drag board | 4 | 4 | 3 | 3 | 4 | 6 | 8 | 4.1 |
| Manual ranks | 2 | 2 | 2 | 2 | 2 | 4 | 9 | 2.6 |
| Trade swipes* | 10 | 9 | 9 | 8 | 9 | 10 | 4 | 8.9 |

*Passive refinement signal, not a standalone board builder.

## Build list (order)

1. Flip `landing.try_before_sync` + demo entry link (backend done; config + one link).
2. Rework SignInScreen → username-first landing; Apple moves off it. ⚠️ Softens the P2.6 account-first decision — frame as *account-later*: Apple stays the only durable identity, moved from front door to save moment. Write a short ADR.
3. Auto-skip LeaguePicker for single-league users.
4. First-session landing = Trades tab, cards pre-generated at league init.
5. Contextual Quick Set prompt after N swipes (inline card + deep link).
6. Save-moment Apple prompt + persisted `ftf_onboarding_state` flag in AsyncStorage (app currently has no persisted first-run flags).
7. Demote RankHomeScreen chooser to "More ways to rank" surface.
8. Funnel instrumentation (client → existing server `user_events`): `landing_username_submitted`, `first_trade_card_seen` (+ms since open), `first_swipe`, `quickset_prompt_shown/accepted`, `apple_prompt_shown/accepted`, `trio_session_started`.

## Success criteria

- Time-to-first-trade-card **< 60s** cold open (north star of the redesign).
- Activation: first swipe in session 1 — target >80% of username submitters.
- Conversion: Apple bind rate at the save moment.
- Retention: % of week-1 users running a trio session on a later day.
