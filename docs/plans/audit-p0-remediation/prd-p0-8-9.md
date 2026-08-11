# PRD — P0-8 (guided-tour sign-off gate) + P0-9 (first-session test prep)

> **Companion LLD:** [`lld-p0-8-9.md`](lld-p0-8-9.md) — code-level design, exact edits, flow
> outlines, and the operator recipe in full. **Binding parent:** [`hld.md`](hld.md) (§2 S-39…S-46,
> §3 commit 11, §4 W2-TS, §6 rows 6/11, §7, §8 R6/R17, §9 LLD-7, §10.1).
> **Source plan/scope:** [`plan-p0-8-9.md`](plan-p0-8-9.md), [`scope-p0-8-9.md`](scope-p0-8-9.md).
> **Source findings:** `docs/business/product/2026-08-09-mobile-ux-audit/` §P0-8, §P0-9.
>
> **Two different kinds of work in one unit.** **P0-8 is a build** — a user-facing bug fix that
> ships in commit 11. **P0-9 is test prep** — a validation pass over an already-built experience,
> plus two client defect fixes it uncovered, plus a mechanism the operator can run **without a
> deploy**. Nothing here flips a feature-flag default.

## Contents

- [1. Problem](#1-problem)
- [2. Requirements](#2-requirements)
- [3. Acceptance criteria](#3-acceptance-criteria)
- [4. Non-goals](#4-non-goals)
- [5. Operator runbook — the first-session test, start to rollback](#5-operator-runbook--the-first-session-test-start-to-rollback)
- [6. Docs rows](#6-docs-rows)
- [7. Rollback](#7-rollback)
- [8. Risks carried into this work](#8-risks-carried-into-this-work)

---

## 1. Problem

**P0-8 — the tour signs off before it teaches.** With today's shipped flags
(`onboarding.trades_first` off), the entire S2 teaching block is unreachable. A user's first *like*
fires the celebration beat `s6.1`, which auto-advances after 2.2 seconds; the chain effect's only
satisfiable branch then fires `s8.1` — *"That's the tour. I'll keep modeling in the background."* —
and `completeTour()` follows. **The app tells the user a tour is over having taught them one line**,
and permanently retires the guide to reactive-only mode. The sign-off was gated on `guideSeen['s6.1']`
alone, which is a *reaction* beat, not a *teaching* beat.

**P0-9 — the trades-first experience has been built but never walked.** Sixteen of the twenty script
entries are unreachable under release flags. Three defects sit in the flagged-on path: the first-like
celebration is silently swallowed when the user's first disposition is a like (**D1**), so the tour
can never sign off in that arm; the celebration's analytics event has been dropped on the floor
since it shipped (**D2**); and the tour's payoff beat `s5.1` — *"There it is. N new trades that only
exist because of your numbers"* — has **never rendered in this repo's evidence** (**D3**). Before the
operator invests in a first-session test, the experience has to be proven walkable and the operator
needs a way to turn it on for their own device that does not require a deploy, a build, or an App
Store round trip.

---

## 2. Requirements

### P0-8 — the sign-off gate

| id | Requirement |
|---|---|
| **R1** | The tour's sign-off beat (`s8.1`) must not fire unless the tour actually taught something. "Taught something" is defined as **the swipe-coaching beat `s2.2` was delivered and acted on** — it is the tour's only `advance:'action'` teaching step, and `guideSeen` is durable across launches. |
| **R2** | The gate must read **persisted product state, never a feature flag**, so one condition is correct under both the release defaults and the full onboarding-v2 set. |
| **R3** | The V2 tour must still sign off on its normal walk. No regression. |
| **R4** | `s6.1` (the first-like celebration) must still fire on the release path — the fix must not over-gate the beat it is downstream of. |
| **R5** | The orphaned `err.burst` script entry (zero call sites) is deleted, so every remaining entry in the script table has a call site. The Trades failure moment ends up with exactly **one** surface — P0-2's error card, which carries a named error and a working retry. |
| **R6** | No feature flag is added and no default is flipped. The fix removes a false statement from a flag-off path and is a strict subset of current behaviour, so it needs no kill switch. |

### P0-9 — validation, defect fixes, and the test mechanism

| id | Requirement |
|---|---|
| **R7** | **D1** — a user whose first disposition is a *like* must not lose the first-like celebration permanently. The celebration is marked consumed **only when the bubble slot was actually free**; a swallowed celebration re-arms, and the user receives one acknowledgement either way (celebration or toast — never silence). |
| **R8** | **D2** — the client emits the **registered** event name `celebration_shown` at all three call sites. No taxonomy edit, no alias, no schema change. |
| **R9** | **D3** — `s5.1` is **proven to render** by a flag-pinned run before any first-session test is considered readable. If it does not render, that is the most important defect in the set and it is surfaced to the operator before the test. If deterministic capture proves impossible, the beat is walked **by hand** and the screenshot filed — it is never faked. |
| **R10** | Every reachable beat of the tour is walked under the pinned `onboarding-v2` flag set and checked on four axes: reachable, renders (bubble + pose + spotlight), advances by its declared mechanism **with no dead end**, and its analytics land. |
| **R11** | The operator can enable the trades-first experience **on their own device only**, with **zero deploys, zero builds, and zero changes to the global flag map**, via a per-unit experiment overlay; and can turn it off again with **one call**. |
| **R12** | The funnel is readable from events that already exist plus P0-7's F1/F3/F4 — this work adds **no new event name**. |
| **R13** | Anything genuinely broken in a beat is fixed; anything merely un-walked, opinion-level, or owned by another agent's exclusive file is **deferred with a named destination**, not silently absorbed. |

---

## 3. Acceptance criteria

Each criterion names the artifact that decides it. LLD assertion ids are in brackets.

| id | Criterion | Decided by |
|---|---|---|
| **A1** | **A user who sees only the first-like celebration is never told the tour is complete — under BOTH flag sets.** Under **release**: after a first like, `s6.1` renders and, once it auto-advances, no bubble replaces it; zero `guide_step_shown {step:'s8.1'}` rows and zero `guide_tour_completed` rows for the session. Under **onboarding-v2**: identical protection, because the gate reads `guideSeen['s2.2']` — a beat that is unreachable without `onboarding.trades_first` — and never reads a flag. | `guide-no-false-signoff@release.yaml` (**fails on the unfixed tree**, passes on the fixed one) + the `user_events` query [P08-A1…A4]; the V2 half is implied by the same single condition and pinned by A2 |
| **A2** | **The V2 tour still signs off.** The normal walk still produces `onboarding__s8-1.png` and exactly one `guide_tour_completed` row with `steps_seen ≥ 7`. | `capture/onboarding-tour@fresh.yaml` re-run after the fix [P08-A8, P08-A9] |
| **A3** | `err.burst` is gone and every remaining script entry has a call site (19 of 19). | `grep -rn "err_burst\|err\.burst" mobile/src/` → empty; `tsc --noEmit` clean [§2.5] |
| **A4** | **D1 — a like-first user under V2 flags still reaches the sign-off.** The swallowed like produces a `'Liked'` toast and leaves `celebrationsShown.first_like` **false**; the next like that finds a free slot renders `s6.1`, writes a `celebration_shown` row, and `s8.1` follows. **Residual, accepted:** the beat is re-armed, not rescheduled — a user who likes exactly once and never again still does not sign off. That case is reported in the validation findings, and the complete fix (re-arm through the chain effect) is a `NEXT.md` candidate. | manual sim walk [D1-A1…D1-A3] + the `user_events` query |
| **A5** | **D2 — `celebration_shown` rows land in `user_events`** for the first time, for both `first_like` and `first_quickset_save`; no `celebration_fired` literal remains in `mobile/`. | the `user_events` query during the tier-1 run; `grep` |
| **A6** | **The operator can enable trades-first per-device with zero deploys.** `GET /api/feature-flags` with the device's `X-Device-Id` returns `experiments: {"trades_first_operator_test": "treatment"}` and the eight-key overlay in `configs`, while the global `flags` map is byte-identical to every other user's. | the §5 step-4 pre-flight call, run before touching the phone |
| **A7** | **All reachable beats walk without a broken one.** Every beat in the checklist is green on all four axes, or is explicitly classified as *not applicable* (with the reason) or *defect* (with a disposition). **`s5.1` is captured** — harness or hand-walked — or its failure is escalated. | the validation report + `TEST_LEDGER.md` |
| **A8** | **The funnel is readable.** Time-to-first-value and the LeaguePicker→Trades drop-off are readable **today** from `screen_viewed`, which is already emitted for every route including tab switches (HLD §10.1) — the dependency this test was said to hang on does not exist. Exposure is readable from P0-7's **F1** `experiment_exposed` and from `experiments.stamp_for_event`; the Quick Set drop-off curve from **F3** `quickset_step_advanced` and **F4** `quickset_abandoned`; the tour itself from `guide_step_shown/_advanced/_skipped`, `guide_tour_completed/_dismissed`; activation from `first_session_like`, `quickset_completed`, `quickset_prompt_shown/_accepted/_snoozed`, `deck_exhausted_viewed`, `apple_prompt_*`. **This work adds no event name.** | P0-7's addendum + the taxonomy; verified flat `dropped_unknown_type` counters during the sim run |
| **A9** | **Rollback is one call and no user outside the allowlist was ever affected.** | §7 |

**Known reading limitation, stated up front so nobody discovers it mid-test.** Two client events
inside this surface are fired but **not registered**, so they are counted-and-dropped:
`deck_regenerated` (the S5 reveal's `new_trades` count) and `guide_tour_reenabled` (the Settings
replay signal). Both are asserted as registered by `plan-p0-8-9.md` §3.4 and `scope-p0-8-9.md` §1;
neither is. They are **not** fixed here — `analytics_taxonomy.py` is `W0-TAX`'s exclusive file — and
the D3 proof was redesigned so it does not depend on them. Registering `deck_regenerated` is
recommended to the orchestrator (LLD §9 D-4). A sweep of the whole client found **33 of 73** event
names in this state; commit 1 fixes one (`invite_shared`) and this commit fixes one
(`celebration_fired`), leaving 31 on `NEXT.md`.

---

## 4. Non-goals

- **NO default flag flips — restated, because P0-9 is *about* flags.** `config/features.json` is
  **not edited**. Every `onboarding.*` key keeps its current value (`v2: true`,
  `guided_avatar: true`, all ten siblings `false`), and `landing.try_before_sync` stays `false`.
  No key is added to `backend/feature_flags.py` `FLAG_KEYS`. The operator's test is delivered
  entirely by a per-unit experiment overlay, which leaves the global `flags_dict()` **byte-identical
  for every user who is not on the allowlist**. **If the operator later asks to flip
  `onboarding.trades_first` in `config/features.json`, that IS the bright line** and requires an
  explicit confirming yes (root `CLAUDE.md` §Conventions).
- **No redesign of the tour.** No new beats, no copy changes, no reordering, no pacing changes.
  P0-9 is validation; opinions about the script are out of scope.
- **No new analytics event name, and no taxonomy edit.** D2 renames a client call to a name that is
  already registered with matching props.
- **No new `testID`s**, no new selectors, and no `testid-lint-allow.txt` entry.
- **No third tour flow.** The three existing `onboarding-v2`-tagged capture flows are reused; a
  duplicate would clone ~300 lines carrying timing knowledge from three documented failed runs.
- **No backend file, route, schema, env var, or `model_config` key is touched.**
- **The operator's experiment is not created by any agent.** Creating, launching, and stopping
  `trades_first_operator_test` are **operator actions** against production (§5). Agents write the
  recipe; the operator runs it.
- **`config/tester_allowlist.json` is not edited by any agent** (S-45). Device-id currency is an
  operator checklist item because only the operator can read their current device id.
- **Not widening the experiment beyond the operator's own device.** That is a separate,
  bright-line decision.
- **Deferred with destinations:** `s7.1` capture (needs a `/__test__` deck-size pin); the
  swipe-vs-button harness limit (a harness fact, not a product bug); the FeedbackFAB overlap
  (audit A-34); the Quick Set payoff-copy intermediate (operator's call, not planned);
  `s2.wait`'s dependence on injected latency (reported, not fixed); the complete D1 fix (M-b).

---

## 5. Operator runbook — the first-session test, start to rollback

> Full detail, with the code citations behind every claim, is in **LLD §6**. This is the operating
> sequence. **`CRON_SECRET` lives in `secrets.local.env` — read it from there, never paste it into
> chat.** Host below is `https://fantasy-trade-finder.onrender.com`.

**Prerequisites**

1. The build carrying P0-8 + D1 + D2 is **installed on the device**. The overlay only turns on flags
   the client reads; walking against an older build validates the old code.
2. Validation (A7) has passed, or its failures are known and accepted. A test whose payoff moment
   is unverified cannot answer the question that was asked.
3. **This recipe is AASA-independent.** It needs no deep link, no universal link, and no
   `growth.invite_join_link` flip. Entry is a normal cold app launch. P0-3 can ship, slip, or roll
   back without touching any step here.

**Step 0 — check for a collision, and pick the branch.**
`GET /api/admin/experiments` (CRON header). Look for an **`onboarding`-layer** experiment that is
`running` or `paused` — in practice `onboarding_v2_rollout`.

- **A — none:** proceed to step 1.
- **B — `onboarding_v2_rollout` is running and its treatment `client_config.flags` already matches
  the map in step 1:** **create nothing.** Skip to step 3 (device id), then step 4 (verify). Zero
  writes.
- **C — one is running with a different or partial overlay:** you must stop it first, because
  `validate_spec(for_launch=True)` rejects a launch whose buckets overlap any running **or paused**
  experiment in the same layer, and the incumbent occupies the whole range. **Before stopping it,
  save its full row** (`GET /api/admin/experiments/onboarding_v2_rollout`) — that response is the
  restore spec. ⚠ **`stopped` is a one-way door:** there is no `stopped → running` transition;
  restarting means `revise` to a new version plus a `transition`, and its metrics reset.

**Step 1 — create the experiment** (branches A and C). `POST /api/admin/experiments` with the body
in LLD §6.2: key `trades_first_operator_test`, layer `onboarding`, unit type `device` (the onboarding
layer requires it), buckets `[0, 10000)`, targeting `{"is_tester_allowlist": true}`, variants
`control` 0 bp / `treatment` 10000 bp, primary metric `activation_rate`, exposure surface
`onboarding`. The treatment's `client_config.flags` carries eight keys — the same map the capture
flows were validated against:

`onboarding.v2: true` · `onboarding.guided_avatar: true` · `onboarding.landing: true` ·
`onboarding.trades_first: true` · `onboarding.quickset_prompt: true` ·
`onboarding.apple_save_moment: true` · **`onboarding.league_autoskip: false`** ·
**`landing.try_before_sync: true`**

The last two are the non-obvious ones. `league_autoskip` must stay **off** — with it on, a
single-league user skips the picker and the `s1.1` beat becomes unreachable. `landing.try_before_sync`
is **not** an `onboarding.*` key and is `false` globally, but it is the launch pairing: without it
`/api/session/demo` 404s and the landing's demo link is a dead end.

**Step 2 — launch.** `POST /api/admin/experiments/trades_first_operator_test/transition`
`{"to": "running", "version": 1, "override_underpowered": true, "reason": "n=1 operator-only rollout, not a powered test"}`.
A 400 mentioning `layer_overlap` means step 0 was branch C and was missed.

**Step 3 — device-id currency.** `config/tester_allowlist.json` holds
`["device:dev_loc-mrpy6qog-2t72t6", "313560442465169408"]`. The device pseudo-id is minted by the
client and stored in SecureStore, so a reinstall that clears the keychain **rotates it**. Confirm the
current id and add it if it changed — one line in a git-deployed JSON file (Render does not apply
`render.yaml` envVars to a dashboard-created service, observed 2026-07-19, which is why the file
exists). Entries carry the `device:` prefix; the header in step 4 does not.

**Step 4 — verify before touching the phone (do not skip).**
`GET /api/feature-flags` with header `X-Device-Id: <id without the device: prefix>`.
**Expect** `experiments` to contain `"trades_first_operator_test": "treatment"` and `configs` to
carry the eight-key overlay. This single unauthenticated call proves the allowlist matched, the
layer has a salt, the bucket resolved, the targeting passed, and the variant carries the config —
all of which otherwise fail **silently**. If `experiments` is empty: the device id is wrong or not
on the allowlist, or the layer has no salt (fix with the CRON-gated
`POST /api/admin/experiments/reseed-layers`, which **refuses once any experiment has assigned a
unit** — so run it before launching, never after).

**Step 5 — walk it.** Force-quit and reopen the app on the allowlisted device (the flag store
fetches at boot and on the ≥30-min foreground refetch). Walk the first session end to end.

**Step 6 — read it.** Per **A8**: `screen_viewed` (already live) for time-to-first-value and the
picker→Trades drop-off; P0-7's **F1** `experiment_exposed` for exposure (and
`experiments.stamp_for_event`, which already attaches `{key: variant}` to events inside a running
experiment's scope, so arm attribution needs nothing new); **F3** `quickset_step_advanced` and
**F4** `quickset_abandoned` for the per-step Quick Set drop-off curve; `guide_step_*` for the tour
itself; `first_session_like` / `quickset_completed` / `deck_exhausted_viewed` for activation.
Details and event-by-event provenance are in P0-7's addendum,
`docs/business/analytics/2026-08-11-p0-7-addendum.md`.

**Step 7 — stop.** See §7.

---

## 6. Docs rows

Owned by **`W3-DOCS`** (wave 3) — no build agent edits a `docs/` or `living-memory/` file. Full
row text is in **LLD §8.2**.

| Doc | Updated? | Row |
|---|---|---|
| `docs/runbook.md` | **Yes** | New subsection *"Operator-only onboarding test (`trades_first_operator_test`)"* — §5 in full, including the step-0 branch, the one-way `stopped` door, the step-4 pre-flight verification, the two non-obvious overlay values, and the one-call rollback. This knowledge currently exists only inside a feedback status doc for a different experiment. |
| `docs/plans/onboarding-conversion/guided-avatar-script.md` | **Yes** | `err.burst` is deleted from the implementation (keep the design intent, mark it unbuilt); S8.1 now requires the S2.2 beat. |
| `docs/config-reference.md` | **Conditional** | Only if the operator's device id is added to `config/tester_allowlist.json`. **No flag row changes.** |
| `living-memory/DECISIONS.md` | **Yes — `D-032`** (per HLD §7, **not** `D-011`) | Beat-identity gate over step-count gate, with the three reasons a count fails. Plus a candidate entry for D1's request-first-consume-on-success idiom. |
| `living-memory/GOTCHAS.md` | **Yes — `G-031`** (per HLD §7, **not** `G-013`) | An unregistered client `track()` name is counted and dropped in silence — and the sweep found **33 of 73**, not one. Names `deck_regenerated` and `guide_tour_reenabled` as still-broken. |
| `living-memory/NEXT.md` | **Yes** | Register the remaining 31 dropped event names (start with `deck_regenerated`); the complete D1 fix (M-b); `s7.1` capture needs a deck-size pin; decide whether `s2.wait` earns its place. |
| `living-memory/CHANGELOG.md` | **At ship** | Inside the batch's dated H2: no more false tour sign-off; the first-like celebration is no longer lost; `celebration_shown` starts landing. |
| `living-memory/TEST_LEDGER.md` | **At ship (`W3-QA`)** | Tier-1 run, the **pre-fix control** result for the regression flow, the four manual checks verbatim, the D3 outcome, and whether `s5-1.png` was harness-captured or hand-walked. |
| `docs/api-reference.md` · `living-memory/LLD.md` · `docs/architecture.md` · `living-memory/HLD.md` · `docs/cross-client-invariants.md` · `docs/glossary.md` · `docs/data-dictionary.md` · `living-memory/DEPENDENCIES.md` | **n/a** | No route, schema, shared constant, domain term, dependency, or convention shift. |
| `docs/business/product/2026-08-09-mobile-ux-audit/*` | **n/a — do not edit** | Dated artifact. Its P0-8 count is superseded by `plan-p0-8-9.md` §1.3 (16 of 20 unreachable, not 9 of 15); the correction lives in the plan. |

---

## 7. Rollback

Three independent levers, in increasing blast radius. **None of them is a flag-default change,
because none was made.**

| What | Lever | Cost |
|---|---|---|
| **The operator's test** | `POST /api/admin/experiments/trades_first_operator_test/transition {"to": "stopped", "version": 1, "reason": "…"}` | **One call. No deploy, no build, no App Store round trip.** Every non-allowlisted user was byte-identical throughout. The allowlisted device keeps its cached merged flag map until the next `/api/feature-flags` fetch — force-quit to reconcile immediately. If step 0 was branch C, restore the incumbent now: `revise` with the saved spec, then `transition` to `running`. |
| **The allowlist entry** | Remove the device id line from `config/tester_allowlist.json`, redeploy | One commit. Only needed if the id was added. |
| **The P0-8 / D1 / D2 code** | `git revert` commit 11 | Reverts P0-2 with it — the two share one commit by HLD §3/R6 design. **P0-8 itself needs no kill switch:** it removes a false statement from a flag-off path and is a strict subset of current behaviour, so its "off" position would be the known bug. There is nothing to toggle. |

---

## 8. Risks carried into this work

| # | Risk | Sev | Carried mitigation |
|---|---|---|---|
| R-a | **`s5.1` turns out to be broken** — the payoff beat carrying the entire trades-first argument has never rendered in this repo's evidence (HLD R17) | Med | S-43 makes proving it a gate on validation. The proof design distinguishes "broken" from "the walk failed to move the board": `s5.0` renders *iff* `fresh === 0` at a single ternary, so `s5.0` is **inconclusive**, never a verdict. A failure is surfaced to the operator **before** any first-session test. |
| R-b | **`TradesScreen.tsx` merge complexity** — 6 158 lines, four findings, one commit (HLD R6) | High | `W2-TS` is the sole owner for the wave; every edit here is addressed by a **grep anchor, never a line number**; §1 of the LLD proves disjointness from P0-2's fifteen edits and fixes the internal ordering (D1 before the last D2 rename). |
| R-c | **A consumer of `guideTourCompleted` was missed**, and the release path never setting it breaks something | Low | Fully enumerated and re-grepped: `useGuide` (writes), the two `TradesScreen` sites being edited, `resetGuideProgress`. Settings reads `guideDismissed`, not this. Re-grep at build time. |
| R-d | **An `onboarding`-layer experiment is already running**, and stopping it is irreversible for that version | Med | Step 0 branches on it; branch B may need **zero** writes; branch C saves the incumbent's full spec before stopping and restores by `revise` + `transition`. |
| R-e | **The experiment's overlay is cached client-side**, so stopping it leaves the operator in treatment until the next fetch | Low | Documented behaviour. Force-quit and reopen; ≥30-min foreground refetch otherwise. |
| R-f | **The funnel is less readable than the plan assumed** — `deck_regenerated` and `guide_tour_reenabled` are dropped, and 31 names remain unregistered after this batch | Med | Named in A8's limitation note rather than discovered mid-test. The D3 proof depends on neither. `deck_regenerated`'s registration is recommended to the orchestrator; the rest go to `NEXT.md`. |
| R-g | **D1's residual** — a like-first user who never likes again still does not sign off | Low | S-42's adjudicated one-condition fix, stated in A4 rather than hidden. `W3-QA` reports the case; M-b is a `NEXT.md` candidate. |
| R-h | **`s2.wait` may only exist because the harness injects latency** | Low | Not a P0-8/P0-9 defect. Recorded in the validation findings: "13 beats" overstates the real-world tour by one for a user on a warm pre-gen. |
