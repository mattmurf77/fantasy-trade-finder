# PRD F10 — Deck Replenishment Ritual (honest scarcity)

**Priority:** 9 · **Effort:** ~2d · **Flag:** `deck.replenishment` · **Depends:** none (uses existing
notification stack)
**Source:** gap-analysis #13; presentment-research principle 9 — "a finite deck should END" is the
deliberate divergence from TikTok; honest scarcity + scheduled replenishment is the utility-app
habit loop.

## Problem

The deck-exhausted state exists (rank-more CTA) but cadence is entirely pull-based: users must
remember to come back and manually regenerate. There's no completion *moment* (the session just
peters out), no scheduled fresh inventory, and no re-engagement hook tied to real events (waivers,
news, value shifts). The 7-day card expiry exists in data but is unused as a product hook. TikTok
retains via infinite feed; the utility-app analog is a **ritual**: deck ends → model updated →
fresh deck arrives on a schedule worth returning for.

## Solution

1. **Completion moment (client):** finishing a deck renders a summary card in Chalkline style:
   "Deck done — 9 passed, 2 liked, 1 proposed. Your model updated from 12 verdicts. Fresh trades
   after waivers." Buttons: "See liked" (existing portfolio/likes surface), "Done". Terminate on
   success, not exhaustion — no auto-regenerate, no infinite feed (guardrail 3).
2. **Scheduled replenishment (backend):** a weekly cron (existing cron stack + `CRON_SECRET`
   conventions) pre-generates a fresh deck per active user-league after the league's waiver day
   (default Wed 6am local-ish; config), honoring all live layers (F3 fatigue, F5 taste when on).
   Pre-generation reuses the existing job/cache path — the deck is *ready*, not pushed onto screen.
3. **Fresh-deck notification:** one push per replenishment via the existing typed dispatcher,
   deep-linking to the deck: "Your new deck is ready — 11 trades, 3 you haven't seen before."
   Strictly capped at 1/week/league, honors the existing notification-preference surface (the
   re-engagement default-off stance applies — this is opt-in-able, not forced; exact default left
   to the operator's existing notification policy).
4. **Expiry honesty:** cards older than the 7-day expiry drop from replenished decks with a count
   in the notification copy ("4 expired — values moved"). Scarcity framed as freshness, never
   fake-urgency (no countdown timers, no "act now").
5. Replenishment events log to F1 (deck_job source = `replenish`) so pull-vs-replenish engagement
   is comparable.

## Acceptance criteria
- [ ] Completing a deck shows the summary card with real tallies; dismissing returns to the hub.
- [ ] Cron generates decks only for users active in the trailing 30d (no zombie churn), idempotent
      per week.
- [ ] Push respects notification preferences + 1/week cap; deep link lands on the fresh deck.
- [ ] No auto-advance into a new deck after completion — ever.
- [ ] Flag OFF: today's exhausted-state behavior, no cron output, no pushes.

## Metrics
Weekly deck-completion rate, replenishment-push open rate, proposals per weekly-active (north star)
for replenished vs pull-only cohorts. Session length is a **cost** metric here (guardrail 1).

## Risks
Notification fatigue — 1/week hard cap, preference-gated, and copy always names concrete inventory
("11 trades"), never bare "come back".
