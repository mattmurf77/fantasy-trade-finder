# Valuation & age audit — is Davante Adams over-valued, or is the ladder under-penalising age?

**Date:** 2026-08-18
**Scope:** read-only investigation. No engine code changed, no branch created. All prod queries were `SELECT` only, run through a `default_transaction_read_only=on` session.
**Triggered by:** operator report of repeated bad suggestions built around Davante Adams (`player_id` 2133, WR, LAR, age 33), with the hypothesis "Davante seemed to be overvalued".

---

## 1. Verdict

**Neither hypothesis survives contact with the data. The problem is a third thing.**

| Question asked | Answer | Confidence |
|---|---|---|
| Is Adams's **consensus seed** wrong? | **No.** FTF has him WR43 / value 1138.8. KeepTradeCut has him WR43, DynastyProcess WR43, FantasyCalc WR35. FTF is dead-on market. | **High** |
| Is the ladder **systematically under-penalising age**? | **No.** Median board/consensus value ratio is 1.00 for every age bucket, and the p90 for 30+ (1.36) is *lower* than for under-25s (1.55). 30+ players are 14.4% of suggested assets vs 13.5% of rostered players — a 1.07× ratio, i.e. no over-mining. | **High** |
| Then where does the error come from — seed or votes? | **Neither, exactly. It comes from the *tier-placement override* layer that sits between them,** which pins a player's Elo and makes the vote loop inert. | **High** |

**The one-sentence version:** Adams's seed is right, his age cohort is priced correctly, and the boards are not age-biased — but the operator's board has Adams **pinned** at Elo 1565.3 by a tier placement, his 17 subsequent down-votes moved that number by exactly **zero**, and because the confidence-shrinkage weight is driven by *vote count* rather than *vote direction*, those 17 down-votes **raised** Adams's effective trade value from 1138.8 to ≈1281.4 (**+12.5%**). The elicitation UI taught the engine the opposite of what the operator was telling it.

**Most important number in the report:** **67.8% of every ranking comparison ever recorded (2,721 of 4,013 swipes) is inert** — both players are override-pinned, so the Elo update is a no-op. The 3-player matchup loop is, for the three active users, mostly a placebo.

---

## 2. Where the numbers come from

Consensus seeds do **not** live in a `seed_elo` table. The pipeline is:

1. `backend/data_loader.py:_fetch_dynasty_process()` fetches `https://raw.githubusercontent.com/dynastyprocess/data/master/files/values-players.csv` live at boot (`VALUES_URL`, line 64).
2. `seed_elo_for_value()` (line 96) maps the DP 0–10000 value affinely onto `[SEED_VALUE_FLOOR=223.1, SEED_VALUE_CEIL=8467]`, then into Elo via `elo = 1500 + ln(v/1000)/0.005`.
3. `_apply_consensus_blend()` blends KeepTradeCut in (flag-controlled, #145/#148).
4. The daily result is snapshotted into **`player_value_history`** (`player_id, scoring_format, consensus_elo, consensus_value, snapshot_date`) — that table is the readable record of the seed.
5. Personal boards live in **`member_rankings`** (per `user_id` + `league_id` + `scoring_format`).
6. Manual placements live in **`users.tier_overrides`** — a per-format JSON blob of `{player_id: elo}`.

Snapshot coverage in prod: `1qb_ppr` 15,339 rows and `sf_tep` 15,574 rows, 2026-07-10 → 2026-08-18, **644 players per daily snapshot**.

---

## 3. Adams specifically

### 3.1 His seed is correct

```sql
SELECT rank() OVER (ORDER BY h.consensus_elo DESC) r, p.full_name, p.age,
       h.consensus_elo, h.consensus_value
FROM player_value_history h JOIN players p USING (player_id)
WHERE h.scoring_format='1qb_ppr' AND h.snapshot_date='2026-08-18' AND p.position='WR'
ORDER BY h.consensus_elo DESC;
```

| | FTF consensus | KeepTradeCut | DynastyProcess | FantasyCalc |
|---|---|---|---|---|
| Davante Adams, 1QB pos rank | **WR43** | WR43 | WR43 | WR35 |
| Value | 1138.8 (Elo 1526.0) | 4364 | 1087 | 2153 |

Raw values are not comparable across sources (different scales); ranks are. **Three of four sources put him at WR43.** He is also flat-to-slightly-*up* over 30 days on both KTC and FantasyCalc — he is not a falling knife the app failed to mark down. *(Confidence: high. KTC was read from the `playersArray` JSON the rankings page ships, since the page is JS-rendered and does not fetch cleanly; FantasyCalc via its public `values/current` API; both live 2026-08-18.)*

Seed stability over the audit window: Elo 1526.9 → 1520.0 → 1526.0 (2026-07-10 / 08-01 / 08-18). No drift, no spike. *(Confidence: high.)*

### 3.2 His per-board Elo — and the pin

```sql
SELECT user_id, league_id, scoring_format, elo, updated_at
FROM member_rankings WHERE player_id='2133' ORDER BY elo DESC;

SELECT sleeper_user_id, tier_overrides::json->'1qb_ppr'->>'2133' AS adams_override
FROM users WHERE tier_overrides IS NOT NULL AND tier_overrides <> '';
```

In the active league (`1312140920132497408`, 1qb_ppr), consensus = Elo 1526.0 / value 1138.8:

| User | Board Elo | Board value | Override? | vs consensus |
|---|---|---|---|---|
| 867830050538598400 (**operator**) | 1565.28 | 1386 | **yes — 1565.2777…** | 1.22× |
| 479505639769370624 | 1538.16 | 1210 | **yes — 1538.1578…** | 1.06× |
| 867831697150996480 | 1522.8 | 1121 | no | 0.98× |
| 313560442465169408 | 1341.33 | 452 | **yes — 1341.3333…** | 0.40× |
| 867953552205717504 / 460238423161040896 | 1278.7 | 331 | no (stale, Apr 2026) | 0.29× |

The repeating decimals are the signature of `RankingService.apply_tiers` (`backend/ranking_service.py:1364-1368`), which spreads a tier's members **linearly** across the tier's Elo band: `elo = hi − (hi−lo)·i/(n−1)`. For Adams: the `second` band ("worth a 2nd-round pick") is `[1400, 1575]`, and `1575 − 175·(1/18) = 1565.2777…` — he was placed **2nd of 19** in that tier. *(Confidence: high — the arithmetic reproduces exactly.)*

### 3.3 The vote history, and why it did nothing

```sql
SELECT user_id,
       sum((winner_player_id='2133')::int) wins,
       sum((loser_player_id ='2133')::int) losses
FROM swipe_decisions WHERE '2133' IN (winner_player_id, loser_player_id)
  AND scoring_format='1qb_ppr' GROUP BY 1;
```

Adams has **90 recorded comparisons** in `1qb_ppr` league-wide — he is *heavily* sampled, not thin. The operator's share:

- **18 comparisons on 2026-08-17 alone: 17 losses, 1 win.** He lost to Isiah Pacheco (consensus Elo 1255), Isaiah Likely (1524), Jayden Daniels (1681).
- Board Elo after that session: **1565.28 — byte-identical to the override, i.e. unchanged.**

`_compute_elo` (`ranking_service.py:1023-1050`) seeds an overridden player from `_elo_overrides` and then **skips the rating update for any pid with an override**. The operator's 17 down-votes were discarded by design. *(Confidence: high — code path is explicit and the data matches.)*

### 3.4 The inversion: down-voting him made him worth more

`trade_service._shrink_user_elo` (line 876) shrinks the personal Elo toward the seed with `w = n/(n + shrink_pseudocount)`, `shrink_pseudocount = 4` (confirmed in prod `model_config`). Critically, `n` comes from `RankingService.comparison_counts` = **the number of unique opponents faced**, i.e. *how much you voted*, with **no reference to which way you voted**.

For the operator and Adams, `n` = 6 unique opponents (0 before 2026-08-17):

| | personal Elo | n | w | shrunk Elo | **effective trade value** |
|---|---|---|---|---|---|
| Before the down-vote session | 1565.28 (pinned) | 0 | 0.00 | 1526.0 | **1138.8** |
| After 17 down-votes + 1 up-vote | 1565.28 (pinned) | 6 | 0.60 | 1549.6 | **1281.4 (+12.5%)** |

Because the Elo is pinned but the vote *count* still rises, every additional comparison drags the effective value **further toward the pinned override** — and the override is above consensus. **Voting a pinned player down increases his value in the trade engine, monotonically.** *(Confidence: high on the mechanism, which is plain in the code; medium-high on the exact +12.5%, since I reconstructed the shrinkage arithmetic rather than instrumenting a live deck run.)*

That is a complete, sufficient explanation of the reported symptom: the operator saw "receive Davante Adams" cards **14 times in 7 days**, tried to correct the app in the ranking UI, and each correction made the next deck more Adams-heavy.

---

## 4. Age treatment, systematically — the negative result

### 4.1 The consensus seed does price age (adequately)

Max WR consensus value by age, 2026-08-18 snapshot (medians are useless — 331 of 644 players sit on the value floor of ~224, see §5.3):

| Age | 26 | 27 | 28 | 29 | 30 | 31 | 32 | **33** |
|---|---|---|---|---|---|---|---|---|
| Max WR value | 8470 | 7290 | 1568 | 4179 | 1492 | 376 | 936 | **1139 (Adams)** |

There is a real cliff. Adams at 1139 is 13.4% of WR1. Externally, KTC puts a 33-year-old startable WR at ~40–45% of WR1 and FantasyCalc at ~20–22%; the *rank* agrees across all four sources even though the scales don't. The apparent age-33 bump over 31/32 is survivorship (Adams and Evans are the only two productive 33-year-old WRs left), not a curve inflection — confirmed against KTC and FantasyCalc, which show the same shape. *(Confidence: high on rank agreement, medium on the value-scale comparison, which is why I lean on ranks.)*

**Caveat worth recording:** DynastyProcess's published formula is `value = 10500·e^(−0.0235·FantasyPros_ECR)`. Age is a *descriptive column* in their CSV, **not an input**. Age reaches our seed only via whatever the FantasyPros expert panel already baked into ECR. That works today, but the app is treating a non-age-aware source as an age-aware one, and nothing would alert us if ECR started lagging on age. *(Confidence: high — DP's own methodology page.)*

### 4.2 The boards do not inflate aging players

```sql
-- median board/consensus VALUE ratio by age, placed players only (elo > 1200),
-- the three active boards in league 1312140920132497408
WITH j AS (
  SELECT p.age, exp(0.005*(m.elo - h.consensus_elo)) ratio
  FROM member_rankings m JOIN players p USING (player_id)
  JOIN player_value_history h ON h.player_id = m.player_id
       AND h.scoring_format='1qb_ppr' AND h.snapshot_date='2026-08-18'
  WHERE m.scoring_format='1qb_ppr' AND m.league_id='1312140920132497408'
    AND m.user_id IN ('867830050538598400','313560442465169408','479505639769370624')
    AND m.elo > 1200 AND p.age IS NOT NULL)
SELECT ..., percentile_cont(0.5) WITHIN GROUP (ORDER BY ratio) FROM j GROUP BY bucket;
```

| Age bucket | n | median ratio | mean | p90 |
|---|---|---|---|---|
| <25 | 470 | 1.00 | 1.12 | **1.55** |
| 25–27 | 476 | 1.00 | 1.07 | 1.47 |
| 28–29 | 152 | 1.00 | 1.04 | 1.40 |
| **30+** | 204 | 1.00 | 1.08 | **1.36** |

Flat. If anything the tail inflation is *worse* for young players. **The ladder is not under-penalising age.** *(Confidence: high.)*

### 4.3 The one real age gap: the age curve exists and is switched off

`backend/trade_service.py:1338-1400` defines `_AGE_NOW_CURVE` and `_AGE_FUTURE_CURVE` — e.g. WR future value decays `1.10 − 0.09·(age−24)` down to a 0.50 floor, which would put a 33-year-old WR at 0.29 of a 24-year-old's future multiplier. They are applied only inside `if FLAGS.trade_outlook_blend:` (line 2929).

Live prod check (`GET https://fantasy-trade-finder.onrender.com/api/feature-flags`): **`"trade.outlook_blend": false`.**

So the engine applies **no explicit age adjustment to any value, anywhere**. Age enters only through the seed. Given §4.2 this is not currently causing harm, but it means the app has no independent age opinion at all — it is fully dependent on FantasyPros ECR staying age-sane. *(Confidence: high — flag read live from prod.)*

---

## 5. Seed vs votes — the decomposition, and what it actually found

### 5.1 The vote loop is 68% inert

```sql
-- swipes where BOTH sides are override-pinned → Elo update is a no-op
WITH ov AS (SELECT u.sleeper_user_id uid, f.fmt, k.key pid
            FROM users u CROSS JOIN LATERAL (SELECT unnest(ARRAY['1qb_ppr','sf_tep']) fmt) f
            CROSS JOIN LATERAL json_object_keys(coalesce(u.tier_overrides::json->f.fmt,'{}'::json)) k(key))
SELECT s.user_id, s.scoring_format, count(*) swipes,
       sum((w.pid IS NOT NULL AND l.pid IS NOT NULL)::int) both_pinned
FROM swipe_decisions s
LEFT JOIN ov w ON w.uid=s.user_id AND w.fmt=s.scoring_format AND w.pid=s.winner_player_id
LEFT JOIN ov l ON l.uid=s.user_id AND l.fmt=s.scoring_format AND l.pid=s.loser_player_id
GROUP BY 1,2;
```

| User | Format | Swipes | Both pinned (dead) | % dead |
|---|---|---|---|---|
| 313560442465169408 | 1qb_ppr | 1,428 | 1,337 | **93.6%** |
| 313560442465169408 | sf_tep | 282 | 275 | **97.5%** |
| 867830050538598400 | sf_tep | 296 | 266 | **89.9%** |
| 479505639769370624 | 1qb_ppr | 701 | 465 | 66.3% |
| 867830050538598400 (operator) | 1qb_ppr | 903 | 378 | 41.9% |
| **All users, both formats** | | **4,013** | **2,721** | **67.8%** |

At least one side is pinned in 93–99% of the heavy users' swipes.

**How boards get this pinned:** `POST` reorder (`backend/server.py:8021`) calls `apply_reorder`, which writes an Elo override for **every** id in `ordered_ids`, then persists the whole dict via `save_tier_overrides` (line 8060). The comment at line 8047 records that **Quick Rank routes its per-tier saves through this endpoint** — so one onboarding pass pins hundreds of players at once. Live override counts in `1qb_ppr`: 737, 644, 547, 42, 16. *(Confidence: high.)*

### 5.2 So: boards ≈ seeds, except where a human touched them

The honest decomposition is not "seed vs votes" — it is **seed vs manual placement**, with votes as a near-nullity:

| Basis of a board entry | Share of the operator's 644-row board | What drives the trade value |
|---|---|---|
| Never compared (`n = 0` → shrink weight 0) | **529 (82.1%)** | 100% consensus seed |
| `n ≥ 4` (shrink weight ≥ 0.5) | 53 (8.2%) | mostly personal |
| Override-pinned (swipe-immune) | **502 (78.0%)** | the tier placement, weighted by vote *count* |

Across the three active boards, 56.7–82.1% of entries carry zero personal signal. **The engine is running on the consensus seed for four out of five players, and on a pinned tier placement — never on votes — for the rest.** *(Confidence: high.)*

### 5.3 The tier bands distort the bottom of the board

`backend/tier_config.json` bands are identical for every position and format; the lowest is `waivers = [1150, 1215]` and `fourth = [1220, 1275]`. The consensus value floor is Elo ≈1200.7 → value 224, and **331 of 644 players (51.4%) sit on it** — DP gives them value 0, so the seed cannot distinguish half the universe.

Any player a user drops into a tier therefore lands *above* the consensus floor by construction. On the operator's board, the 76 placed players whose consensus is at the floor average **1.69× consensus**:

| Player | Age | Board value | Consensus value | Ratio |
|---|---|---|---|---|
| KaVontae Turpin | 30 | 552 | 225 | **2.45×** |
| Mack Hollins | 32 | 546 | 225 | **2.42×** |
| Van Jefferson | 30 | 507 | 224 | 2.26× |
| Allen Lazard | 30 | 417 | 224 | 1.86× |

This is not an age effect (young floor players inflate the same way — see §4.2's p90 column) but it is a real source of junk filler in packages. *(Confidence: high on the numbers; medium on the claim that it materially degrades decks, which I did not measure directly.)*

### 5.4 Cross-board divergence is enormous — and the engine mines it deliberately

`features_json` on deck impressions carries `"basis": "divergence"`. The largest value gaps between two boards in the operator's league, 1qb_ppr:

| Player | Age | Low board | High board | Ratio | Consensus |
|---|---|---|---|---|---|
| Amon-Ra St. Brown | 26 | 381 | 6,760 | **17.8×** | 7,725 |
| KC Concepcion | 21 | 629 | 4,158 | 6.6× | 1,907 |
| Cam Skattebo | 24 | 454 | 3,710 | 8.2× | 2,393 |
| Jonathan Taylor | 27 | 1,492 | 5,565 | 3.7× | 5,403 |
| *Davante Adams* | *33* | *452* | *1,386* | *3.1×* | *1,139* |

**Adams is not even in the top 20 divergences.** The St. Brown case is an explicit override at Elo 1306.8 — the consensus WR3, pinned at "worth a 3rd-round pick", 20× below market, and immune to correction by voting. *(Confidence: high.)*

---

## 6. Blast radius — the age hypothesis, measured

```sql
-- assets appearing in deck cards, last 7 days, joined to players.age
WITH imp AS (SELECT impression_id, assets_json FROM deck_impressions
             WHERE served_at >= '2026-08-11' AND assets_json IS NOT NULL),
a AS (SELECT x.pid FROM imp i, LATERAL (
        SELECT json_array_elements_text(i.assets_json::json->'give') pid
        UNION ALL SELECT json_array_elements_text(i.assets_json::json->'receive')) x)
SELECT bucket, count(*), 100.0*count(*)/sum(count(*)) OVER () FROM a JOIN players USING (player_id) ...;
```

| Age bucket | Share of suggested assets (7d, n=3,498) | Share of rostered players (n=1,837) | Over-representation |
|---|---|---|---|
| <28 | 81.7% | 76.2% | 1.07× |
| 28–29 | 3.9% | 10.3% | 0.38× |
| **30+** | **14.4%** | **13.5%** | **1.07×** |

Centerpieces alone: 30+ = 12.0%, *below* their roster share.

**Aging players are not over-mined. The systematic-age hypothesis is dead.** *(Confidence: high.)*

Adams individually *is* over-represented, but as a single mis-pinned player, not as a cohort:

| Metric (7d) | Value |
|---|---|
| Distinct players appearing in deck assets | 188 |
| Median appearances per player | 8 |
| **Davante Adams appearances** | **90 (rank 8 of 188, 11× median)** |
| — as "give" for user 313560442465169408 | 73 of that user's 368 impressions (**19.8%**) |
| — as "receive" for the operator | 14 |

One player, valued 3.1× apart on two boards in the same league, is driving a fifth of one member's entire deck. *(Confidence: high.)*

---

## 7. What I could not determine

| Open item | Why |
|---|---|
| Whether the tier placements were deliberate or a Quick Rank artifact | `users.tier_overrides` is a wholesale-overwritten blob with **no history** (noted in `backend/database.py:3915`). I can see the final Elo and reconstruct which slot of which tier it came from, but not whether the user consciously put Amon-Ra St. Brown in the "worth a 3rd" tier or whether a bulk save did it. **This is the single most valuable thing to instrument next.** |
| Exact effective (shrunk) value at deck-generation time | `deck_impressions.features_json` reports `give_value`/`receive_value` from `_consensus_packages` (`trade_service.py:3652`) — **consensus by design**, so the card's displayed numbers match the manual calculator. The personal shrunk values that actually drove selection are never persisted. My §3.4 figures are reconstructed from code + stored inputs, not observed. |
| Whether the card's consensus display vs personal-divergence selection confuses users | Structural observation only. A card can display a perfectly balanced consensus trade while having been chosen for a private divergence the user cannot see. Not measured. |
| Behaviour of users beyond the 3 active boards | Only 6 users have meaningful swipe history; 18 boards total, several stale since April. Everything here is a small-n finding on the operator's league. |
| Whether `FTF_FLAGS` env overrides prod `features.json` | I read the live `/api/feature-flags` endpoint, which reflects the resolved state, so `trade.outlook_blend=false` is confirmed *as served*. I did not inspect Render's env directly. |

---

## 8. Recommended fixes, cheapest high-confidence first

### F1 — Stop letting votes on a pinned player raise that player's weight *(cheapest, highest confidence)*
`_shrink_user_elo` weights by vote **count**; `_compute_elo` ignores votes on overridden players. The combination is strictly perverse: every vote you cast on a pinned player pulls the value toward the pin, regardless of direction. **Fix:** in `RankingService.comparison_counts`, exclude comparisons where the player is override-pinned (or make the trade layer read a confidence map that does). One-line-ish change, no schema, no migration, immediately stops the Adams inversion.
*Blast radius: shrink weights fall for pinned players → their values move toward consensus. Expect deck churn on the next generation. Confidence this is a genuine bug: **high**.*

### F2 — Make a vote on a pinned player *unpin* it
Today a tier placement is permanent until re-tiered. The user's most recent expression of preference (a swipe) should beat their older one (a tier drag). **Fix:** in `_compute_elo`, drop the override for any pid that has swipes recorded *after* the override was written — which requires storing a timestamp alongside the override value. Cheap-ish, but needs an `tier_overrides` shape change (add `{elo, at}`), so it is F2 not F1.
*Confidence this is the right product behaviour: **medium-high** — it is a design call, and the current pinning was itself a deliberate fix (see the `_compute_elo` comment about tier saves becoming "decorative"). Worth an operator decision, not an agent decision.*

### F3 — Surface the pin in the ranking UI
The operator voted Adams down 17 times against a control that could not move. Whatever F1/F2 land on, a pinned player should visibly say so ("you placed him in *worth a 2nd*, tap to unpin") rather than silently absorbing votes. **Fix:** mobile/web ranking screens; `board_override_count` / the override map is already available server-side.
*Confidence this prevents recurrence: **high**. Cost: UI work, needs a Maestro delta per the feature gates.*

### F4 — Replace linear intra-tier spread with a value-preserving permutation
`apply_tiers` (line 1364) spreads a tier linearly across its Elo band. `apply_reorder` was already fixed for exactly this reason (the "44 elite QBs" bug, FB #60/#69) by permuting existing Elos instead of interpolating; `apply_value_map` does the same against the seed distribution. `apply_tiers` never got the same treatment, which is why 76 floor-level players on the operator's board average 1.69× consensus.
*Confidence the mechanism is real: **high**. Confidence it materially improves decks: **medium** — worth measuring first.*

### F5 — Add a divergence sanity gate to the deck engine
No matter how the board got there, a card built on a **3×+ gap between two boards on the same player** should be suppressed or labelled. Amon-Ra St. Brown at 17.8× is not a trade opportunity, it is a data error the engine is monetising. A simple cap (skip candidate assets where `max(board_value)/min(board_value) > k`, or where the user's board is >2× off consensus and `n < 4`) would kill the whole class of symptom the operator reported.
*Confidence: **medium-high**. Needs a threshold chosen empirically, and it is a scoring change, so full feature gates apply.*

### F6 — Turn on `trade.outlook_blend`, or delete the curves
The app's only explicit age model has been dark since it was written. Either enable it (after backtesting — §4.2 says the current values are *not* age-broken, so this could easily make things worse) or remove the dead code so nobody assumes an age curve is running.
*Confidence this is urgent: **low**. It is hygiene, not a fix. Listed last on purpose.*

### Not recommended
- **Do not adjust Adams's seed, or add an age penalty on top of DP.** FTF agrees with KTC, DP, and (within a rank tier) FantasyCalc. Marking him down would move the app *away* from market.
- **Do not treat this as a WR/age problem.** The measured over-representation of 30+ players in suggestions is 1.07×.

---

## 9. Appendix — reproducing this

Prod access: `DATABASE_URL_PROD` from the gitignored `secrets.local.env`, opened with `PGOPTIONS="-c default_transaction_read_only=on"`. Every statement in this document is a `SELECT`.

Key tables: `player_value_history` (consensus seed snapshots), `member_rankings` (per-board Elo), `users.tier_overrides` (manual pins), `swipe_decisions` (the 3-player matchup votes), `deck_impressions` (`assets_json`, `features_json`).

Key code: `backend/data_loader.py` §seed pipeline · `backend/ranking_service.py:998` `_compute_elo`, `:1306` `apply_tiers`, `:1541` `apply_reorder`, `:756` `comparison_counts` · `backend/trade_service.py:876` `_shrink_user_elo`, `:1338` age curves, `:2921` shrinkage call site · `backend/tier_config.json` · `backend/server.py:8021` reorder endpoint.
