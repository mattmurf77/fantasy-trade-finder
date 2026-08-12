# Tracking plan — feedback #300 (League rankings → positional trade candidates)

**Date:** 2026-08-12
**Status:** built, verified statically; **deploy-then-probe gate NOT yet run** (§8 — it needs a deploy and is above this agent's authority).
**Base:** `analytics-300` = `integration-300` @ `d207b03` (= `origin/main` + the #300 backend half + the #300 mobile half + both flags flipped ON + v1.13.1).
**Owner:** analytics instrumentation agent, feedback #300.
**Closes:** the analytics waiver in [`scope.md`](scope.md) §1, which was left open for the mobile lane. §1 has been rewritten from waiver to spec.
**Supersedes:** the `league_candidate_pinned` recommendation in [`status-mobile.md`](status-mobile.md) §5. Three of its four props survive; see §7 for what changed and why.

This is the tracking-plan addendum `backend/analytics_taxonomy.py`'s own module
docstring requires before a new client event name may be registered.

**Why this exists at all.** #300 shipped **lit** — both flags flipped ON in
`d207b03` — with the pre-ship simulator gate **and** the Maestro flow execution
**waived by the operator**. The divider, the 44pt hit-slop treatment and the
rule-A removal have never run on a device or a simulator. So these two events
are not a nice-to-have measurement layer: they are the **only** evidence that
will ever exist that the feature works in the wild.

---

## Table of Contents

- [1. What is added, in one table](#1-what-is-added-in-one-table)
- [2. `league_candidate_pinned` — the conversion moment](#2-league_candidate_pinned--the-conversion-moment)
- [3. `league_pos_candidates_viewed` — the exposure](#3-league_pos_candidates_viewed--the-exposure)
- [4. Deliberately NOT instrumented](#4-deliberately-not-instrumented)
- [5. Intent vs non-intent — decided per event, in the same commit](#5-intent-vs-non-intent--decided-per-event-in-the-same-commit)
- [6. Reports these events support](#6-reports-these-events-support)
- [7. What in the mobile agent's §5 proposal turned out to be wrong](#7-what-in-the-mobile-agents-5-proposal-turned-out-to-be-wrong)
- [8. Verification, and the deploy-then-probe gate](#8-verification-and-the-deploy-then-probe-gate)
- [9. Proposed shared-doc text (orchestrator-owned files)](#9-proposed-shared-doc-text-orchestrator-owned-files)

---

## 1. What is added, in one table

| # | Event | New? | Client | Trigger moment | Props | Intent? |
|---|---|---|---|---|---|---|
| 1 | `league_candidate_pinned` | **new name** | mobile (`LeagueSummaryScreen.tsx`) | An Offer/Target row action is tapped in the drill-in — the pin is written and the finder is entered | `verb`, `position`, `rank`, `side` | **INTENT** |
| 2 | `league_pos_candidates_viewed` | **new name** | mobile (`LeagueSummaryScreen.tsx`) | The single-position candidate view is reached (`candidatePos` becomes non-null and the payload has resolved) | `position`, `divider` | **NON-INTENT** |
| 3 | `league_team_closed` | **no — one new `via` VALUE** | mobile | unchanged | `via` gains `filter_change` (already shipped by the mobile agent; **no prop key changes**) | NON-INTENT (unchanged) |
| 4 | `league_team_opened` | **no — untouched** | mobile | unchanged | unchanged | INTENT (unchanged) |

**Two new event names, no new properties on any shipped event, no new server
event, no route change, no schema change, no flag.** Row 3 is listed only to
record that it is *not* a registration change: a new value inside an existing
string prop passes the registry untouched, which is why
`check-analytics-297-302.js` stayed green at 35/35.

---

## 2. `league_candidate_pinned` — the conversion moment

**Fires from:** `handleRowAction` in `mobile/src/screens/LeagueSummaryScreen.tsx`
— the single choke point behind every drill-in row's `onPress`, and the only
invocation of that helper in the file (asserted; sabotages S38, and the
definition/invocation count check). It fires **before** `navigation.navigate`,
so a slow transition cannot eat it.

**Screen prop:** `route.name` (`LeagueRankings` on the tab root,
`LeagueSummary` on the legacy root-stack push).

### Properties

| Prop | Type | Values | Notes |
|---|---|---|---|
| `verb` | string | `offer` · `target` | The user's action. `offer` pins `give` (a player from **your** roster), `target` pins `receive` (a player from **theirs**). |
| `position` | string | `QB` · `RB` · `WR` · `TE` | The single core position the ranked list was filtered to — read from `candidatePos`, the memo the divider's own render gate reads. **A core position, never a device platform and never a roster slot.** |
| `rank` | int | 1-based | The tapped team's **on-screen** rank at the moment of the pin (`selectedIdx + 1`, the same value the drill-in subline prints). |
| `side` | string | `above` · `below` | The **tapped team's** side of the median line, read from `candidateDir`. |

### Why `verb` and `side` are both needed — the mirror

The obvious objection to the §5 proposal is that `side` is a restatement of
`verb`: above the line ⇒ target theirs, below ⇒ offer yours. **That is true of
the primary roster only.** The drill-in stacks the **mirror** roster underneath
it (operator decision 4 — stacked, never side-by-side), and the mirror's rows
carry the **opposite** verb:

| `side` | primary section | mirror section |
|---|---|---|
| `above` | their roster, `verb = target` | your roster, `verb = offer` |
| `below` | your roster, `verb = offer` | their roster, `verb = target` |

All four `(verb, side)` combinations occur, and the one that matters is the
derived quantity:

```
mirror = (verb === 'target') === (side === 'below')
```

`mirror = true` means **the user acted against the direction the median line
chose for them** — they opened the collapsed roster and traded the other way.
That rate is the direct test of the feature's central bet, and it is
unreadable from either prop alone. `mirror` is not sent as a third prop
because it is exactly determined by the two that are.

### Why `rank` is carried rather than joined

Every pin happens inside a drill-in, and every drill-in fires
`league_team_opened{rank}` first — so `rank` is nominally recoverable by
sessionizing and taking the preceding open. It is carried anyway, following
the precedent `league_team_closed.rank` set in the previous batch: the join is
order-dependent and easy to get wrong, and the two can legitimately **differ**
— a basis change mid-focus re-ranks the list without ejecting the user, so
`league_team_opened.rank` is the rank at open while this is the rank the pinned
row was actually at. Carrying it also keeps `rank` coherent with `side`, which
is computed over the same snapshot.

### Why a new name and not a property on an existing event

Three existing events were considered and each fails for a different reason:

* **`find_trades_tapped`** — the closest relative, and it *will* fire shortly
  after (the handoff routes to `TradesHome`). But it fires from `TradesScreen`,
  by which point the League screen's context — position, rank, side — is gone,
  and it also fires on paths that have nothing to do with #300. Adding four
  League-only props to it would make them NULL on the large majority of rows
  and would still not identify a #300 handoff, because the pin store carries no
  provenance.
* **`league_team_opened`** — the wrong moment. It fires when the drill-in
  opens, not when an asset is chosen; the whole question is what fraction of
  opens convert.
* **`league_home_action_tapped{action}`** — a generic action bucket, but it is
  the *League home* screen's event (`LeagueScreen`), not this screen's, and it
  carries none of the context that makes this measurable.

---

## 3. `league_pos_candidates_viewed` — the exposure

**Fires from:** an effect in `LeagueSummaryScreen.tsx`, immediately after the
`medianCaption` derivation.

**Screen prop:** `route.name`.

### Properties

| Prop | Type | Values | Notes |
|---|---|---|---|
| `position` | string | `QB` · `RB` · `WR` · `TE` | Same sense as above — `candidatePos`, read not re-derived. |
| `divider` | string | `shown` · `no_median` · `no_split` | The render **outcome**, read off `medianAtPos` / `cutAfter`. |

`divider` values, and why the event is not gated on `shown`:

| Value | Condition | What a spike in it means |
|---|---|---|
| `shown` | `cutAfter != null` — the line drew | The feature is working |
| `no_median` | `medians[position]` absent from the payload | **An ops signal, not a product one.** An old server, or the field missing for that position. The client cannot label a median itself (`_aggregate_pick_label` needs server-only pick seeds) and a raw numeric is forbidden on this screen, so it draws nothing. |
| `no_split` | a median arrived but `cutAfter` is null — every team on one side, or a list too short to split | A flat league (mock S-2's case, whose explanatory copy was **not built**). Product, not ops. |

A `shown`-only impression event would collapse all three into "no row", and
the two failure stories are exactly the ones an operator needs separated:
*"the rollout is incomplete"* looks identical to *"users never found it"*.

### Why a new name and not a property on an existing event

The brief's own hypothesis — that `league_team_opened` (P0-7) might already
cover this — was checked and **does not hold**. `league_team_opened` fires on
drill-in entry, i.e. only for users who **already acted**. The population whose
absence needs measuring is precisely the users who saw the divider and did
nothing; they emit no `league_team_opened` at all. Hanging a `side` or
`divider` prop on it would answer a different question.

Every other candidate on this screen was checked at the call site:

| Candidate | Verdict |
|---|---|
| `league_view` | Fires **ONCE per mount**, guarded by `viewFiredRef`, at `query.isFetched` — before any position pill can have been tapped. A `divider_shown` prop on it would be `false` on essentially every row. |
| `league_subset_changed` | Fires from `switchSubset` only — the **All / Starters / Bench** control. **A position-pill tap emits nothing today, anywhere in the app**: `togglePos` has no `track` call, and after the 2026-08-12 rule A/B removal it is a plain, flag-independent toggle. There is no existing event on the transition that produces the divider. |
| `league_basis_changed` | Consensus/My-board toggle. Orthogonal. |
| `league_team_opened` | See above — wrong population. |

So a new name is genuinely required, and it is the **only** new impression-class
name #300 adds.

### The over-count trap, and how the emit is pinned to the render

The divider renders only when **four** clauses hold together:
`league.pos_candidates` on · subset is `all` · `PICKS` **not** in the filter ·
**exactly one** core position selected. Those four live in one memo,
`candidatePos` (`LeagueSummaryScreen.tsx`), and the render gate reads it.

**The emitter reads the same memo and re-derives nothing.** A second copy of
the conjunction would drift the moment one clause moved — and one just did:
#294's rule A (a position tap auto-adding `PICKS`) shipped on 2026-08-10 and
was removed on 2026-08-12, inside three days. A copy that drifted **loose**
would be the expensive failure: every multi-position filter and every
Starters/Bench view would land as an exposure, inflating the denominator of
the only conversion rate this feature has, silently.

The test suite pins this four ways — the gate must be `if (!candidatePos)`,
and the effect must contain **none** of `posFilter.has('PICKS')`,
`subset !== 'all'`, `CORE_POSITIONS.filter`, or `posCandidatesOn`. Sabotages
S17–S20.

### Emit discipline

* **Deduped on the position alone**, in a ref (`candidateViewRef`). One row per
  entry into a position's candidate view — not one per render, and not a second
  row when a background refetch nudges `cutAfter`.
* **Leaving the view resets the ref**, so WR → All → WR is two genuine
  exposures. A sticky ref would make re-entry invisible (sabotage S23).
* **Held until `query.isFetched`.** Before the first fetch resolves there is no
  payload to be missing, so emitting early would report `no_median` for a
  request that has not answered yet (sabotage S21 — this one was a **live false
  pass** in an earlier draft of the suite; see §8).

### Known bound on what it measures

This is *"the user reached the state in which the divider renders"*, not
*"divider pixels crossed the viewport"*. True visual impression would need
`onLayout` + scroll-offset math on the `ScrollView`. Not built: it is
disproportionate for a single flag-gated surface, and the difference is a
strict over-count bound (`exposures ≥ true impressions`) that is stated here
rather than discovered later. In practice the divider sits inside the ranked
list the user just filtered, so the gap should be small.

One further ordering note, recorded rather than guarded: the exposure effect is
declared **before** the filter-change auto-return effect, so a user who changes
the pill while drilled in emits the exposure in the same commit that ejects
them back to the list. They do see the divider on the very next render. The
first exposure for a position can never happen while drilled in, because
`selectedId` starts null and a drill-in cannot be entered without first passing
through the list.

---

## 4. Deliberately NOT instrumented

Over-instrumenting a lit feature is not free — every name is a permanent
taxonomy entry, a DAU/WAU decision, and a row in every future report's WHERE
clause. Five things were considered and dropped.

1. **`band` (Buyer / Seller) as a property.** The brief asks whether the band
   labels correlate with action. They are not measured, and the reason is that
   the operator's own ruling makes them inert: *"the LINE, not the label, is the
   direction rule"* — `bandFor` has exactly one consumer, a caption prop, and a
   second one would silently make the middle third inert. A property measuring
   a label that drives nothing, sitting on the one event that measures the
   feature's conversion, is the definition of over-instrumentation. It is also
   **recoverable**: band is a pure function of `rank` (sent) and
   `league_view.team_count` (already on the wire, same mount), via
   `round(team_count * 0.33)`. The honest cost of that recovery is stated
   plainly: the 33% constant is client-side only and is **not** in
   `docs/cross-client-invariants.md` (scope.md §4 waived that row), and it has
   already moved once — 25% → 33% during design. A historical recomputation
   therefore needs the constant's effective date, which is in the frozen design
   and in `config/features.json`'s `_comment_league_pos_candidates`. If the
   operator wants band correlation as a first-class read, the right fix is to
   record the constant in cross-client-invariants and add `band` to **both**
   this event and `league_team_opened` (numerator and denominator) — a
   deliberate decision, not a default.
2. **The mirror disclosure toggle** (`league-summary.roster-mirror-toggle`).
   Expanding the mirror **without** acting is not measured. The acting case
   already is, through `(verb, side)`, and that is the half that carries a
   decision. A pure expand event would be a second impression name on a control
   nested two levels inside a flag-gated drill-in.
3. **A general position-pill-changed event.** `togglePos` fires nothing today
   and this work does not change that. Registering `league_pos_filter_changed`
   would fire in every state on the screen — most of them unrelated to #300 —
   and is a taxonomy decision that belongs to whoever owns the League filter
   surface, not to this item.
4. **A server-side signal for the `medians` field.** The backend serves
   `medians` unflagged and fires nothing (scope.md §1(c), correctly waived).
   The `no_median` value on the exposure event is the client-side witness that
   a payload arrived without it, which is the form the question actually takes
   ("did the client get it", not "did the server compute it").
5. **`league_team_closed.via = 'filter_change'` as a registration change.** It
   is a new **value** in an existing string prop, not a new key, so nothing is
   registered and nothing is at risk of being stripped. Recorded in §1 row 3 and
   asserted (the prop set of `league_team_closed` must stay exactly
   `{via, dwell_ms, rank}` — sabotage S41).

---

## 5. Intent vs non-intent — decided per event, in the same commit

`analytics_queries.py:65`:
`INTENT_EVENTS = (SERVER_FIRED_EVENTS | ALLOWED_CLIENT_EVENTS) - NON_INTENT_EVENTS`.

**Taxonomy growth is intent-by-default.** Any name added to the allowlist
becomes an INTENT event unless *also* added to `NON_INTENT_EVENTS`, and
`INTENT_EVENTS` feeds DAU/WAU across ~10 call sites in that module. Registering
a passive event without the guard step-changes DAU/WAU with no error, no log,
and no way to tell the artifact from real growth afterwards.

| Event | Verdict | Reasoning |
|---|---|---|
| `league_pos_candidates_viewed` | **NON-INTENT** | A passive exposure — the same class as `league_view` and `tab_selected`. Decisive detail: it is the **only** event on this screen a user can emit without ever drilling in, because a position-pill tap fires nothing else. Admitting it to INTENT would promote every idle filter tap to a user-day and step-change DAU from ship day. Added to `NON_INTENT_EVENTS` in the same commit as its allowlist entry. |
| `league_candidate_pinned` | **INTENT — deliberately left out of `NON_INTENT_EVENTS`** | An asset chosen and the trade finder entered is a real value moment, the peer of `find_trades_tapped` and `league_team_opened`. |
| `league_team_opened` / `league_team_closed` | **unchanged** | Untouched by #300; the enter/exit pair still owns the drill-in. |

**Seam analysis.** Neither name adds a DAU/WAU seam:

* `league_pos_candidates_viewed` is NON-INTENT, so it enters no user-day series
  at all — that is the whole point of the row above.
* `league_candidate_pinned` **is** INTENT and is new from ship day, but it adds
  **no user-day that was not already counted**. The row action is reachable only
  inside the drill-in, the drill-in is reachable only through `openTeam`, and
  `openTeam` always fires `league_team_opened`, which is INTENT. So every pin is
  preceded in the same session by an intent event that already counts the user.
  Pinned structurally: `LeagueSummaryScreen` has exactly one
  `league_team_opened` emitter and exactly one `handleRowAction` invocation.

`FUNNEL_CRITICAL` is **not** touched — neither event is worth retaining over a
`signin_attempted` under SDK queue overflow — so the mobile mirror in
`mobile/src/api/events.ts` needs no edit.

---

## 6. Reports these events support

Written down because a tracking plan that does not name its reads is a wish
list. **None of these may be wired before the §8 probe passes.**

| Question | Read |
|---|---|
| Did anyone find the feature? | `count(league_pos_candidates_viewed)` per user-day, split by `divider` |
| Is the rollout complete? | share of `league_pos_candidates_viewed` with `divider = no_median` — should be ~0 and is an **ops** alarm, not a product metric |
| Does the divider convert? | `count(league_candidate_pinned) / count(league_pos_candidates_viewed WHERE divider = 'shown')` |
| Which positions do people shop? | `position` on both events; they share a value space by construction |
| Was the median line's direction rule right? | share of `league_candidate_pinned` where `(verb = 'target') = (side = 'below')` — the mirror rate. High ⇒ the line is picking the wrong roster |
| Do people shop the extremes? | `rank` distribution on `league_candidate_pinned`, banded with `league_view.team_count` (see §4 item 1 for the constant's caveat) |
| Does the handoff survive into the finder? | `league_candidate_pinned` followed by `find_trades_tapped{mode}` in the same session |

---

## 7. What in the mobile agent's §5 proposal turned out to be wrong

`status-mobile.md` §5 proposed `league_candidate_pinned` with props
`{verb, position, rank, side}` and the verdict "not in `NON_INTENT_EVENTS`".

| Proposed | Status now | Why |
|---|---|---|
| The name `league_candidate_pinned` | **KEPT** | Accurate — the pin, not the navigation, is the moment. |
| `{verb, position, rank, side}` | **KEPT, all four** | `verb` and `side` looked 1:1 on first reading and are not: the mirror section carries the opposite verb, so all four combinations occur (§2). The proposal did not state that reason, and the *first* review of it concluded `side` was redundant — it is not. |
| "`rank` the tapped team's 1-based on-screen rank" | **KEPT, tightened** | Specified as the **live** `selectedIdx + 1` rather than the rank at open, so it is coherent with `side`. The proposal left the snapshot unstated. |
| "Belongs in `NON_INTENT_EVENTS`? **No**" | **CORRECT, and kept** | Independently reached. |
| §5's `backend/analytics_taxonomy.py` edit 2, verbatim | **SUPERSEDED** | It registered the props but named no `NON_INTENT_EVENTS` decision line, no exposure event, and no client↔taxonomy prop cross-check. Registration alone would have left the feature's conversion measurable and its denominator absent. |
| **The gap the proposal did not close** | **THE EXPOSURE EVENT** | §5 proposed exactly one event. With the simulator gate and the Maestro run both waived, one event means a zero is uninterpretable. `league_pos_candidates_viewed` is added here. |
| `status-mobile.md` §4's alternative — "extend `league_team_opened` with `side` rather than adding an event" | **NOT ADOPTED** | Sound as far as it goes, but it measures the wrong population for the exposure question (users who already drilled in) and the pin event already carries `side` at the moment it matters. Widening a shipped high-volume P0-7 event with a prop that is null in most states was the worse trade. |
| `scope.md` §1's third suggested name, `league_candidate_action {action, side, pos}` | **RENAMED** | `action`/`pos` are spelled `verb`/`position` to match `status-mobile.md` §5 and the house vocabulary (`via`, `position` elsewhere in the registry). One name, one spelling. |

---

## 8. Verification, and the deploy-then-probe gate

### The base was RED before this work started

Two pre-existing failures, both caused by `d207b03` (the flags-ON commit)
and neither by this work. Recorded because the brief expected a green base:

| Symptom | Cause | Fix (this branch, commit `c3c2e9b` / `c48e17b`) |
|---|---|---|
| `test_seed_ui_test_db.py::test_onboarding_v2_flags_are_release_plus_the_onboarding_surface` and `::test_profiles_on_flags_turn_on_public_pages_only` — 2 failed | `d207b03` flipped both #300 keys ON in `config/features.json` and `fixtures/flags/release.json` but not in the two release-mirrored fixtures, which the tests enforce as "release plus exactly one **named** delta" | value-only sync of `profiles-on.json` + `onboarding-v2.json`; named deltas unchanged |
| `check-league-candidates-300.js` — 3 checks failed | Its §1 hard-coded `false` ("shipping dark") for both keys; the operator's flip made the assertions assert the opposite of the intent | §1 rewritten to compare `LAUNCHED_FLAG_DEFAULTS` against `config/features.json` — the invariant that actually matters (the whole-map `set({flags})` footgun) and that survives every future flip. The stale `DARK (both false)` comment above the now-`true` defaults was corrected too. |

### Run here (all green)

| Command | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | **2610 passed, 1 skipped** (2605 + 5 new) |
| `npx tsc --noEmit` (mobile) | clean, exit 0 |
| `bash mobile/scripts/testid-lint.sh` | `testid-lint OK` |
| `node mobile/tests/check-league-drill-in.js` | 29 PASS |
| `node mobile/tests/check-analytics-297-302.js` | 35 PASS |
| `node mobile/tests/check-single-pin-actions.js` | 17 PASS |
| `node mobile/tests/check-league-candidates-300.js` | **67 PASS** (was 66; −3 stale flag assertions, +4 agreement assertions) |
| `node mobile/tests/check-picks-subset-invariance.js` | 72 PASS |
| `node mobile/tests/check-analytics-300.js` | **51 PASS** (new) |

### Sabotage matrix — 41 mutations + 1 control, all accounted for

Each mutation was applied to the real tree one at a time, the mutation was
**proven to have landed** (`git diff` on that path must be non-empty — a silent
no-op mutation is itself a false pass), the suite run, and the file restored.

Backend (`pytest backend/tests/test_events_api.py -k 300`):

| # | Sabotage |
|---|---|
| S2 | Drop `league_candidate_pinned` from `ALLOWED_CLIENT_EVENTS` (NAME survival) |
| S3 | Rename the registered prop `divider` → `outcome` (PROP survival, name intact) |
| S5 | Drop `side` from the pin prop registry |
| S7 | Hollow the pin registry to one prop |
| S9 | Admit a device-`platform` prop on the pin event (the NULL-`platform` incident) |
| S10 | Drop `divider` entirely — the three-outcome test loses all three |
| S12 | Drop the exposure from `NON_INTENT_EVENTS` |
| S14 | Demote `league_candidate_pinned` to NON-INTENT |
| S42 | Desync the `profiles-on` flag fixture from `release.json` (the base break, re-armed) |

Client (`check-analytics-300.js` unless noted):

| # | Sabotage |
|---|---|
| S1 | Drop the exposure name from `ALLOWED_CLIENT_EVENTS` |
| S4 | The `divider` → `outcome` rename, caught by the client↔taxonomy cross-check |
| S6 | Drop `rank` from the pin registry |
| S8 | Register a `band` prop nobody sends (a field that reads all-NULL forever) |
| S11 | Mint a duplicate `league_divider_shown` name |
| S13 / S15 | The two intent sabotages, caught client-side |
| S16 | Typo the exposure event name (`league_pos_candidate_viewed` — the `celebration_fired` failure class) |
| S17 | **Loosen the exposure gate** from `candidatePos` to the flag alone |
| S18 | Re-derive the `PICKS` clause beside the emitter |
| S19 | Re-derive the `subset === 'all'` clause beside the emitter |
| S20 | Re-derive the exactly-one-core-position clause beside the emitter |
| S21 | Drop the `isFetched` guard — **this one was a live FALSE PASS** (see below) |
| S22 | Drop the dedup early-return — one row per dependency change |
| S23 | Never reset the dedup ref — a genuine re-entry becomes invisible |
| S24 | Collapse `divider` to a shown-only impression |
| S25 | **Transpose** `no_median` and `no_split` — all three strings still present, meaning inverted |
| S26 | Stop distinguishing a missing payload from a flat league |
| S27 | Drop `candidatePos` from the exposure dep array |
| S28 | Send an unregistered prop key on the exposure (`pos`) |
| S29 | Invert `side` |
| S30 | Re-derive `side` from `selectedIdx < cutAfter` instead of reading `candidateDir` |
| S31 | Take `rank` from a different snapshot than `side` |
| S32 | Stop sending `position` (a registered prop nobody produces) |
| S33 | Send an unregistered `band` prop on the pin event |
| S35–S37 | Drop `candidatePos` / `candidateDir` / `selectedIdx` from `handleRowAction`'s deps |
| S38 | Add a **second** pin emitter after the navigate |
| S39 | Flip `league.pos_candidates` in `config/features.json` only (`check-league-candidates-300.js`) |
| S40 | Delete a #300 key from `LAUNCHED_FLAG_DEFAULTS` (`check-league-candidates-300.js`) |
| S41 | Sneak a new prop **key** onto the shipped `league_team_closed` |
| **S34** | **CONTROL** — an inert `void 0;` inside `handleRowAction`. The suite must stay **GREEN**; a control that goes red means the suite pins incidental text. It stayed green. |

**42/42 accounted for, one genuine false pass found and fixed.** S21 initially
did **not** turn the suite red: the assertion checked for the identifier
`query.isFetched` inside the effect, and that identifier also appears in the dep
array, so deleting the early return left it satisfied. Fixed by pinning the
statement (`if (!query.isFetched) return`) rather than the name — commit
`8f8f786`. This is the same shape as the four false-passing tests this batch
has already caught, and it is why the control and the applied-check exist.

### Deploy-then-probe gate — REQUIRED before any report reads these names, NOT run here

Static tests prove the registry and the call sites agree. They **cannot** prove
the deployed backend agrees, because every drop path is silent and the health
endpoint's counters are in-process and reset on deploy (so "counters stayed
flat" is evidence of nothing).

**After merge and deploy, before any dashboard, report, or experiment reads
these names**, hand-roll one `POST /api/events` per new name carrying its
**full** property set, and assert **all three**:

1. `accepted > 0` — **the trap.** Without identity the response is
   `{"accepted":0,"dropped":0,"rejected":[{"reason":"no_identity"}]}`, which has
   `dropped == 0` and therefore **reads as a pass and is not one**. The request
   must carry `X-Device-Id` (or a session token).
2. `dropped == 0` — proves **NAME** survival. An unknown type still counts in
   `accepted`, so `accepted` alone proves nothing.
3. Every property echoed back **at the destination** — read the row out of
   `user_events.props` — proves **PROP** survival. An unknown prop is popped
   while the envelope still reports `dropped: 0`.

Envelope requirements (else the row is `rejected`, not dropped, and again
`dropped == 0` lies): `event_type`, `session_id` 8–64 chars, `event_id`
matching `^[A-Za-z0-9_-]{8,64}$`, `seq` in 1..1e6.

```
POST /api/events
Headers: Content-Type: application/json
         X-Device-Id: probe-300-device            # WITHOUT THIS, accepted == 0
{ "events": [
  { "event_id": "probe300aaaaaaaa", "event_type": "league_pos_candidates_viewed",
    "session_id": "probe-300-sess", "seq": 1, "screen": "LeagueRankings",
    "client_ts": "2026-08-12T12:00:00Z",
    "props": { "position": "WR", "divider": "shown" } },
  { "event_id": "probe300bbbbbbbb", "event_type": "league_candidate_pinned",
    "session_id": "probe-300-sess", "seq": 2, "screen": "LeagueRankings",
    "client_ts": "2026-08-12T12:00:01Z",
    "props": { "verb": "target", "position": "WR", "rank": 3, "side": "above" } }
] }
```

Then, in the read-only DB:

```sql
SELECT event_type, props FROM user_events
 WHERE event_type IN ('league_pos_candidates_viewed','league_candidate_pinned')
 ORDER BY occurred_at DESC LIMIT 2;
```

Pass = `accepted == 2`, `dropped == 0`, and both `props` blobs contain every key
above (`seq` and `ts_suspect` are server-stamped additions and are expected).

Repeat once per `divider` value if the report in §6 will split on it — the
value space is not registry-enforced, so a typo there is invisible to every
test in this branch.

**Not run: it needs a deploy, and it is above this agent's authority.**

### Seam date

Both names first appear on this batch's ship date. `league_pos_candidates_viewed`
is NON-INTENT, so no DAU/WAU/retention series has a seam.
`league_candidate_pinned` is INTENT but adds no user-day that
`league_team_opened` did not already count (§5), so the same holds. No
historical backfill is possible or needed: before this ship the row action fired
nothing at all.

---

## 9. Proposed shared-doc text (orchestrator-owned files)

Proposed, **not applied** — these files are orchestrator-owned and both #300
branches would collide on them. Exact text follows.

### `docs/cross-client-invariants.md` — new row in the analytics-event section

> **`league_pos_candidates_viewed.divider`** — closed enum, three values:
> `shown` · `no_median` · `no_split`. Mobile-only today (#300). `no_median`
> means the client received a `GET /api/league/power-rankings` payload with no
> `medians[position]`; it is an incomplete-rollout signal, not a product one.
> **`league_candidate_pinned.side`** — closed enum, `above` · `below`, the
> tapped team's side of the League-rankings median line. With
> `league_candidate_pinned.verb` (`offer` · `target`) it encodes whether the
> user acted on the roster the line chose or on the mirror:
> `mirror = (verb == 'target') == (side == 'below')`. `position` on both events
> is a CORE POSITION (`QB|RB|WR|TE`), never a device platform.

### `living-memory/DECISIONS.md` — one entry

> **#300's analytics are two events, and the exposure half is the one that
> makes the other readable (2026-08-12).** The feature shipped lit with the
> simulator gate and the Maestro run both waived, so `league_candidate_pinned`
> — the Offer/Target row action — is the only witness that anyone uses it, and
> a zero on it is uninterpretable on its own: nobody found the divider looks
> exactly like nobody wanted it. `league_pos_candidates_viewed` supplies the
> denominator, and no shipped event could: `league_view` fires once per mount
> before any pill is tapped, `league_subset_changed` covers the
> All/Starters/Bench control only (a position-pill tap fires nothing, anywhere
> in the app), and `league_team_opened` fires only for users who already acted
> — the exact population whose absence is being measured. The exposure carries
> `divider ∈ shown|no_median|no_split` rather than being gated on "shown",
> because "the payload arrived without `medians`" is an ops story and "the
> league is flat" is a product one, and a shown-only event collapses both into
> silence. **The emit gate is `candidatePos` itself, read and never
> re-derived**: the divider's render condition is a four-clause conjunction and
> a second copy that drifted loose would count every multi-position and every
> Starters/Bench view as an exposure, inflating the denominator of the only
> conversion rate this feature has, silently. #294's rule A came and went
> inside three days, so the drift is not hypothetical. On the action event
> `verb` and `side` are both carried and are **not** redundant, because the
> drill-in stacks the mirror roster whose rows carry the opposite verb — all
> four combinations occur, and `(verb == 'target') == (side == 'below')` is the
> rate at which users override the line, which is the feature's central bet.
> No `band` prop: the Buyer/Seller labels drive no behaviour by operator ruling
> and are a pure function of `rank` and `league_view.team_count`. Intent split
> decided in the same commit as the registration, because `INTENT_EVENTS` is
> derived by subtraction: the exposure is NON-INTENT (it is the only event on
> that screen a user can emit without drilling in, so INTENT would promote every
> idle filter tap to a user-day), the action is INTENT and seams nothing (every
> pin is preceded by an intent `league_team_opened`).

### `living-memory/TEST_LEDGER.md` — one entry

> **#300 analytics, static gate only** (no simulator — operator waived the
> sim gate and the Maestro run for this ship): `pytest backend/tests` **2610
> passed / 1 skipped** · `tsc --noEmit` clean · `testid-lint.sh` OK ·
> `check-league-drill-in` 29 · `check-analytics-297-302` 35 ·
> `check-single-pin-actions` 17 · `check-league-candidates-300` **67** (was
> 66; three "shipping dark" assertions replaced by four that compare
> `LAUNCHED_FLAG_DEFAULTS` against `config/features.json`) ·
> `check-picks-subset-invariance` 72 · **`check-analytics-300` 51 (new)**.
> Proven against **41 sabotages + 1 inert control, 42/42 accounted for, one
> genuine false pass found and fixed** (S21: the `isFetched` guard was pinned
> by an identifier that also appears in the dep array). **The base was RED**
> before this work: `d207b03` flipped both #300 flags ON without syncing the
> two release-mirrored flag fixtures (2 pytest failures) and left
> `check-league-candidates-300.js` asserting the dark posture (3 failures);
> both fixed here. **Deploy-then-probe gate OWED** — see analytics.md §8; no
> report may read the two new names until it passes, and it must assert
> `accepted > 0` as well as `dropped == 0`.

### `living-memory/CHANGELOG.md` — append to the #300 entry

> **Analytics (2026-08-12).** #300 shipped with zero instrumentation; two
> client events close that. `league_candidate_pinned {verb, position, rank,
> side}` (INTENT) is the Offer/Target conversion moment;
> `league_pos_candidates_viewed {position, divider}` (NON-INTENT) is the
> exposure that makes a zero on it readable. Registered in
> `ALLOWED_CLIENT_EVENTS` + `CLIENT_EVENT_PROPS` with the `NON_INTENT_EVENTS`
> decision in the same commit. Tracking plan:
> `docs/feedback/items/300-league-rankings-trade-candidates/analytics.md`.
> Deploy-then-probe gate is owed before any report reads either name.

### `docs/api-reference.md`

**No change owed by this work.** The `medians` field row proposed in
`status-mobile.md` §5 is still owed by the backend lane; nothing here adds,
renames or removes a route. `POST /api/events` is documented in terms of its
envelope, not its allowlist.

### `docs/config-reference.md`

**No change owed by this work.** No flag, env var or `model_config` key is
added. The two `config/features.json` corrections proposed in
`status-mobile.md` §5 are still owed by the mobile lane.

### `mobile/src/screens/CLAUDE.md` — § Sharp edges, add one

> - `LeagueSummaryScreen`'s two #300 analytics events are gated on the SAME
>   memos the render is: `league_pos_candidates_viewed` on `candidatePos`, and
>   `league_candidate_pinned`'s `side` on `candidateDir`. Neither may re-derive
>   the divider's four-clause condition beside itself — a copy that drifted
>   loose would count every multi-position and every Starters/Bench view as an
>   exposure, inflating the denominator of the feature's only conversion rate
>   with nothing on screen to show for it. Pinned by
>   `mobile/tests/check-analytics-300.js`.
