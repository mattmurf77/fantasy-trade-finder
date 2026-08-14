# Audit — X's For You Page algorithm vs FTF's trade recommender

> **Purpose:** stage-by-stage comparison of X's open-sourced For You feed pipeline
> (reference docs in [`reference/x-algorithm/`](../../../reference/x-algorithm/)) against
> FTF's trade-suggestion pipeline as it runs today
> ([ftf-current-state.md](ftf-current-state.md)). Output feeds the
> [enhancement-plan.md](enhancement-plan.md).
>
> Written 2026-08-14 against x-algorithm snapshot `a389166` (2026-08-13) and FTF HEAD.

---

## Table of Contents
- [Framing: the two systems are the same shape](#framing-the-two-systems-are-the-same-shape)
- [Stage 1 — User representation](#stage-1--user-representation)
- [Stage 2 — Candidate generation](#stage-2--candidate-generation)
- [Stage 3 — Scoring and ranking](#stage-3--scoring-and-ranking)
- [Stage 4 — Eligibility, quality gates, negative feedback](#stage-4--eligibility-quality-gates-negative-feedback)
- [Stage 5 — Diversity, exploration, fatigue](#stage-5--diversity-exploration-fatigue)
- [Stage 6 — The training feedback loop](#stage-6--the-training-feedback-loop)
- [Stage 7 — Transparency and control](#stage-7--transparency-and-control)
- [Scorecard](#scorecard)
- [Where FTF should NOT copy X](#where-ftf-should-not-copy-x)

---

## Framing: the two systems are the same shape

Both systems answer the same question — *given everything we know about this user,
which items from a large candidate space should we put in front of them, in what
order?* — with the same architecture:

```
X FYP:   hydrate viewer → source candidates → filter → score (learned) → select → visibility check → diversify → serve → log → retrain
FTF:     load boards/prefs → enumerate trades → gate → score (hand-tuned) → select → suppress/fatigue → taste/bandit reorder → serve → log → (mostly nothing)
```

FTF already made the structural leap in the TikTok-discovery build (F1–F10): it has
impression logging with frozen features and propensities, outcome joins, bandits,
fatigue, taste vectors, exploration slots, and offline replay. What it does **not** have
is what makes X's system compound:

1. **A learned ranker in the live path** — X scores every candidate with a transformer
   trained on its own serving logs; FTF's live score is ~130 hand-tuned config keys
   (the learned model, F6, is built but dark).
2. **Rich, unified interaction history as the user representation** — X's model input
   is the viewer's last ~1022 engagement events; FTF's personalization is an Elo board
   plus an aggregate taste vector, while most captured interaction data
   (`user_events`, `sleeper_trades`, `asset_preferences` stream, 28 dropped client
   events) feeds nothing.
3. **A retraining cadence** — X closes serve→observe→label→retrain continuously; FTF's
   loop stops at "logged."

The audit below goes stage by stage. Each stage ends with a verdict: **Par** (FTF has a
domain-appropriate equivalent), **Gap** (X does something FTF should do and doesn't),
or **N/A** (doesn't transfer).

---

## Stage 1 — User representation

**X.** The viewer *is* their behavior sequence: the last ~1024 engagement events (post,
author, action type, dwell seconds, timestamp) feed the model directly; retrieval has no
per-user ID embedding at all — a user with zero history is representable, and taste
shifts show up in the next request. Declared data (topics, demographics) is minor
seasoning. 17 parallel hydrators also load follows, blocks, mutes, muted keywords,
seen/served history. (Ref: `01-pipeline-architecture.md` §2, `03-ranking-model-and-signals.md` §2.)

**FTF.** The user is represented by *explicit, declared* state: a personal Elo board
built from trio swipes (a genuinely stronger elicitation than anything X has — X never
gets to ask "which of these three do you prefer?"), declared outlook, position
preferences, untouchable/target/not-interested lists, stud-tax mode. Behavioral
representation exists but is thin: taste vectors aggregate deck outcomes into decayed
attribute weights (position mix, shape, value bands); trade swipes nudge player Elo at
K=4–20.

**The difference that matters.** FTF's declared layer is excellent and X has no
equivalent — keep it. But FTF's *implicit* layer only sees deck swipes. Board-editing
behavior, calculator sessions, player-page dwell, tier saves, untouchable toggles,
match dismissals, notification taps — all either dropped at ingest (28 unregistered
events) or parked unread in `user_events`. X would treat every one of those as a
sequence token. And FTF knows nothing about what the user valued *before* they arrived
— their league's executed trades and waiver history is sitting in Sleeper's API
(trades already captured in `sleeper_trades`, FA/waiver moves discarded).

**Verdict: Gap** — not in elicitation (FTF is stronger there) but in breadth and use of
implicit signal.

---

## Stage 2 — Candidate generation

**X.** Three sources queried in parallel (~3,000 raw candidates): in-network recency
(Thunder), behavioral two-tower retrieval (Phoenix), engagement-cluster similarity
(SimClusters). The retrieval *universe* is curated at write time — windowed indexes
(24h/48h, min-favorite tiers, evergreen, small-author tail) with visibility checked at
indexing, so ineligible items never enter the pool. (Ref: `02-candidate-sourcing.md`.)

**FTF.** Exhaustive combinatorial enumeration within one league pair (≤3 assets per
side, pool capped at 12 per side), pruned by the 0.97 divergence heuristic, bounded by a
1s/pair deadline. This is *complete* rather than *retrieved*: within its universe, FTF
considers everything, which X cannot.

**The difference that matters.** FTF's universe is structurally small (a league has ~11
opponents), so ANN retrieval is unnecessary — enumeration is the right call. The real
gaps are inside the enumeration inputs:

- **Pool pruning is value-divergence-only.** The 0.97 prune keeps assets the counterparty
  over-values, but nothing seeds pools from *behavioral* interest (players the user
  lingers on, archetypes they like) or *market* reality (`sleeper_trades` shows which
  shapes/positions actually clear in this league — unread).
- **Opponent modeling is thin.** X models the counterparty implicitly (author features,
  engagement patterns). FTF has real opponent boards when they exist, but for unranked
  opponents falls to consensus with a flat 0.3 score scale, and ignores each opponent's
  *observed* trade behavior (their executed trades, their FA habits) entirely.
- X's "curate the index at write time" pattern maps to pre-computing per-league market
  context (pace, positional liquidity) rather than recomputing nothing.

**Verdict: Par on mechanism, Gap on inputs.**

---

## Stage 3 — Scoring and ranking

**X.** One model predicts ~26 action probabilities per candidate (fav, reply, repost,
share variants, clicks, dwell, follow, and negatives: not-interested, mute, block,
report). A hand-tuned weighted sum collapses them: reply +5 (+15 if mutual follow),
copy-link +20, favorite +0.5 … not-interested −43.2, mute −58.8, **report −234**. The
learned part (probabilities) and the editorial part (weights) are cleanly separated;
weights are inspectable, A/B-tuned in days (the bidirectional-boost doc shows a
headline feed change as one param). (Ref: `01-pipeline-architecture.md` §4,
`03-ranking-model-and-signals.md` §3.)

**FTF.** `composite_score` = hand-tuned formula over surpluses and fairness, times a
stack of hand-tuned multipliers (fit, need, block, outlook, lane, aggression), then
bandit × fatigue × taste × diversity at ordering time. The learned analogue —
F6's `P(like)·V_like + P(like)·P(propose|like)·V_propose`, a faithful miniature of X's
`Σ weight·P(action)` — is **fully built and dark**, blocked on an offline replay win
that nobody is running on a cadence.

**The difference that matters.**

- **X's structure is FTF's F6 structure.** The audit's clearest single finding: FTF
  already built the right thing and hasn't turned it on. The path to parity is
  operational (run F8 replay nightly, hit the promotion gate, flip `deck.value_model`),
  not architectural.
- **F6's head list is too short.** X predicts 26 actions including rich negatives; F6
  predicts like and propose|like. FTF logs — today, in `deck_outcomes` — viewed, pass,
  not_interested, undo, dwell_ms, detail_expanded, calc_opened, plus downstream
  propose→accept/decline. Those are unmodeled heads, and the negatives are the
  most valuable: X weights a report at 468 favorites; FTF's flag (`not_interested`)
  enters taste at −4 and otherwise only rides suppression.
- **Positive-signal asymmetry.** X weights *deep* engagement (share-with-a-friend +20)
  over *cheap* engagement (favorite +0.5). FTF's analogue ladder — view < like <
  detail-expand < calc-open < propose < accepted-by-counterparty — exists in the data
  and is only partially expressed (taste rewards; V_propose=6). An *accepted* trade is
  FTF's copy-link-share and should dominate the objective.

**Verdict: Gap** — the machinery exists; the model is dark, and its objective is
narrower than the signals already logged.

---

## Stage 4 — Eligibility, quality gates, negative feedback

**X.** Ranking and visibility are separate services. Visibility answers
ALLOW/INTERSTITIAL/DROP per (post, viewer) from labels produced by independent systems
(LLM classifiers, behavioral bot models, exposure-normalized negative-feedback batch
jobs, PageRank credibility). Two properties stand out: **the bar is stricter for
unsolicited recommendations** (~26 extra drop-only rules for out-of-network content),
and **aggregate negative feedback is exposure-normalized** (agatha labels accounts on
blocks/reports *per favorite*, not raw counts). (Ref: `04-filtering-and-labeling.md`.)

**FTF.** Quality gates are inline hard vetoes in the generation loop — user-gain gate,
junk-filler floor, fairness intervals, lineup feasibility — and they are genuinely
good, arguably the most domain-tuned part of the system. Per-viewer eligibility exists
(untouchables, not-interested, suppressions). What's missing against X:

- **No stricter bar for pushed content.** FTF now has a notification inbox and pushes
  (`notif-inbox-growth`, shipped 2026-08-13). X's lesson: content you *push* needs a
  higher eligibility bar than content the user *requested*. FTF applies the same deck
  logic to both.
- **Negative feedback doesn't aggregate.** A flag hurts one card (suppression +
  taste −4). Nothing rolls up "this *class* of suggestion gets flagged
  exposure-normalized across users" into a global demotion the way agatha rolls
  blocks-per-favorite into account labels. `bad_trade_flags` — the richest negative
  signal, with engine telemetry snapshotted at flag time — is operator-read-only.
- FTF has no adversarial-content problem, so the trust half of X's stack doesn't
  transfer. But "first drop wins, record `decided_by`" observability does: FTF's gates
  reject silently; nobody can query "what did the funnel kill and why" without reading
  code.

**Verdict: Par on gate quality, Gap on push-vs-pull asymmetry and aggregated negative
feedback.**

---

## Stage 5 — Diversity, exploration, fatigue

**X.** Repeated-author decay (×0.625 on the 2nd, floor 0.25), DPP near-duplicate drop
(θ=0.65), one small-author exploration boost per request, an "unexplored content"
prediction head, a deterministic inventory holdout, WTF module fatigue (30h).

**FTF.** Per-target intra-deck cap (3), league-diversity penalty (×0.6 if 3+ members
saw the target in 7d), F3 fatigue (impression-count + recency decay on
hash/centerpiece/archetype), 30-day decline suppression with one retest, F7 wildcard
slot with audition staging (test→general→retired at 30 views), Thompson sampling for
ordering stochasticity.

**Verdict: Par.** This is the stage where the TikTok build already bought X-class
mechanics, scaled sensibly. The one transferable refinement: X *drops* near-duplicates
(DPP) rather than just decaying them — FTF decks can still serve 3 cards that are the
same trade ±1 filler; a cheap package-overlap dedup at ordering time would close it.

---

## Stage 6 — The training feedback loop

**X.** The loop is the product: served impressions cache their full feature snapshot
(3h TTL); the viewer's subsequent actions join against it to become multi-hot training
labels; no human labeling anywhere; 5% of requests log every head probability and the
applied weights as a per-request audit trail; models retrain on the result and
checkpoints roll forward. (Ref: `01-pipeline-architecture.md` §7,
`03-ranking-model-and-signals.md` §4.)

**FTF.** F1 built exactly the right substrate — `deck_impressions` freeze features and
propensity at serve; `deck_outcomes` append labels; `backend/eval/` can replay
counterfactual policies with SNIPS/IPS + ESS gates. Then it stops:

- F8 nightly eval **does** run (inside `/api/cron/daily-tick`, `server.py:16600`,
  results to `data/eval_runs/runs.jsonl`) — but nobody is reading the results against a
  promotion criterion; NEXT.md has carried "graduate or kill `deck.value_model`" since
  2026-08-08.
- F6's nightly refit is gated behind its own flag (`server.py:16618`), so while
  `deck.value_model` is off the model neither trains nor serves — dark means frozen.
- The label set stops at deck actions — proposal *outcomes* (accepted/declined by the
  counterparty, `trade_accepted`/`trade_declined` server events) are logged to
  `user_events` but not joined back to the originating impression, so the most
  business-real label FTF has never reaches a model.

**Verdict: Gap — the decisive one.** Everything else on this list compounds only if
serve→label→retrain→promote actually cycles.

---

## Stage 7 — Transparency and control

**X.** Publishes weights, ships an Under-the-Hood tool showing users the labels
limiting their reach, logs `decided_by` on every drop.

**FTF.** Cards carry `reasons[]`/`narrative` (why the *trade* makes sense) but nothing
explains the *ranking* (why this card is on top today); gates reject without a queryable
trace; users' controls (suppression undo, refresh_fatigue, preference lists) are real
but nothing surfaces "you're seeing this because you liked X / your board rates Y."

**Verdict: minor Gap.** Low urgency, but "why this suggestion" is cheap given
`features_json` already stores the inputs, and it builds the trust that makes users
feed the loop more signal.

---

## Scorecard

| Stage | X mechanism | FTF today | Verdict |
|---|---|---|---|
| User representation | 1024-event behavior sequence as identity | Elo board (stronger elicitation) + thin taste vector; most implicit signal dropped/unread | **Gap** (breadth of implicit signal) |
| Candidate generation | 3 parallel sources, curated indexes | Exhaustive league-pair enumeration (right for domain); behavioral/market inputs absent | Par mechanism / **Gap** inputs |
| Scoring | Learned P(26 actions) × hand weights, negatives dominant | Hand-tuned composite; learned F6 built but **dark**; 2 heads vs ~10 loggable | **Gap** (the big one) |
| Eligibility | Separate service, stricter for pushed recs, exposure-normalized negative labels | Strong inline gates; same bar push vs pull; flags don't aggregate | Par / **Gap** |
| Diversity & exploration | Author decay, DPP, cold-start boost, holdout | Caps, fatigue, suppression, wildcard, auditions | **Par** |
| Feedback loop | Continuous serve→label→retrain, no humans | Logged but not cycled; eval manual; F6 stale; accept/decline labels orphaned | **Gap** (decisive) |
| Transparency | Public weights, Under the Hood | Trade narratives, no ranking explanations | minor Gap |

---

## Where FTF should NOT copy X

Carried forward from the tiktok-discovery guardrails, reaffirmed against X:

1. **North star stays proposals-sent + matches-accepted per weekly active.** X
   optimizes attention (dwell has positive weight); FTF's product succeeds when a trade
   *happens*, not when a user scrolls decks longer. Dwell belongs in FTF's models as a
   *feature and tie-breaker*, never as reward.
2. **Quality gates never relax for engagement** (guardrail #4). X's fairness analogue
   (visibility) is separate from ranking precisely so ranking pressure can't erode it —
   FTF's gate/rank separation must stay as hard.
3. **No fake-infinite inventory.** A league has finitely many good trades; X-style
   endless feed mechanics (aggressive replenishment, compulsion loops) stay out
   (guardrail #3/#16).
4. **Scale honesty.** X's transformer earns its keep on billions of events; FTF's
   event volume supports logistic/GBDT models and bandits, not sequence transformers.
   Copy the *architecture pattern* (multi-head action prediction, explicit value
   blend, off-policy eval), not the model class. Revisit if event volume grows 100×.
