-- ===========================================================================
-- negmem-gr4-joint.sql — the GR4 joint-multiplier audit.
-- Spec: docs/plans/negative-results-memory/LLD.md §7.3 (DE-6), read with
-- §8.4 runbook line 6.
--
-- WHAT IT ANSWERS: "is negmem compounding with the rest of the ordering stack
-- into a card nobody will ever see again?" GR4 is a trend detector, not a
-- proof — it watches the 5th percentile of the JOINT multiplier and trips
-- when the tail sinks too far.
--
--     joint(row) = negmem_m(row) x final_score / base_score
--
-- TRIP: p5(joint) < 0.15  =>  raise floors (GR4). The bar is p5 >= 0.15.
--
-- WHY THE RATIO DOES NOT DOUBLE-COUNT m (the point of the definition):
--   * `base_score` is card.composite_score AT LOGGING (server.py:4213), and
--     on the serving and gen_v2 paths that value ALREADY CONTAINS m — those
--     seams multiply the composite at generation (LLD §6.2/§6.3). So
--     final/base is purely the POST-generation ordering stack and `joint`
--     counts m exactly once, never m^2.
--   * On FIT rows composite is pure (§6.4 is ordering-only), and on bake-off
--     decks final == base (rerankers bypassed, server.py:4229) — so joint = m
--     there. One formula, uniform across paths.
--
-- THE THOMPSON LAYER, NAMED: the Thompson draw multiplier folds into the
-- ordering key that becomes `final_score`, so it enters the joint VIA THE
-- RATIO. The `propensity` column (database.py:508) records that same draw and
-- is selected below for ISOLATION only — never multiply it back in, that
-- would double-count the draw.
--
-- ACCEPTED POLLUTION (DE-6): A6 diversity penalties and session demotions
-- also ride final/base and push `joint` DOWN — i.e. toward a FALSE trip, the
-- safe direction. Four layers at their floors (0.6 x 0.7 x 0.25 x 0.5 =
-- 0.0525) is the theoretical worst WITHOUT negmem firing at all. So when p5
-- approaches 0.15 the first question is ratio pollution, not real compounding
-- (runbook line 6). Stamping fatigue_m / taste_m under the same uniformity
-- rule is the P2-shaped escalation; it is not built.
--
-- ROW SCOPE, and why each clause is there:
--   model_arm IS NULL   NON-BAKE-OFF rows only. Bake-off decks bypass the
--                       rerankers, so their final == base and they would dump
--                       a pile of joint == m into the percentile, flattering
--                       the tail.
--   base_score > 0      the ratio is undefined otherwise.
--   league_id IN (...)  allowlist-scoped, same loader as the build (HLD §7).
--   served_at >= day    flag-era only — pre-flag rows carry no stamp.
--
-- BINDS: :flag_on_day (ISO day the flag went on); {allowlist} substituted by
-- the pack runner from negmem.load_negmem_league_allowlist(). A "*" wildcard
-- entry means every league — the runner then substitutes no league filter.
--
-- DIALECT (DE-4): SQLite form is NORMATIVE and runs unchanged on Postgres.
-- TWO deliberate non-uses:
--   * `features_json` is returned RAW; the runner parses .negmem.m in Python.
--     Extracting it in SQL would need json_extract (SQLite) or ->> (Postgres)
--     — dialect-split syntax for a value the runner is already holding a JSON
--     parser for. The Postgres-only variant, for reference:
--       (i.features_json::jsonb -> 'negmem' ->> 'm')::float AS negmem_m
--   * p5 is computed in PYTHON, not in SQL: SQLite has no percentile function
--     and PERCENTILE_CONT is Postgres-only. The runner sorts the joint values
--     and takes the 5th-percentile element.
--
-- Rows where the parsed stamp is absent (pre-flag stragglers) or carries
-- {degraded:true} are EXCLUDED by the runner before the percentile: a
-- degraded map multiplied nothing, so its 1.0 would dilute the tail.
-- ===========================================================================

SELECT i.impression_id,
       substr(i.served_at, 1, 10) AS day,
       i.league_id,
       i.features_json,          -- runner parses .negmem.m (see DIALECT above)
       i.base_score,
       i.final_score,
       i.propensity              -- the Thompson draw, for ISOLATION only:
                                 -- it is ALREADY inside final/base. Never
                                 -- multiply it into the joint.
  FROM deck_impressions i
 WHERE substr(i.served_at, 1, 10) >= :flag_on_day
   AND i.league_id IN ({allowlist})                 -- ALLOWLIST-SCOPED (HLD §7)
   AND i.model_arm IS NULL                          -- non-bake-off rows only
   AND i.base_score IS NOT NULL
   AND i.base_score > 0
   AND i.final_score IS NOT NULL
 ORDER BY i.served_at;
