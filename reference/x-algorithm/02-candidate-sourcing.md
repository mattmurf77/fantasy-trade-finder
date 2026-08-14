# X Algorithm — Candidate Sourcing & Retrieval (thunder, phoenix retrieval, simclusters)

Source: the 2026-08-13 open-source release of X's For You feed algorithm. All paths are repo-relative.

**Plain-English summary.** Before any ranking happens, X assembles a candidate pool of roughly 2,000–3,000 posts per feed request from independent sources queried in parallel: Thunder holds the last ~48 hours of posts from every account in memory and returns the newest ~1,200 from the accounts the viewer follows; Phoenix retrieval embeds the viewer's last ~1,024 engagement actions with a transformer and does nearest-neighbor search against a precomputed index of ~10–28M recent posts, returning up to 1,000; SimClusters takes the viewer's ~recent engaged posts as seeds and finds up to 800 posts that similar audiences favorited, via a 145K-cluster "who-engages-with-what" decomposition. The out-of-network index is not "all posts" — a streaming pipeline (phoenix-rankall + a strato event layer) decides which posts even get indexed, gated by engagement thresholds (first favorite, powers of two after that), post type (no replies/reposts/community posts), and a visibility-filtering check at indexing time. The answer to "what universe of items does X consider?" is therefore: everything recent from your follows, plus only the subset of everything else that has cleared engagement + safety gates into a retrieval index, narrowed to what resembles your own engagement history.

---

## 1. The sourcing stage in context (home-mixer/sources/)

The Post Pipeline (`home-mixer/candidate_pipeline/phoenix_candidate_pipeline.rs`) registers seven sources (lines 315–323):

```
thunder_source, tweet_mixer_source, simclusters_source, phoenix_source,
phoenix_topics_source, phoenix_moe_source, cached_posts_source
```

Execution is generic (`candidate-pipeline/candidate_pipeline.rs:256-271`): each source has an `enable(query)` predicate; all enabled sources run concurrently via `join_all`; results are simply concatenated. There is no per-source merge logic at this stage — duplicates across sources are removed later by `DropDuplicatesFilter`, the first pre-scoring filter (`phoenix_candidate_pipeline.rs:345`).

Per-source enablement and default limits (defaults mirrored from production config, `home-mixer/params/param.rs`, sync stamp line 1):

| Source | Enabled when | Max results | Param (line) |
|---|---|---|---|
| Thunder (in-network) | no cached posts | **1200** | `ThunderMaxResults` (param.rs:17-22) |
| Phoenix retrieval (OON) | `EnablePhoenixSource=true`, not in-network-only, no cached posts | **1000** | `PhoenixMaxResults` (param.rs:4-9) |
| SimClusters (OON) | `EnableSimclustersSource=true`, not in-network-only, viewer has engagement signals | **800** | `MAX_RESULTS` const (simclusters_source.rs:25) |
| TweetMixer | `EnableTweetMixerSource` — **default false** | 800 | param.rs:36-46 |
| Phoenix MoE | `EnablePhoenixMOESource` — **default false** | 200 | param.rs:134-163 |
| CachedPosts | previous request left unserved ranked posts | cache cap 750 | `MaxPostsToCache` (param.rs:671-676) |

Thunder and Phoenix max-results pass through `quality_factor::apply(...)` (thunder_source.rs:37, phoenix_source.rs:89), a load-shedding knob initialized `quality_factor::init(70.0, 30.0)` in `home-mixer/main.rs:101` (implementation lives in an unshipped `component_library`; semantics: degrade candidate counts under load rather than fail).

So a typical For You request fans out to ~1200 in-network + ~1800 out-of-network raw candidates before filtering.

## 2. Thunder — in-network posts, held in memory

Thunder (`thunder/`) is a standalone gRPC service that consumes the firehose of post-creation/deletion events from Kafka and keeps recent posts in RAM, keyed by author.

**Data structure** (`thunder/posts/post_store.rs:88-97`): a `DashMap<post_id, CompactPost>` plus three per-author `VecDeque<TinyPost>` maps — `original_posts_by_user`, `secondary_posts_by_user` (replies/reposts), `video_posts_by_user` — and a `deleted_posts` tombstone map.

**Retention & caps:**
- Retention window: `post_retention_seconds` default **172800s = 48 hours** (`thunder/args.rs:48-49`; also `PostStore::default()` at post_store.rs:646). Posts older than retention are rejected at insert (post_store.rs:133-136) and trimmed by a periodic auto-trim loop (post_store.rs:499-604).
- Per-author posting-list cap: **5,000** posts (`MAX_POSTING_LIST_SIZE`, thunder/config.rs:12); oldest evicted first.
- Service-level response caps (`thunder/config.rs:1-8`): **1,200** posts max per request (600 for video requests); following list and exclusion list each truncated to **10,000** entries (`MAX_INPUT_LIST_SIZE`, thunder_service.rs:233-255).
- Per-author read caps per request (`config.rs:5-8`): **50 originals**, **30 replies**, **100 videos**; scan depth 500 newest entries per author (`MAX_TINY_POSTS_PER_USER_SCAN`).

**Query path** (`thunder_service.rs:149-326`): home-mixer sends the viewer's full following list + an `exclude_tweet_ids` list. The store walks each followed author's deques newest-first, skipping excluded IDs (post_store.rs:322-326), then the only "scoring" is `score_recent` — **sort by `created_at` descending, take max_results** (thunder_service.rs:322-326). Thunder is purely recency-based; all real ranking happens downstream.

**Already-seen exclusion:** `ThunderSource` passes `query.seen_ids` as `exclude_tweet_ids` (`home-mixer/sources/thunder_source.rs:31,38`) — Thunder is the *only* source given the seen list; Phoenix and SimClusters repeats are caught later by `PreviouslySeenPostsFilter` / `PreviouslyServedPostsFilter` (root README.md:366). Served-ID memory at the mixer: last **10 minutes / 100 posts** (`ExcludeServedTweetIdsDuration/Number`, param.rs:1009-1020).

**Reply curation in-store** (post_store.rs:339-363): a followed account's reply is only returned if it replies to an original post, or is a reply-to-a-reply-of-the-original where the person being replied to is also followed. Retweets of the viewer's own posts are dropped (post_store.rs:335-337). Three bot/experiment accounts are hard-blacklisted from following lists (@grok, @gork, @products — thunder_service.rs:29-37).

## 3. Phoenix retrieval — out-of-network via two-tower embeddings

**Request side** (`home-mixer/sources/phoenix_source.rs`): requires `query.retrieval_sequence` — the viewer's recent-action sequence — and errors out without it (line 72-75). The sequence is hydrated per request by `RetrievalSequenceQueryHydrator` (`home-mixer/query_hydrators/retrieval_sequence_query_hydrator.rs`) from the User Action Sequence service: max length **1,024 actions** (`MaxSeqLengthRetrieval`, param.rs:895-900), aggregation type `DENSE_WITH_SHORT_DWELL` (param.rs:127-132), dedup/aggregation window 300,000 ms (`UAS_WINDOW_TIME_MS`, params/config.rs:34). New users (action count below `PhoenixRetrievalNewUserHistoryThreshold`, default 0 = disabled) can be routed to a dedicated inference cluster (phoenix_source.rs:25-39).

**Model** (`phoenix/README.md`):
- **User tower** (README.md:98-106): a transformer encodes the engagement history plus one user-features token (country, language, coarse profile). Production retrieval has **no learned per-user ID embedding** (`use_user_embedding=False`) — "the user is represented by what they interacted with."
- **Candidate tower** (README.md:107-113): posts are represented by **semantic IDs** — residual-quantized codes, **6 levels × 256 codes**, derived from each post's multimodal (content) embedding — plus hashed author IDs. Same-topic posts share SID prefixes, so brand-new posts generalize.
- **Hash-based embeddings** (README.md:239-246, table line 408): **2 independent hash functions per entity** into fixed tables — no vocabulary service to maintain; any new ID is representable instantly. Root README lists this as key design decision #3.
- **Index baked into checkpoint** (README.md:114-117): at every checkpoint save the trainer embeds the whole configured corpus and stores `post_embeddings` inside the checkpoint; serving loads it — nothing embeds a corpus at boot.
- **Search** (README.md:118-119): top-K by **dot product** between the user embedding and the index.
- **Training** (README.md:272-274): contrastive, in-batch + 64 sampled global negatives with log-Q correction, **favorites as the positive signal**.

Production retrieval config (README.md table, lines 395-416): embedding dim **1024**, 8 transformer layers, 16/4 GQA heads, history length 1023, candidate index `max_posts` **10.24M** (**28.67M** on the combined config). (Ranking model for contrast: dim 2560, vocab 100M posts / 30M authors.)

**Candidate count:** up to `PhoenixMaxResults` = **1000** per request (quality-factor scaled). A separate `PhoenixTopicsSource` reuses the same dispatch for topic-constrained requests, and `PhoenixMOESource` (off by default) adds a 200-candidate mixture-of-experts variant.

## 4. SimClusters — engagement-pattern clustering

SimClusters is the older Twitter system, retained as a third source "alongside Thunder and Phoenix retrieval" (root README.md:39).

**Offline construction** (`simclusters/simclusters_v2/`): community detection over the follower graph assigns ~**20M** influential producers to ~**145K** clusters (model version string `20M_145K_2020`, `simclusters_v2/common/ModelVersions.scala:7-9`). `KnownFor` = which clusters an account is known for; `InterestedIn` is computed from follows of KnownFor accounts (`scalding/InterestedInFromKnownFor.scala`, weekly batch, 30-day lookback — lines 41-42). Post embeddings accumulate from who favorites the post (log-fav weighted), giving each post a sparse vector over clusters.

**Online source** (`home-mixer/sources/simclusters_source.rs`): post-to-post ANN, seeded by the viewer's recent engagements rather than a user profile:
- Seeds: the viewer's explicit + implicit engagement signals (favorites, replies, shares, video watches …), hydrated per request with **max 15 per signal type** (`EngagementSignalsMaxPerType`, param.rs:717-722), deduped, most-recent first (simclusters_source.rs:149-173).
- Each seed post queries the SimClusters ANN service (`simclusters/simclustersann/`) with (simclusters_source.rs:24-35, 175-196): source embedding type `LOG_FAV_LONGEST_L2_EMBEDDING_TWEET`, candidate type `LOG_FAV_BASED_TWEET`, model `MODEL_20M_145K_2020`, **200 results per query**, scan at most **50 clusters**, top **800 posts per cluster**, candidate age **0–48 hours**, cosine similarity.
- Scoring (`simclustersann/candidate_source/ApproximateCosineSimilarity.scala:73-131`): for every cluster shared between the seed's embedding and the index, accumulate `postScore × sourceClusterScore`, then cosine-normalize; hard cap 1,000 results (`MaxNumResultsUpperBound`, line 32).
- Budgeting back in home-mixer: **10,000** total ANN candidates across all seed queries (`MAX_SANN_CANDIDATES`), per-candidate min score **0.5** (`POST_ANN_MIN_SCORE`), results interleaved round-robin across seeds and truncated to **800** (simclusters_source.rs:95-136). ANN responses are cached 10 minutes per seed post (2M-entry Moka cache, lines 50-56).
- A dedicated pre-scoring filter, `OONNsfwSimclustersFilter`, drops SimClusters posts whose author is flagged for adult content when the viewer doesn't follow them (root README.md:352).

## 5. phoenix-rankall + strato layer — maintaining the retrieval index

The Phoenix candidate index is not "all posts"; it is a set of **named, windowed sub-indexes** maintained by a streaming pipeline.

**phoenix-rankall** (`phoenix-rankall/src/`) is a Rust Kafka consumer that materializes windowed snapshot stores (dumped every **180 s**, keeping 3 versions — `config/mod.rs:38-42`) from indexing events on topic `phoenix_rank_all_indexing_event` (config/mod.rs:118-126). The Main pipeline's windows (`config/mod.rs:141-156`) define the corpus:

- `post_creation` 24h (every eligible new post, no engagement needed)
- `1fav` 24h and 48h (posts with ≥1 favorite)
- `32fav` 24h (posts with ≥32 favorites)
- `video` 48h / 96h / 7d / 14d / 30d; `nsfw_video` 48h / 7d
- `evergreen_video` 5 years; `evergreen_video_grok` 30d
- Topic pipeline: `1fav_topic` + 5 experiment variants, 24h (config/mod.rs:157-165)
- SID pipeline hydrates **semantic IDs (6 levels)** for indexed posts via a lookup service, with a backfill loop (batch 5,000, ≤800k/cycle, 30 s interval, 1 h max age — config/mod.rs:72-85)
- `sid-tail` 24h: a small-author index restricted to authors with ≤**1,000 followers** (`tail_max_author_followers`, config/mod.rs:87-88) — an explicit new/small-creator discovery inventory.

**phoenix-rankall-strato** (`phoenix-rankall-strato/`) is the event layer deciding *which* posts emit indexing events:

- **Post creation** (`columns/phoenix_rank_all/postCreationEventProcessor.strato`): every new post triggers a `PostCreation` indexing request.
- **Favorites, rate-limited by powers of two** (`columns/favoriteEventProcessor.strato:14-64`): a post re-triggers indexing only when its favorite count crosses the next power-of-two threshold, with guards (`lib/eventProcessing.strato:28-36`): ≥1 minute between updates, engagement window closes 48 h after first update, max post age **49 h**, max engagements 2^30, `minEngagements` 32 (used by the 32fav gate).
- **Eligibility gate at indexing time** (`columns/phoenix_rank_all/phoenixRankAllCandidateProcessor.strato:381-487`): community posts, replies, and reposts are skipped entirely (the OON corpus is originals only). Each post is checked against **visibility filtering** before indexing — `shouldDropPostByVF` calls the VF service with safety level `TimelineHomeRecommendations` (`lib/eventProcessing.strato:246-265`) — and against NSFW content annotations. Dropped/adult posts are excluded from the main indexes (adult immersive video is diverted to the separate `nsfw_video` index). Video indexes require valid immersive video **>10 s** and non-NSFW media (eventProcessing.strato:24, 125-138).
- **Topic indexes** filter a post's model-derived topic entity IDs against the author's own category profile — either curated author lists or an analysis of the author's last **15** original/quote posts with category-share thresholds **0.90 / 0.75 / 0.50** for experiment options 3/4/5 (eventProcessing.strato:461-465, 516-556).

Net effect: filtering is applied twice — cheaply at indexing time (so bad content never enters the OON candidate universe) and again per-viewer at request time (blocks/mutes/VF post-selection filters).

## 6. In-network vs out-of-network proportions

There is **no fixed quota** for feed composition; the mix emerges from three mechanisms:

1. **Retrieval budgets** — in-network 1,200 vs OON 1,000 + 800 (+200 MoE when on) ≈ **40% / 60% of the raw candidate pool** at default params (see table in §1).
2. **A scoring discount, not a slot allocation** — `OonWeightFactor = 0.75` (param.rs:246-251): OON posts' final scores are multiplied by 0.75; the same discount applies to replies/reposts even from followed accounts (`EnableOonRescoreForInNetworkRepliesRetweets = true`, param.rs:260-265). Topic requests use a stronger 0.5 (`TopicOonWeightFactor`, param.rs:266-271). Everything else is a single ranked list from one model.
3. **Asymmetric filtering** — several pre-scoring filters only hit OON candidates: `OONRetweetReplyFilter`, `OONNsfwSimclustersFilter`, `NewUserMinEngagementFilter` (OON posts below an engagement floor for brand-new accounts), and the OON-only visibility-filtering rule set that drops (e.g. high-recall spam) content for non-followers while allowing it to followers (root README.md:342-381).

Uniform recency bound across all sources: `AgeFilter` at **48 hours** (`home-mixer/params/config.rs:36`), matching Thunder's retention and the main index windows.

## 7. Reading this against a trade-suggestion engine

The transferable pattern is the two-stage funnel with an explicitly curated candidate universe:

- **Cheap exhaustive source for the "following" analog** — Thunder is just "everything recent from your graph, newest first, capped per author"; ranking quality lives entirely downstream. (FTF analog: all plausible 1-for-1s inside a league = enumerate, cap per manager, let the ranker sort.)
- **Eligibility gating at index-build time, not query time** — X decides at ingestion which posts may ever be recommended (engagement threshold, no replies/reposts, safety check), keeping the ANN corpus small (~10–28M of the vastly larger post stream). (Analog: precompute which trade shapes/assets are even proposable — fairness-band, roster-fit gates — before any per-user scoring.)
- **Represent the user by behavior, not identity** — retrieval has no per-user embedding; the viewer is the sequence of their last ~1,024 actions. Cold-start degrades gracefully to profile features.
- **Multiple redundant retrievers with per-source caps, merged by concatenation + dedup, ranked jointly** — no source-level score arbitration; a single downstream model plus a scalar OON discount governs the blend.
- **Seen/served suppression is layered**: source-level exclusion where cheap (Thunder), filter-level elsewhere, with a 10-min/100-item served-history window preventing intra-session repeats.
