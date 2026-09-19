# P0-8 + P0-9 — guided-tour sign-off gate, and first-session test prep

> **Status:** plan only (2026-08-10). No code changed by this document.
> **Worktree:** `ftf-p0-remediation`, branch `p0-remediation-2026-08-10`, from `origin/main @ ab9368f`.
> **Source findings:** `docs/business/product/2026-08-09-mobile-ux-audit/` — `04-priority-backlog.md` §P0-8/§P0-9, `06-resolutions.md` §P0-8/§P0-9, `07-build-handoff-prompt.md` §P0-8/§P0-9.
> **Split:** P0-8 is a **build**. P0-9 is **test prep only** — every `onboarding.*` sub-flag stays at its `config/features.json` default. Nothing in this plan flips a default.

## Contents

- [1. Verified current state](#1-verified-current-state)
- [2. P0-8 design + behavior matrix](#2-p0-8-design--behavior-matrix)
- [3. P0-9 validation checklist, test mechanism, fix policy](#3-p0-9-validation-checklist-test-mechanism-fix-policy)
- [4. Exact change list](#4-exact-change-list)
- [5. Surface changes](#5-surface-changes)
- [6. Maestro delta](#6-maestro-delta)
- [7. Docs impact table](#7-docs-impact-table)
- [8. Test plan](#8-test-plan)
- [9. Risks and open questions](#9-risks-and-open-questions)

---

## 1. Verified current state

Everything below was re-read in **this** worktree. Line numbers are current, not the audit's.

### 1.1 The machinery

| Thing | Location (this worktree) | Verified behavior |
|---|---|---|
| Tour engine | `mobile/src/state/useGuide.ts` | zustand store; `requestStep` refuses when a bubble is already active (`:93-94`) and when `step.once && guideSeen[id]` (`:92`) |
| `completeTour` | `useGuide.ts:137-141` | sets `guideTourCompleted`, fires `guide_tour_completed {steps_seen}` |
| `guidedAvatarActive()` | `useGuide.ts:76-81` | `onboardingEnabled('onboarding.guided_avatar') && !guideDismissed` |
| `onboardingEnabled` | `mobile/src/state/useFeatureFlags.ts:122-125` | `flags['onboarding.v2'] && flags[key]` |
| Script table | `mobile/src/components/analystScript.ts` | 20 entries in `S` (19 steps + `err_burst`) |
| Chain effect (fires s8.1) | `mobile/src/screens/TradesScreen.tsx:2416-2461` | s8.1 branch at **`:2456-2459`** |
| s8.1 gate today | `TradesScreen.tsx:2457` | `ob.guideSeen['s6.1'] && !ob.guideSeen['s8.1'] && !ob.guideTourCompleted` |
| s6.1 (first-like celebration) | `TradesScreen.tsx:3129-3136` | gated only on `guidedAvatarActive()` + `!celebrationsShown.first_like` |
| s8.1 → completeTour | `TradesScreen.tsx:2464-2469` | effect on `guideSeen['s8.1']` |
| `firstRun` latch | `TradesScreen.tsx:297-304` | **requires `onboarding.trades_first`** — this is the single choke point that kills the S2 block |
| `quicksetPromptOn` | `TradesScreen.tsx:253`, guard at `:2476` | requires `onboarding.quickset_prompt` — sole trigger for S3 |
| `appleSaveOn` | `TradesScreen.tsx:254`, guard at `:2682` | requires `onboarding.apple_save_moment` — sole trigger for S6.2 |
| `landingOn` | `SignInScreen.tsx:110` | requires `onboarding.landing` — sole trigger for S0 |

**The P0-8 mechanism, confirmed:** with today's flags, `s2.1` never fires (needs `firstRun` ⇒ `trades_first`), so `s2.2`/`s2.3` never fire (chained on `guideSeen['s2.1']` at `:2420`). The user's first like fires `s6.1` (`:3136`), which is `advance:'auto', autoMs:2200, once:true`. When it auto-advances, `guideSeen['s6.1']` is written and `active` becomes `null` — which re-runs the chain effect, whose **only satisfiable branch** is `:2457`, so `s8.1` fires ~2.2 s after the like and `completeTour()` follows. The user is told the tour is over having been taught exactly one line.

### 1.2 Flag values — `config/features.json` (today, unchanged by this plan)

```
onboarding.v2                = true    (master kill-switch)
onboarding.guided_avatar     = true
onboarding.landing           = false
onboarding.trades_first      = false
onboarding.quickset_prompt   = false
onboarding.league_autoskip   = false
onboarding.apple_save_moment = false
onboarding.share_sheet       = false
onboarding.rank_routing      = false
onboarding.demo_bridge       = false
onboarding.guided_layer      = false
onboarding.keep_warm         = false
landing.try_before_sync      = false   (NOT an onboarding.* key; still required — see §3.2)
experiments.engine           = true
analytics.client_events      = true
analytics.ingest             = true
```

### 1.3 Tour script inventory — all 20 entries × gating × reachable-today

`R` = release (today's `config/features.json`). `V2` = the `onboarding-v2` set (`backend/tests/fixtures/flags/onboarding-v2.json`, or the equivalent experiment overlay in §3.2).

| # | Step | Defined | Requested at | Effective gate | R | V2 | Capture |
|---|---|---|---|---|:-:|:-:|---|
| 1 | `s0.1` | `analystScript.ts:11-14` | `SignInScreen.tsx:113` | `landingOn` (`onboarding.landing`) + `guidedAvatarActive` | ✗ | ✓ | `s0-1.png` |
| 2 | `s0.2` | `:15-19` | `SignInScreen.tsx:117` (adv `:215`) | same | ✗ | ✓ | `s0-2.png` |
| 3 | `s0.err-notfound` | `:20-23` | `SignInScreen.tsx:312` | same + username lookup 404 | ✗ | ✓ | `s0-err-notfound.png` |
| 4 | `s0.err-down` | `:24-27` | `SignInScreen.tsx:312` | same + Sleeper 5xx | ✗ | ✓ | `s0-err-down.png` |
| 5 | `s1.1` | `:28-32` | `LeaguePickerScreen.tsx:117` (adv `:229`) | `guidedAvatarActive` **only**, + `cached.length >= 2` (`:116`) | **✓\*** | ✓\* | `s1-1.png` |
| 6 | `s2.wait` | `:33-38` | `TradesScreen.tsx:2399` | `firstRun` ⇒ **`onboarding.trades_first`** | ✗ | ✓ | `s2-wait.png` |
| 7 | `s2.1` | `:39-42` | `TradesScreen.tsx:2410` | `firstRun` | ✗ | ✓ | `s2-1.png` |
| 8 | `s2.2` | `:43-47` | `TradesScreen.tsx:2421` | chain: `guideSeen['s2.1']` ⇒ `trades_first` | ✗ | ✓ | `s2-2.png` |
| 9 | `s2.3` | `:48-52` | `TradesScreen.tsx:3013` | `guideSeen['s2.2']` | ✗ | ✓ | `s2-3.png` |
| 10 | `s3.1` | `:53-56` | `TradesScreen.tsx:2495` | `maybeShowQuicksetPrompt` ⇒ **`onboarding.quickset_prompt`** (`:2476`) | ✗ | ✓ | `s3-1.png` |
| 11 | `s3.2` | `:57-67` | `TradesScreen.tsx:2427` | `guidedS3Pending` ⇐ s3.1 path | ✗ | ✓ | `s3-2.png` |
| 12 | `s4.1` | `:68-71` | `QuickSetTiersScreen.tsx:113` | route param `onboardingReturn`, written only at `TradesScreen.tsx:2449` / `:2520` | ✗ | ✓ | `s4-1.png` |
| 13 | `s5.1` | `:72-75` | `TradesScreen.tsx:2571-2572` | `pendingRegenRef` ⇐ Quick Set return; **`fresh > 0`** | ✗ | ✓† | **MISSING** |
| 14 | `s5.0` | `:76-79` | same site | same; `fresh === 0` | ✗ | ✓† | `s5-0.png` |
| 15 | `s5.5` | `:80-88` | `TradesScreen.tsx:2444` | `guidedS55Done` ⇐ s5 fired | ✗ | ✓ | `s5-5.png` |
| 16 | `s6.1` | `:89-92` | `TradesScreen.tsx:3136` | `guidedAvatarActive` + first like | **✓** | ✓‡ | `s6-1.png` |
| 17 | `s6.2` | `:93-96` | `TradesScreen.tsx:3142` | `appleAskEligible` ⇒ **`onboarding.apple_save_moment`** (`:2682`) | ✗ | ✓ | **MISSING** |
| 18 | `s7.1` | `:97-101` | `TradesScreen.tsx:2640` (adv `:4895`) | `guidedAvatarActive` + `deckExhausted` | **✓** | ✓ | not captured |
| 19 | `s8.1` | `:102-105` | `TradesScreen.tsx:2458` | `guideSeen['s6.1']` | **✓** | ✓ | `s8-1.png` |
| 20 | `err.burst` | `:106-109` | **nowhere** | — | ✗ | ✗ | n/a |

\* `s1.1` needs ≥2 cached leagues, so it is invisible to a single-league user; the `fresh` capture profile has one league, which is why `s1-1.png` comes from `onboarding-leaguepicker@two-leagues.yaml`, not the tour flow.
† exactly one of `s5.1`/`s5.0` fires; which one is data-dependent.
‡ `s6.1` can be **swallowed** under V2 — see defect **D1** in §3.3.

**Reachable today: 4 of 20** — `s1.1` (two-league users only), `s6.1`, `s7.1`, `s8.1`. The audit graded this "nine of fifteen unreachable"; the true figure is stricter (16 of 20 unreachable, and only 3 of the 4 reachable beats are on the Trades screen). Three of the four reachable beats are reactive one-liners; none of them teaches anything.

**`err.burst` has zero call sites — confirmed.** `grep -rn "err\.burst\|err_burst" mobile/src/` returns only the definition at `analystScript.ts:106-109`.

### 1.4 What `onboarding.trades_first` and `onboarding.quickset_prompt` actually change

Not vague "trades-first experience" — these are the concrete code effects:

**`onboarding.trades_first`** (read via `onboardingEnabled`, so also requires `onboarding.v2`):
- `TradesScreen.tsx:297-304` — latches `firstRun` at mount. `firstRun` collapses first-run chrome (`:3531`, `:3542`, `:3556`, `:3567`, `:3634`, `:3685`, `:3709`, `:3735`, `:3795` all render `!firstRun`), shows the identity-confirm strip (`:3518`), and enables the first-run auto-generate (`:1398`).
- Gates the **entire S2 guided block** (`:2397`, `:2408`) and therefore, transitively, S2.2/S2.3/S3/S4/S5/S5.5.
- Gates the **ProvenanceChip** render (`:4427`) — the "CONSENSUS VALUES" label the tour's s2.3 line points at, and the evergreen Quick Set entry.
- One of three keys that enable onboarding swipe bookkeeping (`firstSwipeDone`, `totalSwipes`) at `:2996-3005`.
- Launch routing to the Acquire tab on first run lives in `TabNav.tsx` (audit cite `:208-237`) and keys off the same flag.

**`onboarding.quickset_prompt`**:
- `TradesScreen.tsx:2476` — the early return in `maybeShowQuicksetPrompt`. This is the **sole** trigger for the contextual ranking pitch (guided arm: s3.1 → s3.2 with in-bubble `Fix WR →` / `Not now`; unguided arm: the inline prompt card at `:4580`).
- `:4435` — makes the ProvenanceChip tappable as the evergreen Quick Set entry while the board is still consensus.

Neither flag reaches the backend. Both are client-read only.

---

## 2. P0-8 design + behavior matrix

### 2.1 The two candidate gates, evaluated

**Option A — minimum seen-step count.** Rejected, for three independent reasons:

1. **The only live count is not durable.** `useGuide.stepsSeenCount` (`useGuide.ts:87`, `:99`) is zustand in-memory state; it resets on every app launch. A threshold over it is satisfied or not depending on when the user backgrounded the app, which is not a property of whether they were taught anything.
2. **A durable count is unbuildable from what's persisted.** `guideSeen` only records steps declared `once: true`. Of the 19 real steps, `s0.err-*`, `s3.2`, `s5.1`, `s5.0`, `s5.5` and `s7.1` are **not** `once`, so a full guided tour that ended at s5.5 records only 7 keys while a release-flag user who signed in with two leagues records 3 (`s0.1`, `s0.2`, `s1.1`) having learned nothing. The count under-reports real tours and over-reports empty ones.
3. **`N` is arbitrary and drifts.** Any threshold is a magic number that silently changes meaning the next time a beat is added, removed, or has its `once` flag edited — exactly the kind of coupling that produced this bug.

**Option B — require the swipe-coaching beat.** Adopted. Gate `s8.1` on `ob.guideSeen['s2.2']`:

1. **Durable.** `guideSeen` is persisted in `ftf_onboarding_state` (`useOnboardingState.ts:47`) and merged, never cleared, except by the deliberate `resetGuideProgress()` behind the Settings re-enable toggle.
2. **Semantically exact.** `s2.2` is the tour's only `advance:'action'` teaching step: it points the spotlight at the card body, says *"Swipe right to take it, left to pass"*, and clears only when the user performs a real disposition. "The tour taught something" and "s2.2 was delivered and acted on" are the same proposition.
3. **Transitively correct.** `s2.2` is chained on `guideSeen['s2.1']` (`:2420`), which requires `firstRun`, which requires `onboarding.trades_first`. So the gate encodes "the trades-first opening actually ran" without naming a flag in the condition — the gate reads product state, not configuration, which is what keeps it correct under both configs.
4. **Zero magic numbers, one identifier.** It survives beats being added or removed.

**Decision: Option B.** `s8.1` fires only when `guideSeen['s2.2']` is set.

### 2.2 `err.burst` — delete

**Recommendation: delete** `err_burst` from `analystScript.ts:106-109`.

- Zero call sites, so deletion is behavior-preserving by construction.
- Its job is already assigned elsewhere. **P0-2 in this same remediation batch** builds the honest Trades error state — a named error with a working Retry, mirroring the Rank tab's pattern. A mascot bubble reading *"Something's broken on my end. Not your fault. Investigating."* competes with that state for the same moment and offers strictly less: no error name, no retry, and it dismisses on tap leaving no trace. Wiring `err.burst` would put two error surfaces on one failure.
- Wiring it would also blow past effort-S: a new failure surface needs its own Maestro coverage and, being `advance:'tap'` with no `once`, its own re-show policy.
- Nothing is lost as a design record — `docs/plans/onboarding-conversion/guided-avatar-script.md` remains the script's source of truth.
- The positive reason: after deletion every entry in `S` has a call site, which is what makes the inventory table in §1.3 trustworthy going forward.

### 2.3 Behavior matrix

The fix must be correct under both configurations. `✓` = correct, `✗` = the bug.

| # | Configuration | User path | `s2.2` seen | `s6.1` | `s8.1` today | `s8.1` **after fix** | `completeTour` after fix | Verdict |
|---|---|---|:-:|:-:|:-:|:-:|:-:|---|
| 1 | **Release** (today's defaults) | signs in, likes a card | never | shows | **fires ~2.2 s later ✗** | **never** | never | ✓ acceptance met |
| 2 | Release | signs in, exhausts deck without liking | never | not shown | never | never | never | ✓ unchanged |
| 3 | Release | likes, then exhausts deck (s7.1) | never | shows | fires ✗ | never | never | ✓ s7.1 still shows; no false sign-off |
| 4 | Release, 2+ leagues | s1.1 → like | never | shows | fires ✗ | never | never | ✓ |
| 5 | **onboarding-v2 set**, normal walk (pass, pass, Fix WR, Quick Set, s5.x, s5.5 "Later", like) | full tour | **yes** (swipe 1) | shows | fires ✓ | **fires, unchanged** | yes | ✓ no regression — this is the path `onboarding-tour@fresh.yaml` already walks end to end |
| 6 | onboarding-v2 set, user's **first** disposition is a like | s2.2 seen, s2.3 preempts s6.1 | yes | **swallowed** | never | never | never | ⚠ pre-existing defect **D1** (§3.3) — the fix neither causes nor cures it |
| 7 | onboarding-v2 set, user taps **"Skip tour"** at any beat | `guideDismissed` | maybe | n/a | n/a | n/a | n/a | ✓ `guidedAvatarActive()` false everywhere; unchanged |
| 8 | `onboarding.guided_avatar` off | passive surfaces / toasts | n/a | n/a | n/a | n/a | n/a | ✓ untouched |
| 9 | Settings toggle re-enable after a completed V2 tour | `resetGuideProgress()` clears `guideSeen` **and** `guideTourCompleted` (`useOnboardingState.ts:151-153`) | reset to no | replays | — | replays correctly | on re-completion | ✓ full-replay semantics preserved |

**Row 1 is the acceptance criterion**, and the fix satisfies it exactly: *a user who sees only the first-like celebration is never told the tour is complete.*

**Consequence of row 1 audited.** Under release, `guideTourCompleted` now never becomes true. Consumers were enumerated: `useGuide.ts` (writes it), `TradesScreen.tsx:2457`/`:2466` (the code being fixed), and `resetGuideProgress`. `SettingsScreen.tsx:112`/`:948-954` reads **`guideDismissed`**, not `guideTourCompleted`, so the Settings tour toggle is unaffected. `guidedAvatarActive()` reads `guideDismissed`. **Nothing else reads it.** The one observable change is that `guide_tour_completed` stops firing on the release path — which is the correct signal, because no tour is delivered there.

---

## 3. P0-9 validation checklist, test mechanism, fix policy

> **Flags stay OFF.** This section plans a *validation pass* and an *operator test mechanism*. No `config/features.json` value changes. The build agent runs the validation; this document says what to run and what counts as broken.

### 3.1 Validation checklist — the 13-beat tour under the onboarding-v2 set

**How to run it: the flow already exists.** `mobile/.maestro/capture/onboarding-tour@fresh.yaml` is tagged `# flags: onboarding-v2` and `# profile: fresh`, walks S0 → S8, and declares `# captures: s2-wait, s2-1, s2-2, s2-3, s3-1, s3-2, s4-1, s5-1, s5-0, s5-5, s6-1, s6-2, s8-1` — **that is the 13-beat tour**. `mobile/scripts/screen-capture.sh` reads the `# flags:` header (`:113`) and passes `--flags backend/tests/fixtures/flags/onboarding-v2.json` to `mobile/scripts/sim-run.sh`, which merges it over the profile's seeded map (`sim-run.sh:56-68`) and round-trips the pinned map through `/api/feature-flags` as a handshake (`:118-119`). So flag pinning is solved and needs no new machinery.

Do **not** author a duplicate tour flow. Run this one, plus `onboarding-signin@fresh.yaml` (S0) and `onboarding-leaguepicker@two-leagues.yaml` (S1.1).

Per beat, verify four things: **(a) reachable**, **(b) renders** (bubble + correct pose + spotlight target resolves where one is declared), **(c) advances** by its declared mechanism with no dead end (`guide.dismiss-tour` present, `guide.step-x` present), **(d) its analytics land** (`guide_step_shown` / `_advanced` / `_skipped` accepted by `backend/analytics_taxonomy.py`).

| Beat | Verify specifically | Status from the existing capture run |
|---|---|---|
| `s0.1`, `s0.2` | s0.2 advances on the real submit (`SignInScreen.tsx:215`), not on tap | captured ✓ |
| `s0.err-notfound`, `s0.err-down` | both branches at `SignInScreen.tsx:312` reachable; neither traps | captured ✓ |
| `s1.1` | needs ≥2 leagues (`LeaguePickerScreen.tsx:116`); confirm a **single-league** user is not left waiting on a beat that cannot fire | captured under `two-leagues` ✓ |
| `s2.wait` | the `running`/`isPending` window is real, not just harness-injected latency | captured ✓ (with injected latency — see risk R3) |
| `s2.1` | fires the moment the deck lands (`:2405-2413`) | captured ✓ |
| `s2.2` | spotlight resolves to `trades.card-body`; advances on a **real** disposition | captured ✓ |
| `s2.3` | fires immediately after s2.2 in the freed slot; spotlight resolves to `trades.provenance-chip`; the chip is actually rendered (`:4427`, needs `tradesFirstOn`) | captured ✓ |
| `s3.1` | trigger arithmetic at `:2482-2483` (first pass at ≥2 swipes, else ≥3) | captured ✓ |
| `s3.2` | both CTAs work: `Fix <pos> →` routes with `onboardingReturn:true`; `Not now` snoozes and does **not** trap | captured ✓ (accept path only — **verify the dismiss path**) |
| `s4.1` | fires on the onboarding-mode Quick Set mount (`QuickSetTiersScreen.tsx:112-113`) | captured ✓ |
| **`s5.1`** | **the payoff beat — currently UNPROVEN.** See defect **D3** | **MISSING** |
| `s5.0` | the honest-null branch | captured ✓ |
| `s5.5` | leverage ordering from `nextUnrankedPosition` (`analystScript.ts:115-118`); `Rank <next> →` routes, `Later` does not trap | captured ✓ |
| `s6.1` | fires on first like; **check the swallow case** — defect **D1** | captured ✓ (only when the like is not the first disposition) |
| **`s6.2`** | Apple setup line + the 2400/2800 ms handoff to the system sheet (`:3140-3147`) | **MISSING** — the conditional block did not fire |
| `s7.1` | needs a deck exhausted to a nondeterministic length; spotlight `trades.trio-entry`; advances at `:4895` | never captured |
| `s8.1` | **fires only after s2.2 (post-P0-8-fix)**; `completeTour()` follows | captured ✓ |

**Interaction with the P0-8 fix — verify explicitly:** in the V2 arm, `s2.2` is always seen before `s6.1` on the normal walk, so `s8.1` must still fire. Row 5 of the §2.3 matrix is the assertion; the existing capture flow proves it end to end (its `s2-2.png` and `s8-1.png` come from one run). Re-run it after the fix and confirm `s8-1.png` is still produced.

### 3.2 Test mechanism for the operator — **already works, zero code needed**

The overlay path exists and is exactly the `onboarding_v2_rollout` precedent. Verified end to end:

1. **Server side.** `GET /api/feature-flags` (`backend/server.py:17271-17333`) returns `{flags, experiments, configs}`. `flags` is the **global** `flags_dict()` — an experiment does *not* mutate it. Per-unit values ride in `configs`, populated by `experiments.resolve_for_unit` (`backend/experiments.py:320-342`), which returns the matched variant's `client_config` verbatim.
2. **Client side.** `mobile/src/api/flags.ts` `loadFeatureFlags` merges every `configs[*].flags` **over** the global map and returns the merged result; its own comment names this use case — *"the onboarding rollout turning onboarding.\* on for targeted units only"*. The store caches the **merged** map under `feature_flags_v1`, so the treatment survives offline boots and reconciles on the next fetch.
3. **Storage is verbatim.** `create_experiment` writes `variants_json=json.dumps(spec["variants"])` (`experiments.py:507`); `validate_spec` inspects `model_overlay` but never touches `client_config`, so the flag overlay passes through unmodified.
4. **Targeting.** `is_tester_allowlist` is registered for **both** account and device units (`experiments.py:53`) and resolves from `config/tester_allowlist.json` ∪ `FTF_TESTER_ALLOWLIST` (`:120-135`) — the file exists because **Render does not apply `render.yaml` envVars to a dashboard-created service** (observed 2026-07-19).
5. **Constraints that will reject a wrong spec** — all verified in `validate_spec`:
   - `layer: "onboarding"` **requires** `unit_type: "device"` (`:471-472`). Use device.
   - `bucket_start:0, bucket_end:10000` with weights `control:0 / treatment:10000` ⇒ a targeted unit is *always* treatment (the `aggregate_tier_labels` / `onboarding_v2_rollout` shape).
   - `primary_metric` must be in `METRIC_CATALOG` — `activation_rate` fits.
   - `exposure_surface` is required and non-empty.
   - `experiments.engine` must be on — it already is (`true` in `config/features.json`).
6. **Prerequisite the operator must confirm:** `config/tester_allowlist.json` currently holds `["device:dev_loc-mrpy6qog-2t72t6", "313560442465169408"]`. Device pseudo-ids come from the client's `getDeviceId()` and can rotate on reinstall. **Before the test, confirm the current device id and add it if it changed** — this is a one-line edit to a git-deployed JSON file, and it is the only repo change the test needs.

**The overlay set.** Mirror `backend/tests/fixtures/flags/onboarding-v2.json`. Note two non-obvious entries, both already reasoned out in that fixture's `_comment_fixture`:

- **`landing.try_before_sync: true`** — not an `onboarding.*` key and **`false` globally**. It is the launch pairing `config/features.json`'s `_comment_onboarding` records: without it `/api/session/demo` 404s and the landing's demo link is a dead end. It must be in the overlay.
- **`onboarding.league_autoskip` stays `false`** — with it on, a single-league user skips the picker and `s1.1` becomes unreachable.

`onboarding.v2` and `onboarding.guided_avatar` are already `true` globally; including them in the overlay is harmless and makes the spec self-documenting.

**The recipe** (`CRON_SECRET` from `secrets.local.env`; do not paste it into chat):

```bash
curl -s -X POST https://fantasy-trade-finder.onrender.com/api/admin/experiments \
  -H "X-Cron-Secret: $CRON_SECRET" -H "Content-Type: application/json" \
  -d '{
    "key": "trades_first_operator_test", "layer": "onboarding", "unit_type": "device",
    "bucket_start": 0, "bucket_end": 10000,
    "targeting": {"is_tester_allowlist": true},
    "hypothesis": "Operator-only walkthrough of the built trades-first onboarding (P0-9). Not a powered test.",
    "variants": [
      {"name": "control", "weight_bp": 0},
      {"name": "treatment", "weight_bp": 10000, "client_config": {"flags": {
        "onboarding.v2": true,
        "onboarding.guided_avatar": true,
        "onboarding.landing": true,
        "landing.try_before_sync": true,
        "onboarding.trades_first": true,
        "onboarding.quickset_prompt": true,
        "onboarding.apple_save_moment": true,
        "onboarding.league_autoskip": false
      }}}
    ],
    "primary_metric": "activation_rate", "exposure_surface": "onboarding"
  }'

curl -s -X POST https://fantasy-trade-finder.onrender.com/api/admin/experiments/trades_first_operator_test/transition \
  -H "X-Cron-Secret: $CRON_SECRET" -H "Content-Type: application/json" \
  -d '{"to": "running", "version": 1, "override_underpowered": true,
       "reason": "n=1 operator-only rollout, not a powered test"}'
```

Then: force-quit and reopen the app on the allowlisted device (the flag store fetches at boot and on the ≥30-min foreground refetch). **Rollback is a `transition` to `stopped`** — no deploy, no build, and every non-allowlisted user is byte-identical throughout because the global `flags_dict()` never changed.

**Widening later** is `POST .../revise` with the allowlist targeting dropped and weights rebalanced — no code change on client or server, per the documented `onboarding_v2_rollout` graduation path.

### 3.3 Fix policy — only what is actually broken

Nothing here is a redesign. Three defects were found by reading the code and the capture manifest; each is small, and each blocks reading or completing the flagged-on walk.

**D1 — `s6.1` is silently swallowed when the user's first disposition is a like.** `TradesScreen.tsx:3129-3139` sets `celebrationsShown.first_like` and fires `celebration_fired` **before** calling `requestGuideStep(GUIDE.s6_1())`. But on the first disposition, `:3010-3014` has just advanced `s2.2` and requested `s2.3`, so a bubble is active and `requestStep` returns `false` (`useGuide.ts:93-94`). The beat is lost permanently — `firstLike` is now false forever, so `s6.1` is never requested again, `guideSeen['s6.1']` is never written, and `s8.1` never fires. The tour has no ending.
*Fix (surgical, one condition):* only mark `celebrationsShown.first_like` when `requestGuideStep` returned `true`; leave the `else` toast path untouched. *Alternative if the build agent prefers symmetry with the rest of the chain:* arm a `guidedS61Pending` state and let the chain effect request it in the freed slot, mirroring `guidedS3Pending`. Prefer the one-condition version — it is smaller and the chain effect is already crowded.
Note this is a **V2-only** defect: under release flags `s2.3` is unreachable, so the slot is always free and `s6.1` always shows.

**D2 — `celebration_fired` is not in the taxonomy and is being dropped.** The client fires `celebration_fired` at `TradesScreen.tsx:2547`, `:3135` and `:3153`. `backend/analytics_taxonomy.py:76` registers **`celebration_shown`** (props `{beat_key, beat}` at `:225`). Ingest is **default-deny — unknown types are counted and dropped, never 4xx'd** (`analytics_taxonomy.py:10`). This is the exact prior-art failure the build handoff warns about, live in the tree right now.
*Fix:* rename the client call to `celebration_shown` at all three sites. Props already match (`{beat}`). No server change, no schema change. **Coordinate with the P0-7 agent** — if they are touching the taxonomy, the alternative (adding `celebration_fired` as an alias) is theirs to decide; do not do both.

**D3 — `s5.1` has never been observed.** `s5-1.png` is absent from `screens/mobile/onboarding/`. The capture flow walks the eight Quick Set rungs with **empty** saves (`onboarding-tour@fresh.yaml`, the `quick-set.save-btn` loop) — with zero chips selected the primary composes as a Skip, the board is unchanged, the regen returns the same deck, `fresh === 0`, and the flow always lands on `s5.0` ("Honest result: same trades"). So the beat that carries the entire trades-first argument — *"There it is. N new trades that only exist because of your numbers"* — has never rendered in this repo's evidence.
*Action (validation, not a code fix):* run one variant walk that actually assigns players to tiers so `fresh > 0`, and capture `s5.1`. If it does not render, or renders with a wrong count, **that** is a defect and it is the most important one in the set. Nothing else in the tour is worth testing if the payoff beat is broken.

**Explicitly not in scope:** the swipe-vs-button harness limitation (`decide()` is shared by both paths — `TradesScreen.tsx:3008`; the deck's PanResponder rejecting Maestro's synthetic swipe is a harness fact, not a product bug, and is already documented in the flow); the FeedbackFAB overlap (audit **A-34**, deferred); Quick Set payoff copy (the handoff's optional cheap intermediate — an operator call, not planned here).

### 3.4 Funnel events needed to read the test

**Reference, do not duplicate — the P0-7 agent owns the client-instrumentation spec.** What P0-9 needs from it:

*Already registered and sufficient, no work:* `guide_step_shown` / `guide_step_advanced` / `guide_step_skipped` / `guide_tour_dismissed` / `guide_tour_completed` (`analytics_taxonomy.py:78-79`); `quickset_prompt_shown` / `_accepted` / `_snoozed`; `quickset_completed` (`:111`); `deck_exhausted_viewed`; `apple_prompt_*`; `first_session_like` / `first_session_deck_completed` (`:65-66`); `deck_regenerated`.

*Arm identification needs nothing new:* `experiments.stamp_for_event` (FR-32) already attaches `{key: variant}` to events inside a running experiment's scope, so treatment vs control is readable off existing rows.

*Broken today:* `celebration_fired` — defect **D2** above.

*Missing, and P0-9 cannot be read without it — this is P0-7's scope:* `screen_viewed` is **registered** (`analytics_taxonomy.py:40`, props `{screen, prev_screen, tab}`) but the audit found **zero client instrumentation on navigation**. Without it there is no time-to-first-value and no LeaguePicker → Trades drop-off — the two numbers the trades-first hypothesis actually turns on. Raise this to the operator before they invest in a test that cannot be read; it is the dependency the build handoff flags at §P0-9.

---

## 4. Exact change list

### P0-8 — build (3 edits, all `mobile/`, all client-only)

| # | File | Location | Change |
|---|---|---|---|
| 1 | `mobile/src/screens/TradesScreen.tsx` | `:2456-2459` | Add `ob.guideSeen['s2.2'] &&` to the `s8.1` condition. New: `if (ob.guideSeen['s2.2'] && ob.guideSeen['s6.1'] && !ob.guideSeen['s8.1'] && !ob.guideTourCompleted)`. Rewrite the comment above it from *"s6.1 seen → S8 sign-off (tour complete)"* to state the precondition and why: the sign-off requires that swipe coaching was actually delivered, so a user who only saw the first-like celebration is never told the tour is over. |
| 2 | `mobile/src/components/analystScript.ts` | `:106-109` | Delete the `err_burst` entry (§2.2). |
| 3 | `mobile/.maestro/capture/onboarding-tour@fresh.yaml` | S8.1 header comment | Comment only: record that s8.1 now additionally requires `guideSeen['s2.2']`, so the flow's own s2-2 step is a precondition of its s8-1 step, not just an ordering coincidence. |

Not changed: `useGuide.ts` needs no edit. `stepsSeenCount` stays — it is the `steps_seen` property of `guide_tour_completed`, which is in the taxonomy (`:233`).

### P0-9 — test prep

| # | File | Change | Type |
|---|---|---|---|
| 4 | `mobile/src/screens/TradesScreen.tsx` `:3133-3139` | **D1** — set `celebrationsShown.first_like` only when `requestGuideStep(GUIDE.s6_1())` returns `true` | fix (V2-path defect) |
| 5 | `mobile/src/screens/TradesScreen.tsx` `:2547`, `:3135`, `:3153` | **D2** — rename `celebration_fired` → `celebration_shown` | fix (**coordinate with P0-7**) |
| 6 | `config/tester_allowlist.json` | Add the operator's **current** device pseudo-id if it has rotated | config, operator-confirmed |
| 7 | `mobile/.maestro/flows/guide-no-false-signoff@release.yaml` | **New** — the P0-8 regression under release flags (§6) | new Maestro flow |
| 8 | `docs/plans/audit-p0-remediation/scope-p0-8-9.md` | The feature scope block | doc |

**Not changed, deliberately:** `config/features.json` — **no default flips, not one key.** No backend file. No route. No schema.

---

## 5. Surface changes

**Feature-flag surface: NO defaults change.** `config/features.json` is not edited by this plan. Every `onboarding.*` key, plus `landing.try_before_sync`, keeps the value listed in §1.2. No key is added to `backend/feature_flags.py` `FLAG_KEYS`. The operator's test is delivered entirely by a per-unit experiment overlay, which leaves the global `flags_dict()` byte-identical for every user who is not on the allowlist.

Surfaces that **do** change, enumerated:

| Surface | Change | Reversible by |
|---|---|---|
| `config/tester_allowlist.json` | Possibly one added device pseudo-id (§3.2 step 6). Git-deployed, read by `experiments.load_tester_allowlist` and by the `/api/test-users` gate. | Remove the line, redeploy |
| Experiment registry (`experiments` table, prod DB) | One new device-unit experiment `trades_first_operator_test` in the `onboarding` layer, created via `POST /api/admin/experiments` (CRON-gated). **Runtime state, not a repo change.** Occupies buckets `[0,10000)` of the `onboarding` layer — `validate_spec` rejects an overlapping running experiment in the same layer, so confirm no other `onboarding`-layer experiment is running before launch. | `POST .../transition {"to":"stopped"}` — no deploy |
| Client flag cache | The allowlisted device's `feature_flags_v1` AsyncStorage entry holds the **merged** map while the experiment runs | Reconciles on the next `/api/feature-flags` fetch after stop |
| Analytics event names | `celebration_fired` → `celebration_shown` (D2). No taxonomy edit; the target name is already registered with matching props. | n/a — restores a dropped event |
| Maestro flows | One new file (`guide-no-false-signoff@release.yaml`); one comment-only edit to an existing capture flow | n/a |

**Not a surface change:** no route added, renamed, or contract-changed; no table or column; no env var; no `model_config` key; no cross-client constant.

---

## 6. Maestro delta

Both halves, per the brief. Authored to `mobile/.maestro/README.md`'s flow-authoring laws — **id selectors only**, no text matching, no bare sleeps.

### 6.1 Release-flag regression — NEW: `mobile/.maestro/flows/guide-no-false-signoff@release.yaml`

Header: `# tc: TC-GUIDE-NO-FALSE-SIGNOFF`, `# profile: fresh`, `# flags: release`, `tags: [smoke, onboarding, guide]`.

The assertion is **id-only and precise**. Under release flags `s6.1` is `advance:'auto', autoMs:2200`, and it is the *only* beat that can be showing after a first like (`s6.2` needs `apple_save_moment`, off; `s7.1` needs an exhausted deck). So:

1. `launchApp` with `clearState: true, clearKeychain: true`.
2. Sign in (`signin.username-input` → `signin.continue-btn`), pick a league (`leagues.row.*`).
3. `extendedWaitUntil visible: trades.card-top`.
4. `scrollUntilVisible trades.like-btn`, `tapOn trades.like-btn`.
5. `extendedWaitUntil visible: guide.avatar.*celebrate` — proves `s6.1` still fires (a guard against over-gating).
6. **`extendedWaitUntil notVisible: {id: "guide.bubble"} timeout: 8000`** — the regression assertion. `s6.1` auto-advances at 2200 ms and, with the fix, nothing replaces it. Under the bug `s8.1` is `advance:'tap'`, so its bubble persists indefinitely and this wait times out, failing the flow.
7. `assertNotVisible: {id: "guide.bubble"}` — belt and braces after the wait.

This flow **fails on the unfixed tree and passes on the fixed one**, which is what makes it a regression test rather than a smoke check.

### 6.2 Flag-pinned onboarding-v2 flow — REUSE, do not duplicate

`mobile/.maestro/capture/onboarding-tour@fresh.yaml` already is the flag-pinned 13-beat flow (§3.1). Run it via `mobile/scripts/screen-capture.sh`, which resolves `# flags: onboarding-v2` → `backend/tests/fixtures/flags/onboarding-v2.json` → `sim-run.sh --flags`. Delta:

- Comment-only edit at the S8.1 block recording the new `guideSeen['s2.2']` precondition (change #3).
- A **validation-only variant run** for defect **D3**: same flow with the Quick Set rungs walked with real chip selections instead of empty saves, so `fresh > 0` and `s5.1` renders. Whether this lands as a permanent second cell (`onboarding-tour@fresh--populated.yaml`) or a one-off manual walk is the build agent's call after they see whether chip ids can be selected deterministically — the flow's own comment notes chip ids are player-id templated and unusable as selectors, which is exactly why the empty-save loop exists. If deterministic selection is impossible, do the walk by hand on the simulator and file the screenshot; do not fake it.

Authoring a third, non-screenshot copy of the tour under `flows/` was considered and rejected: it would be a 300-line duplicate of a flow that already carries hard-won timing knowledge (three documented failed runs tuning the S2.wait window), and duplicates drift.

`testID`s: none added or renamed. Every selector used already exists — `guide.overlay`, `guide.tap-catcher`, `guide.avatar.<pose>`, `guide.bubble`, `guide.step-x`, `guide.cta.<action>`, `guide.dismiss-tour` (`AnalystGuide.tsx:91-189`). `mobile/scripts/testid-lint.sh` should pass unchanged.

---

## 7. Docs impact table

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **n/a** | No route added, renamed, removed, or contract-changed. The experiment is created through the already-documented `POST /api/admin/experiments`. |
| `living-memory/LLD.md` | **n/a** | No schema/route/invariant convention shifts. |
| `docs/architecture.md` | **n/a** | No module wiring or data-flow change. |
| `living-memory/HLD.md` | **n/a** | No architectural shift. |
| `docs/cross-client-invariants.md` | **n/a** | No shared constant, enum, or color. |
| `docs/glossary.md` | **n/a** | No new domain term. |
| `docs/config-reference.md` | **n/a for flags** (no default changed, no key added). **Update if** change #6 lands — note that `config/tester_allowlist.json` gained the operator's rotated device id. | |
| `docs/data-dictionary.md` | **n/a** | No schema change. The `experiments` table already exists and is documented. |
| `docs/runbook.md` | **Update** | New short subsection: "Operator-only onboarding test (`trades_first_operator_test`)" — the §3.2 recipe, the allowlist prerequisite, and the one-call rollback. This is operational knowledge the next operator will need and it currently lives only in a feedback status doc for a different experiment. |
| `docs/plans/onboarding-conversion/guided-avatar-script.md` | **Update** | Record that `err.burst` is deleted from the implementation and that S8.1 now requires the S2.2 beat. The script is the design source of truth; leaving it describing a step that no longer exists in code is how the `_comment_draft_extensions` contradiction (audit **A-33**) happened. |
| ADR / `living-memory/DECISIONS.md` | **Update — `D-011`** | The choice of a beat-identity gate over a step-count gate (§2.1) is non-obvious and will be re-litigated the next time a beat is added. One entry. |
| `living-memory/CHANGELOG.md` | **Update at ship** | Dated H2. |
| `living-memory/TEST_LEDGER.md` | **Update at ship** | Sim-gate run per §8. |
| `living-memory/GOTCHAS.md` | **Update — `G-013`** | Defect **D2**: a client `track()` name that is not in `analytics_taxonomy.py` is counted and dropped in silence. Second occurrence in this repo; it belongs in GOTCHAS, not just a commit message. |
| `docs/business/product/2026-08-09-mobile-ux-audit/06-resolutions.md` | **n/a** | The audit is a historical record; do not edit it. Corrections to its counts live here (§1.3). |

---

## 8. Test plan

**Success criteria, restated as checks:**

| # | Criterion | How verified |
|---|---|---|
| A1 | *(P0-8)* A user who sees only the first-like celebration is never told the tour is complete | `guide-no-false-signoff@release.yaml` fails on the unfixed tree, passes on the fixed one (§6.1) |
| A2 | *(P0-8)* The V2 tour still signs off | `onboarding-tour@fresh.yaml` still produces `s8-1.png` after the fix |
| A3 | *(P0-8)* `err.burst` is gone and every remaining `S` entry has a call site | `grep -rn "err_burst\|err\.burst" mobile/src/` → empty; re-derive the §1.3 table |
| A4 | *(P0-9)* The operator can flip the experience on for their own device via allowlist | the §3.2 recipe run against prod; the allowlisted device shows the trades-first landing, every other user is unchanged |
| A5 | *(P0-9)* The full 13-beat tour walks without a broken beat | §3.1 checklist, all rows green, including the currently-missing `s5.1` and `s6.2` |
| A6 | *(P0-9)* The instrumentation to compare funnels exists | D2 fixed; P0-7's `screen_viewed` emission landed or explicitly deferred by the operator with the consequence stated |

**Gates:**

- `python3 -m pytest backend/tests/ -q` — expected unchanged (no backend file touched). Run anyway; the repo has concurrent sessions.
- `cd mobile && npx tsc --noEmit` — clean. **`mobile/node_modules` is a symlink in this worktree; never run `npm install`.**
- `mobile/scripts/testid-lint.sh` — clean (no `testID` added or renamed).
- **Simulator gate: Tier 1** (`docs/runbook.md` § Pre-ship simulator gate). P0-8 is a mobile screen/state change on the app's most-trafficked screen, so: full smoke suite (11 flows) + the new `guide-no-false-signoff@release.yaml` + `onboarding-tour@fresh.yaml`. Screen captures: **none required for P0-8** — deleting an unreferenced script entry and tightening a boolean changes no pixels on the release path. The V2 captures are re-run as *validation evidence* for P0-9, not as a capture refresh.
- Evidence: `living-memory/TEST_LEDGER.md` entry + `qa/sim-runs/last-sim-run.json`.

**Manual checks the harness cannot make:**

1. Real-device swipe (not the pass/like buttons) advances `s2.2` — the simulator's PanResponder limitation means the harness always exercises the button path.
2. The `s3.2` **"Not now"** and `s5.5` **"Later"** dismiss paths do not trap the user (script §1 binding principle: never trap). The capture flow only walks accept on s3.2.
3. Settings → tour toggle off → on replays from the first step after the fix (full-replay semantics, `useGuide.ts:66-70`).

---

## 9. Risks and open questions

### Risks

| # | Risk | Likelihood | Mitigation |
|---|---|---|---|
| R1 | Gating `s8.1` on `s2.2` means the release path never sets `guideTourCompleted`, and some consumer we missed depends on it | low | Consumers fully enumerated in §2.3 — `useGuide`, the two `TradesScreen` sites being edited, `resetGuideProgress`. `SettingsScreen` reads `guideDismissed`, not this. Re-grep at build time. |
| R2 | Deleting `err.burst` removes a surface someone intended to wire this sprint | low | It has never had a call site. P0-2 owns the Trades error state in this same batch — check with that agent before deleting; if they want a mascot line, they should own it in their scope, not inherit an orphan. |
| R3 | The `s2.wait` beat only ever renders because the capture flow injects 3 s of latency into `/api/trades/generate` — real users on a warm pre-gen may never see it | medium | Not a P0-8/P0-9 defect, but it means "13 beats" overstates the real-world tour by one. Record it in the validation findings; do not fix here. |
| R4 | The experiment's `client_config.flags` overlay is cached client-side, so stopping the experiment leaves the operator in treatment until the next fetch | low | Documented behavior (`flags.ts` comment). Force-quit and reopen; ≥30-min foreground refetch otherwise. |
| R5 | `TradesScreen.tsx` is ~6,158 lines and mutates under concurrent sessions | **high** | Re-grep every line number in §1.1 immediately before editing. Every anchor in this plan was verified at `ab9368f`. |
| R6 | An `onboarding`-layer experiment already running in prod would collide on buckets `[0,10000)` and `validate_spec` would reject the launch | low | `GET /api/admin/experiments` before creating; if one exists, either stop it or narrow the bucket range. |

### Open questions — for the operator

| # | Question | Why it matters | Default if unanswered |
|---|---|---|---|
| Q1 | **Feature gates or express?** `CLAUDE.md` requires scope block + Maestro delta + docs + sim run. P0-8 does not cross the bright line (no schema, no API, no flag-surface change, no new analytics event). P0-9's test mechanism **does** touch analytics (D2) and a config surface (allowlist). | Agents never self-select express. | **Full gates.** This plan assumes them; `scope-p0-8-9.md` is written. |
| Q2 | **Is the operator's device pseudo-id in `config/tester_allowlist.json` current?** | The entire test mechanism hangs on it. Device ids rotate on reinstall. | Blocks A4. Ask before the build agent starts. |
| Q3 | **Who fixes D2 — this agent or P0-7?** The rename is one word in three places; P0-7 owns the taxonomy. | Doing both creates a conflict (an alias plus a rename). | This agent renames the client calls; P0-7 does not add an alias. Confirm with that agent. |
| Q4 | **Does the operator want `s5.1` proven before the test, or is a walk with `s5.0` enough?** | `s5.1` is the payoff beat and the entire trades-first argument. It has never rendered in this repo's evidence (D3). | Prove it. A test of a first-session experience whose payoff moment is unverified cannot answer the question that was asked. |
| Q5 | **P0-7's `screen_viewed` emission — landing, or deferred?** | Without navigation instrumentation there is no time-to-first-value and no picker→Trades drop-off, which are the two numbers the trades-first hypothesis turns on. The build handoff raises this as the P0-9 dependency. | Surface it; do not silently proceed. A test that cannot be read is worse than no test. |
| Q6 | **Ship the Quick Set payoff-copy intermediate?** The handoff offers it as a cheap, low-risk change that sidesteps the ordering question entirely (`quick-set/step-populated--seeded.png` has no payoff copy at all, while Trios states its payoff prominently). | It is not in P0-8 or P0-9 as scoped and is not planned here. | Not built. Operator's call. |

### Answered by this pass — no longer open

- *"Whether a launch flag config differs from `config/features.json`"* (the audit's falsification handle for P0-8): **it can, and the mechanism is per-unit experiment overlays** (§3.2). Today no such overlay is running for onboarding, so `config/features.json` is the live truth, and the P0-8 mechanism holds exactly as the audit described it.
- *"Whether the operator's test needs new code"*: **no.** The overlay path, the allowlist attribute, the admin routes and the client merge all exist and are exercised by the `aggregate_tier_labels` precedent.
