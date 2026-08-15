# Feature Scope — compressed-board trade generation (pool prune + boarded fallback)

**Date:** 2026-08-15
**Entry point:** direct ask — field bug found running the real engine against the operator's league FFV3 (`league_id 1312140920132497408`)
**Builder:** Claude Code session, worktree `loving-shtern-12e4b1`
**Operator sign-off on waivers:** **needed** — §3 Maestro delta is waived (backend-only, no mobile surface); §5 declares Tier 4. Both flags were built dark and **flipped ON by operator instruction on 2026-08-15** after the §6 field verification.

---

## 0. The bug

Three of the four boarded opponents in FFV3 produced **zero** trade cards at any
per-opponent budget while the fourth produced a full five. Reproduced read-only
against prod boards; the board shapes are the whole story:

| Member | Entries | min | median | max |
|---|---|---|---|---|
| mattmurf77 (the user) | 628 | 1100 | 1208 | 1972 |
| jonbonjourvi | 648 | 1100 | **1379** | 1972 |
| MangoPatti | 646 | 1200 | **1201** | 1816 |
| Bcork | 646 | 1200 | **1201** | 1800 |
| gdubs10 | 646 | 1200 | **1201** | 1839 |

The three zero-yield boards are floor-pinned: the member ranked their top handful
and left everyone else at the 1200 floor — a realistic "started ranking and
stopped" state, not corruption.

**Defect 1 — `backend/trade_optimizer.py` pool prune.** The v3 candidate pools are
the top `v3_pool_size` (12) assets per side by the raw divergence
`_vo(p) - _uv(p)`. `elo_to_value` is exponential, so a board sitting uniformly
lower deflates high-Elo players far more than low-Elo ones: a stud loses
thousands of value points, a bench body loses tens. Every genuinely tradeable
stud therefore sorts **below** the user's worthless bench, the top-12 fills with
junk, and the pair yields nothing. The key is not invariant to a board-wide scale
offset — a difference that carries **zero** information about which player either
side prefers.

**Defect 2 — `backend/trade_service.py` branch.** The boarded/unboarded split was
`if member.has_rankings: <divergence> else: <consensus>`, with no fall-through. A
boarded member yielding zero divergence cards got no consensus fallback either
and vanished from the deck — so a leaguemate who ranked *a little* became a worse
trade partner than one who never ranked at all.

## 1. Analytics scope

- [x] **(c) WAIVED — no analytics needed because:** no new user-visible surface,
  no new event trigger moment, no new client. Deck composition changes, and the
  existing deck impression/outcome spine (`deck_impressions`, `deck_outcomes`,
  card `basis`) already records which member a card came from and whether it was
  divergence- or consensus-basis. That is exactly the signal needed to watch the
  rollout: **consensus-basis cards attributed to a `has_rankings=true` member is
  a new-but-already-instrumented combination**, readable off existing rows with
  no taxonomy change.

## 2. Schema & flag scope

- New/changed tables or columns: **none**.
- New/changed feature flags: **two**, both registered in
  `backend/feature_flags.py` `FLAG_KEYS`, `config/features.json`,
  `backend/tests/fixtures/flags/{release,onboarding-v2,profiles-on}.json`, and
  `docs/config-reference.md`.

  | Flag | State | Graduation |
  |---|---|---|
  | `trade.pool_calibration` | **true** — flipped 2026-08-15 | Operator instruction after the §6 field verification. The stated criterion (deck quality confirmed on FFV3 **plus one healthy-board league**) was met only in part: latency is measured clean and FFV3 is verified, but no second league was checked and card *quality* was never reviewed. Graduated on the operator's call with that gap open. |
  | `trade.divergence_fallback` | **true** — flipped 2026-08-15 | Operator accepted that a boarded member may now show `basis:"consensus"` cards. |

  **Both flags were built dark and flipped ON by explicit operator instruction**,
  not by agent self-selection. Each remains its own kill switch; setting either
  back to `false` in `config/features.json` is deploy-free.

- New env vars / `model_config` keys: **none**. Deliberate — see §6 on why
  `v3_pool_size` is *not* the rollback lever.
- **Ship-the-knob / rollback:** each flag is its own kill switch and is
  deploy-free (`config/features.json`). Off ⇒ the engine is byte-identical to
  today, pinned by tests.

## 3. Test scope

- [x] **WAIVED (Maestro):** backend-only. No mobile file touched, no screen, no
  navigation, no `testID` added or renamed, no route contract changed. The deck
  *contents* change; the deck *surface* does not. Smoke flows crossing the trades
  surface (`04-tabs-navigation`) are unaffected — they assert render, not card
  identity.
- `testID`s added/renamed: **none**.
- **Capture delta:** none — no visual change.
- Smoke-suite impact: none.
- Backend pytest: **new** `backend/tests/test_compressed_board.py` (8 tests).
  Every fixed behaviour is asserted **paired with a flag-off test pinning the old
  behaviour**, so the tests prove the fix is what changed it *and* that the kill
  switch restores today's engine:

  | Test | Asserts |
  |---|---|
  | `..._evicts_studs_from_give_pool_today` | flag off: compressed board starves the pool ⇒ zero cards |
  | `..._keeps_studs_in_a_size_2_give_pool` | flag on: a stud reaches a `v3_pool_size=2` give pool (pool membership proven through the public return value, no white-box reach) |
  | `..._invariant_to_a_board_wide_offset` | flag on: +200 Elo to every opponent rating leaves the deck identical; flag off: it does not |
  | `..._byte_identical_to_the_unpatched_engine` | flag off: cards only use assets the original prune would have selected |
  | `..._leaves_a_healthy_pair_alone` | flag on, same-scale boards: deck identical, composites included |
  | `..._vanishes_today` / `..._still_yields_cards` | defect 2, before and after |
  | `..._does_not_touch_a_member_who_already_has_cards` | fallback is strictly additive |

  Fixture note: the compressed fixture reproduces the **field trade shape**
  (Gibbs ↔ A.J. Brown) — a stud-for-stud swap each side prefers on its own board,
  so both surpluses are strongly positive and only the prune stands in the way.

- Full suite: **2771 passed, 1 skipped** (see `living-memory/TEST_LEDGER.md`).
- Latency, measured per pair on real FFV3 boards (`v3_pool_size=12`):
  calibration on ≈ 1.9–2.6 s, off ≈ 1.5–5.2 s. No regression.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route added, renamed, removed, or contract-changed. Cards keep their existing `basis` field and values. |
| `living-memory/LLD.md` | n/a | No schema/route/invariant *convention* shifted; this is a scoring-internal change behind flags. |
| `docs/architecture.md` | n/a | No module added or re-wired. `trade_optimizer` ← `trade_service` wiring unchanged. |
| `living-memory/HLD.md` | n/a | No new module, client, or major flow. |
| `docs/cross-client-invariants.md` | n/a | No shared constant, enum, or color touched. `basis` values (`divergence`/`consensus`) are unchanged — only which member can carry which. |
| `docs/glossary.md` | **updated** | Added *board compression* and *pool calibration*. |
| `docs/config-reference.md` | **updated** | Both flags documented in the trade-engine flag table. |
| ADR / `DECISIONS.md` | **updated** | `D-052` — why scale-calibration over rank-normalisation, and why the fallback rather than a board-quality threshold. |

## 5. Ship gate declaration

- **Simulator-gate tier: 4** (backend-only) per the matrix in `docs/runbook.md`.
  Required: pytest — done, green. No sim run required, so no
  `qa/sim-runs/last-sim-run.json` is written and `githooks/pre-push` does not
  gate this change (it only blocks on `mobile/src` diffs).
- Evidence: `living-memory/TEST_LEDGER.md` entry dated 2026-08-15.
- Operator deviation from the matrix: **none**.

## 6. Field verification (read-only, real prod boards)

Deck regenerated for mattmurf77 in FFV3 at the production `v3_pool_size=12`.
Boarded opponents only; deck cap `global_target = max(30, max_per_opponent*6)` = 30.

| Config | jonbonjourvi | MangoPatti | Bcork | gdubs10 |
|---|---|---|---|---|
| today (both off) | 5 divergence | **0** | **0** | **0** |
| `pool_calibration` | 5 divergence | 0 | 0 | **5 divergence** |
| both flags | 5 divergence | **5 consensus** | **5 consensus** | 5 divergence |

Two honest caveats:

1. **The deck total stays at 30.** Boarded members are visited first by design
   (`_generate_trades_v2` sorts `has_rankings` ahead of the rest so divergence
   cards are never crowded out). So rescuing three boarded members *displaces*
   consensus cards from unranked members further down the queue. The deck does
   not get bigger; its composition shifts toward real counterparties. That is the
   intended priority order, but it is a visible change and the operator should
   know it is coming.
2. **Calibration alone does not rescue MangoPatti or Bcork.** A single
   multiplicative factor removes a board *offset*; it cannot undo a *nonlinear*
   compression (the opponent's board is closer to `value_u^a`, a<1, than to
   `c·value_u`). For those two the productive assets still sit outside the
   calibrated top 12, and it is the consensus fallback that covers them. Logged
   as `Q-017` — a quantile-matching calibration is the candidate next step if the
   operator wants divergence cards there rather than consensus ones.

**Why `v3_pool_size` is not the fix.** Raising it to 30 does rescue all three with
divergence cards — but measured per pair on real boards it costs **26 s
(Bcork), 80 s (MangoPatti), 102 s (gdubs10)** against ~2 s at pool 12, because
enumeration is cubic-ish in pool size on both sides. A full 11-opponent deck did
not finish in 10 minutes. It is a deploy-free knob but not a shippable
mitigation, and it does not fix the ordering defect underneath.
