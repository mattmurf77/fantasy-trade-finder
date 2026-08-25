# FB-397/#398 — Reconciliation log

## Round 1 (plan → author), 2026-08-24

Author deltas from the planner's plan.md, accepted: guard case IDs renamed **11n/11o (+11p/11q)** — the plan's proposed 11i/11j already exist as the overlap/inset invariant sweep (`mobile/tests/check-guide-spotlight-tracking.js:1086, 1091`); re-arm path restated as the Settings guided-tour toggle rather than "Settings → About" prose. (See prd.md §6 drift note.)

## Round 2 (critic re-audit), 2026-08-24 — verdict: NOT-READY (1 blocking)

Critic re-read prd.md / scope.md / status.md from disk and re-verified every load-bearing claim at file:line.

### BLOCKING

**B-1 — The TestFlight re-arm path cannot re-fire s2.2, so §6c steps 2–3 are unverifiable as written.**
The checklist's step 1 (Settings guided-tour toggle → `enableTour` → `resetGuideProgress`/`resetGuideProgressV2`) clears `guideDismissed`/`guideSeen`/`guideTourCompleted`(/display counts) **but never `firstSwipeDone`** (`mobile/src/state/useOnboardingState.ts:180–192, 209–229`; the field defaults at :86 and is untouched by both resets). Both beats in the checklist are gated on first-run state:
- s2.1's request effect bails unless `firstRun` (`mobile/src/screens/TradesScreen.tsx:3293`), where `firstRun = onboarding.trades_first && hydrated && !firstSwipeDone`, latched at mount (:433–440);
- s2.2's chain condition additionally requires `!ob.firstSwipeDone` (:3316).

On the operator's device `firstSwipeDone` has been true for months, so after the toggle re-arm **neither s2.1 nor s2.2 ever renders** — the checklist would report a false regression (or the operator gives up). The fix that stays in scope: rewrite §6c step 1 to use the operator QA tooling that already resets this state — Settings → Testing → **Factory reset** (`TestStagesScreen.tsx:186–189` → `replaceOnboardingState({})`, a full defaults replace that clears `firstSwipeDone`, `useOnboardingState.ts:231–234`) or a stage-user swap (:229). That is almost certainly how the operator reached the beat on build 129 in the first place. Do **not** "fix" this by making `enableTour` clear `firstSwipeDone` — that changes #187 product semantics and is out of scope.

Riding correction (same edit): the PRD cites the toggle at `SettingsScreen.tsx:924`, which is the **flag-off flat-list screen**; `account.settings_hub` is `true` (`config/features.json:169`), so the live mount is `settings/sections/GuideSection.tsx:54` inside Settings → **About** (`settings/SettingsAboutScreen.tsx:32, 39`). The toggle stays useful in the checklist only as the un-dismiss lever if the operator previously hit "Skip the tour" (`guideDismissed`), not as the re-arm.

### NON-BLOCKING

**N-1 — R-3's "byte-identical" is prose overshoot; the mechanical proxy is fine.** The 4-arg path's mechanical check exists and is real: 11d–11h fixed-point cases plus the 11i/11j invariant sweep *execute* the lifted solver with four args (`check-guide-spotlight-tracking.js:1022–1096`). That is sampled-behavior equivalence, not bytes. Suggest R-3 say "behaviorally unchanged, pinned by 11d–11j" so nobody later claims a stronger guarantee than the guard delivers.

**N-2 — Small-window acceptance bound missing.** R-2 is unambiguous (always pin, no clamp specced — two engineers converge; `insets` is the solver's existing param, sourced from `useSafeAreaInsets`, `AnalystGuide.tsx:109`). But §6c step 3's "bubble nowhere over the card" can fail *per-spec*: at max Dynamic Type / the taller ram sprite (`bandH ≳ 180`), `wantTop = insets.top + BAND_EDGE + bandH + BAND_GAP ≥ ~259` can exceed the deck's resting `frame.y` (~240–290) with the ScrollView already at offset 0 — the band may graze the ring's top border by a few points. Soften step 3 to "Pass/Like row fully visible; at most a minor graze of the ring's top edge at max text size" so a correct build can't fail the checklist. (Recomputed: after a successful scroll, ring top sits 4 pt below the band — the 8 pt cutout pad minus nothing — so the nominal case is clean; verified against `AnalystGuide.tsx:231, 240` and the cutout pad at :344–347.)

**N-3 — Group D disjointness confirmed; PRD should state it, not just mandate serialization.** Group B's guard additions live entirely inside rule 11's block (executable cases in the lifted-solver region ~:1022–1096, structural 11p/11q alongside 11k–11m, ending :1136). Group D extends rule 12/12a's host list, a separate block at :1138–1172 (currently `TradeCalculatorScreen` only). The regions are disjoint, adjacent — a textual conflict is only possible if Group D restructures the rule-12 header. Add one sentence to prd.md §5 recording this.

**N-4 — Sabotage mappings re-audited: all five sound; one tightening.** Sabotages 1/2 depend on 11f being the exact 4-arg twin of 11n's input — verified: `{top:80, height:700}`, `BAND=180` (:1046–1052). Sabotage 3 (unconditional pin) reddens 11d, 11f, and the 11i overlap sweep (offset 67 vs e.g. `c.top=100`: neither above nor below → overlap recorded); 11j correctly stays green (67 ≮ 67) and the PRD rightly doesn't claim it. The silent-no-op chain is closed end-to-end: solver honors pin (11n/11o, executed) → call site passes `active.band` (11q) → s2_2 declares it (11p) → render anchors from the SOLVED offset (existing 11k/11l, :1110–1122) → a missing `GuideStep.band` field fails strict `tsc`. Tightening: implement 11q as "5th argument referencing `active.band` **inside the `solveBandPlacement` CallExpression**" (the PRD's own self-satisfaction note already requires this — carry it into the assertion, not just the note).

**N-5 — scope.md §5 CI claim verified TRUE; a stale doc elsewhere says otherwise.** The critic initially suspected the "mobile-typecheck runs the check-*.js suites" claim, but `.github/workflows/ci.yml:47` does loop `node tests/check-*.js` in the mobile job — the extended guard WILL gate CI. The root `CLAUDE.md` line "the mobile/tests/check-*.js structural suites … gate nothing yet" is stale; flagged separately, not this item's scope.

**N-6 — scope.md analytics answer verified honest.** `guide_step_shown` (`useGuide.ts:279, 447`), `guide_step_advanced` (:480), `guide_step_skipped` (:491) exist as cited; no property changes; placement is render-only — answer (b) stands.

**N-7 — R-8 doc row: also amend the quoted signature.** The `AnalystGuide` row in `mobile/src/components/CLAUDE.md` (:70) quotes `solveBandPlacement(cutout, bandH, winH, insets)` verbatim; the "one clause" update should include the 5th param so the row doesn't half-describe the function it names.

### Verified intact (no objection)

- R-1/R-2/R-5 contracts unambiguous incl. null-cutout (11o) and where insets is read.
- Guard numbering claim (11a–11m exist, :985–1133; 11n–11q free) — correct.
- `onboarding.guided_avatar` and `onboarding.guide_v2` both true (`config/features.json:109, 112`) — the v2 measured-spotlight path in the code-walk is the live path.
- s2.2 carries no `retireAfter`, so `resetGuideProgressV2`'s retired-beat carve-out does not block its `guideSeen` clear — B-1 is solely `firstSwipeDone`.
- TradesScreen read-only stance and Group A boundary — consistent across all three docs.

## Round 3 (2026-08-24) — resolutions (applied by the orchestrator; the Author agent was repeatedly killed by a server-side 529 outage after Round 2, with no Round-3 edits landed)

- **B-1 (BLOCKING) — RESOLVED.** §1 repro step 1 and §6c step 1 rewritten: re-arm requires first-run state via Settings → Testing → Test stages → **Factory reset** (`replaceOnboardingState({})`, clears `firstSwipeDone`) or a stage-user spawn; the Guided-tour toggle documented as the un-dismiss lever only. Added the feasibility branch the critic's fix needed but did not spell: the Test-stages row is gated on `testing.stage_users` (false in features.json, delivered per-device via experiment overlay) — if absent, flip the flag + hot reload for the QA window per the flag's own comment, flip back after. Toggle citation corrected to `GuideSection.tsx:54` (Settings → About); `SettingsScreen.tsx:924` noted as the flag-off flat list. `enableTour` is NOT modified (the critic's out-of-scope ruling on #187 semantics stands).
- **N-1 — RESOLVED.** R-3 now reads "behaviorally unchanged, pinned by 11d–11j" with the sampled-equivalence caveat.
- **N-2 — RESOLVED.** §6c step 3 gains the max-Dynamic-Type acceptance bound (minor top-edge ring graze OK; never over card content/disposition row).
- **N-3 — RESOLVED.** §6a opens with the verified Group-D disjointness statement (rule 11 block ≤ :1136 vs rule 12 block :1138–1172).
- **N-4 — RESOLVED.** 11q's table row now requires the 5th-arg reference *inside the `solveBandPlacement` CallExpression*, matching the self-satisfaction note.
- **N-7 — RESOLVED.** R-8 also amends the quoted 4-arg signature in `mobile/src/components/CLAUDE.md:70`.
- N-5/N-6 were verification confirmations; no doc change required.

## Round 3 verdict

READY — the blocking objection resolved in place; contract R-1/R-2/R-4–R-7 untouched per the critic's "verified intact" list.
