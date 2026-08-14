# Feature Scope — Deck-outcome impression-ownership validation

**Date:** 2026-08-14
**Entry point:** direct ask (dual-agent LLD review finding; standalone security/correctness subset of the trade-relevance-engine P0-3 spec, which is not yet in this tree)
**Builder:** Claude worktree session `charming-lalande-6dc6b6`
**Operator sign-off on waivers:** pending — waivers listed below; no user-visible behavior changes for legitimate clients

---

## What this is

`_save_deck_outcome_safe` (backend/server.py) accepted any ≤64-char client-supplied
`impression_id` and wrote a `deck_outcomes` row — and, under `deck.taste_vectors`,
mutated the taste vector of the **impression owner**. A stale or foreign
`impression_id` therefore let one session write outcomes into another user's
history and poison their personalization. Fix: the helper now takes a required
`acting_user_id` (route-resolved session user, never a body field) and writes only
when the impression **exists**, is **owned by the acting user**, and was **served
within 30 days** (`_DECK_OUTCOME_MAX_AGE_DAYS`). Anything else is
counted-and-dropped (always-200 convention preserved at all six call sites: swipe,
flag, /api/events side-channel, Sleeper/MFL/ESPN propose).

## 1. Analytics scope

- [x] **(c) WAIVED — no new events because:** this adds no client behavior. Rejects
  are observable via the new in-process `deck_outcome_rejects` counters
  (`no_user`/`unknown`/`foreign`/`stale`) on `GET /api/admin/analytics/health`,
  mirroring the existing ingest health-counter pattern (reset on deploy).

## 2. Schema & flag scope

- New/changed tables or columns: **none** (`load_deck_impression` additionally
  returns the existing `served_at` column — read-side only)
- New/changed feature flags: **none** (rides the existing `deck.signal_v2` /
  `deck.taste_vectors` gates)
- New env vars / `model_config` keys: **none** — recency bound is the code
  constant `_DECK_OUTCOME_MAX_AGE_DAYS = 30`

## 3. Test scope (mobile test platform)

- [x] **WAIVED because:** not mobile-visible. Legitimate clients send an
  `impression_id` from their own just-served deck, which passes validation
  unchanged; only forged/stale/foreign ids change outcome (silently, always-200).
- `testID`s added/renamed: none
- **Capture delta:** none — no visual change
- Smoke-suite impact: none crosses this seam behaviorally (responses unchanged)
- Backend: pytest updated — `backend/tests/test_deck_taste.py` (foreign/stale/
  unknown/no-user helper-level rejection + legitimate-path regression),
  `backend/tests/test_deck_signal_v2.py` (route-level foreign/stale rejection
  across swipe, flag and /api/events; existing outcome tests now seed real
  impressions). Full backend suite green: 2741 passed, 1 skipped.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | validation note on `/api/trades/swipe` (canonical), cross-refs on flag/propose/propose-mfl/propose-espn//api/events, `deck_outcome_rejects` on the analytics health row |
| `living-memory/LLD.md` | n/a | no schema/route/invariant *convention* shift — an internal helper contract tightened |
| `docs/architecture.md` | n/a | no module wiring or data-flow change |
| `living-memory/HLD.md` | n/a | no architecture shift |
| `docs/cross-client-invariants.md` | n/a | no shared constant/enum change; client contract (optional additive `impression_id`, always-200) unchanged |
| `docs/glossary.md` | n/a | no new domain term |
| ADR / `DECISIONS.md` | updated | DECISIONS.md — silent counted rejection over 4xx, and the 30-day bound |

## 5. Ship gate declaration

- **Simulator-gate tier:** 4 (backend-only; pytest/CI). Nominally arguable as
  tier 3 ("backend route consumed by mobile"), but no route contract or
  legitimate-client behavior changes — responses are byte-identical for real
  clients. Tier call recorded here for the operator to override pre-merge.
- Evidence: TEST_LEDGER entry (full backend suite, 2026-08-14)
- Operator deviation from the matrix: none
