# TikTok's App & Presentment Model — Consolidated Research

*Consolidated from two independent researchers (T1A: adoption/narrative lens; T1B: adversarial/
quantified lens). Raw reports in gitignored `feedback-workspace/tiktok-discovery/T1{A,B}-presentment.md`.
Convergent findings marked ◆ (high confidence); numbers carry their evidence class. Inference and
folklore are labeled. 2026-07-26.*

## The one-paragraph takeaway

◆ TikTok's core UX insight: **presentment IS instrumentation**. A full-screen, one-item-at-a-time,
paginated feed forces an explicit verdict on every item — "the algorithm can't see which story your
eyes rest on" in a scroll feed, but one-item pagination makes every advance a labeled example (Eugene
Wei). Skip is deliberately the cheapest action in the app; everything else (dwell, rewatch, like,
share, profile-tap) is graded positive signal captured without asking — and watch time *alone*
reconstructs a user's interests in ~36 minutes / 224 videos (WSJ bot audit). Cold start skips the
social graph entirely: popularity-seeded feed + optional interest picker, visible personalization
within tens of videos. Retention comes from variable reward + deliberate interleaving (proven /
fresh / ~5–10% deliberate off-interest "disruptive" content). The compulsion machinery (no exit
points, 260-video habit threshold, retention/time-spent objectives) is documented in internal leaks —
and is precisely what a utility app must NOT import.

## Mechanism catalog (convergent)

### 1. The one-item feed ◆
- Pagination forces a verdict; multi-item feeds make attention illegible. The single most load-bearing
  design decision — the UI exists to make preference legible to the model (Wei).
- Zero choice paralysis: the user never picks the next item; per-item decision collapses to stay/leave.
- Skip economics: rejection costs one flick, "like swiping left on Tinder" — users emit far more
  signal per session than any browse feed.
- **Instant start:** next 1–2 items prefetched, first frame pre-rendered, warm player pool; perceived
  transition sub-100–500ms. The "one more" loop dies at the first loading wall.
- No terminal state (infinite feed, no completion) — flagged by Growth.Design as the top humane-design
  gap; a compulsion mechanic, not a requirement of the format.

### 2. The signal economy ◆
- **Watch time dominates.** WSJ: watch time + rewatch alone fully personalize (no likes/follows
  needed). Boeker & Urman (WWW'22) signal ordering: **follow > like > watch-longer**; watching ≥25%
  of a video already shifts recommendations. Official: completing a long video outweighs weak signals.
- Every affordance is a sensor (Wei's rule: no affordance that doesn't teach the model something).
  The right-rail action stack sits in the thumb zone, executable mid-scroll.
- Leaked scoring shape: `score ≈ P_like·V_like + P_comment·V_comment + E_playtime·V_playtime +
  P_play·V_play`, optimizing retention + time spent toward DAU (Algo 101, NYT-authenticated).
  **The V-vector is the editorial/business layer** — ML predicts, the business chooses what to want.
- Explicit negative ("Not interested") is a pressure valve; the cheap skip is the main negative channel.

### 3. Cold start ◆ (with the real numbers)
- Optional, skippable interest picker → straight into a popularity-seeded feed; consumption before
  creation; regional/language priors (officially down-weighted).
- **Speed:** WSJ — full interest lock-on in <2 hrs, sometimes ~40 min (depression bot: 224 videos /
  36 min → then 93% on-topic). Northeastern 2026 — 200 topic videos took on-topic share from
  1.5–8.5% baseline to 38–44.5%. Internal (Kentucky AG leak, NPR): **habit forms at ~260 videos
  (~35 min)**. The famous "8 videos to hook" is **folklore — unsourced** (both researchers).
- The felt "it gets me" moment inside session one IS the activation event.

### 4. Steering & controls ◆ — and the control-theater trap
- Long-press → Not interested / hide creator / hide sound; Smart Keyword Filters (AI-expanded mute
  words); Manage Topics sliders; **FYP Refresh** (2023) — a full reset "as if you just signed up,"
  an official admission that personalization overfits terminally.
- **Efficacy, measured (Northeastern 2026):** "Not interested" cuts a topic 30.5%→4.75% of feed
  (−84%); fast-skipping alone −47.5%. **But suppression relapses within minutes of stopping** —
  implicit-only suppression relapsed in 11/15 runs; explicit feedback overridden in 5/15. And the
  CHI-track steering study (arXiv 2504.13895) found users' tactics largely fail — "algorithmic
  persistence" erodes trust enough that some quit.
- ◆ **The lesson both researchers converged on:** capturing negative signal is easy; *visibly and
  durably honoring it* is what users actually judge. If you ship a control, make it stick.

### 5. Inventory, exploration & mixing ◆
- New content auditions **follower-blind** through staged test pools (small batch → graduate on early
  completion/engagement/skip-rate; specific thresholds are lore, the mechanism is well-corroborated).
  Prior virality and follower count are officially NOT ranking factors.
- Deliberate anti-boredom interleaving: proven interest-matches + fresh + trending + ~5–10%
  off-interest "disruptive" injections (TikTok's own 7% figure from the WSJ response is the only
  public exploration number); never two consecutive same-creator/same-sound items; same-category
  same-day dispersion penalties; like-bait suppression.
- **Manual "heating" (Forbes leak):** hand-picked boosts ≈ 1–2% of daily views — the pure-algorithm
  story is false at the margin. Cautionary: label any hand-boosting.
- **Intent split across feeds:** FYP (zero-intent discovery) vs Following (declared) vs topic feeds;
  the Friends tab **failed** and was retreated from — live evidence that the interest graph beats the
  social graph for discovery. Search is now a first-class discovery channel (~40% of Gen-Z per Google).

### 6. Presentment craft ◆
- **Overlay economy:** chrome never competes with content — all UI floats over the video, actions in
  the thumb-zone rail, caption behind progressive disclosure ("more"), metadata one tap deep.
- Loop design + no scrubber erases "it ended" exit cues (makes rewatch — top-tier signal — the path
  of least resistance; also pollutes signal via accidental loops).
- **The format trains the content:** distribution decided by early completion forces creators to hook
  in ~3 seconds (63% of high-CTR videos hook <3s, TikTok for Business). Presentment format ⇒ content
  quality pressure — for FTF: each generated trade must be parseable in ~2 seconds or signal turns to
  blind-swipe noise, and the one-card format *amplifies* bad inventory.

### 7. Failure modes — what NOT to import ◆
Rabbit-hole velocity (93% depression feed in 36 min; QAnon spirals) · compulsion by design (260-video
habit threshold; internal framing of screen-time tools as "public trust" optics) · control theater
(minutes-scale suppression half-lives) · engagement-bait pressure (Goodhart on every visible metric)
· opaque editorial overrides (heating) · social-graph-as-discovery (Friends tab retreat).

## Transferable principles for a finite-inventory trade deck (merged, both researchers)

1. ◆ **One trade, full-screen, forced verdict — the crown jewel; transfers 100%.** Never make a
   browse-list the primary surface; attention must stay attributable.
2. ◆ **Dwell is your watch time.** Log per-card dwell, detail-expand taps, re-views of passed trades;
   a 1-second pass ≠ a 30-second inspect-then-pass ("right players, wrong price") — distinguishable
   only if instrumented. A shortlist/"watch this player" action is the follow-equivalent (strongest
   signal per Boeker & Urman).
3. ◆ **Own the V-vector:** score = Σ P(action)·V(action) with V(proposal-sent) ≫ V(like). This is
   where "utility, not time-spent" gets encoded — the deliberate objective divergence from TikTok.
4. ◆ **Cold start: skippable 3–5-tap picker → first card fast → engineered early win** (a clearly
   good trade in the first ~5 cards, confidence-weighted like TikTok's mainstream-first seeding).
   Session one is the 260-video window: visibly adapt within ~20–50 swipes.
5. ◆ **Interleave; never rank purely best-first.** A finite deck sorted descending is a boredom
   machine (card 10 always worse than card 1 teaches early quitting). Mix proven shapes + labeled
   exploration ("Wildcard") + fresh-inventory (news-driven) cards; ~5–10% exploration quota.
6. ◆ **Dispersion rules are mandatory and arrive sooner with finite inventory:** never consecutive
   same-player/team/archetype cards; cap per-session theme repeats; audition new trade archetypes
   follower-blind with early-skip as the kill signal.
7. ◆ **Graded, durable negative steering.** Long-press → "not this player / this position / this
   value tier"; the next deck must *visibly* honor it (the anti-control-theater rule). Player
   blocklists; a "refresh my deck" full reset (the FYP-reset analog) as staleness insurance.
8. ◆ **Instant next card:** pre-render 1–2 cards ahead; advance <100ms, zero spinners.
9. ◆ **A finite deck should END — the deliberate divergence.** Completion is a feature: "Deck done —
   12 passed, 3 saved. Your model updated. New trades after waivers Tuesday." Honest scarcity +
   scheduled replenishment is the utility-app habit loop; terminate sessions on success (proposed/
   saved a trade), not exhaustion. No fake-infinite junk inventory.
10. ◆ **Overlay economy on the card:** the trade owns the pixels; actions in the thumb rail;
    rationale behind one tap of progressive disclosure; suppress your own like-bait card formats.
11. **Multiple decks frame intent cheaply** (For You / buy-low / sell-high / by-team-need) — tab
    choice is itself high-quality intent signal and keeps the main deck pure discovery (T1A).
12. **Signal density is 10–50 samples/session, not 500** — fewer, higher-confidence updates; explicit
    signals are relatively more valuable than at TikTok scale; pool per-item stats across users (T1B).

**Does NOT transfer:** infinite UGC supply · time-maximization objectives + compulsion loops ·
sound/sensory immersion · the creator economy (FTF's "creator" is its own generator — the analog is
archetype auditioning + per-card quality pressure) · TikTok-scale collaborative filtering.

## Key sources
Eugene Wei ("Seeing Like an Algorithm", "TikTok and the Sorting Hat", "American Idle") · WSJ bot
investigation (Jul 2021) · NYT "How TikTok Reads Your Mind" (Algo 101 leak) · NPR Kentucky AG filings
(260-video threshold) · Northeastern 2026 user-agency audit (arXiv 2605.10690) · Boeker & Urman
WWW'22 (arXiv 2201.12271) · CHI steering study arXiv 2504.13895 · Forbes "heating" (Jan 2023) ·
TikTok newsroom (FYP recommendation, FYP refresh, Control-your-scroll, teen defaults) · Growth.Design
TikTok case study · ByteDance exploration papers (arXiv 2307.15893, 2403.12410) · feed engineering
writeups (glich.co, techinterview.org) · TikTok-for-Business 3-second hook stats · Friends-tab
retreat (TechCrunch) · Google Gen-Z search data (Nieman Lab).
