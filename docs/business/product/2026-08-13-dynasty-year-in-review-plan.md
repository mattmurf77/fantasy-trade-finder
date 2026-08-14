# Dynasty Year in Review — capture plan and recap design

> **Role:** pm-growth. **Date:** 2026-08-13.
> **Verified against:** `origin/main` @ `4a4b671`.
> **Origin:** operator ask — *"a historical snapshot process of team values for each league
> that joins the app… let users see a historical progression of their dynasty values
> throughout the season… capture the most significant dynasty value jumps… this could feed
> a yearly recap experience that IS very much a growth tactic — and one of the strongest
> and most unique."*
> **Backlog identity:** this is **#46 (Wrapped)**, the unbuilt consumer named in
> `backend/database.py:976` and `docs/plans/competitor-top20/17-player-profiles.md:127`.
> **This document changes no source file.** Specs and recommendations only.

## Contents

- [1. The headline, and the deadline](#1-the-headline-and-the-deadline)
- [2. Evidence — what is banked and what is being lost](#2-evidence--what-is-banked-and-what-is-being-lost)
- [3. The principle: capture inputs, compute outputs](#3-the-principle-capture-inputs-compute-outputs)
- [4. In-year capture vs end-of-season fetch](#4-in-year-capture-vs-end-of-season-fetch)
- [5. Capture spec — the part that is time-critical](#5-capture-spec--the-part-that-is-time-critical)
- [6. The recap itself — three tiers of defensibility](#6-the-recap-itself--three-tiers-of-defensibility)
- [7. Why this is a growth tactic, mechanically](#7-why-this-is-a-growth-tactic-mechanically)
- [8. Phasing and timeline](#8-phasing-and-timeline)
- [9. Risks](#9-risks)
- [10. Decisions needed](#10-decisions-needed)
- [11. Handoffs](#11-handoffs)

---

## 1. The headline, and the deadline

**The recap is not the urgent part. The capture is.**

Half of what the operator asked for is already running. `player_value_history` has written a
daily consensus value for every player in the universal pool since **2026-07-26** — unflagged,
scheduled in `render.yaml` at 06:00 UTC, with an hourly self-healing fallback
(`docs/architecture.md:230`). That table exists *because* someone made this exact argument for
values in June: *"every week not logging is chart history lost"*
(`docs/plans/competitor-feature-backlog-2026-06-11.md:295`).

**Nobody ever made that argument for rosters, and rosters are being overwritten right now.**
`league_members.roster_data` (`backend/database.py:327`) holds one row per member per league
and is replaced on every sync. There is no history of who owned whom. Zero rows, zero days.

That matters because a team's value is not a stored number — it is *roster × values*. We have
the values. We do not have the rosters. **Every attribution stat in the recap the operator
described — value trajectory, biggest jumps and who owned them, trade P&L, buy-low grades —
is a join between a table that exists and a table that does not.**

**One caveat on "already running", added after review.** The dedicated `value-snapshot-daily`
cron does **not** exist — it was added to `render.yaml` and reverted the same day (`1e50d3e`,
"broke blueprint sync"). `docs/architecture.md:230` still claims otherwise and is **drifted and
false**. The operative mechanism is the `hourly-tick` idempotent fallback guard
(`docs/runbook.md:295`), which rides a cron service that *is* declared. Whether the declared
crons actually fire is **unverified** — the settling query is in
[the plans README](../../plans/dynasty-year-in-review/README.md). The capture design below
works either way; only the urgency of the Render cron migration turns on the answer.

**The deadline is Week 1, roughly four weeks out.** Dynasty rosters churn hardest between now
and mid-September: camp cuts, startup drafts, final-roster moves. A snapshot process that goes
live in October produces a 2026 recap that opens in October. Miss it and the next chance is a
full year away.

**The recap UI, by contrast, is not urgent at all.** It ships in December. The two halves
should be planned together and built months apart.

---

## 2. Evidence — what is banked and what is being lost

All rows verified at `origin/main` @ `4a4b671`.

### 2.1 Already banked

| Data | Table | Status |
|---|---|---|
| **Consensus player value, daily** | `player_value_history` (`database.py:981`) — `player_id`, `scoring_format`, `consensus_elo`, `consensus_value`, `search_rank`, `adp`, `snapshot_date` | **Live since 2026-07-26.** Unflagged, scheduled, self-healing. The backbone |
| **Each user's personal Elo** | `elo_history` (`:957`) — `user_id`, `league_id`, `player_id`, `scoring_format`, `elo`, `snapshot_at` | Live, but **event-driven** — written when a user ranks (`server.py:6001`, `:7367`), not on a schedule. Dense for active rankers, sparse for everyone else |
| **Executed trades, raw** | `sleeper_trades` (`:359`) — full Sleeper transaction payload, append-only, idempotent | Live behind `market.trade_capture`. **Sleeper only** |
| **FTF suggestions shown** | `trade_impressions` (`:442`), `deck_impressions` (`:481`) | Live |
| **FTF decisions** | `trade_decisions` (`:308`), `swipe_decisions` (`:296`) | Live |
| **FTF mutual matches + outcomes** | `trade_matches` (`:394`) | Live |
| **Leaguemates' valuations** | `member_rankings` (`:379`) | Live, but **snapshot semantics** — replaced on every submit. No history |

### 2.2 Being lost, right now

| Data | Where | Why it's lost |
|---|---|---|
| **Roster composition over time** | `league_members.roster_data` (`:327`) | Overwritten on every sync. **The gap. Everything in the recap depends on it** |
| **Draft pick ownership over time** | `draft_picks.owner_user_id` (`:745`) | Mutated in place when a pick trades. `is_traded` is a flag, not a history |
| **Leaguemates' valuations over time** | `member_rankings` (`:379`) | Delete + insert on every submit |
| **Trade block flags** | `trade_block` (`:339`) | Replaced on every sync. Low recap value; noted for completeness |

### 2.3 The honest caveat on "unrecoverable"

Roster history is **semi-recoverable**: at season end you can replay the transaction log
backwards from the final roster to reconstruct who owned whom on any date. This is a real
technique and it should be stated rather than hidden behind an urgency argument.

It is also fragile. It needs a complete, gap-free log of every add, drop, waiver, trade and
offseason move; a single gap corrupts every date before it; it does not cover the pre-season
window at all unless the platform exposes it; and it is materially harder outside Sleeper.

**Conclusion, stated fairly:** if we miss the window, a partial 2026 backfill is possible for
Sleeper leagues and should be attempted. It is a salvage operation, not a plan. Snapshotting
costs about a week of work and produces data that is correct by construction.

---

## 3. The principle: capture inputs, compute outputs

**Do not store "team value" as a number. Store the roster, and join to values at read time.**

Three reasons, in order of importance:

1. **Attribution.** "Who owned the player during the jump" is answerable from a roster
   history and unanswerable from a stored team total. The operator's second ask — *capture
   the most significant dynasty value jumps* — is entirely an attribution problem.
2. **Re-computability.** The value model changes. Storing inputs means a model improvement
   makes history *better* rather than making it a lie.
3. **Compression.** A roster is ~30 player ids. A team total is one float that can only ever
   answer one question.

**With one exception, following a precedent this codebase already set.** `player_value_history`
deliberately denormalises `consensus_value` alongside `consensus_elo` *"so a later
`elo_value_*` config change does not silently rewrite recorded history"* (`database.py:978`).
Same logic applies one level up: **store the computed team value alongside the roster.** The
roster is the source of truth for attribution and recomputation; the stored total is what
guarantees the user's season chart does not visibly change shape after a model tweak. Both,
not either.

---

## 4. In-year capture vs end-of-season fetch

The operator's central question. The test for each row: **does this data still exist in six
months if nobody writes it down today?**

### 4.1 Must capture in-year — perishable

| # | Data point | Feeds | Status |
|---|---|---|---|
| C1 | **Roster composition per team, over time** | Team value trajectory; every attribution stat | ✗ **BUILD — the gap** |
| C2 | **Computed team value at snapshot time** | Chart stability across model changes | ✗ build (rides C1) |
| C3 | **Draft pick ownership over time** | Pick flow; "what your first became" | ✗ build |
| C4 | Consensus player value, daily | Value jumps; buy-low/sell-high; trade aging | ✓ **live** |
| C5 | User's personal Elo over time | "Your calls" — the most defensible stat we have | ~ **partial** — event-driven; needs a cadence backstop |
| C6 | **Leaguemates' valuations over time** | Board divergence; league-comparative stats | ✗ **BUILD** — in scope per the YR-3 ruling. `member_rankings` is delete+insert on every submit, so this is perishable on the same terms as C1 |
| C7 | FTF suggestions shown + decisions | "The one that got away" | ✓ live |
| C8 | FTF matches and dispositions | Trades made through FTF, aged | ✓ live |
| C9 | Executed trades, raw | Trade P&L | ✓ live, **Sleeper only** — ESPN/MFL gap |
| C10 | Roster age curve at snapshot time | Contention-window movement | derived from C1 + player metadata; no extra capture |

### 4.2 Fetch at end of season — recoverable

| # | Data point | Source | Note |
|---|---|---|---|
| F1 | Final standings, W-L, PF/PA | platform API | Commodity |
| F2 | Weekly matchup scores | platform API | Commodity; feeds best/worst week |
| F3 | Playoff bracket and result | platform API | Commodity |
| F4 | Full transaction log (adds/drops/waivers/trades) | platform API, per week | **Verify ESPN/MFL retention before relying on it** |
| F5 | Draft results | platform API | Feeds "what your pick became" |
| F6 | Player season stats / fantasy points | platform or nflverse | Feeds production-vs-value stats |
| F7 | Player metadata — age, position, team | Sleeper players + DynastyProcess | **Age is a trap:** age at season end ≠ age during the season. Snapshot birthdates, compute age per date |
| F8 | Final rosters | platform API | The anchor for any backfill reconstruction (§2.3) |

### 4.3 The rule this produces

> **Capture what the platform overwrites. Fetch what the platform keeps.**

Platforms keep results and transactions. Platforms overwrite *state* — rosters, ownership,
valuations. State is exactly what a dynasty recap is about, and it is exactly the half nobody
is storing.

---

## 5. Capture spec — the part that is time-critical

> **SUPERSEDED, 2026-08-13.** §5.1 and §5.2 below were reviewed by the `an-data-architect` and
> `eng-architect` personas over three adversarial rounds. **The build spec is now
> [`docs/plans/dynasty-year-in-review/`](../../plans/dynasty-year-in-review/README.md)** —
> final DDL, write seam, transaction isolation and scheduling topology. The sketch below is
> retained for the reasoning trail; **build from the plans folder, not from here.** Three
> corrections the review forced are recorded inline.

### 5.1 What to build

One new table. Sketch, not a schema decision — `eng-backend` owns the final shape:

```
league_roster_history
  league_id, user_id (or roster_id for non-FTF teams),
  scoring_format,
  roster_json        -- the player ids, the input of record
  team_value         -- computed at snapshot time (§3 exception)
  starters_json      -- optional; lets a "your starters vs your bench value" cut exist
  roster_hash        -- change detection
  snapshot_at        -- ISO UTC
  source             -- 'sync' | 'scheduled' | 'backfill'
  UNIQUE (league_id, user_id, snapshot_at)
```

Plus the equivalent for pick ownership (C3), which can be a thinner table or a periodic
serialisation of `draft_picks` rows per league.

### 5.2 Cadence — SETTLED: weekly

**Operator ruling (YR-1): a weekly grid.** Not the original four-week proposal, and not the
opportunistic-on-sync variant as the primary mechanism. Build to weekly; an on-sync
change-detect write may be added if it is genuinely free, but the weekly job is the contract
and the thing that must not be allowed to miss.

The reasoning that produced the move from four weeks to one, retained because it also explains
why a *missed* weekly run matters:

- ~~**No extra API calls.** Sync already fetches rosters. Snapshotting is a hash comparison and
  an occasional insert on data already in memory.~~ **CORRECTED — this was wrong.**
  `upsert_league_members` has one caller, `session_init`, and the rosters arrive
  **client-supplied in the request body** (`server.py:14686-14690`). A cron reading
  `league_members` would stamp possibly-months-old data with this week's period key —
  fabricating history. A server-side fetch is required for the scheduled path. Partly
  recovered: `trade_block_service._fetch_rosters` already retrieves the
  `roster_id → owner_id` mapping in the same daemon and discards it, so the *team-key* half
  costs nothing extra. See the review docs for the reconciled write path.
- **Storage is not a constraint.** ~30 ids per team, 12 teams, weekly for 20 weeks = **240
  rows per league-season**. A hundred leagues is 24,000 rows. This is not a number that
  should influence a cadence decision, and it shouldn't be allowed to.
- **Four weeks mis-attributes the exact events the recap is about.** Consensus values move
  *daily*. If a player spikes in week 6 and is traded in week 7, a four-week roster grid
  credits the wrong manager. Roster resolution is the binding constraint on every attribution
  stat, and a mid-season trade is precisely the moment a dynasty recap wants to be right about.
- **It degrades gracefully.** Active leagues get near-perfect resolution for free; dormant
  leagues fall back to the weekly job.

If the operator prefers a fixed grid for simplicity, **weekly** is the number — not four.
Four-week resolution against daily value data is the one combination that guarantees the
headline stat is sometimes wrong.

### 5.3 Snapshot every team, not just FTF users' teams — this is a growth decision

Snapshot all 10–12 teams in every league we sync, including managers who have never heard of
FTF. The marginal cost is zero: the roster payload for the whole league is already in hand.

The payoff: **when a leaguemate joins in November, they get a full season of value history on
day one.** Not an empty chart with a "check back next year" message — their actual season,
already there. That is a materially better first-run experience than anything the product can
otherwise offer a late joiner, and it turns into invite copy that is simply true: *"your
team's history is already here."*

It also means league-wide superlatives are complete rather than covering only the two
managers who happen to use the app.

### 5.4 Fix the personal-Elo cadence too (C5)

`elo_history` is written when a user ranks. A user who ranked once in August and never again
has one data point, which makes "your calls" a single-observation stat for exactly the users
we most want to bring back. Cheap fix: append a personal-Elo snapshot on the same trigger as
the roster snapshot, so every user has a regular series whether or not they re-ranked.

---

## 6. The recap itself — three tiers of defensibility

The operator's instinct is right and worth making explicit as a build rule: **a recap built
from platform data is a commodity; a recap built from FTF's own data is impossible for anyone
else to make.** Sleeper already ships a season recap. We should not spend our effort
re-shipping it.

### Tier 1 — only FTF can produce these

These use personal Elo and FTF decision data. No competitor has either.

| Stat | What it says | Inputs |
|---|---|---|
| **Your calls** | *"You had Player X 14 points above consensus in September. The market came to you by Week 9."* A per-user accuracy grade on the valuations they actually made | C5 × C4 |
| **The one that got away** | *"You passed on this trade in Week 4. It's worth +2,400 to you today."* | C7 × C4 |
| **Trades you made through FTF, aged** | Value then vs value now on every FTF-originated trade | C8 × C4 |
| **Where your board diverged** | The players you valued most differently from the market — and whether you were right | C5 × C4 |

**"Your calls" is the most defensible thing in this document.** It is a direct payoff for the
core loop — ranking — and it is the honest answer to the re-rank prompt we deferred as GD-6:
the reason to keep your board current is that it becomes a scorecard. That is a better
motivation than any notification.

### Tier 2 — dynasty-specific, unlocked by the roster history we're building

| Stat | What it says |
|---|---|
| **Team value trajectory** | The headline chart. Your roster's value, week by week, against the league median |
| **Trade P&L, aged** | Every executed trade: value given vs received *at the time*, and *now*. **The killer dynasty stat.** Platforms grade trades at the moment of the trade; nobody grades how they aged on your actual roster |
| **Biggest value jumps, and who owned them** | The operator's explicit ask. Needs roster resolution finer than the jump (§5.2) |
| **Buy-low / sell-high grades** | Acquisition price vs current value, per asset |
| **Roster age curve movement** | Did you get younger or older? Contention window opening or closing |
| **Draft pick flow** | Picks in, picks out, and what they became |
| **League superlatives** | Biggest riser, most active trader, best trade, sell-off of the year |

### Tier 3 — commodity (regular season and playoffs)

Record, standings, points for and against, best and worst week, playoff run, championship.

**Include it, keep it small.** Two arguments for including it: platform-agnostic rendering
means one consistent recap across Sleeper, ESPN and MFL, and a recap with no mention of who
won feels broken. One argument for keeping it small: every hour here is an hour spent on the
half a competitor already ships for free.

**Suggested proportions:** ~60% tier 1+2, ~20% tier 3, ~20% league-social/shareable. Worth
agreeing up front, because tier 3 is the easiest to build and will expand into the space if
nobody is holding the line.

---

## 7. Why this is a growth tactic, mechanically

The operator called it one of the strongest and most unique. Tracing the loop:

| Step | Mechanic |
|---|---|
| **Timing** | Ships late December / early January. Dynasty attention is high, and it is exactly when the offseason trading window opens. The recap ends by handing the user into the thing the product does |
| **The share moment** | League-wide superlatives are inherently a league-chat artifact. A per-league leaderboard is something you send to eleven people, ten of whom are not users |
| **The invite surface** | League sections are complete for every team (§5.3), so a non-user sees *their own team's season* rendered by a product they have not installed. That is the strongest invite this product will ever have — and it is seasonal, one shot a year |
| **The ranking loop** | Tier 1 makes ranking pay off. Rank → your calls get graded → the recap is better → rank more. This closes the loop GD-6 declined to nag people into |
| **Platform-agnostic reach** | Serves ESPN, MFL and Fleaflicker leagues, not just Sleeper — an addressable-market argument, not just feature parity. **Operator ruling YR-8 (2026-08-14): this claim must be TRUE, not caveated** — the weekly sweep fetches rosters **server-side on every platform**, so no platform's history depends on someone opening the app. Verified feasible: MFL's `rosters` export and Fleaflicker's entire read API are public (`mfl_service.py:432`, `fleaflicker_service.py:15`); ESPN public leagues need no cookies and private leagues use the linking user's stored `espn_credentials` (Fernet-encrypted `espn_s2`+SWID, `database.py:1355`). The one honest edge: a private ESPN league whose linker's cookie has expired degrades to app-open capture **plus a "reconnect ESPN" nudge** — an expiring cookie becomes a visible re-auth ask, never a silent gap |
| **Retention across the trough** | Feb–March is the seasonal trough (`docs/business/context.md`). A December artifact that people revisit and argue about is a bridge into the rookie-draft ramp |

**One caution.** The recap is a *seasonal spike*, not a growth engine. It fires once a year and
cannot compound the way the invite loop does. It is worth building because it is defensible
and cheap on the capture side — not because it will move WAT in Q1.

---

## 8. Phasing and timeline

| Phase | What | When | Why then |
|---|---|---|---|
| **P0 — Capture** | `league_roster_history` (C1, C2), on-sync trigger + weekly backstop, all teams | **Now — before Week 1 (~Sept 10)** | Time-critical. ~1 week of work. Every day of delay is unrecoverable |
| **P1 — Capture, round two** | Pick ownership (C3), personal-Elo cadence (C5), a backfill audit of what P0 missed | Sept–Oct | Valuable, not perishable at the same rate |
| **P2 — Fetchers** | End-of-season fetchers (F1–F8); **verify ESPN/MFL transaction-log retention** | Oct–Nov | Must be verified before the recap design depends on it |
| **P3 — Compute + UI** | Stat computation, recap screens, share artifacts | Nov–Dec | The expensive half, deliberately last |
| **P4 — Ship** | Release, share mechanics, invite surfaces | Late Dec | The window |

**Only P0 is urgent.** Everything else can be re-planned in October with better information —
including whether the recap ships at all. P0 is worth doing *even if the recap slips a year*,
because the data cannot be created retroactively and it also feeds #33 (value-movers digest)
and #17 (player profiles).

That is the strongest argument for P0 and it should be the one used: **it is not a bet on the
recap.** It is cheap insurance on a year of data, with three consumers.

---

## 9. Risks

| Risk | Severity | Handling |
|---|---|---|
| **Miss the Week 1 window** | **High** | The whole reason P0 is separated and sequenced first. Partial Sleeper backfill is the fallback (§2.3), not the plan |
| **Privacy — the recap exposes one manager's valuations to another** | **High** | **Direct tension with D-P1-12** (operator: ranking/tier-board sharing is not a product surface, in any form). "Where your board diverged" and league-wide valuation comparisons are ranking exposure wearing a different hat. **Needs an explicit call — YR-3** |
| **Tone: "the one that got away" reads as mockery** | Medium | Editorial rule: self-only, never comparative, never surfaced to leaguemates. Frame as a near-miss, not a failure. A recap that makes people feel stupid does not get shared |
| **Value-model drift changes history under users** | Medium | Store computed values alongside inputs (§3). This is exactly why `player_value_history` denormalises |
| **ESPN/MFL transaction logs may not be retrievable** | Medium | Verify in P2, before the design depends on it. Degrade to Sleeper-only for trade P&L rather than blocking the whole recap |
| **Sample size — 3–5 users** | Medium | A league-wide recap needs a league. §5.3 (snapshot every team) is the mitigation: the recap works for a league with one FTF user |
| **Scope creep from tier 3** | Medium | Agree proportions up front (§6) |
| **Storage cost** | **None** | ~240 rows per league-season. Explicitly not a reason to choose a coarser cadence |

---

## 10. Decisions needed

**All seven answered by the operator on 2026-08-13. These are binding on any build.**

| # | Decision | **Operator ruling** |
|---|---|---|
| **YR-1** | **Snapshot cadence** | **WEEKLY.** A fixed weekly grid, not the 4-week proposal and not the opportunistic-on-sync variant. Build to a weekly cadence; an on-sync change-detect write is an acceptable *addition* if it costs nothing, but weekly is the contract |
| **YR-2** | **Store computed team value alongside the roster?** | **BOTH.** Roster ids for attribution and recomputation; stored team value so a later model change cannot alter the shape of a season chart already shown to a user |
| **YR-3** | **Does the recap expose one manager's valuations to leaguemates?** | **YES — permitted, and this is a scope expansion.** See the clarification below. Valuation-derived comparative stats are allowed in the recap **and on League Home** |
| **YR-4** | **"The one that got away" in scope?** | **YES.** Self-only, with the tone rule in §9 |
| **YR-5** | **Tier 3 (regular season / playoffs) scope** | **~20% of the surface.** One screen |
| **YR-6** | **Snapshot every team, or only FTF users' teams?** | **EVERY TEAM** |
| **YR-7** | **Does P0 proceed independently of a recap commitment?** | **YES.** Capture work starts now, on its own justification |
| **YR-8** | **Platform parity of capture** (added 2026-08-14) | **The platform-agnostic claim must be true, not caveated.** The weekly sweep fetches server-side on all four platforms — Sleeper (public), MFL (public `rosters` export), Fleaflicker (public API), ESPN (cookie-free for public leagues; stored encrypted `espn_s2`+SWID for private ones). ESPN-private cookie expiry degrades to app-open capture + a visible "reconnect ESPN" nudge. This adds the per-platform sweep adapters to **P0 scope** — the fetch functions already exist (`espn_service.fetch_league`, `mfl_service.fetch_rosters`, `fleaflicker_service.fetch_league_bundle`); the new work is the sweep calling them |

### YR-3 clarification — the scope of D-P1-12, narrowed

The operator's ruling, in substance: *"I just didn't want the share-rankings literal feature
yet — it's not an issue to show it on recaps or even on the League Home page."*

**This narrows how [`D-P1-12`](../../plans/audit-p1-remediation/DECISIONS-p1.md#d-p1-12--rankingtier-board-sharing-is-not-a-product-surface)
should be read**, and the distinction is worth stating precisely because this plan is not the
last thing that will run into it:

| | Status |
|---|---|
| **Public, unauthenticated share routes for tier boards** (`/og/tiers/<pos>/<username>.png`, `/s/tiers/<pos>/<username>` — fetchable by URL guess, no in-app link required) | **Still prohibited.** This is what D-P1-12 actually found and shut down, and the live-exposure takedown it called for is unaffected by this ruling |
| **In-app display of a user's valuations to their own leaguemates**, inside an authenticated league context — recap sections, League Home | **Permitted** |

The line is *public URL exposure*, not *leaguemates can see your board*. A recap section
comparing your valuations to your league's is in scope. A shareable public image of your tier
board is not.

**Consequence for this plan:** C6 (leaguemates' valuations over time) moves from "gap, gated
on privacy" to **in scope**, and "where your board diverged" (§6 Tier 1) is a buildable
league-comparative stat rather than a self-only one. `member_rankings` is replaced on every
submit, so **capturing its history is now a P0/P1 capture item, not a deferred one.**

---

## 11. Handoffs

| To | What |
|---|---|
| **eng-backend** | **P0, this month:** `league_roster_history` schema, the on-sync hash-diff trigger, the weekly backstop, all-teams capture. Plus C3 pick-ownership history and the C5 Elo cadence backstop in P1 |
| **eng-integrations** | **P2 verification, before the design leans on it:** do ESPN and MFL expose a full-season transaction log and final rosters? Sleeper is known-good. This gates F4/F8 and therefore trade P&L outside Sleeper |
| **pm-technical** | PRD for P0 once YR-1/YR-2/YR-6 are answered. Feature-scope block per the root `CLAUDE.md` gates — this is schema + data collection, which is explicitly *not* express-lane eligible |
| **an-data-architect** | Recap event taxonomy (`wrapped_viewed` is already reserved in `SERVER_FIRED_EVENTS` and has never fired); share-artifact events; registration-before-emitter as always |
| **pm-monetization** | Is the recap free, or a premium hook? It is the highest-perceived-value artifact the product will produce. Decide before P3, not after |
| **mkt-brand / mkt-content** | The December launch narrative and the share-artifact design. This is the one seasonal moment with real organic potential |
| **pm-retention** | The Feb–March trough bridge (§7) |
| **pm-pfo** | Late-joiner first-run: what a user who arrives in November sees when a full season of their history already exists |

---

### Appendix — what I checked, and what it changed

1. **"We need to snapshot team values."** Reframed. Team value is a *join*, and the value half
   has been running since 2026-07-26. What is missing is roster history. The build is smaller
   than the ask sounds, and more urgent.
2. **"Every 4 weeks is sufficient."** Challenged on evidence, not preference. Values move
   daily; four-week roster resolution mis-attributes the mid-season trades that the recap's
   headline stats are made of. Storage is ~240 rows per league-season, so cost is not the
   reason to choose four.
3. **"Wrapped" as a new idea.** It is backlog **#46**, named in `database.py:976` as a planned
   consumer of a table that was built specifically to feed it. This plan is that item, and the
   urgency argument it rests on is the same one that got #57 shipped in June.
4. **Is roster history truly unrecoverable?** Not strictly — a Sleeper transaction-log replay
   can reconstruct it. Recorded honestly in §2.3 so the urgency argument stands on its real
   footing: the reconstruction is fragile and partial, the snapshot is correct by construction
   and costs a week.
