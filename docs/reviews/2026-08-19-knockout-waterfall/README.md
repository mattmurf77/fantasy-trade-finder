# Knockout waterfall — data files

> Companion data for [`../2026-08-19-knockout-waterfall.md`](../2026-08-19-knockout-waterfall.md).
> Point-in-time replay output, not reference. Regenerate rather than trust if the engine moved.

Every file is a **replay** of league `1312140920132497408` (6 boarded members) through the real
`TradeService._generate_trades_impl` / `trade_optimizer.generate_pair_trades_v3` /
`trade_gen_v2.generate_league_suggestions`, against prod data read `SET TRANSACTION READ ONLY`.
Nothing here is a production serving count.

| File | Rows | What it is |
|---|---|---|
| `waterfall.html` | — | Self-contained view of the waterfall. No external assets. Open it in a browser. |
| `knockout-all-candidates.csv.gz` | 3,073,019 | **Every candidate**, all three arms, every shape. Complete — no sampling. Assets are ids; join to `assets.csv`. |
| `knockout-notable.csv.gz` | see memo | The subset the memo argues from: every candidate killed by **exactly one** rule, plus every candidate that survived every rule. Carries readable names. |
| `knockout-survivors.csv` | see memo | Uncompressed, directly openable: only the candidates that cleared every rule. |
| `assets.csv` | 693 | `asset_id → name / position / team / kind`. Draft picks carry their D-090 real-slot label where the league's draft order resolves (e.g. `2026 1.08`), the generic ordinal otherwise. |
| `summary.json` | — | Machine-readable counters: per-rule first-kill / would-also-fail / unique-kill, per shape, per user, plus the selection ladder and the live knob values used. |

## Column dictionary (both sheets)

| Column | Meaning |
|---|---|
| `arm` | `B` = live engine, `C` = `trade_gen_v2` |
| `path` | `divergence` (v3 optimizer), `consensus` (`_generate_consensus_for_pair`), `gen_v2` |
| `user` / `partner` | Sleeper usernames. Direction matters: the deck is generated *for* `user`. |
| `shape` | `GxR` — assets given × assets received |
| `give_ids` / `receive_ids` | `|`-separated asset ids (join `assets.csv`) |
| `give` / `receive` | Readable names — **notable/survivor sheets only** |
| `basis` | `divergence` or `consensus` |
| `admit_metric` | The ranking-diff value that admitted the candidate. Divergence: the tightest per-asset prune margin (`_vo·scale − _uv`, `trade_optimizer.py:392-418`). Consensus: `rv − gv`. Arm C: the centerpiece's `uval − oval`. |
| `cons_give` / `cons_recv` | Consensus package values for the two sides |
| `gain_user` / `gain_partner` | Each side's own-board surplus (divergence / arm C) or the consensus delta (consensus path) |
| `killed` | 1 if any rule rejected it |
| `first_rule` | The rule that **actually** rejected it, in real execution order — the waterfall column |
| `all_failing_rules` | `;`-separated, every rule that would reject it when asked independently — the co-kill column |
| `n_failing` | Count of the above |
| `unique_kill_rule` | Set only when `n_failing == 1`: this rule is the **only** thing stopping the trade |

## How the verdicts were obtained

Each gate was monkeypatched, in every namespace that binds it by value, with a wrapper that calls
the original for the true verdict, records it, and returns a forced PASS — so the enumeration runs
the whole ladder for every candidate and each rule is scored on candidates an earlier rule would
have killed. The last gate in each ladder is forced to KILL instead, so no card is built and memory
stays bounded. Knob-driven inline gates (which are `if` statements, not calls) were neutralised via
`_cfg` and recomputed in-harness from values captured out of the real helpers.

The whole thing is validated by a second, uninstrumented pass at real config: the set of candidates
this method says survives every rule is **identical** to the set the real engine scores
(arm B divergence), and the harness's first-kill counts are **identical** to `trade_gen_v2`'s own
`GenerationReport.kill_counts()` (arm C). See the memo's *Proof the counters are real* section.
