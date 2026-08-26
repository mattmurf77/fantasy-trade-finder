-- ===========================================================================
-- bakeoff_readout.sql — the Friday bake-off readout pack (M2) + daily
-- tripwires (M4). Fit-challenger measurement rail; spec:
-- docs/plans/fit-challenger/LLD.md §5.3, queries adopted verbatim from
-- docs/plans/fit-challenger/PLAN-v2-draft-B.md §2.4 plus the M4 additions.
--
-- READ-ONLY POSTURE: run these under the backend/tools/prod_analytics.py
-- posture — a connection with default_transaction_read_only=on and a
-- statement_timeout. Nothing in this file writes, and nothing added to it
-- may write.
--
-- TWO STANDING BANS (readout review rules — reject any query violating them):
--   1. NEVER split fit by `basis`. Fit's `basis` does not mean what arm B's
--      means; analysis keys on features_json.fit.boards ∈
--      {both, viewer, partner, none} (review C4).
--   2. NEVER compare `composite_score` (or the fit 0–100 stamps) across arms
--      as a magnitude. The draft is rank-based; scores are arm-local (C7b).
--
-- Bucket vocabulary (pinned in trade_gen_fit._BUCKETS, = the SQL vocabulary):
--   both_high | mixed | you_tilt | them_tilt | both_ok | weak
--
-- Window rule: all denominators exclude ghosts (COALESCE(is_ghost,0)=0) and
-- no window starts before 2026-08-19 (D-091 contamination discipline).
-- Bind :window_start (ISO UTC) before running.
--
-- DIALECT: written for prod Postgres (features_json::json -> ... operators).
-- SQLite translation, kept as a comment because the readout only ever runs
-- against prod (LLD Punt-3):
--   i.features_json::json->'fit'->>'bucket'
--     ->  json_extract(i.features_json, '$.fit.bucket')
--   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY x)
--     ->  no direct SQLite analog; approximate via ORDER BY x LIMIT 1 OFFSET
--         (SELECT COUNT(*)/2 ...), or run the readout against Postgres.
-- ===========================================================================


-- ===========================================================================
-- §1 — WINDOW HEADER: supply, knob changes, config-snapshot diff
-- ===========================================================================

-- 1a. Decided cards per arm in the window (the n the verdict hangs on).
SELECT i.model_arm,
       COUNT(*) FILTER (WHERE o.action = 'like') AS likes,
       COUNT(*) FILTER (WHERE o.action = 'pass') AS passes,
       COUNT(*)                                  AS decided
FROM deck_impressions i
JOIN deck_outcomes o ON o.impression_id = i.impression_id
WHERE i.served_at >= :window_start
  AND COALESCE(i.is_ghost, 0) = 0
  AND o.action IN ('like', 'pass')
GROUP BY 1 ORDER BY 1;

-- 1b. Every logged knob change in the window (M1). Any engine-affecting key
--     mid-window => censor the window at changed_at (PLAN-v2 R-5); an
--     UNLOGGED change (found by 1c but absent here) => discard the window.
SELECT * FROM model_config_changes
WHERE changed_at >= :window_start
ORDER BY changed_at;

-- 1c. Config-snapshot diff instructions (manual in v1 — LLD Punt-1):
--     pull each run's effective config and diff against the round-start
--     snapshot by eye / local script. Any engine-affecting key differing
--     from round-start without a matching 1b row => WINDOW DISCARDED.
SELECT run_id, created_at, config_json
FROM bakeoff_runs
WHERE created_at >= :window_start
ORDER BY created_at
LIMIT 5;   -- first runs of the window = the round-start reference


-- ===========================================================================
-- §2 — CO-PRIMARY 1: decided like-rate by arm × fit bucket
-- (bucket-matched via the M3 fit_diag stamp on every arm; draft B §2.4 q1)
-- ===========================================================================

SELECT i.model_arm,
       COALESCE(i.features_json::json->'fit'->>'bucket',
                i.features_json::json->'fit_diag'->>'bucket') AS bucket,
       COUNT(*) FILTER (WHERE o.action = 'like') AS likes,
       COUNT(*) FILTER (WHERE o.action = 'pass') AS passes
FROM deck_impressions i
JOIN deck_outcomes o ON o.impression_id = i.impression_id
WHERE i.served_at >= :window_start
  AND COALESCE(i.is_ghost, 0) = 0
  AND o.action IN ('like', 'pass')
GROUP BY 1, 2;

-- Verdict buckets are both_high + mixed ONLY. Wilson intervals on every
-- rate; deltas < 3pp read "did not move"; nothing is called before its
-- pre-registered n (PLAN-v2 §4).


-- ===========================================================================
-- §3 — CO-PRIMARY 2: decline-reason mix by arm (draft B §2.4 q2)
-- (the metric of record for the value_giving complaint: 40% → target ≤ 25%)
-- ===========================================================================

SELECT i.model_arm, r.reason, r.detail, COUNT(*)
FROM trade_pass_reasons r
JOIN deck_impressions i ON i.impression_id = r.impression_id
WHERE i.served_at >= :window_start
GROUP BY 1, 2, 3 ORDER BY 4 DESC;


-- ===========================================================================
-- §4 — DECK-INTEGRITY TRIPWIRE (daily, not just Friday; draft B §2.4 q3)
-- R-9 bars: median deck < 22 => investigate same day;
--           median < 18 on 2 consecutive days => REVERT
--           (bakeoff_serve_interleaved = 0, same day, GOTCHAS entry);
--           SC2 target: median >= 24. Baseline: arm-B-only median 26.5.
-- ===========================================================================

SELECT SUBSTRING(created_at, 1, 10) AS d,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY deck_size) AS median_deck,
       PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_ms) AS p95_ms
FROM bakeoff_runs
WHERE served_arm IS NULL          -- interleaved decks only
GROUP BY 1 ORDER BY 1;


-- ===========================================================================
-- §5 — POSITION BALANCE: per-arm mean served position (draft B §2.4 q4)
-- Tripwire: abs(Δ mean card_index) > 2 between served arms => interleaver
-- bug; window suspect (draft B §6 row 7).
-- ===========================================================================

SELECT model_arm, AVG(card_index), COUNT(*)
FROM deck_impressions
WHERE served_at >= :window_start AND model_arm IS NOT NULL
GROUP BY 1;


-- ===========================================================================
-- §6 — FIT GENERATION DIAGNOSTICS (dark soak + serving; draft B §2.4 q5)
-- Extracted per run from bakeoff_runs.arms_json->'fit'->'diagnostics'.
-- W3 soak bars: top_q_junk_share <= 0.10; top_q_pick_share <= arm B + 10pp;
-- killed[K7] reported first-class (C2); one_sided_pct vs the 96.3% arm-B
-- headline.
-- ===========================================================================

SELECT SUBSTRING(created_at, 1, 10)                              AS d,
       COUNT(*)                                                  AS runs,
       AVG((arms_json::json->'fit'->'diagnostics'->>'enumerated')::numeric)      AS avg_enumerated,
       AVG((arms_json::json->'fit'->'diagnostics'->>'scored')::numeric)          AS avg_scored,
       AVG((arms_json::json->'fit'->'diagnostics'->>'one_sided_pct')::numeric)   AS avg_one_sided_pct,
       AVG((arms_json::json->'fit'->'diagnostics'->>'both_high_pct')::numeric)   AS avg_both_high_pct,
       AVG((arms_json::json->'fit'->'diagnostics'->>'mixed_pct')::numeric)       AS avg_mixed_pct,
       AVG((arms_json::json->'fit'->'diagnostics'->>'you_tilt_pct')::numeric)    AS avg_you_tilt_pct,
       AVG((arms_json::json->'fit'->'diagnostics'->>'median_aggregate')::numeric) AS avg_median_aggregate,
       AVG((arms_json::json->'fit'->'diagnostics'->>'top_q_pick_share')::numeric) AS avg_top_q_pick_share,
       AVG((arms_json::json->'fit'->'diagnostics'->>'top_q_junk_share')::numeric) AS avg_top_q_junk_share,
       AVG((arms_json::json->'fit'->'diagnostics'->>'ms')::numeric)              AS avg_ms
FROM bakeoff_runs
WHERE created_at >= :window_start
  AND arms_json::json ? 'fit'
GROUP BY 1 ORDER BY 1;

-- killed{} counters per run (K0..K7 + junk), inspected raw:
SELECT run_id, created_at,
       arms_json::json->'fit'->'diagnostics'->'killed' AS killed
FROM bakeoff_runs
WHERE created_at >= :window_start
  AND arms_json::json ? 'fit'
ORDER BY created_at DESC
LIMIT 20;


-- ===========================================================================
-- §7 — M4 TRIPWIRES (daily during transition weeks; the standing set plus
-- the four A-added rows: serve-bit leak, arm-B drift, fit_diag null-share,
-- max single-tester share)
-- ===========================================================================

-- 7a. SERVE-BIT LEAK — any served fit card while bakeoff_serve_fit was 0 is
--     a STOP (M4). Cross-reference against the §1b knob log for the exact
--     bakeoff_serve_fit flip instants before calling it.
SELECT COUNT(*) AS fit_impressions_in_window
FROM deck_impressions
WHERE model_arm = 'fit' AND served_at >= :window_start;

SELECT * FROM model_config_changes
WHERE key = 'bakeoff_serve_fit'
ORDER BY changed_at;
-- fit rows > 0 while the bit was 0 over the whole window => STOP: serve-bit
-- leak (draft B §6 / HLD F-6 — check both draft paths).

-- 7b. Per-arm error / forfeits from arms_json (arm health).
SELECT SUBSTRING(created_at, 1, 10) AS d, a.arm,
       COUNT(*) FILTER (WHERE a.val->>'error' IS NOT NULL) AS errors,
       AVG((a.val->>'forfeits')::numeric)                  AS avg_forfeits
FROM bakeoff_runs,
     LATERAL json_each(arms_json::json) AS a(arm, val)
WHERE created_at >= :window_start
GROUP BY 1, 2 ORDER BY 1, 2;

-- 7c. RE-RANKER BYPASS ASSERTION — keyed on served_arm IS NULL, which is the
--     ONLY recorded serving-mode state (NULL = interleaved, 'current' = dark);
--     there is NO bypass marker column on bakeoff_runs or inside arms_json —
--     do not invent one. Interleaved runs present => served rows in the
--     window must carry model_arm. A decided window whose majority of served
--     rows has NULL model_arm => measuring deck position, not model quality
--     => DISCARD (HANDOVER trap 5).
SELECT COUNT(*) FILTER (WHERE model_arm IS NULL)     AS null_arm_rows,
       COUNT(*)                                      AS served_rows,
       ROUND(100.0 * COUNT(*) FILTER (WHERE model_arm IS NULL) / NULLIF(COUNT(*), 0), 1)
                                                     AS null_arm_pct
FROM deck_impressions
WHERE served_at >= :window_start
  AND COALESCE(is_ghost, 0) = 0;

SELECT COUNT(*) AS interleaved_runs
FROM bakeoff_runs
WHERE created_at >= :window_start AND served_arm IS NULL;

-- 7d. GHOST SHARE vs configured rate (holdout health; drift > 5pp from
--     1/ghost_holdout_one_in => holdout logic suspect).
SELECT COUNT(*) FILTER (WHERE COALESCE(is_ghost, 0) = 1) AS ghosts,
       COUNT(*)                                          AS total,
       ROUND(100.0 * COUNT(*) FILTER (WHERE COALESCE(is_ghost, 0) = 1)
             / NULLIF(COUNT(*), 0), 1)                   AS ghost_pct
FROM deck_impressions
WHERE served_at >= :window_start;

-- 7e. MAX SINGLE-TESTER SHARE of decided cards — one tester dominating the
--     denominator makes the round an anecdote about one person.
SELECT i.user_id, COUNT(*) AS decided,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS share_pct
FROM deck_impressions i
JOIN deck_outcomes o ON o.impression_id = i.impression_id
WHERE i.served_at >= :window_start
  AND COALESCE(i.is_ghost, 0) = 0
  AND o.action IN ('like', 'pass')
GROUP BY 1 ORDER BY 2 DESC;

-- 7f. FIT_DIAG NULL-SHARE PER ARM — the M3 stamp is contractually present
--     (null-valued allowed) on every bake-off row. Null-share > 5% on any
--     arm => data bug (executemany column drop, HANDOVER trap 3); window
--     suspect until explained.
SELECT model_arm,
       COUNT(*) FILTER (WHERE features_json::json->'fit_diag' IS NULL
                           OR (features_json::json->>'fit_diag') IS NULL) AS null_fit_diag,
       COUNT(*)                                                           AS n_rows,
       ROUND(100.0 * COUNT(*) FILTER (WHERE features_json::json->'fit_diag' IS NULL
                           OR (features_json::json->>'fit_diag') IS NULL)
             / NULLIF(COUNT(*), 0), 1)                                    AS null_pct
FROM deck_impressions
WHERE served_at >= :window_start AND model_arm IS NOT NULL
GROUP BY 1;

-- 7g. CROSS-ROUND ARM-B DRIFT — arm B's bucketed like-rate vs its own prior
--     round. Bind :prior_start / :prior_end to the previous round. A moving
--     control means the window comparison is unanchored.
SELECT 'current_round' AS era,
       COALESCE(i.features_json::json->'fit_diag'->>'bucket', '(none)') AS bucket,
       COUNT(*) FILTER (WHERE o.action = 'like') AS likes,
       COUNT(*) FILTER (WHERE o.action = 'pass') AS passes
FROM deck_impressions i
JOIN deck_outcomes o ON o.impression_id = i.impression_id
WHERE i.model_arm = 'current' AND i.served_at >= :window_start
  AND COALESCE(i.is_ghost, 0) = 0 AND o.action IN ('like', 'pass')
GROUP BY 1, 2
UNION ALL
SELECT 'prior_round' AS era,
       COALESCE(i.features_json::json->'fit_diag'->>'bucket', '(none)') AS bucket,
       COUNT(*) FILTER (WHERE o.action = 'like') AS likes,
       COUNT(*) FILTER (WHERE o.action = 'pass') AS passes
FROM deck_impressions i
JOIN deck_outcomes o ON o.impression_id = i.impression_id
WHERE i.model_arm = 'current'
  AND i.served_at >= :prior_start AND i.served_at < :prior_end
  AND COALESCE(i.is_ghost, 0) = 0 AND o.action IN ('like', 'pass')
GROUP BY 1, 2;

-- 7h. SCORER-VERSION SKEW (failure row 11) — mixed fit.ver / fit_diag.ver
--     inside one window => the bucket comparison is invalid for the window;
--     fall back to pooled and flag it in the readout header.
SELECT COALESCE(features_json::json->'fit'->>'ver',
                features_json::json->'fit_diag'->>'ver') AS scorer_ver,
       COUNT(*)
FROM deck_impressions
WHERE served_at >= :window_start AND model_arm IS NOT NULL
GROUP BY 1;


-- ===========================================================================
-- §8 — GUARDRAIL (never the verdict — C3): pooled like-rate per arm.
-- Printed LAST on purpose. The fit arm deliberately serves tilt cards and
-- would lose a pooled comparison by construction. R-12 tripwire only:
-- fit pooled < 5% for a full week at n >= 100 => pause and inspect
-- top-of-deck cards by hand.
-- ===========================================================================

SELECT i.model_arm,
       COUNT(*) FILTER (WHERE o.action = 'like') AS likes,
       COUNT(*) FILTER (WHERE o.action = 'pass') AS passes,
       ROUND(100.0 * COUNT(*) FILTER (WHERE o.action = 'like')
             / NULLIF(COUNT(*), 0), 1)           AS pooled_like_pct
FROM deck_impressions i
JOIN deck_outcomes o ON o.impression_id = i.impression_id
WHERE i.served_at >= :window_start
  AND COALESCE(i.is_ghost, 0) = 0
  AND o.action IN ('like', 'pass')
GROUP BY 1 ORDER BY 1;
-- GUARDRAIL (never the verdict — C3).


-- ===========================================================================
-- §9 — LENS CALIBRATION (diagnostic appendix, not a verdict metric).
-- Informs the fit_w_* iterate path (PLAN-v2 §4 / §2.5); weights are never
-- changed mid-window; a promote verdict includes a lens-calibration pass
-- before weights are declared final.
--
-- Lens payload (LLD §1.7): features_json.fit.lenses = {you, them} ×
-- {board (L1), vs_consensus (L2), consensus (L3)}, 0–100, null where the
-- lens did not fire (nulls serialize — R-h). fit cards always carry it; the
-- COALESCE fallback onto features_json.fit_diag.lenses picks up other arms'
-- cards if/when the M3 stamp carries lens detail, and degrades to no rows
-- (never wrong rows) where it does not.
-- ===========================================================================

-- 9a. Per-lens outcome correlation: mean lens score on liked vs passed
--     cards, per lens × team side × arm. The question: does L1
--     (board-vs-board) actually predict likes better than L3 (consensus)?
SELECT i.model_arm, lens.side, lens.lens, o.action,
       ROUND(AVG(lens.score::numeric), 1) AS mean_score,
       COUNT(*)                           AS n
FROM deck_impressions i
JOIN deck_outcomes o ON o.impression_id = i.impression_id
CROSS JOIN LATERAL (VALUES
  ('you',  'L1_board',        COALESCE(i.features_json::json #>> '{fit,lenses,you,board}',
                                       i.features_json::json #>> '{fit_diag,lenses,you,board}')),
  ('you',  'L2_vs_consensus', COALESCE(i.features_json::json #>> '{fit,lenses,you,vs_consensus}',
                                       i.features_json::json #>> '{fit_diag,lenses,you,vs_consensus}')),
  ('you',  'L3_consensus',    COALESCE(i.features_json::json #>> '{fit,lenses,you,consensus}',
                                       i.features_json::json #>> '{fit_diag,lenses,you,consensus}')),
  ('them', 'L1_board',        COALESCE(i.features_json::json #>> '{fit,lenses,them,board}',
                                       i.features_json::json #>> '{fit_diag,lenses,them,board}')),
  ('them', 'L2_vs_consensus', COALESCE(i.features_json::json #>> '{fit,lenses,them,vs_consensus}',
                                       i.features_json::json #>> '{fit_diag,lenses,them,vs_consensus}')),
  ('them', 'L3_consensus',    COALESCE(i.features_json::json #>> '{fit,lenses,them,consensus}',
                                       i.features_json::json #>> '{fit_diag,lenses,them,consensus}'))
) AS lens(side, lens, score)
WHERE i.served_at >= :window_start
  AND COALESCE(i.is_ghost, 0) = 0
  AND o.action IN ('like', 'pass')
  AND lens.score IS NOT NULL
GROUP BY 1, 2, 3, 4 ORDER BY 1, 2, 3, 4;

-- 9b. Lens disagreement vs decline reason — the dual-board thesis, tested
--     directly: "giving up too much" (value_giving) passes should cluster
--     where the user's own board (L1 you) and consensus (L3 you) disagree
--     most. Buckets by |L1(you) − L3(you)| quartile over passed cards that
--     carry a trade_pass_reasons row.
WITH passed AS (
  SELECT i.impression_id,
         ABS((COALESCE(i.features_json::json #>> '{fit,lenses,you,board}',
                       i.features_json::json #>> '{fit_diag,lenses,you,board}'))::numeric
           - (COALESCE(i.features_json::json #>> '{fit,lenses,you,consensus}',
                       i.features_json::json #>> '{fit_diag,lenses,you,consensus}'))::numeric)
                                                        AS disagreement,
         CASE WHEN r.detail = 'value_giving' THEN 1 ELSE 0 END AS value_giving
  FROM deck_impressions i
  JOIN trade_pass_reasons r ON r.impression_id = i.impression_id
  WHERE i.served_at >= :window_start
    AND COALESCE(i.is_ghost, 0) = 0
    AND i.features_json::json #>> '{fit,lenses,you,board}' IS NOT NULL
    AND i.features_json::json #>> '{fit,lenses,you,consensus}' IS NOT NULL
)
SELECT quartile,
       COUNT(*)                                  AS passes,
       ROUND(100.0 * AVG(value_giving), 1)       AS value_giving_pct,
       ROUND(MIN(disagreement), 1)               AS min_disagreement,
       ROUND(MAX(disagreement), 1)               AS max_disagreement
FROM (SELECT NTILE(4) OVER (ORDER BY disagreement) AS quartile,
             disagreement, value_giving
      FROM passed) q
GROUP BY 1 ORDER BY 1;

-- 9c. Weight-sensitivity readout — like-rate by bucket recomputed under two
--     alternative fit_w_* vectors, pure SQL re-aggregation of the STORED
--     per-lens scores (no model rerun; renormalized over fired lenses, the
--     LLD §1.7 combine rule). Bucket CASE mirrors trade_gen_fit._bucket
--     (pinned thresholds 70/40) — if _bucket ever changes, change this WITH it.
WITH lens AS (
  SELECT i.impression_id, o.action,
         (i.features_json::json #>> '{fit,lenses,you,board}')::numeric         AS l1y,
         (i.features_json::json #>> '{fit,lenses,you,vs_consensus}')::numeric  AS l2y,
         (i.features_json::json #>> '{fit,lenses,you,consensus}')::numeric     AS l3y,
         (i.features_json::json #>> '{fit,lenses,them,board}')::numeric        AS l1t,
         (i.features_json::json #>> '{fit,lenses,them,vs_consensus}')::numeric AS l2t,
         (i.features_json::json #>> '{fit,lenses,them,consensus}')::numeric    AS l3t
  FROM deck_impressions i
  JOIN deck_outcomes o ON o.impression_id = i.impression_id
  WHERE i.served_at >= :window_start
    AND COALESCE(i.is_ghost, 0) = 0
    AND o.action IN ('like', 'pass')
    AND i.model_arm = 'fit'
),
rescored AS (
  SELECT w.label, l.action,
         (w.wb * COALESCE(l.l1y, 0) + w.wd * COALESCE(l.l2y, 0) + w.wc * COALESCE(l.l3y, 0))
           / NULLIF(w.wb * (l.l1y IS NOT NULL)::int + w.wd * (l.l2y IS NOT NULL)::int
                  + w.wc * (l.l3y IS NOT NULL)::int, 0) AS you,
         (w.wb * COALESCE(l.l1t, 0) + w.wd * COALESCE(l.l2t, 0) + w.wc * COALESCE(l.l3t, 0))
           / NULLIF(w.wb * (l.l1t IS NOT NULL)::int + w.wd * (l.l2t IS NOT NULL)::int
                  + w.wc * (l.l3t IS NOT NULL)::int, 0) AS them
  FROM lens l
  CROSS JOIN (VALUES ('alt_A 0.50/0.25/0.25', 0.50, 0.25, 0.25),
                     ('alt_B 0.30/0.30/0.40', 0.30, 0.30, 0.40)) AS w(label, wb, wd, wc)
)
SELECT label,
       CASE
         WHEN you >= 70 AND them >= 70 THEN 'both_high'
         WHEN (you >= 70 AND them >= 40 AND them < 70)
           OR (them >= 70 AND you >= 40 AND you < 70) THEN 'mixed'
         WHEN you >= 70 AND them < 40 THEN 'you_tilt'
         WHEN them >= 70 AND you < 40 THEN 'them_tilt'
         WHEN you >= 40 AND you < 70 AND them >= 40 AND them < 70 THEN 'both_ok'
         ELSE 'weak'
       END                                                AS recomputed_bucket,
       COUNT(*) FILTER (WHERE action = 'like')            AS likes,
       COUNT(*) FILTER (WHERE action = 'pass')            AS passes,
       ROUND(100.0 * COUNT(*) FILTER (WHERE action = 'like')
             / NULLIF(COUNT(*), 0), 1)                    AS like_pct
FROM rescored
WHERE you IS NOT NULL AND them IS NOT NULL
GROUP BY 1, 2 ORDER BY 1, 2;
-- Informs the fit_w_* iterate path (PLAN-v2 §4 / §2.5); weights are never
-- changed mid-window; a promote verdict includes a lens-calibration pass
-- before weights are declared final.
