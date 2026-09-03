# Feature Scope — G-414: proportional gap-sweetener trigger (#414 "lopsided 1-for-1 served bare")

<!-- Copied from docs/templates/feature-scope.md. Every section answered or
     explicitly waived with a reason. Maestro / simulator rows are RETIRED per
     D-056 (2026-08-15) and absent from the template — nothing is skipped
     silently here. -->

**Date:** 2026-09-02
**Entry point:** feedback #414 (group G-414; batch plan in [413-sleeper-send-draft-picks/plan.md](../413-sleeper-send-draft-picks/plan.md))
**Builder:** G-414 backend build agent, branch cut from `origin/main` (`ce3f443c` at plan time; worktree HEAD `48f40de5`)
**Operator sign-off on waivers:** **not needed — no section is waived.** One row in §3 (structural guard) is answered *n/a* with its reason (no mobile file changes); that is an answer, not a waiver.
**PRD:** [prd.md](prd.md) · **LLD delta:** [lld-delta.md](lld-delta.md) · **Plan:** [plan-g414.md](plan-g414.md) · **HLD delta:** none (plan §4; noted in [status.md](status.md)) · **Round 1 critique:** [review-round-1.md](review-round-1.md) → [reconciliation-log.md](reconciliation-log.md)

---

## 1. Analytics scope

- [ ] (a) New events specced — no.
- [x] **(b) Existing events cover it.**
- [ ] (c) Waived — no.

**Reasoning.** The only new fact this change creates is *"this served card was balanced by the
gap pass, and by how much"* — and that fact is **already stamped on every impression row**:
`deck_impressions.features_json.gap_sweetener` (`backend/server.py:4519-4524`, written by
`_log_deck_signal_impressions` `:4378`), **null when the card was bare**, so sweetened vs. bare is
an exact split with no absent-key ambiguity. The proportional trigger changes *how often* that
field is non-null and what `gap_after` reads; the dict's shape `{player_id, side, gap_before,
gap_after}` is unchanged (lld-delta §7). Joined by `impression_id` to `match_swiped` (the prod
row for #414 carries one) and `trade_pass_layer1` (`backend/analytics_taxonomy.py:1440-1442`) it
answers the two questions this feature raises:

| Question | Read |
|---|---|
| Do users like/pass sweetened cards at a different rate than bare ones? | `deck_impressions.features_json->'gap_sweetener' IS NOT NULL` × `trade_decisions.decision` via `impression_id` |
| What share of served 1-for-1s sat above 10 % of their larger side, before vs. after? | `features_json` `give_value`/`receive_value` per row, bucketed by ship date; the sweetened share after |

No new event, no new property, no emitter change. `backend/analytics_taxonomy.py` and
`analytics_queries.NON_INTENT_EVENTS` are untouched — there is no `platform`-style taxonomy hazard
because no event's property set changes.

**Caveat — the impression gap.** Cards a client shows from a *streaming* snapshot and the final
mutation stack later trims never get a `deck_impressions` row; their swipes arrive with
`impression_id: 'none'` (the #414 row itself is one). Those swipes are invisible to the join above.
That gap pre-dates this change, under-counts both arms of the comparison equally, and is carried
as a separate follow-up (PRD Appendix A). Size it first with `share of match_swiped {source: deck}
WHERE impression_id = 'none'`.

## 2. Schema & flag scope

- **New/changed tables or columns:** **none.** `docs/data-dictionary.md` n/a. (`model_config` is an existing key/value table; a new *row* is seeded, not a column.)
- **New/changed feature flags:** **none.** `config/features.json`, `backend/feature_flags.py` `FLAG_KEYS`, and the flag tables in `docs/config-reference.md` are untouched. The change rides no flag: it is a knob-gated engine tightening whose kill value is byte-identical.
- **New env vars / `model_config` keys:** **one — `sweetener_gap_frac`**, float, default **0.10**.
  - Seeded via `_MODEL_CONFIG_DEFAULTS` (`backend/database.py`, row after `:2445`; loop `:3184-3195`, `INSERT OR IGNORE` / `ON CONFLICT DO NOTHING`, so an operator override survives redeploys). Mirrored in `_DEFAULT_CFG` (`backend/trade_service.py`, after `:516`); parity pinned by PRD T-9. Read only through `_c(...)` (`trade_service.py:1239-1245`) so the bake-off per-arm overlays compose.
  - `docs/config-reference.md` gains the row (PRD §7).
  - **Ship-the-knob / deploy-free rollback lever:** `sweetener_gap_frac = 0` → this feature off, byte-identical to 2026-08-31 (PRD T-4b proves it live on all four arms). **The lever surface is `PUT /api/admin/config/sweetener_gap_frac`** (`server.py:18577-18601`, `X-Cron-Secret`), which writes the row **and reloads `trade_service._cfg` inline** (`:18600`); `_cfg` is otherwise loaded only at process start (`:449`), so a raw `UPDATE model_config` does nothing on the running dyno until a restart — never describe a direct DB write as the lever. This lever is **independent of the D-143 pair rule**: `sweetener_gap_threshold ≤ 0` remains the master switch for the whole pass and still rolls back only together with `package_bench_trade_wide` (D-143). The new knob is a third, tightening-only lever and is **deliberately absent** from `bakeoff_profiles.MODEL_A_PROFILE` (`:98-105`) — arm A's threshold pin already short-circuits every caller before the fraction is consulted (lld-delta §5).
  - **Tuning floor:** values below **0.0952** turn `test_engine_quality.py::test_adding_a_pick_to_a_fair_package_does_not_raise_composite` red (the C1 fixture's bare card sits at a 9.52 % gap and its pick becomes an eligible equalizer under `_ORTHOGONAL_GATES_OPEN`) — recorded in the config-reference row and D-173 (unshipped parallel build; see D-175) so an operator retunes that fixture before lowering the knob.
  - **Arm-A bookkeeping (mini-round, Gap 3):** the golden's knob-drift guard (`test_bakeoff_arm_a_golden.py:724-727`) requires the key in `_PINNED_KNOBS` (`:527`) **and** a disposition row in `docs/plans/three-model-bakeoff/scope-phase2.md`. The key is added to `_PINNED_KNOBS` and dispositioned as an **excluded inert companion** (precedent: `package_floor_cross`, `scope-phase2.md:122`) — inert while `sweetener_gap_threshold ≤ 0`, which `MODEL_A_PROFILE` pins. `MODEL_A_PROFILE` is **not** edited and the golden is **not** re-captured.
  - **Retired invariant (mini-round, Gap 2):** "a huge absolute threshold ≡ off" no longer holds; `≤ 0` is the master switch. The one test that pinned it (`test_gap_sweetener_arm_c.py:239`) is the declared re-spec in §3.

## 3. Evidence scope

- [ ] **Structural guard (`mobile/tests/check-*.js`): n/a.** No file under `mobile/`, `web/` or `extension/` changes. The one client-visible effect (the "+ X added to balance the deal" line on gap-sweetened cards) is produced by the **existing** renderer reading the **existing** `sweetener` key (`mobile/src/api/trades.ts:86-95`, `mobile/src/components/TradeCard.tsx:235-240`, `:734`/`:766`; `web/js/app.js:3655-3665`) — verified by `git grep gap_sweetener mobile/src web` returning 0 hits, i.e. clients never read the gap dict and need nothing new. A structural suite would have nothing to pin. `mobile/scripts/testid-lint.sh` stays in CI and passes trivially (no testIDs added/renamed).
- [x] **Unit tests:** new `backend/tests/test_gap_sweetener_frac.py` — PRD §6.1, **T-1…T-9 + T-4a-ov + T-11/T-12** (helper trigger/close at frac 0.10 and 0 on the X1 = 1550 fixture with three validity pre-asserts; never-loosens with the `(1539, 2000]` residual; default-kwarg byte-identity with literal expected results; per-arm on/off × 4 arms incl. the arm-C outcome assertion; the consensus epsilon-window overshoot served bare; master switch beats frac (S-5′); untouchable never balances and the deck never empties; sibling beats bare on v3 + v2 divergence with a second closable card after the bare; payload precedence; seed/default parity; **tier-2 fallback narrows to the D-143 line when nothing reaches `eff`; tier 1 beats tier 2 regardless of walk order**) — **21 test functions / 26 node ids, 14 named sabotages** each proven RED before the assertion is accepted. **T-10** regression: full `pytest backend/tests` green — run at the new default **before** writing the new tests — with `test_gap_sweetener.py` (its four legacy asserts kept green by tier 2, not by editing), `test_engine_quality.py`, `test_knockout_refine.py`, `test_shape_knob.py`, `test_bakeoff_challenger.py` **unedited**; `test_bakeoff_arm_a_golden.py` edited only by the `_PINNED_KNOBS` token; and **one declared re-spec** — `test_gap_sweetener_arm_c.py::test_arm_c_kill_value_is_a_byte_identical_no_op:239` pins `sweetener_gap_frac = 0` on its `10 ** 9` leg with a dated D-173 (unshipped parallel build; see D-175) comment (the "huge threshold ≡ off" invariant is retired; the `≤ 0` legs stand). A red in `test_bakeoff_challenger.py` or `_v2_cards(max_per_opponent=3)` is a spec signal to report, not a test to edit.
- [x] **Code-walk proof:** `code-walk.md` in this folder, targets (a)–(e) in PRD §6.3 — all four callers reach `close_value_gap` with the same `eff`; arm-A guard order; per-arm collision branches (and why gen_v2 has none); `_dedup_and_sort` after sweetening; R-C serialisation precedence + the unchanged client path.
- [x] **Manual TestFlight checklist:** PRD §6.4, **5 steps** — pushed deck renders; a ~8–15 % 1-for-1 arrives balanced with the "added to balance" line; the added asset is not untouchable and ✕/✓/edit work; the `PUT /api/admin/config/sweetener_gap_frac` `0` → bare → `0.10` → balanced round-trip (the deploy-free lever, both directions, via the only route that reloads `_cfg` live); the `deck_impressions.features_json.gap_sweetener` read joined to the swipe. Runtime proof genuinely matters: the defect was a *judgement* about a served card, and only a served card can confirm the judgement now lands the other way. No mobile build is needed — the current TestFlight build against the deployed backend is the surface.
- [x] **deck_eval golden note** (beyond the template): `scripts/deck_eval.py` prod-boards replay at frac 0 vs 0.10 — over-line share, sweetened share, 1×1/2×1/3×1 shape mix, mean deck size, `gen_ms` p90 — recorded in TEST_LEDGER (PRD §6.2). A readout for shape drift and latency (PRD §5), not a gate — with **one pre-registered tripwire:** a 3×1 share rise of more than **+5 pp absolute** at frac 0.10 vs 0 means the builder reports before merge and the operator decides (no auto-block).
- [ ] **WAIVED because:** nothing.
- `testID`s added/renamed: **none.**

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | **updated** | No route changes; **card shape** does: (1) `:299` `sweetener` comment amended — the key is now also populated for gap-sweetened cards (`{player_id, side}` — same two-key shape clients already validate); (2) a new `gap_sweetener { player_id, side, gap_before, gap_after }` line after `:300` — OPTIONAL, served since 2026-08-22, undocumented until now. Request bodies unchanged. |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | **n/a** | No convention shifts. A `model_config` knob seeded in both `_MODEL_CONFIG_DEFAULTS` and `_DEFAULT_CFG` and read via `_c` is the existing convention (every `sweetener_*` / `package_*` knob follows it); "serialised only when present" for optional card keys is the existing convention `trade_card_to_dict` already states at `:11810-11817`. |
| `docs/architecture.md` (module wiring / data flow changed) | **n/a** | No module added, removed or re-wired; the data path (generate job → per-arm generator → gap pass → mutation stack → impressions → snapshot) is unchanged. One pure helper is added inside `trade_optimizer.py` next to the function that uses it. |
| `living-memory/HLD.md` (architecture genuinely shifted: new module, client, major flow) | **n/a** | No new module, client, table, route or flow — plan §4 "HLD delta: none", recorded in `status.md`. |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | **n/a** | No new string, enum or colour. The copy string `+ {player name} added to balance the deal` (`:290`) is unchanged and simply reached on more cards; its trigger column ("card has a `sweetener`") stays literally true because R-C populates that key. `side ∈ give\|receive` is the existing enum. |
| `docs/glossary.md` (new domain term) | **n/a** | No new term. "gap sweetener", "equalizer", "balanced sibling" (C1 tie-break) all pre-exist in the 2026-08-18/21 docs; the "proportional trigger" is a knob description, not a domain concept. |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | **updated — required** | `living-memory/DECISIONS.md` gains **D-173 (unshipped parallel build; see D-175)** (PRD §9, planner's draft with the id filled in and a Consequences line: v3 pair −1 no backfill; consensus outcome-level invariant; arm C no collision rule; the 0.0952 tuning floor; the +5 pp 3×1 tripwire) amending D-143. **Placement:** directly **above** `## D-171` at `:1046` — the entry block is newest-first (D-171 `:1046`, D-170 `:1065`, D-169 `:1079` … D-153 `:1471`) — and its index row after `:522`. Next id verified 2026-09-02: max is D-171. |

**Additional doc rows this change owes, beyond the template's list:**

| Doc | Updated? | Section / reason |
|---|---|---|
| `docs/config-reference.md` | **updated — required** | New `sweetener_gap_frac` row **after `:996`** (default 0.10; `eff = min(threshold, frac × max(give, receive))`, trigger and close both use `eff`; `≤ 0` = absolute trigger only; inert while `sweetener_gap_threshold ≤ 0`; a third tightening-only lever outside the D-143 pair rule; live-changed via `PUT /api/admin/config/<key>`; DB-seeded; **tuning gotcha:** *values below 0.0952 turn `test_engine_quality.py::test_adding_a_pick_to_a_fair_package_does_not_raise_composite` red — retune that fixture first*). **And fix the stale sentence at `:996`** in the `sweetener_gap_threshold` row — *"Arm C (`trade_gen_v2`) and the fit arm do NOT run the pass in v1"* — arm C **does** run it (`backend/trade_gen_v2.py:740`; `docs/plans/package-benchmark-sweetener/scope.md:59` marks it DONE 2026-08-21); the fit arm still does not. |
| `docs/plans/three-model-bakeoff/scope-phase2.md` | **updated — required** | Knob-disposition table gains an **exclusion row** for `sweetener_gap_frac` after the `sweetener_gap_threshold` row (`:123`), on the `package_floor_cross` "inert companion" precedent (`:122`): inert while `sweetener_gap_threshold ≤ 0` (arm A's pin); every caller reads it only behind the `> 0` guard; pinning it would imply it matters to arm A. Required by `test_bakeoff_arm_a_golden.py:724-727` together with the `_PINNED_KNOBS` token. |
| `docs/data-dictionary.md` | **n/a** | No table or column changes. |
| `living-memory/CHANGELOG.md` | **updated at ship** | Dated H2 for the merge. |
| `living-memory/TEST_LEDGER.md` | **updated at ship** | `test_gap_sweetener_frac.py` pass count, the 10 named sabotages, the deck_eval readout (frac 0 vs 0.10), the code-walk and the 5-step checklist named as the runtime evidence, per D-056. |
| `living-memory/NEXT.md` | **updated at ship** | #414 closed; Appendix A (impression gap) and H2/H5 logged as candidates. |
| `docs/feedback/items/414-lopsided-one-for-one/status.md` | **updated at ship** | Status → shipped, with the sha. |

## 5. Ship gate declaration

- **CI green** on the pushed sha: `backend-tests` (`pytest backend/tests` — the new file plus the untouched-proof on the six named suites) + `mobile-typecheck` (`tsc --noEmit`, plus the `check-*.js` suites — expected green with **zero** mobile edits) + `maestro-testid-lint` (`mobile/scripts/testid-lint.sh`, trivially green).
- **Evidence recorded** in `living-memory/TEST_LEDGER.md`: the pytest counts (21 functions / 26 node ids in the new file; the suite total), the 14 sabotages proven RED, **the one declared re-spec** (`test_gap_sweetener_arm_c.py:239`, reason: "huge threshold ≡ off" retired by D-173 (unshipped parallel build; see D-175)) and the `_PINNED_KNOBS` token named explicitly, the deck_eval readout at frac 0 vs 0.10 **with the +5 pp 3×1 tripwire evaluated and its verdict stated**, and the code-walk + checklist named as the runtime evidence.
- **TestFlight verification:** a 5-step checklist **was** written (§3 / PRD §6.4), so the operator runs it against the deployed backend and logs the outcome in TEST_LEDGER — step 4 (the knob round-trip) is the deploy-free-lever proof and step 2 is the direct falsification of the #414 complaint.
- **Pre-push hook:** `FTF_SKIP_SIM_GATE=1` is the standing posture under D-056; the note records pytest + code-walk + checklist as the evidence run instead. Install the hooks once per clone: `git config core.hooksPath githooks`.
- **Express lane declared by the operator?** **No.** Full gates apply. Bright-line note: this change touches **no** schema, **no** feature-flag surface and **no** analytics event; it does touch the **API card shape** (an existing optional key populated in one more case, plus documenting an already-served key) — recorded here so that if express were ever declared on it, the API-contract bright line would be surfaced first.
