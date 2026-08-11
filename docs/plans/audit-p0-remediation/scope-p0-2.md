# Feature Scope — P0-2: a failed trade search must be distinguishable from never having searched

<!--
Copied from docs/templates/feature-scope.md per CLAUDE.md §Conventions "Feature gates".
Every section is answered or explicitly WAIVED with a reason.
Full design + verification: docs/plans/audit-p0-remediation/plan-p0-2.md
-->

**Date:** 2026-08-10
**Entry point:** mobile UX audit remediation — `docs/business/product/2026-08-09-mobile-ux-audit/07-build-handoff-prompt.md` §P0-2
**Builder:** planning agent, worktree `ftf-p0-remediation`, branch `p0-remediation-2026-08-10` (base `origin/main` @ `ab9368f`)
**Operator sign-off on waivers:** **pending** — five waivers below (analytics, schema, flags, env vars, three of seven doc rows), plus five open questions in the plan's final section. Express lane was **not** declared, so full gates apply.

---

## 1. Analytics scope

- [ ] **(a) New events specced:** — not taken.
- [ ] **(b) Existing events cover it:** — not taken as a claim of coverage; see the note below.
- [x] **(c) WAIVED — no analytics needed because:** this is a bug fix that adds a rendered
  state and a retry affordance to an existing user action. The retry re-enters the existing
  `handleFindTrades(source)` entry point, which already fires `track('find_trades_tapped', {source})`
  (`mobile/src/screens/TradesScreen.tsx:733`) — **no new event name, no new client `track()` call.**

  **Trap documented so the next reader doesn't trip it:** `backend/analytics_taxonomy.py:191`
  declares `"find_trades_tapped": frozenset()` — an *empty* prop allowlist — and
  `backend/analytics_ingest.py:385` strips any prop not listed. The existing
  `source: 'prefs_changed_strip'` prop is therefore **already being silently dropped in
  production**, and the new `source: 'deck_error_retry'` will be too. Passing it costs
  nothing and measures nothing.

  **Consequence the operator should weigh:** generation-failure rate is the exact number
  that would falsify this finding's load-bearing assumption ("errors occur at a non-trivial
  rate on Render's free tier"), and it is currently unmeasurable from the client. Making it
  measurable requires a tracking-plan PR adding `source` to `find_trades_tapped`'s allowlist
  **server-side first** (default-deny — this is the NULL-`platform` failure mode the handoff
  warns about). That is deferred-P0-7 work; **flagged, not built here.**

  → follow-through: `docs/data-dictionary.md` **n/a** (nothing stored); taxonomy doc **n/a**
  (nothing added).

## 2. Schema & flag scope

- **New/changed tables or columns:** **none.** No `backend/database.py` edit; no migration.
  The fix reads `job.error`, an existing in-memory field already returned by
  `_trade_job_public_view` (`backend/server.py:2707`) and already typed client-side
  (`mobile/src/shared/types.ts:293`). → `docs/data-dictionary.md` **n/a because** no
  persisted schema is touched.
- **New/changed feature flags:** **none.** → `config/features.json`, `backend/feature_flags.py`
  `FLAG_KEYS`, and `docs/config-reference.md` all **unchanged**.
  **WAIVER, explicit:** the `flag-gated-remediation-build` convention wants user-visible
  changes default-OFF. This change is waived from that because **its OFF state is the bug** —
  a flag defaulting to off would ship a build in which a failed search still looks identical
  to never having searched, i.e. the acceptance criterion would be unmet in the default
  configuration. Existing flags are *read* but not modified: `ux.toast_v2` (already `true`)
  governs the ≥5 s warn-toast hold. **Operator decision needed** — see open question 3 in
  the plan; if a flag is wanted for batch-level rollback, this section changes from
  "none" to one new key plus its three registration rows, and the change must be re-scoped.
- **New env vars / `model_config` keys:** **none.** → `docs/config-reference.md` **n/a**.
  **Ship-the-knob:** no deploy-free lever is added, and none is judged necessary — the
  change is a client-only render branch with no server behaviour, no data write, and no
  new network call. Rollback is the branch revert.

## 3. Test scope (mobile test platform)

- [x] **New flow:** `mobile/.maestro/flows/trades-generation-failure.yaml` — covers all
  three failure paths and their retries, six legs:
  1. Path B (job errors during polling) — `fail_next` on `/api/trades/status*` with
     **`status: 200`** and body `{"job_id":"ftf_injected","status":"error","error":"timeout","cards":[],"opponents_done":0,"opponents_total":0}`. Legal because
     `backend/test_support.py:12-15` permits any status including 2xx (only
     `/api/trades/propose` carves out `< 400`). **No new seam required.**
  2. retry from 1 → deck populates (`trades.card-top`).
  3. Path C (poll abandoned) — `fail_next` `/api/trades/status*`, `status: 500`, `count: 4`
     (= `MAX_POLL_FAILURES`, `TradesScreen.tsx:1260`); `timeout: 45000` to cover the
     800 ms→4000 ms backoff.
  4. retry from 3 → deck populates.
  5. Path A (POST fails) — `fail_next` `/api/trades/generate`, `status: 500`, real
     production body `{"error":"internal_error","message":"Unexpected server error."}`.
  6. retry from 5 → deck populates.

  Ordering is load-bearing: the poll legs run **before** any successful generation, because
  a cached fresh job (`backend/server.py:2728-2748`) can return `complete` straight from the
  POST and skip polling entirely. `INJECT_KIND: reset` is never used mid-flow — it clears
  in-memory sessions and signs the app out (`inject.js:22-25`).

- [x] **Extended flow:** `mobile/.maestro/capture/trades.yaml` — **mandatory, not optional.**
  Its error leg currently asserts the bug: after the injected 500 it waits for
  `trades.empty-text` to reappear (`:88-91`), which is precisely the never-searched card
  this fix removes. That flow **fails against the fix** unless updated in the same commit.
  Added steps: wait on `trades.deck-error` instead, tap `trades.deck-error.retry` to return
  to a clean state before the loading leg, and correct the leg's header comment
  (`:71-76`, "the failure surfaces as a Toast, which carries no testID today").

- **`testID`s added:** `trades.deck-error` (container `View`), `trades.deck-error.retry`
  (`Button`). Both follow the in-file `trades.deck-summary` / `trades.deck-summary.see-liked`
  precedent (`TradesScreen.tsx:4850`, `:4861`), are plain string literals, and need no
  `mobile/scripts/testid-lint-allow.txt` entry. Must pass `mobile/scripts/testid-lint.sh`
  (exit 0). Flow selectors are `id:`-only; `text:` appears solely to assert load-bearing
  error copy, permitted by `docs/plans/mobile-testing/lld.md:253`.
  **Not renamed:** `trades.empty-text` keeps its id and its copy — the new state sits
  *before* it in the ladder, it is not a replacement.

- **Capture delta:** `trades` — run `mobile/scripts/screen-capture.sh --screen trades`
  (`docs/runbook.md` § Screen library). `screens/mobile/trades/error.png` changes materially
  (red **SEARCH FAILED** card replaces the "HIT \"FIND A TRADE\" TO START" card), and every
  trades frame carrying a toast shifts because the toast's vertical offset moves off the
  mode bar. Optional, not required for acceptance: add `error--poll` / `error--job` capture
  ids so the library distinguishes the three failures.

- **Smoke-suite impact:** `flows/smoke/05-trades-render.yaml` and
  `flows/smoke/06-trades-deck.yaml` cross this surface. Neither asserts `trades.empty-text`
  after a failure, so both are expected to stay green — **verified at build time, not
  assumed.** The other nine flows do not touch the trades deck slot or the Toast offset.

- **Backend: pytest files added/updated: none.** **Waived because** no backend file changes.
  `backend/tests/` is run unchanged as a regression check
  (`python3 -m pytest backend/tests/ -q`). `backend/tests/test_test_support.py` already
  asserts the injection blueprint is dead outside `FTF_TEST_MODE=1`; the new flow uses only
  existing endpoints, so that guardrail is untouched.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **no** | n/a because no route is added, renamed, removed, or contract-changed. `job.error` already ships in the `/api/trades/status` + `/api/trades/generate` snapshot (`backend/server.py:2696-2707`). *Optional courtesy edit, flagged not required:* the `/api/trades/status` row (`:195`) never mentions the `error` field at all. |
| `living-memory/LLD.md` | **no** | n/a because no schema, route, or invariant *convention* shifts — one screen gains local state and one component gains an optional prop. |
| `docs/architecture.md` | **no** | n/a because no module wiring or data flow changes. No new module, no new call. |
| `living-memory/HLD.md` | **no** | n/a because no architectural shift — no new module, client, or major flow. |
| `docs/cross-client-invariants.md` | **no** | n/a because the copy and colour are mobile-only. `semantic.neg` (#EF4444) is an existing Chalkline token already used by five Rank screens; no shared constant, enum, or colour is introduced or changed. Web/extension are untouched. |
| `docs/glossary.md` | **no** | n/a because no new domain term — "deck", "job", "retry" are all existing vocabulary. |
| ADR or `DECISIONS.md` entry | **YES** | New **`D-026`** (last id `D-024`, `living-memory/DECISIONS.md:209`): *"A failed trade search renders a named, persistent deck state; `job.error` is mapped, never echoed."* Records the deliberate deviation from the handoff's "render the backend message" and why — `job.error` is `str(e)` of a server-side Python exception (`backend/server.py:5247`) or the literal `"timeout"` (`:2528`), not user-facing copy. Also records the one-funnel `deckFailure` state choice over a render-time read of `job.status`. |
| `living-memory/GOTCHAS.md` *(added row)* | **YES** | New **`G-029`** (last id `G-026`, `GOTCHAS.md:200`): *"First run + four failed polls = a `SkeletonTradeCard` that never resolves."* Found during re-verification, not in the audit: ladder row 4 (`TradesScreen.tsx:4819-4823`) excludes `job?.status === 'error'`, but the poll-abandon path sets `job` to `null`, so the guard misses and the first-run skeleton renders forever. Closed by this fix. |
| `docs/design/components.md` *(added row)* | **CHECK AT BUILD** | `Toast` gains a public optional prop (`topOffset?: number`, default `space.xxl` = today's value). If the doc specs Toast's prop surface, add the row; if it specs only the visual, n/a — the default keeps every existing call site byte-identical. |
| `living-memory/CHANGELOG.md` *(added row)* | **YES at ship** | Dated H2 with the rest of the P0 remediation batch. |
| `living-memory/TEST_LEDGER.md` *(added row)* | **YES at ship** | Sim-run evidence, per §5. |

### 4.1 Execution record — W3-DOCS, commit 14 (2026-08-11)

> Row-by-row closure of the table above, per the feature-gate contract. **IDs are `hld.md` §7 / §10.4's**, which supersede any `D-011` / `G-013` written above — root `CLAUDE.md`'s next-ID columns were stale when these scope blocks were authored (they have since been changed to "max existing + 1 — grep first", so the trap is closed at the source).

| Row | Status | Where it landed |
|---|---|---|
| `living-memory/DECISIONS.md` | **updated — D-027** (the table above says `D-026`; `hld.md` §7 assigns `D-026` to P0-1 and is the reconciliation of record) | Named persistent deck failure; `job.error` mapped never echoed; the one-funnel `deckFailure` choice over a render-time `job.status` read. |
| `living-memory/GOTCHAS.md` | **updated — G-029** | *First run + four failed polls = a skeleton card that never resolves*, with all three blocking facts. |
| `living-memory/NEXT.md` | **updated** | Item 0i — `source` missing from `find_trades_tapped`'s server-side allowlist. |
| `living-memory/CHANGELOG.md` | **updated** | Batch H2, P0-2 bullet. |
| `docs/design/components.md` | **n/a — confirmed by reading the file** | Its § Feedback & status specs Toast's *visual* treatment, not a React prop surface; `topOffset` defaults to today's `space.xxl`, so the specced visual is unchanged. This closes the HLD's "verify at build" row. |
| `mobile/src/components/CLAUDE.md` | **updated (beyond the table)** | `Toast` row notes the optional `topOffset`. |
| `docs/api-reference.md` | **n/a — confirmed** | No route added, renamed, removed or contract-changed. The optional `/api/trades/status` `error`-field courtesy clause was **not** written: it was flagged optional and is unrelated to this fix. |
| `living-memory/LLD.md` · `living-memory/HLD.md` · `docs/architecture.md` · `docs/cross-client-invariants.md` · `docs/glossary.md` · `living-memory/DEPENDENCIES.md` | **n/a — confirmed** | As stated above. |

**Not executed, and why:** `screens/CLAUDE.md` + `screens/manifest.json` re-capture rows are **deferred** — the renamed/new frames require a run of `mobile/scripts/screen-capture.sh` against the simulator, which `W3-QA` holds for the sim gate. Writing index entries for PNGs that do not exist would make the manifest lie. Tracked for the capture pass. `living-memory/TEST_LEDGER.md` is owned by `W3-QA` and is deliberately untouched here.

## 5. Ship gate declaration

- **Simulator-gate tier:** **Tier 1** — mobile screen / state change
  (`docs/runbook.md:94-99`). Required before merge to `main`:
  - full smoke suite (11 flows) on sim,
  - the feature's own flow `mobile/.maestro/flows/trades-generation-failure.yaml`,
  - the updated capture flow `mobile/.maestro/capture/trades.yaml`,
  - `mobile/scripts/screen-capture.sh --screen trades` (visuals changed on the trades screen).

  Tier 1 rather than Tier 2 because the deck slot's render ladder and the Toast's layout
  both change — this is UI, not logic-only.

- **Evidence:** append flows run / pass-fail / sim device / SHA to
  `living-memory/TEST_LEDGER.md`, and write `qa/sim-runs/last-sim-run.json`
  (`{"date":…,"sha":…,"tier":1,"flows":[…],"result":"pass"}`). Enforced locally by
  `githooks/pre-push` — install with `git config core.hooksPath githooks`.
  Also gating, per the handoff's definition of done: `python3 -m pytest backend/tests/ -q`
  and `cd mobile && npx tsc --noEmit` both green, plus `mobile/scripts/testid-lint.sh`
  exit 0.

- **Operator deviation from the matrix:** **none requested.** Express lane was **not**
  declared by the operator, so the full gates above apply. Per `CLAUDE.md` §Conventions,
  agents never self-select express. Note for completeness: this change does **not** cross
  the bright line (no schema, no API contract, no feature-flag surface, no analytics event),
  so it would be eligible for express *if the operator declared it* — but no such
  declaration exists, and the mandatory `trades.yaml` capture-flow update means skipping the
  Maestro delta would knowingly leave a red flow on `main`.
