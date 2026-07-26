# TikTok's Models Layer — Consolidated Research

*Consolidated from two independent researchers (T2A: architecture lens; T2B: practitioner lens). Raw
reports in gitignored `feedback-workspace/tiktok-discovery/T2{A,B}-models.md`. Both cite primary
sources; convergent findings are marked ◆ (high confidence). Inference is labeled. 2026-07-26.*

## The one-paragraph takeaway

◆ TikTok's strategic core is **not model sophistication — it is feedback-loop latency plus logging
discipline**. Every micro-interaction (watch time above all) is joined to its impression in a
streaming pipeline and folded into servable parameters **within minutes** (Monolith, RecSys 2022);
ByteDance published proof that shrinking the sync interval monotonically buys accuracy (AUC 79.66 @
5hr → 79.80 @ 30min; online beat batch 14–18% every day for a week) and deliberately trades away
durability to keep freshness (daily snapshots; "reliability could be traded off for real-time
learning"). Serving is a two-stage funnel — candidate retrieval → multi-task fine ranking scored by
the leaked value function **score ≈ Σ P(action)·V(action)** → a rules-based re-rank layer (diversity
swaps, same-category same-day cooldowns, fatigue, exploration quota). Watch time alone locks onto a
user in ~40min–2hrs (WSJ bots). Almost none of the deep-learning stack transfers to FTF's scale;
almost all of the **loop discipline** does.

## Mechanism catalog (convergent findings)

### 1. Monolith — the real-time substrate ◆ [primary: arXiv 2209.07663]
- **Collisionless embeddings** (Cuckoo-hashed; collisions measurably depress AUC forever). Memory via
  admission thresholds (an ID must appear k times before getting state) + inactivity TTL expiry.
- **Online joiner:** features are logged **as served**, keyed by a unique request id; actions join to
  impressions later (in-memory cache + on-disk KV for late labels). *Never recompute features at
  label time — that's how training/serving skew is born.*
- **Minute-level sparse sync / daily dense sync**; serving runs stale-dense + fresh-sparse with no
  measurable loss. **Daily snapshots suffice** — losing a day of updates for 0.1% of users is invisible.
- **Log-odds correction** at serving when training on negative-downsampled streams, so predicted
  probabilities stay calibrated (`logit_cal = logit_raw + ln(r)`), a prerequisite for value-weighted
  scoring to mean anything.
- **Design permission slips for a small team (T2B):** ship learning fast rather than perfectly;
  partial/inconsistent updates are fine; the event log — not the model — is the system of record.

### 2. The serving funnel ◆
Retrieval (Deep Retrieval paper + CF/tag/follow channels, thousands→hundreds) → multi-task fine
ranking (MMoE-pattern heads: P(like), P(comment), E(playtime), P(play)…) → **value model** —
the leaked Algo 101 shape (NYT-authenticated):

```
score = P_like·V_like + P_comment·V_comment + E_playtime·V_playtime + P_play·V_play
```

Learning lives in the P's; **strategy lives in the hand-set V's** (tuned toward retention + time
spent + DAU). Then a **policy/re-rank layer** applies legible rules: author boost for prior
engagement, same-category same-day suppression, quality demotions (like-begging), **slate-level
diversity swaps** (replace a near-duplicate with a lower-scored dissimilar item), ad slots, and the
admitted manual "heating" lever. Rules live outside the model so strategy changes need no retraining.

### 3. Signals & weighting ◆
- Implicit dominates explicit: **watch time + rewatch alone fully personalize** (WSJ 100-bot study);
  completion of a long video is officially weighted above weak signals like same-country.
- Fast skip (<~1s) is a clean implicit negative; explicit "Not interested" is two-track — a hard-ish
  suppression AND a training label. (Mozilla's YouTube study: explicit negatives wired only as
  gradient nudges prevent just ~11% of similar recs — they must drive *visible suppression*.)
- **Dwell/watch-time debiasing:** long items get more watch time structurally — Kuaishou's D2Q (KDD
  2022) fixes it with quantile regression within duration bins ("watched more than typical *for this
  length*"). FTF transposition: normalize card dwell by trade-complexity bin.
- **Position bias:** YouTube's shallow-tower pattern (position as a training feature, dropped at
  serving) or inverse-propensity weighting; a small randomization slot in serving estimates
  examination probabilities. In a one-item deck, *session-position/fatigue* bias replaces rank bias.

### 4. Exploration / new-item cold start ◆
Staged impression pools: a new item gets a small test batch (~200–300 impressions lore), graduating
to larger pools only by clearing early completion/engagement bars — functionally a
successive-elimination bandit; follower count explicitly not a factor. User-side: deliberate
out-of-interest injections + diversity interleaving (official) prevent feedback-loop collapse (the
WSJ rabbit-hole failure mode). Exploration traffic doubles as the randomized logging that keeps
off-policy learning honest.

### 5. Bandits done well (directly upgrades FTF's Thompson deck) [T2B; Deezer arXiv 2009.06546]
- **Pessimistic priors at the observed base rate** — Beta(1,1) floods decks with junk exploration;
  Beta(1, ~1/base_rate) won Deezer's production A/B.
- **Posterior decay** (γ ≈ 0.99–0.999/day) so arms track drift instead of ossifying.
- **Semi-personalized arms** (user-cluster × attribute, not per-user-per-item) — pooling beats full
  personalization at small data; warm-start child arms from parent levels (DoorDash).
- **Cascade updates:** in a deck, items after the user's last engagement are **unseen, not
  negatives** — the single biggest correctness bug in naive deck bandits.
- Thompson tolerates delayed/batched posterior updates well (cron is fine).

### 6. Fatigue & negative feedback ◆
- **Impression discounting as a score multiplier** (LinkedIn): `score × (w₁·g(impCount) +
  w₂·g(lastSeen))`, exponential g — items decay out gracefully and can return after cooldown.
- Fatigue accrues at item AND category/author level (WWW 2016).
- Graduated response: one skip = mild; repeated in-session = strong; explicit reject = hard ~30-day
  suppression of the item/near-duplicates + a days-level attribute penalty, then one low-exposure
  retest.

### 7. Session-level adaptation ("responds in 3 swipes") ◆
Not mid-session retraining — it's minute-fresh sparse state + **re-ranking the candidate pool against
a short-term interest vector that updates instantly**. Small-system version: a last-k (≈5–20)
boost vector over liked/passed attributes, recency-weighted, `score × (1 + η·cos(attrs, boost))`,
recomputed per request; reset/decay hard between sessions; a long-τ profile absorbs what persists.
Sophistication beyond last-k (GRUs/transformers) adds little.

### 8. Interest representation, right-sized
Long/short split without embeddings: per-user **decayed attribute-preference vectors** over
engineered attributes (position, age band, value tier, archetype, trade shape, pick involvement) —
`w[a] ← w[a]·exp(−Δt/τ) + r(action)` with τ≈21d (short) and τ≈180d (long); rewards mirroring the
existing Elo K ratios (like +1, accept +4, proposal-sent +6, pass −0.5, decline −2). Lazily created,
TTL'd — Monolith's admission/expiry in SQL rows. This coexists with player-level Elo: **Elo learns
player values; the vector learns trade-shape taste.**

## The staged minimal blueprint (T2B, endorsed by T2A's right-sizing)

Each stage shippable alone, in order, Flask + SQL, one person:

1. **Log like Monolith joins** — `impressions(impression_id, user, trade, position, deck, features_json,
   propensity, shown_at)` + `outcomes(impression_id, action, dwell_ms, acted_at)`. Features frozen at
   serve time; every card gets a row; position + propensity always logged (Thompson already provides
   the stochastic policy — record it). *Prerequisite for everything; FTF's thinnest spot today.*
2. **Per-user attribute-preference vectors** updated synchronously on every outcome (the minute-level
   sync miniaturized), short+long τ pair, lazy rows + GC.
3. **Multiplicative re-rank of the generated pool** — keep v2/v3 generation as retrieval; final =
   base_score × (1+η·prefMatch) × (1+η_s·sessionBoost) × fatigue × freshness; then slate rules (hard
   30-day suppression of declined near-duplicates, max 2 trades per centerpiece per deck,
   same-partner cooldown). Multiplicative keeps the surplus gate authoritative — bad trades can't be
   boosted in, only good trades reordered.
4. **Exploration quota + bandit fixes** — pessimistic priors, posterior decay, archetype-level arms,
   cascade updates; 1 slot in ~5–10 decks (or 1 fully-shuffled deck in 20) as the
   randomization/exploration slot feeding propensity logs.
5. **Offline eval before online A/B** — replay/IPS on the propensity logs; calibration checks;
   time-ordered eval on future days; within-user interleaving over parallel-cohort A/B at small
   traffic. Only replay winners graduate to live tests.

**Explicitly not worth building at FTF scale ◆:** learned embeddings/two-tower/ANN retrieval (the
trade *generator* is the retrieval stage), neural rankers (LR/GBT + vectors + Elo dominate), streaming
infra (synchronous SQL writes are minute-level sync at this QPS), parameter servers/snapshots (SQL is
the snapshot), MMoE (separate calibrated heads suffice).

## Key sources
Monolith arXiv 2209.07663 · Deep Retrieval arXiv 2007.07203 · NYT "How TikTok Reads Your Mind"
(Algo 101; deeplearning.ai + Gizmodo/TechTimes summaries) · WSJ bot investigation (Jul 2021) · TikTok
newsroom "How TikTok recommends videos #ForYou" + transparency pages · D2Q arXiv 2206.06003 · YouTube
MMoE/shallow-tower RecSys 2019 · Deezer carousel bandits arXiv 2009.06546 · LinkedIn impression
discounting · WWW 2016 user fatigue · Mozilla YouTube negative-feedback study · SIM arXiv 2006.05639 ·
Eugene Yan bandits survey · AiEdge TikTok reconstruction.
