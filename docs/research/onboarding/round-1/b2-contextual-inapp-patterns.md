# B2 — Contextual In-App Feature-Presentment Patterns

**Date:** 2026-08-15
**Lens:** How complex apps surface feature depth *inside the product* — tooltips, hotspots, coach marks, badges, what's-new modals, announcement centers, teaching empty states, behavior-triggered hints, banners/slideouts, and discovery-via-search. Adjacent lenses (onboarding sequencing, permissions/lifecycle messaging, information architecture) are deliberately out of scope.

---

## TL;DR

- **Interruption cost is real and measurable, and it is a function of *timing*, not just volume.** In a controlled experiment (N=50), the *same* peripheral task shown *during* a primary task rather than *between* tasks cost 3–27% more completion time, **2× the errors**, 31–106% more annoyance, and 2× the increase in anxiety ([Bailey & Konstan 2006](https://interruptions.net/literature/Bailey-CHB06_1.pdf)). Nothing about the message changed — only when it fired.
- **Deferring a message ~90 seconds to a task boundary measurably reduces frustration and reaction time** with no meaningful timeliness penalty ([Iqbal & Bailey, CHI 2008](https://dl.acm.org/doi/10.1145/1357054.1357070)). Relevance to the current task mattered *more* than timing: off-topic notifications scored 4.98 on frustration vs 3.59 for task-relevant ones (p<0.001).
- **Upfront tutorials/coach marks made an app feel *harder*, with no performance benefit.** NN/G's between-subjects test (N=70, 4 iPhone apps) found task success 91% (tutorial) vs 94% (skipped, p=0.443) and completion time 93.5s vs 85.2s (n.s.) — but perceived ease was *significantly worse* for the tutorial group: 4.92 vs 5.49 on SEQ (p=0.047) ([NN/G](https://www.nngroup.com/articles/mobile-tutorials/)).
- **Length and trigger dominate every other tour variable.** Across 550M+ interactions, Chameleon reports 3-step tours at 72% and 4-step at 74% completion vs **16% at 7+ steps**; click-triggered tours 67% vs delay-triggered 31%; progress indicators +12% ([Chameleon 2025](https://www.chameleon.io/benchmark-report)).
- **Modals are dismissed roughly as often as they're clicked, and the decision is instant.** 37.5% average dismiss rate, 40% CTA click rate, and **38% of dismissals happen in under 4 seconds** — i.e. before the copy can plausibly have been read ([Chameleon 2025](https://www.chameleon.io/benchmark-report)).
- **In-flow, user-pulled surfaces beat pushed overlays.** Embedded cards are ~1.5× more likely to be acted on than pop-ups; tours launched from a persistent launcher/checklist complete at 67% vs 31% standalone; surveys 54% vs 15% ([Chameleon 2025](https://www.chameleon.io/benchmark-report)).
- **Blindness is a learned response and it generalizes beyond ads.** NN/G eye-tracking found a right rail drawing **0.8% of attention despite occupying 25% of the content area** — a 33× disparity — and legitimate content acquires the same invisibility when it adopts ad-like placement or styling ([NN/G](https://www.nngroup.com/articles/banner-blindness-old-and-new-findings/)). Red-dot badging has the same failure mode ([Braze](https://www.braze.com/resources/articles/beware-red-dot-badging)).
- **Accessibility is non-optional and mostly unimplemented.** Custom tooltips must be dismissible, hoverable, and persistent (WCAG 2.1 SC 1.4.13, Level AA — [W3C](https://www.w3.org/WAI/WCAG21/Understanding/content-on-hover-or-focus.html)); announcement modals need focus trapping, Escape, `aria-modal`, and focus return ([W3C ARIA APG](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/)); pulsing hotspots must respect `prefers-reduced-motion` ([SC 2.3.3](https://www.w3.org/WAI/WCAG21/Understanding/animation-from-interactions.html)).
- **Vendor benchmark numbers are directionally useful and numerically untrustworthy.** Pendo excludes dismiss/close/snooze from "engagement" ([Pendo docs](https://support.pendo.io/hc/en-us/articles/50384284250523-Guide-effectiveness)) — so a Pendo engagement rate and a Chameleon click rate are not the same measurement, and neither is a controlled experiment.

---

## 1. The interruption budget: the cross-cutting constraint

Every pattern below spends from the same account. The HCI literature is unusually clean here because it isolates *timing* while holding message content constant.

**Bailey & Konstan (2006, Computers in Human Behavior 22(4):685–708, N=50)** manipulated only *when* a peripheral task appeared — between primary tasks vs during them. Interrupting mid-task produced 3–27% longer completion times, roughly double the errors, 31–106% more annoyance, and twice the anxiety increase ([PDF](https://interruptions.net/literature/Bailey-CHB06_1.pdf)). The practical reading: a badly-timed tooltip is not "a tooltip with a lower click rate," it is a *degradation of the user's actual task*.

**Adamczyk & Bailey (CHI 2004)** established the mechanism: subtask boundaries are cheaper interruption points because mental workload dips there, leaving resources for the interrupting task and for resuming afterward.

**Iqbal & Bailey (CHI 2008, "Effects of Intelligent Notification Management on Users and Their Tasks")** built OASIS, a system that defers notifications to detected breakpoints, and tested it on authentic programming and diagram-editing work. Findings ([PDF](https://interruptions.net/literature/Iqbal-CHI08.pdf)):
- Scheduling at breakpoints reduced frustration and reaction time vs immediate delivery.
- **Average deferral cost was under 90 seconds** — the authors call this an acceptable balance.
- Coarser breakpoints were better: in diagram editing, Medium-breakpoint delivery scored 2.6 on frustration vs 4.5 for immediate (p<0.037) and 5.5 for Fine (p<0.001).
- **Content relevance had a larger main effect than policy.** General-interest notifications: µ=4.98 frustration; task-relevant: µ=3.59 (p<0.001). Users tolerated disruption when the content turned out to matter.
- Caveat the paper states plainly: breakpoint detection on *novel* task sequences was only 55.5% accurate on average, and models could not reliably distinguish breakpoint type.

**Iqbal & Horvitz (CHI 2007)** field-studied real desktop alerts ([PDF](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/11/CHI_2007_Iqbal_Horvitz-1.pdf)): 40.8% of email alerts and 71% of IM alerts triggered a switch within seconds (mean ~2s), users then spent ~10 minutes on the diversion and another 10–15 minutes in the resumption phase, and **27% of task suspensions had not been resumed two hours later**. The relevant lesson for in-app presentment: the visible cost of an interruption ("they dismissed it in 2s") is a fraction of the real cost.

**Design consequence.** Treat presentment as a scheduler problem, not a content problem. Every candidate message should carry (a) a relevance predicate, (b) a permitted trigger boundary, and (c) a place in a global frequency cap.

---

## 2. Coach marks, spotlight overlays, and multi-step tours

**The strongest single piece of evidence against upfront overlays is NN/G's quantitative test.** Between-subjects, remote unmoderated, N=70 (35 per condition), four iPhone apps, all participants new to the apps ([NN/G, *Mobile Tutorials: Wasted Effort or Efficiency Boost?*](https://www.nngroup.com/articles/mobile-tutorials/)):

| Measure | Saw tutorial | Skipped tutorial | Result |
|---|---|---|---|
| Task success | 91% | 94% | n.s. (p=0.443) |
| Task time | 93.49s | 85.17s | n.s. (p>0.1) |
| Perceived ease (SEQ) | 4.92 | 5.49 | **significant (p=0.047)** |

The only significant effect was *negative*: the tutorial made the app feel harder. NN/G's companion piece on [instructional overlays and coach marks](https://www.nngroup.com/articles/mobile-instructional-overlay/) is qualitative but adds three failure modes observed in usability testing: (1) overlays require memorization because they vanish before use, and short-term memory fades in ~20 seconds; (2) frequent hint screens train faster dismissal regardless of usefulness; (3) coach marks styled like real UI get tapped as if they were interactive (observed in the Wimbledon and Ness apps).

**Vendor telemetry agrees on shape even where it disagrees on level.** Chameleon's 2025 report (550M+ interactions across tours, checklists, embeddables, launchers, modals, microsurveys) reports ([report](https://www.chameleon.io/benchmark-report), [analysis](https://www.chameleon.io/blog/mastering-product-tours)):

- 3-step 72%, 4-step 74%, **7+ step 16%** completion. Top-1% tours cap at 5 steps.
- Click-triggered 67% vs set-delay-triggered 31%; "self-triggered tours double engagement compared to automated, blanket-triggered ones."
- Progress indicators: +12% completion.
- Average time in a tour rose 132s → 154s year over year.
- Chameleon also asserts ~70% of users skip traditional linear tours ([source](https://www.chameleon.io/blog/effective-product-tour-metrics)).

Their [2023 report](https://www.chameleon.io/benchmark-report-2023) (212M interactions, calendar 2022) put **average tour completion at 30%** overall, with launcher-started tours at 61.65% and on-page-positioned triggers at 69.56%. The gap between "30% average" (2023) and "72–74% for short tours" (2025) is a *denominator* difference, not a genuine 2.4× improvement — a caution repeated in §11.

**Verdict.** Coach-mark overlays are net-negative as a comprehension device and modestly positive as a *pointer*, but only when short (≤4–5 steps), user-initiated, and anchored to a task the user has already started.

---

## 3. Modals and what's-new announcements

Modals are the highest-cost surface and the most-used one for release news — Chameleon reports release announcements account for ~40% of modal usage, with every other use case under 20% ([2025 report](https://www.chameleon.io/benchmark-report)).

Measured behavior from the same dataset:

- **37.5% average dismiss rate; 40% average CTA click rate.**
- **38% of users close a modal in under 4 seconds**; 37% dismiss after 10+ seconds. Meanwhile 35% complete the action within 4 seconds and 40% after 10+ seconds. The distribution is bimodal: a fast reflex group and a deliberate group, with little in between.
- Trigger matters: custom/hover-based 51% completion, click-based 47%, **immediate on page load 39%**.
- Media *hurts*: text-only 44% completion, text+image 29%, **text+video 21%**. This directly contradicts Chameleon's own 2023 finding that video tours completed at 47.67% — another reason to treat vendor time-series as unstable.

Practitioner guidance (opinion, not measurement) from [Appcues](https://www.appcues.com/blog/in-app-notifications) and [Userpilot](https://userpilot.com/blog/in-app-messaging/) converges on: modals only for changes that alter the user's mental model of the product; slideouts and banners for routine news; a rule of thumb that >40% dismissal-without-interaction indicates bad timing or targeting. Userpilot names "instant dismiss" (closing in under 2s) as a growing behavior — asserted, not sourced.

**The 4-second rule is the actionable finding.** If a large fraction of the audience decides before reading, then the *first line and the visual shape* carry the whole message, and any modal whose value requires reading a paragraph is mis-formatted by construction.

---

## 4. Tooltips and inline hints

Two distinct things share the name:

1. **Anchored guide tooltips** (a step in a walkthrough) — governed by the tour evidence in §2.
2. **Persistent, on-demand tooltips** (an `ⓘ` next to a jargon term) — closer to reference documentation, and the least-costly teaching surface available because the user pulls them.

Chameleon's 2023 dataset recorded 12 million tooltip impressions, **98% triggered on hover** ([2023 report](https://www.chameleon.io/benchmark-report-2023)). That number is a desktop artifact and is precisely the trap for a mobile app: **hover does not exist on touch.** A tooltip pattern ported from web to React Native must become tap-to-open, which changes it from a passive affordance to an interactive element with a discoverability problem of its own.

Accessibility requirements are hard constraints, not polish (see §12): custom tooltips must satisfy WCAG SC 1.4.13's dismissible / hoverable / persistent triad.

Inline hints — helper text rendered *in* the layout rather than over it — inherit the embeddable advantage: Chameleon reports users are "up to 1.5× more likely to take action on an embedded experience than a pop-up," with an optimal copy length of **≤26 words**.

---

## 5. Hotspots and beacons

A pulsing dot adjacent to a feature, expanding to a tooltip on tap. It is the lowest-interruption pointer in the library — and, notably, **the pattern with the least published measurement.** I found no controlled study or vendor benchmark isolating hotspot click-through; Chameleon's benchmark reports tours, modals, launchers, embeddables, and microsurveys, but not hotspots as a category.

What exists is convergent practitioner guidance ([Jimo](https://jimo.ai/glossary/hotspot), [Chameleon templates](https://www.chameleon.io/templates/hotspot-tooltip), [Appcues](https://www.appcues.com/blog/in-app-notifications)):
- Best fit: announcing a new capability to *existing* active users, and passive discovery of secondary features.
- One or two active hotspots at a time; multiple simultaneous pulses read as noise and signal that nothing is important.
- The revealed message should be short and action-framed.

**Treat all of the above as opinion.** The one adjacent piece of hard evidence is the banner-blindness literature (§7): a small, animated, visually-distinct element in a fixed position is exactly the profile that trains blindness.

Accessibility: a continuously pulsing indicator is decorative motion. WCAG SC 2.3.3 (Level AAA) requires non-essential interaction-triggered motion be disableable, and the standard practical answer is honoring `prefers-reduced-motion` ([W3C](https://www.w3.org/WAI/WCAG21/Understanding/animation-from-interactions.html)).

---

## 6. Badges and "NEW" dots

Badges are the cheapest attention purchase and the fastest to devalue.

Braze's own guidance names the failure mode: **"red dot blindness,"** explicitly analogized to banner blindness, plus frustration-driven disengagement and uninstalls, and it warns against badge use as a dark pattern ([Braze](https://www.braze.com/resources/articles/beware-red-dot-badging)). Braze provides **no data** for this. Practitioner articles circulate claims like "16–25% more open rates with badges" and "20–30% session-time lift" for social apps; I could not trace these to a primary source and they should be treated as unverified.

The mechanism claims (red is detected fastest; a numeric badge creates "cognitive debt" that users clear to make the number vanish) are plausible and widely repeated but rest on general color/attention psychology rather than product experiments.

**Design consequence.** A "NEW" badge has a strictly finite budget: it works because it is rare. The rules that follow directly are (a) one badge namespace per surface, (b) mandatory expiry (time-based or on-first-view), and (c) never badge something the user cannot act on immediately — a badge that leads to a dead end is the fastest way to teach the user to ignore all future badges.

---

## 7. Banners, slideouts, and the blindness risk

NN/G's eye-tracking corpus (1997–2024) is the strongest evidence in this whole document, because it is behavioral rather than self-reported ([*Banner Blindness Revisited*](https://www.nngroup.com/articles/banner-blindness-old-and-new-findings/)):

- In one case study, the right rail received **0.8% of user attention while occupying 25% of the content area** — a 33× mismatch between space and attention.
- Three triggers for blindness: **ad-typical location**, **ad-typical visual treatment** (animation, colored background, small rectangle), and **proximity** — content adjacent to ads gets "poisoned" by association.
- Critically, this is not limited to ads. Legitimate content — the article cites public-health announcements, voting information, emergency alerts — gets skipped when it wears banner clothing.

The original finding traces to Benway & Lane (Rice University, 1998), where users missed links containing exactly the information they were searching for because those links sat in banner positions ([NN/G history](https://www.nngroup.com/articles/banner-blindness-original-eyetracking/)).

**Design consequence.** A top-of-screen announcement bar styled as a distinct colored strip is optimized for *being ignored*. The escape hatch that the evidence supports is to make the announcement look like the app's content, sit in the content flow, and appear where the relevant task is — which is the embeddable-card pattern, and the reason it outperforms pop-ups by ~1.5×.

---

## 8. Empty states that teach

NN/G's [three guidelines for empty states in complex applications](https://www.nngroup.com/articles/empty-state-interface-design/):

1. **Communicate system status** — a truly blank panel leaves the user unable to distinguish "loading" from "error" from "no data."
2. **Provide learning cues** — the DataDog example ("Star your favorites to list them here") teaches a feature *at the moment its absence is felt*. NN/G calls these "pull revelations" and argues they are more memorable and applicable than forced tutorials.
3. **Provide a direct pathway** — a button that performs the action that would populate the state; the Loggly example offers both "add a source" and "explore with demo data."

This is the pattern with the best *cost profile* in the entire library: zero interruption cost (the user navigated here), perfect timing (the feature's value is maximally salient because the screen is useless without it), and no dismissal mechanic to blind.

Vendor claims of "+60% activation" or "25–30% → 40%+" from empty-state work circulate widely ([example](https://pixxen.com/blog/saas-empty-state-design/)) but carry no methodology, sample, or control and should not be planned against.

---

## 9. Checklists, launchers, and announcement centers

The single most consistent finding across Chameleon's datasets is that **a persistent, user-initiated hub outperforms pushed equivalents of the same content**:

| Content | Launched from launcher | Standalone / pushed |
|---|---|---|
| Product tour | 67% completion | 31% |
| Microsurvey | 54% completion | 15% |

([Chameleon 2025](https://www.chameleon.io/benchmark-report)). Additional launcher data: 23% of users click into a launcher, rising to **27% when a welcome state is added**; users complete ~5 checklist items per session. The 2023 report recorded a 1,100% YoY increase in launcher engagement and 54.5% of launcher users going on to start a tour — a growth figure that mostly reflects Chameleon customers adopting the feature, not user preference shifting.

**Interpretive caution:** this comparison is confounded by selection. A user who opens a launcher has self-selected into a learning mood; a user who is shown a tour has not. The honest reading is not "launchers are 2× better" but "**pull beats push, partly because pull pre-qualifies the audience**" — which is still the correct design conclusion, since a pushed message spends interruption budget on the unqualified majority.

Announcement centers (a persistent, always-available "what's new" list) are the same structural bet: zero interruption cost, retrieval on demand, and a home for the depth that a modal cannot carry. No published engagement benchmarks were found for standalone announcement centers.

---

## 10. Behavior-triggered contextual prompts and discovery-via-search

**Behavior-triggered "did you know" prompts** are the pattern the HCI literature most directly endorses, because they satisfy both variables that matter: relevance (fired by an observed behavior that the feature addresses) and timing (fireable at a task boundary). Iqbal & Bailey's relevance effect — 3.59 vs 4.98 frustration — is the quantified argument. Userpilot cites a Smoobu A/B test in which walkthrough-exposed users connected channels at a 17% higher rate ([source](https://userpilot.com/blog/in-app-messaging/)); this is a single-customer vendor case study with no absolute numbers.

**Discovery via search / command palette** is the "pull" extreme. Superhuman's engineering write-up makes the design argument without any data ([blog](https://blog.superhuman.com/how-to-build-a-remarkable-command-palette/)):
- It permits shipping features that "could never warrant a button or a dropdown."
- Users prefer search to menus, because menus only help if the user already understands the organizing scheme.
- Showing the keyboard shortcut next to each command lets users graduate from palette → direct shortcut over time — a genuine progressive-disclosure mechanic.
- Supporting principles: fuzzy matching and synonym tolerance ("archive" → "Mark Done"), contextual ranking, and deliberate visual cutoff to imply more options exist.

No adoption data was locatable for command palettes in any product. This is a pattern with strong practitioner consensus and effectively zero public measurement.

Pendo's benchmark supplies the reason discovery surfaces matter at all: across 6,800 customers, **6.4% of features drive 80% of click volume**, and even top-performing products only reach 15.6% feature adoption ([Pendo](https://www.pendo.io/pendo-blog/product-benchmarks/)). Feature depth is, by default, unused.

---

## 11. Frequency capping and orchestration

The operational practices, as documented by the messaging vendors:

- **Global + per-channel caps in parallel.** Braze supports capping total messages across all channels *and* per-channel limits simultaneously ([Braze docs](https://www.braze.com/docs/user_guide/messaging/messaging_fundamentals/frequency_capping)). Its stated rationale for asymmetric limits: a high volume of in-app messages may not degrade effectiveness, while **more than two push notifications per week can raise uninstall rates** ([Braze](https://www.braze.com/resources/articles/whats-frequency-capping)). No study is cited for the push threshold.
- **Cross-channel is the point.** Braze's argument is that per-channel isolation makes fatigue accumulate invisibly, because no system sees the aggregate.
- **Priority arbitration.** Practitioner guidance is to run an orchestration layer where urgent/system messages preempt promotional ones and no more than one flow can occupy a session ([Appcues](https://www.appcues.com/blog/in-app-notifications) recommends a cap of one or two in-app notifications per session).
- **Preference centers** let users self-select categories and frequency, moving the cap decision to the user ([Airship](https://www.airship.com/explainer/in-app-messaging-explained/)).

The HCI evidence adds a fourth control that vendors rarely implement: **a deferral queue with a boundary condition and a timeout**. OASIS's design — hold the request until the next breakpoint of the required granularity, or until a max-wait expires — is directly implementable without machine learning if the app has explicit task boundaries (screen exits, flow completions, submit/confirm events). The measured cost was <90s of deferral.

---

## 12. Accessibility

These are conformance requirements, not recommendations.

**Tooltips and any hover/focus-triggered content — WCAG 2.1 SC 1.4.13 (Level AA)** ([W3C Understanding](https://www.w3.org/WAI/WCAG21/Understanding/content-on-hover-or-focus.html)):
- **Dismissible** without moving pointer or focus (typically Escape).
- **Hoverable** — the pointer can enter the tooltip without it vanishing.
- **Persistent** until dismissed, until the trigger is removed, or until the info becomes invalid. No auto-hide timers.
- Native `title`-attribute tooltips are exempt (the user agent controls them); **every custom tooltip, popover, and non-modal popup is covered.**
- SC 1.4.13 is referenced by ADA Title II/III practice, Section 508, EN 301 549, and the European Accessibility Act ([summary](https://www.boia.org/blog/tips-for-meeting-wcag-1.4.13-content-on-hover-or-focus)).

**Announcement modals — ARIA Authoring Practices dialog pattern** ([W3C APG](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/)): `role="dialog"`, `aria-modal="true"` *only* when outside content is genuinely inert both in code and visually, an accessible name via `aria-labelledby`/`aria-label`, focus moved into the dialog on open, Tab/Shift+Tab cycling within it, Escape to close, and focus returned to the invoking element on close.

**Animated hotspots, beacons, confetti — SC 2.3.3 Animation from Interactions (Level AAA)** ([W3C](https://www.w3.org/WAI/WCAG21/Understanding/animation-from-interactions.html)): non-essential motion triggered by interaction must be disableable; honoring the OS `prefers-reduced-motion` setting is the standard mechanism. Vestibular-disorder impact (dizziness, nausea) is the stated harm.

**Additional practical items** not covered by a single SC: badge state must be exposed to screen readers as text (a colored dot alone conveys nothing); dynamically injected banners need an appropriate live region or they will not be announced; and every dismiss affordance needs a touch target and an accessible name, not just an "×" glyph.

---

## Evidence quality notes

**Tier 1 — controlled experiments with published methods.** Bailey & Konstan 2006 (N=50, within-subjects timing manipulation); Adamczyk & Bailey CHI 2004; Iqbal & Bailey CHI 2008 (OASIS, two studies, ANOVA reported with F and p); Iqbal & Horvitz CHI 2007 (field study, 5,747 email + 4,487 IM alerts); NN/G mobile tutorials (N=70, between-subjects, p-values reported). **Caveat:** all the interruption work is 2004–2008 desktop knowledge-work; the mechanisms (working memory, task boundaries) are general, but the effect sizes were not measured on mobile consumer apps.

**Tier 2 — eye-tracking / observational research.** NN/G banner blindness (multi-study, 1997–2024). Behavioral, but case-study-level reporting: the "0.8% of attention" figure is from one site, not a pooled estimate.

**Tier 3 — vendor telemetry benchmarks (Chameleon, Pendo).** Large N (550M+ interactions; 6,800 customers), but with structural bias:
- **Selection bias.** The population is customers of a guidance tool, i.e. B2B SaaS web apps whose teams already invest in in-app guidance. Consumer mobile is essentially absent.
- **Denominator opacity.** Pendo excludes close/dismiss/snooze from "engagement" and weights its benchmark by traffic ([docs](https://support.pendo.io/hc/en-us/articles/50384284250523-Guide-effectiveness)); Chameleon's "completion" and Pendo's "engagement" are not interchangeable. Pendo also suppresses benchmark lines below 10 matching guides.
- **Instability.** Chameleon's 2023 report has video tours at 47.67% completion; its 2025 report has text+video modals at 21% vs text-only 44%. Different surfaces, but the reversal shows how little these numbers travel.
- **Commercial incentive.** Every one of these reports concludes that more/better in-app guidance is warranted. Findings that *reduce* guidance (shorter tours, user-triggered only, launchers over modals) are more credible than findings that expand it, because they cut against interest.
- **No controls.** None of these are experiments. "Launcher tours complete at 67%" compares self-selected users to a pushed population.

**Tier 4 — asserted practitioner claims with no traceable source.** "Coach marks improve adoption 40–60%"; "in-app messages → 3.5× retention" (attributed to Localytics via [Appcues](https://www.appcues.com/blog/in-app-notifications)); "badges → 16–25% more opens"; "empty states → +60% activation"; Airship's "8× vs push," "140% more frequent purchases," "82% lift" ([Airship](https://www.airship.com/explainer/in-app-messaging-explained/), no methodology, sample, or period disclosed); the widely-repeated "23 minutes 15 seconds to recover from an interruption" (a Gloria Mark finding routinely quoted out of its original context). **Do not plan against any of these.**

---

## Implications for FTF *(hypotheses only — none of this is validated on FTF users)*

FTF's shape matters for translation: it is a consumer mobile app with a strongly seasonal, spiky usage pattern (trade deadlines, rookie drafts, waiver days), sessions that are short and goal-directed, and a feature set where the depth (Elo matchup voting, tier ladders, want/accept boards, send-in-platform) is genuinely secondary to the core loop.

1. **The interruption budget is smaller here than in the B2B SaaS benchmarks.** A 3-minute session evaluating one trade has fewer safe boundaries than a 90-minute programming session. *Hypothesis:* FTF can afford roughly one pushed presentment per session, and it should be spent on the single highest-value unadopted feature for that user, not on whatever shipped most recently.

2. **Explicit breakpoints already exist and are cheap to instrument.** Trade-send confirmed, matchup vote submitted, board saved, results screen reached. *Hypothesis:* a deferral queue that holds a message until the next of these events (with a session timeout) reproduces the OASIS result without any modeling, since FTF's boundaries are declared by the code rather than inferred.

3. **Relevance-gating should outrank recency-gating.** Iqbal & Bailey found content relevance had a larger effect on frustration than timing policy. *Hypothesis:* "you have 3 unranked players at a position you're thin at" will outperform "we shipped tier ladders" even though the latter is newer, and a purely chronological what's-new modal is the weakest available format.

4. **The notification inbox is the right home for depth; modals are the wrong one.** FTF already has an inbox — structurally a pull surface with the launcher/announcement-center profile. *Hypothesis:* routing feature news to the inbox with at most a badge, and reserving modals for changes that alter the trade-evaluation mental model (e.g. a valuation-model change), preserves both surfaces' signal.

5. **If a modal ships, assume 4 seconds and one line.** 38% dismissed under 4s, and text+video completed at 21% vs text-only 44%. *Hypothesis:* an FTF modal whose value requires watching a clip or reading a paragraph will underperform a one-line + one-button version of the same message.

6. **Empty states are FTF's highest-leverage untapped teaching surface.** Empty want/accept boards, an empty trade-finder result set, an empty matchup history, an empty inbox — each is a moment where the missing feature's value is maximally salient and the interruption cost is zero. *Hypothesis:* converting these to status + learning cue + direct action outperforms any equivalent pushed tooltip, and does so without spending interruption budget.

7. **Badges need an expiry policy before the first badge ships.** FTF has multiple badgeable namespaces (inbox, feedback, new features, trade offers). *Hypothesis:* without per-namespace caps and auto-expiry, red-dot blindness will degrade the *inbox* badge — the one with genuine transactional value — as collateral damage from feature-announcement badges.

8. **Seasonality is an orchestration variable the vendor literature doesn't model.** Deadline week is simultaneously peak engagement and peak task-focus. *Hypothesis:* presentment volume should be inverse to task urgency — teach during the offseason and preseason lulls, go quiet during deadline and draft windows.

9. **Any tooltip pattern must be designed touch-first.** The 98%-hover figure is a desktop artifact. *Hypothesis:* an `ⓘ` tap-target next to domain jargon (Elo, tier, mutual gain, want/accept) is the highest-value tooltip use in FTF — reference-on-demand, not walkthrough steps — and it needs Escape/back-dismissal and persistence to satisfy SC 1.4.13.

10. **Accessibility work is a prerequisite, not a follow-up.** Any hotspot animation needs a `prefers-reduced-motion` branch; any announcement modal needs focus trap + return; any badge needs a text equivalent. *Hypothesis:* retrofitting these across a shipped pattern library costs more than building the three primitives (Tooltip, AnnouncementModal, Badge) correctly once.

**Open questions this lens could not answer:** no published measurement exists for hotspot engagement, standalone announcement-center usage, or command-palette adoption; no interruption research has been replicated on short-session consumer mobile; and no vendor benchmark segments by seasonal usage. If FTF wants numbers for those, it will have to generate them.

---

## Sources

**HCI / peer-reviewed**
- Bailey & Konstan (2006), *On the need for attention-aware systems* — https://interruptions.net/literature/Bailey-CHB06_1.pdf | https://www.sciencedirect.com/science/article/abs/pii/S074756320500107X
- Adamczyk & Bailey (CHI 2004), *If not now, when?* — https://dl.acm.org/doi/10.1145/1240624.1240732 (referenced via Iqbal & Bailey CHI 2007)
- Iqbal & Bailey (CHI 2008), *Effects of Intelligent Notification Management on Users and Their Tasks* — https://interruptions.net/literature/Iqbal-CHI08.pdf | https://dl.acm.org/doi/10.1145/1357054.1357070
- Iqbal & Bailey (CHI 2007), *Understanding and Developing Models for Detecting and Differentiating Breakpoints* — https://interruptions.net/literature/Iqbal_Bailey-CHI07.pdf
- Iqbal & Horvitz (CHI 2007), *Disruption and Recovery of Computing Tasks: Field Study, Analysis, and Directions* — https://www.microsoft.com/en-us/research/wp-content/uploads/2016/11/CHI_2007_Iqbal_Horvitz-1.pdf
- Trafton et al., goal encoding & rehearsal in interruption recovery — https://www.interruptions.net/literature/Trafton-IJHCS03.pdf
- Resumption-cost mechanisms review — https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10896823/

**Nielsen Norman Group**
- *Mobile Tutorials: Wasted Effort or Efficiency Boost?* — https://www.nngroup.com/articles/mobile-tutorials/
- *Instructional Overlays and Coach Marks for Mobile Apps* — https://www.nngroup.com/articles/mobile-instructional-overlay/
- *Banner Blindness Revisited: Users Dodge Ads on Mobile and Desktop* — https://www.nngroup.com/articles/banner-blindness-old-and-new-findings/
- *Banner Blindness: The Original Eyetracking Research* — https://www.nngroup.com/articles/banner-blindness-original-eyetracking/
- *Designing Empty States in Complex Applications* — https://www.nngroup.com/articles/empty-state-interface-design/
- *Progressive Disclosure* — https://www.nngroup.com/articles/progressive-disclosure/

**Accessibility standards**
- WCAG 2.1 SC 1.4.13 Content on Hover or Focus — https://www.w3.org/WAI/WCAG21/Understanding/content-on-hover-or-focus.html
- WCAG 2.1 SC 2.3.3 Animation from Interactions — https://www.w3.org/WAI/WCAG21/Understanding/animation-from-interactions.html
- ARIA Authoring Practices — Modal Dialog pattern — https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/
- BOIA, tips for meeting 1.4.13 — https://www.boia.org/blog/tips-for-meeting-wcag-1.4.13-content-on-hover-or-focus
- Deque University, 1.4.13 — https://dequeuniversity.com/resources/wcag2.1/1.4.13-content-on-hover-or-focus

**Vendor benchmarks and guidance (flagged for bias)**
- Chameleon User Onboarding Benchmark Report 2025 (550M+ interactions) — https://www.chameleon.io/benchmark-report
- Chameleon, *What 550M data points say about your product tour* — https://www.chameleon.io/blog/mastering-product-tours
- Chameleon, *The Hidden Metrics of Effective Product Tours* — https://www.chameleon.io/blog/effective-product-tour-metrics
- Chameleon Benchmark Report 2023 (212M interactions) — https://www.chameleon.io/benchmark-report-2023
- Pendo, 2024 software benchmarks — https://www.pendo.io/pendo-blog/product-benchmarks/
- Pendo Help Center, Guide effectiveness (metric definitions) — https://support.pendo.io/hc/en-us/articles/50384284250523-Guide-effectiveness
- Appcues, *In-app notifications: 8 types, best practices, and examples* — https://www.appcues.com/blog/in-app-notifications
- Appcues, *User Onboarding Metrics & KPIs* — https://www.appcues.com/blog/user-onboarding-metrics-and-kpis
- Appcues, *Modal window design* — https://www.appcues.com/blog/modal-dialog-windows
- Braze, *Rate limiting and frequency capping* (docs) — https://www.braze.com/docs/user_guide/messaging/messaging_fundamentals/frequency_capping
- Braze, *What is Frequency Capping* — https://www.braze.com/resources/articles/whats-frequency-capping
- Braze, *Red Dot Blindness: A Human-First Approach to Badging* — https://www.braze.com/resources/articles/beware-red-dot-badging
- Airship, *What is in-app messaging?* — https://www.airship.com/explainer/in-app-messaging-explained/
- Userpilot, *Is In-App Messaging Still Working in 2026?* — https://userpilot.com/blog/in-app-messaging/
- Superhuman, *How to build a remarkable command palette* — https://blog.superhuman.com/how-to-build-a-remarkable-command-palette/
- Jimo, hotspot definition and best practices — https://jimo.ai/glossary/hotspot
- Chameleon hotspot-tooltip template — https://www.chameleon.io/templates/hotspot-tooltip
