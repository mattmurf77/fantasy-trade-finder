# Candidate generator implementation evidence

September 22, 2026. Agent A, following the parent-authored [generator specification](spec-generator.md), [scope](scope.md), and [round 2 specification](spec-round2-price-and-presentation.md). Local implementation evidence only; no production access, config flip, deployment, acceptance claim, or evaluator holdout tuning.

## API and retained incumbent

`backend/trade_gen_bilateral_candidate.py` exports `generate_bilateral_trades(**kwargs)`, `evaluate_bilateral_trades(cards, **kwargs)`, `evaluate_bilateral_trade(card, **kwargs)`, and `VERSION` / `BILATERAL_GENERATOR_VERSION = owner-v2-bilateral-2`. The arm remains `owner_v2_bilateral`. The incumbent `owner-v2-bilateral-1` remains callable. Its only source edit extracts the existing generation loop into `_generate_with_search(search, *, ranker, version)`; incumbent entrypoints still pass their own search/ranker/version.

A frozen pre-edit incumbent card/report digest is checked after normalizing generated occurrence ID and timestamps. Config registration of the parent's new disabled knob is excluded from that source-parity check. Exact personal boards, captured config, pricing convention, search pool/per-pair/total budgets, full/partial selection semantics, and immutable exact-package proof remain inherited. No output cap is introduced and `max_cards` remains ignored.

## Mechanisms and round 2 finding

The candidate retains the incumbent support weights `.45 personal / .35 adjusted market / .20 plan`. A provisional reweighting was considered but removed because it would confound price efficiency with a broad market-equality preference. The independent framework decides whether the narrower candidate is useful.

Companion evaluation compares a valid package with a legal package removing one unpinned non-focal asset. An extra asset is independently useful when it meets the declared value-share threshold and supplies known personal interest, a declared target, future-portfolio utility, or meaningfully improves both-sided adjusted market balance. Otherwise it is marked avoidable. Both offers remain available; no valid inventory is deleted merely for inefficient consideration. Required price compensation and explicit anchors are preserved.

An actual round 2 regression showed that merely retaining weights and partitioning removable companions was insufficient: stronger target liking changed first outgoing consideration from 1000 to 1150 in a fixed three-player fixture. A new bounded, symmetric same-focal comparison now imposes precedence on offers sharing a partner and exact give or receive side. A cheaper alternative precedes the expensive alternative only when both managers' captured raw personal cost/benefit and portfolio direction are no worse, with matching positional and availability roles, or when the larger offer has an audited unnecessary companion. Different independently useful counterpart benefits stay distinct. Missing personal boards do not prove equivalent conviction.

The pure `term_precedence(cards) -> {later_index: set(earlier_indices)}` contract derives these edges from immutable private per-side `consideration_profile` and `term_efficiency` fields. `term_evidence_valid(data, *, user_id, target_user_id)` fails closed on incomplete/incompatible profile data; the serving helper uses it to protect malformed occurrences. `TERM_ORDERING_VERSION` is `same-focal-terms-1`; at most the first 32 lower-cost representatives per exact-side family are compared, giving at most 64 comparisons/edges per card plus sorting. Strictly increasing `(worst adjusted market loss, asset count)` makes the relation acyclic. Stable topological ordering keeps the constructor's existing quality/diversity order wherever no efficiency constraint applies. Unrelated focal exchanges are never treated as dominated merely because they cost more.

The post-significance module must preserve this native baseline and prevent novelty from crossing surviving precedence edges. An independently run composed constructor → survivors → original presentation test reproduced another RED: the original support-only presentation sort restored the costly offer to first place. Agent B owns that separate fix and its evidence.

## Outlook and evidence honesty

For tanking/rebuilding, future portfolio scoring jointly uses personal intent and known age/position: picks retain positive plan fit; favored horizon-appropriate WR/TE/QB get more fit than neutral youth, disfavored youth is not automatically desirable, and ordinary RB sales get relief. Rebuilding uses the weaker existing 0.6 intensity. Unknown age remains unknown. Canonical personally elite RB tiers and genuinely discounted personally favored prospects retain the incumbent explicit exceptions; own-next-draft pick and favored-young sale protections remain. Contending/all-in continue their existing plan mechanics. These coefficients remain provisional policy, not empirically ratified acceptance thresholds.

Private evidence includes plan composition by market-value share, known/unknown preference provenance, raw/adjusted market terms and the unchanged package-pricing convention, support decomposition/uncertainty, and explicit starter-evidence status. The existing constructor receives starter slots and inactive IDs, but no fresh scoring-compatible per-player projections, projection horizon, availability as-of timestamp, or complete required-cut evidence. Projected starter delta is therefore `null` / Unknown; immediate starter improvement is not applicable for a tanker. Dynasty roster fit is labeled as a proxy. No provider calls, invented points, global pick repricing or new stud convention are added.

## Executed local checks

All commands use `DATABASE_URL=sqlite:////private/tmp/bilateral-candidate-agent.sqlite` and `/private/tmp/ktc-benchmark-venv/bin/python` (3.14); production is never a test target. Parent owns supported-runtime/full-suite/CI/release verification.

Final generator verification: **34 candidate + 38 incumbent contracts = 72 passed**, 1.67s. Coverage includes frozen incumbent output, candidate generator/evaluator agreement, detached exact proofs, both-manager mirror, asset/roster permutations, full/partial/forged pins, capped-compute/full-output distinction, all four outlooks, unknown counterpart evidence, own-next-pick/favored-young protection, elite and discounted-prospect RB exceptions, real-benefit versus unnecessary companions, honest missing starter evidence, malformed term metadata, and the composed stronger-liking regression through final presentation. An intermediate combined candidate/incumbent/presentment run was **144 passed**, 3.35s; Agent B's evidence owns subsequent presentation-only additions.

Named isolated in-memory sabotage controls (no source sabotage persisted):

- `DISABLE_SAME_FOCAL_PRECEDENCE`: replace `term_precedence` with no edges. The stronger-liking fixture fails because the outgoing package changes from cheap to costly (1 failed).
- `RESTORE_AGE_ONLY_PORTFOLIO`: restore incumbent `_plan_asset`. The favored-versus-neutral youth fixture fails because both plan gains equal 0.75 (1 failed).
- `FABRICATE_STARTER_EVIDENCE`: label the missing projection evidence known and delta 0. The Unknown evidence fixture fails (1 failed).
- `IGNORE_REAL_COMPANION_PREFERENCE`: remove independently identified recipient benefits. The useful companion is incorrectly labeled avoidable and its test fails (1 failed).
- `DROP_AVOIDABLE_ALTERNATIVES`: turn inefficient-but-valid terms into an eligibility veto. The inventory-preservation test fails because the valid larger alternative disappears (1 failed).
- Initial test collection failed before the candidate module existed; this is bootstrapping evidence, not a substitute for the behavioral controls above.

Independent cross-review by Agent B reproduced the round 2 cheap→costly failure and identified that presentation would undo a constructor-only repair. Both now pass with the composed regression. Agent A separately reviewed the final Agent B presentation logic (both directions of precedence crossing, both-manager/fixed-baseline bounds, exact occurrence slots, version/proof checks and bounded work) and the parent's selector/publication integration; no additional blocking defect was found. The parent was advised to add an explicit same-arm overhaul rollback test, although the existing overhaul path already checks full generation identity/version.

## Limits

This is a bounded local efficiency audit, not an exhaustive search or a calibrated willingness model. Same-focal substitution comparisons requiring personal equivalence are intentionally evidence-limited for unknown counterpart boards. A survivor filter can change which 32 family representatives fall inside a new audit; presentation's preservation of the native baseline is not an exhaustive guarantee about newly discovered, previously unaudited edges. Companion usefulness thresholds, support weights and plan coefficients need independent grading/calibration. Broad real starter-benefit claims remain unsupported without the missing inputs. Raw market return alone cannot establish either manager's willingness or ideal consolidation compensation. Offline framework results and production/load/device/outcome coverage remain separate release gates owned by the parent.
