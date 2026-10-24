# Model-surface triage — classify before anyone plans

"The model served something wrong" is usually not a model defect: the write
didn't land, a source was stale, a deploy rolled the process, a flag or arm
served it, or a by-design refusal wore a bad message. Classify it in Phase 0,
**before** grouping and before any planner traces code. The classification is a
triage-table column; model defects leave the build pipeline as a packet.

**When to use:** a feedback item or report says a model output is wrong — a
trade card or deck, outlook or window, Win Now, player values or tiers, ranking
order, or a Calibration deck.

## Step 0 — the prod row first

- **Request it through `analytics-lead`, read-only.** Under the operator's
  2026-10-15 W3 decision, diagnosis reads (`backend/tools/prod_analytics.py` /
  `DATABASE_URL_PROD`, or the X-Cron-Secret admin GET reports) need no per-read
  approval once the grant is given in the acting session; until then, ask per
  pull. Never a write, migration, flag change or POST. Key names only.
- **Cite every result as `query | source | time` (UTC).**
- **Render logs are not W3** (it covers DB reads and admin GET reports only).
  Minute-level logs need the operator's approval, asked through the chain (area
  PM → `head-product` → coordinator). Never call the Render API without it.
- **Free first:** `git log origin/main`, `gh pr view <n> --json mergedAt`,
  `config/features.json` at the deployed sha, `living-memory/DECISIONS.md`,
  Sleeper's public API, and the unmodified code path run locally against the
  league's public data with a scratch SQLite. Never Maestro, the simulator or
  screen captures (D-056).

Rows to pull (names checked against `backend/database.py`,
`backend/analytics_taxonomy.py` and `backend/server.py` on 2026-10-15):

| Complaint | Pull |
|---|---|
| Any | `app_feedback`: `created_at` (UTC, canonical), `app_version`, `screen` |
| Trade card or deck | `deck_impressions` near the report: `impression_id`, `served_at`, `assets_json` (the exact card), `model_arm`, `policy_version`, `is_ghost`, `fairness_threshold`. Then `deck_outcomes` by `impression_id`; `trade_decisions` for the pair (`decision`, `created_at`, `impression_id`); `user_events` `trade_proposed` (like) / `match_swiped` (pass); `calc_find_a_trade_tapped` (`props.path`) if it came from the calculator |
| Values, tiers, ranking order | `member_rankings` (`elo`, `updated_at`, `scoring_format`) for the user and league; `player_value_history` (`consensus_value`, `snapshot_date`) for the players named |
| Outlook, window, preferences | `league_preferences` (`team_outlook`, `acquire_positions`, `trade_away_positions`, `avoid_positions`, `updated_at`) |
| Win Now, season projections | `win_now_jobs` (`status`, `reason`, `created_at`); `season_projection_snapshots` (`created_at`, `expires_at`) for the league |
| Calibration deck | `grading_sessions` / `grading_cards` (`arms_json`, `grade`, `tags_json`), or `GET /api/admin/grading/report` |
| Knob changes | `model_config_changes` (`key`, `old_value`, `new_value`, `changed_at`) around the report minute |

`user_events.occurred_at` is an ISO VARCHAR: compare as text (`extract()` fails).

## Decision tree — in order, stop at the first yes

1. **Did the write fail to land, or land and not read back?** ("I set it and it
   shows not set.") Evidence: `league_preferences.updated_at` /
   `member_rankings.updated_at` against the report minute; the
   `league_preferences/set` INFO line logs user/league/outlook/positions per
   write (Render logs, approval needed). Split "did the write land" from "what
   does the client read". → **write-path defect** → area eng lead via `head-eng`.
2. **Was a source stale at report time?** NFL week / Sleeper state
   (`https://api.sleeper.app/v1/state/nfl`), latest
   `player_value_history.snapshot_date`, roster sync (`leagues.updated_at`),
   prepared deck age (`prepared_trade_manifests_v2.created_at`, `expires_at`),
   Win Now projections (`season_projection_snapshots.expires_at`, the receipt's
   timestamp). → **data/freshness defect** → area eng lead via `head-eng`.
3. **Does the report minute sit on a deploy, rollover or decision?** Line up
   feedback `created_at` (UTC) to the minute against merges, Render deploys,
   process rollovers and `DECISIONS.md`. A typed client failure right after a
   rollover, or a deadline missed by a few hundred ms, is not a model fault. →
   **deploy/rollover** → `release-lead` via `head-eng`.
4. **Did a flag, knob, fork or arm other than the assumed one serve it?** Flags:
   defaults → `config/features.json` at the deployed sha → `FTF_FLAGS` env
   (later wins; `_compute_flags`, `backend/feature_flags.py`). Knobs:
   `model_config_changes`. Producer: `deck_impressions.model_arm` (NULL when no
   arm produced the card, e.g. a likes-you injection), `policy_version`;
   Calibration: `grading_cards.arms_json`. **Never infer a producer from a
   missing row:** the injector runs before impression logging, and a
   streamed-then-trimmed engine card carries `impression_id: 'none'`; read the
   ordering in `_run_trade_job` (`backend/server.py`) first. → **config/arm
   attribution** → `release-lead` (flags) or `models-lead` (arms, knobs).
5. **Is it a by-design refusal wearing a bad message?** A structured refusal
   (`unsupported_roster_slots`, `unknown_starter_availability`,
   `live_week_unsupported`) whose copy reads as a bug or a retry prompt. Evidence:
   the response body and size (a ~98-byte 200 from
   `/api/league/season-projections` is the `unavailable` reply; compare a working
   league the same day) and the oldest fielded client's catch-all. →
   **surface/copy defect** → area PM.
6. **Only now: is the output wrong against `models-lead`'s bars?** Name the bar
   (deck bars: D-055; League bars are still drafts — say so) and the served
   artifact. → **model defect** → a model-change packet
   (`.claude/skills/pm-technical/references/model-change-packet.md`) →
   `head-product` → `head-bizops` → `models-lead`. No build group until
   `models-lead` signs off.
7. **Otherwise** → **presentation or copy defect** → area PM.

Area PM = the lead whose surface showed it: trade cards → `trades-pm`; outlook,
window, Win Now → `league-pm`; values, tiers, ranking order → `rankings-pm`.

## The uncalibrated-disclosure check

Season projections, Win Now and championship odds shipped as an uncalibrated
beta whose UI receipts must retain the uncalibrated-beta disclosure
(`docs/business/ops/2026-09-05-win-now.md`, Evidence and limits). On every
complaint about those outputs, wherever the tree stops:

- Confirm the receipt said "Uncalibrated beta". Clients print it unless
  `meta.calibrated === true` (`sourceReceipt`, `mobile/src/utils/winNow.ts:17`;
  `web/js/win-now.js:29`). Missing or dropped → a separate **surface defect** to
  `league-pm`, filed even when the tree found something else.
- Present, and the complaint sits inside the disclosed limits (sampling error
  only; no model or projection uncertainty) → accepted follow-up validation
  work. It reaches `models-lead` as calibration evidence by the packet route,
  not as an eng fix.

## Routing

| Classification | Owner box | Route | Artifact |
|---|---|---|---|
| Write-path defect | area eng lead | area PM → `head-product` → `head-eng` | repro note + eng fix brief |
| Data/freshness defect | area eng lead (`models-eng` if inside an engine) | same | repro note + eng fix brief |
| Deploy/rollover | `release-lead` | same | repro note with the minute timeline |
| Config/arm attribution | `release-lead` (flags); `models-lead` (arms, knobs) | `head-eng`; or `head-product` → `head-bizops` | repro note naming the flag, knob or arm |
| Surface/copy, missing disclosure | area PM | stays in `/feedback` (polish or fast-track) | repro note → Phase 1 |
| Model defect | `models-lead` | packet → `head-product` → `head-bizops` | model-change packet + repro note |
| Calibration grading content (questions, tags, rubric) | `trades-pm` (decision P2) | stays in `/feedback` | repro note |
| Calibration arms, gates, bars | `models-lead` (decision P2) | packet route | model-change packet |

The eng fix brief seeds the mini-PRD: the failing step, its evidence, the
suspected file:line. Never route to a retired skill (`fin-budget`,
`fin-forecast`, `legal-privacy`, `ux-design`, `ux-research`).

## Repro note template

Draft in `feedback-workspace/<id>/`; on selection move it to the item folder as
`repro-note.md`. Ids only, no other PII.

```
# Repro note — #<id>
- Report: #<id> · user <user_id> · league <league_id> · <created_at UTC> · build <app_version>
- Pins: deployed sha <sha> · flags <key=value, …> · model_config <key=value, …>
- Served artifact: <impression_id | job_id | card_id> · arm <model_arm> · policy <policy_version>
- Prod rows: <query> | <source> | <time UTC>   (one line per pull)
- Tree: stopped at step <n> — <one-line evidence> · disclosure check: present | missing | n/a
- Classification: <…> · Owner: <box> · Next: <eng fix brief | packet path | Phase 1>
```

**Provenance:** promotes `lessons.md` 2026-09-02 [plan] (prod row first),
2026-09-06 [plan] (minute-level deploy correlation) and 2026-09-08 [triage]
(`league_preferences/set`: did the write land), so planners stop re-learning them.
