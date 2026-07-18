# Onboarding & Conversion Redesign — Value-First First Launch (v2.1, review-converged + guided layer)

*2026-07-17 — v2 after a 3-round adversarial review: ux-design × pm-growth, growth holding final say, shared goal = user conversion (activation → Apple bind). Both roles signed off; no open dissents. Review log at bottom.*
*v2.1 (same day, operator-directed): adds the **guided layer** — F2P onboarding mechanics (gesture hint, coach marks, celebration beats, Assistant GM voice) WITHOUT an animated mascot. See "Guided layer" section; not panel-reviewed, rides on screens the plan already rebuilds.*

## Problem

First launch today: Apple sign-in (maximum friction) is the front door → LeaguePicker → Main → Rank tab presents a 5-way ranking-method chooser (maximum cognitive load) before the user has seen a single trade. The hook — trade suggestions for *your* team — arrives last.

Facts that make the fix cheap:

- **Sleeper "login" is username-only** (public API read, no password — `POST /api/extension/auth`). Not signup friction.
- **The trade engine works off the consensus-seeded board** with zero ranking effort; a full demo-league engine exists (`POST /api/session/demo`) behind the off flag `landing.try_before_sync`.
- Boards, likes, and swipes **already persist server-side keyed to the Sleeper user_id** — with or without Apple (`auth.enforce_verified_writes` is false). Apple's real value is durable cross-device identity, not "saving."

## Core inversion

| | Today | v2 |
|---|---|---|
| First screen | Apple sign-in (primary) | Sleeper username ("See trades for your team") + quiet "Already have an account? Sign in with Apple" link |
| First value | After auth + league + ranking chooser | Trade cards, pre-generated, <60s from **warm** server |
| Ranking ask | 5-way chooser up front | Inline swipeable prompt card → Quick Set (one position) → back to Trades with a visibly changed deck |
| Apple sign-in | Front door | Save moment (first like / first Quick Set save), honestly framed |

## First-launch flow (converged)

1. **Landing.** One field: Sleeper username, framed "See trades for your team." Quiet links below (styled like the current demo link, never competing with the field): "Already have an account? Sign in with Apple" (re-entry for P2.6 account-only users — without it they're stranded) and "Just looking? Browse a sample league." Error states are first-class: not-found copy explains username ≠ team name; Sleeper-down/offline elevates the demo escape into the error state ("Sleeper isn't responding. Browse the sample league while we retry →"). All failures emit reason-coded events.
2. **League.** One league → auto-skip the picker (fallback: picker errors fail back to the landing with league name + retry; picker stays reachable via LeagueSwitcherSheet). Multiple → picker. Zero → demo with banner.
3. **Hook — Trades tab first.** Card generation kicks the moment username auth returns (during league init), cards stream into a skeleton first-run deck — the manual "Hit 'Find a Trade'" empty state never shows on first run. First-run chrome collapses to one control row (invite banner deferred until after first swipe; one-tap inferred-outlook confirm stays). Guards on the first impression:
   - **Identity-confirm strip**: avatar + "Trading as @username — not you?" (a valid-but-wrong username silently loads a stranger's team; this also gates the later Apple bind). Stays reachable post-first-run via Settings.
   - **Provenance chip** on every card: "CONSENSUS VALUES" → becomes "YOUR BOARD" after Quick Set — makes the upgrade legible and is the evergreen Quick Set entry point.
   - **Fit-led first deck**: lead with roster-fit narratives (`trade.need_fit`) — positional need is the only personal signal before any ranking, and it defuses the consensus-vs-consensus "value-neutral shuffle" problem.
   - "Bad trade?" flag stays visible; counted as a first-session quality metric.
4. **Contextual ranking ask.** Inline **swipeable prompt card** in the deck (same gesture grammar, never a modal): "These trades use consensus values. Fix them in 2 minutes →". Trigger: **first pass after swipe 2, else after 3 swipes**; max one show per session. Dismiss = snooze (re-offer at deck-exhausted, once in session 2, then retire to the provenance chip — "dismissed forever" does not exist). Deep-links to **onboarding-mode Quick Set** (one position): suppresses the Quick Rank finish-prompt, **returns to Trades, forces deck regeneration**, and shows a diff banner — "Re-ranked with your WR board — N new trades" (before/after value chip on a previously-seen card = stretch). *This regeneration step is mandatory: without a visible deck change the ask is pure interruption and the ranking loop never reinforces.*
5. **Save moment — Apple.** Modal prompt on first **like** or first **Quick Set save**, whichever first. **Honest framing** (cross-device / keep your board if you switch phones — never "save your board," which is false). Decline = one tap, persisted, no immediate re-ask. Policy: max one auto-prompt per save-moment class (first like, first Quick Set save, first mutual match), then never automatically; a persistent "Back up your board" row in Settings carries it. Unbound users with ≥N swipes get one **non-modal dismissible banner** above the session-2 deck (never a re-entry modal). On first like, the Apple prompt resolves before the **share button** appears on the liked card (native share sheet: card image + link, user-initiated, persistent thereafter) — never two simultaneous CTAs. Apple binds to the unverified username (identity strip is the precondition); SleeperConnect verification lives in Settings post-bind.
6. **Session 2+.** Persisted username + silent session re-init on cold open — unbound users never retype. Deck-exhausted state becomes the trio entry: "You've seen every trade. Sharpen your board with quick head-to-heads →" (the push-independent path to the habit loop). Push-permission gate stays strictly after the Apple moment.

## Guided layer (v2.1 — F2P mechanics, no mascot)

Rationale: F2P games win first sessions with guided mechanics, not characters. The character half is rejected for FTF — a cartoon companion conflicts with Chalkline (ADR-004/005), risks patronizing a hobbyist-expert audience whose identity the product flatters, and costs weeks the mid-Aug window doesn't have. The mechanics half is adopted, thin:

- **Swipe-gesture hint** on card 1, first run only (one animated nudge on the card itself; the swipe remains the tutorial).
- **Coach marks — 4 maximum, each shown once, always dismissible**, persisted in `ftf_onboarding_state`: (1) swipe hint, (2) provenance chip ("these are consensus values — yours after Quick Set"), (3) diff-banner moment (reinforce attribution: *your* board changed the deck), (4) deck-exhausted trio entry. Nothing else gets a coach mark; a fifth requires removing one.
- **Celebration beats** at the two moments that precede the Apple ask: first like and first Quick Set save get brief ceremony (Chalkline-compliant — motion/copy, no confetti-kitsch). Conversion asks land better immediately after a win; v2 had zero celebration beats.
- **Assistant GM voice**: a consistent textual persona — the front office is fantasy's native fiction, and it frames the user as the GM the app works *for*. Lives in onboarding copy, prompt card, diff banner, empty states, and later push notifications (where mascot-personality actually earns its money). Voice definition → mkt-brand/mkt-writer; no character art, no dialogue system.
- **Parked, not killed**: an animated mascot/companion is a post-launch experiment at best, contingent on instrumented session-1 drop-off showing *guidance* (not friction) is the leak. Any such experiment needs an mkt-brand proposal + ADR (Chalkline fork).

Guardrail: coach marks are exempt from nothing — they're interruptions, so they obey the same TTFV discipline as everything else (once, dismissible, never modal, never stacked with another ask).

## Ranking methods by journey point (unchanged from v1, ratified by both roles)

| Journey point | Method | Notes |
|---|---|---|
| Session 1, min 0–2 | Trade swipes (passive) | The hook is a ranking input (Elo K=8/4) |
| Session 1, min 2–5 | Quick Set, one position | Via prompt card; onboarding mode returns to Trades with regenerated deck |
| Session 1 end / session 2 | Trio matchups | Deck-exhausted entry + push hook; the habit loop |
| Week 1, ~2 positions tiered | Quick Rank | Existing finish-prompt chain (suppressed only in onboarding mode) |
| Week 1–2, contextual | Pick Anchors | Offer when a user disputes a trade value |
| Never promoted | Tier drag, Manual ranks | "More ways to rank" only |
| On format switch | Copy-from-format | Already contextual |

Rank tab default for everyone (prompted or not): **Quick Set directly + "More ways to rank" header link.** The 5-way chooser is never a default; it becomes the "More ways to rank" surface. (Off the cut line permanently — after the routing changes it is load-bearing, not cosmetic.)

## Final build list (ordered; growth-ratified round 3)

1. **Event ingestion + core events (8a)** — an-data-architect tracking plan v2 §S2 endpoint + events in its `object_action` taxonomy: `landing_username_submitted`, `first_trade_card_seen` (+ms, cold-start marker), `first_swipe`, `apple_prompt_shown/accepted/declined/dismissed`, **plus reason-coded failure events**. Ships against the CURRENT flow; **~2 weeks baseline, capped so the new flow flips before mid-Aug** (July–Aug ramp is the prize). Baseline TTFT samples tagged pre/post keep-warm and pre/post the item-4 pregen hook.
2. **Offline deck-quality + timing eval — GATE.** Script 10–15 real leagues with the exact production first-run flag config (incl. fit-led ordering): human-score first 5 cards (insult rate <3%, empty-deck <5%, proposed), measure init+pregen latency. Fails → engine cold-start work jumps the queue; the funnel does not ship showcasing a deck that insults strangers.
3. **Keep-warm ping** (cron precedent exists); paid-Render-tier memo → fin-budget (recommended as a conversion expense, non-blocking).
4. **Trades-first hook screen**: pregen at auth-return **hooked into the existing username path too**, skeleton/streamed deck, first-run chrome collapse (mode flag on the existing screen, not a new screen), provenance chip, identity strip, visible bad-trade flag, **`ftf_onboarding_state` scaffold** (read by items 7–8). *Guided layer: swipe-gesture hint on card 1 + coach marks 1–2 (swipe, provenance chip), state in the same scaffold.*
5. **Username-first landing**: field + Apple re-entry link + not-found copy + Sleeper-down demo escape (**`landing.try_before_sync` flips here** — the escape is its first consumer) + **ADR**: account-later (Apple = sole durable identity, moved to save moment); `auth.enforce_verified_writes` frozen until bind rate is measured; bind-to-unverified rationale; unbind/rebind path for mistyped-username ownership disputes.
6. **LeaguePicker auto-skip + fallback.** *Serialize with item 5 (shares its inline-error surface).*
7. **Contextual Quick Set**: prompt card (trigger: first pass after swipe 2, else 3 swipes; snooze semantics) + onboarding-mode Quick Set (suppress finish-prompt, return to Trades, force regeneration, diff banner; value chip = stretch). *Guided layer: coach mark 3 on the diff-banner moment; celebration beat on first Quick Set save (fires before the Apple prompt it triggers).*
8. **Save-moment Apple prompt**: honest framing, decline/re-prompt policy, Apple-specific `ftf_onboarding_state` fields, persisted-username silent re-init, session-2 non-modal banner (≥N swipes unbound), share sheet on liked card (+`trade_card_shared`). *Guided layer: celebration beat on first like, resolving before the Apple prompt (win → ask ordering; never two overlapping surfaces).*
9. **Ranking-surface routing**: chooser demotion → "More ways to rank", Rank tab defaults to Quick Set, deck-exhausted → trio entry. *Guided layer: coach mark 4 on the trio entry.*
10. **Demo path**: demo→real persistent bar ("See this for YOUR team →"), redraft label ("Dynasty values shown") + segment tag (excluded from activation denominators). *(Demo-routing of real redraft users rejected: real league + honest label beats fake demo data.)*
11. **Remaining events (8b)**: quickset prompt shown/accepted/snoozed, deck regeneration/diff, share, demo crossover (`demo_session_started` → `landing_username_submitted`), trio session, deck-exhausted, coach marks shown/dismissed (per mark), celebration beats fired.
12. **Assistant GM voice pass** (v2.1): mkt-brand defines the persona (one page: tone, vocabulary, what it never says); mkt-writer applies it across all onboarding copy touched by items 4–10 (landing, prompt card, diff banner, celebration beats, empty/error states, coach marks). Copy-only; runs in parallel with items 4–7 so screens land with voiced copy, not lorem-ipsum-then-rewrite.

**Cut order under schedule pressure:** (1) F2 before/after value chip, (2) share sheet, (3) demo polish (bar + label; the flag flip stays), (4) coach marks 3–4 + celebration ceremony (the moments still fire, just plainer — swipe hint and the provenance/diff mechanics are never cut with them). **Never cut:** instrumentation baseline, deck eval, Apple re-entry link, onboarding-mode Quick Set + regeneration + diff banner, identity strip.

**Explicitly deferred (named, not omitted):** referral rewards, invite flows, `invite.k_factor_dashboard`, public profiles, any leaguemate-facing automation, anything touching the ToS-adverse Sleeper write path (`trade.send_in_sleeper`) in onboarding, Apple capability-gating (rejected as an artificial wall; revisit with a real capability — multi-device sync UI — only if measured bind rate disappoints), SleeperConnect verification at the save moment (lives in Settings post-bind), **animated mascot/companion + dialogue system** (post-launch experiment at best, contingent on instrumented session-1 drop-off showing guidance is the leak; requires mkt-brand proposal + Chalkline ADR).

## Success criteria (revised)

- **North star: time-to-first-trade-card < 60s from a warm server** (design budget until item-2 timing data confirms it; cold-start incidence and added latency measured separately via ms + reason marker).
- **Activation**: first swipe in session 1. Denominator = `landing_username_submitted` with successful league init (username-error rate tracked as its own leak metric). 80% is **aspirational** (industry D0 activation broadly 25–60%, directional benchmark); the first instrumented cohort sets the real baseline.
- **Conversion**: Apple bind rate at the save moment (observational for cohort 1; declined measured separately from ignored).
- **Retention**: % of week-1 users running a trio session on a later day; **session-2 return rate for unbound users** (the silent-re-init leak metric); demo→username crossover.

## Handoffs

- Event names/ingestion → an-data-architect (tracking plan v2); denominators → an-funnel. Deck eval script → eng-backend/eng-qa. Keep-warm → eng-integrations; paid-tier memo → fin-budget. Redraft segment size check → pm-pfo. Share-sheet ToS exposure → pm-partnerships (share sheet is OS-native and user-initiated; no Sleeper write path). Assistant GM persona definition → mkt-brand; all onboarding copy in that voice → mkt-writer. Coach-mark/celebration visual specs (Chalkline-compliant motion) → ux-design. ADR → eng-architect.

## Review log (3 rounds, 2026-07-17)

- **R1**: independent pressure-tests. UX found 4 silent conversion killers: no re-entry for Apple-only users; the Quick Set "aha" doesn't actually happen (deck never regenerates, wrong exit tab); <60s collides with documented 30–60s Render cold starts; "Save your board" framing is false. Growth found: instrumentation sequenced last = shipping blind (moved to first + baseline); riskiest assumption = consensus deck quality (offline eval gate); plan silent on the leaguemate share surface (one share affordance in, all else deferred); session-2 re-entry is the real churn leak (silent re-init).
- **R2**: growth ruled on all 12 UX findings (10 accept, 2 accept-modified, 0 reject on substance) and 6 open questions; conceded the chooser-demotion cut-line conflict (load-bearing routing, not cosmetics). UX signed off conditionally with 2 minor dissents + 4 sequencing hazards.
- **R3**: growth accepted both UX counter-proposals (session-2 ask = non-modal banner, not modal; prompt trigger floored at ≥2 swipes) and all 4 hazards (state scaffold to item 4; flag flip to item 5; pregen hooks existing path; items 5–6 serialize). **Review closed, both roles bought in; zero open dissents.**
- **v2.1 (post-review, operator-directed)**: guided layer added (swipe hint, ≤4 coach marks, celebration beats, Assistant GM voice; mascot rejected → deferred list). Not panel-reviewed; coach marks explicitly bound to the same TTFV/ask-stacking discipline the panel ratified. If the panel reconvenes, the guided layer is in scope for critique.
