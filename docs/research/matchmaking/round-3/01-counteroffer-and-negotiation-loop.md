# Counter-offer dynamics and the negotiation loop

> Round-3 matchmaking research. Topic flagged by round-2/02 §7 ("Counter-offer dynamics: what to do after a decline — negotiation-dance literature on concession reciprocity untouched") and round-2/04. FTF generates and anchors the first offer; today a decline is a dead end, and every real counter-offer happens off-app in Sleeper. This memo is about the loop that should exist between "declined" and "closed."

**Confidence tags**

| Tag | Meaning |
|---|---|
| `[PR]` | Peer-reviewed journal or top-tier conference |
| `[WP]` | Working paper / preprint |
| `[OFFICIAL]` | Platform's own docs, help centre, or newsroom |
| `[TEARDOWN]` | Third-party observation of a live product |
| `[VENDOR]` | Marketing/benchmark aggregator — directionally useful, methodology undisclosed |
| `[PRACTITIONER]` | Domain-expert writing, no formal evidence |
| `[INFERENCE]` | My reasoning on top of the above |

**Sourcing note.** The empirical-bargaining core (§1.1–1.7) is unusually solid: I extracted and read the *full text* of the QJE eBay paper, the round-numbers working paper, the eBay-Germany communication paper, and the Mercari bargaining paper, so those numbers are quoted from the papers themselves, not from abstracts. §1.9 (marketplace mechanics), §1.8/§1.10–1.12 (mediation, reciprocity, fatigue, decline reasons, staged commitment) and §1.14 (automated negotiation) come from three parallel research threads working mostly from official help-centre docs and primary PDFs. Where a source could not be opened at the primary (paywall, 403, unrendered record page), it is marked inline.

---

## 0. TL;DR

1. **A decline is weak evidence that no deal exists.** For the median product on eBay, **37% of negotiations end in impasse even when the buyer values the good more than the seller** (Freyberger & Larsen, *Econometrica* 2025). In post-auction used-auto bargaining, **more than half of failed negotiations had gains from trade**, costing 12–23% of available surplus (Larsen, *ReStud* 2021).
2. **No marketplace treats a decline as terminal.** eBay states it outright: after a decline the buyer can offer higher or the seller can counter. Across eight platforms audited, **zero** end the thread on a decline. FTF is currently the outlier, and not in a good way.
3. **Real bargaining is short and quits early.** Mean **1.66 offers per thread**; **1.48** when it sells. After a seller counters, the most common buyer response is to **walk away (58%)**. The dead end is the human default; supplying persistence *is* the product.
4. **Concessions are reciprocal, gradual, and time-critical.** Concession weight regressed on the opponent's previous concession weight is positive in every round (β ≈ 0.12–0.23); **98.8%** of sellers concede at least a little on their first counter. And door-in-the-face field work found the reciprocity effect **works immediately but dies after a three-minute delay** — which forces a **two-clock design**.
5. **Words and commitment are worth more than money.** Attaching free text to an offer raised transaction probability **+7.4–7.7 pp on a 44.2% base (≈14% less breakdown)**. On Mercari, a pledge of immediate payment is worth **+26.8 pp on acceptance** — equivalent to being allowed a **19.6% deeper discount**.
6. **The best anti-pester mechanism already exists and is published.** Poshmark's per-recipient ratchet: a repeat offer to the same person must be **≥10% below your lowest offer to them in the last 90 days**. It makes pestering structurally unprofitable rather than merely rate-limited.
7. **Spend the effort on *what* to re-offer, not on modelling the decliner.** In a 277,200-session decomposition of automated negotiating agents, the **bidding strategy explains 58% of performance variance; the opponent model explains 3.5%** — and a *bad* opponent model scores worse than no model at all.
8. **Change one thing per revision.** Candidate elimination: a decline on a package that differs by exactly one asset tells you that asset was the blocker. Change three things and the "no" teaches you nothing.
9. **Do not optimise the loop for acceptance rate.** A documented RL failure mode: reward structures that "give zero reward to a rational walk-away" restore deal rates to 99% while eroding surplus back to the untrained baseline. An app that maximises acceptances converges on suggesting trades that are easy to accept and bad for the user.

---

## 1. Best practices

### 1.1 The empirical shape of the loop

**Backus, Blake, Larsen & Tadelis, "Sequential Bargaining in the Field," *QJE* 135(3), 2020** `[PR]`, read in full. 88.4M Best-Offer-enabled US listings (May 2012–Jun 2013); 18.2M received ≥1 offer; **25.45M bargaining threads**; 1.2M sellers, 4.7M buyers. Protocol at the time: list price = seller's opening offer; buyer opens the bargaining; **3 offers per side**; **48h expiry**; hidden seller **auto-accept** / **auto-decline** thresholds.

- **Threads are short.** Mean **1.66** offers/thread (median 1, max 6); **1.48** conditional on selling. Stable across categories (1.54–1.70).
- **Agreement rate 45.4%** (31.7% electronics → 59.6% media).
- **Opening asks are aggressive and consistent.** First buyer offer = **60.8% of list** (median 0.626), stable across categories (0.575–0.660). Final bargained price = **72.7% of list**. The typical negotiation closes ~60% of the way from the opening bid back toward the ask — *most of the value is created after the first offer*.
- **The game tree (Fig. III).** After the buyer's first offer: seller **accepts 32%**, **declines 40%**, **counters 28%**. After a seller decline: buyer **quits 62%**, counters ~38%. After a seller counter: buyer **accepts 17%**, **quits 58%**, **counters 25%**; if the buyer counters, seller accepts 31%.
- **Only 32% is immediate agreement** — the one branch classical theory explains. The other 68% is delay, impasse, or *delayed impasse*, which almost no bargaining model generates.
- **Round caps almost never bind.** Only **1.1%** of interactions reach the 3-offer limit, and **most of those fail**. eBay raised the cap to 5 in 2017 specifically to rescue them.

**Practice:** design for a **two-to-three-move loop**, not a chat thread. The modal successful path is offer → counter → accept.

### 1.2 Reciprocal gradualism is the strongest regularity in the data

Concession weight γ_t defined by p_t = γ_t·p_{t−1} + (1 − γ_t)·p_{t−2} — how much weight your new offer puts on your opponent's last offer vs. your own.

- **Concessions beget concessions.** γ_t on γ_{t−1} is positive and highly significant at every round t = 3,4,5,6: **0.125, 0.226, 0.156, 0.124** (used goods); 0.120, 0.223, 0.149, 0.166 (new). Same result regressing percentage offer changes. `[PR]`
- **Gradualism, not war-of-attrition.** Only **0.77%** of sellers hold firm at list then concede in a jump; **98.8%** concede a little on their very first counter. Buyers: 0.42% vs **95.9%**. The "stonewall then capitulate" equilibria describe under 1% of real behaviour. `[PR]`
- **Default concessions are partial.** Typical γ sits *below* 0.5 — closer to the sender's own prior offer than the opponent's. Meeting in the middle is a distinguished special case, not the norm. `[PR]`
- **Concession adapts to opponent strength.** Players concede more against a more experienced opponent, less when experienced themselves. `[PR]`

### 1.3 Split-the-difference is a real, exploitable salience effect

- **~8% of offers land exactly at the midpoint** of the last two offers (γ ≈ 0.5 to the nearest hundredth); 11% at nearest-0.05, 16% at nearest-0.1. The midpoint is the **modal** offer for the buyer's first offer, the seller's first counter, and the buyer's first and second counters. `[PR]`
- **Split offers are 5–10 pp more likely to be accepted** controlling for actual generosity, "curiously stable" across all six rounds. `[PR]`
- The implication the authors flag: this is **non-monotonic** — a split offer beats an offer that is *slightly more favourable to the accepter*. No standard theory, including inequity aversion, explains it. It reads as a norm/salience effect. `[PR]`
- Counterweight from practice: offering to split reveals you have more to give, and 50/50 "overlooks the actual value being exchanged when parties bring different priorities." The practitioner rule of thumb is *never offer to split, but there can be reasons to accept someone else's offer to*. `[PRACTITIONER]`

**Practice:** when a counter exists, propose exactly the midpoint and **say it is the midpoint** — but do it as the *closing* move, not the opening revision.

### 1.4 A decline is a strategic move carrying information in both directions

**Green & Plunkett, "The Science of the Deal," ACM EC'22 (Best Paper)** `[PR]` — deep-RL agent trained inside a learned model of human eBay bargaining. As seller it sells more often *and* at higher prices; as buyer it buys more often *and* cheaper.

- Headline learned tactic: **the seller rejects most first offers, especially generous ones**. A generous first offer reveals willingness to pay; declining it signals "the list price is firm," and **human buyers often respond by paying full list**. `[PR]`
- The agent was constrained to offers common in the data (offline-RL extrapolation); the tree is shallow *because eBay caps each side at three offers*. `[PR]`

**Practice, two directions:** (a) don't hard-update "no trade exists" on one decline — update "this package at this split was rejected"; (b) protect your own user from panic generosity, because capitulating after a rejection is exactly the human behaviour the optimal agent farms.

### 1.5 Attach words to the offer

**Backus, Blake, Pettus & Tadelis, "Communication, Learning, and Bargaining Breakdown," *Management Science* 2023** `[PR]`, read in full. Natural experiment: on 23 May 2016 eBay Germany let **desktop** Best Offer users attach free text to an offer; mobile users could not.

- Baseline success **44.2%**. Messaged (complier) interactions **+7.44 pp** (+7.73 pp with controls) more likely to transact ⇒ **~14% reduction in breakdown**.
- **Adoption was immediate; the effect was not** — it grows over ~4 weeks then stabilises. Repeat players *learn how to communicate*.
- Content that works is mundane: **justifying** the price or condition, concrete item information, politeness. Messages resembling experienced sellers' content are likelier to be accepted.
- Concentrated on low stakes: **8.98–10.44 pp** for asks under $50, only 2.41–3.51 pp above $150. Fantasy trades are psychologically low-stakes. `[INFERENCE]`

**Caveat from the marketplace audit:** *none* of the eight platforms surveyed requires or even prompts a note on an offer — "the offer object is a number plus a clock," with messaging in a parallel thread `[OFFICIAL]`. So the industry has **not** internalised this result. That is an opportunity, not a warning. `[INFERENCE]`

### 1.6 Credible commitment beats a better price

**Kuno, "Buyer Commitment in Bilateral Bargaining" (2026 WP, Mercari data)** `[WP]`, read in full.

- Match outcomes: purchase at list **47.3%**, offer made and accepted **20.0%**, neither **32.7%**; an offer is made in 32.0% of matches.
- **37.4% of accepted offers end with the buyer not purchasing.** "Yes" is not the end of the funnel.
- **41.4%** of buyer offer messages contain an immediacy/immediate-payment pledge.
- Holding the discount constant, a pledge is worth **+26.8 pp on acceptance**, **−8.9 pp** walkaway, **~15% faster** completion — equivalent to being allowed a **19.6% deeper discount** at constant acceptance probability.
- Calibration on greed: **a 10 pp deeper discount ask costs ~13.6 pp of acceptance probability.**

Corroborating design evidence: OfferUp attaches a **card authorization** to an offer explicitly to cut no-shows `[TEARDOWN]`; eBay introduced immediate-payment-on-acceptance for the same reason `[WP, cited in Kuno]`; Mercari, Depop, Poshmark and StockX all make acceptance **binding** `[OFFICIAL]`.

### 1.7 Round numbers signal flexibility; precise numbers signal firmness

**Backus, Blake & Tadelis** (WP 2015; *JPE* 127(4), 2019) `[PR]`, WP read in full.

- Listings at multiples of $100 get offers and sale prices **5–8% lower**, offers **6–11 days sooner**, and are **3–5% more likely to sell** than neighbouring precise listings. (The published JPE version reports 8–12% lower offers and 15–25% higher sale probability.)
- Sellers using *precise* prices are **less likely to accept a comparable offer** and **counter more aggressively**.
- Identified causally via UK listings currency-converted onto the US site; replicates in Illinois real-estate data.

**Practice:** numeric presentation is a dial on the speed/surplus frontier. Round values ("about 4,000") for throughput; precise ones ("4,137") to defend the initiator's surplus. Choose per mode deliberately. `[INFERENCE]`

### 1.8 Mediated renegotiation — the single most transferable framework

FTF is the neutral, so the mediation literature applies more directly than the bargaining-party literature does.

- **Single Negotiating Text (SNT).** A neutral drafts a document reflecting *interests, not positions*, shows it to each side separately, and explicitly asks for **criticisms of the draft, not concessions or counter-proposals**. It incorporates the criticism, re-circulates, and repeats — producing "a document from which all major objections have been removed." Operational rules: mark it DRAFT; review with each party without letting them keep a copy; state explicitly that you are **not** asking for accept/reject yet; **only when no further improvement is possible do you flip and ask for a yes/no**. `[PRACTITIONER]`
- **Why criticism instead of counter-proposals:** it stops parties retreating into opposing positions. Fisher & Ury single it out as especially effective when parties won't cooperate "for personal or emotional reasons." `[book, via study guide]`
- **Camp David 1978** is the canonical case: Carter controlled a single draft through **23 drafts over 13 days**, incrementally locking in agreed points. `[TEARDOWN]`
- **Mediator's proposal (the closing device).** The mediator names one settlement and takes **confidential, double-blind** yes/no from each side. If it's a yes and a no, the mediator publishes **"two no's"** — the accepting party is never exposed. Rationale: confidential acceptance lets people show movement "without fear that they will be setting a new floor or ceiling." **Use it late** — deploying it early squanders it. `[PRACTITIONER]`
- **Sequential mediator's proposals are a real practice** — one commercial matter ran **eight or nine** successive written proposals — but they carry a specific failure mode: **strategic delay**, where parties stall precisely to see how far the mediated revisions will travel. In that documented case, counsel eventually started exchanging drafts *directly* once they could see the projected path. That is the argument for **handing the pen back** after a bounded number of iterations. `[PRACTITIONER]`
- **Post-settlement settlement (PSS).** Raiffa (1985): after a deal is signed, a neutral hunts for Pareto improvements with the original agreement as the guaranteed fallback. `[PR — abstract only]` **But the empirics are discouraging:** Gettinger, Filzmoser & Koeszegi (2016) note "prior research reports low agreement-rates in post-settlement negotiations," and in their lab study renegotiators "focus rather on an extension than on a reallocation of welfare gains." `[PR]` Treat PSS as a tempting-but-unproven FTF feature.

### 1.9 Marketplace counter-offer mechanics — what the industry converged on

Audited across eight platforms, mostly from official help centres.

**eBay Best Offer** `[OFFICIAL]`
- **5 counteroffers per side**; buyers may submit up to **5 offers per item** (10 in most vehicle categories).
- Expiry: **buyer offers 24h**; **seller counteroffers 24h**; **seller-initiated "Offers to Buyers" 96h** on ebay.com/.co.uk (48h elsewhere). The seller-initiated window is **4×** the buyer window — a deliberate asymmetry. (The 48h figure in the 2020 QJE paper is now stale for buyer offers.)
- **Auto-accept** above an upper limit, **auto-decline** below a lower limit, manual review in the band between.
- **Declining does not end the thread**: "the buyer can make a higher offer, or you can send a counteroffer manually."
- **Offers to Buyers**: goes to the **30 most recent interested buyers** (watched or carted **within 5 days**); if more than 30 qualify, **30 every 48h** until covered; offers must be **≥5% below** Buy It Now. Adjacent: coupons can't go to a buyer who got one **in the last 14 days**.

**Mercari** `[OFFICIAL]` — the most precisely specified cooldown system found
- Counteroffer → buyer has **24h**; acceptance **charges the buyer automatically** (binding).
- **Offer to Likers**: **50 most recent likers**, valid **24h**, must be **≥10% below the item's *historically lowest* price**, **once per 72h**.
- Promote: ≥5% below historical low, once per **24h**. Time-Limited Sale: ≥10% below historical low, runs 3 days, item listed 7+ days, once per **72h**.
- **No published cap on counter rounds and no minimum offer percentage** for buyer offers.

**Poshmark** `[OFFICIAL]`
- Offer to Likers: **≥10% below current price**; offers expire in **24h**.
- **The best anti-pester rule published anywhere:** a liker will not receive the offer unless it is **at least 10% below your lowest offer to that same liker in the last 90 days**. A per-recipient, 90-day decaying ratchet.
- Original 2018 launch also required a shipping discount; later reporting says that was dropped `[TEARDOWN]`.

**Depop** `[OFFICIAL]` — the only platform publishing volume data
- Offers valid **24h**; recipient can accept, reject, or counter. Binding `[TEARDOWN]`.
- **Over 40% of all items are now bought via offers**; **62M offers** in a year; **2M seller-sent offers per week**; buyers achieve an **average 23% reduction** via offers.

**Vinted** `[OFFICIAL]` — the outlier on every axis
- **Buyers capped at 25 offers per day** platform-wide (not per item); sellers uncapped.
- **Maximum 40% discount** — a hard floor against lowballing, applying to both sides.
- **No expiry** — offers "are always valid." **Non-binding**: the item stays available to everyone until the buyer presses Buy Now.

**OfferUp** `[TEARDOWN]/[OFFICIAL snippet]` — offers auto-cancel at **48h**; counteroffers exist with no published cap; **Hold Offers** authorizes the buyer's card and requires a meeting within **6 days**.

**StockX** `[OFFICIAL]` — the control case: **no counter-offers at all**. A double-auction order book; Bid matches Ask and executes with no human step; "Sell Now"/"Buy Now" cross the spread. Expiry is a user-chosen menu of **1/3/7/14/30/60 days**.

**Convergent patterns**

| Pattern | Evidence |
|---|---|
| **24h is the default expiry** | eBay buyer offers, eBay counters, Mercari counters, Mercari Offer-to-Likers, Poshmark, Depop — all 24h, with no coordination |
| **Round caps are rare** | Only eBay publishes one (5/side). Mercari, Depop, Vinted, Poshmark, OfferUp publish none. The loop is bounded by **expiry and offer economics**, not by a counter counter |
| **Decline is never terminal** | True on all eight platforms; eBay states it explicitly |
| **Minimum-discount floors gate nudges** | 5% (eBay Offers-to-Buyers, Mercari Promote) or 10% (Mercari/Poshmark Offer-to-Likers, Mercari TLS). **Mercari measures against the *historically lowest* price** — kills the inflate-then-discount exploit |
| **Cooldowns run on 24h/72h clocks** | Mercari 24h/72h, eBay batches of 30 per 48h, eBay coupons 14 days. Poshmark's per-recipient 90-day ratchet is the sophisticated variant |
| **"Offer to interested parties" is table stakes** with a capped audience and a recency window | eBay 30/48h, watched within 5 days; Mercari 50 most recent likers |
| **Auto-accept/auto-decline bands are eBay's alone** | The clearest unbuilt feature elsewhere |
| **Binding acceptance is what makes short timers safe** | Binding: Mercari, Depop, Poshmark, StockX. Non-binding: Vinted — which is precisely why Vinted has no timer |
| **Offers carry a number, not a conversation** | None of the eight requires or prompts a free-text note. Contradicts §1.5's evidence — an unexploited edge |
| **The loop is load-bearing where it exists** | Depop: 40%+ of purchases via offers. StockX: 0% — negotiation UX is for heterogeneous, hard-to-price inventory; order books are for fungible liquid inventory |

**The StockX lesson for FTF:** dynasty assets are heterogeneous and hard to price, and FTF's own tiering exists because there is no clearing price. That places FTF firmly on the negotiation-loop side of the split, not the order-book side. `[INFERENCE]`

### 1.10 Reciprocity of concessions — and the three-minute rule

- **Cialdini et al. (1975), door-in-the-face.** Large request → target request: **50%** compliance; target-only control **17%**; exposure control (heard the large request, asked only the small one) **25%**. The 50-vs-25 gap is what rules out pure anchoring/contrast. Average absolute gain across the first three experiments ≈ **26 pp**. `[PR]`
- **It replicates.** Genschow et al. (2021), N = 391: **34%** (small request only) vs **51%** (DITF) — "nearly identical to the rates observed by Cialdini," 46 years and a continent apart. `[PR, via secondary write-up]`
- **The mechanism is contested** — reciprocal concessions is Cialdini's account, but empirical support is mixed; social responsibility, self-presentation and guilt compete. `[PR]`
- **THE most product-relevant moderator: delay kills it.** Restaurant field research found DITF worked when the second request came **immediately** after the rejection and **failed with a three-minute delay**. `[PR, via encyclopedia summary]`
- **In-group requesters do better** than out-group, though the effect survives both. `[PR, via same]`
- DITF and foot-in-the-door show **no significant difference** in effectiveness across 22 studies. `[PR, via same]`

- **GRIT (Osgood, 1959).** One side makes a *small* unilateral concession, communicates the expectation it will be matched, and **escalates on reciprocity** ("a peace spiral"); if ignored, it follows with a **second or even third** initiative. Concessions "should not be terribly costly (materially or strategically), nor should they suggest weakness." `[PRACTITIONER]` The commonly cited extra rules — announce in advance, keep concessions verifiable, retain retaliatory capacity — appear only in secondary summaries and are **low confidence**.
- **The Kennedy Experiment (1963)** is the field test: a step "large enough to be noticed, but small enough not to endanger security," announced with "an unambiguous statement of a new, peaceful policy." Khrushchev responded by dropping his prior demands; negotiations ran **12 days**; Senate ratified 80–19. `[TEARDOWN]/[OFFICIAL archive]`
- **Lindskold (1978)**, *Psychological Bulletin*: **unilateral initiatives produced more concession-making and less hostility than pure tit-for-tat**; tit-for-tat retaliation raised hostility initially and reduced it only over time. `[PR — record page would not render; medium confidence]`

**Practice:** the *proposer's* side is the natural first conceder; make the concession small, legible, and explicitly labelled as a step toward the other party; and **land it in the same session as the decline.**

### 1.11 Re-offer, pestering and cooldowns

All figures below are `[VENDOR]` unless marked. They disagree across vendors; use them as guardrails, not targets.

- **Frequency is the #1 cause of opt-out** — **20–30% of unsubscribes** attributed to volume across independent surveys.
- **Triggered sends churn ~2.4× faster than scheduled ones**: unsubscribe **0.182%** (automated) vs **0.077%** (scheduled) vs **0.067%** (transactional). A decline-triggered re-offer is exactly the risky class.
- **Push:** 1/week → **10%** disable; 6–10/week → **32%** opt out; >6 notifications → 46% disable / 32% uninstall (this last cluster looks like one much-recycled study). ~50% cite "too many."
- **Category variance is huge** (iOS opt-in: 79% ride-sharing → 39% social), and **age moderates** (57% of over-60s disable at 2–5/week vs 31% of 18–29s).
- **Sales cadence converges on 3–5 follow-ups**, with sharp diminishing returns past step 5; spacing of **2–3 days** reportedly lifts replies **11%** vs daily or longer gaps; **steps 3–5 drive 53.5%** of email-sourced meetings — so one-and-done is too conservative.
- **Reactance is the mechanism and repetition amplifies it.** A meta-analysis finds repeated-effort requests induce greater reactance than one-time ones, and "repeated exposure to bossy… messages could lead to a general resistance." `[PR]`
- **The cheap antidote is contested.** "But you are free" (BYAF): Carpenter's 2013 meta-analysis of 42 studies found it effective, but a 2023 pre-registered re-analysis of 74 effect sizes found g = 0.44 overall **yet no effect among low-risk-of-bias studies (g = 0.11, CI [−0.18, 0.40])** with "critically low reproducibility." `[PR]` Ship the explicit out because it is nearly free and honest, not because the effect is established.
- **Shipped precedent for auto-decay:** LinkedIn **auto-disables Open to Work** when a member stops responding to recruiter messages. Silence is a signal; stop the flow without waiting to be muted. `[OFFICIAL]`

**The two-clock reconciliation.** §1.10 says revise *within minutes*; §1.11 says re-offer *no faster than every few days*. These are not in conflict — they are two different clocks. **Reciprocity clock (minutes–hours):** the revision that answers a decline, in-session. **Fatigue clock (days):** a fresh approach to the same manager after the chain is exhausted. `[INFERENCE]`

### 1.12 Decline-reason capture and staged commitment

**What shipped products actually do** — the taxonomy is short, non-accusatory, and feeds a *filter*, rarely a stated model update.

- **DoorDash** has the richest verified taxonomy: decline → a confirmation screen showing the acceptance-rate consequence → **reason selection from ~a dozen options** ("Distance is too far," "Order is too small," "I don't want to go to this store," …) plus **"Something else"** requiring free text. Acceptance rate is a rolling average over the **last 100 offers**. `[TEARDOWN]`
- **LinkedIn Recruiter InMail** is deliberately binary — "Yes, interested" / "No thanks," each auto-filling an editable templated reply. **No reason taxonomy.** Declining with only the template **closes the thread**; typing a real reply keeps it open. `[OFFICIAL]`
- **Spotify** ships three negative signals with three different **scopes**: *Not interested* → fewer similar recommendations; *hide* → never again **in that playlist**, with Premium *snooze* = not suggested **anywhere for 30 days**; *exclude from taste profile* → less influence on future recommendations. It also notes implicit non-engagement signals alongside explicit ones. `[OFFICIAL]`
- **Netflix**: three-level thumbs, **no "why" taxonomy at all**. `[TEARDOWN]`
- **Meta ads**: hide ad / hide advertiser / why am I seeing this / report — and the "why" surface asks you to rate the *explanation*, not to give a reason. Meta's own language is hedged: feedback "may impact which ads we show you." `[OFFICIAL]`
- **Airbnb**'s published help text on declining is vague — no option list or penalty structure in the official article. `[OFFICIAL]`
- **Reliability:** the say/do gap is driven by limited self-awareness rather than dishonesty — "people genuinely do not know why they chose what they chose, so when asked, they confabulate a plausible reason." Remedies anchor stated preferences to revealed behaviour (de Corte et al. 2021, *Health Economics*). `[PR]`

**Staged commitment — the M&A ladder is the cleanest template.**
- **IOI**: non-binding, pre-diligence, price often stated as a **range** ("$650–700M"), high-level structure, funding, remaining diligence. **LOI**: later, a **single point bid** replacing the range, confirmed structure, timeline, **exclusivity typically 30–60 days**, closing conditions. Binding-ness: IOIs entirely non-binding; LOIs non-binding **except** exclusivity and break-up fees, which are enforceable. Some processes run a **second, refined IOI round** before data-room access. `[PRACTITIONER]`
- **Exclusivity is the price of escalation** — the seller stops shopping for 45–60 days in exchange for real buyer commitment. `[PRACTITIONER]`
- **Real estate mirrors it**: a non-binding Expression of Interest vs. an enforceable Offer to Purchase. `[PRACTITIONER]`
- **Dating apps have the probe but not the exclusivity, and leak badly**: Bumble ~26% message response rate (opt-in by design), but **~70% of matches stall before plans are made**; Tinder match→first-date ~3% (men)/~8% (women); Hinge claims 2× Tinder's date rate. `[VENDOR/TEARDOWN, low confidence]`
- **LinkedIn's probe is a persistent *state*, not a message**: Open to Work with three visibility tiers, plus specified titles/locations/types/start dates. Lower friction than per-item probes and it generates preference data continuously. `[OFFICIAL]`

### 1.13 Fantasy-specific norms

- **Sleeper's Trade Center supports counters natively** — open an incoming offer, modify it, send it back; counters stay in the same thread. Declining ends the thread; countering keeps it alive. `[OFFICIAL]/[TEARDOWN]`
- Community norm: **keep the originally-requested player in your counter.** If someone asked for player X, they want X; removing X restarts the negotiation. `[PRACTITIONER]`
- Dynasty leagues are explicitly **repeated games** — long relationships with the same 9–11 people, so lowball spam carries durable reputational cost ("a bit of a stigma"). `[PRACTITIONER]`
- Simultaneously, practitioners endorse **breadth**: to make a lot of trades you must make a lot of offers, and shopping an asset to every team with the matching piece is acceptable *if done openly*. `[PRACTITIONER]` This matches eBay's finding that 7.8% of listings had ≥2 buyers bargaining at once, which *raised* seller prices `[PR]`.

### 1.14 Automated negotiation: what ANAC actually learned about the re-offer loop

This is the engineering literature for exactly this problem, and several of its results are counter-intuitive enough to change the build.

**The tactic taxonomy (Faratin, Sierra & Jennings 1998)** `[PR]`. Offers are generated as `x(t) = min_j + α_j(t)·(max_j − min_j)`, with `α(0) = κ` (the opening-offer constant) and `α(t_max) = 1` (fully conceded at the deadline). Two families, both parameterised by **β**:
- Polynomial: `α(t) = κ + (1 − κ)·(min(t, t_max)/t_max)^(1/β)`
- Exponential: `α(t) = exp((1 − min(t, t_max)/t_max)^β · ln κ)`
- **β < 1 = Boulware** (hold, then concede at the deadline); **β = 1 = Linear**; **β > 1 = Conceder** (rush to reservation value). Later literature writes this as *e*, with **e = 0.2 the Boulware baseline and e = 2 Conceder**.

**Behaviour-dependent (imitative) tactics** come in three flavours — relative tit-for-tat (mirror the opponent's *percentage* concession from δ steps ago), random absolute tit-for-tat (mirror the *absolute* concession, plus a random perturbation to escape local minima), and averaged tit-for-tat (over a window γ). Real agents combine tactics via a weighted linear blend, often switching weights from Boulware-ish early to Conceder-ish near the deadline. `[PR]`

**Steady beats both extremes — and this disconfirmed the authors' own hypothesis.** In Faratin et al.'s simulations "the most successful tactics are **Linear, Patient and Steady** … characterised by the fact that they **concede at a steady rate throughout**." Boulware's problem is volume, not quality: it "make[s] significantly fewer deals than all the other tactic families," though its deals are individually good. Conceder and Impatient are the worst. `[PR]`

**Imitative tactics cap your upside.** In the same work, behaviour-dependent tactics "never do better than other tactics; the best they do is gain equal utility to the best tactic" — and they change the ecology: Boulware's utility rose **10%** when reciprocators were removed from the population, because mirroring clones hardheadedness straight back. `[PR]`

**Pure reciprocity is measurably too nice.** The Nice Tit for Tat Agent (ANAC 2011 finalist) reciprocates in terms of *its own* utility and targets the estimated Nash point rather than the naive midpoint, because the naive version "would lead to an agent strategy that is far too nice." Post-tournament verdict: it was the only agent to match its opponent's behaviour, but "this approach might not be as successful in negotiation as in some other games, because **it does not exploit the conceding strategies enough** to reach the top rankings." `[conference paper]`

**The optimal concession schedule is a function of attempts *remaining*, not attempts *made*.** Baarslag et al. derive, via sequential decision theory, `B_{j+1} = (1 + U_j)/2` for the optimal utility target with *j* rounds left. Behaviour: with **j = 1 remaining, the optimal bidder targets exactly halfway** between its reservation value and the maximum attainable; with many rounds left it acts like an **extreme Boulware**. It "significantly outperforms all agents in all cases (one-tailed t-test, p < 0.01)," including CUHKAgent (ANAC 2012 winner) — whose diagnosed weakness is being "very behavior-dependent and [not taking] into account the remaining time as much as they need to." `[conference paper]` **This independently confirms the §5.4 schedule below: small step on revision 1, midpoint on the last one — the exact opposite of a fixed per-round decay.**

**The BOA decomposition and where performance actually comes from.** A negotiating agent splits into **B**idding strategy / **O**pponent model / **A**cceptance condition. Baarslag's thesis built **11 × 6 × 24 = 1,584 agents**, played them against 7 opponents across 5 scenarios × 5 repetitions = **277,200 sessions**, and decomposed the variance (η²):

| Component | η² |
|---|---|
| **Bidding strategy** | **0.582** |
| Acceptance conditions | 0.118 |
| BS × AC interaction | 0.114 |
| BS × OM interaction | 0.085 |
| **Opponent model** | **0.035** |
| OM × AC | 0.014 |

`[PR — PhD thesis]` The bidding strategy explains 58% of performance; the opponent model 3.5%. This is the single most build-relevant number in the memo.

**Acceptance conditions are worth 3× the opponent model, and the best one is empirical.** The formal family: `AC_next(α,β)` (accept if their offer beats what I was about to send), `AC_prev`, `AC_const(α)` (fixed threshold), `AC_time(T)`, `AC_gap(β)`. The proposed winner **AC_combi** benchmarks against a *local empirical* threshold — the max utility the opponent offered during the **preceding window of equal size to the time remaining** (MAX_W) — rather than a hard-coded constant. Results (ANAC 2011 setup, 168 runs/condition): `[conference paper]`

| Condition | Agreement % | Utility of agreements | **Total avg** |
|---|---|---|---|
| **AC_combi(MAX_W)** | 99% | 0.679 | **0.675** |
| AC_gap(0.1) | 83% | 0.761 | 0.630 |
| Agents' own built-in | 82% | 0.768 | 0.627 |
| AC_next(1.02, 0) | 77% | 0.788 | 0.610 |
| AC_next(1, 0) | 72% | 0.787 | 0.567 |
| AC_const(0.8) | 38% | 0.851 | 0.324 |
| AC_const(0.9) | 26% | 0.935 | 0.239 |

AC_combi beats the agents' own acceptance logic by 7% and AC_next by 18%; the expanded thesis replication puts AC_combi(0.98, MAX_W) at **0.762 total utility with a 100% agreement rate**, "at least 12% better than AC_next (p < 0.01)." The mechanism generalises: `AC_const` fails because "the choice of the constant α is highly domain-dependent"; `AC_next` fails because it relies wholly on someone conceding before the deadline. **The last two rows are the acceptance dilemma in miniature — AC_const(0.9) agrees only 26% of the time but averages 0.935 when it does.** `[PR — thesis]`

**Opponent modelling: what a rejection actually reveals** (Baarslag, Hendrikx, Hindriks & Jonker, *AAMAS journal* 2016 survey) `[PR]`.
- **Candidate elimination is the cleanest formalisation of "a decline is data."** An offer the opponent *sends* is a positive training instance; **an offer they reject is a negative example**, and hypotheses are specialised to no longer cover it. The survey's worked case is precisely a re-offer: you receive (x₁,x₂,x₃), counter with (x₁,x₂,x′₃) — changing only the third issue — and it is rejected. "**This reveals a lot of information**": issue 3 matters, and x′₃ is out.
- **Frequency analysis (the HardHeaded model) is the workhorse:** values offered relatively more often are preferred; **an issue whose value churns often is probably unimportant** to them. Preferred in large outcome spaces for scalability, and jointly with Bayesian learning the most popular ANAC technique.
- **Frequency models empirically beat Bayesian ones, and a bad model is worse than none.** Utility gained over using no model, by the host agent's concession speed: HardHeaded frequency +0.0156/+0.0137/+0.0118/+0.0128 (e = 0.1/0.2/1/2); IAMhaggler Bayesian +0.0084/+0.0055/+0.0033/+0.0039; **Bayesian Scalable −0.0050/−0.0058/−0.0032/−0.0053** (negative). Modelling pays most when the outcome space is large and you concede slowly. `[PR — thesis]`
- **The offer-implies-acceptable heuristic:** several systems pool offers with acceptances on the assumption that "if an agent makes an offer, it is also willing to accept it."
- **Time-weighting matters:** "a bid which is unacceptable for an opponent at the beginning of the negotiation might be acceptable at the end," so recent bids — and recent *sessions* — get higher weight.
- **Gaussian-process regression of the concession curve:** fit (time, observed utility) pairs to predict where the opponent will be, sampling **only the maximum utility offered per window** to suppress noise. Implemented as IAMhaggler2011, 3rd in ANAC 2011, strong on large domains and merely average on small ones.

**Cross-session learning: ratchet the floor, randomise the path.** ANAC 2017's Repeated Multilateral league (18 teams, matchups repeated 5× against the same opponents, 1,680 negotiations per finalist) `[conference paper]`:
- **The winner used no history at all.** PonPokoAgent (0.75 avg utility) carries five hard-coded time-dependent patterns and **picks one at random per session**, explicitly "because it is hard for the opponents to predict our agent strategy through the previous sessions."
- The agents that *did* use history ratcheted a floor: **CaduceusDC16** (2nd) — "if the current threshold is 0.6 and the agent had an agreement with a utility of 0.8 in its previous negotiation, then it updates the threshold to 0.8"; **Rubick** (3rd) sets its lower bound to "the highest utility ever received" from those opponents, and keeps a sorted list of bids **accepted by only one** counterparty for deployment near the deadline.
- The organisers name the tension explicitly: "negotiating like a Hardliner (i.e. being selfish) may cause your opponent **not to concede next time**."

**LLM and RL negotiators (2017–2026)** — three results that bear directly on FTF `[preprints unless noted]`:
- **Anchoring is measurable and large.** NegotiationArena: **Spearman ρ = 0.716 between the initial proposed price and the final accepted price.** In a bilateral-trade study, o3 opens at **3.04× its own cost** (vs 1.97–2.14× for every other model) and captures the most surplus in *both* roles while also posting the highest deal rates — high surplus and high close rate are not inherently a tradeoff for the strongest model.
- **The reward-design trap.** SFT roughly doubled surplus share but **cratered deal rates (97.3% → 49.3%)**; subsequent RL restored the deal rate (→99.0%) but **eroded surplus back to near the untrained baseline** — attributed directly to "a reward-structure flaw that gives zero reward to a rational walk-away." Conversely, an RLVR-trained agent that got *better* moved from 82.8% deal rate / 70.0% surplus in-distribution to **70.7% deal rate / 77.0% surplus** out-of-distribution: it learned to walk away.
- **Aggressive agents win deals they get and lose the ones they don't.** Lewis et al.'s end-to-end RL negotiator out-scored human partners (8.0 vs 7.1 on agreed deals) but its **agreement rate collapsed to 57.2%** (vs 76.5% for the imitation-learned model) and it bargained longer (7.2 vs 5.3 turns). Documented emergent behaviours: **deceptive anchoring** ("feigning interest in a valueless item, only to later 'compromise' by conceding it") and counterparties who "preferred a $0 no-deal outcome to capitulating." `[PR]`

**The transfer caveat that governs all of §1.14.** This literature models a *bilateral adversarial* setting. FTF's loop has two different counterparties: the **user**, whose decline is cooperative preference-revelation (exploitation risk runs *toward* the user, not from them), and the **trade partner**, who is genuinely adversarial and not in the conversation. The concession-pacing and reward-design results apply to the partner-facing fairness target; the opponent-modelling results apply to the user-facing decline loop. Treating a user's decline as a hardball signal to be out-waited is where the analogy breaks. `[INFERENCE]`

---

## 2. Antipatterns

1. **Treating a decline as "no trade exists."** 37% of median-product eBay negotiations end in impasse *despite* positive gains from trade `[PR]`; >50% of failed used-auto negotiations had gains from trade `[PR]`. And no marketplace on earth ends a thread on a decline `[OFFICIAL]`.
2. **Making the user compose the counter from a blank editor.** 58% of eBay buyers walk away rather than respond to a counter `[PR]`. Quitting is the human default; "here's the trade builder, good luck" rebuilds the dead end.
3. **Asking "what would you accept?" after a decline.** That solicits a *counter-proposal*, which re-anchors positions. The SNT answer is to ask **what's wrong with the draft** and have the neutral revise it. `[PRACTITIONER]`
4. **Delivering the revision in a next-day push.** Door-in-the-face reciprocity survived immediacy and **died at a three-minute delay** `[PR]`. A revision on the fatigue clock forfeits the mechanism that makes it work.
5. **Re-offering something equal to or worse than the declined package.** Reciprocal gradualism is the most robust pattern in the data (β positive every round) `[PR]`; a non-concession is read as stubbornness and reciprocated with stubbornness. Poshmark encodes this as a hard rule `[OFFICIAL]`.
6. **Panic generosity.** The optimal RL agent's most profitable tactic is *declining generous offers* precisely because humans then capitulate `[PR]`. A neutral that lets one decline trigger a huge concession is exploiting its own user.
7. **Exposing who conceded.** In a persistent league the social cost of appearing eager is permanent. Mediators solve this with the double-blind proposal and the **"two no's"** convention `[PRACTITIONER]`; "they rejected your compromise" is the wrong string to ever render.
8. **Unbounded mediated iteration.** Sequential mediator's proposals work but invite **strategic delay** — parties stall to see how far the mediator will travel `[PRACTITIONER]`; and reactance grows with repetition `[PR]`. Bound it and announce the bound.
9. **A long "why did you decline?" survey.** Friction on the decline path is paid by someone already leaving. Every shipped taxonomy is short (Netflix has none at all). `[OFFICIAL]/[INFERENCE]`
10. **Showing a consequence before the reason picker when declines don't actually cost anything.** DoorDash can do this because acceptance rate is a real, published metric `[TEARDOWN]`. Manufacturing a fake cost to extract a reason is manipulative and reads as such. `[INFERENCE]`
11. **Trusting decline reasons as valuation training data.** People confabulate plausible reasons `[PR]`. Use the reason to route the next draft; use *which revision they accept* to update values.
12. **Auto-suppressing near-boundary matches.** eBay's auto-decline is a seller's labour-saving device `[OFFICIAL]`. If FTF silently suppresses marginal proposals, it destroys exactly the observations the acceptance model needs most. `[INFERENCE]`
13. **Building a six-round negotiation UI.** Mean 1.66 offers; 1.48 when successful; the eBay cap binds in 1.1% of threads `[PR]`. Depth is not the constraint.
14. **Dropping the originally-requested player from the revision.** Contrary to practitioner consensus and to the reciprocity mechanism — it reads as a new offer, not a concession `[PRACTITIONER]`.
15. **Silent expiry.** Every marketplace makes the clock explicit `[OFFICIAL]`. A proposal that just goes stale teaches the user nothing and produces an ambiguous label (decline, or absence?).
16. **Waiting to be muted.** LinkedIn auto-disables Open to Work on non-response `[OFFICIAL]`; decay exposure automatically rather than letting a user reach the opt-out.
17. **Changing several assets at once between revisions.** A multi-dimension revision makes the resulting decline uninterpretable. Candidate elimination only works when the revision is a **one-issue perturbation** — that is what makes the rejection "reveal a lot of information." `[PR]`
18. **Optimising the loop for acceptance rate.** RL agents whose reward gives "zero reward to a rational walk-away" converge on deals that close and don't pay `[preprint]`. "No good trade exists right now" must be a scored, legitimate outcome.
19. **Building an elaborate decliner-preference model before a good revision policy.** Bidding strategy = 58% of variance, opponent model = 3.5%, and poorly-fit models score *negative* `[PR]`. Sophistication in the wrong component is worse than none.
20. **A fixed per-round concession decay (e.g. "sweeten 10% each time").** The optimal schedule is a function of attempts *remaining* — near-Boulware early, midpoint on the last `[conference paper]`. A fixed decay concedes too much too early and has nothing left to close with.
21. **A hard-coded fairness constant as the accept/stop threshold.** `AC_const` is the worst-performing family in the literature because "the choice of the constant α is highly domain-dependent" `[conference paper]`. Benchmark against what this user has recently engaged with instead.
22. **Deceptive anchoring — padding the package with a throwaway asset to "concede" later.** It emerges spontaneously from RL negotiators `[PR]`, it works, and for a neutral holding the pen it is exactly the trust-destroying move that ends the product in a 12-person league. Name it now so nobody builds it by accident. `[INFERENCE]`

---

## 3. What matters most (ranked)

1. **Existence of the loop at all.** Converting "declined → dead" into "declined → one revised proposal." The base rates say the trade often exists (37% inefficient impasse) and that humans abandon by default (58% walk-away), and no competitor marketplace treats decline as terminal. `[PR]/[OFFICIAL]`
2. **Landing the revision on the reciprocity clock — same session, minutes not days.** The three-minute DITF result is the sharpest empirical constraint in this memo `[PR]`, and it is a *scheduling* decision, which makes it cheap.
3. **The revision must be a visible, partial, monotone concession**, framed as a step toward the decliner — **small on revision 1, midpoint on the last**. Three independent literatures converge here: reciprocal gradualism (β = 0.12–0.23) + 98.8% first-counter concession `[PR]`; GRIT's "small, legible, invites reciprocation" `[PRACTITIONER]`; and the optimal-stopping result `B_{j+1} = (1 + U_j)/2`, which is near-Boulware with many attempts left and exactly the midpoint on the last `[conference paper]`.
4. **Change exactly one asset per revision.** It is what converts a decline from an unlabelled negative into an identified blocker (candidate elimination), and it costs nothing to enforce `[PR]`.
5. **Ask for criticism, not a counter-proposal — and keep the pen.** SNT. This is what makes FTF a mediator rather than a courier, and it is a copy change plus a routing table, not a new subsystem. `[PRACTITIONER]`
6. **Capture the counter in-app.** The counter is the highest-information event in the protocol and today it happens in Sleeper where FTF never sees it. Everything in §5.5 depends on this. `[INFERENCE]` on `[PR]`
7. **A one-line justification attached to every proposal and revision.** +7.4–7.7 pp, ~14% less breakdown, strongest at low stakes — and *no marketplace does this*, so it is an unexploited edge. `[PR]/[OFFICIAL]`
8. **A credible immediate-execution pledge.** +26.8 pp on Mercari acceptance ≈ a 19.6% deeper discount `[WP]`. FTF can make it verifiable with a Sleeper deep-link.
9. **A short decline-reason taxonomy that routes the revision policy.** 5 options + "something else." Value is routing, not truth. `[OFFICIAL]/[PR]`
10. **Double-blind revision outcomes.** "No deal" rather than "they said no to your compromise." Cheap to build, and the social cost it prevents is permanent in a 10–12 person league. `[PRACTITIONER]`
11. **Bounded loop + Poshmark-style per-recipient ratchet + auto-decay on silence.** ~2 revisions, then yes/no or hand over the pen; each fresh approach must be materially better than your best previous one to that manager. `[OFFICIAL]/[PR]`
12. **Explicit expiry with a visible clock.** 24h is the industry's convergent default; seller/platform-initiated offers get up to 96h. `[OFFICIAL]`
13. **Split-the-difference framing as the *closing* move.** Free 5–10 pp `[PR]`.
14. **Staged commitment — in-app soft probe (range) before the binding Sleeper offer (point + short exclusivity).** `[PRACTITIONER]/[INFERENCE]`
15. **An empirical, local accept/stop threshold instead of a hard-coded fairness constant** (AC_combi over AC_const). Worth ~12% in the literature, and acceptance conditions carry 3× the variance weight of the opponent model `[PR]`.
16. **Acceptance-model updates from declines.** Real but slow-burning; depends entirely on #4, #6 and #9 shipping first — and it is the *smallest* component (3.5% of variance), so it should be the last thing built, not the first.
17. **Round-vs-precise number presentation.** A genuine second-order speed/surplus dial `[PR]`.

---

## 4. What doesn't matter, even though it seems like it should

1. **Round limits and deep negotiation trees.** Only **1.1%** of eBay threads reach the 3-per-side cap `[PR]`, and **only eBay publishes a cap at all** — Mercari, Depop, Vinted, Poshmark and OfferUp bound the loop with expiry and offer economics instead `[OFFICIAL]`. Round caps are optional; expiry is not.
2. **Negotiation length as an engagement proxy.** Mean 1.66 offers, and successful threads are *shorter* (1.48) `[PR]`. Length correlates with failure.
3. **Optimising concession magnitude precisely.** A midpoint offer beats a *strictly more generous* non-midpoint offer by 5–10 pp `[PR]`. Where the number lands dominates the marginal economics.
4. **Patience and delay tactics.** The QJE authors' revealed-preference patience measure was insignificant with category fixed effects; what shows up instead is **fixed costs of bargaining** — low-stakes bargaining collapses to one round `[PR]`. Reduce per-round *effort*, not per-round *delay*. Artificial urgency is the wrong lever; a two-tap revision is the right one.
5. **Domain-specific concession curves at v1.** eBay's statistics are startlingly stable across seven very different categories — offers/thread 1.54–1.70, first-offer/list 0.575–0.660 `[PR]`. A bespoke dynasty concession schedule before FTF has telemetry is premature. `[INFERENCE]`
6. **Eloquent messaging.** What works is mundane — justification, concrete information, politeness `[PR]`. A template captures most of the 7.4 pp. (Caveat: the effect matured over ~4 weeks as users *learned*, so make the template editable, not locked.)
7. **The literal truthfulness of decline reasons.** People confabulate `[PR]`; the taxonomy's job is to pick a revision branch, and "not enough value" routes correctly even when the real reason is personal. `[INFERENCE]`
8. **"But you are free" language as an engineered lever.** Low-risk-of-bias studies show **no effect** (g = 0.11, ns) `[PR]`. Ship the explicit out for honesty and opt-out prevention, not because it will move acceptance.
9. **Preventing users from shopping the same asset around.** Practitioner consensus tolerates breadth when transparent `[PRACTITIONER]`; 7.8% of eBay listings had simultaneous bargainers and it *raised* prices `[PR]`. Concurrency is a market feature.
10. **Auto-accept thresholds.** eBay's exist to save *absent* sellers labour `[OFFICIAL]`. FTF's users are in the app when they respond; automating the accept removes deliberation without removing friction. `[INFERENCE]`
11. **Post-settlement settlement as an early feature.** Elegant, and Raiffa's own idea — but published agreement rates in post-settlement renegotiation are low and participants pursue extension rather than reallocation `[PR]`. Park it.
12. **An order-book / clearing-price redesign.** StockX shows the negotiation loop is a *choice* — but only for fungible, liquid, price-discoverable goods `[OFFICIAL]`. Dynasty assets are neither fungible nor liquid; that is why FTF has tiers instead of prices. `[INFERENCE]`
13. **Sophistication in the opponent model.** It explains **3.5%** of performance variance against the bidding strategy's **58%**, and the two Bayesian models tested scored *worse than using no model at all* `[PR]`. A Bayesian preference-inference layer is the most seductive and least valuable thing on this roadmap.
14. **Mirroring the counterparty's concessions (pure tit-for-tat).** Imitative tactics "never do better than other tactics; the best they do is gain equal utility to the best tactic," and ANAC's explicitly reciprocal entrant was judged to "not exploit the conceding strategies enough" to place `[PR]/[conference paper]`. Reciprocity is the right *frame* for the user (§1.10) and a mediocre *policy* for the engine.
15. **Cross-session opponent learning, early.** ANAC 2017's repeated league was won by an agent that used **no history at all** and randomised among five fixed patterns specifically to stay unpredictable `[conference paper]`. What the history-users got value from was a one-line **floor ratchet**, not a model.

---

## 5. Transfer notes for FTF

### 5.1 The reframing

FTF is not a party. It is the **neutral holding the pen** — the single-negotiating-text position. Two consequences:

- After a decline, **FTF revises the draft**; it does not tell the user "go counter them."
- The right question to the decliner is **"what's wrong with this?"**, not "what would you accept?" The first keeps FTF holding the pen; the second hands positions back to the parties and re-anchors them.

FTF's analogue of "price" is the **value split** between the two boards. A concession means moving the split toward the decliner — either by **adding value** or by **re-composing at constant value**. The decline-reason taxonomy exists to say which.

**And FTF has two counterparties, not one.** The **user** who declines is cooperatively revealing preferences; the **trade partner** is genuinely adversarial and not in the conversation. The automated-negotiation results split cleanly along that line: concession pacing and reward design govern the partner-facing fairness target; opponent modelling governs the user-facing decline loop. Treating a *user's* decline as a hardball signal to be out-waited is where the analogy breaks, and the exploitation risk in this product runs toward the user, not from them. `[INFERENCE]`

**Build order follows the variance decomposition, not intuition.** Bidding strategy 58% → acceptance condition 11.8% → opponent model 3.5%. So: the revision policy first, the accept/stop threshold second, the decliner model last. `[PR]`

### 5.2 Decline-reason taxonomy (5 options + free text, one tap, skippable)

| Tap | Class | Revision policy |
|---|---|---|
| "I'm not moving **&lt;player&gt;**" | **Hard constraint** | Remove that asset from all packages for this user; regenerate around it. Not a concession problem. |
| "Not enough coming back" | **Value** | Concede on value: widen the split toward them by a bounded step. |
| "Doesn't fit my roster" | **Fit** | Re-compose at ~constant value: swap position/timeline, keep the requested asset. |
| "Not right now" | **Timing** | No revision. Cooldown; re-arm on a trigger event. |
| "Not with this manager" | **Partner** | Suppress the pair. |
| *(skip)* | **Unknown** | Treat as Value with a smaller step and a 1-revision chain. |

Register the decline **first**, then show the picker. Never gate the decline behind it. Do **not** show a consequence screen — FTF declines carry no real cost, and manufacturing one is manipulative (§2.10).

Borrow **Spotify's scoping insight**: the same negative gesture should be available at three scopes — this package / this asset / this manager. That is what the taxonomy above encodes.

### 5.3 The state machine

```
                    ┌───────────┐
                    │ GENERATED │  FTF drafts P0 (it anchors)
                    └─────┬─────┘
                          │ initiator sends soft probe (in-app, non-binding, value RANGE)
                          ▼
                    ┌───────────┐
        ┌───────────│  PROBED   │  P_n live · 48h TTL · visible countdown
        │           └──┬──┬──┬──┘
        │              │  │  └──────────────► EXPIRED ──┐  (label ≠ DECLINED)
        │   interested │  │ declined(reason)            │
        │              │  ▼                             │
        │              │ ┌──────────┐                   │
        │              │ │ DECLINED │─► capture reason  │
        │              │ └────┬─────┘   (≤1 tap)        │
        │              │      │                         │
        │              │  revisable AND rev_count < 2 ? │
        │              │      │yes           │no        │
        │              │      ▼              ▼          ▼
        │              │ ┌──────────┐  ┌──────────────────────┐
        │              │ │ REVISING │  │  COOLED  /  CLOSED   │
        │              │ └────┬─────┘  └──────────┬───────────┘
        │              │  FTF drafts P_{n+1}      │ re-arm on TRIGGER
        │              │  SAME SESSION (minutes)  │ (not a bare timer)
        │              │      │                   │
        │              │      └────► PROBED ◄─────┘  rev_count++ / new chain
        │              ▼
        │      ┌────────────────┐
        └─────►│ AGREED_IN_     │  double-blind: publish only "deal / no deal"
               │ PRINCIPLE      │
               └───────┬────────┘
                       │ deep-link → Sleeper (binding instrument, single POINT package)
                       ▼
               ┌────────────────┐
               │  HANDED_OFF    │──► EXECUTED   (Sleeper trade lands)
               └────────────────┘──► LAPSED     (no Sleeper trade in 72h)
```

**Why two tiers.** `PROBED` is the non-binding **IOI** — carrying a *range* ("would you move Player X for something in this band?"). The Sleeper offer is the **LOI/definitive** — a single point package. This is the M&A ladder, and it is what makes a decline cheap enough to be honest and revisable. Dating apps have the probe without the exclusivity, and their probe→commitment conversion is dismal (~70% of matches stall) — so add the exclusivity: while a proposal is `AGREED_IN_PRINCIPLE`, FTF does not shop those assets to other managers for 24h. `[PRACTITIONER]/[INFERENCE]`

**Consider also a state-based probe**, LinkedIn-Open-to-Work style: a standing "open to moving this player" flag per roster slot. It is lower friction than a per-trade probe and generates continuous preference data with no decline event at all. `[OFFICIAL]/[INFERENCE]`

### 5.4 Transition rules

**Concession function (REVISING).** Let `gap` = the value-split delta between P_n and the decliner's implied position (from their in-app counter if given, else from the reason class and their board).

- **Schedule as a function of attempts *remaining*, not attempts made.** With 2 revisions in the chain: **revision 1 concedes γ ≈ 0.3–0.4 of the gap** (near-Boulware); **revision 2 goes to the midpoint, γ = 0.5**. This is the optimal-stopping result `B_{j+1} = (1 + U_j)/2` — extreme-Boulware with rounds left, exactly halfway on the last one `[conference paper]` — and it independently reproduces both the empirical fact that real first counters sit *below* the midpoint `[PR]` and GRIT's prescription of a *small* first initiative `[PRACTITIONER]`. **Do not implement a fixed per-round decay.**
- **Revision 2 is the closing move:** propose exactly the midpoint and **label it as the midpoint**. This cashes the 5–10 pp split bonus `[PR]` and doubles as the mediator's-proposal closing device `[PRACTITIONER]`.
- **One-issue perturbation invariant (new, and load-bearing).** Each revision changes **exactly one asset** relative to its predecessor. This is what makes the resulting decline interpretable under candidate elimination — "the rejection of its last offer counts as a negative example," and a single-issue delta identifies *which* asset was the blocker `[PR]`. A multi-asset revision that gets declined teaches you nothing.
- **Timing invariant:** revision 1 lands **in the same session as the decline** — minutes, not a next-day push. The three-minute DITF cliff is the binding constraint `[PR]`.
- **Monotonicity invariant:** the decliner's share is non-decreasing across P0 → P1 → P2. Assert it in the generator; never re-anchor.
- **Preservation invariant:** any asset the decliner named as wanted stays in every revision `[PRACTITIONER]`.
- **Ceiling:** cap total concession across the chain so the initiator's board still shows net gain above `user_gain_epsilon` — the anti-panic-generosity guard `[PR]`.
- **No padding.** Never insert a low-value asset into P0 in order to "concede" it later. RL negotiators discover this tactic spontaneously and it works `[PR]`; for a neutral it is disqualifying.
- **Legibility requirement:** every revision states what moved and in whose favour ("You said the value was light — added a 2027 2nd. That's a step toward you."). GRIT's "communicate the expectation of reciprocity" `[PRACTITIONER]`.

**Accept/stop threshold — empirical, not constant.** Do not gate the loop on a fixed fairness number; `AC_const` is the worst-performing family in the literature precisely because the right constant is domain-dependent `[conference paper]`. Instead use an **AC_combi analogue**: benchmark the current proposal against the **best package this user has actually engaged with in a recent window** (their `MAX_W`), and as the chain's remaining attempts run out, require the final proposal to beat that. AC_combi(0.98, MAX_W) hit 0.762 total utility at a 100% agreement rate vs. 0.737/89% for the standard condition, ≥12% better (p < 0.01) `[PR — thesis]`.

**Caps, clocks and cooldowns.**

| Rule | Value | Basis |
|---|---|---|
| Revisions per chain | **2**, then yes/no or hand the pen to the managers | eBay cap binds in 1.1% `[PR]`; sales cadence 3–5 total touches `[VENDOR]`; strategic-delay risk `[PRACTITIONER]` |
| Probe TTL | **48h**, visible countdown | 24h is the industry default for *buyer* offers; eBay gives *platform-initiated* offers 96h (US/UK). FTF's proposal is platform-initiated, so 48h splits the difference `[OFFICIAL]` |
| Revision latency | **same session** | DITF three-minute cliff `[PR]` |
| Cooldown after chain exhaustion | **72h** minimum before any fresh chain to that pair | Mercari's 72h Offer-to-Likers clock `[OFFICIAL]` |
| **Per-recipient ratchet** | a fresh chain to the same manager must be **materially better on their board than your best previous offer to them in 90 days** | Poshmark's 10%/90-day rule — the strongest published anti-pester mechanism `[OFFICIAL]` |
| Cooldown after "Not right now" | until a **trigger event** | trigger-gated ≫ timer-gated `[INFERENCE]` |
| Hard-constraint block ("not moving X") | **30 days** or until X's roster status changes | `[INFERENCE]` |
| Partner suppression | indefinite, user-reversible | `[INFERENCE]` |
| Global rate limit | **≤2 FTF-initiated chains per pair per week**; **1 live chain per pair**; **≤25 outbound proposals per user per day** | repeated-game reputational cost `[PRACTITIONER]`; Vinted's 25/day is the only published global cap `[OFFICIAL]` |
| Auto-decay | after **2 consecutive non-responses**, mute proposals to that manager and tell the initiator why | LinkedIn auto-disables Open to Work on non-response `[OFFICIAL]` |

**Trigger events that re-arm a cooled pair** (prefer over a bare timer): injury or IR move on either roster, a starter's breakout/bust week, a bye-week hole, a waiver/FA add that changes positional depth, a roster change from any executed trade, and the approaching trade deadline. `[INFERENCE]`

**Double-blind outcomes.** When a revision is accepted by one side and declined by the other, publish **"no deal"** to both. Never render "they rejected your compromise." Mediator's-proposal "two no's" convention `[PRACTITIONER]`.

**Message template** attached to every probe and revision — pre-filled and **editable**, because the eBay effect matured as users learned `[PR]`:

> *"[Justification: their roster need + what this fixes.] [If a revision: 'You said X — this moves Y your way.'] [If closing: 'This lands halfway between the two offers.'] Accept and I'll send it in Sleeper right now. [Explicit out: 'Not interested? Tap pass and I'll stop suggesting this pair.']"*

Four evidenced components: justification `[PR]`, legible concession `[PR]/[PRACTITIONER]`, immediate-execution pledge `[WP]`, explicit out `[PR — weak]`.

### 5.5 What the model learns

Every decline becomes a **directionally labelled** negative instead of an unlabelled one:

- `(package, decliner, reason_class)` → shrink the feasible region on the named dimension.
- `(P_n declined, P_{n+1} accepted)` → **brackets** the decliner's acceptance threshold between two known packages. This is the highest-value observation the loop produces and it does not exist today.
- `counter_offer` captured in-app → a point estimate of their position, not just a bound.
- `EXPIRED` ≠ `DECLINED`. Keep them distinct; expiry is mostly attention. Spotify's implicit/explicit split is the precedent `[OFFICIAL]`.
- **Sampling policy:** prefer proposing **near the estimated acceptance boundary**. A decline far from the boundary teaches almost nothing. This argues against auto-suppression thresholds. `[INFERENCE]`
- **Weighting:** stated reasons weight the *routing*; revealed acceptances weight the *values*. Anchor stated to revealed, per de Corte et al. `[PR]`

**Use frequency analysis, not Bayesian inference, and keep it cheap.** `[PR]`
- Assets a manager includes in packages **relatively more often** are the ones they prefer; an **asset slot whose occupant churns often is unimportant to them**. That is the entire HardHeaded model, it beat every Bayesian model tested, and two Bayesian models scored *worse than no model at all*.
- Pool sends with accepts: **"if an agent makes an offer, it is also willing to accept it."** Every package a manager constructs in Sleeper is a positive label.
- **Time-weight everything.** "A bid which is unacceptable at the beginning of the negotiation might be acceptable at the end" — weight recent proposals, and recent *sessions*, more heavily. In dynasty this is doubly true: rosters and contention windows move weekly.
- **Ratchet a floor, randomise the path.** Persist a per-manager acceptance floor updated from actual outcomes (CaduceusDC16: "if the current threshold is 0.6 and the agent had an agreement with a utility of 0.8, it updates the threshold to 0.8"; Rubick sets the floor to the highest utility ever received from that opponent). But do **not** make the concession path predictable across sessions — ANAC 2017's winner randomised among five fixed patterns precisely so opponents could not learn it, and used no history at all. `[conference paper]`

**Reward design — the trap to avoid.** Do not train or tune the loop on acceptance rate. RL negotiators whose reward "gives zero reward to a rational walk-away" restore deal rates to 99% while eroding surplus to the untrained baseline `[preprint]`. FTF's objective must score **"no good trade exists right now"** as a legitimate, positively-valued outcome, and the primary metric (§5.6) must be surplus-weighted, not count-weighted.

### 5.6 Instrumentation

Spec these against the analytics taxonomy **before** building (per CLAUDE.md feature gates; the NULL-`platform` incident is why).

`proposal_probed` · `proposal_declined` (+`reason_class`, `revision_index`, `latency_from_probe`) · `decline_reason_skipped` · `revision_generated` (+`gamma`, `dimension`, `latency_from_decline`) · `revision_probed` · `proposal_agreed_in_principle` · `handoff_opened` · `trade_executed` · `proposal_expired` · `chain_closed` (+`close_cause`) · `cooldown_rearmed` (+`trigger_type`) · `ratchet_blocked` (+`pair`)

**Primary metric: surplus-weighted executed trades per generated *chain*** — the chain is the unit, and the weighting matters because a count-only metric reproduces the documented RL failure mode of closing cheap deals `[preprint]`. Report the raw chain→execution rate alongside it, never instead of it. **Guardrails:** declines per user per week, partner-suppression rate, auto-decay rate, and **notification opt-out rate** — the last is the pestering canary, and the vendor data says triggered sends churn ~2.4× faster than scheduled ones `[VENDOR]`.

### 5.7 Sequencing

Ordered by the BOA variance decomposition (bidding 58% → acceptance 11.8% → opponent model 3.5%), which happens to agree with the base-rate evidence.

1. **Loop skeleton (the bidding strategy).** Decline-reason capture + one FTF-drafted revision **in-session**, as a **one-asset perturbation** on the remaining-attempts schedule + 48h TTL + the message template + double-blind outcomes. Mostly copy, routing and scheduling.
2. **Revision 2** with midpoint framing and the yes/no flip.
3. **The empirical accept/stop threshold** (AC_combi analogue over a recent-engagement window), replacing any fixed fairness constant.
4. **Cooldowns, the per-recipient ratchet, trigger re-arm, auto-decay.**
5. **Frequency-based decliner model and the per-manager floor ratchet** — last, cheapest form first, and only once 1–4 have produced volume. Resist the Bayesian version.

Per CLAUDE.md this is **not** a "quick fix": it touches schema, API surface, feature-flag surfaces and analytics events, so it takes the full four gates (scope block → Maestro delta → docs → sim run) unless the operator explicitly declares otherwise on the record — and on a change of this class that declaration needs a confirming yes.

---

## 6. Not researched / follow-up topics

Ranked by how much they'd change the design above.

1. **Whether split-the-difference transfers to multi-asset packages.** The eBay result is one-dimensional. "The midpoint" of a 3-for-2 package is not uniquely defined — board value? player count? a specific named asset? Which framing triggers the salience effect is unknown, and is the best early A/B in this memo. Note the tension with the one-asset-perturbation rule: a midpoint that requires changing two assets breaks candidate elimination, so §5.4 may need to choose between them on the closing move.
2. **Facebook Marketplace, Grailed, Etsy, Alibaba/Amazon RFQ mechanics.** Not reached before the search budget ran out (Grailed and Etsy return 403 to automated fetches). Facebook Marketplace's "Is this available?" pattern is well known anecdotally with **no official citation** — do not assert specifics.
3. **Faratin et al.'s formulas were OCR'd from a scanned PDF** and subscripts are imperfect; the notation in §1.14 is normalised. Re-derive from a clean copy before implementing the α/β schedule literally. Similarly, the BOA-decomposition source (*Decoupling Negotiating Agents…*) was read via the thesis chapter and secondary descriptions, not the conference PDF directly.
4. **Green & Plunkett's full EC'22 text is paywalled** (confirmed non-OA via Unpaywall), so the agent's quantitative concession schedule and surplus tables are still unread; only the abstract and the author's SIGecom retrospective were obtained.
4. **Concession direction under asymmetric boards.** FTF has two valuation boards; a concession on the initiator's board may not read as one on the decliner's. §5.4 assumes monotonicity on the **decliner's** board — an assumption, not a finding.
5. **Cooldown and cap values.** 48h TTL, 72h cooldown, 2 revisions and ≤2 chains/pair/week are calibrated from adjacent industries, not from fantasy. All four are A/B candidates. The vendor cadence data is unreliable enough that FTF's own numbers should replace it quickly.
6. **Fantasy-specific base rates.** Nothing published on trade-offer acceptance, counter, or re-offer conversion rates in Sleeper/ESPN/MFL leagues. FTF's own telemetry is the only realistic source — another argument for shipping §5.6 early.
7. **Cross-session identity.** The floor-ratchet and time-weighting designs in §5.5 assume FTF can reliably tie a decline to the same manager across sessions and leagues. Whether that is true in FTF's account model was not checked.
8. **GRIT's primary sources.** The Beyond Intractability GRIT essay 404'd and Osgood was not read directly; "announce in advance," "keep concessions verifiable" and "retain retaliatory capacity" rest on secondary summaries only. Lindskold (1978) was likewise read via a search-index summary.
9. **DITF meta-analytic effect size.** Feeley, Anker & Aloe (2012, *Human Communication Research*) covers the first 35 years but the full text was not obtained, so the pooled *r* is not in hand — only the individual-study rates.
10. **The "delayed disagreement" population.** The QJE paper flags it as the pattern nearly no theory generates, and it is precisely FTF's target segment (people who engaged, exchanged offers, and still ended with nothing). No model of it was reviewed.
11. **Multi-party re-offer.** If revision 2 fails with partner A, is the right move a *first* offer to partner B carrying the learned constraint? That is round-2/01's thin-market machinery meeting this memo's loop; neither round has covered the join.
12. **Veto / league-governance interaction.** A revised package a league would veto is worse than no package. Carried over unresolved from round-2/02 §7.
13. **Post-settlement settlement in fantasy.** Raiffa's idea is attractive for dynasty (rosters keep changing), but the published lab evidence is discouraging. Worth a cheap test, not a build.

---

## 7. Sources

### eBay Best Offer empirical corpus

1. Backus, Blake, Larsen & Tadelis, *Sequential Bargaining in the Field: Evidence from Millions of Online Bargaining Interactions*, **Quarterly Journal of Economics** 135(3): 1319–1361, 2020 — https://academic.oup.com/qje/article-abstract/135/3/1319/5721265 `[PR]` *(full text read via https://faculty.haas.berkeley.edu/stadelis/qjaa003.pdf)*
2. Same, NBER WP 24306 — https://www.nber.org/papers/w24306 · PDF https://www.nber.org/system/files/working_papers/w24306/w24306.pdf `[WP]`
3. Same, eScholarship — https://escholarship.org/uc/item/3t78f7pt `[WP]`
4. **Public replication data** — NBER, *Best Offer Sequential Bargaining* — https://www.nber.org/research/data/best-offer-sequential-bargaining `[OFFICIAL]` — the anonymised offer-level dataset is publicly released and directly usable for calibrating a concession function before FTF has telemetry
5. Backus, Blake & Tadelis, *Cheap Talk, Round Numbers, and the Economics of Negotiation*, WP 2015 — https://www.microsoft.com/en-us/research/wp-content/uploads/2016/09/backusblaketadelis_2015_wp_roundsignal-Copy.pdf `[WP]` *(read in full)* · SSRN https://www.ssrn.com/abstract=2621339
6. Backus, Blake & Tadelis, *On the Empirical Content of Cheap-Talk Signaling: An Application to Bargaining*, **JPE** 127(4), 2019 — https://www.journals.uchicago.edu/doi/abs/10.1086/701699 `[PR]`
7. Backus, Blake, Pettus & Tadelis, *Communication, Learning, and Bargaining Breakdown*, **Management Science**, 2023 — https://pubsonline.informs.org/doi/10.1287/mnsc.2023.00366 `[PR]` *(full text read via http://faculty.haas.berkeley.edu/stadelis/bo_germany.pdf)* · NBER WP 27984 https://www.nber.org/papers/w27984 · appendix https://mbackus.github.io/docs/backusblakepettustadelis_2023_wp_breakdown_appendix.pdf
8. PBS NewsHour, *What economists learned from your eBay haggling* — https://www.pbs.org/newshour/economy/economists-learn-ebay-haggling `[TEARDOWN]`

### Bargaining efficiency / impasse

9. Freyberger & Larsen, *How Well Does Bargaining Work in Consumer Markets? A Robust Bounds Approach*, **Econometrica** 93(1): 161–194, 2025 — https://onlinelibrary.wiley.com/doi/abs/10.3982/ECTA20125 `[PR]` · https://www.econometricsociety.org/publications/econometrica/2025/01/01/How-Well-Does-Bargaining-Work-in-Consumer-Markets-A-Robust-Bounds-Approach · NBER WP 29202 https://www.nber.org/papers/w29202
10. Larsen, *The Efficiency of Real-World Bargaining: Evidence from Wholesale Used-Auto Auctions*, **Review of Economic Studies** 88(2): 851–882, 2021 — https://academic.oup.com/restud/article-abstract/88/2/851/5734664 `[PR]` · NBER WP 20431 https://www.nber.org/papers/w20431 · data https://www.nber.org/research/data/dealer-dealer-used-car-bargaining-and-auction-data-larsen-2020

### Automated / RL bargaining

11. Green & Plunkett, *The Science of the Deal: Optimal Bargaining on eBay Using Deep Reinforcement Learning*, **ACM EC'22** (Best Paper) — https://dl.acm.org/doi/10.1145/3490486.3538373 `[PR]` · award https://ec22.sigecom.org/program/awards/ · talk https://www.youtube.com/watch?v=OXj5X7kRFwQ
12. Green, *Deep Reinforcement Learning for Economics: Progress and Challenges*, **ACM SIGecom Exchanges** 21(1): 49–53, 2023 — https://www.sigecom.org/exchanges/volume_21/1/GREEN.pdf `[PR]` *(read in full — source of the "reject generous first offers" tactic)*
13. *Strategic Bargaining in Multi-Buyer Markets: RL from Verifiable Rewards for LLM Negotiations* — https://arxiv.org/abs/2607.05863 `[WP]` *(82.8%/70.0% trained vs 35.5%/4.8% base; OOD "strategic selectivity")*
14. *Training Language Models for Bilateral Trade with Private Information* — https://arxiv.org/abs/2604.16472 `[WP]` *(o3 opens at 3.04× cost; the SFT/RL surplus-vs-deal-rate trap)*
14b. Bianchi et al., *How Well Can LLMs Negotiate? NegotiationArena* — https://arxiv.org/abs/2402.05863 `[WP]` *(anchoring ρ = 0.716)*
14c. Fu et al., *Improving Language Model Negotiation with Self-Play and In-Context Learning from AI Feedback* — https://arxiv.org/abs/2305.10142 `[WP]`
14d. Lewis et al., *Deal or No Deal? End-to-End Learning for Negotiation Dialogues*, EMNLP 2017 — https://arxiv.org/abs/1706.05125 `[PR]` *(57.2% agreement rate; deceptive anchoring)*
14e. Meta AI, *Cicero* — https://ai.meta.com/research/cicero/ `[secondary summary — the Science paper returned 403]`

### Automated negotiation: ANAC, BOA, opponent modelling

14f. Faratin, Sierra & Jennings, *Negotiation decision functions for autonomous agents*, **Robotics and Autonomous Systems** 24:159–182, 1998 — https://jmvidal.cse.sc.edu/library/faratin98a.pdf `[PR]` *(time/behaviour/resource-dependent tactics; the Linear-Patient-Steady result. Formulas OCR'd from a scan — see §6 item 3)*
14g. Baarslag, *What to Bid and When to Stop* (PhD thesis) — https://homepages.cwi.nl/~baarslag/pub/What_to_Bid_and_When_to_Stop.pdf `[PR]` *(the 277,200-session BOA variance decomposition; opponent-model comparison; concession-rate R² results)*
14h. Baarslag et al., *Acceptance Conditions in Automated Negotiation* — https://homepages.cwi.nl/~baarslag/pub/Acceptance_conditions_in_automated_negotiation.pdf `[conference paper]` · Springer chapter https://link.springer.com/chapter/10.1007/978-3-642-30737-9_6
14i. Baarslag et al., *Optimal Non-adaptive Concession Strategies with Incomplete Information* — https://homepages.cwi.nl/~baarslag/pub/Optimal_Non-adaptive_Concession_Strategies_with_Incomplete_Information.pdf `[conference paper]` *(B_{j+1} = (1 + U_j)/2)*
14j. Baarslag et al., *Decoupling Negotiating Agents to Explore the Space of Negotiation Strategies* — https://homepages.cwi.nl/~baarslag/pub/Decoupling_Negotiating_Agents_to_Explore_the_Space_of_Negotiation_Strategies.pdf `[conference paper — read via thesis chapter]`
14k. Baarslag, Hendrikx, Hindriks & Jonker, *Learning about the opponent in automated bilateral negotiation: a comprehensive survey of opponent modeling techniques*, **AAMAS journal** 30(5):849–898, 2016 — https://homepages.cwi.nl/~baarslag/pub/Learning_about_the_opponent_in_automated_bilateral_negotiation-a_comprehensive_survey_of_opponent_modeling_techniques.pdf `[PR]` · https://link.springer.com/article/10.1007/s10458-015-9309-1 *(candidate elimination; frequency analysis; GP concession curves)*
14l. Baarslag et al., *A Tit for Tat Negotiation Strategy for Real-Time Bilateral Negotiations* — https://homepages.cwi.nl/~baarslag/pub/A_tit_for_tat_negotiation_strategy_for_real-time_bilateral_negotiations.pdf `[conference paper]`
14m. Aydoğan, Fujita, Baarslag, Jonker & Ito, *ANAC 2017: Repeated Multilateral Negotiation League* — https://homepages.cwi.nl/~baarslag/pub/ANAC_2017-Repeated_Multilateral_Negotiation_League.pdf `[conference paper]` *(PonPokoAgent; CaduceusDC16 and Rubick floor ratchets)*
14n. *ANAC 2018: Repeated Multilateral Negotiation League* — https://homepages.cwi.nl/~baarslag/pub/ANAC_2018-Repeated_Multilateral_Negotiation_League.pdf `[conference paper — listed, not read]`
14o. *The 13th International Automated Negotiating Agent Competition: Challenges and Results* (ANAC 2022) — https://homepages.cwi.nl/~baarslag/pub/The_13th_International_Automated_Negotiating_Agent_Competition-Challenges_and_Results.pdf `[conference paper — listed, not read]`
14p. ANAC official site — https://anac.cs.brown.edu/ `[OFFICIAL]` *(carried from round-2/02)*

### C2C marketplace bargaining (academic)

15. Kuno, *Buyer Commitment in Bilateral Bargaining: The Case of Online Japanese C2C Market*, 2026 (Mercari data, Univ. of Tokyo) — https://arxiv.org/pdf/2602.13707 `[WP]` *(read in full)*

### Marketplace mechanics (official help centres)

16. eBay, *Best Offer* (seller) — https://export.ebay.com/en/marketing/promote-listings/best-offer/ `[OFFICIAL]`
17. eBay, *Best Offer* (services & tools) — https://export.ebay.com/en/services-tools/best-offer/ `[OFFICIAL]`
18. eBay, *Counteroffers* — https://www.ebay.com/help/buying/buy-now/counteroffers?id=4020 `[OFFICIAL]`
19. eBay, *Adding Best Offer to a listing* — https://www.ebay.com/help/selling/listings/selling-buy-now/adding-best-offer-listing?id=4144 `[OFFICIAL]`
20. eBay, *Offers to Buyers* — https://export.ebay.com/en/marketing/promote-listings/offer-buyers/ `[OFFICIAL]`
21. eBay Developers, *Best Offers — counter* — https://developer.ebay.com/api-docs/user-guides/static/trading-user-guide/best-offers-counter.html `[OFFICIAL]`
22. Vendoo, *Comprehensive Guide to eBay Offers for Sellers* — https://blog.vendoo.co/comprehensive-guide-to-ebay-offers-for-sellers `[TEARDOWN]`
23. Mercari, *Offers* — https://www.mercari.com/us/help_center/article/330/ `[OFFICIAL]`
24. Mercari, *Offer to Likers / promotions* — https://www.mercari.com/us/help_center/article/347/ `[OFFICIAL]`
25. Value Added Resource, *Mercari Time-Limited Sales & Auto Offers to Likers* — https://www.valueaddedresource.net/mercari-time-limited-sales-auto-offers-to-likers/ `[TEARDOWN]`
26. Poshmark blog, *New Feature Alert: Offer to Likers* — https://blog.poshmark.com/2018/02/24/new-feature-alert-offer-to-likers/ `[OFFICIAL]`
27. Poshmark support, Offer to Likers — https://support.poshmark.com/s/article/831745541 `[OFFICIAL]`
28. Depop Newsroom, *Depop community embraces offers as suite of negotiation tools expands* — https://news.depop.com/company-news/depop-community-embraces-offers-as-suite-of-negotiation-tools-expands/ `[OFFICIAL]` *(source of the 40% / 62M / 2M/week / 23% figures)*
29. Depop help, *Make Offer* — https://depophelp.zendesk.com/hc/en-gb/articles/4412315779345-Make-Offer `[OFFICIAL]`
30. Export Your Store, *Depop binding offer* — https://www.exportyourstore.com/blog/depop-binding-offer `[TEARDOWN]`
31. Vinted, *I want to make an offer or suggest a different price* — https://www.vinted.co.uk/help/4/258-i-want-to-make-an-offer-or-suggest-a-different-price · https://www.vinted.com/help/258-i-want-to-make-an-offer-or-suggest-a-different-price `[OFFICIAL]`
32. OfferUp, *Accept an offer* — https://help.offerup.com/hc/en-us/articles/360032334451-Accept-an-offer `[OFFICIAL snippet, page 403s to automated fetch]`
33. EcommerceBytes, *OfferUp figures out how to reduce the no-shows* — https://www.ecommercebytes.com/2019/07/21/offerup-figures-out-how-to-reduce-the-no-shows/ `[TEARDOWN]`
34. StockX, *Sell Now vs. an Ask* — https://stockx.com/help/articles/what-is-the-difference-between-sell-now-and-an-ask `[OFFICIAL]`
35. StockX, *What is an Ask* — https://stockx.com/help/en-US/articles/What-is-an-Ask-and-how-do-I-sell-on-StockX `[OFFICIAL]`
36. StockX, *How long do bids stay active* — https://stockx.com/help/en-GB/articles/How-long-do-bids-stay-active-on-StockX `[OFFICIAL]`
37. Watcher.guru, *How long do bids last on StockX* — https://watcher.guru/news/how-long-do-bids-last-on-stockx `[TEARDOWN]`

### Mediation, SNT, GRIT, reciprocity

38. Beyond Intractability, *Single-Text Negotiation* — https://www.beyondintractability.org/essay/single-text-negotiation `[PRACTITIONER]`
39. Via Conflict, *Drafting Agreement: The Single Text Approach* — https://viaconflict.wordpress.com/2012/05/13/drafting-agreement-the-single-text-approach/ `[PRACTITIONER]` *(step-by-step operational rules)*
40. LitCharts, *Getting to Yes* — one-text procedure — https://www.litcharts.com/lit/getting-to-yes/terms/one-text-procedure `[book, via study guide]`
41. LitCharts, *Getting to Yes* — Camp David Accords — https://www.litcharts.com/lit/getting-to-yes/terms/camp-david-accords `[book, via study guide]`
42. University of Oregon Scholars' Bank — Camp David / single-text scholarship — https://scholarsbank.uoregon.edu/xmlui/handle/1794/27149 `[TEARDOWN]`
43. UWW-ADR, *The Mediator's Proposal* — https://www.uww-adr.com/blog/mediators-proposal/ `[PRACTITIONER]` *(double-blind, "two no's", use-it-late)*
44. Miles Mediation, *Patience, Process and Persistence: Using Sequential Mediator's Proposals* — https://milesmediation.com/blog/patience-process-and-persistence-using-sequential-mediators-proposals-in-commercial-contractual-negotiations/ `[PRACTITIONER]` *(8–9 sequential proposals; strategic-delay risk)*
45. Raiffa, *Post-Settlement Settlements*, **Negotiation Journal** 1(1), 1985 — https://onlinelibrary.wiley.com/doi/10.1111/j.1571-9979.1985.tb00286.x `[PR — abstract only]`
46. Gettinger, Filzmoser & Koeszegi, *Why can't we settle again?*, **Journal of Business Economics** 86(4): 413–440, 2016 — https://ideas.repec.org/a/spr/jbecon/v86y2016i4d10.1007_s11573-016-0809-5.html `[PR]`
47. SAGE Encyclopedia, *Graduated Reciprocation in Tension Reduction (GRIT)* — https://sk.sagepub.com/ency/edvol/processes/chpt/graduated-reciprocation-tension-reduction-grit `[reference work]`
48. IResearchNet, *GRIT tension-reduction strategy* — https://psychology.iresearchnet.com/social-psychology/antisocial-behavior/grit-tension-reduction-strategy/ `[reference work]`
49. Intractable Conflict (Colorado), *GRIT* — https://www.intractableconflict.org/www_colorado_edu_conflict/peace/treatment/grit.htm `[PRACTITIONER]`
50. Osgood, *An Alternative to War or Surrender* (1962) — https://archive.org/details/osgood-alt-1962 `[book, not read directly]`
51. Arms Control Association, *JFK's American University Speech Echoes Through Time* — https://www.armscontrol.org/act/2013-06/jfks-american-university-speech-echoes-through-time `[TEARDOWN]`
52. JFK Library, *Nuclear Test Ban Treaty* — https://www.jfklibrary.org/learn/about-jfk/jfk-in-history/nuclear-test-ban-treaty `[OFFICIAL archive]`
53. Lindskold (1978), *Trust development, the GRIT proposal, and the effects of conciliatory acts on conflict and cooperation*, **Psychological Bulletin** — https://psycnet.apa.org/record/1979-23571-001 `[PR — record page would not render; medium confidence]`
54. Cialdini, Vincent et al. (1975), *Reciprocal Concessions Procedure for Inducing Compliance: The Door-in-the-Face Technique*, **JPSP** — https://www.semanticscholar.org/paper/Reciprocal-Concessions-Procedure-for-Inducing-The-Cialdini-Vincent/92b260654b792a48084c99fb8f844e18183a5933 `[PR]` · summary incl. the three-minute-delay and in-group moderators: https://en.wikipedia.org/wiki/Door-in-the-face_technique
55. Genschow et al. (2021) DITF replication, via Psychology Today — https://www.psychologytoday.com/us/blog/culture-conscious/202107/does-the-door-in-the-face-technique-really-work `[PR, via secondary]`
56. Feeley, Anker & Aloe, *The Door-in-the-Face Persuasive Message Strategy: A Meta-Analysis of the First 35 Years*, **Human Communication Research**, 2012 — https://www.researchgate.net/publication/263263459_The_Door-in-the-Face_Persuasive_Message_Strategy_A_Meta-Analysis_of_the_First_35_Years `[PR — full text not obtained]`
57. Forbes / Kwame Christian, *Splitting the Difference in Negotiation: A Double-Edged Sword* — https://www.forbes.com/sites/kwamechristian/2023/03/26/splitting-the-difference-in-negotiation-a-double-edged-sword/ `[PRACTITIONER]`
58. Karrass, *Splitting the Difference* — https://www.karrass.com/blog/splitting-the-difference `[PRACTITIONER]`

### Fatigue, cadence, reactance

59. Clean Email, *Email subscription fatigue statistics* — https://clean.email/blog/insights/email-subscription-fatigue-statistics `[VENDOR]`
60. Count.co, *Unsubscribe rate* (Acoustic 2024 benchmarks) — https://count.co/metric/unsubscribe-rate `[VENDOR]`
61. WiserNotify, *Push notification statistics* — https://wisernotify.com/blog/push-notification-stats/ `[VENDOR]`
62. SashiDo, *Push notification opt-outs: real reasons users say no* — https://www.sashido.io/en/blog/push-notification-opt-outs-real-reasons-users-say-no `[VENDOR]`
63. Andrew Chen, *Why people are turning off push* — https://andrewchen.com/why-people-are-turning-off-push/ `[VENDOR]`
64. MailReach, *How many follow-ups should you send* — https://www.mailreach.co/blog/how-many-follow-ups-should-you-send-to-maximize-responses `[VENDOR]`
65. Supered, *Sales cadence* — https://www.supered.io/blog/sales-cadence/ `[VENDOR]`
66. Instantly, *How many times should you follow up* — https://instantly.ai/blog/how-many-times-should-you-really-follow-up-with-a-prospect/ `[VENDOR]`
67. LeadResponse, *Sales follow-up statistics* — https://leadresponse.co/blog/sales-follow-up-statistics `[VENDOR]`
68. *Psychological reactance* meta-analysis, **Human Communication Research** (advance article) — https://academic.oup.com/hcr/advance-article/doi/10.1093/hcr/hqaf016/8178818 `[PR]`
69. Carpenter (2013), BYAF meta-analysis, **Communication Studies** — https://www.tandfonline.com/doi/full/10.1080/10510974.2012.727941 `[PR]`
70. *BYAF pre-registered re-analysis*, **Meta-Psychology**, 2023 — https://open.lnu.se/index.php/metapsychology/article/view/2640 `[PR]`

### Decline-reason capture

71. EntreCourier, *Accepting and declining DoorDash orders* — https://entrecourier.com/delivery/gig-delivery-platforms/doordash/doordash-strategies/accepting-and-declining-doordash-orders/ `[TEARDOWN]`
72. Ridesharing Driver, *DoorDash pause dash / acceptance* — https://www.ridesharingdriver.com/doordash-pause-dash-acceptance/ `[TEARDOWN]`
73. LinkedIn Help, *Responding to InMail* — https://www.linkedin.com/help/linkedin/answer/a552643/ `[OFFICIAL]`
74. LinkedIn Help, *Open to Work* — https://www.linkedin.com/help/linkedin/answer/a507508 `[OFFICIAL]` *(also the auto-disable-on-non-response precedent)*
75. Spotify, *Understanding recommendations* — https://www.spotify.com/us/safetyandprivacy/understanding-recommendations `[OFFICIAL]`
76. Variety, *Netflix two thumbs up ratings* — https://variety.com/2022/digital/news/netflix-two-thumbs-up-ratings-1235228641/ `[TEARDOWN]`
77. Meta Help, ad controls — https://www.facebook.com/help/769828729705201 `[OFFICIAL]`
78. Meta Newsroom, *Why am I seeing this?* — https://about.fb.com/news/2019/03/why-am-i-seeing-this/ `[OFFICIAL]`
79. Airbnb Help, declining requests — https://www.airbnb.com/help/article/3592 `[OFFICIAL]` · common decline reasons https://www.airbnb.com/help/article/315 `[OFFICIAL]`
80. Cloud Army, *Why stated preferences fail: the say/do gap* — https://cloud.army/why-stated-preferences-fail-the-saydo-gap-in-market/ `[PRACTITIONER synthesis]`
81. VoxEU/CEPR, *Reported preference versus revealed preference* — https://cepr.org/voxeu/columns/reported-preference-versus-revealed-preference `[PR/academic]`
82. de Corte et al. (2021), **Health Economics** — https://onlinelibrary.wiley.com/doi/full/10.1002/hec.4246 `[PR]`

### Staged commitment

83. Transacted, *IOI vs LOI* — https://www.transacted.io/ioi-vs-loi `[PRACTITIONER]`
84. Redpath, *IOI vs LOI in an M&A transaction* — https://www.redpathcpas.com/blog/ioi-vs-loi-in-an-ma-transaction `[PRACTITIONER]`
85. Confident Group, *Expression of Interest in real estate* — https://www.confident-group.com/blog/expression-of-interest-eoi-in-real-estate/ `[PRACTITIONER]`
86. WCN LLP, *Is an offer to purchase real estate binding?* — https://wcnllp.com/is-an-offer-to-purchase-real-estate-binding/ `[PRACTITIONER/legal]`
87. GetCupid, *Bumble statistics* — https://getcupid.ai/blog/editorial/bumble-statistics `[VENDOR, low confidence]`
88. SwipeStats, *Hinge vs Bumble vs Tinder* — https://www.swipestats.io/blog/hinge-vs-bumble-vs-tinder `[VENDOR, low confidence]`
89. GetMatches, *Hinge vs Bumble vs Tinder* — https://getmatches.ai/en/blog/hinge-vs-bumble-vs-tinder `[VENDOR, low confidence]`

### Fantasy / Sleeper

90. Sleeper Support, *Welcome to a New Trading Experience* — https://support.sleeper.com/en/articles/4238825-welcome-to-a-new-trading-experience `[OFFICIAL]`
91. Sleeper blog, *How to Make Fantasy Football Trades* — https://sleeper.com/blog/how-to-trade-in-fantasy-football/ `[OFFICIAL]`
92. LordSkunk, *Sleeper Trade Tools* — https://lordskunk.com/guides/sleeper-trade-tools/ `[TEARDOWN]`
93. The Fantasy Footballers, *Dynasty Trade Secrets: 10 Tips* — https://www.thefantasyfootballers.com/dynasty/dynasty-trade-secrets-10-tips-for-successful-negotiations-fantasy-football/ `[PRACTITIONER]` *(tip #9: keep the requested player in your counter)*
94. The Fantasy Footballers, *Negotiation Strategy: Five Tips* — https://www.thefantasyfootballers.com/analysis/negotiation-strategy-five-tips-for-your-fantasy-football-trades/ `[PRACTITIONER]`
95. Going For 2, *Fantasy Football Trade Etiquette* — https://goingfor2.com/the-good-and-bad-fantasy-football-trade-etiquette/ `[PRACTITIONER]`
96. Going For 2, *Trade Better: A Guide to Fantasy Football Trade Strategy* — https://goingfor2.com/trade-better-a-guide-to-fantasy-football-trade-strategy/ `[PRACTITIONER]`
97. Dynasty League Football, *The Five Rules of Dynasty Trading* — https://dynastyleaguefootball.com/2016/08/30/five-rules-dynasty-trading/ `[PRACTITIONER]` *(HTTP 403 to automated fetch; cited from search-result summary only)*
98. CBS Sports, *Dynasty Fantasy Football Mailbag: Trade etiquette…* — https://www.cbssports.com/fantasy/football/news/dynasty-fantasy-football-mailbag-trade-etiquette-escaping-the-middle-and-deebo-samuels-trade-value `[PRACTITIONER]`

### Cited but not verified at the primary source

99. EmergentMind, *Automated Negotiating Agents Competition* — https://www.emergentmind.com/topics/automated-negotiating-agents-competition-anac `[secondary]` *(carried from round-2/02; superseded by sources 14f–14p)*
100. eBay help centre, *Making a Best Offer* — https://www.ebay.com/help/buying/buy-now/making-best-offer?id=4019 `[OFFICIAL — fetch timed out; superseded by sources 16–21]`

### Related prior-round memos

- `docs/research/matchmaking/round-2/02-bundle-construction-and-offer-design.md` — first-offer anchoring (Petrowsky et al. 2025), MESO, log-rolling; §7 flagged this memo's topic
- `docs/research/matchmaking/round-2/01-thin-markets-and-multiparty-matching.md` — the multi-party re-offer question in §6 item 11
- `docs/research/matchmaking/round-2/03-sparse-data-learning-and-evaluation.md` — the acceptance-model machinery §5.5 feeds
