# Open-access onboarding — removing the ranking lock, and a platform-choice front door

> **Role:** pm-growth. **Date:** 2026-08-14.
> **Verified against:** `origin/main` @ `4a4b671`.
> **Origin:** operator direction — *"remove the ranking feature as a lock to access the rest
> of the app… too much friction up front… let users naturally start using the features, they
> will appreciate the value of ranking players after they start using the other features…
> initial onboarding options of just Sleeper and Apple should change to include MFL and ESPN."*
> **This document changes no source file.** Specs and recommendations only.
> **v1.1 (same day, operator-directed):** Phase B redesigned. The lock machinery is
> **retained**, but what it locks inverts: not access to trades — **the right to call the
> board yours**. And grading trades (deck swipes, match decisions, sends) becomes a
> first-class unlock pathway that builds your rankings as a side effect of using the product.
> **v1.2 (2026-08-15, ratified):** operator approved **O-1 through O-9, all as recommended**
> (§10 is now the decision record, not an open list). The plan is executable: Phase A
> proceeds now, Phase B ships with the basis-lock design and coordinates the counterparty-basis
> clause into P1-9's build, Phase C follows the notification batch.

## Contents

- [1. The headline: most of this plan already exists, and it is built](#1-the-headline-most-of-this-plan-already-exists-and-it-is-built)
- [2. Evidence — what the lock actually is](#2-evidence--what-the-lock-actually-is)
- [3. Prior art inventory](#3-prior-art-inventory)
- [4. Pressure test](#4-pressure-test)
- [5. The plan](#5-the-plan)
- [6. Guided onboarding changes](#6-guided-onboarding-changes)
- [7. Platform-choice front door (ESPN / MFL first-class)](#7-platform-choice-front-door-espn--mfl-first-class)
- [8. Measurement](#8-measurement)
- [9. Risks](#9-risks)
- [10. Decisions needed](#10-decisions-needed)
- [11. Handoffs](#11-handoffs)

---

## 1. The headline: most of this plan already exists, and it is built

The operator's instinct — see the product first, rank when you understand why — **is the
onboarding-conversion plan v2.1** (`docs/plans/onboarding-conversion/plan.md`, 2026-07-17),
which survived a 3-round adversarial ux-design × pm-growth review and was then **built**:
trades-first hook screen, contextual Quick Set prompt, save-moment Apple ask, username-first
landing, guided layer. It is all dark behind flags today:

| Flag | State | What it does when on |
|---|---|---|
| `onboarding.trades_first` | **false** | New user lands on a consensus-priced trade deck at first launch — pregen at auth-return, skeleton deck, provenance chip ("CONSENSUS VALUES" → "YOUR BOARD"), first-run chrome collapse |
| `onboarding.quickset_prompt` | **false** | The ranking ask becomes an inline swipeable card *after 2–3 swipes* — "These trades use consensus values. Fix them in 2 minutes →" — returning to a visibly regenerated deck |
| `onboarding.landing` | **false** | Username-first landing; Apple demoted to a quiet re-entry link |
| `onboarding.league_autoskip` | **false** | One league → skip the picker |
| `onboarding.apple_save_moment` | **false** | Apple prompt moves to first like / first Quick Set save |
| `onboarding.v2` | true | Master switch (feature live iff master AND own flag) |

The 2026-08-09 mobile UX audit reached the same conclusion independently (**P0-9**, "a new
user's first act is a 32-tap chore, before seeing anything of value"), noted *"the trades-first
alternative is built and disabled,"* and its resolution says plainly: *"If you'd rather not
wait: ship trades-first. The argument that a user should see the product before doing data
entry is strong enough to act on, and the flag makes reverting cheap."*

**So the operator, the v2 review panel, and the audit have now reached the same conclusion
three separate times across a month.** What this document adds is the part none of them
covered:

1. **The lock itself.** v2 re-sequences *when* ranking is asked; it does not remove the
   unlock concept. The operator's ask goes further — §5 Phase B specs the gate becoming a
   grade.
2. **The front door.** No prior plan makes ESPN/MFL first-class at sign-in. That is genuinely
   new work with a real identity problem under it — §7.
3. **The decision to ship as default rather than experiment.** v2 was designed as an A/B
   (`onboarding_v2_rollout`, device-allowlist, operator-only since 2026-07-19) that a 3–5
   user population can never power. §4 argues the experiment framing is now the obstacle.

---

## 2. Evidence — what the lock actually is

Verified at `4a4b671`. The "ranking lock" is four distinct mechanisms, and they differ in how
locked they actually are:

| # | Mechanism | Where | What it blocks |
|---|---|---|---|
| L1 | **Default landing on the Rank tab.** `initialTab = 'Rank'` unless `onboarding.trades_first` is on and no first swipe yet (`TabNav.tsx:557-561`) | client routing | Nothing structurally — but every new user's first screen is data entry (Quick Set at QB, tier 1 of 8; the audit's structural minimum: 32 save/continue taps to finish all four positions) |
| L2 | **The unlock threshold.** `GET /api/rankings/progress` → `unlocked` when all 4 positions ≥ threshold (10 each, 40 total; anchor/manual lanes have their own evidence bar per D-P1-10 / P1-7) (`server.py:6228-6260`) | backend + client | The **Find-a-Trade / mutual-matching lane** and its UI affordances; the `rank.unlocked-banner`; `league_member_unlocked_trades` push fires off it |
| L3 | **Per-format re-lock.** A league resolving to a format not in `unlocked_formats` re-gates even a ranked user (`TradesScreen.tsx:983-1019`) | client | Trades content for the un-ranked format |
| L4 | **League-facing unlock states.** `load_league_member_unlock_states` renders leaguemates as Unlocked / in-progress (`LeagueScreen.tsx:972-975`); invite social proof and match-density messaging key off it | cross-user display | Nothing for the user — but it is the league's density signal |

**The critical engineering fact: the deck does not need the lock.** The trade engine runs on
the consensus-seeded board with zero ranking effort (v2 plan §Problem, confirmed by the
existence of the trades-first flag itself — it lands users on a working deck pre-ranking).
The lock is not protecting users from a broken product. What it actually protects is
**counterparty signal quality** (§4, T2) — a real thing, but a different thing, and not one
a wall is the right tool for.

---

## 3. Prior art inventory

Answering the operator's literal question — *is there a prior plan for this?*

| Artifact | Date | Covers | Status |
|---|---|---|---|
| `docs/plans/onboarding-conversion/plan.md` v2.1 | 2026-07-17 | Trades-first sequencing, contextual ranking ask, Apple at save moment, username-first landing, guided layer, demo path | **Built, dark.** 12-item build list executed; flags off |
| `docs/business/analytics/2026-07-18-onboarding-v2-rollout-experiment.md` | 2026-07-18 | The A/B design: activation_rate = first swipe in session 1, treatment = the v2 flow | Live for operator's device only via `config/tester_allowlist.json` |
| UX audit P0-9 + resolution (`04-priority-backlog.md:140`, `06-resolutions.md:87`) | 2026-08-09 | The same friction finding, independent; explicitly invites this pressure test | Resolution on record: ship it if not waiting for the A/B |
| P0-8 tour fix (audit) + P0 remediation | 2026-08-11 | The guided tour's false-completion bug (told users the tour was over before it began) | Merged (P0 batch, `716c2b7`) |
| D-P1-10 + P1-7 | 2026-08-11 | *Every ranking method must unlock* — anchor + manual lanes fixed | Merged. Gate-integrity work, not gate-removal — §5 Phase B repurposes it |
| **Nothing** | — | Removing the unlock as a concept; ESPN/MFL as first-class sign-in | **This document** |

---

## 4. Pressure test

The direction is aligned with three prior artifacts, so agreement is cheap. The honest test
is where the shift *breaks*. Six tensions, two of which are real.

**T1 — "Consensus-vs-consensus trades are value-neutral shuffles."** The v2 panel's own
phrase. An unranked user's deck prices both sides off the same consensus list, so pure-value
edges barely exist. *Held, and already mitigated:* the built flow leads with **fit-led
narratives** (`trade.need_fit`) — positional need is personal before any ranking is — and the
provenance chip makes the limitation legible instead of silent. The deck-quality eval gate
(v2 item 2: insult rate <3% on scripted real leagues) exists precisely so this is measured,
not assumed. **Verdict: manageable, with the eval gate kept.**

**T2 — The lock protects leaguemates' signal quality. This is the strongest counterargument
and it deserves a real answer.** A "like" from a user with a real board is revealed
preference; a like from a day-one consensus user is weaker evidence. Two live systems consume
likes as intent: mutual matching, and **P1-9's `trade_found` push, whose entire gate is
"another human's revealed intent."** Open the floodgates and the intent currency inflates.
*Answer:* this argues for **grading signal, not walling users**. A like carries its author's
board strength (L2's machinery, repurposed); the `trade_found` gate adds one clause — the
counterparty's board meets the strength bar the unlock used to enforce. Matching can weight
matches by board strength without hiding them. The wall's *function* survives; the wall goes.
**Verdict: real, solvable, and the solution is specced in Phase B. Do not ship Phase B
without it.**

**T3 — Removing the lock removes the only goal structure.** The audit found streaks reward
nothing (P1-6); the unlock is the one earned milestone in the product. *Held partially:* the
unlock-as-wall becomes unlock-as-grade (Board Strength), which is a *better* goal because it
never blocks and never completes — and the parked Year-in-Review's "your calls" stat is the
honest long-run payoff for ranking (you can only be graded on calls you made). **Verdict:
net improvement if the grade ships with the removal, regression if the wall just disappears.**

**T4 — "Users will never rank if they don't have to."** The fear behind any gate removal.
*Tested against the design:* the built flow's entire architecture is a rebuttal — the
contextual prompt fires *after* the user has seen consensus trades (when the "fix these
values" pitch means something), the diff banner makes ranking visibly change the deck, and
the deck-exhausted state funnels into trios. The v2 panel's position, ratified twice: the
hook is itself a ranking input (swipes feed Elo at K=8/4). And empirically the wall converts
poorly anyway — the audit's structural-minimum arithmetic *is* the drop-off argument.
**Verdict: the risk is real but the mitigation is the feature being shipped. Measure
`rank_method_selected` post-flip; if organic ranking craters, the prompt cadence is the lever,
not the wall.** *(v1.1 makes this tension nearly moot: under B-2, using the product IS
ranking — a user who never opens the Rank tab still builds a board by grading trades. The
question shifts from "will they rank?" to "does graded signal converge on a board worth
claiming?" — which is exactly what B-3's coverage rule and O-9's tuning answer.)*

**T5 — The A/B can never run.** The experiment needs powered samples; the user base is 3–5.
Holding the built flow dark awaiting an unpowered experiment is a decision to never ship it.
The audit's resolution already conceded this ("run it as a directional read"). The operator
has now made the product call directly. **Verdict: retire the experiment framing. Ship as
default with the flags as revert levers; keep the pre/post seam honest (§8).**

**T6 — ESPN/MFL-first entry adds friction, not removes it.** Sleeper entry is username-only
(public API, no password). ESPN entry is a WebView credential capture; MFL is a login. Making
platform choice the first screen risks taxing the 90%-case (Sleeper) to serve the 10%.
**Verdict: real. §7's design keeps Sleeper's one-field fast path visually primary; ESPN/MFL
are peers in *availability*, not in *prominence*. This is a layout constraint, recorded as a
requirement.**

**Net: the shift survives the pressure test.** Two conditions attach: T2's signal-grading
ships *with* the lock removal (not after), and T5's measurement seam is recorded so the
before/after read is honest.

---

## 4b. Positioning — the inversion is the value prop (v1.1, operator-articulated)

The operator's framing, recorded because it should drive the launch narrative, not just the
mechanics:

> *Every other app uses user inputs to build consensus rankings. We're giving that value
> back to the user by helping them build their own rankings.*

**The industry structure makes this literal.** KeepTradeCut's entire model is crowdsourced
valuation labor: users answer "who would you rather have?" comparisons — often as the *toll
for accessing the data* — and the output is KTC's consensus list, KTC's asset, identical for
every user who helped build it. FantasyCalc derives values from league transaction data;
DynastyProcess aggregates market signals. In every case the user's judgment is **raw
material** for a communal average that erases the individual who supplied it.

The grading pathway takes the *same interaction* — a valuation judgment on a player
comparison — and points the output at the user: **your grades build your board, and your
board prices your trades.** The labor is identical to what KTC asks; the asset lands on the
opposite side of the table.

**One line, several cuts** (raw material for mkt-brand, not final copy):

- *"Other apps turn your opinions into their rankings. We turn them into yours."*
- *"Stop donating your takes to a consensus. Build a board that argues for you."*
- *"Every grade you give makes your trade finder smarter — yours, not everyone's."*

**The honesty guardrail that keeps the claim clean:** FTF's consensus seed comes from
external market data (DynastyProcess CSV), not from harvesting its own users — and a user's
board is shared only with their own league (`member_rankings`, league-scoped), never
aggregated into an FTF consensus product. **That must stay true for the positioning to stay
true.** If FTF ever builds a cross-user consensus from boards, this claim dies in the same
release — record it as a standing constraint, ADR-worthy if ever challenged.

**Why this positioning needed Phase B to exist:** under the old lock, ranking was a *toll*
FTF charged before showing value — structurally identical to KTC's quiz-gate, the exact
thing the claim differentiates against. Open access + the grading pathway is what makes the
sentence true. Positioning and mechanics ship as one thing.

---

## 5. The plan

Three phases. A is a flag flip of built code; B is the genuinely new unlock work; C is §7.

### Phase A — ship the built flow as the default (days, not weeks)

> **STATUS 2026-08-15 — BUILT, PENDING GATES.** Items 1 and 2 are implemented on branch
> **`feat/open-access-phase-a`** (draft PR — see the recovery/ship ledger for the URL).
> **Item 1 (flips): done.** The six flags are `true` in `config/features.json`
> (`onboarding.trades_first`, `quickset_prompt`, `landing`, `league_autoskip`,
> `apple_save_moment`, + `landing.try_before_sync`). No other `onboarding.*` flag moved —
> `share_sheet`, `rank_routing`, `demo_bridge`, `guided_layer`, `keep_warm` stay dark
> (§5 does not name them; see the §6 note below).
> **Item 2 (retire the overlay): documented, not executed.** The experiment lives in the
> prod DB, so retirement is a runtime admin action, not a code change. The exact
> copy-pasteable procedure — plus the analysis of what a *stale running* overlay does once
> the flags are globally true — is now `docs/runbook.md` § "Retiring the onboarding
> experiment overlay". Headline finding: `onboarding_v2_rollout` v1 is a **value-level
> no-op** post-flip (true-over-true for the one allowlisted device; everyone else excluded
> by targeting), but it is **not inert** — it keeps writing assignments, stamping funnel
> events and emitting `experiment_exposed`, which corrupts §8's pre/post seam; and the
> client merge (`mobile/src/api/flags.ts:56-60`) is an unconditional overwrite, so any
> future revise giving *control* a flags block could silently un-ship Phase A.
> `config/tester_allowlist.json` is deliberately **left intact** — it is shared with
> `aggregate_tier_labels`, `trades_home_inline` and the `/api/test-users` gate.
> **Items 3 and 4 remain open** and gate the merge: the deck-quality eval + S-43 render
> check are running separately, and the operator TestFlight pass has not happened.
> **§6 delta audit: zero code changes are Phase A scope.** Coach marks 1–4 need none; the
> "unlock"-vocabulary sweep is explicitly conditioned on Phase B; the voice pass and the
> platform-specific first-run are Phase B/C. Only `s5.1` (item 3's S-43 check) is a Phase A
> obligation, and it is a verification, not an edit.

1. **Flip, in one release:** `onboarding.trades_first`, `onboarding.quickset_prompt`,
   `onboarding.landing`, `onboarding.league_autoskip`, `onboarding.apple_save_moment`
   (+ `landing.try_before_sync`, the documented launch pairing for `onboarding.landing` —
   the demo endpoint 404s without it, `config/features.json:71`).
2. **Retire the `onboarding_v2_rollout` allowlist** — the flow stops being an experiment
   overlay and becomes the product. The flags stay as revert levers (they gate client
   behavior, not server routes — a clean lever by D-P1-07's own distinction).
3. **Pre-flip gates, both cheap, both already specced:** (a) the v2 deck-quality eval
   (item 2) runs against current production data — the funnel must not showcase a deck that
   insults strangers; (b) the audit's S-43 check — prove the `s5.1` payoff beat actually
   renders, since it carries the whole trades-first argument and has never rendered in this
   repo's evidence.
4. **Operator TestFlight pass** on the full first-run (D-P1-08 posture: TestFlight is
   primary QA).

### Phase B — the lock survives; what it locks inverts (v1.1, operator-directed)

**The lock machinery is kept in full.** The threshold math, `GET /api/rankings/progress`,
the per-method evidence bars D-P1-10/P1-7 just made coherent, the celebration banner, the
league-facing states, the `league_member_unlocked_trades` push — all of it stays. What
changes is the *object* of the lock:

> **Today the lock gates access to trades. After Phase B it gates the right to call the
> board yours.** Everything is usable from minute one, priced honestly on consensus. The
> unlock moment is the product saying: *we now have enough evidence of your actual
> valuations that these are YOUR values, not the market's.*

#### B-1 · What the milestone gates (and what it never gates again)

An engineering honesty note first: the "basis" is a continuum, not a switch. The user's
board is consensus-seeded and drifts from the first signal (`record_trade_signal`,
`server.py:10251`). The lock is therefore a **trust milestone** — the evidence bar at which
the product changes what it claims — and it gates three real things:

| Gated by the milestone | Why it must stay gated |
|---|---|
| **The label.** Provenance chip flips "CONSENSUS VALUES" → "YOUR BOARD"; values across deck, calculator, league surfaces are branded as the user's | Claiming a board on five swipes of evidence would be false. The chip is already built for exactly this seam |
| **League participation of the board.** `member_rankings` publish — the table leaguemates' divergence matching and mutual-gain discovery read | **This is the wall's one legitimate function, retained where it matters** (T2). An unearned board never prices anyone else's trades. Pre-milestone likes still work — they are graded as consensus-basis signal |
| **Your-board features.** Divergence displays ("where you differ from the market"), Board Strength shown to leaguemates, the future recap's "your calls" | These are incoherent without evidence — you cannot diverge from consensus until you exist |
| **Never gated again** | The deck, Find-a-Trade, matches, the calculator, sends, every tab (L1/L2/L3 as access gates all die) |

#### B-2 · The new unlock pathway: grading trades builds your board

The operator's directive, and the elegant part: **the evidence that unlocks your board is
generated by using the product.** Every trade interaction is an implicit valuation
statement, and the plumbing already exists — `swipe_trade` feeds
`record_trade_signal(winner_ids=receive, loser_ids=give)` today. What is new is a
**weighted evidence ladder** and counting it toward the bar:

| Signal | Statement it makes | Strength | Exists? |
|---|---|---|---|
| Deck **pass** | Weak/ambiguous (don't want ≠ don't value) | low K (as today) | ✓ wired to Elo |
| Deck **like** | receive > give, package level | moderate | ✓ wired to Elo |
| **Bad-trade flag** | The *pricing* is wrong — a calibration signal, not a preference | moderate, inverse | ✓ event exists; not yet an Elo input |
| **Match accept / decline** | Considered judgment on a concrete package | strong | ✓ `trade_decisions`; verify Elo wiring |
| **Sent trade** (any platform) | Strongest revealed preference in the product | strongest | ✓ `sleeper_send_succeeded` / `trade_sent`; not yet an Elo input |
| **Explicit grade** (optional, O-8) | A deliberate "I win / fair / I lose" on a card | strong, per-side | ✗ new affordance |

Grading joins the D-P1-10 ladder as a **sixth method lane** — and D-P1-10's own rule binds
it: *every ranking method must unlock, and its evidence rule must be designed, not assumed.*
The deliberate methods (Quick Set, trios, anchors…) remain the fast lane — a 2-minute Quick
Set detour still unlocks faster than grading ever will, and the contextual prompt card still
offers it. Grading is the **passive lane**: rank nothing, use the app, and your board
assembles behind you.

#### B-3 · The grading lane's evidence rule (the design problem, named)

Trade signal is **package-level and coverage-biased** — it concentrates on tradeable,
interesting players and can leave a position untouched forever. A grading lane that unlocks
on raw count would brand a board "yours" with an empty TE column. The rule that handles it,
following P1-7's `anchor_count`/`anchor_required` precedent exactly:

- **Per-position graded-appearance counts.** Each graded trade credits every player's
  position with an appearance; the lane's bar is per-position thresholds on those counts —
  the same shape as the trio lane's `{QB, RB, WR, TE} ≥ threshold`, so
  `/api/rankings/progress` gains `grade_count` / `grade_required` fields and **no new
  machinery**.
- **Uncovered positions route to the fast lane.** When grading has covered three positions
  and starved one, the prompt card gets specific: *"Your TE board is thin — 2 minutes to
  set it."* The two lanes compose; the bar is one bar.
- **Exact thresholds and weights are tuning, not architecture** — eng-backend proposes,
  an-data-architect instruments, the operator ratifies (O-9). The architecture is: one
  evidence bar, six lanes in, per-position coverage enforced.

#### B-4 · What each existing surface becomes

| Today | Phase B |
|---|---|
| Find-a-Trade lane blocked until `unlocked` | **Never blocked.** Consensus-priced from minute one, chip says so |
| `rank.unlocked-banner` celebrates the wall falling | Celebrates the **basis flip** — "This is your board now" — the single best celebration beat the product will ever have, and it fires on a real achievement |
| L3 re-locks a second format | Second format opens on consensus; its *own* basis milestone applies per format (the machinery is already per-format) |
| Leaguemates shown Unlocked / in-progress (L4) | Shown **on their own board / on consensus** — the density signal keeps meaning, because the milestone still marks real counterparty quality |
| `league_member_unlocked_trades` push | Fires on the basis flip — same threshold crossing, same dedup key, copy shifts to "@user built their board — your trades just got sharper" |
| Likes are likes | **Likes carry the author's basis.** Mutual matching weights on-board likes above consensus likes; **P1-9's `trade_found` gate adds the counterparty-basis clause** (one predicate at build time — coordinate with the eng partner now, migration later) |
| Provenance chip: static until Quick Set | **The progress affordance**: "Consensus values · 9 grades to your board" — the unlock is always visible, never in the way |

**Build shape:** B-1 and B-4 are relabeling plus one un-gating; B-2's new Elo inputs
(flag, accept/decline, send) are additive writes into an existing engine; B-3 is one lane
added to a route that gained a lane three days ago (P1-7). The genuinely new surface is the
optional explicit-grade affordance (O-8), which can trail everything else.

### Phase C — platform-choice front door (§7)

Sequenced last because it has the only unresolved design problem (identity), and Phases A/B
are valuable without it.

---

## 6. Guided onboarding changes

The guided layer (v2.1) was **designed for trades-first** — its beats assume the deck is the
first surface — so Phase A is what makes the existing script *correct*, not what breaks it.
Verified deltas:

| Piece | Change |
|---|---|
| **Coach marks 1–2** (swipe hint, provenance chip) | None — they were built for the deck-first flow Phase A enables |
| **Coach mark 3** (diff banner) & **4** (deck-exhausted trio entry) | None structurally; they finally become *reachable* (the audit's P0-8 found 9 of 15 steps unreachable; the tour-completion fix merged in P0) |
| **Any beat pitching ranking as a prerequisite** | Sweep the script for "unlock"-vocabulary: with Phase B there is nothing to unlock. The ask reframes from *requirement* to *upgrade* — which is what the prompt card's copy already says ("Fix them in 2 minutes") |
| **`s5.1` payoff beat** | Must be proven to render pre-flip (S-43) |
| **Sign-off `s8.1`** | Already gated on a real tour having been shown (P0-8 fix) |
| **Assistant GM voice pass** | Extend to the Board Strength vocabulary and the platform-choice landing (§7) — mkt-writer |
| **Platform-specific first-run** (Phase C) | ESPN/MFL users skip Sleeper-specific beats (Sleeper Connect pitch, send-in-Sleeper framing); the send affordance beat resolves per platform (send-in-MFL/ESPN shipped 2026-08-11) |

---

## 7. Platform-choice front door (ESPN / MFL first-class)

### What exists

- **Sleeper:** username-only entry, the working identity key (`sleeper_user_id`) — everything
  downstream assumes it.
- **Apple:** account-anchor sign-in (`auth.accounts`, `acct_` keys); post-audit-P0-5,
  account-only sessions route to LeaguePicker showing "Connect Sleeper, ESPN or MFL."
- **ESPN / MFL as *secondary* platforms:** full link flows exist and are on
  (`espn.link`, `espn.webview_capture`, `espn.league_picker`, `mfl.link`, `mfl.auth_link`) —
  but they are reached *after* an identity exists. Send-in-ESPN/MFL shipped. Fleaflicker has
  a read adapter (`fleaflicker_service.py`, public API, zero auth).

### The design

**One landing, one question — "Where do you play?" — with Sleeper's one-field path kept
visually primary** (T6's constraint):

1. **Sleeper** — username field, exactly the v2 landing. No regression to the 90%-case.
2. **ESPN** — the existing WebView capture (`EspnLinkSheet`), promoted from Settings-reachable
   to landing-reachable; `espn.league_picker` then lists their leagues.
3. **MFL** — the existing `mfl.auth_link` login, same promotion.
4. **Apple** — stays the quiet re-entry link (v2 position), *and* the identity anchor that
   ESPN/MFL entry binds to (below).
5. *(Optional, near-free: Fleaflicker via email lookup — `fetch_user_leagues(email)`, zero
   auth. Decision O-6.)*

### The hard problem, named honestly: identity

The app's working key is `sleeper_user_id`. An ESPN-first user has none. Two options:

- **Option 1 — account-first bind (recommended).** ESPN/MFL entry creates/binds an `acct_`
  identity (the layer built for exactly this in the account-auth plan), and the platform's
  own id (SWID / MFL franchise) becomes the working context. The P0-5 resolution already
  routes account-only sessions to the platform-link picker — Phase C is largely *moving that
  moment to the front door*. Real work remains: every engine surface that assumes
  `sleeper_user_id` needs the account-keyed path exercised end-to-end (rankings, likes,
  matches, notifications), and ESPN's synthetic-id instability (SWID rotation,
  `database.py:7911`) means the bind must anchor on the `acct_` key, not the SWID —
  the same lesson the recap reviewers just learned for `team_key`.
- **Option 2 — require Apple first for non-Sleeper users.** Cheaper, honest about the
  dependency, but it re-erects a friction wall at the exact door we are opening — Apple
  sign-in as the price of being an ESPN user, when Sleeper users pay nothing. Rejected as
  the default; acceptable as a v1 stopgap *only if* Option 1's surface audit finds something
  structural.

**Phase C's first deliverable is therefore not UI — it is the account-keyed engine audit:**
a verification pass proving (or scoping the fixes for) rank/like/match/notify on an `acct_`
session with zero Sleeper linkage. eng-architect + eng-backend own it; the landing screen is
trivial once it passes.

---

## 8. Measurement

The activation definition **changes** with this shift, and the seam must be recorded (the
analytics platform's standing rule).

| Question | Metric | Exists? |
|---|---|---|
| Did opening access help? | `first_trade_card_seen` (+ms), `first_swipe` in session 1 — the experiment doc's activation_rate, now read pre/post-flip as a directional seam, not an A/B | Registered (v2 item 8a set) |
| Do users still rank? (T4) | `rank_method_selected`, `quickset_prompt_accepted/snoozed`, `deck_regenerated` per first-week cohort | Registered |
| Does signal quality dilute? (T2) | Like→mutual-match conversion, and match disposition rates, split by author board strength | **New cut, not new events** — needs the board-strength property on the like write; spec to an-data-architect |
| Platform mix at the door (Phase C) | `signin_attempted/succeeded` gain a `platform` prop; `espn_connect_*` already exist | Prop extension — taxonomy commit first |
| Funnel stage 5 ("activated" = `ranking_complete_first_time`) | **Redefinition decision** — with no lock, first-completion is a milestone, not activation. Propose stage 5 becomes first-swipe (matching the experiment doc) and ranking-complete moves to a depth metric | an-funnel decision, before the flip so the series break is dated |

---

## 9. Risks

| Risk | Severity | Handling |
|---|---|---|
| Consensus decks embarrass the product in front of exactly the new users we open to | High | The v2 eval gate (insult rate <3%) runs pre-flip, on current production data. It was designed as a ship-gate; keep it one |
| Signal dilution degrades mutual matching and the `trade_found` push | High | Phase B's like-weighting + gate clause ship *with* the lock removal (T2 condition). Coordinate with the P1-9 build now |
| Organic ranking rate collapses (T4) | Medium | Watch `rank_method_selected` weekly post-flip; the lever is prompt cadence/copy, never re-walling |
| The account-keyed path has structural gaps (Phase C) | Medium | The audit-first sequencing exists for this; Option 2 is the recorded stopgap |
| Cold-start latency makes the first deck a spinner | Medium | `onboarding.keep_warm` (built, dark) + the eval gate measures init+pregen latency; fin-budget memo on the paid Render tier already recommended in v2 |
| Activation series breaks silently at the flip | Low | §8's seam decision, dated in the tracking plan before the flip |

---

## 10. Decisions needed

> **Ratified 2026-08-15 — operator: yes to all nine, recommendations as written.**
> This table is the decision record. O-9's protocol (eng-backend proposes numbers,
> an-data-architect instruments, operator ratifies) is approved as a protocol; the
> numbers themselves still come back for a ratifying yes.

| # | Decision | Recommendation |
|---|---|---|
| **O-1** | Ship Phase A as default (retire the experiment framing)? | **Yes.** Three artifacts agree; the A/B can never power; flags remain the revert lever |
| **O-2** | Phase B scope: does access un-gating wait for the basis-lock design (B-1's `member_rankings` publish gate + like-basis weighting), or ship ahead of it? | **Ship together.** The publish gate *is* the wall's legitimate function relocated (T2); un-gating access without it invites the exact dilution P1-9's gate was designed against |
| **O-3** | The basis-milestone frame — the lock gates "calling the board yours," celebrated at the flip (names/copy to mkt-brand)? | **Yes** (v1.1, operator-directed) — it preserves D-P1-10's machinery whole, keeps the density signal meaningful, and gives streaks and the recap's "your calls" an honest anchor |
| **O-8** | Ship an explicit grade affordance ("I win / fair / I lose") or rely on the implicit ladder (swipe/flag/accept/send)? | **Implicit first.** The ladder covers the bar without new UI; the explicit grade is a strong v2 candidate once `grade_count` data shows where implicit signal is thin |
| **O-9** | Grading-lane thresholds and signal weights (B-3) | eng-backend proposes against real deck data, an-data-architect instruments, operator ratifies — same protocol as P-3 on P1-9. The architecture (one bar, six lanes, per-position coverage) is settled; the numbers are tuning |
| **O-4** | Funnel stage 5 redefinition (activation = first swipe)? | **Yes**, dated in the tracking plan; ranking-complete becomes a depth metric |
| **O-5** | Phase C identity: Option 1 (account-first bind) with the engine audit as the first deliverable? | **Yes**; Option 2 recorded as stopgap only |
| **O-6** | Include Fleaflicker at the door? | **Cheap yes** (email lookup, zero auth, adapter exists) — but only if it costs the landing no layout complexity; otherwise Settings-link only |
| **O-7** | Sequencing vs the two in-flight briefs | **Phase A now** (flag flips, independent of both); Phase B coordinates with P1-9's build (one added predicate); Phase C after the notification batch ships |

## 11. Handoffs

| To | What |
|---|---|
| **eng-mobile** | Phase A flag flips + pre-flip S-43 render check; Phase B lane un-gating + Board Strength surfaces |
| **eng-backend** | Phase B: the grading lane (`grade_count`/`grade_required` on `/api/rankings/progress`, P1-7 shape); new Elo inputs (flag, accept/decline, send — B-2); the `member_rankings` publish gate (B-1, **verify the current publish trigger first** — the plan assumes submit-time replace); like-basis weighting + `trade_found` clause (coordinate with the eng partner's P1-9 build); threshold/weight proposal (O-9); Phase C account-keyed engine audit (with eng-architect) |
| **eng-qa** | The v2 deck-quality eval run (item 2 spec, unchanged) against current prod data |
| **an-funnel** | O-4 activation redefinition, dated |
| **an-data-architect** | Board-strength prop on like events; `platform` prop on signin events; taxonomy-first ordering as always |
| **mkt-brand / mkt-writer** | **The §4b positioning narrative** — "your grades build YOUR board" as the launch story, one page: claim, proof mechanics, the honesty guardrail, and where it lives (landing copy, App Store subtitle, provenance chip microcopy). Plus basis-milestone vocabulary and the platform-choice door voice pass. Coordinate with mkt-aso: the differentiation claim belongs in the store listing |
| **pm-pfo** | First-run audit of the flipped flow — the core-loop guardrail this persona is bound by before any public-launch sequencing |
| **pm-partnerships** | ESPN WebView capture moving to the front door raises its ToS profile — flag, not block |
