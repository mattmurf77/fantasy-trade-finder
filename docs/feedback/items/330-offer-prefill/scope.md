# Feature Scope — #330 Offer prefill + auto-run (G4)

**Date:** 2026-08-16 (round 2 — incorporates `review-round-1.md`; dispositions
in `reconciliation-log.md`)
**Entry point:** feedback #330 (2026-08-16 wave, group G4; batch plan
`../304-positional-need-filter/batch-plan.md`)
**Builder:** G4 Author agent (Phase-1/Author round); Phase-2 build agent TBD
**Operator sign-off on waivers:** required — §1's no-new-events call and §3's
D-056 posture are surfaced here for the operator before build

**Orchestrator note (review B-4):** G4 adds **one new backend test file**,
`backend/tests/test_offer_hard_lock_330.py`, to an otherwise client-only
group — the executable single-pin hard-lock assert that a written proof
cannot provide while G6 concurrently rewrites the enforcing functions in
`backend/trade_service.py`. It is a new file (no G6-owned file touched), and
a test file is not production backend code: the path stays **Polish**.

Base for every verification below: `origin/main` @ `0b2dcee` (the plan's
header says `d3fe3ac`, but its cites match `0b2dcee` — see prd.md
§"Base and verification notes"). Full requirements: [`prd.md`](prd.md).

---

## 1. Analytics scope

- [x] **(b) Existing events cover it** — no new event names, no new props, no
  taxonomy edit, no backend file touched. Verified evidence:

  | Event | Props used | Answers | Evidence |
  |---|---|---|---|
  | `find_trades_tapped` | `source: 'league_offer'`, `mode` | how many handoffs auto-run, and in which deck mode | props `{source, mode}` registered at `backend/analytics_taxonomy.py:523`; enforcement is prop-NAME-level (`CLIENT_EVENT_PROPS` frozensets of names), `source` carries no closed-enum contract, and free-form values ship today (`'deck_error_retry'`, `TradesScreen.tsx:5776`) — a new *value* of a registered prop is never dropped |
  | `league_candidate_pinned` | existing (`verb`, `position`, `rank`, `side`) | the conversion moment at the tap site — unchanged from #300 | registered per the #300 ship (`LeagueSummaryScreen.tsx:1135-1143`) |

  The plan's claim "no taxonomy edit needed" is **confirmed**. Funnel
  question "handoff → deck viewed" is answerable by pairing
  `find_trades_tapped{source:'league_offer'}` with the existing
  `trade_card_viewed` — no new instrumentation.

## 2. Schema & flag scope

- New/changed tables or columns: **none** (client-only; generate payload uses
  existing fields `pinned_give_players` / `pinned_receive_players` /
  `opponent_user_id`, `backend/server.py:9882-9908`) → data-dictionary n/a
- New/changed feature flags: **none.** Kill switch is the existing
  `league.player_trade_handoff` (`config/features.json:151`, ON; read at
  `LeagueSummaryScreen.tsx:600`) — OFF removes the Offer/Target rows, the
  only writer of the store handoff, and the consumption path is inert on a
  null handoff (prd R-8). Gating decision recorded here per plan §6.
- New env vars / `model_config` keys: **none.** Deploy-free rollback lever =
  the flag above.

## 3. Test scope (mobile test platform)

- [ ] ~~New flow~~ / [ ] ~~Extended flow~~ — **n/a per D-056**
  (`living-memory/DECISIONS.md:600`, 2026-08-15): Maestro/simulator retired
  entirely — no flow authoring, extension, or execution for any change.
  This is standing policy, not a per-feature waiver. Replacement evidence,
  per D-056 and prd §Test plan:
  - unit tests U-1..U-4 (`useFinderTargets` handoff lifecycle incl. `seq`;
    the R-10 epoch-guard helper — U-4 fails without the guard);
  - new structural suite `mobile/tests/check-offer-prefill-330.js`
    (assertions S-1..S-5, listed concretely in prd.md);
  - written code-walk proofs P-1..P-3 (hard-lock narrative companion,
    relaxed-pass survival, never-relax) into `status.md`;
  - operator TestFlight checklist (8 steps, prd.md — incl. the
    repeat-Offer, mid-search-Offer, and manual-re-run-honesty steps the
    round-1 checklist could not catch).
- `testID`s added/renamed: `trades.scoped-empty.back` (must pass
  `mobile/scripts/testid-lint.sh` — still in CI per D-056)
- **Capture delta:** n/a per D-056 — no simulator captures; the empty-state
  card's look is verified on TestFlight (checklist step 3)
- Smoke-suite impact: n/a per D-056 — the 11 smoke flows are historical
  artifacts, kept but never run
- Backend: pytest files added/updated: **new file
  `backend/tests/test_offer_hard_lock_330.py`** (BT-1, per review B-4):
  single-give-pin and single-receive-pin hard-lock asserts across the v2 +
  v3 generator paths, harness mirrored from
  `backend/tests/test_finder_targeting.py` (which verifiably lacks any
  single-pin assert — all `pinned_give_players` uses are `None` or
  two-pin). G6-owned files are not touched; this file is the executable
  tripwire G6's `trade_service.py` rewrite must keep green. P-1 remains as
  the narrative companion (prd R-5).

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added/renamed/removed and no contract change — the auto-run sends only fields `/api/trades/generate` already documents (`pinned_give_players`, `pinned_receive_players`, `opponent_user_id`); payload shape byte-identical to a manual scoped search |
| `living-memory/LLD.md` | **update at build** | one line: the finder preselection contract (store `useFinderTargets`, never route params) now also carries the opponent + one-shot auto-run intent (`handoff` field) |
| `docs/architecture.md` | n/a | no backend module wiring or data-flow change; client-only state plumbing between two existing screens |
| `living-memory/HLD.md` | n/a | no new module, client, or major flow — an existing handoff (#300) gains scope + auto-start |
| `docs/cross-client-invariants.md` | n/a | no shared constant/enum/color changes; `source:'league_offer'` is a client-emitted value of an already-registered prop, single client |
| `docs/glossary.md` | n/a | no new domain term — "handoff", "pin", "scoped opponent" all pre-exist (#300/#269) |
| ADR / `DECISIONS.md` | n/a | the two binding choices (hard lock; honest empty state, never relax) are operator decisions recorded in the batch plan §G4 and prd.md, not agent design choices; no non-obvious architectural choice introduced |

## 5. Ship gate declaration

- **Simulator-gate tier:** n/a per D-056 — the pre-ship simulator gate is
  retired; `FTF_SKIP_SIM_GATE=1` is the standing posture for the pre-push
  hook, and `docs/runbook.md` § Pre-ship simulator gate is banner-marked
  historical. This is standing policy (operator decision 2026-08-15), not a
  per-feature deviation.
- Evidence: TEST_LEDGER entry after the structural suite + unit + BT-1
  pytest runs; no `qa/sim-runs/last-sim-run.json` (retired with the gate).
  CI (including `testid-lint`) must be green.
- Operator deviation from the matrix: none beyond D-056 itself.
- **Ship-order constraint (batch plan):** G6's backend contract lands before
  G4's auto-run ships; the open G6 question (does pinned+scoped bypass the
  #304 eligibility filter — default **no bypass**) is carried by the
  orchestrator (prd §Dependencies).
