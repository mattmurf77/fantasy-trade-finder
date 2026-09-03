# Feature Scope — FB-418 "Send this offer" dismisses the shop tile

<!-- Filled copy of docs/templates/feature-scope.md. Every section is answered
     or explicitly WAIVED with a reason — silence is not a waiver. The template's
     Maestro/simulator rows are dead under D-056 and are not reproduced. -->

**Date:** 2026-09-03
**Entry point:** feedback #418 (operator, filed 2026-09-02, app v1.16.14,
screen `ShopAsset`, severity bug — *"Hitting send this offer should dismiss
the card"*)
**Builder:** Phase 1 Author agent (planning docs only; build agent TBD)
**Operator sign-off on waivers:** not needed — no waivers. Two sections are
answered "none" / "n/a" with reasons, none is waived.
**Path:** fast-track bug (≤ 2 files; no schema, API, flag or analytics change).
Full gates still apply — the operator has not declared express.

**Tree verified against:** `origin/main` @ `c7e75666`.

---

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [x] **(b) Existing events cover it.** `calc_trade_queued` already fires for
  every ✓ on this surface, inside the shared helper
  (`mobile/src/utils/queueCalcTrade.ts:82-86`): `{queued: true}` on success
  (including the server's `already_queued`) and `{queued: false, reason}` on a
  refusal, with `screen: 'ShopAsset'` supplied by the body
  (`mobile/src/components/ShopOffersBody.tsx:709`; pinned by
  `check-shop-deck.js` h5d). The question it answers — *how often does a shop
  ✓ queue, and why does it refuse?* — is unchanged by this fix. The tile
  leaving the pager is a client-side consequence of that same event, not a
  new user intent, so no removal/dismiss event is added; `shop_dismiss_undone`
  is untouched because a like has no undo. The taxonomy
  (`backend/analytics_taxonomy.py`) and `NON_INTENT_EVENTS` are not edited.
- [ ] **(c) WAIVED:** n/a.

## 2. Schema & flag scope

- New/changed tables or columns: **none** — no `backend/` file is touched.
- New/changed feature flags: **none**. The surface stays behind the existing
  chain (`trade.shop_asset` ∧ `trade.asset_ideas` ∧ `calc.merged_layout`, guard
  n1a); the fix is inert wherever the entry is dark.
- New env vars / `model_config` keys: **none**. Rollback lever: revert the one
  commit (client-only; ships in the next EAS build). No deploy-free knob is
  warranted for a two-line state write.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-shop-deck.js` — **extended**
  with section `(k)`, eight assertions, each with a named sabotage
  ([`prd.md`](prd.md) §8.1): `handleLike` writes `setSuppressed` (k1), never
  `locallyRemoved` (k2), requests the pager index **before** the write (k3),
  writes only inside the `then` branch of a `queued` condition (k4), does not
  exclude `alreadyQueued` (k5), does not flush the pending dismiss (k6),
  releases `busyKey` in `finally` with the write post-`await` inside the
  `try` (k7), and the three amended comments carry `#418` (k8, a textual
  tripwire). Existing
  `npm run test:shop-deck` (`mobile/package.json:85`); CI runs every
  `tests/check-*.js` (`.github/workflows/ci.yml:47`). **Why extend, not add:**
  the eight assertions need the suite's AST helpers (`functionNamed`,
  `referencesIdentifier`, `nearestAncestor`) and sit beside the assertions
  they fence (i3, n2a–f, n3a–b); a new file would copy ~100 helper lines to
  hold them (prd D-3).
- [x] **Unit tests:** none — no backend change; nothing mechanically checkable
  beyond the guard above. (`tsc --noEmit` covers the type surface.)
- [x] **Code-walk proof:** required from QA against the built diff — the
  8-hop tap → queue → `suppressed` → `visibleByMode` → effect clamp → next
  tile trace specified in [`prd.md`](prd.md) §8.2, every hop file:line-cited.
- [x] **Manual TestFlight checklist:** [`prd.md`](prd.md) §8.3 — 10 steps
  (1–9 plus 2b) with expected results (send on tile 1 → `1 / N-1`; send on a
  middle tile → position held; last tile → empty state; already-queued
  inside the 60 s cache window; forced refusal via Airplane Mode; pending
  dismiss + like). Runtime proof genuinely matters here: the pager scroll is a FlatList
  side effect no static check can observe.
- [ ] **WAIVED because:** n/a — nothing is waived.
- `testID`s added/renamed: **none**. Existing IDs used by the checklist:
  `shop.like-btn`, `shop.dismiss-btn`, `shop.counter`, `shop.pager`,
  `shop.empty`, `shop.clear-positions`, `shop.widen-notice`. `testid-lint.sh`
  is unaffected.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **n/a because** no route is added, renamed, removed or contract-changed; `POST /api/trades/queue` is called exactly as today. |
| `living-memory/LLD.md` | **n/a because** no schema/route/invariant convention shifts; the fix applies the existing Fix A + P-1 conventions to one more path. |
| `docs/architecture.md` | **n/a because** no module wiring or data-flow change. |
| `living-memory/HLD.md` | **n/a because** same. |
| `docs/cross-client-invariants.md` | **n/a because** no shared constant, enum or color changes. |
| `docs/glossary.md` | **n/a because** no new domain term. |
| ADR or `DECISIONS.md` entry | **n/a because** the two choices (a like is a second *commit* gate into `suppressed`; a like does not flush the pending dismiss) follow directly from the shipped rulings R-A / P-1 / B-4 and are recorded in [`prd.md`](prd.md) §5 — nothing of D- weight is overturned. If the orchestrator wants the "second gate" recorded centrally, it is one line under the existing Fix A decision. |
| `docs/feedback/items/INDEX.md` | **updated** | Row 418 added (planned, 2026-09-03). |
| `living-memory/TEST_LEDGER.md` | **at ship** | Guard k1–k8 red-under-sabotage / green-after-revert pairs + checklist outcome (§5). |
| `living-memory/CHANGELOG.md` | **at ship** | Dated H2 by the shipping session. |

## 5. Ship gate declaration

- **CI green** on the pushed sha: `backend-tests` (unchanged, must still pass)
  · `mobile-typecheck` (`npx tsc --noEmit` **and** the `for f in
  tests/check-*.js` loop, `.github/workflows/ci.yml:47` — this is where the
  new `(k)` section gates) · `maestro-testid-lint`.
- **Ownership diff check:** `git diff --name-only origin/main` is exactly
  `mobile/src/components/ShopOffersBody.tsx`,
  `mobile/tests/check-shop-deck.js`, plus this folder and the INDEX row.
  None of `queueCalcTrade.ts`, `ShopAssetScreen.tsx`, `TradesScreen.tsx`,
  `backend/**`, `config/features.json`.
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry naming, for
  each of k1–k8, the sabotage applied, the red, and the green after revert —
  the pair is the evidence, not the pass count — plus the existing-assertion
  fence (e, i3, i5, i6, n2b–f, n3a–b) green on the fixed file.
- **TestFlight verification:** [`prd.md`](prd.md) §8.3 (10 steps), run by the
  operator on the first build carrying the fix; outcome logged in TEST_LEDGER.
- **Simulator gate:** none to declare (D-056). `FTF_SKIP_SIM_GATE=1` is the
  standing posture for `githooks/pre-push`; note the guard run in its place.
- **Express lane declared by the operator?** **No.** The report is a bug
  filing, not an express declaration; agents never self-select express. The
  change is off the bright line (no schema / API / flag / analytics), so an
  express declaration *would* be honorable if the operator makes one — until
  then, full gates.
