# PRD — Receipts

**Date:** 2026-08-21 · **Siblings:** [PLAN.md](PLAN.md) · [HLD.md](HLD.md) · [LLD.md](LLD.md)

---

## Table of Contents
- [1. Summary](#1-summary)
- [2. Problem & context](#2-problem--context)
- [3. Goals & non-goals](#3-goals--non-goals)
- [4. The metric (product spec)](#4-the-metric-product-spec)
- [5. Decision register (the calls this PRD makes)](#5-decision-register-the-calls-this-prd-makes)
- [6. Requirements](#6-requirements)
- [7. Goodhart & reflexivity hard lines](#7-goodhart--reflexivity-hard-lines)
- [8. Rollout & measurement](#8-rollout--measurement)
- [9. Dependencies, risks, open questions](#9-dependencies-risks-open-questions)

---

## 1. Summary

Receipts shows users the graded track record of the app's own trade suggestions — both
sides of every suggested trade, marked to market consensus 2/4/8 weeks later, wins and
losses alike — and gives the operator per-trade-shape accuracy readouts. The prediction is
locked the moment a card is served (`deck_impressions`, frozen at serve); grading can never
move the goalposts. No competitor (KeepTradeCut, FantasyCalc) grades its own advice.

## 2. Problem & context

- **User pain / trust gap:** the engine asks users to act on suggestions but never shows
  whether past suggestions were any good. Decline reasons show users argue with the
  card's values (40% `value_giving` — accuracy PLAN Part 1); a track record is the only
  durable answer.
- **Program need:** the accuracy program is measurement-first; its per-arm measurement
  questions need exactly the grading substrate Receipts builds. `propose` has fired zero times ever — every current quality metric is a proxy;
  value-movement grading is a proxy with teeth.
- **Why now:** preregistration data exists since 2026-08-16 (telemetry-era
  `assets_json`); consensus snapshots since 2026-07-26; every week without grading is
  cohort lost. The pitch's "trades from July" is **not achievable** (no July asset data
  — PLAN NG-7); the honest v1 story starts mid-August.
- **Users:** v1 targets the current tester cohort (n≈5 users, ~6 leagues) and the
  operator; the design's min-n gates assume small leagues.

## 3. Goals & non-goals

**Goals (outcomes):**
1. A user can see, per league, how suggestions served to them tracked the market — with
   losses shown as prominently as wins (trust through honesty, not through bragging).
2. The operator can slice graded accuracy by taxonomy cell × arm × window with
   honest intervals (engine-iteration evidence).
3. The preregistration discipline is established product-wide: predictions locked at
   serve, grades append-only, corrections versioned and visible.

**Non-goals:** PLAN §2's NG-1…NG-8 table is normative for this PRD (feedback-into-scoring,
executed-trade claims, cross-user receipts, personal-board grading, extra surfaces, pick
modeling, pre-telemetry backfill, negmem).

## 4. The metric (product spec)

### 4.1 Definitions (normative; formulas in LLD §4)
- **Swap edge** = (receive-side consensus delta) − (give-side consensus delta), in
  consensus value units, both endpoints from `player_value_history` at the serve date and
  serve+window date. The give side is the built-in market control — drift common to both
  sides cancels in proportion to serve-time balance and shape symmetry; the exact
  statements and disclosed residuals are HLD D-1.
- **`edge_pct`** = edge ÷ serve-time package midpoint.
- **Win** = `edge > 0`; ties (`edge == 0`) count as non-wins and their count is
  disclosed; **win share** reported against an explicit 50% null ("a coin-flip swap
  breaks even").
- **Windows:** 14 / 28 / 56 days; 28d is the fixed headline window; all three always
  shipped in one payload.
- Picks: held constant (Δ=0), counted in coverage; pick-majority rows excluded
  (LLD §4.3). Busts: floor-imputed, never dropped (D-8).

### 4.2 What we claim it measures — and don't
Agreement with market consensus movement, nothing more. Copy says "graded against market
consensus", never "accuracy" or "graded against reality". Consensus (DynastyProcess) is
the yardstick; the yardstick has opinions (disclosed in methodology line).

### 4.3 Small-n presentation rules
n is always shown ("12 of 19") and always means the **post-dedup, coverage-passing
graded count** — the same rows every displayed stat is computed over (LLD §2.2, asserted
in tests); headline requires that n ≥ `receipts_min_n` (10); internal cells carry Wilson
95% intervals (center-shifted form, LLD §4.4); sub-min-n leagues get the maturity/ledger
state, never a number.

### 4.4 Banned phrasing (copy review checks against this list)
- Any acquire-side % without the give side beside it ("+14% on the acquire side" alone —
  the assignment's own example — is the canonical violation).
- Any aggregate without n.
- "Accuracy" for market-agreement; "right/wrong" for graded/ungraded.
- Best-call shown without worst-call.
- Any claim over a cherry-picked window or cohort.

## 5. Decision register (the calls this PRD makes)

| # | Decision | Call | Rationale |
|---|---|---|---|
| DR-1 | Grading windows | **14/28/56d, headline 28d, all always reported** | 14d = news-cycle read (noisy, labeled early); 28d = signal/wait balance; 56d = season arc (empty until ~Oct 11 given the 8/16 cohort start — the screen's maturity state covers it) |
| DR-2 | "Acquire side gained value" means | **Swap edge on consensus** (§4.1) — not standalone acquire %, not personal boards | Market drift cancels; personal Elo is endogenous + sparse (HL-2); consensus is the only yardstick with daily frozen history |
| DR-3 | Preregistration: the immutable prediction | **`deck_impressions` row fields:** `assets_json` (asset ids + direction — the prediction proper), `served_at`, `league_id`, `user_id`, `is_ghost`, `trade_hash`, and the frozen slice keys (`shape_bucket`, `archetype`, `basis`, `model_arm`, `policy_version`, `features_json` slice keys). **Never used for valuation:** `features_json.give_value/receive_value` (may be personal-basis, `server.py:4159`) | The prediction is *what to swap*, not *what it was worth in engine units*; valuation both ends from the independently-frozen snapshot table |
| DR-4 | Preregistration enforcement | Grader forbidden to: (1) import/replay engine code, (2) read any live value (seeds, `elo_to_value`, features values) **for valuation or edge arithmetic** — sole exemption: the grader's own frozen value-unit pick weights, coverage/pick-share only, versioned under `grader_version` (LLD §1, T-4), (3) reconstruct assets from `trade_hash`, (4) UPDATE/DELETE grades. Each rule has a named test (LLD §7 T-1/T-3/T-10); grades carry `grader_version` + `taxonomy_version`; corrections = version bump + visible footnote | "Can't move goalposts" must be mechanical, not aspirational |
| DR-5 | Cohort graded | Telemetry-era rows (`assets_json IS NOT NULL`), **served rows only (`is_ghost` NULL/0 — operator ruling 2026-08-21), all arms, likes-you included**; pre-telemetry permanently ungradeable (NG-7); read-time filters do the rest | Grade everything gradeable once; filter per surface |
| DR-6 | Ghost usage | **None — excluded entirely** (operator ruling 2026-08-21, post-sign-off amendment): `is_ghost=1` rows never enter the grading queue; historical rows untouched (append-only); user surfaces never included them, so no user-facing number changes | Operator is against ghost cards, full stop; the served-vs-ghost internal control analysis is deleted with the ruling |
| DR-7 | Whose receipts | **Viewer's own impressions only** in v1; league-wide aggregate = operator question Q-2 | Other managers' decks are private; small-league aggregates reverse-engineer |
| DR-8 | Platform scope | **Platform-agnostic** (pure DB feature; impressions + universal-pool ids carry it). De-facto Sleeper today; no platform check written | A check would need removing later; grading code has no platform surface |
| DR-9 | Analytics events | `receipts_opened` (client, **INTENT** — i.e. registered in `ALLOWED_CLIENT_EVENTS` and deliberately ABSENT from the `NON_INTENT_EVENTS` deny-list; deliberate feature engagement, cf. `find_trades_tapped`), props `league_id, status, n_graded_28d, headline_bucket(neg/flat/pos)` · `receipts_window_changed` (client, listed in `NON_INTENT_EVENTS` — navigation, cf. `tab_selected`, `analytics_queries.py:73`) · `receipts_grade_run` (server-fired, listed in `NON_INTENT_EVENTS`), props `graded, ungradeable, cap_hit, duration_ms, trigger`. Registrations + classifications land **in the same commit as the emitters** | House rule (NULL-platform incident); minimal surface |
| DR-10 | Feedback-into-scoring boundary | **Out of v1 entirely (NG-1).** Receipts' side of the boundary = the per-cell accuracy read (admin metrics keyed taxonomy cell × `taxonomy_version` × `policy_version` × window). A future PRD that consumes it must (a) hook only the ordering/presentation multiplier stack (PLAN §7.3 RESERVED seam), (b) answer HL-1's holdout objection, (c) clear the accuracy plan's change-control rule | The boundary is an artifact, not a vibe |
| DR-11 | Flags & sequencing | `receipts.grading` then `receipts.screen`, both default false; grading runs dark ≥2 weeks before any screen ship | A-1/A-2 sequencing; screen must launch with real maturity data |
| DR-12 | Regrades | `grader_version` bump + full regrade + retained history + on-screen footnote ("regraded under receipts-2: <reason>") | D-3; corrections without goalpost-moving accusations |

## 6. Requirements

**FR-1** Grading job per LLD §4 (queue, prefetch, pure grader, append-only writes, run
ledger), triggered by cron endpoint + daily-tick guard + backfill script.
**FR-2** `GET /api/league/<id>/receipts` per LLD §2.2 — viewer-scoped, ghost-free,
deduped, min-n-gated, all-windows payload.
**FR-3** `GET /api/admin/receipts/metrics` per LLD §2.3 — cells, intervals.
**FR-4** `ReceiptsScreen` (mobile): root-stack push; own `FeedbackFAB
activeScreen="Receipts"` (rule #188; global FAB covers tabs only, `RootNav.tsx:559`);
entry point: a "Track record" row in `TradeHomeUtilityRow`
(`mobile/src/components/TradeHomeUtilityRow.tsx`) on TradesHome — placement to be
confirmed at build against the `trades_home_inline` experiment state (it runs at 100%
strip on the tester allowlist) — hidden while `receipts.screen` dark.
**FR-5** Screen states — all designed, none an afterthought:
- **Maturity/ledger state (the launch hero):** "23 suggestions on record since Aug 16 —
  first full report ~Oct 11. Predictions are locked the moment we show them; we grade
  against market consensus and publish every result, wins and losses." Renders tracked
  count + per-window pending counts.
- **Mature state:** headline (28d win share + median edge_pct + n), three window chips
  (ready/insufficient/pending), row list (both sides, serve values, deltas per window,
  pick + imputation flags), best call + worst call (always both; selection = max/min `edge_pct` at the headline
  window among the displayed rows — symmetric by construction), methodology line.
- **Loading** skeleton; **error** + retry; **flag-off/404** → entry hidden (never an
  error dialog).
**FR-6** Chalkline compliance: ledger tone; no streaks/letter-grades/confetti; flare
accent reserved for the preregistration-lock explainer (informational); ice on tappables;
radius ≤8px; no emoji icons/gradients; gain/loss colors from design-system semantic
tokens, not new hexes (`docs/design/design-system.md`; position/tier hexes stay governed
by `docs/cross-client-invariants.md`).
**FR-7** Analytics per DR-9. **FR-8** Flags/knobs per LLD §1. **FR-9** Docs: api-reference
(3 routes), data-dictionary (2 tables), config-reference (2 flags + 5 knobs), glossary
("swap edge", "preregistration", "receipt"), cross-client-invariants n/a in v1 (no shared
enums rendered), DECISIONS.md entry for the append-only-grades pattern.

**NFRs:** grading run bounded by batch cap, off the request path (202+daemon); user route
one indexed query + small aggregates; no PII beyond existing ids; screen accessible
(dynamic type, no color-only meaning — deltas carry sign glyphs).

## 7. Goodhart & reflexivity hard lines

- **HL-1 (feedback holdout):** any future feedback-into-scoring must ship with a holdout
  (e.g. feedback applied to a fraction of leagues, graded against the untouched
  fraction). Optimizing consensus-movement agreement is a momentum objective, not a
  good-trade objective — the future PRD inherits this objection in writing.
- **HL-2 (no personal-board grading):** `elo_history` moves when users swipe — partly the
  echo of our own suggestion. Consensus-only for grading, permanently; personal boards at
  most a *display* lens later ("your board agreed at serve"), and not in v1.
- **HL-3 (reflexivity tripwire, documented not engineered):** at n≈5 users FTF cannot
  move DynastyProcess consensus. If app-driven trades ever become a nontrivial share of
  dynasty market signal, the yardstick is partially endogenous and this design must be
  revisited. Dated and owned here.
- **HL-4 (recalibration immunity):** the grader reads only `player_value_history`
  (denormalized at snapshot time, `database.py:1294-1296`) — engine repricings
  (D-084-class) cannot rewrite grades by construction.

## 8. Rollout & measurement

### 8.1 Launch plan
P0 prod counts → P1 `receipts.grading` on (invisible; backfill drains; ledger populates)
→ P2 operator checkpoint on real numbers (**framing, not filtering** — pre-committed,
PLAN A-2) → P3 screen ships dark → P4 TestFlight checklist + `receipts.screen` flip.
Graduation criteria: grading live ≥2 weeks · backfill drained · operator reviewed admin
metrics · checklist passed · min-n satisfied for at least the operator's league **or**
Q-1 ruled in favor of the ledger-state launch.

### 8.2 How we know it worked
- **Primary:** `receipts_opened` unique users/week and repeat-open rate (a track record
  is a comeback surface); qualitative tester feedback via FeedbackFAB on the screen.
- **Guardrails:** no support/feedback reports of debunkable numbers (any such report =
  A-2 review); screen error rate ~0; `receipts_grade_run` cadence daily; gradeable share
  not degrading (supply health).
- **Program-level:** the P2 per-cell accuracy readout delivered to the accuracy
  program, regardless of screen launch.

### 8.3 Manual TestFlight checklist (operator, the only runtime evidence — D-056)
1. Fresh league (no grades): entry point visible when flag on; maturity state shows
   tracked count + ETA; no numbers.
2. Operator league post-backfill: headline + n; three window chips; 56d shows
   pending/insufficient (not blank, not hidden).
3. Row detail: both sides with serve values and deltas; at least one negative-edge row
   rendered identically to positive rows; pick-containing row shows the picks-held-flat
   flag.
4. Best call and worst call both present.
5. Window chip tap fires no reload of a different cohort (same payload).
6. Ghost check: no row the operator never saw on a deck.
7. Flag `receipts.screen` off + reload → entry point gone, no crash.
8. FeedbackFAB present on Receipts; no double-FAB on the Trades tab.
9. Dark-mode + dynamic-type pass.

## 9. Dependencies, risks, open questions

Dependencies: value-snapshot supply (existing, fallback-driven); sibling reconciliation
(PLAN §7); EAS build cadence for P3. Risks: PLAN §6 (A-1…A-5, R-1…R-3). Open decisions
for the operator: PLAN §8 (Q-1…Q-6). The single biggest product risk is launching a
numbers screen before the numbers deserve it — the design's answer is the maturity/ledger
state and the A-2 pre-commitment, both of which exist precisely so the honest state IS
the launch state.
