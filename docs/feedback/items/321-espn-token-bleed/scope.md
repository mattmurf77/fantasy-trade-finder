# Feature Scope — #321 ESPN token bleed (identity binding + mismatch surfacing)

**Date:** 2026-08-16
**Entry point:** feedback #321 (G5, 2026-08-16 wave — batch plan:
[`../304-positional-need-filter/batch-plan.md`](../304-positional-need-filter/batch-plan.md))
**Builder:** G5 author agent (this doc) → G5 build agents (Phase 2)
**Operator sign-off on waivers:** required before build — see waiver summary
at the bottom; the batch selection already placed G5 on **full gates** with
operator awareness that the fix grazes the API-contract bright line
(additive `reason` field + new 403 path + data migration; plan §6 flagged
it, batch plan confirms).

---

## 1. Analytics scope

- [x] **(a) New events specced:**

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `espn_connect_store_rejected` | `reason`: `"wrong_account"` \| `"bad_credentials"` \| `"unavailable"` (string enum); `source`: `"send_button"` \| `"link_sheet"` (mirrors existing `espn_connect_opened`); `saw_otp`: boolean (mirrors existing capture events) | `storePair` in `EspnConnectScreen` fails — i.e. the server refused or couldn't judge the captured pair. `reason` is derived from the response: 403 + `reason: wrong_account` → `wrong_account`; other 403 `espn_bad_credentials` → `bad_credentials`; anything else → `unavailable` | mobile (`EspnConnect` screen tag, via the existing `track` helper) |

  Rationale: today the connect flow tracks opened / captured / abandoned /
  otp_step but **no failure event at all** (verified at `d3fe3ac` —
  `EspnConnectScreen.tsx` `track(` call sites), so the wrong-account
  rejection this fix introduces would be analytically invisible. One
  additive client event closes that; it also gives the migration's
  re-sign-in wave a signal (a spike of `bad_credentials`/`wrong_account`
  after deploy is expected and now measurable).

  → follow-through: taxonomy doc updated (an-data-architect owns it);
  `docs/data-dictionary.md` **n/a** — event is not stored in a new
  table/column (rides the existing events ingestion).

## 2. Schema & flag scope

- New/changed tables or columns: **none**. One **data migration** over the
  existing `espn_credentials.verified_at` column (PRD R10, respec'd after
  review B1: null **every pre-release stamp** — no existing stamp predates
  identity binding, so none proves identity; cutoff literal finalized at
  ship from the observed deploy time, idempotent via NULL-fails-`<`, in
  `_migrate_db()`), reviewed as a migration entry →
  `docs/data-dictionary.md` gains a `verified_at` semantics addendum (the
  2026-08-16 invalidation event), not a schema row. **Blast radius for the
  operator:** the entire (small) ESPN-connected cohort re-signs-in exactly
  once, including post-08-12 sign-ins.
- New/changed feature flags: **none**. The change rides the existing
  `espn.link` / `espn.league_picker` gates; no new flag surface (plan §6:
  "no flag surface touched").
- New env vars / `model_config` keys: **none**.
- Deploy-free rollback lever: **none needed, by design** — the wire code is
  unchanged (`espn_bad_credentials`), so old clients degrade to today's
  generic rejected copy; the migration is one-way but its effect
  (`verified_at = NULL`) is exactly the pre-existing "legacy unproven row"
  state the GET honesty gate already handles, and recovery is one re-sign-in.
  Reverting the server commit restores prior verify behavior without data
  repair.

## 3. Test scope (mobile test platform)

- [ ] ~~New flow~~ / [ ] ~~Extended flow~~
- [x] **WAIVED because:** **D-056 (2026-08-15)** — Maestro/simulator retired
  entirely, for any change in any pipeline. Automated evidence = structural
  `check-*.js` suites + unit tests + written code-walk proofs; runtime proof
  = operator TestFlight checklist. This is the batch-wide QA regime
  (batch plan § Baseline), not an agent-selected shortcut.
- `testID`s added/renamed: one candidate — a distinct wrong-account banner
  element on `EspnConnectScreen` (e.g. `espn-connect.wrong-account`) so the
  structural check can assert the state; must pass
  `mobile/scripts/testid-lint.sh` (stays in CI per D-056). If the build
  reuses `espn-connect.store-error` with variant copy, no new testID —
  builder's call, structural check adapts.
- **Capture delta:** none — per D-056 no simulator captures are taken; the
  change is an error-banner state and a server contract.
- Smoke-suite impact: n/a — smoke flows are historical artifacts per D-056
  (kept, never run).
- Backend: pytest **added** — `tests/` gains the T1–T10 (+T2b/T8b/T8c) suite from PRD §7.1
  (verify membership assertions, link-path assertion, public-league stamp
  gap, migration, 403 shape), each with a named proven-to-fail sabotage.
  Structural checks per PRD §7.2.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated (build phase — required)** | `POST /api/espn/link` row: additive `reason: "wrong_account"` field on the 403, the three mismatch conditions (verify-time across all bound leagues, team-binding step any cookie provenance, `espn_import` re-sync), the additive `credential_stored`/`credential_reason` fields on import success, the R4 import-path stamp change (**delete the "Known residual (2026-08-12)" sentence** — this fix closes it), and a migration note on the `GET` row (all pre-release rows read `connected: false` until re-verified). Full contract of record is `prd.md` §5 |
| `living-memory/LLD.md` | n/a | Fast-track bug path — no convention shift; no lld-delta owed. The changed contract is carried in full by `prd.md` §5 (per the batch's fast-track rule) |
| `docs/architecture.md` | n/a | No module wiring or data-flow change — same routes, same modules, one helper extended |
| `living-memory/HLD.md` | n/a | No architecture shift |
| `docs/cross-client-invariants.md` | n/a | `espn_bad_credentials` and the new `reason` value are consumed by one client surface only (`mobile/src/api/espn.ts`); the doc contains no ESPN error-code section today (verified) — nothing multi-client to pin for the 403 contract. The **notification-type enum IS multi-client** (web allowlists types, `web/js/app.js:4895`) — which is exactly why R9 is pinned to **reuse** the existing `espn_reconnect` type (new copy/`meta` only, review N3): no enum value changes, so no invariants row. Revisit if web/extension ever consume the ESPN link API or a new type is minted |
| `docs/glossary.md` | n/a | No new domain term — "wrong account" is plain English; oracle/verify terms were added with the 2026-08-12 fixes |
| ADR or `DECISIONS.md` entry | **updated (ship time)** | New D-entry: identity binding is a separate assertion from session validity; the any-bound-league mismatch rule (B2); the inconclusive-accept (zero-false-reject) posture incl. the deliberate drop of plan §F1's ownerless fallback (N4); the full-eviction migration with the final `RELEASE_CUTOFF` literal and the `2fa1ff2`/`7dfcd16` timestamps (B1). Grep for max ID first |
| `docs/data-dictionary.md` *(row added — migration touches stored semantics)* | **updated (build phase)** | `espn_credentials.verified_at` addendum: the 2026-08-16 invalidation migration (**all pre-release stamps nulled** — no pre-identity-binding stamp is identity-trustworthy) and what a NULL now additionally implies |
| `docs/runbook.md` *(row added — support surface)* | **updated (ship time)** | One-time support note (plan §10 drafted it, blast radius corrected per B1): post-deploy, **every** ESPN-connected user (any vintage) is signed out of ESPN once and re-asked to sign in — expected, deliberate, resolved by one re-sign-in with the identity-bound flow. Include the wrong-account rejection copy so support can recognize the *other* new question ("it says my account doesn't own this team") |
| `living-memory/GOTCHAS.md` *(candidate, ship time)* | optional | Plan §10's candidate: "a `verified_at` stamp proves session validity, not identity — membership binding is a separate assertion" |

## 5. Ship gate declaration

- **Simulator-gate tier:** **n/a — superseded by D-056** (Maestro/simulator
  retired entirely; `FTF_SKIP_SIM_GATE=1` is the standing posture for the
  pre-push hook per the decision text). The runbook matrix predates D-056.
- Evidence: `living-memory/TEST_LEDGER.md` entry recording the pytest run
  (T1–T10 + T2b/T8b/T8c green, sabotages proven-to-fail), the structural-check run, and
  the operator TestFlight checklist outcome (PRD §7.3 — the two-account
  switch sequence is the runtime proof for this security-scoped fix). No
  `qa/sim-runs/` artifact per D-056.
- Operator deviation from the matrix (if any) and why: none beyond D-056
  itself, which is an operator decision of record (2026-08-15).

---

## Waiver summary for the operator (surface before build)

1. **Maestro delta waived** — D-056 (operator decision, 2026-08-15): no
   flows, no simulator; structural checks + pytest + your TestFlight
   checklist instead.
2. **Sim gate waived** — same D-056 basis; standing `FTF_SKIP_SIM_GATE=1`.
3. **LLD delta not written** — fast-track bug path; the full changed API
   contract lives in `prd.md` §5 and `docs/api-reference.md` is updated.
4. **Bright-line acknowledgement** — this change touches an API contract
   (additive 403 `reason` field + additive import-response fields) and runs
   a data migration. The batch selection already put G5 on full gates with
   this called out; no express lane is used anywhere in G5.
5. **Migration blast radius widened (round 1, B1)** — the migration now
   evicts **every** existing `verified_at` stamp, not just a pre-08-12
   window: the whole (small) ESPN cohort re-signs-in once, including you if
   you reconnected after 08-12. Rationale in `prd.md` R10; surfacing here
   because it changes what you'll observe at first launch (TestFlight
   checklist step 1).

Everything else is answered above (no waiver): analytics specced (§1), no
schema/flag/env change (§2), backend tests added (§3), docs rows answered
row-by-row (§4).
