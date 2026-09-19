# Knockout refine — R5 two-sided, R1 in the right currency, R2 quality-aware, 3-for-1 unlock

> **Status:** active. Branch `claude/knockout-refine-0823` from `origin/main` @ `c321958`.
> Verdict + evidence: [`docs/reviews/2026-08-22-knockout-rules-judged.html`](../../reviews/2026-08-22-knockout-rules-judged.html). Operator aligned on items 1–4 (2026-08-23) and clarified the shape-rule intent: it was meant to stop sending 2 same-position starters with none returning — a job **R2 actually owns** (signed per-position net, #341). That clarification is a design input here: R2 stays and gets quality-aware; the shape rule becomes a knob.

## 1. What ships in code vs what flips in prod

**Code (this branch), every piece with its own kill knob, all defaults byte-identical to today except where noted:**

| # | Change | Knob (default) | Default behavior |
|---|---|---|---|
| C1 | R5 need gate: any-asset check + dual-need rescue | `need_gate_dual_rescue` (**1.0 — LIT at merge**, operator-aligned; 0 = today, byte-identical) | rescue active |
| C2 | R1 overpay: gap measured in `package_value_v2` (the currency the card shows) | `overpay_adjusted` (**1.0 — LIT**; 0 = raw sums, byte-identical) | adjusted |
| C3 | R2 pos-net: starter-depth relief for over-cap moves | `pos_net_starter_relief` (**1.0 — LIT**; 0 = today) | relief active |
| C4 | Shape rule → knob | `v3_shape_max_delta` (**1.0 = today**, byte-identical) | unchanged until prod flip |

**Prod `model_config` flips (deploy-free, AFTER merge, applied together as the consolidation bundle — the rules nest, G-058):** `filler_min_frac` 0.25 → **0.15** (`asset_floor_abs` 450 **held**), `trade_elo_gap_max` 250 → **0**, `v3_shape_max_delta` 1 → **2**. `filler_min_frac` and `trade_elo_gap_max` have existing prod rows; `v3_shape_max_delta`'s row is seeded by the idempotent startup migration at the first post-merge deploy (B1 registered it in `_MODEL_CONFIG_DEFAULTS`), so the three flips are applied AFTER the deploy is live, together. Each is independently revertible via the admin config API.

## 2. The structural key — opponent context reaches the gates per member

`_presentment_ok(give_ids, recv_ids)` is a **job-level closure** built before the member loop (`trade_service.py:5430`) — it has no opponent context. But `opp_profile = analyze_roster_strengths(member.roster, …)` is computed at the top of the loop body, and all three `presentment_ok_fn = _presentment_ok` bindings (`:5491`, `:5527`, `:5553`) are **inside** the loop. So:

- Extend the closure to `_presentment_ok(give_ids, recv_ids, opp_ctx=None)`.
- Inside the loop, derive `opp_ctx` once per member from `opp_profile` + `member.roster`: per-position **startable counts** (the `analyze_roster_strengths` definition of startable — dynasty value ≥ its threshold; reuse its output, do not invent a new one) and needs.
- Bind per member: `_member_presentment = lambda g, r, _ctx=opp_ctx: _presentment_ok(g, r, _ctx)` and pass THAT at all three sites. `presentment_ok_fn(g, r)` callers in the pair generators are unchanged — the ctx rides the default.
- `opp_ctx=None` (any other caller) ⇒ every new branch is skipped ⇒ byte-identical.

## 3. The three gate changes, precisely

**C1 — `need_gate_ok` (`:2210`).** Two edits, both inside the existing function, both no-ops when the knob is 0 or ctx is None:
  (a) *Any-asset:* the hole/upgrade tests currently judge only the single highest-value received player; pass if **any** non-pick received asset clears them. (The Loveland case still dies: no received asset fills a hole or upgrades.)
  (b) *Dual-need rescue*, checked just before the contender kill: pass when the give side sends ≥ 1 non-pick asset at a position P where the USER is in `position_surplus` at P **and** the OPPONENT's startable count at P is below their starter need (from `opp_ctx`). Measured expectation (armb bucket A): one-sidedness 96.3 → 88.7; unique-kill scope 827 + 1,919.

**C2 — `overpay_ok` (`:2129`).** With `overpay_adjusted` ≥ 1: price each side via `package_value_v2(vals, v_max, n_other=…, other_values=…)` exactly as the consensus emit path does (mirror the call shape used near the consensus gate — grep `package_value_v2` call sites and copy the argument convention); gap and `gap/big ≥ max_overpay_frac` test unchanged, still `abs()` two-sided, `max_overpay_min_value` unchanged. Knob 0 ⇒ the current raw-sum body, byte-identical. NOTE the defence's consensus fleeces (2-for-1 at raw 0.50 fairness) get *worse* in adjusted space — verified direction; they still die.

**C3 — `pos_net_ok` (`:2151`).** Signature gains `opp_ctx=None` + a user-side startable map (derive the user's from the already-built `_user_pos_values` at closure-build time — count entries ≥ the same startable threshold). With the knob on and both ctxs present, an over-cap position P is allowed **only if**: the shedding side was **above** its starter need at P before the trade, AND both rosters remain **at/above** starter need at P after (count startable bodies moved, picks excluded as today, `_STARTER_NEED` incl. superflex QB2). Otherwise today's `abs(net) <= cap` kill. This implements the operator's "two starting RBs" intent better than the count rule: shipping RB4+RB5 passes, stripping RB1+RB2 below startable depth dies.

**C4 — `trade_optimizer.py` shape rule (~`:524`).** `SHAPE_D = int(_c("v3_shape_max_delta"))` read per call alongside `POOL_P`/`MIN_SIDE` — through `_c()`, NOT `_ts._cfg.get(...)`: the raw-dict read is blind to `_cfg_override`, which would silently no-op arm A's pin (proven by test_shape_knob sabotage 3). No import-time binding (D-098). Default 1 byte-identical; the 3×1/1×3 subsets already exist in the enumeration, so no other optimizer change.

## 4. Ownership (disjoint — no shared files)

| Agent | Owns |
|---|---|
| **B1 (Opus)** | `backend/trade_service.py` (C1+C2+C3, closure threading), `backend/database.py` (3 knob rows), `backend/tests/test_bakeoff_arm_a_golden.py` (`_PINNED_KNOBS` — all 4 knobs incl. C4's; disposition reasons per the corrected style: state WHERE each is read relative to arm overlays), `backend/tests/test_knockout_refine.py` |
| **B2 (Opus)** | `backend/trade_optimizer.py` (C4), `backend/tests/test_shape_knob.py`, `scripts/knockout_knob_sweep.py` (stretch — see §6), `docs/config-reference.md` (4 knob rows), `docs/plans/README.md` (one row) |
| **Lead** | this plan, `scope.md`, `scope-phase2.md` disposition rows, D-159, ledger entries, merge + prod flips |
| **Reviewer (Fable)** | read-only adversarial pass after B1+B2 |

## 5. Tests (sabotage-proven, byte-copy restore — NOT `git checkout --` on an uncommitted branch)

B1: (1) every knob at 0 / ctx None ⇒ each gate byte-identical on a fixture sweep (same accept/reject verdicts as a vendored copy of today's logic); (2) dual-need rescue passes the surplus-RB→RB-hole case and still kills the Loveland shape; (3) any-asset passes when the SECOND received asset fills the hole; (4) C2 at knob 1 kills a raw-even/adjusted-lopsided package and passes a raw-lopsided/adjusted-even one (construct both); (5) C3 allows RB4+RB5 out from an RB-rich roster and kills RB1+RB2-below-depth, both rosters checked; (6) per-member binding: two members with different needs get different verdicts for the same candidate. B2: (7) delta knob 1 rejects 3×1, at 2 admits it and still rejects 4×1; (8) module-object read (patching `trade_service._cfg` changes the verdict — the D-098 trap test).

## 6. Measurement + flip protocol (lead, after merge)

Preferred: `scripts/knockout_knob_sweep.py` (B2 stretch) — read-only replay of league `1312140920132497408` under {today, bundle, bundle-with-filler-0.10}, reporting cards, distinct ideas, viewer-favoured share, sub-450-body share, shape mix. Run with `DATABASE_URL` read-only; numbers to TEST_LEDGER; pick 0.15 vs 0.10. **B1 finding (2026-08-23): C2 in adjusted currency is algebraically an adjusted-fairness ≤ 0.75 kill, which taxes raw-even 3-for-1s — the exact shape C4 unlocks** (fit fixture: 12.1% raw → 35.9% adjusted gap). The sweep therefore runs the bundle BOTH ways on `overpay_adjusted` (1 and 0) and the flip picks the measured winner. **If the sweep cannot run, `overpay_adjusted` flips to 0 (raw, today's behavior) pending measurement** — conservative beats harsher-than-today on the unlocked shape. If the script proves too heavy for the rest, ship the defence-certified conservative bundle (0.15, floor held) without the sweep and say so in the ledger. Rollback ladder: each prod knob individually → each code knob to 0 (deploy-free) → revert.

## 7. Out of scope
The viewer-must-win gate (Q-030a — operator decision pending), `waiver_slot_cost` audit, diversity-key refinement, FLEX-aware feasibility, filler code changes (knob-only this round).
