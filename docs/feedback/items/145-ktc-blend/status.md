# Status — 145-ktc-blend

```project-status
{
  "status": "shipped",
  "updated": "2026-07-18",
  "summary": "#145 — Blend KeepTradeCut into the baseline consensus — status",
  "evidence": "Carried forward as the last documented disposition, not a fresh production audit. Prior index merge corrections take precedence over older pre-merge notes. Last documented index disposition: shipped 2026-07-18 — FB-145 KTC blend `ktc_blend_weight=0.5` — CHANGELOG 2026-07-18, v1.9.0. Prior row preserved at ../../../reviews/2026/2026-09-06-project-status-migration/feedback-index.md."
}
```

## Historical notes

The material below is retained evidence. Its former status wording does not override the record above.

# #145 — Blend KeepTradeCut into the baseline consensus — status

**State:** built + tested (2026-07-17, branch `trade-engine-v2`). Source-layer
change only (seed values in, same pool shape out) — no trade-engine changes,
per the operator's separate trade-logic thread. New KTC-blend suite green
(13 tests); full change-adjacent suites green (116). Grouped with **#148**
(the sf_tep TE premium) — both live in the same consensus-seed layer;
#148's own notes are in `docs/feedback/items/148-tep-te-copy/status.md`.

**Owner ask (operator-validated):** "Player universe shouldn't change at
all… blend the two rank sets [DynastyProcess + KeepTradeCut]… baseline
consensus rankings set built from this aggregate."

## What shipped

All in `backend/data_loader.py` (`_apply_consensus_blend`, called at the end
of `_fetch_dynasty_process` so both format builds go through it):

1. **Sourcing.** KTC has no official API. Its `dynasty-rankings` page embeds
   the full top-500 player list as a `var playersArray = [...]` HTML literal;
   `parse_ktc_players` extracts it. Each entry carries both formats plus
   TE-premium variants — one GET per boot (24h in-memory TTL, browser
   headers to clear Cloudflare) serves both builds. `1qb_ppr` reads
   `oneQBValues.value`; `sf_tep` reads the TE-premium `superflexValues.tep.value`.
2. **Fail-soft.** Any KTC problem (fetch error, 403, markup change,
   `playersArray` missing) → `_ktc_consensus` logs and returns `{}`, and the
   blend leaves the maps **DP-only**. Never blocks boot; the failure is cached
   for the TTL so a broken endpoint isn't re-hammered. Mirrors the existing DP
   CSV last-good/flat-Elo fallback.
3. **Blend math.** KTC values are **rank-normalized onto the DP value curve**
   per format (the KTC-rank-i matched player takes the i-th largest DP pool
   value), then `value = (1−w)·dp + w·ktc_on_dp`, `w = model_config
   ktc_blend_weight` (default 0.5). Rank-normalization keeps the value
   distribution DP-shaped → tier occupancy and the #117 affine calibration
   (top asset ≈ 4 firsts) are preserved while KTC's *ordering* opinion is
   imported. A top-anchor guard rescales if the blended max ever slips below
   the DP max (sources disagree on #1) so the top asset still lands on the
   4-firsts rung.
4. **Universe unchanged.** Only players already in the DP-derived pool are
   blended; match is position-strict (#127) via the DP `db_playerids.csv`
   crosswalk (`espn_service.get_crosswalk`, extended with `by_ktc_id` /
   `by_mfl_id`), id-first with a name fallback, never across positions.
   Unmatched KTC players are ignored; unmatched pool players keep pure DP. On
   2026-07-17 data, 441/464 KTC players matched.
5. **Kill switch.** `ktc_blend_weight = 0` (+ `tep_te_uplift = 1`) reproduces
   the pre-#145 DP-only seeds **byte-for-byte** and short-circuits before KTC
   is fetched. Takes effect on next boot / pool rebuild.
6. **Value-history versioning — no marker/rescale.** Unlike the #117 scale
   migration (linear→affine, which needed `value_history_seed_scale`), a
   blend does not change the value *scale* — individual players shift
   slightly on the same affine map. Pre/post-blend `player_value_history` rows
   stay directly comparable, so the FB-61 30d-trend baselines remain valid.
   Documented in runbook + data-dictionary.

## Occupancy sanity (2026-07-17 pool, w=0.5, tep_te_uplift=1.18)

Top asset reads **4.00 firsts** in both formats (affine anchor holds); top-5
read 3.4–4.0 firsts. "Worth a 1st or more" per position stays bounded
(≤ ~35), no tier inflation. Full before/after tables in the final report.

## Knobs (model_config, DB-seeded)

| Key | Default | Effect |
|---|---|---|
| `ktc_blend_weight` | 0.5 | KTC weight; 0 = DP-only kill switch, 1 = KTC ordering only |
| `tep_te_uplift` | 1.18 | #148 — sf_tep TE premium multiplier; 1 = off |

## Files

- `backend/data_loader.py` — KTC fetch + parse + blend (`_apply_consensus_blend`,
  `_ktc_consensus`, `parse_ktc_players`, `_blend_config`, `_fetch_ktc_html`,
  `_crosswalk_id_maps`).
- `backend/espn_service.py` — `Crosswalk.by_ktc_id` / `by_mfl_id`.
- `backend/database.py` — `ktc_blend_weight`, `tep_te_uplift` defaults.
- `backend/tests/test_ktc_blend.py` — new suite (parse, blend-off byte
  identity, fail-soft, universe-unchanged, occupancy, #148 TE pins).
- `backend/tests/fixtures/ktc_rankings_snapshot_2026-07-17.html`,
  `ktc_blend_pipeline_2026-07-17.json` — checked-in fixtures.
- Docs: `config-reference.md`, `runbook.md`, `architecture.md`, `glossary.md`,
  `data-dictionary.md`.

## Fragility watch

The KTC scrape is unsanctioned — expect the page markup to break without
notice. Fail-soft covers "down"; the `ktc_blend_weight = 0` kill switch
covers "serving garbage". Guard suite pins the parse + blend against
checked-in fixtures (network-free). See runbook → "KTC consensus blend".
