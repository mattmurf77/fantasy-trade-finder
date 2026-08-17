# FB-328 — Reconciliation log

> Author's incorporation of the round-1 critique
> ([`review-round-1.md`](review-round-1.md)) plus two orchestrator-directed
> edits, 2026-08-16. All new claims verified against `origin/main` @
> `d3fe3ac`. Docs updated: `hld-delta.md`, `lld-delta.md`, `prd.md`,
> `scope.md`.

## Objection dispositions

| # | Severity | Disposition | Where |
|---|---|---|---|
| OBJ-1 (T-7's SAB-C mapping self-satisfying) | BLOCKING | **Adopted — SAB-F added** ("hardcode `OWNERSHIP_SOURCE_NONE`"); T-7's label half remapped to SAB-F. Full matrix re-audited under the rule "a sabotage may never produce the value its test expects"; **three further violations found and fixed** (see self-audit below), including the critic-predicted second one (T-9's MFL half). Audit paragraph now sits in prd §6.1 above the matrix. | prd §6.1 |
| OBJ-2 (partial coverage under a full label) | NON-BLOCKING, disposition required | **Adopted, strong form: vocabulary gains `"partial"`** — applied rows still apply, uncovered slots draft at slot order, own caption ("Some real pick ownership applied — other slots use draft order"). Chosen over the critic's minimum (documented-limitation bullet) per the coordinator's framing — a documented silent gap is a smaller #328; degrade-to-`"none"` was rejected as data-destroying. Covers both cases (round-≥2 contested/orphaned ESPN slots; mock `rounds` deeper than grid/board/store) **and** the MFL identity partial-drop, which previously labeled `"platform"`. Round-1 holes still drop the whole resolution to `"none"` (existing order rule); the asymmetry is stated and pinned (T-12(d)). Detection contracts: `expected <= covered` set test in `_mock_real_draft` (board paths; `_mock_real_draft` gains the route's clamped `rounds` param), per-round census in `_mock_owned_pick_overlay` (MFL). Verified enablers: Sleeper assigned path emits every `(round, slot)` (`draft_board_service.py:826-829`); `_ORDER_CAP=500` can't truncate a ≤8-round rookie mock (`:172`). Cost accepted and documented: `"partial"` drops the platform-vs-user provenance distinction (HD-8). New R-14, T-12, SAB-G/SAB-H, TestFlight step 7. | hld §3 + HD-8; lld §1.1/§1.2/§2.2/§2.3/§3.1/§4; prd R-6/8/9/11/14, §6.1, §6.3; scope §1/§4 |
| OBJ-3 (HD-2 parity sentence factually wrong) | NON-BLOCKING | **Adopted — rewritten.** Parity is with the ESPN **Draft Room**; `PickAssignmentScreen` renders the pick-assignments GET, which deliberately includes contested/orphaned slots (verified: `docs/api-reference.md:484`, "this is the screen where someone fixes them"), so screen and mock can diverge on exactly those slots — round-1 divergence → `"none"`, round-≥2 → `"partial"` (OBJ-2's fix turns the divergence from silent into disclosed). HD-2's design and its raw-JSON rejection stand. | hld HD-2 |
| OBJ-4 (SAB-D undefined on slot-less rows; T-3 seed-collision vacuity) | NON-BLOCKING | **Adopted.** SAB-D now concrete: `slot = int(str(r.get("original_roster_id") or "0").lstrip("0") or 0)` (franchise-fid ordinal). T-3 gains (i) a fixture **precondition assertion** that, for the pinned seed, each traded row's correct shuffled slot ≠ its SAB-D ordinal (a colliding seed can never record a false green), and (ii) a distinct-seeds-differ assertion (de-vacuous determinism). `original_roster_id` confirmed on the row shape (`server.py:9603`) and added to lld §2.3's key list. | prd §6.1 (SAB-D, T-3); lld §2.3 step 2 |
| OBJ-5 (settings_echo cite drift vs G2) | NON-BLOCKING (trivial) | **Adopted — harmonized to G2's `:1414`,** which is also the verified truth: `"settings_echo": {` opens at `mock_draft_service.py:1414`, the new echo line lands under `order_source` at `:1418`. No disagreement with G2's region split — accepted as authoritative and mirrored verbatim in prd §4. (Note: the critic's own ":1411" figure is the `undrafted` line — the objection's substance stands, its number didn't.) | lld §1.3; prd §4; scope waiver 4 |

## Orchestrator-directed edits (not objections)

1. **Build serialization stamped as decided** (was "orchestrator's call"):
   G3 builds and merges to the group branch first; G2 branches after G3's
   merge and rebases its regions on G3's edits — same terms as G2 PRD §3.
   → prd §4, scope waiver 4.
2. **Cite alignment — with one correction.** The addendum's ":1416" figure
   **fails verification**: `:1416` is the `teams` line; the dict opens at
   `:1414` (G2's own table already says ":1414 block"). Cites aligned to the
   verified `:1414` rather than the directed `:1416` — flagged here instead
   of writing a false anchor into the contract.

## Self-audit findings (OBJ-1's re-audit, beyond the critic's finding)

- **T-9 (MFL half)** expected `"platform"` under SAB-C (hardcodes
  `"platform"`) — the critic-predicted second instance. → SAB-F.
- **T-3's "SAB-A (reachability)" was wrong:** SAB-A re-adds the early return
  in `_mock_real_draft`, but the MFL overlay block lives in the **create
  route** and still runs under SAB-A — the sabotage never reached T-3's
  subject. SAB-D itself proves the block live; label half → SAB-F.
- **T-12(d)** expects `"none"`, which SAB-A **and** SAB-G both produce →
  new SAB-H (delete the round-1 completeness rule), which fails (d) hard;
  the matrix note names the two rejected sabotages explicitly.
- **T-8 hardened:** asserting `ownership_source is None` via `.get()` would
  self-satisfy under SAB-E (key absent). T-8 now asserts key **presence**
  and `null` value.

## Round-2 readiness

All five objections dispositioned (4 adopted as proposed or stronger, 1
adopted with a factual correction to the directed line number); both
orchestrator edits applied; no open disagreements with G2's boundary table.
Ready for critic round 2 / sign-off.
