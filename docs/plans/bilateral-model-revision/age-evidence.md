# Future private age and request-input evidence

Implemented under [the parent age specification and capture amendment](spec-age-evidence.md). This is evidence collection and request consistency, **not an age-eligibility, ranking, pricing or acceptance-model change**. Existing imputed public age 25 still reaches the current model unchanged; using the new provenance requires a separate model specification and evaluation. Old immutable captures are not repaired from current player data.

## Implemented contract

`backend/trade_input_evidence.py` is pure and has no provider/database/filesystem dependency. Its `owner-age-evidence-1` envelope is private, explicitly `used_in_model=False`, and contains per-player validated age or Unknown, selected source, imputation state, available observation timestamp/basis and missingness reasons.

The optional build collector mirrors the existing source priority: truthy enriched DB age first, then the existing raw integer conversion, then default 25. Age/source-observation scalars are read once before Player construction and those same values feed the collector; it does not reread mutable source rows afterward. It does not alter `Player`, public serialization, prices, return values or existing direct callers. A genuine source age 25 is distinct from missing/defaulted age 25. Boolean, malformed, nonfinite, nonpositive and fractional selected ages do not become positive age evidence. A malformed raw conversion that already prevented a legacy pool build still does so; collection does not silently repair that behavior. Generic and injected picks are not human age evidence.

Only timezone-bearing `players.last_synced` is recorded as an available DB observation time. Raw-cache values have no invented receipt timestamp, and a discarded DB source's time is not attributed to them. `observed` means a validated selected source value, not a guarantee that age was independently verified or freshly updated. Missing timestamps remain Unknown; birth dates are not converted without an as-of contract.

Both initial pool construction and the existing refresh build-new-then-rebind loop put the sidecar in the same atomic pool entry as its exact Players. Bindings retain bounded actual object references and frozen relevant attributes, not a process-wide registry of reusable numeric object IDs. Equal replacement objects, cross-format instances, stale session objects, wrong map keys and attribute mutations cannot inherit another Player's evidence. A failed refresh keeps the old pool and its own evidence; partial format refresh preserves the untouched format's incarnation. Already captured old requests retain their original facts.

For the new candidate revision only, `_owner_generation_context` owns one selected-Player map, freezes source validation against the original pool references and their immutable signatures, then deep-copies the complete generator input tree using that owned map. The explicit capture step rebinds those frozen validation results to owned copies only when their relevant attributes match the retained signature. It never uses a later lookup in the caller's mutable Player map to certify a source. This covers Players, nested preferences and selection arrays without modifying their values. Generator kwargs remain the same: a minimal dict-compatible private attribute carries evidence separately. Ordinary `dict(context)`, `.copy()` or `**context` discards that attribute; a subsequent assignment records Unknown. Arbitrary deep copying does not authenticate freshly copied Players either. Generation never depends on the attribute.

The new revision's assignment stores detached request-level `input_evidence`, outside the strict `Player(**attrs)` payload, and binds it into the request hash. Candidate Player capture also retains the existing `search_rank` and `pick_value` fields used by fallback outlook; no duplicate `id`/`name` is added. Returned candidate assignment inputs, including member boards, are detached before their hash is minted. These are **new future capture guarantees**, not proof that older records reproduced every input used in historical execution. The experiment hash remains an assignment/join key, not a certificate permitting skipped evaluation.

Per-offer projection retains only exact offered age rows and the unchanged request-hash join to the full once-per-run capture. Existing private diagnostic compaction/hydration preserves these fields; no public response or valuation/proof schema gains an age-evidence field. Other managers' boards remain private. Default-off returns the prior plain context, prior Player capture shape and prior hash behavior; it does not detach legacy Player inputs or expose the private channel.

## Verification

Seven named controls (nine parameterized cases) were observed RED before their fixes:

- `test_named_red_control_pool_keeps_genuine_25_distinct_from_fallback_25`: the actual successful pool entry discarded provenance although both public ages were 25.
- `test_named_red_control_revision_detaches_player_instances`: changing an original Player after context capture changed the supposedly captured age.
- `test_named_red_control_revision_captures_search_rank_and_pick_value`: the assignment omitted consumed existing fields.
- `test_named_red_control_assignment_member_board_is_detached`: changing a context member's board altered an already-hashed returned assignment.
- `test_named_red_control_pool_age_and_evidence_use_same_source_read`: both raw and enriched source mutation between construction and recording produced Player age 25 with evidence age 40.
- `test_named_red_control_selection_cannot_rebind_checked_age_to_mutated_player`: mutation immediately after validation rebound observed age 25 to a captured Player aged 26.
- `test_named_red_control_copy_cannot_retarget_selected_pool_incarnation`: both foreign-to-original and original-to-foreign live-map swaps during copying changed attribution instead of retaining the selected incarnation. The final implementation keeps one owned selection snapshot and its pre-copy validation result.

Restored GREEN: **77 focused tests**, plus existing bilateral routes, owner routes, player refresh and DP crosswalk tests, **149 passed in 5.09 seconds**. Tests cover source priority, invalid values and timestamps, both formats/rebuild failure/partial refresh, exact incarnation and preclone matching, mutation during/after capture, copy loss, no additional SQL/provider calls, strict replay with nondefault fields/owned picks, private selected and organic durability, exact offered-row projection and unchanged model proof output with/without the private channel. Network is denied in the new tests and database work uses isolated SQLite fixtures. Deterministic mutation hooks are adversarial falsifications of the provenance contract, not evidence that those interleavings occurred in production.

An additional read-only comparison executed the untouched assignment functions from checkpoint `6c53caf9` against the new functions on ten default-off configuration cases. Every returned field except intentionally volatile `captured_at` matched exactly. One independently obtained old hash is committed as a golden regression. The initial test-mode collection attempts stopped at explicit hermetic-environment safety rails; they are not counted as mechanism RED evidence. The successful regression runs use the repository's existing isolated route-fixture pattern.

Reproduction from the isolated worktree:

```sh
DATABASE_URL=sqlite:///:memory: PYTHONDONTWRITEBYTECODE=1 \
FTF_DP_VALUES_FILE=backend/tests/fixtures/outlook-hypotheses/dp-values-players-2026-08-09.csv \
/private/tmp/ktc-benchmark-venv/bin/python -m pytest \
  backend/tests/test_trade_input_evidence.py \
  backend/tests/test_bilateral_revision_routes.py \
  backend/tests/test_owner_generator_routes.py \
  backend/tests/test_players_refresh.py \
  backend/tests/test_dp_crosswalk_position.py \
  -q -p no:cacheprovider --tb=short
```

## Bounded capture-cost observation

After the performance agent released its exclusive timing window, five local synthetic trials used real Player dataclasses, twelve manager boards/source maps and nested request inputs. This measures capture work separately from construction, serialization, persistence and provider acquisition; it is not production latency or a release result.

| Synthetic size | Full input deep-copy median | Source validation + detached context median |
|---|---:|---:|
| 1,000 Players / 12,000 manager-board rows | 8.16 ms | 19.62 ms |
| 3,000 Players / 36,000 manager-board rows | 24.79 ms | 59.86 ms |

The total includes provenance validation/rebinding and the whole input copy. Assignment creation has its own canonicalization/detachment cost and is not included in this microbenchmark. No timing threshold was fitted, and this observation does not waive the independent worker latency gate.

## State and limits

Runtime source at focused verification: server SHA-256 `3fa92ee850dfc8eb01a69ab7d052a85f8cda5facc158ac84d730ad27d2ed19c6`; helper SHA-256 `d294a4d049c00c4191d7e5964197452ff7c4fad3140572ff23cd98a8d0c27065`. Agent A independently reviewed the final source, full specification and tests without a blocking finding; parent also reviewed the diff. Parent owns the fresh full-suite result and release decision. Earlier 72/144 and 75/147 results and their hashes were superseded by these final capture corrections. No production access, source promotion, flag change or historical-record mutation was performed. Actual starter projections, corrected age-aware model decisions and authenticated proof reuse remain separately scoped work.
