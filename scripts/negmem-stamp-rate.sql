-- ===========================================================================
-- negmem-stamp-rate.sql — the negative-results-memory stamp-rate tripwire.
-- Spec: docs/plans/negative-results-memory/LLD.md §7.2 (query adopted
-- verbatim), read with §8.4 runbook lines 1 and 7.
--
-- WHAT IT ANSWERS: "is the memory actually running?" While `trade.negmem` is
-- ON, EVERY deck_impressions row written for an ALLOWLISTED league carries a
-- `features_json.negmem` key — served rows and ghost rows, every arm,
-- influenced or not (the §3.4 trichotomy stamps {m:1.0} when nothing fired).
-- So the expected stamp_rate is exactly 1.0000. Anything less means map
-- builds are failing silently: failure is in the DATA, never inferred from
-- absence.
--
-- READ-ONLY POSTURE: run under the backend/tools/prod_analytics.py posture —
-- default_transaction_read_only=on plus a statement_timeout. Nothing here
-- writes, and nothing added to this file may write.
--
-- BINDS:
--   :flag_on_day   the ISO day (YYYY-MM-DD) `trade.negmem` was flipped on.
--                  Rows before it have no stamp by design, so including them
--                  manufactures a false alarm.
--   {allowlist}    substituted by the pack runner from
--                  negmem.load_negmem_league_allowlist() — the SAME loader
--                  the build uses, so a partial rollout can never read as
--                  build failures. Do NOT hand-type a league list here.
--
-- DIALECT (DE-4): SQLite form is NORMATIVE. The `LIKE '%"negmem"%'` probe is
-- deliberate — it needs no JSON operator, so one statement runs on both
-- engines, and the key string cannot appear inside any value we write (no
-- free text enters features_json; the one free-text field in this family is
-- quarantined in trade_pass_reasons.free_text, database.py:903-905) and the
-- substring carries its own JSON quoting. The Postgres variant, kept as a
-- comment because the normative form already runs there:
--   SUM(CASE WHEN i.features_json::jsonb ? 'negmem' THEN 1 ELSE 0 END)
--
-- READING A ZERO — the two ways this query lies if you skim it:
--   * ZERO ROWS (empty denominator) while the flag is ON is NOT "no stamps".
--     It is an empty allowlist: the file is missing, unparseable, or lists no
--     league. Check the build warning log and negmem_readout's `allowlisted`
--     field before concluding builds are broken (runbook line 7). Note the
--     allowlist supports a "*" wildcard entry meaning every league — under
--     "*" the runner substitutes no league filter at all, and the denominator
--     is every flag-era row.
--   * A ZERO COUNT ANYWHERE IN THE M2 FAMILY is not "no drops". The M2 feed
--     is killed structurally by gen2_accept_prior_strength = 0 (GLOBAL knob
--     only — never an arm overlay, runbook line 4) and returns {} on a
--     degraded map. Under either condition the M2 queries never ran, so
--     negmem_readout's `dropped_unmapped_partner_ids: 0` means "not counted",
--     NOT "nothing was dropped". Always read that counter together with the
--     readout's `m2` annotation ("live" | "killed (…)" | "degraded").
--     `negmem_strength` does not govern M2 and cannot kill it.
--
-- TRIAGE ORDER when stamp_rate < 1.0 (runbook line 1): stamp rate ->
-- degraded notes (`negmem_note` on the job dict, `{degraded:true}` stamps) ->
-- the knob triple (negmem_strength / negmem_floor /
-- gen2_accept_prior_strength).
-- ===========================================================================

SELECT substr(i.served_at, 1, 10) AS day,
       COALESCE(i.model_arm, 'organic') AS arm,
       COUNT(*) AS rows_,
       SUM(CASE WHEN i.features_json LIKE '%"negmem"%' THEN 1 ELSE 0 END) AS stamped,
       ROUND(1.0 * SUM(CASE WHEN i.features_json LIKE '%"negmem"%' THEN 1 ELSE 0 END)
             / COUNT(*), 4) AS stamp_rate          -- expected 1.0000 while flag ON
  FROM deck_impressions i
 WHERE substr(i.served_at, 1, 10) >= :flag_on_day
   AND i.league_id IN ({allowlist})                 -- ALLOWLIST-SCOPED (HLD §7)
 GROUP BY 1, 2 ORDER BY 1, 2;
