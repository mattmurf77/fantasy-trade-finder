# X Algorithm — Request-Path Pipeline (home-mixer + candidate-pipeline)

Source: the 2026-08-13 open-source release of X's For You feed. Every For You request runs two nested pipelines built on one generic framework. The inner **Post Pipeline** (`PhoenixCandidatePipeline`) loads the viewer's context (recent action sequence, follows, blocks, mutes, seen/served history), pulls ~2,000-3,000 candidate posts in parallel from in-network and out-of-network sources, hydrates and filters them, asks the Phoenix transformer for per-action probabilities (P(favorite), P(reply), P(report), ...), collapses those into one score with a fixed weight vector (reply = 5.0, favorite = 0.5, report = -234.0, ...), applies author-diversity decay, an out-of-network discount, and a small-author cold-start boost, keeps the top 50, runs visibility filtering, and returns 35 posts. The outer **Blending Pipeline** (`ForYouCandidatePipeline`) treats those posts as one source among several and interleaves ads, Who to Follow, prompts, and sports frames at fixed or computed positions. After the response is sent, ~18 side effects write back what was served — served history, impression records, candidate caches, Kafka logs of every score — which is the data the next request and the next model-training run read. Ranking optimizes a weighted sum of predicted user actions; being shown at all is a separate system (visibility filtering) with its own rules.

---

## 1. Pipeline framework (`candidate-pipeline/` crate)

The crate defines one trait per stage type, each with an `enable(query)` gate, a `run()` wrapper that adds tracing/stats, and a `name()`:

- **QueryHydrator** (`candidate-pipeline/query_hydrator.rs`) — takes the query, returns an enriched copy; `update()` merges one field back. Failures are logged and skipped (the request proceeds without that context).
- **Source** (`candidate-pipeline/source.rs`) — takes the query, returns `Vec<Candidate>`. Failures return an error; other sources' results still flow.
- **Hydrator** (`candidate-pipeline/hydrator.rs`) — enriches candidates; must return exactly one result per input candidate or the whole stage's output is discarded (length-mismatch guard). Also provides a `CachedHydrator` variant with per-candidate cache lookup, batch fetch of misses, and hit/miss stats.
- **Filter** (`candidate-pipeline/filter.rs`) — splits candidates into `{kept, removed}`; removal counts per filter are recorded.
- **Scorer** (`candidate-pipeline/scorer.rs`) — async, batch: takes all candidates, returns scored copies; same length-mismatch guard.
- **Selector** (`candidate-pipeline/selector.rs`) — default implementation sorts descending by `score(candidate)` and splits at `size()` into `{selected, non_selected}`.
- **SideEffect** (`candidate-pipeline/side_effect.rs`) — receives `{query, selected_candidates, non_selected_candidates}` after the response.

`CandidatePipeline::execute_stages` (`candidate-pipeline/candidate_pipeline.rs:97-148`) fixes the stage order:

```
query_hydrators (parallel, join_all)
→ dependent_query_hydrators (parallel; may read the first wave's output)
→ sources (parallel; results concatenated)
→ hydrators (parallel over hydrators; each sees all candidates)
→ filters (sequential, order matters)
→ scorers (sequential — each scorer sees the previous scorer's updates)
→ selector (sort + split at K)
→ post_selection_hydrators (parallel)
→ post_selection_filters (sequential)
→ truncate to result_size()
→ side_effects (tokio::spawn — fire-and-forget after the result is returned)
```

Parallelism rule of thumb: everything *within* a stage that is independent runs concurrently (`join_all`); stages that mutate ordering or depend on prior stage output (filters, scorers) run sequentially. Side effects never block the response (`candidate_pipeline.rs:396-409`).

## 2. Query hydration (`home-mixer/query_hydrators/`)

The Post Pipeline registers 17 query hydrators (`home-mixer/candidate_pipeline/phoenix_candidate_pipeline.rs:224-275`), all fetched in parallel per request:

| Hydrator | What it loads |
|---|---|
| `ScoringSequenceQueryHydrator` | **The main model input**: the viewer's aggregated user-action sequence from the User Action Aggregation service — up to **1024 actions** (`MaxSeqLengthScoring`, `param.rs:889-894`), aggregation type `DENSE_WITH_SHORT_DWELL` (`param.rs:121-126`), 300s aggregation window (`params/config.rs:34`). Returned in Arrow columnar format. |
| `RetrievalSequenceQueryHydrator` | Same thing again, separately, for the retrieval model (up to 1024 actions, `UaasModelType::Retrieval`). |
| `BlockedUserIdsQueryHydrator` | Full list of accounts the viewer blocks (social graph service). |
| `MutedUserIdsQueryHydrator` | Full list of accounts the viewer mutes. |
| `FollowedUserIdsQueryHydrator` | Full following list (skipped if the request already carries it). |
| `SubscribedUserIdsQueryHydrator` | Creators the viewer pays to subscribe to (gates subscriber-only posts). |
| `CachedPostsQueryHydrator` | Previously scored candidates from Redis (zstd+JSON); counted as "has cached posts" only if ≥500 posts (`cached_posts_query_hydrator.rs:806`); lets a follow-up request skip Phoenix scoring entirely. |
| `MutualFollowQueryHydrator` | Viewer's follow-graph MinHash (for Jaccard similarity to authors; off by default). |
| `UserDemographicsQueryHydrator` | Viewer demographics (context features for the model). |
| `FollowedGrokTopicsQueryHydrator` | Followed Grok topics as a boolean array over a fixed parent-topic vocabulary. |
| `FollowedStarterPacksQueryHydrator` | Followed starter packs as a boolean array. |
| `UserInstalledAppsQueryHydrator` | Multi-hot vector of which X-family apps the viewer has installed. |
| `ExplicitEngagementSignalsQueryHydrator` | Recent engaged posts split by type — Favorite, Retweet, Reply, Bookmark, Share, OriginalTweet — **max 15 per type** (`EngagementSignalsMaxPerType`, `param.rs:717-722`), each with `{tweet_id, author_id, engaged_at_ms}`. |
| `ImplicitEngagementSignalsQueryHydrator` | Same shape for implicit signals: PhotoExpand, VideoQualityView, ImmersiveVideoQualityView (videos ≥10s only), max 15 per type. |
| `ImpressionBloomFilterQueryHydrator` | Bloom filters of everything the viewer has been shown on Home (primary seen-posts record). |
| `IpQueryHydrator` | Geo location from IP. |
| `UserInferredGenderQueryHydrator` | Stored inferred gender; falls back to a live model call for day-0 accounts. |

Notable: `ImpressedPostsQueryHydrator` (a second impression record) is constructed but **not registered** in this pipeline (`phoenix_candidate_pipeline.rs:277-279` binds it to `_impressed_posts_hydrator`), so `PreviouslySeenPostsBackupFilter` usually sees an empty list here.

The Blending Pipeline adds two of its own (`for_you_candidate_pipeline.rs:185-192`): `ServedHistoryQueryHydrator` — recent served entries; derives `served_ids` (posts served in the last **10 minutes**, max **100**, `param.rs:1009-1020`) and module fatigue (Who to Follow eligible only if not shown in **30h**, feed survey **24h**) — and `PastRequestTimestampsQueryHydrator` (last 10 non-polling request times).

## 3. Pre-scoring filters (`home-mixer/filters/`), in registration order

Order from `phoenix_candidate_pipeline.rs:344-362`; filters run sequentially, each on the survivors of the previous one.

| # | Filter | Removes |
|---|---|---|
| 1 | `DropDuplicatesFilter` | Same tweet_id returned by more than one source (first source wins). |
| 2 | `CoreDataHydrationFilter` | Posts whose core data failed to hydrate (`author_id == 0`). |
| 3 | `AgeFilter` | Posts older than **48 hours** (`MAX_POST_AGE`, `params/config.rs:36`); age decoded from the snowflake ID. |
| 4 | `SelfTweetFilter` | The viewer's own posts. |
| 5 | `OONRetweetReplyFilter` | Reposts/replies whose author the viewer does not follow; also any reply with no ancestors loaded. |
| 6 | `OONNsfwSimclustersFilter` | SimClusters-sourced posts from an adult-content-flagged author the viewer doesn't follow. |
| 7 | `RetweetDeduplicationFilter` | Second and later reposts of the same original post. |
| 8 | `IneligibleSubscriptionFilter` | Subscriber-only posts from creators the viewer doesn't subscribe to. |
| 9 | `PreviouslySeenPostsFilter` | Posts (or their retweeted/quoted/ancestor posts) in the seen-ids list or matching the impression bloom filters. |
| 10 | `PreviouslySeenPostsBackupFilter` | Same check against the second impression store (usually empty here — see §2). |
| 11 | `PreviouslyServedPostsFilter` | Posts served in the last 10 minutes (max 100 tracked); on by default for all request types (`EnableServedFilterAllRequests`, `param.rs:908-913`). |
| 12 | `MutedKeywordFilter` | Posts whose tokenized text matches any viewer muted keyword. |
| 13 | `AuthorSocialgraphFilter` | Author blocked or muted by viewer; author blocks viewer; quoted author blocks viewer or is blocked by viewer; retweeted author blocked by viewer. |
| 14 | `VideoFilter` | Video posts when the request says exclude videos. |
| 15 | `TopicIdsFilter` | On topic-scoped requests: posts outside the requested topic (with supertopic/category expansion, ~90 hardcoded xAI topic IDs); always: posts in explicitly excluded topics. |
| 16 | `NewUserMinEngagementFilter` | For brand-new/resurrected viewer accounts (<30 min): OON posts below an engagement threshold (off by default). |
| 17 | `InventoryHoldoutFilter` | Deterministic per (post, viewer) hash holdout of N% of originals/replies/retweets — a causal-measurement holdout (off by default, 0%). |

Sources feeding this: Thunder (in-network, max 1200), Phoenix retrieval (max 1000), SimClusters, Phoenix topics, cached posts; TweetMixer (800) and Phoenix MOE (200) exist but default off (`param.rs:4-53,134-163`). Thunder is given the seen-ids list and pre-excludes them; other sources rely on filters 9-11.

## 4. Scoring (`home-mixer/scorers/`)

Three scorers run in sequence: `PhoenixScorer` → `RankingScorer` → `VMRanker` (`phoenix_candidate_pipeline.rs:395-396`).

**PhoenixScorer** (`scorers/phoenix_scorer.rs`) sends the viewer's action sequence + all candidates to the Phoenix transformer inference service and gets back, per post, a probability for each action head. Skipped entirely when serving from cached posts. Candidates cannot attend to each other in the model, so scores are batch-independent and cacheable.

**RankingScorer** (`scorers/ranking_scorer.rs`) computes, in default `weighted` mode:

```
weighted_score = Σ_i  weight_i × P(action_i)          (ranking_scorer.rs:422-523)
score < 0 → remapped into [0, 0.001) via offset       (ranking_scorer.rs:525-533, NEGATIVE_SCORES_OFFSET params/config.rs:40)
then: × author-diversity multiplier                    (ranking_scorer.rs:614-679)
      × OON discount if out-of-network                 (ranking_scorer.rs:681-700, 847-858)
      max(score, cold-start target) for one small author (author_cold_start.rs:156-192)
```

### Actual per-action weights (`home-mixer/params/param.rs`, production defaults synced 2026-08-12)

The file's own comment (`param.rs:279-281`): weights reflect both how much an action is valued and its typical propensity (negative feedback is rare, hence huge magnitudes).

| Action head | Weight | param.rs line |
|---|---|---|
| Reply | **5.0** | 283 |
| ...reply boost if author is a mutual follow (original posts only) | **+15.0** → effective 20.0 | 284-289 |
| Quote | **5.0** | 332 |
| Share via DM | **5.0** | 319-324 |
| Share via copy link | **20.0** | 325-330 |
| Follow author | **4.0** | 345-350 |
| Share (sheet open) | **2.0** | 318 |
| Repost | **1.0** | 296 |
| Favorite | **0.5** | 282 |
| Click (post detail) | **0.4** | 309 |
| Open link | **0.2** | 310 |
| Photo expand | **0.05** | 297-302 |
| Video open | **0.05** | 303-308 |
| Video quality view (VQV) | **0.05** | 317 |
| Quoted-post click | **0.05** | 333-338 |
| Post unexplored (exploration bonus, in-network only) | **0.02** | 351-356, gate 369-374 |
| Dwell time (continuous, per unit) | **0.004** | 376-380 |
| Dwell (binary) | **0.0** | 331 |
| Profile click | **0.0** | 311-316 |
| Quoted VQV | **0.0** | 339-344 |
| Click dwell time | **0.0** | 381-386 |
| Active secs 5m residual | **0.0** | 417-422 |
| Not dwelled | **-0.02** | 443-448 |
| Block author | **-31.2** | 430-435 |
| Not interested | **-43.2** | 424-429 |
| Mute author | **-58.8** | 436-441 |
| Report | **-234.0** | 442 |

Reading: one predicted report costs as much as ~468 predicted favorites; a reply from a mutual follow is worth 40× a favorite. Everything negative is user-initiated rejection; "not dwelled" is the only cheap negative.

### Post-sum adjustments

- **Author diversity** (`param.rs:222-239`, math `ranking_scorer.rs:614-616`): candidates are ranked by pre-diversity score; an author's k-th post (k=0,1,2,...) is multiplied by `(1-floor)·decay^k + floor` with **decay = 0.5**, **floor = 0.25** → multipliers 1.0, 0.625, 0.4375, ... → 0.25. Slate context is persisted with cached posts so re-serves reuse the same k.
- **Out-of-network discount** (`param.rs:246-251,266-271`; `ranking_scorer.rs:681-700`): OON posts ×**0.75** (`OonWeightFactor`); the same discount applies to in-network *replies and reposts* (`EnableOonRescoreForInNetworkRepliesRetweets`, default true, `param.rs:260-265`). Topic-scoped requests use **0.5**. Brand-new users (< `NewUserAgeThresholdSecs`, currently 0 = off) with ≥5 follows would get factor **0.00001** — effectively in-network only (`params/config.rs:38-39`).
- **New-author cold-start boost** (`scorers/author_cold_start.rs`; params `param.rs:620-663`): per request, pick the best-scoring candidate that is an original post, author ≤**1000 followers** (`ColdStartFollowerCap`), post <**1000 views** (`ColdStartImpressionThreshold`), currently ranked within the top **85%** of nonzero scores (`LowImpressionsMaxPositionRatio`), and raise its score to the score of a random slot in ranks **15-16** (`ColdStartSlotMin/Max`). Enabled by default (`EnableViewerColdStart`, `param.rs:658-663`). One post per request — a deliberate exploration slot for small accounts.
- **Bidirectional-follow boost** eligibility (`ranking_scorer.rs:180-193`): original posts only (not replies/reposts), author must mutually follow the viewer; implemented as +15.0 on the *reply weight*, not a score multiplier.

Alternative value-model modes exist behind `ValueModelMode` (`param.rs:450-557`, default `"weighted"`): `dwell_regret_sigmoid` scores posts as `dwell_time × 2·sigmoid(positive/T) × exp(min(negative,0)/T)` with T=10 and enormous negative weights (not_interested -10000, block -8000, mute -15000, report -60000), and `gated_dwell_regret` turns that on per-user via a 19-feature logistic gate whose fitted coefficients are in `param.rs:534-551`.

**VMRanker** (`scorers/vm_ranker.rs`) sends the top candidates (ids, scores, all Phoenix heads, slate context) to the external `vm-ranker` service, which reorders via a determinantal point process over post embeddings — trading a little score for less similarity between neighbors. DPP params: **theta = 0.65**, **max_selected_rank = 150** (`param.rs:608-619`). Returned scores replace `candidate.score`; on gRPC failure the pre-VMRanker scores stand (fallback behavior configurable).

## 5. Selection and post-selection

**TopKScoreSelector** (`selectors/top_k_score_selector.rs`) sorts by final score descending and keeps **K = 50** (`TOP_K_CANDIDATES_TO_SELECT`, `params/config.rs:17`). The pipeline's final `result_size()` is **35** (`RESULT_SIZE`, `config.rs:18`) — 50 go through post-selection hydration/filtering, then the list is truncated to 35 (extra 15 = headroom for post-selection drops).

Post-selection hydrators (`phoenix_candidate_pipeline.rs:400-415`) run only on the 50 survivors — notably `VFCandidateHydrator`, which calls the visibility-filtering service per (post, viewer). Post-selection filters (`:417-421`):

| Filter | Removes |
|---|---|
| `VFFilter` (`filters/vf_filter.rs`) | Posts visibility filtering answered **Drop** for; Interstitial verdicts pass through. |
| `AncillaryVFFilter` (`filters/ancillary_vf_filter.rs`) | Posts whose thread ancestor, quoted post, or reposted post was itself dropped. |
| `DedupConversationFilter` (`filters/dedup_conversation_filter.rs`) | All but the highest-scoring branch of each conversation (conversation id = min ancestor id). |

Doing expensive per-viewer policy checks only on the top 50 — after ranking — is the key cost optimization.

## 6. Blending pipeline (`candidate_pipeline/for_you_candidate_pipeline.rs`)

The outer pipeline's candidate type is `FeedItem` (post | ad | WhoToFollow | prompt | pushToHome | frame | survey). Sources (`:194-209`): `ScoredPostsSource` (wraps the entire Post Pipeline), `AdsSource`, `WhoToFollowSource`, `PromptsSource`, `PushToHomeSource`, `JetfuelFrameSource` (sports cards), `FeedSurveySource`. One pre-filter (`PushToHomeDedupFilter`), no scorers.

**BlenderSelector** (`selectors/blender_selector.rs:30-95`) does the interleave:

1. Partition items by type.
2. Blend ads into posts via the configured blender — default `partition_organic_low_risk` (`AdsBlenderType`, `param.rs:852-857`). `PartitionOrganicAdsBlender` (`ads/partition_organic_blender.rs`) splits posts into brand-safe vs not, allocates at most `safe_count/2` and `(n-1)/spacing` ad slots, and places each ad as a (safe post, ad, safe post) sandwich, skipping ads whose brand-safety risk, advertiser handle, or negative keywords clash with the adjacent posts; remaining posts fill gaps in score order; a trailing ad is popped. A `time_gap` blender variant spaces ads by predicted time-per-post (t=4s, min organic gap 3, `param.rs:858-881`).
3. Insert prompts at **position 0**, Who to Follow at **position 6**, feed survey at **position 12** (`PROMPTS_POSITION`, `WHO_TO_FOLLOW_POSITION`, `FEED_SURVEY_POSITION`, `params/config.rs:29-32`); pin push-to-home post at the very top; insert sports frames per their occurrence plan (NFL cards every 8th slot).

Final size cap: 35 posts + 4 module slots + 8 frames = **47** items (`FOR_YOU_MAX_RESULT_SIZE`, `config.rs:21-22`).

## 7. Side effects — the feedback loop

All fire after the response, in the background. This is where "what we showed you" becomes input to the next request and to model training.

**Post Pipeline side effects** (`phoenix_candidate_pipeline.rs:423-440`):

| Side effect | Writes |
|---|---|
| `RedisPostCandidateCacheSideEffect` | Top **750** scored candidates by weighted score (selected + non-selected, score > 0) → Redis, zstd JSON, **TTL 180s** (`redis_post_candidate_cache_side_effect.rs:1057`). Read back by `CachedPostsQueryHydrator` so pagination re-serves without re-scoring. |
| `PhoenixRequestCacheSideEffect` | The full Phoenix prediction request (minus sequence) + per-candidate feature snapshots → two Redis clusters (dual-DC), **TTL 10800s** (3h, `param.rs:960-965`). Joins served impressions to model features for training-label generation. |
| `RerankingKafkaSideEffect` | On a **5% random sample** of requests (`reranking_kafka_side_effect.rs:1319`): top 50 candidates with *every* per-head probability, final/weighted score, position, served_type, in_network, mutual-follow flag, **plus the full applied weights map and value-model mode** → Kafka. This is the audit trail of the exact scoring arithmetic per request. |
| `PhoenixExperimentsSideEffect` | On shadow traffic: re-scores the served slate against every experimental Phoenix cluster and logs all heads per cluster → Kafka (offline model comparison without serving users). |
| `ScoredStatsSideEffect` | Score-distribution histograms per head (5% sample), served-count by source, retrieval-source top-K hit rates. |
| `AuthorServedMetricsSideEffect` / `MutualFollowStatsSideEffect` / `DebugSideEffect` | Per-tracked-author serve counters; average mutual-follow Jaccard; debug logging for trace users. |

**Blending Pipeline side effects** (`for_you_candidate_pipeline.rs:216-231`):

| Side effect | Writes |
|---|---|
| `UpdateServedHistorySideEffect` | Every served item (posts with score + served_type + prediction_request_id, ads with impression id, WTF user ids, prompts, frames, ancestors of thread posts) keyed by (user, timeline, platform, request time) → served-history store. Feeds the next request's `served_ids` filter and module fatigue. |
| `TruncateServedHistorySideEffect` | Deletes served-history rows beyond the most recent **50** responses. |
| `UpdatePastRequestTimestampsSideEffect` | Prepends this request's timestamp (keep 10) — used for session/freshness logic. |
| `PublishSeenIdsToKafkaSideEffect` | The request's seen-ids (client-reported impressions) republished as `Impression` records → Kafka (`CLIENT_SENT_IMPRESSIONS_TOPIC`) — feeds the impression bloom-filter store. |
| `ServedCandidatesKafkaSideEffect` | (Shadow traffic) Full served-entry log: request info (ip, user agent, country, query type) + per-entry position/score → Kafka. |
| `ClientEventsKafkaSideEffect` | Server-emitted analytics events mirroring client-event schema: counts served (posts/ads/WTF), per-tweet-type and per-served-type counts, video counts, empty-timeline events, request-type × result-size matrix → Kafka. |
| `AdsInjectionLoggingSideEffect` / `ServedAdHistoryCacheSideEffect` | Full ad-injected timeline (positions, brand-safety verdicts, counts) → ads Kafka; served-ad record → 5-min cache (ad fatigue/pacing). |
| `ResponseStatsSideEffect` | Response health counters (posts/ads counts by subscription tier, country, blender). |

Loop summary: serve → record (served history, impressions, caches) → those records filter the next request (no repeats) and label training data (Phoenix request cache joins features to eventual user actions) → retrained model changes the next scores.

## 8. `docs/BIDIRECTIONAL_BOOST_CHANGE.md` — parameter evolution case study

The doc walks through the July 2026 "bidirectional follow boost" as a worked example of how algorithm changes appear as diffs:

- **2026-07-10**: A/B test assigns small user cohorts reply-weight boosts of 5/10/15/20 for mutual-follow original posts (most users at 0). A dwell-weight variant was tested alongside and never shipped (still 0.0 today).
- **2026-07-13**: broad launch at **+20.0** — the diff adds a new hydrator (`BidirectionalFollowHydrator`, one social-graph batch call tagging `is_mutual_follow_author`), a candidate field, two params, and ~25 lines in `RankingScorer` swapping the constant reply weight for `reply_weight_for(candidate)`.
- **2026-07-24**: dialed back to **+15.0** — a one-line param diff — after experiment results plus user feedback that World Cup content (mostly from non-followed accounts) was being crowded out.

Takeaways for any ranking system: (1) a major, widely-felt feed change was ~200 lines plus one weight; (2) the mechanism is additive weight on one predicted action for one relationship class, gated to original posts; (3) tuning happened as config-value changes on a days-long cadence, driven by A/B metrics *and* qualitative feedback; (4) because production defaults are cron-synced into `param.rs`, the repo's history doubles as a changelog of the live weight vector.

---

## Quick constants reference

| Constant | Value | Where |
|---|---|---|
| Candidate fetch budgets | Thunder 1200, Phoenix 1000, MOE 200 (off), TweetMixer 800 (off) | `param.rs:4-46,158-163` |
| Max post age | 48h | `params/config.rs:36` |
| Action sequence length | 1024 (scoring and retrieval) | `param.rs:889-900` |
| Engagement signals | 15 per type, 9 types | `param.rs:717-722` |
| Selector K | 50 | `params/config.rs:17` |
| Posts returned | 35 (47 with modules/frames) | `params/config.rs:18-22` |
| Author diversity | decay 0.5, floor 0.25 | `param.rs:228-239` |
| OON discount | 0.75 (0.5 topic; 0.00001 new-user) | `param.rs:246-271`, `config.rs:38` |
| Cold start | ≤1000 followers, <1000 views, boost to rank 15-16 | `param.rs:620-649` |
| DPP diversity | theta 0.65, max rank 150 | `param.rs:608-619` |
| Served-posts exclusion | last 10 min, max 100 ids | `param.rs:1009-1020` |
| Candidate cache | 750 posts, TTL 180s | `param.rs:671-676`, `redis_post_candidate_cache_side_effect.rs` |
| WTF / survey fatigue | 30h / 24h | `param.rs:1000-1005,1065-1070` |
| Scoring audit log sample | 5% of requests | `reranking_kafka_side_effect.rs` |
