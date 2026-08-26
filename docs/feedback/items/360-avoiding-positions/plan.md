# Plan — "Avoiding" positions (#360 / #361)

> Planner deliverable, 2026-08-19. A later Author agent writes the PRD + LLD
> delta from this. Base: `origin/main` @ `50e0451`. **Every `file:line` below was
> read at that sha this session** — line numbers drift, the enclosing function
> names do not.
>
> Feedback (verbatim):
> - **#360** (jonbonjourvi, TradesHome, v1.15.0, polish): "Forget if I've
>   mentioned before but an option right next to the shopping for and willing to
>   sell positions we should have positions we're not looking for (eg I don't
>   want QB, TE)"
> - **#361** (same user, minutes later): "Well I guess I can just select the
>   other positions I do want but perhaps doesn't hurt to add a no flag since
>   the logic is already there"
>
> Operator decision (2026-08-19): build a **third section under Chasing /
> Shopping called "Avoiding"**.
>
> **Gate posture: FULL gates, not express.** This adds a column to
> `league_preferences` — the CLAUDE.md bright line. Scope block, D-056 evidence,
> row-by-row docs table, TEST_LEDGER entry. §9 names what the scope block must
> answer.

---

## 1. The decision in one paragraph

Ship **Avoiding as a hard receive-side exclusion applied at pool source**, stored
in a new `league_preferences.avoid_positions` JSON column, gated by a new flag
`trade.avoid_positions`. Do **not** revive the dormant `pos_conflict_penalty`
soft multiplier. The mechanism is not a new invention: **#163 `not_interested`
("never suggest acquiring this player") is the per-player twin of this feature,
and its plumbing is a complete, already-shipped map of every receive-side seam
in the codebase** — six sites, all cited in §4. Avoiding is that same filter
evaluated on `position` instead of `player_id`. That framing decides most of the
open design questions for free and keeps the change surgical.

---

## 2. Answering the operator's question: does Shopping already cover this?

**No, and the proof is mechanical.** Both existing prefs run through
`_positions_ok`, which is duplicated with identical semantics in the two live
engines:

- v3 (`trade_engine.v3 = true`, the production path):
  `backend/trade_optimizer.py:423-438`, called at `:525`
- v2 fallback: `backend/trade_service.py:4566-4579` (inside
  `_generate_for_pair_v2`), called at `:4647`

```
if _acq:   recv_pos = [...recv_ids...];  if not any(p in _acq  for p in recv_pos):  return False
if _away:  give_pos = [...give_ids...];  if not any(p in _away for p in give_pos):  return False
```

Three facts follow, each of which independently kills the "Shopping already does
it" reading:

1. **Shopping reads `give_ids` only.** It constrains what leaves the user's
   roster. It says nothing about what arrives. "I have too many QBs" and "don't
   send me a QB" are opposite sides of the trade and the code treats them that
   way.
2. **Chasing is `any()`, not `all()`.** #361's own workaround — "I can just
   select the other positions I do want" — is *insufficient*, and this is the
   sharpest argument for building the feature. Setting Chasing = WR, RB requires
   that **at least one** received player is a WR or RB. A 2-for-2 that sends the
   user a WR **and a QB** passes the gate cleanly. The user gets exactly the
   thing they said they didn't want, riding along in the same package.
3. **Nothing anywhere expresses a negative receive constraint at position
   granularity.** The only negative receive constraint that exists is #163, and
   it is per-player.

---

## 3. Semantics decision — hard exclusion, and why not the dormant knob

### 3.1 The parent's lead on `pos_conflict_penalty` is confirmed: it is dead

Verified this session. `pos_conflict_penalty` appears at exactly three sites,
none of which is an application:

| Site | What it is |
|---|---|
| `backend/database.py:2187` | `model_config` seed row, `0.15`, described as "−N% per received player whose position the user wants to shed" |
| `backend/trade_service.py:98` | `_DEFAULT_CFG` default |
| `backend/tests/test_bakeoff_arm_a_golden.py:499` | a golden **inventory of config key names** — it asserts the key *exists*, never that it does anything |

Its two siblings are equally dormant: `pos_acquire_bonus` (`database.py:2185`,
`trade_service.py:96`) and `pos_tradeaway_bonus` (`database.py:2186`,
`trade_service.py:97`). The comment at `trade_service.py:100-102` calls the
acquire bonus "(dormant)" in so many words.

### 3.2 The history argues *against* reviving it — this is the load-bearing point

The parent asked me to challenge rather than rubber-stamp the hard-filter
recommendation. Challenging it made the case stronger, for a reason that is not
in the parent's brief:

**The trio was designed together as soft multipliers, and the v2 rebuild
deliberately replaced two of the three with hard filters.**
`docs/glossary.md:116` states it outright: positional preferences are "a **hard
filter** on candidate packages … in both engine paths; the old soft multipliers
(`pos_acquire_bonus` etc.) are deleted from code though their `model_config`
keys remain." `docs/plans/competitor-top20/02-asset-preference-lists.md:79`
records the same finding independently.

So `pos_conflict_penalty` is not an unbuilt spec waiting for an implementer. It
is **the third member of a retired design**, left behind because deleting a
`model_config` seed is a migration and deleting a `_DEFAULT_CFG` key breaks the
golden inventory. Reviving it would re-introduce, for the negative case only,
precisely the soft-multiplier architecture the rebuild consciously abandoned for
the positive cases — leaving one preference row behaving categorically
differently from the two rows directly above it in the same UI block.

Supporting arguments, in descending weight:

- **The user's model.** #361 says "add a **no flag** since the logic is already
  there." A flag is binary. An "I don't want QBs" that still shows QBs 15% less
  often is indistinguishable from a bug, and the user has no instrument to tell
  the difference.
- **Precedent density.** Every negative preference in this codebase is a hard
  filter: untouchables (give side, never relaxed), #163 not-interested (receive
  side, never relaxed), pinned give/receive. There is no soft negative anywhere.
- **Free ride on the never-relaxed guarantee.** §6.2 — a pool exclusion is
  structurally immune to the #189 relaxed pass. A multiplier is not.
- **No new `model_config` key** ⇒ no edit to the golden inventory at
  `test_bakeoff_arm_a_golden.py:485-515`, and no new tuning surface to calibrate
  or defend. A penalty would need a measured default, and §8 explains why the
  measurement corpus is not reliably available.

**Recommendation: hard exclusion. Leave `pos_conflict_penalty` untouched and
dormant** (coding-guidelines §3: mention pre-existing dead code, don't delete
it). The PRD should state in one line that the knob was evaluated and
deliberately not revived, so the next planner doesn't re-litigate it.

### 3.3 Hard *how* — pool exclusion, not a package gate

Within "hard" there are two mechanisms, and the choice is not cosmetic.

| | Package gate (extend `_positions_ok`) | **Pool exclusion at source (recommended)** |
|---|---|---|
| Predicate | `none(p in avoid for p in recv_pos)` — note it needs `none()`, the *inverse* of the `any()` the other two branches use | `known_opp = [p for p in opponent.roster if pos_of(p) not in avoid]` |
| Guarantee | avoided position cannot appear in a *served* package | avoided position cannot enter the search space **at all** |
| Consensus path | **does not work** — `_generate_consensus_for_pair` has no `_positions_ok` (§4, site 4) | works; it is already how that path handles positions |
| Sweetener / add-on | needs a second, separate hook | free — the sweetener pool is built from the same filtered list |
| Cost | enumerate-then-discard | smaller combinatorial search; strictly faster |
| Precedent | none | **#163 `not_interested`, verbatim** |

Pool exclusion wins on every row. Crucially, the third generator path — the
consensus path used for unranked opponents — **does not run `_positions_ok` at
all**; it restricts the receive pool by position instead
(`backend/trade_service.py:4943`: `recv_pool = [p for p in recv_pool if _pos(p)
in need_positions]`). Pool exclusion is therefore the only mechanism that is
uniform across all three paths, and in that path it is already the local idiom.

---

## 4. Scope of the filter — receive side only, six seams

These are the six sites where `not_interested_ids` is applied today. Every one is
a site where `avoid_positions` must be applied, and the mapping is 1:1. Verified
by `git grep -n not_interested -- backend`.

| # | Site | Code today | Avoiding change |
|---|---|---|---|
| 1 | **v3 receive pool** — `trade_optimizer.py:359-361` (`known_opp` build inside `generate_pair_trades_v3`) | `and not (not_interested_ids and p in not_interested_ids)` | add `and _pos_of(p) not in avoid` |
| 2 | **v3 sweetener** — `trade_optimizer.py:708-709`, comment reads "#163 never sweeten INTO the user" | side-aware receive filter | same predicate, same `side == "receive"` guard |
| 3 | **v2 receive pool** — `trade_service.py:4761-4763` (`_known_opp` in `_generate_for_pair_v2`) | same idiom | same |
| 4 | **Consensus path** — `trade_service.py:4932-4934` (`_opp_pool` in `_generate_consensus_for_pair`) | `_opp_pool = [p for p in opponent.roster if not (not_interested_ids and p in not_interested_ids)]` | same |
| 5 | **Asset ideas** — `trade_service.py:3775`, `:3836`, `:3855` (`_generate_asset_ideas_impl`) | three receive-side guards | same at all three |
| 6 | **likes-you injector** — `server.py:3019-3021`: `if not_interested_ids and set(their_give) & not_interested_ids: continue` | their give IS the user's receive after mirroring | add a position-set intersection on the same line |

The parent specifically asked about the likes-you path (site 6): **yes, it must
be filtered.** The precedent is already in that function and the comment states
the reasoning — "#163 — not-interested players are never offered TO the user,
even via a counterparty like." A boosted, deck-position-1 card that sends the
user an avoided position is the single most visible way to break the promise.
Note this is a *different* class from the G6 Q21 exemption: Q21 exempts
likes-you from deck **quality** rules (R1/R2/R3/R5), while untouchables, #163 and
the R4 dedup are all applied there. Avoiding is a user constraint, not a quality
rule, so it lands on the constraint side of that line. Worth one sentence of
confirmation from the operator (Q-A3, §11).

### 4.1 Plumbing — two loaders, mirroring `acquire_positions` exactly

- `server.py:5179-5188` — the trade job's pref load. Add
  `avoid_positions = prefs.get("avoid_positions", []) or []` beside the two
  existing lines.
- `server.py:5355-5356` — passed into `generate_trades`. Add the third kwarg.
- `server.py:11031-11073` — the asset-ideas route does its own pref load and
  pass-through; mirror both halves.
- Thread through `_generate_trades_impl` (`trade_service.py:3116-3117`) →
  `_generate_trades_v2` (`:3966-3967`) → `_generate_for_pair_v2` (`:4437-4438`)
  / `generate_pair_trades_v3` (`trade_optimizer.py:208-209`) /
  `_generate_consensus_for_pair` (`:4887-4888`). Every one of these signatures
  already carries `acquire_positions, trade_away_positions` adjacently — the
  third parameter goes on the next line in each.

### 4.2 Explicitly OUT of scope, with reasons

- **Eveners** (`server.py:1027` `_roster_eveners`, reached from
  `/api/trade/evaluate` at `:9540`). The manual calculator is a surface where
  the user has already hand-built the package and asked for a balancing
  suggestion. Decisive: `_roster_eveners` reads asset preferences at
  `:1046-1051` and takes **only `untouchables`** — #163 `not_interested` is
  *not* applied there either. Excluding Avoiding from eveners is therefore the
  choice that keeps Avoiding consistent with its own precedent; including it
  would make the position-level filter stricter than the player-level one on the
  same surface. (Operator may overrule — Q-A4.)
- **The give side.** #360's wording — "positions we're not looking for" — is
  unambiguously about what arrives. One PRD sentence should say so, because a
  reasonable reader could stretch "I don't want QB" to "keep QBs out of the trade
  entirely", and Shopping already owns the give side.
- **`web/` and `extension/`.** See §7.

---

## 5. Conflict rules — the asymmetry that must not be flattened

This is the most likely thing for a build agent to get wrong, because the
obvious implementation ("make all three mutually exclusive, like the existing
two") destroys the feature's best use case.

| Pair | Coherent? | Rule |
|---|---|---|
| Chasing ∩ Shopping | no (existing) | mutually exclusive — already enforced, `TradeDnaSheet.tsx:474-500` |
| **Chasing ∩ Avoiding** | **no** | mutually exclusive — new |
| **Shopping ∩ Avoiding** | **YES — and it is the modal case** | **must be co-selectable** |

The operator flagged Shopping+Avoiding as arguably the most common real usage,
and the code agrees: Shopping gates `give_ids`, Avoiding gates the receive pool.
They are disjoint sides of the trade and cannot contradict. "I'm selling my QB
and I don't want another one back" compiles to *"at least one given player is a
QB, and zero received players are QBs"* — a perfectly well-formed, and very
common, dynasty request. Flattening this into three-way exclusion would make the
headline use case unexpressible.

### 5.1 Server-side contradiction guard (required, not optional)

The UI enforcing Chasing ⊕ Avoiding is not sufficient — an older client, a
replayed request, or a direct POST can still send both. The failure mode is
specific and silent: if `acquire = ["QB"]` and `avoid = ["QB"]`, the pool
exclusion empties every receive pool of QBs while `_positions_ok` demands at
least one received QB. Result: **zero cards on every opponent, forever, with no
error.** That is the exact class of bug the "verify blockers" lesson warns about.

Guard: in `_run_trade_job` immediately after the pref load
(`server.py:5186-5188`), compute `acquire_positions = [p for p in
acquire_positions if p not in avoid_positions]` before anything downstream sees
either list. Avoid wins because a negative promise is the stronger commitment and
the cheaper one to honor. Log at INFO when it fires. Cover with a pytest
regression — this is the single highest-value test in the suite.

---

## 6. Empty-state and safety

### 6.1 Avoiding everything

`DNA_POSITIONS` (`TradeDnaSheet.tsx:75-81`) has **five** entries — QB, RB, WR,
TE, **and PICK**. Avoiding all five empties every receive pool, permanently and
silently.

Three options were considered; recommend **(a) + (c), explicitly not (b)**:

- **(a) UI guard** — the sheet blocks the tap that would select the last
  unselected position, with an inline line ("Leave at least one position
  available"). Cheap, honest, no round trip.
- **(b) Backend treats "avoid everything" as unset.** *Rejected.* Silently
  disobeying a saved preference to avoid an awkward empty state is exactly the
  invented-state-change failure the repo's own feedback lesson names. If the user
  says avoid everything, the app owes them "that's why you see nothing", not a
  quiet override.
- **(c) Honest empty-state copy** when the deck comes back empty and
  `avoid_positions` is non-empty.

### 6.2 Partial tightness — the existing safety valve, and it works for free

`trade_service.py:3294-3297` fires the #189 relaxed pass when a job is
*targeted*:

```
targeted = bool(pinned_give_players or pinned_receive_players
                or acquire_positions or trade_away_positions)
if targeted and not cards:
    cards = self._relaxed_targeted_pass(_v2_kwargs)
```

**Recommendation: add `or avoid_positions` to that predicate.** A user who has
narrowed the field should get the same staged widening the other narrowing prefs
already get.

The safety property comes free: `_relaxed_targeted_pass`
(`trade_service.py:3479-3533`) relaxes only the fairness band and the surplus
floor, and re-runs `_generate_trades_v2` with the *same* kwargs. Because Avoiding
lives in pool construction rather than in a relaxable gate, **it is structurally
impossible for the relaxed pass to relax it** — no code is needed to guarantee
that. Still add Avoiding to the never-relaxed list in the docstring at `:3491-3499`
(which already names untouchables and the G6 rules), so the guarantee is written
down where the next reader looks.

### 6.3 Client empty-state

`TradesScreen.tsx:6274-6293` is the existing toast branch, with per-intent copy
added by #172 — the stated pattern is "same mechanism as the existing
fairness-aware message, not a new one". Add one branch there. Suggested copy,
naming the constraint the user set: *"No trades found that avoid
{positions}. Try un-avoiding one."* There is **no** existing "your filters are
too tight" path — I looked; the only empty states are fairness-aware, intent-aware,
and the #330 scoped-empty card at `:6276-6300`.

---

## 7. Platforms

| Client | Verdict | Evidence |
|---|---|---|
| **Backend** | in scope | §4 |
| **Mobile** | in scope, **one file** | `TradeDnaSheet.tsx` is the only live editor |
| `mobile/src/screens/TradeFinderHubScreen.tsx` | **do not touch** | It duplicates the whole Chasing/Shopping editor (`:299-303`, `:322-323`, `:343-344`, `:383-384`) but is **UNROUTED** — `mobile/src/navigation/TabNav.tsx:37` ("TradeFinderHubScreen is unrouted (guided-first landing)") and `:432`. Dead code kept in tree per #246. Leaving it stale is correct; deleting it is out of scope. **Flag this to the build agent explicitly** — a `git grep acquire_positions` makes it look like a required second edit. |
| **Web** (`web/js/app.js:4425-4600`) | **safe to skip in v1** | The outlook modal's `saveOutlookWithPositions` (`:4542-4560`) and `skipPositionalPrefs` (`:4583-4600`) send `acquire_positions` + `trade_away_positions` explicitly and would omit `avoid_positions`. `upsert_league_preference` (`database.py:8507-8512`) only writes a positional field when it is **not None** — so a web save **preserves** an avoid set written from mobile. This is a verified no-data-loss guarantee, not an assumption. Web parity is a follow-up, not a blocker. |
| **Extension** | n/a | `git grep -n "preferences\|acquire_pos" -- extension` returns nothing. The extension never reads league preferences. |

---

## 8. `trade_gen_v2.py` — out of scope for the build, but escalate now

The parent asked whether the dark `trade_gen.v2` generator needs the same
treatment. The answer is more uncomfortable than "it's dark":

1. `trade_gen.v2 = false` in `config/features.json:65`, so it does not serve on
   the normal path. **But `trade.bakeoff = true`** (`config/features.json`), and
   the bake-off calls `trade_gen_v2.generate_league_suggestions`
   (`trade_gen_v2.py:844`) **directly**, as arm `gen_v2`
   (`bakeoff_runner.py:113`, `:389`), by design — that module's own flag gates
   only the *normal* serving path.
2. Serving is dark **by knob, not by flag**: `bakeoff_serve_interleaved = 0.0`
   (`trade_service.py:508`; gate at `bakeoff_runner.py:211`, with the note at
   `:196` "back to 0.0 = DARK (operator, 2026-08-19)"). A `model_config` knob
   flips without a deploy.
3. **`trade_gen_v2.py` reads no positional preferences at all.**
   `git grep -n "acquire_positions\|trade_away_positions" backend/trade_gen_v2.py`
   returns **zero hits**.

Two consequences:

- **A pre-existing bug, not mine to fix but worth surfacing:** the moment
  `bakeoff_serve_interleaved` goes to 1, one of three deck groups comes from a
  generator that already ignores Chasing and Shopping. That is a live risk today,
  independent of this feature.
- **For Avoiding specifically it is worse in kind.** Chasing/Shopping are
  preferences; Avoiding is a *promise* ("never send me a QB"). A generator that
  can serve a QB to a user who checked "no QB" turns a hard guarantee into a
  coin flip, and the user cannot tell which arm produced the card.

**Recommendation:** port the receive-pool exclusion into gen-v2's candidate
build. It is small — the same pool filter — and there is direct precedent for
porting a rule into gen-v2 ahead of the v1 wave: `trade_gen_v2.py:177-197`
documents exactly that for the G6 #341/#339 rules, including a 2026-08-17
reconciliation onto shared knobs. Alternative, if the operator prefers minimum
surface: rule that `bakeoff_serve_interleaved` stays 0 until gen-v2 honors
positional prefs, and log it as an open question. **This needs an operator
ruling before build** (Q-A1, §11) — it is the difference between a hard promise
and a leaky one.

---

## 9. What the scope block must answer

Copy `docs/templates/feature-scope.md` → `docs/feedback/items/360-avoiding-positions/scope.md`.

### §1 Analytics

**Recommended answer: (b) + a stored-state query, no new event.**
`outlook_saved` is already registered (`analytics_taxonomy.py:412`, props
`frozenset({"source"})` at `:1122`) and fires once per sheet session at the first
preference write (`TradeDnaSheet.tsx:452-457`). It covers the write moment.
Adoption ("how many users avoid a position?") is answerable directly from
`league_preferences.avoid_positions` — it is durable stored state, not an
ephemeral interaction, so an event would be strictly redundant for that question.

**If the operator wants funnel attribution** (does avoiding change like-rate?), a
new event is needed, and the scope block must then carry these constraints
verbatim:

- Register the name in `ALLOWED_CLIENT_EVENTS` (`analytics_taxonomy.py`, the
  block around `:412`) **and** the property allow-map (around `:1122`) **and**
  classify it in `analytics_queries.NON_INTENT_EVENTS` (`:63`) — **all in the
  same commit as the emitter.**
- Two reasons this is not boilerplate, both documented in-repo: the registry is
  **default-deny behind a 200** (`analytics_taxonomy.py:419-424`), so an
  unregistered name is silent, unrecoverable loss with a success-shaped response;
  and `INTENT_EVENTS` is a **deny-list** (`analytics_queries.py:244`), so a new
  name is intent-by-default and admitting it step-changes DAU at the emitter's
  ship date (`analytics_queries.py:67-73`).
- A preference toggle is a deliberate user action ⇒ intent-class ⇒ correctly
  *absent* from `NON_INTENT_EVENTS`. That must be a stated decision, not an
  omission.

### §2 Schema & flag

- **Column:** `league_preferences.avoid_positions TEXT DEFAULT "[]"` —
  `database.py:992-993` for the column pair to mirror, `:2445-2446` for the
  additive-migration list entry (`("league_preferences", "avoid_positions",
  "TEXT")`). SQLite locally, Postgres in prod; the existing two columns were
  added by this same mechanism.
- Touch: `upsert_league_preference` (`:8477-8534` — the `is not None` guard **and**
  the insert branch's `vals.get(..., "[]")` defaults **and** the `k not in (...)`
  exclusion tuple at `:8532-8533`, which is easy to miss) and
  `load_league_preference` (`:8537-8575`).
- **Flag:** `trade.avoid_positions` → `config/features.json` +
  `backend/feature_flags.py` `FLAG_KEYS` (`:47`; `trade.presentment_rules` at
  `:799` is the template) + `docs/config-reference.md`. Ship **ON** (user-requested
  feature; the flag is the kill switch). Mobile reads flags by string key from a
  generic `FlagMap` (`mobile/src/state/useFeatureFlags.ts`), so add the key to
  `LAUNCHED_FLAG_DEFAULTS` (`:45`) per the #115 fail-open lesson documented at
  `:36-44`. Flag OFF ⇒ column ignored, decks byte-identical, section hidden.
- **`model_config` keys: none.** Consequently **no edit to
  `backend/tests/test_bakeoff_arm_a_golden.py:485-515`** (the knob-inventory
  golden). Worth stating — it is a concrete dividend of choosing a filter over a
  penalty.
- **API:** `GET`/`POST /api/league/preferences` (`server.py:15380`, `:15455-15510`)
  gain one additive array field, with the same `isinstance(list)` 400 validation
  as its siblings (`:15484-15487`).

### §3 Evidence (D-056 — no Maestro, no sim, no captures)

- **Structural guard:** `mobile/tests/check-avoid-positions.js` +
  `"test:avoid-positions"` in `mobile/package.json`. Dependency-free plain node,
  matching the 60-odd existing `check-*.js`. Pin: the Avoiding row exists in
  `TradeDnaSheet.tsx`; its testIDs follow the `dna.avoid.<tid>` shape;
  **`toggleDnaPos` clears the tapped position from Chasing but NOT from
  Shopping** (the §5 asymmetry — this is the assertion worth the whole file);
  the autosave payload carries all three lists.
- **Unit tests:** new `backend/tests/test_avoid_positions.py`, every behavioral
  test proven-to-fail on sabotage (the G6 convention). Minimum set:
  1. avoid QB ⇒ no served card receives a QB, across **all four** generator
     paths (v3, v3-sweetened, v2, consensus);
  2. avoid QB **+ shop QB** ⇒ cards still generate, and they *give* a QB
     (the §5 modal case; this test is the feature);
  3. avoid QB **+ chase QB** ⇒ the §5.1 guard drops QB from acquire and the deck
     is non-empty (the silent-zero regression test);
  4. avoid PICK ⇒ owned-pick pseudo-assets (`position == "PICK"`,
     `server.py:10320`) never appear on the receive side;
  5. likes-you injection refuses a mirrored card containing an avoided position;
  6. relaxed pass does not resurrect an avoided position;
  7. **flag OFF ⇒ byte-identical deck** with a populated `avoid_positions`
     column (the pattern `test_user_gain_gate.py` uses);
  8. avoid-everything ⇒ empty deck, no exception, no hang.
- **Code-walk proof:** file:line trace showing all six §4 seams plus the two
  loaders are on the filtered path. Commit to this folder.
- **Manual TestFlight checklist** (the only runtime evidence mobile gets):
  1. Open Trades → the sheet → confirm a third "Avoiding" row under
     Chasing/Shopping with five chips.
  2. Tap Avoiding **QB**. Confirm QB clears from Chasing if it was set, and
     **stays** set in Shopping if it was set.
  3. Re-run the finder. Swipe the **entire** deck (not just the first cards) and
     confirm no card sends you a QB — in any package position, not just the
     headline.
  4. Set Shopping QB + Avoiding QB together. Confirm cards still appear and that
     they send your QB out.
  5. Avoid all five positions. Confirm an honest empty state, not a spinner and
     not a crash.
  6. Kill and relaunch. Confirm Avoiding persisted.
  7. Open the same league on the **web** app, save an outlook there, return to
     mobile, and confirm Avoiding survived (the §7 no-data-loss claim, verified
     by hand).
- **testIDs:** `dna.avoid.{qb,rb,wr,te,picks}` — must pass
  `mobile/scripts/testid-lint.sh` (still in CI).

### §4 Docs table (fill row-by-row)

| Doc | Expected |
|---|---|
| `docs/api-reference.md` | **updated** — `/api/league/preferences` GET+POST gain `avoid_positions` |
| `docs/data-dictionary.md` | **updated** — the `league_preferences` table at `:650-663` gains a row |
| `docs/config-reference.md` | **updated** — new flag `trade.avoid_positions`; no new `model_config` keys |
| `docs/glossary.md` | **updated** — "Positional preferences" at `:116` currently names only two lists and says they are hard filters; it must name three and record that Avoiding is a *receive-pool exclusion*, not a package gate |
| `living-memory/LLD.md` | **updated** — the negative-receive-constraint convention (positions join players) |
| `docs/architecture.md` / `living-memory/HLD.md` | likely **n/a** — no new module or flow; state the reason, don't leave blank |
| `docs/cross-client-invariants.md` | **judgment call** — see §10 R3. If the PICK-identity predicate is used, the "Mirror locations" table at `:398+` gains a row |
| `DECISIONS.md` (decisions recorded item-scoped as **D-360-1…D-360-4** in `prd.md` §2 — sequential ids were taken by `origin/main` before ship) | **required ×2** — (i) hard exclusion over reviving `pos_conflict_penalty`, with the retired-trio reasoning; (ii) the Shopping+Avoiding co-selectable asymmetry |

### §5 Ship gate

CI green (`pytest backend/tests`, `tsc --noEmit`, testid-lint) + TEST_LEDGER
entry naming the pytest file, the `check-*.js` suite, the code-walk doc, and the
operator's checklist outcome. `githooks/pre-push` still enforces the retired
simulator marker — `FTF_SKIP_SIM_GATE=1` is the standing posture under D-056; note
the evidence run in its place.

---

## 10. UI

### 10.1 Where it goes

`mobile/src/components/TradeDnaSheet.tsx` renders **two** variants and both need
the row:

- **`full` variant** (`:661-700`) — the shipped TradesHome edit sheet
  (`trades.edit_full_sheet = true`). A `POSITIONS` header followed by two
  `styles.posLine` rows, each a label column (`Chasing` / "want more";
  `Shopping` / "happy to move") plus a `styles.toggleRow` of `DnaToggle`s. The
  third row drops in directly below Shopping: **`Avoiding` / "no thanks"**.
- **legacy variant** (`:743-786`) — the DNA-only half-sheet, `Chasing — tap all
  that apply` style headers plus the hint paragraph at `:781-785`. That hint
  currently reads "A position can't be both chased and shopped" and **must be
  rewritten** to state the three-way rule including the Shopping+Avoiding
  exception. Do not skip this branch: omitting `full` is what keeps the flag-off
  path byte-identical (`:71-73`), so it is live.

Mechanics:

- Extend `toggleDnaPos` (`:474-500`) from a 2-way to a 3-way move, **preserving
  the §5 asymmetry**: `chase` clears from shop **and** avoid; `avoid` clears from
  chase **only**; `shop` clears from chase only.
- **The autosave payload must carry all three lists — six sites.** The
  `dnaDesired` ref type (`:401-405`), `queueDnaSave`'s parameter type
  (`:439-443`), the mutation's variable type + body (`:384-392`), the
  error-revert (`:427-431`), `pickOutlook`'s call (`:467`) and `toggleDnaPos`'s
  call (`:493-499`) **all** currently carry `{outlook, acquire, shed}`. If
  `avoid` is not added to every one of them, a Chasing tap that clears QB from
  Avoiding will not persist the clear — the row and the DB silently diverge, and
  the next sheet open re-seeds the stale value. This is the most likely build bug
  in the whole feature; the structural test in §3 should pin it.
- `TradesScreen.tsx:1058-1074` `receiptDetails` — the deck banner summarizes
  "Chasing … · Shopping … · N off the table". Add "Avoiding …" using the same
  `posLabel` helper (`:1059`, which already maps `PICK → 'Picks'`).
- `mobile/src/api/league.ts:28-45` — `LeaguePreferences` gains
  `avoid_positions: string[]`. `saveLeaguePreferences` (`:54-59`) spreads the
  object, so no signature change.

### 10.2 The screen captures are STALE — do not use them as the "before"

`screens/mobile/sheets-trade-dna/open.png` and `fine-tuning.png` are both stamped
`captured_at: 2026-08-10T15:03:04+00:00` (`screens/manifest.json:1440-1461`) and
the library is frozen at D-056. Two independent proofs they no longer match
source:

1. **Three commits have landed on `TradeDnaSheet.tsx` since** — `7057d86`
   (2026-08-14, +23/−8), `6158e65` and `8827810` (both 2026-08-15, +30/−1).
2. **Observable mismatch.** I read `open.png`. Its POSITIONS block shows Chasing
   and Shopping rows with **four** chips each — QB, RB, WR, TE. Current source
   defines **five** (`DNA_POSITIONS`, `TradeDnaSheet.tsx:75-81`, including
   `{ key: 'PICK', label: 'Picks' }`). The rendered frame and the code disagree.

**Plainly: neither frame is current.** They are useful only as a rough sense of
the sheet's shape (dark sheet, "WHAT ARE YOU AFTER?" header, POSITIONS block with
left label column + chip row, TRADE IDEA below, then SPECIFIC PLAYERS / OFF THE
TABLE / FINE TUNING). Any mockup or design review must read the source, and no
new capture can be produced — D-056 retired the capture pipeline.

**Layout risk worth a design pass:** `styles.toggleRow` is
`{ flexDirection: 'row', gap: 6 }` with `flex: 1` children and `minHeight: 44`
(`:1302-1310`). Five chips already share a row alongside a label column; a third
such row deepens an already-long sheet. Whether five chips at that width still
clear the 44pt tap target and stay legible is a real question, and the frozen
captures cannot answer it — the operator's TestFlight pass is the only check.

---

## 11. File ownership, and the #362 collision

### 11.1 Proposed ownership for #360/#361

**Backend**
- `backend/trade_service.py` — pool exclusions (sites 3, 4, 5), signature
  threading, `targeted` predicate `:3294`, never-relaxed docstring `:3491`
- `backend/trade_optimizer.py` — sites 1, 2 *(almost certainly uncontested)*
- `backend/database.py` — column, migration entry, upsert/load
  *(almost certainly uncontested)*
- `backend/server.py` — pref loads `:5179-5188` + `:11031-11073`, the §5.1
  contradiction guard, likes-you site 6 `:3019-3021`, route
  `:15380`/`:15455-15510`
- `config/features.json`, `backend/feature_flags.py`
- new `backend/tests/test_avoid_positions.py`

**Mobile**
- `mobile/src/components/TradeDnaSheet.tsx` — **exclusive**
- `mobile/src/api/league.ts` — **exclusive**
- `mobile/src/state/useFeatureFlags.ts` — one line
- `mobile/src/screens/TradesScreen.tsx` — **two narrow regions only** (see below)
- new `mobile/tests/check-avoid-positions.js` + `mobile/package.json` script

**Docs:** per §9.4.

### 11.2 The collision is real — `TradesScreen.tsx` and `server.py`

I could not read #362's plan (`docs/feedback/items/` has no 362 folder at this
sha), so this is reasoned from the feature description rather than from its file
list. On that basis:

**Yes, expect a collision on `mobile/src/screens/TradesScreen.tsx`.** It is 7,563
lines and is the deck surface — a standing-offer feature almost certainly touches
it. `backend/server.py` is a likely second. This is the same shape as the
documented G6/G4 case ("disjoint functions, same file — coordinate the merge",
`docs/feedback/items/304-positional-need-filter/plan.md` §3, §6).

**Recommendation: parallel build is fine, with two conditions.**

1. #360/#361 confines its `TradesScreen.tsx` edits to exactly two named regions —
   the `receiptDetails` memo (`:1058-1074`) and the empty-state toast branch
   (`:6274-6293`) — and touches nothing else in that file. Both are small,
   self-contained, and far apart, so a rebase is mechanical.
2. #360/#361 takes **exclusive** ownership of `TradeDnaSheet.tsx` and
   `api/league.ts`; #362 must not edit either. If #362 needs a control in the same
   sheet, the two features must serialize instead — a two-way concurrent edit of
   `toggleDnaPos` and the autosave payload would be a merge hazard with a silent
   failure mode (§10.1).

If #362's actual file list contradicts this, serialize: land #360/#361 first (it
is the smaller, more contained change) and rebase #362 on top.

---

## 12. Risks and spikes

| # | Risk | Mitigation |
|---|---|---|
| **R1** | **Deck thinning.** Pool exclusion shrinks the search space on every opponent; avoiding two positions could materially thin decks. | §6.2's relaxed pass is the runtime valve. For pre-ship measurement, `scripts/deck_eval.py` is the G6-era harness — **but its corpus (`feedback-workspace/deck-eval/…`) is gitignored scratch and is not present in this worktree.** Do not promise a measured number until someone confirms the corpus can be regenerated. Recommend a **spike** (S1): confirm corpus availability, then replay avoid-QB / avoid-TE and report deck-size delta. If the corpus is gone, ship on the tripwire instead — `server.py:5100-5110` already logs a presentment tripwire and is the natural place for an avoid-attributed counter. |
| **R2** | **gen-v2 leak.** §8 — a knob flip serves cards from a generator that ignores every positional preference. | Operator ruling Q-A1 before build. |
| **R3** | **PICK identity.** `_positions_ok` and the proposed exclusion read raw `player.position`. `docs/cross-client-invariants.md:380` records that `build_universal_pool` stamps the 12 **generic** pick rungs with a **fake** position (`_PICK_POS = {1:"RB",2:"WR",3:"TE",4:"QB"}`, `server.py:1479-1484`) — so a generic 4th-round rung is typed **QB**. Owned picks carry `position == "PICK"` (`server.py:10320`). The canonical predicate is `trade_service.is_pick_asset` (`:1549-1557`): `position == "PICK" or team == "PICK"`. Two shipped bugs (#222, the 2026-08-18 B3 sweep) came from re-deriving pick identity. | Deck-side this is **currently moot** — generic rungs live in the ranking pool, not on rosters, so they cannot enter a receive package. But the correct predicate is cheap: `pos_of(p) = "PICK" if is_pick_asset(p) else p.position`. Using it makes Avoiding *more* correct than the existing `_positions_ok`, which is a knowing asymmetry — record it, or fix all three sites. **Operator call (Q-A2).** Surgical-changes rule says don't fix the neighbours unasked. |
| **R4** | **Contradictory config ⇒ silent zero deck.** | §5.1 guard + dedicated regression test. Highest-value test in the suite. |
| **R5** | **Mobile autosave drops the third list** ⇒ mutual-exclusion clears don't persist. | §10.1; pinned by the structural test. |
| **R6** | **Migration.** Additive `ALTER TABLE` on Postgres in prod. | Mirrors `acquire_positions` exactly (`database.py:2445-2446`); the existing pair is the working precedent. Low. |
| **S1** | Spike: deck-eval corpus availability (see R1). | Before build. |
| **S2** | Spike: read #362's actual file list and confirm or revise §11.2. | Before parallel build starts. |

---

## 13. Open questions for the operator

- **Q-A1 (blocking, §8):** `trade_gen_v2.py` reads no positional preferences at
  all, and `trade.bakeoff` is ON with serving dark behind a knob, not a flag.
  Port the Avoiding exclusion into gen-v2 now, or rule that
  `bakeoff_serve_interleaved` stays 0 until gen-v2 honors preferences? *(Related
  pre-existing finding: interleaved serving would already break Chasing/Shopping
  today.)*
- **Q-A2 (§12 R3):** Should Avoiding use the canonical `is_pick_asset` predicate
  — making it stricter-and-correcter than the existing `_positions_ok`, which
  reads raw `position` — or match the existing sites' behavior for consistency?
  Planned default: use the canonical predicate for the new code, leave the
  existing sites alone, record the asymmetry.
- **Q-A3 (§4, site 6):** Confirm Avoiding applies to likes-you injections.
  Planned default: **yes** — it is a user constraint like #163/untouchables, not
  a deck-quality rule, so the G6 Q21 quality exemption does not reach it.
- **Q-A4 (§4.2):** Confirm eveners stay out of scope. Planned default: **yes** —
  `_roster_eveners` does not apply #163 either, so including Avoiding there would
  make the position filter stricter than the player filter on the same surface.
- **Q-A5 (§5):** Confirm the asymmetry — Chasing ⊕ Avoiding mutually exclusive,
  **Shopping + Avoiding co-selectable**. This is the operator's own
  "selling my QB, don't want another back" case and it needs to be an explicit,
  recorded decision (D-360-1) rather than an implementation detail, because the
  obvious three-way-exclusion implementation silently deletes it.
- **Q-A6 (§9.1):** New analytics event, or stored-state query only? Planned
  default: no new event; adoption comes from `league_preferences.avoid_positions`.
- **Q-A7 (§7):** Web parity — follow-up item, or same wave? Planned default:
  follow-up (verified no data loss in the meantime).

Next OPEN_QUESTIONS id is **Q-031** (was Q-024 when this plan was written; `origin/main` advanced repeatedly — renumbered again 2026-08-26 to clear Q-026, which main had also taken); the four decisions are
recorded item-scoped as **D-360-1…D-360-4** in `prd.md` §2 (sequential ids D-093–D-096 were taken by `origin/main` before ship).
