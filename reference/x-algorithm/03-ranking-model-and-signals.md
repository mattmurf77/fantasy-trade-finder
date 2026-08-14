# X Algorithm — Phoenix Ranking Model, User Signals & Diversity Re-ranking

Phoenix is the transformer that scores every post in X's For You feed. Its only real input about the viewer is a sequence of their last ~1,000 engagement events (post, author, which of ~60 actions they took, dwell seconds, timestamp, surface) plus a handful of coarse profile features; there is no hand-built feature vector of aggregate stats. The model reads that history and, for each candidate post (identified by hashed post/author IDs plus content-derived "semantic ID" codes), emits an independent probability for each of ~30 actions the viewer might take — favorite, reply, repost, several click types, video/dwell attention signals, follow, and five explicit negatives — plus a dwell-time regression. A hand-tuned weighted sum of those per-action probabilities (reply ×5.0, report ×−234, etc.) produces one score, and a separate DPP re-ranking service (vm-ranker) then trades a little score for diversity by greedily selecting posts whose content embeddings aren't too similar to already-selected neighbors. Training needs no human labels: every served impression becomes a training example whose multi-hot label is simply what the user actually did with it.

All paths below are relative to the 2026-08-13 open-source drop (repo root); `phoenix/` is the model workspace.

---

## 1. Model architecture: transformer with candidate isolation

**Two models, one trunk** (`phoenix/README.md:35-131`): a two-tower **retrieval** model (user embedding · precomputed post index, dot-product top-K) and the **ranking** transformer. The ranking model is the focus here; both share the same transformer trunk and input machinery and differ only in heads (`phoenix/README.md:248-255`).

**Input sequence layout** (`phoenix/README.md:134-189`, built in `phoenix/xrex/models/recsys_model.py:2071+` / `block_*_reduce` at 813-1105):

- **User prefix tokens `[B, ≤2]`** — one token from the hashed user ID (+ hashed IP address embedding summed in, `recsys_model.py:844-847`), and one "user features" token carrying profile features: country, language, location (lat/long Fourier features), gender, age bracket, installed apps (`phoenix/xrex/configs/xrecsys.py:269-285`, `phoenix/xrex/data/recsys/feature_config.py:72-100`).
- **History tokens `[B, S=1022, D]`** — per past engagement event: hashed post ID embeddings + hashed author ID embeddings + **action-type embeddings** (multi-hot of what the user did) + semantic-ID embedding + product-surface embedding, concatenated then projected to model width (`recsys_model.py:936-1015`, `proj_mat_3` at 980). **Dwell time is added as an input**: the continuous dwell seconds are normalized and passed through a small MLP to an embedding summed onto the event token (`recsys_model.py:994-1011`).
- **Candidate tokens `[B, C=64, D]`** — hashed post + author IDs + semantic IDs + product surface + optional multimodal post embedding (1024-d, projected in at `recsys_model.py:1070-1083`), same projection pattern (`proj_mat_2`, `recsys_model.py:1018-1105`). Candidates carry **no action embeddings** (that's what's being predicted).
- **Context features** on both history and candidates: timezone, local hour-of-day, local day-of-week, post-age bucket (60-min granularity, max 4800 min), author-NSFW bit, and optional engagement-count buckets (fav/reply/repost/quote/view) (`phoenix/xrex/configs/xrecsys.py:587-665`, `phoenix/xrex/data/recsys/feature_config.py:8-34`).

**Candidate isolation.** The attention mask lets user+history tokens attend bidirectionally among themselves; candidates attend to user+history **and only to themselves** (diagonal). Implemented at `phoenix/xrex/pallas/ranker_attention_utils.py:54-56`:

```python
history_mask = kv_is_history & (q_is_history | q_is_candidate)
candidate_self_mask = q_is_candidate & kv_is_candidate & (q_pos == kv_pos)
```

so a candidate's score is independent of which other candidates share the batch ("batch-invariant serving", `phoenix/README.md:275-279`). ASCII mask diagram at `phoenix/README.md:196-233`.

**Hash-based embeddings.** No ID dictionary service: each entity (user, post, author, IP) is looked up via **2 independent hash functions** into fixed-size tables and the resulting rows are concatenated/projected (`phoenix/README.md:239-246`; hash scales/moduli at `phoenix/xrex/configs/xrecsys.py:161-172`). Any ID — including a brand-new post — is representable instantly, at the cost of collisions the multiple hashes tolerate. Posts additionally carry **semantic IDs**: 6-level × 256-code residual quantization of the post's multimodal embedding, embedded per level and summed (`recsys_model.py:854-933`), giving content-aware generalization to never-seen posts.

**Sizes** (`phoenix/README.md:395-416` table, config in `phoenix/xrex/configs/xrecsys.py:239-295, 360-373`):

| Parameter | Ranking prod | Ranking nano | Retrieval prod |
|---|---|---|---|
| Model width (emb_size) | 2560 | 512 | 1024 |
| Layers | 8 | 4 | 8 |
| Q / KV heads (GQA), key size | 20 / 4, 128 | 4 / 2, 128 | 16 / 4, 128 |
| FFN widening | 2× | 2× | 2× |
| History len / candidates | 1022 / 64 | 1022 / 64 | 1023 / 64 |
| Embedding-table width | 1024 | 128 | 1024 |
| Vocab (user/item/author/IP) | 100M / 100M / 30M / 10M | 100k / 100k / 30k / 10k | — / 100M / 30M / — |
| Hashes per entity | 2 | 2 | 2 |
| Semantic IDs | 6 × 256 | 6 × 256 | 6 × 256 (candidate identity) |
| Per-device batch | 512 (GB300) / 256 (H100) | 64 | 480 |

An 8-layer, 2560-wide transformer — modest by LLM standards; the capacity is in the embedding tables.

---

## 2. The user action sequence

This is the load-bearing input: "the viewer's recent engagements, and the main input to the model" (`README.md:80-84`).

**Wire format** (`phoenix/python/common/xai-proto/proto/recsys.proto`): `UserActionSequence` (line 1244) contains `AggregatedUserAction`s (line 1224), each = one impressed post with **all** actions the user took on it:

- `TweetInfo` (line 1150): tweetId, authorId, retweet/quote/reply lineage IDs, semantic IDs, language, fav/reply/retweet/quote/view counts, `isAuthorFollowedByUser`, video duration…
- `actions: repeated ActionInfo` (line 1205): `engagementTimeMs`, `actionName` (the enum in §3), plus `UserActionMeta` (line 1119) with **`dwellTime`** (ms), product surface, client platform/app, timezone, IP country, `percent_screen_height_100k`, even device battery/network state.
- `impressedTimeMs` — when the post was shown.

**What serving actually feeds the model** (`phoenix/crates/common/xai-recsys/src/util.rs:645-780`): the engine takes the **last 1022 events** (`start = len - history_seq_len`, line 686) and per event writes: 2 post-ID hashes, 2 author-ID hashes, a **multi-hot bool vector over the 64-slot action vocab** (line 712-719), **summed dwell time in seconds** into the DWELL_TIME continuous slot (lines 714-728), product surface, impression timestamp (seconds), post-creation timestamp derived from the snowflake ID (line 754), timezone enum, and safety-label mask. Note what is *not* fed: no post text, no aggregate per-user counters — the raw event sequence is the representation.

**Hydration on the request path** (`home-mixer/query_hydrators/scoring_sequence_query_hydrator.rs:37-68`): home-mixer fetches the sequence from a "user action aggregation" service with `MaxSeqLengthScoring = 1024` (`home-mixer/params/param.rs:890-894`), a freshness window `UAS_WINDOW_TIME_MS = 300_000` (5 min, `home-mixer/params/config.rs:34`), and aggregation type `DenseWithFavVqvCleaned` (line 53) — i.e., events are pre-joined per post ("aggregated"), deduped/cleaned upstream. The aggregation service itself is not in the repo.

**Recency weighting: none explicit.** There is no decay factor on history events. Order + timestamps are the signal: events are position-encoded with right-anchored RoPE (`right_anchored_rope=True`, `xrecsys.py:258`; `recsys_model.py:148-171`) so the most recent event always sits at the same relative position, and each event carries its impression timestamp and post-age bucket. The model learns recency itself.

---

## 3. Predicted actions (the heads)

**Output shape**: `[B, num_candidates, 64]` binary logits + `[B, num_candidates, 8]` continuous slots (`xrecsys.py:42-44`: `ACTION_TYPE_MAP_LEN = 60` rounded to `output_vocab_size = 64`; 4 defined continuous actions rounded to 8). Unembedding at `recsys_model.py:1891-1978`.

**Action vocabulary** — `enum ActionName`, `recsys.proto:229-435`, ~60 organic actions in the trained range (0-104; ads actions 128+ are separate metric groups). **Head-to-engagement mapping** confirmed in `phoenix/xrex/data/recsys/constants.py:23-158` (`primary_engagement_to_action_types`) and consumed by the serving scorer via `PhoenixScores` fields (`home-mixer/scorers/ranking_scorer.rs:470-506`, `home-mixer/scorers/vm_ranker.rs:140-177`). The full serving head list with production blend weights (`home-mixer/params/param.rs:282-448`):

| Group | Head (proto action) | Weight |
|---|---|---|
| Engagement | favorite (`SERVER_TWEET_FAV`) | 0.5 |
| | reply (`SERVER_TWEET_REPLY`) | 5.0 (+15.0 if bidirectional follow, param.rs:284-289) |
| | repost (`SERVER_TWEET_RETWEET`) | 1.0 |
| | quote (`SERVER_TWEET_QUOTE`) | 5.0 |
| | share (`CLIENT_TWEET_SHARE`) | 2.0 |
| | share via DM (`CLIENT_TWEET_CLICK_SEND_VIA_DIRECT_MESSAGE`) | 5.0 |
| | share via copy link (`CLIENT_TWEET_SHARE_VIA_COPY_LINK`) | 20.0 |
| Clicks | post click (`CLIENT_TWEET_CLICK`) | 0.4 |
| | profile click (`CLIENT_TWEET_CLICK_PROFILE`) | 0.0 |
| | open link (`CLIENT_TWEET_OPEN_LINK`) | 0.2 |
| | photo expand (`CLIENT_TWEET_PHOTO_EXPAND`) | 0.05 |
| | video open (`CLIENT_TWEET_VIDEO_OPEN`) | 0.05 |
| | quoted-post click (`CLIENT_QUOTED_TWEET_CLICK`) | 0.05 |
| Attention | video quality view (`CLIENT_TWEET_VIDEO_QUALITY_VIEW`) | 0.05 (gated on video ≥ min duration) |
| | quoted VQV (`CLIENT_QUOTED_TWEET_VIDEO_QUALITY_VIEW`) | 0.0 |
| | dwell (`CLIENT_TWEET_RECAP_DWELLED`) | 0.0 |
| | dwell time (continuous `DWELL_TIME`) | 0.004 per unit |
| | click dwell time (continuous `CLICK_DWELL_TIME`) | 0.0 |
| | active seconds (continuous `ACTIVE_SECS_5M_RESIDUAL_NORM`) | 0.0 |
| Author | follow author (`CLIENT_TWEET_FOLLOW_AUTHOR`) | 4.0 |
| Exploration | post unexplored (`SERVER_TWEET_POST_UNEXPLORED`) | 0.02 |
| Negative | not interested (`CLIENT_TWEET_NOT_INTERESTED_IN`) | **−43.2** |
| | mute author (`CLIENT_TWEET_MUTE_AUTHOR`) | **−58.8** |
| | block author (`CLIENT_TWEET_BLOCK_AUTHOR`) | **−31.2** |
| | report (`CLIENT_TWEET_REPORT` / `SERVER_TWEET_REPORT`) | **−234.0** |
| | not dwelled (`CLIENT_TWEET_RECAP_NOT_DWELLED`) | −0.02 |

`Final Score = Σ weight_i × P(action_i)` (`ranking_scorer.rs:422-523`; README.md:312-330), then author-diversity decay (0.5 per repeat, floor 0.25 — param.rs:229-240), an out-of-network discount (×0.75 — param.rs:247), and a new-author boost. Negative weights are huge because negative feedback is rare but decisive (comment at param.rs:280-282).

**Extras beyond the README list**: bookmark (`CLIENT_TWEET_BOOKMARK`) is in the trained taxonomy (constants.py:36-38) though not in the serving blend; a bank of external-link-session duration buckets (<3s … >60s, constants.py:84-116) that operationalize "clickbait detection"; screenshot, translate, show-more, Grok-analyze, hashtag/mention clicks in the extended `"all"` metric group (constants.py:120-158); and `NEGATIVE_FEEDBACK_HEAD_INDICES` also includes see-fewer, not-relevant, mute-conversation (constants.py:274-283).

**Definitions**: "dwell"/"not dwelled" are client-emitted recap events (thresholds live client-side, not in the repo); dwell *time* is the summed per-post `UserActionMeta.dwellTime`. The synthetic world marks "dwelled" at ≥10 s, capped 300 s (`phoenix/reference/world.py:73-74,338-339`), and a data filter treats "VQV + dwell ≥10 s" as the positive bar (`recsys_batch.py:97-108`) — consistent hints that ~10 s is the operative dwell notion. "Post unexplored" is a computed exploration label, not a user action: true for original posts <24 h old whose view count is below a decaying 3%-of-followers reach target (`recsys_batch.py:45-73`) — predicting it gives under-distributed fresh posts a small positive boost (weight 0.02).

---

## 4. Training: labels, loss, synthetic data, JAX/Rust split

**Labeling path — logged impressions become examples.** Each training row is one user's event stream; a `newEventMask` column splits it: old events → history, new events (the just-served impressions) → candidates, whose recorded actions become the labels (`recsys_batch.py:615-724`: history = `~newEventMask & padding`, candidates = `newEventMask & padding`). The label per candidate is the **multi-hot `actionNameMultiHotSeqSeq` vector over the 64-action vocab** (`recsys_batch.py:371-377`) — a post that was shown and only scrolled past has an all-zero row (implicit negative); a favorited+replied post has two bits set. Continuous targets ride in `continuousActionValuesSeqSeq`. No human labeling anywhere.

**Loss** (`phoenix/xrex/models/loss_recsys.py`):
- Binary heads: **per-action sigmoid binary cross-entropy** on multi-hot targets, masked and weight-normalized (`multihot_loss_compute`, lines 15-49). Multi-label, not softmax — actions aren't exclusive.
- Continuous heads: MSE/MAE/Huber (`continuous_loss_compute`, 52-92) and **Tweedie deviance** (95-127) for the zero-inflated dwell-time distribution. Production dwell config (`xrecsys.py:565-586`): Tweedie p=1.5, cap 300 s, weight 0.1 on the video-gallery surface; MAE with norm-scale 30 s elsewhere.
- **Log-Q popularity correction**: each candidate's loss weight is 1/frequency of its post in the stream (`recsys_model.py:2626-2636`, `log_q_num_bins=100M`), so viral posts don't dominate gradients.
- **In-batch negative sampling**: each example's 64 real candidates are augmented with candidates borrowed from other users in the batch, labeled all-zero (`recsys_batch.py:933-1105`; `negative_sample_mask` at `recsys_model.py:2604-2614`) — teaching "this user would *not* have engaged this," not just reweighing served posts. Optionally, positives co-occurring with negative feedback are masked out of positive heads (`recsys_model.py:2781-2803`, report/not-interested/block/mute/etc.).
- Optimizers (`phoenix/TRAINING.md:12-30`): dense params AdamW (wd 1e-3, β=0.95/0.98; prod uses a tuned RMS-norm-Adam variant not shipped), embedding tables **rowwise AdaGrad** (LR 0.2), non-finite-gradient steps skipped. LR 1e-3 (H100) / 5e-4 (GB300), μP-style width scaling with 512 base width (`README.md:418-421`).
- Retrieval trains contrastively — in-batch + 64 sampled global negatives with log-Q correction, **positives = favorites** (`phoenix/xrex/configs/xrecsys_two_tower.py:280-282`; an "immersive" head widens positives to fav/reply/quote/repost/VQV/follow/bookmark/share, lines 283-292).

**Synthetic proof-of-concept** (`phoenix/reference/README.md`): since production Kafka/embedding/SID services can't ship, `reference/world.py` plants a seeded world (topics, authors, users, posts) with a known engagement model — P(action) = per-action base rate × sigmoid(14·(topic-affinity − 0.10)) (`world.py:308-312`), dwell threshold 10 s — and `dump_gen.py` emits parquet in the exact production `aggregated_kafka` layout; `oss_recsys_synth.py` fabricates unit-norm multimodal embeddings (random-Fourier sin map) and 6×256 RQ semantic IDs. `train_synth.py` trains the geometry-identical `home_direct_packed_nano` on it in minutes; the planted structure is learnable, so the pipeline is verifiable end to end.

**JAX training / Rust serving split**: the model and losses are JAX/Haiku (`phoenix/xrex/`), while serving is a Rust gRPC engine (`phoenix/crates/serving/`, built via `uv sync --extra engine`) that loads the same checkpoints and answers `RecsysPredictor.PredictNextActions` (`recsys.proto:7-12,79-124`) — request = user sequences + candidate sets, response = per-candidate logits + continuous values. Training-only mechanics (sequence packing of multiple variable-length sessions per row, varlen attention kernels) don't change the serving contract (`phoenix/README.md:185-189`).

---

## 5. vm-ranker: determinantal point process re-ranking

After the weighted sum, home-mixer's `VMRanker` scorer calls the separate `vm-ranker/` service (`home-mixer/scorers/vm_ranker.rs`), sending each candidate's blended score plus all its per-head Phoenix probabilities (lines 140-204).

**Algorithm** (`vm-ranker/dpp.rs:35-197`, greedy MAP at 205-286):
1. Sort by score; keep the top `max_selected_rank` as the pool (prod **150**, `param.rs:615-620`; binary default 100, `vm-ranker/args.rs:24-25`).
2. Normalize quality `q_i = score_i / max_score`, then `qf_i = exp(α·q_i)` with **α = θ / (2(1−θ))** (`dpp.rs:94-97`). θ (prod **0.65**, `param.rs:609-613`; default 0.5) is the score-vs-diversity dial: θ→0 pure score, θ→1 pure diversity.
3. Build the DPP kernel **L_ij = qf_i · qf_j · cos(e_i, e_j)** over the posts' **1024-d multimodal content embeddings** (f16, fetched from the MM embedding store, `vm-ranker/scoring/dpp_model.rs:38-82`, `vm-ranker/embedding_store.rs`). Reposts use the original post's embedding (line 59-63); missing embeddings get a random unit vector (i.e., ~orthogonal to everything, no diversity penalty).
4. **Greedy MAP selection** via incremental Cholesky: repeatedly pick the item with the largest conditional volume `cv_i = L_ii − Σ_j f_ji²` — high score *and* low similarity to everything already selected — until `top_k` (prod 50) items or `cv ≤ 1e-6` (rank exhausted; near-duplicates of selected posts can never be picked) (`dpp.rs:241-279`).
5. Selected posts **keep their original scores** and order (`dpp.rs:136-153`); unselected posts are returned with score 0 and dropped (`dpp_model.rs:143-153`). So the DPP is a diversity *filter* over the top-150, not a score perturbation: test `identical_embeddings_select_top_scorer_only` (`dpp.rs:363-380`) shows exact duplicates collapse to the single best-scoring copy; `orthogonal_embeddings_promote_diversity` (382-403) shows a lower-scored but different post beats a near-duplicate of #1.

Summary from the root README: "reorders them with a determinantal point process over their embeddings, giving up a little score for less similarity between neighbours" (`README.md:265`).

---

## 6. Cold start: new users and new posts

**New users (thin history):**
- Serving can route users whose sequence length is below `PhoenixRankerNewUserHistoryThreshold` to a dedicated inference cluster (a separately-trained/configured model) — mechanism in `home-mixer/scorers/phoenix_scorer.rs:24-42`, threshold param at `param.rs:215-219` (published default 0 = off; same knob exists for retrieval, param.rs:190-194).
- Training explicitly tracks the segment: examples with **<128 history events** are bucketed as "new user" and 0 events as "no history" for metrics (`recsys_model.py:2675-2684, 2773-2775`), so head quality is monitored on cold users.
- A protective filter: `NewUserMinEngagementFilter` drops low-engagement out-of-network posts for new accounts (`README.md:362`).
- Retrieval carries **no learned per-user ID embedding at all** (`use_user_embedding=False`, `xrecsys_two_tower.py:308`; `phoenix/README.md:99-106`) — the user *is* their history plus coarse profile features, so representation quality degrades gracefully with history length rather than depending on a per-user vector having been trained.
- The user-features prefix token (country, language, age, gender, installed apps) gives a demographic prior when history is empty.

**New posts:**
- **Hash embeddings mean any post ID is representable the moment it exists** — hashing needs no vocabulary update or embedding-table growth (`phoenix/README.md:239-246`).
- **Semantic IDs carry the content prior**: a new post's 6×256 RQ code shares prefixes with topically similar old posts, so the model generalizes to it immediately even though its ID hash rows are untrained ("compositional generalization to unseen posts", `phoenix/README.md:108-113`).
- The **post-unexplored head** (+0.02 weight) actively boosts original posts <24 h old that haven't reached ~3% of the author's followers (§3; `recsys_batch.py:45-73`).
- The **new-author boost** lifts posts from authors below an impression threshold toward a target feed position (`README.md:336`; `home-mixer/scorers/author_cold_start.rs`, params `ColdStartImpressionThreshold` / `ColdStartSlotMin/Max` / `LowImpressionsMaxPositionRatio`).
- Post-age is an input feature (60-min buckets), and a hard `AgeFilter` caps the feed at 48 h (`home-mixer/params/config.rs:36`), so the whole system is biased toward fresh inventory by construction.

---

## 7. Takeaways for a trade-suggestion engine comparison

- **The ranking signal is a raw event sequence, not aggregate features.** ~1,000 (post, author, action-multi-hot, dwell-seconds, timestamp, surface) tuples; the model learns recency/taste itself. FTF equivalent: the sequence of (player/trade viewed, action taken — proposed/saved/dismissed/sent-in-sleeper, dwell) events rather than summary stats.
- **One model, many heads, hand-tuned blend.** Per-item scoring = Σ weight × P(action), with rare-but-decisive negative actions (report −234 vs favorite +0.5) doing the safety work. Trade analog: predict P(propose), P(save), P(dismiss), P(report-unfair) per suggestion and blend.
- **Labels are free**: every impression + observed response is a training row; non-engagement of served items and in-batch borrowing of other users' items provide the negatives.
- **Candidate isolation** makes scores stable and cacheable per (user, item) — worth preserving in any learned ranker.
- **Cold start is structural, not a bolt-on**: hash IDs (instant representability), content codes (semantic IDs ≈ player archetype features), history-only user representation, an exploration head, and a new-author boost.
- **Diversity is a separate post-pass**: greedy DPP over content embeddings filters near-duplicates from the top-150 while keeping original scores — directly analogous to avoiding five near-identical trade suggestions for the same two rosters.
