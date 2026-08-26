# #362 — Standing offer: broaden a liked 1-for-1 — build plan

> Base: `origin/main` @ `50e0451` (v1.15.0). Plan only — no production code was
> written. **Every `file:line` below was re-verified against `50e0451` in a clean
> worktree.** The operator's own citations were taken from an older tree and have
> drifted; where they differ, the numbers here are the current ones.
>
> Design intent: [`mockups/standing-offer-362/`](../../../../mockups/standing-offer-362/)
> (six sections; §1 embeds the real 2026-08-10 capture, §2–§5 are labelled
> reconstructions, §6 raises the open questions this plan rules on).
> ⚠️ **That mockup is currently UNCOMMITTED** in the operator's working checkout.
> It must be committed before the Author/Build agents start, or their only
> reference to the approved design is this file.

**Report (jonbonjourvi, TradesHome, v1.15.0, 2026-08-19, idea):**

> "Idea on the cycling thru one player for one pick. If you accept hey I'm
> willing to trade Malik Willis for a 2028 1st maybe you just add a label so the
> rest of the league knows he's willing to trade for a first. Or a pop up after
> you say yes to that trade that's like hey I'll sell Willis for a 27 or 28 first
> but not 29 or maybe like a first from any of these rosters but not xyz"

**Operator framing (2026-08-19, verbatim):**

> "Thinking it's simple, if a user accepts a one for one trade offer where they
> are getting a first, they should be prompted to select all other teams they
> would take a first from and all other years they would accept a first from.
> Should be rather straightforward. Team selection and year selection are
> independent of each other. Going through this experience prioritizes showing
> that card to all users associated to the teams the original user selected."

---

## 0. TL;DR — what changed against the mockup

| Mockup §6 proposal | This plan's ruling |
|---|---|
| Bind the offer to the originating pick's value **±1 ladder tier** | **Rejected.** Its premise is factually false — FTF prices every 1st in a league at *exactly the same number*. A value band is unimplementable and unnecessary. §4. |
| Default: source team only + prominent "All" | **Adopted**, with the years row defaulted the same way. §3. Needs an operator confirm (it does not pre-answer his "select all other teams" framing). |
| Injection cap: reserved split (2 organic + 1 standing) | **Adopted in principle, one knob not two constants** — cap stays 3, standing offers take at most `standing_offer_inject_cap` (default 2), drop is counted. §5. |
| Trigger: 1-for-1 + pick + no active offer + not dismissed 2× this session | **Tightened substantially.** The post-like moment already arbitrates ~8 competing surfaces. §6. |
| Expiry: 21 days (floated) | **30 days**, behind a `model_config` knob, stored not derived. §8. |
| Table `standing_offers(… asset_class …)` | Adopted minus `asset_class` (speculative — `round` already carries it). §7. |

Two things the operator asked me to check that turned out differently than
expected are called out inline: the pick-value model (§4) and the crowding of
the post-like moment (§6). Both change the shape of the build.

---

## 1. Current-behavior trace — the receiving half already exists

Confirmed. The operator's read is right; only the line numbers moved.

**A "like" is one exact package.** `POST /api/trades/swipe`
(`backend/server.py:11222`) resolves the card, moves Elo, and writes one
`trade_decisions` row (`backend/database.py:319`) holding the literal
give/receive id lists (`backend/server.py:11360-11367`). Nothing on that row
generalises.

**League-mates' likes are read back on a 90-day window.**
`load_recent_league_likes(league_id, exclude_user_id, days=90)`
(`backend/database.py:5228`) — filters `decision == "like"`,
`retracted_at IS NULL` (#318), ordered `id DESC`, i.e. **newest like first**
(`backend/database.py:5261`).

**The injector mirrors them into the viewer's deck.**
`_inject_likes_you_cards` (`backend/server.py:2931`) →
`_inject_likes_you_cards_impl` (`backend/server.py:2943`). Its match rule, in
order (`backend/server.py:3000-3056`):

1. opponent is a current league member
2. **their give ⊆ their current roster** and **their receive ⊆ the viewer's roster**
3. no untouchable on the viewer's give side (#95)
4. no not-interested on the viewer's receive side (#163)
5. not already swiped (`_past_decision_keys`)
6. not live in the match pipeline (`exclusion_keys`, G6 R4 #336)
7. **D-055 user-gain floor** — `_likes_you_user_delta` ≥ `likes_you_min_user_delta`
   (default −500, `backend/server.py:2900-2911`, knob at `backend/database.py:2254`)

Survivors either flag+boost an existing deck card or synthesize a
`basis="consensus"` TradeCard, both boosted to `max(composite)+1.0`
(`backend/server.py:3060`, `:3088`).

**Cap: `_LIKES_YOU_CAP = 3`** (`backend/server.py:2928`), enforced as a hard
`break` at the top of the loop (`backend/server.py:2999`). **Confirmed: the drop
is silent** — no counter, no log, no event.

**Call site and its gates** (`backend/server.py:5422-5438`): the whole injection
is skipped unless `trade.likes_you` is on, and skipped for `league_demo`,
`pinned_give`, `pinned_receive`, and `opponent_user_id` decks.

**Client render:** `likesYou` (`mobile/src/shared/types.ts:184`) →
`mobile/src/components/TradeCard.tsx:167`, flare "They're interested" pill at
`mobile/src/components/TradeCard.tsx:375-378`.

**Verdict:** #362 widens the match rule feeding this injector. **No new
recipient-side surface.** That is what keeps this item tractable.

### 1a. Picks are real roster assets — the match rule can reach them

Rule 2 above is a roster-containment test, so a standing offer only works if
picks live on rosters. They do: `_inject_owned_picks`
(`backend/server.py:10347`) injects each team's owned picks as `position="PICK"`
pseudo-Players onto `league.members[].roster` and the viewer's roster, from
`_owned_pick_assets` (`backend/server.py:10261`).

Two properties of that injection constrain the design:

- **`pick_id` is `{league}_{season}_{round}_{original_roster}`**
  (`backend/database.py:9120-9129`). Season and round are parseable straight out
  of the id — no join needed to answer "is this a 2027 1st?".
- **Only the top `picks_pool_cap` (default 6) picks per team are injected**
  (`backend/server.py:10251`, knob `backend/database.py:2277`), sorted by priced
  value. For **round 1 this is a non-issue** — firsts price highest and, under
  D-079, all price equally, so every first a team owns is inside the top 6. For
  round 2+ it can silently bite. One more reason §4 scopes v1 to firsts.

Generic ladder rungs (`generic_pick_*`, `backend/pick_values.py:213`) are
explicitly **not** roster assets and can never satisfy an offer. The trigger
must test for an *owned* pick, not merely `position == "PICK"`.

### 1b. FB-46 reconstruction — the prompt must not assume a resolved card

`POST /api/trades/swipe` has a recovery path: when the in-memory deck was lost
to a restart, `_reconstruct_swipe_card` (`backend/server.py:11188`) rebuilds the
card from client-echoed `give_player_ids` / `receive_player_ids` /
`target_user_id`. The rebuilt card carries **zeroed scores and no `lane_shift`**
(`backend/server.py:11206-11216`).

**Requirement R-FB46:** the standing-offer prompt derives its content only from
fields present on *both* the real and the reconstructed card — the give/receive
id lists and `target_user_id`. It must never key off `composite_score`,
`fairness_score`, `basis`, or `likes_you`. The prompt is triggered **client-side
off the card the client already holds**, so it is structurally immune to this
path; the requirement exists so the Author does not "improve" it into a
server-driven response field.

---

## 2. Scope — what v1 is

An offer is: **"I will send player P for any round-`R` pick, in seasons `Y`, from
teams `T`, in this league, until it expires."**

**v1 fixes R = 1 (firsts only).** Jon asked about firsts; the operator's framing
says firsts; the injection cap is only safe for firsts (§1a); and the `round`
column exists so widening to seconds later is a config change, not a schema
change.

**Out of scope, stated so nobody has to guess:** offering *for* a player rather
than a pick ("any 1st" generalises, "any Tyler Warren" does not); multi-asset
packages; a global player badge (see §9); offers to non-members; cross-league
offers.

---

## 3. Open question 1 — default selection

**Ruling: pre-check the source team only, and the source pick's season only.
One prominent "All" per group. The CTA carries the live count.**

The mockup's reasoning is sound and one measured fact makes it safer than it
feared: **a "blast" cannot produce spam at volume.** Even an all-teams offer
yields at most *one* card per league-mate per deck, and each must still clear
roster containment, untouchables, not-interested, the R4 exclusion and the D-055
floor (§1). The blast radius is 11 single cards, not 11 spam streams.

So the argument for source-only is not spam control. It is these three:

1. **Jon's ask is half exclusion.** "a first from any of these rosters but not
   xyz" is explicitly a *negative*. A pre-checked-all sheet makes the thing he
   asked for into the work.
2. **A tap-through must be a no-op, not a broadcast.** With source-only, an
   accidental confirm reproduces exactly today's behavior (the like alone,
   already committed). No other default has that property.
3. **The count is the nudge.** "Broadcast to 1 team" reads visibly weak; "All"
   is one tap away. That is the right gradient.

**Years follow the same rule** for symmetry — the two selections are independent
per the operator, so they should not have asymmetric defaults.

> **OPERATOR CONFIRM (non-blocking).** This does not contradict the framing —
> the user is still "prompted to select all other teams" — but it declines to
> pre-answer. If the operator wants tap-through to broadcast league-wide, flip
> the default; nothing else in this plan changes.

**The years pills come from the league's real horizon, never a hardcoded 3.**
Feedback #355 / D-091 is exactly this defect: a fixed window offered 2029 picks
in leagues with no 2029 picks, and it reached **12.8 % of served cards**. The
horizon is now derived league state (`draft_status.pick_horizon`, 3 classes
anchored at the first undrafted class) and enforced at the writer
(`sync_draft_picks`). **Therefore: build the pill set from the distinct `season`
values present in `all_picks` where `round == 1`.** That is automatically
horizon-correct with zero new endpoint and zero new constant.

**The per-team year annotations** the mockup shows (which selected years each
team still owns a 1st in) come from the same payload. Confirmed:
`GET /api/league/picks` (`backend/server.py:9791`) returns `all_picks` with
`owner_user_id`, `season`, `round` per row (`backend/server.py:9883-9890`),
typed at `mobile/src/api/league.ts:123-170`, fetched by
`getLeaguePicks` (`mobile/src/api/league.ts:174`). No new route.

**Platform gate:** the same payload carries `picks_supported`
(`backend/server.py:9885-9889`) — **false for ESPN leagues with no assigned
picks**. Those leagues can never satisfy a pick offer; the prompt must not fire
there at all (§6, condition 4).

---

## 4. Open question 2 — asset-class granularity

**Ruling: reject the ±1-tier value band. Ship "any 1st, in seasons Y, from teams
T" with no value bound at all. The user's team selection *is* the granularity
control.**

This is the ruling the operator flagged as genuinely hard, so here is the
evidence in full. **The mockup's premise — "FTF's own 8-tier pick ladder prices a
rebuilder's 2027 1st far from a contender's" — is false.**

**Fact 1 — slot is not a pricing input.** `pick_pool_value(round, years_out)`
prices a league pick at "the generic ladder's **Mid** tier of that round"
(`backend/pick_values.py:264-286`). D-090 (2026-08-19) re-examined this and
explicitly **did not overturn it**: "Every pick of a round still prices at the
generic ladder's Mid rung." Slot labels are display-only, pinned by
`test_no_price_moves_with_or_without_an_order`. Whether a 1.01 should outprice a
1.12 is logged **unbuilt** as Q-023 — and D-090 measured that building it would
move 48 of 48 current-year pick values and 38 of 48 tier badges, so it is a
cross-client pricing decision, not something #362 can lean on.

**Fact 2 — year is not a pricing input for firsts.** D-079 (2026-08-19) set
round-1 year decay to **1.00** — `PICK_YEAR_DECAY_DEFAULTS[1] = 1.00`
(`backend/pick_values.py:159-163`), knob `pick_year_decay_r1`
(`backend/database.py:2367`). A 2029 1st now prices *identically* to a 2026 1st.
That was the entire point: 99 of 2048 served cards had been arbitraging one 1st
against another.

**Consequence:** in the default `tier_ladder` pricing mode, **every first in a
league carries exactly the same engine value.** "Any 1st" is not an
approximation of a value class — it *is* one, exactly. A ±1-tier band over a set
of identical values is a no-op that admits everything, and there is no
per-(team, year) first value for it to be relative *to*. It would be code that
looks like a safeguard and does nothing.

**The one caveat, and its answer.** `trade.slot_pricing` is ON
(`config/features.json:186`) and exposes a per-user `market_slots` mode
(default `tier_ladder`, `backend/pick_values.py:333-334`) that prices owned
picks off DynastyProcess's curve by **absolute season and round**
(`backend/pick_values.py:322-331`). In that mode year *does* create a spread —
still not team, since the slot is unresolvable. So a `market_slots` user who
selects a far season could see a card they'd refuse.

That is already handled, and by the mechanism built for exactly this failure:
the **D-055 user-gain floor** runs on every injection
(`backend/server.py:3055`) and was shipped because "a like the VIEWER loses
badly on reads as an insult rather than an opportunity". Standing-offer
injections go through the same code path and inherit it for free.

**What the offer IS bounded by:**

- **Round**, fixed to the originating pick's round — exact, free (parsed from
  `pick_id`), and the only bound the data actually supports.
- **Season set** and **team set**, chosen by the user. Jon's "not xyz" is a
  hand-written team-quality filter. It is a better instrument than any value
  band we could infer, because it encodes what he actually thinks of those
  rosters.
- **D-055**, on the receiving side, unchanged.

**No new gate. No new constant. No new tier math.** This is the surgical answer
and it is the one the data supports.

> **NOT an operator ruling — a finding.** Nothing here needs a decision; it needs
> the operator to know that the "hard" question dissolved once the pricing model
> was read. If Q-023 (per-slot pricing) is ever built, revisit this section —
> that, not #362, is where a value band would belong.

---

## 5. Open question 3 — injection cap

**Ruling: keep one cap of 3. Standing offers may consume at most
`standing_offer_inject_cap` (model_config, default 2), leaving ≥1 slot for
organic likes. Count the drops; do not emit a per-drop event.**

**Why a reservation, when the mockup's own instinct was to keep it simple.**
There is a genuine asymmetry the plain cap cannot absorb. An organic like
generates **one** candidate for **one** deck, once. A standing offer to 11 teams
generates a candidate for **11 decks, continuously, for its whole life.** Under
the current newest-first ordering (`backend/database.py:5261`), a league where
standing offers catch on will see them structurally crowd out organic mirrors.
That is not a hypothetical tuning worry; it follows from the fan-out.

**Why one knob and not two constants.** `_LIKES_YOU_CAP = 3` stays as-is
(`backend/server.py:2928`). Adding a second hardcoded constant would fix the
split at deploy time. A `model_config` key is deploy-free reversible and matches
the convention D-079 set explicitly ("ship the knob" — the risk is in the
number, not the code path). Setting it to 3 reproduces an unreserved cap;
setting it to 0 kills standing-offer injection without touching the flag.

**Drop accounting.** Mirror the existing observability idiom rather than
inventing one: `trade_service._r4_excluded_keys` collects R4-excluded keys for
inspection (`backend/server.py:3043`). Add a parallel counter for cap
drops, split organic vs standing offer, and log it once per job at the existing
injection log site. **Not** an analytics event — one event per dropped card in
a chatty league is high-cardinality server noise for a question a counter
answers.

**Ordering within the standing-offer share:** newest offer first, matching the
existing `id DESC` semantics, so nothing new has to be explained.

---

## 6. Trigger conditions — the ruling that most affects whether this ships well

**The operator's instinct was right and the situation is worse than the mockup
assumed.** I traced `advance('like')` (`mobile/src/screens/TradesScreen.tsx:3947`)
and the post-like branch (`mobile/src/screens/TradesScreen.tsx:4179-4241`). The
moment immediately after a right-swipe is **already arbitrating roughly eight
competing surfaces**:

| Surface | Where |
|---|---|
| First-like celebration (`s6.1` guide step) | `TradesScreen.tsx:4207-4215` |
| Apple review ask (`s6.2` + `maybeAskApple`) | `TradesScreen.tsx:4220-4227`, `:3447` |
| Guide-v2 like chain (`v2RunLikeChain`) | `TradesScreen.tsx:4189-4195` |
| Quick Set prompt | `TradesScreen.tsx:3113` (called `:3355`) |
| First-session adaptation moment | `TradesScreen.tsx:4105-4154` |
| Share affordance (`setLastLikedCard`) | `TradesScreen.tsx:4184` |
| Liked toast (three variants) | `TradesScreen.tsx:4190`, `:4216`, `:4238` |
| Mutual-match modal (from the POST response) | `TradesScreen.tsx:1820-1839` |

The code says the constraint out loud, twice: *"never two overlapping
surfaces"* (`TradesScreen.tsx:4183`, `:4205`). **A ninth surface added without
joining that arbitration is the single most likely way this ships and is then
flagged as annoying.**

**The gate — all must hold:**

1. Flags `trade.standing_offers` **and** `trade.likes_you` are on. (The
   receiving half is gated on the latter at `backend/server.py:5422`; without it
   an offer would be posted into a void.)
2. The like was a **1-for-1**.
3. The **received** asset is an **owned** pick of **round 1** — `position ==
   "PICK"` and the id is not `generic_pick_*` (§1a). Season and round come from
   the `pick_id` (`backend/database.py:9120`).
4. `picks_supported === true` for the league (`backend/server.py:9885`) — ESPN
   without assignments never prompts.
5. The deck is not demo / pinned / opponent-scoped — mirror the injector's own
   gate verbatim (`backend/server.py:5422-5424`), so the prompt can never
   promise an injection the injector will refuse.
6. No live standing offer already exists for `(player, round)` in this league.
7. **This is not the user's first like.** The first-like celebration → `s6.2` →
   Apple-ask chain owns that moment and is a growth surface; do not race it.
8. **No other surface is claiming this swipe** — no quickset prompt shown, no
   adaptation moment, no guide step requested, no mutual match on the response.
   Register in the same arbitration, do not bypass it.
9. **At most one prompt per session, full stop** — stricter than the mockup's
   "not dismissed twice this session".

**On condition 9.** "Twice this session" is weaker than it sounds: a session
counter resets on every app restart, so a user who dismisses and backgrounds the
app is prompted again immediately, forever. Follow the house pattern instead —
the Quick Set prompt (`TradesScreen.tsx:3113-3143`, `:3145-3156`) uses a
**persisted** ladder: one show per session → snooze → exactly one re-offer in
session 2 → retired for good, via `getOnboardingState()` /
`patchOnboardingState()`. **Reuse that ladder as-is.** It is proven on this
exact surface, it survives restarts, and it means "no" eventually means no.

**Where the prompt renders.** The like is already committed by the time the
sheet appears (`swipeMutation.mutate` fires at `TradesScreen.tsx:4165`, the deck
advances at `:4178`). **The sheet can never cost the user their like**, and it
must not block the deck advance — it renders over the next card. Dismiss =
today's behavior exactly.

---

## 7. Data model

New table in `backend/database.py`, following `league_preferences`
(`backend/database.py:987`) and `asset_preferences` (`backend/database.py:1015`)
for shape, and `trade_decisions.retracted_at` (`backend/database.py:335`) for
the revoke idiom:

```python
standing_offers_table = Table("standing_offers", metadata,
    Column("id",             Integer, primary_key=True, autoincrement=True),
    Column("user_id",        String,  nullable=False),
    Column("league_id",      String,  nullable=False),
    Column("player_id",      String,  nullable=False),  # the asset offered OUT
    Column("round",          Integer, nullable=False),  # pick round wanted IN (v1: always 1)
    Column("seasons",        Text,    default="[]"),    # JSON array of ints
    Column("team_user_ids",  Text,    default="[]"),    # JSON array of strings
    Column("source_trade_id",String),                   # provenance: the like that made it
    Column("created_at",     String),                   # ISO UTC
    Column("expires_at",     String),                   # ISO UTC, STORED not derived
    Column("revoked_at",     String),                   # NULL = live
)
```

**Convention checks, all verified:**

- **JSON in `Text` columns is the house precedent** — `league_preferences
  .acquire_positions` / `.trade_away_positions` are `Text, default="[]"` holding
  `["WR","TE"]` (`backend/database.py:992-993`). Follow it; do not reach for a
  join table.
- **Timestamps are ISO strings in `String` columns**, not `DateTime` — every
  table in the module does this (`backend/database.py:335`, `:994`, `:1020`).
- **No `asset_class` column.** The mockup proposed one; there is exactly one
  asset class in v1 and `round` already names it. Guideline 2 (no speculative
  configurability).
- **No `UniqueConstraint`.** `asset_preferences` uses one, but it has no revoke
  concept; a hard constraint here would make "revoke, then re-post" collide.
  Enforce **at most one live offer per (user, league, player, round)** at the
  writer with a `revoked_at IS NULL` predicate — exactly how `trade_decisions`
  handles retraction (`backend/database.py:5167`, `:5259`).
- **Migration:** three-tuple rows appended to `migration_cols`
  (`backend/database.py:2432`) are for *columns on existing tables*; a wholly new
  `Table(...)` is created by the existing `metadata.create_all` path. Verify
  which the Author needs — do not add a column-migration row for a new table.

**`expires_at` is stored, not derived.** A derived expiry would mean a knob
change silently moves the deadline on offers the user was already shown "18 days
left" for. Storing it costs nothing and keeps the manage screen honest.

---

## 8. Expiry

**Ruling: 30 days, via `model_config` key `standing_offer_days` (default 30).**

The like window is 90 days (`backend/database.py:5231`). A standing offer is a
**louder** signal — it is the first thing in FTF that puts a user's intent in
front of other people with no further tap from them — so it should be materially
tighter. 21 (the mockup's float) and 30 are both judgment calls; 30 is chosen
because it is a clean 3× tightening of an existing, understood window and spans
a month of a season without spanning a phase change. It is a knob, so this is a
cheap decision to revisit — consistent with D-079's "ship the knob" reasoning.

**Two expiries, not one:**

- **Time** — `expires_at`, filtered at read.
- **Validity** — an offer whose player has left the sender's roster is dead
  regardless of the clock. The injector already enforces this for free (rule 2,
  `backend/server.py:3010-3012`), so no card is ever generated. **But the manage
  screen must apply the same test**, or it will show a live-looking offer for a
  player the user no longer has. Do not let the two surfaces disagree.

---

## 9. Privacy invariant (hard requirement)

**REQ-PRIV: the recipient learns that they were selected. They never learn who
else was selected, and never who was excluded.**

Jon's "but not xyz" is a **private negative**. Surfacing it starts fights in
real leagues.

Enforcement, stated so it cannot be lost in review:

1. `team_user_ids` **never leaves the server on any recipient-facing payload.**
   It is read only inside the injector's match test.
2. The "Why you're seeing this" line is composed **server-side** from
   `(sender, player, round, seasons)` only. No count, no roster list.
3. The sender-side toast/manage count ("4 teams will see this") is on the
   **sender's own** payloads only.
4. No global "open to 1sts" badge on the player anywhere in the app. Beyond the
   privacy argument, a permanent badge outlives the intent that created it — the
   QB you were shopping becomes the QB you need. The chip is bound to the offer
   record and dies with it. (This is also the mockup's §3 position.)

**One leak that cannot be closed, stated honestly rather than claimed away:**
two league-mates comparing notes — one carrying the card, one not — can infer
exclusion. That is inherent to any targeted broadcast and no payload change
prevents it. It should be acknowledged in the PRD, not engineered around.

---

## 10. Routes

Three, all on the existing `/api/trades/*` prefix. New write routes take
`@_gate_unverified_write`, matching every sibling (`backend/server.py:11223`,
`:14831`).

| Route | Method | Notes |
|---|---|---|
| `/api/trades/standing-offer` | POST | create. Body `{league_id, player_id, round, seasons[], team_user_ids[], source_trade_id}`. Validates: member-ids only, seasons within the league's real pick horizon, round == 1 in v1, at most one live offer per (user, league, player, round). |
| `/api/trades/standing-offers` | GET | list the caller's live + expired offers for the manage surface. |
| `/api/trades/standing-offer/revoke` | POST | body `{offer_id}` → `revoked_at = now`. |

**POST for revoke, not DELETE** — matches `/api/trades/awaiting/dismiss`
(`backend/server.py:14830`), the nearest sibling, which is also a
"retract my own outbound intent" operation.

**Injector change** — one predicate, inside
`_inject_likes_you_cards_impl` (`backend/server.py:2943`): union the exact-mirror
candidate list with standing-offer candidates. A standing offer of
`(sender S, player P, round R, seasons Y, teams T)` yields a candidate for
viewer V when `V ∈ T`, `P ∈ S.roster`, and V holds ≥1 owned pick with
`round == R` and `season ∈ Y`. **Every downstream rule (untouchables,
not-interested, `_past_decision_keys`, R4 exclusion, D-055) applies unchanged.**
That reuse is the whole reason this item is small; do not fork the loop.

---

## 11. Flag, analytics, config

**Flag `trade.standing_offers`, default OFF** → `config/features.json` +
`backend/feature_flags.py` `FLAG_KEYS` (`backend/feature_flags.py:89` is the
`trade.likes_you` neighbour) + `docs/config-reference.md`. Graduation: operator
TestFlight pass on a real 12-team Sleeper league.

**model_config keys** → `backend/database.py` `_MODEL_CONFIG_DEFAULTS` (`backend/database.py:2157`) +
`docs/config-reference.md`:

| Key | Default | Purpose |
|---|---|---|
| `standing_offer_days` | 30 | expiry window (§8) |
| `standing_offer_inject_cap` | 2 | max of the 3 injection slots (§5) |

**Analytics — five events**, registered in `backend/analytics_taxonomy.py`
(`ALLOWED_CLIENT_EVENTS` at `:38` for the mobile ones, `SERVER_FIRED_EVENTS` at
`:494` for the server one), with props in `CLIENT_EVENT_PROPS` (`:627`), **and
classified in `analytics_queries.NON_INTENT_EVENTS`
(`backend/analytics_queries.py:63`) in the same commit** — the CLAUDE.md rule,
and the reason the NULL-`platform` incident is cited in the gates.

| Event | Props | Fires when | Client | Intent? |
|---|---|---|---|---|
| `standing_offer_prompted` | `round`, `seasons_offered` (count) | sheet shown | mobile | non-intent |
| `standing_offer_posted` | `round`, `seasons` (count), `teams` (count), `used_all_teams` (bool) | POST succeeds | mobile | **intent** |
| `standing_offer_skipped` | `snoozed` (bool) | "Just this one trade" | mobile | non-intent |
| `standing_offer_card_shown` | `round` | a standing-offer card is injected | server | non-intent |
| `standing_offer_revoked` | `age_days` | revoke succeeds | mobile | **intent** |

Counts only, never id lists — low cardinality, matching the `mock_*` family's
stated convention (`backend/analytics_taxonomy.py:1016-1020`).

---

## 12. File ownership

| File | Change | Collision risk |
|---|---|---|
| `backend/database.py` | `standing_offers_table` + loader/writer/revoke helpers; 2 `model_config` defaults | **shared registry** — append in one block |
| `backend/server.py` | 3 routes; the injector predicate + cap split (`:2943`, `:2999`) | **shared** — §10 is one predicate; keep it surgical |
| `backend/feature_flags.py` | `trade.standing_offers` in `FLAG_KEYS` | append-only |
| `backend/analytics_taxonomy.py` | 5 events + props | append-only |
| `backend/analytics_queries.py` | 3 non-intent classifications | append-only |
| `config/features.json` | flag + `_comment_` block | append-only |
| `mobile/src/api/trades.ts` | 3 client fns | low |
| `mobile/src/screens/TradesScreen.tsx` | trigger gate + sheet mount + offer chip | **HIGH — 7,563 lines, see §13** |
| `mobile/src/components/StandingOfferSheet.tsx` | **new** | none |
| `mobile/src/components/TradeCard.tsx` | "Why you're seeing this" line + chip slot | low |
| `mobile/src/screens/MatchesScreen.tsx` | third segment (§14) | medium |
| `mobile/tests/check-standing-offer-362.js` + `mobile/package.json` script | **new** | none |
| `backend/tests/test_standing_offers.py` | **new** | none |
| `docs/feedback/items/362-standing-offer/*` | scope block, plan, PRD, status, QA checklist | none |

**Docs table (row-by-row, per CLAUDE.md gate 3):**

| Doc | Verdict |
|---|---|
| `docs/api-reference.md` | **updated** — 3 new routes |
| `docs/data-dictionary.md` | **updated** — `standing_offers` |
| `docs/config-reference.md` | **updated** — 1 flag, 2 `model_config` keys |
| `living-memory/LLD.md` | **updated** — one line: the likes-you match rule is now a union of exact mirrors and standing offers |
| `docs/architecture.md` / `living-memory/HLD.md` | **n/a** — no new module or client; one predicate inside an existing injector |
| `docs/cross-client-invariants.md` | **n/a** — no shared constant, color, or enum crosses clients |
| `docs/glossary.md` | **updated** — "standing offer" |
| `DECISIONS.md` | **recorded item-scoped as D-362-1** (origin/main took the sequential ids before ship; see hld-delta.md §9). Subject: *the offer is bounded by round and by the user's own team selection, not by a pick-value band, because FTF prices every first in a league identically* (§4). |

---

## 13. Collision with feedback #360

**I could not verify #360 from the repo.** There is no `docs/feedback/items/360-*`
directory, and `git grep` for `#360` across `docs/feedback` and `docs/plans`
returns nothing in **either** this worktree (`origin/main` @ `50e0451`) or the
operator's working checkout. The analysis below reasons from the operator's
one-line description ("an 'Avoiding positions' feature being planned in
parallel") and should be re-checked once #360 has artifacts.

**The operator's expectation is correct: both will want `TradesScreen.tsx`.**

**Likely #360 shape.** "Avoiding positions" maps almost exactly onto columns
that **already exist**: `league_preferences.acquire_positions` /
`trade_away_positions` (`backend/database.py:992-993`), read into generation at
`backend/server.py:5180-5187` and passed through at `:5355-5356`, with routes at
`backend/server.py:15381` (GET) / `:15447` (POST). If #360 is built on those, its backend work
is in `trade_service` generation and a preferences UI — **disjoint from every
backend file #362 touches except the shared registries.**

**Certain collisions — all append-only registries.** `config/features.json`,
`backend/feature_flags.py` `FLAG_KEYS`, `backend/analytics_taxonomy.py`,
`backend/analytics_queries.py` `NON_INTENT_EVENTS`, `backend/database.py`
(defaults/migration lists), `docs/api-reference.md`, `docs/config-reference.md`.
These merge cleanly **provided each agent appends its own contiguous block** and
neither reformats a neighbour. Say this to both build agents explicitly.

**The real one — `mobile/src/screens/TradesScreen.tsx` (7,563 lines).** If #360
adds any deck-side filter chip or empty-state, both agents edit this file.
Proposed split, by region:

- **#362 owns** the `advance()` post-like branch
  (`TradesScreen.tsx:4179-4241`) and the prompt-arbitration state it adds.
- **#360 owns** the deck-filter / lane-chip region and the preferences plumbing.
- **Neither** touches `swipeMutation` (`:1795-1893`) or the guide/Apple chain
  (`:3432-3490`) without coordinating.

If the two land in the same wave, sequence them (#362 second — it has the
smaller, more localised diff in this file) rather than merging in parallel.

**One genuine product interaction to name, not just a merge conflict:** if #360
lets a user say "I'm avoiding QBs", and #362 lets a league-mate broadcast "I'll
send my QB for a 1st", the standing-offer injection must respect the *recipient's*
avoidance. It already does, structurally: the not-interested filter runs on the
viewer's receive side inside the same loop (`backend/server.py:3021`), and
standing offers reuse that loop (§10). **Whoever ships second should add a test
asserting it, and should not rebuild the filter.**

---

## 14. Revocation surface

**Verified: `mobile/src/screens/MatchesScreen.tsx` exists (1,650 lines) and is
the right home.**

It already carries two segments — `type Segment = 'mutual' | 'awaiting'`
(`MatchesScreen.tsx:67`) — and the "Awaiting them" segment is *precisely the
existing analogue*: the user's own outbound likes that haven't been mirrored,
backed by `GET /api/trades/awaiting` (`backend/server.py:14739`) and revocable
via `POST /api/trades/awaiting/dismiss` (`backend/server.py:14830`), which
retracts the underlying like rows. A standing offer is the generalised version
of exactly that row.

**Add a third segment**, `'standing'`, alongside the existing two. Not Settings
— this is content, not configuration (and D-089 already made Settings a pushed
page, a different information architecture). The list shows player → round,
seasons, team count, days left, and Edit/Revoke; expired offers group separately
with a Repost affordance.

**Note for the Author:** `MatchesScreen.tsx` currently mounts no `FeedbackFAB`
(verified — no match in the file), so it is presumably covered by the RootNav
tab-stack mount per CLAUDE.md #188. Do not add one; confirm the RootNav mount
covers the new segment.

---

## 15. Evidence plan (D-056 — Maestro and the simulator are retired)

No Maestro flows. No sim runs. No `screens/` captures.

**Backend unit — `backend/tests/test_standing_offers.py` (new file, so no
collision with another agent's test ownership):**

1. Create → the row is live; a second create for the same
   `(user, league, player, round)` is refused while the first has
   `revoked_at IS NULL`; it succeeds after revoke.
2. A season outside the league's pick horizon is rejected (the #355 / D-091
   regression class).
3. A `team_user_id` that is not a current league member is rejected.
4. **Injector:** a standing offer produces a card for a selected team that holds
   a matching pick; **no** card for a non-selected team that holds one; **no**
   card for a selected team that holds none.
5. **Injector inherits every existing rule** — untouchable on the give side,
   not-interested on the receive side, `_past_decision_keys`, R4 exclusion, and
   the D-055 floor each independently suppress a standing-offer card.
6. **Cap split:** with 5 eligible candidates (3 standing, 2 organic), exactly 3
   inject and at least 1 is organic; the drop counter reports 2.
7. **Expiry:** an offer past `expires_at` injects nothing; an offer whose player
   left the sender's roster injects nothing.
8. **REQ-PRIV:** the recipient-facing card payload contains no `team_user_ids`
   and no team count — asserted on the serialized dict, not the object.

**Structural — `mobile/tests/check-standing-offer-362.js` + a
`test:standing-offer-362` script in `mobile/package.json`** (dependency-free
node, matching the 60 existing suites):

1. The trigger gate in `TradesScreen.tsx` tests all nine §6 conditions, and the
   prompt is registered in the same arbitration as the quickset prompt (no
   direct `setVisible` bypass).
2. The persisted snooze ladder uses `patchOnboardingState`, not a module-scoped
   session flag.
3. The years pill set is built from `all_picks` seasons, with no hardcoded year
   or year-count literal anywhere in the sheet.
4. The five analytics event names in the client cross-check against
   `backend/analytics_taxonomy.py` (the pattern `check-league-candidates-300.js`
   §1 already uses for flags).
5. `team_user_ids` appears in no recipient-facing render path.
6. `testID`s added pass `mobile/scripts/testid-lint.sh` (still in CI).

**Code-walk proof (written into `status.md`, file:line-cited):** the trigger
gate traced through `advance('like')` showing it cannot fire during any of the
eight competing surfaces in §6; and the injector predicate traced showing every
pre-existing filter still runs on standing-offer candidates.

**Manual TestFlight checklist (operator) — the only runtime evidence mobile
gets.** Numbered, on a real 12-team Sleeper league:

1. Swipe right on a 1-for-1 where you receive a first → sheet appears **after**
   the deck has advanced; the like is already banked (check Matches → Awaiting).
2. Dismiss with "Just this one trade" → nothing posts; Matches → Standing offers
   is empty.
3. Repeat in the same session → **no second prompt** (one per session).
4. Force-quit, relaunch, repeat → prompt appears once more, then snooze retires
   it per the quickset ladder.
5. Post an offer for 2 seasons × 3 teams → toast names "3 teams"; the chip
   `Open to 1sts · '27–'28` appears on matching cards in your own deck.
6. On a **selected** team's account: the card appears with the flare "They're
   interested" pill and the "Why you're seeing this" line naming the player,
   round and seasons — **and no team names or counts**.
7. On a **non-selected** team's account: no card.
8. Revoke from Matches → Standing offers → the selected team's next deck no
   longer carries the card.
9. Swipe right on a 1-for-1 receiving a **player** (not a pick) → no prompt.
10. Repeat step 1 in an ESPN league with no assigned picks → no prompt.

**Pre-ship gate:** `pytest backend/tests` green (baseline **3,480 passed, 1
skipped** on clean `origin/main` per `living-memory/TEST_LEDGER.md:68`),
`tsc --noEmit`, `testid-lint.sh`, and `mobile/tests/check-*.js` (60 passing,
`TEST_LEDGER.md:139`). Evidence logged in `TEST_LEDGER.md`.
`githooks/pre-push` still enforces the retired simulator marker — set
`FTF_SKIP_SIM_GATE=1` and note the evidence run instead (standing posture under
D-056).

---

## 16. Gate posture

New table + 3 new routes + new flag + 5 new analytics events. Per CLAUDE.md
§Feature gates this is squarely the **bright line** — **not express lane**, and
no agent may self-select it. Required before any code:

1. **Scope block** — `docs/templates/feature-scope.md` → this directory's
   `scope.md`. Every section answered or explicitly waived; waivers surfaced to
   the operator.
2. **Evidence delta** — §15.
3. **Docs table** — §12, filled row-by-row.
4. **Pre-ship gate** — §15 close.

---

## 17. Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | The prompt reads as a nag and the feature is flagged | §6's nine conditions + the persisted quickset ladder; `standing_offer_prompted` ÷ `standing_offer_posted` is the metric that answers it |
| R2 | Standing offers crowd organic likes out of the deck | §5's reserved slot + drop counter; `standing_offer_inject_cap = 0` kills it without a flag flip |
| R3 | A user broadcasts more widely than intended | §3's source-only default; the CTA count; revoke in Matches |
| R4 | The offer generates cards the sender would refuse | §4: D-055 already gates the viewer side; round is fixed; team/season selection is the sender's own instrument |
| R5 | Seasons offered that the league does not have picks for (#355 class) | §3: pills derive from `all_picks`, which D-091 keeps horizon-correct at the writer |
| R6 | A private negative leaks | §9 REQ-PRIV, with a structural test (§15 backend #8, structural #5) |
| R7 | `TradesScreen.tsx` merge conflict with #360 | §13's region split; sequence rather than parallelise |
| R8 | The mockup is lost before build | It is uncommitted — commit `mockups/standing-offer-362/` before handing off |

---

## 18. Open items needing an operator ruling

| # | Item | Default if no ruling |
|---|---|---|
| **O1** | **Default selection** (§3): source-team-and-source-season only, vs. pre-check everything. Slightly declines to pre-answer the "select all other teams" framing. | Source-only ships |
| **O2** | **Expiry** (§8): 30 days. A judgment call, not a derivation. | 30 days ships; it is a knob |
| **O3** | **v1 scope = firsts only** (§2). Jon and the operator both said firsts; the injection cap is only safe for firsts. Seconds are a later config change. | Firsts only |

**Not a ruling — a finding the operator should see (§4):** the "genuinely hard"
asset-class question dissolves on inspection. FTF prices *every first in a
league identically* — D-090 keeps slot out of pricing, D-079 made round-1 year
decay flat. There is no value spread for a ±1-tier band to bound, so the mockup's
proposal is rejected and no new gate is built. If Q-023 (per-slot pick pricing)
is ever built, this section is what to revisit.

**Correction to a lead:** D-090 is committed to `feat/pick-slot-labels` and
**not merged** (`DECISIONS.md` D-090, Status line). It is display-only and does
not affect this plan either way, but the Author should not assume slot labels
are live on `main`.
