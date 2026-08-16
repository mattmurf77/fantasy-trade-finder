# R2-2B — How Small Teams Actually Build In-House Contextual Guidance (and Measure It at Low Traffic)

**Date:** 2026-08-15
**Round:** 2 (follow-on to [round-1 B5](../round-1/b5-measurement-and-tooling.md))
**Lens:** Engineering practice — the data model, the content-delivery path, the React Native rendering problem, exposure logging, low-traffic measurement, and content governance for a home-built tips/tour layer.
**Scope note:** This is a build-mechanics document. It does not re-argue build-vs-buy (round 1 settled that), does not recommend a pattern, and contains no implementation.

---

## TL;DR

- **Nobody publishes "we built a tour engine." They publish three adjacent things**: a *tour engine* (Sentry), a *communications/nudge platform* (Airbnb OMNI, Uber's driver content feed), and *server-driven UI* (Airbnb Ghost Platform, Plaid Link). All three converge on the same decomposition — **what / who / when / where** — which is the reusable artefact.
- **The best-specified public data model for a tips registry is Apple's TipKit**, and it reads as a framework-agnostic spec: a `Tip` with title/message/asset/actions, **parameter-based rules** (state predicates) and **event-based rules** (counts over a time window), a global **display frequency** with per-tip override, `maxDisplayCount(n)`, and explicit **invalidation reasons** (`.userPerformedAction`).
- **Round 1's "OSS RN tour libs are unmaintained" needs a correction.** `stackbuilders/react-native-spotlight-tour` is **actively maintained** — v4.0.0 (2025-06-23), commits through 2026-08-11, 517 stars, MIT — rendering the spotlight with `react-native-svg` + Floating UI. `rn-tourguide` and `react-native-copilot` remain stale; `react-native-walkthrough-tooltip` (82k weekly downloads) has shipped nothing since 2024-01-09. The category is not dead; one library is alive.
- **The brief's premise "FTF has EAS Update for OTA JS" is false as of this checkout.** `expo-updates` is **absent** from `mobile/package.json`; `mobile/app.json` has no `updates` or `runtimeVersion` block. Content changes today require a TestFlight/App Store binary.
- **Exposure logging has one universal rule: fire it where the UI renders, not where the flag is read.** Statsig ships `disable_exposure_logging` + `manually_log_*_exposure` for exactly this; PostHog's default `$feature_flag_called` fires at `getFeatureFlag()` and is **cached across sessions** ("won't fire again unless `identify` or `reset` is called") — a real trap for returning users; GrowthBook routes everything through a `trackingCallback`.
- **PostHog's own numbers say FTF-sized traffic can't run classical guidance A/Bs**: projections need "at least 1 day of runtime and 100 exposures"; **500+ users per variant** for a 10%+ lift; default MDE **30%**. The substitutes are painted-door tests, staged-rollout difference-in-differences, Bayesian shrinkage priors, and qualitative replay — not smaller A/Bs.
- **Holdouts are the one causal instrument that fits a permanently-on guidance layer.** Statsig recommends **1–2%** sizing over **three to six months**, with the caveat that "you must maintain a functioning product with no new features for a longer period."
- **FTF already has a working in-house guidance engine**: `useGuide.ts` (zustand), `guideTargets.ts` (testID→ref registry, `measureInWindow` + 250 ms timeout + degrade-to-bubble-only), `AnalystGuide.tsx` (single RootNav overlay), `analystScript.ts` (114-line content table), persisted in `ftf_onboarding_state_v1`, arbitrated by `useInterruptCoordinator`. The gaps are **remote content**, **a declarative eligibility layer**, and **exposure joined to downstream adoption** — not the overlay.

---

## 1. What teams actually publish, and the shape underneath

There is essentially no genre of engineering blog post called "how we built our tips engine." What exists is three adjacent genres, and reading them together gives you the design.

**(a) The tour engine.** [Sentry's write-up](https://blog.sentry.io/building-a-product-tour-in-react) is the closest thing to a direct account. They replaced a legacy system that was "disjointed; the text for each step was separated from the focused element," making it "challenging to conditionally alter it, use custom styling, or swap in pre-existing components within tour steps." The replacement is deliberately unglamorous: an enum of tour steps passed to a generalised `TourContextProvider` for type safety, a `useReducer` for navigation state, and — the interesting bit — a **`useRef`-based step registry** that tracks when elements mount and **prevents tour progress until all steps have registered**, explicitly to avoid expensive re-renders. The provider itself renders the overlay "using visual layering (via `z-index`) rather than DOM hierarchy," with `backdrop-filter: blur(3px)` and an inset box-shadow ring on the focused element — chosen because re-parenting children would cause "layout shift."

Two transferable lessons: **co-locate step content with the element it points at**, and **never re-parent the target to highlight it** (measure and draw over it instead).

**(b) The communications/nudge platform.** [Airbnb's OMNI](https://medium.com/airbnb-engineering/airbnbs-promotions-and-communications-platform-6266f1ffe2bd) is the most complete public specification of eligibility-driven messaging. A campaign creator defines "the 'what', 'who', 'when', and 'where'," each backed by a service: an **Audience Service** (visual Audience Builder over "100+ such user attributes (both static and machine learning-derived)"), a **Workflow Service** (hourly cron for scheduled campaigns; real-time event triggers that evaluate *and rank* eligible campaigns), an **Optimization Service** (content ranking, propensity personalisation, send-time optimisation), plus Presentation/Rendering/Delivery. Non-engineers work entirely in the OMNI UI, including approval workflows and analytics. Their stated lessons are governance-shaped: "approval processes, debug tooling, and systematic guardrails," plus rate limiting.

[Uber's driver content feed](https://www.uber.com/en-US/blog/mobile-content-delivery/) covers the same ground for mobile, and its central lesson is the one most relevant to a tips system: they **divorced targeting logic from presentation**. Initially "adding new content types required mobile code changes for each design variation"; the fix was a **"block-based" design system** where reusable components (title, image, button sets) are configured in a UI tool and serialised as JSON for runtime rendering, so "new services producing updates for users no longer need to deal with presentational aspects." A new message type went from a mobile release cycle to days.

**(c) Server-driven UI, the maximal version.** [Airbnb's Ghost Platform](https://medium.com/airbnb-engineering/a-deep-dive-into-airbnbs-server-driven-ui-system-842244c5f5) ships *sections*, *screens* and *actions* from a GraphQL backend, motivated by release cadence — previously a feature change needed "a new version of our mobile apps." Its load-bearing constraint: clients must already contain the native section components, and features "can only use existing sections." [Plaid Link](https://engineering.plaid.com/server-driven-ui-with-directed-graphs-65fbdfe6a8ba) goes further — the flow is a backend directed graph of Pane/Processor/Switch nodes, clients are "focused rendering engines," workflows carry semantic versions so legacy SDKs pin to compatible graph versions. Plaid's cost list is the most useful paragraph in the SDUI literature: **tooling investment was underestimated**, the fixed pane set must keep being loosened, mixing static graphs with dynamic processors "adds cognitive overhead," and it is "tempting to put experiential branching logic into" the wrong layer.

**The synthesis for a small team**: the SDUI end of the spectrum is a platform investment with a documented tooling tax. The tractable version is Uber's — *fix the presentation primitives in the client, ship only content + targeting from the server*. A tips system is the easiest case of this, because the primitive count is roughly two (inline callout, anchored spotlight step).

---

## 2. The reference data model: TipKit as a spec

Apple's [TipKit](https://developer.apple.com/videos/play/wwdc2023/10229/) is the best-documented tips registry in existence, and worth reading as a *schema* independent of Swift.

- **Tip** = title + message, optionally asset, actions, options. Content guidance: titles are direct actions, messages benefit-focused, placement "close to the relevant button or element."
- **Parameter-based rules** are "persistent and are best suited for showing tips based on a Swift value type" — predicates over durable user state (`isLoggedIn == true`).
- **Event-based rules** "allow you to define an action that must be performed before a person becomes eligible for a tip," canonically a count over a window: entered the detail view ≥ 3 times in the last 5 days.
- **Display frequency** is a *global* policy (`.daily`, `.hourly`, `.immediate`, or custom interval) with a per-tip escape hatch `.ignoresDisplayFrequency(true)`.
- **Termination** has two independent mechanisms: `maxDisplayCount(5)` and `invalidate(reason: .userPerformedAction)`.
- **Anti-scope** is specified: *not* for promotional messages, error messages, feature announcements with no required action, or complex instructions.

The governing sentence — "In-app education should be focused on those who would benefit from it, and we aim to avoid getting in the way of individuals while they are trying to accomplish something in an app" — is the acceptance criterion the rest of the model implements.

Read against OMNI: TipKit's parameter rules are the Audience Service in miniature, event rules are the event-driven Workflow triggers, display frequency is rate limiting, invalidation is campaign lifecycle. **The two are the same system at two scales** — a good sign the decomposition is real rather than an artefact of one company's architecture.

---

## 3. Shipping content without an app release — the actual constraints

[EAS Update](https://docs.expo.dev/eas-update/introduction/) lets an app "update its own non-native pieces (such as JS, styling, and images) over-the-air" — copy, layout, assets. It cannot change native code, native dependencies, permissions, or the Expo SDK version, and store rules still bind: "your updates need to follow the App Store and Play Store guidelines, including the content of the updates and how you use them."

**Verified against this repo, the round-2 brief's premise is wrong**: `expo-updates` does not appear in `mobile/package.json` (Expo `~54.0.33`, RN `0.81.5`, `newArchEnabled: true`), and `mobile/app.json` has no `updates` or `runtimeVersion` key. There is no OTA path today.

That leaves three content-delivery tiers, in ascending cost:

1. **Compiled-in content** — what FTF does now (`analystScript.ts`; `useWhatsNew`'s in-file `WHATS_NEW` map keyed to `Constants.expoConfig.version`). Zero infrastructure; every copy edit is a binary release.
2. **OTA JS** — adopt `expo-updates`; copy edits ship in minutes, still a build+publish step, still subject to store guidelines. Content remains code.
3. **Server-delivered content** — a JSON registry served by the existing Flask backend, client holding the render primitives (the Uber pattern). Copy and targeting change with no client artefact, at the cost of a schema, a cache/fallback path, and a forward-compatibility rule (unknown tip types silently skipped by old clients — the Ghost Platform constraint).

FTF already has a server-side flag surface (`config/features.json`, 187 keys, via `backend/feature_flags.py`), so tier 3 is a narrower jump than it looks: the delivery channel exists; only the content payload and eligibility grammar are missing.

---

## 4. React Native specifics: anchoring, overlays, and what's actually maintained

### 4.1 The library landscape, re-verified

Round 1 concluded the OSS RN tour category is unmaintained. Re-checking the npm registry and GitHub APIs directly on 2026-08-15 gives a more differentiated picture:

| Package | Latest | Published | Repo last push | Stars | Weekly dl |
|---|---|---|---|---|---|
| `react-native-spotlight-tour` | 4.0.0 | 2025-06-23 | **2026-08-14** | 517 | 7,542 |
| `@wrack/react-native-tour-guide` | 1.0.1 | **2026-06-27** | 2026-07-30 | 19 | 1,783 |
| `react-native-walkthrough-tooltip` | 1.6.0 | 2024-01-09 | 2024-05-10 | 688 | 82,225 |
| `react-native-copilot` | 3.3.3 | 2024-12-17 | 2024-12-17 | 2,437 | 15,580 |
| `rn-tourguide` | 3.3.2 | 2024-10-30 | 2025-06-11 | 861 | 9,968 |

`react-native-spotlight-tour` is the correction: MIT-licensed, commits within the last week, and architecturally close to what a hand-built layer would do anyway. Per [its docs](https://stackbuilders.github.io/react-native-spotlight-tour/), it wraps targets in an `AttachStep` component with an `index`, renders the spotlight with SVG, and "uses Floating UI under the hood in order to handle elements positioning, it re-exports all floating-ui middlewares" (defaults `[flip(), offset(4), shift()]`, placement `bottom`). Peer deps are minimal — `react-native-svg >= 12.1.0` — and it claims Android/iOS/Web. What the docs do **not** state: Expo support, New Architecture support, or handling of off-screen/cross-screen targets. Those three questions decide whether it's usable, and the documentation answers none of them.

The high-download outlier is instructive: `react-native-walkthrough-tooltip` has ~82k weekly downloads on a two-year-old release. High usage is not a maintenance signal.

### 4.2 The anchoring problem

The core mechanic in every RN implementation is the same: get the target's window-space rect, then draw an absolutely-positioned overlay with a cutout at that rect. `measureInWindow` is the standard call. The known failure modes are what a hand-rolled layer must handle:

- **Unmounted or not-yet-laid-out nodes never call back.** No error; the callback simply doesn't fire.
- **Fabric changes the timing contract.** Under the New Architecture the shadow tree moves to C++ and measurement becomes synchronous, but "code that reads measurements inside ref callbacks or immediately after component mount may produce incorrect values under Fabric until the first layout pass completes" ([Software Mansion](https://swmansion.com/blog/react-natives-new-architecture-the-tricky-parts-3-4-c4638c65927c/), [PkgPulse](https://www.pkgpulse.com/blog/react-native-new-architecture-fabric-turbomodules-expo-2026)). FTF has `newArchEnabled: true`.
- **Android release builds have a reported `measure`/`measureInWindow` coordinate bug** ([wix/react-native-navigation #8086](https://github.com/wix/react-native-navigation/issues/8086)), worse on Android 15+, only in release builds — invisible in development.
- **Cross-screen targeting has no library answer.** Sentry's registry-gate pattern (don't advance until every step's element has registered) is the published mitigation, and only works within a mounted tree.

FTF's `guideTargets.ts` already encodes the pragmatic version of all of this: a `Map<testID, RefObject<View>>` registry, `measureInWindow` promise-wrapped with a **250 ms timeout**, NaN/zero-width validation, and an explicit degrade path — "A missing/unmeasurable target degrades to bubble-only — never a blank cutout." That is a more defensive contract than the published libraries offer, and `testID` as the registry key doubles as the Maestro selector.

---

## 5. Exposure logging done right

All three candidate platforms agree on the principle and differ only in ergonomics.

**Statsig** is the most explicit. By default the SDK logs an exposure when you check a gate, config, experiment, or layer parameter. Every main function accepts `disable_exposure_logging`, paired with `manually_log_gate_exposure` / equivalents, and the documented rationale is exactly the coach-mark case: log exposure "only after a user has been exposed to the treatment. Logging earlier pollutes test results with users who didn't see the treatment."

**PostHog** derives exposure from `$feature_flag_called`, emitted when you call `getFeatureFlag()` or read a flag from an `evaluateFlags` result. Two mechanics matter for a guidance layer. First, **only variant-reading APIs count** — "You must use `getFeatureFlag()` (or its framework equivalent like `useFeatureFlagVariantKey()`) to check variants"; `getAllFlags()`, `getFeatureFlags()` and payload-only accessors "do **not** record an exposure event." Second, **the event is deduplicated and cached across sessions**: "Once emitted for a given flag and value, the event is cached across sessions and won't fire again unless `identify` or `reset` is called" — which silently under-counts exposure for returning users. PostHog supports **custom exposure events** for teams needing "more precise control over when users are considered exposed," provided the custom event manually carries `$feature/<flag-key>`. Their clarifying rule: "Metric events don't need a variant property — only the **exposure event** determines which variant a user belongs to."

**GrowthBook** has no manual/automatic split; a `trackingCallback` is "called every time a user is put into an experiment," and they recommend recording the attributes handed to the callback "so exposure events consistently reflect the attributes GrowthBook used for targeting and assignment." Their RN SDK is "a thin wrapper on top of the Javascript Library."

**The composite pattern**, consistent with round 1's Spotify/Microsoft dilution material: evaluate eligibility freely; suppress the automatic exposure; fire one exposure event **inside the render path of the tip itself**, carrying tip id, variant and surface. The downstream join is then `exposure → first meaningful use of the feature the tip advertises`, with the untriggered remainder as an A/A sanity check. FTF's `guide_step_shown` already fires at exactly this point (`useGuide.ts:101`, inside `requestStep`) — a render-time exposure event that simply isn't wired to the experiment layer.

---

## 6. Measuring guidance when you don't have the traffic

PostHog's published thresholds are the cleanest statement of the constraint. Their [sample-size guidance](https://posthog.com/docs/experiments/sample-size-running-time) uses `N = (16 × variance) / d²` where 16 "comes from achieving 80% statistical power at 95% confidence," defaults the MDE to **30%**, requires "at least 1 day of runtime and 100 exposures" before automatic projections, and recommends **500+ users per variant** even for a 10%+ lift, plus "at least one full cycle of user behavior." A tooltip that moves adoption by 5% is not measurable at FTF's weekly new-user volume.

The credible substitutes, in rough order of cost:

1. **Painted-door / fake-door tests.** Measure a coarse signal (does anyone tap the entry point at all) instead of a subtle conversion delta. [Amplitude](https://amplitude.com/explore/experiment/painted-door-testing) and [ProdPad](https://www.prodpad.com/glossary/fake-door-testing/) both treat this as the low-cost demand check; the documented risk is trust damage, mitigated by an honest disclosure moment. For a *guidance* question it reframes "does the tip work" into "does anyone want the thing the tip points at" — a much larger effect to detect.
2. **Staged rollout as a natural experiment.** Rolling to cohort A before cohort B produces a difference-in-differences design; the identifying assumption is parallel pre-treatment trends ([Statsig](https://www.statsig.com/perspectives/diff-in-diff-causal-inference)). Where a guidance rule has a numeric threshold (show the tip after N sessions), the threshold itself supports a regression-discontinuity estimate ([Statsig](https://www.statsig.com/perspectives/regression-discontinuity-thresholds)).
3. **Bayesian analysis with an explicit shrinkage prior.** GrowthBook defaults to Bayesian with "a Normal distribution with mean 0 and standard deviation 0.3" which "will shrink positive and negative results towards 0" and is "strong enough to ensure that experiments with small sample sizes are not over-interpreted," backed by "Minimum Data Thresholds so you aren't drawing conclusions too early (e.g. when it's 5 vs 2 conversions)." They are honest that early stopping "can still result in inflated false positive rates."
4. **Holdouts for the layer, not the tip.** [Statsig's holdouts](https://docs.statsig.com/experiments/holdouts-introduction) measure aggregate impact of everything shipped since the holdout began; recommended sizing is "a low single-digit holdout percentage, such as 1%–2%," run "three to six months, then releas[e] the holdout," with the stated debt that "you must maintain a functioning product with no new features for a longer period." It is the only instrument that can price a whole guidance layer at low traffic — at the cost of answering one question every six months.
5. **Qualitative replay.** PostHog session replay does support React Native (via `@posthog/react-native-plugin`, the renamed `posthog-react-native-session-replay`, ≥ 2.0.1 for SDK 4.47+; replay itself requires SDK ≥ 3.2.0, `enableSessionReplay: true`, and project-level "Record user sessions"). Caveats: **RN defaults to full screenshots** for masking rather than the wireframe view used on native iOS/Android, **mobile replay bills on its own meter**, and iOS install requires `pod install` — so not an Expo Go path.

The honest read: at FTF scale, guidance work should be **evaluated observationally and gated qualitatively**, with randomised inference reserved for the largest, coarsest questions.

---

## 7. Content governance at small scale

There is no published playbook for "who writes the tips." Two adjacent bodies of practice converge on one.

**From the platform side**, OMNI's lessons name the three governance artefacts directly: "approval processes, debug tooling, and systematic guardrails." Practitioner writing on in-app messaging adds the concrete controls — session caps (one to two messages per session is the common recommendation), global suppression windows, and **priority queues** so lifecycle-critical messages outrank promotional ones ([Airship](https://www.airship.com/explainer/in-app-messaging-explained/), [Courier](https://www.courier.com/blog/how-to-reduce-notification-fatigue-7-proven-product-strategies-for-saas)). This material is vendor-produced and unquantified; treat the *controls* as real and the *numbers* as folklore.

**From the content-ops side**, the recurring prescriptions are a **single named owner** per artefact (not a team), a **quarterly review cadence**, and an explicit **retirement workflow** answering four questions: under what circumstances is a piece retired, what does retiring look like, is it removed or archived, and who is accountable ([Docsie](https://www.docsie.io/blog/glossary/content-governance/), [US DOL](https://www.dol.gov/agencies/eta/ui-modernization/use-plain-language/content-governance)).

TipKit supplies the machine-enforceable half that prose cannot: `maxDisplayCount`, global display frequency, and `invalidate(reason: .userPerformedAction)` mean a tip that has done its job stops existing without anyone remembering to retire it. **The strongest small-team pattern implied by these sources is to make sunsetting automatic rather than procedural** — every tip declares its own death condition at authoring time — reserving the human quarterly review for the tips that *didn't* self-terminate.

FTF already has the arbitration half in `useInterruptCoordinator` (flag `ux.prompt_arbiter`): a single `activeSurface` slot with a fixed priority order (quickset prompt > coach mark > apple banner > outlook banner), no pre-emption, root modals self-deferring while a slot is claimed, flag-off passthrough. That is the "priority queue + session cap" control the vendor literature describes, already shipped.

---

## 8. Cost and SDK maturity, re-verified 2026-08-15

**Free tiers** (from the pricing pages, not marketing summaries):

| Platform | Free monthly | Then |
|---|---|---|
| **PostHog** | 1M events, 5k session replays, 1M feature-flag requests, 1,500 survey responses, 1M data-warehouse rows; experiments "billed with feature flags" | $0.00005/event, $0.005/replay, $0.0001/flag request, $0.10/survey response — all with volume tiering down |
| **Statsig** | 2M events, **unlimited** flag/config checks, 50k session replays | Pro $150/mo incl. 5M events, then $0.05/1k events |
| **GrowthBook** | Open-source, self-hostable | Cloud tiers not verified this round |

**SDK maintenance** (npm registry + GitHub, direct):

- `posthog-react-native` — **4.63.2, published 2026-08-14**, ~982k weekly. Expo path needs no native deps beyond supported Expo packages. Session replay adds `@posthog/react-native-plugin` and a native build.
- `@statsig/react-native-bindings` — **3.33.4, 2026-08-07**, ~28k weekly. The current package per Statsig's docs.
- **`statsig-react-native-expo` — 4.7.2, last published 2024-06-11**, ~1.1k weekly. The Expo-specific Statsig package is stale even though the general RN bindings are fresh — anyone reaching for it on "Statsig has a maintained RN SDK" adopts a two-year-old dependency. A genuine trap, not surfaced in round 1.
- `@growthbook/growthbook-react` — 1.7.0, 2026-08-11, ~392k weekly.
- Primitives FTF already has: `react-native-svg` 15.12.1 (latest 15.15.5), `react-native-reanimated` 4.1.1 (latest 4.5.3) — both sufficient for an SVG-mask spotlight.

---

## Evidence quality notes

- **Strong (primary, verifiable):** npm registry and GitHub API results (queried directly, not scraped from blogs); PostHog, Statsig, GrowthBook and Expo product documentation; Apple's WWDC23 TipKit session; the Sentry, Airbnb (OMNI + Ghost Platform), Uber and Plaid engineering posts — first-party accounts of systems those companies actually run, including stated costs and failures.
- **Medium (credible but self-interested):** Statsig's DiD/RDD explainers and holdout guidance; PostHog's sample-size formula (standard, but the 30% default MDE is a product default, not a statistical finding); Amplitude/ProdPad on painted-door tests.
- **Weak (treat as opinion):** all in-app-messaging "governance" numbers — session caps of 1–2, suppression windows, message budgets — come from vendor explainers with no cited data. The *controls* are consistently described; the *thresholds* are unsourced. Same for content-governance cadence advice (quarterly review, single owner): sensible, widely repeated, unmeasured.
- **Unverified / gaps:**
  - `react-native-spotlight-tour`'s **Expo and New Architecture support are not stated in its documentation**. Given FTF runs `newArchEnabled: true` on RN 0.81.5, this is the most decision-relevant unknown here and needs a spike, not a doc read.
  - Statsig's `exposure_logging` doc page 404'd on three URL guesses; the `disable_exposure_logging` / `manually_log_*_exposure` details are cited from search summaries of Statsig's server-SDK docs. The mechanism is corroborated across pages; the exact RN-client API surface is not verified.
  - CXL's low-traffic article returned 403; those substitutes are sourced elsewhere. GrowthBook Cloud pricing not re-verified.
  - Hacker News yielded **nothing** on in-house guidance engines — four Algolia queries, zero hits. The practitioner-discussion channel this brief hoped for does not appear to exist for this topic; the server-driven-UI thread list was the only productive HN result.
- **Corrections to round 1:** (a) the OSS RN tour category is not uniformly dead — `react-native-spotlight-tour` is actively maintained; (b) `statsig-react-native-expo` is stale even though `@statsig/react-native-bindings` is not, so "Statsig has a maintained RN SDK" is true only for one of the two packages.
- **Correction to the round-2 brief's premise:** FTF does **not** have EAS Update. `expo-updates` is absent from `mobile/package.json` and there is no `updates`/`runtimeVersion` block in `mobile/app.json`.
- **Transfer risk:** OMNI, Ghost Platform, Plaid Link and Uber's content feed are all platforms built by teams of dozens for user bases in the tens of millions. Their *decompositions* transfer; their *architectures* emphatically do not. Plaid's own "tooling investment underestimated" note is the warning label.

---

## Implications for FTF — hypotheses only, not recommendations

None of these has been tested against FTF data or code beyond the read-only inspection cited.

1. **FTF's build problem is not the overlay — it's the registry.** `useGuide.ts` + `guideTargets.ts` + `AnalystGuide.tsx` already implement a spotlight/anchor engine with a defensive measurement contract the maintained OSS libraries do not document. *Hypothesis:* adopting `react-native-spotlight-tour` has negative marginal value — swapping working, design-system-native code for an unverified New-Architecture dependency — while adding a declarative eligibility layer (TipKit-shaped rules) on top of the existing engine has high marginal value.
2. **Content is compiled into the binary, and there is no OTA path.** *Hypothesis:* the cheapest unlock is not `expo-updates` but serving the script table as JSON from the existing Flask/`features.json` surface with the client keeping the render primitives (the Uber pattern), because that delivery channel already exists and OTA still requires a build+publish cycle.
3. **`guide_step_shown` is already a correctly-placed exposure event** — fired inside `requestStep` at step activation, carrying `step`/`pose`/`screen`. *Hypothesis:* the round-1 exposure gap can be closed for guidance specifically with no client change, by treating `guide_step_shown` / `coach_mark_shown` as the custom exposure event and joining it to `experiment_exposed`'s `{experiment, variant, unit}` shape server-side.
4. **A tip's death condition should be declared at authoring time.** `GuideStep` already has `once?: boolean`; TipKit adds `maxDisplayCount` and event-rule invalidation. *Hypothesis:* a `maxDisplayCount` + `invalidateOn` field would make sunsetting automatic, shrinking the quarterly-review surface to only the tips that failed to self-terminate — the governance model a one-person content team can sustain.
5. **`useInterruptCoordinator` is the message-budget control the vendor literature describes, already shipped.** *Hypothesis:* the missing half is not more arbitration but *measurement of suppression* — logging which surface was denied the slot would reveal whether the priority order starves a high-value tip, which no current event answers.
6. **Classical A/B testing of individual tips is out of reach.** PostHog's floor is 500+ users/variant at a 10%+ lift with a 30% default MDE. *Hypothesis:* the tractable designs at FTF scale are painted-door tests on the *feature* a tip advertises, staged-rollout DiD across weekly cohorts, and RDD on any session-count threshold in an eligibility rule — and per-tip A/Bs will yield winner's-curse-inflated estimates rather than knowledge.
7. **A 1–2% permanent guidance holdout is the only way to price the whole layer.** Statsig's three-to-six-month guidance maps naturally onto the NFL calendar. *Hypothesis:* a season-long holdout would answer "is the guidance layer worth its clutter" once, credibly; no accumulation of per-tip readouts ever will.
8. **Session replay is the highest-value qualitative instrument available and is genuinely supported on RN — with costs.** *Hypothesis:* it would reveal whether spotlight targets mis-measure in production (the Android release-build `measureInWindow` bug is invisible in dev), but requires a native build, bills on a separate meter, and defaults to full screenshots for masking — a privacy decision to make before switching it on.
9. **The New Architecture measurement contract is an unpriced risk.** FTF runs `newArchEnabled: true`, and Fabric changes when measurements are valid relative to mount. *Hypothesis:* the existing 250 ms timeout masks rather than fixes a class of first-render mis-measurements; the observable symptom would be an elevated bubble-only degrade rate, currently uninstrumented and cheap to add as a property on `guide_step_shown`.

---

## Sources

**In-house guidance and content-delivery engines**
- Sentry Engineering — Building a product tour in React: https://blog.sentry.io/building-a-product-tour-in-react
- Airbnb Engineering — Airbnb's Promotions and Communications Platform (OMNI): https://medium.com/airbnb-engineering/airbnbs-promotions-and-communications-platform-6266f1ffe2bd
- Uber Engineering — Redesigning Uber Engineering's Mobile Content Delivery Ecosystem: https://www.uber.com/en-US/blog/mobile-content-delivery/
- Airbnb Engineering — A deep dive into Airbnb's server-driven UI system (Ghost Platform): https://medium.com/airbnb-engineering/a-deep-dive-into-airbnbs-server-driven-ui-system-842244c5f5
- Plaid Engineering — A new architecture for Plaid Link: server-driven UI with directed graphs: https://engineering.plaid.com/server-driven-ui-with-directed-graphs-65fbdfe6a8ba
- Hacker News (Algolia API) — server-driven UI story index: https://hn.algolia.com/api/v1/search?query=server-driven%20UI&tags=story

**Tips data model**
- Apple — Make features discoverable with TipKit (WWDC23, session 10229): https://developer.apple.com/videos/play/wwdc2023/10229/
- Apple — TipKit documentation: https://developer.apple.com/documentation/tipkit

**React Native implementation**
- react-native-spotlight-tour docs: https://stackbuilders.github.io/react-native-spotlight-tour/
- react-native-spotlight-tour (GitHub): https://github.com/stackbuilders/react-native-spotlight-tour
- react-native-tour-guide (GitHub, `@wrack/react-native-tour-guide`): https://github.com/himanshu-lal4/react-native-tour-guide
- react-native-walkthrough-tooltip (GitHub): https://github.com/jasongaare/react-native-walkthrough-tooltip
- Software Mansion — React Native's New Architecture: the tricky parts (3/4): https://swmansion.com/blog/react-natives-new-architecture-the-tricky-parts-3-4-c4638c65927c/
- PkgPulse — React Native New Architecture 2026: https://www.pkgpulse.com/blog/react-native-new-architecture-fabric-turbomodules-expo-2026
- wix/react-native-navigation #8086 — Android release build `measure`/`measureInWindow` values incorrect: https://github.com/wix/react-native-navigation/issues/8086
- npm registry + downloads API (queried directly 2026-08-15): https://registry.npmjs.org/ , https://api.npmjs.org/downloads/point/last-week/
- GitHub REST API (repo activity queried directly 2026-08-15): https://api.github.com/

**Remote content delivery**
- Expo — EAS Update introduction: https://docs.expo.dev/eas-update/introduction/

**Exposure logging**
- PostHog — Exposures: https://posthog.com/docs/experiments/exposures
- PostHog — Adding experiment code: https://posthog.com/docs/experiments/adding-experiment-code
- PostHog — Experiments: common questions: https://posthog.com/docs/experiments/common-questions
- Statsig — Log custom exposure events (API reference): https://docs.statsig.com/api-reference/events/log-custom-exposure-events
- Statsig — Python server core SDK (exposure options): https://docs.statsig.com/server-core/python-core
- GrowthBook — React Native SDK / tracking callback: https://docs.growthbook.io/lib/react-native

**Low-traffic measurement**
- PostHog — Running time and sample size: https://posthog.com/docs/experiments/sample-size-running-time
- GrowthBook — Statistics overview (Bayesian priors, minimum data thresholds, sequential testing): https://docs.growthbook.io/statistics/overview
- Statsig — Holdouts: https://docs.statsig.com/experiments/holdouts-introduction
- Statsig — Difference-in-differences: https://www.statsig.com/perspectives/diff-in-diff-causal-inference
- Statsig — Regression discontinuity: testing around thresholds: https://www.statsig.com/perspectives/regression-discontinuity-thresholds
- Amplitude — Painted door testing: https://amplitude.com/explore/experiment/painted-door-testing
- ProdPad — Fake door testing: https://www.prodpad.com/glossary/fake-door-testing/

**Session replay on React Native**
- PostHog — React Native session replay installation: https://posthog.com/docs/session-replay/installation/react-native
- PostHog — React Native SDK: https://posthog.com/docs/libraries/react-native
- PostHog/posthog-react-native-session-replay (GitHub): https://github.com/PostHog/posthog-react-native-session-replay

**Content governance**
- Airship — In-app messaging explained: https://www.airship.com/explainer/in-app-messaging-explained/
- Courier — How to reduce notification fatigue: https://www.courier.com/blog/how-to-reduce-notification-fatigue-7-proven-product-strategies-for-saas
- Docsie — Content governance: https://www.docsie.io/blog/glossary/content-governance/
- US Department of Labor — Content governance: lightweight practices: https://www.dol.gov/agencies/eta/ui-modernization/use-plain-language/content-governance

**Pricing**
- PostHog pricing: https://posthog.com/pricing
- Statsig pricing: https://www.statsig.com/pricing

**FTF files inspected (read-only)**
- `mobile/src/state/useGuide.ts` — guided-tour engine (zustand), `guide_step_shown` fired at step activation
- `mobile/src/state/guideTargets.ts` — testID→ref registry, `measureInWindow` with 250 ms timeout and degrade-to-bubble-only
- `mobile/src/components/AnalystGuide.tsx` — single overlay host mounted in RootNav
- `mobile/src/components/analystScript.ts` — 114-line compiled-in content table
- `mobile/src/components/CoachMark.tsx` — inline dismissible callout primitive
- `mobile/src/hooks/useWhatsNew.ts` — version-keyed in-file `WHATS_NEW` map
- `mobile/src/state/useOnboardingState.ts` — persisted `ftf_onboarding_state_v1`
- `mobile/src/state/useInterruptCoordinator.ts` — single-slot prompt arbiter (`ux.prompt_arbiter`)
- `mobile/package.json`, `mobile/app.json` — Expo ~54.0.33, RN 0.81.5, `newArchEnabled: true`, no `expo-updates`
- `backend/analytics_taxonomy.py` — `coach_mark_*`, `guide_step_*`, `guide_tour_*`, `experiment_exposed`
- `config/features.json` — 187 flag keys incl. `onboarding.guided_avatar`, `ux.prompt_arbiter`, `ux.whats_new`
