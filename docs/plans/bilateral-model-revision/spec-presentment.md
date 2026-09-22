# Agent B specification — post-significance survivor ordering

Read scope.md, ../model-evaluation-framework/model-revision-plan.md section5, comparison-2026-09-22.md and scorecard-spec.md. Repo canonical AGENTS.md applies. Model Astra Ultra; worktree /private/tmp/fleeced-bilateral-revision-20260922.

## Ownership / API

Own backend/trade_bilateral_presentment.py, backend/tests/test_bilateral_presentment.py and docs/plans/bilateral-model-revision/presentment-evidence.md. No server/config/generator/eval edits; parent wires once after final significance/removal and before first durable publication. No prod changes.

Expose pure present(cards, *, selected_give=(), selected_receive=(), opponent_user_id=None) -> (ordered_cards, diagnostics). Parent only calls it for the captured revision2 exclusive owner deck; module must independently identify eligible version2 owner-evaluated cards and leave unknown/legacy/injected/likes_you cards in their exact slots. All explicit-selection/selected-partner searches return unchanged. Preserve object identity, terms, immutable proof, membership and count; no rank mutation to proof or max output count.

## Behavior

Improve survivor novelty after significance: trade purpose, give focal, receive focal, partner. Compare meaningful alternatives within bounded **both-manager** quality tolerance, not merely A score or gross sum. No candidate with known unacceptable proof becomes eligible because different. Do not reorder across protected/inbound/source classes. Be deterministic and bounded in time/memory (thousands of cards); one final ordering pass only. Quality-leading representative first; prevent needlessly repeated headliners where similarly good distinct alternatives exist. Avoid starvation, forced quotas or inventing variants. If novelty unavailable, retain strongest legitimate cards. Preserve full surviving inventory for later exploration. Returning no-op when metadata is absent is safer than fabricating quality.

Diagnostics aggregate count/moved/quality tolerance/version; if per-card occurrence map needed tell parent exact schema. No public counterparty private rankings, raw Elo or claimed acceptance probability. Do not log into DB or import server/database; existing private features supply evidence.

## Verification

Tests: post-filter synthetic case reproducing original11/30→17/30 concentration, bounded improvement on available comparable alternatives; quality nonregression for either manager; first/final inventory identical; exact identity/duplicates maintained, no resurrection; protected slots at arbitrary positions; different source/version no crossover; explicit-selection/partner no-op; deterministic independent of unstable card IDs; 10k-card time sanity without brittle wallclock assertion. Named sabotage proving test sensitivity. Parent separately tests actual worker invocation and no poll-time reorder. Return results, failure probes and review boundaries.
