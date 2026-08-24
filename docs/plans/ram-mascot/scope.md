# Feature Scope — Fleeced replaces The Analyst as the guide avatar

**Date:** 2026-08-23
**Entry point:** direct ask ("re-write the onboarding experiences using the painted ram and push it live, hidden behind an A/B test only enabled for me")
**Builder:** Opus session, branch `claude/ram-mascot-fleeced`
**Operator sign-off on waivers:** **pending** — three waivers below (§1c, §3 partial, §5 TestFlight) and two open decisions in §6
**Binding docs:** [brief.md](brief.md) §3 · [experiment.md](experiment.md) · [D-155, D-156](../../../living-memory/DECISIONS.md)

---

## 1. Analytics scope

**(c) WAIVED — no analytics needed, and deliberately so.**

The change swaps *which component draws the avatar*. It adds no surface, no interaction and no state. The existing
`guide_step_shown{pose}` event already reports the six pose values, and the pose vocabulary is **shared** between the two
mascots — `RamAvatar` types its `pose` against `AnalystPose`, and `mobile/tests/check-mascot-ram.js` asserts it. So the
same event means the same thing in both states, which is what makes the two arms comparable at all.

Exposure attribution comes free: the unit is assigned to `mascot_ram_rollout`, and `flagProvenance()` already tags
flag→experiment provenance on every fetch.

**What would have been dishonest:** minting a `mascot_rendered` event. Nothing would consume it, and it would imply a
measurement intent this rollout does not have (§6 of experiment.md — no readout will be drawn).

## 2. Schema & flag scope

- **New/changed tables or columns:** none. No migration.
- **New/changed feature flags:** **`onboarding.mascot_ram`** — default **`false`**, registered in
  `config/features.json`, `backend/feature_flags.py`, and the three flag fixtures
  (`release.json`, `onboarding-v2.json`, `profiles-on.json`). Documented in `docs/config-reference.md`.
  - **Graduation criterion:** operator TestFlight pass on the ram in all six poses at 96 pt and on Team Review at
    44/38 pt. It is **not** intended to be flipped globally from `features.json` — it reaches the operator only through
    the allowlist-targeted experiment overlay ([experiment.md](experiment.md) §2).
  - **Deploy-free rollback lever:** `/api/admin/experiments/mascot_ram_rollout/transition` → `stopped`. The overlay
    vanishes on the next flag fetch; the global flag was never on, so there is nothing to un-flip.
- **New env vars / `model_config` keys:** none.

**Pre-existing defect fixed in passing, called out rather than buried:** `backend/tests/fixtures/flags/release.json`
had `trade.full_sweep: false` while `config/features.json` had `true`, so
`test_release_flags_mirror_features_json` was **already failing on `origin/main`** (lit by #182, fixture not updated).
CI could not be green for anyone until it was corrected. One value changed; unrelated to this feature.

## 3. Evidence scope

- [x] **Structural guard:** [`mobile/tests/check-mascot-ram.js`](../../../mobile/tests/check-mascot-ram.js) — pins:
      the flag gate exists and routes through `useOnboardingFeature` (so the `onboarding.v2` master is ANDed in);
      no bare `useFlag` on an `onboarding.*` key; the gate is not short-circuited; **both branches survive** so flag-off
      still renders the Analyst; all three call sites go through `AnalystAvatar` and none imports a ram pose directly;
      all 18 sprites exist at @1x/@2x/@3x and sit inside the 60 KB/file budget; **the 70 % ink inset holds**;
      `flip` survives; the pose vocabulary is unchanged.
      Runnable as `node tests/check-mascot-ram.js`; picked up by CI's `for f in tests/check-*.js` loop.
- [x] **Sabotage-tested** (the guard is only worth its runtime if it fails when it should):
      forcing the gate with `|| true` → caught; re-exporting a sprite trimmed to its bounding box → caught, reporting
      97.9 % ink against the 70 % target. Both restored, guard green.
- [x] **Unit tests:** no new backend tests. The flag is a registered key with no server behaviour behind it — nothing
      branches on it in Python. Full suite re-run: **4198 passed, 1 skipped** (the one prior failure was the
      pre-existing mirror drift above, now fixed).
- [x] **Code-walk proof:**
      - `mobile/src/components/analyst/index.tsx:59` — `useOnboardingFeature('onboarding.mascot_ram')`, read
        unconditionally (hooks cannot sit behind a branch).
      - `:60` — flag on → `<RamAvatar pose size flip />`. Flag off → falls through to `POSE_COMPONENTS[pose]` at
        `:62`, which is the pre-change body verbatim, so **flag-off is byte-identical**.
      - `mobile/src/components/mascot/ram/index.tsx:27-34` — static `require()` per pose; Metro resolves `@2x`/`@3x`
        by filename convention, so one entry covers three files.
      - `:56-59` — `width: size, height: size` (square, deliberately taller than the Analyst) with
        `resizeMode="contain"`.
      - `:64-66` — `flip` wraps in `scaleX: -1`, matching `AnalystAvatar`'s own flip semantics.
      - Call sites unchanged: `AnalystGuide.tsx:452`, `TeamReviewScreen.tsx:351`, `TeamReviewEntryCard.tsx:118`.
      - Layout safety: `AnalystGuide.tsx:526` — `row: { flexDirection: 'row', alignItems: 'flex-end' }`. The avatar box
        is `{ width: AVATAR }` with no height constraint, so a taller square sprite grows **upward** off a shared
        bottom edge. No call site needs to change for the height difference the operator sanctioned.
- [ ] **Manual TestFlight checklist:** [testflight-checklist.md](testflight-checklist.md) — **written, unrun.**
      Under D-056 this is the only runtime evidence mobile can get, and it is the graduation gate.
- **WAIVED — no `screens/` capture, no Maestro flow:** retired entirely by D-056.
- **`testID`s added/renamed:** none. The existing `guide.avatar.<pose>` testID is on the wrapping `View` in
  `AnalystGuide`, not on the avatar component, so it is unaffected by the swap. `testid-lint` unaffected.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **n/a** | No route added, renamed, removed, or contract-changed. `/api/feature-flags` already documents per-unit overlay resolution; this adds one key to an existing map |
| `living-memory/LLD.md` | **n/a** | No schema, route or invariant *convention* shifted. One flag key on an existing registry |
| `docs/architecture.md` | **n/a** | No module wiring or data-flow change — one component gained a second render branch |
| `living-memory/HLD.md` | **n/a** | No architectural shift. `components/mascot/` is a new folder, not a new layer or client |
| `docs/cross-client-invariants.md` | **n/a** | The pose vocabulary is unchanged and remains mobile-only; no shared constant, enum or colour moved. Web and extension have no mascot |
| `docs/glossary.md` | **updated** | "Fleeced (the ram)" — the mascot and guide avatar |
| `docs/config-reference.md` | **updated** | `onboarding.mascot_ram` — default, what it gates, rollback lever, and the bundled-asset caveat |
| `DECISIONS.md` | **updated** | [D-155](../../../living-memory/DECISIONS.md) (ram is the mascot, named Fleeced, scoped raster exception) and [D-156](../../../living-memory/DECISIONS.md) (painted everywhere; the 70 % ink-inset sizing rule) |
| `mobile/src/components/analyst/CLAUDE.md` | **updated** | Documents the switch and that the folder is no longer the only mascot |
| `mobile/assets/CLAUDE.md` | **updated** | The scoped raster exception naming `mascot/ram/` |
| `mobile/src/components/CLAUDE.md` | **updated** | `mascot/ram` row |

## 5. Ship gate declaration

- **CI green:** `backend-tests` 4198 passed / 1 skipped · `mobile-typecheck` (`tsc --noEmit`) · the full
  `tests/check-*.js` suite including the new guard · `testid-lint`. Verified locally before push.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md`.
- **TestFlight verification:** **owed, not done.** The checklist is written; running it needs a build.
- **Express lane declared by the operator?** **No.** Full gates apply — and this change touches a
  **feature-flag surface**, which CLAUDE.md's bright line puts outside "quick fix" regardless.

## 6. Open decisions carried into the build, stated not assumed

1. **Copy split — unresolved by design.** D-155 deferred which of the six "The Analyst" strings become "Fleeced".
   **This build changes none of them**, so the bubble still reads "The Analyst" above a ram. That is the recorded
   default, not an oversight — *"I'm Fleeced"* as an opening line reads as "I got ripped off".
2. **Anchor corner — dissolved, and worth recording why.** D2 decided `BUBBLE_ANCHOR` moves off-centre. Reading the
   shipped code, **`BUBBLE_ANCHOR` is exported and never consumed**: `AnalystGuide` lays the bubble out *beside* the
   avatar in a flex row (`:445-455`), not above it with a tail. There was nothing to move. `RAM_BUBBLE_ANCHOR` is
   declared for symmetry and documented as unconsumed. The horn-clash finding in the avatar lab describes the layout
   the brief *described*, not the one that ships.

## 7. What this deliberately does not do

- **No tour-script change.** No beat, no copy, no ordering, no `analystScript.ts` edit.
- **No change to the three call sites.** The switch is one function, which is what keeps the flag a single lever.
- **No web or extension mascot** — out of scope per the brief.
- **No global flag flip.** `onboarding.mascot_ram` ships `false` and is intended to stay false in `features.json`.
- **No experiment created.** Creating and launching `mascot_ram_rollout` is a production write against the prod DB and
  is held for explicit operator confirmation ([experiment.md](experiment.md) §4).
