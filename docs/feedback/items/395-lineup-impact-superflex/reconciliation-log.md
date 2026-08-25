# #395/#396 — Dual-agent reconciliation log

Date: 2026-08-24 · Docs under review: [plan.md](plan.md) → [prd.md](prd.md) + [scope.md](scope.md)

## Round 1 — Planner → Author deltas (recorded, accepted)

1. Test plan grew 5 → 7 pytest cases (route-level aligned-display test split out; existing-suite row explicit).
2. Rank chip fixed in scope as R-6 one-liner (`${pos}${rank}` → `${pos} #${rank}`, `CardImpactBlock.tsx:155`) with a `check-card-impact-order.js` pin — the plan had left it conditional on the operator's league answer; the author ships it unconditionally and lets the TestFlight pass disambiguate the report.
3. `docs/api-reference.md` row is "updated", not a semantics note only — the current row literally documents the 3-WR template (`api-reference.md:378`, "QB/2RB/3WR/TE/FLEX, + SUPER_FLEX for sf_tep"), so "n/a" was never available. Verified true on disk.
4. Second rank-chip renderer found (`InLeagueCalculator.tsx:1570-1572` `posRankLabel`) and dispositioned out of scope (tier-prefixed, reads as a stat).
5. `test_trade_evaluate.py:1034` expected-value update flagged as the one deliberate expected-value change (verified: it asserts `slots == list(srv._MOCK_DEFAULT_LINEUP)` inside `test_numeric_espn_id_never_fetches_sleeper_meta`).

## Round 2 — Critic hunt (all claims re-verified from disk @ ff153a0)

### BLOCKING

**B-1 — R-1 under-specifies iteration order; two conforming implementations produce different output.**
`prd.md` R-1 says "deterministic (fixed iteration order)" but never *fixes* the order: which side is scanned first, in what pair order, and whether the scan restarts after an applied swap. Termination is sound as specified (each applied swap strictly increases the match count, bounded by template length) — but the *result* is order-dependent. Concrete counterexample on a two-FLEX template (both slots mutually eligible): before `[A, B]`, after `[B, C]`. Scanning the before side first applies before-swap → before `[B, A]`, displayed change on **FLEX2** (`A → C`); scanning the after side first applies after-swap → after `[C, B]`, displayed change on **FLEX1** (`A → C`). Both are 1-changed-row optima; the labeled row differs. Fix (doc-level, one paragraph in R-1): pin e.g. "scan the *before* side first; visit index pairs `(i, j)`, `i < j`, ascending; apply the first strictly-improving eligibility-valid swap and restart that side's scan; a side is done when a full scan applies nothing; alternate sides until both pass clean." Any pinned order is fine — it must just be *in the contract*, and test 3's repeated-call determinism assert then has teeth across reimplementations, not just within one.

**B-2 — Test 4's named sabotage cannot turn it red (self-satisfying mapping).**
Fixture: trade the only QB (`prd.md` §4a row 4); sabotage "over-eager alignment that swaps a TE into the QB row → eligibility assert red". Hand-recompute: after the QB leaves, every non-QB slot fills identically on both sides; the **only** mismatched row is QB (`daniels → None`). Any swap on either side either breaks an existing match (net ≤ 0) or is the QB↔empty-slot swap, which nets exactly 0 (+1 at QB, −1 at the vacated slot) — never *strictly* improving. So an implementation that merely drops the eligibility check applies **nothing** in this fixture: the eligibility assert stays green, the row-set assert stays green. The TE-into-QB corruption is unreachable from any improvement-respecting implementation. Fix: respecify the sabotage as dropping **both** guards (strict-improvement AND eligibility) — then the net-0 QB↔TE(None) swap applies, before shows `QB: None / TE: daniels`, and the exact-row-set assert goes red; or reshape the fixture.

**B-3 — Test 3's eligibility sabotage is only provably red on a fixture the PRD doesn't pin.**
With plain duplicate `FLEX`/`SUPER_FLEX` slots (the shapes test 3 names), whenever an *invalid* improving swap exists, a *valid* improving alternative on the other side typically also exists (the shared player is eligible for both slots by construction of the fill); depending on scan order the sabotaged implementation applies the valid one first and the eligibility assert never fires — sabotage green. A fixture where the **only** improving swaps are invalid requires mixed flex types: template with `WRRB_FLEX` + `REC_FLEX`; before `{WRRB: wrP, REC: teQ}`, after `{WRRB: rbR, REC: wrP}`. Aligning `wrP` needs either `rbR → REC_FLEX` (invalid: RB ∉ WR/TE) or `teQ → WRRB_FLEX` (invalid: TE ∉ RB/WR). Correct implementation applies nothing (2 changed rows stand); eligibility-dropped implementation applies one and the validity assert reds. Fix: pin this fixture (or equivalent) by name in test 3's spec.

### NON-BLOCKING

**N-1 — Two-sided rule: satisfied, with one tightening.** Display-side: test 1 asserts the unaligned diff has 2 changed rows and the aligned diff exactly 1 — recomputed the Daniels fixture by hand (before `QB=daniels … FLEX=wr3, SF=maye`; after `QB=maye … SF=fannin`; the QB↔SF before-swap improves matches 6→7; final single row `SUPER_FLEX: daniels→fannin`) — correct, and identity-alignment sabotage is provably red. Totals-side: test 3 asserts equality only "to 1e-9". Alignment does no arithmetic, so assert exact `==` (byte-equal), not approx. Test 2's WR-cascade recompute also checks out (3 rows → 1 `FLEX` row via two before-side swaps, both valid).

**N-2 — Test 4 wording.** "Genuine multi-row cascade preserved" — the no-second-QB fixture yields a *single* changed row (`QB: daniels → —`) pre- and post-alignment. Rename ("forced change preserved / alignment is a no-op") or reshape the fixture; as written the title promises a shape the fixture can't produce.

**N-3 — Nothing pins `_MOCK_DEFAULT_LINEUP` after the :1034 update.** Once `test_trade_evaluate.py:1034` asserts `_PLATFORM_DEFAULT_LINEUP`, the only remaining references to the mock constant in tests are a comment (`test_trade_evaluate.py:888`); R-4's protection is a manual `git grep`. A sabotage swapping the mock constant (or pointing mock draft at the platform constant) is caught by nothing in CI. Cheap fix: test 6 additionally asserts `srv._MOCK_DEFAULT_LINEUP == ["QB","RB","RB","WR","WR","WR","TE","FLEX"]` (literal), pinning both constants' divergence.

**N-4 — R-6 guard: feasible and CI-live, but anchor the regex.** `mobile/tests/check-card-impact-order.js` exists and already reads `CardImpactBlock.tsx` (verified), and CI runs every `tests/check-*.js` (`.github/workflows/ci.yml:47`) — note the root `CLAUDE.md` claim that these suites "gate nothing yet" is stale; separate hygiene fix, not this diff. The pin must anchor to the rank literal itself (e.g. match `position ?? ''} #${beforeRank}` and the `afterRank` twin), not a bare `/#\$\{/` over the file — a bare match is satisfiable by any future unrelated `#${` and fails the non-vacuity bar.

**N-5 — R-6 judgment: endorsed over dropping the chip on flex rows.** "WR #3" next to a `FLEX` slot label reads as a rank, which is the truth; dropping the chip on flex rows loses #169's designed rank-movement info exactly where flex churn makes it useful, and forks card behavior from the calculator's tier-chip convention. Two cosmetic residuals, both acceptable: the chip widens by ~4 chars inside a `numberOfLines={1}` row (truncation on narrow devices trims the after-half first — worth one look in the TestFlight pass), and the position prefix repeats on both halves ("WR #3 → WR #12") — consistent with the chip's before/after read.

**N-6 — TestFlight checklist: concrete and executable, one qualifier missing.** Pre-fix, step 1 fails on the two-row cascade (expects exactly one row; pre-fix shows two) and step 5 fails on `WR3` — both items would concretely fail their steps ✓. ESPN/MFL step executable: the operator has both platforms linked, and the outcome-interpretation paragraph handles the league-type ambiguity ✓. Gap: step 1's "exactly one row" holds only for a Daniels-for-picks package — an incoming *starter* legitimately adds rows. Qualify the step ("build Daniels → picks in the calculator"), which the step's calculator alternative already permits.

**N-7 — Fix B format detection: verified complete.** `leagues.default_scoring` is exactly `'1qb_ppr' | 'sf_tep'` (`backend/database.py:257`; NULL reads as 1qb) — no 2QB-but-not-TEP value exists in the enum, so `== 'sf_tep'` is the whole superflex universe for platform leagues. MFL import derives it from `_max_qb_starters ≥ 2` (`backend/mfl_service.py:735-781`).

**N-8 — Blast radius: verified.** `git grep starter_impact -- web extension` → zero hits (re-run 2026-08-24). Team Review renders only the weakest-slot *name* (`backend/server.py:24617-24630`), no before/after rows — alignment can't touch it; Fix B's template shift for platform leagues is named in prd §3. Power-rankings starters stays on `_sleeper_lineup_slots` (`server.py:24307`, deliberate #311 deferral). `trade.position_impact` ON confirmed (`config/features.json:219`). Scope's analytics waiver is sound: presence semantics of `starter_impact` unchanged, so `lineup_impact_unavailable` is unaffected; DECISIONS.md entry specced; api-reference "updated" claim verified against `api-reference.md:378`.

### Round-2 verdict

**NOT-READY** — B-1 (pin `align_starter_slots` scan order in R-1), B-2 (test 4's sabotage provably red — drop both guards, or reshape), B-3 (pin a mixed-flex fixture where only invalid swaps improve). All three are doc-level edits to prd.md §2/§4a; no design change requested. Non-blocking items N-1…N-6 are cheap tightenings the author should fold in while there.

## Round 3 — Author resolutions (all Round-2 items closed)

### Blocking

**B-1 — RESOLVED.** R-1 now pins the scan order as contract: **before side first**; within a side visit index pairs `(i, j)`, `i < j`, ascending lexicographic; apply the first strictly-improving eligibility-valid swap and **restart that side's scan from `(0, 1)`**; a side is done when a full scan applies nothing; alternate sides until both pass clean. The critic's 2-FLEX counterexample is resolved in the contract text itself: before `[A, B]` / after `[B, C]` → the before-side swap applies, the change displays on `FLEX2` (`A → C`), never `FLEX1`. Before-first chosen deliberately (the after lineup stays the engine's canonical post-trade fill; the before display is re-arranged toward it), and R-1 states that two conforming implementations must produce byte-identical output. §5's R-1 row notes the pinned order is what makes test 1's changed-row *label* assertable across implementations.

**B-2 — RESOLVED (both remedies applied: guards AND fixture).** Test 4 renamed `test_align_forced_change_is_noop` (also closing N-2's title/shape mismatch). Fixture reshaped: trade the ONLY QB on a template with a second TE slot the roster cannot fill (before `TE2 = None`), so an improving-adjacent invalid swap exists: the net-0 `QB ↔ TE2` (+1 at QB, −1 at the vacated TE2). Sabotage respecified per the critique: drop **both** guards — relax strict-improvement to net-≥0 AND drop eligibility (single pass). **Hand-verified red:** sabotaged run applies `QB ↔ TE2` → before renders `QB: —, TE2: daniels`; QB row becomes None-vs-None (match), TE2 becomes daniels-vs-None (mismatch) → changed-row set flips `{QB}` → `{TE2}`, exact-row-set assert red; daniels (QB) sits in a TE row, eligibility assert red. Also hand-verified that the OLD sabotage (eligibility alone) is indeed a no-op on this fixture — no strictly-improving swap exists — which is recorded in the test row so a future editor doesn't regress it.

**B-3 — RESOLVED.** The critic's mixed-flex fixture is written into test 3's spec verbatim and marked mandatory: template containing `WRRB_FLEX` + `REC_FLEX`; before `{WRRB_FLEX: wrP, REC_FLEX: teQ}`, after `{WRRB_FLEX: rbR, REC_FLEX: wrP}`. The ONLY match-improving swaps are eligibility-invalid (before-side `teQ → WRRB_FLEX`, TE ∉ {RB,WR}; after-side `rbR → REC_FLEX`, RB ∉ {WR,TE}); a correct implementation applies nothing (both changed rows stand). **Hand-verified red:** with the eligibility check dropped, the before-side scan reaches the `wrP ↔ teQ` pair, the swap strictly improves (REC_FLEX row becomes wrP-vs-wrP, +1) and applies → teQ occupies `WRRB_FLEX` → validity assert red; no valid alternative swap exists anywhere to mask it.

### Non-blocking (all applied)

- **N-1:** test 3 asserts totals with exact `==` (byte-equal — alignment does no arithmetic), not 1e-9.
- **N-2:** closed by B-2's rename/reshape (`test_align_forced_change_is_noop`; single forced change, alignment is a no-op).
- **N-3:** test 6 additionally asserts the literal `srv._MOCK_DEFAULT_LINEUP == ["QB","RB","RB","WR","WR","WR","TE","FLEX"]`, pinning the two constants' divergence in CI; its sabotage row extended accordingly. §5 R-4 row updated.
- **N-4:** R-6 guard anchored to the rank literal itself (`position ?? ''} #${beforeRank}` + `afterRank` twin), bare `/#\$\{/` explicitly forbidden as vacuous; mirrored in §4a, §5, and scope.md §3. (The stale root-CLAUDE.md "check suites gate nothing yet" claim is a separate hygiene item, not this diff.)
- **N-5:** R-6 `${pos} #${rank}` choice kept as endorsed; the truncation residual is already covered by TestFlight step 4's rank-chip look.
- **N-6:** TestFlight step 1 now specifies **Daniels away for picks only** (build Daniels → picks in the calculator if no such card fronts), with the reason stated inline (an incoming starter legitimately adds rows).

### Round-3 verdict

**READY** — all three blocking objections closed with the critic's own remedies (B-2 took both belt and suspenders: reshaped fixture AND double-guard sabotage); both reworked sabotages hand-verified to flip their assertions red; all six non-blocking tightenings folded in. prd.md + scope.md are build-ready.
