# Round 2 — Presentation, Explanation, and Post-Match Conversion Engineering (Implementation Depth)

> Research memo, 2026-08-15. Round-2 follow-up to the round-1 finding that presentation captures a huge share of matching value. This memo goes one level down: HOW to implement explanation, endorsement, pacing, expiry, and turn-taking mechanics, with numbers, plus a primary-source verification sweep of the round-1 claims.
>
> **Confidence tags used throughout:** `[peer-reviewed]` published study read directly; `[official]` company's own announcement/patent/help doc; `[industry-report]` vendor benchmark (Airship/Braze/Localytics/CleverTap etc. — real data, marketing incentive); `[press]` journalism citing company claims; `[reverse-engineered]` third-party teardown; `[inference]` our judgment.

---

## 1. Best practices

### 1.1 Explanations: show both sides' benefit — but only when saying yes is costly

The single most FTF-relevant paper in this literature is **Kleinerman, Rosenfeld & Kraus, "Providing Explanations for Recommendations in Reciprocal Environments" (RecSys 2018)** — read in full for this memo `[peer-reviewed]`. Their setting is exactly ours: a recommender that must get *two* parties to say yes. Findings:

- **Reciprocal explanations** ("why you'll like this match" + "why they're likely to accept you") vs **one-sided explanations** ("why you'll like this match"):
  - **Live dating app (Doovdevan, N=161 active users, randomized):** acceptance rate (sent a message after viewing the rec) was **53% with reciprocal explanations vs 36% one-sided (p<0.05)**. For women: 39% vs 25% (significant). For "choosy" users (below-median message senders): **47% vs 25%** (significant); for heavy senders 61% vs 56% (n.s.).
  - **Follow-on engagement:** reciprocal-explanation users logged in **56 times vs 23** in the following week (p≤0.05).
  - **Simulated platform with explicit acceptance cost** (points lost if the other side declined): acceptance 3.49/5 recs vs 2.83/5 (p≤0.01) and **trust in the system was higher** (3.38 vs 2.93, p≤0.05).
  - **Critical boundary condition:** with **negligible acceptance cost** (just rate relevance, nothing at stake), one-sided explanations *beat* reciprocal on relevance (3.76 vs 3.34), satisfaction (4.0 vs 3.57), and perceived competence (4.13 vs 3.27). Authors' diagnosis: information overload, plus users' discomfort at being told why they're attractive to the other side when it clashes with self-image.
  - **Transfer:** proposing a trade in a dynasty league is a *high-cost* accept (you burn social capital and negotiating position with a leaguemate; rejection is visible). FTF sits squarely in the regime where reciprocal explanations win. `[inference]` on the mapping, `[peer-reviewed]` on the mechanism.

- **Explanation structure that tested best** `[peer-reviewed]`:
  - Format = **top-k concrete features, k capped at 3** (they cite Pu & Chen's overload guideline and enforce it).
  - **Correlation-based feature selection beat "transparent" (frequency-based) selection** on satisfaction (3.58 vs 3.14, p≤0.02), perceived usefulness (3.8 vs 3.17, p≤0.02) and — remarkably — *perceived transparency* (3.97 vs 3.41, p≤0.04), even though it is the less faithful method. Users judge transparency by whether the explanation *feels* intuitive, not by algorithmic fidelity.
  - **Asymmetric two-part format for privacy** (used in the live deployment because they couldn't reveal the other user's preferences): part 1 = concrete features for the receiver's side; part 2 = a *confidence statement* about the other side ("the system believes you fit their preferences; they are likely to reply positively") **without revealing the other party's data**. This is the exact pattern FTF needs: never expose the other manager's board; just assert fit with evidence-free confidence on their side and evidence-rich features on yours.

- General explanation-research context: explanations increase acceptance and satisfaction (Herlocker et al. 2000), and feature-specific explanations work **even when the cited features are not the real reason** the rec was generated (Gedikli/Jannach/Ge 2014; Herlocker 2000) `[peer-reviewed]`. Tintarev & Masthoff's canonical framework separates seven explanation goals (transparency, scrutability, trust, effectiveness, persuasiveness, efficiency, satisfaction) and warns that transparency can raise *or lower* trust depending on whether users like what they see `[peer-reviewed]`. Recent surveys (arXiv 2412.14193) note most deployed explanation work optimizes persuasion, not faithfulness — see antipattern 2.3 for the trap.

### 1.2 Endorsement: one endorsed pick, scarce and mutual, presented as its own artifact

- **Hinge Most Compatible** `[official/press]`: exactly **one endorsed profile per user per 24h**, chosen by a Gale–Shapley-inspired *stable matching* over revealed preferences (mutual, not one-directional), presented in a special slot. Hinge's tested claim: Most Compatible pairs were **8x more likely to exchange phone numbers** than other matches (TechCrunch, 2018-07-11). The endorsement is powerful because it is (a) scarce — one per day, (b) mutual — the algorithm claims *both* sides fit, and (c) visually distinct.
- **Tinder Top Picks** `[official]`: 1 free pick/day for everyone; 4–10/day for Gold/Platinum; the set **expires in 24h**. So even the "abundant" version of endorsement is capped at ~10 and deadline-bound.
- **Tier count in practice:** shipped products use **two tiers** — the default pool plus ONE endorsed tier (Most Compatible, Top Picks, Standouts). Nobody ships 4-level endorsement ladders on the consumer surface. `[reverse-engineered, consistent across apps]`
- **Calibrated conservative display (OkCupid pattern)** `[official blog, widely documented]`: OkCupid's match % displays the **lower bound of the estimate given the margin of error** from the number of commonly-answered questions (2 shared questions → max displayable 50%). Two effects: displayed confidence never overpromises on thin data, and users are incentivized to feed the system more data to raise the ceiling. Directly portable: cap displayed trade-confidence by data volume (few ranking matchups completed → capped confidence + "rank more players to sharpen this").
- **Confidence-display calibration research** `[peer-reviewed]`: Li et al. (arXiv 2402.07632) — miscalibrated AI confidence is *hard for users to detect*, damages appropriate reliance, and disclosing that confidence is uncalibrated triggers global under-reliance (users stop trusting even the good calls). FAccT 2025 work adds: **confidently-wrong errors damage trust far more than tentatively-wrong ones**, and errors late in an interaction sequence or in high-stakes contexts hurt most. Design consequence: display *bounded, conservative* confidence; never display a high number you can't stand behind; degrade the claim ("worth a look") rather than the number when uncertain.

### 1.3 Pacing & notifications: per-user timing beats clock rules; batch the rest; keep weekly frequency low single digits

- **Frequency-vs-churn numbers** `[industry-report]`:
  - Localytics (via MobiLoud roundup): **46% of users opt out at 2–5 pushes/week; 32% at 6–10/week** (the 6–10 cohort is survivorship-selected — tolerant users remain). On perceived over-frequency: 42% change settings, 39% disable notifications entirely, **8% delete the app**.
  - Airship 2024–25 benchmarks (50B pushes): median opt-in **61.4% Android / 49.8% iOS**; average reaction (direct-open) rate **7.8%** (Android 10.7%, iOS 4.9%). CTR of 1–7% is the normal band by category.
  - Copy levers: **personalization ≈ 4x reaction rate** (Airship) and **+27% conversions** (Braze/Appboy study); **emoji +20%** reaction (Airship) but Braze warns the emoji lift decays with repetition; **rich media +25%**; **≤10 words ≈ 2x the CTR of 11–20 words** (Localytics).
  - Send timing: population-level peaks are 6–8am and 10pm–midnight (CleverTap, 301B pushes), but the consistent vendor finding is that **per-user send-time optimization beats any fixed hour**: Braze Intelligent Timing **+25% engagement** (their STO article; KFC Ecuador +15% opens), OneSignal Intelligent Delivery **up to +23% opens**. With FTF's small user base, approximate this with "send at the user's median historical session hour" — no ML needed. `[inference]`
- **Batching/digest evidence** `[peer-reviewed]`: Fitz et al. 2019 (RCT, 2 weeks): notifications batched **3x/day** improved mood, felt control, and productivity vs. deliver-as-they-arrive; **hourly batching ≈ no benefit; zero notifications was neutral-to-negative** (FOMO). So the answer to "digest vs real-time" is *neither extreme*: a small number of scheduled delivery moments per day/week wins.
- **Delivery cadence in a live reciprocal recommender** `[peer-reviewed, operational detail]`: in Kleinerman's live-app experiment the platform owner insisted on **one recommendation per day** delivered to the inbox with a push, each with unique visual tagging — the deployed-practice norm matches the research direction (scarce, paced, distinct).
- **Match-volume pacing as an ML output** — verification (see §6 sweep): the patent that actually covers this space, **US10540607B1 "reply rate matching"**, is owned by **Plentyoffish Media ULC (Match Group)**, not eharmony. It claims neural-net models predicting *which candidates are likely to reply to this specific user*, trained on messaging behavior, refreshed in near-real-time — i.e., **rank deliveries by P(response), not P(good match)** `[official patent]`. It contains **no claims on volume/timing throttling**. eharmony's on-record statements (CIO interviews) verify communication-likelihood models ("predict how likely a user will communicate … with a particular compatible person that we deliver as a match" — Jonathan Beber, eharmony R&D) but not the "ML decides how many and when" claim, which stays `[press/unverified]`.

### 1.4 Expiry & deadlines: short deadlines convert; sell the extension; warn before the drop

- **Hinge timed-match test** `[press, company-reported]`: when Hinge tested 24h match expiry in five markets (Denver, Omaha, Houston, Atlanta, Dallas), **conversations started AND phone numbers exchanged both rose ~50%** (Bustle, 2015). Note Hinge later chose not to keep hard expiry as its core mechanic — deadline pressure converts but fights the "designed to be deleted" brand `[inference from product history]`.
- **Deadline-length research** `[peer-reviewed]`: Shu & Gneezy 2010 — gift certificate with a **3-week deadline: ~31% redemption vs 2-month deadline: 6%**; gift-card field data 49% (short) vs 35% (long). Longer windows *feel* better (higher stated satisfaction) but produce procrastination. Implication: the deadline that maximizes completion is shorter than the one users say they want.
- **Shipped expiry implementations** `[official help docs]`:
  - **Bumble:** first move within **24h** of match; other side then has **24h** to reply (72h total inactivity kills the match); **one free Extend/day** (+24h), unlimited Extends paid; Rematch on expiry is a paid feature. Expiry is monetized twice.
  - **Coffee Meets Bagel:** 24h to act on the daily bagel; chats auto-close after ~7–8 days unless a message lands in the final 72h; reopening costs 99 beans (+30 days). Warning state before close.
  - **Tinder Top Picks:** the endorsed set itself expires in 24h.
  - Common grammar: **deadline (24h) → warning state → expiry → paid/limited resurrection.** Every app pairs the stick with a rescue product.
- **Streak/decay UI (loss-aversion framing)** `[reverse-engineered teardowns; treat numbers as directional]`: Duolingo teardowns report 7-day-streak users **3.6x** more likely to stay engaged long-term; Streak Freeze **−21% churn** among at-risk users; streak widget **+60% commitment**. The mechanism that matters: loss framing ("don't lose X") beats gain framing, and a *forgiveness valve* (freeze) increases long-term retention rather than weakening the mechanic.

### 1.5 Turn-taking & stall recovery: label whose move it is, sort by it, cap open loops

Hinge is the only product with a public, numbers-attached evolution here — three generations `[official/press]`:

1. **Your Turn (2017):** every match/chat carries an explicit whose-move-is-it label + reminder. Tested in London & DC with tens of thousands of users: **matches dying without a conversation −25%**. Focus-group finding worth stealing: **23% of ghosting was "got busy and forgot"** — a state-visibility problem, not a motivation problem.
2. **Match-list reordering (2023):** chats where it's *your* move sort to the top of the list. Result (company-stated): increased responsiveness.
3. **Your Turn Limits (2024 test):** users with **8+ chats awaiting their reply** cannot make new matches until they **reply or end** each one; "end" is a first-class, low-guilt action. Company-reported: **~20% increase in responsiveness**.

The implementation pattern is a small state machine per match: `your_move | their_move | stalled(t) | ended`, with (a) the state rendered on every surface, (b) sort order driven by it, (c) a cap on concurrent `your_move` items, and (d) a graceful `ended` exit so declines are cheap and honest instead of silent. The eharmony/PoF patent layer adds: prioritize *new* deliveries toward counterparties with high predicted response rates, which prevents stalls before they happen `[official patent]`.

---

## 2. Antipatterns

1. **Explaining the low-stakes action.** Reciprocal (two-sided) explanations *underperform* when accepting costs nothing (Kleinerman: relevance 3.34 vs 3.76). Don't attach "why you both win" essays to cheap actions like viewing or saving a trade — reserve the two-sided pitch for the expensive action (sending the offer). `[peer-reviewed]`
2. **Telling the user why THEY are attractive, in detail.** Kleinerman's debriefs found users uncomfortable with the system explaining their own appeal when it clashed with self-perception. In FTF terms: don't say "they want your RB because your roster is failing" — describe the *other side's need*, not the user's weakness. Use the asymmetric format (features for your side, confidence statement for theirs). `[peer-reviewed]`
3. **Optimizing explanations purely for persuasion.** The OkCupid "power of suggestion" experiment proved a displayed 90% score makes actual-30% pairs behave like good matches — persuasion works even when false `[official blog]`. But in a repeated-play product (a 12-team league, all season) a persuasive-but-wrong endorsement gets audited by reality: confidently-wrong errors damage trust more than any other error class, and late/high-stakes misses hurt most `[peer-reviewed]`. Dating apps get away with placebo scores because pairs rarely re-meet; leaguemates always do. `[inference]`
4. **Displaying uncapped confidence on thin data.** The anti-OkCupid pattern: showing "94% match!" off three data points. Display the lower bound; cap by data volume. `[official + peer-reviewed]`
5. **Fixed-clock notification blasts.** Sending everyone at "the best hour" leaves the 23–25% lift of per-user timing on the table, and >5 pushes/week puts you into the 46%-opt-out zone. `[industry-report]`
6. **Expiry without a warning state or rescue.** Every shipped implementation (Bumble, CMB, Tinder) pairs deadline → warning → paid/limited extension. A silent hard drop just deletes pipeline and angers users. `[official]`
7. **Unlimited open loops.** Letting a user accumulate 30 "their offer is waiting" threads reproduces the inbox-overload that Hinge's Your Turn Limits exists to fix. Cap it (~8 was Hinge's number) and provide a one-tap "decline politely" so ending is cheaper than ghosting. `[official/press]`
8. **Long notification copy.** ≤10 words ≈ 2x the CTR of 11–20 words. "The Bears need a WR. You have three." beats a paragraph. `[industry-report]`
9. **Running classical fixed-horizon A/B tests on hundreds of users.** At FTF scale a 5-point conversion lift needs thousands of users per arm; a naive t-test at N=150/arm only detects massive effects. Testing small UI deltas this way produces noise theater. Use the small-N designs in §3. `[peer-reviewed/industry practice]`

---

## 3. What matters most (ranked)

1. **Reciprocal explanation on the costly action** — the only intervention in this memo with a randomized, in-product, reciprocal-domain result (**53% vs 36% acceptance**; +17pp, ~1.5x) plus a trust lift, and it's nearly free to implement: two lines of copy per suggestion. Highest evidence-to-effort ratio. `[peer-reviewed]`
2. **One scarce endorsed pick, mutual and visually distinct** (Hinge 8x, round-1 confirmed; Tinder caps even its paid version at ~10/day with 24h expiry). This is the presentation fix for the scrollable-list problem: N small, one hero. `[official/press]`
3. **Turn-state visibility + sort + cap** (−25% dead matches; +20% responsiveness; 23% of ghosting is pure forgetting). Trades die in the gap between "generated" and "sent/answered" — this is the conversion machinery for two-party completion. `[official/press]`
4. **Deadline mechanics with warning + extension** (+50% conversations in Hinge's test; Shu & Gneezy 31% vs 6% redemption). Strongest known lever on *completion rate* of an accepted-in-principle action; also the most brand-risky (see §4.3). `[press + peer-reviewed]`
5. **Pacing: few deliveries, per-user timing, batched otherwise** (≤~3–5 pushes/week; per-user send time +23–25%; 3-batches-a-day beats streams). Protects the whole channel every other lever depends on — opt-out is nearly irreversible. `[industry-report + peer-reviewed]`
6. **Calibrated, capped confidence display** (OkCupid lower-bound; miscalibration research). Matters more the longer the user stays — it's the compounding-trust lever. `[official + peer-reviewed]`
7. **Copy mechanics** (≤10 words, personalization 4x, emoji +20%-but-decaying). Real but small relative to the structural levers above. `[industry-report]`

---

## 4. What doesn't matter (even though it seems like it should)

1. **Faithful/transparent explanations.** The *less* algorithmically faithful correlation-based explanations were rated MORE transparent (3.97 vs 3.41) and more useful than the method that truthfully mirrored the recommender. Users cannot perceive faithfulness; they perceive intuitiveness. Spend effort making explanations *concrete and plausible* (≤3 named features), not on surfacing actual model internals. (Ethical floor still applies — see antipattern 3.) `[peer-reviewed]`
2. **The precise truth of the displayed score, short-term.** OkCupid's placebo experiment shows behavior follows the displayed number, not the latent one. The number is a UI element, not a measurement readout — what matters is calibration *over repeated exposure*, not per-item precision. `[official blog + peer-reviewed]`
3. **Longer deadlines as user-friendliness.** Users report preferring long windows; long windows produce 6% vs 31% completion. Stated preference and behavior point in opposite directions here. `[peer-reviewed]`
4. **Population-level "best hour to send."** The 6–8am/10pm folk wisdom is real but tiny next to per-user timing, and irrelevant next to frequency discipline. `[industry-report]`
5. **More endorsement tiers.** No shipped product exceeds default + one endorsed tier on the consumer surface. Tier proliferation dilutes the scarcity that makes the endorsement work. `[reverse-engineered]`
6. **Emoji and rich-media styling as a durable lever.** Braze explicitly warns the lift decays with repetition — novelty effects, not structure. `[industry-report]`
7. **Real-time delivery of everything.** Fitz et al.: hourly ≈ no better than a stream; 3 scheduled batches/day is the winning cadence. Immediacy only matters for genuinely time-sensitive states (counterparty responded; offer expiring). `[peer-reviewed]`

---

## 5. Transfer notes for FTF

Concrete redesign implications for the trade-suggestion surface (current state: scrollable list; push exists):

1. **Suggestion card = reciprocal explanation, asymmetric format.** Two lines under every suggested trade:
   - *Your side, feature-rich (≤3 features):* "You get a starting-caliber WR2 for your playoff push."
   - *Their side, confidence-statement only:* "Based on their roster needs and recent activity, [Manager] is likely to be interested in this deal." Never expose the other manager's board/valuations (Kleinerman's privacy-driven format, which is also the socially safe one in a league).
2. **Replace the list with "Today's Trade" + bench.** One endorsed hero suggestion per league per delivery cycle (mutual-fit-ranked, Gale-Shapley-flavored: maximize P(you propose) x P(they accept), the PoF patent's P(response) idea applied to trades), plus a small collapsed "more ideas" set (cap ~5, Tinder-style). The endorsement badge is binary — endorsed or not — no ladder.
3. **Confidence display: OkCupid rule.** Show a mutual-fit indicator whose ceiling is capped by data volume (few Elo matchups completed by either manager → cap at "Moderate fit — rank 10 more players to sharpen this"). Never a two-digit percentage on thin data; prefer 3 labeled bands over numbers given FTF's N.
4. **Turn-state machine per trade thread:** `your_move | their_move | stalled(3d) | expired | ended`. Render the state chip everywhere the trade appears; sort "your move" to top; cap concurrent open proposals (start at ~5, Hinge used 8); one-tap "withdraw politely" with prewritten message so ending beats ghosting.
5. **Expiry with the full grammar:** endorsed suggestions expire when the next cycle lands (like Top Picks); *sent offers* get a 72h response window with a 24h-left warning push to the counterparty and one free "extend" per week for the proposer. Never silently drop — expire into a "revive" affordance.
6. **Pacing:** default **weekly digest per league** (suggestion refresh, batched per Fitz), sent at each user's median historical open hour; real-time push ONLY for two-party state changes (offer received, response received, expiring soon). Hard budget: ≤3 pushes/week/user from FTF total, autothrottled. This stays under the 46%-opt-out cliff and mirrors the 1/day norm every dating app converged on — trades are lower frequency than dates, so weekly is the analog. `[inference]`
7. **Copy:** ≤10 words, personalized with player/manager names: "Jets need RB help. Your bench has it." Loss-frame the expiry pushes ("Offer to Mike expires tonight"), gain-frame the digest.
8. **Small-N testing plan** (hundreds of users — do NOT run classical two-arm conversion A/Bs):
   - **Interleaving for ordering questions** (which suggestion ranks first): blend variant A and B orderings within the same user's list; needs ~10x less traffic than A/B and every user is their own control. Only valid for preference/ranking metrics. `[industry practice: Netflix/Etsy/Airbnb]`
   - **Within-user / within-league crossover** for presentation variants: alternate hero-card vs list by week per user, compare within-user proposal rates (each user as own control kills between-user variance, which is huge in fantasy engagement).
   - **Bayesian A/B with informative priors** for the few true between-user tests (e.g., explanation copy): Beta prior seeded from historical proposal rate at effective N≈50 (weak — the metric is new), monitor continuously, ship at P(better)≥95%; accept that only large effects (≥1.3x) are detectable — which is fine, because per §3 only the large-effect levers are worth building.
   - **Test the big structural changes, not micro-copy.** At this N, an experiment that can't detect less than a 30% lift is a feature, not a bug: it filters for the levers that matter.
9. **Trust discipline (the league repeated-game).** Because leaguemates re-encounter every endorsement outcome, adopt: conservative display (never show confidence you can't defend), degrade language before degrading numbers, and after a visibly bad endorsement (offer insta-rejected), *acknowledge in-product* ("Mike passed — we'll weight his behavior in future suggestions"). The miscalibration literature says undetected miscalibration silently destroys reliance; make the model's learning visible instead. `[peer-reviewed + inference]`

---

## 6. Primary-source verification sweep (round-1 claim upgrades)

| Round-1 claim | Verdict after sweep |
|---|---|
| Hinge Most Compatible 8x lift | **Confirmed `[official via press]`** — TechCrunch 2018 quoting Hinge's internal testing (8x more likely to exchange phone numbers). One per 24h, Gale-Shapley-based: confirmed in the same coverage + Harvard D3 case. **No Hinge patent found** for Most Compatible; the algorithmic detail rests on company statements, not patent record. |
| OkCupid displayed-score placebo | **Confirmed `[official]`** — Rudder's "We Experiment on Human Beings" blog post (archived at gwern.net); 30%-actual pairs shown 90% behaved like good matches; effect persisted beyond first message. Lower-bound display rule confirmed via OkCupid help/analyses. |
| Match expiry +50% conversations | **Confirmed with corrected attribution `[press]`** — it was **Hinge's** 2015 timed-match test (5 markets): +50% conversations AND +50% phone numbers. CMB/Bumble supply the shipped-implementation details (24h/72h/extend/beans), not the +50% number. |
| Turn-taking labels −25% ghosting | **Confirmed `[press, company-stated]`** — Hinge Your Turn 2017 test, London + DC, tens of thousands of users, −25% matches-without-conversation. Upgraded with 2024 sequel: Your Turn Limits (cap 8) → ~20% responsiveness gain `[official newsroom/PR]`. |
| eharmony "ML decides how many matches to send and when" (CIO interview) | **Downgraded to `[press/unverified]`.** The CIO articles verify communication-likelihood models used to select which matches to deliver (Beber quotes; ~20 affinity models), but contain no volume/timing claim. **US10540607B1 belongs to Plentyoffish Media ULC (Match Group), not eharmony** — round-1's attribution should be corrected. The patent claims reply-rate-predictive match selection (neural nets on messaging behavior, near-real-time refresh) and has **no pacing/volume claims**. Deliver-by-P(response) is `[official patent]`; deliver-N-at-time-T-by-ML remains reverse-engineered. |
| Tinder presentation ordering patents | **Partially confirmed `[official patent]`** — the "Matching process system and method" family (US8566327, US9733811, US9959023, US10203854, US11513666; Tinder Inc → Match Group) covers card-stack presentation of one suggestion at a time and double-blind mutual opt-in. Ordering *within* the stack is not meaningfully claimed in this family; Tinder's desirability-scoring specifics remain `[reverse-engineered]` (old Elo-era press). |

---

## 7. Not researched / follow-up topics

- **Kleinerman's follow-up** (Springer UMUAI 2020, "Supporting users in finding successful matches in reciprocal recommender systems") — likely contains the personalized-explanation extension (varying explanation type by user's inferred rejection cost); paywalled, not read.
- **Explanation length/format ablations in production** — no public A/B of 1 vs 2 vs 3 feature bullets; the k≤3 rule is lab-derived.
- **Match Group earnings-call detail on Your Turn Limits rollout results** (did the 2024 test ship globally? Blind chatter suggests engagement tradeoffs; unverified).
- **Braze/Airship category-level dating-app benchmarks** — vendors publish cross-category medians; dating/social-specific opt-out curves weren't publicly broken out.
- **Optimal deadline length for B2B-ish two-party actions** — Shu & Gneezy is consumer coupons; no direct evidence for the 24h-vs-72h-vs-7d choice on *offer response windows* specifically. Recommend FTF measure response-latency distribution of real accepted offers and set the window at ~p90.
- **Sports-trade-specific explanation research** — nothing found; the reciprocal-explanation transfer from dating is analogical.
- **Multi-armed bandits for suggestion ordering at small N** — plausible alternative to interleaving; not researched this round.
- **Loss-aversion framing A/Bs on push copy with published numbers** — vendor claims exist but no clean public experiment found.

---

## 8. Sources

**Explanation / reciprocal recsys (peer-reviewed):**
1. Kleinerman, Rosenfeld, Kraus — Providing Explanations for Recommendations in Reciprocal Environments, RecSys 2018 (full text read): https://u.cs.biu.ac.il/~krauss/data/articles/recsys18a-sub1364.pdf ; arXiv: https://arxiv.org/abs/1807.01227 ; ACM: https://dl.acm.org/doi/10.1145/3240323.3240362
2. Kleinerman et al. — Optimally balancing receiver and recommended users' importance, RecSys 2018: https://dl.acm.org/doi/10.1145/3240323.3240349
3. Kleinerman et al. — Supporting users in finding successful matches (UMUAI 2020, not read): https://link.springer.com/article/10.1007/s11257-020-09279-z
4. Tintarev & Masthoff — Designing and Evaluating Explanations for Recommender Systems: https://link.springer.com/chapter/10.1007/978-0-387-85820-3_15 ; survey: https://www.macs.hw.ac.uk/~dwcorne/ACMRecSys07/p203-tintarev.pdf
5. Whom do Explanations Serve? (survey, 2024): https://arxiv.org/pdf/2412.14193
6. Zhang & Chen — Explainable Recommendation: A Survey: https://arxiv.org/pdf/1804.11192

**Confidence display / trust calibration:**
7. Li et al. — Effects of Miscalibrated AI Confidence on User Trust (2024): https://arxiv.org/abs/2402.07632
8. Misclassification Severity and Timing → Trust (FAccT 2025): https://dl.acm.org/doi/10.1145/3715275.3732187
9. OkCupid "We Experiment on Human Beings" (archived): https://gwern.net/doc/psychology/okcupid/weexperimentonhumanbeings.html ; Forbes coverage: https://www.forbes.com/sites/kashmirhill/2014/07/28/okcupid-experiment-compatibility-deception/
10. OkCupid match-% margin-of-error math: https://blogs.ams.org/mathgradblog/2016/06/08/okcupid-math-online-dating/

**Endorsement mechanics:**
11. TechCrunch — Hinge Most Compatible (8x, Gale-Shapley, 1/day): https://techcrunch.com/2018/07/11/hinge-employs-new-algorithm-to-find-your-most-compatible-match-for-you/
12. Harvard D3 — Hinge and Machine Learning: https://d3.harvard.edu/platform-rctom/submission/hinge-and-machine-learning-the-makings-of-a-perfect-match/
13. Tinder Top Picks help doc: https://www.help.tinder.com/hc/en-us/articles/360005039092-Top-Picks ; launch: https://techcrunch.com/2018/09/11/tinder-launches-its-curated-top-picks-feature-worldwide/

**Notifications & pacing:**
14. MobiLoud push-notification statistics roundup (Localytics/Airship/CleverTap aggregate): https://www.mobiloud.com/blog/push-notification-statistics
15. Airship 2025 push benchmarks: https://www.airship.com/resources/benchmark-report/mobile-app-push-notification-benchmarks-for-2025/ (PDF: https://growth.airship.com/rs/313-QPJ-195/images/Airship-2025-Push-Notification-Benchmarks-EN.pdf)
16. Braze — Send-Time Optimization: https://www.braze.com/resources/articles/send-time-optimization ; Intelligent Timing: https://www.braze.com/docs/user_guide/brazeai/intelligence_suite/intelligent_timing ; push best practices: https://www.braze.com/resources/articles/push-notifications-best-practices
17. OneSignal — Intelligent Delivery (+23% opens): https://onesignal.com/blog/increase-open-rates-by-up-to-23-percent-with-intelligent-delivery/ ; timing: https://onesignal.com/blog/optimizing-notification-timing/
18. Fitz et al. — Batching smartphone notifications can improve well-being (2019): https://www.sciencedirect.com/science/article/abs/pii/S0747563219302596 (PDF: https://static1.squarespace.com/static/57a40c19414fb54f51f8095f/t/685daca461a93c25f5b3dabe/1750969509917/2019+Fitz+Batching.pdf)

**Expiry / deadlines / streaks:**
19. Bustle — Hinge timed matches +50%: https://www.bustle.com/articles/120965-dating-app-hinge-will-now-time-your-matches-to-get-you-talking
20. Bumble Extend: https://bumble.com/en-us/the-buzz/bumble-extend-match ; expired matches: https://support.bumble.com/hc/en-us/articles/28424238819357-Expired-matches
21. Coffee Meets Bagel chat extension: https://coffeemeetsbagel.zendesk.com/hc/en-us/articles/360020787834-How-do-I-extend-a-chat
22. Shu & Gneezy — Procrastination of Enjoyable Experiences (JMR 2010): https://journals.sagepub.com/doi/abs/10.1509/jmkr.47.5.933 (PDF: https://anderson-review.ucla.edu/wp-content/uploads/2021/03/Shu-Gneezy_ProcrastinationofEnjoyable_2010.pdf)
23. Duolingo streak teardowns (directional): https://duolingo.deconstructoroffun.com/mechanics/streaks ; https://apptitude.io/blog/how-duolingos-streak-mechanic-actually-works/

**Turn-taking:**
24. TechCrunch — Hinge Your Turn (−25% ghosting): https://techcrunch.com/2017/12/20/dating-app-hinge-rolls-out-a-new-feature-to-reduce-ghosting/
25. Hinge newsroom — Your Turn Limits test (cap 8, ~20% responsiveness): https://hinge.co/newsroom/your-turn-limits-test ; PR: https://www.prnewswire.com/news-releases/hinge-tests-limiting-unanswered-messages-to-reduce-dating-burnout-302144187.html
26. Hinge help — What is Your Turn: https://help.hinge.co/hc/en-us/articles/26848706496659-What-is-Your-Turn

**Patents & pacing verification:**
27. US10540607B1 — reply rate matching (Plentyoffish Media ULC): https://patents.google.com/patent/US10540607B1/en
28. Tinder matching-process patent family: https://patents.google.com/patent/US10203854B2/en ; https://patents.google.com/patent/US9733811B2/en ; https://patents.google.com/patent/US11513666B2/en ; GDI on the 2013 patent: https://www.globaldatinginsights.com/news/tinders-swiping-matching-model-patented-2013/
29. CIO — How eHarmony uses data science for matchmaking (Beber quotes; fetched and checked): https://www.cio.com/article/213555/how-eharmony-uses-data-science-for-matchmaking.html ; Click Me Maybe: https://www.cio.com/article/206096/click-me-maybe-inside-eharmony-s-matchmaking-machine.html

**Choice overload (context):**
30. Pronk & Denissen — A Rejection Mind-Set: Choice Overload in Online Dating (SPPS 2020): https://journals.sagepub.com/doi/10.1177/1948550619866189

**Small-N experimentation:**
31. Etsy Engineering — Faster ML Experimentation with Interleaving (~10% of A/B traffic): https://www.etsy.com/codeascraft/faster-ml-experimentation-at-etsy-with-interleaving
32. Airbnb — Interleaving + counterfactual evaluation for search ranking: https://arxiv.org/html/2508.00751v1
33. Navigating the Evaluation Funnel (interleaving limits): https://arxiv.org/pdf/2404.08671
34. Statsig — When to use Bayesian experiments: https://www.statsig.com/blog/bayesian-experiments-beginners-guide ; caveats: https://www.statsig.com/perspectives/bayesian-ab-testing-beyond
35. Analytics-Toolkit — A/B testing with small sample size: https://blog.analytics-toolkit.com/2019/a-b-testing-with-a-small-sample-size/
36. Speicher — Bayesian A/B testing practical primer: https://uxdesign.cc/bayesian-a-b-testing-a-practical-primer-c0d4ab1c689e
