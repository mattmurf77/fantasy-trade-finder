# TC-CFG-001 — Feature flags + model_config live-tuning contract

| Field | Value |
|---|---|
| **Status** | PASS (11/11 checks) |
| **Date executed** | 2026-06-11 |
| **Layer** | config |
| **Component(s)** | `feature_flags.py` (FTF_FLAGS precedence), `/api/feature-flags[/reload]`, `/api/admin/config[/<key>]`, `set_config` + `reload_config` |
| **Requirement / doc ref** | config-reference.md; recon live-tuning item |
| **Engine path & flags** | v2/v3 default; CRON_SECRET set; FTF_FLAGS override |

### Objective
Verify the operator control surface: flag map + env precedence, cron-gated config
mutation with validation, and that a config write takes effect live (write →
persist → reload → readback) without a restart.

### Scope
- **In scope:** GET flags; FTF_FLAGS env precedence over features.json; PUT
  config auth (401)/unknown-key (404)/bad-value (400)/success (200); config
  readback after reload; reload endpoint auth.
- **Out of scope:** every individual model_config key's behavioral effect
  (TC-ENG-003 covers the gate knobs).

### Actual Result
**11/11 PASS.** Flag map returned (40 flags). FTF_FLAGS override won
(`trade.likes_you` forced false despite features.json=true). Config PUT:
no-auth→401, unknown→404, bad-value→400. Live tuning: PUT
`min_side_surplus_marginal=999999` → GET readback 999999 → revert → 60 (write
persists + reloads). reload endpoint: no-secret→401, with-secret→200. Evidence:
`qa/api/scratch_cfg/TC-CFG-001-run.json`.

### Outcome
**PASS** — the flag/config control surface is correct and live-reloadable. One
operational gotcha documented below.

### Findings requiring attention
| ID | Severity | Finding | Evidence | Suggested action |
|---|---|---|---|---|
| F-1 | **P3 (operational)** | **Surplus-floor config does not suppress consensus-basis decks.** Cranking `min_side_surplus_marginal` to 999999 left all 30 pinned cards in place — they were 100% `basis="consensus"`. Correct by design (unranked opponents have no divergence → no surplus to gate; the consensus path uses the *fairness* gate only), but an operator trying to reduce trade volume by raising surplus floors will see **no effect** in cold / low-ranking-coverage leagues (which are consensus-dominated). | basis breakdown `{consensus: 30}` under cranked floor | Document in config-reference.md: to throttle consensus-heavy leagues use `fairness_threshold` / `consensus_score_scale`, not the surplus floors. Optionally surface "active gate" per card in engine-metrics. |
| F-2 | **P3** | With `trade.marginal_value` on (prod default), the active surplus floor is `min_side_surplus_MARGINAL` (60), not `min_side_surplus` (150) — tuning the latter alone is a no-op. | TC-CFG-001 debug | One line in config-reference.md noting the marginal flag switches which floor is live. |

### Observations & feedback (no change required)
- **FTF_FLAGS precedence is the right operational lever** — an env override beats
  the committed features.json, so a prod flag can be flipped via Render env
  without a redeploy. Verified it wins.
- **The config write path is clean**: validates key existence (404) and value
  type (400) before mutating, then reloads both service modules (and
  trade_optimizer reads the same live `_cfg`), so v3 picks up changes too.
- F-1 is the more interesting half: it means the surplus floors and the fairness
  threshold govern *different populations* of the deck (divergence vs consensus).
  An operator needs both levers, and which one bites depends on league ranking
  coverage — worth making explicit in the tuning docs.
