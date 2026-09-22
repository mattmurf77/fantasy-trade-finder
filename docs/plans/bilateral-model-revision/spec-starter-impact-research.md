# Parent specification — starter-impact data plan

2026-09-22. The owner explicitly authorizes production deployment of the current
new model and its documentation to learn from user data despite the previously
disclosed latency and model-quality uncertainty. Parent owns release operations,
CI, configuration changes/readback and the final integrated data-source plan.
This research does not authorize implementing a new projection pipeline yet.

## Parallel research lanes

1. Agent A: Sleeper's season-long and weekly fantasy projection sources. Inspect
   current repository adapters/fixtures, then verify primary official sources
   and, if necessary, a few bounded public read-only requests. Distinguish
   documented API, observable but undocumented endpoints, current-season versus
   historical availability and actual verified payload semantics. Determine
   full-season/rest-of-season versus weekly horizons, projected stat fields,
   scoring adjustments, player IDs, bye/schedule/injury/status coverage, timestamps,
   updates, limits and failure behavior. Do not assume missing rows mean zero,
   divide season totals blindly by17, or assume a season endpoint is remaining
   projection rather than actual-plus-projected. Report what is unknown. Write
   `starter-impact-sleeper-research.md` only (private probe scripts in unique tmp
   directories are allowed via apply_patch); no runtime, other docs or prod writes.
2. Agent B: year-long fantasy rankings/projections alternatives from primary
   providers and maintained source projects. Prioritize redraft/in-season/ROS
   points or ranks, not dynasty market prices as scoring projections. Compare
   FantasyPros and reasonable public/licensed alternatives, including raw weekly
   stat projection availability, scoring/TEP/IDP/2QB support, ID mapping, legal
   access/licensing, coverage/freshness and historical as-of retention. Owner
   approvals for Sleeper/KTC/MFL do not imply other-provider commercial reuse
   rights. No purchases/accounts/bulk scraping. Write
   `starter-impact-alternative-sources.md` only; primary web citations required.
3. Agent C: current internal starter-impact and season-forecast data path. Read
   source without running generation or touching production. Identify reusable
   league scoring/slots/bench/IR/inactive/schedule/projection adapters and data
   provenance; current gaps and where a frozen projection snapshot should enter
   both managers' give/receive lineup evaluation. Design weekly legal-lineup
   reoptimization and season/ROS aggregation without bye double-counting,
   including bench substitution, FLEX/SF assignment, injury/missing distinction,
   required cuts and outlook-specific weighting. Add pre/post release evaluation
   requirements and identify existing genuine-view, like/mutual/completion
   attribution gaps so production learning does not mislabel generated cards.
   Write `starter-impact-internal-audit.md` only, with cited source locations.

## Common constraints and handoff

Use current canonical AGENTS/README/workflow instructions; isolated worktree is
`/private/tmp/fleeced-bilateral-revision-20260922`. Preserve all runtime/test files
and the frozen release candidate. No new packages, flags, schemas, credentials,
provider writes, bulk ingestion, model weights or user messaging. Public bounded
read-only source verification is permitted. Cite direct primary URLs and dates,
mark inferences and access failures honestly; no fabricated endpoint contracts.

Parent will combine findings into an engineering-ready Markdown plan covering
source selection, evidence quality, weekly and season horizon semantics,
architecture/refresh/cache/performance, private versioned offer-time evidence,
incremental rollout/rollback, bilateral eval/unknown handling and acceptance
criteria. A bye is zero for the unavailable player's week, not automatically zero
for the team's occupied slot; optimize the legal replacement lineup. Keep current
dynasty pricing separate from projected in-season utility. Draft picks need
future/dynasty value rather than fabricated weekly points. Cover missing full
boards, sparse actual outcomes and whether rankings are only a fallback prior.
