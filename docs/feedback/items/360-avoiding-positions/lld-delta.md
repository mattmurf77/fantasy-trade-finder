# LLD delta — "Avoiding" positions (#360 / #361)

> **This is the interface contract.** A backend agent and a mobile agent must be
> able to build against it independently, without talking, and meet in the
> middle. Where two engineers could read a field differently, this document
> picks one reading and says so.
>
> **Base sha:** `f68eddd`. Every `file:line` re-read this session.
> **Companions:** `prd.md` (requirements R-1…R-16, decisions D-360-1…D-360-4),
> `scope.md` (gates), `hld-delta.md` (n/a, one line).

---

## 1. Storage

### 1.1 Table declaration

`backend/database.py`, `league_preferences_table` (`:987-996`). Add one column
after `trade_away_positions` (`:993`):

```python
Column("avoid_positions",     Text,    default="[]"),  # JSON array e.g. ["QB","TE"] — #360
```

### 1.2 Migration — the pattern this repo actually uses

There is **no `_ensure_columns` helper and no Alembic**. The mechanism is
`_migrate_db()` (`backend/database.py:2422`), which walks a literal
`migration_cols` list (opened at `:2432`, closed at `:2583`) and issues one
`ALTER TABLE … ADD COLUMN` per entry, **each in its own transaction**, each
wrapped in a bare `except Exception: pass` so it is idempotent
(`:2584-2593`). The per-entry transaction is deliberate and load-bearing:
PostgreSQL marks the whole transaction aborted on any error even when Python
catches it (comment at `:2585-2587`).

Add exactly one entry, immediately after the existing sibling pair at
`:2445-2446`:

```python
        ("league_preferences", "acquire_positions",    "TEXT"),
        ("league_preferences", "trade_away_positions", "TEXT"),
        # #360/#361 — receive-side positional exclusion. TEXT to match the two
        # rows above. NO SQL DEFAULT and NO BACKFILL by design: every existing
        # row reads NULL, and load_league_preference's _parse_positions returns
        # [] for any falsy raw value, which is the correct "avoiding nothing".
        ("league_preferences", "avoid_positions",      "TEXT"),
```

**Do not add a SQL `DEFAULT '[]'`.** The two siblings do not have one, the
read path already normalizes, and adding one would make SQLite and Postgres
disagree about what a pre-existing row contains.

### 1.3 `upsert_league_preference` (`backend/database.py:8477-8534`)

Four edits. The third and fourth are the easy ones to miss.

1. Signature (`:8481` region) — add after `trade_away_positions`:
   ```python
   avoid_positions: list[str] | None = None,
   ```
2. Values dict, after `:8511`:
   ```python
   if avoid_positions is not None:
       vals["avoid_positions"] = json.dumps(avoid_positions)
   ```
3. Insert branch, after `:8530` — add the `"[]"` fallback:
   ```python
   avoid_positions      = vals.get("avoid_positions",      "[]"),
   ```
4. **The exclusion tuple at `:8532-8533`** — the `**{k: v for k, v in vals.items() if k not in (...)}` splat. `avoid_positions` **must** be added to that tuple, or the insert passes the key twice and raises `TypeError: got multiple values for keyword argument`:
   ```python
   if k not in ("acquire_positions", "trade_away_positions",
                "avoid_positions", "updated_at")},
   ```

**Semantics, unchanged from the siblings and load-bearing for §5.3 of the PRD:
`None` means "leave the stored value alone", not "clear it".** An empty list
`[]` means "clear it". A caller that omits the field preserves whatever is
stored. This is what makes a web save non-destructive.

### 1.4 `load_league_preference` (`backend/database.py:8537-8575`)

Add to the docstring shape block (`:8545` region) and to the return dict
(`:8572` region):

```python
"avoid_positions":       _parse_positions(getattr(row, "avoid_positions",      None)),
```

`getattr(..., None)` is required, not defensive noise: a row object read before
the migration ran has no such attribute. `_parse_positions` (`:8558-8565`)
already maps `None`, `""`, malformed JSON and non-list JSON all to `[]`.

---

## 2. The predicate

### 2.1 `_pos_for_avoid` — one function, one home

New module-level helper in `backend/trade_service.py`, placed immediately after
`is_pick_asset` (`:1549-1557`) so the two read together:

```python
def _pos_for_avoid(p) -> str | None:
    """Position key used by the #360 receive-side avoid filter.

    Pick-ness is resolved FIRST, via the canonical is_pick_asset: the generic
    pick rungs carry a deliberately FAKE player position (_PICK_POS in
    server.build_universal_pool, {1:"RB",2:"WR",3:"TE",4:"QB"}) so they
    distribute across the trio tabs. Reading p.position raw here would let
    "avoid QB" delete every 4th-round pick from the receive pool, which is a
    defect, not consistency. Avoiding "PICK" — one of the five DNA chips — is
    the only way to exclude pick assets.
    """
    if p is None:
        return None
    if is_pick_asset(p):
        return "PICK"
    return getattr(p, "position", None)


def avoid_ok(pid: str, players: dict, avoid: set[str] | None) -> bool:
    """True when player/asset `pid` may enter a RECEIVE pool. Unknown ids pass
    (they cannot be scored anyway and the surrounding pool builders already
    filter on membership)."""
    if not avoid:
        return True
    return _pos_for_avoid(players.get(pid)) not in avoid
```

`backend/trade_optimizer.py` imports `avoid_ok` by adding it to the existing
`from .trade_service import (...)` block at `:51-69` — the same direction
`filler_ok`, `fit_premium_1for1` and `pick_swap_ok` already travel. Note that
file's own header at `:74-76` ("Replicated helpers … shared refactor is a
follow-up"): **do not replicate this one.** `_pos_for_avoid` and `avoid_ok` have
exactly one definition and seven call sites. Re-deriving pick identity is what
shipped #222 and the 2026-08-18 B3 sweep.

### 2.2 Known, deliberate asymmetry — record it, do not fix it

`_positions_ok` — the Chasing/Shopping gate, duplicated at
`backend/trade_optimizer.py:419-437` and `backend/trade_service.py:4564-4577`
— reads `players[p].position` **raw**. It therefore treats a 4th-round generic
rung as a QB. Avoiding, using `_pos_for_avoid`, does not.

**Avoiding is deliberately stricter-and-correcter than its two neighbours.**
This is orchestrator ruling Q-A2, and it is the right call: the alternative
("be consistent") means shipping a known defect on purpose. Fixing the two
neighbours is a behavior change to two shipped features that nobody asked for
(coding-guidelines §3, surgical changes), and it is out of scope for this wave.

Deck-side the neighbours' bug is currently **moot** — generic rungs live in the
ranking pool, not on rosters, so they cannot enter a receive package today. The
asymmetry is recorded here, in `docs/glossary.md`, and as a new row in the
`docs/cross-client-invariants.md` mirror table (`:398-404`) so the next reader
finds it before re-deriving pick identity a third time (#222; the 2026-08-18 B3
sweep).

---

## 3. HTTP contract — `/api/league/preferences`

**Pin this section verbatim.** Both build agents code against it blind.

### 3.1 Flag independence — decided, and it matters

The **persistence layer is not flag-gated.** `GET` always returns the field;
`POST` always accepts and stores it — in **both** states of
`trade.avoid_positions`. The flag gates exactly two things: whether the
**engine reads** the column, and whether the **sheet renders** the row.

Rationale: a kill-switch flip must not destroy user data, and flipping the flag
back on must restore every user's saved set with no migration and no re-entry.
A flag that hid the field would also make the mobile type optional, which
removes the `tsc` pressure that catches R-13's silent-divergence bug.

### 3.2 `GET /api/league/preferences?league_id=…`

`backend/server.py:15381-15444`. Response gains **one** key.

```jsonc
{
  "team_outlook":          "championship",   // unchanged
  "acquire_positions":     ["WR", "TE"],     // unchanged
  "trade_away_positions":  ["QB"],           // unchanged
  "avoid_positions":       ["TE"]            // NEW
}
```

| Field | Type | Always present? | Empty value | Notes |
|---|---|---|---|---|
| `avoid_positions` | `array<string>` | **yes** | `[]` | Never `null`, never absent. Elements are uppercase, drawn from `{"QB","RB","WR","TE","PICK"}`. Order is the stored order (insertion order from the client). No duplicates. |

Two code paths must both be updated, or the field is missing exactly when there
is no stored row:

1. The `prefs is not None` path — `load_league_preference` already returns the
   key after §1.4.
2. **The no-row fallback literal at `:15408-15412`** — add
   `"avoid_positions": []` beside its two siblings.

The additive `inferred_outlook` / `inferred_signals` (`:15418-15421`) and
`position_needs` / `position_surplus` (`:15436-15438`) blocks are untouched.

### 3.3 `POST /api/league/preferences`

`backend/server.py:15447-15513`.

**Request body**

```jsonc
{
  "league_id":            "1234567890",
  "team_outlook":         "championship",       // required, unchanged
  "acquire_positions":    ["WR"],               // optional, unchanged
  "trade_away_positions": ["QB"],               // optional, unchanged
  "avoid_positions":      ["te", " QB ", "QB"]  // NEW, optional
}
```

| Input for `avoid_positions` | Behavior |
|---|---|
| absent, or `null` | **Stored value left unchanged.** (Matches the siblings' `is not None` semantics at `backend/database.py:8509-8511`. This is what makes a web save non-destructive — PRD §5.3, test `T-14`.) |
| `[]` | Clears the stored list. |
| a list | Normalized (below), then stored. |
| any non-list (string, number, object, bool) | `400` `{"error": "avoid_positions must be an array"}` — same shape as its siblings at `:15484-15487`. |

**Normalization — exact algorithm, applied in this order:**

1. Drop any element that is not a `str`.
2. `.strip().upper()`.
3. Drop any token not in `{"QB", "RB", "WR", "TE", "PICK"}`.
4. Dedupe, **preserving first-seen order**.
5. Cap at 5 elements (the set has exactly 5 members, so this is belt-and-braces).

`["te", " QB ", "QB", "DEF", 7]` → `["TE", "QB"]`.

**Why drop rather than `400`.** A `400` would make one bad token discard the
user's whole valid save. Storing an unknown token would be worse: it is inert
in the filter but the UI would render "Avoiding DEF", which is a **lie about a
promise**. Dropping is the only option that is both non-breaking and honest —
and it is not silent, because the response echoes what was actually stored
(below), and an `INFO` log fires naming the dropped tokens.

> **Do not touch `valid_positions` at `backend/server.py:15483.`** That set is
> defined and **never referenced** — dead since it was written — and it omits
> `PICK`, which the shipped client does send (`DNA_POSITIONS` includes
> `{ key: 'PICK' }`). Wiring it up would newly reject live payloads. It is
> recorded in `scope.md` §6 and left alone.

**Response** (`:15505-15511`) gains one key:

```jsonc
{
  "ok":                   true,
  "team_outlook":         "championship",
  "acquire_positions":    ["WR"],
  "trade_away_positions": ["QB"],
  "avoid_positions":      ["TE", "QB"]   // NEW — the NORMALIZED, STORED list
}
```

**The echo is the normalized list, not the request's list.** A client that sent
`["te","DEF"]` gets back `["TE"]` and can reconcile. `acquire_positions` and
`trade_away_positions` keep their existing `x or []` echo, unchanged.

Existing side effects are untouched: `_invalidate_trade_jobs` still fires
(`:15501`), so a preference change still drops the league-scoped deck cache —
which is what makes the new preference take effect on the next generate.

### 3.4 Feature flag

| | |
|---|---|
| Key | `trade.avoid_positions` |
| `config/features.json` | `true` |
| `backend/feature_flags.py` `FLAG_KEYS` | add the literal to the tuple (opened `:47`), with a comment block modeled on `"trade.presentment_rules"` (`:799`) stating both flag states |
| Python attribute | `FLAGS.trade_avoid_positions` — derived by `_key_to_attr` (`:858-864`: `key.replace(".", "_")`); nothing to declare |
| `mobile/src/state/useFeatureFlags.ts` | add `'trade.avoid_positions': true` to `LAUNCHED_FLAG_DEFAULTS` (`:45`) |
| `docs/config-reference.md` | new entry; state "no new `model_config` keys" |

**Both files or neither.** `useFeatureFlags.ts:62-70` documents why: `revalidateFlags`
does a whole-map `set({ flags })`, so a key present in only one of
`config/features.json` / `LAUNCHED_FLAG_DEFAULTS` disagrees with itself across
the first two paints — a row that paints for one frame and then vanishes.
Pinned by assertion `A-10`.

---

## 4. Engine seams — every function-level touch point

Seven receive-side seams. The set is **exactly** the sites where
`not_interested_ids` is applied (PRD D-360-3(a)), which makes it verifiable by
`git grep -n not_interested -- backend`.

| # | Seam | `file:line` | Change |
|---|---|---|---|
| 1 | **v3 receive pool** — `known_opp` in `generate_pair_trades_v3` | `backend/trade_optimizer.py:359-361` | add `and avoid_ok(p, players, _avoid)` to the comprehension |
| 2 | **v3 sweetener** — candidate list in `_try_sweeten` | `backend/trade_optimizer.py:705-710` | add `and not (side == "receive" and not avoid_ok(p, players, avoid_positions))`, mirroring the `side == "receive"` guard the `#163` clause at `:708-709` already uses |
| 3 | **v2 receive pool** — `_known_opp` in `_generate_for_pair_v2` | `backend/trade_service.py:4761-4763` | same predicate |
| 4 | **consensus receive pool** — `_opp_pool` in `_generate_consensus_for_pair` | `backend/trade_service.py:4931-4932` | same predicate |
| 5 | **asset ideas, `direction == "give"`** — return pool | `backend/trade_service.py:3772-3775` | same predicate |
| 6 | **asset ideas, `direction == "receive"`** — pinned-asset guard + `extras` pool | `backend/trade_service.py:3836-3837`, `:3853-3855` | pinned-asset guard mirrors #163's `return empty`; `extras` gets the predicate |
| 7 | **likes-you injector** | `backend/server.py:3021` | add a position-set intersection beside the `#163` line — see §4.3 |

### 4.1 Seams 1–4: filter at the source, and only at the source

All four pools are built once and then *re-added to*. Filtering the source list
is therefore sufficient **and** gives R-8 (an exclusion beats a pin) for free,
because every re-add loop iterates the already-filtered list:

- v3: `recv_pool` prune at `:404`; `pinned_recv_set` re-add `:407-410` and
  `target_ids` re-add `:412-415` both iterate `known_opp`.
- consensus: `recv_pool = list(_opp_pool)` at `:4933`; `target_ids` re-add
  `:4946-4949` iterates `_opp_pool`. The comment at `:4929-4930` already states
  the rule — *"so an exclusion always wins"*.

**Do not add a pin exemption.** R-8 exists specifically to stop a build agent
from "improving" this.

### 4.2 Signature threading

Every one of these signatures **already carries `acquire_positions` and
`trade_away_positions` on adjacent lines**. The third parameter goes on the next
line in each, with the same alignment.

| Function | Signature at | Call site(s) that must pass it |
|---|---|---|
| `TradeService._generate_trades_impl` | `backend/trade_service.py:3116-3117` | `backend/server.py:5355-5356` (via `generate_trades`) |
| `TradeService._generate_trades_v2` | `:3966-3967` | `_v2_kwargs` dict at `:3269-3270` |
| `TradeService._generate_for_pair_v2` | `:4437-4438` | `:4182-4183` |
| `trade_optimizer.generate_pair_trades_v3` | `backend/trade_optimizer.py:208-209` | `backend/trade_service.py:4214-4215` |
| `TradeService._generate_consensus_for_pair` | `backend/trade_service.py:4887-4888` | `:4239-4240` |
| `trade_optimizer._try_sweeten` | `backend/trade_optimizer.py:677-681` | `backend/trade_optimizer.py:649` (`not_interested_ids=` is passed there; add beside it) |
| `TradeService._generate_asset_ideas_impl` | `backend/trade_service.py:3557-3558` | `backend/server.py:11063-11073` (through the `**kwargs` wrapper at `:3540-3544`) |

**Type at every level:** `avoid_positions: list[str] | None = None` where the
siblings are optional, `list[str]` where they are positional-required
(`:4437-4438`, `:4887-4888`). Convert **once**, at the top of each consuming
function: `_avoid = set(avoid_positions or ())`. Pass lists across boundaries
(matching the siblings), use a set inside.

**Do NOT change `_generate_for_pair`** (`backend/trade_service.py:5094`), the
legacy v1 generator. It applies neither `untouchable_ids` nor
`not_interested_ids` and is unreachable (`trade_engine.v2 = true`). PRD §5.2.

### 4.3 Seam 7 — the likes-you injector

`_inject_likes_you_cards_impl` (`backend/server.py:2943-2953`) currently takes
`untouchable_ids` and `not_interested_ids`. Add:

```python
    avoid_positions: set | None = None,   # #360 — position twin of not_interested
```

and beside the `#163` guard at `:3019-3022`:

```python
        # #360 — a position the user avoids is never offered TO them, even via
        # a counterparty like. Their give side IS the user's receive side.
        # This is a USER CONSTRAINT, not a deck-quality rule, so the G6 Q21
        # likes-you exemption (R1/R2/R3/R5) does not reach it — same side of
        # that line as untouchables, #163 and the R4 dedup.
        if avoid_positions and any(
                _pos_for_avoid(trade_service._players.get(p)) in avoid_positions
                for p in their_give):
            continue
```

Positions come from `trade_service._players` — the dict the service is
constructed with (`TradeService.__init__`, `backend/trade_service.py:3056`),
already in scope in this function. Wire the kwarg at the call site
(`backend/server.py:5427-5438`), beside `not_interested_ids` at `:5436`.

### 4.4 The #189 `targeted` predicate and the never-relaxed docstring

`backend/trade_service.py:3294-3295`:

```python
            targeted = bool(pinned_give_players or pinned_receive_players
                            or acquire_positions or trade_away_positions
                            or avoid_positions)
```

And extend the `NEVER relaxed:` list in the `_relaxed_targeted_pass` docstring
(`:3492-3501`) to name `avoid_positions`. **No code change is needed for the
guarantee** — the relaxed pass re-runs `_generate_trades_v2` with the *same*
kwargs and relaxes only the fairness band and the surplus floor, so a
pool-construction filter is structurally un-relaxable (PRD D-360-4). The docstring
edit is so the guarantee is written where the next reader looks.

### 4.5 Preference loaders — two of them

**(a) The trade job** — `backend/server.py:5178-5189`.

```python
        outlook_value        = None
        acquire_positions    = []
        trade_away_positions = []
        avoid_positions      = []              # NEW
        try:
            prefs = load_league_preference(user_id=g_user_id, league_id=league_id)
            if prefs:
                outlook_value        = prefs.get("team_outlook")
                acquire_positions    = prefs.get("acquire_positions",    []) or []
                trade_away_positions = prefs.get("trade_away_positions", []) or []
                if FLAGS.trade_avoid_positions:                              # NEW
                    avoid_positions  = prefs.get("avoid_positions",      []) or []
```

The flag read lives **here**, at the single point of entry, so every downstream
consumer sees `[]` when the flag is off and no other site needs a flag check.
That is what makes R-11 (flag-off byte-identical) a one-line property.

**(b) The R-9 contradiction guard** — immediately after the block above, before
`_presentment_need_gate_bypass` at `:5202-5203` consumes `acquire_positions`:

```python
        # #360 R-9 — avoid ⊕ chase is unsatisfiable and fails SILENTLY: the
        # pool exclusion empties every receive pool of the position while
        # _positions_ok still demands at least one received player at it, so
        # every opponent yields zero cards with no error. The UI makes this
        # state unreachable, but an older client, a replayed request or a
        # direct POST can still send both. AVOID WINS — a negative promise is
        # the stronger commitment and the cheaper one to honor.
        if avoid_positions and acquire_positions:
            _dropped = [p for p in acquire_positions if p in set(avoid_positions)]
            if _dropped:
                acquire_positions = [p for p in acquire_positions
                                     if p not in set(avoid_positions)]
                log.info("trade-job: #360 avoid⊕chase — dropped %s from acquire "
                         "(user=%s league=%s)", _dropped, g_user_id, league_id)
```

**Ordering is load-bearing.** It must run *before* `:5202-5203`
(`_presentment_need_gate_bypass(..., acquire_positions)`) and before the
`_generate_kwargs` dict at `:5345-5357`, so nothing downstream ever sees the
contradictory pair. Add `avoid_positions = avoid_positions` to that dict beside
`trade_away_positions` at `:5356`.

**(c) The asset-ideas route** — `backend/server.py:11020-11073`. **This is new
plumbing, not a mirror.** That route loads *asset* preferences only
(`load_asset_preferences` at `:11033`) and passes no positional prefs at all.
Add a `load_league_preference` call beside it, guarded and best-effort in the
same style as its neighbour:

```python
    avoid_positions: list[str] = []
    if FLAGS.trade_avoid_positions:
        try:
            _lp = load_league_preference(user_id=g_user_id, league_id=league_id)
            avoid_positions = (_lp or {}).get("avoid_positions", []) or []
        except Exception as lp_err:
            log.warning("asset-ideas: league prefs load failed: %s", lp_err)
```

then pass `avoid_positions = avoid_positions or None` in the
`generate_asset_ideas` call at `:11063-11073`, beside `not_interested_ids` at
`:11073`.

Note the resulting asymmetry, which is **intended**: asset ideas honor Avoiding
but not Chasing/Shopping. That follows D-360-3(a) — Avoiding goes where
`not_interested` goes, and `not_interested` is applied here (`:3775`, `:3836`,
`:3855`) while Chasing/Shopping never were. Asset ideas are already scoped by
the pinned asset, so a Chasing filter there would be redundant at best.

### 4.6 Explicitly NOT touched

| Site | Why |
|---|---|
| `_roster_eveners` (`backend/server.py:1027`, prefs read at `:1046-1049`) | reads **only** `untouchables`; `not_interested` is not applied there either (ruling Q-A4, PRD D-360-3(a)) |
| `backend/trade_gen_v2.py` | orchestrator ruling Q-A1 — **but read PRD §5.1 before agreeing with it**, and ship the `bakeoff_serve_interleaved` guardrail |
| `_generate_for_pair` (`backend/trade_service.py:5094`) and its gate at `:5460-5470` | legacy v1, unreachable, applies no exclusion lists |
| `pos_conflict_penalty` / `pos_acquire_bonus` / `pos_tradeaway_bonus` | dormant, named not deleted (D-360-1) |
| `backend/tests/test_bakeoff_arm_a_golden.py` | no new `model_config` key ⇒ no golden edit |

---

## 5. Mobile

### 5.1 `mobile/src/api/league.ts`

`LeaguePreferences` (`:28-45`) gains, after `trade_away_positions` (`:32`):

```ts
  /** #360/#361 — positions the user will not accept on the RECEIVE side.
   *  Always present on GET (never null, never absent), in both states of
   *  `trade.avoid_positions`. Uppercase, from QB|RB|WR|TE|PICK. */
  avoid_positions: string[];
```

**Required, not optional.** This is deliberate: `saveLeaguePreferences`
(`:54-59`) takes `prefs: LeaguePreferences` and spreads it, so making the field
required turns every object-literal call site into a `tsc --noEmit` error. That
compiler pressure is the mechanical guard against R-13's silent-divergence bug.
There are **five** such call sites (§5.3) — `plan.md` §11.1 found two.

No signature change to `getLeaguePreferences` (`:47-51`) or
`saveLeaguePreferences` (`:54-59`).

### 5.2 `mobile/src/components/TradeDnaSheet.tsx` — exclusive ownership

| Region | `file:line` | Change |
|---|---|---|
| draft state | `:238-239` | add `const [draftAvoiding, setDraftAvoiding] = useState<string[]>([]);` |
| seeding effect | `:353-362` | add `setDraftAvoiding(prefs?.avoid_positions ?? []);` |
| `saveOutlook` mutation `vars` type + body | `:383-392` | add `avoid: string[]` and `avoid_positions: vars.avoid` |
| `dnaDesired` ref type | `:400-405` | add `avoid: string[]` |
| error-revert in `flushDnaSave` | `:426-431` | add `setDraftAvoiding(saved?.avoid_positions ?? []);` |
| `queueDnaSave` param type | `:439-443` | add `avoid: string[]` |
| `pickOutlook` call | `:467` | add `avoid: draftAvoiding` |
| `toggleDnaPos` | `:474-500` | 3-way move — §5.2.1 |
| `DnaToggle` | `:109-149` | optional `glyph` prop — §5.2.2 |
| `full` variant | `:661-700` | third `posLine` after Shopping |
| legacy variant | `:743-786` | third toggle block + **rewritten hint** at `:781-785` |

All six payload sites are R-13; assertion `A-4` pins them together.

#### 5.2.1 `toggleDnaPos` — the D-360-2 asymmetry

Signature widens from `(side: 'chase' | 'shop', pos: string)` to
`(side: 'chase' | 'shop' | 'avoid', pos: string)`. The move table, in full —
**note that only `chase` clears two rows**:

| Tapped | `nextChasing` | `nextShopping` | `nextAvoiding` |
|---|---|---|---|
| `chase` | toggle `pos` | remove `pos` | remove `pos` |
| `shop` | remove `pos` | toggle `pos` | **unchanged** |
| `avoid` | remove `pos` | **unchanged** | toggle `pos` |

Then `setDraftAvoiding(nextAvoiding)` alongside the two existing setters, and
`queueDnaSave({ outlook: draftOutlook ?? 'not_sure', acquire: nextChasing,
shed: nextShopping, avoid: nextAvoiding })`.

The existing "computed up front so the tap can autosave the exact state it
shows" comment (`:472-473`) still governs — compute all three `next*` values
before any `set*`.

#### 5.2.2 `DnaToggle` glyph (R-15)

`DnaToggle` (`:109-149`) hardcodes `<Icon name="check" size={12} color={ice.on} />`
at `:140`, and its own header comment states the rule: *"the check is the
primary state cue, never color alone"*. A check meaning "avoided" inverts that
cue.

Add an optional prop, **defaulting so the two existing rows are untouched**:

```ts
  glyph = 'check',            // 'check' | 'x' — #360: Avoiding selects with ✕
```

`x` exists in the icon set (`mobile/src/components/chalkline/Icon.tsx:70`).
The Avoiding row passes `glyph="x"`; Chasing and Shopping pass nothing.
Assertion `A-9` pins exactly that.

**Chip fill color is unchanged** — `dnaPosColor` (`:101-104`) stays the position
data encoding governed by `docs/cross-client-invariants.md`. Do **not** recolor
the Avoiding row to a semantic danger red: it would break the position encoding
*and* introduce a non-sanctioned accent (Chalkline permits ice for actions and
flare for informational highlights only).

#### 5.2.3 Copy

| Where | Text |
|---|---|
| `full` row label / sublabel (`:684-687` pattern) | **`Avoiding`** / **`no thanks`** |
| legacy header (`:763-766` pattern) | **`Avoiding — tap all that apply`** + the existing `· multi-select` span |
| `accessibilityLabel` | `Avoid ${p.label}` |
| legacy hint (`:781-785`) — **rewrite** | "Pick as many per row as apply. A position can't be both chased and shopped, or both chased and avoided — tapping it there moves it. Shopping and avoiding the same position is fine: you're selling it and don't want another back. Changes save as you tap." |

The hint rewrite is mandatory (R-14): leaving *"A position can't be both chased
and shopped"* after D-360-2 ships is wrong documentation inside the product.

#### 5.2.4 Flag gate

`const avoidOn = useFlag('trade.avoid_positions');` — gate every Avoiding render
site in **both** variants. Flag off ⇒ no third row, no glyph prop, byte-identical
sheet. The draft state, the seeding effect and the payload key stay unconditional
(so a user's stored set survives a flag flip in both directions), and with the
flag off the sheet simply echoes back whatever it loaded.

### 5.3 `mobile/src/screens/TradesScreen.tsx` — **four** narrow regions

`plan.md` §11.1 named two. There are four; the two extra ones are `tsc` breaks,
not features.

| # | Region | `file:line` | Change |
|---|---|---|---|
| 1 | `confirmOutlookMutation` | `:1017-1023` | add `avoid_positions: []` to the literal — **compile fix only**; this is the one-tap inferred-outlook confirm, which deliberately writes empty position arrays |
| 2 | `receiptDetails` memo (**R-10**) | `:1058-1074` | after the `shopping` part, push `` `Avoiding ${avoiding.map(posLabel).join(', ')}` ``. Reuse `posLabel` at `:1059` (already maps `PICK → 'Picks'`). Order: Chasing · Shopping · Avoiding · intent · N off the table |
| 3 | empty-state toast (**R-9**) | `:1509-1532` | new branch in the `intentCopy` ladder, **above** the `fairnessOn` fallback and **below** the `tradeIntent` branch: when `avoid.length > 0`, `No trades found that avoid ${avoid.map(posLabel).join(', ')}. Try un-avoiding one.` Keep the #330 scoped-empty early return at `:1513-1515` intact |
| 4 | `handleOutlookSubmit` | `:4443-4456` | add `avoid_positions: <current avoid>` — **compile fix**; still reachable via `onSubmit={handleOutlookSubmit}` at `:4574` (the legacy OutlookSheet). Pass the currently stored list, `prefsQuery.data?.avoid_positions ?? []`, so this legacy path never silently clears it |

`fitTargetPositions` (`:2556-2561`) reads `acquire_positions` only and is
**unchanged** — it sharpens fit-line copy about what the user *wants*, which
Avoiding does not contribute to.

**Touch nothing else in this 7,500-line file.** It is the collision surface with
#362 (`plan.md` §11.2); four small, far-apart regions rebase mechanically.

### 5.4 `mobile/src/screens/TradeFinderHubScreen.tsx` — compile fix only

**UNROUTED dead code**, kept in tree per #246 —
`mobile/src/navigation/TabNav.tsx:37` says so explicitly. Do **not** build the
Avoiding UI here. It will nonetheless fail `tsc` at `:341-345` once
`avoid_positions` is required, so add `avoid_positions: vars.avoid ?? []` (or
`[]`) to that one literal and stop. A `git grep acquire_positions -- mobile/src`
makes this file look like a required second editor; it is not.

### 5.5 New files

- `mobile/tests/check-avoid-positions.js` — assertions `A-1`…`A-10`, PRD §7.2.
- `mobile/package.json` — `"test:avoid-positions": "node tests/check-avoid-positions.js"`.
  (Ergonomics only: `.github/workflows/ci.yml`'s `mobile-typecheck` job globs
  `tests/check-*.js`, so the file is live in CI without the script.)

---

## 6. Build order and file ownership

Backend and mobile can run in parallel once §3 is frozen — it is the only
contract between them.

**Backend agent owns:** `backend/database.py`, `backend/trade_service.py`,
`backend/trade_optimizer.py`, `backend/server.py`, `backend/feature_flags.py`,
`config/features.json`, new `backend/tests/test_avoid_positions.py`, new
`docs/feedback/items/360-avoiding-positions/code-walk.md`.

**Mobile agent owns:** `mobile/src/components/TradeDnaSheet.tsx` (**exclusive**),
`mobile/src/api/league.ts` (**exclusive**), `mobile/src/state/useFeatureFlags.ts`
(one line), `mobile/src/screens/TradesScreen.tsx` (**the four regions in §5.3 and
nothing else**), `mobile/src/screens/TradeFinderHubScreen.tsx` (one line),
`mobile/src/components/chalkline/Icon.tsx` (read only — `x` already exists),
new `mobile/tests/check-avoid-positions.js`, `mobile/package.json`.

**Docs** (`scope.md` §4 table) can land with either agent, but the three
item-scoped decisions (D-360-1, D-360-2, D-360-3 — in `prd.md` §2), the `OPEN_QUESTIONS.md` entry
(Q-031 — renumbered from Q-024 on 2026-08-19 after `origin/main` advanced and took Q-024/Q-025; wording constrained by PRD §5.1) and the two `bakeoff_serve_interleaved`
guardrail lines are **backend-agent deliverables** — they carry the reasoning
that agent is closest to.

**#362 collision:** `TradesScreen.tsx` and `backend/server.py` are the likely
contact points. `TradeDnaSheet.tsx` and `api/league.ts` are **exclusive** to
this item; if #362 needs a control in the same sheet, the two features must
serialize instead — a concurrent edit of `toggleDnaPos` and the autosave payload
is a merge hazard whose failure mode is silent (R-13).
