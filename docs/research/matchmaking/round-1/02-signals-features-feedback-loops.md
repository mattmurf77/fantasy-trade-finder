# Signals, Feature Engineering, Preference Learning, and Feedback Loops in Dating/Matchmaking Apps

> Research memo — Round 1, Topic 02. Companion memos cover core matching algorithms (01) and marketplace dynamics (03); this one stays on **what signals the apps collect, which ones carry predictive weight, how preferences are learned from behavior rather than declarations, and how the outcome feedback loop is engineered**.
>
> Date: 2026-08-15. Sources: ~30, full list at bottom.
>
> **Confidence flags used throughout:**
> - `[OFFICIAL]` — documented by the company itself (press release, help center, engineering blog, conference talk, patent)
> - `[ACADEMIC]` — peer-reviewed study or large-N dataset analysis
> - `[REVERSE-ENG]` — credible third-party teardown, journalist access, or inference from ML first principles; directionally reliable, details uncertain
> - `[SPECULATIVE]` — plausible but weakly evidenced; treat as hypothesis

---

## TL;DR (the five findings that matter most)

1. **Behavior beats declarations, decisively.** Every credible study finds stated preferences ("wish lists," filters, questionnaires) have little to no bearing on who users actually contact — a 41,936-user QUT study found most users contacted people bearing "no resemblance whatsoever" to their stated ideal ([ScienceDaily](https://www.sciencedaily.com/releases/2017/02/170221110744.htm)) `[ACADEMIC]`. Apps therefore treat swipe/contact history as the strongest signal and stated preferences mainly as hard filters plus a cold-start prior.
2. **Pre-interaction trait similarity predicts almost nothing.** The landmark Joel/Eastwick/Finkel machine-learning study (random forests over 100+ traits and preferences from speed daters) could predict who is generally desirable and who generally desires others — but essentially **zero** of the pair-specific "chemistry" variance ([Psychological Science 2017](https://journals.sagepub.com/doi/10.1177/0956797617714580)) `[ACADEMIC]`. This is the empirical death sentence for questionnaire-similarity matching and the reason the industry migrated to behavioral/interaction signals.
3. **The winning label is the furthest-downstream outcome you can cheaply observe.** OkCupid's success label was the 4-message conversation; Hinge pushed the label all the way to "did a real-world date happen and was it good" via the We Met prompt — an explicit, low-friction outcome-collection feature that they credit with materially better recommendations ([Engadget](https://www.engadget.com/2018-10-16-hinge-we-met-first-date-ai.html), [HBS analysis](https://aiinstitute.hbs.edu/platform-rctom/submission/hinge-and-machine-learning-the-makings-of-a-perfect-match/)) `[OFFICIAL]`. Everyone who trains on shallow labels (impressions, right-swipes) ends up optimizing engagement, not matching.
4. **Degenerate feedback loops are the #1 structural failure mode.** Collaborative filtering + behavioral learning means the model shows you X, you engage with X (it's all that's offered), and the model concludes you love X. DeepMind formalized this (echo chamber vs filter bubble) and showed **random exploration + growing the candidate pool** are the effective countermeasures ([arXiv 1902.10730](https://arxiv.org/abs/1902.10730)) `[ACADEMIC]`. The Monster Match project demonstrated the same dynamic specifically in dating-app collaborative filtering ([massivesci.com](https://massivesci.com/notes/monster-match-bias-online-dating-collaborative-filtering-algorithm/)) `[ACADEMIC/DEMO]`.
5. **Reciprocity is the single biggest scoring upgrade.** Moving from "will A like B" to "will A like B × will B like A (× will a real interaction follow)" roughly doubled top-10 recommendation success in the canonical RECON study (23% → 42%) and helped cold-start too ([RECON, RecSys 2010](https://dl.acm.org/doi/10.1145/1864708.1864747)) `[ACADEMIC]`. This is signal-side as much as algorithm-side: it forces you to collect and weight *both parties'* negative and positive signals.

---

## 1. The signal taxonomy: what apps actually collect

### 1.1 Explicit signals (user tells you)

| Signal | Who uses it | Notes | Confidence |
|---|---|---|---|
| Hard filters (age, distance, gender; height/religion/kids on Hinge) | All | Applied as constraints, not preferences; "rarely overridden by algorithms" | `[OFFICIAL/REVERSE-ENG]` ([nsokolsky teardown](https://nsokolsky.substack.com/p/how-dating-app-algorithms-likely)) |
| Questionnaires (OkCupid match questions, eharmony 29 dimensions) | OkCupid, eharmony | Weak predictors of outcomes (see §3); OkCupid's own experiments showed the *displayed* match % drove behavior as much as the real one | `[ACADEMIC/OFFICIAL]` |
| Dealbreaker vs preference distinction | Hinge | Hinge separates hard dealbreakers from soft preferences the model may trade off | `[REVERSE-ENG]` ([datafield.dev](https://datafield.dev/blog/dating-app-algorithms.html)) |
| Super-likes / roses / hearts | Tinder, Hinge, The League | Costly explicit signal — scarcity makes it higher-precision than a plain like | `[OFFICIAL]` |
| Post-date surveys ("We Met" — did you meet, would you see them again) | Hinge | The crown-jewel explicit signal: a ground-truth outcome label | `[OFFICIAL]` |

### 1.2 Implicit signals (user shows you)

Roughly in ascending order of cost-to-fake / descending order of volume:

1. **Impressions + swipe direction** (like/nope). Tinder officially: "Likes and Nopes are obviously key pieces of insight into what members like" ([Tinder press room, 2019](https://www.tinderpressroom.com/powering-tinder-r-the-method-behind-our-matching)) `[OFFICIAL]`. But raw right-swipe direction is noisy at scale — in some demographics users right-swipe on a majority of profiles, so the *rate-adjusted* swipe (this user's selectivity baseline) is what carries information `[REVERSE-ENG]`.
2. **Dwell time / profile view duration.** Lingering 45 seconds vs 3 seconds on a profile discriminates attention even when both end in a left-swipe; teardowns consistently list it among the strongest implicit signals ([datafield.dev](https://datafield.dev/blog/dating-app-algorithms.html), [nsokolsky](https://nsokolsky.substack.com/p/how-dating-app-algorithms-likely)) `[REVERSE-ENG]`.
3. **Match → message conversion.** Did a match lead to a first message; did the message get a reply; how long did the conversation run. eharmony explicitly found compatibility scores weren't producing communication and retargeted its models at predicting **two-way communication** ([SiliconANGLE, Hadoop Summit 2013](https://siliconangle.com/2013/06/28/eharmony-refines-the-science-of-love-hadoop-machine-learning-hadoopsummit/)) `[OFFICIAL]`.
4. **Contact-info exchange.** Phone number / off-platform exchange is a strong proxy for "date likely" — Hinge triggers the We Met prompt a few days after detecting number exchange ([Elite Daily](https://www.elitedaily.com/p/what-is-hinges-we-met-feature-its-designed-to-make-your-next-first-date-even-better-12257228)) `[OFFICIAL]`.
5. **Activity/recency.** Tinder: "We prioritize potential matches who are active, and active at the same time" `[OFFICIAL]`. The League rewards daily login with a claimed 10% higher match rate and demotes inactives ([League FAQ/reviews](https://www.theleague.com/faqs-en/)) `[OFFICIAL]`.
6. **Photo-derived features.** Tinder uses "anonymized cues from photos" to find imagery similar to what you've liked `[OFFICIAL]`; teardowns describe CV features (composition, smile, solo vs group) and photo embeddings for taste-matching `[REVERSE-ENG]`.
7. **Negative signals** — left-swipes, unmatches, blocks, reports, ghosted conversations (see §5).

### 1.3 Third-party / graph signals

The League scores social/professional graph inputs (employer, education, referrals, mutual friends) `[OFFICIAL]`; Coffee Meets Bagel computed mutual-friend set intersections as a candidate feature in its recommendation pipeline ([AWS blog](https://aws.amazon.com/blogs/database/powering-recommendation-models-using-amazon-elasticache-for-redis-at-coffee-meets-bagel/)) `[OFFICIAL]`.

---

## 2. Stated vs revealed preferences: the gap is the product

The single most replicated finding in this literature:

- **QUT / RSVP study (41,936 users, 219,013 contacts):** "stating a preference for what you are looking for appears to have little to no bearing on the characteristics of people you actually contact" ([ScienceDaily](https://www.sciencedaily.com/releases/2017/02/170221110744.htm)) `[ACADEMIC]`. Women deviated from stated preferences more than men when initiating/replying. One nuance: **replies** skewed back toward the *receiver's* stated preferences — stated preferences aren't pure noise, they're a weak prior that shows up more in accept/reject than in pursuit ([arXiv 1401.5710](https://arxiv.org/pdf/1401.5710)) `[ACADEMIC]`.
- **Hitsch, Hortaçsu & Ariely, "What Makes You Click?"** — the canonical revealed-preference estimation from browsing + first-contact behavior. Behavioral data exposed preferences (notably strong same-race preference) that users would not state in surveys ([QME 2010](https://link.springer.com/article/10.1007/s11129-010-9088-6)) `[ACADEMIC]`.
- **Zhao et al. 2025 (speed-dating + simulation):** the stated/revealed discrepancy is partly *mechanical* — in real choice contexts, options are correlated and constrained, so revealed weights diverge from stated weights even for honest reporters ([J. Personality](https://journals.sagepub.com/doi/10.1177/08902070241286254)) `[ACADEMIC]`. Implication: don't interpret the gap purely as self-deception; part of it is market structure.
- **Bruch & Newman, "Aspirational pursuit of mates":** both sexes systematically pursue partners ~25% more desirable than themselves, and reply probability drops sharply with the desirability gap ([Science Advances 2018](https://www.science.org/doi/10.1126/sciadv.aap9815)) `[ACADEMIC]`. So *outbound* behavior (who I message) is aspirational and biased upward; *inbound acceptance* (who replies to me) is the better-calibrated preference signal. **Different behavioral streams reveal different preference distributions — apps that conflate them mis-learn.**

**How apps operationalize the gap** `[OFFICIAL + REVERSE-ENG]`: stated preferences become **hard constraints** (never violate a dealbreaker — violating explicit filters is perceived as a bug and destroys trust), while **ranking within the constraint set is driven almost entirely by revealed behavior**. Hinge's Most Compatible "looks at a user's past behavior on the platform to guess with which profiles he or she would be most likely to interact" ([TechCrunch](https://techcrunch.com/2018/07/11/hinge-employs-new-algorithm-to-find-your-most-compatible-match-for-you/)).

---

## 3. Which signals actually predict success — and which are noise

### Predictive (with evidence)

- **Reciprocal interaction history.** RECON: modeling both sides' revealed tastes nearly doubled success@10 (23%→42%) and lifted cold-start success to 26% ([RecSys 2010](https://dl.acm.org/doi/10.1145/1864708.1864747)) `[ACADEMIC]`.
- **Conversation depth.** OkCupid's internal threshold: once a conversation crosses ~4 back-and-forth messages, downstream success decouples from initial attractiveness/match% — rapport takes over (Rudder, *Dataclysm*; [NPR interview](https://www.npr.org/transcripts/345884282)) `[OFFICIAL-ish]`. Conversation length is both a good label and a good feature.
- **Activity/responsiveness.** Being active, replying, not letting matches expire — every platform confirms these dominate exposure. Boring but true.
- **Costly signals.** Longer first messages to more-desirable targets measurably raise reply odds (modestly) ([Bruch & Newman](https://www.science.org/doi/10.1126/sciadv.aap9815)) `[ACADEMIC]`; likes-with-comments on Hinge convert dramatically better than bare likes `[REVERSE-ENG]`.
- **Date-outcome feedback.** Hinge claims Most Compatible pairings were 8× more likely to lead to a date, and We Met feedback loops are credited with a reported ~30% lift in "great first dates" over time ([The Hustle](https://thehustle.co/hinge-machine-learning-algorithm), [knowtechie](https://knowtechie.com/hinge-we-met/)) `[OFFICIAL, self-reported — treat magnitudes skeptically]`.

### Noise (despite seeming like signal)

- **Questionnaire/trait similarity.** Joel, Eastwick & Finkel: ML over 100+ self-reported traits/preferences explained actor variance (who likes people generally) and partner variance (who is liked generally) but **~0% of dyad-specific attraction** ([Psych Science 2017](https://journals.sagepub.com/doi/10.1177/0956797617714580); [APS summary](https://www.psychologicalscience.org/news/releases/romantic-matches-are-hard-to-predict.html)) `[ACADEMIC]`. A 2023 preregistered follow-up extended the null to early relationship development ([Eastwick et al.](https://journals.sagepub.com/doi/10.1177/08902070221085877)).
- **eharmony's "29 dimensions."** Finkel et al.'s 60-page *Psychological Science in the Public Interest* review concluded matching algorithms built on pre-meeting self-report "likely foretell love no better than chance"; the industry never mounted a convincing empirical rebuttal ([Nautilus summary](https://nautil.us/when-dating-algorithms-can-watch-you-blush-235802), [HDSR](https://hdsr.mitpress.mit.edu/pub/i4eb4e8b)) `[ACADEMIC]`.
- **The displayed compatibility number itself.** OkCupid's notorious experiment: telling 30%-matches they were 90% made them message and converse nearly as much as genuine 90% pairs — "the mere myth of compatibility works just as well as the truth" ([OkTrends, archived](https://gwern.net/doc/psychology/okcupid/weexperimentonhumanbeings.html)) `[OFFICIAL]`. The score functioned as a *confidence prosthetic*, not a measurement. (Actual match% did add some real signal — best results were real-90% shown 90% — but the placebo effect was most of it.)
- **Photos as compatibility signal.** Love Is Blind Day: with photos removed, first-message reply rates rose 44% and conversations went deeper/exchanged contact info faster; when photos returned, the blind conversations "melted away" ([The Week](https://theweek.com/technology/59713/okcupid-five-things-it-learned-about-love-by-tricking-its-users)) `[OFFICIAL]`. Photos drive *selection* enormously while contributing little to *interaction quality* — a textbook attention/outcome divergence.

---

## 4. Outcome definition: the training label changes everything

Observed label ladders, shallow → deep:

| Label | Used by | Failure mode if optimized alone |
|---|---|---|
| Right-swipe received | Tinder Smart Photos (photo SRR) | Optimizes thumbnail appeal; learns attractiveness, not fit |
| Mutual match | All swipe apps | Cheap; massively inflated by aspirational/indiscriminate swiping |
| First message sent | RECON-era systems | Aspirational bias (Bruch & Newman) — pursuit ≠ preference |
| Reply / 2-way communication | eharmony's pivot `[OFFICIAL]` | Better; still on-platform chatter, not real-world outcome |
| 4+ message conversation | OkCupid's canonical success metric `[OFFICIAL]` | Good proxy for rapport; can be gamed by small talk |
| Contact exchange | Hinge trigger for We Met | Strong but sparse |
| Date happened + "would see again" | Hinge We Met `[OFFICIAL]` | Sparse, delayed, survivorship-biased — but closest to truth |
| Relationship / "deleted the app" | Hinge marketing metric | Too sparse/delayed to train on directly; use for evaluation |

Key engineering lessons:

1. **eharmony's pivot is the pattern to copy:** their compatibility models were "working" by their own definition but users weren't messaging each other, so they re-labeled on predicted two-way communication and blended attraction into affinity models ([SiliconANGLE](https://siliconangle.com/2013/06/28/eharmony-refines-the-science-of-love-hadoop-machine-learning-hadoopsummit/), [CIO](https://www.cio.com/article/206096/click-me-maybe-inside-eharmony-s-matchmaking-machine.html)) `[OFFICIAL]`. When your model's target and your product's purpose diverge, the model wins and the product loses.
2. **Hinge deliberately optimizes off-platform success, not engagement** — "We Met is actually focused on quantifying real world dating successes… not in-app engagement" ([HBS RCTOM](https://aiinstitute.hbs.edu/platform-rctom/submission/hinge-and-machine-learning-the-makings-of-a-perfect-match/)) `[OFFICIAL]`. This is also brand-strategic ("designed to be deleted") — the label choice *is* the positioning.
3. **Use deep labels for evaluation and calibration, shallow labels for volume.** Nobody trains purely on date-outcomes (too sparse). The practical architecture is a cascade: train on abundant mid-funnel labels (reply, conversation), calibrate/reweight with sparse deep labels (We Met yes/no) `[REVERSE-ENG — inferred from public statements + standard practice]`.

---

## 5. Negative signals and their weighting

- **Left-swipes** are the bulk of all signal volume and are treated as *weak* negatives — exposure bias means a nope on a shown profile is informative, but non-exposure is not a negative at all ([bias survey, ACM TOIS](https://dl.acm.org/doi/10.1145/3564284)) `[ACADEMIC]`. Reciprocal-recommender research explicitly mines negative samples (send-without-reply etc.) as graded negatives ([arXiv 2007.16120](https://arxiv.org/pdf/2007.16120)) `[ACADEMIC]`.
- **Unmatch / block / report** are strong negatives with asymmetric handling: they feed *safety* systems faster than *preference* systems. Multiple reports in a short window, bulk unmatching, >~80% right-swipe rates, and copy-paste openers are documented shadowban/deprioritization triggers across community evidence ([nsokolsky](https://nsokolsky.substack.com/p/how-dating-app-algorithms-likely)) `[REVERSE-ENG]`. Hinge confirmed it quietly hides bad actors from feeds/search rather than banning outright `[OFFICIAL via TechCrunch]`.
- **Ghosting** is increasingly treated as a first-class negative: The League penalizes "flaky" members (match but don't message, don't reply) with reduced match rates `[OFFICIAL]`; Hunch drops ghosting users from others' feeds `[OFFICIAL]`; Match built nudges to either continue or politely close stalling conversations ([TechCrunch](https://techcrunch.com/2021/08/09/match-beta-test-targets-dating-app-complaints-like-frustration-with-swiping-ghosting/)) `[OFFICIAL]`.
- **Weighting principle** that emerges: negative signal severity ≈ how much of the *other person's* scarce resource was wasted. A left-swipe wastes an impression (cheap). A ghosted conversation wastes days of attention (expensive). A no-show date wastes an evening (most expensive → strongest penalty at apps that can observe it).

---

## 6. Feedback-loop design and its degenerate failure modes

### The healthy loop
Show candidates → observe graded reactions → update per-user preference model + global desirability priors → re-rank → observe deeper outcomes (conversation, date) → recalibrate. Hinge's version closes all the way at the date level; Tinder's official description closes at the like/nope + activity level; CMB precomputed nightly recommendation queues refreshed by the previous day's interactions ([AWS blog](https://aws.amazon.com/blogs/database/powering-recommendation-models-using-amazon-elasticache-for-redis-at-coffee-meets-bagel/)) `[OFFICIAL]`.

### Degenerate loop #1: preference collapse (echo chamber)
The model shows you X, you engage with X because that's what's shown, the model learns you love X. DeepMind's formal analysis distinguishes **echo chambers** (repeated exposure reinforces the interest itself) from **filter bubbles** (the candidate set narrows); their strongest empirical result: the *more accurate* the recommender, the *faster* degeneracy sets in, and the effective mitigations are **continuous random exploration** and **growing the candidate pool over time** ([arXiv 1902.10730](https://arxiv.org/abs/1902.10730), [MIT Tech Review](https://www.technologyreview.com/2019/03/07/65984/deepmind-is-asking-how-google-helped-turn-the-internet-into-an-echo-chamber/)) `[ACADEMIC]`. In dating-app form: "every swipe narrows the model toward a type… the system reads consistency as preference, even when the preference is only a rut."

### Degenerate loop #2: early-cohort imprinting (collaborative-filtering bias)
Monster Match (Mozilla Creative Media Award) demonstrated that CF in dating apps inherits the tastes of *early users*: if early cohorts systematically under-swipe a group, new users never get shown that group, so no corrective signal can ever arrive ([massivesci](https://massivesci.com/notes/monster-match-bias-online-dating-collaborative-filtering-algorithm/), [Mozilla](https://www.mozillafoundation.org/en/blog/mozilla-explains-how-dating-apps-might-be-keeping-you-single/)) `[ACADEMIC/DEMO]`. Documented downstream effect: racial bias amplification in real apps ([TNW](https://thenextweb.com/tech/2019/05/29/this-game-reveals-the-hidden-racial-bias-of-dating-app-algorithms/)).

### Degenerate loop #3: desirability spiral
Low score → less exposure → fewer likes → lower score. Documented as the core dynamic of Elo-type systems (see §8); the datafield teardown calls it the "algorithmic amplification cycle" `[REVERSE-ENG]`.

### Degenerate loop #4: self-fulfilling labels
OkCupid's experiment is the cleanest demonstration that **the act of recommending changes the outcome you then train on**: bad pairs told they were great matches went on to have good conversations *because they were told so* ([OkTrends](https://gwern.net/doc/psychology/okcupid/weexperimentonhumanbeings.html)) `[OFFICIAL]`. Any outcome label collected downstream of your own recommendation UI is contaminated by presentation effects; you cannot distinguish "model was right" from "user trusted the model" without holdout randomization.

### Loop hygiene that practitioners converge on
- Log **exposure**, not just action (a nope on shown ≠ never shown) — standard unbiased-LTR practice ([position/exposure bias literature](https://dl.acm.org/doi/10.1145/3564284)) `[ACADEMIC]`.
- Keep an **exploration budget** (Tinder Smart Photos runs explicit explore/exploit over photo order, measuring per-photo swipe-right-rate ([Quartz](https://qz.com/809681/tinders-machine-learning-algorithms-can-now-serve-your-most-appealing-photos-to-potential-dates)) `[OFFICIAL]`).
- **Randomized holdouts** to measure the recommender's true lift vs its placebo effect (OkCupid literally ran these on humans; the ethics blowback is its own antipattern — see below).

---

## 7. Recency, decay, and session vs lifetime preference

- Tinder's post-Elo system is explicitly **recency-weighted**: "recent activity," being active at the same time as candidates, and 24-48h new-user boosts `[OFFICIAL + REVERSE-ENG]`. Bumble expires matches in 24h — a structural forcing function that converts stale positive signals into explicit negatives (expiration) `[OFFICIAL]`.
- Session-level intent differs from lifetime taste: Smart Photos personalizes *which of your photos* is shown per viewing session based on the viewer's history (e.g., suppressing dog photos for users who consistently nope them) — per-impression contextualization on top of lifetime preference `[OFFICIAL via Quartz]`.
- No app documents exact decay constants `[SPECULATIVE]`, but the observable design choices (activity prioritization, match expiry, "dynamic system that continuously factors in" engagement) all imply heavy discounting of old signals — sensible in a domain where preferences shift with life circumstances and where account dormancy is the norm.

---

## 8. Desirability scoring: what's real, what's retired, what remains

- **The original Tinder Elo** `[OFFICIAL, retired]`: every swipe was a "game" — being right-swiped by a high-scored user moved your score more than by a low-scored one; CEO Sean Rad described it as "hundreds of games of pong" resolving into a stable rating and insisted it measured "desirability," not attractiveness ([Fast Company](https://www.fastcompany.com/3054871/whats-your-tinder-score-inside-the-apps-internal-ranking-system), [Slate](https://slate.com/business/2016/01/you-have-a-secret-tinder-rating-and-only-the-company-knows.html)). Scores were used to pair people of comparable desirability.
- **Officially deprecated 2019**: "Elo is old news… our cutting-edge technology no longer relies on it," replaced by a dynamic engagement-based system; Tinder also states it doesn't use social status, religion, or ethnicity ([Tinder press room](https://www.tinderpressroom.com/powering-tinder-r-the-method-behind-our-matching)) `[OFFICIAL]`.
- **Consensus of teardowns**: desirability didn't die, it became a *vector* — incoming-like velocity, reply rates received, mutual-match frequency, selectivity — "the good old ELO is still alive under a fancier name" ([nsokolsky](https://nsokolsky.substack.com/p/how-dating-app-algorithms-likely)) `[REVERSE-ENG]`.
- **Why it's structurally hard to avoid**: Bruch & Newman showed the desirability hierarchy exists in user behavior regardless of whether the platform scores it — pursuit is aspirational (+25%) and response probability decays with the gap `[ACADEMIC]`. Scoring desirability is really just *modeling reply probability*; the controversy is about opacity and the spiral (§6, loop #3), not the existence of the gradient.
- **PR lesson**: secret scalar scores about users' worth become scandals when discovered (Fast Company 2016 → years of "what's my Elo" anxiety content). If you must rank users, (a) never expose or leak a single scalar, (b) frame internal usage as pairing/likelihood, not worth.

---

## 9. Cold start: what signal is worth onboarding friction

- **Structured explicit prior first**: hard filters + a handful of high-information preference questions. Preference-elicitation research: pairwise comparisons beat single-item ratings for information per interaction, and eliciting on *attributes* as well as items helps ([arXiv 2510.27342](https://arxiv.org/html/2510.27342), [arXiv 2309.00356](https://arxiv.org/pdf/2309.00356)) `[ACADEMIC]`.
- **New-user exposure boost**: Tinder gives new profiles a 24-48h visibility boost across desirability tiers — deliberately over-exposing to *collect* initial signal fast (and, cynically, to hook the user with early matches) `[REVERSE-ENG]`.
- **0-day fallback model**: CMB explicitly ran an Elasticsearch attribute-match model as the "0-day model" until behavioral data accumulated, then ML recommendations took over ([AWS blog](https://aws.amazon.com/blogs/database/powering-recommendation-models-using-amazon-elasticache-for-redis-at-coffee-meets-bagel/)) `[OFFICIAL]`.
- **Reciprocity helps cold start**: RECON got 26% success@10 for brand-new users by leaning on the *other side's* established preferences `[ACADEMIC]` — when you know nothing about A, you can still rank candidates by who would plausibly say yes to A.
- **OkCupid's 3-question finding** (horror movies / traveled alone abroad / live-on-a-sailboat agreement predicted long-term couples at 3.7× chance) is a reminder that a *few* well-chosen questions carry most of the questionnaire's total value ([Mic](https://www.mic.com/articles/85297/these-3-simple-questions-can-predict-if-an-okcupid-date-will-succeed)) `[OFFICIAL, weak causal claim]`.

---

## Best practices (consolidated, with citations)

1. **Treat stated preferences as constraints, revealed behavior as ranking.** Never violate an explicit filter; never rank primarily on questionnaire similarity. ([QUT study](https://www.sciencedaily.com/releases/2017/02/170221110744.htm); [Hitsch et al.](https://link.springer.com/article/10.1007/s11129-010-9088-6); [Finkel review via HDSR](https://hdsr.mitpress.mit.edu/pub/i4eb4e8b))
2. **Score reciprocally**: P(A engages B) × P(B engages A) × P(interaction succeeds). Single biggest documented accuracy win. ([RECON](https://dl.acm.org/doi/10.1145/1864708.1864747))
3. **Build an explicit outcome-collection feature** for the deepest observable label, triggered by a behavioral tripwire (Hinge: contact exchange → "We Met?" prompt days later). One binary question, asked at the right moment, is the cheapest ground truth you'll ever get. ([Engadget](https://www.engadget.com/2018-10-16-hinge-we-met-first-date-ai.html))
4. **Grade your signal ladder and weight by cost-to-fake**: impression < swipe < dwell < message sent < reply < sustained conversation < contact exchange < confirmed real-world outcome. Train on volume in the middle, calibrate on truth at the top. (eharmony pivot: [SiliconANGLE](https://siliconangle.com/2013/06/28/eharmony-refines-the-science-of-love-hadoop-machine-learning-hadoopsummit/); OkCupid 4-message metric: [NPR/Dataclysm](https://www.npr.org/transcripts/345884282))
5. **Normalize per-user selectivity.** A right-swipe from an 80%-right-swiper ≈ nothing; from a 5%-right-swiper it's gold. Both Tinder-Elo mechanics and shadowban thresholds embody this. ([Fast Company](https://www.fastcompany.com/3054871/whats-your-tinder-score-inside-the-apps-internal-ranking-system); [nsokolsky](https://nsokolsky.substack.com/p/how-dating-app-algorithms-likely))
6. **Log exposure, weight negatives by wasted counterpart cost**, and treat "never shown" as unknown, not negative. ([bias survey](https://dl.acm.org/doi/10.1145/3564284))
7. **Reserve a permanent exploration budget** and grow the candidate pool; accuracy without exploration accelerates preference collapse. ([DeepMind](https://arxiv.org/abs/1902.10730))
8. **Run explore/exploit at the presentation layer too** (which asset/angle to lead with), not just candidate selection — Tinder Smart Photos yielded +12% matches from photo ordering alone. ([Quartz](https://qz.com/809681/tinders-machine-learning-algorithms-can-now-serve-your-most-appealing-photos-to-potential-dates))
9. **Prioritize recency and co-activity**; expire stale positives. ([Tinder press room](https://www.tinderpressroom.com/powering-tinder-r-the-method-behind-our-matching))
10. **Penalize flake behavior symmetrically** — matching-then-silence degrades the counterpart's experience; The League's flaky-member demotion is the cleanest public template. ([League reviews/FAQ](https://www.theleague.com/faqs-en/))
11. **Keep a randomized holdout** so you can separate model lift from presentation placebo. (Implied by [OkCupid's experiments](https://gwern.net/doc/psychology/okcupid/weexperimentonhumanbeings.html) — the displayed score alone moved behavior.)

## Antipatterns (documented failures)

1. **Questionnaire-similarity matching as the core engine.** Two decades of eharmony/OkCupid-style matching never demonstrated pair-level predictive validity; the flagship academic test found ~zero dyadic predictability. ([Joel et al. 2017](https://journals.sagepub.com/doi/10.1177/0956797617714580); [Finkel critique](https://nautil.us/when-dating-algorithms-can-watch-you-blush-235802))
2. **Training on shallow engagement labels.** Optimizing swipes/matches produces attractive-thumbnail feeds and hollow matches; eharmony's "compatible but silent" era is the canonical case. Choice of label is strategy.
3. **A single opaque desirability scalar.** Creates PR catastrophe on discovery, invites spiral dynamics, and conflates many distinct quantities (activity, selectivity, appeal). ([Fast Company](https://www.fastcompany.com/3054871/whats-your-tinder-score-inside-the-apps-internal-ranking-system))
4. **Unchecked collaborative filtering on a small early cohort.** Early users' tastes get baked in as permanent exposure policy; groups nobody was shown can never recover. ([Monster Match](https://massivesci.com/notes/monster-match-bias-online-dating-collaborative-filtering-algorithm/))
5. **Reading consistency as preference.** "The system reads consistency as preference, even when the preference is only a rut" — showing more of what got engaged with, when engagement was exposure-driven. ([Hinge/CF coverage](https://www.bustle.com/wellness/how-does-hinge-algorithm-work); [DeepMind](https://arxiv.org/abs/1902.10730))
6. **Treating outbound pursuit as calibrated preference.** Users aim ~25% above their realistic band; a model trained on "who they message" learns aspiration, then feeds them people who won't reciprocate. ([Bruch & Newman](https://www.science.org/doi/10.1126/sciadv.aap9815))
7. **Experimenting on outcome labels without consent/guardrails.** OkCupid's fake-match-percentage experiment produced real insight and a lasting trust scar + FTC/press blowback ([Forbes](https://www.forbes.com/sites/kashmirhill/2014/07/28/okcupid-experiment-compatibility-deception/)).
8. **Letting monetization silently override ranking.** Boost/priority products that distort the feed teach users the feed is untrustworthy; teardowns consistently identify pay-to-rank as the most corrosive credibility issue. ([nsokolsky](https://nsokolsky.substack.com/p/how-dating-app-algorithms-likely)) `[REVERSE-ENG]`
9. **Ignoring the placebo channel.** If your UI displays a confidence score, the score *causes* outcomes; naive retraining on those outcomes is self-confirming. ([OkTrends](https://gwern.net/doc/psychology/okcupid/weexperimentonhumanbeings.html))

## What matters most (ranked)

1. **Outcome label choice.** Everything downstream — features, weights, product feel — is determined by what you call success. The single documented differentiator between "engagement machine" (Tinder-era Elo) and "designed to be deleted" (Hinge We Met). Get the deepest cheaply-observable label and build a collection feature for it.
2. **Reciprocity in scoring.** Doubled success rates in the best-controlled study; also the correct conceptual frame for any two-sided acceptance problem.
3. **Revealed-over-stated hierarchy with stated-as-constraints.** The most replicated behavioral finding; violating it in either direction (ranking on questionnaires, or overriding explicit filters) is a known failure.
4. **Signal grading by cost-to-fake + per-user selectivity normalization.** Converts a noisy event firehose into a usable preference model; the difference between counting swipes and understanding them.
5. **Exploration budget / anti-degeneracy design.** Not optional at small scale — small user pools imprint faster (Monster Match's whole point). Cheap insurance: a fixed % of deliberately off-model candidates, logged as exploration.
6. **Negative-signal weighting by counterpart cost.** Protects the scarce side of the market (responders); The League's flake penalty and Bumble's expiry are structural versions.
7. **Recency weighting.** Important but mechanically simple; a decay constant, not an architecture.

## What doesn't matter (even though it seems like it should)

1. **Compatibility questionnaires' *content*, beyond a few high-variance items.** ~Zero dyadic predictive power at scale ([Joel et al.](https://journals.sagepub.com/doi/10.1177/0956797617714580)); OkCupid's 275k questions reduced to 3 with most of the couple-level signal ([Mic](https://www.mic.com/articles/85297/these-3-simple-questions-can-predict-if-an-okcupid-date-will-succeed)). Long onboarding questionnaires are mostly ritual/commitment devices (which *does* have retention value — eharmony's paying users self-select for motivation — but that's marketing, not modeling).
2. **The accuracy of a displayed compatibility score.** Displayed 90% ≈ real 90% in driving conversations ([OkTrends](https://gwern.net/doc/psychology/okcupid/weexperimentonhumanbeings.html)). Users respond to the *existence* of a confident recommendation. Corollary: presentation confidence is a lever, and an honesty obligation.
3. **Raw right-swipe direction as preference.** Near-meaningless without selectivity normalization when base rates hit 60-80% `[REVERSE-ENG]`.
4. **Photo optimization for downstream outcomes.** Photos dominate selection but wash out of interaction quality (44% higher reply rates *without* photos; attractiveness "goes out the window" after 4 messages). Optimizing photo appeal (Smart Photos) lifts matches, not relationships.
5. **Predicting pair-level chemistry before any interaction.** The best ML on the richest pre-meeting data can't do it ([APS](https://www.psychologicalscience.org/news/releases/romantic-matches-are-hard-to-predict.html)). The actionable move is not better pre-interaction prediction, it's cheaper/faster *interaction* so revealed signal arrives sooner.
6. **More onboarding questions.** Information-per-question decays fast; pairwise/attribute elicitation gets more from less ([arXiv 2510.27342](https://arxiv.org/html/2510.27342)). Friction is better spent getting the user to their first real interaction (which generates better signal than any answer).

---

## Transferable insight: mapping to FTF trade matchmaking

*(Framing only — not part of the web research. The dating→trade mapping the client asked for.)*

| Dating signal | FTF analog | Grade (cost-to-fake) |
|---|---|---|
| Impression (profile shown) | Trade suggestion rendered in list | Log it; it's the exposure denominator |
| Left-swipe | Dismiss suggestion | Weak negative; normalize by user's dismiss rate |
| Dwell on profile | Time on trade detail view / expansion | Mid implicit positive even when dismissed |
| Right-swipe / like | Save trade | Real positive |
| Super-like | (n/a today — a "pin/target this trade" would be one) | High-precision explicit |
| First message sent | Send trade to other party | Strong intent; but beware aspirational bias — users propose lopsided trades "25% above their league," expect counterpart rejection gradients |
| Reply / conversation | Counterparty views/responds/counter-offers | The reciprocity term — score P(sender sends) × P(receiver accepts-ish) |
| Contact exchange | Trade discussed in league chat / counter built | Deep proxy |
| **We Met** | **Trade executed on Sleeper (observable!) + optional 1-tap "happy with this trade?" later** | Ground truth. FTF's structural advantage: the "date happened" signal is *automatically observable* via the league platform — Hinge had to ask. |
| Elo desirability | Asset/manager desirability from matchup votes + accept rates | Already have the vote-Elo; the *manager-level* accept-rate prior is the missing analog |
| Stated filters (want/accept boards) | Want/accept boards | Constraints, not ranking — never suggest a trade violating an accept board; but expect boards to lag revealed behavior, and surface the gap rather than silently override |
| Degenerate loop risk | Only suggesting trade archetypes the user previously engaged → user never sees (and model never learns about) other viable archetypes | Acute at league scale (11 counterparties): reserve exploration slots for off-model suggestions |

Sharpest transfers: (1) label on **executed trades** (and later, post-trade satisfaction), not on saves/sends; (2) reciprocal scoring — a suggestion is only good if *both* sides' revealed patterns say yes; (3) log every suggestion exposure now, even before any model exists — the exposure log is the dataset; (4) stated boards = hard constraints + a diffable "your board says X, your behavior says Y" feature, which dating apps can't do transparently but a trade app can.

---

## Not researched / follow-up topics

1. **Match Group internal ML infrastructure post-2020 (TinVec-style embeddings, deep retrieval).** Public engineering detail is thin; conference talks (MLconf, QCon) by Match Group staff may exist and would upgrade several `[REVERSE-ENG]` items to `[OFFICIAL]`.
2. **Quantitative negative-signal weighting schemes.** No public source gives actual loss weights for unmatch/report/ghost vs left-swipe; worth searching RecSys/KDD industry-track papers on "reciprocal" + "negative sampling" for concrete ratios.
3. **Uplift modeling / incremental-lift labels.** Training on "did the recommendation *cause* the outcome" rather than "did the outcome co-occur" — the clean fix for the self-fulfilling-label problem (§6.4); mature in ads, unexplored here.
4. **Bandit formulations for presentation-layer choices** (which trade rationale/framing to show, analog of Smart Photos). The explore/exploit literature for creative selection maps directly to "which of 3 equivalent trade packagings converts."
5. **Session-based/sequential recommenders (SASRec/GRU4Rec-family) applied to swipe streams.** Would ground the recency/session-vs-lifetime section (§7), which is currently the thinnest evidence-wise.
6. **Privacy/regulatory constraints on behavioral preference learning** (GDPR "profiling," FTC actions against Match Group). Matters before shipping any inferred-preference feature that users didn't opt into.
7. **The 2023-2026 AI-features wave** (Hinge Prompt Feedback, Tinder AI photo picking, LLM-scored conversation quality). Early signals that LLMs are becoming feature extractors over free-text — relevant to mining FTF's feedback text and league chat someday.
8. **eharmony's published patents and papers in detail** (e.g., reply-rate-matching patent US10540607) — skimmed only; they contain concrete feature lists that would firm up §4.
9. **Post-relationship attrition as a label** ("deleted the app" / exit surveys) and survivorship bias in deep labels — how sparse delayed labels get de-biased.
10. **KeepTradeCut's crowdsourced-value loop** — the nearest same-domain analog of matchup-vote signal collection; deliberately out of scope here (competitor-analysis memo territory) but the signal-decay + manipulation-resistance design would be directly comparable.

---

## Sources

**Official / first-party**
- https://www.tinderpressroom.com/powering-tinder-r-the-method-behind-our-matching — Tinder, "Powering Tinder: The Method Behind Our Matching" (2019, Elo deprecation)
- https://www.help.tinder.com/hc/en-us/articles/7606685697037-Powering-Tinder-The-Method-Behind-Our-Matching — same, help-center version
- https://www.tinderpressroom.com/introducing-smart-photos-for-the-most-swipeworthy-you — Tinder Smart Photos launch
- https://gwern.net/doc/psychology/okcupid/weexperimentonhumanbeings.html — OkTrends, "We Experiment on Human Beings!" (archived)
- https://www.theleague.com/faqs-en/ — The League FAQ (algorithm behavior, flaky penalty)
- https://aws.amazon.com/blogs/database/powering-recommendation-models-using-amazon-elasticache-for-redis-at-coffee-meets-bagel/ — Coffee Meets Bagel recommendation pipeline (AWS Database Blog)
- https://siliconangle.com/2013/06/28/eharmony-refines-the-science-of-love-hadoop-machine-learning-hadoopsummit/ — eharmony ML at Hadoop Summit (Petricek)
- https://www.cio.com/article/206096/click-me-maybe-inside-eharmony-s-matchmaking-machine.html — CIO, inside eharmony's matchmaking machine

**Academic**
- https://journals.sagepub.com/doi/10.1177/0956797617714580 — Joel, Eastwick & Finkel (2017), "Is Romantic Desire Predictable?"
- https://www.psychologicalscience.org/news/releases/romantic-matches-are-hard-to-predict.html — APS summary of the above
- https://journals.sagepub.com/doi/10.1177/08902070221085877 — Eastwick et al. (2023), preregistered follow-up
- https://www.science.org/doi/10.1126/sciadv.aap9815 — Bruch & Newman (2018), "Aspirational pursuit of mates in online dating markets"
- https://link.springer.com/article/10.1007/s11129-010-9088-6 — Hitsch, Hortaçsu & Ariely (2010), "What Makes You Click?"
- https://www.sciencedaily.com/releases/2017/02/170221110744.htm — QUT/RSVP stated-vs-actual contact study (Whyte & Torgler)
- https://journals.sagepub.com/doi/10.1177/08902070241286254 — Zhao et al. (2025), speed-dating + simulation explanation of the stated/revealed gap
- https://arxiv.org/pdf/1401.5710 — "Who is Dating Whom" (large dating-site behavior; replies track receivers' stated prefs)
- https://dl.acm.org/doi/10.1145/1864708.1864747 — RECON reciprocal recommender (RecSys 2010)
- https://arxiv.org/pdf/2007.16120 — Reciprocal recommender systems survey
- https://arxiv.org/abs/1902.10730 — Jiang et al. (DeepMind), "Degenerate Feedback Loops in Recommender Systems"
- https://www.technologyreview.com/2019/03/07/65984/deepmind-is-asking-how-google-helped-turn-the-internet-into-an-echo-chamber/ — MIT Tech Review on the above
- https://dl.acm.org/doi/10.1145/3564284 — "Bias and Debias in Recommender System: A Survey" (ACM TOIS)
- https://arxiv.org/html/2510.27342 — Pairwise & attribute-aware preference elicitation for cold start
- https://arxiv.org/pdf/2309.00356 — Explainable active learning for preference elicitation
- https://hdsr.mitpress.mit.edu/pub/i4eb4e8b — Harvard Data Science Review, "Finding Love on a First Data: Matching Algorithms in Online Dating"

**Journalism / teardowns / demos**
- https://www.fastcompany.com/3054871/whats-your-tinder-score-inside-the-apps-internal-ranking-system — Austin Carr, Fast Company (Tinder Elo access)
- https://slate.com/business/2016/01/you-have-a-secret-tinder-rating-and-only-the-company-knows.html — Slate on the secret Tinder rating
- https://qz.com/809681/tinders-machine-learning-algorithms-can-now-serve-your-most-appealing-photos-to-potential-dates — Quartz, "Tinder is A/B testing your face" (Smart Photos explore/exploit)
- https://nsokolsky.substack.com/p/how-dating-app-algorithms-likely — Sokolsky, "How dating app algorithms (likely) work in 2026" (best current teardown; patents + community evidence)
- https://datafield.dev/blog/dating-app-algorithms.html — DataField, "How Dating App Algorithms Actually Work: Tinder, Hinge, Bumble Decoded"
- https://techcrunch.com/2018/07/11/hinge-employs-new-algorithm-to-find-your-most-compatible-match-for-you/ — TechCrunch, Hinge Most Compatible (Gale-Shapley)
- https://thehustle.co/hinge-machine-learning-algorithm — The Hustle, Hinge's Nobel-prize algorithm (8× date claim)
- https://www.engadget.com/2018-10-16-hinge-we-met-first-date-ai.html — Engadget, We Met launch
- https://www.elitedaily.com/p/what-is-hinges-we-met-feature-its-designed-to-make-your-next-first-date-even-better-12257228 — Elite Daily, We Met mechanics (trigger on number exchange)
- https://knowtechie.com/hinge-we-met/ — KnowTechie, We Met and the 30%-better-dates claim
- https://aiinstitute.hbs.edu/platform-rctom/submission/hinge-and-machine-learning-the-makings-of-a-perfect-match/ — HBS RCTOM, "Hinge and Machine Learning"
- https://massivesci.com/notes/monster-match-bias-online-dating-collaborative-filtering-algorithm/ — Massive Science on Monster Match
- https://www.mozillafoundation.org/en/blog/mozilla-explains-how-dating-apps-might-be-keeping-you-single/ — Mozilla explainer on CF in dating apps
- https://thenextweb.com/tech/2019/05/29/this-game-reveals-the-hidden-racial-bias-of-dating-app-algorithms/ — TNW on Monster Match / racial bias
- https://www.forbes.com/sites/kashmirhill/2014/07/28/okcupid-experiment-compatibility-deception/ — Forbes (Kashmir Hill) on the OkCupid deception experiment
- https://theweek.com/technology/59713/okcupid-five-things-it-learned-about-love-by-tricking-its-users — The Week, Love Is Blind Day numbers
- https://www.mic.com/articles/85297/these-3-simple-questions-can-predict-if-an-okcupid-date-will-succeed — Mic, OkCupid's 3 predictive questions
- https://www.npr.org/transcripts/345884282 — NPR interview w/ Christian Rudder (Dataclysm; 4-message rapport threshold)
- https://nautil.us/when-dating-algorithms-can-watch-you-blush-235802 — Nautilus on Finkel's critique of matching algorithms
- https://techcrunch.com/2021/08/09/match-beta-test-targets-dating-app-complaints-like-frustration-with-swiping-ghosting/ — TechCrunch, Match anti-ghosting nudges
- https://www.bustle.com/wellness/how-does-hinge-algorithm-work — Bustle insider explanation of Hinge algorithm / CF rut effect
