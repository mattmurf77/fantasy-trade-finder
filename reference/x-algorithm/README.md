# X For You Feed Algorithm — Reference

> **Purpose:** internal reference on how X's open-sourced For You feed recommendation
> algorithm works, produced so FTF can audit its own trade-suggestion pipeline against it
> and borrow the transferable patterns. The companion audit and enhancement plan live in
> [`docs/plans/trade-relevance-engine/`](../../docs/plans/trade-relevance-engine/).

## Source

- **Repo:** <https://github.com/xai-org/x-algorithm>
- **Snapshot reviewed:** commit `a389166` — "Open-source X Recommendation Algorithm",
  2026-08-13 (the August 13th 2026 release, which added production scoring weights,
  visibility filtering + labeling systems, real Phoenix training code, and SimClusters).
- **License:** Apache 2.0.

## How this review was produced (process)

1. Shallow-cloned the repo locally (2026-08-14) and read the top-level `README.md` to
   map the subsystem layout.
2. Fanned out four parallel research subagents, each assigned one subsystem group, each
   reading the actual source (Rust, Python/JAX, Scala) — not just the READMEs — and each
   writing one of the numbered docs below with repo-relative path + line citations.
3. In parallel, a fifth subagent mapped FTF's own trade generation, ranking, and
   analytics code; that map feeds the audit in `docs/plans/trade-relevance-engine/`.
4. Findings were synthesized into the audit (X's pipeline vs. FTF's, stage by stage) and
   the enhancement plan (interaction-driven trade relevance).

All numeric values quoted in these docs (scoring weights, decay factors, limits) are the
production-synced defaults as of the snapshot date; X notes cron jobs sync prod values
into `home-mixer/params/param.rs`.

## The docs

| Doc | Covers | Answers |
|---|---|---|
| [01-pipeline-architecture.md](01-pipeline-architecture.md) | `home-mixer/`, `candidate-pipeline/` | How a feed request flows: query hydration → sources → hydration → filters → scoring → selection → blending → side effects; the real per-action scoring weights; the served-history/training feedback loop |
| [02-candidate-sourcing.md](02-candidate-sourcing.md) | `thunder/`, `phoenix/` retrieval, `simclusters/`, `phoenix-rankall*/` | How X decides what universe of posts to even consider: in-network recency store + two OON retrieval systems + curated windowed indexes |
| [03-ranking-model-and-signals.md](03-ranking-model-and-signals.md) | `phoenix/` ranking, `vm-ranker/` | The transformer that turns a user's last ~1022 engagement events into per-post action probabilities; how it's trained from logged impressions with zero human labels; DPP diversity re-ranking |
| [04-filtering-and-labeling.md](04-filtering-and-labeling.md) | `visibility-filtering/`, `grox/`, `agatha/`, `bdsm/`, `user-cred-v2/`, `scarecrow/`, `botmaker*/`, enforcement, `under-the-hood/` | The quality/eligibility layer that runs separately from ranking: labels, per-viewer ALLOW/INTERSTITIAL/DROP, negative-feedback loops, reputation scores, transparency |

## The algorithm in one page

Every For You feed is assembled per request:

1. **Hydrate the viewer.** 17 parallel lookups build the viewer context. The dominant
   input is the **user action sequence** — the viewer's last ~1024 engagement events
   (what they faved, replied to, dwelled on, muted…), each carrying the post, author,
   action type, dwell seconds, and timestamp. Plus follows, blocks, mutes, muted
   keywords, seen/served history, topics.
2. **Source candidates in parallel** (~3,000 raw): Thunder returns recent posts from
   followed accounts (pure recency, 48h window); Phoenix retrieval embeds the viewer
   *from their behavior history alone* (no per-user ID embedding) and does
   nearest-neighbor search over curated post indexes; SimClusters finds posts similar to
   ones the viewer recently engaged with, via engagement-graph communities.
3. **Filter before scoring.** 17 deterministic filters: duplicates, stale (>48h), own
   posts, already seen/served, blocked/muted authors, muted keywords, etc.
4. **Score every survivor with one model.** The Phoenix transformer predicts, per post,
   the probability of ~26 distinct viewer actions (favorite, reply, repost, share,
   dwell, follow author … and negative ones: not-interested, mute, block, report). A
   hand-tuned weighted sum collapses those into one score — positives small (favorite
   +0.5, reply +5), negatives huge (report −234). Then: repeated-author decay,
   out-of-network ×0.75 discount, one small-author exploration boost per request.
5. **Select top 50, then check visibility.** A separate service answers
   ALLOW/INTERSTITIAL/DROP per (post, viewer) from labels produced continuously by
   LLM content classifiers, behavioral bot models, aggregate negative-feedback batch
   jobs, and a PageRank credibility score. Out-of-network recommendations face ~26
   extra drop-only rules that followers don't. A DPP pass drops near-duplicate posts.
   ~35 posts are served.
6. **Close the loop.** After serving: served-post history is written (and read back next
   request as a filter), and served posts' full feature snapshots are cached so the
   viewer's subsequent actions on them become tomorrow's training labels — the system
   labels itself from its own outcomes, no human labeling anywhere.

**The five ideas that transfer to any recommender** (including a trade-suggestion engine):

1. **Behavior sequence as identity** — the user *is* their recent action history, not a
   profile they filled out.
2. **Multi-action prediction, explicit blending** — predict many specific user reactions
   separately, then combine with inspectable hand-set weights; negative reactions get
   weights an order of magnitude larger than positives.
3. **Serve → observe → label → retrain** — every impression is a free training example;
   the feedback loop is the product.
4. **Eligibility is not ranking** — a separate, rule-based quality/safety layer decides
   what *can* be shown, with a stricter bar for unsolicited recommendations than for
   requested content.
5. **Managed exploration** — deterministic holdouts, small-author boosts, and an
   "unexplored content" prediction head keep the system from collapsing onto what it
   already knows works.
