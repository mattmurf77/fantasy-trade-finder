# Consolidated Findings — Area B: Feature Presentment & Progressive Discovery

> **Date:** 2026-08-15
> **Synthesizes:** [b1-progressive-disclosure-theory.md](round-1/b1-progressive-disclosure-theory.md) · [b2-contextual-inapp-patterns.md](round-1/b2-contextual-inapp-patterns.md) · [b3-discovery-loops-lifecycle.md](round-1/b3-discovery-loops-lifecycle.md) · [b4-depth-mastery-case-studies.md](round-1/b4-depth-mastery-case-studies.md) · [b5-measurement-and-tooling.md](round-1/b5-measurement-and-tooling.md)
> Full citations live in the round-1 files; this doc names the finding and which file carries the sources.

---

## The eight themes that survived five independent research passes

### 1. Calibrate every expectation down: real-world nudge effects average ~+8%, and ~94% of features go unused

The 126-RCT DellaVigna & Linos meta-analysis (B3): practitioner-run nudges move behavior **+1.4pp / +8%** vs +33% in published papers — the gap is pure publication bias. Pendo's aggregate telemetry (B5): ~6.4% of features drive 80% of clicks. For a feature-dense app, most features going undiscovered is the *normal condition*; the game is picking which 3–4 features deserve discovery investment, not lifting all of them.

### 2. Timing beats volume, and FTF has free timing infrastructure

The strongest HCI evidence in the corpus (B2): mistimed interruptions **double error rates** and add 31–106% annoyance vs the same message at a task boundary; deferring ~90s to a boundary is nearly free; relevance-gating beats recency-gating (off-topic notifications scored 4.98 vs 3.59 frustration). FTF has *explicit code-level boundaries* — trade sent, vote submitted, board saved — so boundary-timed teaching is implementable with no modeling.

### 3. Pull surfaces beat push surfaces, and empty states are the best pull surface FTF isn't using

Launcher-initiated tours complete at 67% vs 31% pushed; embedded cards get ~1.5× the action rate of pop-ups; modals are dismissed in <4s by 38% of users (B2). Empty states carry zero interruption cost, perfect timing, and no dismissal blindness (B1's "pull revelations," seconded by A1). FTF has four natural ones: empty boards, empty trade-finder results, empty matchup history, empty inbox.

### 4. Scaffolding needs a retirement condition; interfaces should never silently rearrange

Expertise-reversal research (B1): guidance that helps novices measurably degrades experts — every coach mark needs a *behavioral* retirement trigger (N successful uses), not a session counter. Findlater & McGrenere: adaptive (self-rearranging) menus were the *slowest* condition; adaptable defaults won preference. Progressive disclosure itself has a two-level ceiling. And Carroll's training-wheels result — the strongest in the literature — *blocked with explanation* rather than hid, preserving the user's model of the full system: staged surfacing, not secret features.

### 5. Users never self-graduate — the product must synthesize the social channel

Satisficing is permanent: shortcuts are ~2× faster and still unused after a decade; adoption tracks *social exposure*, not efficiency (B1, B4). A solo-use consumer app has no over-the-shoulder colleague, so depth adoption dies without a synthetic channel. The two best-evidenced synthetic channels (B4) are buildable from data FTF already has: **collaborative-filtering feature recommendations** (CommunityCommands: 2.1× better suggestions, field-verified increase in unique commands used) and **reflective usage widgets** (Skillometers: hotkey use 42%→80% by tenth repetition). Warning attached: the Skillometer study showed *no short-run efficiency gain* — a mastery nudge measured on short-run metrics gets falsely killed.

### 6. Feature requests are often discovery failures — testable against FTF's feedback backlog today

Microsoft's Ribbon telemetry (~3B sessions): "people weren't finding the very features they asked us to add" (B4). The Ribbon also documents the cost of restructuring for discoverability: ~20% self-reported productivity loss concentrated in experts — FTF's most active testers would complain loudest. Cheap diagnostic available now: classify the existing in-app feedback backlog into *missing* vs *exists-but-not-found*.

### 7. The notification inbox is a plausible-but-unproven discovery surface; recaps are the proven one

Zero controlled studies anywhere on inboxes/activity feeds as feature-discovery surfaces — treat FTF's shipped inbox as an experiment platform, not a settled pattern (B3). The circulating "+40% retention" stat is unsourced. By contrast, **annual recap artifacts are the best-measured depth-discovery mechanism in the corpus**: Spotify Wrapped +13–14% DAU day-over-day with *falling* ad spend. This directly upgrades the priority of the existing Dynasty Year in Review plan (`docs/business/product/2026-08-13-dynasty-year-in-review-plan.md`). Weekly digests: copy Grammarly's structure (fixed slot, protected from campaign collision, one dynamic next-step payload) — no public lift numbers exist.

### 8. Buy doesn't fit; the build path runs through infrastructure FTF already chose

(B5) Pendo/Appcues MAU pricing scales badly for a free consumer app; Chameleon doesn't support native mobile despite its marketing; the popular OSS React Native tour libraries are unmaintained since 2024. PostHog/Statsig-class tooling (flags + experiments + generous free tiers + real RN/Expo support) fits, and FTF's half-built exposure logging (`experiment_exposed` registered but dark) is the highest-leverage measurement gap — plausibly a 10× sensitivity loss on any onboarding/discovery test while unfixed.

## Tensions worth carrying forward

- **Badges are a commons problem:** "NEW" dots on features will inherit red-dot blindness *and* degrade the transactionally-valuable inbox badge unless namespaced and auto-expired (B2).
- **Gamification of discovery is the weakest evidenced mechanism** (B3): behavioral effects smallest and least stable in meta-analysis; badges *steer* effort rather than create it; Duolingo's own mechanics failed transplant outside learning. Completion-style mechanics > status/competition mechanics, if any.
- **Games' competence-gated locking doesn't transfer** (B4): content is the reward in games. Frame FTF's approach as *staged surfacing* — not shown yet, always reachable.
- **Interruption research is 2004–2008 desktop-era** — mechanisms generalize, effect sizes were never measured on short-session consumer mobile (B2, explicitly logged gap).

## Recommended round-2 drill-downs (Area B's share)

1. **A just-in-time teaching system for FTF** — empty-state pattern library from real products, trigger taxonomy + retirement conditions, and how small teams built in-house tips/announcement engines instead of buying (the un-researched half of B5's build-vs-buy).
2. **Seasonal lifecycle, recaps, and the inbox as discovery surface** *(shared with Area A)* — fantasy's violent seasonality, returning-user re-entry flows, recap artifact design, digest structure, provisional push. Multiple round-1 agents logged unfinished threads here (Airship sports benchmarks gated, no fantasy seasonality curves, four unrun queries in B3).
