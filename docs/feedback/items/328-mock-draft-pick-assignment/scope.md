# Feature Scope — FB-328 mock-draft real pick assignment (G3)

**Date:** 2026-08-16
**Entry point:** feedback #328 (group G3, 2026-08-16 wave — batch plan:
[`../304-positional-need-filter/batch-plan.md`](../304-positional-need-filter/batch-plan.md))
**Builder:** G3 Author agent (docs) → G3 build agent (Phase 2), base
`origin/main` @ `d3fe3ac`
**Operator sign-off on waivers:** **required before build** — see the waiver
summary at the bottom; none are agent-selected (each cites a standing
operator decision or is surfaced here for a decision).

---

## 1. Analytics scope

- [x] **(a) New events specced** — no new event; one **new property on an
  existing event**, specced against the taxonomy:

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `mock_started` (existing) | + `ownership_source` ∈ `platform` \| `user` \| `partial` \| `none` \| `null`, read off the server's **resolved** `settings_echo` (never the request), alongside the existing `platform, teams, rounds, type, order_source, mode` | unchanged — successful mock create, `DraftRoomScreen` create handler | mobile |

  → follow-through: `backend/analytics_taxonomy.py:855` prop frozenset gains
  `"ownership_source"`; `mobile/tests/check-mock-draft-modes.js:617-627`
  props pin extended; `docs/cross-client-invariants.md` vocabulary row (§4
  below). Not stored in any dedicated column (`user_events` JSON props), so
  no `docs/data-dictionary.md` analytics change.
- [ ] (b) —
- [ ] (c) —

  This answers the assignment's required question directly: every mock create
  reports which resolution source (real/platform, manual/user, fallback/none)
  produced it, so the fallback rate per platform is one query.

## 2. Schema & flag scope

- **New/changed tables or columns:** none. One new key
  (`"ownership_source"`) inside the existing `mock_drafts.settings` JSON blob
  (`backend/database.py:1851`) → `docs/data-dictionary.md:1179` key-list
  updated; no migration (read-time nullable echo covers old rows, no
  backfill).
- **New/changed feature flags:** none. Existing flags **consulted**:
  `draft.room` (Sleeper branch, unchanged), `picks.assign` (NEW consultation
  in the mock's ESPN branch — same gate the board route's ESPN branch uses,
  `backend/server.py:11763`), `draft.mock` (route gate, untouched).
  `draft.mfl` is deliberately NOT consulted: it gates the MFL *board*, not
  the normalized store this reads. No flag defaults change; no
  `docs/config-reference.md` change beyond noting `picks.assign`'s new
  consumer (one line).
- **New env vars / `model_config` keys:** none. **Ship-the-knob / rollback
  lever:** none deploy-free — rollback is a code revert (additive nullable
  wire field + additive JSON key strand nothing; prd §7). Surfaced for
  operator awareness rather than waived silently: a dedicated kill-flag was
  considered and rejected as flag-surface growth for a correctness fix whose
  failure mode (bad resolution) degrades to the labeled fallback by design.

## 3. Test scope (mobile test platform)

- [ ] New flow: —
- [ ] Extended flow: —
- [x] **WAIVED because: D-056 (2026-08-15, operator)** — Maestro/simulator
  retired entirely; no flow authoring or execution for any change. Evidence
  regime instead: pytest T-1…T-12 with named sabotages, structural suites
  S-1…S-3, and the operator TestFlight checklist (prd §6.3).
- `testID`s added: `mock-draft.ownership-caption`,
  `mock-draft.recap.ownership-caption` (both must pass
  `mobile/scripts/testid-lint.sh`; no renames, no removals).
- **Capture delta:** none — no simulator captures per D-056; the visual
  change (one caption line, two cards) is verified on TestFlight steps 1/2/6.
- **Smoke-suite impact:** n/a per D-056 — the 11 smoke flows are historical
  artifacts, kept but never run.
- **Backend pytest files added/updated:** `backend/tests/test_mock_draft.py`
  additions (or new `backend/tests/test_mock_pick_ownership.py` if size
  warrants) — T-1…T-12 per prd §6.1, each behavioral test proven-to-fail
  under its named sabotage (SAB-A…SAB-H; matrix self-satisfaction-audited
  per review OBJ-1).

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated (build phase)** | Mock-draft block (`:520-536`): `settings_echo` field list gains nullable `ownership_source`; the "Resolution inputs (W2d)" paragraph's "Sleeper only …" sentence rewritten to the three-platform resolution + labeled fallback; capability-probe paragraph gains "ownership_source deliberately absent" |
| `living-memory/LLD.md` | **updated (build phase)** | Convention note: create-time resolution owns ownership honesty — the resolver that drops an overlay degrades the label at the same site; engine stays I/O-free (plan §7 already schedules this) |
| `docs/architecture.md` | **updated (build phase)** | `:135` mock row — create-path wiring sentence now names the three sources (Sleeper board / ESPN assignment grid / MFL normalized store) and the `ownership_source` label; "the one place the mock touches a platform" qualified (ESPN/MFL paths are DB-only) |
| `living-memory/HLD.md` | **updated (build phase)** | Mirror of the architecture.md sentence (module wiring changed: `_mock_real_draft` gained a second board producer + a store reader). No new module/client, so a one-paragraph delta, not a redesign |
| `docs/cross-client-invariants.md` | **updated (build phase)** | New section beside "Mock-draft mode + typed-empty reason" (`:645`): `ownership_source` closed server vocabulary `platform`\|`user`\|`partial`\|`none` (constants `backend/mock_draft_service.py`), open + nullable client type `MockOwnershipSource` (`mobile/src/api/mockDraft.ts`), `null` = pre-change row = *unknown, never "none"*, `partial` = applied-but-incomplete (uncovered slots at slot order); plus the `mock_started` prop note |
| `docs/glossary.md` | **updated (build phase)** | One term: **ownership source** (provenance label for the mock's traded-pick overlay) — new domain term appearing in code, payload, and UI copy |
| ADR or `DECISIONS.md` entry | **updated (build phase)** | `living-memory/DECISIONS.md` entry (next D-id): per-platform create-time ownership resolution with labeled fallback; alternatives rejected (engine reads store; raw-JSON ESPN read; invented MFL order; backfilled labels) — condensed from hld-delta §4. No new ADR: no architecture shift, ADR-010 (assignment tool) already covers the ESPN data source |

## 5. Ship gate declaration

- **Simulator-gate tier:** n/a — **D-056** retired the simulator gate;
  `FTF_SKIP_SIM_GATE=1` is the standing posture for the pre-push hook.
  Replacement evidence: sabotage-proven pytest + structural suites green in
  CI + written code-walk proof for the create-route diff + operator
  TestFlight checklist (prd §6.3) before the operator's go/no-go.
- **Evidence:** `living-memory/TEST_LEDGER.md` entry citing D-056, the
  pytest/sabotage matrix results, and the structural-suite run; no
  `qa/sim-runs/last-sim-run.json` (retired with the gate).
- **Operator deviation from the matrix:** none beyond D-056 itself (a
  standing operator decision, not a per-item deviation).

---

## Waivers & operator-attention items (surfaced, not silent)

1. **Maestro delta + simulator gate + capture delta: waived per D-056** —
   standing operator decision, cited above; not agent-selected.
2. **No deploy-free rollback knob** (§2) — revert-only rollback on an
   additive contract; flagged for an explicit operator OK.
3. **Batch-plan platforms column amendment:** the batch plan lists G3 as
   "backend"; the operator's "labeled … in the UI" requirement adds a
   one-caption mobile delta + one analytics prop (`MockDraftScreen.tsx`,
   `mockDraft.ts`, `DraftRoomScreen.tsx`). Already flagged by the Planner
   (plan §4 note); orchestrator should amend the column to "backend +
   mobile-caption".
4. **G2/G3 overlap:** G2 (#322–#327) also edits `MockDraftScreen.tsx` and
   `mock_draft_service.py`. G3's exact reserved regions are named in prd §4
   (constants block, `build_settings`, `state_payload` echo at `:1414`,
   caption helper + two mounts), mirrored in G2's PRD §3 boundary table.
   **Serialization decided (orchestrator): G3 builds and merges to the group
   branch first; G2 branches after and rebases its regions on G3's edits.**
5. **Bright line:** API payload contract change ⇒ full gates; express is not
   available for this item (CLAUDE.md §Feature gates) — noted so no later
   session shortcuts it.
