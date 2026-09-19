# Status — 158-picks-ownership

```project-status
{
  "status": "shipped",
  "updated": "",
  "summary": "#158 — Draft picks in the calculator & suggestions — status",
  "evidence": "Carried forward as the last documented disposition, not a fresh production audit. Prior index merge corrections take precedence over older pre-merge notes. Last documented index disposition: shipped undated (PRD); cross-refs 2026-07 to -08 — `picks.owned_sync` flag. Prior row preserved at ../../../reviews/2026/2026-09-06-project-status-migration/feedback-index.md."
}
```

## Historical notes

The material below is retained evidence. Its former status wording does not override the record above.

# #158 — Draft picks in the calculator & suggestions — status

**Status:** shipped · date not recorded in this folder · `picks.owned_sync` flag

This folder's `prd.md` is marked "planning. PLAN ONLY — no code in this
folder" at authoring time, but the feature it specs (owned-pick
resolution/store/sync, calculator + suggestion inclusion) is extensively
built and live: `GET /api/league/picks`, `sync_draft_picks`/`replace_draft_picks`,
the `picks.owned_sync` daemon step, and `pick_values.py` are all documented
as shipped in `docs/api-reference.md`, `docs/data-dictionary.md`, and
`docs/architecture.md`, with multiple later items (#189, #200, #207, #220,
#228) building directly on top of it.

Backfilled 2026-08-08 — original session did not record a status.md in this
folder; classified `shipped` from cross-references in `docs/` rather than
from any file inside this folder.
