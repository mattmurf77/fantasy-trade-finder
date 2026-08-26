# Feature Scope — Serving re-light (W1 interleaved serving, PR-S)

**Date:** 2026-08-20
**Entry point:** fit-challenger build — PLAN-v2 §3 PR-S (owed skeleton: LLD §7)
**Builder:** PR-S coding agent (worktree `trade-suggestions-review-69c9eb`)
**Operator sign-off on waivers:** needed on §3's mobile-guard waiver (same waiver
already surfaced as PRD-build decision-register row 9)

**What this scope covers:** re-lighting interleaved bake-off serving for the W1–W2
screen round (arms B + D + C, per-arm user decisions), which is a **user-visible
serving change** made entirely by post-merge `model_config` writes. PR-S itself
ships **no serving-code change and no knob-value change** — it ships the regression
tests, this scope block, the operator TestFlight checklist
([testflight-checklist-serving.md](testflight-checklist-serving.md)), and the
re-ranker-bypass code-walk (§6 appendix). All flips are post-merge
`scripts/set_knob.py` writes, logged via M1.

---

## 1. Analytics scope

- [x] **(b) Existing events/columns cover it:**
  - `deck_impressions.model_arm` / `.arm_rank` / `.policy_version` — which arm
    produced each served card (answers: per-arm exposure).
  - `deck_outcomes` joined on `impression_id` — per-arm like/decline decisions
    (answers: the co-primary like-rate reads in PLAN-v2 §4).
  - `bakeoff_runs` (`served_arm`, `arms_json`, `agreement_json`, `config_json`) —
    per-run serving mode, arm accounting, config snapshot.
  - `model_config_changes` (PR-M) — when each W1 knob flipped (answers: window
    censoring per R-5).

  No new events. The whole point of the re-light is that the attribution spine
  already exists and per-arm decisions start accruing the moment serving is
  interleaved.

## 2. Schema & flag scope

- New/changed tables or columns: **none** (PR-S is tests + docs only).
- New/changed feature flags: **none**. `trade.bakeoff` (existing) remains the
  program-level switch.
- New env vars / `model_config` keys: **none in-PR.** The re-light is VALUE flips
  on existing keys, made post-merge via `scripts/set_knob.py` (logged,
  `source='operator'`), never in this PR:

  | Knob | Today (2026-08-20) | W1 value | Meaning of the W1 value |
  |---|---|---|---|
  | `bakeoff_serve_interleaved` | 0.0 (DB row; operator set 2026-08-19 — code default is 1.0, HLD §8) | **1** | interleaved decks served; per-arm decisions begin |
  | `bakeoff_group_size` | 10.0 (default) | **0** | composition killed; live draft path = plain per-arm `team_draft` (HLD F-6) |
  | `bakeoff_deck_limit` | 30.0 (default) | **30** | confirm-as-is; the cap the team draft fills to |
  | `bakeoff_include_challenger` | 1.0 | 1 (unchanged) | arm D rostered (R-1) |
  | `bakeoff_include_gen_v2` | 1.0 | 1 (unchanged) | arm C rostered (R-1; self-caps by supply) |
  | `bakeoff_include_baseline` | 0.0 | 0 (unchanged) | arm A stays dark |

  Fit's own knobs (`bakeoff_include_fit`, `bakeoff_serve_fit`) do not exist until
  PR-F1/PR-F3 and are 0 at W1 regardless — fit is not part of this scope's serving
  surface.

  **Ship-the-knob rollback lever:** `bakeoff_serve_interleaved = 0` — one logged
  write, no deploy; next deck is arm-B normal-stack (dark mode: all arms still
  generate and log). Rehearsed in the checklist's R1/R2 steps. Full ladder in §5a.

## 3. Evidence scope

- [ ] **Structural guard (`mobile/tests/check-*.js`):** **WAIVED** — no mobile code
      changes; the client renders interleaved decks through the same card UI it
      renders today (arm labels are deliberately not shown). Waiver surfaced as
      PRD-build decision-register row 9; operator sign-off required there covers
      this row.
- [x] **Unit tests:** `backend/tests/test_bakeoff_serving.py` (extended in-PR):
  - `test_zero_card_arm_deck_still_fills` (S1b) — the 2026-08-18 shrink inverted:
    under `bakeoff_group_size = 0` (the W1 posture — HLD F-6 establishes the
    `team_draft` fallback at `bakeoff_runner.py:1424-1427` as the live path), a
    zero-card arm forfeits (counted, recorded in `arms_json`) and the surviving
    arms fill the deck to `bakeoff_deck_limit`. Proven RED under a named sabotage
    (draft loop terminated on first dry participant — the shrink behavior), green
    on revert.
  - `test_zero_card_arm_composed_deck_shrinks_under_group_quotas` — the same
    pinned fixture under `group_size = 10`: consensus/empty groups compose 0 and
    the deck tops out at 20/30. Documents WHY `group_size = 0` is a load-bearing
    W1 value, and trips if composition's supply behavior ever changes.
  - `test_run_row_serving_mode_is_served_arm_not_a_bypass_marker` — pins the §6
    finding: `served_arm` (NULL = interleaved / `'current'` = dark) is the only
    recorded serving-mode state; no bypass marker exists on the run row.
  - Pre-existing in the same file and load-bearing for this scope:
    `test_post_generation_rerankers_cannot_touch_the_merged_deck` (every reorderer
    replaced with a reversing spy; none may run) and
    `test_rerankers_do_run_when_the_bakeoff_is_off` (the mirror), plus
    `test_likes_you_injection_does_not_reorder_the_interleave`.
- [x] **Code-walk proof:** §6 appendix below — file:line-cited trace that
      `bypass_rerankers()` covers every reordering layer the runner docstring
      names. Verdict: **all seven layers covered**; two deliberate non-bypasses
      (suppression, likes-you) are order-safe and tested.
- [x] **Manual TestFlight checklist:**
      [testflight-checklist-serving.md](testflight-checklist-serving.md) — draft B
      §7's 8 steps + the 2-step rollback rehearsal, run by the operator within the
      hour of the W1 flip. This is the only runtime evidence the re-light gets
      (D-056).
- `testID`s added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added/changed; PR-S is tests + docs (the PUT `source` delta is PR-M's row) |
| `living-memory/LLD.md` | n/a in-PR | no convention shift in PR-S; the fit-knob conventions land with the F-packages per PRD-build §7 |
| `docs/architecture.md` | n/a | no module wiring change |
| `living-memory/HLD.md` | n/a | no architecture change (serving machinery already exists; this re-lights it by config) |
| `docs/cross-client-invariants.md` | n/a | no shared constants/enums/colors touched (fit-challenger's n/a note is a PR-F3-time item, PLAN-v2 §7) |
| `docs/glossary.md` | n/a | no new domain term ("interleaved serving", "team draft", "dark mode" already in use since Phase 3) |
| ADR / `DECISIONS.md` | n/a in-PR | the two fit-challenger ADRs and the `group_size = 0` DECISIONS entry are build-time items owed by PLAN-v2 §7 at the F-package/flip stage, not by PR-S |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` + `maestro-testid-lint` on the
  pushed sha (`FTF_SKIP_SIM_GATE=1` standing posture per D-056, evidence noted).
- **No knob values change in-PR** — reviewer-checkable: the PR diff touches only
  `backend/tests/test_bakeoff_serving.py`,
  `docs/plans/fit-challenger/testflight-checklist-serving.md`, and this file.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry naming the new tests,
  the sabotage (draft loop terminated on first dry participant → S1b red → revert
  → green), and this code-walk.
- **TestFlight verification:** the §3 checklist is run by the operator at the W1
  flip (post-merge), outcome logged in TEST_LEDGER. It gates the flip, not the
  merge.
- Express lane: **no** — full gates (PLAN-v2 §6: "full gates, no express").

### 5a. Revert playbook

W1-specific revert (the R-9 tripwire's action, rehearsed in the checklist):

- **`bakeoff_serve_interleaved = 0`** — one logged `set_knob.py` write. Next deck
  is arm-B normal-stack; all arms keep generating and logging (dark mode), so
  diagnostics continue while users see the pre-W1 experience. Deck-shrink
  tripwire: median < 22 → investigate same day; median < 18 on 2 consecutive days
  → this revert (R-9).
- **`bakeoff_group_size = 10`** — restores composition if the team-draft posture
  itself is ever the problem (not expected; it is the *less* shrink-prone path).

Full knob-rollback ladder for the fit stages (HLD §6, rungs 1–5 — each rung one
logged `set_knob.py` write, no deploy; rungs 1–4 become live once the F-packages
merge):

1. `bakeoff_serve_fit = 0` — fit out of the draft; generation + diagnostics continue.
2. `bakeoff_include_fit = 0` — fit out of the fan-out entirely; zero added cost.
3. `fit_max_packages_per_pair` ↓ — job-time relief without leaving the roster.
4. `fit_junk_floor = 1` / `fit_r5_mode` — pre-wired dark levers, flipped only as a
   pre-registered iterate action, never mid-window.
5. `trade.bakeoff` off — program-level kill (feature flag, not `model_config`);
   also stops attribution and unfreezes swipe-K (`elo_freeze_mult`).

---

## 6. Appendix — re-ranker-bypass code-walk (D-056 code-walk proof)

**Claim under proof:** `bypass_rerankers()` covers every post-generation reordering
layer the runner docstring enumerates (`backend/bakeoff_runner.py:83-88`: "F2
Thompson, A6 diversity + per-target cap, F3 fatigue multipliers, F5 taste, F6 value
model, F7 wildcard insert, F9 first-session shaping"), so an interleaved deck's
order is exactly the interleaver's. Verified against the working tree at PR-S build
time (parent `a76498e`).

**The predicate and its single consultation point:**

- `backend/bakeoff_runner.py:374-383` — `bypass_rerankers(league_id, pinned_give,
  pinned_receive, opponent_user_id)` returns `serve_interleaved() and
  bakeoff_active(...)`. Deliberately False in dark mode (`serve_interleaved()`
  reads `bakeoff_serve_interleaved`, `bakeoff_runner.py:218-244`) and for
  pinned/opponent-scoped/demo decks (`bakeoff_active`,
  `bakeoff_runner.py:360-372`).
- `backend/server.py:5617-5618` — `_run_trade_job` computes it once per job as
  `bakeoff_fixed_order`; every bypass site below checks that local. (Arm-agnostic
  by construction — HLD §4: sites check `bakeoff_fixed_order`, never the arm — so
  fit inherits the same protection at W4 with zero new code.)

**Layer-by-layer:**

| # | Layer (docstring name) | Bypass site | Mechanism |
|---|---|---|---|
| 1 | F2 Thompson (v1 + thompson_v2) | `server.py:5858-5861` | The entire ordering block — `if not bakeoff_fixed_order and league_id != "league_demo" and (_thompson_deck_enabled() or _deck_thompson_v2_enabled() or ...)` — is skipped, so `_order_deck` (`server.py:5868`) is never called. The Thompson draw lives only inside `_order_deck` (`server.py:3836-3838`). |
| 2 | A6 diversity + per-target cap | `server.py:5858-5861` (same gate) | Diversity penalty (`server.py:3906-3926`) and `_cap_per_target` (`server.py:3932-3933`, knob `deck_max_per_target`) run only inside `_order_deck` — unreachable when the gate skips it. (LLD R-g relies on exactly this: per-target caps are disabled on interleaved decks for every arm equally.) |
| 3 | F3 fatigue multipliers | `server.py:5772` | `fatigue_mults = None if bakeoff_fixed_order else _deck_fatigue_multipliers(...)` — never computed; and the consuming ordering block is independently gated (#1). |
| 4 | F5 taste | `server.py:5810-5811` | `if (_deck_taste_enabled() and league_id != "league_demo" and not bakeoff_fixed_order)` — `taste_mults` stays None. |
| 5 | F6 value model | `server.py:5833-5834` | `if (_deck_value_model_enabled() and league_id != "league_demo" and not bakeoff_fixed_order)` — `value_scores` stays None (base-key swap never happens). |
| 6 | F7 wildcard insert (exploration) | `server.py:5620-5626` | `explore_active = (... and not bakeoff_fixed_order)` — gates the over-generation kwargs (`server.py:5627-5632`), the pool split (`server.py:5691-5693`), and `_apply_exploration_slot` (`server.py:5905`). The pool-picker's internal thompson_v2 read (`server.py:4917`) is only reachable via `explore_active`, so it is covered transitively. |
| 7 | F9 first-session shaping | `server.py:5964-5966` | `shaped = (final_cards if bakeoff_fixed_order else _apply_first_session_shaping(...))` — reorder/clamp skipped; the additive `first_deck` job field still fires (non-reordering, intended). |

**Two layers that run on interleaved decks BY DESIGN (order-safe, each tested):**

- **Decline suppression** — `_apply_deck_suppression` (`server.py:5762`) stays
  live: it only REMOVES cards (a durable user promise that shifts every arm
  equally); the fatigue *multipliers* beside it are what's bypassed (site #3).
  Pinned by `test_post_generation_rerankers_cannot_touch_the_merged_deck`, which
  asserts suppression is still reached while every reorderer is not.
- **Likes-you injection** — `_inject_likes_you_cards` (`server.py:5716`) runs and
  re-sorts, then `server.py:5733-5735` immediately repairs it: `if
  bakeoff_fixed_order: final_cards = _bakeoff.restore_order(...)`
  (`bakeoff_runner.py:1276-1291` — injected cards keep the top, every arm card
  returns to its interleaved index). Pinned by
  `test_likes_you_injection_does_not_reorder_the_interleave`.

**Verdict: no gap.** All seven docstring layers are bypassed for interleaved decks;
the two non-bypassed layers are removal-only or order-restored, and both are pinned
by existing tests in `backend/tests/test_bakeoff_serving.py`.

**Finding (recorded, not fixed — PR-S is forbidden to touch serving code):** the
bypass leaves **no dedicated marker** in any persisted row. The only recorded
serving-mode state is `bakeoff_runs.served_arm` (NULL = interleaved ⇒
`bypass_rerankers` was True for that deck; `'current'` = dark ⇒ the normal stack
ran). M4's "re-ranker bypass assertion" tripwire must therefore key on
`served_arm IS NULL` joined to the deck's impression rows, not on a marker column.
Pinned by `test_run_row_serving_mode_is_served_arm_not_a_bypass_marker` so the
contract cannot drift silently; if a dedicated marker is ever wanted it is new
schema (a `bakeoff_runs` column), to be scoped then — not invented by a test now.
