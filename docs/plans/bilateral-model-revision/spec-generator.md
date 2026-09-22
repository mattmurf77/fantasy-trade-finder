# Agent A specification — separately versioned bilateral candidate

Read scope.md first, ../model-evaluation-framework/model-revision-plan.md M1/M2/M3, scorecard-spec.md and comparison-2026-09-22.md. Repo instructions from canonical /Users/teresadickens/Documents/Claude/Projects/Fleeced/AGENTS.md apply. Model: Astra Ultra. Worktree /private/tmp/fleeced-bilateral-revision-20260922.

## Ownership / output

Own new backend/trade_gen_bilateral_candidate.py, narrowly necessary reusable generation hook in backend/trade_gen_bilateral.py, backend/tests/test_bilateral_candidate.py, and docs/plans/bilateral-model-revision/generator-evidence.md. No edits to server, bakeoff selector, config defaults, evaluator or other agents' files. Parent integrates. No production access/toggles/push.

Expose generate_bilateral_trades(**kwargs), evaluate_bilateral_trades(cards, **kwargs), evaluate_bilateral_trade(card, **kwargs), VERSION/BILATERAL_GENERATOR_VERSION='owner-v2-bilateral-2'; ARM remains owner_v2_bilateral. Incumbent -1 entrypoints and output unchanged. Prefer subclassing incumbent _Search and a narrow shared generate-with-search/ranker/version helper over copying 500 lines; do not replace module globals or monkeypatch live code. Preserve request-pinned config, immutable exact proof and efficient reuse.

## Implement

1. Read actual existing mechanics first and identify where preference fulfillment/outlook support can outrank avoidable market sacrifice. Keep a decomposition of personal preference, plan/needs, adjusted market terms and uncertainty for both managers; support remains explicitly not a probability.
2. Minimal consideration: compare same focal/partner legal alternatives and avoid unnecessary companions or more expensive packages when they fail to add meaningful independently explainable counterparty benefit. Do not optimize only the initiating side or make giver/receiver symmetry dependent on traversal order. Prefer ranking non-dominated efficient alternatives over destroying all inventory. Mandatory safety and intentional-explicit searches stay authoritative. Personal preference perturbation must not increase asking price solely due to stronger liking.
3. Improve tank/rebuild portfolio ordering using picks, RB-sale relief and favored horizon-appropriate WR/TE/QB, jointly with personal intent. Preserve elite/discounted-prospect RB exceptions, explicit pins, selected-vs-inferred authority, separate counterpart outlook, and middle-outlook flexibility. No forced pick quotas, fabricated youth, or additional hard class ban. Ordinary unrelated neutral pieces may price a desirable focal trade.
4. Use actual fresh supplied starter/availability evidence if existing context supports it; otherwise mark proxy/Unknown and do not claim point improvement. Do not bolt on provider calls. Identify downstream data gaps to parent.
5. Preserve all search budgets, no max-card cap, small organic search plus explicit anchors. Add deterministic diagnostics of term efficiency/plan composition and elapsed work, private board details remain private. Do not reprice global picks or change stud-tax convention as an untested shortcut.

## Tests / acceptance

Use real constructor fixtures, not only mocked outputs. Validate incumbent byte parity except intentionally variable occurrence IDs; candidate generator/evaluator version agreement; both-manager mirror and asset permutation invariance; exact/partial pins; candidate budget stability; no false known opponent; elite/favored-youth and own-next-pick rules; prospect-discount exception; extra asset real-benefit versus needless-cost examples; stronger preference doesn't auto-price-up; all four outlooks; missing starter evidence not positive points; returned deck not capped. Add an independent before/after failure-sensitive regression for each new behavior, with a named sabotage and evidence. State any mechanism you could not support rather than claiming it done. Return API/files, tests, trade-offs and unresolved issues; do not tune against locked evaluator holdout results.
