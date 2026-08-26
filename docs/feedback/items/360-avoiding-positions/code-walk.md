# Code-walk proof — "Avoiding" positions (#360 / #361)

> Required by `scope.md` §3 and `prd.md` §7.4. Under D-056 this replaces what
> would once have been a simulator capture: a `file:line`-cited trace showing
> that every receive-side seam is on the filtered path, that both preference
> loaders pass the third list, that the two exempt seams are exempt **by the
> stated rule** rather than by omission, and that the flag-off path reaches
> none of it.
>
> **Written by the backend build agent, 2026-08-19**, against the working tree
> on `feat/jon-357-360-362`. Every line number below was read out of the tree
> with `git grep -n` after the change landed, not copied from the plan.

---

## 0. The one-line claim

`avoid_positions` is a **receive-pool exclusion applied at pool
construction**, threaded through call signatures that already carried its two
siblings, and read behind the flag at exactly **one** point of entry per
route. Nothing enumerates a package and then discards it; nothing gates.

The governing scope rule (PRD D-360-3(a)) is: **Avoiding applies exactly where
`not_interested` applies, and nowhere else.** That makes every scope question
mechanically decidable by `git grep -n not_interested -- backend`, and §4
below runs that grep.

---

## 1. The predicate — one definition, one home

`backend/trade_service.py:1549` `is_pick_asset` — the canonical pick predicate,
untouched.

`backend/trade_service.py:1560` `_pos_for_avoid(p)` — resolves pick-ness
through `is_pick_asset` **first**, returning `"PICK"`, and only then falls
through to `getattr(p, "position", None)`. This is why a player-position avoid
can never delete a draft pick: the generic rungs carry a deliberately fake
position (`_PICK_POS = {1:"RB",2:"WR",3:"TE",4:"QB"}`,
`backend/server.py:1479-1484`) for tier display, and a raw `position` read
would let "avoid QB" delete every 4th-round rung.

`backend/trade_service.py:1584` `avoid_ok(pid, players, avoid)` — `True` when
the asset may enter a receive pool. Falsy `avoid` ⇒ everything passes; an
unknown id passes (it cannot be scored anyway).

`backend/trade_optimizer.py:62` imports `avoid_ok` from `trade_service` —
the same direction `filler_ok`, `fit_premium_1for1` and `pick_swap_ok`
already travel. **Not replicated**, despite that file's own
"Replicated helpers" header at `:74-76`: re-deriving pick identity is what
shipped #222 and the 2026-08-18 B3 sweep.

Pinned by `backend/tests/test_avoid_positions.py::test_avoid_qb_keeps_pick_rungs`
and `::test_avoid_pick_removes_pick_assets`, both proven RED against a raw
`p.position` read.

---

## 2. The seven receive-side seams — all on the filtered path

| # | Seam | Line | Form |
|---|---|---|---|
| 1 | v3 receive pool — `known_opp` in `generate_pair_trades_v3` | `backend/trade_optimizer.py:367` | `and avoid_ok(p, players, _avoid)]` |
| 2 | v3 sweetener — candidate list in `_try_sweeten` | `backend/trade_optimizer.py:718` | `and not (side == "receive" and not avoid_ok(p, players, avoid_positions))` |
| 3 | v2 receive pool — `_known_opp` in `_generate_for_pair_v2` | `backend/trade_service.py:4845` | `and avoid_ok(p, self._players, _avoid)]` |
| 4 | consensus receive pool — `_opp_pool` in `_generate_consensus_for_pair` | `backend/trade_service.py:5018` | `and avoid_ok(p, players, _avoid)]` |
| 5 | asset ideas, `direction == "give"` — return pool | `backend/trade_service.py:3843` | `and avoid_ok(p, players, _avoid))` |
| 6a | asset ideas, `direction == "receive"` — pinned-asset guard | `backend/trade_service.py:3908` | `if not avoid_ok(asset_id, players, _avoid): return empty` |
| 6b | asset ideas, `direction == "receive"` — `extras` pool | `backend/trade_service.py:3928` | `and avoid_ok(p, players, _avoid))[:_POOL]` |
| 7 | likes-you injector | `backend/server.py:3149` | `_pos_for_avoid(trade_service._players.get(p)) in avoid_positions` over `their_give` |

Each of seams 1, 3, 4 sits **inside the same list comprehension** as the
`not_interested_ids` clause it was modeled on, one line below it. Seam 2
mirrors the `side == "receive"` shape the `#163` clause at
`backend/trade_optimizer.py:714-716` already uses. Seam 7 sits directly
beneath the `#163` guard at `backend/server.py:3140-3143`.

### 2.1 Why filtering the source is sufficient — and gives R-8 for free

All four generator pools are built once and then **re-added to**. Every re-add
loop iterates the already-filtered list, so an exclusion always wins over a
pin without any additional code:

- **v3** (`backend/trade_optimizer.py`): `recv_pool` is derived from
  `known_opp` at `:410`; the `pinned_recv_set` re-add at `:413-416` and the
  `target_ids` re-add at `:418-421` both iterate `known_opp` — the filtered
  list.
- **v2** (`backend/trade_service.py`): `recv_candidates` derives from
  `_known_opp` at `:4848`; the `pinned_recv_set` re-add at `:4853-4856` and the
  `target_ids` re-add below it both iterate `_known_opp`.
- **consensus** (`backend/trade_service.py`): `recv_pool = list(_opp_pool)` at
  `:5019`; the `target_ids` re-add iterates `_opp_pool`. The comment at
  `:5012-5015` already stated the rule before this change —
  *"the target re-add below iterates this filtered list too, so an exclusion
  always wins."*

No pin exemption was added. `test_exclusion_beats_pinned_receive` pins that,
and was proven RED by re-adding `pinned_recv_set` members from
`opponent.roster` (the unfiltered list).

### 2.2 Signature threading

Every one of these already carried `acquire_positions` /
`trade_away_positions` on adjacent lines; the third goes on the next line in
each, with the same alignment.

| Function | Signature | Call site |
|---|---|---|
| `TradeService._generate_trades_impl` | `backend/trade_service.py:3158` (`avoid_positions` at `:3169`) | `backend/server.py:5652` (`_generate_kwargs`) |
| `TradeService._generate_trades_v2` | `backend/trade_service.py:4028` (`avoid_positions` at `:4041`) | `_v2_kwargs`, `backend/trade_service.py:3327` |
| `TradeService._generate_for_pair_v2` | `backend/trade_service.py:4502` (`avoid_positions` at `:4516`) | `backend/trade_service.py:4317` |
| `trade_optimizer.generate_pair_trades_v3` | `backend/trade_optimizer.py:196` (`avoid_positions` at `:211`) | `backend/trade_service.py:4291` |
| `TradeService._generate_consensus_for_pair` | `backend/trade_service.py:4956` (`avoid_positions` at `:4971`) | `backend/trade_service.py:4258` (`_consensus_kw`) |
| `trade_optimizer._try_sweeten` | `backend/trade_optimizer.py:684` (`avoid_positions` at `:687`) | `backend/trade_optimizer.py:648-659` |
| `TradeService._generate_asset_ideas_impl` | `backend/trade_service.py:3609` (`avoid_positions` at `:3622`) | `backend/server.py:16172` |
| `server._inject_likes_you_cards_impl` | `backend/server.py:3050` (`avoid_positions` at `:3061`) | `backend/server.py:5734` |

Converted **once**, at the top of each consuming function
(`_avoid = set(avoid_positions or ())`), and passed as a list across
boundaries, matching the siblings.

---

## 3. Both preference loaders pass the third list

### (a) The trade job — `backend/server.py:5449-5484`

```
5452        avoid_positions      = []          # #360
...
5463                if FLAGS.trade_avoid_positions:
5464                    avoid_positions  = prefs.get("avoid_positions",      []) or []
```

The flag read is **here**, at the single point of entry, so every downstream
consumer sees `[]` when the flag is off and no other site needs a flag check.
That is what makes "flag off ⇒ byte-identical" a one-line property rather
than eight scattered guards.

Immediately below it, the **R-9 contradiction guard**
(`backend/server.py:5468-5484`) drops every avoided position from
`acquire_positions`, at `INFO`. Its position is load-bearing: it runs
**before** `_presentment_need_gate_bypass(..., acquire_positions)` and before
the `_generate_kwargs` dict at `:5637`, so nothing downstream ever sees the
contradictory pair. Without it, `acquire = ["QB"]` + `avoid = ["QB"]` empties
every receive pool of QBs while `_positions_ok` still demands at least one
received QB — zero cards on every opponent, forever, with no error.

`avoid_positions = avoid_positions` joins `_generate_kwargs` at
`backend/server.py:5652`, beside `trade_away_positions`.

The likes-you call site passes it at `backend/server.py:5734`
(`avoid_positions = set(avoid_positions) or None`), beside
`not_interested_ids`.

### (b) The asset-ideas route — `backend/server.py:11357-11372`

**New plumbing, not a mirror.** That route loads *asset* preferences only
(`load_asset_preferences`, `:11346`) and passed no positional prefs at all.
A guarded, best-effort `load_league_preference` was added in the same style as
its neighbour:

```
11365    if FLAGS.trade_avoid_positions:
11366        try:
11367            _lp = load_league_preference(user_id=g_user_id, league_id=league_id)
11368            avoid_positions = (_lp or {}).get("avoid_positions", []) or []
```

then threaded at `backend/server.py:16172`.

The resulting asymmetry — asset ideas honor Avoiding but not
Chasing/Shopping — is **intended** and follows D-360-3(a): `not_interested` is
applied on this route's three receive-side guards and Chasing/Shopping never
were.

### (c) Persistence is NOT flag-gated

`GET /api/league/preferences` returns `avoid_positions` from
`load_league_preference` (`backend/database.py:8593`) and, when no row exists,
from the fallback literal at `backend/server.py:16066`. `POST` normalizes it at
`backend/server.py:16155-16165`, stores it at `:16177`, and echoes the stored
list at `:16193`. Neither is behind
`FLAGS.trade_avoid_positions`. A kill-switch flip must never destroy user
data. `test_prefs_route_roundtrip` is parameterized over both flag states.

---

## 4. The exempt seams are exempt BY THE RULE, not by omission

The rule is `git grep -n not_interested -- backend`. Running it in this tree
returns exactly these consumers:

```
backend/server.py            — _inject_likes_you_cards_impl (seam 7), the two
                               route loaders, kwarg plumbing
backend/trade_service.py     — _generate_trades_impl/_v2 plumbing, the v2 and
                               consensus pools (seams 3, 4), the three asset-
                               ideas guards (seams 5, 6a, 6b)
backend/trade_optimizer.py   — generate_pair_trades_v3 (seam 1), _try_sweeten
                               (seam 2)
backend/trade_gen_v2.py      — :509 / :530 / :533   ← see below
```

Two things are **not** in that list, and that is the proof of exemption:

- **`_roster_eveners`** (`backend/server.py:1027`, prefs read at `:1046-1049`,
  reached from `/api/trade/evaluate`) reads **only `untouchables`**.
  `not_interested` is not applied there either, so including Avoiding would
  make the position-level filter **stricter than the player-level one on the
  same surface** — backwards. Orchestrator ruling Q-A4; consistency, not an
  oversight.
- **The legacy v1 generator `_generate_for_pair`**
  (`backend/trade_service.py:5180`) applies neither `untouchable_ids` nor
  `not_interested_ids` and is unreachable in production
  (`trade_engine.v2 = true`). Its call site at `backend/trade_service.py:3394`
  was deliberately **not** given the new kwarg; the three v2/v3/consensus
  call sites two hundred lines below it were.

### 4.1 `trade_gen_v2` — the one place the rule and the ruling disagree

`backend/trade_gen_v2.py` **does** apply `not_interested_ids` (`:509`,
filtered at `:530`) and `untouchable_ids` (`:533`), so the governing rule
points **into** it. The orchestrator ruled it OUT of scope (Q-A1) and this
build honors that ruling — no line of `trade_gen_v2.py` was touched.

Stating the caveat as PRD §5.1 requires: the ruling's rationale ("gen-v2
reads no positional preferences at all today, so Chasing and Shopping are
already not honored there") is true of *positional* prefs but not of the
negative lists this feature is modeled on. Serving is genuinely dark
(`bakeoff_serve_interleaved = 0.0`), so nothing user-visible leaks — but the
exposure is a **knob**, not a flag, and it flips without a deploy.

The required guardrail therefore ships in **both** places the bake-off arm is
documented:

- `backend/feature_flags.py` — the `trade.bakeoff` comment block
- `docs/config-reference.md` — the flag group prose **and** the
  `bakeoff_serve_interleaved` knob row

> Do not raise `bakeoff_serve_interleaved` above `0` until `trade_gen_v2`
> honors `acquire_positions`, `trade_away_positions` **and**
> `avoid_positions`.

Pinned by `test_gen_v2_guardrail_note_present`.

Tracked as `living-memory/OPEN_QUESTIONS.md` **Q-031** (renumbered from Q-024
on 2026-08-19: `origin/main` advanced mid-build and took Q-024 and Q-025).

**Not delivered by this agent:** the `living-memory/OPEN_QUESTIONS.md` entry
`Q-024` (shipped as Q-031) and the four decisions (item-scoped D-360-1…D-360-4, recorded in `prd.md` §2, not in DECISIONS.md — see scope.md §4). `living-memory/`
is owned by the orchestrator for this wave; the wording constraint from PRD
§5.1 (headline is the pre-existing Chasing/Shopping gap, Avoiding named in
the body) still applies.

---

## 5. The flag-off path reaches none of it

One flag read per route, both at the point of entry:

- `backend/server.py:5463` — the trade job. Off ⇒ `avoid_positions` stays
  `[]`; the R-9 guard's `if avoid_positions and acquire_positions:` is
  therefore false; `_generate_kwargs` carries `[]`; every consuming function's
  `set(avoid_positions or ())` is empty; `avoid_ok` short-circuits on
  `if not avoid: return True`. No pool membership changes. No card payload
  key changes (Avoiding adds none).
- `backend/server.py:11365` — asset ideas. Off ⇒ the
  `load_league_preference` call is not even made, and the kwarg is `None`.

Pinned by `test_flag_off_deck_is_byte_identical`, which asserts both the
structural flag gate and deck equality (give ids, receive ids, composite
scores) against the baseline — proven RED by removing the `if FLAGS.…` line.

---

## 6. Never relaxable — structural, and written down

`_relaxed_targeted_pass` (`backend/trade_service.py:3537-3607`) re-runs
`_generate_trades_v2` with the **same kwargs** inside a `_cfg_override` that
moves only `fairness_floor_divergence` and `min_side_surplus`. Because
Avoiding lives in pool construction rather than in a relaxable gate, it is
structurally impossible for that pass to relax it — no code is needed for the
guarantee.

It is written into the `NEVER relaxed:` list of that method's docstring anyway
(`backend/trade_service.py:3552-3558`), with the failure mode named: *do not
move the filter into a gate*. The guarantee that costs nothing to hold is the
one nobody notices they have broken.

`avoid_positions` also joins the #189 `targeted` predicate at
`backend/trade_service.py:3351-3353`, so a job narrowed only by Avoiding gets the
same staged widening the other narrowing preferences get.

---

## 7. What this walk does NOT cover

- **Mobile.** Every client-side requirement (R-12 … R-15), the
  `check-avoid-positions.js` structural suite and the `LAUNCHED_FLAG_DEFAULTS`
  half of the flag are the mobile agent's deliverables.
- **Runtime evidence.** The operator's TestFlight checklist (`prd.md` §7.3) is
  the only runtime proof mobile gets under D-056, and it has not been run.
- **Deck-size delta.** `plan.md` §12 R1 established that the
  `scripts/deck_eval.py` corpus is not present in this worktree, so **no
  measured deck-thinning number is claimed**. The runtime valve is the #189
  relaxed pass; the runtime signal is the existing presentment tripwire.

---

## Post-merge re-verification — 2026-08-26 (merge of `origin/main` @ 867c3baa)

The branch was rebuilt on current `origin/main` (123 commits past the 2a492b6
base: knockout refine D-159, full sweep D-154, #384 merged calculator, package
pricing honesty #162, pick YoY floor D-161, receipts, breaker, negmem). Every
claim below was re-walked on the MERGED tree; line numbers are merged-tree.

**The single flag read and the exclusion chain (R-4, R-11):**
1. `backend/server.py:5869-5870` — `_run_trade_job` reads
   `league_preferences.avoid_positions` ONLY when `FLAGS.trade_avoid_positions`
   is true; otherwise `avoid_positions` stays `[]` (`:5858`). This is still the
   single point of entry: every downstream consumer receives the list as an
   argument, so flag-off ⇒ `[]` everywhere ⇒ byte-identical generation.
2. `backend/server.py:5883-5891` — avoid⊕chase: every avoided position is
   dropped from `acquire_positions` BEFORE `_generate_kwargs` is built (R-9;
   `INFO` log names the dropped tokens).
3. `backend/server.py:6101` — the list rides the generate kwargs;
   `backend/trade_service.py:4484` accepts it, `:4675` threads it into
   `_generate_trades_v2`, `:5590/:5838/:5872/:5898` fan it out to the v3 /
   v2 / consensus pair generators (each `or []`).
4. Receive-pool construction sites, all filtered through `avoid_ok`:
   - v3: `backend/trade_optimizer.py:381-385` (`known_opp`), sweetener
     receive-side candidates `:800-805` (threaded at `:674`);
   - v2: `backend/trade_service.py:6475-6480` (`_known_opp`);
   - consensus: `backend/trade_service.py:6726-6730` (`_opp_pool`);
   - asset ideas: `backend/trade_service.py:5195-5200` (give-direction
     return pool), `:5262-5265` (pinned receive asset at an avoided
     position ⇒ empty, D-360-3(b)), `:5281-5285` (extras pool);
   - likes-you injector: `backend/server.py:3431-3435` (organic mirrors)
     and `:3590-3593` (#362 standing-offer branch), receiving the set at
     `:6217`.
5. Pick-ness before position (R-5): `backend/trade_service.py:2091`
   (`_pos_for_avoid` — `is_pick_asset` first, so avoiding QB never deletes a
   4th-round rung; only the `PICK` chip excludes picks) and `:2115`
   (`avoid_ok` — unknown ids pass, falsy avoid passes everything).
6. Never relaxed (D-360-4): the #189 relaxed pass re-runs
   `_generate_trades_v2` with the SAME kwargs
   (`backend/trade_service.py:4921-4929` states it; `avoid_positions` also
   marks the job "targeted" at `:4706-4708` so an over-constrained job takes
   the relaxed pass instead of silently emptying) — the exclusion lives in
   pool construction, so there is nothing a gate relaxation could reach.
7. Persistence is NOT flag-gated (R-2/R-3): GET always serves the array
   (`backend/server.py:17438` no-row fallback, `:17457-17462` row path);
   POST normalizes-and-echoes (`:17515-17531`, normalizer `:17371`);
   storage `backend/database.py:998` (column), `:2743` (migration),
   `:9018-9019` (None-leaves-alone upsert).

**New post-merge seam closed this session:** `origin/main`'s counterparty
breaker added `load_league_preferences_bulk` (`backend/database.py:9090`),
contract "identical per-row shape to `load_league_preference`". It predated
`avoid_positions` and did not carry the key; fixed 2026-08-26 so the bulk row
now includes `avoid_positions` (pinned by
`test_breaker_seam.py::test_bulk_readers_match_the_singular_loaders`).

**Mobile (flag-gated render):** `TradeDnaSheet.tsx:282` (`avoidOn`), row
rendered only when on; `TradesScreen.tsx:657` (`avoidOn`), receipt line
`:1288-1293` (R-10), empty-state copy naming Avoiding `:1770-1782` (R-9).
Deliberately absent from `LAUNCHED_FLAG_DEFAULTS` (D-163 — that map fails
open).

**Fixture note (not a behavior change):** `origin/main` d42872f2 ("package
pricing honesty + gap auto-sweetener", #162) stopped admitting 1-for-1s that
lose seed value for the giver. The T-4/T-5 harness seeded coveted receive
assets at 1500 against a 1540 give, so the BASELINE premise (a WR / the extra
pick surfaces before Avoiding is applied) failed on the merged engine. The
fixture now seeds those assets at parity (1540); the assertions are unchanged.
Suite: `test_avoid_positions.py` 29/29 green on the merged tree, 2026-08-26.
