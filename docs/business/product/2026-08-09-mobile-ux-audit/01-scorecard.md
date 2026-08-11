# Scorecard — FTF Mobile UX & Product Audit

> Independent audit, 2026-08-09. Source of truth: `origin/main @ 72a0770` (v1.11.0), read as a pinned snapshot.
> Grades reflect **what a real user encounters under shipped flag defaults** (98 of 154 flags on), not what exists in the codebase.

---

## Grading scale

| Grade | Means |
|---|---|
| **A** | Best in category. No competitor does this better; no material gap. |
| **B** | Solid and competitive. Real but minor gaps. |
| **C** | Functional with genuine friction, or a notable gap against the field. |
| **D** | Significant deficiency that will cost adoption or retention. |
| **F** | Broken, absent, or actively working against the user. |

**Criteria as applied**

- **Usability (Us)** — can a user accomplish the screen's job; clarity, states, error handling, recoverability.
- **Simplicity (Si)** — how fast a *brand-new* user becomes competent here. Cognitive load and time-to-first-success.
- **Retention (Re)** — does this surface earn a return visit.
- **Replicability (Rp)** — how hard this is for a newcomer to copy. **Higher = more defensible.**
- **Competition (Cm)** — how it stacks against KTC, FantasyCalc, Dynasty Daddy, DynastyGM, DynastyDealer, RosterAudit, DTF, FPTrack.
- **Growth (Gr)** — does this surface produce net-new users.

---

## Tier A — full treatment

| # | Unit | Us | Si | Re | Rp | Cm | Gr | Page |
|---|---|---|---|---|---|---|---|---|
| 1 | Sign-in | B | A− | C | C | B+ | D | **B−** |
| 2 | League Picker | B+ | B+ | C | C | B | D+ | **B−** |
| 3 | **Guided Onboarding** | D | D+ | D | C− | C | F | **D** |
| 4 | Global Shell | B+ | B | C+ | C | B | D | **B−** |
| 5 | Quick Set Tiers | C+ | C | C− | B− | A− | F | **C** |
| 6 | Trios | B+ | B+ | B | B+ | A | D | **B** |
| 7 | Acquire Deck | C+ | C | B− | A− | A | D+ | **B−** |
| 8 | **Trade Card** | B | B− | B | A− | A− | D | **B** |
| 9 | Trade Calculator | B | B+ | C+ | C+ | B− | C | **B−** |
| 10 | Matches | B− | C+ | C+ | A | A | D+ | **C+** |
| 11 | League Home | B− | C+ | C | C+ | C+ | D+ | **C+** |
| 12 | League Rankings | A− | B | B− | B− | B+ | D | **B** |
| 13 | Draft Room | B | C+ | C− | B | C+ | F | **C+** |
| 14 | Settings | B+ | B | n/a | C | B | D | **B−** |

## Tier B — condensed

| # | Unit | Us | Si | Re | Rp | Cm | Gr | Page |
|---|---|---|---|---|---|---|---|---|
| 15 | Rank Home / Rank Menu | B | B+ | C | C | B | F | **C+** |
| 16 | Quick Rank | B | B | C | B− | B+ | F | **C+** |
| 17 | Tiers Board | B+ | C+ | C+ | B− | A− | F | **C+** |
| 18 | Manual Ranks | A− | B | C | C | B | F | **C+** |
| 19 | Pick Anchors | C+ | B− | C− | B+ | A− | F | **C+** |
| 20 | Trends | B | B+ | B | C | B− | F | **C+** |
| 21 | Free Agents | B+ | B | B− | C+ | C+ | F | **C+** |
| 22 | Portfolio | C | C+ | C | C | C− | F | **C−** |
| 23 | Mock Draft | F | F | F | C | D | F | **F** |
| 24 | Rookie Ranks | B | B | C | B− | B | F | **C+** |
| 25 | Record Picks | B+ | C+ | C− | B | B+ | F | **C+** |
| 26 | Pick Assignment | B | C | D | B | B+ | F | **C** |
| 27 | ESPN Connect | A− | B+ | n/a | B | A− | F | **B−** |
| 28 | Sleeper Connect | B+ | B | n/a | B+ | A− | F | **B−** |
| 29 | Feedback Inbox | C+ | B | C | C | B | F | **C** |
| 30 | Profile *(dark)* | F | F | F | C− | D | F | **F** |
| 31 | Test Stages *(dark)* | n/a | n/a | n/a | n/a | n/a | n/a | **n/a** |
| 32 | Trade Finder Hub *(dead)* | F | F | F | F | F | F | **F** |
| 33 | Placeholder *(dead)* | F | F | F | F | F | F | **F** |

*Units 31–33 are unreachable. 31 is operator tooling and correctly gated — excluded from the composite. 30, 32, 33 are graded F as shipped product surface: they occupy 1,656 lines and contribute nothing to a user.*

---

## App-wide grades

| Criterion | Grade | The one-sentence reason |
|---|---|---|
| **Usability** | **B−** | Individual screens are well-built and unusually honest about their own limits; the damage is at the seams — a failed trade search is indistinguishable from a fresh one, and the default path silently never completes its own progression. |
| **Simplicity** | **C+** | A new user's first act is a 32-tap tier-sorting chore they never asked for, before seeing a single trade. |
| **Retention** | **C** | Push permission never fires on the default path, there is no email capture at all, and the only calendar-aware mechanism in the entire codebase is one hardcoded date. |
| **Replicability** | **C+** | Exactly one mechanism is genuinely hard to copy, and it has essentially never run in production. |
| **Competition** | **B** | Genuinely ahead where it matters most (mutual-gain discovery, write-back, native app) and behind on table stakes the whole field treats as baseline. |
| **Growth** | **D** | Every loop is built and broken at the last inch: invite links don't route, two complete share landings have zero callers, and the most shareable artifact carries no URL. |

### Composite: **C+ / B−**

An unusually well-engineered product with a **distribution problem and a first-session problem**, not a quality problem. The engineering discipline is visible everywhere — typed empty states, honest refusals, deliberate read-only postures, gates that prevent bad trades. That care has not been extended to the two things that decide whether a launch works: what happens in a new user's first ninety seconds, and whether anyone can bring a friend.

---

## Distribution of grades

- **A-range:** 3 of 186 criterion-grades (League Rankings usability, Sign-in simplicity, Manual Ranks usability)
- **D or F:** 41 — of which **28 are Growth**, the single worst column by a wide margin
- **Growth is D or F on 28 of 31 graded units.** No other criterion is below C on more than 6.

That concentration is the audit's central finding. The product is good. Almost nothing in it is built to bring a second user.

---

## What this scorecard does not measure

Accessibility and Dynamic Type were scoped out (covered by the July internal teardown) except where they cap adoption. Backend architecture, the web app, and the browser extension are out of scope. Where a screen's live behavior depends on per-device experiment overlays rather than `config/features.json`, the grade reflects the static default and says so in the brief.
