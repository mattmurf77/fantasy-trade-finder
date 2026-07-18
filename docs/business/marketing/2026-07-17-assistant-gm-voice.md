# Assistant GM Voice — Persona Definition for Onboarding Copy

**Role:** mkt-brand · **Date:** 2026-07-17 · **Status:** Approved persona spec (copy execution → mkt-writer)
**Context:** Onboarding redesign item 12 (`docs/plans/onboarding-conversion/plan.md` v2.1, "Guided layer"). Governs all copy on the surfaces built by items 4–10. Sits beside the Chalkline visual identity (`docs/design/brand.md`, "Peer, not tutor") and the voice charter (`living-memory/BRAND.md`). Honesty constraints are binding per ADR-006 (`docs/adr/adr-006-account-later-onboarding.md`).

## The persona

The voice is the user's **assistant GM**: a sharp front-office aide who works *for* the user — the user is the GM, the app is staff. Confident, concise, dry; it reports numbers, flags opportunities, and hands the decision back — never cartoonish, never pleading, never exclamation-heavy.

It is not a mascot, not a coach, and not a hype man. It briefs; the GM decides.

## Tone rules

| DO | DON'T |
|---|---|
| Report results with numbers: "Re-ranked with your WR board — 4 new trades." | Cheer with adjectives: "Awesome!! Your board just got better! 🎉" |
| Second person, present tense — the user owns everything: "your board," "your deck," "you've seen every trade." | First-person-plural chumminess: "We found some great trades for us!" |
| Name what failed and the next move: "That username isn't on Sleeper. Check your profile — usernames aren't team names." | Apologize theatrically or vaguely: "Oops! Something went wrong." |
| Offer, then step back — the GM makes the call: "Fix them in 2 minutes →" | Plead or manufacture urgency: "Don't miss out!" "Last chance!" |
| Front-load the payoff in the first few words: "4 new trades" before the how. | Bury the result under setup: "Because you updated your rankings, we were able to…" |
| Stay factually true, always. Apple sign-in = cross-device identity; boards persist regardless (ADR-006 honest-framing rider: **"save your board" is prohibited copy**). | Claim false loss or false scarcity for conversion — one discoverable lie poisons every later ask. |
| Dry understatement, at most one beat per surface: "Noted." | Exclamation points, emoji (never — Chalkline prohibition #1), or stacked jokes. |
| Milestones get quiet ceremony — a declarative sentence that treats the win as expected of a good GM. | Confetti language: "You did it!!" "Congrats, superstar!" |

Numbers are always literal and set in the UI as data (Plex Mono per Chalkline) — the copy string carries the `N`, never a vague "several."

## Vocabulary

**The voice uses:** board, front office, GM, scout / scouting, deck, value, consensus, re-rank, roster fit, window (contend / rebuild), filler, stud, target, pick, tier, leaguemate, head-to-head, "your call."

**The voice never uses:** bestie, fam, journey, unlock your potential, magic / magical, supercharge, level up, awesome, amazing, oops / whoops / uh-oh, "hey there," "we're so excited," hype adjectives without a number behind them (per `living-memory/BRAND.md`: no "powerful," "robust," "game-changer").

## Sample copy — ready to lift

Strings marked with `@username`, `N`, or `POS` are template slots. Arrows (→) are the Chalkline link affordance, not decoration.

| # | Surface | Copy | Limit |
|---|---|---|---|
| 1 | Landing field placeholder | `Sleeper username` | ≤25 ch |
| 2 | Landing subline (under headline "SEE TRADES FOR YOUR TEAM") | `No password. Your league's rosters do the talking.` | ≤60 ch |
| 3 | Username not-found error | `No "@username" on Sleeper. Usernames aren't team names — check your Sleeper profile and retype it.` | ≤110 ch |
| 4 | Sleeper-down / offline error | `Sleeper isn't responding. Browse the sample league while we retry →` | ≤80 ch |
| 5 | Skeleton deck status line | `Scouting your league. First trades in a few seconds.` | ≤60 ch |
| 6 | Identity strip | `Trading as @username — not you?` | ≤40 ch |
| 7 | Provenance chip coach mark | `These are consensus values. After Quick Set, they're yours.` | ≤65 ch |
| 8 | Quick Set prompt card | Title: `These trades use consensus values.` Body: `Your board would find better ones. Fix one position in 2 minutes →` | title ≤40, body ≤75 ch |
| 9 | Diff banner (post-Quick Set) | `Re-ranked with your POS board — N new trades.` | ≤55 ch |
| 10 | First-like celebration | `First target logged. Your front office is open for business.` | ≤65 ch |
| 11 | First-Quick-Set-save celebration | `That's your board now. The deck rebuilds around it.` | ≤60 ch |
| 12 | Apple save-moment prompt | Title: `Keep your board on every device.` Body: `Sign in with Apple links your board to you — new phone, same front office.` CTA: `Sign in with Apple` Decline: `Not now` | title ≤40, body ≤90 ch |
| 13 | Session-2 non-modal banner (unbound, ≥N swipes) | `N swipes on this board. Add Apple sign-in to carry it across devices →` | ≤80 ch |
| 14 | Deck-exhausted trio entry | `You've seen every trade. Sharpen your board with quick head-to-heads →` | ≤80 ch |
| 15 | Demo-mode persistent bar | `Sample league. See this for YOUR team →` | ≤45 ch |

Usage notes for builders:

- #3: never echo raw API errors; the explanatory clause (username ≠ team name) is load-bearing per plan §First-launch-flow 1.
- #12: this is the full honest framing. Do not add loss language ("don't lose your board"), do not gate features on it, and decline is always one tap (`Not now`), persisted (ADR-006 ask policy). Apple's button label follows Apple HIG verbatim.
- #10 and #11 fire *before* the Apple prompt (win → ask ordering, plan item 8). They are the only two celebration beats; keep them to one line, no punctuation heavier than a period.
- #9: `N` comes from the regeneration diff; if N = 0, suppress the banner rather than fudge it (never claim change that didn't happen).

## Where the voice does NOT apply

System chrome stays neutral: error stack traces and diagnostic strings, legal / privacy / ToS text, settings labels and toggles, permission dialogs (OS-owned), version and build metadata, and empty technical states like network debug output. If a string exists to be parsed or audited rather than read by a GM mid-session, it gets plain descriptive language, not persona.

## Decisions needed

1. Approve the persona + the 15 strings above as the lift-verbatim set — **operator** (recommended: approve; strings stay within the plan's already-reviewed framing and ADR-006 constraints).

## Handoffs

- Full onboarding copy pass in this voice across items 4–10 (every string, not just these 15) → **mkt-writer**, using this doc as the source of truth.
- String integration + character-limit verification in actual layouts → **eng-mobile** (items 4–10 builders).
- Celebration-beat motion that matches the "quiet ceremony" register → **ux-design** (Chalkline-compliant, no confetti).
- Future push-notification copy in this voice (post-launch) → **mkt-lifecycle**, same persona doc.
