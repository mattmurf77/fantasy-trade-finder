# Reconciliation log — Group F (#346 + #381, Quick Set HOLD)

> Dual-agent record for [prd.md](prd.md) + [scope.md](scope.md). Round 1 = plan → author handoff; Round 2 = critic pass (2026-08-24). Batch plan (`plan.md`) and `plan-group-f.md` untouched per protocol.

## Round 1 — plan → author (2026-08-24)

Author received `plan-group-f.md` (repro verdict, `a8898a7`/#161 as origin, HOLD
contract, both-sides fix, D-056 evidence plan) and produced `prd.md` (R-1…R-9,
T-1…T-7, A1…A3, CW-1…CW-5, 7-step checklist, D-160 draft, no-flag
justification) and `scope.md` (analytics waiver, no-schema/no-flag, evidence
rows, docs table, ship gate). Author additions beyond the plan: T-7 (signature
guard), route-level rather than service-level T-1/T-3, the CI-drift note
(check-*.js DO gate), exact api-reference replacement wording, and the
old-binary "ignored-silently" disposition argued in R-3.

## Round 2 — critic pass (2026-08-24, this document)

Method: prd.md + scope.md re-read from disk; every file:line citation
re-verified on `ff153a0`; tier math recomputed from `backend/tier_config.json`;
test→sabotage map re-audited for self-satisfaction; DECISIONS.md ID re-counted.

### Verified clean (no objection)

- **D-160 is the next free ID** — `living-memory/DECISIONS.md` max is D-159
  (line 1482). D-160 spec has date, trigger, decision, back-compat, rollback,
  no-repair clauses.
- **Contract completeness** — R-1 (exact payload), R-3 (old-binary
  disposition), R-4 (cleared_pids incl. the legacy both-keys case), R-6 (where
  the held player appears, file:line to the sort + chip label). Two engineers
  implementing from R-1…R-8 converge; no ambiguity found beyond O-6 below.
- **Test→sabotage map is not self-satisfying** — every T-case asserts a held
  **value** (T-1 elo byte-unchanged + `tier_for_elo == firsts_4plus`; T-2
  override value + response key set; T-3 tier back to `first_1`; T-4 elo inside
  1150–1215; T-5 rookie value + vet override byte-unchanged). T-1/T-3/T-5/T-6
  re-derived as genuinely RED on today's `ff153a0` (current code pins 1100 /
  200s the demote-only body). T-4 is a survives-affordance pin (green-before,
  green-after) with a named sabotage — correctly labeled, not passed off as
  red-under-old. T-7 uniquely catches "param restored, loop omitted".
- **Worked example recomputed** — bands from `tier_config.json` (`firsts_4plus`
  1927–1972; n=3 spread 1972/1949.5/1927 all in-band; `waivers` 1150–1215;
  n=1 FA-rung pin at hi=1215 → `waivers` both sides; 1100 < 1150 → backend
  `tier_for_elo` None / client `tierForElo` `'waivers'`). PRD §1 chain and R-6
  hold. Checklist step 2 fails pre-fix (elo 1100 → bottom, FA) and passes
  post-fix (elo unchanged → top, "4+ 1STS").
- **Guard non-vacuity (the coordinator's exact question)** — "client still
  computes `demoted_pids`, backend ignores it" is **FAIL** per R-1, and A1/A2
  encode that: both go red on the client-side computation/body key regardless
  of backend state. A2's `cleared_pids`-still-present positive check prevents
  a trivially-empty-body pass. CI note verified: `.github/workflows/ci.yml`
  `mobile-typecheck` glob-runs `tests/check-*.js` (the `for f in` loop, line
  48) — the PRD's drift note against root CLAUDE.md ("gate nothing yet") is
  correct; CLAUDE.md is the stale side.
- **R-5 citations real** — `test_pin_tier_bounded.py:113/214/407` all read
  `RankingService.DEMOTED_ELO`; `ANCHOR_NO_VALUE_ELO = 1100.0` at
  `server.py:1313`. Analytics waiver's `X-App-Version` claim real
  (`server.py:2776`, `:8160`). `test_override_pin_unpin.py` parametrize entry
  confirmed (line 455). `test_rookie_scope.py::test_m2_09*` confirmed free of
  `demoted_pids` (line 329ff uses band-edge tier assignment only — "demotion"
  in its name is a different concept; leaving it untouched is right).
- **Blast radius** — threshold/completeness path (`server.py:8819–8858`) never
  reads `demoted_pids`; trends snapshot already excluded demotions
  (`8812–8817`); cross-format derive and KTC blend interact only with override
  *values*, which this change stops writing, never reshapes. Historical
  1100-pinned players are not stranded: they render in every rung's grid
  (bottom, FA chip), in TiersScreen's FA bucket (client `tierForElo` returns
  `waivers`, not None), and in the anchor wizard — checklist step 7 covers the
  manual rescue.
- **File-ownership disjointness** — grep of the four sibling Group folders
  (376/397/395/386) finds none of Group F's owned files.

### Objections

**O-1 (NON-BLOCKING) — D-160/§5 rollback claim overstates.** PRD §5(c) and the
D-160 text say rollback is "a git revert on a Render-autodeployed backend
(minutes, no client rebuild)". True for every binary ≤ v1.16.x (they still
compute and send `demoted_pids` forever, so a backend revert restores demote
fleet-wide today). False for binaries carrying the client half of this fix:
they never send the key, so a backend revert alone cannot restore the old
behavior for them — that needs a client revert + EAS build. One-sentence
amendment required in both PRD §5 and the D-160 text before it lands in
DECISIONS.md; the no-flag call itself survives (the rollback audience is nil
by the operator's own ruling, and the claim is fully true for the window
before the next mobile release).

**O-2 (NON-BLOCKING) — R-2 must reword, not remove, `ranking_service.py:553`.**
The cited comment is a bullet inside the D-085 tier-bounded-voting docstring
(lines ~549–557) stating that below-band pins (`DEMOTED_ELO`, anchor
no-value) stay FROZEN and must never be dragged back onto the board. That rule
remains true and load-bearing after this fix — anchor no-value still writes
1100-pins, and historical #161 pins persist un-repaired (PRD §3), so
tier-bounded voting must keep freezing them. Deleting the bullet per R-2's
literal wording would remove correct documentation of live behavior. Fix:
change R-2's instruction to "reword the #161 clause to past tense (historical
pins + anchor no-value), keep the frozen-populations rule".

**O-3 (NON-BLOCKING) — api-reference replacement wording is incomplete.**
scope.md §4 gives "exact" replacement text for the `demoted_pids` contract
sentence and the scoped clause, but the same row (`docs/api-reference.md:217`)
*opens* with `Body {position, tiers: …, cleared_pids, demoted_pids}` — left
as-is, the row would list the key as part of the body shape and then declare
it removed two sentences later. Add to the exact wording: the Body listing
drops `demoted_pids` (or annotates it "legacy, ignored").

**O-4 (NON-BLOCKING) — checklist step 5 is not differentiating in the
one-player case.** If the revisited rung holds exactly one placed player,
deselecting him makes `ids.length === 0` → the *old* code's clear-only branch
(`QuickSetTiersScreen.tsx:477–478`) also skipped demotion → step passes
pre-fix too. Sharpen the step: "on a rung where you placed **two or more**,
deselect one and keep the rest selected, then Save" — that path is
demote-beats-clear (→ FA) on old code and consensus-restore on new, matching
T-3 exactly.

**O-5 (NON-BLOCKING) — A1 lacks a positive anchor.** A1 is absence-only ("no
`demoted` token"); a renamed or gutted `QuickSetTiersScreen.tsx` would green
it vacuously. Cheap fix mirroring A2's pattern: also assert the file contains
the new mutate shape (`mutate({ ids, cleared })` or equivalent) and
`cleared_pids` still flows. (Practical risk is low — tsc and other suites
break on a rename — but the guard should stand alone.)

**O-6 (NON-BLOCKING) — stale comment escapes R-1's rewrite list.**
`QuickSetTiersScreen.tsx:770–775` (the #233 save-button label comment) ends
"…and #161 demotion only ever fires on a save with ≥1 pick — see onSave". Not
in R-1's enumerated comment blocks (64–79, 453–459, 461–474), and A1 won't
catch it ("demotion" ≠ `demoted` token). Left alone it points at deleted code.
Add the line range to R-1.

**O-7 (NON-BLOCKING, housekeeping) — root CLAUDE.md is stale on check-*.js
gating.** The PRD correctly documents the drift (ci.yml runs the suites); the
ship should also fix the stale "gate nothing yet" line in root CLAUDE.md (and
the NEXT.md open item, if still listed) so the next session doesn't
re-discover it. One line each.

### Round 2 verdict

**READY** — zero blocking objections. O-1…O-7 are text amendments (PRD §5 +
D-160 sentence, R-2 wording, scope §4 wording, checklist step 5, A1 positive
anchor, R-1 line range, CLAUDE.md line); none changes the contract, the test
matrix, the file-ownership set, or the no-flag call. Author may fold them in
without a further critic round; O-1 and O-2 must land before the ship commit
(they touch a permanent decision record and a live docstring).

## Round 3 — author resolutions (2026-08-24)

All seven amendments folded in; citations re-verified from disk before
editing (`ranking_service.py:549–560` frozen-populations bullet;
`QuickSetTiersScreen.tsx:766–775` — the #233 comment block starts at 766,
its #161 clause at 774–775, so R-1 cites 766–775 rather than the critic's
770–775).

| Obj | Resolution |
|---|---|
| O-1 | ACCEPTED — caveat added in both the D-160 spec (PRD §4) and §5(c): backend revert restores demote fleet-wide only while binaries ≤ v1.16.x are the fleet; post-client-fix binaries would need a client revert + EAS build. Consistency touch: scope.md §2's no-flag bullet, which repeated the unqualified claim, now carries the same caveat with a pointer to PRD §5/D-160. No-flag call unchanged. |
| O-2 | ACCEPTED — R-2 now instructs reword-not-remove for the D-085 docstring bullet (~549–557): frozen-populations rule kept verbatim in force; only the #161 clause moves to past tense (historical pins + anchor no-value). |
| O-3 | ACCEPTED — scope.md §4's exact api-reference wording now also drops `demoted_pids` from the row's opening `Body {…}` listing, so shape spec and removal note can't contradict. |
| O-4 | ACCEPTED — checklist step 5 sharpened to "a rung where you placed two or more, deselect one and keep the rest", with a parenthetical explaining why the one-player case is non-differentiating (clear-only branch never demoted) and the mapping to T-3. |
| O-5 | ACCEPTED — A1 gains a positive anchor (the two-member `mutate({ ids, cleared })` shape with `cleared` flowing into `saveTiers`) plus a red condition for its disappearance. |
| O-6 | ACCEPTED — R-1's rewrite list now includes the #233 save-button label comment's trailing #161 clause (766–775). |
| O-7 | ACCEPTED as a recorded handoff, not an edit — PRD §6b now carries a ship-time housekeeping line for the orchestrator naming the stale root CLAUDE.md "gate nothing yet" line and the matching NEXT.md item. Root CLAUDE.md is the operating contract; this group does not touch it. |

No disagreements. Verdict stands: **READY** — build may proceed from
prd.md R-1…R-9 + scope.md as amended; O-1/O-2 are in the documents ahead of
the ship commit as required.
