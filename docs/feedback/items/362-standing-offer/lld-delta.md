# LLD delta — #362 Standing offer

> Delta against [`living-memory/LLD.md`](../../../../living-memory/LLD.md) and
> [`docs/api-reference.md`](../../../../docs/api-reference.md). Everything here is
> **binding**: a backend agent and a mobile agent working blind must produce compatible
> code from this document alone.
>
> Base: `origin/main` + `f68eddd`. Every `file:line` verified 2026-08-19.
> Requirements referenced as `R-n` are in [`prd.md`](prd.md) §4.

---

## 1. Shape of the change

One new table, three new routes, one new predicate inside an existing loop, one new
stamping pass, one flag, two `model_config` knobs, five analytics events. **No new
module. No new client. No new engine path.**

```
sender                                        recipient
──────                                        ─────────
TradesScreen.advance('like')                  generate_trade_cards job
  └─ R-1 gate (11 conditions)                   └─ _inject_likes_you_cards_impl
       └─ StandingOfferSheet                         ├─ organic mirrors  (unchanged)
            └─ POST /api/trades/standing-offer       └─ standing offers  (NEW predicate)
                 └─ standing_offers row ─────────────────┘
                                                   └─ _stamp_own_standing_offers (NEW)
MatchesScreen 'standing' segment
  ├─ GET  /api/trades/standing-offers
  └─ POST /api/trades/standing-offer/revoke
```

---

## 2. Schema — `standing_offers`

New `Table(...)` in `backend/database.py`, placed immediately after
`asset_preferences_table` (`backend/database.py:1015-1024`).

```python
# ---------------------------------------------------------------------------
# standing_offers — broadcast intent to trade one player for any pick of a
# round (#362)
# ---------------------------------------------------------------------------
# Where trade_decisions holds ONE exact package the user liked, this holds a
# GENERALISED offer: "I will send player P for any round-R pick, in seasons
# Y, from teams T, in this league, until expires_at."
#
# Read by _inject_likes_you_cards_impl as a second candidate source next to
# the exact mirrors; written only by POST /api/trades/standing-offer.
#
# At most ONE LIVE offer per (user_id, league_id, player_id, round) —
# enforced AT THE WRITER with a `revoked_at IS NULL` predicate, deliberately
# NOT a UniqueConstraint: revoke-then-repost is a supported flow and a hard
# constraint would collide with it. Same idiom as
# trade_decisions.retracted_at (#318, database.py:335).
# ---------------------------------------------------------------------------
standing_offers_table = Table("standing_offers", metadata,
    Column("id",              Integer, primary_key=True, autoincrement=True),
    Column("user_id",         String,  nullable=False),   # the SENDER
    Column("league_id",       String,  nullable=False),
    Column("player_id",       String,  nullable=False),   # the asset offered OUT
    Column("round",           Integer, nullable=False),   # pick round wanted IN (v1: always 1)
    Column("seasons",         Text,    default="[]"),     # JSON array of ints, e.g. [2027, 2028]
    Column("team_user_ids",   Text,    default="[]"),     # JSON array of strings — PRIVATE (R-19)
    Column("source_trade_id", String),                    # provenance: the like that made it; nullable
    Column("created_at",      String),                    # ISO UTC
    Column("expires_at",      String),                    # ISO UTC, STORED not derived (R-23)
    Column("revoked_at",      String),                    # ISO UTC; NULL = live
    Index("ix_standing_offers_league_live", "league_id", "revoked_at"),
)
```

**Convention checks, all verified in this tree:**

| Rule | Precedent |
|---|---|
| JSON lives in `Text` columns, not a join table | `league_preferences.acquire_positions` / `.trade_away_positions`, `Text, default="[]"` holding `["WR","TE"]` — `backend/database.py:992-993` |
| Timestamps are ISO strings in `String` columns, never `DateTime` | `backend/database.py:335`, `:994`, `:1020` |
| No `asset_class` column | one asset class in v1; `round` already names it (coding guideline 2) |
| No `UniqueConstraint` | `asset_preferences` uses one (`:1023`) but has no revoke concept |
| `Index` declared inline on the `Table` | `mock_drafts` does the same — `backend/database.py:2152` |

**Migration.** This is a *whole new table*, created by the existing
`metadata.create_all(engine)` path (`backend/database.py:3331`). **Do NOT add a row to
`migration_cols`** (`backend/database.py:2432`) — that list is three-tuples for *columns
on existing tables*, and a bogus entry there will attempt an `ALTER TABLE` on a table that
was just created with the column.

**Data dictionary entry** (`docs/data-dictionary.md`, follow the `league_preferences`
shape at `:650`):

```markdown
## `standing_offers`

Per-(user, league, player, round) broadcast intent to trade a player for any pick of a
round. At most one LIVE row per `(user_id, league_id, player_id, round)` — enforced at
the writer with `revoked_at IS NULL`, not by a unique index.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `user_id`, `league_id` | str | `user_id` is the SENDER |
| `player_id` | str | the asset offered OUT |
| `round` | int | pick round wanted IN; v1 always `1` |
| `seasons` | JSON text | e.g. `[2027, 2028]` |
| `team_user_ids` | JSON text | e.g. `["u_1","u_2"]`. **Private** — never on a recipient-facing payload (#362 R-19) |
| `source_trade_id` | str | provenance: the `trade_id` of the like that created it; nullable |
| `created_at`, `expires_at` | str | ISO UTC. `expires_at` is stored, not derived (knob `standing_offer_days`) |
| `revoked_at` | str | ISO UTC; NULL = live |
```

---

## 3. Database helpers — `backend/database.py`

Four functions, appended in one contiguous block near the `trade_decisions` readers
(`backend/database.py:5228` area).

```python
def create_standing_offer(*, user_id, league_id, player_id, round, seasons,
                          team_user_ids, source_trade_id, days) -> dict | None:
    """Insert a standing offer. Returns the row dict, or None when a LIVE
    offer already exists for (user_id, league_id, player_id, round)."""
```
- Live check: `SELECT id FROM standing_offers WHERE user_id=? AND league_id=? AND
  player_id=? AND round=? AND revoked_at IS NULL AND expires_at > <now iso>` — an expired
  row does **not** block a new one.
- `created_at = _now_iso()`, `expires_at = (now + timedelta(days=days)).isoformat()`.
- `seasons` / `team_user_ids` stored via `json.dumps(sorted(...))`.

```python
def load_standing_offers(*, league_id, exclude_user_id=None, live_only=True) -> list[dict]:
    """Live standing offers for a league, newest first (id DESC).
    live_only ⇒ revoked_at IS NULL AND expires_at > now."""
```
- `id DESC` mirrors `load_recent_league_likes`'s newest-first ordering
  (`backend/database.py:5261`), so nothing new has to be explained about deck order.
- Returns `seasons` / `team_user_ids` already `json.loads`-ed into `list[int]` /
  `list[str]`.

```python
def load_user_standing_offers(*, user_id, league_id=None) -> list[dict]:
    """The caller's own offers — live AND expired — newest first. Used by the
    manage surface only, so team_user_ids is included."""
```

```python
def revoke_standing_offer(*, user_id, offer_id) -> bool:
    """Set revoked_at=<now iso> on the caller's own live offer. Idempotent:
    returns False when already revoked or not owned by user_id. NEVER
    deletes — the row is history (trade_decisions.retracted_at idiom)."""
```

**Ownership is checked in the WHERE clause**, not after the read: `UPDATE ... WHERE id=?
AND user_id=?`. A caller can never revoke another user's offer.

---

## 4. Routes — `backend/server.py`

All three on the existing `/api/trades/*` prefix, registered next to
`dismiss_awaiting_trade` (`backend/server.py:14830`). Both writes take
`@_gate_unverified_write` (`backend/server.py:2447`), stacked **under** `@app.route`,
matching every sibling — that decorator returns
`403 {"error": "verification_required"}` on an unverified write when a verified
controller exists or `auth.enforce_verified_writes` is on.

All three return `404` when `trade.standing_offers` is off, so the surface does not exist
flag-off (R-24).

### 4.1 `POST /api/trades/standing-offer` — create

**Request** (all fields required except `source_trade_id`):

```json
{
  "league_id": "1048291234567890123",
  "player_id": "4034",
  "round": 1,
  "seasons": [2027, 2028],
  "team_user_ids": ["u_bigbenchmob", "u_dynastydegen", "u_punt_the_te"],
  "source_trade_id": "likesyou_ab12cd34ef56"
}
```

- `seasons`: non-empty array of ints. Server sorts and de-duplicates.
- `team_user_ids`: non-empty array of strings, each a current member of `league_id`,
  excluding the caller. Server sorts and de-duplicates.
- `round`: int; **v1 accepts only `1`**.
- `source_trade_id`: string or omitted/null. Never validated against the deck — an
  FB-46-reconstructed card carries a synthetic id and must still work (R-18).

**200**

```json
{
  "status": "ok",
  "offer": {
    "offer_id": 41,
    "league_id": "1048291234567890123",
    "player_id": "4034",
    "player_name": "Malik Willis",
    "round": 1,
    "seasons": [2027, 2028],
    "team_user_ids": ["u_bigbenchmob", "u_dynastydegen", "u_punt_the_te"],
    "team_count": 3,
    "created_at": "2026-08-19T19:42:11+00:00",
    "expires_at": "2026-09-18T19:42:11+00:00",
    "days_left": 30,
    "revoked_at": null,
    "stale": false
  }
}
```

> `team_user_ids` and `team_count` appear here because this is the **sender's own**
> payload. They must never appear on a deck card (R-19).

**Errors**

| Status | Body | When |
|---|---|---|
| 400 | `{"error": "session not initialised"}` | no `user_id` on the session |
| 400 | `{"error": "league_id, player_id, round, seasons, team_user_ids are required"}` | any required field missing or empty |
| 400 | `{"error": "round must be 1"}` | `round != 1` (v1) |
| 400 | `{"error": "seasons must be within the league's pick horizon", "allowed_seasons": [2027, 2028]}` | any season not present as a round-1 `draft_picks` season for this league |
| 400 | `{"error": "team_user_ids must be current league members", "invalid": ["u_x"]}` | any id is not a member, or is the caller |
| 403 | `{"error": "verification_required"}` | `_gate_unverified_write` |
| 404 | *(Flask default)* | flag off |
| 409 | `{"error": "a live standing offer already exists for this player and round", "offer_id": 39}` | R-21 |
| 500 | `{"error": "internal_error"}` | unexpected |

`allowed_seasons` is the sorted distinct `season` of round-1 `draft_picks` rows for the
league — the same set the client derived its pills from (R-4), so a mismatch means the
client's cache was stale and it can refetch.

### 4.2 `GET /api/trades/standing-offers` — the caller's own list

Query: `?league_id=<id>` optional. Omitted ⇒ all leagues.

**200**

```json
{
  "offers": [
    {
      "offer_id": 41,
      "league_id": "1048291234567890123",
      "league_name": "QA Standard League",
      "player_id": "4034",
      "player_name": "Malik Willis",
      "round": 1,
      "seasons": [2027, 2028],
      "team_user_ids": ["u_bigbenchmob", "u_dynastydegen", "u_punt_the_te"],
      "team_count": 3,
      "created_at": "2026-08-19T19:42:11+00:00",
      "expires_at": "2026-09-18T19:42:11+00:00",
      "days_left": 18,
      "revoked_at": null,
      "stale": false
    }
  ]
}
```

- Sorted newest first (`id DESC`).
- Includes **live, expired and revoked** rows so the manage screen can group them. The
  client's grouping rule: **Active** = `revoked_at === null && days_left > 0 && !stale`;
  **Expired** = everything else.
- `days_left` = `ceil((expires_at - now) / 1 day)`, floored at `0`.
- `stale: true` when the offered player is **no longer on the sender's roster** — R-11.
  This is the same condition the injector enforces via roster containment
  (`backend/server.py:3010-3012`), applied here so the manage screen and the injector can
  never disagree. Resolving it needs the league's member rosters; use the cached league
  session state, and when the roster is unavailable return `stale: false` (fail-open on a
  display-only field — never fail a whole list read for it).
- Empty list ⇒ `{"offers": []}`, **never 404**.

### 4.3 `POST /api/trades/standing-offer/revoke`

POST, not DELETE — matching `/api/trades/awaiting/dismiss`
(`backend/server.py:14830`), the nearest sibling and also a "retract my own outbound
intent" operation.

**Request** `{"offer_id": 41}`

**200** `{"status": "ok", "revoked": true}` — `revoked: false` on an idempotent repeat or
an offer the caller does not own. **Still 200, never 404** (the awaiting/dismiss contract
at `backend/server.py:14848-14851` sets this precedent: `0` is still "ok").

**Errors** `400 {"error": "offer_id is required"}` · `400 {"error": "session not
initialised"}` · `403 {"error": "verification_required"}` · `404` flag off.

### 4.4 `docs/api-reference.md`

Three rows appended to the `## Trades` table (`docs/api-reference.md:227`), house style:
one row per route, request body inline in backticks, response after `→`, errors after `·`,
flag bolded, `Off ⇒ 404`. Plus the `standing_offer_reason` and `standing_offer_mine` keys
added to the `### Trade card object` fenced block (`:253`).

---

## 5. Injector — `backend/server.py`

### 5.1 The widened match rule

Inside `_inject_likes_you_cards_impl` (`backend/server.py:2943`), **after** the existing
organic-mirror loop and **before** the `if injected == 0: return cards` tail
(`backend/server.py:3096-3098`).

The organic loop is **not modified, reordered or copy-pasted**. Its `break` at
`backend/server.py:2999` still caps total injections at `_LIKES_YOU_CAP = 3`
(`backend/server.py:2928`).

```python
# #362 — standing offers as a SECOND candidate source. Everything below the
# candidate construction is the same sequence of filters the organic loop
# above runs; the two loops share `seen_keys`, `existing_by_key`,
# `boost_score` and `injected` so a standing offer can never double-inject a
# package an organic mirror already covered.
if _standing_offers_enabled():
    so_cap = min(_LIKES_YOU_CAP - injected, _standing_offer_inject_cap())
    for offer in load_standing_offers(league_id=league_id,
                                      exclude_user_id=user_id):
        if so_injected >= so_cap:
            trade_service._standing_offer_cap_drops += 1
            continue
        ...
```

**Candidate construction — the only genuinely new logic:**

1. `offer["user_id"] != user_id` (never mirror your own offer back at you).
2. `opp = members_by_id.get(offer["user_id"])`; skip if `None`.
3. `user_id in offer["team_user_ids"]` — **the selection test.**
4. `offer["player_id"] in set(opp.roster)` — the sender still holds the player. (This is
   the same containment the organic loop applies at `backend/server.py:3010`, and it is
   what makes R-11's staleness free.)
5. Candidate give-side picks = ids in `user_roster_set` that are **owned league picks of
   this league** (`pid.startswith(f"{league_id}_")`) whose parsed `(season, round)`
   satisfies `round == offer["round"]` and `season in offer["seasons"]`.
   Parse from the id: strip the `f"{league_id}_"` prefix, then `split("_")` →
   `[season, round, original_roster_id]` (format pinned at
   `backend/database.py:9120-9129`). Generic rungs are `generic_pick_*`
   (`backend/pick_values.py:213`) and fail the prefix test, so they can never satisfy an
   offer.
6. **Deterministic choice:** `sorted(candidates, key=lambda pid: (season, pid))[0]`.
   Exactly one candidate per offer per deck (R-12, `UT-10`).
7. `my_give = [that_pick_id]`, `my_recv = [offer["player_id"]]`, `target = opp.user_id`.

**Then the candidate falls into the identical filter sequence**, in this order — reuse the
existing code, do not restate it:

| Order | Filter | Line |
|---|---|---|
| 1 | untouchables on the user's give side (#95) | `backend/server.py:3016` |
| 2 | not-interested on the user's receive side (#163) | `backend/server.py:3021` |
| 3 | `seen_keys` dedup | `backend/server.py:3027-3030` |
| 4 | `trade_service._past_decision_keys` | `backend/server.py:3031` |
| 5 | G6 R4 `exclusion_keys` (#336), appending to `_r4_excluded_keys` | `backend/server.py:3038-3046` |
| 6 | **D-055 user-gain floor** `_likes_you_user_delta(...) < min_user_delta` | `backend/server.py:3055` |

The D-055 floor works correctly on picks because `seed_map` is primed with pick Elos —
`_inject_owned_picks` calls `seed_map.update(_pick_asset_elos(pick_assets))`
(`backend/server.py:10403-10411`) on a job-local copy. Without that priming every pick
would default to Elo 1500 and the floor would be meaningless; **verify the priming has run
before trusting the floor** (it has, for every deck the injector sees — the call site at
`backend/server.py:5422` is downstream of it).

**Survivors** take the same two branches as organic mirrors — flag+boost an existing deck
card (`backend/server.py:3058-3063`) or synthesize a `basis="consensus"` TradeCard
(`:3077-3094`) — with two additions on **both** branches:

```python
card.likes_you = True                       # reuses the shipped flare pill
card.standing_offer_reason = _standing_offer_reason(opp, offer, give_pick_label)
```

`trade_id` prefix for synthesized standing-offer cards: `standing_{uuid4().hex[:12]}`
(distinct from `likesyou_`, so a swipe row's provenance is readable). Register in
`trade_service._trade_cards` exactly as the organic branch does
(`backend/server.py:3092`), or `/api/trades/swipe` cannot resolve it.

**Server-fired event** `standing_offer_card_shown` (§7) fires once per injected
standing-offer card, via `record_event(user_id, "standing_offer_card_shown",
league_id=league_id, source="api", props={"round": ..., "seasons": len(...)})` — the
`trades_generated` pattern at `backend/server.py:5863-5868`. Wrap in try/except and log a
warning on failure; analytics must never break deck generation.

### 5.2 The reason line

```python
_ROUND_WORD = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}

def _standing_offer_reason(opp, offer, matched_pick_label: str) -> str:
    """R-16. Composed from (sender, player, round, seasons) ONLY — no count,
    no team names, no roster list (R-19)."""
```

Exact output for a two-season offer:

```
@qa_l1_member_01 posted a standing offer: Malik Willis for any 2027 or 2028 1st, and you hold a 2027 1st.
```

`seasons_phrase`: one season → `"2027"`; two → `"2027 or 2028"`; three or more →
`"2027, 2028 or 2029"` (comma-joined, final ` or `, no Oxford comma). Seasons ascending.
`matched_pick_label` is `_owned_pick_label(pick_row, slot_order)`
(`backend/server.py:9896`) of the viewer's own give-side pick. `player_name` from
`players_dict`; fall back to the id if absent.

### 5.3 Cap-drop counters

On `TradeService.__init__` next to `_r4_excluded_keys`
(`backend/trade_service.py:3078`) and reset in the same place as it
(`backend/trade_service.py:3194`):

```python
self._standing_offer_cap_drops: int = 0
self._organic_like_cap_drops: int = 0
```

The organic loop's existing `break` (`backend/server.py:2999`) becomes a counted `break`
— increment `_organic_like_cap_drops` by the number of remaining unexamined likes before
breaking, or leave it at a simple count of one; either is acceptable so long as it is
documented in the log line. Logged once, at the end of
`_inject_likes_you_cards_impl`:

```python
log.info("likes-you injection: injected=%d (organic=%d standing=%d) "
         "cap_drops(organic=%d standing=%d)", ...)
```

**No analytics event on a drop** (R-15).

### 5.4 Sender-side chip stamping — `_stamp_own_standing_offers`

New function in `backend/server.py`, called from the generate job immediately after the
`_inject_likes_you_cards` block (`backend/server.py:5422-5457`), inside its own
try/except (non-fatal — a failure serves the deck unchanged), gated on
`_standing_offers_enabled()`.

```python
def _stamp_own_standing_offers(cards: list, user_id: str, league_id: str) -> None:
    """R-9 — mark the SENDER's own cards that their live standing offers
    would cover, so the client can render the `Open to 1sts · '27-'28` chip
    without a client-side join. Mutates cards in place; never reorders."""
```

For each of the caller's live offers, for each card where
`offer["player_id"] in card.give_player_ids` **and** any `pid` in
`card.receive_player_ids` is an owned league pick of this league whose parsed
`(season, round)` matches the offer: set

```python
card.standing_offer_mine = {"round": offer["round"], "seasons": offer["seasons"]}
```

Never reorder, never boost, never filter. Display only.

### 5.5 Serialization — `trade_card_to_dict`

`backend/server.py:10637`. Two keys, appended next to the `likes_you` block
(`backend/server.py:10679-10681`), **each serialized only when set**, so flag-off payloads
stay byte-identical (R-24, `UT-14`):

```python
    # #362 — standing-offer provenance. Recipient-facing; composed
    # server-side and carries NO team ids and NO counts (R-19).
    _so_reason = getattr(card, "standing_offer_reason", None)
    if _so_reason:
        out["standing_offer_reason"] = _so_reason
    # #362 — the SENDER's own chip. Present only on the sender's own deck.
    _so_mine = getattr(card, "standing_offer_mine", None)
    if _so_mine:
        out["standing_offer_mine"] = _so_mine
```

### 5.6 `TradeCard` dataclass

`backend/trade_service.py:2833`. Two optional fields appended in the existing
comment-per-field style:

```python
    # #362 (flag trade.standing_offers) — "Why you're seeing this" line for a
    # card produced by a league-mate's standing offer. Server-composed;
    # serialized only when set. Never carries team ids or counts (R-19).
    standing_offer_reason: Optional[str] = None
    # #362 — {"round": int, "seasons": [int]} when one of the DECK OWNER's own
    # live standing offers covers this card. Display only; never reorders.
    standing_offer_mine: Optional[dict] = None
```

### 5.7 Signal-spine features dict

`backend/server.py:3850` currently stamps `"likes_you"` into the impression features.
Add `"standing_offer": True` so the two injection sources are separable in the
deck-outcome corpus. **A boolean, not the reason string** — the corpus must not carry
copy.

> **Amended by the backend build agent, 2026-08-19 — key-only-when-set, NOT inside the
> literal.** This section originally said "alongside it", i.e. inside the always-emitted
> `features = {...}` dict. Built that way it **fails**
> `backend/tests/test_bakeoff_serving.py::test_flag_off_is_byte_identical_to_the_captured_golden`,
> which pins `features_json` byte-for-byte against a golden captured at the pre-bake-off
> SHA — an unconditional new key is a byte change on a surface that has none, and R-24
> requires flag-off byte-identity anyway. The shipped form follows the `deck_source`
> (F10) / `first_deck` (F9) discipline immediately below it in that function:
>
> ```python
> if getattr(card, "standing_offer_reason", None):
>     features["standing_offer"] = True
> ```
>
> With the flag off no card can carry the attribute, so the key never appears. Pinned by
> `test_signal_features_standing_offer_key_is_set_only_when_true`.

---

## 6. Flags and knobs

### 6.1 `trade.standing_offers`

- `backend/feature_flags.py` `FLAG_KEYS` — append next to `trade.likes_you` (`:89`):
  ```python
      "trade.standing_offers",  # #362 broadcast a liked 1-for-1 as a standing offer (server.py)
  ```
- `config/features.json` — a `_comment_standing_offers` sibling immediately preceding the
  key, per the house convention (`config/features.json:26-40`):
  ```json
    "_comment_standing_offers": "2026-08-19 #362 standing offers (docs/feedback/items/362-standing-offer/). trade.standing_offers gates the post-like sheet, the three /api/trades/standing-offer* routes (404 when off), the standing-offer branch of _inject_likes_you_cards_impl, and the sender-side chip stamp. Requires trade.likes_you (the receiving half) and trade.picks_in_pool (picks must be roster assets) — with either off the feature is inert. OFF (default) = no route, no prompt, no predicate evaluated, byte-identical deck payloads. Deploy-free tuning: model_config standing_offer_inject_cap (0 kills injection without a flag flip) and standing_offer_days.",
    "trade.standing_offers": false,
  ```
- Server accessor next to `_likes_you_enabled` (`backend/server.py:2881`):
  ```python
  def _standing_offers_enabled() -> bool:
      return getattr(FLAGS, "trade_standing_offers", False)
  ```
- Client: register in `mobile/src/state/useFeatureFlags.ts` the same way
  `trade.likes_you`'s neighbours are, defaulting to the served value.

### 6.2 `model_config` keys

Appended to `_MODEL_CONFIG_DEFAULTS` (`backend/database.py:2157`) as one contiguous block
at the end, following the D-079 block's comment style (`:2360-2367`):

```python
    # ── #362 standing offers (flag trade.standing_offers) ────────────────
    ("standing_offer_days",       30.0, "#362: days a standing offer stays live; stored on the row at create time, so a change here moves only offers created after it"),
    ("standing_offer_inject_cap",  2.0, "#362: max of the 3 likes-you injection slots a deck may spend on standing offers (organic mirrors are evaluated first). 3 = unreserved cap; **`0` = off / kill switch**, standing offers stop injecting without a flag flip"),
```

Read through `trade_service._cfg`, the `_likes_you_min_user_delta` pattern
(`backend/server.py:2900-2911`) — defensive, so a missing key can never break deck
generation:

```python
def _standing_offer_inject_cap() -> int:
    try:
        from .trade_service import _cfg as _ts_cfg
        return max(0, int(_ts_cfg.get("standing_offer_inject_cap", 2)))
    except Exception:
        return 2
```

`standing_offer_days` is read at the route with `get_config().get("standing_offer_days",
30)`, the `_picks_pool_cap` pattern (`backend/server.py:10251-10258`).

`docs/config-reference.md`: one flag row under a new `## Flags — Standing offers (#362)
(2026-08-19 — ships dark)` group, and one `### Standing offers — `backend/server.py`,
DB-seeded` group in the `model_config` half (`:529`), each Meaning cell ending with the
kill-switch sentence per house style.

---

## 7. Analytics

Exact registration sites and literal shapes:

**`backend/analytics_taxonomy.py`** — one dated banner block appended to
`ALLOWED_CLIENT_EVENTS` (`:38`) in the `:449-487` style, naming the tracking-plan
addendum path, the client-vs-server rationale, the `FUNNEL_CRITICAL` verdict (**no** — a
side surface, not a step in the core loop), the `NON_INTENT_EVENTS` verdict per event, and
the cardinality bound (counts only, no ids):

```python
    # ── #362 standing offers, 2026-08-19 ────────────────────────────────
    "standing_offer_prompted", "standing_offer_posted",
    "standing_offer_skipped", "standing_offer_revoked",
```

`CLIENT_EVENT_PROPS` (`:627`) — **mandatory**: the import-time check at `:1283-1288`
raises `ValueError` if any `ALLOWED_CLIENT_EVENTS` member has no entry here.

```python
    "standing_offer_prompted": frozenset({"round", "seasons_offered",
                                          "teams_offered"}),
    "standing_offer_posted":   frozenset({"round", "seasons", "teams",
                                          "used_all_teams"}),
    "standing_offer_skipped":  frozenset({"snoozed", "retired"}),
    "standing_offer_revoked":  frozenset({"age_days"}),
```

`SERVER_FIRED_EVENTS` (`:494`) — server-fired events have **no** `CLIENT_EVENT_PROPS`
entry; document props in the inline comment, per `awaiting_trade_dismissed` (`:540-556`):

```python
    # #362 — one per standing-offer card injected into a served deck.
    # Props: round (int), seasons (int count). Never team ids or counts (R-19).
    # NOT in ALLOWED_CLIENT_EVENTS: the client cannot know an injection
    # happened without the server telling it, which would be a round trip
    # for an impression.
    "standing_offer_card_shown",
```

**`backend/analytics_queries.py`** `NON_INTENT_EVENTS` (`:63`) — **same commit**, per the
house comment convention (`:73-76`):

```python
    # #362 standing offers, 2026-08-19 — added in the SAME commit that added
    # them to ALLOWED_CLIENT_EVENTS / SERVER_FIRED_EVENTS. `_posted` and
    # `_revoked` are deliberately ABSENT: both are deliberate user actions.
    "standing_offer_prompted", "standing_offer_skipped",
    "standing_offer_card_shown",
```

`INTENT_EVENTS` is derived by subtraction at `:244`, so omitting the three impression-class
names silently inflates DAU/WAU. That is the failure this rule exists for.

---

## 8. Mobile

### 8.1 `mobile/src/api/trades.ts` — three client functions

Appended after `dismissAwaitingTrade` (`:578-590`), each with the contract restated in a
comment block, matching that function's house style.

```ts
export interface StandingOffer {
  offer_id: number;
  league_id: string;
  league_name?: string;
  player_id: string;
  player_name: string;
  round: number;
  seasons: number[];
  /** Sender-owned payloads only — never present on a deck card (#362 R-19). */
  team_user_ids: string[];
  team_count: number;
  created_at: string;
  expires_at: string;
  days_left: number;
  revoked_at: string | null;
  /** True when the offered player has left the sender's roster — the offer is
   *  dead regardless of the clock. The injector enforces the same test. */
  stale: boolean;
}

export async function createStandingOffer(body: {
  league_id: string; player_id: string; round: number;
  seasons: number[]; team_user_ids: string[]; source_trade_id?: string;
}): Promise<{ status: string; offer: StandingOffer }>;

export async function getStandingOffers(leagueId?: string): Promise<StandingOffer[]>;

export async function revokeStandingOffer(offerId: number):
  Promise<{ status: string; revoked: boolean }>;
```

`getStandingOffers` unwraps `res.offers` and returns `[]` on a malformed payload — the
`getAwaitingTrades` posture (`:557-560`).

### 8.2 `mobile/src/shared/types.ts` — two card fields

Appended next to `likesYou` (`:184`):

```ts
  /** #362 — server-composed "Why you're seeing this" line when this card came
   *  from a league-mate's standing offer. Serialized only when set. Carries no
   *  team ids and no counts by construction (R-19). */
  standingOfferReason?: string;
  /** #362 — set when one of the DECK OWNER's own live standing offers covers
   *  this card; drives the `Open to 1sts · '27-'28` chip. Display only. */
  standingOfferMine?: { round: number; seasons: number[] };
```

Normalizer (`mobile/src/api/trades.ts:181-193`), same posture as `likesYou`:

```ts
    standingOfferReason: typeof raw?.standing_offer_reason === 'string'
      ? raw.standing_offer_reason : undefined,
    standingOfferMine:   raw?.standing_offer_mine ?? undefined,
```

### 8.3 `mobile/src/components/StandingOfferSheet.tsx` — new

Props:

```ts
export interface StandingOfferSheetProps {
  visible: boolean;
  leagueId: string;
  /** The card just liked — give[0] is the player, receive[0] the source pick. */
  playerId: string;
  playerName: string;
  sourcePickId: string;
  sourceSeason: number;
  sourceTeamUserId: string;
  round: number;                       // v1 always 1
  /** All round-1 seasons present in the league (R-4). Derived, never literal. */
  availableSeasons: number[];
  /** Every other league member (R-5). */
  members: Array<{ user_id: string; username: string }>;
  /** owner_user_id → seasons in which they hold a round-`round` pick (R-5). */
  memberFirstsBySeason: Record<string, number[]>;
  sourceTradeId?: string;
  defaultSelection?: StandingOfferDefaultSelection;  // defaults to the R-6 constant
  onPosted: (offer: StandingOffer) => void;
  onSkip: (snoozed: boolean, retired: boolean) => void;
}
```

Chalkline: **ice** for the CTA and the selected-state affordances (actions); **flare**
nowhere in this sheet (it is informational-only, and the flare pill in this feature is the
existing "They're interested" treatment on the recipient card, reused unchanged); no
emoji as icons; radius ≤8px except the specced season pills; per
`docs/design/design-system.md` + `docs/design/components.md`.

`testID`s: `standing-offer-sheet`, `standing-offer-season-<season>`,
`standing-offer-team-<user_id>`, `standing-offer-all-seasons`,
`standing-offer-all-teams`, `standing-offer-confirm`, `standing-offer-skip`. All must pass
`mobile/scripts/testid-lint.sh`.

### 8.4 `mobile/src/screens/TradesScreen.tsx`

Confined to the `advance()` post-like branch (`:4179-4241`) plus the new state and the
sheet mount. **Do not touch** `swipeMutation` (`:1795-1893`) or the guide/Apple chain
(`:3432-3490`) — §7.4 of the PRD.

New: `maybeShowStandingOfferPrompt(card)` implementing R-1's eleven conditions and R-3's
ladder — modelled line-for-line on `maybeShowQuicksetPrompt` (`:3113-3143`) and
`snoozeQuicksetPrompt` (`:3145-3156`). The only site that may set the sheet's visibility
(R-2, `SC-2`).

Prefetch, when `trade.standing_offers` is on and the deck loads: `getLeaguePicks(leagueId)`
and `getStandingOffers(leagueId)` via react-query. Both fail-closed at swipe time (R-1
note).

### 8.5 `mobile/src/components/TradeCard.tsx`

One new text line, rendered under the existing "Why you're seeing this"-adjacent copy slot
when `data.standingOfferReason` is set, and one chip slot when `data.standingOfferMine` is
set. **No new pill or badge component** — the "They're interested" pill at `:375-378` is
reused as-is (R-17).

### 8.6 `mobile/src/screens/MatchesScreen.tsx`

`type Segment = 'mutual' | 'awaiting'` (`:67`) → `'mutual' | 'awaiting' | 'standing'`.
The new segment lists offers from `getStandingOffers()`, grouped Active / Expired per
§4.2, with a **Revoke** action only (no Edit, no Repost — PRD R-10). No `FeedbackFAB`
(covered by the RootNav tab-stack mount, CLAUDE.md #188).

### 8.7 `mobile/src/state/useOnboardingState.ts`

Four keys on `OnboardingPersisted` (`:16-92`) and in `DEFAULTS` (`:88`):

```ts
  // #362 — standing-offer prompt ladder (quickset semantics, R-3)
  standingOfferPromptShows: number;        // 0
  standingOfferPromptSnoozed: boolean;     // false
  standingOfferPromptSession2Shown: boolean; // false
  standingOfferPromptRetired: boolean;     // false
```

Additive and read only behind the flag, so with the flag dark the store is inert — the
posture the file's own header states (`:9-12`).

---

## 9. Touch-point index

| File | Change | Collision risk |
|---|---|---|
| `backend/database.py` | `standing_offers_table` + `Index`; 4 helpers; 2 `_MODEL_CONFIG_DEFAULTS` rows (`:2157`) | **shared registry** — one contiguous append block |
| `backend/server.py` | `_standing_offers_enabled` (`~:2881`); injector branch (`:2943`, after `:3095`); `_standing_offer_reason`; `_stamp_own_standing_offers` (call site `~:5457`); 2 `trade_card_to_dict` keys (`:10679`); 1 signal-features key (`:3850`); 3 routes (`~:14870`) | **shared** — keep each edit surgical |
| `backend/trade_service.py` | 2 `TradeCard` fields (`:2833`); 2 counters (`:3078`, reset `:3194`) | low |
| `backend/feature_flags.py` | 1 `FLAG_KEYS` entry (`:89` neighbour) | append-only |
| `backend/analytics_taxonomy.py` | 4 client + 1 server event; 4 `CLIENT_EVENT_PROPS` entries | append-only |
| `backend/analytics_queries.py` | 3 `NON_INTENT_EVENTS` entries (`:63`) | append-only |
| `config/features.json` | flag + `_comment_` sibling | append-only |
| `mobile/src/api/trades.ts` | 3 fns + `StandingOffer`; 2 normalizer keys | low |
| `mobile/src/shared/types.ts` | 2 card fields (`:184` neighbour) | low |
| `mobile/src/components/StandingOfferSheet.tsx` | **new** | none |
| `mobile/src/screens/TradesScreen.tsx` | trigger + ladder + sheet mount | **HIGH — 7,563 lines; see PRD §7.4** |
| `mobile/src/components/TradeCard.tsx` | reason line + chip slot | low |
| `mobile/src/screens/MatchesScreen.tsx` | third segment (`:67`) | medium (#360) |
| `mobile/src/state/useOnboardingState.ts` | 4 persisted keys | low |
| `mobile/src/state/useFeatureFlags.ts` | 1 client flag default | append-only |
| `mobile/tests/check-standing-offer-362.js` + `mobile/package.json:52` | **new** | none |
| `backend/tests/test_standing_offers.py` | **new** | none |

---

## 10. LLD conventions this establishes

One line for `living-memory/LLD.md`:

> **The likes-you match rule is a union, not a single source (#362, 2026-08-19).**
> `_inject_likes_you_cards_impl` draws candidates from *exact mirrors* (`trade_decisions`
> likes, 90-day window) **and** from *standing offers* (`standing_offers`, generalised
> intent). Both then pass through the identical filter sequence — untouchables,
> not-interested, `_past_decision_keys`, R4 exclusion, D-055 floor — and share one
> `_LIKES_YOU_CAP` of 3, of which standing offers may take at most
> `standing_offer_inject_cap`. Any future candidate source joins the same union and the
> same filter sequence; forking the loop is the failure mode this convention exists to
> prevent.

Plus, as a general schema convention already implicit in the tree and now stated:
**"at most one live row" is enforced at the writer with a `<x>_at IS NULL` predicate, not
a `UniqueConstraint`, whenever the row has a revoke/retract concept** — `trade_decisions`
(`retracted_at`, #318) and now `standing_offers` (`revoked_at`, #362).
