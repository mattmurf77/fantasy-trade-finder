# Feature Scope — #189 relaxed-pass disclosure on deck trade cards

**Date:** 2026-08-16
**Entry point:** direct ask (operator task: deck trade cards silently omit the #189 relaxed-pass disclosure)
**Builder:** Claude session, worktree `peaceful-keller-de2832`
**Operator sign-off on waivers:** surfaced in the ship summary (autonomous session; waivers listed below are all "no new surface" waivers)

---

## 1. Analytics scope

- [x] **(c) WAIVED — no analytics needed because:** the change is a non-interactive
  disclosure chip on an existing card. No new decision point, no new interaction.
  Card serve/disposition telemetry (F1 `deck_impressions` / `deck_outcomes`) already
  records the card's `trade_id`, and the backend knows which cards were relaxed, so
  "how do relaxed cards perform" is already answerable server-side without a client event.

## 2. Schema & flag scope

- New/changed tables or columns: **none**
- New/changed feature flags: **none** — mirrors the backend's #189 decision (no flag:
  the field only appears on otherwise-empty targeted jobs; absent field ⇒ chip absent,
  cards byte-identical)
- New env vars / `model_config` keys: **none**

## 3. Test scope (mobile test platform)

- Maestro: **retired** (D-057, 2026-08-15) — not authored, per convention.
- [x] **Structural check + unit test:** `mobile/tests/check-relaxed-disclosure.js`
  (npm run test:relaxed-disclosure) —
  1. `shared/types.ts` `TradeCard` carries `relaxed`/`relaxed_reason`;
  2. `normalizeTradeCard` passes both through, executed as a real unit test
     (transpiled with a stubbed `./client`): `relaxed: true` + reason survive
     normalization; malformed/absent values degrade to `undefined`;
  3. `TradeCard.tsx` renders `trade-card.relaxed-chip` exactly once, inside a
     `data.relaxed === true` guard, with the stretch wording;
  4. wording stays consistent with `AssetIdeasPanel.tsx`'s existing disclosure;
  5. `TradesScreen.tsx` declares no copy of the testID (G4 owns that file this wave —
     this change deliberately never touches it).
- `testID`s added: `trade-card.relaxed-chip` (passes `mobile/scripts/testid-lint.sh`)
- **Capture delta:** n/a — simulator captures retired (D-057). Code-walk proof: the chip
  is the wildcard chip's exact construction (`styles.wildcardChip`), already shipped and
  visually verified; only label text and guard differ.
- Smoke-suite impact: n/a (Maestro retired)
- Backend: pytest **none — no backend change** (field already shipped + tested in
  `backend/tests/test_relaxed_fallback.py`)
- Manual TestFlight checklist (runtime proof, next build): pin a player with an
  unrealistic ask (e.g. acquire a top-tier asset from a thin roster) so the targeted
  deck falls back to the relaxed pass → each card shows "STRETCH — OUTSIDE YOUR
  FAIRNESS BAND" above the header; ordinary decks show nothing new.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route/contract change — client now consumes fields already documented (§`relaxed`/`relaxed_reason`) |
| `living-memory/LLD.md` | n/a | no schema/route/invariant convention shifted |
| `docs/architecture.md` | n/a | no module wiring change |
| `living-memory/HLD.md` | n/a | no architecture shift |
| `docs/cross-client-invariants.md` | n/a | wording is mobile-only today (deck card + asset-ideas panel share it in-code; web renders no relaxed label yet) |
| `docs/glossary.md` | updated | "Relaxed card" entry now names the shipped mobile labels instead of a hypothetical |
| ADR / `DECISIONS.md` | n/a | no non-obvious choice — reuses the sanctioned wildcard-chip construction (ADR-005 flare = informational) |

Also updated: `mobile/src/components/CLAUDE.md` TradeCard row (component map).

## 5. Ship gate declaration

- **Simulator-gate tier:** retired (D-057/D-P1-08). Automated evidence = CI +
  `check-relaxed-disclosure.js` + testid-lint; runtime proof = TestFlight checklist above.
- Evidence: TEST_LEDGER entry written at ship
- Operator deviation from the matrix: none
