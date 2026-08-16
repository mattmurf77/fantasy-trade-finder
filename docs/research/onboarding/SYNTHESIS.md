# Synthesis — Onboarding & Feature Presentment Research (Rounds 1 + 2)

> **Date:** 2026-08-15
> **Status:** research complete; no implementation decisions made. This doc ties together 16 research files (10 round-1, 2 consolidations, 6 round-2 drill-downs — index at bottom).

---

## The four-part answer that emerged

### 1. First session: value before identity — and the gate design is now precise

The strongest-evidenced onboarding intervention anywhere is delaying/softening the sign-up wall (Duolingo ~+20% DAU, on record). Round 2 sharpened this into something unusually specific for FTF:

- **KTC's vote gate is not what the industry believes** ([r2-1a](round-2/r2-1a-vote-first-precedents.md)). Code-level teardown: the full ranking table renders *ungated on first paint*; the vote modal fires ~2s later; a labeled "I don't know all of these players" link grants a 240-minute no-vote bypass; a real vote buys 24h. **Content first, gate second, bypass always available** — the "contribute to see" claim is narrative, not enforcement.
- **The account is the poison, not the vote.** Near-controlled natural experiment: the same keep/trade/cut mechanic shipped behind a login (Fantasy Roundup, Jan 2026) was torched by the same community that defends KTC's gate (+86 "required login is a huge turn off" vs +40 defending KTC's vote requirement). Category revealed preference: every major dynasty tool serves full value to a cold visitor; the lone account-at-the-door player (Dynasty Nerds) pays for it.
- **The first recommendation is a verdict, not a sample** ([r2-1b](round-2/r2-1b-first-session-mechanics.md)). Three peer-reviewed results: early algorithm errors cause *durable* trust damage, concentrated in domain experts — exactly FTF's audience. This argues for confidence-gating what the first session shows (Whoop/Oura's named calibration period is the live counter-pattern to "magic in seconds") and for sandboxing the *mechanic* while personalizing the *content* (Superhuman's synthetic inbox +17% activation; Carroll's training-wheels result behind it).
- **Unskippable is safe when the step does work FOR the user (defaulted setup, Superhuman 30%→98%); dangerous when it asks something OF the user (Vevo's skip added ~10% logins).** Pre-filled confirmation taps do psychological work even when the answer is known (Pinterest +11%) — but pre-population manufactures expert assent as easily as it harvests corrections; fine for legibility, not for data quality.
- **App Store:** guideline 4.8 almost certainly doesn't apply to a Sleeper-username lookup; 5.1.1(v) is the near-term risk if generic content sits behind the username field (guest mode is the mitigation); **5.2.2 is the underrated one** — Sleeper's API terms are "non-commercial purposes" only, and Apple has enforced 5.2.2 against apps using official SDKs. No documented fantasy-app rejection exists; that absence is a finding, not an all-clear. Operationally: store Sleeper `user_id`, not username; account deletion is already mandatory for minted `acct_` keys. Guest→account data migration is **unsolved at every auth vendor** — if FTF does guest mode, the merge path is bespoke work.

### 2. Teaching depth: pull surfaces, boundary timing, and retirement conditions

- **Complexity is the gate; context is a multiplier.** The 45,318-player CHI study: tutorials paid only in the complex product (+75% progression), and delivering *identical* content in-context added +40% more. FTF is in the complex band — guided doing pays; upfront carousels don't (NN/g: tutorials made apps feel harder, no performance gain; Apple's HIG agrees).
- **Scaffolding can hurt even when opt-in** — a help button measurably reduced progression and return rate in the same CHI paper. Retirement conditions ("retire after N successful unaided uses") are load-bearing, and **no vendor sells them** ([r2-2a](round-2/r2-2a-empty-states-and-tips.md)) — FTF would be building the concept.
- **Trigger predicate and delivery budget must be separate systems.** A pure relevance trigger over-fires ~3:1; LinkedIn's Air Traffic Controller (one arbiter scoring predicted-benefit minus predicted-channel-damage) is the industrial pattern. FTF's `useInterruptCoordinator` is the seed of exactly this.
- **Interruptive copy budget is ~16 words** (4-second modal dismissal × reading-rate data). One line + one button, or move it to a pull surface.
- **Empty states are the best pull surface, and no-results is the best-researched case.** The convergent contract across four design systems: name the state → next step → exactly one primary action → never a dead end. The teaching move that converts failure into *feature adoption* is eBay's saved-search-with-alert — the exact shape for "no mutual-gain trades found → save targets to your want board."
- **FTF already owns most of the needed engine** ([r2-2b](round-2/r2-2b-inhouse-guidance-engineering.md)): `useGuide.ts` + target registry + interrupt coordinator + a correctly-placed `guide_step_shown` exposure event. Gaps: remote content (**no OTA path exists — `expo-updates` is not installed**; every copy tweak is a TestFlight binary today), a declarative eligibility layer (Apple's TipKit is the best public spec — tips declare their own death conditions), and the exposure→adoption join. Buy doesn't fit (MAU pricing, no native-mobile support, dead OSS libs — with one exception: `react-native-spotlight-tour` is alive).

### 3. The calendar: two peaks, returning-state-as-default, archetype recaps

- **Dynasty has two seasonal peaks, and the second is a competitive gap** ([r2-3a](round-2/r2-3a-seasonal-reonboarding.md)). Measured (Wikimedia pageviews, replicating 3 years): July→August steps up 3.4–3.5×, September peaks 6.3–7.3× the trough — but the NFL Draft in April runs ~15× its own baseline while generic fantasy attention bottoms out. Redraft-shaped competitors treat April as dead time; dynasty's rookie-draft economy doesn't. True trough is Dec–Mar; build season is late May/June.
- **Delete the re-entry decision.** ESPN's answer to seasonal return is auto-reactivation, not a welcome-back screen. WoW's best returning mechanic is *suppression* (hide the stale backlog first). TurboTax's is *the diff as the feature* (last year vs this year, proactively computed). FTF holds a rich diff — roster changes, Elo movement, picks that became players. No product anywhere has published welcome-back flow results, so anything shipped needs its own holdout.
- **Recap stat selection is solved** ([r2-3b](round-2/r2-3b-recaps-digests-inbox.md)): percentile cards concentrate >half of shares in the top decile; archetype cards everyone qualifies for distribute sharing (Duolingo, on record). Gate the recap until the data is good enough to be proud of (Whoop's 14-day gate) — the gate becomes an activation prompt. Berger & Milkman: low-arousal negative stats are unshareable; keep "the one that got away" self-only. Spotify's AI-narration Wrapped is the negative case — don't dilute real facts with narration. Monzo's engineering pattern: precompute everything, backend-driven templates, batch-rendered share images.
- **The inbox's strongest quantitative case:** 25% message-center read rates among push-opted-**out** users (Airship, 83 apps, 2016). Segment inbox reporting by push-opt-in status from day one. Provisional push is a measured null for lift — its value is reach into the never-prompted population, and the first send carries a permanent Turn Off button.

### 4. Measurement posture: FTF cannot A/B its way through this

Flagged independently by five agents. Onboarding tests are the hardest kind (no pre-exposure history → CUPED inapplicable; 500+ users/variant for a 10% lift). Real-world nudge effects average ~+8% (126-RCT meta-analysis) — vendor stats are upper bounds, and ~94% of features going unused is the normal condition, not failure. The honest posture: one behavioral activation definition ("viewed a mutual-gain trade from their real roster," not "connected a league"), exposure logging fired at render (the `experiment_exposed` dark event + the already-firing `guide_step_shown`), staged rollouts and painted-door tests instead of classical A/Bs, a small long-running holdout to price the guidance layer once, and the feedback backlog re-read as a discovery diagnostic (classify items *missing* vs *exists-but-not-found* — Microsoft's Ribbon telemetry says the second category is large).

## Corrections ledger (round 2 overturned round 1 / circulating beliefs)

| Believed | Actual | Where |
|---|---|---|
| KTC hard-gates rankings behind votes | Soft gate: content first, 2s delay, free 4h bypass | r2-1a |
| Vote gates are friction risk | Community defends the vote; the *login* is what gets torched | r2-1a |
| Baymard forced-account abandonment 24–26% | 18% | r2-1a |
| FTF ships tips via EAS Update OTA | No OTA path — `expo-updates` not installed | r2-2b |
| OSS RN tour libs all dead | `react-native-spotlight-tour` actively maintained | r2-2b |
| FTF needs to build a guidance overlay | Overlay exists (`useGuide`); gaps are content/eligibility/measurement | r2-2b |
| Fantasy offseason = one long summer lapse | Two peaks (Aug–Sep, April); trough is Dec–Mar | r2-3a |
| Push priming worth 2–3× | +10–23% measured; provisional push a null for lift | a5, r2-3b |
| Recaps: show your best stats | Percentile stats concentrate sharing in top decile; archetypes distribute it | r2-3b |
| "Magic first screen" is evidence-backed | Unfalsified — zero published post-connection funnels | r2-1b |

## Open gaps (round-3 candidates, logged per-file)

Sleeper's own returning-manager experience (needs in-app observation, no teardown exists); no controlled inbox-as-discovery experiment anywhere; no confirm/correct-rate benchmarks for inferred attributes; no sandbox-vs-real-data A/B for a recommendation product; guest→account three-way merge design precedents; Airship sports-vertical PDF (downloaded but unreadable without `poppler`); `react-native-spotlight-tour` Expo/New-Architecture support (needs a spike, not research).

## File index

| File | Subject |
|---|---|
| [PLAN.md](PLAN.md) | Study design |
| [round-1/a1](round-1/a1-onboarding-pattern-taxonomy.md)–[a5](round-1/a5-mobile-onboarding-constraints.md) | Onboarding: patterns, activation, case studies, personalization, mobile/iOS |
| [round-1/b1](round-1/b1-progressive-disclosure-theory.md)–[b5](round-1/b5-measurement-and-tooling.md) | Presentment: theory, in-app patterns, lifecycle loops, mastery curves, measurement/tooling |
| [CONSOLIDATED-A-onboarding.md](CONSOLIDATED-A-onboarding.md) | Area A synthesis (7 themes) |
| [CONSOLIDATED-B-feature-presentment.md](CONSOLIDATED-B-feature-presentment.md) | Area B synthesis (8 themes) |
| [round-2/r2-1a](round-2/r2-1a-vote-first-precedents.md), [r2-1b](round-2/r2-1b-first-session-mechanics.md) | Drill: account-optional first session |
| [round-2/r2-2a](round-2/r2-2a-empty-states-and-tips.md), [r2-2b](round-2/r2-2b-inhouse-guidance-engineering.md) | Drill: just-in-time teaching layer |
| [round-2/r2-3a](round-2/r2-3a-seasonal-reonboarding.md), [r2-3b](round-2/r2-3b-recaps-digests-inbox.md) | Drill: seasonality, recaps, inbox |
