# #300 — League rankings → trade candidates + player→finder handoff (Planner doc)

**Feedback (verbatim, screen LeagueRankings, severity `idea`, v1.12.0, 2026-08-10):**

> "I want a way to identify good trade candidates teams from this page and
> incorporate a way to navigate to the trade screen from the page too. For the
> second one, I'm thinking that when you click a player, a button appears below
> the clicked tile with the button saying 'find trade suggestions'. It brings
> the user to the find a trade page with that player preselected in either the
> trade away or trade for settings depending on whether the user is clicking
> the button on one of their players or one of their opponents players. For the
> first, specifically what I'm trying to do is let a user identify a position
> they're trying to trade away and get presented the teams that are worse at
> that position."

Two sub-features:
- **300-A — positional-weakness team finder** ("teams worse than me at P")
- **300-B — player → trade-finder handoff** (tap a player, "Find trade
  suggestions", land in the finder with that player preselected on the right
  side)

Plan basis: worktree `feedback-300-plan` @ `origin/main` `ab9368f`. Every claim
below was read from source in that tree, not from docs.

---

## 1. Headline

**Both sub-features are pure-client work, buildable in one branch, shipped
behind two independent default-OFF flags — no backend change, no API change,
no schema change.** The evidence: the power-rankings payload already carries
per-team per-position value totals (`positions: {QB|RB|WR|TE: {count, value}}`,
`mobile/src/api/league.ts:560-566`, computed at
`backend/power_rankings.py:204-246`), and the screen already computes in-league
positional ranks from it (`LeagueSummaryScreen.tsx:652-665`) — so 300-A is a
presentation layer over data already on the wire. 300-B is even smaller: the
trade finder's ONLY live preselection contract is the session-scoped
`useFinderTargets` zustand pin store (`mobile/src/state/useFinderTargets.ts`),
which the deck reads at generate time regardless of mode
(`TradesScreen.tsx:1161-1183`) — pin + navigate is the whole feature, and it
requires **zero edits to TradesScreen.tsx** (a large sequencing win given
#297/#298 own that file).

Recommendation: **build together, flag separately** (`league.pos_candidates`,
`league.player_trade_handoff`). They share one file (LeagueSummaryScreen.tsx),
one Maestro suite, and one QA pass, but neither depends on the other and either
can be killed alone. 300-B is the low-risk quick win; 300-A carries the one
genuine product decision (the definition of "worse", §3.1) that needs operator
sign-off before build.

**The trap this plan exists to prevent:** the feedback's phrasing ("preselected
in the trade away or trade for *settings*") invites a nav-params design — and
route-param targeting is a **dead path in the shipped flag state**. With
`trades.sheet_targeting` ON (it is ON — `config/features.json:180`),
`scopedOpponent` reads sheet-local state and route params are ignored
(`TradesScreen.tsx:515-519`). A params-based handoff would compile, demo
correctly with flags off, and silently no-op in production. The pin store is
the only contract that works in every flag state.

---

## 2. What the code actually does today (with `file:line`)

### 2.1 LeagueRankings (`mobile/src/screens/LeagueSummaryScreen.tsx`, 2,347 lines)

- **Two registrations, one component** (#181, header comment :145-152): tab
  root `LeagueRankings` (`TabNav.tsx:449-452`) and legacy root-stack push
  `LeagueSummary` (`RootNav.tsx:514-515`). `isTabRoot = route.name ===
  'LeagueRankings'` (:362).
- **Data:** TWO parallel queries (one per basis, #248) against
  `GET /api/league/power-rankings` (:399-412). Payload per team
  (`league.ts:542-597`): `rank, user_id, username, display_name, is_you,
  total_value, positions{QB|RB|WR|TE:{count,value}}, positions_value,
  picks{count,value,items}, starters[]|null, roster[]` (each roster row:
  `player_id, name, position, team, age, value, tier?` — `league.ts:527-540`).
- **`is_you` is server-stamped** (`server.py:19155`: `t["is_you"] =
  (t["user_id"] == g_user_id)`). The caller-excluded `sess["league"].members`
  convention is handled server-side: `_power_ranking_inputs` appends the
  caller's own roster row explicitly in the fresh/demo fallback
  (`server.py:18965-18980` — comment: "session league members exclude the
  caller"). ESPN-imported leagues store the caller's OWN team under their real
  session user id, synthetic `espn:` ids only for the others
  (`server.py:18729`, `:18913`, `_espn_member_id` :18562-18566) — so `is_you`
  resolves on every platform.
- **Client-side re-ranking is already positional:** `computeSubset` builds
  per-team `posValues` under the All/Starters/Bench subset (:272-294),
  `activeTotal` collapses subset + position filter + the
  `league.picks_always_counted` flag into one number (:333-354), `ranked`
  re-sorts the league on it (:527-537, tie-break `user_id` asc). Filtering to
  RB literally re-ranks the league by RB value today.
- **In-league positional rank per team already exists:** `teamPosRank`
  (:652-665) — rank of each team's position-group value among all teams, used
  for the drill-in tercile chips (:1195-1207).
- **The only "player tiles" on this screen live in the drill-in roster panel**:
  after tapping a team (bar :1534+ or row :1620+), roster rows render as
  non-pressable `<View style={styles.rosterRow}><PlayerCard dense …/></View>`
  (:1210-1229). There is **no player-level press affordance anywhere on the
  screen today** — 300-B adds the first one.
- **`league.picks_always_counted`** (ON, kill switch — `features.json:135`,
  `useFeatureFlags.ts:44-56`): tapping the first position pill auto-adds PICKS
  (rule A, :721-735), so "filter = {RB}" is actually `{RB, PICKS}` in the
  shipped state. Consequence for 300-A: the bar totals under a single-position
  filter INCLUDE pick value; a candidates comparison must read
  `posValues[P]` directly, not `activeTotal` (§3.1).
- **Screen-library ground truth:** `screens/mobile/league-summary/` has
  populated/basis--personal/error/loading/populated--single-format captures.
  **No drill-in (focused-team) capture exists** — that state is where 300-B
  lives, so the mockup/QA loop needs a capture run for it (capture gap, not
  policy — `screens/CLAUDE.md`).

### 2.2 The trade finder (`mobile/src/screens/TradesScreen.tsx`, 6,158 lines)

- **TradeFinderHubScreen is UNROUTED** (#246): no navigator registers it
  (`TabNav.tsx:396-419`, `screens/CLAUDE.md` row). The Acquire tab's root
  `TradesHome` renders TradesScreen with `initialParams {mode:'guided'}` when
  `trades.finder_hub` is on (it is ON, `features.json:11`). Modes are route
  params on TradesScreen itself: `finderMode: 'guided'|'team'|'player'`
  (:500-502).
- **Team-mode route params are dead in prod:** with `trades.sheet_targeting`
  ON (`features.json:180`), `scopedOpponent` comes from sheet-local
  `sheetOpponent` state, NOT `route.params.opponentUserId` (:515-524). There
  is no way to preset the opponent from outside the screen.
- **The pin store is the live preselection contract:**
  `useFinderTargets` (`state/useFinderTargets.ts:41-57`) — `pinnedGive` /
  `pinnedReceive` / `addGive` / `addReceive` (dedupe by id), session-only,
  self-clears on league switch via a module-level `useSession` subscription
  (:62-73). The generate mutation reads the store fresh at call time
  (`TradesScreen.tsx:1165-1183`: `pinned_give_players` /
  `pinned_receive_players`, sent only when `trade.finder_targeting` is on —
  it is ON, `features.json:36`). Today the ONLY `addGive`/`addReceive` caller
  in the app is TradesScreen's own picker (:1937-1938) — 300-B becomes the
  first external caller, which is exactly what the store was lifted out of
  TradesScreen for (its header comment, :5-7).
- **A single pin already produces a full "trade suggestions for this player"
  experience with no button press:** `singlePin` (:1038-1045, gate never
  checks `finderMode` — confirmed by #250's status doc) drives the
  asset-ideas query (`trade.asset_ideas` ON, `features.json:53`), the featured
  trade window (editable calculator under `trades.player_offers_calc` ON,
  `features.json:186`), and the #243 collapsed "Pinned: <name> · Edit · ✕"
  control row with an always-visible clear affordance
  (`trades.pin-summary.edit` / `trades.pin-summary.clear`, :3652-3677).
- **Player-mode board** (`TRADE AWAY` / `TRADE FOR` columns with per-pin rows
  `trades.board.away.<id>` / `trades.board.for.<id>`, :3837-3916) renders only
  when `finderMode === 'player'` — reachable programmatically via params, but
  the #269 chip strip no longer offers Player/Team chips in the shipped flag
  state.
- **Cross-tab navigation precedent:** `navigation.navigate('Trades',
  {screen:'TradesHome'})` from LeagueScreen (`LeagueScreen.tsx:367`) and
  MatchesScreen (:547). Root stack name is `Main` (`RootNav.tsx:54, :428`);
  the legacy root-stack `LeagueSummary` variant must target
  `navigate('Main', {screen:'Trades', params:{screen:'TradesHome'}})`
  (precedent `RootNav.tsx:230`).

### 2.3 Backend (read for evidence; nothing changes)

- Route `server.py:19082-19215`; math `power_rankings.py:134-273`. Per-team
  `positions` totals are computed and serialized for every team
  (`power_rankings.py:204-246`) — **per-team positional strength is already in
  the payload**; 300-A needs no endpoint work.
- The backend also has a *different* positional-strength notion:
  `analyze_roster_strengths` (`trade_service.py:1033-1081` — tier-binned
  starter counts vs `_STARTER_NEED`/`_SURPLUS_AT` thresholds) feeding
  `_position_strength`/`partner_fit_score` (:1090-1120) inside the trade
  engine, and surfaced to the caller only as their own
  `position_needs`/`position_surplus` on `GET /api/league/preferences`
  (`league.ts:39-45`). It is NOT available per-team to clients. §3.1 rejects
  it as 300-A's definition.

### 2.4 Doc drift found

1. **The pipeline's own framing of prior art is stale:** "the hub already
   supports `mode:'player'` and `mode:'team'`" — the hub is unrouted (#246)
   and, more importantly, `mode:'team'` + `opponentUserId` **route params no
   longer reach the deck** under `trades.sheet_targeting` ON
   (`TradesScreen.tsx:515-519`). Likewise
   `docs/feedback/items/250-team-targeting/status.md:60-62` ("scopedOpponent
   is only ever defined when finderMode === 'team'") predates #269 and is now
   false in the shipped flag state. Nothing to fix in reference docs (both are
   status snapshots), but the Author must not design against them.
2. `mobile/.maestro/README.md:40-47` flow table is self-acknowledged stale
   (:53-56 points at the real `flows/` families). Cosmetic.
3. `docs/api-reference.md:350` (power-rankings) was checked field-by-field
   against `power_rankings.py` + the route — **current, no drift**.

---

## 3. 300-A design — positional-weakness team finder

### 3.1 The definition of "worse at that position" (the whole feature)

**Chosen: team T is a trade candidate for position P iff
`T.posValues[P] < you.posValues[P]`, computed under the active subset
(All/Starters/Bench) from the payload the chart is already showing, position
value only (pick value excluded). Ordered weakest-first; tie-break `user_id`
asc (the screen's existing deterministic ordering, :532-536).**

Why this wins:

- **It answers the operator's literal question.** "Identify a position they're
  trying to trade away and get presented the teams that are worse at that
  position" — worse *than the seller*, in the currency the page already
  displays. A team below the league median but above YOU is not a candidate to
  sell P to.
- **One screen, one value system.** The candidates strip sits inches from a
  chart whose bars are `posValues` sums. Any second definition (tier-binned
  starter counts, medians) would let the strip contradict the chart —
  "Team 4 is weak at RB" while their RB bar segment towers over yours — and
  the screen's history (#208, #248, #293) is a catalog of exactly this class
  of two-sources-of-truth bug.
- **Starter-quality is already expressible compositionally.** The user who
  means "weak RB *starters*" taps the existing Starters subset control;
  `computeSubset` re-derives `posValues` from the derived optimal lineup
  (:272-294) and the candidates recompute with it. We get the
  starter-quality variant for free instead of baking one aggregation choice
  into the definition.

Alternatives considered and rejected:

| Definition | Why it loses |
|---|---|
| Raw positional total, but relative to **league median/average** | Answers "who is weak league-wide", not "who can I sell to" — a team above you but below median is a *rival buyer*, not a candidate. Also introduces a second reference line the chart doesn't draw. |
| **Starter-quality only** (always compute over derived starters) | Hides depth-poor/stud-rich asymmetries the All view exposes; unavailable at all when `starters_available` is false (non-Sleeper platforms, `server.py:19200-19204`), which would make the feature Sleeper-only for no reason. Available on demand via the subset control instead. |
| **Need-based** (`analyze_roster_strengths` bins, `trade_service.py:1033`) | The data is not per-team in any client payload — it would force a new/extended endpoint for a definition measured in a different value system (`dynasty_value` bins vs `elo_to_value` sums) that can visibly disagree with the chart. Coding-guideline §2 (simplicity) and the one-value-system argument both kill it. If the operator later wants "needs a starter at P" semantics, that is a backend feature (extend the power-rankings payload with `_position_strength` per team) — out of scope here. |
| Chart's `activeTotal` (what the filtered bars show) | Under `league.picks_always_counted` ON, a single-position filter is `{P, PICKS}` (rule A, :729-733), so bar values include draft capital — a picks-rich team would read "strong at RB" while holding no RBs. Picks aren't a position; the strip reads `posValues[P]` directly. The plan's copy must state the number is "P value" so the (possibly picks-inclusive) bar and the strip aren't presenting the same-looking number with different contents. |

### 3.2 Entry point and presentation

**Trigger: exactly one core position selected in the existing filter pills**
(`posFilter` contains exactly one of QB/RB/WR/TE — PICKS membership ignored).
No new "pick a position" control: the pills already are that control, mirrored
in chart card and drill-in (#237, one shared state :380), and the feedback's
"identify a position they're trying to trade away" maps 1:1 onto "tap that
position's pill".

**Presentation: a "Trade candidates" section** rendered between the chart card
and the ranked team list (unfocused state only — the drill-in already occupies
that slot when a team is focused, :1133):

- Header: `TickLabel` "Trade candidates" + caption
  `Teams with less RB value than you — weakest first` (subset-aware suffix
  when not All: `…less RB starter value…`).
- Rows (weakest first): rank-in-view numeral, team name, their `posValues[P]`
  (fmtK), and the deficit vs you (`−1.2k vs you`; `semantic.neg` would be
  wrong here — the deficit is *good* for the seller — use the neutral
  `chalk.dim` data tone, no semantic color judgment). Row construction mirrors `TeamRow`
  (:1609-1647): hairline list row, chevron.
- Row tap = `setSelectedId(team.user_id)` — the existing drill-in focus
  (:1294), where 300-B's player rows take over. No new navigation surface; the
  drill-in is already the "inspect this team's roster" answer, and 300-B makes
  it the "start a trade from a specific player" answer.
- Cap: show all qualifying teams (a league is ≤ ~14 rows; no pagination
  speculation).
- The caller's own row never appears (strict inequality; `is_you` team is the
  anchor, not a candidate).

**States:**

- No single position selected → section absent (not an empty shell).
- **Caller is weakest (or tied-weakest) at P** → honest empty state, testID
  `league-summary.candidates.empty`: `No team has less RB value than you.`
  (This is also the "every team equally weak" answer: all-tied ⇒ strict
  inequality ⇒ empty.)
- **No `is_you` team in the payload** (defensive; should be impossible per
  §2.1 ESPN evidence) → section hides entirely. Never anchor on a guess.
- **Position with no starter slot in the league template** (e.g. TE in a
  hypothetical no-TE template) under Starters subset: every team's
  `posValues[P]` is 0 ⇒ all tied ⇒ the empty state above, which is truthful
  ("no team has less TE starter value than you" — everyone has none). No
  special case needed; note for QA.
- **ESPN/MFL/demo leagues:** positions data is identical in shape
  (crosswalked player ids, `server.py:19104-19106`); no picks noise (their
  `picks.value` is 0, irrelevant anyway since the strip reads `posValues`);
  `starters_available` false locks subset to All (:465-467) — strip computes
  on All. Works unchanged.
- Basis toggle: candidates follow the bar-drawing basis (`ranked`'s payload),
  exactly as every other derived signal on the screen does.

**Flag:** `league.pos_candidates`, default OFF, client-only. Register in
`backend/feature_flags.py` (the :284 registry) + `config/features.json`
(default `false` + `_comment_*` sibling per the file's convention). Not in
`LAUNCHED_FLAG_DEFAULTS` (dark launch, unlike the #293 kill-switch pattern).

**Design-system notes:** tokens only (ink/chalk/ice/semantic, `type.*`);
position hexes only as data encodings on the position label (per
cross-client-invariants); no new colors; 11px floor; radius ≤8px; the deficit
number in `type.data`. No emoji, no icon beyond the existing chevron.

### 3.3 What 300-A explicitly does NOT do

- No backend/endpoint change (the decisive answer to the planner brief's
  central question: per-team positional strength **already exists in the
  payload** — `league.ts:560-566`, `power_rankings.py:204-246`).
- No new "trade away" intent control, no persistence of the selected position,
  no cross-screen state.
- No team-level handoff to the finder (route-param team mode is dead under
  #269; the sheet-local opponent state is unreachable from outside
  TradesScreen — see §9 Q3 before anyone tries).

---

## 4. 300-B design — player → trade-finder handoff

### 4.1 Interaction

In the drill-in roster panel (the screen's only player tiles, :1210-1229):

1. Wrap each roster row in a `Pressable` (testID
   `league-summary.player-row.<player_id>`). Tap toggles that row as the
   armed row (component state `armedPlayerId`); tapping another row moves the
   armament; tapping the armed row again disarms.
2. The armed row renders an action row directly BELOW the tile (a sibling
   row, never an overlay — deliberately independent of tile height, see §5
   re #299): one ice-accent button, label **"Find trade suggestions"**,
   testID `league-summary.find-trades-btn` (single static id — only one can
   be visible at a time; the armed row's own id already identifies the
   player).
3. On press:
   - Build `Player` from the `PowerRankedPlayer` row: `{id: player_id, name,
     position, team, age}` (`shared/types.ts:26-40` — all fields optional
     beyond id/name/position).
   - **Side determination:** `selected.tc.team.is_you` → `addGive(player)`
     ("trade away" — it's mine); otherwise `addReceive(player)` ("trade for"
     — it's theirs). `is_you` is server-stamped against the session user
     (`server.py:19155`) and correct on every platform incl. ESPN
     (`server.py:18729`) and the fresh/demo members fallback that works
     around the caller-excluded `sess["league"].members` convention
     (`server.py:18965-18980`) — the client never re-derives ownership.
   - **Pin policy: replace, don't append** — call
     `useFinderTargets.getState().clear()` then `addGive`/`addReceive`
     (recommendation; operator question §9 Q2). Rationale: the feedback says
     "with **that player** preselected"; landing with 1 pin puts the deck in
     the single-pin featured-window mode (:1038-1045) — the strongest
     possible version of "trade suggestions for this player" and it renders
     in guided mode with `trade.asset_ideas` ON with **zero generate tap
     needed**. Appending to stale pins instead lands the user in a 2+-pin
     state with no featured window and a package-mode semantic they never
     chose (#174).
   - Navigate: tab-root variant → `navigation.navigate('Trades',
     {screen:'TradesHome'})` (precedent `LeagueScreen.tsx:367`); legacy
     root-stack variant → `navigation.navigate('Main', {screen:'Trades',
     params:{screen:'TradesHome'}})` (`RootNav.tsx:54`, precedent :230). One
     small helper branching on `isTabRoot` (:362).
   - **No `mode` param.** Deliberate: the single-pin experience (featured
     window + collapsed "Pinned: <name> · Edit · ✕" row with its
     always-visible clear, :3652-3677) renders in guided mode, and #269 hid
     the Guided/Team/Player chips — parking the user in `mode:'player'`
     would strand them in a mode with no chip to leave by. Guided is the
     shipped landing; the pin does the preselecting.

### 4.2 Availability and honest degradation

- **Gate the button on `trade.finder_targeting`** (the flag that controls
  whether pins are ever SENT, :1176-1183) **plus the new
  `league.player_trade_handoff` flag.** If targeting is off, pins are read
  by nobody — rendering the button would be a silent no-op, the exact failure
  class this plan's §1 trap describes.
- **Value-0 rows (out-of-pool K/DEF, deep stashes — `power_rankings.py:16-18`)
  and rows with `tier: null`:** suppress the button (`value > 0` guard). A
  pinned valueless asset generates nothing and the resulting "No trades
  found" toast (:1212-1218) would read as breakage. The armed row still
  toggles (visual consistency); the action row renders a dim caption
  `No market value — can't build suggestions` instead of the button.
  (Operator may prefer hiding entirely — §9 Q5.)
- **Draft-capital items** (the picks group, :1244-1277) get NO press
  affordance in this item — the feedback says "player", and pick-pinning is
  not a `useFinderTargets` capability (`Player`-typed lists only).
- **"Can't honor the preselection" cases:** with the gates above, the only
  residual case is the finder finding nothing for the pin — which the deck
  already answers honestly (asset-ideas empty groups / "No trades found"
  toast). The handoff never needs its own failure UI.
- League switch between arm and tap is impossible (both live on one screen),
  and the store self-clears on league switch anyway
  (`useFinderTargets.ts:62-73`) — no stale-league pin can survive.

### 4.3 What 300-B explicitly does NOT touch

- **No TradesScreen.tsx edit. No TradeDnaSheet edit. No navigation-registry
  edit** (both routes exist; `deepLinks.ts` unchanged — no new route is
  created). No backend call. The entire feature is LeagueSummaryScreen +
  the store the finder already consumes.

---

## 5. File-ownership footprint and sequencing

**Files 300 will touch (all sub-features):**

| File | Why |
|---|---|
| `mobile/src/screens/LeagueSummaryScreen.tsx` | Both sub-features' UI (strip, pressable rows, action row, nav helper) |
| `mobile/src/components/…` (optional) | If the candidates strip is extracted as `TradeCandidatesSection` to keep the screen diff small — Author's call; the screen must still mount it |
| `config/features.json` + `backend/feature_flags.py:284` registry | Two new flags (+ `_comment_*` entries) |
| `backend/analytics_taxonomy.py` | Two new client events + props (§7) |
| `mobile/.maestro/flows/league/05..0N-*.yaml` (+ `scripts/testid-lint-allow.txt`) | Maestro delta (§6) |
| `docs/config-reference.md`, `docs/glossary.md` ("trade candidate"), `living-memory/LLD.md` | Docs (§8) |

**Sequencing (from triage): #300 lands AFTER #299/#302 (LeagueSummaryScreen
owners) and #297/#298 (TradesScreen owners).** Where those could invalidate
this design:

- **#299 (player-tile height halved):** 300-B deliberately survives it — the
  action row is a *sibling row inserted below the pressed tile*, not an
  overlay or an in-tile expansion, so tile height is irrelevant. What #299
  CAN break: the drill-in row markup this plan cites (:1210-1229) will move/
  change shape, so 300-B's Pressable wrapper must be written against
  *post-#299* line reality, and the armed-row visual (border? surface tint?)
  must be re-checked against the shorter tile in a mockup. Do not build 300-B
  from this plan's line numbers if #299 has merged — re-read the drill-in
  block first.
- **#302 (LeagueSummaryScreen, scope unknown at plan time):** same file;
  whatever it does to the chart-card/list region could move 300-A's insertion
  point (between chart card and list). The insertion point is a layout
  decision, not a data decision — the strip's model survives any reshuffle.
- **#297/#298 (TradesHome entry surface):** 300-B's contract with the deck is
  exactly three things: (1) `useFinderTargets` pins are read at generate time
  (:1165-1183), (2) a single pin produces the featured/asset-ideas surface in
  the landing mode (:1038-1045), (3) `navigate('Trades',
  {screen:'TradesHome'})` lands on the deck. If #297/#298 change (2) — e.g.
  replace the single-pin featured window — the handoff still *works* (pin +
  generate) but the landing UX should be re-verified; if they rename the
  landing route (unlikely; #246 kept every call site working), (3) must
  follow. State this contract in the PRD so the #297/#298 QA can check it.

**Conflict surface if built in parallel anyway:** only
`LeagueSummaryScreen.tsx`. The plan's assumption is serial landing per triage;
if the operator re-orders, rebase cost is contained to that one file.

---

## 6. Test plan

Maestro flows in `mobile/.maestro/flows/league/` (family exists: 01-04), id
selectors only (`testid-lint.sh` bans text-taps), per the 23 authoring laws
(`mobile/.maestro/README.md:67-167`). Dynamic ids (`league-summary.player-row.
<player_id>`, `league-summary.candidates.row.<user_id>`) are template
literals → `mobile/scripts/testid-lint-allow.txt` entries naming
LeagueSummaryScreen.tsx (law 4; lint matches static prefixes for dynamic
qualifiers). Flows run against the hermetic QA league (profile `standard`,
deterministic rosters/values); flags via resolved fixture filenames (law 16) —
new fixtures `release+300` (both flags on) and reuse `release` for the
off-state flow. No draft-picks seeding dependency (the league/01-02 Tier-B
blocker does not apply — candidates read positions, not picks).

Every test below names the sabotage it detects — the standard is "fails on a
deliberately broken build", per the pipeline lesson.

| # | Flow | Steps → assertion | Detects (sabotage that makes it FAIL) |
|---|---|---|---|
| T1 | `05-candidates-set-and-order` | Sign in QA league → League tab → tap RB pill → assert `league-summary.candidates` visible; assert row ids for EXACTLY the seeded teams whose RB `posValues` < caller's, in weakest-first order (assert first row's id AND assert a known stronger-than-caller team's row id is `notVisible`) | Comparator flipped (`>` for `<`); sorted by `total_value` instead of `posValues[P]`; caller's own row included; strip built from `activeTotal` (picks folded in — the seeded picks-rich weak-RB team would appear/disappear wrongly) |
| T2 | `05b` (same flow, second phase) | Tap a candidate row → assert drill-in opens for THAT team (`league-summary.focus-caption` + the team name) | Row tap wired to nothing or to the wrong `user_id` |
| T3 | `06-candidates-empty-state` | Filter to the position where the QA caller is seeded weakest → assert `league-summary.candidates.empty` visible and zero `league-summary.candidates.row.*` | Strict-inequality broken (ties rendered as candidates); empty state never renders |
| T4 | `07-handoff-give-side` | Drill into the `is_you` team → tap own player row → assert `league-summary.find-trades-btn` → tap → assert Acquire tab landed (`trades.pin-summary.*` row visible with player name) → **side assertion:** relaunch-free navigate to the deck's player board via the flow's flag fixture with `trades.sheet_targeting: false` so the Player chip renders, enter Player mode, assert `trades.board.away.<player_id>` visible AND `trades.board.for.<player_id>` not visible | `addGive`/`addReceive` swapped; pin never written; nav lands elsewhere. The side assertion crosses the store contract boundary (asserts TradesScreen's *reading* of the pin, not 300-B's own label) — a build that shows the right button copy but pins the wrong side fails here |
| T5 | `08-handoff-receive-side` | Drill into a NON-you team → same as T4 → assert `trades.board.for.<player_id>` visible, `.away.` absent | `is_you` inversion (the classic caller-excluded-members bug class); side hardcoded |
| T6 | `09-flags-off` | Fixture `release` (both flags absent/false) → position filter → assert no `league-summary.candidates`; drill in → tap player row → assert no `league-summary.find-trades-btn` | Unflagged rendering (dark-launch violation) |

Notes for the flow author (laws applied): T4/T5's side assertion needs its own
fixture (`release+300+sheet-targeting-off`) because the shipped chip strip
hides the Player chip; pins are in-memory zustand, so NO relaunch between
handoff and assertion (law 6's `clearState` guidance is for cache, but a
relaunch also wipes the store — order steps in one session). Text asserts are
full-match regex (law 1) — wrap candidate captions in `.*`. Scroll before
below-fold taps with `visibilityPercentage: 100` (law 2) — the candidates
strip sits below the chart card.

Non-Maestro: `cd mobile && npx tsc --noEmit` clean; manual QA pass on an ESPN
league (is_you anchor, §2.1) and demo league; screen-library capture run for
the new states (`league-summary/populated--candidates`, drill-in armed-row) —
the drill-in has no capture today (§2.1), so the mockup phase needs one first.

Sim gate: this is a user-visible mobile change on two screens' flows — runbook
tier matrix (docs/runbook.md § Pre-ship simulator gate) says run at least the
league + trades smoke set (`flows/smoke/05/06/09` + the new league flows);
log in TEST_LEDGER + `qa/sim-runs/last-sim-run.json`.

---

## 7. Analytics spec (against `backend/analytics_taxonomy.py` — DEFAULT-DENY)

`ALLOWED_CLIENT_EVENTS` is a frozenset (:38-99); unknown events are dropped,
unknown props stripped (:149-163); new props require a tracking-plan addendum
first (:159 comment). Nothing existing fits (the closest, `find_trades_tapped`
:51, has an empty props set and means the generate button). **Spec — two new
client events:**

```python
# analytics_taxonomy.py — ALLOWED_CLIENT_EVENTS additions
"league_pos_candidates_viewed",   # 300-A strip rendered (fires once per
                                  # position-selection that produces a strip,
                                  # not per frame)
"league_player_handoff_tapped",   # 300-B "Find trade suggestions" pressed

# CLIENT_EVENT_PROPS additions
"league_pos_candidates_viewed": frozenset({"position", "candidate_count",
                                           "subset", "basis"}),
"league_player_handoff_tapped": frozenset({"side",       # "give" | "receive"
                                           "position",   # pinned player's pos
                                           "from_candidates"}),  # bool: drill-in
                                           # reached via a 300-A row tap
```

Server-side: nothing (the resulting generate is already measured by
`trades_generated`, server-fired :115). Neither event is funnel-critical.
Client fires via the existing `track()` SDK (`api/events.ts`, flag
`analytics.client_events`). A tracking-plan addendum doc accompanies the
taxonomy edit (the NULL-`platform` incident rule: spec BEFORE firing).
`side`'s two values are exactly the store's give/receive vocabulary — no new
cross-client enum (not a cross-client-invariants entry; the strings live in
one client + the taxonomy).

If the operator prefers zero analytics for v1, the waiver must be written into
the scope block explicitly — but the recommendation is to keep both events:
300-A's whole value hypothesis ("do users act on candidates?") is unmeasurable
without `from_candidates` + `league_player_handoff_tapped`.

---

## 8. Scope-block inputs (for `docs/templates/feature-scope.md`)

| Template section | What the Author writes |
|---|---|
| **1. Analytics scope** | The two events + props from §7, verbatim, with the taxonomy + tracking-plan-addendum edits listed as build tasks. No waiver. |
| **2. Schema & flag scope** | No schema change. Two new flags `league.pos_candidates`, `league.player_trade_handoff` — both client-only, default OFF, registered in `feature_flags.py` + `features.json` with `_comment_*` entries; NOT in `LAUNCHED_FLAG_DEFAULTS`. Bright-line note: flag-surface change ⇒ never express-lane. |
| **3. Test scope** | §6's six flows + fixtures + allow-list entries + the sabotage table (copy it — QA reviews against it). tsc clean. Capture-delta: drill-in + candidates states added to the screen library. |
| **4. Docs scope** | `docs/api-reference.md`: **n/a — no route change** (state it row-by-row). `docs/config-reference.md`: two flags — updated. `docs/cross-client-invariants.md`: n/a — no new cross-client enum/color (position hexes reused as data encodings). `docs/architecture.md`/`living-memory/HLD.md`: n/a — no module/wiring change. `living-memory/LLD.md`: **updated** — one convention worth recording: "cross-screen finder preselection goes through `useFinderTargets` (store), never nav params; route-param targeting is dead under `trades.sheet_targeting`". `docs/glossary.md`: "trade candidate" if the operator keeps the label. |
| **5. Ship gate declaration** | Sim tier per §6 (league + trades smoke + new flows); logged in TEST_LEDGER + `last-sim-run.json`. Lands after #297/#298/#299/#302 per triage — restate the file-ownership footprint (§5). |

---

## 9. Risks and open questions for the operator

**Sharpest risk (named again because it will bite a future builder):** the
shipped flag state makes every *param-shaped* preselection path a silent no-op
(`trades.sheet_targeting` ON ⇒ `TradesScreen.tsx:515-519` ignores
`opponentUserId`). 300-B's pin-store design routes around it, but any
"small scope addition" during build that tries to also preselect the *team*
(e.g. from a 300-A row straight into a team-scoped deck) has no working
mechanism today — `sheetOpponent` is component-local state (:497-499). Do not
improvise one mid-build.

Open questions (genuinely open — each changes the build):

1. **Definition sign-off (300-A):** "teams with less P value than YOU, under
   the active subset, position value only" (§3.1). The alternatives are
   documented with reasons; confirm or redirect before the PRD freezes.
2. **Pin policy on handoff (300-B):** replace existing pins (recommended,
   §4.1 — deterministic landing, single-pin featured mode) vs append
   (preserves a user's in-progress pin board; risks a confusing 2-pin landing
   with package-mode semantics). #250's status note shows stale pins were
   deliberately left alone before — replacing is a (small) behavior change to
   that stance.
3. **Does 300-A need a team-level handoff at all** ("weak at RB" row → deck)?
   This plan says v1 row-tap = drill-in (then per-player handoff). A true
   team-scoped handoff needs a TradesScreen-side change (an externally
   settable opponent under `trades.sheet_targeting`) — a #297/#298-owned file
   and a separate item if wanted.
4. **300-A entry trigger:** single-position filter selection (recommended —
   zero new controls) vs an explicit "I want to trade away…" affordance.
   The former shows candidates to *anyone* filtering (including "who's weak
   where I'm weak" browsers); if the operator wants sell-intent framing only,
   the strip needs its own opt-in control and the plan's copy changes.
5. **Value-0 players (300-B):** dim explanatory caption (recommended, §4.2)
   vs suppressing the press affordance entirely.
6. **Label:** "Find trade suggestions" (the feedback's words, recommended) —
   confirm against the deck's existing "Find a Trade" vocabulary; two nearby
   labels for adjacent concepts is a glossary decision.
