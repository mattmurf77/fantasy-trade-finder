# PRD — #362 Standing offer: broaden a liked 1-for-1

> **Date:** 2026-08-19 · **Entry point:** feedback #362 (jonbonjourvi, TradesHome, v1.15.0, idea)
> **Base:** `origin/main` + `f68eddd` · **Flag:** `trade.standing_offers`, default OFF
> **Inputs:** [`plan.md`](plan.md) (Planner, citations re-verified) · [`mockups/standing-offer-362/`](../../../../mockups/standing-offer-362/) (approved design)
> **Design deltas:** [`lld-delta.md`](lld-delta.md) · [`hld-delta.md`](hld-delta.md) · **Gate posture:** [`scope.md`](scope.md)
>
> Every `file:line` in this document was verified against this worktree on 2026-08-19.

---

## 1. The ask

Jon:

> "If you accept hey I'm willing to trade Malik Willis for a 2028 1st maybe you just add
> a label so the rest of the league knows he's willing to trade for a first. Or a pop up
> after you say yes … I'll sell Willis for a 27 or 28 first but not 29 or maybe like a
> first from any of these rosters but not xyz"

Operator framing (2026-08-19):

> "if a user accepts a one for one trade offer where they are getting a first, they should
> be prompted to select all other teams they would take a first from and all other years
> they would accept a first from … Team selection and year selection are independent of
> each other. Going through this experience prioritizes showing that card to all users
> associated to the teams the original user selected."

**What we are building.** After a user right-swipes a 1-for-1 where they receive a
first-round pick, a sheet asks which *other* seasons and which *other* teams they would
take a first from. Confirming writes a **standing offer** — "I will send player P for any
round-1 pick, in seasons Y, from teams T, in this league, for 30 days" — which widens the
match rule feeding the **existing** likes-you injector so the selected teams see that
trade near the top of their deck.

**Why it is small on the receiving end.** No new recipient surface. The likes-you
machinery already exists end to end: `load_recent_league_likes`
(`backend/database.py:5228`) → `_inject_likes_you_cards_impl` (`backend/server.py:2943`)
→ the flare "They're interested" pill (`mobile/src/components/TradeCard.tsx:375-378`),
capped at `_LIKES_YOU_CAP = 3` (`backend/server.py:2928`). #362 adds one predicate to
that loop.

---

## 2. Decisions taken before build (do not relitigate)

| # | Decision | Where it came from |
|---|---|---|
| D-a | **No value gate.** The offer is bounded by round, by the user's own season/team selection, and by the existing D-055 floor. The mockup §6 "±1 ladder tier" premise is **factually wrong** and is corrected in the mockup. | Orchestrator ruling, 2026-08-19; evidence in §3 below |
| D-b | **Injection cap: one knob.** `_LIKES_YOU_CAP = 3` unchanged; standing offers take at most `standing_offer_inject_cap` (default 2). Drops counted via the `_r4_excluded_keys` idiom, **not** a per-drop analytics event. | Orchestrator ruling |
| D-c | **Expiry 30 days**, stored on the row, knob-backed (`standing_offer_days`). | Orchestrator ruling |
| D-d | **v1 = FIRSTS ONLY** (`round == 1`). | Orchestrator ruling |
| D-e | **Year pills derive from the seasons present in `all_picks`.** Never a hardcoded window — that is exactly the #355 defect D-091 fixed at the writer. | Orchestrator ruling |
| D-f | **Privacy is requirement R-19**, not a note. | Orchestrator ruling |
| D-g | **Default selection: SOURCE-ONLY.** Confirmed by the operator 2026-08-19. Rationale: an unedited tap-through reproduces today's behavior exactly (one team — the same reach a plain like already has), and the CTA count ("Broadcast to 1 team") makes an unedited tap *visibly weak*, which nudges toward a real choice rather than an accidental league-wide blast. Variant (b) (pre-check-all) stays specced behind one named constant — the operator weighed it explicitly and may revisit if uptake is low. See **R-6**. | Operator, 2026-08-19 |

### 3. The value-gate finding, stated once so nobody rebuilds it

The mockup's §6 claim — *"FTF's own 8-tier pick ladder prices a rebuilder's 2027 1st far
from a contender's"* — is false in the shipped pricing model:

- **Slot is not a pricing input.** `pick_pool_value` prices every league pick at the
  generic ladder's **Mid** rung of its round (`backend/pick_values.py:264-286`). D-090
  re-examined this and did not overturn it; per-slot pricing is logged **unbuilt** as
  Q-023.
- **Year is not a pricing input for firsts.** D-079 set `PICK_YEAR_DECAY_DEFAULTS[1] =
  1.00` (`backend/pick_values.py:159-163`, knob `pick_year_decay_r1` at
  `backend/database.py:2367`). A 2029 1st prices identically to a 2026 1st.

**Consequence:** in the default `tier_ladder` mode every first in a league carries exactly
the same engine value. A ±1-tier band over a set of identical values admits everything —
it would be code that looks like a safeguard and does nothing. The one exposure is a
`market_slots` user (`config/features.json` `trade.slot_pricing`,
`backend/pick_values.py:322-334`), whose far seasons *do* spread — and that is already
caught by the **D-055 user-gain floor**, which standing-offer candidates inherit for free
because they run through the same loop (`backend/server.py:3055`).

If Q-023 is ever built, revisit this section. Nothing else.

---

## 4. Requirements

Each requirement has a **pass criterion** that is mechanically checkable — a named unit
test, a named structural assertion, or a numbered manual step. `UT-n` = backend pytest in
`backend/tests/test_standing_offers.py`. `SC-n` = assertion in
`mobile/tests/check-standing-offer-362.js`. `MT-n` = manual TestFlight step (§8).
`CW-n` = code-walk proof section (§7.3).

### 4.1 Trigger — when the prompt may fire

**R-1 — The prompt fires only when ALL eleven conditions hold.**

| # | Condition | Source of truth |
|---|---|---|
| 1 | `trade.standing_offers` is on **and** `trade.likes_you` is on | client flag store; the receiving half is gated on the latter at `backend/server.py:5422` |
| 2 | `trade.picks_in_pool` is on | `backend/server.py:10240-10248` — with it off, picks are not roster assets and the injector can never match |
| 3 | The like was a **1-for-1** (`give.length === 1 && receive.length === 1`) | the card the client already holds |
| 4 | The received asset is an **owned league pick**: `receive[0].position === 'PICK'` **and** `receive[0].id.startsWith(\`${leagueId}_\`)` | id format `{league_id}_{season}_{round}_{original_roster_id}` (`backend/database.py:9120-9129`); generics are `generic_pick_*` (`backend/pick_values.py:213`) and fail the prefix test |
| 5 | That `pick_id` resolves in `all_picks` with `round === 1` | `GET /api/league/picks` → `OwnedPick.round` (`mobile/src/api/league.ts:123-170`). **The `all_picks` lookup is the authority; the id prefix in #4 is only a cheap pre-filter.** Do not parse season/round out of the id in client code. |
| 6 | `picks_supported === true` for the league | `backend/server.py:9885-9889` — ESPN leagues with no assigned picks never prompt |
| 7 | The deck is not demo / pinned-give / pinned-receive / opponent-scoped | mirror `backend/server.py:5422-5424` verbatim |
| 8 | No **live** standing offer already exists for `(player_id, round)` in this league | the cached `GET /api/trades/standing-offers` list |
| 9 | This is **not** the user's first like | `!getOnboardingState().celebrationsShown.first_like` is FALSE, i.e. the first-like celebration → `s6.2` → Apple-ask chain (`TradesScreen.tsx:4207-4227`) already owns that moment |
| 10 | **No other surface is claiming this swipe** — no quickset prompt shown, no adaptation moment, no guide step requested, no mutual match on the swipe response | `TradesScreen.tsx:4183`, `:4205` say the constraint out loud: *"never two overlapping surfaces"* |
| 11 | At most **one prompt per session**, and the persisted snooze ladder (R-3) permits it | R-3 |

> **Data availability is fail-closed.** Conditions 5, 6 and 8 need `getLeaguePicks` and
> `getStandingOffers`. Both are prefetched when the deck loads and the flag is on. If
> either is unresolved at swipe time the prompt **does not fire** — the swipe surface
> never blocks on a spinner. A missed prompt is free; a stalled swipe is not.

*Pass:* `SC-1` asserts all eleven conditions appear in the gate and that the gate has no
early `return true`. `CW-1` traces `advance('like')` (`TradesScreen.tsx:3947`, post-like
branch `:4179-4241`) showing the prompt cannot fire during any of the eight competing
surfaces. `MT-1`, `MT-9`, `MT-10`.

**R-2 — The prompt joins the existing arbitration; it does not bypass it.**
The sheet is opened through the same one-surface-at-a-time bookkeeping the Quick Set
prompt uses, not by a bare `setVisible(true)` from inside `advance()`.

*Pass:* `SC-2` asserts the sheet's visibility state is set in exactly one function, that
this function performs the R-1 checks, and that no other call site sets it. Sabotage it
detects: a second `setStandingOfferVisible(true)` added later that skips the gate.

**R-3 — Dismissal uses the persisted ladder, not a session counter.**
Mirror `maybeShowQuicksetPrompt` / `snoozeQuicksetPrompt`
(`TradesScreen.tsx:3113-3143`, `:3145-3156`): one show per session → snooze → exactly one
re-offer once `sessionCount >= 2` → retired for good. New persisted keys on
`OnboardingPersisted` (`mobile/src/state/useOnboardingState.ts:16-92`):
`standingOfferPromptShows`, `standingOfferPromptSnoozed`,
`standingOfferPromptSession2Shown`, `standingOfferPromptRetired`.

A session counter alone resets on every cold start, so a user who dismisses and
backgrounds the app is prompted again forever. "No" must eventually mean no.

*Pass:* `SC-3` asserts the four keys exist in `useOnboardingState.ts` DEFAULTS **and** are
read/written via `getOnboardingState()` / `patchOnboardingState()`, and that the retire
branch matches quickset's. Sabotage: a module-scoped `let shown = false` used as the only
gate. `MT-3`, `MT-4`.

### 4.2 The sheet

**R-4 — Year pills derive from the league's real pick horizon.**
The pill set is the sorted distinct `season` values present in `all_picks` where
`round === 1`. No hardcoded year literal, no hardcoded year *count*, anywhere in the sheet
or its helpers.

This is the #355 defect class: a fixed 3-year window offered 2029 picks in leagues with
no 2029 picks and reached 12.8% of served cards. D-091 made `all_picks` horizon-correct at
the writer (`sync_draft_picks`), so deriving from it is correct by construction and needs
no new endpoint and no new constant.

*Pass:* `SC-4` asserts the sheet source (comment-stripped) contains no 4-digit year
literal in the range 2020-2099 and no `slice(0, 3)`-style window, and that the pill array
is derived from an `all_picks`-sourced value. `MT-10`.

**R-5 — The teams grid lists every other league member, annotated from `all_picks`.**
Rows come from `GET /api/league/members` (`mobile/src/api/league.ts:225-242`) minus the
caller — **not** from `all_picks`, so a team that owns no first still appears and can be
seen to own none. Each row's trailing annotation is the set of *currently selected*
seasons in which that member owns a round-1 pick, from `all_picks`
(`owner_user_id`, `season`, `round`); a member with none renders `—`.

*Pass:* `SC-5` asserts the member list is sourced from the members query and the
annotation from the picks query, and that the two are not conflated. `MT-5`.

**R-6 — Default selection state, one named constant.**

```ts
// mobile/src/components/StandingOfferSheet.tsx
export type StandingOfferDefaultSelection = 'source-only' | 'all';
/** R-6 — flipping this to 'all' is the entire change for variant (b). */
export const STANDING_OFFER_DEFAULT_SELECTION: StandingOfferDefaultSelection = 'source-only';
```

The sheet takes an optional prop `defaultSelection?: StandingOfferDefaultSelection` whose
default value is that constant. Nothing else branches on the variant.

- **R-6(a) — `'source-only'` — SHIPPED DEFAULT (operator-confirmed 2026-08-19).**
  Exactly one season pill is pre-checked (the season of the pick in the card just liked)
  and exactly one team row is pre-checked (that card's `target_user_id`). Each group
  carries a prominent **All** affordance. The CTA reads the live count.
- **R-6(b) — `'all'` — specced, not shipped.** Every season pill and every team row
  arrives checked. The source season and source team keep their `FROM THIS OFFER`
  caption. The **All** affordance becomes **None**. No other behavior differs.

Why (a) ships: an unedited tap-through under (a) reproduces today's behavior exactly — one
team, the same reach the plain like already has — so an accidental confirm is a no-op
rather than a league-wide broadcast. And Jon's ask is half *exclusion* ("a first from any
of these rosters but **not xyz**"); pre-checking everything makes the thing he asked for
into the work. The count in the CTA ("Broadcast to 1 team") is the nudge.

*Pass:* `SC-6` asserts (i) the constant exists and equals `'source-only'`, (ii) the prop
defaults to it, (iii) exactly one `if`/ternary in the sheet reads it, and (iv) neither
`'source-only'` nor `'all'` appears as a bare string anywhere else in the file. Sabotage:
a second hardcoded default in the parent that would survive flipping the constant. `MT-1`.

**R-7 — Independence, and a first-class exit.**
Season selection and team selection never constrain each other: toggling a season may
change a team row's *annotation* but never its checked state, and toggling a team never
changes any season pill. The sheet renders two flat multi-selects, never a matrix.

"Just this one trade" dismisses with **today's exact behavior** — the like is already
committed by the time the sheet appears (`swipeMutation.mutate` fires at
`TradesScreen.tsx:4165`, the deck advances at `:4178`). The sheet renders over the *next*
card and must never block the deck advance. **The sheet can never cost the user their
like.**

*Pass:* `SC-7` asserts the deck-advance call is not inside any standing-offer branch and
that the season and team state setters do not reference each other. `CW-2`. `MT-2`.

**R-8 — Confirm posts the offer and shows the count.**
The CTA is disabled when zero teams or zero seasons are selected. On success a toast reads
`Standing offer posted` / `{n} teams will see {player} for a 1st. Manage it in Matches →
Standing offers.` — the sender's own count, on the sender's own device (see R-19).

*Pass:* `UT-1`, `SC-8` (the toast body reads `team_count` from the POST response, not a
client-side length), `MT-5`.

### 4.3 Sender-side surfaces

**R-9 — The offer chip on the sender's own matching cards.**
A card in the *sender's own* deck whose give side contains the offered player and whose
receive side contains a round-1 pick in an offered season carries the chip
`Open to 1sts · '27–'28` (ice accent — this is an action-state marker on the user's own
commitment). Server-stamped, so no client-side join: `standing_offer_mine: {round,
seasons}` is set by `_stamp_own_standing_offers` and serialized by `trade_card_to_dict`
(see `lld-delta.md` §5).

The chip is bound to the offer record and dies with it. **No global "open to 1sts" badge
on the player anywhere in the app** — a permanent badge outlives the intent that created
it (the QB you were shopping becomes the QB you need), and it would leak the offer to
every league-mate including the excluded ones.

*Pass:* `UT-9` (stamp present on a matching card, absent on a non-matching one, absent
when the flag is off). `SC-9` asserts no player-level badge component reads standing-offer
state. `MT-5`.

**R-10 — Manage surface: a third segment on Matches.**
`type Segment = 'mutual' | 'awaiting'` (`mobile/src/screens/MatchesScreen.tsx:67`) gains
`'standing'`. Rows show player → round, seasons, team count, days left, and **Revoke**.
Expired offers group separately, read-only.

> **Deliberate deviation from mockup §5.** The mockup shows **Edit** on active rows and
> **Repost** on expired ones. Both are out of v1. *Edit* would need a fourth route and a
> second entry point into the sheet outside the post-like moment; revoke-then-repost
> achieves the same result with zero new surface, and the writer's one-live-offer rule
> (R-16) makes that sequence safe. *Repost* has the same problem. Neither is load-bearing
> for the ask. Revisit once the flag has graduated.

Not Settings: this is content, not configuration (and D-089 already made Settings a pushed
page — a different information architecture). `MatchesScreen.tsx` mounts no `FeedbackFAB`;
it is covered by the RootNav tab-stack mount per CLAUDE.md #188. **Do not add one** —
confirm the RootNav mount covers the new segment.

*Pass:* `SC-10` asserts the `Segment` union has exactly three members and the standing
segment renders no Edit/Repost control. `MT-8`.

**R-11 — The manage screen and the injector agree on what is live.**
An offer whose player has left the sender's roster is dead regardless of the clock — the
injector already enforces this for free via roster containment
(`backend/server.py:3010-3012`). `GET /api/trades/standing-offers` applies the **same**
test and returns `stale: true` on such rows so the list never shows a live-looking offer
for a player the user no longer has.

*Pass:* `UT-7`.

### 4.4 Recipient side

**R-12 — The injector's match rule is widened, not forked.**
A standing offer `(sender S, player P, round R, seasons Y, teams T)` yields a candidate
for viewer `V` when `V ∈ T`, `V ≠ S`, `P ∈ S.roster`, and `V` holds ≥1 owned pick with
`round == R` and `season ∈ Y`. Mirrored into V's perspective: `my_give = [that pick]`,
`my_recv = [P]`, `target = S`.

Exactly one candidate per offer per deck. When V holds several matching picks the give
side is the first by `(season ASC, pick_id ASC)` — deterministic, so two runs of the same
deck produce the same card.

*Pass:* `UT-4` (card for a selected team holding a matching pick; **no** card for a
non-selected team holding one; **no** card for a selected team holding none), `UT-10`
(determinism: same pick chosen across two runs with three matching picks).

**R-13 — Every pre-existing filter still runs on standing-offer candidates.**
Untouchables (#95), not-interested (#163), `_past_decision_keys`, the G6 R4 exclusion
(#336) and the **D-055 user-gain floor** all apply unchanged. This reuse is the entire
reason the item is small. **Do not fork the loop.**

*Pass:* `UT-5` — five independent sub-cases, each suppressing a standing-offer card with
one filter and nothing else. `CW-3`.

**R-14 — Cap split.**
`_LIKES_YOU_CAP = 3` is unchanged and remains the total. Organic mirrors are evaluated
first; standing offers then fill remaining slots up to `standing_offer_inject_cap`
(default 2). `= 3` reproduces an unreserved cap; `= 0` kills standing-offer injection
without touching the flag. Ordering within the standing-offer share is newest offer first
(`id DESC`), matching the existing like ordering (`backend/database.py:5261`).

*Pass:* `UT-6` — with 3 standing + 2 organic candidates eligible, exactly 3 inject, at
least 1 is organic, and the drop counter reports 2.

**R-15 — Cap drops are counted, never evented.**
Mirror the `_r4_excluded_keys` idiom (`backend/server.py:3043`,
`backend/trade_service.py:3078`): `trade_service._standing_offer_cap_drops` and
`_organic_like_cap_drops`, reset per job, logged once per injection at `log.info`. **Not**
an analytics event — one event per dropped card in a chatty league is high-cardinality
server noise for a question a counter answers.

*Pass:* `UT-6` asserts the counter value; `UT-11` asserts no `record_event` call fires on
a drop.

**R-16 — "Why you're seeing this", composed server-side.**
When a card came from a standing offer the server sets
`standing_offer_reason` (string), serialized by `trade_card_to_dict` only when present:

```
@{sender_username} posted a standing offer: {player_name} for any {seasons_phrase} {round_word}, and you hold a {matched_pick_label}.
```

`seasons_phrase` ∈ `"2027"` / `"2027 or 2028"` / `"2027, 2028 or 2029"`.
`round_word` from `{1:"1st", 2:"2nd", 3:"3rd", 4:"4th"}`. `matched_pick_label` is
`_owned_pick_label` of the viewer's own give-side pick. Without this line a boosted card
is indistinguishable from a lucky generation.

*Pass:* `UT-8` pins the exact string for a two-season offer. `MT-6`.

**R-17 — The recipient card is the shipped likes-you card.**
Standing-offer cards set `likes_you = True` and reuse the flare **"They're interested"**
pill (`mobile/src/components/TradeCard.tsx:375-378`) and the existing
`max(composite)+1.0` boost (`backend/server.py:3060`, `:3088`). No new recipient-side
component. Flare stays informational; the only new *action*-accented element in this
feature is the sender's own chip (R-9).

*Pass:* `SC-11` asserts no new pill/badge component is introduced in `TradeCard.tsx`,
only a new text line bound to `standingOfferReason`. `MT-6`.

**R-18 — Reconstruction-safe (FB-46).**
The prompt derives its content only from fields present on **both** a real and a
reconstructed card — the give/receive id lists and `target_user_id`
(`_reconstruct_swipe_card`, `backend/server.py:11188`, zeroed scores and no `lane_shift`
at `:11206-11216`). It must never key off `composite_score`, `fairness_score`, `basis` or
`likes_you`. The prompt is triggered client-side off the card the client already holds, so
it is structurally immune; this requirement exists so nobody "improves" it into a
server-driven response field.

*Pass:* `SC-12` asserts the trigger reads only `give`, `receive`, `target_user_id` and
`trade_id` off the card.

### 4.5 Privacy, data, config

**R-19 — PRIVACY (hard requirement). The recipient learns that THEY were selected. They
never learn who else was selected, and never who was excluded.**

Jon's "but not xyz" is a **private negative**. Surfacing it starts fights in real leagues.
Enforcement, all four clauses:

1. `team_user_ids` never appears on any **recipient-facing** payload. It is read only
   inside the injector's match test. (It *does* appear on the sender's own
   `GET /api/trades/standing-offers` rows — that is the sender's own data.)
2. `standing_offer_reason` (R-16) is composed from `(sender, player, round, seasons)`
   only. **No count. No roster list. No team names.**
3. The team count appears on **sender-owned payloads only** (POST response, GET list).
4. No global "open to 1sts" player badge anywhere (R-9).

**One leak that cannot be closed, stated honestly rather than engineered around:** two
league-mates comparing notes — one carrying the card, one not — can infer exclusion. That
is inherent to any targeted broadcast; no payload change prevents it.

*Pass:* `UT-12` asserts the **serialized dict** of a standing-offer deck card contains
neither `team_user_ids` nor any team count key, and that `standing_offer_reason` matches a
regex containing no digits-as-count and no member username other than the sender's.
`SC-13` asserts `team_user_ids` appears in no recipient-facing render path in
`mobile/src/`. `MT-6`, `MT-7`.

**R-20 — `standing_offers` table.** JSON-in-`Text` (the `league_preferences` precedent,
`backend/database.py:992-993`), ISO strings in `String` columns (`:335`, `:994`, `:1020`),
**no `UniqueConstraint`**, **no `asset_class` column**. Full DDL in `lld-delta.md` §2.

*Pass:* `UT-1`, and `docs/data-dictionary.md` carries the table.

**R-21 — Exactly one live offer per `(user, league, player, round)`, enforced at the
writer** with a `revoked_at IS NULL` predicate — the `trade_decisions.retracted_at` idiom
(`backend/database.py:335`, `:5167`, `:5259`). A hard DB constraint would make
"revoke, then re-post" collide.

*Pass:* `UT-1` — second create refused with 409 while the first is live; succeeds after
revoke.

**R-22 — Create-time validation.** `round == 1` (v1); every `team_user_ids` entry is a
current league member; every season is present in the league's real pick horizon
(the distinct `season` values of round-1 rows in `draft_picks` for that league).

*Pass:* `UT-2` (out-of-horizon season rejected — the #355 / D-091 regression class),
`UT-3` (non-member rejected), `UT-13` (`round != 1` rejected).

**R-23 — Expiry.** `expires_at` is **stored**, not derived, at
`created_at + standing_offer_days` (default 30). A derived expiry would let a knob change
silently move the deadline on an offer the user was already shown "18 days left" for.

Why 30: the like window is 90 days (`backend/database.py:5231`); a standing offer is a
louder signal — the first thing in FTF that puts a user's intent in front of other people
with no further tap from them — so it should be materially tighter. 30 is a clean 3×
tightening of an understood window, spans a month of a season without spanning a phase
change, and is a knob.

*Pass:* `UT-7` — an offer past `expires_at` injects nothing.

**R-24 — Flag `trade.standing_offers`, default OFF.** Registered in
`config/features.json` + `backend/feature_flags.py` `FLAG_KEYS` (neighbour
`trade.likes_you` at `:89`) + `docs/config-reference.md`. **Off ⇒ byte-identical**: no
route reachable, no prompt, no injector predicate evaluated, no card payload key added.
Graduation: operator TestFlight pass (§8) on a real 12-team Sleeper league.

*Pass:* `UT-14` asserts a flag-off deck payload is byte-identical to the pre-change
shape. `SC-14` asserts the flag key agrees between `config/features.json` and the client
default map (the `check-league-candidates-300.js:129-143` pattern).

**R-25 — `model_config` knobs.** `standing_offer_days` (30) and
`standing_offer_inject_cap` (2), appended to `_MODEL_CONFIG_DEFAULTS`
(`backend/database.py:2157`) and documented in `docs/config-reference.md`.

*Pass:* `UT-6`, `UT-7` read them through `get_config()`.

**R-26 — Analytics: five events, registered AND classified in the same commit.**
See §5. The taxonomy has an **import-time completeness check**
(`backend/analytics_taxonomy.py:1283-1288`): a client event without a `CLIENT_EVENT_PROPS`
entry raises `ValueError` at boot. And `INTENT_EVENTS` is derived by *subtraction*
(`backend/analytics_queries.py:244`) — an impression-class event omitted from
`NON_INTENT_EVENTS` silently inflates DAU/WAU. That is the NULL-`platform` failure mode
the CLAUDE.md rule exists for.

*Pass:* `UT-15` imports both modules and asserts each of the five names is registered in
the right set with the right props, and that the three non-intent ones are in
`NON_INTENT_EVENTS`. `SC-15` cross-checks the client-side event-name string literals
against `backend/analytics_taxonomy.py`.

---

## 5. Analytics specification

Registered in `backend/analytics_taxonomy.py` under one dated banner block per the house
convention (`:449-487`), with props in `CLIENT_EVENT_PROPS` (`:627`), and classified in
`backend/analytics_queries.py` `NON_INTENT_EVENTS` (`:63`) **in the same commit**.

| Event | Set | Props (exact keys) | Fires when | Intent? |
|---|---|---|---|---|
| `standing_offer_prompted` | `ALLOWED_CLIENT_EVENTS` | `round`, `seasons_offered` (int count of pills shown), `teams_offered` (int count of rows shown) | the sheet becomes visible | **non-intent** → `NON_INTENT_EVENTS` |
| `standing_offer_posted` | `ALLOWED_CLIENT_EVENTS` | `round`, `seasons` (int count selected), `teams` (int count selected), `used_all_teams` (bool) | the POST returns 200 | **intent** — omit from `NON_INTENT_EVENTS` |
| `standing_offer_skipped` | `ALLOWED_CLIENT_EVENTS` | `snoozed` (bool), `retired` (bool) | "Just this one trade" | **non-intent** |
| `standing_offer_revoked` | `ALLOWED_CLIENT_EVENTS` | `age_days` (int) | revoke returns 200 | **intent** |
| `standing_offer_card_shown` | `SERVER_FIRED_EVENTS` | `round`, `seasons` (int count) — server-fired events carry no `CLIENT_EVENT_PROPS` entry; document props in the inline comment, per `awaiting_trade_dismissed` (`:540-556`) | a standing-offer card is injected into a served deck | **non-intent** |

**Counts only, never id lists** — the `mock_*` family's stated convention
(`backend/analytics_taxonomy.py:991-1013`, `:1018-1031`): low cardinality, no query
strings, no member ids. `teams` and `seasons` are integers; `team_user_ids` is never an
analytics prop (R-19).

**Screen arg** for all four client events: `'Trades'`, except `standing_offer_revoked`
which is `'Matches'`.

**Not evented:** cap drops (R-15). **Not in `FUNNEL_CRITICAL`** — this is a side surface,
not a step in the sign-in → suggestion loop.

The primary health metric is `standing_offer_prompted ÷ standing_offer_posted`. If that
ratio is low the prompt is a nag and the trigger (R-1) is what to tighten.

---

## 6. Out of scope for v1

Stated so nobody has to guess:

- **Rounds other than 1.** The `round` column exists so widening is a config change, not a
  schema change. Also: only the top `picks_pool_cap` (default 6) picks per team are
  injected (`backend/server.py:10251`), which is safe for firsts (all firsts price equally
  under D-079 and sort to the top) but can silently bite for round 2+.
- **Offering for a player rather than a pick.** "Any 1st" generalises; "any Tyler Warren"
  does not.
- **Multi-asset packages** on either side.
- **Edit / Repost** on the manage screen (R-10 note).
- **A global player badge** (R-9, R-19).
- **Offers to non-members, cross-league offers, offers to the demo league.**
- **Any change to pick pricing.** Q-023 is not this item.
- **Web and extension clients.** Mobile only; the flag gates the routes so the other
  clients are unaffected.

---

## 7. Guardrails

### 7.1 What must not change

| Invariant | Why |
|---|---|
| `_LIKES_YOU_CAP = 3` stays 3 | the split is a knob, not a second constant |
| The organic-mirror loop is not forked, reordered, or copy-pasted | R-13 — every filter must keep running |
| `swipeMutation` (`TradesScreen.tsx:1795-1893`) and the guide/Apple chain (`:3432-3490`) are untouched | R-1 condition 10; #360 co-ownership (§7.4) |
| Flag-off payloads are byte-identical | R-24 |
| `screens/` is not written to | D-056 froze it 2026-08-11 |

### 7.2 Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | The prompt reads as a nag and the feature gets flagged | R-1's eleven conditions + R-3's persisted ladder; `prompted ÷ posted` is the metric that answers it |
| R2 | Standing offers crowd organic likes out of the deck | R-14's ceiling + R-15's counter; `standing_offer_inject_cap = 0` kills it without a flag flip |
| R3 | A user broadcasts more widely than intended | R-6(a) source-only default; the CTA count; revoke in Matches |
| R4 | The offer generates cards the sender would refuse | §3: D-055 gates the viewer side; round is fixed; the sender's own team/season selection is the instrument |
| R5 | Seasons offered that the league has no picks for (#355 class) | R-4: pills derive from `all_picks`, kept horizon-correct at the writer by D-091 |
| R6 | A private negative leaks | R-19, with `UT-12` + `SC-13` |
| R7 | `TradesScreen.tsx` merge conflict with #360 | §7.4 |

### 7.3 Code-walk proofs (written into `status.md`, file:line-cited)

- **CW-1** — `advance('like')` (`TradesScreen.tsx:3947`) through the post-like branch
  (`:4179-4241`), showing the standing-offer prompt cannot fire during the first-like
  celebration (`:4207-4215`), the Apple ask (`:4220-4227`, `:3447`), the guide-v2 like
  chain (`:4189-4195`), the Quick Set prompt (`:3113`, called `:3355`), the first-session
  adaptation moment (`:4105-4154`), the share affordance (`:4184`), any of the three liked
  toasts (`:4190`, `:4216`, `:4238`), or the mutual-match modal (`:1820-1839`).
- **CW-2** — the like is banked and the deck advanced before the sheet can mount
  (`:4165`, `:4178`), so dismissal is byte-identical to today.
- **CW-3** — the injector predicate traced showing every pre-existing filter
  (`backend/server.py:3010`, `:3016`, `:3021`, `:3031`, `:3038`, `:3055`) still runs on
  standing-offer candidates.

### 7.4 Co-ownership with #360

Both items want `mobile/src/screens/TradesScreen.tsx` (7,563 lines).

- **#362 owns** the `advance()` post-like branch (`:4179-4241`) and the prompt-arbitration
  state it adds.
- **#360 owns** the deck-filter / lane-chip region and the preferences plumbing.
- **Neither** touches `swipeMutation` (`:1795-1893`) or the guide/Apple chain
  (`:3432-3490`) without coordinating.

Certain collisions, all **append-only registries** — merge cleanly provided each agent
appends its own contiguous block and neither reformats a neighbour:
`config/features.json`, `backend/feature_flags.py` `FLAG_KEYS`,
`backend/analytics_taxonomy.py`, `backend/analytics_queries.py` `NON_INTENT_EVENTS`,
`backend/database.py` (`_MODEL_CONFIG_DEFAULTS`), `docs/api-reference.md`,
`docs/config-reference.md`.

If both land in the same wave, **sequence them, #362 second** — it has the smaller, more
localised diff in this file.

**One genuine product interaction, not just a merge conflict:** if #360 lets a user say
"I'm avoiding QBs" and #362 lets a league-mate broadcast "I'll send my QB for a 1st", the
standing-offer injection must respect the *recipient's* avoidance. It already does,
structurally — the not-interested filter runs on the viewer's receive side inside the same
loop (`backend/server.py:3021`) and standing offers reuse that loop (R-13). Whoever ships
second adds a test asserting it and **does not rebuild the filter**.

---

## 8. Evidence plan (D-056 — no Maestro, no simulator, no captures)

### 8.1 Backend unit — `backend/tests/test_standing_offers.py` (new file, no collision)

| ID | Asserts | The sabotage it catches |
|---|---|---|
| UT-1 | create → live row; second create for the same `(user, league, player, round)` → **409** while the first is live; succeeds after revoke | swapping the writer predicate for a DB `UniqueConstraint`, which makes revoke-then-repost collide |
| UT-2 | a season outside the league's pick horizon → 400 | reintroducing a hardcoded N-year window (#355 / D-091) |
| UT-3 | a `team_user_id` that is not a current member → 400 | trusting the client's member list |
| UT-4 | card for a selected team holding a matching pick; **no** card for a non-selected team holding one; **no** card for a selected team holding none | dropping the `V ∈ T` test and broadcasting league-wide |
| UT-5 | five sub-cases: untouchable, not-interested, `_past_decision_keys`, R4 exclusion, D-055 floor each independently suppress a standing-offer card | forking the loop into a parallel path that skips the filters |
| UT-6 | 3 standing + 2 organic eligible → exactly 3 inject, ≥1 organic, drop counter = 2 | letting standing offers consume all three slots |
| UT-7 | past `expires_at` → nothing injects; player left the sender's roster → nothing injects and the manage list marks it `stale` | deriving expiry at read time, or letting the two surfaces disagree |
| UT-8 | `standing_offer_reason` is exactly the R-16 string for a two-season offer | copy that drifts from the spec, or that starts naming teams |
| UT-9 | `standing_offer_mine` stamped on the sender's matching card, absent on a non-matching one, absent flag-off | a chip that appears on every card |
| UT-10 | with three matching picks, two runs choose the same give-side pick | nondeterministic set iteration producing a different card each generate |
| UT-11 | no `record_event` fires on a cap drop | "helpfully" adding a per-drop event |
| UT-12 | the **serialized dict** of a standing-offer deck card carries no `team_user_ids` and no team-count key | returning the offer row wholesale into the card payload |
| UT-13 | `round != 1` → 400 | v1 scope drift |
| UT-14 | flag-off deck payload byte-identical to pre-change | a payload key added unconditionally |
| UT-15 | all five events registered in the right taxonomy set with the right props; the three non-intent ones in `NON_INTENT_EVENTS` | registering the events and forgetting the classification — DAU/WAU inflation |

### 8.2 Structural — `mobile/tests/check-standing-offer-362.js`

New dependency-free node file following `mobile/tests/check-league-candidates-300.js`:
`#!/usr/bin/env node`, a **WHY THIS EXISTS** header naming the silently-wrong failure mode,
soft-require of `typescript` with `process.exit(2)`, the `assert(cond, name, detail)`
harness where `detail` names the sabotage, `stripComments()` before any "X appears
nowhere" assertion (a TSX comment naming the forbidden construct is what made four earlier
tests unfailable — `check-league-candidates-300.js:18-22`), numbered `═`-ruled sections,
and `process.exit(1)` on failure. Add
`"test:standing-offer-362": "node tests/check-standing-offer-362.js"` to
`mobile/package.json` after `:52`.

Assertions **SC-1 … SC-15** as named per-requirement above. Test names are prefixed
`#362`.

### 8.3 Manual TestFlight checklist (operator) — the only runtime evidence mobile gets

On a real 12-team Sleeper league, with `trade.standing_offers` on:

1. **MT-1** — Swipe right on a 1-for-1 where you receive a first → the sheet appears
   **after** the deck has advanced; the like is already banked (check Matches → Awaiting).
   The source team is the only team checked, the source season the only season checked;
   the CTA reads **Broadcast to 1 team**.
2. **MT-2** — Dismiss with "Just this one trade" → nothing posts; Matches → Standing offers
   is empty; the deck is exactly where it was.
3. **MT-3** — Repeat step 1 in the same session → **no second prompt**.
4. **MT-4** — Force-quit, relaunch, repeat → the prompt appears once more; dismiss again →
   it never returns.
5. **MT-5** — Post an offer for 2 seasons × 3 teams → the toast names **3 teams**; the chip
   `Open to 1sts · '27–'28` appears on matching cards in your own deck; Matches → Standing
   offers lists it with a days-left count.
6. **MT-6** — On a **selected** team's account: the card appears with the flare "They're
   interested" pill and a "Why you're seeing this" line naming the player, round and
   seasons — **and no team names and no counts**.
7. **MT-7** — On a **non-selected** team's account: no card.
8. **MT-8** — Revoke from Matches → Standing offers → the selected team's next deck no
   longer carries the card.
9. **MT-9** — Swipe right on a 1-for-1 where you receive a **player** (not a pick) → no
   prompt.
10. **MT-10** — Repeat step 1 in an ESPN league with no assigned picks → no prompt. In a
    league whose horizon is 2 classes, the sheet shows exactly 2 year pills.

### 8.4 Pre-ship gate

- `pytest backend/tests` green. Most recent measured suite on this branch point:
  **3526 passed, 1 skipped, 0 failed** (`living-memory/TEST_LEDGER.md:23`, the #357
  entry — this worktree's base). The clean-`origin/main` baseline of **3480 passed, 1
  skipped** is at `:105`. **Re-measure your own branch point rather than assuming
  either** — the ledger's own entry at `:105` says "re-measured rather than assumed"
  for exactly this reason.
- `tsc --noEmit` green.
- `mobile/scripts/testid-lint.sh` green (still in CI).
- `mobile/tests/check-*.js` — **60 passed, 0 failed** baseline
  (`living-memory/TEST_LEDGER.md:176`), 61 with this item's new suite.
- Evidence logged in `living-memory/TEST_LEDGER.md`.
- `githooks/pre-push` still enforces the retired simulator marker — set
  `FTF_SKIP_SIM_GATE=1` and note the evidence run instead (standing posture under D-056).

---

## 9. Success criteria

**Ship criteria** (all must hold before the flag graduates past the operator):

1. Every requirement R-1 … R-26 has its named pass criterion green.
2. The pre-ship gate in §8.4 is green.
3. The operator's manual pass MT-1 … MT-10 is clean, logged in `TEST_LEDGER.md`.
4. `docs/api-reference.md`, `docs/data-dictionary.md`, `docs/config-reference.md`,
   `docs/glossary.md`, `living-memory/LLD.md`, `docs/architecture.md`,
   `living-memory/HLD.md` and `living-memory/DECISIONS.md` (decision recorded item-scoped as D-362-1 — see hld-delta.md §9) are updated per
   [`scope.md`](scope.md) §4.

**Health criteria** (read after the flag is on for real testers):

| Metric | Read as |
|---|---|
| `standing_offer_posted ÷ standing_offer_prompted` | the prompt earns its interruption. Low ⇒ tighten R-1's trigger, or reconsider R-6(a) |
| `used_all_teams` share | whether source-only is burying the value. High ⇒ R-6(b) is the better default |
| cap-drop counter (log) | whether `standing_offer_inject_cap` needs moving |
| `standing_offer_card_shown` per offer per week | fan-out is behaving as modelled |
| revocations within 48h of posting | users broadcasting more widely than they meant (R3) |

---

## 10. Open items

| # | Item | Status |
|---|---|---|
| O1 | Default selection state | **CLOSED** — operator confirmed source-only, 2026-08-19 (D-g). Variant (b) stays specced behind `STANDING_OFFER_DEFAULT_SELECTION`. |
| O2 | Expiry = 30 days | Ruled (D-c). A judgment call, not a derivation — and a knob. |
| O3 | v1 = firsts only | Ruled (D-d). |
| O4 | Value gate | **REJECTED** on evidence (§3). Mockup §6 corrected 2026-08-19. |
| O5 | Edit / Repost on the manage screen | Out of v1 (R-10 note). Revisit after graduation. |

**Not a decision — a note for the builder.** D-090 is committed to
`feat/pick-slot-labels` and **not merged**. It is display-only and does not affect this
item either way, but do not assume slot labels are live on `main`.

---

## Build deviations — recorded 2026-08-19 (orchestrator)

> The PRD must stay true, because QA tests against it.

**D-1 — `StandingOfferSheetProps.onSkip` is `() => void`, not `(snoozed, retired) => void`.**
The snooze ladder lives in `useOnboardingState`, and the retire computation has to sit
next to the patch that applies it — exactly as `snoozeQuicksetPrompt` does. The LLD's
signature would have forced the sheet to duplicate that computation, giving two places
that decide when the prompt retires. The parent now owns the ladder, the patch, and the
`standing_offer_skipped` event. Check SC-3d pins the terminal branch against quickset's.

**D-2 — SC-14 reinterpreted: the flag must be ABSENT from `LAUNCHED_FLAG_DEFAULTS`, not present-and-matching.**
The PRD asked the flag key to "agree between `config/features.json` and the client
default map". `trade.standing_offers` ships **dark**, and that map **fails open** — a
listed key is ON for a first-ever boot or a failed revalidate. Asserting presence would
have pinned a fail-open bug that lights a dark feature. Shipped as: SC-14a asserts
`false` in `config/features.json`; SC-14b asserts **absence** from the defaults map.
Same reasoning as #360's D-1 and as `mobile/src/api/league.ts:709`.

**D-3 — A mutual-match retraction effect was added (~8 lines).**
R-1 condition 10 requires "no mutual match on the swipe response", which is not knowable
synchronously inside `advance()`. Implemented as an effect observing `swipeMutation.data`
only; `swipeMutation` itself is untouched.

**D-4 — There is no mutual-match modal in `TradesScreen`.**
CW-1 cites `:1820-1839` as the mutual-match modal. That range is `swipeMutation.onSuccess`,
which only stashes `match_id` in a ref for the share affordance; the match surfaces on the
Matches tab. This is why D-3 above is an effect rather than a state check.

**D-5 — Edit and Repost are out of v1 on the manage surface**, as argued in R-10 —
either would need a fourth route and a second entry point into the post-like sheet, and
revoke-then-repost already reaches the same end state. Mockup §5 shows both controls;
the mockup is ahead of v1 here. Pinned by check SC-10d.
