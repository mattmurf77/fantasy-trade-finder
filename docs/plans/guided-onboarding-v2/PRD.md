# PRD: Guided Onboarding v2 — The Analyst, Act II

> **Status:** FINAL (2026-08-15) — dual-agent validated through 7 rounds: base PRD signed off by both lenses (round 4); operator amendments O-1…O-5 reviewed rounds 5–7. The round-7 verifier's three remaining consistency fixes were applied verbatim as prescribed (no new design decisions) and close the loop; they are flagged in [RECONCILIATION.md](RECONCILIATION.md) as prescription-applied, not re-reviewed. Build starts at Phase 0 behind full gates (D7).
>
> **Operator decisions (2026-08-15), binding:**
> - **O-1 (seed #1 reshaped):** teach **find → like → the "Awaiting them" section → optional proactive send**. Showing the user a *match* is a **separate walkthrough** (N3 stays its own beat).
> - **O-2:** outlook/Trade DNA beat (N2) — aligned as specced.
> - **O-3:** rankings calibration framing (N1 + two-minute ask) — aligned as specced (resolves OQ-1: calibration framing confirmed).
> - **O-4:** league-standing beat (N5) — aligned as specced.
> - **O-5:** empty-deck beat (N4) aligned, **plus a varied ranking-method ladder**: push simple rankings through different features by effort — **Trios lightest/quickest; Tiers and Quick Set heaviest/longest** (§5.3 ladder policy).
> - **O-6 (2026-08-15, mid-build):** the **import question is the first thing The Analyst asks when the ranking process launches** — "do you have or pay for rankings to upload?" Yes → CSV upload / DLF & Dynasty Nerds linking (the premium-import intake chooser). No → **Trios** as the first rank feature. Built as `N8` (§5.3-A below). Supersedes "session 1 keeps Quick Set primary."
> - **O-7 (2026-08-15, mid-build):** **first-visit fallback triggers on every taught page** — each surface's walkthrough fires at its planned trigger OR the user's first visit to that page, whichever comes first (nobody lands lost; nobody is taught after already using the feature). Built as: trigger floors on all beats, `N5` pulled into Phase 1, new `N9` Matches first-visit beat (§5.3-A).
>
> ## §5.3-A — O-6/O-7 additions (built in Phase 1; delta-grounded on post-Phase-A main)
>
> **`N8` — The import question** *(O-6; the guided gateway to the ranking process)*
> - **Trigger:** guided entry to the ranking process — `s3.2`'s CTA now routes to **RankHome (guided param)** instead of directly to QuickSetTiers — OR first `RankHome` focus (O-7 floor). Once per device.
> - **Surface:** bubble on `RankHomeScreen`, cta class, non-deictic.
> - **Copy (drafting target, 14):** "Do you pay for rankings — or keep your own? Upload them, I'll use yours." · Primary CTA `Upload →` opens RankHome's **existing import entry** (today `RankImportSheet`; when `feat/premium-import-v1` lands, that same entry is the `ImportRankingsSheet` intake chooser whose Dynasty Nerds / DLF rows appear per their dark `ranks.source.*` flags — **loose coupling: N8 navigates to the entry point and never names a premium source in copy while those flags are dark**). Ghost CTA `No — start simple` navigates nested to `Trios` (guided arm), per O-6.
> - **Payoff wiring (new; generalizes the QuickSet return handoff):** completing ≥1 guided trio, or completing an import, sets the same forced-regen return handoff QuickSet uses, so the `s5.x` reveal fires method-agnostically ("your numbers" copy already is). Import → reveal is the strongest payoff path in the tour.
> - **Retirement:** `once`; `invalidateOn:` any board receipt (import completed; `quicksetCompletedPositions` non-empty; trio receipt).
> - **Ladder interaction:** O-6 makes Trios the guided default from session 1; the §5.3 ladder governs *subsequent* nudges unchanged; `s4.1` (QuickSet coaching) now fires only when the user actually lands in QuickSet.
> - **Trio receipt pulled into Phase 1:** `trio_session_started` already has a client emitter (`RankScreen.tsx:92`) — register it in the taxonomy and persist a local trio receipt for eligibility.
>
> **`N9` — Matches first visit** *(O-7 floor for MatchesScreen)*
> - **Trigger:** first `MatchesScreen` focus — unless arrival is via `N6.1`'s chain (that arrival already teaches; `N9` suppresses and is consumed).
> - **Surface:** bubble, tap class, **non-deictic** (per-card spotlights stay Phase 2 with `N6.2`/`N3`).
> - **Copy (12):** "Mutual matches land here. Awaiting them holds your likes — send either anytime."
> - **Retirement:** `once`. **Funnel:** `awaiting_segment_viewed` on segment tap.
>
> **O-7 trigger floors in this build:** `N5` moves to Phase 1 — trigger = **first League-tab focus** AND its content gates (≥3 ranked members, `league.pos_candidates` on, median present; gates still fail closed — a first visit that fails shows nothing, and the beat stays armed for a later visit that passes). Trades beats (N1/N2/N4) already have Act I as their floor. Rankings' floor is `N8` itself.
>
> **Date:** 2026-08-15
> **Amends:** the shipped guide engine (`mobile/src/state/useGuide.ts`, `mobile/src/state/guideTargets.ts`, `mobile/src/components/AnalystGuide.tsx`, `mobile/src/components/analystScript.ts`) and Script v1 (`docs/plans/onboarding-conversion/guided-avatar-script.md`)
> **Research basis:** `docs/research/onboarding/SYNTHESIS.md` + round-2 files `r2-1b`, `r2-2a`, `r2-2b`, `r2-3a`
> Claims are labelled **code-verified** (file:line), **measured** (cited artifact), or **assumed**.

---

## 1. Summary

FTF already owns a working guided-tour engine — a zustand step store, a `testID`→ref spotlight registry with a defensive measurement contract, a single RootNav overlay, an interrupt arbiter, and a 19-entry compiled-in script for The Analyst. What it does not own is a tour that (a) actually runs, (b) teaches the non-discoverable mechanics that make FTF worth keeping, or (c) knows when to stop.

**Guided Onboarding v2 amends the existing system rather than replacing it**, in three moves:

1. **Phase 0 — make it real and honest.** Decouple the tour from the sibling onboarding flags that render most script entries unreachable; add a TipKit-shaped declarative eligibility layer (trigger, display cap, behavioral retirement, degrade behavior, adoption event — required fields, lint-enforced); give the guide a real, named place in the interrupt arbitration; ship the event inventory (taxonomy rows + emitters + read-back) that all measurement depends on; fix the engine defects that corrupt measurement; trim every v1 line to its copy-budget class with the target copy in this document.
2. **Phase 1 — four beats on TradesScreen** covering the deck's non-discoverable mechanics: the rankings calibration reframe (`N1`), the outlook/Trade DNA re-aim at the failure boundary (`N2`, two-form), the empty-deck pin path (`N4`, shipped as an extension of the existing deck-summary card), and the first-like router (`N6.1`: like → "Awaiting them" → optional proactive send, per O-1).
3. **Phase 2 — cross-screen beats**: the awaiting-segment send spotlight (`N6.2`), the **separate** mutual-match walkthrough (`N3`, platform-resolved, per O-1), league standing (`N5`, content-gated), and the Trios rung of the ranking ladder (`N7`, per O-5). A stronger rankings-progress beat is gated on open-access Phase B shipping `grade_count`.

Every new beat teaches by doing at a declared boundary or failure (the only two trigger families with real evidence), spends one line and one action within a per-class word cap, retires on a behavioral condition, and carries the owning feature flags of the surface it teaches as trigger preconditions — a beat must never outlive the feature it points at.

---

## 2. Problem & Context

### 2.1 The tour is effectively dark in production — and one live beat points at nothing

`config/features.json` has `onboarding.v2 = true` and `onboarding.guided_avatar = true`. That reads as "the tour is live." It is not. Every substantive step is gated a second time by a sibling flag that is **off**, and one step that does fire cannot draw its pointer (all code-verified):

| Step group | Second gate / defect | State | Consequence |
|---|---|---|---|
| S0.x (SignIn) | `onboarding.landing` (`SignInScreen.tsx:152`) | false | The Analyst never introduces himself |
| S2.x (deck teaching) | `firstRun` ← `onboarding.trades_first` (`TradesScreen.tsx:334-337`) | false | The entire deck act is dead |
| S3.x (Quick Set pitch) | `onboarding.quickset_prompt` | false | Never fires |
| S5.x (the reveal) | reachable only via S3 → S4 handoff | — | Unreachable in practice |
| S6.2 (Apple save) | `onboarding.apple_save_moment` | false | Dead |
| S8.1 (sign-off) | requires `guideSeen['s2.2'] && guideSeen['s6.1']` (`TradesScreen.tsx:2588-2594`) | — | Unreachable because S2.2 is dead. **v2 note:** `s6.1` is replaced by `N6.1`, so the second conjunct becomes `guideSeen['n6.1'] \|\| guideSeen['s6.1']` (the OR keeps v1 upgraders eligible) — asserted in `guide-no-false-signoff@release.yaml` |
| **S7.1 (trios ramp)** | request ungated (`TradesScreen.tsx:2775-2776`) but its target `trades.trio-entry` mounts only under `onboarding.rank_routing` (**false**, `features.json:81`) inside the non-summary exhausted branch (`TradesScreen.tsx:5096-5117`), which the live `deck.replenishment` summary card displaces anyway | — | **Fires today pointing at nothing** — the deictic-degrade incoherence FR-E6 exists to catch, already shipping |

The P0-8/P0-9 audit measured the gating directly: *sixteen of the twenty script entries are unreachable under release flags* (`docs/plans/audit-p0-remediation/prd-p0-8-9.md` §1). The real shipped tour today is: maybe `s1.1` (multi-league users), maybe `s6.1`, and a pointer-less `s7.1` bubble. No core-loop teaching, no sign-off.

**This reframes the work: v2's first job is not new content, it is making content reachable and coherent under one gate.** And "reachable" is defined properly in G-1: a beat is reachable only if its trigger can fire **and** its target mounts (or it has a defined degrade contract). Adding beats to a tour that fails both tests spends the scarcest resources (binary releases, one interrupt slot) on the wrong constraint.

### 2.2 The teaching that exists stops one step short of the payoff

Script v1 ends the trade story at *"First target logged. If they accept, you'll hear it from me first"* (`s6.1`). It never shows where the like actually went. Per **O-1**, the loop is taught in two separate walkthroughs: **(a)** first like → the **"Awaiting them"** segment (`MatchesScreen`, segment `awaiting` — one-sided likes not yet matured, `mobile/src/api/trades.ts:554-559`, code-verified), where the awaiting card already carries the platform-routed send button (`TradeCard.tsx:666`, `surface="awaiting"`) so the user can **send proactively without waiting for a match**; and **(b)** a separate walkthrough when a *mutual match* first appears. The honesty constraint stands: **there is no in-app "accept a trade" on mobile** (`mobile/src/api/trades.ts:484-487`) — the counterparty accepts in their platform, and the copy says so.

### 2.3 Allocation rule: teach by discoverability, not by tenure

The governing experiment (Andersen et al., CHI 2012, n=45,318, `r2-2a` §6.1): tutorials paid **only** in the most complex product (+75% progression); identical content in-context added +40%; and an opt-in help affordance was measurably **harmful** in the simpler games. FTF is in the complex band, so guided doing pays — allocated per feature by discoverability:

- **Self-evident, teach nothing:** the swipe gesture beyond its one existing beat, the trade calculator, free agents, the rankings-method menu (a pull surface that already exists), the League bar chart itself.
- **Not discoverable by poking, teach:** the outlook/Trade DNA control (one collapsed line; nothing says "this re-aims every card"); the League-rankings buyer/seller median divider (only appears under a single-position filter); the relationship between a board and card prices; the mutual-match → send path.

### 2.4 The rankings problem is a framing and honesty problem

Seed #3 asks to show the rankings section and its methods while downplaying the work ("we'll generate rankings as they like/dislike trades"). Four facts bound what the copy may say (all code-verified):

- The Elo write from swipes is **real and per-user**: `POST /api/trades/swipe` resolves the *session-scoped* `RankingService` (`service = sess["service"]`, `backend/server.py:~10165`) and calls `record_trade_signal` (`backend/ranking_service.py:334`) on both like and pass (`trade_k_like=8.0`, `trade_k_pass=4.0` vs `elo_k=32.0`). The swipes write the **user's own** Elo, not a shared pool — this per-user scoping is the entire load-bearing basis for the Phase-1 copy claim below.
- Nothing in the mobile UI currently reflects it: the provenance chip stays `CONSENSUS VALUES`, and swipes count toward **no** unlock lane until open-access Phase B ships `grade_count`/`grade_required` (§B-2/§B-3, unbuilt).
- There are **seven** ranking methods plus import and the steer slider; sixteen words cannot tour them, and the method menu (`RankHome`) is already a pull surface.
- The audience is domain experts, who punish early algorithm errors durably (`r2-1b` §6).

So the copy strategy is two-stage: **now**, a calibration-framed, mechanically-true line ("your swipes are already teaching me") that promises no visible board change; **after Phase B**, the stronger progress promise ("your board is building itself") anchored to the chip rendering `grade_count`. Promising board generation before the product shows it is the G-038 dead-end failure in copy form.

### 2.5 Target users

- **Primary — the new dynasty manager, first session.** Domain expert with strong player-value priors; the Nourani/Dietvorst early-error trust risk dominates this segment.
- **Secondary — the returning user who met tour v1** (has `guideSeen` v1 ids, possibly `guideDismissed`). Must not be re-taught, must never have an opt-out silently reversed, must not get a fresh wave of bubbles after "that's the tour."
- **Tertiary — the multi-league manager** (sees `s1.1` today; the only user who has met The Analyst at all).

### 2.6 Why now

The research round closed with a specific engineering verdict (`r2-2b`): the build problem is the eligibility/registry layer, not the overlay; buy doesn't fit. The calendar is right: dynasty's measured July→August attention step is 3.4–3.5× with a September peak 6.3–7.3× the trough (`r2-3a`) — mid-August is the last cheap window. And the no-OTA constraint (`expo-updates` absent from `mobile/package.json`, code-verified) means copy must be right at the pre-season build.

---

## 3. Goals & Non-Goals

### 3.1 Goals

| # | Goal | How we'd know |
|---|---|---|
| G-1 | Every script beat is **reachable** — trigger can fire AND target mounts (or a degrade contract is defined) — under the shipped flag set, or is deleted | Reachability table in the scope block: one row per beat, columns for trigger gate, target mount condition, degrade contract; zero rows failing |
| G-2 | A new user finishes session one having completed the core loop once | First-swipe activation (ratified O-4 definition), monitored per §4.3 — *note: the causal read has a volume precondition and may be unreadable; the goal is then assessed qualitatively* |
| G-3 | A user whose deck is failing them finds the outlook control at that moment | `N2` exposure→`find_trades_tapped{source:'prefs_changed_strip'}` join + painted-door tap count |
| G-4 | Ranking stops reading as homework: post-tour mental model is "prices come from a board; mine is already forming; sharpening it costs two minutes" | `N1`/`s3.2` funnel to first Quick Set completion |
| G-5 | A user knows where they stand in their league and can use it directionally | `N5` exposure→`league_pos_candidates_viewed` join |
| G-6 | Every scaffold declares trigger, budget, retirement, degrade, and adoption event at authoring time; the layer stops teaching people who have learned | `GuideStep` fields + structural CI test; quarterly review only of steps that failed to self-terminate |
| G-7 | Guide/modal contention is deterministic and observable | FR-E4 mechanism + suppression event; zero modal-over-bubble occurrences in Maestro runs |

### 3.2 Non-goals (with reasons)

| # | Non-goal | Why |
|---|---|---|
| NG-1 | Teaching "accept a trade" as an in-app mobile verb | Doesn't exist (`mobile/src/api/trades.ts:484-487`). The beat teaches **send**. Mobile accept/decline is separate feature work (OQ-2) |
| NG-2 | A "rankings build themselves" promise before Phase B | §2.4: mechanism real, surface absent; promise-before-proof is the expert-trust failure |
| NG-3 | A tour of the ranking-methods menu | Seven methods vs 16 words; the pull surface exists (`RankHome`) |
| NG-4 | An opt-in "show me around" help button on the deck | Only controlled test is negative (Andersen); `HelpSheet` already ships |
| NG-5 | Idle-timeout triggers (delete v1's unbuilt `S4.idle` spec line) | Worst measured trigger family (attention 0.63 vs 0.93, p<0.001) |
| NG-6 | "Did you know" framing / feature-announcement beats | Zero controlled evidence; TipKit's anti-scope names announcements |
| NG-7 | Per-step A/B tests | 500+ users/variant floor vs 156 measured league members |
| NG-8 | Seasonal / welcome-back re-onboarding, recaps | Year in Review thread owns it |
| NG-9 | Adopting `react-native-spotlight-tour` or any OSS tour lib | FTF's registry is more defensive than the lib documents; Expo/New-Arch support unstated |
| NG-10 | Adopting `expo-updates` in this scope | Stated non-goal in a live plan; Phase 3 is the alternative |
| NG-11 | Any beat rendered inside a `<Modal>` | `AnalystGuide` is a RootNav sibling; RN `Modal`s render above it (`TradeDnaSheet.tsx:475`). Beats target entry points |
| NG-12 | Overlay/avatar redesign; checklists/gamification; guest mode | Separate threads |

---

## 4. Success Metrics

### 4.1 The honest posture, stated first

**FTF is under-powered for A/B testing this work and no metric below pretends otherwise.** The 2026-08-15 production mirror (measured): 12 leagues, **156 league_members**, 2,513 swipe_decisions, 8,600 user_events. PostHog's floor is 500+ users per variant; a 1–2% holdout here is two people. Real-world nudge effects average +8% (DellaVigna & Linos), invisible at this N.

**Consequence: no beat-level causal claim is available this season.** Beats are chosen on defensibility, cost, and honesty; validated qualitatively (operator TestFlight walk + Maestro assertion flows); and monitored by within-subject diagnostics that need tens of users. A season-long causal holdout is explicitly **not** run at current N — revisit at ≥5,000 MAU.

### 4.2 Diagnostics (within-subject; detect *broken*, not *worked*)

| # | Metric | Definition | Target |
|---|---|---|---|
| M1 | Beat completion | `guide_step_advanced{step, via ≠ 'timeout'}` ÷ `guide_step_shown{step}`, deduplicated per `(device_id, step)` per day (shown over-counts on mid-guide app kill; timeout advances are excluded from the numerator — `via` is already in the event's registered props and `'timeout'` in `advance()`'s union, no taxonomy work) | ≥0.60; <0.40 → re-author or retire |
| M2 | Teach rate | Share of new devices with `guide_step_advanced{step:'s2.2', via:'action'}` (baseline ≈0 today) | Reported |
| M3 | Spotlight degrade rate | `guide_step_shown{spotlight:'degraded'}` share, split by platform + app_version | **<5%** |
| M4 | Suppression rate | `guide_step_suppressed{step, blocked_by}` ÷ requested | Reported; >30% for a beat = priority bug |
| M5 | Annoyance guardrail | `guide_tour_dismissed` per new device; `guide_step_skipped` rate | No rise vs pre-v2 cohort |
| M6 | Exposure→adoption smell test | `guide_step_shown{step}` → first `adoptionEvent` within 7 days, joined on `device_id` | Reported with the caveat **inline and unremovable**: not a control; a smell test |
| M7 | Copy-budget conformance | CI lint (words per class, `autoMs` floor, required fields) | 100% — a test, not a metric |
| M8 | Interrupt budget | Pushed surfaces per session | ≤2 at p95 |

### 4.3 Monitored series with halt thresholds (the rollout's trip wires)

The staged rollout needs outcome trip conditions, not just annoyance ones. Two **absolute series, explicitly non-causal**, per weekly cohort:

- **First-swipe activation rate** (O-4 definition) — halt and investigate if a guided cohort drops >5pp below the trailing 4-week mean.
- **D7 return rate** — same threshold.

If weekly new-device volume ≥~50, these support a difference-in-differences read (parallel pre-trends stated and plotted); below that, they are monitoring only, and any readout says so. **Precondition, still owed: publish weekly new-device volume.** Regression-discontinuity reads at numeric triggers (`N1` swipe 3; `N2` three passes) are free identification, reported with shrinkage priors.

### 4.4 Painted door for the least-certain beat

Before/after taps on the outlook entry point per exposed device (the `N2` thesis test). A beat that does not move a raw tap count will not move activation.

### 4.5 Structural guardrails (enforced, not measured)

- No guide-owned dots or badges on the notification bell, ever.
- Staged **surfacing**, never staged gating: later cohorts lose only the teaching, never the feature.

---

## 5. Requirements

### 5.0 The `GuideStep` contract

Every beat is specified on eight axes. **Five become new fields on `GuideStep`** (`retireAfter`, `maxDisplayCount`, `invalidateOn`, `adoptionEvent`, `degradeLine`/`degrade`); trigger and copy class formalize existing practice; skip semantics are inherited from the overlay. A beat missing any axis fails the structural CI test (`mobile/tests/check-guide-script.js`) and does not build:

```
trigger          — named predicate id; a declared boundary or failure state; never idle-time.
                   MUST include the owning feature flag(s) of any surface the beat teaches (fail closed).
copy class + cap — auto: 12 words AND autoMs ≥ words/4.17×1000 + 800 · action: 16 · tap: 20 · cta: 16 + ≤4-word buttons
retireAfter      — {event, count} behavioral death condition, or explicit 'never' with a stated reason
maxDisplayCount  — hard display cap (default 1 for once-steps, 2 otherwise)
invalidateOn     — event ids that permanently kill the step
adoptionEvent    — the downstream event the beat claims to cause (no event, no thesis)
degradeLine | degrade:'suppress' — copy when the spotlight cannot measure; purely deictic lines must suppress
skip semantics   — per-step ✕ + permanent "Skip the tour" opt-out on every bubble (never-trap)
```

**Enforcement split, stated plainly:** the structural CI test enforces the **five stored fields** (`retireAfter`, `maxDisplayCount`, `invalidateOn`, `adoptionEvent`, `degradeLine`/`degrade`) plus copy class/length/`autoMs`. `trigger` remains an inline call-site predicate today (e.g. `TradesScreen.tsx:2775`, `SignInScreen.tsx:152`) — it is **a documented convention audited by the G-1 reachability table and the per-beat Maestro flow, not a CI-checkable field**. Promoting triggers to stored predicates is Phase-3 work if the server-delivered script ships.

### 5.1 Engine requirements (Phase 0 — precedes all new content)

**FR-E1 — One gate.** Step eligibility depends on `onboarding.v2` + `onboarding.guided_avatar` and nothing else from the `onboarding.*` family. Every second gate in §2.1 is replaced by a **product-state predicate** on the step itself. Feature flags owning a *taught surface* (e.g. `trade.outlook_direction`, `league.pos_candidates`) are trigger preconditions per §5.0 — that is not a second gate, it is fail-closed correctness. *Test:* with only the two guide flags true and all other `onboarding.*` false, a fresh install reaches `s8.1`. **Coordination:** `feat/open-access-phase-a` (unmerged, separately owned) flips several of the same flags; re-diff at build start. The guide must not *require* that branch (OQ-6).

**FR-E2 — Declarative eligibility.** `GuideStep` gains the §5.0 fields; `requestStep` evaluates `maxDisplayCount` and `invalidateOn` before activating and refuses on failure.

**FR-E3 — Behavioral retirement is mandatory.** Every beat declares `retireAfter` or an explicit justified `'never'`; `once: true` is a display cap, not a retirement condition. The measured harms (Andersen's opt-in help; Aleven's help-abuse r=−0.46) come from users who *engage* — dismissal does not cover it. **A retirement condition wired to an event that does not fire is worse than none: the §5.3.1 event inventory is therefore a Phase-0 exit gate, not a footnote.**

**FR-E4 — Deterministic guide/modal arbitration, mechanism named.** The shipped `claim()` is strictly **first-come with no preemption** (`useInterruptCoordinator.ts:~50-56`: `if (cur !== null) return false`); `SURFACE_PRIORITY` is documentation only, and the root modals (`PushPrimingModal.tsx:37`, `AppleSaveMomentSheet.tsx:40`) test only `activeSurface !== null`. "Add the guide at priority 0" is therefore a no-op on its own. **Chosen mechanism (default): keep first-come, and (a)** `requestStep` claims a new `'guide_step'` surface **synchronously, ahead of any screen-level `useInterruptSlot` effect**, holding it for the active step's lifetime — the root modals already subscribe reactively to `activeSurface !== null`, so (a) alone defers them without touching `claim()`; **(b)** as belt-and-braces for `ux.prompt_arbiter` being flipped off, both root modals additionally subscribe to the guide via the reactive hook (`useGuide((s) => s.active === null)`, matching the existing `surfaceBusy` pattern — **not** a one-shot `getState()` read, which would not re-render when the guide clears), gated on `onboarding.guide_v2`; **(c)** `SURFACE_PRIORITY` is renumbered and its comment corrected. The alternative — real priority comparison + preemption in `claim()` — is explicitly not chosen: it modifies a live arbiter (`ux.prompt_arbiter: true`) and would need regression across its four existing surfaces. *Test:* with a guide step active, neither root modal mounts; with `onboarding.guide_v2` off, behavior is byte-identical to today (which is also why (b) must be flag-gated — v1 steps like `s1.1`/`s6.1` can be active under `guided_avatar` alone).

**FR-E5 — Suppression is measured.** `requestStep` refusals emit `guide_step_suppressed {step, blocked_by}` (once per deferral episode). Today the beat is silently dropped (`useGuide.ts:94`).

**FR-E6 — Degrade is observable and coherent.** `guide_step_shown` gains `spotlight ∈ {'measured','degraded','none'}`. When `measureGuideTarget` returns null (250 ms timeout — masking Fabric first-render timing and a reported Android release-build `measureInWindow` bug), the overlay currently renders the same line with no pointer. v2: render `degradeLine`, or suppress when `degrade:'suppress'`. §2.1's live `s7.1` incoherence is the standing exhibit.

**FR-E7 — Copy lint in CI.** Word caps per class, `autoMs` reading floor, one primary action per beat, required-fields presence. The lint owns the counts; current known violations to fix in the Phase-0 pass (recounted after round-2 review): `s2.1` 21w, `s2.3` 18w, `s3.1` 19w, `s7.1` 19w, `s0.1` 16w, `s5.0` 27w, plus the two **auto-advance timing violations**: `s6.1` (12w / 2200 ms, needs ≈3,680) and `s6.2` (17w / 2600 ms, needs ≈4,880) (`analystScript.ts:89-96`, code-verified).

**FR-E8 — Taxonomy first.** Every new event/prop ships its `backend/analytics_taxonomy.py` addendum **before** the emitter, with a post-deploy read-back of `user_events` per name (value survives, not just key — G-036). Third recorded occurrence of drop-behind-a-200 (G-031); `guide_tour_reenabled` is emitted today (`useGuide.ts:134`) and unregistered — register it or remove the emitter.

**FR-E9 — Script versioning.** Persisted state gains `guideScriptVersion`. Retained v1 steps keep ids; new steps get new ids. `guideTourCompleted && guideScriptVersion < 2` → at most one v2 beat per release, boundary-triggered, never the opening. No seen-state cleared on upgrade.

**FR-E10 — Opt-out is sacred; re-enable is sane.** `guideDismissed` suppresses everything including new beats; Settings-only reversal. `enableTour()` replays **only beats whose trigger can still fire from current state** (today it replays into an unreachable opening — `useGuide.ts:132-135`).

**FR-E11 — Kill-switch honesty.** `guidedAvatarActive()` off is documented to fall back to the passive layer, but `onboarding.guided_layer` and `onboarding.quickset_prompt` are both false — it falls back to **nothing** (code-verified). The runbook kill-switch entry either flips the passive flags or corrects the claim (OQ-7), recorded before rollout.

### 5.2 Script v1 inventory — verdicts **and target copy**

Copy below is the **drafting target** (subject to the mkt-writer voice pass, then frozen pre-build — owner in D9). Slot values (`{n}`, `{pos}`) resolve from live values only, per the script's own honesty rule.

Each row states its **copy class** so FR-E7's lint has an authority to check against (caps: auto 12 · action 16 · tap 20 · cta 16). `autoMs` values are **recomputed from the frozen post-D9 copy**, not pinned to the pre-trim numbers in FR-E7.

| v1 id | Class | Verdict | Target copy (words) |
|---|---|---|---|
| `s0.1` | tap | CHANGE — trim; un-gate per FR-E1 | "I'm The Analyst. I model dynasty trades — you bring the roster." (11) |
| `s0.2` | action | KEEP | "Type your Sleeper username. No password needed." (7) |
| `s0.err-notfound` | tap | CHANGE — trim | "No Sleeper account by that name. Check the spelling — caps don't matter." (12) |
| `s0.err-down` | tap | KEEP | (current line) |
| `s1.1` | action | CHANGE — trim | "Pick the league you check at work. That's the one that matters." (12) |
| `s2.wait` | action | CHANGE — itemize real computation, live numbers | "Reading {n} rosters, scoring candidate trades. First cards land in seconds." (11) |
| `s2.1` | tap | CHANGE — trim + **soften the confidence claim** (market claim, not a card warranty; measured first-run insult rate 1.48%/3.70% makes some broken promises certain) | "These are trades both sides should want. Not a wishlist — a market." (12) |
| `s2.2` | action | KEEP — the only guided-doing beat; `s8.1` gates on it | "Swipe right to take it, left to pass. Every swipe teaches me." (12) |
| `s2.3` | — | REPLACE → `N1` | — |
| `s3.1` | — | CUT — merged into `s3.2`. Safe: `setGuidedS3Pending(true)` runs unconditionally after the s3.1 request (`TradesScreen.tsx:2630-2633`) and `s3.2` chains off `guidedS3Pending` (`:2550`), never off `guideSeen['s3.1']` | — |
| `s3.2` | cta | CHANGE — absorbs s3.1; full spec promoted to §5.3 | see §5.3 (13 ≤ cta cap 16) |
| `s4.1` | action | CHANGE — trim; needs `degradeLine` (deictic) | "Tap everyone worth the tier label, then Save. Gut calls beat overthinking." (12) · degrade: "Tap every player worth the tier, then Save. Gut calls beat overthinking." |
| `s5.1` | tap | KEEP — **plus the N=1 plural fix** (S-43 handoff, 2026-08-15: engine stochasticity means the beat can honestly fire with `fresh = 1`, rendering "1 new trades"; flagged in TEST_LEDGER, unshipped — lands in this copy pass) | "{n} new trade{n, plural}s that exist only because of your numbers." — singular/plural resolved at render; lint measures the longest form (10) |
| `s5.0` | tap | **CHANGE** — trim 27→13 (relabelled from KEEP: the copy is materially rewritten); the honest-null branch is a trust asset | "Same trades — your {pos} board agrees with consensus. More positions, more edge." (13 ≤ tap cap 20) |
| `s5.5` | cta | CHANGE — trim; `invalidateOn: [all_positions_ranked]` | "{done} is done. {next} is your next-highest leverage — same drill, two minutes." (13 ≤ 16) |
| `s6.1` | — | **REPLACE → `N6.1`** (per O-1): the passive "you'll hear from me" toast becomes an active router to "Awaiting them" with an optional-send offer. **Sign-off rewire (round-5):** `s8.1`'s predicate reads `guideSeen['s6.1']` as its second conjunct (`TradesScreen.tsx:2588-2594`) — it MUST be re-pointed to `guideSeen['n6.1'] \|\| guideSeen['s6.1']` or the tour permanently loses its ending (the exact P0-8 failure this PRD exists to fix) | — |
| `s6.2` | auto | **CHANGE** — trim to auto cap + fix `autoMs`; predicate replaces flag gate (relabelled from KEEP: copy rewritten). **Sequencing (round-6 corrected):** the first-like moment belongs to `N6.1`; the like handler's existing timer chain (`s6.2` request + `maybeAskApple('like')` — `TradesScreen.tsx:3316-3322`) fires from **`N6.1`'s completion callback** (advance / `Later` / swipe-dismiss / timeout — three of the four exits never leave TradesScreen, so a focus hook would starve the chain); only the CTA-navigation exit uses the next-TradesScreen-focus hook. The deferred chain re-checks `appleAskEligible('like')` at fire time (session/verification state can change in the interval), and non-first likes keep today's inline chain — **except the like that itself swipe-dismisses `N6.1`: the deferred chain owns that moment and the inline chain is skipped for that like** (the engine's `once`/`active` guards make a double-fire benign, but ownership is declared, not left to timing). The chain hangs off the new `onComplete(via)` hook (D2), which covers every terminal transition including the per-step ✕. `maybeAskApple` (`:2824-2837`) currently consumes its once-per-class shot *before* showing — it MUST consume only on successful show, or the deferred like-class ask is burned unseen (the P0-9 bug shape) | "Quick admin: sign in with Apple to save your rankings. Five seconds." (12 = auto cap) |
| `s7.1` | — | **CUT as a pushed beat.** Its target cannot mount under shipped flags (§2.1) and the exhausted-deck boundary now belongs to the summary card + `N4` (§5.3). Trios remain a pull surface; revival condition: `onboarding.rank_routing` ships AND a boundary is free | — |
| `s8.1` | tap | KEEP | "That's the tour. I'll surface when the numbers say something worth hearing." (12) |
| S2.identity, S2.re-entry, S4.2, S4.idle | — | CUT from the script doc — phantom scope; `S4.idle` is the banned trigger family | — |

### 5.3 New beats

**The exhausted-deck boundary has four claimants; the allocation is a declared rule.** The claimants: the shipped `deck.replenishment` summary card (`trades.deck-summary`, which renders at exhaustion for every user with ≥1 swipe — `summaryVisible`, `TradesScreen.tsx:~2787-2791`, rendered `~5060-5090`, code-verified); `N4`; `N2`; and legacy `s7.1`. **The rule: the summary card owns the slot, and `N4` ships as an extension of it** — not a competing card. `N2` fires on the *pass-failure* trigger, which is upstream of exhaustion. `s7.1` is cut (§5.2). One boundary, one surface, deterministic.

---

**`N1` — Prices, and where yours come from** *(replaces `s2.3`+`s3.1`; seed #3, honest version)* — Phase 1
- **Trigger:** third disposition in the first session (post-success boundary). Suppressed for redraft leagues (`settings_type === 0`).
- **Surface:** spotlight `trades.provenance-chip`.
- **Copy (12, calibration-framed; mechanically true per §2.4's per-user Elo scoping):** "These prices are the market's. Your swipes are already teaching me yours."
- **Action:** tap the chip or tap-advance. **adoptionEvent:** `quickset_started` *(NEW — see §5.3.1)*.
- **Retirement:** `once`; `invalidateOn: [quickset_completed, tiers_saved, ranks_imported]` *(names per §5.3.1)*.
- **Degrade:** `degradeLine`: "Card prices are consensus for now. Your swipes are already teaching me your values." (14)
- **Honesty bound:** claims *teaching*, not board generation. The progress line is Phase-B-gated.

**`s3.2` — The two-minute ask** *(amended; carries seed #3's downplay; from Phase 2 it doubles as the ladder's Quick Set rung — see Ladder arbitration below)* — Phase 1
- **Trigger:** first pass after ≥2 swipes, else at swipe 3 (existing predicate, decoupled from `onboarding.quickset_prompt` per FR-E1); fires only after `N1` **seen or ineligible** — `N1` is suppressed for redraft leagues, and a strict after-N1 chain would silently kill the whole s3.2→s4.1→s5.x reveal for redraft-only users (§5.4 redraft row).
- **Surface:** bubble with in-bubble CTAs anchored near `trades.provenance-chip`.
- **Copy (13):** "Two minutes on {pos} and I'll re-price every card with your numbers."
- **Action:** primary CTA `Fix {pos} →` routes to QuickSetTiers with `onboardingReturn: true`; ghost CTA `Not now` snoozes.
- **adoptionEvent:** `quickset_completed`. **Retirement:** `maxDisplayCount: 2` (initial + one session-2 re-offer), then permanent; `invalidateOn: [quickset_completed, tiers_saved, ranks_imported]`.
- **Degrade:** bubble is not deictic; no degrade needed.
- **This is the rankings downplay:** one position, cost in minutes, the word "rankings" never appears, no method chooser.

**`N2` — Re-aim the deck** *(seed #2; two-form)* — Phase 1
- **Trigger:** failure family — three consecutive passes with no like, AND no **declared** outlook, AND owning flags on: `trade.outlook_direction` (the receipt), **`trades.edit_full_sheet` + `trades.finder_hub`** (without `consolidateOn = fullSheetOn && !!finderMode` — `TradesScreen.tsx:572` — the outlook entry points route to the legacy `OutlookSheet` at `:3933/:4584/:4603`, so Form B would teach a non-live entry point, and the adoption receipt's strip never renders — `:3707`). All fail closed. Not idle; not first-card.
- **Surface, two forms (the round-2 fix):** the `OutlookBiasReceipt` renders only when a directional outlook *resolves* — `outlookReceiptCovers(directionOn, declared, inferred)` returns false when `declared ?? inferred` is null/`not_sure` (`OutlookBiasReceipt.tsx:46-54`; the `trades.outlook-receipt.change` target sits inside that guard at `:79/:87`, code-verified). So:
  - **Form A (receipt mounted** — backend inferred a direction): spotlight `trades.outlook-receipt.change`. Copy (11): "Not your kind of deal? Set your outlook — I'll re-aim these."
  - **Form B (receipt absent** — the common no-outlook case): bubble with one primary CTA (`advance:'cta'`, no deixis, nothing to degrade). Copy (11): "Not your kind of deal? Tell me what you're hunting for." · CTA `Set outlook →` opens `TradeDnaSheet` directly.
- **Action:** open the DNA sheet (autosaves per tap; the sheet itself is a `<Modal>` and is never coached — NG-11).
- **Completion:** sheet opened + ≥1 preference write. **adoptionEvent:** `find_trades_tapped{source:'prefs_changed_strip'}` *(EXISTS — §5.3.1; the honest receipt for "changed prefs, then re-ran the deck." Two stated caveats: the strip is prefs-change-generic, not outlook-specific; and it only arms when `deck.length > 0` at sheet close (`:613-618`), so a user who passes to full exhaustion before closing the sheet is undercounted by the G-3 join — say so in readouts)*.
- **Retirement:** `invalidateOn: [outlook_saved]` *(NEW emitter — §5.3.1)*, `maxDisplayCount: 2`. **Degrade (Form A only):** fall back to Form B.

**`N4` — The empty deck** *(rides the shipped summary card)* — Phase 1
- **Trigger:** deck exhausted, zero pinned targets, and **all three owning flags** on: `deck.replenishment` (the summary card), `trade.finder_targeting` (`features.json:36` — the flag behind `targetingEnabled`, the pin board), and `trades.finder_hub` (without which `finderMode` resolves `undefined` — `TradesScreen.tsx:531/:541` — and the hand-off CTA would be dead). If any is off, the pin line is omitted entirely (fail closed). Note the summary card itself additionally requires ≥1 disposition **this session** and `!summaryDismissed` (`TradesScreen.tsx:2787-2791`) — see §5.4.
- **Surface:** **an added line + primary action on the existing `trades.deck-summary` card** — not a new card, not an overlay bubble. This keeps the one-surface boundary rule, reads as content not chrome (NFR-5), and keeps the in-workspace delivery form whose evidence is the strongest in the corpus (attention 0.93 vs 0.63 for in-workspace vs message-box hints, p<0.001).
- **Copy (12):** "Cleared the market. Pin who you want — I'll ping you on matches."
- **Action (the round-2 fix — the pin verb needs a reachable control):** the card's primary action `Pin targets →` performs an explicit hand-off: sets `finderMode = 'player'` and opens the FB-47 targeting board (gated `!firstRun && targetingEnabled && finderMode==='player'` — `TradesScreen.tsx:4047/:4337`, code-verified; a legacy "Target players" construction also renders outside player mode at `:4157`, but the board is the taught surface). This is a **scoped small UI delta**: one CTA + one mode hand-off, named in D2 with its `testID` and a Maestro flow.
- **Completion:** ≥1 pin recorded. **adoptionEvent / retirement:** `finder_target_pinned` *(NEW emitter on the targeting board's pin handler — §5.3.1)*; `retireAfter: {finder_target_pinned, 1}`.
- **Rationale:** FTF's eBay moment — the only no-results pattern that converts failure into feature adoption.

**`N6` — First like → "Awaiting them"** *(seed #1 per O-1; replaces `s6.1`)* — N6.1 Phase 1, N6.2 Phase 2

Two chained units, one narrative moment (the s3.2→s4.1 chain is the precedent):

*N6.1 — the router (TradesScreen)* — Phase 1
- **Trigger:** first like recorded for this device (the moment `s6.1` owns today). Takes the moment; the `s6.2` + Apple-ask chain moves behind `N6.1`'s completion (§5.2 `s6.2` row).
- **Surface:** bubble with in-bubble CTAs (cta class; not deictic, no degrade needed). **Lifetime bound:** auto-dismisses on the next swipe or after 8 s — a cta bubble with no bound would hold the interrupt slot across further swipes and starve the push primer/Apple ask (named under M4/M8 monitoring alongside `N3`). **This bound is a new engine capability** (timeout + swipe-driven dismissal on a cta step) — added to D3's structural-test scope. **Timeout disposition:** a timeout MUST write `guideSeen['n6.1']` (or `s8.1`'s rewired predicate never becomes true for timed-out users — the ending lost through a new door) and MUST be analytics-distinguishable (`via:'timeout'`) so it inflates neither M1's completion numerator nor M5's skip rate.
- **Copy (12) — honesty bound, like `N1`'s:** "Logged — they haven't seen it yet. Send it to them now?" A one-sided like creates **no** notification and no row on the counterparty's side (notifications exist only for mutual matches — `backend/server.py:10321-10339`, `trade_match`); the copy must never imply the other manager was pinged or is deciding. ~~"It's waiting on their side"~~ is exactly that false social fact.
- **Action:** primary CTA `See it →` navigates `Matches {segment:'awaiting', at: Date.now()}` (the effect keys on `[segment, at]` — `MatchesScreen.tsx:112-119`); ghost `Later` dismisses.
- **Empty-awaiting gate (round-6 sequencing — a like-time prefetch would race the swipe POST and read a list that never contains this like):** the gate is evaluated in **`swipeMutation`'s `onSuccess`** (`TradesScreen.tsx:~1517/:1543`) — the first-like determination moves there too, and two rapid likes MUST NOT both read first-like true. The swipe response already carries `{matched, match_id}` (`:1548`): if `matched`, the like matured instantly — **suppress `N6.1`, and the suppression path writes `guideSeen['n6.1'] = true`** (emitting `guide_step_suppressed{step:'n6.1', blocked_by:'matched'}`, no `guide_step_shown`, so M1/M5 are untouched). The moment is **consumed** — without this write, `s8.1`'s rewired predicate is permanently false for instant-matchers: the same lost-ending door the timeout disposition bolts, and worse in Phase 1 where `N3` doesn't exist yet. Otherwise issue the `['awaiting-trades']` fetch from `onSuccess` and request the bubble only after it resolves; the 8 s lifetime bound covers the tail, and on timeout/empty/error show the router-less variant — the bubble's copy is chosen before render and **never swaps after**. Emptiness is not rare (the backend drops rows whose counterparty can't be resolved from the cached roster index — `load_awaiting_trades`, `database.py:6979-6987`), and the segment's empty state ("No pending trades… Swipe more") would flatly contradict the bubble one tap later, at the most trust-critical moment (R1). Router-less variant: "Logged — I'll flag it the moment they like it back." (10, tap class), no CTA.
- **Completion:** CTA tapped, dismissed, or timed out. **Funnel step:** `awaiting_segment_viewed` *(NEW — §5.3.1)* records arrival, but it is **not** the adoption event — the beat's own CTA causes it, so it would read ~100% and manufacture a win. **adoptionEvent:** send-attempt family with `surface='awaiting'` within 7 days.
- **Retirement:** `once`; `invalidateOn: [send_attempt_family]`.

*N6.2 — the send offer (MatchesScreen, awaiting segment)* — Phase 2
- **Trigger:** arrival in the awaiting segment via N6.1's CTA (a **new route param** carries the chain state — `MatchesScreen` reads only `segment`/`at` today; the param is named in D2), awaiting list non-empty.
- **Surface (round-6 disambiguated):** `trades.send-sleeper-btn` is the testID on **every** `SendInSleeperButton` (`SendInSleeperButton.tsx:483`) across all awaiting *and* mutual cards, and `guideTargets` is last-mount-wins **per testID** (`guideTargets.ts:9-16`) — spotlighting the raw testID would frame an arbitrary trade. The target is a **per-instance, platform-agnostic registration id** (`trades.send-control.guide`) mounted on **whichever branch the router actually renders** — `SendInSleeperButton` early-returns to `SendInMflButton` (~`:410`), `SendInEspnButton` (`:431`), or the copy-trade fallback (`:459-471`) before its own Sleeper `Button` at `:483`, so a registration pinned to the Sleeper button covers Sleeper only. Mounted only on the chain-target row (the trade `N6.1` carried, else the top awaiting row). **Same fix and same id for `N3` on the mutual list — carried into D2.**
- **Copy — platform-resolved like N3 (14):** "Send it in Sleeper now, or wait — I'll flag it if they match." Copy-trade/suppress branches identical to N3's platform table.
- **Action:** tap Send/Copy, or tap-advance (sending is optional — the beat teaches that the *choice* exists).
- **Completion:** advanced. **adoptionEvent / retirement:** send-attempt family; `retireAfter: {send_attempt_family, 1}`, `maxDisplayCount: 2`. **Degrade:** `degradeLine`: "You can send this from here anytime — or wait for them to like it back."
- **Until N6.2 ships (Phase 1 interim):** N6.1 routes to the segment and stops; the awaiting card's own send button is visible unspotlit. Acceptable — the router is the teaching payload.

*(N3 degrade axis, added for §5.0 conformance — it was the one beat missing it:)* **N3 degrade:** `degradeLine`: "Both sides said yes — send it from this match to make it real." (12, no deixis), frozen under D9 with the rest.

**Ranking-method ladder** *(O-5 policy — governs every ranking nudge after session 1)*

Session 1 keeps the Quick Set two-minute ask (`s3.2`→`s4.1`) as primary, because it powers the `s5.x` reveal. From session 2 on: **at most one ranking nudge per session; nudge the lightest method the user hasn't tried; each rung retires on first use of its method.** Effort order per O-5: **Trios (~30 s) → Quick Set (~2 min) → Tiers (heaviest)** *(Quick-Set-before-Tiers within O-5's "heaviest" group is this PRD's interpretation — cheap for the operator to overturn)*. This is not a methods-menu tour (NG-3 stands — one method, one moment, one action); it is staged variety with retirement.

**Ladder arbitration (round-6 — phase-scoped, or Phase 1 loses the re-offer):** `s3.2`'s "session-2 re-offer" fires early in the deck (swipe 3) while `N7` fires only at exhaustion, so first-come would hand every session-2 budget slot to Quick Set — the heavier rung — and O-5's variety never materializes. Rule: **the ladder arbitration takes effect when `N7` ships (Phase 2). In Phase 1, `s3.2`'s re-offer is unconditioned** (there is no lighter rung to defer to, and `rankLadder` state ships with Phase 2). From N7's ship onward: `s3.2`'s re-offer is the ladder's Quick Set rung and fires only when no lighter rung is **pending** — where a rung stops being pending when **its `retireAfter` fired, OR its `maxDisplayCount` is exhausted, OR it has not been eligible to fire for 3 consecutive sessions** (a user whose deck never exhausts must not block Quick Set forever). Ladder state (`rankLadder: { nudgeSpentSessionId, methodsTried[], perRung: { lastEligibleSessionId, ineligibleStreak } }`, persisted onboarding store, Phase 2 — the per-rung fields are what make the 3-session not-eligible clause implementable; eligibility is sampled once per session at the summary-card evaluation) is written from client receipts (`quickset_completed`; the trio client receipt below; tiers save). `s3.2`'s `maxDisplayCount: 2` gloss reads "initial + one re-offer" — the re-offer lands in session 2 under Phase 1 and whenever the ladder frees it thereafter. **Expectation note:** most pre-Phase-2 users will have spent both `s3.2` displays before `N7` exists — the ladder does not revive an exhausted rung; for them the ladder's practical effect is Trios-then-Tiers.

**`N7` — The Trios rung** *(O-5)* — Phase 2
- **Trigger:** exhausted-deck summary card visible (owning flag `deck.replenishment`, same as `N4`), session ≥2, `rankLadder.methodsTried` lacks trios, ladder budget free this session, and `N4`'s pin line retired or user has pins (the pin action outranks the ladder on first exhaustion).
- **Surface:** tertiary line + CTA **on the summary card**, subject to the card's button budget (below). **Not** the dead `trades.trio-entry` spotlight — the CTA navigates **nested**: `navigate('Rank', { screen: 'Trios' })` (precedent `TradesScreen.tsx:2571-2575`; `Trios` is registered unconditionally in the Rank stack, `TabNav.tsx:266-275` — reachable without `onboarding.rank_routing`), which is what keeps the `s7.1` cut honest.
- **Copy (12):** "Thirty seconds of head-to-heads sharpens every price. Try one trio."
- **Action:** CTA `Try a trio →`. **adoptionEvent / retirement:** the **client** trio receipt (§5.3.1 — `trio_swipe` is server-emitted and client-invisible; a NEW client emitter or persisted `trioVoted` flag is required for both trigger and retirement); `retireAfter: {trio_client_receipt, 1}`, `maxDisplayCount: 2`.

**Summary-card button budget (round-5):** the shipped card already carries `trades.deck-summary.see-liked` (secondary) and `.done` (primary) (`TradesScreen.tsx:5078-5087`). Rule: the card keeps **one primary** (FR-E7). When `N4`'s pin line shows, `Pin targets →` is primary and `Done` demotes to ghost; `See liked` stays secondary; `N7`'s `Try a trio →` renders only when the pin line is absent/retired, as the tertiary slot. Never all four.

**`N3` — Send the trade on a mutual match** *(the **separate** match walkthrough, per O-1)* — Phase 2
- **Trigger:** first mutual match exists for this device (`MatchesScreen` focus, `mutual` segment non-empty). **Never synthetic** — a fake match is a fake *social* fact; the one case where the sandbox pattern does not transfer. Fires days after install for most users, never for some; correct, not a defect.
- **Surface:** spotlight the send control (**new registration**; the guide has zero targets on this screen).
- **Copy — platform-resolved, mandatory:** Sleeper (14): "They like it too. Sending puts the offer in Sleeper — they accept there." · MFL under `trade.send_in_mfl` (same shape, platform word swapped) · **ESPN under `espn.send` — which is `true` (`config/features.json:65`, flipped 2026-08-12 when D-026 reversed the NO-GO to a gated GO; `SendInSleeperButton.tsx:115/:428-433` routes ESPN leagues to `SendInEspnButton`)** — same shape, platform word swapped. Note: the header comments in `sendInEspn.ts:2` / `SendInEspnButton.tsx:21` still claim the flag is absent — they are stale; the flag file is authoritative. · Fleaflicker and flag-off platforms only → Copy-trade variant (12): "Both sides said yes. Copy the trade and post it in your league." A platform mismatch is a false statement; if unresolvable, suppress.
- **Action:** tap Send/Copy. **adoptionEvent / retirement:** the send-attempt family — `sleeper_send_attempted` exists (`SendInSleeperButton.tsx:358`; `:252` is `sleeper_send_failed`); **MFL and ESPN attempt events are both NEW** (neither button tracks anything today — §5.3.1/D1); until they ship, retirement on those platforms fails closed. `retireAfter: {send_attempt_family, 1}`, `maxDisplayCount: 2`. (Client emits no `trade_sent`; the beat teaches the verb, so attempt is the honest receipt.) **Owning flag:** `trade.send_in_sleeper` is the master kill switch — with it off, **no** send control renders on any platform (`SendInSleeperButton.tsx:454`), so `N3` and `N6.2` carry it as a trigger precondition (fail closed) or their degrade lines become false statements.
- **Collision:** `PushPrimingModal` triggers on the same first-mutual-match moment. `N3` wins via FR-E4's mechanism (root modals check `useGuide.active`); the push ask defers to next mount, where "tell me when they respond" framing is strictly better. M4 monitors starvation.
- **Risk carried:** send is a flagged beta; the beat fires only where the platform branch sends or renders Copy-trade with a stated reason. **ESPN build precondition:** `_comment_espn_send` (`features.json:64`) records that `espn.send` requires a build ≥103 (`feat/send-auth-lazy`) — below that, the ESPN send dead-ends for public-league users with no in-flow sign-in. Phase 2 ships a later binary, so this is satisfied by construction, but the line stays here because a dead-ending taught control is exactly R5. **Stale-comment cleanup (build task):** `sendInEspn.ts:2`, `SendInEspnButton.tsx:21`, and `SendInSleeperButton.tsx:110-112/:428-430` all still claim `espn.send` is absent/off — the flag file is authoritative; fix the comments during build.

**`N5` — Where you stand** *(seed #4)* — Phase 2
- **Trigger:** boundary — first League-tab entry in session ≥2, AND content gates: league has ≥3 members with rankings coverage, AND `league.pos_candidates` on (owning flag; the pin clause of the drill-in additionally requires `league.player_trade_handoff` — both currently true, and `features.json:143` names them the kill switches), AND the coverage payload has a median for ≥1 position (suppress on `no_median`/`no_split` — `LeagueSummaryScreen.tsx:922`).
- **Surface:** spotlight the position-filter pill row on `LeagueRankings` (**new registration**; note the basis chip already carries `league-summary.basis.personal` at `:1432` but the pill row is the correct target for this copy — the registration cost is accepted).
- **Copy (11):** "Filter one position — I'll split the league into buyers and sellers."
- **Action:** tap a pill → the shipped median divider draws (`league-summary.median-divider`, `:2085`); drill-ins carry Offer/Target pins.
- **adoptionEvent / retirement:** `league_pos_candidates_viewed` *(EXISTS — fires at `:920`)*; `retireAfter: {league_pos_candidates_viewed, 1}`, `maxDisplayCount: 2`.
- **Copy must not imply a finished board pre-Phase-B.**

**Phase-B-gated (not in this release): the progress beat.** Once `grade_count`/`grade_required` ship and the chip renders progress: "Every swipe is a valuation. Your board is building itself." Condition: chip verified rendering progress on-device.

**Candidate held out (first Phase-4 item): the bad-card flag beat** (after 3 consecutive passes, teach the bad-trade flag — converting a trust-damaging card into a calibration signal).

### 5.3.1 Event inventory (Phase-0 exit gate)

Every retirement/adoption/invalidation event above, with its verified state. **NEW = taxonomy row + emitter + post-deploy read-back required in Phase 0** (FR-E8). No beat builds until its rows are green — and "green" is evidenced, not asserted: the Phase-0 exit adds a read-back artifact column to this table (path + date of the `user_events` query proving each name and prop survived ingestion).

| Event | Used by | State (dual-agent verified, rounds 2–4) |
|---|---|---|
| `guide_step_shown` / `_advanced` / `_skipped` | exposure, M1–M2 | EXISTS, registered; `spotlight` prop is NEW |
| `guide_tour_reenabled` | FR-E10 | Emitted (`useGuide.ts:134`), **unregistered** — register or remove |
| `guide_step_suppressed` | FR-E5, M4 | NEW |
| `find_trades_tapped{source:'prefs_changed_strip'}` | N2 adoption | EXISTS — event + `source` prop registered (`analytics_taxonomy.py:417`, registered 2026-08-11 per `TradesScreen.tsx:775-777`), emitted via `handleFindTrades('prefs_changed_strip')` at `TradesScreen.tsx:3712/:773-780`. Receipt requires `trades.edit_full_sheet` + `trades.finder_hub` (strip gated on `consolidateOn`, `TradesScreen.tsx:572/:3707`). **Do not use `deck_regenerated` here:** its prop allowlist is `{position, new_trades}` only (`analytics_taxonomy.py:596`) and its sole emitter (`TradesScreen.tsx:2699`) is armed only by the QuickSet-return path — the round-3 review caught this exact splice |
| `outlook_saved` | N2 retirement | NEW — emit from the DNA sheet save path |
| `finder_target_pinned` | N4 | NEW — emit from the targeting board pin handler |
| `league_pos_candidates_viewed` | N5 | EXISTS — `LeagueSummaryScreen.tsx:920` |
| `league_candidate_pinned` | (optional N5 secondary) | EXISTS — `:1086` |
| `sleeper_send_attempted` / `_failed` | N3, N6.1 adoption, N6.2 | EXIST on client (`sleeper_send_attempted` at `SendInSleeperButton.tsx:358`, `_failed` at `:252`; registered `surface` prop includes `'awaiting'` — `analytics_taxonomy.py:530-531`); **`trade_sent` never fires from the client** — do not reference it. **MFL and ESPN attempt events: both NEW** (round-6 verified — `SendInMflButton.tsx` and `SendInEspnButton.tsx` contain zero `track()` calls and no `mfl_send*`/`espn_send*` name exists in mobile or the taxonomy; the send-attempt family is Sleeper-only today). Until they ship, N3/N6.2 retirement on non-Sleeper leagues fails closed |
| `quickset_completed` | s3.2 adoption; N1/s3.2 invalidation | EXISTS — registered (`analytics_taxonomy.py:280`) |
| `quickset_started` | N1 adoption | **NEW** — zero repo hits (round-3 verified); taxonomy row + emitter required |
| `awaiting_segment_viewed` | N6.1 funnel step (NOT its adoption event — §5.3) | **NEW** — zero repo hits (round-5 verified); taxonomy row + emitter on awaiting-segment mount. Note: the swipe response's `{matched, match_id}` (`TradesScreen.tsx:1548`) answers the matured-into-match half of N6.1's gate locally — no fetch needed for that branch |
| trio client receipt | N7 adoption/retirement; `rankLadder.methodsTried` | **NEW — and a named trap:** the registered `trio_swipe` (`analytics_taxonomy.py:278`) is emitted **server-side only** (`server.py:~6019`); the client can never observe it, so wiring `retireAfter` to it means N7 never retires (the FR-E3 worse-than-none case). Client emits only `trio_session_started` (`RankScreen.tsx:92`) and `trio_entry_tapped` (`TradesScreen.tsx:5111`) — **neither registered**. Required: a NEW registered client emitter on trio submit (or a persisted local `trioVoted` flag) for both trigger and retirement |
| `tiers_saved` | N1/s3.2 invalidation | In code (44 files) but **no taxonomy row** — register if used |
| `ranks_imported`, `all_positions_ranked`, `account_verified` | invalidations | NEW (no emitter anywhere) — build or drop from the step definitions |

### 5.4 States & edge cases

| State | Required behavior |
|---|---|
| No leagues (`acct_`-only session) | No league-dependent beat fires; `no_league` sentinel + content gates fail closed |
| Single league | `s1.1` never fires; `league_autoskip` trap documented |
| Deck exhausted | Summary card owns the slot; `N4` rides it; pin line omitted if any owning flag off. **Declared non-fire:** a returning user landing on an already-exhausted deck with zero dispositions this session gets the legacy branch, not the summary card — `N4` correctly does not fire (its "Cleared the market" copy would be false); do not "fix" this at QA |
| Owning feature flag pulled mid-season | Beat's trigger precondition fails closed — the guide never teaches a surface that no longer renders (runbook lists guide preconditions per flag) |
| Target-measure failure | `degradeLine` or suppress + `spotlight:'degraded'`; degraded still counts as shown and advances |
| Target in a `<Modal>` | Unbuildable (NG-11); beats target entry points |
| Mid-guide app kill | `guideSeen` written on advance/skip only → shown re-fires next launch (correct); M1 deduplicates |
| Backgrounded mid-beat | Re-offer at same gate on foreground; verify no auto-replay of completed steps in Phase 0 |
| Returning v1 user | FR-E9: ≤1 v2 beat, boundary-only, no seen-state cleared |
| `guideDismissed` | FR-E10: zero steps incl. upgrades; Settings-only reversal |
| Two beats eligible | Single slot, first-come (FR-E4); loser deferred + logged; retries on free |
| Root modal vs live bubble | FR-E4 mechanism; zero occurrences in Maestro runs |
| First like returns `matched === true` (like matured instantly) | `N6.1` **suppresses** — and the suppression path writes `guideSeen['n6.1'] = true` and emits `guide_step_suppressed{step:'n6.1', blocked_by:'matched'}` with **no** `guide_step_shown` (§5.3), consuming the moment. In Phase 1 (N3 not yet shipped) the user gets no beat at that moment — accepted; the match UI itself is the payoff |
| Awaiting fetch empty (counterparty unresolvable from the cached roster index → row dropped by `load_awaiting_trades`) or failed/timed out | `N6.1` shows the **router-less variant** (§5.3) — the user is never routed into "No pending trades" one tap after being told their like is logged. The gate is the `swipeMutation.onSuccess`-issued `['awaiting-trades']` fetch, never a like-time prefetch. `N6.2` additionally suppresses on an empty list |
| Deep-link arrival | Beats fire on own predicates; landed-screen beats take the degrade path if targets haven't registered |
| League switch mid-tour | League-scoped beats re-evaluate; pins self-clear on switch → `N4` may legitimately re-arm |
| Redraft league | `N1` suppressed; `s2.1` bounded by the redraft label; `s3.2` fires on "N1 seen **or ineligible**" so the Quick Set chain survives for redraft-only users |
| Demo / guest session | All beats suppressed |
| Non-Sleeper league | `N3` platform resolution or suppress |
| Sleeper down / 404 | `s0.err-*`; no beat fires on an error screen |
| VoiceOver / Reduce Motion | §5.5 |

### 5.5 Non-functional requirements

- **NFR-1 Performance:** p95 trigger→bubble ≤400 ms; measurement stays promise-wrapped `measureInWindow` with the 250 ms ceiling; no host-screen re-render on activation; no re-parenting or forced scroll.
- **NFR-2 Accessibility:** announce lines via `AccessibilityInfo.announceForAccessibility` (not done today); degrade path leaves no hint naming an invisible target; ✕/opt-out targets ≥44pt; Reduce Motion skips the spring; scrim doesn't trap VoiceOver.
- **NFR-3 No-OTA:** copy ships frozen in a binary. The §5.2/§5.3 lines are the drafting targets; the mkt-writer voice pass finalizes; the operator approves the freeze (D9). Phase 3 is the structural fix.
- **NFR-4 Maestro:** assertion flows (today only `guide-no-false-signoff@release.yaml` asserts) per new beat + never-trap paths + the FR-E4 no-modal-over-bubble check; new `testID` registrations (outlook receipt, match send control, league pill row, `N4` pin CTA) pass `testid-lint.sh`.
- **NFR-5 Design system:** Chalkline tokens only; `N4` extends the existing summary card so it reads as content.
- **NFR-6 Privacy:** no player names or league identifiers in guide events.

---

## 6. Scope & Phasing

**The phase boundary is a gate, not a schedule.**

| Phase | Contents | Exit gate |
|---|---|---|
| **0 — Engine & honesty** (no new beats) | FR-E1…E11; §5.3.1 event inventory (taxonomy rows, emitters, read-back); copy+timing pass over v1 (targets in §5.2); degrade-line pass; phantom steps + `s7.1` cut; kill-switch semantics corrected; arbiter mechanism landed | Structural test green in CI; G-1 reachability table (fires AND mounts) with zero failing rows; event inventory all green; operator TestFlight walk under the pinned flag set |
| **1 — Four beats (TradesScreen-anchored)** | `N1`, `N2` (two-form), `N4` (summary-card extension + pin hand-off UI delta), `N6.1` (first-like router — CTA navigation, no new spotlight; its funnel emitter `awaiting_segment_viewed` lands on MatchesScreen, so that file is in the Phase-1 set), the `s8.1` predicate rewire, the like-handler sequencing rewrite (§5.2 `s6.2` row), plus the amended `s3.2` chain | M3 <5%; M1 ≥0.60 on operator walk + first staged cohort; no M5 rise; §4.3 series within thresholds; painted-door read on `N2` |
| **2 — Cross-screen beats + ladder rung 1** | `N6.2` (awaiting-segment send spotlight), `N3` (the separate match walkthrough, platform-resolved), `N5` (content-gated), `N7` (Trios rung — summary-card CTA); durable cross-session trigger state; Matches/League target registrations; Maestro fixtures (seeded awaiting trade; seeded mutual match; seeded multi-team league) | Same bars, per beat |
| **3 — Server-delivered script** | Step table as JSON from the existing Flask flag surface; client keeps render primitives; compiled-in script the permanent fallback; unknown step types skipped by old clients | Only if the beat roadmap exceeds ~2 further beats (OQ-5); adds a route → api-reference + HLD rows |
| **Phase-B-gated** | The progress beat | Phase B merged + chip verified on-device |

**Cut list** (revival needs the citation overturned): trade calculator walkthrough; notification-inbox step; portfolio; multi-league switcher (defer); `s7.1` as pushed beat; everything in §3.2.

---

## 7. Dependencies & Risks

### 7.1 Dependencies

| # | Dependency | State | If it slips |
|---|---|---|---|
| D1 | §5.3.1 event inventory: taxonomy rows + **new emitters** (`outlook_saved`, `finder_target_pinned`, `quickset_started`, `awaiting_segment_viewed`, trio client receipt, **MFL and ESPN send-attempt — both NEW, neither button tracks anything today**, `guide_step_suppressed`, `spotlight` prop) + read-back artifacts | backend + mobile | **Hard blocker** — beats never retire and M6 joins on nothing |
| D2 | New registrations/`testID`s: outlook receipt, league pill row, **`N4` pin CTA + mode hand-off** (small UI delta), **per-instance platform-agnostic send-control registration `trades.send-control.guide`** for N6.2 **and** N3 — mounted on **whichever router branch actually renders** (the raw `trades.send-sleeper-btn` testID is per-testID last-mount-wins across every card, *and* `SendInSleeperButton` early-returns to MFL/ESPN/copy-trade before its own Sleeper button, so a Sleeper-pinned id covers Sleeper only), **N6 chain route param** on MatchesScreen, **`onComplete(via)` guide-step hook** (new engine surface: fires on advance / cta-dismiss / skip / ✕ / swipe-dismiss / timeout — the s6.2/Apple chain hangs off it), **summary-card button-budget change** (§5.3) | mobile | Beats unbuildable/un-assertable |
| D3 | Structural CI test + copy lint | mobile/CI | FR-E2/E3/E7 unenforced |
| D4 | `feat/open-access-phase-a` coordination (same flags/files) | unmerged, separately owned | FR-E1 designed not to require it (OQ-6); re-diff before build |
| D5 | Open-access Phase B (`grade_count`) | designed, unbuilt | Progress beat doesn't ship; calibration line stands |
| D6 | Maestro assertion flows + fixtures | eng-qa | Project gate: flow delta or written waiver |
| D7 | Feature scope block + tracking plan rows before build | convention | Build does not start — analytics + flag surface = bright line, **not express-eligible** |
| D8 | Pre-ship sim gate Tier 1 + TEST_LEDGER + `qa/sim-runs/last-sim-run.json` | eng-qa | Cannot merge |
| D9 | **Copy freeze:** mkt-writer voice pass over §5.2/§5.3 targets, operator approval, frozen before build | operator + mkt-writer | No-OTA means a second authoring round costs a binary |

### 7.2 Risks (each with handling)

| # | Risk | Sev | Handling |
|---|---|---|---|
| R1 | Bad first card + emphatic tour copy = durable expert-trust damage (measured insult rate 1.48%/3.70%) | High | `s2.1` de-risked; `N1` calibration-framed; honest-null `s5.0` retained; deck-eval stays a ship gate for any beat vouching for card quality; bad-card-flag beat named for Phase 4; confidence-gating the first deck = OQ-3 |
| R2 | A beat silently dropped, nobody knows | High | FR-E5 + M4 |
| R3 | Deictic copy pointing at nothing (already live via `s7.1`) | High | FR-E6 contract + M3 <5% split by platform; fix is a registry gate, not a longer timeout |
| R4 | New event names dropped behind a 200 (third occurrence) | High | FR-E8 + read-back per name |
| R5 | Teaching a verb the product lacks, or a promise the code doesn't keep | High | NG-1/NG-2; platform-resolved `N3`; owning-flag preconditions; §5.3.1 gate |
| R6 | Guide vs push primer race | Med | FR-E4 named mechanism (root modals read `useGuide.active`); M4 monitors |
| R7 | Returning users bubbled after "that's the tour" | Med | FR-E9 |
| R8 | Copy frozen between binaries | Med | D9 freeze + Phase 3 |
| R9 | Over-firing (Aleven's 72%) | Med | Trigger/budget separation + M8 |
| R10 | Scope creep back to a longer tour | Med | Beat count is a budget: adding one retires one, in the scope block. **Amended by operator direction 2026-08-15:** O-1/O-5 added `N6` (which retires `s6.1`) and `N7` + the ladder policy (which caps ranking nudges at one per session) — the per-session interrupt budget (M8) is unchanged, which is the constraint that matters |
| R11 | M6 over-interpreted as causal | Med | Inline unremovable caveat; readouts include "what this cannot tell us" or are rejected |
| R12 | The layer ships on vibes | Accepted | Correctness controls (structural test, assertion flows, operator walk, self-retirement, §4.3 trip wires) substitute for effectiveness evidence at N=156 — stated, not hidden |

---

## 8. Rollout & Measurement

**Unit: device** (matches `onboarding_v2_rollout` precedent; works pre-sign-in; deterministic two-stage SHA-256; device+account merged on flag fetch).

**Flags:** `onboarding.v2` (master) · `onboarding.guided_avatar` (single gate post-FR-E1) · **`onboarding.guide_v2`** (new; gates eligibility layer, arbiter membership, new beats; off = byte-identical to today — that is the rollback). No per-step flags.

**Stages:**
1. **Operator device** via `config/tester_allowlist.json` (`device:` prefix); verify with unauthenticated `GET /api/feature-flags` + `X-Device-Id` **before touching the phone**. Walk all beats on a fresh install, a v1-upgrade install, AND a `guideDismissed` install (expect zero bubbles).
2. **TestFlight testers:** Maestro tier green; no M5 rise over 3 days; qualitative read of guide-mentioning feedback.
3. **Weekly device cohorts** (rollback = experiment → `stopped`; note `stopped` is one-way — save the row first; `validate_spec` rejects bucket overlap in the occupied `onboarding` layer).
4. **Default-on** after Phase-1 exit gates.

**Variant-attribution footgun, named:** `stamp_for_event` covers no `guide_*` event → `user_events.experiments` is NULL for the tour unless the experiment declares scope on SignIn/Trades/Matches/League screens; declare it, or join `experiment_exposed` on the unit. Into the scope block.

**Readout cadence:** one page per cohort, fixed template — M1–M8, §4.3 series vs thresholds, M6 with inline caveat, painted-door read, and an explicit **"what this cannot tell us"** line (absent = readout rejected). Plus the qualitative gate: feedback backlog classified *missing* vs *exists-but-not-found*.

**Quarterly review:** only steps that failed to self-terminate surface, with a named owner.

---

## 9. Open questions for the operator

| # | Question | Default assumed |
|---|---|---|
| OQ-1 | ~~Rankings copy framing~~ | **RESOLVED (O-3, 2026-08-15):** calibration framing confirmed; effortlessness promise waits for Phase B |
| OQ-2 | ~~Seed #1's teaching shape~~ | **RESOLVED (O-1, 2026-08-15):** teach like → "Awaiting them" → optional send (`N6`), match walkthrough separate (`N3`). Building mobile accept/decline remains open **feature** work (NEXT.md item), outside this PRD |
| OQ-3 | Confidence-gate the *first* deck (engine decision, out of scope here)? | Logged only |
| OQ-4 | Exhausted-deck rule: summary card owns the slot, `N4` extends it, `s7.1` cut — confirm | As drafted |
| OQ-5 | Phase 3 server script: build after Phase 2, or only when the roadmap grows? | Only if >~2 further beats |
| OQ-6 | If `feat/open-access-phase-a` doesn't land this cycle, ship Phase 0 alone? | Yes |
| OQ-7 | Kill-switch fallback: flip passive flags in the runbook entry, or delete the claim? | Flip the flags |
| OQ-8 | Full gates confirmed (analytics + flags = bright line)? | Full gates |

## 10. Docs rows (per feature gates)

| Doc | Row |
|---|---|
| `docs/api-reference.md` | n/a unless Phase 3 |
| `docs/config-reference.md` | `onboarding.guide_v2`; §5.3.1 taxonomy entries |
| `docs/cross-client-invariants.md` | n/a — guide is mobile-only |
| `living-memory/LLD.md` | `GuideStep` required-fields convention |
| `docs/architecture.md` / HLD | n/a unless Phase 3 |
| `docs/glossary.md` | "beat", "retirement condition", "degrade line" |
| `docs/runbook.md` | Corrected kill-switch semantics; guide flag-preconditions list; staged-rollout recipe |
| `docs/plans/onboarding-conversion/guided-avatar-script.md` | Superseded; phantom steps + `s7.1` deleted |
