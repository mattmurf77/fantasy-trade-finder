# Tier B Briefs — Condensed

> 19 peripheral and utility units. Each gets description, strengths, shortfalls, six criteria grades, and three ranked changes holistically.
> Tiers: **P0** launch blocker · **P1** first 30 days · **P2–P4** backlog. Levers **[A]** adoption · **[R]** retention. Effort S/M/L.

---

## 15. Rank Home / Rank Menu — **C+** · Us B · Si B+ · Re C · Rp C · Cm B · Gr F

**What it is.** The "Build your board" chooser: three outcome-labelled cards (Fastest / Most precise / Most control) over a collapsed "More ways to rank" disclosure. Content is shared with the Rank Menu bottom sheet via one model so the two can't diverge.

**Strongest.** Labelling methods by *outcome* rather than mechanism is excellent product writing — "Fastest," "Most precise," "Most control" tells a user what they get, not what the feature is called. The shared content model is disciplined engineering.

**Shortfalls.** Under shipped defaults, **no in-app UI navigates here** — the Rank tab lands on Quick Set and this chooser is reachable only via a "More ways to rank" header link. Yet it is one of only two places that write `ranking_method`, making an unreachable screen load-bearing for the unlock. Choosing via the chooser persists the preference; choosing the identical method from the Rank Menu sheet does not — the same action has different side effects depending on which surface you used.

1. **P0 · [A/R] · S** — Reconcile the two choosers' side effects, or write `ranking_method` from the surfaces themselves. This asymmetry is the mechanism behind the unlock break.
2. **P1 · [A] · S** — Decide whether this screen exists. It is currently a well-designed page nothing links to.
3. **P2 · [A] · S** — Give `RookieRanks` an entry here; it appears in neither chooser list.

---

## 16. Quick Rank — **C+** · Us B · Si B · Re C · Rp B− · Cm B+ · Gr F

**What it is.** The within-tier ordering pass after Quick Set. Tap players best-first; each tap stamps the next rank. Subset-safe by construction — reordering a tier can never move anyone across a tier boundary.

**Strongest.** The subset-safety guarantee is real engineering rigor around a construction the codebase notes has destroyed a board before. Auto-skipping tiers with fewer than two players is a thoughtful touch.

**Shortfalls.** Deliberately excluded from both choosers, so its only entry is a completion alert from Quick Set — meaning a user who dismisses that alert can essentially never find it again. Zero client analytics.

1. **P2 · [A] · S** — Give it a discoverable entry point for users who skipped the prompt.
2. **P2 · [A] · S** — Explain the click-order mechanic before the first tap.
3. **P3 · [A] · S** — Instrument completion.

---

## 17. Tiers Board — **C+** · Us B+ · Si C+ · Re C+ · Rp B− · Cm A− · Gr F

**What it is.** The drag-to-bin tier board with an "ALL" cross-position view, multi-select, VoiceOver move actions, search, and an explicit save.

**Strongest.** Two full input paths — drag, and a no-drag multi-select — plus VoiceOver custom actions is unusually complete accessibility thinking for a gesture-heavy surface. The one-directional pool guard (tiered players can't return to Unassigned) prevents a real class of mistake. It's populated from seed values, so a new user's board is never empty.

**Shortfalls.** Nothing auto-saves, which is correct but unsignalled until the pinned Save bar is noticed. `TierBadge` and `TierBin` components exist but are unused by this screen. Zero analytics on drag, bulk move, save, reset, or copy.

1. **P2 · [A] · S** — Make unsaved-changes state unmistakable before navigation away.
2. **P2 · [A] · S** — Add the multi-key pool sort Angle Ranks has and this lacks.
3. **P3 · [A] · S** — Delete the unused tier components or wire them.

---

## 18. Manual Ranks — **C+** · Us A− · Si B · Re C · Rp C · Cm B · Gr F

**What it is.** The 1-to-N board with two reorder paths — long-press drag, or tap the rank number and type a target — auto-saved on a 600ms debounce with a save-status pill.

**Strongest.** The jump-to-rank input is the best interaction in the ranking cluster: moving a player from 120 to 3 costs the same effort as moving them from 5 to 3, which drag can never achieve. The three-state save pill (saving / saved / error) is exactly right. `apply_reorder` permutes the user's own existing values rather than interpolating, deliberately avoiding a documented past bug.

**Shortfalls.** Selecting this method from the chooser sets `ranking_method: 'manual'`, which unlocks the trade finder **unconditionally with zero board changes** — a one-tap unlock that makes the progression system incoherent. Zero analytics.

1. **P1 · [A/R] · S** — Fix the one-tap unconditional unlock; it undermines the entire progression.
2. **P2 · [A] · S** — Surface jump-to-rank; it's the best affordance here and least discoverable.
3. **P3 · [A] · S** — Instrument saves.

---

## 19. Pick Anchors — **C+** · Us C+ · Si B− · Re C− · Rp B+ · Cm A− · Gr F

**What it is.** A one-player-at-a-time valuation wizard pricing players in draft-pick terms ("Worth how much in draft capital?") across eight rungs.

**Strongest.** Conceptually the most distinctive elicitation method in the product — asking for a *value statement* rather than a comparison. The footer explains why pick-denomination matters better than any other copy in the app. One tap saves and advances. Progress persists per format.

**Shortfalls.** **Anchor saves can never satisfy the unlock**, because `apply_anchor` sets an Elo override without touching the interaction counter — so a user who exclusively uses this method, which the "in your own vocabulary" framing most invites, can never unlock. Its rung labels also differ from the tier ladder's labels for the same underlying bands ("4 1sts" vs "4+ 1sts", "No value" vs "FA"), which is a quiet consistency break in the app's most important vocabulary.

1. **P0 · [A/R] · S** — Make anchor saves count toward unlock, or route anchor users to a method that can.
2. **P1 · [A] · S** — Reconcile the two label sets; the pick vocabulary is the product's core metaphor and it currently says two things.
3. **P2 · [A] · S** — Show the value being assigned as it's assigned.

---

## 20. Trends — **C+** · Us B · Si B+ · Re B · Rp C · Cm B− · Gr F

**What it is.** Risers, fallers, and easiest sells/buys over a 30-day window, with a position filter.

**Strongest.** The best evergreen return hook in the ranking cluster — content changes without the user doing anything. The no-history empty state explains precisely what generates history and over what window. Genuinely read-only with no mutation risk.

**Shortfalls.** Deliberately not prefetched, so it always loads cold. Position filtering is client-side over a full fetch. Zero analytics. Not linked from anywhere a user would naturally look for market news.

1. **P2 · [R] · M** — Promote this; it's the most habit-forming content in the app and it's buried under "More ways to rank."
2. **P2 · [R] · S** — Add a notification hook for large movers on the user's roster.
3. **P3 · [A] · S** — Make riser/faller entries shareable.

---

## 21. Free Agents — **C+** · Us B+ · Si B · Re B− · Rp C+ · Cm C+ · Gr F

**What it is.** Best available players ranked by the caller's own board with consensus fallback, position filters, a drop-candidate suggestion, and a claim sheet for Sleeper leagues.

**Strongest.** The FAAB-aware claim sheet — bid input, remaining budget, open-slot detection, drop candidates sorted least-valuable-first with untouchables withheld — is the most operationally useful flow in the app. The consensus-fallback notice is honest. Non-Sleeper leagues get a dimmed Add that *explains itself*, which is better than the silent absence elsewhere.

**Shortfalls.** The flow terminates in a deep link out to Sleeper rather than an in-app claim. Weekly relevance in season, near-zero out of it. Zero growth affordance.

1. **P2 · [R] · M** — Notify on high-value free agents matched to the user's roster needs; this is a natural weekly hook.
2. **P2 · [A] · S** — Show FA value relative to the tier ladder for consistency with the rest of the app.
3. **P3 · [A] · S** — Add projections alongside value; both competitors with this screen show them.

---

## 22. Portfolio — **C−** · Us C · Si C+ · Re C · Rp C · Cm C− · Gr F

**What it is.** Cross-league exposure, sorted by ownership count, with per-league tier chips. Hard-gated behind having two or more leagues.

**Strongest.** The gate is honest and offers a route to Settings. Per-league tier chips make lopsided exposure legible at a glance.

**Shortfalls.** For the large majority of users — single-league — this is a permanently empty tab-adjacent surface. It is the thinnest screen in the app relative to its competitive equivalents: DynastyDealer's portfolio carries summary tiles, per-league records, a value chart, roster breakdown, and an optimal-lineup computation; DynastyGM's Shares shows ownership percentages. FTF shows a sorted list.

1. **P2 · [A] · M** — Add exposure percentage and league-count context; the single cheapest step toward parity.
2. **P2 · [A] · S** — Give single-league users a reason to add a second league here rather than a dead gate.
3. **P3 · [A] · M** — Add per-league record/rank context.

---

## 23. Mock Draft — **F** · Us F · Si F · Re F · Rp C · Cm D · Gr F

**What it is.** A mock-draft surface reachable from a Real/Mock toggle inside the Draft Room. **It cannot be started.** The CPU-bot model failed its calibration gate, so every entry path terminates in a refusal: *"Not ready yet. Our computer drafters don't pick closely enough to real drafters, and we'd rather ship nothing than ship bots we can't stand behind."*

**Strongest.** The refusal itself is admirable — it's an honest, well-written statement of a real quality bar, and the mode-marking rail ensures a mock can never be confused with a real draft. The recap deliberately omits a metric it cannot compute rather than fabricating one. This is a team with standards.

**Shortfalls.** `draft.mock` is **on**, so the feature is reachable, advertised by a visible toggle, and dead. A user who taps Mock from a top-level tab gets a polite refusal. That is worse than the feature not appearing at all, and it sits one level under the app's third tab.

1. **P0 · [A] · S** — Hide the Mock toggle until the model passes. Shipping a visible, tappable dead end on a top-level tab is a launch-quality problem, not a roadmap item.
2. **P2 · [A] · L** — Fix or cut the CPU model; DynastyGM ships a working simulator.
3. **P3 · [A] · S** — If kept, move it behind an explicit "beta" opt-in.

---

## 24. Rookie Ranks — **C+** · Us B · Si B · Re C · Rp B− · Cm B · Gr F

**What it is.** Every rookie on the board in one cross-position list, drag-reorderable, writing through the same reorder lane as Manual Ranks.

**Strongest.** Values are synced by construction with the position boards — the same board read through a filter, not a second Elo space. That's the right architecture and the code says so. The two-way bridge to and from the Draft Room ("Back to the draft room") is well handled. It was made editable after live testing showed a labelled "Rank the rookies" entry landing on a read-only screen — good responsiveness.

**Shortfalls.** Appears in neither ranking chooser, so outside the Draft Room it's effectively undiscoverable. Zero analytics.

1. **P2 · [A] · S** — Add a chooser entry.
2. **P2 · [R] · M** — Make it seasonally prominent around the rookie draft window.
3. **P3 · [A] · S** — Instrument it.

---

## 25. Record Picks — **C+** · Us B+ · Si C+ · Re C− · Rp B · Cm B+ · Gr F

**What it is.** Live offline pick recording — one tap per pick, movable cursor, offline-queued and fire-and-forget.

**Strongest.** The offline-first design copying the analytics queue's contract is smart reuse. One tap per pick with auto-advance is the correct interaction for a live draft. The "no auto-shift" decision around off-by-one recovery is deliberate and documented. The precondition message names exactly what to fix.

**Shortfalls.** Requires completed pick assignment first, and the precondition copy doesn't link to the screen that fixes it. Useful for a few hours a year. Zero analytics on a feature whose entire value is a live event.

1. **P2 · [A] · S** — Link the precondition to Pick Assignment directly.
2. **P2 · [A] · S** — Instrument it; a live-draft feature with no telemetry can't be evaluated.
3. **P3 · [A] · M** — Add Maestro coverage; it has none and ships flag-on.

---

## 26. Pick Assignment — **C** · Us B · Si C · Re D · Rp B · Cm B+ · Gr F

**What it is.** An ESPN-only grid for asserting who owns each rookie pick, with immediate per-tap persistence, CAS conflict resolution, and member-entered provenance tagging.

**Strongest.** The provenance model is excellent — every user-asserted slot is tagged "MEMBER-ENTERED" with the note that ESPN never confirms them, and contested or orphaned picks are explicitly "not priced." The CAS conflict prompt ("X changed this pick — keep theirs, or use yours?") is a genuinely sophisticated multi-user affordance. The "no price input, ever" constraint is a good design line.

**Shortfalls.** **Zero analytics and zero outbound navigation** — a user finishing assignment cannot proceed to recording picks without backing out and re-entering. Reachable only via a three-tap path on ESPN leagues. No Maestro coverage despite shipping flag-on.

1. **P2 · [A] · S** — Add a forward path to Record Picks on completion.
2. **P2 · [A] · S** — Instrument the screen.
3. **P3 · [A] · M** — Add Maestro coverage for the conflict path.

---

## 27. ESPN Connect — **B−** · Us A− · Si B+ · Re n/a · Rp B · Cm A− · Gr F

**What it is.** A WebView capturing ESPN's two league cookies after the user logs in on ESPN's own page.

**Strongest.** The best-explained sensitive flow in the app. It states plainly what is captured and why, discloses encryption and read-only use, links to the privacy policy, handles the OTP step with an explicit hint about iOS autofill, and shows a wedge hint if the page stalls. Four analytics events including abandonment — the best-instrumented screen in the audit.

**Shortfalls.** Inherently fragile against a third party's login page. Multi-step and unavoidably intimidating.

1. **P2 · [A] · S** — Add a recovery path when capture repeatedly fails.
2. **P3 · [A] · S** — Set expectations on duration before entering.
3. **P4 · [A] · S** — Consider read-only-scope messaging even more prominently.

---

## 28. Sleeper Connect — **B−** · Us B+ · Si B · Re n/a · Rp B+ · Cm A− · Gr F

**What it is.** A WebView capturing Sleeper's JWT from local storage after login, enabling Send-in-Sleeper and account verification.

**Strongest.** Clear four-phase model, honest disclosure ("We never see your password"), and it doubles as account verification — clearing the verify banner and hard-gating the highest-risk route in the app.

**Shortfalls.** **Zero analytics** — no opened/captured/abandoned events, unlike the ESPN twin which has four. Given this flow gates the app's most consequential capability, its funnel is invisible. It also captures a full-account token against an undocumented private API that internal docs mark ToS-adverse.

1. **P1 · [A] · S** — Instrument it to match ESPN Connect; this is the gate on your highest-value action.
2. **P1 · [A] · S** — Make the ToS/fragility risk an explicit operator-tracked item before public launch.
3. **P2 · [A] · S** — Add Maestro coverage; it has none.

---

## 29. Feedback Inbox — **C** · Us C+ · Si B · Re C · Rp C · Cm B · Gr F

**What it is.** A device-local list of submitted feedback with severity and lifecycle status chips.

**Strongest.** Closing the loop on user feedback with real status ("Fixed — in next update," "Shipped") is a genuine trust mechanism most apps skip entirely. Retry-sync handles offline capture properly.

**Shortfalls.** **No header close control — swipe-to-dismiss only**, which is a modal accessibility gap. Buried in a Testing section gated on `__DEV__` or an allowlist, so ordinary users can submit feedback via the FAB but can never see its status. Zero analytics.

1. **P2 · [A] · S** — Add a close control.
2. **P2 · [R] · S** — Make it reachable for real users; status feedback is wasted if only operators can see it.
3. **P3 · [A] · S** — Instrument it.

---

## 30. Profile *(dark)* — **F** · Us F · Si F · Re F · Rp C− · Cm D · Gr F

**What it is.** A read-only public profile of a user's ranking footprint. **Unreachable twice over**: `profiles.public_pages` is false, and there is **zero in-app entry point anywhere in the app** — no button, row, or avatar navigates here. Only a `/u/<username>` link reaches it, and with the flag off that renders "Profile not available."

**Strongest.** The concept is the app's most natural growth surface: a public artifact of a user's opinions, addressable by URL, with OG-image infrastructure already built server-side.

**Shortfalls.** 429 lines of shipped-but-invisible code. This is the clearest example of the audit's central pattern — a complete growth loop built and left unconnected.

1. **P1 · [A] · M** — Turn it on and link to it. Public profiles are the cheapest identity-based growth loop available and everything but the entry point exists.
2. **P2 · [A] · S** — Link from contrarian leaderboards and match rows.
3. **P3 · [A] · S** — Make it work for non-users as a landing page.

---

## 31. Test Stages *(operator tooling)* — **n/a**

Correctly gated behind `testing.stage_users` plus a server-side allowlist, and correctly excluded from analytics by design. No user-facing grade applies. Well built for its purpose. One note: it is the only path to a documented factory reset, which is a useful QA affordance worth keeping.

1. **P4 · S** — No action. Working as intended.

---

## 32. Trade Finder Hub *(dead code)* — **F**

1,196 lines, unrouted, zero importers, documented as dead in three separate places. Its DNA editor was lifted into `TradeDnaSheet`; its FA link was superseded by the mode-bar chip.

1. **P2 · S** — Delete it. Dead code of this size makes the screens registry misleading and every future audit more expensive.
2. **P3 · S** — Same for `TradeMeter.tsx`, which has no import site anywhere.
3. **P4 · S** — Add a lint rule for unrouted screens.

---

## 33. Placeholder *(dead code)* — **F**

31 lines, never registered, superseded by all four screens it stood in for.

1. **P2 · S** — Delete.
2. **P4 · S** — —
3. **P4 · S** — —

---

## Tier B pattern summary

Three things recur across all nineteen:

1. **Analytics are near-absent.** Fifteen of nineteen have zero client events. Combined with the Tier A findings, the app ships with no client instrumentation on ranking saves, League surfaces, draft actions, or Send-in-Sleeper.
2. **Discoverability is the dominant defect, not quality.** Rank Home, Quick Rank, Rookie Ranks, Trends, and Profile are all well built and effectively unreachable. The app's problem is rarely that a screen is bad.
3. **Growth is F on eighteen of nineteen.** Not one peripheral surface produces a user, including the several — tier boards, profiles, draft boards — that are naturally shareable and already have server-side infrastructure waiting.
