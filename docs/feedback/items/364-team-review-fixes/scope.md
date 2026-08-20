# Feature Scope — Team Review defect batch (#364 / #367 / #368) + outlook transparency

**Date:** 2026-08-20
**Entry point:** in-app feedback #364, #367, #368 (operator `mattmurf77`, v1.15.0, screen `TeamReview`), plus two mid-session operator instructions (see §6)
**Builder:** session `team-outlook-experience-27a7a1`
**Operator sign-off on waivers:** yes — scope selection made in-session ("confirmed defects now, plan the rest"; "fix upstream — repairs Trends too")

---

## 1. Analytics scope

- [x] **(b) Existing events cover it.**
  - `team_review_exited` with `outcome='completed'` already answers "did the user finish the
    review?" — it is registered in `analytics_taxonomy.py:423` and classified as a terminator
    in `analytics_queries.py:104`.
  - A `team_review_completed` peer was written and then **deliberately removed**: the taxonomy
    comment block at `analytics_queries.py:96-105` exists precisely to stop one flow minting a
    second terminator series. Completion persistence is local (AsyncStorage), which needs no event.
- [x] **(c) WAIVED for the minimize-on-completion state itself** — it is device-local UI memory,
  the same class as the existing `ftf_team_review_collapsed` blob, which also emits nothing.

## 2. Schema & flag scope

- New/changed tables or columns: **none**.
- New/changed feature flags: **none**. All three fixes land inside the already-lit
  `trades.team_review`; `outlook.odds` gates the #364 surface and is unchanged. Both remain
  deploy-free kill switches via `POST /api/feature-flags/reload`.
- New env vars / `model_config` keys: **none**. `window.model` *reports* seven existing
  `_DEFAULT_CFG` knobs (`vet_age`, `youth_age`, `infer_w_*`, `infer_*_cut`); it does not add any.

## 3. Evidence scope

- [x] **Structural guard:** no new file. The two existing suites that own this surface —
  `mobile/tests/check-team-review.js` (7 assertions) and `check-outlook-bands.js` (7) — still
  pass, including 5c "renders the band" and 5b "never renders a bare playoff percentage", which
  the reworded #364 caption and the new inputs card had to stay inside.
- [x] **Unit tests:** `backend/tests/test_team_review.py` **+6** (21 total),
  `backend/tests/test_trends_rank_deltas.py` **1 rewritten**.
  **All five are sabotage-proven red** — see `code-walk.md` §5.
- [x] **Code-walk proof:** [`code-walk.md`](code-walk.md) — file:line trace for each of the
  three defects and both operator instructions.
- [x] **Manual TestFlight checklist:** [`testflight-checklist.md`](testflight-checklist.md),
  9 steps. Runtime proof matters here: three of the five changes are copy/ordering the operator
  reads rather than logic a test can judge, and **nobody has seen the corrected divergence beat
  on a device**.
- `testID`s added: `team-review.window.inputs`, `team-review.standing.coverage`.
  `mobile/scripts/testid-lint.sh` passes.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated** | `GET /api/league/team-review` — `window.model` added; `divergence.higher_than_market` / `lower_than_market` semantics corrected. `GET /api/trends/consensus-gap` — `easiest_sells` direction corrected. |
| `living-memory/LLD.md` | n/a | No convention shifted. The "a client reads an encoding, it never restates one" rule that `window.model` follows is pre-existing (`equal_pick_share`). |
| `docs/architecture.md` | n/a | No module wiring change. `#368` restores an argument the route already computed; no new call edge. |
| `living-memory/HLD.md` | n/a | No new module, client, or flow. |
| `docs/cross-client-invariants.md` | **updated** | New § "Consensus-gap direction" — `easiest_sells` / `easiest_buys` now have two clients (Trends, Team Review) and one web consumer; the sign convention is exactly the class of thing this doc governs. |
| `docs/glossary.md` | n/a | No new domain term; "easiest sell" already defined, and its definition was the thing that was wrong. |
| `DECISIONS.md` entry | **added** | D-100 (sell direction reversed, upstream), D-101 (ship the inference model, not just its verdict). |

## 5. Ship gate declaration

- **CI green:** `pytest backend/tests` → **3606 passed, 1 skipped**. `tsc --noEmit` → clean.
  64 `check-*.js` suites → 0 failed. `testid-lint` → OK. All run locally pre-push.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` 2026-08-20 entry.
- **TestFlight verification:** checklist written, **UNRUN** — owed by the operator on the next build.
- Express lane declared by the operator? **No.** Full gates ran.

## 6. Waivers and scope boundaries — READ BEFORE ASSUMING THIS BATCH IS "#364–#371 DONE"

Four of the eight reports are **planned, not built**, by operator selection. They are specced in
[`plan-remaining.md`](plan-remaining.md), not shipped:

| Left out | Why |
|---|---|
| **#365** (window is age-only) | Changes `infer_team_outlook`'s score, which the **trade engine** consumes via `outlook_alpha` — a bright-line engine change needing its own scope, evidence and TestFlight pass. This batch instead makes the existing model *visible* so the misread is legible (§1 of `plan-remaining.md`). |
| **#366** (Handcuff tier, "elite" logic) | Needs an NFL depth-chart source FTF does not currently ingest, and `_bin_player` is three position-blind absolute cuts. Real modeling work. |
| **#369** (plan beat too thin) | Design expansion, not a defect. |
| **#371** (playoff outlook as primary driver) | Direction-setting; depends on #365's outcome. |
| **#370** (repeat liked trades) | Different surface (TradesHome deck), unrelated to Team Review. |
| **#367's second half** — the consensus-vs-league-specific **toggle** | The *inversion* is the defect and is fixed; the toggle is a new API parameter and control. Not silently dropped — specced in `plan-remaining.md` §4. |
| `web/js/app.js:6261` Trends copy | Left **untouched on purpose**: "Easiest sells from your roster" and "No over-valued players on your roster" are both still true under the corrected direction, so there was nothing false to fix. Noted so the omission is visible rather than assumed. |
