# Consolidated Findings — Area A: Onboarding Strategies for Complex Apps

> **Date:** 2026-08-15
> **Synthesizes:** [a1-onboarding-pattern-taxonomy.md](round-1/a1-onboarding-pattern-taxonomy.md) · [a2-time-to-value-activation.md](round-1/a2-time-to-value-activation.md) · [a3-complex-app-case-studies.md](round-1/a3-complex-app-case-studies.md) · [a4-personalized-segmented-onboarding.md](round-1/a4-personalized-segmented-onboarding.md) · [a5-mobile-onboarding-constraints.md](round-1/a5-mobile-onboarding-constraints.md)
> Full citations live in the round-1 files; this doc names the finding and which file carries the sources.

---

## The seven themes that survived five independent research passes

### 1. Gate placement beats every teaching pattern — the best-evidenced move in the entire corpus

Delaying or softening the sign-up wall is the single intervention with the strongest primary evidence, and **three agents converged on it independently** (A1, A2, A3). Duolingo's VP of Growth is on record: moving signup past the first lesson ≈ **+20% DAU**, with a further **+8.2% DAU** from soft-wall/hard-wall sequencing — and neither wall type worked as well alone. Spool's "$300M button" (Register → Continue) is the older sibling of the same finding. No teaching pattern (tour, checklist, wizard) has published effects anywhere near this size.

**FTF fit:** the manual trade calculator and the 3-player matchup vote need zero league context — a value-before-identity first session is genuinely available, not theoretical. KeepTradeCut is the proof-of-concept in FTF's own market: its onboarding action *is* its data-collection action (3-player vote, no account, just a cookie), self-reporting 26.4M crowd data points.

### 2. Upfront tutorials don't teach — but complexity is the moderator

The cleanest controlled test (NN/g, N=70, 4 apps) found intro tutorials produced **no task-success gain and made apps feel significantly harder** (A1, A2, B2 all surfaced this). But the 45,000-player CHI 2012 study adds the crucial qualifier: tutorials moved engagement **up to +29% only in the most complex product tested**, nothing in simple ones. What pays is *context-grouped, guided doing* (stencils tutorials 26% faster; ToolClips 7× unfamiliar-task completion) — not upfront card decks. Skippability, notably, changed nothing ("they can skip it" is not absolution).

**FTF fit:** FTF sits in the complex band, so instruction can pay — but as guided first actions (cast a vote, run the finder on your real roster), never as a carousel.

### 3. No strong case study runs a feature tour of a dense product

Every case study (A3) converged on: **one canonical first action taught by doing** (clear the inbox / finish a lesson / vote) plus a **pre-populated workspace** (Slack auto-created channels, Notion's 2-question template pick, Canva starter challenges). "Not overwhelming" ≠ blank. Superhuman is the most transferable playbook: activation 40%→50% from re-ordering teaching around one objective (Inbox Zero); setup completion **30%→98% after removing the skip option** on one full-screen defaulted step; 45%→80% feature opt-in by teaching at moments of receptiveness.

### 4. Question count matters less than perceived payoff — and FTF mostly doesn't need to ask

Pinterest gained **+11% completion by adding a question** (with a stated reason, in-flow) and lost 30% of Google signups placing the same question out of context (A4). The real tax is collecting data you visibly don't use (Reforge: cutting 12 unused questions to 2 *used* ones → +20% first-week actives). Stated intent decays fast; **imported behavioral data beats it** (Spotify, Deezer). FTF's roster import already answers what an intent survey would ask — contender/rebuild, positional holes, pick capital — at zero taps. The open hypothesis is whether a single *confirmation* tap ("you look like a rebuilder, right?") is worth it for legibility.

### 5. Apple's rules shape the whole design space — and currently point the same direction as the growth evidence

(A5) Guideline 5.1.1(v) makes a first-screen account demand the canonical rejection shape when core features (calculator, rankings, tiers) work without one. Apple's HIG itself argues against intro carousels and for "context-specific tips instead of a single onboarding flow," teaching "through interactivity." Compliance pressure and activation evidence agree: value first, identity later. Two operational landmines: account deletion is already mandatory if FTF mints `acct_` keys (submission blocker, independent of onboarding); and store Sleeper `user_id`, not username (usernames change).

### 6. Push permission is a designable moment, not a formality — but the folklore numbers are fake

iOS sports-app opt-in medians sit ~45–50% (A5). Measured priming lifts are **+10–23%**, not the circulating "2–3×" (untraceable vendor claim). The underused lever is **provisional authorization** — quiet delivery, no prompt at all, supported directly by `expo-notifications` — which fits FTF's informational inbox, but has no published lift data: it's an experiment, not a known win.

### 7. FTF cannot A/B test its way through onboarding — plan around it

Three agents (A2, A4, B5) independently flagged this. Duolingo needs ~100k DAU to detect 1% effects; onboarding tests are the hardest kind (no pre-exposure history → CUPED inapplicable; early-converter distortion). At FTF's scale the honest posture: qualitative session review + the existing feedback loop + one validated behavioral activation metric, with experiments reserved for structural changes big enough to show double-digit effects. "Connected a Sleeper league" is a *setup* event, not an activation event — the activation definition should be behavioral (e.g., viewed a mutual-gain trade from their real roster).

## Contradictions and tensions worth carrying forward

- **Step-minimization vs the Noom counter-case:** Noom monetizes a ~113-screen onboarding. Reconciliation hypothesis (A2): tolerance scales with *visible return per step*, not step count. Noom also optimizes paid-traffic conversion, not organic retention — don't import its conclusions.
- **Skip-removal (Superhuman) vs friction-removal (Duolingo):** both are evidence-backed. The synthesis: remove *identity* friction, but make the one setup step that powers everything else (league connect, for users who came for that) confident and default-filled rather than skippable-and-abandoned.
- **Evidence hygiene:** all five agents found the onboarding-stats ecosystem substantially circular vendor content. Specific untraceable claims to never plan against are listed per-file ("every extra step costs X%", "personalization lifts retention 40%", "2–3× push priming").

## Recommended round-2 drill-downs (Area A's share)

1. **The account-optional first session for FTF specifically** — vote-first/calculator-first flow design, Sleeper-username-as-"connect-a-league" framing vs guideline 4.8, KTC/dynasty-community sentiment on vote gates (an explicitly logged gap), and re-onboarding implications. Two round-1 agents ran out of search budget before closing fantasy-specific questions.
2. *(shared with Area B)* Seasonal lifecycle and returning-user re-onboarding — see CONSOLIDATED-B.
