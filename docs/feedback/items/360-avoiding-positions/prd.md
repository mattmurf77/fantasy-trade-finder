# PRD — "Avoiding" positions (#360 / #361)

> **Status:** build contract. Author agent, 2026-08-19, from `plan.md` in this
> folder + the orchestrator's rulings on Q-A1…Q-A7.
> **Base sha:** `f68eddd` (`origin/main` + one commit). Every `file:line` below
> was re-read at that sha this session.
> **Companions:** `scope.md` (gates), `lld-delta.md` (exact interfaces — the
> API contract lives there), `hld-delta.md` (one line, n/a).
> **Gate posture:** FULL gates. Schema change = CLAUDE.md bright line.

---

## 1. What we are building, in ordinary words

A third row in the Trade DNA sheet, under **Chasing** and **Shopping**, called
**Avoiding**. Tap a position there and the trade finder will never build you a
trade that sends that position your way. It is a promise, not a preference —
there is no "less often", no multiplier, no ranking nudge. If you avoid QB, no
card in your deck contains a QB coming to you. Full stop.

Feedback, verbatim:

- **#360** — "Forget if I've mentioned before but an option right next to the
  shopping for and willing to sell positions we should have positions we're not
  looking for (eg I don't want QB, TE)"
- **#361** — "Well I guess I can just select the other positions I do want but
  perhaps doesn't hurt to add a no flag since the logic is already there"

**#361's own workaround does not work, and that is the strongest reason to
build this.** Chasing is an `any()`, not an `all()`
(`backend/trade_optimizer.py:420-427`, duplicated at
`backend/trade_service.py:4564-4577`): setting Chasing = WR, RB requires that
*at least one* received player is a WR or RB. A 2-for-2 that sends you a WR
**and a QB** passes that gate cleanly. The user gets exactly the thing they said
they didn't want, riding along in the same package. No existing preference —
Chasing, Shopping, or otherwise — can express a negative receive constraint at
position granularity. Shopping constrains `give_ids` only.

---

## 2. Decisions recorded (rationale, not just verdicts)

Each of these is a real decision with a real alternative that was considered.
The three marked **D-0xx** go into `living-memory/DECISIONS.md`.

### D-093 — Hard pool exclusion, not a soft multiplier

**Decision:** Avoiding is a hard exclusion applied at *pool construction*.
The dormant `pos_conflict_penalty` knob (`backend/database.py:2187` seed row;
`backend/trade_service.py:98` default) is **left untouched and dormant**.

**Why not revive the knob** — it was the tempting option, and the history
argues against it. `pos_conflict_penalty` is not an unbuilt spec waiting for an
implementer; it is the third member of a **retired design**. Its two siblings
`pos_acquire_bonus` and `pos_tradeaway_bonus` (`database.py:2185-2186`,
`trade_service.py:96-97`) are equally dead, and `docs/glossary.md:116` records
why: the v2 rebuild deliberately replaced the soft positional multipliers with
hard filters, "the old soft multipliers (`pos_acquire_bonus` etc.) are deleted
from code though their `model_config` keys remain." Reviving the negative third
would re-introduce, for one case only, precisely the architecture the rebuild
consciously abandoned for the other two — leaving one row of the UI behaving
categorically differently from the two rows directly above it.

Supporting, in descending weight:

- **The user's own model.** #361 asks for a "no **flag**". A flag is binary.
  An "I don't want QBs" that still shows QBs 15% less often is
  indistinguishable from a bug, and the user has no instrument to tell the
  difference.
- **Precedent density.** Every negative preference in this codebase is a hard
  filter: untouchables (give side, never relaxed), #163 `not_interested`
  (receive side, never relaxed), pinned give/receive. There is no soft negative
  anywhere.
- **The never-relaxed guarantee comes free.** See D-096 below.
- **No new `model_config` key** ⇒ no edit to the knob-inventory golden in
  `backend/tests/test_bakeoff_arm_a_golden.py`, and no default to calibrate.

**Why pool exclusion rather than extending `_positions_ok`** (the other "hard"
option): the consensus path, used for unranked opponents, **has no
`_positions_ok` at all** — it restricts the receive pool by position instead
(`backend/trade_service.py:4941-4942`). Pool exclusion is therefore the only
mechanism uniform across all generator paths, and in that path it is already
the local idiom. It is also strictly cheaper (smaller search space rather than
enumerate-then-discard) and it covers sweeteners for free.

### D-094 — Shopping + Avoiding are co-selectable; Chasing ⊕ Avoiding are not

*(Orchestrator ruling Q-A5, recorded as a decision because the obvious
implementation silently destroys the headline use case.)*

| Pair | Coherent? | Rule |
|---|---|---|
| Chasing ∩ Shopping | no | mutually exclusive — **existing**, `TradeDnaSheet.tsx:474-500` |
| Chasing ∩ Avoiding | no | mutually exclusive — **new** |
| **Shopping ∩ Avoiding** | **yes, and it is the modal case** | **must be co-selectable** |

"I'm selling my QB and I don't want another one back" compiles to *"at least one
given player is a QB, and zero received players are QBs"*. Shopping gates
`give_ids`; Avoiding gates the receive pool. They are disjoint sides of the same
trade and cannot contradict. The naive "make all three mutually exclusive, like
the existing two" implementation makes the single most common real usage
**unexpressible**. This is the highest-risk misimplementation in the feature and
is pinned by both a structural test (§7.2 A-3) and a pytest (§7.1 T-3).

### D-095 — An exclusion beats a pin; Avoiding applies exactly where `not_interested` applies

**Two questions, one rule.**

**(a) Where does Avoiding apply?** *Exactly at the seams where
`not_interested` (#163) is applied today, and nowhere else.* This is the
governing scope rule for the whole feature. It is not an aesthetic preference —
it makes every scope question mechanically decidable by
`git grep -n not_interested -- backend`, and it is the rule that already
justifies the orchestrator's Q-A4 ruling (eveners are out **because**
`_roster_eveners` reads only `untouchables`, verified at
`backend/server.py:1046-1049` — `not_interested` is not applied there either, so
including Avoiding would make the position-level filter stricter than the
player-level one on the same surface).

The rule yields seven seams (`lld-delta.md` §4). It also cleanly excludes the
legacy v1 generator `_generate_for_pair` (`backend/trade_service.py:5094`),
which applies neither exclusion list and is unreachable anyway.

**One place the rule and the orchestrator's ruling disagree — see §5.1.**

**(b) What happens when a pinned receive target's position is avoided?**
*The exclusion wins.* This question is not in `plan.md`, and it is not a new
invention to answer it — it is the shipped house rule, stated in the consensus
path's own comment at `backend/trade_service.py:4929-4930`:

> "#163 — not-interested players never enter the receive pool (filtered at the
> source; the target re-add below iterates this filtered list too, **so an
> exclusion always wins**)."

The v3 path is built identically: `known_opp` is filtered at `:359-361`, and
both the `pinned_recv_set` re-add (`:407-410`) and the `target_ids` re-add
(`:412-415`) iterate that already-filtered list. So pinning a QB while avoiding
QB yields an empty result, exactly as pinning a not-interested player does
today.

**This is only acceptable because it is not silent.** R-9 requires the empty
state to name Avoiding as the cause, and `receiptDetails` (R-10) keeps the
avoid set permanently visible above the deck. Without both, this decision would
be the "silent zero deck" failure and should be reversed.

### D-096 — The never-relaxed guarantee is structural, and must be written down anyway

Adding `avoid_positions` to the #189 `targeted` predicate
(`backend/trade_service.py:3294-3295`) gives a narrowed job the same staged
widening the other narrowing preferences get. The safety property comes free:
`_relaxed_targeted_pass` (`:3479-3533`) relaxes only the fairness band and the
surplus floor and re-runs `_generate_trades_v2` with the *same* kwargs. Because
Avoiding lives in pool construction rather than in a relaxable gate, **it is
structurally impossible for the relaxed pass to relax it** — no code is needed
to guarantee that.

Write it down regardless, in the `NEVER relaxed` docstring at
`backend/trade_service.py:3492-3501` (which already names untouchables and the
G6 rules). The guarantee that costs nothing to hold is the one nobody notices
they have broken.

### Non-decisions, recorded so they are not re-litigated

- **Analytics: no new event.** Full waiver with the alternative named and
  costed — `scope.md` §1 (orchestrator ruling Q-A6).
- **Eveners: out of scope.** Orchestrator ruling Q-A4; the consistency argument
  is in D-095(a) above, stated so the next reader does not read it as an
  oversight.
- **Web parity: follow-up, not this wave.** Orchestrator ruling Q-A7. The
  no-data-loss verification is in §5.3.
- **Likes-you injection honors Avoiding: yes.** Orchestrator ruling Q-A3; it
  falls out of D-095(a) automatically, since `not_interested` is applied there
  (`backend/server.py:3021`).

---

## 3. Requirements

Every requirement carries at least one mechanically verifiable pass criterion —
a pytest name (§7.1), a `check-avoid-positions.js` assertion id (§7.2), or a
numbered TestFlight step (§7.3).

### Data & contract

**R-1 — The column exists and defaults to "no positions avoided".**
`league_preferences.avoid_positions`, `TEXT`, JSON array of position strings.
Added additively via `_migrate_db()`. Pre-existing rows read SQL `NULL`, which
`load_league_preference` returns as `[]`. **No backfill.**
*Pass:* `T-1` (fresh DB and migrated-from-NULL row both read `[]`).

**R-2 — `GET /api/league/preferences` always returns `avoid_positions`.**
Always an array, never absent, never `null`, in **both** flag states, and
whether or not a preference row exists. Exact contract: `lld-delta.md` §3.2.
*Pass:* `T-2`; TestFlight step 12.

**R-3 — `POST /api/league/preferences` accepts, normalizes, and echoes
`avoid_positions`.** Optional field. Absent or `null` ⇒ existing value
unchanged (matching the two siblings' `is not None` semantics at
`backend/database.py:8509-8511`). Non-list ⇒ `400`. Values are uppercased,
trimmed, deduped, order-preserved, and any token outside
`{QB, RB, WR, TE, PICK}` is **dropped**; the response echoes the normalized
list that was actually stored. Exact contract and the rationale for
drop-rather-`400`: `lld-delta.md` §3.3.
*Pass:* `T-2` (round-trip), `T-11` (normalization + echo).

### Engine behavior

**R-4 — No served card sends the user a player at an avoided position.**
Applied at pool construction on all four live generator paths — v3, v3
sweetener, v2, consensus. Enumerated with `file:line` in `lld-delta.md` §4,
seams 1–4.
*Pass:* `T-4` (parameterized over all four paths); TestFlight steps 3 and 4.

**R-5 — A player-position avoid never excludes a draft pick.**
*(Orchestrator ruling Q-A2.)* The predicate resolves pick-ness via the canonical
`is_pick_asset` (`backend/trade_service.py:1549-1557`) **before** reading
`position`. The generic pick rungs carry a deliberately **fake** position
(`_PICK_POS = {1:"RB", 2:"WR", 3:"TE", 4:"QB"}`, `backend/server.py:1479-1484`),
so a raw-`position` read would let "avoid QB" delete every 4th-round pick from
the pool. Avoiding **PICK** — one of the five chips — excludes pick assets, and
only that.

This makes Avoiding **stricter and more correct than the neighbouring
`_positions_ok`**, which reads raw `position` at
`backend/trade_optimizer.py:421-422` and `backend/trade_service.py:4565-4576`.
That asymmetry is **known, deliberate, and left in place**: fixing the
neighbours is a behavior change to two shipped features that nobody asked for
(coding-guidelines §3). It is recorded in `lld-delta.md` §2.2 and in the
`docs/cross-client-invariants.md` mirror table.
*Pass:* `T-5` (avoid QB leaves 4th-round rungs and owned picks in the pool);
`T-6` (avoid PICK removes them).

**R-6 — Asset ideas honor Avoiding.** The `/api/trades/asset-ideas` route
gains a `load_league_preference` call and threads `avoid_positions` into
`_generate_asset_ideas_impl`'s three receive-side guards.

Two consequences that are **correct but surprising**, and must be built
deliberately rather than discovered:

1. `direction == "give"`: #198 constrains the Upgrade and Lateral groups to the
   *pinned asset's own position* (`backend/trade_service.py:3776-3779`). So
   "what can I get for my QB?" while avoiding QB returns **Downgrade only** —
   the Upgrade and Lateral groups are empty by construction. That is precisely
   what the user asked for.
2. `direction == "receive"` with the pinned asset itself at an avoided
   position: return the empty result, mirroring #163's identical guard at
   `backend/trade_service.py:3836-3837` (D-095(b)).

*Pass:* `T-7`.

**R-7 — Likes-you injections honor Avoiding.** *(Orchestrator ruling Q-A3.)*
A counterparty's liked trade is mirrored, so their give side **is** the user's
receive side. A boosted, deck-position-1 card that sends the user an avoided
position is the most visible possible way to break the promise. Note this is a
*user constraint*, not a deck-quality rule, so the G6 Q21 exemption — which
exempts likes-you from R1/R2/R3/R5 quality rules — does not reach it, exactly as
untouchables, #163 and the R4 dedup already apply there.
*Pass:* `T-8`.

**R-8 — An exclusion beats a pin.** A `pinned_receive_players` entry or a
Backlog-#2 `target_ids` entry at an avoided position does **not** re-enter the
pool. Implementation is free: the re-add loops already iterate the filtered
list (D-095(b)). This requirement exists so that a build agent does not
"helpfully" add an exemption.
*Pass:* `T-9` (a pinned receive target at an avoided position yields no card,
and specifically does not yield a card containing it).

**R-9 — Avoid + Chase of the same position can never produce a silent empty
deck.** Two independent layers, both required:

- **Server-side (load-bearing):** in `_run_trade_job`, immediately after the
  preference load, drop every avoided position from `acquire_positions` before
  anything downstream sees either list. Avoid wins — a negative promise is the
  stronger commitment and the cheaper one to honor. Log at `INFO` when it fires.
  Without this, `acquire = ["QB"]` + `avoid = ["QB"]` empties every receive pool
  of QBs while `_positions_ok` demands at least one received QB: **zero cards on
  every opponent, forever, with no error.**
- **Client-side (defense in depth):** the sheet's mutual exclusion (R-12) makes
  the state unreachable through the UI. The server guard is still required — an
  older client, a replayed request, or a direct POST can all still send both.

Additionally, when a deck comes back empty **and** `avoid_positions` is
non-empty, the empty-state copy must name Avoiding as a possible cause. Extend
the existing intent-aware toast at `mobile/src/screens/TradesScreen.tsx:1509-1532`
— same mechanism as #172, not a new one. Suggested copy, naming the constraint
the user set:

> `No trades found that avoid ${positions}. Try un-avoiding one.`

*Pass:* `T-10` (the guard fires, drops QB from acquire, and the deck is
non-empty); `A-6` (the toast branch reads `avoid_positions`); TestFlight step 7.

**R-10 — Avoiding is visible above the deck.** `receiptDetails`
(`mobile/src/screens/TradesScreen.tsx:1058-1074`) gains an `Avoiding …` part
using the existing `posLabel` helper at `:1059` (which already maps
`PICK → 'Picks'`), in the order **Chasing · Shopping · Avoiding · <intent> ·
N off the table**. This is what makes D-095(b) honest rather than silent.
*Pass:* `A-5`; TestFlight step 8.

**R-11 — Flag off ⇒ byte-identical.** With `trade.avoid_positions` false and a
populated `avoid_positions` column, every generation path produces the deck it
produces today, and the sheet renders no Avoiding row. The column keeps its data
in both flag states, so flipping the flag back on restores every saved set.
*Pass:* `T-12` (same pattern as the existing flag-off goldens); `A-7`.

### Client

**R-12 — Three-way toggle preserving the D-094 asymmetry.**
`toggleDnaPos` (`mobile/src/components/TradeDnaSheet.tsx:474-500`) extends from
a 2-way to a 3-way move:

| Tapped side | Clears from | Leaves alone |
|---|---|---|
| `chase` | `shop`, `avoid` | — |
| `shop` | `chase` | **`avoid`** |
| `avoid` | `chase` | **`shop`** |

*Pass:* `A-3` (the load-bearing structural assertion); TestFlight step 3.

**R-13 — The autosave payload carries all four lists, at every one of six
sites.** This is the most likely build bug in the feature and it fails
*silently*: if `avoid` is missing from any one of them, a Chasing tap that
clears QB from Avoiding will not persist the clear — the row and the DB diverge,
and the next sheet open re-seeds the stale value. The six sites, verified this
session:

| # | Site | `TradeDnaSheet.tsx` |
|---|---|---|
| 1 | `saveOutlook` mutation `vars` type + body | `:383-392` |
| 2 | `dnaDesired` ref type | `:400-405` |
| 3 | error-revert in `flushDnaSave` | `:426-431` |
| 4 | `queueDnaSave` parameter type | `:439-443` |
| 5 | `pickOutlook`'s call | `:467` |
| 6 | `toggleDnaPos`'s call | `:493-499` |

Plus the seeding effect at `:353-362` (`setDraftAvoiding(prefs?.avoid_positions ?? [])`).
*Pass:* `A-4` (all six pinned structurally); TestFlight steps 3 and 10.

**R-14 — The Avoiding row renders in both sheet variants.**
- `full` variant (`:661-700`): a third `styles.posLine` directly below Shopping —
  label **`Avoiding`**, sublabel **`no thanks`** (matching `Chasing`/"want more",
  `Shopping`/"happy to move").
- **legacy** variant (`:743-786`): the DNA-only half-sheet. It is **live** —
  omitting the `full` prop is what keeps the flag-off path byte-identical
  (`:71-73`), so this branch must not be skipped. Its hint paragraph at
  `:781-785` currently reads *"A position can't be both chased and shopped"* and
  **must be rewritten** to state the three-way rule **including the
  Shopping + Avoiding exception** — a hint that still claims two-way exclusion
  after D-094 ships is actively wrong documentation in the product.

*Pass:* `A-1`, `A-2`, `A-8` (the hint no longer claims two-way exclusion);
TestFlight steps 1 and 2.

**R-15 — Chalkline compliance.** Per `docs/design/design-system.md`:
- The selected-state glyph on an Avoiding chip is **`x`**, not `check`.
  `DnaToggle` (`:109-149`) uses `Icon name="check"` and its own comment states
  the rule — *"the check is the primary state cue, never color alone"*. A check
  meaning "avoided" inverts that cue. `x` exists in the icon set
  (`mobile/src/components/chalkline/Icon.tsx:70`). This requires a new optional
  `glyph` prop on `DnaToggle`, defaulting to `check` so the two existing rows
  are untouched.
- No emoji as icons. No gradients. Position chip fills stay the existing
  `dnaPosColor` data encoding (`:101-104`), governed by
  `docs/cross-client-invariants.md` — **not** re-colored to a semantic
  "danger" red, which would both break the position encoding and use a
  non-sanctioned accent.
- `accessibilityRole="checkbox"` retained; `accessibilityLabel` is
  `Avoid ${label}`.

*Pass:* `A-9` (Avoiding row passes `glyph="x"`; the two existing rows pass no
`glyph`); TestFlight step 1.

**R-16 — Avoiding all five positions is allowed, and honest.**
The UI does **not** block the fifth tap, and the backend does **not** silently
treat "avoid everything" as "avoid nothing". Silently disobeying a saved
preference to dodge an awkward empty state is the exact
invented-state-change failure the repo's own feedback lesson names. The user gets
an empty deck and the R-9 copy explaining why.
*Pass:* `T-13` (empty deck, no exception, no hang); TestFlight step 9.

---

## 4. Success criteria

1. A user who taps Avoiding QB and re-runs the finder can swipe the **entire**
   deck without seeing a single QB on the receive side of any card — headline or
   package filler, on any generator path, including a boosted likes-you card.
2. A user who sets Shopping QB **and** Avoiding QB together still gets cards,
   and those cards send their QB out. (D-094; the feature's headline use case.)
3. Turning `trade.avoid_positions` off restores today's decks byte-for-byte
   without a deploy, with no data loss.
4. CI green on the pushed sha: `backend-tests`, `mobile-typecheck` (tsc + the
   `check-*.js` loop), `maestro-testid-lint`.
5. The operator's TestFlight checklist (§7.3) passes end to end, and the outcome
   is logged in `living-memory/TEST_LEDGER.md`.

---

## 5. Out of scope — with reasons, not just names

### 5.1 `trade_gen_v2.py` — OUT, per orchestrator ruling Q-A1, **with a guardrail and a caveat I am obliged to state**

**The ruling:** `trade_gen_v2` is out of scope. Avoiding must not become the
feature that silently fixes an unrelated engine gap. **I am building to this.**

**The caveat, stated loudly as instructed.** The ruling's stated rationale is
that gen-v2 "reads no positional preferences at all today, so Chasing and
Shopping are *already* not honored there". The first half is true. But gen-v2
**does** apply the per-player negative constraints: `not_interested_ids` at
`backend/trade_gen_v2.py:509`, filtered at `:530`, and `untouchable_ids` at
`:533`. Since this feature's entire architecture is *"Avoiding is the positional
twin of `not_interested`"* (D-095(a)), the governing scope rule points **into**
gen-v2, not away from it. The ruling is a defensible product call — gen-v2 is
dark for serving — but it is not the free consequence of an existing gap that
the rationale describes, and the next reader deserves to know that.

**Why I am not escalating further:** serving is genuinely dark
(`bakeoff_serve_interleaved = 0.0`, `backend/trade_service.py:508`; gate at
`backend/bakeoff_runner.py:211`, note at `:196` "back to 0.0 = DARK (operator,
2026-08-19)"), so nothing user-visible leaks today. The exposure is a **knob**,
not a flag — it flips without a deploy.

**Guardrail, required as part of this wave:**

> Do not raise `bakeoff_serve_interleaved` above `0` until `trade_gen_v2`
> honors `acquire_positions`, `trade_away_positions`, **and** `avoid_positions`.

Add that line to `docs/config-reference.md:779` (the
`bakeoff_serve_interleaved` row) and to `backend/feature_flags.py:833` (the
`trade.bakeoff` comment block) — the two places the bake-off arm is documented.

**Deliverable — `living-memory/OPEN_QUESTIONS.md` entry `Q-031`.**
**Renumbered 2026-08-19 (was `Q-024`):** `origin/main` advanced mid-build and
took both `Q-024` (the `check-*.js` CI-contract question) and `Q-025` (Team
Review waivers), so max is now `Q-025`. **Wording constraint,
per the ruling:** the headline is the **pre-existing Chasing/Shopping gap**, not
the Avoiding one. Draft title:

> **Q-031 — `trade_gen_v2` ignores positional preferences entirely; interleaved
> serving would break Chasing and Shopping today**

with Avoiding named in the body as the reason the question surfaced and as the
third list to fix, never as the headline.

### 5.2 Everything else that is out

| Surface | Verdict | Reason |
|---|---|---|
| **Eveners** (`_roster_eveners`, `backend/server.py:1027`, reached from `/api/trade/evaluate`) | out | Q-A4. Decisive and mechanical: that function reads asset preferences at `:1046-1049` and takes **only `untouchables`** — `not_interested` is not applied there either. Including Avoiding would make the position-level filter **stricter than the player-level one on the same surface**, which is backwards. This is consistency, not an oversight. |
| **The give side** | out | #360's wording — "positions we're not looking for" — is unambiguously about what *arrives*. A reasonable reader could stretch "I don't want QB" into "keep QBs out of the trade entirely"; that reading is wrong, and Shopping already owns the give side. |
| **Legacy v1 `_generate_for_pair`** (`backend/trade_service.py:5094`) | out | Applies neither `untouchable_ids` nor `not_interested_ids`, so D-095(a) excludes it. Unreachable in production (`trade_engine.v2 = true`). |
| **`web/`** | follow-up | Q-A7. Verification in §5.3. |
| **`extension/`** | n/a | `git grep -n "preferences\|acquire_pos" -- extension` returns nothing; the extension never reads league preferences. |
| **`mobile/src/screens/TradeFinderHubScreen.tsx`** | **do not touch** | It duplicates the whole Chasing/Shopping editor (`:299-303`, `:322-323`, `:341-344`, `:383-384`) but is **UNROUTED** — `mobile/src/navigation/TabNav.tsx:37` ("TradeFinderHubScreen is unrouted (guided-first landing)"). Dead code kept in tree per #246. **Explicit warning to the build agent:** a `git grep acquire_positions -- mobile/src` makes this look like a required second edit. It is not. It will, however, need a compile-only fix once `avoid_positions` is required on `LeaguePreferences` — see `lld-delta.md` §6.3. |
| **`pos_conflict_penalty` / `pos_acquire_bonus` / `pos_tradeaway_bonus`** | leave dormant | D-093. Named, not deleted. |
| **`backend/server.py:15483` dead `valid_positions`** | leave | Dead and wrong (omits `PICK`), but fixing it would newly reject payloads the shipped client sends. Surgical changes. Recorded in `scope.md` §6. |

### 5.3 Web parity — the no-data-loss verification, re-verified this session

The web outlook modal (`web/js/app.js`) sends `acquire_positions` and
`trade_away_positions` explicitly and will omit `avoid_positions`. That is
**safe**, and it is a verified guarantee rather than an assumption:
`upsert_league_preference` writes a positional field **only when it is not
`None`** (`backend/database.py:8509-8511`), and the insert branch defaults an
absent field rather than nulling it (`:8528-8533`). A web save therefore
**preserves** an avoid set written from mobile.

**The build agent must not change this behavior**, and `T-14` pins it: a POST
that omits `avoid_positions` leaves a stored non-empty value intact.
Web parity ships as a follow-up feedback item.

---

## 6. Guardrails

1. **Never delete a pick for a player-position avoid.** R-5. The two shipped
   bugs from re-deriving pick identity (#222, the 2026-08-18 B3 sweep) are why
   `docs/cross-client-invariants.md:380` exists. Call `is_pick_asset`; do not
   re-implement it.
2. **Never let Avoiding become relaxable.** D-096. If a future change moves the
   filter from pool construction into a gate, the #189 relaxed pass will start
   relaxing it, silently.
3. **Never silently override a saved preference.** R-16. "Avoid everything"
   produces an honest empty deck, not a quiet reset to "avoid nothing".
4. **Never ship a zero-deck path without copy.** R-9. The server guard *and*
   the empty-state copy, or neither is done.
5. **Do not fix the neighbours.** `_positions_ok`'s raw-`position` read
   (R-5) and `trade_gen_v2`'s missing positional prefs (§5.1) are both
   pre-existing. Record them; do not repair them in this wave.
6. **Flag off is byte-identical, and is tested, not asserted.** R-11 / `T-12`.
7. **Deck thinning is a real risk with no pre-ship measurement.** Pool exclusion
   shrinks the search space on every opponent. `plan.md` §12 R1 established that
   the `scripts/deck_eval.py` corpus lives in gitignored scratch and is **not
   present in this worktree** — so **do not promise a measured deck-size delta.**
   The runtime valve is the #189 relaxed pass (D-096); the runtime signal is the
   existing presentment tripwire near `backend/server.py:5100-5110`. If the
   operator wants a number before ship, that is a spike, not part of this build.

---

## 7. Test plan (D-056: no Maestro, no simulator, no captures)

Every behavioral test below names the **sabotage that must turn it red**. A test
whose sabotage cannot be stated is a test that cannot fail, and four of those
shipped once already (`mobile/tests/check-league-candidates-300.js` header).

### 7.1 Backend unit tests — `backend/tests/test_avoid_positions.py` (new file)

| id | Test | Proves | Sabotage that must turn it red |
|---|---|---|---|
| **T-1** | `test_column_defaults_to_empty_list` | R-1 | Change `_parse_positions` to return `None` for falsy input, or drop the `migration_cols` entry. |
| **T-2** | `test_prefs_route_roundtrip` | R-2, R-3 | Remove `avoid_positions` from the GET payload dict, or from the `upsert_league_preference` call. |
| **T-3** | **`test_shop_and_avoid_same_position_still_generates`** | **D-094** | Make Shopping and Avoiding mutually exclusive server-side (drop avoided positions from `trade_away_positions`). The deck goes empty; assert both non-empty **and** that a card's give side contains the position. **This test is the feature.** |
| **T-4** | `test_no_avoided_position_received[v3\|v3_sweetened\|v2\|consensus]` | R-4 | Remove the predicate from any one of the four seams — the parameterization is what makes a single-seam miss visible. |
| **T-5** | `test_avoid_qb_keeps_pick_rungs` | R-5 | Replace `_pos_for_avoid` with a raw `p.position` read. Round-4 generic rungs carry a fake `"QB"` and vanish. |
| **T-6** | `test_avoid_pick_removes_pick_assets` | R-5 | Drop the `is_pick_asset` arm so `"PICK"` matches only owned-pick pseudo-assets and generic rungs survive. |
| **T-7** | `test_asset_ideas_honor_avoid` | R-6 | Remove the new `load_league_preference` call in the asset-ideas route; the kwarg silently defaults to `[]`. |
| **T-8** | `test_likes_you_injection_refuses_avoided_position` | R-7 | Remove the position-set intersection at `backend/server.py:3021`. A mirrored card carrying an avoided position is injected at deck position 1. |
| **T-9** | `test_exclusion_beats_pinned_receive` | R-8, D-095(b) | Add a pin exemption — re-add `pinned_recv_set` members from the **unfiltered** roster. |
| **T-10** | **`test_avoid_and_chase_same_position_is_not_a_silent_zero_deck`** | **R-9** | Remove the `_run_trade_job` guard. Every opponent yields zero cards with no error — the single highest-value regression in the suite. |
| **T-11** | `test_post_normalizes_and_echoes` | R-3 | Skip normalization: `["qb", "DEF", "QB"]` stores verbatim and the echo lies about what was stored. |
| **T-12** | `test_flag_off_deck_is_byte_identical` | R-11 | Read the column unconditionally instead of behind `FLAGS.trade_avoid_positions`. Follows the existing flag-off golden pattern. |
| **T-13** | `test_avoid_all_positions_yields_empty_deck_no_exception` | R-16 | Add an "avoid everything ⇒ treat as unset" override; the deck comes back non-empty and the assertion flips. |
| **T-14** | `test_post_omitting_avoid_preserves_stored_value` | §5.3 | Change `upsert_league_preference` to write `[]` when the field is absent; a web save wipes a mobile-set avoid list. |

### 7.2 Structural guard — `mobile/tests/check-avoid-positions.js` (new file)

Plain node, parsing the real TSX with the project's own TypeScript. Same harness
family as `check-dna-side-order.js`. Assertions that read "X appears nowhere"
must read **comment-stripped** source — the header comments in these files name
the constructs they forbid, which is exactly how four un-failable tests shipped
before.

| id | Assertion | Sabotage |
|---|---|---|
| **A-1** | The `full` variant contains three `styles.posLine` blocks, in source order Chasing → Shopping → Avoiding (RN lays a column out in child order, so source order **is** screen order). | Insert Avoiding above Shopping, or omit it. |
| **A-2** | The legacy variant contains an Avoiding `DNA_POSITIONS.map` block with `dna.avoid.` testIDs. | Add the row to `full` only — the legacy branch is live and would silently lack it. |
| **A-3** | **In `toggleDnaPos`, the `avoid` branch filters `draftChasing` and does **not** filter `draftShopping`; the `shop` branch does not filter avoid.** AST-level, not textual. | Implement three-way mutual exclusion. **This assertion is worth the whole file** — it is the only mechanical check on D-094. |
| **A-4** | All six R-13 payload sites carry an `avoid` key. | Omit it from any one; the clear silently fails to persist. |
| **A-5** | `receiptDetails` reads `avoid_positions` and pushes its part after `shopping`. | Drop the part, or order it before Shopping. |
| **A-6** | The empty-state toast branch at `TradesScreen.tsx:1509-1532` references `avoid_positions`. | Ship the server guard without the copy. |
| **A-7** | Every Avoiding render site is behind the `trade.avoid_positions` flag read. | Render it unconditionally; flag-off stops being byte-identical. |
| **A-8** | The legacy hint no longer contains the string `both chased and shopped`, and does mention avoiding. | Leave the stale hint — actively wrong in-product documentation. |
| **A-9** | `DnaToggle` invocations in the Avoiding row pass `glyph="x"`; the Chasing and Shopping rows pass no `glyph`. | Reuse `check` for Avoiding, inverting the state cue (R-15). |
| **A-10** | `'trade.avoid_positions'` appears in **both** `config/features.json` and `LAUNCHED_FLAG_DEFAULTS` with the same value — compare the two files, do not assert a literal (the pattern `check-league-candidates-300.js` §1 uses). | Add it to one file only: the row paints for one frame and then vanishes (`useFeatureFlags.ts:62-70`). |

### 7.3 Manual TestFlight checklist (operator)

The only runtime evidence mobile gets. Written as a regression suite.

| # | Step | Expected |
|---|---|---|
| 1 | Trades → open the DNA sheet. | A third row **Avoiding / "no thanks"** sits directly under Shopping, with five chips (QB RB WR TE Picks). Tapping one fills it and shows an **✕** glyph, not a check. Chips are ≥44pt tall and legible. |
| 2 | Read the sheet's hint text (legacy half-sheet entry point, if reachable). | It describes the three-way rule and states that Shopping + Avoiding *can* both be set. It must **not** still say "can't be both chased and shopped". |
| 3 | Set Chasing = QB. Then tap Avoiding **QB**. | QB **clears** from Chasing and lights in Avoiding. |
| 4 | Set Shopping = QB (with Avoiding QB still on). | **Both stay lit.** This is D-094; if Shopping clears, stop — the build is wrong. |
| 5 | Close the sheet, re-run the finder, and swipe the **entire** deck — not just the first few cards. | No card sends you a QB, in **any** package position, including sweeteners and any card badged as a counterparty like. |
| 6 | Confirm the cards from step 5 send your QB **out**. | They do. Shopping still works alongside Avoiding. |
| 7 | Clear Shopping. Set Chasing = QB and Avoiding = QB together via a direct sequence (tap Chasing QB, then Avoiding QB, then Chasing QB again). | The UI never lets both be lit. Re-run: you get cards, not an empty deck and not a spinner. |
| 8 | Look at the banner above the deck. | It reads `… · Avoiding QB` alongside Chasing / Shopping / off-the-table. |
| 9 | Avoid **all five** positions and re-run. | An honest empty state naming Avoiding as the cause. **Not** a spinner, not a crash, and not a deck of results. |
| 10 | Un-avoid one position. Force-quit the app and relaunch. Reopen the sheet. | Exactly the positions you left avoided are still lit. Nothing re-seeded stale. |
| 11 | Re-run the finder after step 10. | The un-avoided position can now appear on the receive side. |
| 12 | Open the **same league** in the web app, save an outlook there, return to mobile, and reopen the sheet. | Avoiding survived untouched. (This is the §5.3 no-data-loss claim, verified by hand — the one part of the web-parity deferral that could bite a user.) |

### 7.4 Code-walk proof

`docs/feedback/items/360-avoiding-positions/code-walk.md`, written by the
backend build agent. A `file:line`-cited trace showing:

1. All **seven** receive-side seams (`lld-delta.md` §4) are on the filtered path.
2. Both preference loaders pass the third list.
3. The two exempt seams (eveners, `trade_gen_v2`) are exempt **by the D-095(a)
   rule**, not by omission — with the `not_interested` grep that proves it for
   eveners and the §5.1 caveat restated for gen-v2.
4. The flag-off path reaches none of them.

---

## Build deviations — recorded 2026-08-19 (orchestrator)

> The PRD must stay true, because QA tests against it. These are the places the
> shipped build differs from the spec above, with the reason each was accepted.

**D-1 — Hazard A-10 is REVERSED. `trade.avoid_positions` is deliberately NOT in
`LAUNCHED_FLAG_DEFAULTS`, and no test asserts its presence.**
A-10 was written before this session learned that the map **fails open** by design
(the `#115` comment in `mobile/src/state/useFeatureFlags.ts`): a first-ever boot with
no cached map, or a failed revalidate, keeps listed features ON. For a flag whose
entire job is to be a kill switch, listing it means a client with a failed revalidate
keeps rendering the Avoiding row *after the operator kills the flag* — the sheet would
go on accepting a preference the engine has stopped honoring. A silently-ignored user
promise is strictly worse than the one-frame paint-in that omitting the key causes.
The one-frame pop-in is accepted. Reasoning is written into comments at both gating
sites (`TradeDnaSheet.tsx`, `TradesScreen.tsx`) and in the check file's header.
This is the same trap that `mobile/src/api/league.ts:709` warns about for
`outlook.odds`; see D-094 in the parallel Team Review work.

**D-2 — Hazard A-8 reworded rather than implemented literally.**
A-8 asked for the string `both chased and shopped` to be removed from the file
entirely. That is incompatible with **R-11 (flag-off ⇒ byte-identical)**, which this
same PRD requires: with the flag off the Avoiding row does not exist and the two-way
sentence is the *correct* copy. Shipped as a conditional on `avoidOn`, with the
flag-**ON** branch pinned instead (checks A-8b/c/d). Sabotage-proven.

**D-3 — `saveLeaguePreferences` has FOUR object-literal call sites, not five.**
`lld-delta.md` §5.1 said five and `plan.md` said two. The four are
`TradeDnaSheet.tsx:388`, `TradeFinderHubScreen.tsx:341`, `TradesScreen.tsx:1019`,
`TradesScreen.tsx:4449`. All four carry `avoid_positions`.

**D-4 — `avoidOn` had to be introduced in `TradesScreen.tsx`.**
§5.3's table describes regions 2 and 3 as though the flag were already in scope there.
It was not; added beside `intentModesOn`.

**D-5 — OPEN FOR THE OPERATOR: the one-tap outlook confirm clears `avoid_positions`.**
§5.3 region 1 specifies that `confirmOutlookMutation` writes empty position arrays, and
it was built as written (`TradesScreen.tsx:1047-1058`). The consequence: a user who has
set Avoiding but has **not** declared an outlook sees the inferred-outlook banner, taps
**Confirm**, and their saved Avoiding set is wiped.

This is **inherited, not introduced** — `acquire_positions` and `trade_away_positions`
are already cleared by the same call, so Avoiding is merely consistent with its two
siblings. It was built as specced rather than "improved" in passing, per the
surgical-changes rule.

It is nonetheless worth an operator decision, because Avoiding reads as a stronger
promise than the other two ("never send me this") and losing it silently is a worse
failure than losing a Chasing hint. **The fix, if wanted, is ~3 lines:** drop all three
position keys from that mutation's payload entirely. The backend contract already
supports it — an omitted position key leaves the stored value **unchanged** (verified
over HTTP during the backend build). That would preserve all three lists on an outlook
confirm and is a strict improvement, but it also changes existing Chasing/Shopping
behavior, which is why it was not done unilaterally.
