# A5 — Mobile-Specific Onboarding Constraints and Conventions

**Date:** 2026-08-15
**Lens:** iOS/App Store platform rules, permission priming, sign-in friction, first-launch performance, and mobile onboarding benchmark data — for a feature-dense React Native/Expo consumer sports app.
**Scope note:** This is external research only. Nothing here inspects or judges FTF's current code; the final section is explicitly hypotheses.

---

## TL;DR

- **Apple's rules are the binding constraint, not the design advice.** Guideline 5.1.1(v) says verbatim: *"If your app doesn't include significant account-based features, let people use it without a login... Apps may not require users to enter personal information to function, except when directly relevant to the core functionality of the app or required by law."* A first screen that demands an account before showing anything is the single most-cited onboarding rejection pattern. ([Apple](https://developer.apple.com/app-store/review/guidelines/))
- **Account creation implies mandatory in-app account deletion** — required since June 30, 2022, must be easy to find, cannot be web-only or support-ticket-only, must delete user-generated content, and must call the Sign in with Apple REST revoke endpoint if SIWA is used. ([Apple](https://developer.apple.com/support/offering-account-deletion-in-your-app/))
- **Guideline 4.8 is narrower than most people think.** It triggers on *third-party or social login services used to authenticate the user's primary account*. Apps that use only their own account system, or that are "a client for a specific third-party service," are exempt. A public read-only username lookup is arguably neither an authentication service nor a login service. ([Apple](https://developer.apple.com/app-store/review/guidelines/))
- **Apple's HIG is unusually explicit that onboarding is optional, brief, post-launch, and preferably replaced by contextual tips** — "fast, fun, and optional," "teach through interactivity," "consider providing a collection of context-specific tips instead of a single onboarding flow." That guidance points feature-dense apps toward progressive disclosure, not a carousel. ([HIG](https://developer.apple.com/design/human-interface-guidelines/onboarding))
- **iOS push opt-in for sports sits in the mid-40s to high-40s percent.** Airship's 2025 report (Jan–Dec 2024, >9B users, thousands of apps) puts iOS opt-in at 74.1% / 49.4% / 27.1% for the 90th/50th/10th percentiles — flat YoY. Pushwoosh's 2025 table puts Sports at 46.66% iOS / 68.97% Android. ([Airship PDF](https://growth.airship.com/rs/313-QPJ-195/images/Airship-2025-Push-Notification-Benchmarks-EN.pdf?version=0), [Pushwoosh](https://www.pushwoosh.com/blog/increase-push-notifications-opt-in/))
- **Priming works, but the honest effect size is ~10–40%, not the "2–3×" vendors claim.** The best-sourced numbers: NHL's custom pre-permission screen → **+10% opt-in**; Airship in-app messages to already-opted-out users → **+14%**; apps running onboarding campaigns → opt-in **up to 40% above category average**; Hawaiian Airlines Scenes campaign → **+23% opt-ins**. The "2–3×" figure appears repeatedly with no cited study. ([Airship](https://www.airship.com/blog/increase-push-notification-opt-in-rates-with-these-two-tactics/), [Airship PDF](https://growth.airship.com/rs/313-QPJ-195/images/Airship-2025-Push-Notification-Benchmarks-EN.pdf?version=0), [Plotline](https://www.plotline.so/blog/how-to-improve-push-notification-opt-in-rates))
- **Provisional authorization (`allowProvisional`) is the underused iOS option** — no prompt at all, notifications land quietly in Notification Center with per-notification Keep/Turn-Off buttons. `expo-notifications` supports it directly. No credible published lift data exists, so it is an experiment, not a known win. ([Expo](https://docs.expo.dev/versions/latest/sdk/notifications/), [Use Your Loaf](https://useyourloaf.com/blog/provisional-authorization-of-user-notificatons/))
- **First launch has a hard ceiling and a soft target:** iOS watchdog kills an app that takes ~20s to launch; the widely-cited practical target is **~400ms to first frame**, which is roughly the length of the app-open animation. Expo on the New Architecture benchmarks at ~267ms iOS cold start — parity with bare RN — though that benchmark discloses no devices or app complexity. ([Apple](https://developer.apple.com/documentation/xcode/reducing-your-app-s-launch-time), [HN](https://news.ycombinator.com/item?id=34694347), [Applighter](https://www.applighter.com/blog/react-native-performance-benchmarks-expo-vs-bare-vs-flutter-vs-native-2026))

---

## 1. Apple's rules: what onboarding is legally allowed to be

These are hard constraints. Everything else in this document is advice.

### 1.1 Guideline 5.1.1(v) — Account Sign-In (the forced-registration rule)

Verbatim from the App Store Review Guidelines:

> If your app doesn't include significant account-based features, let people use it without a login. If your app supports account creation, you must also offer account deletion within the app. Apps may not require users to enter personal information to function, except when directly relevant to the core functionality of the app or required by law. If your core app functionality is not related to a specific social network... you must provide access without a login or via another mechanism. Pulling basic profile information, sharing to the social network, or inviting friends to use the app are not considered core app functionality. The app must also include a mechanism to revoke social network credentials and disable data access between the app and social network from within the app. An app may not store credentials or tokens to social networks off of the device and may only use such credentials or tokens to directly connect to the social network from the app itself while the app is in use.

Practitioner guidance is consistent about the remediation: a **guest or anonymous mode** that lets users reach core functionality without entering anything, with registration deferred to genuinely account-dependent features (sync, purchases, personalized state). One 2026 review-practice write-up names 5.1.1(v) as the highest-volume 5.1.1 sub-clause, followed by 5.1.1(i) (thin privacy policy) and 5.1.1(iii) (collecting data the app doesn't need) — while noting Apple publishes no sub-clause-level rejection rates ([PTKD](https://ptkd.com/journal/guideline-5-1-1-data-collection-and-storage-fix)).

The last sentence of the guideline is a separate and under-read constraint: **social-network credentials/tokens may not be stored off-device.** Apps that link a third-party platform account need to be able to describe exactly what they store server-side.

### 1.2 Account deletion (5.1.1(v), enforced since June 30, 2022)

Apple's support page is specific ([Apple](https://developer.apple.com/support/offering-account-deletion-in-your-app/)):

- Deletion must be **initiated in-app** and **easy to find** (typically account settings).
- Deactivation or "disable" is explicitly insufficient — the account record and associated personal data must go.
- If deletion completes on the web, the app must **link directly to the completion page**; phone/email/support flows are only permitted for highly-regulated industries per 5.1.1(ix).
- **Automatically generated accounts must also offer deletion** — relevant to any app that mints an anonymous/device identity at first launch.
- **User-generated content must be deleted** (posts, reviews, uploads).
- **Sign in with Apple requires calling the REST revoke-tokens endpoint** on deletion.
- Availability must be global; CCPA/GDPR-region-only deletion is not compliant.

### 1.3 Guideline 4.8 — Login Services

Verbatim: apps using "a third-party or social login service (such as Facebook Login, Google Sign-In, Log in with X, Sign In with LinkedIn, Login with Amazon, or WeChat Login) **to set up or authenticate the user's primary account**" must also offer an equivalent login service that (a) limits collection to name and email, (b) lets users keep their email private, and (c) doesn't collect in-app interactions for advertising without consent.

Exemptions, verbatim-adjacent: the app uses only the company's own account system; it's an alternative marketplace app; it's an education/enterprise app using an existing org account; it uses a government/industry citizen-ID system; or **"your app is a client for a specific third-party service and users are required to sign in to their mail, social media, or other third-party account directly to access their content."**

Practical reading: 4.8 keys on *authentication of the primary account* via a third-party identity provider. Apple removed the blanket "if you have any social login you must add SIWA" framing in early 2024, replacing it with the privacy-features test — though in practice Sign in with Apple is the easiest way to satisfy it ([9to5Mac](https://9to5mac.com/2024/01/27/sign-in-with-apple-rules-app-store/), [WorkOS](https://workos.com/blog/apple-app-store-authentication-sign-in-with-apple-2025)).

### 1.4 Guideline 2.1(a) — the demo-account trap

Verbatim: *"include demo account info (and turn on your back-end service!) if your app includes a login. If you are unable to provide a demo account due to legal or security obligations, you may include a built-in demo mode in lieu of a demo account with prior approval by Apple. Ensure the demo mode exhibits your app's full features and functionality."*

For apps whose identity is "an account on someone else's platform," this is a recurring operational hazard: the review credential must resolve to a fully-populated state at review time, including in the offseason or after upstream data changes.

### 1.5 Guideline 5.1.2 — ATT and pre-prompts

If the app tracks, the ATT prompt is mandatory before tracking, and collecting tracking data after "Ask App Not to Track" is grounds for removal. Apple's design guidance additionally constrains the *pre*-prompt: no incentives for allowing, no imitation of the system alert, no "alert images" or visual cues that steer the user toward Allow. Apple's privacy guidance goes further and states that a pre-alert screen should carry **a single button** (e.g. "Continue"/"Next") so it cannot function as a filter on who sees the real prompt ([HIG privacy](https://developer.apple.com/design/human-interface-guidelines/privacy), [Shopapper](https://shopapper.com/fix-apple-att-rejection-guideline-5-1-2-explained/), [Tracker.my.com](https://tracker.my.com/blog/how-to-optimize-your-ios-14-5-update-strategy-with-pre-permission-prompts?lang=en)).

This is a real asymmetry worth internalizing: **the industry-standard two-button soft-ask ("Not now" / "Enable") is normal and unpoliced for push, but is exactly what Apple warns against for ATT.**

### 1.6 Guideline 5.3 — contests and anything money-adjacent

5.3.1: sweepstakes/contests must be sponsored by the developer. 5.3.2: official rules must be in-app and state Apple is not a sponsor. 5.3.3: no IAP for real-money-gaming credit. 5.3.4: real-money gaming needs licensing, geo-restriction, and must be free. Fantasy apps that stay purely analytical avoid all of this; any leaderboard-with-prize or contest feature pulls onboarding into a licensing review ([Apple](https://developer.apple.com/app-store/review/guidelines/)).

---

## 2. Apple's design guidance (HIG): onboarding should barely exist

Apple's HIG onboarding page is short and directive ([HIG onboarding](https://developer.apple.com/design/human-interface-guidelines/onboarding)). Onboarding, **if necessary**, should be "fast, fun, and optional," and it **occurs after launching completes — it isn't part of the launch experience.** Apple tells you to **teach through interactivity** ("People tend to grasp and retain information better when they can actually perform the task they're learning about instead of just viewing instructional material"), to **prefer context-specific tips to a single flow** ("Consider providing a collection of context-specific tips instead of a single onboarding flow"), and to **keep it brief**. A separate tutorial should be skippable, not re-presented on later launches, but reachable from help/settings. Teach your app, not the OS. Postpone non-essential setup and customization, keep licensing out of the flow, delay rating and purchase prompts until people are engaged, and **request permissions within onboarding only when necessary for functionality**.

The launching page complements it ([HIG launching](https://developer.apple.com/design/human-interface-guidelines/launching)): launch instantly; the launch screen's "sole function is to enhance the perception of your experience as quick to launch"; design it **nearly identical to the first screen** and **avoid text, logos, or branding**; **restore the previous state** on relaunch. The privacy page sets the permission convention ([HIG privacy](https://developer.apple.com/design/human-interface-guidelines/privacy)): "Request permission only when your app clearly needs access to the data or resource," with active-voice purpose strings describing the concrete use ("The app records during the night to detect snoring sounds"), not the abstract category.

**Read together, Apple's position is that a feature-dense app should ship almost no upfront onboarding and instead disclose depth contextually** — a stronger claim than most vendor onboarding literature makes.

---

## 3. Push permission: benchmarks, priming, and the one-shot problem

### 3.1 The structural constraint

iOS shows the system notification prompt **once**. Deny is effectively terminal — recovery requires a trip to Settings, and one vendor estimates fewer than 5% of dismissed users ever do it (uncited; treat as folklore) ([Plotline](https://www.plotline.so/blog/how-to-improve-push-notification-opt-in-rates)). This is why the soft-ask exists: a pre-prompt that a user declines costs nothing, because the real prompt was never spent.

### 3.2 Benchmarks (best-sourced first)

**Airship 2025 Push Notification Benchmarks** — methodology disclosed: aggregate customer data Jan–Dec 2024, apps with ≥1,000 active users that sent ≥1,000 pushes in a month; **>9 billion app users, thousands of apps, 13 verticals**, monthly figures averaged over 12 months ([PDF](https://growth.airship.com/rs/313-QPJ-195/images/Airship-2025-Push-Notification-Benchmarks-EN.pdf?version=0)).

| Metric (opt-in) | 90th pct | Median | 10th pct |
|---|---|---|---|
| iOS 2023 | 73.9% | 49.1% | 27.3% |
| iOS 2024 | 74.1% | 49.4% | 27.1% |
| Android 2023 | 88.0% | 71.3% | 42.1% |
| Android 2024 | 79.7% | 59.5% | 37.1% |

Airship's takeaway: iOS held flat while Android fell sharply as Android 13's runtime notification permission propagated. **Sports & Recreation is one of the 13 verticals, but the per-vertical opt-in figures live in bar charts whose labels don't survive text extraction** — the report's own worked example uses Media at 60% / 44.5% / 29.8%.

Direct open rates in the same report: medians ~3.4% (Android) and ~3.1% (iOS), flat YoY; iOS high performers slipped 8.6% → 8.0%, which Airship reads as possible notification fatigue. Average monthly pushes per user rose on both platforms; the report notes media and sports apps send materially more than travel or food.

**Pushwoosh 2025 industry table** — no methodology disclosed ([Pushwoosh](https://www.pushwoosh.com/blog/increase-push-notifications-opt-in/)):

| Industry | iOS | Android |
|---|---|---|
| Media & Entertainment | 55.93% | 76.68% |
| News | 51.84% | 68.00% |
| **Sports** | **46.66%** | **68.97%** |
| Games / Action | 44.17% | 74.68% |
| Games / HyperCasual | 23.01% | 69.03% |

**A third, widely-recycled triad** — iOS 43.9%, Android 91.1%, blended 67.5% — appears verbatim across several vendor blogs with no traceable origin ([MobiLoud](https://www.mobiloud.com/blog/push-notification-opt-in-rate)). Its Android figure is implausibly high post-Android-13, which suggests stale underlying data.

**Convergent read for a US consumer sports app on iOS: expect roughly 45–50% opt-in from a competent single ask, with ~74% representing top-decile performance.**

### 3.3 Measured priming effects

Ordered by sourcing quality:

| Intervention | Effect | Source |
|---|---|---|
| NHL: custom screen explaining *why* before the system dialog | **+10% opt-in rate** | [Airship blog](https://www.airship.com/blog/increase-push-notification-opt-in-rates-with-these-two-tactics/) |
| In-app messages targeted at already-opted-out users | **+14% average increase in opt-in** | Airship 2025 PDF |
| Hawaiian Airlines: in-app "Scenes" campaign explaining day-of-travel alerts | **+23% push opt-ins** | Airship 2025 PDF |
| Apps running onboarding campaigns generally | opt-in **up to 40% above category average** | Airship 2025 PDF |
| TNT Sports: in-app messaging during onboarding + rich, segmented push | **+28% push open rate YoY**, **+25% longer live viewing sessions** for push vs. non-push audiences | Airship 2025 PDF |
| Rich push (image/preview) vs. plain | **+22% average lift in direct opens** | Airship 2025 PDF |
| Personalized/tailored messages | **+37% average increase in open rate** | Airship 2025 PDF |
| Pre-permission priming, generic vendor claim | "2–3×" | [Plotline](https://www.plotline.so/blog/how-to-improve-push-notification-opt-in-rates) — **no study cited** |

The TNT Sports case is the closest published analogue to a consumer sports app and is the one datapoint here that combines onboarding-time in-app messaging with a sports content cadence.

**Downstream value of the opt-in** (all Airship, all vendor-incentivized): opted-in customers make 13% more purchases on average (top performers +39%); identified users return at day 30 at 17% vs. 4% for anonymous users; users who receive any push in their first 90 days show ~3× higher retention; top apps see day-30 activation 56% above category average ([Airship activation](https://www.airship.com/blog/first-impressions-optimizing-the-activation-phase/)).

### 3.4 Provisional authorization — the option nobody uses

iOS 12+ offers `UNAuthorizationOptionProvisional`: **no permission prompt at all.** Notifications are delivered quietly — Notification Center only, no lock-screen alert, no sound — and each notification carries inline "Keep" / "Turn Off" affordances so the user decides after seeing real content rather than before ([Use Your Loaf](https://useyourloaf.com/blog/provisional-authorization-of-user-notificatons/), [OneSignal](https://documentation.onesignal.com/docs/en/ios-provisional-push-notifications)).

`expo-notifications` exposes this as `allowProvisional` in `requestPermissionsAsync()`, alongside `allowAlert`, `allowBadge`, `allowSound`, `allowCriticalAlerts`, `allowDisplayInCarPlay`, and `provideAppNotificationSettings` ([Expo](https://docs.expo.dev/versions/latest/sdk/notifications/)). That last option — `provideAppNotificationSettings` — surfaces an in-app notification-settings button inside iOS Settings, which pairs with Airship's second tactic: let users manage push preferences inside the app rather than only in system settings.

**I found no credible published measurement of provisional-vs-explicit opt-in outcomes.** The trade is structural, not empirical: provisional trades alert prominence for a guaranteed non-zero delivery channel and defers the real decision to a moment of demonstrated value.

---

## 4. ATT: probably not your problem, and if it is, don't stack it

ATT applies only if the app tracks users across apps/websites owned by other companies — typically via ad SDKs or third-party attribution.

The benchmark numbers are wildly divergent because the **denominators differ**:

- **AppsFlyer (April 2025, ATT's fourth anniversary):** "50% of users now consent to tracking," a ~10-point rise since rollout; France ~51%, Germany 47%. No methodology disclosed. This is consent *among users shown the prompt* ([AppsFlyer](https://www.appsflyer.com/company/newsroom/pr/post-att-growth/)).
- **Singular, Q2 2024 (via Purchasely):** global *immediate* opt-in **13.85%**; gaming 18.58%; non-gaming 11.92%; weather 38%; music games 35%; casino/trivia under 10%. This counts across the whole install base including users never prompted ([Purchasely](https://www.purchasely.com/blog/att-opt-in-rates-in-2025-and-how-to-increase-them), [Singular](https://www.singular.net/quarterly-report-2024-q2/)).
- Secondary reporting cites Adjust at ~38% global iOS ATT opt-in in Q1 2026, up from ~35% a year earlier.

**These are not in conflict; they are different metrics.** Any internal target must state which denominator it uses.

The practical onboarding rule: ATT and push are two separate permission asks with two separate value propositions, and Apple constrains ATT pre-prompts far more tightly (§1.5). Stacking multiple permission dialogs in the first session is the pattern Airship names first among opt-in mistakes — "Don't Jump the Gun with a Generic Prompt."

---

## 5. Sign-in friction on mobile

### 5.1 The platform-linking spectrum

Fantasy apps that read a user's roster pick one of three patterns. **OAuth against the platform** (Yahoo-style) is real authentication with a real consent screen and token storage — highest friction, highest trust, and squarely inside 4.8's orbit if it establishes the primary account. **Public read-only lookup** (Sleeper-style) is the lowest-friction option: Sleeper's public endpoints are documented as read-only and unauthenticated, a user object is fetched by username *or* user_id, and Sleeper's own docs warn that **usernames change over time, so `user_id` is what you persist** ([Sleeper docs](https://docs.sleeper.com/), [Zuplo](https://zuplo.com/learning-center/sleeper-api)). But "sign-in" by public username is identity *assertion*, not *authentication* — anyone can type anyone's handle. **Manual entry / no link** is zero friction and zero personalization.

The friction ordering is unambiguous; the security and reviewer-narrative implications are not. **No published measurement compares conversion across these patterns for fantasy apps.**

### 5.2 Sign in with Apple mechanics that bite later

If SIWA is added it must use `ASWebAuthenticationSession` (system browser, not a WebView), should use OAuth 2.0 + PKCE with no client secret in the binary, and **account deletion must call the REST revoke-tokens endpoint** ([WorkOS](https://workos.com/blog/apple-app-store-authentication-sign-in-with-apple-2025), [Apple](https://developer.apple.com/support/offering-account-deletion-in-your-app/)). Hide My Email means the address you receive may be a relay — plan lifecycle email and support identity around that.

### 5.3 Evidence from the fantasy category (qualitative only)

A UX teardown of ESPN's Fantasy app names the friction of **signing up twice** — once for a fantasy account, then again to create or join a league — and generalizes the failure modes as signup length, a confusing league-join step, unexplained terminology, and forcing experienced users through introductory steps ([Usability Geek](https://usabilitygeek.com/ux-case-study-espns-fantasy-app/), [SportsFirst](https://www.sportsfirst.net/post/best-ui-ux-practices-fantasy-football-app-development)). Designer opinion, not measured data — but "experienced users must be able to move fast" is the point that recurs most across dynasty-adjacent commentary.

---

## 6. First-launch performance expectations

- **Hard ceiling:** iOS watchdog terminates an app that fails to launch in roughly 20 seconds ([Apple forums](https://developer.apple.com/forums/thread/715445)).
- **Practical target:** ~400ms to first frame — commonly justified as roughly the duration of the app-open animation, so anything longer reads as a stall ([Apple](https://developer.apple.com/documentation/xcode/reducing-your-app-s-launch-time), [HN](https://news.ycombinator.com/item?id=34694347), [Use Your Loaf](https://useyourloaf.com/blog/testing-app-launch-time/)).
- **Production measurement:** MetricKit's `MXAppLaunchMetric` histograms (`TimeToFirstDrawMetric`, `ApplicationResumeTimeMetric`) give per-day real-device distributions plus hang/crash diagnostics — no third-party SDK required.
- **Rejection exposure:** Guideline 4.2 (Minimum Functionality) is cited by practitioners for slow loading and frozen screens; performance is reported as the largest 2024 rejection bucket (>1.23M), though Apple publishes no such breakdown and the figure has no primary attribution ([Twinr](https://twinr.dev/blogs/apple-app-store-rejection-reasons-2025/)).
- **The HIG constraint that matters most for onboarding:** a branded splash that blocks on a network fetch violates both the launch-screen rule and the perceived-speed goal.

---

## 7. React Native / Expo specifics

**Cold start.** A 2026 benchmark summary reports Expo on the New Architecture at **~267ms iOS / ~341ms Android**, identical to bare React Native (both use Fabric + Hermes via EAS Build), against native Android at ~248ms ([Applighter](https://www.applighter.com/blog/react-native-performance-benchmarks-expo-vs-bare-vs-flutter-vs-native-2026)). **No devices, app complexity, or RN version are disclosed** — directional only. Hermes-attributed cold-start improvements of 30–50% circulate widely with similar sourcing weakness. RN 0.82 (Oct 2025) introduced experimental Hermes V1; Static Hermes moves compilation to build time ([RN Journal](https://medium.com/react-native-journal/hermes-v1-in-react-native-0-82-unlocking-faster-startup-times-bfd0cf1b107c)).

**Push notifications got harder in Expo SDK 53+.** Expo Go no longer supports remote push; testing requires a **development build** (`expo-dev-client`). A **paid Apple Developer account** is needed for the APNs key, and the device must be registered before the first build. Local notifications still work in Expo Go. Testing runs on a physical device or an iOS Simulator on Xcode 14+/macOS 13+/iOS 16+ ([Expo setup](https://docs.expo.dev/push-notifications/push-notifications-setup/), [FAQ](https://docs.expo.dev/push-notifications/faq/)). **Consequence: any permission-priming flow cannot be validated in Expo Go.**

**EAS Update is the sharpest onboarding lever an Expo app has.** Copy, screen order, priming timing, and gating ship over-the-air with no review cycle, turning onboarding into a weekly-iterable surface — bounded by the rule that OTA updates must not change the app's primary purpose or add unreviewed features. And `expo-notifications` exposes both sophisticated iOS patterns (§3.4) without dropping to native.

---

## 8. Onboarding benchmark data

**Retention, cross-industry 2025–2026:** roughly **25–26% day-1, 11–13% day-7, 5–7% day-30**, aggregated from AppsFlyer and Adjust by third parties. AppsFlyer's own day-1 average is cited at 24.33%; Adjust's day-7 at ~12%. More than 70% of users are gone within 30 days ([UXCam](https://uxcam.com/blog/mobile-app-retention-benchmarks/), [EngageLab](https://www.engagelab.com/blog/increase-app-retention)).

**By category (strong performers, UXCam citing AppsFlyer/Adjust/data.ai):** Social 50–60% / 25–30% / 15–20% (D1/D7/D30); Streaming & media 45–55% / 20–28% / 10–15%; Gaming 40–50% / 12–18% / 5–8%; Productivity 40–50% / 22–28% / 12–18%; Fintech 35–45% / 18–25% / 10–15%; Health & fitness 35–45% / 15–22% / 8–12%.

**Sports is absent from every category table I could reach.** The closest proxy is a table reporting "onboarding rate" by category — Sports at **26% day-1 / 9% day-30**, versus News & Magazines 24%/13%, Finance 26%/11%, Shopping 23%/9%, with a global day-30 figure of 8.4% ([Digia](https://www.digia.tech/post/app-onboarding-rates-statistics/)). The metric definition is not stated clearly and the numbers track retention curves closely enough that I suspect relabeling. Directional at best.

**Flow-shape data**, all weakly sourced: completion reportedly drops ~**15% for every onboarding screen beyond five** (attributed to Appcues; primary study not locatable), with typical flows running 3–5 screens covering value prop, personalization, permissions, and first meaningful action ([Lowcode](https://www.lowcode.agency/blog/mobile-onboarding-best-practices)). Simple apps are said to reach 70–80% completion versus 50–65% for complex ones. "76% of abandoners leave within the first few seconds" and "segmentation lifts completion ~25%" both circulate unsourced. Duolingo's motivation question is the canonical personalization example, but every write-up I found is a designer's teardown and **none report measured lift** ([Appcues](https://goodux.appcues.com/blog/duolingo-user-onboarding)).

**The genuinely well-sourced flow-shape claim** comes from Apple, not from growth vendors: prefer context-specific tips to a single flow, keep it brief, and make it skippable.

---

## Evidence quality notes

**Tier A — primary, authoritative, directly checkable.** Apple's App Store Review Guidelines (quoted verbatim), Apple's account-deletion support page, and Apple's HIG. These are rules, not findings. One caveat: the HIG pages themselves are JS-rendered and could not be fetched directly; the HIG text here came from a mirrored copy in a public repository plus a search-engine extraction of the same pages, and the two agreed closely. Anyone relying on an exact HIG sentence should re-read it on developer.apple.com.

**Tier B — vendor research with disclosed methodology.** Airship's 2025 benchmarks report is the strongest quantitative source in this document: stated window (Jan–Dec 2024), stated population (>9B users, thousands of apps, ≥1,000 MAU + ≥1,000 sends/month), stated statistic (monthly figures averaged over 12 months), percentile framing rather than a single average. Its limits: Airship's customer base skews to enterprise brands with marketing teams, so opt-in medians are probably *above* the true app-store-wide median; and its per-vertical opt-in numbers are locked in chart graphics whose labels don't survive text extraction, so I could not retrieve the Sports & Recreation opt-in figure specifically. Its case studies (NHL, Hawaiian, TNT, ASDA) are customer wins with obvious selection bias — real measurements of real campaigns, but the losses aren't published.

**Tier C — vendor numbers without methodology.** Pushwoosh's industry opt-in table, AppsFlyer's ATT press release, Singular's quarterly figures as relayed by Purchasely. Usable as order-of-magnitude anchors; not usable for target-setting without knowing the denominator.

**Tier D — aggregator recycling.** The iOS 43.9% / Android 91.1% / blended 67.5% triad propagates across many blogs with no origin. The "2–3× from pre-permission priming" claim is asserted by at least two vendors with zero citation and is contradicted by the only well-sourced priming measurements in this document (+10%, +14%, +23%, "up to +40% above category average"). **I would not plan against 2–3×.** The Appcues "15% per screen" heuristic and the "76% abandon in seconds" statistic are in the same category.

**Specific conflicts and unresolved items:**

1. **ATT rates differ by ~3.6× across sources** (50% vs 13.85%) purely because of denominators — consent-among-prompted vs opt-in-across-installs. Any ATT target must name its denominator.
2. **iOS push opt-in ranges 43.9% to 54% across sources.** Airship's 49.4% median has the best methodology behind it.
3. **A claim that iOS 18.2's revised notification prompts lifted iOS opt-in to 54% — "the first measurable iOS opt-in growth in three years" — surfaced in a search-engine synthesis attributed to Airship's 2026 report. I could not verify it: the 2026 report is gated behind a form. Treat as unverified.**
4. **No published measurement of provisional authorization's effect on eventual opt-in or engagement was found**, despite it being available since iOS 12.
5. **No sports- or fantasy-specific onboarding funnel data exists in public sources.** The TNT Sports case study is the single sports datapoint with numbers attached, and it measures push engagement, not onboarding completion.
6. **The React Native/Expo cold-start numbers have no disclosed methodology.** They are plausible and consistent with the New Architecture narrative, but they are not measurements you should quote to a stakeholder.
7. Search budget for this session was exhausted at 200 queries; several intended verifications (Airship 2026 gated report, AppsFlyer's sports vertical, Adjust's 2026 vertical splits) remain open.

---

## Implications for FTF (hypotheses only — none of this is a recommendation to ship)

1. **H1 — The 5.1.1(v) exposure is real and specific.** FTF has features that are plainly *not* account-based: the manual trade calculator, player rankings, and tier ladders. Apple's text says apps "may not require users to enter personal information to function, except when directly relevant to the core functionality." *Hypothesis:* a first-run that requires a Sleeper username before any of those are reachable is the exact shape reviewers flag, and a guest lane that opens on the calculator or tiers would both de-risk review and shorten time-to-value.

2. **H2 — Sleeper username entry probably doesn't trigger 4.8, but the reasoning should be written down before review.** A public, unauthenticated, read-only username lookup is not "a third-party or social login service used to authenticate the user's primary account," and 4.8's client-for-a-specific-third-party-service exemption is nearby. *Hypothesis:* the risk isn't the rule, it's the reviewer's first impression that a screen labeled "Sign in with Sleeper" is a social login. Labeling it as *connecting a league* rather than *signing in* may matter more to review outcome than to users.

3. **H3 — If FTF mints account keys, account deletion is already mandatory.** Apple's page explicitly covers *automatically generated accounts* and requires in-app, easy-to-find, global, content-deleting removal. *Hypothesis:* this is a launch blocker independent of onboarding design, and it should be verified before any App Store submission rather than discovered in review.

4. **H4 — The 2.1(a) demo credential is a recurring seasonal hazard.** A review account whose value depends on a live Sleeper league with a populated dynasty roster can degrade between submissions. *Hypothesis:* a stable seeded demo identity (or an approved built-in demo mode) is cheaper than a rejection cycle each offseason.

5. **H5 — Expect ~45–50% iOS push opt-in from a single competent ask; ~74% is top-decile.** Sports sits slightly below Media/News in every table. *Hypothesis:* FTF's notification inbox has an unusually concrete value story (a trade offer arrived; your player's tier moved; someone accepted your board) — concreteness is precisely what produced the +10% NHL result. A priming screen that names the actual notification types beats a generic "stay updated."

6. **H6 — Provisional authorization deserves a real experiment, not a default.** Most of FTF's nine notification types are informational rather than time-critical. *Hypothesis:* `allowProvisional` converts a binary permission gamble into a trial where the user decides after seeing a real trade alert — at the cost of no lock-screen presence. Because no published data exists, this can only be settled by measuring FTF's own cohorts.

7. **H7 — Trigger the ask at a moment that generates a notification.** Airship's data says onboarding campaigns lift opt-in up to 40% above category average, and in-app messages recover 14% of already-opted-out users. *Hypothesis:* asking immediately after a user's first board save or first sent trade — when a notification is genuinely imminent — will outperform asking during a first-run carousel, and the opted-out population is recoverable later rather than lost.

8. **H8 — ATT should be kept out of onboarding unless and until ads ship.** If AdMob or attribution SDKs land, ATT becomes a second permission with far tighter pre-prompt rules (single button, no incentives, no prompt mimicry). *Hypothesis:* stacking ATT behind push in one session depresses both.

9. **H9 — Apple's guidance favors contextual tips over a carousel, which fits a feature-dense app better than the growth-blog consensus does.** With Elo voting, tiers, a finder, a calculator, boards, send-in-platform, an inbox, and feedback, no upfront flow can cover the surface. *Hypothesis:* a very short first-run (value prop → league connect or skip → one interactive action) plus per-feature first-use tips will outperform a 5-screen tour — and it is what Apple's own reviewers-adjacent guidance describes.

10. **H10 — The Elo matchup vote is an unusually good "teach through interactivity" candidate.** Apple's HIG explicitly favors letting people perform the task over watching an explanation. *Hypothesis:* a single 3-player matchup vote as the first interaction both teaches the ranking mechanic and produces data, without requiring any account.

11. **H11 — First frame must not block on network.** HIG requires the launch screen to be a static near-replica of the first screen with no branding, and onboarding to begin only after launch completes. *Hypothesis:* if rankings/tiers require a fetch before the first screen renders, the perceived launch cost is paid by every user on every cold start; caching last-known tiers would decouple first frame from the network.

12. **H12 — Expo changes the economics in both directions.** EAS Update makes onboarding copy, ask timing, and step order iterable over-the-air on a weekly cadence — "instrument and tune" rather than "get it right once." But from SDK 53 onward push QA cannot happen in Expo Go, so any priming work needs a dev-build/TestFlight loop budgeted in, and a Maestro flow can assert the pre-prompt but never the system dialog.

13. **H13 — Store `user_id`, not the Sleeper username.** Sleeper's own docs warn usernames change. *Hypothesis:* anything durable keyed on username silently breaks when a user renames on Sleeper — and it presents to the user as broken onboarding, not a broken lookup.

---

## Sources

**Apple (primary)**
- App Store Review Guidelines — https://developer.apple.com/app-store/review/guidelines/
- Offering account deletion in your app — https://developer.apple.com/support/offering-account-deletion-in-your-app/
- HIG: Onboarding — https://developer.apple.com/design/human-interface-guidelines/onboarding
- HIG: Launching — https://developer.apple.com/design/human-interface-guidelines/launching
- HIG: Privacy — https://developer.apple.com/design/human-interface-guidelines/privacy
- Reducing your app's launch time — https://developer.apple.com/documentation/xcode/reducing-your-app-s-launch-time
- Optimizing App Launch (WWDC19-423) — https://developer.apple.com/videos/play/wwdc2019/423/
- Account deletion requirement start date — https://developer.apple.com/news/?id=mdkbobfo
- Watchdog termination discussion — https://developer.apple.com/forums/thread/715445
- 5.1.1(v) developer forum threads — https://developer.apple.com/forums/thread/692065 · https://developer.apple.com/forums/thread/724336

**Push notification benchmarks and priming**
- Airship, Push Notification Benchmarks for 2025 (PDF, methodology disclosed) — https://growth.airship.com/rs/313-QPJ-195/images/Airship-2025-Push-Notification-Benchmarks-EN.pdf?version=0
- Airship, 2026 benchmarks landing page (gated) — https://www.airship.com/resources/mobile-app-push-notification-benchmarks-2026/
- Airship, Two Tactics to Increase Opt-In Rates (NHL +10%) — https://www.airship.com/blog/increase-push-notification-opt-in-rates-with-these-two-tactics/
- Airship, First Impressions: Optimizing the Activation Phase — https://www.airship.com/blog/first-impressions-optimizing-the-activation-phase/
- Pushwoosh, opt-in benchmarks by industry — https://www.pushwoosh.com/blog/increase-push-notifications-opt-in/
- MobiLoud, average push opt-in rate — https://www.mobiloud.com/blog/push-notification-opt-in-rate
- Plotline, improving opt-in rates (unsourced 2–3× claim) — https://www.plotline.so/blog/how-to-improve-push-notification-opt-in-rates
- Use Your Loaf, Provisional Authorization of User Notifications — https://useyourloaf.com/blog/provisional-authorization-of-user-notificatons/
- OneSignal, iOS provisional push notifications — https://documentation.onesignal.com/docs/en/ios-provisional-push-notifications

**ATT**
- AppsFlyer, post-ATT growth press release (Apr 2025) — https://www.appsflyer.com/company/newsroom/pr/post-att-growth/
- AppsFlyer, boosting ATT opt-in with pre-prompts (qualitative) — https://www.appsflyer.com/blog/tips-strategy/apps-boost-att-opt-in/
- Purchasely, ATT opt-in rates 2025 (relaying Singular Q2 2024) — https://www.purchasely.com/blog/att-opt-in-rates-in-2025-and-how-to-increase-them
- Singular quarterly report Q2 2024 — https://www.singular.net/quarterly-report-2024-q2/
- Business of Apps, ATT opt-in rates — https://www.businessofapps.com/data/att-opt-in-rates/
- Shopapper, fixing 5.1.2 ATT rejections — https://shopapper.com/fix-apple-att-rejection-guideline-5-1-2-explained/
- Tracker.my.com, do's and don'ts of ATT pre-prompts — https://tracker.my.com/blog/how-to-optimize-your-ios-14-5-update-strategy-with-pre-permission-prompts?lang=en

**Sign-in and review practice**
- WorkOS, App Store authentication / Sign in with Apple in 2025 — https://workos.com/blog/apple-app-store-authentication-sign-in-with-apple-2025
- 9to5Mac, Apple relaxes the Sign in with Apple requirement — https://9to5mac.com/2024/01/27/sign-in-with-apple-rules-app-store/
- PTKD, fixing a Guideline 5.1.1 rejection — https://ptkd.com/journal/guideline-5-1-1-data-collection-and-storage-fix
- Twinr, App Store rejection reasons 2025 — https://twinr.dev/blogs/apple-app-store-rejection-reasons-2025/

**Retention and onboarding benchmarks**
- UXCam, retention benchmarks by industry — https://uxcam.com/blog/mobile-app-retention-benchmarks/
- EngageLab, app retention benchmarks 2026 — https://www.engagelab.com/blog/increase-app-retention
- Digia, app onboarding rate statistics (incl. Sports row) — https://www.digia.tech/post/app-onboarding-rates-statistics/
- Lowcode Agency, mobile onboarding best practices (Appcues screen-count heuristic) — https://www.lowcode.agency/blog/mobile-onboarding-best-practices
- Appcues, Duolingo onboarding teardown — https://goodux.appcues.com/blog/duolingo-user-onboarding
- Adjust, Mobile app trends 2026 — https://www.adjust.com/resources/ebooks/mobile-app-trends-2026/

**React Native / Expo**
- Expo, push notifications setup — https://docs.expo.dev/push-notifications/push-notifications-setup/
- Expo, push notifications troubleshooting and FAQ — https://docs.expo.dev/push-notifications/faq/
- Expo, expo-notifications SDK reference (allowProvisional) — https://docs.expo.dev/versions/latest/sdk/notifications/
- Applighter, RN benchmarks: Expo vs bare vs Flutter vs native (2026) — https://www.applighter.com/blog/react-native-performance-benchmarks-expo-vs-bare-vs-flutter-vs-native-2026
- React Native Journal, Hermes V1 in RN 0.82 — https://medium.com/react-native-journal/hermes-v1-in-react-native-0-82-unlocking-faster-startup-times-bfd0cf1b107c

**Sleeper, fantasy-category UX, and launch performance**
- Sleeper API documentation — https://docs.sleeper.com/
- Zuplo, comprehensive guide to the Sleeper API — https://zuplo.com/learning-center/sleeper-api
- Usability Geek, UX case study: ESPN's Fantasy app — https://usabilitygeek.com/ux-case-study-espns-fantasy-app/
- SportsFirst, UI/UX practices for fantasy football apps — https://www.sportsfirst.net/post/best-ui-ux-practices-fantasy-football-app-development
- Use Your Loaf, testing app launch time — https://useyourloaf.com/blog/testing-app-launch-time/
- Hacker News, discussion of Apple's ~400ms launch target — https://news.ycombinator.com/item?id=34694347
