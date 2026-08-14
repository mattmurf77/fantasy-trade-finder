# X Algorithm — Visibility Filtering, Labeling & Trust Systems

X separates "how good is this post for this viewer" (ranking) from "is this post allowed to be shown to this viewer at all" (visibility filtering) — two different services with different inputs. Ranking orders posts; visibility filtering then answers ALLOW, INTERSTITIAL, or DROP per (post, viewer) pair, reading safety labels that a whole constellation of offline and event-driven systems attach to posts and accounts: LLM classifiers at publish time (grox), batch models of how other users react to an account (agatha — blocks and reports relative to favorites), a behavioral-sequence bot detector (bdsm), a PageRank-style reputation score (user-cred-v2), an event-driven rule engine (scarecrow/botmaker), and an enforcement service that converts model scores into labels, challenges, or suspensions. A key structural idea throughout: recommendations to strangers are held to a much stricter bar than posts shown to people who chose to follow the author, and a user's own negative actions (block, mute, report, "not interested") feed back both into what *they* see (hard drops, big negative ranking weights) and into what *everyone* sees (aggregate labels on the offending account).

Source: local clone of the 2026-08-13 x-algorithm release. All paths repo-relative.

---

## 1. The ALLOW / INTERSTITIAL / DROP model

Visibility filtering (`visibility-filtering/`) is called after ranking, per post and viewer, and returns one of three verdicts (README.md:188-215):

- **ALLOW** — show normally.
- **INTERSTITIAL** — show behind a tap-through warning (adult/graphic media). The post stays in the feed.
- **DROP** — remove. `home-mixer/filters/vf_filter.rs` removes dropped posts, and `AncillaryVFFilter` also removes any post whose thread ancestor, quoted post, or reposted post was dropped.

### Per-viewer inputs

The decision is not a property of the post alone. Every rule evaluates against a `RuleContext` combining:

- **Post safety labels** — `visibility-filtering/models/safety_labels.rs` (a map of `SafetyLabelType` → label).
- **Author account state and labels** — suspended/deactivated/protected, NSFW flags, account-level `UserLabelSet`.
- **Viewer↔author relationship** — `visibility-filtering/models/relationship.rs:1-7`: `viewer_blocks_author`, `viewer_mutes_author`, `viewer_follows_author`, `viewer_mutes_retweets_from_author`.
- **Viewer settings and identity** — `visibility-filtering/models/viewer.rs`: logged in/out, `allows_sensitive_media`, country code, and age (`ADULT_AGE_YEARS = 18`, viewer.rs:17).

So the same post can be ALLOW for one viewer, INTERSTITIAL for another, and DROP for a third.

### Two rule sets: followers vs. recommendations

`visibility-filtering/rules/registry.rs:26-30` defines three safety levels: `FilterAll` (drop everything — used e.g. when the index must exclude a post), `TimelineHome` (in-network: viewer follows the author), and `TimelineHomeRecommendations` (out-of-network recommendation).

`home-mixer/candidate_hydrators/vf_candidate_hydrator.rs:66-103` splits each request's candidates: in-network posts are checked at `TimelineHome`, OON posts — plus all thread ancestors and quoted posts — at `TimelineHomeRecommendations`.

**Base rules (both surfaces)**, in evaluation order (`registry.rs:101-132`):
suspended/deactivated/erased/offboarded author → protected author → **viewer blocks author** → **viewer mutes author** → muted-retweets → PDNA (known child-safety media) → bounced post → spam → emergency-use → four FOSNR ("freedom of speech, not reach") label drops (hateful conduct, violent speech, abuse, civic integrity) → nullcast → stale → legal takedowns → sensitive-media age gates (logged-out / under-18 / no-stated-age viewers in 16 gating countries, `rules/nsfw_age_gating.rs:5-7`) → exclusive (subscriber-only) content → then the interstitial rules (NSFW high-precision, gore/violence, NSFW card image, NSFW-flagged author with media).

**Recommendation-only additions** (`registry.rs:138-170`) — 26 extra rules appended after the base set, and they can only DROP: DMCA / geo-restricted media, NSFW author flags (user- or admin-set), NSFW tweet flags, NSFW high-recall / high-precision / card-image / text labels, gore high-precision, do-not-amplify, malicious URL, **spam high recall**, FOSNR abuse-insults, plus account-level label drops (NSFW high recall/precision/near-perfect, spam high recall, compromised, read-only, impersonation, NSFW avatar/banner, abusive high recall, do-not-amplify non-follower).

The registry tests spell out the asymmetry: `SpamHighRecall` allows in-network but drops OON (registry.rs:419-454); an NSFW author interstitials in-network but drops OON (registry.rs:334-378); `AbusiveHighRecall` allows a follower on both surfaces but drops an OON non-follower (registry.rs:798-848). High-recall (cheap, over-triggering) classifiers gate only the algorithmic amplification surface; people who opted in by following still see the content.

### Evaluation semantics — first drop wins

`visibility-filtering/rules/mod.rs:86-110` (`evaluate_rules`):

- Rules run in registry order; the **first DROP short-circuits** and its rule name is recorded as `decided_by`.
- INTERSTITIAL does not short-circuit: the **first** interstitial verdict is remembered, later rules keep running, and a later DROP still wins over an earlier interstitial.
- If nothing fires: ALLOW with `decided_by = None`.

Two systematic exemptions are built into the rule types: post-label drop rules take `exempt_author` (an author always sees their own labeled post — `rules/tweet_label_drops.rs:7-44`), and account-label drop rules take `require_non_follower` (`rules/user_label_drops.rs:7-27`). FOSNR labels never drop for the author (registry.rs:556-582).

---

## 2. How labels get created (the labeling path)

Labels are produced continuously off the request path, written to storage, and read back at serving time (README.md:155-215).

### grox — LLM classifiers at publish/traction time

`grox/` is a Python streaming service that runs Grok/Gemma prompts over posts. Flows (`grox/flows/`): `ptos` ("post terms of service" safety: policy prompts for adult content, child safety, hate/abuse, violent speech/media, illegal behaviors, spam, suicide/self-harm — `grox/flows/ptos/prompts.py`), `reply_spam` (coordinated spam, reply ranking), `upa`, and `mm_emb` (multimodal post embeddings). Posts enter via Kafka topics gated on minimum traction/impressions (`grox/flows/ptos/constants.py`, `HIGH_FAV_THRESHOLD = 128`). The result sink (`grox/flows/ptos/task_write_safety_post_annotations_result_sink.py:29-64`) doesn't just record annotations — it can **apply safety labels directly** (`StratoApplyLabelFromPtos`), bounce posts for self-harm encouragement, send support messages, and suspend accounts for child sexual exploitation. The actual `.j2` prompt templates are withheld from the release to reduce gameability (prompts.py:12).

### agatha — batch models of how others react to an account

`agatha/` is a Scalding (Hadoop) batch stack that labels accounts from **other users' negative reactions normalized by positive ones**. Label generators (`agatha/scalding/labels/AgathaLabelManager.scala:12-21`): `ReportsPerFav`, `AllSpamReportsPerFav`, `SpamReportsPerFav`, `BlocksPerFav`, `SpamSuspended`, `NSFW`. Build jobs (e.g. `agatha/scalding/RateBasedBuildJob.scala:23-30`) train over 30 days of active-user features using PMI-crossed feature statistics (`agatha/hub/pmi/PMI.scala`); predict jobs score all active users. Scores are consumed downstream by name, e.g. a botmaker rule fires when `AgathaAllSpamReportsPerFav > 0.9975` or `AgathaSpamSuspended > 0.98` (`botmaker-rules/scarecrow/bot/AgathaSpamProduction__ApplySearchTopTweetLabel.bot`), and agatha's calibrated NSFW score is an input feature to the pnsfwmedia media classifier.

### bdsm — behavioral-sequence bot detection

`bdsm/` (README.md) is a bidirectional transformer over an account's recent **action sequence** (512 actions, time-aware rotary embeddings so mechanical cadence/burstiness is representable). Eight task heads: FollowBot, LikeBot, EngagementAmplifier, ReplySpamBot, TweetSpamBot, RTBot, MultiActionBot, LegitimateUser. A streaming pipeline (Kafka → Rust accumulator → prefetcher → GPU scorer → results sink) scores accounts as events arrive. The sink applies **graduated actioning**: per-head thresholds route to challenge (Arkose/captcha/liveness check) at "cusp" scores vs. suspension above the full threshold, with a 30-action minimum before any enforcement (`bdsm/runtime/sink_policy.yaml:5`). The tuned operating points are redacted (9.99 sentinels) to hide the evasion boundary.

### user-cred-v2 — PageRank reputation

See section 4.

### scarecrow + botmaker — event-driven labeling rules

`scarecrow/` is the always-on rule service; it embeds `botmaker/` (a compiled DSL: ANTLR grammar, compiler, runtime) and loads rules from `botmaker-rules/scarecrow/` (20 published `.bot` rules + 53 derived features; some rules withheld). A rule is `event → condition → action`. Example: `botmaker-rules/scarecrow/bot/nsfw_user_write_user_label.bot` — on a `health_side_effect` event with sub-event `nsfw_user`, apply `NSFW_HIGH_PRECISION` and `NSFW_HIGH_RECALL` account labels. Rules routinely apply labels with TTLs (e.g. `AGATHA_SPAM` for one week) and carry guard conditions: not a test user, not gray-verified, and **not a high-PageRank user**.

### abuse-enforcement-service — model scores → actions

`abuse-enforcement-service/` evaluates YAML rule files (mirrored from a dynamic config system) against score events about a user or post. Ordered rules, first match; `skip` guards run first: allowlisted, **high follower count**, and `cred.is_high || cred.score >= 50.0` — a good reputation score short-circuits automated enforcement (`service-lib/rules/enforcement_user.yaml:17-30`, `enforcement_post.yaml:24-37`). Then action rules: e.g. `llm_slop_user` in score labels → apply `SpamHighRecall` account label with 30-day TTL; `gibberish_post` → `SpamHighRecall` post label; `anchor_campaign_suspend` → suspend; cusp labels → Arkose/captcha/liveness challenges instead of suspension (`enforcement_user.yaml:33-105`).

### safety-label-user-agg — rolling post labels up to accounts

`safety-label-user-agg/` escalates repeated post-level offenses to the account level. On each applied `TweetSafetyLabelEvent`, the processor (`safetyLabelToUserLevelAggregationV2Processor.strato:14-80`) loads config-driven rules, scans the author's recent timeline (window capped at 10 posts, up to 4x for media-only conditions), counts posts matching label selectors, and if the condition holds (e.g. N of the last M posts labeled NSFW) applies an **account** label — restricted to `POSSIBLY_NSFW_ACCOUNT` or `NSFW_HIGH_PRECISION`, TTL ≤ 7 days (`postToUserLabelRules.strato:96-107`). Exclusions again include `highPageRankOrGreyBadge` (postToUserLabelRules.strato:131-139). Bounded config everywhere: ≤10 rules, ≤60-day post age, etc.

---

## 3. Negative user feedback in labeling and ranking

Negative actions are used three distinct ways:

1. **Hard per-viewer removal (my blocks/mutes shape my feed).** Blocked/muted authors are filtered pre-scoring (`AuthorSocialgraphFilter`, README.md:359) *and* again in visibility filtering (`ViewerBlocksAuthorRule`, `ViewerMutesAuthorRule`, `MutedRetweetsRule` — `visibility-filtering/rules/socialgraph_rules.rs`). Muted keywords are a pre-scoring filter too. These are deterministic viewer-specific gates, not scores.

2. **Ranking penalties (my *predicted* negative reactions demote posts for me).** Phoenix predicts, per post, the probability the viewer will hit "not interested", mute, block, report, or bounce without dwelling; `RankingScorer` folds these in with large negative weights (`home-mixer/params/param.rs:425-446`): not interested **-43.2**, block author **-31.2**, mute author **-58.8**, report **-234.0**, not-dwelled -0.02 — versus favorite +0.5, reply +5.0, repost +1.0 (param.rs:282-296). A single predicted report outweighs hundreds of predicted likes; negative feedback is rare, so the weights are scaled up to make it decisive.

3. **Aggregate labeling (everyone's negative actions shape what the offender can reach).** agatha turns population-level blocks/reports-per-favorite into account scores; botmaker rules and abuse-enforcement convert those into `SPAM_HIGH_RECALL`-class labels; visibility filtering then removes that account's posts from *recommendation* surfaces for all users (section 1). The loop: many users report/block → account labeled → account's posts stop being recommended to strangers — while followers still see them.

---

## 4. user-cred-v2 in detail

`user-cred-v2/` is a daily Scalding job computing PageRank over a combined graph:

- **Nodes**: all accounts that are not restricted/deactivated/suspended/erased (`ValidUserInfo.scala:22-26`); "near-zero" (inactive-state) accounts are kept as sinks but excluded as edge destinations (`UserCredV2App.scala:287-318`).
- **Walk edges**: the follow graph (`FlockFollowsJavaDataset`, `UserCredV2App.scala:24-28`) — following someone passes reputation mass to them.
- **Teleport distribution** (the personalization vector): a 50/50 blend (`engagement_teleport_beta` default 0.5, `UserCredV2Config.scala:35`) of (a) a uniform distribution over **premium/verified accounts only** (`UserCredV2App.scala:174`), and (b) engagement-weighted mass: each engager distributes their own prior mass across authors they favorited/retweeted in the last **7 days**, in proportion to engagement counts (`UserCredV2App.scala:79-100, 141-193`). So random-jump probability flows toward verified accounts and accounts that recently earned real engagement, weighted by the credibility of the engager — engagement from high-cred users counts more.
- **Anti-gaming edge filter**: edges between accounts flagged as linked (same operator, from an account-expansion investigation dataset) are removed before both graphs are built (`UserCredV2App.scala:110-118`) — you can't boost your own alt.
- **Iteration**: standard power iteration with jump probability α=0.2, warm-started from last week's snapshot, until L1 diff < 0.001 or 50 iterations (`UserCredV2Config.scala:30-33`, `UserCredV2App.scala:195-270`).
- **Score**: `score = clamp(165.2 + 7.07 * ln(mass), 0, 100)` (`UserCredV2.scala:10-17`) — a log-mass affine mapping to 0-100.
- **Snapshot safety gate**: before publishing, row count, mass sum (must be in [0.99, 1.005]), and counts above score 55/90 are compared to the previous snapshot; on failure the snapshot goes to quarantine instead of production (`SnapshotSafeguard.scala`, `UserCredV2App.scala:392-430`).

**How the score is used — as a shield, not a boost.** In this repo the score never raises ranking; it *exempts* accounts from automated punishment:
- botmaker's `IsHighPageRankUser` derived feature: `score >= 54` (threshold in `botmaker-rules/scarecrow/derived-feature/HighPageRankThreshold.df`) or a `PREDICTED_HIGH_PAGE_RANK` label, with a >25k-follower fallback when no score exists (`IsHighPageRankUser.df`); spam-labeling rules require `!IsHighPageRankUser`.
- abuse-enforcement-service skips enforcement when `cred.score >= 50` (`enforcement_user.yaml:24-30`).
- safety-label-user-agg excludes `highPageRankOrGreyBadge` users from post-to-account label escalation.

The rationale: false-positive enforcement on a reputable, well-connected account is far more costly than on a fresh throwaway, and reputation is expensive to fake because it flows through verified accounts and credibility-weighted engagement.

---

## 5. Under the Hood transparency tool

`under-the-hood/` builds the per-account label-transparency report at `x.com/i/under_the_hood` (README.md:425-429), designed to compensate for the withheld prompts/rules: users can see the *outputs* (which labels their account and posts carry) and match them to the open rule code.

- **Daily collection jobs** (Scalding): `UthDailyPostsJob.scala` joins each day's posts against the tweet-safety-label dataset and label events, tracking per post-label per day how many of the account's posts **carried** vs. had the label **removed**; `UthDailyAccountLabelsJob.scala` replays gizmoduck user-label modification events against a seed snapshot to compute which account labels were active on each day.
- **Monthly aggregation**: `UthUserMonthMhPublisherJob.scala` / `UthReferenceMonthMhPublisherJob.scala` roll dailies into per-user month aggregates (`UthUserMonthAggregate` in `thrift/uth_serving.thrift:70-78`: eligible-post counts per day, post-label carried/removed per day, account-label active days) plus reference-population percentile stats (`UthRateStats`: mean/p10..p99 by follower-count class) so a user can compare their label rates to peers.
- **Serving**: a Strato column gated to the **authenticated viewer's own account** (`strato/columns/underTheHoodReport.strato:9-19`, `accessPolicy = AllowTwitterUserId`). Eligibility checks in `underTheHoodReport.User.strato:16-20`: account ≥ 1 year old and ≥ 10 posts in the reporting month; reports publish ≥ 10 days after month end.

---

## 6. Media/content classifiers (short)

- **clip/** — trains the CLIP-style image+text embedding model; its media embeddings are the shared input representation for the media classifiers.
- **media-model-proxy/** — a proxy service that loads media from blob storage once and fans out inference to multiple media models (adult content, violence/gore, hateful symbols, known-media matching), returning scores to the caller; it stores nothing itself (`media-model-proxy/README.rst`).
- **adult-content/** — training + isotonic-regression calibration for the adult-media classifier (`adult-content/calibration.py`).
- **pnsfwmedia/** — a small "probability NSFW" model that concatenates the CLIP media embedding with **account-level** signals — agatha's calibrated NSFW score, an NSFW-text score, the NSFW-consumer-follower score, and log follower count — through batch-norm + one dense layer + sigmoid (`pnsfwmedia/model_experimental.py:50-92`). Media evidence and author reputation are combined in one calibrated score.
- **grox mm_emb** — multimodal post embeddings produced at publish time for downstream models.

These produce the `NSFW_HIGH_PRECISION` / `NSFW_HIGH_RECALL` / gore labels that visibility filtering's interstitial and OON-drop rules key on.

---

## Transferable ideas (for a trade-suggestion engine)

1. **Quality gates separate from ranking** (README.md:451-453, "Key Design Decisions #4"). Trade candidates could be scored for mutual gain by one system while a separate rule registry answers "is this trade allowed to be *suggested* at all" (roster-illegal, league-rule-violating, obviously lopsided) — ordered rules, first drop wins, with a `decided_by` audit trail for every suppressed suggestion.
2. **Per-viewer eligibility.** X's verdict depends on (post, viewer): relationship, settings, age, country. Analog: the same trade can be suggestable to one manager and not another (their do-not-trade lists, blocked partners, risk settings) — evaluate eligibility against the receiving user's context, not just the item.
3. **Stricter bar for unsolicited recommendations.** X allows content to followers that it refuses to *recommend* to strangers, and uses cheap high-recall classifiers only on the recommendation surface. Analog: a proactively pushed trade suggestion should pass stricter fairness/quality thresholds than one a user explicitly requests or builds manually.
4. **Negative-feedback loops at two levels.** Per-user: a dismissed/"not interested" trade type should carry a large negative weight relative to positive signals (X: report = -234 vs. like = +0.5). Aggregate: many users rejecting suggestions involving a pattern (e.g. a stale player valuation) should label and suppress that pattern for everyone — normalized by exposure, as agatha normalizes blocks/reports by favorites.
5. **Reputation as an enforcement shield with anti-gaming.** user-cred-v2's score exempts trusted accounts from automated punishment, flows only through hard-to-fake channels (verified accounts, credibility-weighted engagement), strips same-operator edges, and gates each snapshot before publishing. Any user-trust score should similarly bias toward false-negative enforcement on established users and be validated against its prior snapshot before going live.
6. **Transparency by aggregate output.** Where rules must stay hidden (anti-gaming), Under the Hood shows each user the labels applied to *them*, with peer percentiles. Analog: show users why trades were or weren't suggested to them, in aggregate, without exposing the exact thresholds.
