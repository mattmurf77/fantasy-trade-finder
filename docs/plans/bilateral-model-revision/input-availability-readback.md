# Production evidence availability — September 22, 2026

Read-only aggregate query against Render production PostgreSQL at
**2026-09-22T06:40:11.459831+00:00**. Connection used the established
`backend.tools.prod_analytics` helper with server-enforced
`default_transaction_read_only=on`, explicitly verified by SHOW, and a10-second
statement timeout. The private script performs only SELECT/SHOW; no server import,
schema setup, row export, provider fetch, generation, flag change or deployment.
No credentials or user/league identifiers appear here.

- `season_forecast_snapshots`:0 retained rows.
- `season_projection_snapshots`:0 retained rows across0 leagues; no latest
  capture or unexpired evidence exists. The aggregate SUM returnsNULL over an
  empty table; this is not a failed query or an unknown nonempty population.
- `trade_matches` in the preceding30 days, excluding `league_demo`:1 row,
  status `pending`;0 rows have both impression links;0 have both managers'
  subsequent confirmation decisions set to `accept`.

The match table normally records two mirrored likes, followed by a separate
confirmation lifecycle. That one pending row is not a provider completion, nor a
fully attributed evaluation episode. This query does not classify every historic
match, reverify actor authenticity, infer unseen rejections, establish provider
completion coverage, or estimate an acceptance rate. Zero linked observations
means no usable paired-impression evidence in this bounded result, not proof of
zero user interest in the product.

## Consequence for this revision

The source-level conditional Win Now reuse path is real, but **there are no
existing durable projection snapshots to reuse in production at this check**.
Adding only a reader would not resolve today's starter-evidence gap. Preparation,
source-observation provenance and exact-format/roster qualification must first
produce those records; old request captures cannot be backfilled with future
data. No preparation was started by this read.

Offline mechanical tests and independent contextual review remain useful, but
they cannot establish live mutual acceptance from these counts. A later scoped
online evaluation must distinguish exposure, one-sided intent, mutual interest,
confirmation, and verified provider completion, retaining their own timestamps.
Missing outcomes and starter evidence remain explicit, not inferred passes.
