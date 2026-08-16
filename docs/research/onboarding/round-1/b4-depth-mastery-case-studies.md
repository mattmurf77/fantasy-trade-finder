# B4 — Case Studies of Mastery Curves: How Products Reveal Depth Over Time

**Date:** 2026-08-15
**Lens:** Games (tutorialization, skill-gating, unlock systems) + Pro tools (Figma, Office/Excel, Photoshop, Linear, Superhuman, command palettes, keyboard-shortcut teaching)
**Scope note:** This is research only. No product decisions are made here; the final section contains hypotheses for FTF, not recommendations to build.

---

## TL;DR

- **Games teach by constraining the space, not by narrating it.** Mario World 1-1 and Portal's early chambers are engineered so the *only* available action is the lesson. Nintendo's documented four-beat structure (introduce → develop → twist → conclude, borrowed from kishōtenketsu) and Valve's documented "checklisting then lateral thinking" are the same shape: teach one primitive in a safe room, then force recombination. ([Game Developer](https://www.gamedeveloper.com/design/the-secret-to-i-mario-i-level-design), [Game Informer](https://gameinformer.com/b/features/archive/2010/03/17/thinking-with-portals-making-a-test-chamber.aspx))
- **The most-cited game-teaching wins came from watching people fail, not from theory.** The Goomba exists because playtesters couldn't handle a Koopa first; GLaDOS exists because playtesters said Portal "felt like a tutorial." Valve playtested Portal weekly and ran roughly 100 testers per Half-Life 2 chapter. ([Adafruit/Eurogamer](https://blog.adafruit.com/2025/09/14/miyamoto-explains-how-super-mario-bros-world-1-1-was-created/), [GMTK](https://gmtk.substack.com/p/valves-secret-weapon))
- **Competence-gating in games is real but is mostly *pacing*, not *proof of skill*.** The strongest published evidence for gating is engagement-shaped ("curiosity gap," staged feature reveal in the Accommodate → Assimilate → Accelerate model), not "we verified you were good enough." Treat "unlock behind demonstrated competence" as design lore with weak public evidence. ([Game Developer](https://www.gamedeveloper.com/design/first-five-minutes-how-tutorials-make-or-break-your-social-game))
- **In pro tools, the hard problem is not hiding depth — it's that users never find the depth they explicitly asked for.** Office's Ribbon was built after Microsoft found "people weren't finding the very features they asked us to add," on telemetry of ~3 billion sessions and ~150M Word command clicks per month. ([Wikipedia](https://en.wikipedia.org/wiki/Ribbon_(computing)), [UX Week notes](https://www.jurecuhalev.com/blog/jensen-harris-the-story-of-the-ribbon-office-2007-uxweek08-notes/))
- **Users are structurally biased against learning the faster way.** Carroll & Rosson's "paradox of the active user" (production bias, assimilation bias) plus documented satisficing and the "performance dip" explain why keyboard shortcuts stay unused even by decade-long experts. ([NN/g](https://www.nngroup.com/articles/paradox-of-the-active-user/), [Raursø et al., DUXU 2020](https://vbn.aau.dk/ws/portalfiles/portal/438685057/HCII2020_cameraready.pdf))
- **Two interventions have real controlled/field evidence.** *Skillometers* (a reflective widget showing your own modality mix + the shortcut you skipped) raised hotkey use from 28% → 50% mean, and 42% → 80% by the tenth repetition, n=24, UIST 2013 — but did **not** significantly improve task time in-study. *CommunityCommands* (collaborative-filtering command recommendations in AutoCAD) produced 2.1× as many "good" suggestions as prior techniques and significantly increased unique commands issued in a 6-week field deployment. ([Skillometers](https://www.research.autodesk.com/app/uploads/2023/03/skillometers-reflective-widgets-that.pdf_reco6nF5Pb4FQHd2x.pdf), [TOCHI 2011](https://www.tovigrossman.com/papers/2011%20TOCHI%20cc.pdf))
- **Superhuman is the clearest commercial case of buying mastery with humans instead of UI.** 30-minute 1:1 concierge onboarding, explicit shortcut drilling (j/k/e/h), ~2× activation and ~2× referral vs self-serve, ~$650k ARR per onboarding specialist — and when they finally productized it, the winning traits were *opinionated, interruptive, interactive* (full-screen panels lifted feature opt-in 45% → ~80%). ([First Round Review](https://review.firstround.com/superhuman-onboarding-playbook/))
- **Command palettes are the single most transferable expert-accelerator, and they double as a teaching surface** — one shortcut to reach everything, fuzzy matching so recall isn't required, and the palette displays the shortcut you *could* have used. Superhuman states this explicitly as a design goal. ([Superhuman](https://blog.superhuman.com/how-to-build-a-remarkable-command-palette/), [uxpatterns.dev](https://uxpatterns.dev/patterns/advanced/command-palette))

---

## Part 1 — Games: teaching as level design

### 1.1 The canonical case: Super Mario Bros. World 1-1

The design intent is documented, not merely inferred. Miyamoto designed World 1-1 so players would "gradually and naturally understand what they're doing" through the level itself rather than explicit instruction, and the level contains everything needed to eventually play freely; he later applied this "learning through play" principle to subsequent games ([Wikipedia: World 1-1](https://en.wikipedia.org/wiki/World_1-1)).

Concrete mechanisms on the first screen:

1. **Empty space first.** The player is placed with nothing to do but move, so movement is discovered before it matters.
2. **A single, slow, forgiving threat.** The approaching Goomba teaches jumping with a low-consequence failure — you lose almost no progress and retry immediately ([Wikipedia](https://en.wikipedia.org/wiki/World_1-1)).
3. **A deliberate downgrade of the first enemy.** The opening enemy was originally a Koopa Troopa; teaching jump-then-kick proved too much for a first encounter, so Nintendo *invented* the stomp-once Goomba specifically to be the first lesson ([Adafruit summarizing the 2015 Eurogamer Miyamoto/Tezuka interview](https://blog.adafruit.com/2025/09/14/miyamoto-explains-how-super-mario-bros-world-1-1-was-created/)).
4. **A surprise that rewrites a rule.** The question block yields a Mushroom that *moves like an enemy* but helps you — teaching that the world's objects need to be evaluated, not pattern-matched ([Wikipedia](https://en.wikipedia.org/wiki/World_1-1)).

The transferable observation is not "put a Goomba in your app." It's that the teaching lives in **what the environment makes possible**, and that the difficulty of the first lesson was *lowered by inventing a new, simpler object* rather than by adding explanation.

### 1.2 The formal structure: kishōtenketsu / four-beat level design

Koichi Hayashida (Super Mario 3D World) described Nintendo's level structure as four beats: **introduction** (learn the mechanic), **development** (a harder use of it), **twist** (something unexpected that reframes the mechanic), **conclusion** (demonstrate mastery). Hayashida credited the framing to Miyamoto, who drew comics as a kid and stressed the payoff beat ([Game Developer](https://www.gamedeveloper.com/design/the-secret-to-i-mario-i-level-design)).

Two things are worth flagging. First, this is **stated design intent from a named designer**, which is stronger than blog reconstruction but is not measured evidence. Second, the load-bearing beat is the *twist* — the point at which the player must apply the mechanic in a context they weren't shown. That is the difference between demonstrating a feature and building competence with it.

### 1.3 Valve: the same structure, arrived at empirically

Valve's published account of building a Portal 2 test chamber names two phases:

- **Checklisting** — break a new mechanic into the components a player must understand and give them a clean environment to experiment safely with the fundamentals.
- **Lateral thinking** — once the basics are held, enumerate the interesting things the mechanic can do, then build challenges that force players to reconsider what they learned.

They state the goal as focusing "on some key aspect of a mechanic, and on how we can teach it to players while still challenging them," and they report a recurring failure mode: players very rarely look up, and almost never look at what is obvious to the designers ([Game Informer](https://gameinformer.com/b/features/archive/2010/03/17/thinking-with-portals-making-a-test-chamber.aspx)).

Note that checklisting → lateral thinking is functionally identical to introduction/development → twist/conclusion. Two studios with no shared lineage converged on "isolate the primitive, then force recombination."

Valve's stated differentiator is volume of playtesting: Gabe Newell has called it their "secret weapon"; Portal was tested weekly through development; Half-Life 2 chapters used roughly 100 playtesters each; testing began within days of prototyping. Concrete outcomes attributed to playtests include GLaDOS (testers reported the game felt like a tutorial, so a narrative antagonist was added), the sterile white aesthetic (cluttered rooms confused players about what was interactive — one tester spent 30 minutes trying to push a shelf instead of the nearby box), and cutting a Portal 2 paint mechanic that made testers nauseous ([GMTK](https://gmtk.substack.com/p/valves-secret-weapon)). Their stated observation rules are relevant to any app's usability testing: observe silently, have designers run their own tests, treat feedback as data rather than instruction.

### 1.4 Open-world variant: Breath of the Wild's Great Plateau

The Great Plateau is a walled tutorial region: it teaches the core mechanics but is exploration-driven, presents mechanics piecemeal, and lets players choose order and pace — the game tells you *where* to go but not *how*, or what to do on arrival. It is widely cited by critics as a best-in-class tutorial area ([Wikipedia: Great Plateau](https://en.wikipedia.org/wiki/Great_Plateau)).

The structural trick worth stealing: it is a **bounded sandbox with a hard exit gate**. Everything the game will ask of you exists inside a small, safe area, and the exit is earned by completing a small number of self-directed objectives — not by sitting through a sequence. Note that "critically acclaimed" is press consensus, not measured learning outcomes.

### 1.5 Unlock systems and gating: what's actually evidenced

This is where the transfer story is weakest, and it's worth saying so plainly.

The best-documented *data* on gating comes from social/F2P game onboarding rather than from competence verification. An analysis of six popular Facebook games found:

- MixPanel data indicating that if a user advances past the second tutorial step, **over 90% complete the whole tutorial** — the drop-off is concentrated in the first two steps.
- A de-facto **three-minute standard** for tutorial length, with all six games completable in under four minutes and the densest instruction in the first 60 seconds.
- **Progressive complexity by design:** the first minute has the most steps, then the tutorial eases into resource management, social features, and monetization.
- **Feature gating framed as a "curiosity gap"** — locked features/levels are used to create the desire to return, i.e. a *retention* device.
- A three-phase framework: **Accommodate** (give the mechanics and starting resources) → **Assimilate** (tie progress to social peers) → **Accelerate** (expose the full feature set).
- The endpoint matters more than the length: leave something "cooking" so the player is incentivized to come back ([Game Developer](https://www.gamedeveloper.com/design/first-five-minutes-how-tutorials-make-or-break-your-social-game)).

What I could *not* find published: controlled evidence that gating a feature behind *demonstrated competence* (as opposed to time, level, or session count) improves learning or retention. Games do this constantly — ranked modes behind level thresholds, difficulty ladders unlocked by winning — but the public justification is matchmaking integrity and pacing, not pedagogy. **Classify "competence-gated unlocks" as design lore with a plausible mechanism and no public controlled evidence.**

### 1.6 Why text tutorials fail (and the learning-science framing)

The practitioner consensus, with the usual caveat that it's practitioner consensus:

- **Cognitive load.** Working memory holds little; instructional methods should avoid overloading it. Front-loading multiple instructions before any application creates strain.
- **Passive vs. active.** Reading about a mechanic retains worse than doing it.
- **Motivation mismatch.** Players opened the game to play, not to read ([GDevelop](https://gdevelop.io/blog/improve-game-tutorials)).

The recommended patterns — contextual/just-in-time introduction at the moment the mechanic becomes relevant, one mechanic at a time, gradual difficulty increase within the zone of proximal development — are the same ones that keep appearing on the pro-tools side.

### 1.7 What transfers to a utility app, and what doesn't

**Transfers:**
- Isolate one primitive, give a safe place to exercise it, then force a recombination that proves it stuck.
- Lower the difficulty of the *first* lesson by changing the object, not by adding text (invent the Goomba).
- Failure must be cheap and instantly retryable.
- Observe silently; the thing that is obvious to you is invisible to them.
- Concentrate your instrumentation on the first two steps — that's where the cliff is.

**Doesn't transfer cleanly:**
- **Games control the world; utility apps don't.** Mario can guarantee the only affordance is "jump." FTF cannot guarantee a user's roster, league settings, or intent. Level-design teaching depends on authorial control over the environment; a data-driven app's "level" is the user's own messy data.
- **Games own the motivation.** Players accept friction and failure as the product. A user opening a trade app at 11pm before a waiver deadline does not.
- **Session shape is inverted.** Games get a long uninterrupted first session; mobile utility apps get 90 seconds, and the "level" is re-entered at unpredictable intervals with full context loss.
- **Failure is not cheap in a utility app.** A bad trade sent in-platform is a real consequence, which argues for sandboxes (Superhuman's synthetic inbox) over "learn by dying."
- **Locking is hostile in a tool the user pays for or depends on.** Games can lock content because content *is* the reward. In a tool, a locked feature reads as the product withholding value. The safer analogue is *not-yet-surfaced* rather than *locked*.

---

## Part 2 — Pro tools: novice → expert in feature-dense software

### 2.1 The Office Ribbon: the best-documented depth problem in software

Microsoft's Customer Experience Improvement Program telemetry, per Jensen Harris's "Story of the Ribbon" talk, covered roughly **3 billion anonymous data sessions**, tracked ~**150 million Word command-button clicks per month**, and instrumented nearly **6,000 discrete data points**. The complexity trajectory it documented:

| Release | Toolbars | Menu items |
|---|---|---|
| Word 1.0 (1989) | 2 | ~50 |
| Word 97 | 18 | — |
| Word 2000 | 23 | — |
| Word 2002 | 30 | — |
| Word 2003 | 31 | ~300 |

Harris's framing of the failure is the one worth carrying: **"The sense of mastery of our software was gone."** They also report their most useful method was *longitudinal* usability testing — weeks-to-months of observation — plus eye-tracking and hundreds of prototypes ([UX Week 2008 notes](https://www.jurecuhalev.com/blog/jensen-harris-the-story-of-the-ribbon-office-2007-uxweek08-notes/)).

The single most-quoted finding: **"people weren't finding the very features they asked us to add"** — the most-requested features frequently already existed ([Wikipedia: Ribbon](https://en.wikipedia.org/wiki/Ribbon_(computing))). This is the depth problem in one sentence: user feature requests are often *discovery* failures wearing a feature-request costume.

The Ribbon's answers were structural: unify menus/toolbars/task panes into one extensible surface consistent across a dozen apps; use **contextual tabs** that appear when you select a picture/chart/table and disappear when you don't; use **galleries** to show concepts that were hard to name; and build each command group in up to four sizes (large/medium/small/collapsed) with a prioritization system that responds to window width ([Jensen Harris](https://jensenharris.com/home/ribbon), [Wikipedia](https://en.wikipedia.org/wiki/Ribbon_(computing))).

**The cost is documented too, and matters as much as the win.** Power users reported the Ribbon took too much time and patience to learn; an ExcelUser survey skewed negative with dissatisfaction *increasing* with expertise; self-reported productivity loss averaged around 20%. Average users showed "fairly good acceptance" ([Wikipedia: Ribbon](https://en.wikipedia.org/wiki/Ribbon_(computing))). Harris's own conclusion — "no user interface affordance can be good at everything" — is the honest read ([Jensen Harris](https://jensenharris.com/home/ribbon)).

**Implication:** restructuring for discoverability is a *transfer of pain from novices to experts*. If you re-architect surfaces to reveal depth, you will make your most engaged users slower, and they will tell you about it.

### 2.2 Why users don't level up on their own

Carroll & Rosson's **paradox of the active user** (IBM User Interface Institute, early 1980s): users start using software immediately and never read the manual, because they optimize for the task in front of them rather than for their own long-run efficiency. Nielsen's gloss: we cannot build products for an idealized rational user ([NN/g](https://www.nngroup.com/articles/paradox-of-the-active-user/); [original paper PDF](https://research.cs.vt.edu/ns/cs5724papers/4.mental.mental.carroll.paradox.pdf)). The two named sub-effects: **production bias** (learning time feels stolen from the task) and **assimilation bias** (users interpret the new system through the old one, importing habits that no longer fit).

The keyboard-shortcut literature adds mechanism:

- Keyboard shortcuts are the fastest command modality but are **remarkably underutilized — by long-tenured experts, not just novices**.
- **Satisficing** (Simon): users aim to accomplish the task sufficiently, not optimally.
- **GUIs actively work against the transition:** presenting options in a visually salient way helps novices but biases users toward incremental interactive actions, each of which produces an immediate display change that cues the next action — cheap cognitively, and self-reinforcing.
- **Recognition beats recall**, so clicking a visible icon stays easier than remembering a binding.
- Switching modality causes a **performance dip** that further dissuades adoption.
- Existing aids fail in characteristic ways: full shortcut cheat-sheets are information overload and require the user to be proactive; post-hoc "you could have pressed X" notifications arrive *after* the choice and action, so their preventive power is small; and forceful approaches (disabling the mouse path, adding time buffers) do work but are obtrusive ([Raursø et al., DUXU/HCII 2020](https://vbn.aau.dk/ws/portalfiles/portal/438685057/HCII2020_cameraready.pdf)).

That last bullet is important: Grossman's known result that adding a delay to pointer selection increases hotkey adoption works by making the old path *worse*, not the new path better.

### 2.3 Two interventions with real evidence

**Skillometers (Malacria, Scarr, Cockburn, Gutwin, Grossman — UIST 2013).** A "skillometer" is a reflective widget that visualizes the user's own performance level and the gains available from switching modality — explicitly *not* a tooltip, because a tooltip helps you do the thing but doesn't reveal a meta-level fact about your own behavior. They define four target domains: intramodal improvement (get faster at the method you use), **intermodal improvement** (switch to a faster method), **vocabulary extension** (learn functions you don't know exist), and **strategic** (combine functions better). Four design goals for any skillometer: visualize that improvement is possible; show how; motivate; minimize disruption.

Controlled experiment: n=24, Apple Keynote, between-subjects, 80 logged command selections each, ~15 minutes.
- Hotkey use: **50% (skillometer) vs 28% (control)** mean across repetitions (F₁,₂₂=4.52, p<0.05).
- By the 10th repetition: **80% vs 42%** — a significant Interface × Repetition interaction (F₉,₁₉₈=3.13, p<0.01), i.e. **earlier and faster adoption**.
- Modality speeds confirmed: hotkey **3.3s**, toolbar **5.2s**, menu **7.7s** (p<0.001).
- **No significant task-time improvement** in-study — toolbar selections were actually *slower* with the skillometer present (5.8s vs 4.2s), which the authors attribute to the extra mental work of memorizing bindings. They speculate performance would keep improving beyond the study window, but say further work is needed ([paper PDF](https://www.research.autodesk.com/app/uploads/2023/03/skillometers-reflective-widgets-that.pdf_reco6nF5Pb4FQHd2x.pdf)).

That last point deserves emphasis: **the teaching intervention that provably changed behavior did not provably make people faster within the measurement window.** Anyone shipping a mastery nudge should expect a short-run cost.

**CommunityCommands (Li, Matejka, Grossman, Konstan, Fitzmaurice — TOCHI 2011).** Collaborative filtering applied to software commands, shipped as an AutoCAD plug-in.
- Baseline scale of the problem: AutoCAD command count grows roughly linearly per release (45 new commands in the 2011 release alone), and **90% of users use fewer than 90 commands** out of hundreds.
- Their item-based CF algorithm generated **2.1× as many "good" suggestions** as prior techniques (online survey with 36 heavy AutoCAD users, ≥20 hrs/week, ~10 weeks of logged command data each).
- Field deployment: **32 full-time professionals, 6 weeks**, in real work environments. Both contextual (short-term) and global (long-term) recommendation algorithms **significantly increased the number of unique commands issued**; users subjectively preferred *contextual* recommendations.
- Ratings used **cf-iuf** (command frequency × inverse user frequency) — i.e. weight a command by how much *you* use it against how rare it is community-wide, which is the recommender-systems answer to "what should this specific user learn next" ([TOCHI 2011 PDF](https://www.tovigrossman.com/papers/2011%20TOCHI%20cc.pdf)).

**Design read:** vocabulary extension is tractable with usage data and peer comparison, and the *contextual* variant beats the *global* one on user preference. This is the most directly portable finding in this entire document for a data-rich app.

### 2.4 Progressive disclosure — widely believed, thinly evidenced

Nielsen defines progressive disclosure as deferring advanced or rarely-used features to a secondary screen: show the most important options first, offer specialized ones on request; the goal is satisfying both the desire for power and the desire for simplicity. He distinguishes it from **staged disclosure** (wizard-style, linear, users usually traverse all steps) and warns staged disclosure breaks down when steps are interdependent. Two requirements are named: split features correctly (frequent up front, confusing deferred, primary display uncrowded) and make the progression mechanic obvious with labels that set expectations. Determining what belongs in the initial set requires task analysis, field studies, and usage analytics *supplemented by observation*.

Critically, **the NN/g article contains no controlled study or numbers** ([NN/g](https://www.nngroup.com/articles/progressive-disclosure/)). Several secondary sources circulate impressive-sounding figures (e.g. "30–50% faster initial task completion, 70–90% feature discoverability") attributed to "Nielsen 2006"; I could not trace those numbers to a primary source and they do not appear in the NN/g article. **Treat them as unsourced.**

Related, and better-evidenced on the negative side: NN/g's testing of mobile **instructional overlays / coach marks** found users don't recognize overlays as non-interactive and tap through them; chained tip sequences get skipped or fail to be memorized; and users dismiss hints faster when they arrive in chains. Their recommendation is one tip per interaction, delivered at the relevant moment in the workflow to enable learning-by-doing, visually distinct from the real UI, with ultra-short text ([NN/g](https://www.nngroup.com/articles/mobile-instructional-overlay/)).

Carroll's related **minimalist instruction** tradition argues for rapid achievement of realistic tasks from the start, short task-oriented chunks rather than monolithic documentation, and treating errors as teachable moments rather than designing to prevent all mistakes ([Wikipedia](https://en.wikipedia.org/wiki/Minimalism_(technical_communication))).

### 2.5 Superhuman: buying mastery with humans, then productizing it

Superhuman is the strongest commercial case study because the numbers are published.

**Concierge onboarding.** Mandatory human-led 1:1 onboarding for every new customer, initially 90 minutes (30 discovery + 60 onboarding), later compressed to 30. Modeled on Apple's Genius Bar and hotel concierge service.

**Explicit shortcut drilling.** The playbook taught `j`/`k` to navigate, `e` to mark done, `h` for reminders, emphasizing physical interaction over passive explanation — plus behavioral commitment devices: verbally committing to 30 days of daily use, creating a browser bookmark, pinning the extension, deleting competing mail apps from the device.

**Numbers:**
- ~2× activation vs self-serve; ~2× referral rate from manually onboarded users.
- ~$650k ARR per onboarding specialist (40 calls/week × 45 weeks × $30/mo).
- Self-serve activation rose 40% → 50% once they prioritized Inbox Zero as the target achievement.
- Feature opt-in rose 45% → ~80% when tucked-away tooltips were replaced with full-screen setup panels.
- "Get Me To Zero" hit 57% opt-in and archived ~1 billion emails.

**The three attributes of their scaled onboarding:** **opinionated** (drive toward one core achievement — Inbox Zero), **interruptive** (full-screen panels, not tooltips), **interactive** (a *synthetic inbox sandbox* for safe experimentation).

**The stated tradeoff:** "Humans can gracefully fill in for the lack of self-serve onboarding. But humans cannot fill in for critical missing features." They deliberately deferred self-serve investment until PMF, and got feedback loops "several orders of magnitude faster" than analytics alone ([First Round Review](https://review.firstround.com/superhuman-onboarding-playbook/)).

**The game-design layer.** Vohra frames Superhuman via genuine game design rather than gamification (no points/badges): design for *fun* and for how the product makes people feel; protect flow with sub-100ms response (they rewrote Chrome components to get it); amplify the emotional peak of reaching Inbox Zero with a reward image; and give ordinary users the keyboard-driven velocity that developers get in code editors, which is explicitly framed as mastery through responsive controls and muscle memory ([Acquired](https://www.acquired.fm/episodes/special-superhuman-part-ii-designing-software-to-feel-like-a-game-with-rahul-vohra)). This is a podcast conversation — treat as well-articulated practitioner philosophy, not evidence.

### 2.6 Command palettes: the expert accelerator that also teaches

Origin: popularized by Sublime Text 2, whose palette let users fuzzy-search obscure features buried in menus; `Ctrl/Cmd+Shift+P` became "the one shortcut to rule them all," and the pattern spread to VS Code, Figma, Notion, Linear, and macOS Spotlight ([Sublime docs](https://docs.sublimetext.io/guide/extensibility/command_palette.html), [Mobbin](https://mobbin.com/glossary/command-palette)).

Superhuman's published principles: one consistent shortcut everywhere (`Cmd+K`); centralize *everything* in one place because it simplifies the app's mental model; expose *every* action, not a curated subset; forgiving matching (fuzzy, case-insensitive, synonyms); and contextual relevance. Their stated teaching claim: users "instantly do any action — and also learn the shortcut for next time," turning discovery into muscle memory without dedicated memorization. Craft details: center the palette, monospaced type, per-command icons, deliberately clip the last row to imply more below, and show the matched alias alongside your preferred term to nudge users toward your vocabulary ([Superhuman](https://blog.superhuman.com/how-to-build-a-remarkable-command-palette/)).

Figma's equivalent (the actions menu / quick-actions search) does the same job: type a phrase to reach a feature or setting without traversing menus, and shortcuts are surfaced alongside ([Figma Help](https://help.figma.com/hc/en-us/articles/360040328653-Use-the-quick-actions-search-bar)).

**The counter-guidance matters.** Pattern documentation explicitly warns: don't add a command palette for products with small feature sets where visible navigation suffices; don't add hidden power-user behavior before the baseline visible path is solid; and don't assume one design serves novices and experts equally — a palette risks hiding critical functionality from beginners while accelerating experts. Accessibility requirements are non-trivial (full keyboard operation, focus management, screen-reader state announcements, 200% zoom, reduced motion) ([uxpatterns.dev](https://uxpatterns.dev/patterns/advanced/command-palette)).

### 2.7 Linear: opinionation as a depth strategy

The Linear Method states, among its principles: **"Purpose-built"** — productivity software needs to be designed for purpose, favoring opinionated defaults over flexible customization that becomes chaos at scale; **"Aim for clarity"** — don't invent terms; **"Say no to busy work"** — your tools shouldn't make you their designer and maintainer; and most directly on point, **"Simple first, then powerful"** — a tool should be simple to get started with and grow more powerful as you scale ([Linear Method](https://linear.app/method/introduction)).

Secondary commentary describes Linear's shortcut system as a core design philosophy rather than a feature: shortcuts are discoverable (hover any action to see its binding), learnable (mostly single letters), and composable, and Linear's audience already carries shortcut muscle memory from editors and terminals ([925 Studios](https://www.925studios.co/blog/linear-design-breakdown-saas-ui-2026)). That last point is an important scoping constraint: **Linear's approach works partly because its users arrived pre-trained.** That assumption does not hold for a consumer sports app.

---

## Part 3 — Transferable principles

Ranked by strength of supporting evidence.

1. **Vocabulary extension via personalized, contextual recommendation is the best-evidenced way to reveal depth.** Field-tested, significant increase in unique commands used, with contextual > global on user preference. Requires usage telemetry and a peer corpus ([TOCHI 2011](https://www.tovigrossman.com/papers/2011%20TOCHI%20cc.pdf)).
2. **Reflective self-comparison ("here's how you're doing it, here's the faster way") accelerates modality switching** — but budget for a short-run performance cost, and don't promise a speed win in week one ([Skillometers](https://www.research.autodesk.com/app/uploads/2023/03/skillometers-reflective-widgets-that.pdf_reco6nF5Pb4FQHd2x.pdf)).
3. **Just-in-time, one-thing-at-a-time beats front-loaded sequences.** Convergent across NN/g overlay testing, game tutorial practice, and Carroll's minimalism ([NN/g](https://www.nngroup.com/articles/mobile-instructional-overlay/), [GDevelop](https://gdevelop.io/blog/improve-game-tutorials), [Wikipedia](https://en.wikipedia.org/wiki/Minimalism_(technical_communication))).
4. **Design against the paradox of the active user, not for a rational learner.** Users will satisfice forever; nothing about your feature being better will, by itself, cause a switch ([NN/g](https://www.nngroup.com/articles/paradox-of-the-active-user/), [DUXU 2020](https://vbn.aau.dk/ws/portalfiles/portal/438685057/HCII2020_cameraready.pdf)).
5. **Feature requests are often discovery failures.** Instrument "asked for a thing that already exists" as a first-class signal ([Wikipedia: Ribbon](https://en.wikipedia.org/wiki/Ribbon_(computing))).
6. **Context-triggered surfaces (contextual tabs, contextual recommendations) reveal depth without permanent clutter** — appear on selection, disappear when irrelevant ([Jensen Harris](https://jensenharris.com/home/ribbon)).
7. **Isolate → complicate → twist → prove.** Two independent studios converged on it; adopt as a shape for teaching any multi-step feature ([Game Developer](https://www.gamedeveloper.com/design/the-secret-to-i-mario-i-level-design), [Game Informer](https://gameinformer.com/b/features/archive/2010/03/17/thinking-with-portals-making-a-test-chamber.aspx)).
8. **Provide a sandbox for consequential actions.** Superhuman's synthetic inbox; Portal's clean experimentation room. Cheap failure is a design requirement, not a nicety ([First Round](https://review.firstround.com/superhuman-onboarding-playbook/)).
9. **Command palettes accelerate experts and teach shortcuts simultaneously** — but only after a solid visible baseline exists, and only for products with enough surface area to justify them ([Superhuman](https://blog.superhuman.com/how-to-build-a-remarkable-command-palette/), [uxpatterns.dev](https://uxpatterns.dev/patterns/advanced/command-palette)).
10. **Pick one core achievement and be opinionated, interruptive, and interactive about it.** Superhuman's Inbox Zero is the model: a single named milestone moved self-serve activation 40% → 50%, and full-screen beats tooltips 45% → 80% on opt-in ([First Round](https://review.firstround.com/superhuman-onboarding-playbook/)).
11. **Watch real people for a long time.** Microsoft's most valuable method was longitudinal observation; Valve's was weekly silent playtesting. Both outrank analytics for finding teaching failures ([UX Week notes](https://www.jurecuhalev.com/blog/jensen-harris-the-story-of-the-ribbon-office-2007-uxweek08-notes/), [GMTK](https://gmtk.substack.com/p/valves-secret-weapon)).
12. **Restructuring for discoverability taxes your experts.** ~20% self-reported productivity loss and expertise-correlated dissatisfaction is the documented price of the Ribbon ([Wikipedia](https://en.wikipedia.org/wiki/Ribbon_(computing))).

**And one anti-principle:** competence-gated *locking* of features in a utility app has no published support. Games can lock because content is the reward; a tool that withholds capability reads as adversarial. Prefer *staged surfacing* (not shown yet, always reachable) over *gating* (blocked until you qualify).

---

## Evidence quality notes

| Claim | Type | Confidence |
|---|---|---|
| Skillometers hotkey adoption 28%→50%, 42%→80% by rep 10 | Peer-reviewed controlled lab experiment, n=24, UIST 2013 | High for effect direction; low external validity (15-min lab task, students, Keynote) |
| Skillometers produced **no** significant task-time gain | Same study, reported as a rejected hypothesis | High — and notable because it's a negative result the authors published |
| CommunityCommands: 2.1× good recommendations; unique commands significantly increased | Peer-reviewed, TOCHI 2011; 36-user survey + 32-user 6-week field study | High for the domain (CAD professionals); unknown transfer to consumer mobile |
| "90% of AutoCAD users use fewer than 90 commands" | Vendor telemetry reported in a peer-reviewed paper | High for AutoCAD; illustrative only elsewhere |
| Keyboard shortcuts underused even by experts; performance dip; satisficing | Peer-reviewed literature review within a 2020 DUXU paper; the paper's own user evaluation is small-n qualitative (reaction cards + interviews) | High for the literature claims, low for the intervention's efficacy |
| Office telemetry scale (3B sessions, 150M clicks/mo, 6,000 data points) | Third-party conference notes of a Jensen Harris talk | Medium — plausible and consistent across accounts, but transcribed secondhand |
| "People weren't finding the very features they asked us to add" | Wikipedia, sourced to Microsoft accounts | Medium-high; widely repeated and consistent with Harris's own writing |
| Ribbon caused ~20% self-reported productivity loss for power users | Wikipedia summarizing an ExcelUser survey | Low-medium — self-reported, self-selected respondents, hostile-sampling risk |
| Superhuman metrics (2× activation, 2× referral, 40→50%, 45→80%, $650k/specialist) | Company-supplied figures in a First Round Review case study | Medium — internally consistent and specific, but unaudited vendor marketing-adjacent |
| Vohra's game-design framework | Podcast interview; practitioner philosophy | Low as evidence, high as articulation |
| Mario 1-1 design intent; Goomba-replaced-Koopa | Named-designer interviews (Eurogamer 2015) via secondary summaries | Medium-high for intent; zero measured learning data |
| Kishōtenketsu four-beat structure | Named designer (Hayashida) describing his own method | Medium-high for intent; the "everyone does this" generalization is lore |
| Valve checklisting / lateral thinking; playtest scale | Studio-sourced feature article + a well-researched secondary essay | Medium-high |
| Great Plateau as best-in-class tutorial | Critical consensus | Low as evidence; useful as a structural template |
| Social-game tutorial data (>90% past step 2; 3-min standard) | Practitioner analysis citing MixPanel; six-game sample, ~2010-era Facebook games | Low-medium — small sample, dated platform, no methodology published |
| Progressive disclosure "30–50% faster / 70–90% discoverability" | **Uncited figure circulating in SEO content**, attributed to Nielsen 2006 but absent from the NN/g article | **Do not use.** Could not trace to a primary source |
| NN/g coach-mark findings | Qualitative usability testing, specific app examples named | Medium — real observation, no effect sizes |
| Competence-gated unlocks improve learning/retention | **No published evidence found** | Lore |

**Access failures worth noting for follow-up:** the Valve Developer Community's own "Portal Design And Detail" tutorial returned HTTP 403; the ACM DL page for KeyMap (CHI 2020) returned 403; Springer's page for the DUXU 2020 chapter is paywalled (the AAU accepted manuscript was used instead). The WebSearch budget for this session was exhausted mid-research, so the following threads are **unexplored and should be picked up in a round 2**: Asher Vollmer's GDC talk on tutorials; Marc BG's GDC talk on teaching complex games (his site 404'd); Findlater & McGrenere's controlled comparison of static vs adaptive vs adaptable menus (an important negative result for adaptive UI — a static split menu was significantly *faster* than an adaptive one, and users preferred adaptable to adaptive — I encountered the thesis text but could not verify a citable canonical URL, so it is deliberately excluded from the sources list); Adobe's Discover panel and contextual task bar (helpx.adobe.com timed out); Excel's "Tell me" search box; and any published evidence on milestone-celebration mechanics in productivity software.

---

## Implications for FTF — hypotheses only

These are hypotheses to test, not proposals to build.

**H1 — Feature requests in the in-app feedback loop are partly a discovery telemetry stream.** The Ribbon's central finding was that most-requested features already existed. FTF has an in-app feedback loop and nine notification types; a cheap first study is to classify existing feedback items into *missing* vs *exists-but-not-found*. If the second bucket is non-trivial, the depth problem is surfacing, not building.

**H2 — Contextual, personalized "next capability" recommendations will outperform any static tour.** CommunityCommands' contextual variant beat the global one on user preference and significantly increased unique commands issued. FTF already logs user events and has a natural peer corpus (users with similar roster shape, league type, or contention window). The testable version: a single, contextual, dismissible suggestion surfaced at a moment of relevance — e.g. surfacing want/accept boards only after a user has manually rejected several generated trades — measured on adoption of the suggested capability, not on session length.

**H3 — A "skillometer"-shaped reflective surface may raise adoption of the deeper features but will not show a short-run efficiency win.** If FTF ever shows users their own behavior mix ("you've evaluated 40 trades manually; users who set want/accept boards evaluate 3× fewer"), the Skillometers result predicts adoption moves and *task time does not*, at least initially. Any success metric tied to time-to-trade in the first weeks would falsely kill the feature.

**H4 — The first two steps are where the cliff is, and everything after step two is comparatively safe.** The >90%-past-step-2 finding from social games is weak evidence, but it's cheap to check against FTF's own funnel. If FTF's drop-off is similarly front-loaded, effort belongs almost entirely in the first 60 seconds after Sleeper sign-in rather than in mid-funnel tours.

**H5 — Trade evaluation is FTF's "twist" beat, and it may be under-taught.** The convergent games structure is isolate → complicate → twist → prove. FTF's primitives (Elo rankings from 3-player votes, tiers, generated trades, manual calculator, want/accept boards) are individually explicable; the competence that actually matters is *judging whether a proposed trade fits your roster and window*. Hypothesis: users who never form that judgment churn regardless of how many features they've been shown. That suggests teaching investment should concentrate on one "prove it" moment rather than on breadth of feature exposure.

**H6 — A single named core achievement would outperform feature-breadth onboarding.** Superhuman's Inbox Zero is the model; the analogous FTF candidate is something like "sent your first trade in-platform" or "your first accepted trade." Their data point is 40% → 50% self-serve activation from choosing the milestone, and 45% → 80% opt-in from making the ask full-screen rather than a tooltip. Both are testable framings, and the second predicts FTF's tooltips underperform interruptive panels.

**H7 — A sandbox lowers the cost of failure for consequential actions.** Send-trade-in-platform (Sleeper/MFL/ESPN) is irreversible-feeling and socially consequential. Superhuman's synthetic inbox is the precedent. A "practice league" or dry-run mode is the analogue; the hypothesis is that it raises first-send rate rather than cannibalizing it.

**H8 — Staged surfacing, not gating.** No published evidence supports locking features behind demonstrated competence in a utility app, and games' justification for it (content *is* the reward) doesn't hold for FTF. Prefer "not surfaced yet, always reachable via search" over "locked until you qualify."

**H9 — A command palette is probably premature on mobile and possibly right on web.** The pattern's own guidance says don't add a hidden expert layer before the visible baseline is solid, and don't assume it serves novices and experts equally. FTF's mobile users are unlikely to arrive pre-trained the way Linear's do. The narrower, better-supported version is a *search-everything* entry point on web that surfaces capabilities by name, which is the discoverability half of the pattern without the keyboard-mastery half.

**H10 — Any restructuring for discoverability will make FTF's most engaged users slower and unhappier first.** The Ribbon's ~20% self-reported productivity loss, concentrated among experts, is the warning. Plan for a vocal negative reaction from the most active testers and decide in advance whether that signal will be treated as a defect or as expected transition cost.

---

## Sources

**Games**
- Wikipedia — World 1-1: https://en.wikipedia.org/wiki/World_1-1
- Adafruit (summarizing the 2015 Eurogamer Miyamoto/Tezuka interview) — Miyamoto explains how World 1-1 was created: https://blog.adafruit.com/2025/09/14/miyamoto-explains-how-super-mario-bros-world-1-1-was-created/
- Game Developer — The secret to Mario level design (Hayashida, kishōtenketsu): https://www.gamedeveloper.com/design/the-secret-to-i-mario-i-level-design
- MCV/Develop — Nintendo's level design secrets in four steps: https://mcvuk.com/business-news/publishing/video-nintendos-level-design-secrets-in-four-steps/
- Game Informer — Thinking With Portals: Making a Portal 2 Test Chamber: https://gameinformer.com/b/features/archive/2010/03/17/thinking-with-portals-making-a-test-chamber.aspx
- Mark Brown (GMTK) — Valve's "Secret Weapon" (playtesting): https://gmtk.substack.com/p/valves-secret-weapon
- Valve Developer Community — Portal Design And Detail (returned HTTP 403 during this research; listed for follow-up): https://developer.valvesoftware.com/wiki/Portal_Design_And_Detail
- Wikipedia — Great Plateau (Breath of the Wild): https://en.wikipedia.org/wiki/Great_Plateau
- Game Developer — First Five Minutes: How Tutorials Make or Break Your Social Game: https://www.gamedeveloper.com/design/first-five-minutes-how-tutorials-make-or-break-your-social-game
- GDevelop — Why Game Tutorials Fail: Creating Effective Player Onboarding: https://gdevelop.io/blog/improve-game-tutorials

**Pro tools — practice**
- Jensen Harris — Designing the Ribbon: https://jensenharris.com/home/ribbon
- Jensen Harris — Designing Microsoft Office (index): https://jensenharris.com/home/office
- Jure Cuhalev — notes from Jensen Harris, "The Story of the Ribbon," UX Week 2008: https://www.jurecuhalev.com/blog/jensen-harris-the-story-of-the-ribbon-office-2007-uxweek08-notes/
- Wikipedia — Ribbon (computing): https://en.wikipedia.org/wiki/Ribbon_(computing)
- First Round Review — Superhuman's Onboarding Playbook: https://review.firstround.com/superhuman-onboarding-playbook/
- First Round Review — How Superhuman Built an Engine to Find Product-Market Fit: https://review.firstround.com/how-superhuman-built-an-engine-to-find-product-market-fit/
- Acquired — Superhuman Part II: Designing Software to Feel Like a Game (Rahul Vohra): https://www.acquired.fm/episodes/special-superhuman-part-ii-designing-software-to-feel-like-a-game-with-rahul-vohra
- Lenny's Newsletter — Superhuman's secret to success (Rahul Vohra): https://www.lennysnewsletter.com/p/superhumans-secret-to-success-rahul-vohra
- Superhuman Blog — How to build a remarkable command palette: https://blog.superhuman.com/how-to-build-a-remarkable-command-palette/
- Linear — The Linear Method (introduction / principles): https://linear.app/method/introduction
- 925 Studios — Linear design breakdown (secondary commentary on keyboard-first design): https://www.925studios.co/blog/linear-design-breakdown-saas-ui-2026
- Figma Help Center — Use the quick actions / actions menu: https://help.figma.com/hc/en-us/articles/360040328653-Use-the-quick-actions-search-bar
- Sublime Text community docs — Command Palette: https://docs.sublimetext.io/guide/extensibility/command_palette.html
- Mobbin — Command Palette UI design glossary: https://mobbin.com/glossary/command-palette
- UX Patterns for Developers — Command Palette (including when *not* to use): https://uxpatterns.dev/patterns/advanced/command-palette

**Pro tools — research**
- Malacria, Scarr, Cockburn, Gutwin, Grossman — Skillometers: Reflective Widgets that Motivate and Help Users to Improve Performance (UIST 2013): https://www.research.autodesk.com/app/uploads/2023/03/skillometers-reflective-widgets-that.pdf_reco6nF5Pb4FQHd2x.pdf (landing page: https://www.research.autodesk.com/publications/skillometers-reflective-widgets-that-motivate-and-help-users-to-improve-performance/)
- Li, Matejka, Grossman, Konstan, Fitzmaurice — Design and Evaluation of a Command Recommendation System for Software Applications (ACM TOCHI 18(2), 2011): https://www.tovigrossman.com/papers/2011%20TOCHI%20cc.pdf
- Autodesk Research — Deploying CommunityCommands: A Software Command Recommender System Case Study: https://www.research.autodesk.com/publications/deploying-communitycommands-a-software-command-recommender-system-case-study/
- Raursø, Persson, Garðarsson, Mazáň, Andreasen, Avotiņa, Ventegodt, Triantafyllou — Intermodal Improvement: Nudging Users to Use Keyboard Shortcuts (DUXU/HCII 2020), accepted manuscript: https://vbn.aau.dk/ws/portalfiles/portal/438685057/HCII2020_cameraready.pdf
- Carroll & Rosson — Paradox of the Active User (original chapter PDF): https://research.cs.vt.edu/ns/cs5724papers/4.mental.mental.carroll.paradox.pdf
- Nielsen Norman Group — Paradox of the Active User: https://www.nngroup.com/articles/paradox-of-the-active-user/
- Nielsen Norman Group — Progressive Disclosure: https://www.nngroup.com/articles/progressive-disclosure/
- Nielsen Norman Group — Instructional Overlays and Coach Marks for Mobile Apps: https://www.nngroup.com/articles/mobile-instructional-overlay/
- Wikipedia — Minimalism (technical communication), on Carroll's minimalist instruction: https://en.wikipedia.org/wiki/Minimalism_(technical_communication)
</content>
</invoke>
