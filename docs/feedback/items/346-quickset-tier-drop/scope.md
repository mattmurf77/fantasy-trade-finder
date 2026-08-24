# Feature Scope — Quick Set holds unselected players (#346/#381, supersedes #161)

**Date:** 2026-08-24
**Entry point:** feedback #381 + #346 (Group F, 2026-08-24 wave — [plan.md](plan.md))
**Builder:** Group F author agent (PRD: [prd.md](prd.md))
**Operator sign-off on waivers:** needed — two waivers below (§1c, §3 testIDs), plus the §2 no-flag call; surface before build

---

## 1. Analytics scope

- [ ] (a) New events specced: none.
- [x] **(b) Existing events cover it** — this change removes a silent mutation;
  the events that measure the flow already exist and are untouched:
  - `quickset_started` (client, `QuickSetTiersScreen.tsx:149`) — walk intent.
  - `quickset_step_advanced` (client, `QuickSetTiersScreen.tsx:327–335`,
    props `seeded_accepted`/`picked_n`/`via`) — per-rung saves; answers "are
    users passing players over?" (`picked_n` vs the seeded set), which is the
    behavioral question behind this fix. Its `seeded_accepted` math reads
    `gridPlayers` + `tierForElo` and is unaffected by removing the demote.
  - `tier_save` (server, `server.py:8861–8871`, props
    `position`/`changed_count`/`via`) — every save; `changed_count` counts
    assigned pids only (`total_assigned`), so its meaning is unchanged.
  - `quickset_completed` (server, FR-20, fires on `via == "quickset"`) —
    known pre-existing gap: mobile's unscoped saves send no `via`, so it
    never fires for mobile walks. Flagged separately (plan-group-f.md §7),
    **not** part of this change.
- [x] **(c) WAIVED — no new events because:** removing the demote deletes
  behavior no event ever recorded (demoted pids were never in
  `quickset_step_advanced` props, `tier_save.changed_count`, or the
  elo_history snapshot — `server.py:8812–8817`). There is nothing new to
  observe: a save's observable surface (one save event per rung) is
  unchanged. Adding a "legacy demoted_pids key seen" counter event was
  considered and rejected — it would instrument a field on its way out, and
  binary-version adoption is already answerable from `X-App-Version` request
  headers.

→ No taxonomy change, no `docs/data-dictionary.md` change.

## 2. Schema & flag scope

- **New/changed tables or columns:** none. `users.tier_overrides` keeps its
  shape; the change only stops one writer of the value 1100.0 into it. No
  migration, no data repair (PRD §3 — historical 1100-pins are
  indistinguishable from anchor no-value answers).
- **New/changed feature flags:** **none — deliberate no-flag call.** This
  change alters API behavior (a POST route stops honoring `demoted_pids`),
  which is bright-line territory; the justification (PRD §5): the removed
  behavior is the bug per the operator's explicit #381 ruling, a flag would
  keep the defect dormant-but-live, rollback is a git revert on an
  auto-deploying backend (fully true until the client half ships in a mobile
  release; after that, restoring demote would also need a client revert —
  caveat spelled out in PRD §5/D-160), and flag surface costs four synchronized
  touchpoints for a behavior nobody may re-enable. **Surface this call to the
  operator with the waivers**; if overruled, the seam is one `if` around the
  two pin loops.
- **New env vars / `model_config` keys:** none. Deploy-free rollback lever:
  not applicable (no knob); the rollback is revert-and-redeploy, and the
  mobile half is independently safe to ship late (an old binary against the
  new backend already gets HOLD).

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-quickset-hold.js` — pins:
  no `demoted` computation/payload member in `QuickSetTiersScreen.tsx` (A1);
  no `demotedPids` param / `demoted_pids` body key in `rankings.ts`'s
  `saveTiers`, with `cleared_pids` still present (A2); no `demoted` token in
  `TiersScreen.tsx` (A3). Matching `npm run test:quickset-hold`. Named red
  sabotages per assertion in PRD §6b. (CI note: the `mobile-typecheck` job
  glob-runs every `check-*.js` — `.github/workflows/ci.yml:47` — so this
  guard gates.)
- [x] **Unit tests:** `backend/tests/test_quickset_demote.py` rewritten to
  7 cases pinning HOLD + ignored-key + guard revert (PRD §6a, T-1…T-7, each
  with a named red sabotage and a held-tier **value** assertion);
  `test_override_pin_unpin.py` one parametrize entry updated;
  `test_rookie_scope.py::test_m2_08…` rewritten in place to the scoped hold
  contract. `test_pin_tier_bounded.py` must stay green **untouched** (R-5).
- [x] **Code-walk proof:** CW-1…CW-5 (PRD §6c), written into this folder at
  build time — the post-fix trace of payload → route → apply_tiers, plus the
  no-remaining-`_pin(…, DEMOTED_ELO)`-caller and elo_history non-interaction
  checks.
- [x] **Manual TestFlight checklist:** PRD §6d — 7 steps: the exact Nabers
  walk (steps 1–3), explicit FA-rung demote still works (4), revisit-deselect
  consensus restore (5), the #346 preseeded angle (6), manual cleanup of
  historical pins (7). Runtime proof matters here: the bug is a
  mid-walk-refetch visual, and this is mobile's only runtime evidence.
- [ ] WAIVED — not waived; all four rows above are filled.
- **`testID`s added/renamed:** none — no markup changes; the mobile diff is
  deletion of the demote computation/params + comment rewrites.
  `mobile/scripts/testid-lint.sh` unaffected (WAIVER of new testIDs: no new
  interactive elements exist to tag).

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **UPDATED** | `/api/tiers/save` row (line ~217). Replace the `demoted_pids` contract text with, exactly: *"`demoted_pids` (removed 2026-08-24, D-160 — superseded #161/FB-161): **accepted and silently ignored** for wire compatibility with installed binaries v1.10.0–v1.16.x, which still send it; it no longer pins anything and the response is byte-identical to a request without the key. A save touches only the assigned and cleared pids — passed-over players HOLD their tier. `cleared_pids` keeps its restore-the-consensus-suggested-tier meaning (the old demote-beats-clear precedence is gone: a legacy request carrying a pid in both keys now clears). An empty save (`total_assigned == 0` and no `cleared_pids`) 400s even if `demoted_pids` is present."* Additionally: the row's **opening body listing** `Body {position, tiers: {<tier_key>: [pids]}, cleared_pids, demoted_pids}` drops `demoted_pids` (i.e. becomes `…, cleared_pids}`) so the shape spec and the removal note can't contradict each other two sentences apart; and the scoped-save clause "(2) `cleared_pids` / `demoted_pids` are scoped…" is trimmed to `cleared_pids` only. |
| `living-memory/LLD.md` | **UPDATED** (small) | The tiers-save convention: note that `/api/tiers/save` body is `{position, tiers, cleared_pids, scope?, via?}` and that `demoted_pids` is an ignored legacy key (D-160). If LLD.md has no tiers-save section, add the one-liner under its route-conventions area — a route contract shrank, which is a convention shift under the gate's own definition. |
| `docs/architecture.md` | n/a | No module added/removed/re-wired; a parameter died inside an existing flow. |
| `living-memory/HLD.md` | n/a | No architecture shift — same modules, same data flow, one fewer field. |
| `docs/cross-client-invariants.md` | n/a | Verified (git grep 2026-08-24): the demote rule is not listed there; tier keys/bands are unchanged; `DEMOTED_ELO`'s value is unchanged and stays. |
| `docs/glossary.md` | n/a | No new term; "demote" leaves the vocabulary rather than entering it. |
| ADR or `DECISIONS.md` entry | **UPDATED** | `living-memory/DECISIONS.md` gains **D-160** (full text in PRD §4; next-id verified against max D-159). Plus the superseded-by note appended to `docs/feedback/items/161-quickset-demote/status.md` (PRD §4). No ADR — this is a product-behavior decision, not an architectural one. |

Also at ship (living-memory motion, per root CLAUDE.md): CHANGELOG.md dated
entry; TEST_LEDGER.md entry naming the pytest run, the sabotage-red proof
runs, and the checklist handed to the operator.

## 5. Ship gate declaration

- **CI green:** `backend-tests` (pytest incl. the rewritten
  `test_quickset_demote.py`) + `mobile-typecheck` (`tsc --noEmit` + all
  `check-*.js` incl. the new `check-quickset-hold.js`) +
  `maestro-testid-lint` — all on the pushed sha.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry: suite counts,
  the named sabotages proven red (T-1…T-7, A1…A3), code-walk CW-1…CW-5
  linked, TestFlight checklist issued.
- **TestFlight verification:** yes — PRD §6d checklist run by the operator
  after the next EAS build; outcome logged in TEST_LEDGER. The backend half
  may ship first (it alone fixes installed binaries); the checklist's steps
  1–6 are valid on any binary ≥ v1.10.0 once the backend is live, since the
  behavior under test is server-side — only the comment/payload hygiene
  waits on the mobile build.
- **Express lane declared by the operator?** No — full gates (batch plan
  records "No express declared"). Bright-line notice: this is an API-contract
  change, so express would have required an explicit confirming yes anyway.
