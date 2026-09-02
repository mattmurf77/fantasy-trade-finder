# Feature Scope — Consensus roster-fit sort key (`consensus_fit_weight`)

**Date:** 2026-09-02
**Entry point:** direct ask (lead-verified premise 2026-09-01; R7 of [docs/reviews/2026-08-22-trade-model-restrictiveness.html](../../reviews/2026-08-22-trade-model-restrictiveness.html) in its sort-key form — the pool-prune form was rejected at 5.5× cost / stuffed packages)
**Builder:** agent worktree `claude/consensus-fit-sort-key` (build + prove); the lead ships
**Operator sign-off on waivers:** needed — §1(c) and §3 (structural guard, TestFlight) are waived below with reasons; surfaced to the lead in the final report

---

## 0. What changes, in one paragraph

`backend/trade_service.py::_generate_consensus_for_pair` serves **84.5%** of production cards (every pairing where the partner has no published board). It emits the first `max_cards` combos that clear its gate stack **in pool order**, so the two pool sorts *are* the ranking of which consensus cards exist — and both were pure `seed_value`. Both sides are priced by the same consensus functional, so the partner's gain is the exact negative of the user's and the only modelled reason a counterparty would accept is roster fit, which was not in the sort at all. One new `model_config` knob, `consensus_fit_weight` (default **0.0**), blends it in: each pool sorts on `seed_value × (1 + w × fit_norm)`, `fit = marginal_value(pid, opp_repl) − marginal_value(pid, user_repl)` on consensus prices (negated for the receive side), normalised to `[−1, 1]` per pool; picks get fit 0; the give pool keeps `pos ∈ shed_positions` as its primary key. **Reorders only** — no gate moves. At `w = 0` the sort-key factory returns `seed_value` itself: byte-identical, golden-proven.

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [ ] **(b) Existing events cover it** — `trade_card_impression` / the deck-outcome corpus already carry `basis`, `give_positions`, `receive_positions`, `need_fit`, `fairness_score` per served card, so "did fit-sorted consensus decks change like rate / positional mix" is answerable from what is already logged, split by `basis == "consensus"` as D-095's C2 mitigation prescribes. **The new `card.consensus_fit` stamp is NOT added to `features_json`** in this change (that dict at `backend/server.py:4498` names its keys explicitly, so the stamp is invisible to it) — adding it would touch the analytics surface and is out of scope here; noted as a follow-up in the code-walk.
- [x] **(c) WAIVED — no NEW analytics needed because:** the change is a sort-key inside one generator with no new user-visible surface; the existing impression/decision events, split by basis, are the measurement. No event is added, so no taxonomy or data-dictionary entry.

## 2. Schema & flag scope

- New/changed tables or columns: **none**. `TradeCard.consensus_fit` is an in-process dataclass field (never serialized — `trade_card_to_dict` at `server.py:11846` and `features_json` at `server.py:4498` both emit named keys only; no `asdict`/`__dict__` dump of cards exists in `backend/`).
- New/changed feature flags: **none**. The knob is its own kill switch (0 = byte-identical).
- New env vars / `model_config` keys: **`consensus_fit_weight`** (float, default 0.0) → registered in **both** stores: `trade_service._DEFAULT_CFG` and `database._MODEL_CONFIG_DEFAULTS` (the DB seed — `PUT /api/admin/config/<key>` refuses keys without a row, and rows are created only by the boot migration at `database.py:~3184` from that list). Documented in `docs/config-reference.md` § Trade engine v2 (Tier 1). **Ship-the-knob:** deploy at 0.0 (boot seeds the row) → `GET /api/admin/config` shows `consensus_fit_weight: 0.0` (deploy-landed check) → `PUT /api/admin/config/consensus_fit_weight` to the recommended value in [results.md](results.md). **Rollback:** the same PUT back to `0` — deploy-free.
- Bake-off dispositions: `MODEL_A_PROFILE` **pins the identity 0.0** (the C4 `v3_shape_max_delta` rule, not the D-095 exclusion — the live row is going to move, and an unpinned arm A would inherit it silently); `MODEL_CHALLENGER_PROFILE` deliberately does not pin it (the challenger is the live engine under an overlay). Recorded in `backend/tests/test_bakeoff_arm_a_golden.py::_PINNED_KNOBS` and `docs/plans/three-model-bakeoff/scope-phase2.md`.

## 3. Evidence scope

- [ ] **Structural guard:** `mobile/tests/check-<name>.js` — **WAIVED because:** backend-only; no mobile/web file is touched and no client reads the new field.
- [x] **Unit tests:** `backend/tests/test_consensus_fit_sort_key.py` (25 tests):
  - **golden, knob 0** — the consensus generator's output on the engine-quality deck fixture AND on the mirror fixture (both profile modes), in emitted order, captured on a `git archive origin/main` (`ce3f443c`) tree with the same file, asserted byte-identical at the default and at an explicit `0.0`; the mirror golden is also asserted NOT to hold at `w = 0.5` (non-vacuity), and the engine-quality fixture is documented as fit-symmetric (it proves identity, not sensitivity);
  - **mirror fixture, knob > 0** — user 6 startable WR + 1 RB, partner 1 WR + 6 RB, `has_rankings=False`, identical consensus prices per rung: at `w = 0` (profile-silent) the first card is `uWR1 → oQB` (the partner's lone 1700 QB into a roster that already starts one); at `w = 0.5` the first card is `uWR1 → oRB1`, the mirror swap, with `consensus_fit == 1.0`; with real `analyze_roster_strengths` profiles the need filter + shed key already lead with the swap at `w = 0` (stated, not hidden);
  - **sign test** — every emitted card at every `w ∈ {0, 0.25, 0.5, 1}` in both profile modes still clears `rv − gv ≥ user_gain_epsilon`; uncapped, `w = 0.5` emits the same SET as `w = 0` in a different order;
  - **pick neutrality** — a pool of picks sorts identically at every `w`; an all-picks card stamps 0.0; an all-zero-fit pool does not divide by zero;
  - **call-time read** — a process-global 0.5 overlaid with `_cfg_override({knob: 0.0})` produces the knob-0 deck (arm A's pin and the #189 relaxed pass reach it);
  - **registration** — `_DEFAULT_CFG` and `_MODEL_CONFIG_DEFAULTS` agree at 0.0; arm A pins 0.0; the challenger does not;
  - **D-159 junk guard** — on three harness fixtures (`12t_1qb@u0`, `12t_1qb@u8`, `mirror@b`), the sub-450 body share of consensus cards at `w = 0.5` ≤ the `w = 0` share + 2pp and the deck does not shrink (clock monkeypatched, G-065).
  - Three sabotages proven red → green (byte-copy restore, `__pycache__` cleared per G-060); recipes in the module docstring, outcomes in [results.md](results.md) § Sabotages.
- [x] **Code-walk proof:** [code-walk.md](code-walk.md) — call-time knob read, the `w = 0` identity, pick neutrality, every caller of `_generate_consensus_for_pair` and which overlays reach it, the server view path for the stamp, and the "where does the deck get re-sorted" trace that qualifies the premise.
- [x] **Harness measurement:** [measure_consensus_fit.py](measure_consensus_fit.py) → `results-raw-f075.json` / `results-raw-f050.json` (the two thresholds prod sends) / `results-raw-f085.json` (the 2026-08-21 regime) → [results.md](results.md). Prod-pinned baseline (`filler_min_frac` 0.15, `overpay_adjusted` 0, `trade_elo_gap_max` 0, `v3_shape_max_delta` 2), `PYTHONHASHSEED=0`, clock frozen (G-065), baseline run twice and byte-identical in every cell; sweep `w ∈ {0, 0.25, 0.5, 1}` × 5 viewpoints × 2 paths × 3 arms × 3 thresholds.
- [ ] **Manual TestFlight checklist** — **WAIVED because:** no client change; the runtime check that matters is server-side and is written as a prod verification for the lead in results.md § After the flip (a specific league shape — a viewer with no need position — where RB-in cards from the partner's surplus should now fill the consensus slots).
- `testID`s added/renamed: none.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | n/a | no route added or changed; the new knob is reachable through the existing `GET/PUT /api/admin/config` contract, whose key set is documented as "every `_MODEL_CONFIG_DEFAULTS` row" |
| `docs/config-reference.md` | **updated** | § Trade engine v2 (Tier 1) — new `consensus_fit_weight` row after `consensus_fairness_floor`: semantics, where it bites, the stamp, arm dispositions, the **DB seed** (row exists from first boot, which is what makes the PUT reachable), recommended live value and the rollback PUT |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | n/a | no convention shifted — the knob follows the existing D-098 call-time-`_c` rule and the existing two-store registration discipline (the lead owns living-memory writes per the brief) |
| `docs/architecture.md` (module wiring / data flow changed) | n/a | a sort key inside one function; no module, import or data-flow edge changes (`replacement_levels` / `marginal_value` are module-local helpers the optimizer already uses) |
| `living-memory/HLD.md` (architecture genuinely shifted) | n/a | as above |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | n/a | no client-visible constant, enum or wire key |
| `docs/glossary.md` (new domain term) | n/a | "fit asymmetry" / "marginal value" already exist in the Tier-2 vocabulary (`docs/plans/trade-engine-tier2-models.md`); no new term |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | **for the lead** | two non-obvious choices to record when shipping: (1) fit as a **sort-key blend**, not a prune or a gate — the pool-prune prototype was rejected (5.5× cost, stuffed packages) and a gate would move the fairness floor; (2) arm A **pins** the identity rather than excluding it (C4 rule over D-095 rule, because the live row will move) |
| `docs/plans/three-model-bakeoff/scope-phase2.md` | **updated** | knob disposition row |
| `docs/plans/README.md` | **updated** | thread-folder row |

## 5. Ship gate declaration

- **CI green:** `pytest backend/tests` — 4508 passed, 1 skipped on the branch tip (clean-main baseline 4483 passed, 1 skipped; +25 new); `tsc --noEmit` and `testid-lint` untouched (no mobile file changed). Counts in [results.md](results.md).
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` — **the lead writes it** (brief: no living-memory writes from this worktree); the ledger text is drafted in results.md § Ledger draft.
- **TestFlight verification:** waived (§3) — replaced by the prod verification steps in results.md § After the flip.
- Express lane declared by the operator? **No** — full gates.
