# LLD — P0-1: write `ranking_method` at the point of use

> Code-level design for finding **P0-1** of the 2026-08-09 mobile UX audit.
> **Build agent:** `W1-BE`. **Commit:** 2 of 15 (`P0-1: write ranking_method at the
> point of use + suppressed startup backfill`).
> **Worktree:** `ftf-p0-remediation`, branch `p0-remediation-2026-08-10`, off
> `origin/main @ ab9368f`.
>
> **Bound by** `hld.md` §2 S-01…S-07 · §3 commit 2 · §4 W1-BE · §6 rows 1, 8 ·
> §7 · §8 R7 · §9 LLD-1 · §10.3. Where `plan-p0-1.md` / `scope-p0-1.md` disagree
> with the HLD or with code verified in this worktree, **§11 Deviations** states it
> explicitly — nothing here diverges silently.
>
> **Companions:** `prd-p0-1.md` (requirements + acceptance), `plan-p0-1.md`
> (rationale of record), `scope-p0-1.md` (gate declarations).

## Contents

- [1. Conformance summary](#1-conformance-summary)
- [2. Data layer — `backend/database.py`](#2-data-layer--backenddatabasepy)
- [3. Route layer — `backend/server.py`](#3-route-layer--backendserverpy)
- [4. The write matrix, as concrete conditionals](#4-the-write-matrix-as-concrete-conditionals)
- [5. The `quickset-done` inversion (S-06)](#5-the-quickset-done-inversion-s-06)
- [6. Mobile — one `testID`](#6-mobile--one-testid)
- [7. Backend tests — `test_ranking_method_point_of_use.py`](#7-backend-tests--test_ranking_method_point_of_usepy)
- [8. Maestro delta](#8-maestro-delta)
- [9. Build order inside the commit](#9-build-order-inside-the-commit)
- [10. What this LLD deliberately does not do](#10-what-this-lld-deliberately-does-not-do)
- [11. Deviations](#11-deviations)

---

## 1. Conformance summary

| HLD row | How this LLD satisfies it |
|---|---|
| **S-01** `'anchor' → 'quickset'` upgrade | §3.4's call passes `allow_over=("anchor",)`; §2.1's helper widens its `WHERE` by exactly that tuple and nothing else. Truth table in §4.2. |
| **S-02** startup migration, cohort = NULL method + all four positions in ≥1 format | §2.2 + §2.3. |
| **S-03** push fan-out suppressed by pre-seeding `unlocked_formats` | §2.2.3 — **the exact mechanism**, traced through `mark_format_unlocked`'s `was_first` computation and `get_rankings_progress`'s `_already_unlocked` short-circuit. |
| **S-04** no flag, no analytics event | Nothing in this LLD adds a `record_event` call, a `FLAG_KEYS` entry, or a `config/features.json` key. |
| **S-05** live-experiment check | Pre-merge checklist item, `prd-p0-1.md` §7. Not a build task. |
| **S-06** fixture / seeder / capture inversion ships in the same commit | §5. |
| **S-07** old capture re-captured, not preserved | §8.2. |
| **§10.3** `testid-lint.sh` does **not** read `CLAUDE.md` | §6 — the registry row is W3-DOCS's, and is **not** a wave-1 dependency. `plan-p0-1.md` change-list item 15 is dropped. |
| **§7** docs | No `docs/**` or `living-memory/**` file is touched by this commit. Rows supplied to W3-DOCS in `prd-p0-1.md` §5; ids are **D-025** (not D-011) and, if needed, **G-027+**. |
| **R1** line-number drift | Every anchor below carries a **grep string** as well as a line number. The build agent re-greps before editing and trusts the grep string. |

**Files this commit touches** (exactly `hld.md` §4 W1-BE's P0-1 rows, minus the
dropped `CLAUDE.md` row, plus two `test_seed_ui_test_db.py` rewrites forced by §5
— see §11 D-3):

```
backend/database.py
backend/server.py
backend/tests/fixtures/profiles/quickset-done.json
backend/tests/fixtures/seed_ui_test_db.py
backend/tests/test_ranking_method_point_of_use.py          (new)
backend/tests/test_seed_ui_test_db.py                      (two tests rewritten)
mobile/src/screens/RankScreen.tsx
mobile/.maestro/flows/p0-1-quickset-unlock.yaml            (new)
mobile/.maestro/capture/league@quickset-done.yaml
```

---

## 2. Data layer — `backend/database.py`

### 2.1 `set_ranking_method_if_unset`

**Placement:** immediately after `set_ranking_method` (currently `:3358-3365`,
grep `def set_ranking_method(`) and before `get_ranking_method` (`:3368`).

**Signature**

```python
def set_ranking_method_if_unset(
    user_id: str,
    method: str,
    allow_over: tuple[str, ...] = (),
) -> bool:
```

- `user_id` — `users.sleeper_user_id` (account-scope keys `acct_<id>` included; the
  column is a plain PK string and this helper makes no assumption about its shape).
- `method` — one of `RANKING_METHODS = ("trio", "manual", "tiers", "anchor", "quickset")`
  (the set `set_ranking_method_route` validates at `server.py:6303`, mirrored in
  `seed_ui_test_db.py:138`). An unknown value is a **programming error**; the helper
  returns `False` without writing rather than raising (§2.1.4).
- `allow_over` — a tuple of *existing* method strings this write is permitted to
  overwrite. Default `()` = first-use-wins with no exceptions. The **only** caller
  that passes a non-empty tuple is the tiers/quickset save, and it passes exactly
  `("anchor",)` (S-01).
- **Returns** `True` iff a row was actually written (`rowcount > 0`), `False`
  otherwise — including "the user already has a method", "the value is unchanged",
  and "no such users row". Callers use the return value only to decide whether to
  drop the league-members cache (§3.2).

**Body — one conditional `UPDATE`, one statement, one transaction**

```python
def set_ranking_method_if_unset(user_id, method, allow_over=()):
    """P0-1 — record the ranking method at the point of USE, first-use wins.

    A SINGLE conditional UPDATE, so it is race-free under concurrent saves:
    there is no read-then-write window in which two requests can both decide
    the column is empty. Returns True iff this call wrote the value.

    FIRST-USE WINS, not last-use wins. The unlock rule in
    get_rankings_progress is method-dependent, so overwriting an established
    method can RE-LOCK a user who already qualified under the old one — the
    exact regression the monotonic unlocked_formats floor was added for
    (server.py:6177-6187). Writing only where there was nothing means this
    helper can never subtract an unlock.

    `allow_over` is the one deliberate widening: 'anchor' is the only method
    string whose unlock rule can never succeed (it falls to the trio branch),
    so a completeness-marking tiers/quickset save is allowed to overwrite it
    and ONLY it. See docs/plans/audit-p0-remediation/lld-p0-1.md §4.2.
    """
    if method not in RANKING_METHODS:
        return False
    col  = users_table.c.ranking_method
    cond = or_(col.is_(None), col == "")
    if allow_over:
        cond = or_(cond, col.in_(tuple(allow_over)))
    with engine.begin() as conn:
        res = conn.execute(
            update(users_table)
            .where(users_table.c.sleeper_user_id == user_id)
            .where(cond)
            .values(ranking_method=method)
        )
    return bool(res.rowcount)
```

Rendered SQL (SQLite and Postgres alike; `allow_over=("anchor",)` shown):

```sql
UPDATE users SET ranking_method = ?
 WHERE users.sleeper_user_id = ?
   AND (users.ranking_method IS NULL
        OR users.ranking_method = ''
        OR users.ranking_method IN (?))
```

**2.1.1 Why the condition is built in Python rather than always emitting `IN`.**
An empty `allow_over` must not render `IN ()`. SQLAlchemy's empty-`IN` expansion is
version-dependent and has historically emitted a warning plus a synthetic
always-false predicate; building the `or_` conditionally removes the question. It
also keeps the common case (`allow_over=()`, three of the four call sites) to the
two-clause form.

**2.1.2 Why `= ''` is in the predicate.** `''` is not written by any current path,
but `_note_ranking_method` is a bookkeeping write and the column is a bare `String`
with no `CHECK`. Treating empty-string as unset costs one clause and closes the
only way a row could be permanently un-writable by a legacy/manual edit. The
backfill (§2.2) uses the identical unset predicate, so the two never disagree
about who is "unset".

**2.1.3 No `INSERT` fallback.** Unlike `set_profile_public` (`:3390`) and
`set_stud_tax_mode` (`:3425`), this helper does **not** create the `users` row when
`rowcount == 0`. Every call site is behind `_require_initialized_session`, which
implies session-init already upserted the user. Inventing a `users` row from a
ranking save would create a row with no `created_at` semantics and is out of scope.
A missing row is simply "not written" — the next save writes it once session-init
has run.

**2.1.4 Never raises to the caller's caller.** The helper can still raise on a DB
outage (it is an ordinary DB helper and behaves like its neighbours). The
never-raises contract lives one level up, in `_note_ranking_method` (§3.2) — that
is the layer the four save handlers call, and it is the layer that must not be able
to fail a user's save.

**2.1.5 Docstring cross-reference is mandatory.** The docstring must name
`server.py:6177-6183` (the re-lock hazard comment) so the next reader can find the
argument for first-use-wins without this document.

### 2.2 `backfill_ranking_method_from_tiers`

**Placement:** immediately after `_backfill_mfl_name_entities`'s final
`print(f"[backfill] mfl name entities failed: {e}")` (currently `:2436`, grep
`mfl name entities failed`) and before `EXPERIMENT_LAYERS = (` (`:2439`). It sits
in the backfill block with `_backfill_dual_format` (`:2233`) and inherits that
block's "never break boot" posture.

It is **public** (no leading underscore) because `prd-p0-1.md` §7 has the operator
importing it for a dry-run count against a prod replica, and because the pytest
suite calls it directly (T-18…T-22).

**2.2.1 Signature and contract**

```python
def backfill_ranking_method_from_tiers() -> int:
    """P0-1 (audit 2026-08-09) — one-time repair for users who completed a
    Quick Set / Tiers board BEFORE the point-of-use writes shipped, and are
    therefore stuck on the trio branch of get_rankings_progress with
    unlocked:false forever.

    COHORT (deliberately narrow):
        ranking_method IS NULL (or '')  AND  tiers_saved names all four of
        QB/RB/WR/TE for AT LEAST ONE scoring format
      → ranking_method = 'quickset'
      → unlocked_formats gains every qualifying format (see below)

    STRICTLY IMPROVING. For every row it touches the tiers branch returns
    True, which is >= whatever the trio branch was returning. A user with a
    PARTIAL tier board plus a full trio board is a real shape; tagging them
    would move them from the trio rule to the tiers rule and could RE-LOCK
    them, so they are excluded. They lose nothing: their next full-board save
    writes the method at the point of use anyway.

    THE unlocked_formats PRE-SEED IS NOT COSMETIC — it is the fan-out
    suppression required by hld.md S-03. See lld-p0-1.md §2.2.3.

    Idempotent by predicate (after the first run the cohort is empty), safe on
    every boot, and never raises: a failure prints and returns what it wrote.
    Returns the number of rows written.
    """
```

**2.2.2 Body**

```python
    _POS = ("QB", "RB", "WR", "TE")
    col  = users_table.c.ranking_method
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                select(users_table.c.sleeper_user_id,
                       users_table.c.tiers_saved,
                       users_table.c.unlocked_formats)
                .where(or_(col.is_(None), col == ""))
            ).fetchall()
    except Exception as e:
        print(f"[backfill] ranking_method cohort read failed: {e}")
        return 0

    # (uid, merged unlocked_formats JSON) for every qualifying row.
    plan: list[tuple[str, str]] = []
    for row in rows:
        saved    = _parse_per_format_json(row.tiers_saved, is_list=True)
        complete = [f for f in SCORING_FORMATS
                    if all(p in (saved.get(f) or []) for p in _POS)]
        if not complete:
            continue
        try:
            existing = json.loads(row.unlocked_formats) if row.unlocked_formats else []
            if not isinstance(existing, list):
                existing = []
        except (json.JSONDecodeError, TypeError):
            existing = []
        merged = list(existing) + [f for f in complete if f not in existing]
        plan.append((row.sleeper_user_id, json.dumps(merged)))

    written = 0
    for i in range(0, len(plan), 500):
        chunk = plan[i:i + 500]
        try:
            with engine.begin() as conn:
                for uid, uf in chunk:
                    conn.execute(
                        update(users_table)
                        .where(users_table.c.sleeper_user_id == uid)
                        .values(ranking_method="quickset", unlocked_formats=uf)
                    )
            written += len(chunk)
        except Exception as e:
            print(f"[backfill] ranking_method chunk at {i} failed: {e}")

    if plan:
        # scope-p0-1.md §2 makes the affected ids a BUILD REQUIREMENT: the
        # scoped SQL undo is only expressible if the cohort was logged.
        print(f"[backfill] ranking_method: tagged {written}/{len(plan)} user(s) "
              f"'quickset' — cohort: {[uid for uid, _ in plan]}")
    return written
```

Design notes, each load-bearing:

- **Python filter, not SQL.** `tiers_saved` is a per-format JSON blob
  (`{"1qb_ppr": ["QB","RB"], "sf_tep": []}`) read everywhere else through
  `_parse_per_format_json` (`:3482`). Reusing that parser is what guarantees the
  backfill's reading of "all four saved" is byte-identical to `get_tiers_saved`'s
  (`:3573`), which is the function the unlock ladder actually calls. Expressing the
  same predicate as portable SQLite+Postgres JSON-over-TEXT is fragile and would be
  a *second* definition of completeness.
- **Both columns in one `UPDATE` per row.** `ranking_method` and `unlocked_formats`
  must never be observable apart: a request that saw `'quickset'` without the floor
  would take the `was_first` branch and fan out (§2.2.3). One statement per row
  inside one transaction removes the interleaving entirely.
- **Chunked at 500** so a large cohort cannot hold one long write transaction open
  across the whole `users` table at boot, and so one bad row fails 500 rows rather
  than all of them.
- **`written` counts rows in successfully committed chunks**, and the log prints
  `written/len(plan)` so a partial failure is visible in the boot log rather than
  inferred.
- **Idempotence** is by predicate: the second run's cohort query returns no rows for
  anyone tagged by the first, so `plan == []`, nothing is printed, and it returns 0
  (T-21).
- **Malformed input** is absorbed: `_parse_per_format_json` already swallows
  `JSONDecodeError`/`TypeError` and returns the empty per-format dict, so
  `tiers_saved` of `NULL` / `''` / `'{}'` / `'not json'` / a legacy top-level list
  all produce `complete == []` and no write (T-22).

**2.2.3 The push-suppression mechanism, exactly (S-03)**

The thing being suppressed is in `get_rankings_progress`
(`server.py:6199-6265`, grep `_already_unlocked`):

```python
6199    if unlocked:
6207        _already_unlocked = fmt in unlocked_formats_list
6208        _unlock_res = {"inserted": False, "was_first": False}
6209        if not _already_unlocked:
6211            _unlock_res = mark_format_unlocked(g_user_id, fmt) or _unlock_res
...
6228        if _unlock_res.get("was_first"):
6230            record_event(g_user_id, "ranking_complete_first_time", …)
6246            _members = load_league_member_unlock_states(_league_id, exclude_user_id=g_user_id)
6254            _send_typed_push(_p["user_id"], "league_member_unlocked_trades", …)
```

and in `mark_format_unlocked` (`database.py:3862-3901`):

```python
3892        was_first = (len(unlocked) == 0)
3893        inserted  = scoring_format not in unlocked
...
3901        return {"inserted": inserted, "was_first": was_first and inserted}
```

**The chain, step by step, for a backfilled user's first `/api/rankings/progress`
call after the deploy:**

1. `get_ranking_method` now returns `'quickset'` → the ladder takes the
   `elif ranking_method in ("tiers","quickset")` branch (`server.py:6165`) →
   `unlocked = True` for the active format (the backfill's own cohort predicate is
   what guarantees this).
2. `get_unlocked_formats` (`:6184`) returns the pre-seeded list, which **contains
   that format** — because the backfill seeded every format in which all four
   positions are saved, i.e. exactly the formats for which step 1 can return True.
3. `_already_unlocked = fmt in unlocked_formats_list` is therefore `True`
   (`:6207`), so **`mark_format_unlocked` is never called** (`:6209`) and
   `_unlock_res` keeps its literal `{"inserted": False, "was_first": False}`.
4. `if _unlock_res.get("inserted")` is False → no members-cache invalidation.
   `if _unlock_res.get("was_first")` is False → **no `ranking_complete_first_time`
   event and no `league_member_unlocked_trades` push fan-out.**

Two properties worth stating so no one "improves" this later:

- Seeding **only** the qualifying formats is what keeps the suppression exact. If
  the user's active format is the *other*, non-complete format, step 1 returns
  `False` for it, the monotonic OR at `:6188` does not fire (that format is not in
  the list), and nothing is marked — which is correct, because they have not built
  that board.
- Even if step 3 were somehow bypassed, `mark_format_unlocked` would still return
  `was_first=False`, because `was_first = (len(unlocked) == 0)` and the pre-seeded
  list is non-empty. **The suppression is belt-and-braces: the short-circuit and
  the `was_first` computation each independently suppress it.**

**Permanent, deliberate consequence.** A backfilled user has spent `was_first`
forever: a genuine later unlock in their *second* format will insert the format but
will never emit `ranking_complete_first_time`. That is the price S-03 accepts, and
it is recorded in `prd-p0-1.md` §8 and in the D-025 entry W3-DOCS writes.

### 2.3 Call the backfill from `_migrate_db()`

Current (`:1967-1971`, grep `_backfill_mfl_name_entities()`):

```python
1967    # Backfill: tag existing rows with '1qb_ppr' format since that was the only one
1968    _backfill_dual_format()
1969
1970    # #258 — entity-decode MFL names stored before #210's import-time cleaning
1971    _backfill_mfl_name_entities()
```

After:

```python
1970    # #258 — entity-decode MFL names stored before #210's import-time cleaning
1971    _backfill_mfl_name_entities()
1972
1973    # P0-1 (audit 2026-08-09) — users who completed a Quick Set board before
1974    # the point-of-use ranking_method writes shipped are stuck on the trio
1975    # branch with unlocked:false. Same slot, same idempotent-every-boot
1976    # contract as the two backfills above. See docs/runbook.md.
1977    backfill_ranking_method_from_tiers()
```

The forward reference to `_parse_per_format_json` (defined at `:3482`, below the
call site) is resolved at call time, and `init_db()` is invoked from
`server.py:407` at runtime, long after the module body has executed. No reordering
is needed.

### 2.4 Column comment (`:181`)

```python
    Column("ranking_method",  String),   # null | 'trio' | 'manual' | 'tiers'
```

becomes

```python
    # P0-1: written at the point of USE by the four save handlers (first-use
    # wins; 'anchor' upgradable) as well as by POST /api/ranking-method.
    Column("ranking_method",  String),   # null | 'trio' | 'manual' | 'tiers'
                                          #      | 'anchor' | 'quickset'
```

`'anchor'` (2026-07-10) and `'quickset'` (2026-07-12, #119) have shipped and are
both accepted by `set_ranking_method_route` (`server.py:6303`); the comment has been
stale since. Correcting it is in scope precisely because a comment contradicting
runtime behaviour is the A-33 class the handoff warns about.

---

## 3. Route layer — `backend/server.py`

`W1-BE` is the sole owner of this file for wave 1 (`hld.md` §4). The P0-1 edits are
five insertions and one comment; none of them is inside a region P0-3, P0-5 or P0-7
also touches.

### 3.1 Import

Current (`:148`, grep `set_ranking_method, get_ranking_method`):

```python
148    set_ranking_method, get_ranking_method,
```

After:

```python
148    set_ranking_method, get_ranking_method, set_ranking_method_if_unset,
```

`backfill_ranking_method_from_tiers` is **not** imported into `server.py` — it is
invoked from `_migrate_db()` inside `database.py`.

### 3.2 `_note_ranking_method` — the never-raises wrapper

**Placement:** immediately after `_invalidate_league_members_cache`
(`:5789-5798`, grep `def _invalidate_league_members_cache`) and before
`@app.route("/api/leaderboard"…)` (`:5801`). It must be defined before its first
call site (`post_rank3`, `:5876`) at import time — this placement satisfies that
with 78 lines to spare.

```python
def _note_ranking_method(sess: dict, method: str, *,
                         allow_over: tuple[str, ...] = ()) -> None:
    """P0-1: record the ranking method at the point of USE.

    NEVER RAISES. This is bookkeeping attached to a save that has already
    succeeded; a failure here must never turn a successful board save into a
    500. Every path out of this function is a return.

    Writes only where the column is unset (or in `allow_over`) — see
    database.set_ranking_method_if_unset for the first-use-wins contract and
    the re-lock hazard it exists to avoid.

    Drops the 60 s league-members cache ONLY on an actual write:
    `has_ranking_method` is one of the fields load_league_member_unlock_states
    projects, so leaguemates would otherwise see a stale badge for up to a
    minute. Mirrors what set_ranking_method_route already does at :6318-6326.
    A no-op write changes nothing leaguemates can see, so it must not pay the
    cache-drop cost — a save-heavy Quick Set walk would otherwise flush the
    league cache on every position.
    """
    try:
        wrote = set_ranking_method_if_unset(
            sess["user_id"], method, allow_over=allow_over)
    except Exception as db_err:
        log.warning("set_ranking_method_if_unset(%s) failed: %s", method, db_err)
        return
    if not wrote:
        return
    log.info("ranking-method noted at point of use for %s: %s",
             sess.get("user_id"), method)
    try:
        _lid = getattr(sess.get("league"), "league_id", None)
        if _lid:
            _invalidate_league_members_cache(_lid)
    except Exception:
        pass
```

**Contract details the build agent must not soften:**

| Property | Requirement |
|---|---|
| Never raises | `sess["user_id"]` is read **inside** the `try`, so even a malformed session object cannot propagate. There is no bare `raise`, no re-raise, and no `finally` that can throw. |
| Returns `None` | Callers never branch on the outcome. Do not "helpfully" return the bool — a caller acting on it would be encoding unlock policy in a route. |
| Cache-drop condition | **`wrote is True` only.** Not "always", not "when method changed". |
| No analytics | It must not call `record_event`. S-04: `ranking_method_changed` means *the user chose*, and firing it from an implicit write would corrupt a shipped funnel event. |
| Keyword-only `allow_over` | Forces the one exceptional call site to name itself at the call, so `grep -n 'allow_over' backend/server.py` returns exactly one line. |

### 3.3 `post_rank3` → `'trio'`

**Anchor** (`:5982-5985`, grep `record_event(trio_swipe) failed`):

```python
5982        except Exception as ev_err:
5983            log.warning("record_event(trio_swipe) failed: %s", ev_err)
5984
5985        # Invalidate cached trade-generation jobs — the user's ELO map just
```

**After:**

```python
5982        except Exception as ev_err:
5983            log.warning("record_event(trio_swipe) failed: %s", ev_err)
5984
5985        # P0-1: the trio path is the one that always DID unlock, but only
5986        # because null fell to the same branch. Recording it explicitly is
5987        # what makes null mean "no ranking action yet" instead of "trio".
5988        _note_ranking_method(sess, "trio")
5989
5990        # Invalidate cached trade-generation jobs — the user's ELO map just
```

It sits inside the handler's existing `try:` (opened at `:5909`), after
`service.record_ranking` has succeeded (`:5910`) and after the swipe has been
persisted — so a request that 400s at the stale-trio guard (`:5901-5907`) or
throws inside `record_ranking` leaves the column untouched (T-14).

### 3.4 `save_tiers_route` → `via` (`'tiers'` | `'quickset'`), with the upgrade

**Anchor** (`:7383-7387`, grep `via = (body.get("via")`):

```python
7383        via = (body.get("via")
7384               if body.get("via") in ("tiers", "quickset", "rookie_tiers",
7385                                      "rookie_quickset", "rookie_anchors")
7386               else "tiers")
7387        try:
```

**After:**

```python
7383        via = (body.get("via")
7384               if body.get("via") in ("tiers", "quickset", "rookie_tiers",
7385                                      "rookie_quickset", "rookie_anchors")
7386               else "tiers")
7387
7388        # P0-1: a COMPLETENESS-marking save is the one that should own the
7389        # unlock rule. A rookie-scope save deliberately does not complete a
7390        # position (see the tiers_saved comment above), and the rookie_* via
7391        # tags are subset boards — neither may pin the user to a rule they
7392        # never opted into. `allow_over=("anchor",)` is the single approved
7393        # upgrade (hld.md S-01): 'anchor' can never satisfy any unlock
7394        # branch, so letting it shadow a finished Quick Set board would be a
7395        # NEW failure created by this fix.
7396        if scope != "rookie" and via in ("tiers", "quickset"):
7397            _note_ranking_method(sess, via, allow_over=("anchor",))
7398
7399        try:
```

**Why here and not after `all_done` (`:7371`).** The guard depends on `scope` and
`via` only, not on `all_done` — the unlock ladder re-derives completeness from
`tiers_saved` on every progress read, so nothing is gained by waiting for it, and
`plan-p0-1.md` item 8's "move the `via` assignment a few lines up" is unnecessary
code motion (§11 D-1). Placing the call immediately after `via` is defined keeps
the diff to one inserted block and leaves the existing `record_event(tier_save)`
call byte-identical.

**Both guards are load-bearing and neither is redundant.** `via in ("tiers",
"quickset")` already excludes the three `rookie_*` tags; `scope != "rookie"`
additionally excludes a rookie-scoped save that sends `via: 'quickset'` — which is
reachable today (the route reads `scope` and `via` independently, and `scope` is
only non-`None` when `ranks.rookie_subset` is on). Dropping either guard leaves a
subset save able to pin a method.

### 3.5 `save_anchor_route` → `'anchor'`, `'anchors'` only

**Anchor** (`:7512-7515`, grep `_record_trends_snapshot(service, g_user_id, g_league, fmt, [player_id])`):

```python
7512        # #164 — feed the Trends tab (see _record_trends_snapshot).
7513        _record_trends_snapshot(service, g_user_id, g_league, fmt, [player_id])
7514
7515        tier = service.tier_for_elo(target_elo, player.position, fmt)
```

**After:**

```python
7512        # #164 — feed the Trends tab (see _record_trends_snapshot).
7513        _record_trends_snapshot(service, g_user_id, g_league, fmt, [player_id])
7514
7515        # P0-1: only the WIZARD marks a method. Answering an anchor inside
7516        # the Draft Room (_ANCHOR_VIA = ("anchors","draft_room"), :1283) is
7517        # not "I chose the Pick Anchor flow as my ranking method", and
7518        # 'anchor' is the branch that can never unlock — pinning it from a
7519        # draft-room tap would lock a user on a side quest.
7520        if via == "anchors":
7521            _note_ranking_method(sess, "anchor")
7522
7523        tier = service.tier_for_elo(target_elo, player.position, fmt)
```

`via` is already computed at `:7459` (`via = raw_via if raw_via in _ANCHOR_VIA else
"anchors"`), so the guard reads the route's own whitelisted value. Note the
fallback: an absent/unknown `via` resolves to `"anchors"` and therefore **does**
write `'anchor'` — that is correct, because the wizard is the default surface and
old binaries that send no `via` are wizard traffic.

### 3.6 `reorder_rankings` → `'manual'`, skipping `rookie_ranks`

**Anchor** (`:7886-7889`, grep `_record_trends_snapshot(service, g_user_id, g_league, fmt, ordered_ids)`):

```python
7886        # #164 — feed the Trends tab (see _record_trends_snapshot).
7887        _record_trends_snapshot(service, g_user_id, g_league, fmt, ordered_ids)
7888
7889        return jsonify({"ok": True, "count": len(ordered_ids), "scoring_format": fmt})
```

**After:**

```python
7886        # #164 — feed the Trends tab (see _record_trends_snapshot).
7887        _record_trends_snapshot(service, g_user_id, g_league, fmt, ordered_ids)
7888
7889        # P0-1: 'manual' unlocks UNCONDITIONALLY (:6163), so it is the most
7890        # consequential method string in the ladder — and via:'rookie_ranks'
7891        # is the editable consolidated ROOKIE board, a subset. Marking a
7892        # subset reorder 'manual' would hand a user a permanent unlock off a
7893        # rookies-only edit. Excluded.
7894        if body.get("via") != "rookie_ranks":
7895            _note_ranking_method(sess, "manual")
7896
7897        return jsonify({"ok": True, "count": len(ordered_ids), "scoring_format": fmt})
```

Note the guard is on the **raw body value**, not a whitelisted local: this route has
no `via` local, and `quickrank` (`:7844`) is a full-board flow that legitimately
writes `'manual'`. Only the literal `'rookie_ranks'` is excluded, per S-01's sibling
reasoning and `plan-p0-1.md` §2.2.

### 3.7 The unlock-ladder comment

**Anchor** (`:6155`, grep `# Unlock logic depends on the user's chosen ranking method`):

```python
6155    # Unlock logic depends on the user's chosen ranking method
```

**After:**

```python
6155    # Unlock logic depends on the user's ranking method. P0-1 (2026-08-09
6156    # audit): `ranking_method` is now written at the POINT OF USE by the four
6157    # save handlers as well as by the chooser, so NULL here means "no ranking
6158    # action taken since the P0-1 fix", not "never visited the chooser".
6159    # The ladder itself is UNCHANGED — 'anchor' still falls to the trio
6160    # branch (audit A-16) and 'manual' still unlocks unconditionally (A-17).
```

No logic on `:6163-6175` changes. This is the single most likely place for a future
reader to assume the fix lives, and the comment redirects them.

---

## 4. The write matrix, as concrete conditionals

### 4.1 One row per route

| Route | Handler | Inserted conditional | Method written |
|---|---|---|---|
| `POST /api/rank3` | `post_rank3` `:5876` | *(none — unconditional at that point in the `try`)* | `"trio"` |
| `POST /api/tiers/save` | `save_tiers_route` `:7240` | `if scope != "rookie" and via in ("tiers", "quickset"):` | `via` (`"tiers"` or `"quickset"`), `allow_over=("anchor",)` |
| `POST /api/anchor/save` | `save_anchor_route` `:7437` | `if via == "anchors":` | `"anchor"` |
| `POST /api/rankings/reorder` | `reorder_rankings` `:7802` | `if body.get("via") != "rookie_ranks":` | `"manual"` |

### 4.2 The three exclusions and the one exception, as truth

**Exclusion 1 — rookie-scope tier saves.** `scope == "rookie"` ⇒ no write. The route
itself states why completeness is the criterion (`:7362-7366`): *"`tiers_saved` /
`all_done` are COMPLETENESS markers, and a rookies-only save does not complete a
position."* A save that does not complete a position must not choose the rule that
measures completion.

**Exclusion 2 — `via: 'rookie_ranks'` reorders.** The consolidated rookie board is a
subset editor. `'manual'` unlocks **unconditionally** (`:6163`), so this is the one
exclusion whose absence would hand out unlocks rather than withhold them.

**Exclusion 3 — `via: 'draft_room'` anchors.** `_ANCHOR_VIA = ("anchors",
"draft_room")` (`:1283`). A draft-room anchor tap is in-draft valuation, not a
declaration of ranking method — and `'anchor'` is the branch that can never unlock,
so pinning it there is strictly harmful.

**The exception — `'anchor'` → `'quickset'`/`'tiers'` upgrade (S-01).** Only the
tiers/quickset call passes `allow_over`, and only with `("anchor",)`.

| Existing value | tiers/quickset save | rank3 | reorder | anchor save |
|---|---|---|---|---|
| `NULL` / `''` | **writes** `via` | **writes** `'trio'` | **writes** `'manual'` | **writes** `'anchor'` |
| `'anchor'` | **overwrites** → `via` | no-op | no-op | no-op |
| `'trio'` | no-op | no-op | no-op | no-op |
| `'manual'` | no-op | no-op | no-op | no-op |
| `'tiers'` / `'quickset'` | no-op | no-op | no-op | no-op |

Read the table as the whole policy: **the only overwrite anywhere in this design is
the `'anchor'` cell in the first column.** Every other non-empty value survives every
subsequent save. A rookie-scope save reaches none of these cells (exclusion 1), so
`'anchor'` is never upgraded by a subset save (T-12).

---

## 5. The `quickset-done` inversion (S-06)

The fixture, the seeder guard, and the capture were authored days ago **specifically
to preserve** this bug. The startup backfill rewrites the seed user at Flask boot
(`init_db()` runs at `server.py:407` on **every** boot, including the seeded UI-test
backend), so all of it moves in this commit or the seeder starts refusing the only
coherent post-fix configuration.

### 5.1 The target state

`qa_quickset` post-fix is the shape a real backfilled production user has:
`ranking_method = 'quickset'`, `unlocked_formats = ["1qb_ppr","sf_tep"]`,
`tiers_saved` complete in both formats, **zero** trio swipes, `unlocked:true` from
`/api/rankings/progress` — and, because the floor is pre-seeded, **no**
`ranking_complete_first_time` on first poll. Seeding the floor is what makes the
UI-test backend behave identically to prod after the backfill; without it the
seeded backend would fire the event and the fan-out on the first `/progress` call
and diverge from every prod user in the cohort.

### 5.2 `backend/tests/fixtures/profiles/quickset-done.json`

Two value changes plus a rewritten `description`:

```json
  "app_user": {
    "username": "qa_quickset",
    "user_id": "900000000000000001",
    "unlocked": true,
    "ranking_method": "quickset",
```

`description` (replacing the current one at `:4`) states the post-fix meaning and
keeps one sentence of history:

> THE FIXED QUICK-SET STATE (mobile UX audit P0-1, capture request #8). `qa_quickset`
> has finished Quick Set across all four positions in both formats — `tiers_saved` is
> QB/RB/WR/TE and `tier_overrides` holds a real 96-player board — with ZERO trio
> interactions. `ranking_method` is `'quickset'` and `unlocked_formats` is pre-seeded,
> which is exactly the shape the P0-1 startup backfill produces in production: the
> ring reads 4/4, `/api/rankings/progress` answers `unlocked:true`, the push primer
> is armed, and the first-unlock fan-out is already spent so it does not fire
> retroactively. HISTORY: until the P0-1 fix this profile existed to reproduce the
> 4/4-BUT-LOCKED contradiction (`ranking_method` NULL → the trio branch → 0 of 40
> interactions → `unlocked:false`); see `docs/plans/audit-p0-remediation/`. Also the
> only profile that seeds `tier_overrides`, so it doubles as the populated-profile
> fixture under `flags/profiles-on`.

### 5.3 `backend/tests/fixtures/seed_ui_test_db.py` — three edits, not one

`plan-p0-1.md` item 13 names only `_validate_quickset`. Setting `unlocked: true` on
a profile with `rankings: null` trips **two other places** that were written on the
assumption that only a trio board can unlock. All three move together (§11 D-2).

**(a) `_validate_profile` `:278-280`** — the "unlocked ⇒ rankings" precondition:

```python
278    rankings = app.get("rankings")
279    if app.get("unlocked") and not rankings:
280        _refuse("unlocked:true requires a rankings block")
```

becomes

```python
    rankings = app.get("rankings")
    if app.get("unlocked") and not rankings:
        # P0-1: a COMPLETE Quick Set board is now a legitimate basis for
        # unlocked:true — that is the whole fix. A trio block is no longer the
        # only way in; an all-four-position quickset block is the other.
        qs = app.get("quickset") or {}
        qs_positions = set(qs.get("positions") or POSITIONS) if qs else set()
        if qs_positions < set(POSITIONS):
            _refuse("unlocked:true requires a rankings block, or a quickset "
                    "block covering all four positions (audit P0-1)")
```

**(b) `World.unlocked_formats` `:688-692`** — currently indexes the rankings block
unconditionally and would raise `TypeError` on this profile:

```python
688    def unlocked_formats(self) -> list[str]:
689        app = self.profile["app_user"]
690        if not app.get("unlocked"):
691            return []
692        return list(self.app_rankings()["formats"])
```

becomes

```python
    def unlocked_formats(self) -> list[str]:
        """Formats to pre-seed into users.unlocked_formats.

        P0-1: a quickset-only profile has no rankings block, and its unlocked
        formats are the formats its Quick Set board covers. Pre-seeding them is
        also what reproduces the production backfill's fan-out suppression
        (hld.md S-03) in the UI-test backend.
        """
        app = self.profile["app_user"]
        if not app.get("unlocked"):
            return []
        r = self.app_rankings()
        if r:
            return list(r["formats"])
        qs = self.quickset()
        return list(qs["formats"]) if qs else list(db.SCORING_FORMATS)
```

**(c) `_validate_quickset` `:314-368`** — invert THE guard. New docstring and body
tail:

```python
def _validate_quickset(app: dict, _refuse) -> None:
    """`app_user.ranking_method` + `app_user.quickset` (audit P0-1).

    Quick Set commits a board through `/api/tiers/save`, which writes
    `tiers_saved` + `tier_overrides` and never touches the trio counter. Until
    the P0-1 fix, `ranking_method` stayed NULL (the default route never visits
    the chooser that wrote it), `/api/rankings/progress` fell to the trio
    branch, and the user read 4/4 on the ring while `unlocked` was false.

    POST-FIX that state is unreachable, and the guard is inverted. The server
    writes the method at the point of use, and the startup backfill
    (database.backfill_ranking_method_from_tiers) tags any pre-fix NULL row
    with 'quickset' at Flask boot — including this seeded one. So an
    all-four-position Quick Set profile with `unlocked:false` no longer
    describes anything the server can produce, REGARDLESS of ranking_method,
    and is refused rather than allowed to rot. There is no `ranking_method:
    null` escape hatch any more; the backfill closes it at boot.
    """
    # …the method-validity check at :332-336 is UNCHANGED…
    # …the quickset shape checks at :338-356 are UNCHANGED…

    # THE guard, inverted (audit P0-1). No longer keyed on `ranking_method`.
    if not app.get("unlocked") and set(positions) >= set(POSITIONS):
        _refuse(
            "an all-four-position quickset board with unlocked:false is "
            "incoherent post-P0-1 — /api/rankings/progress answers "
            "unlocked:true for it, and the startup backfill writes "
            "ranking_method='quickset' at Flask boot even if the profile "
            "leaves it null. Set unlocked:true."
        )
```

The `resolved = None if method is _RANKING_METHOD_DEFAULT else method` line and the
`resolved in ("tiers","quickset","manual")` condition are **deleted** — the new
guard is method-independent, which is the point.

### 5.4 `backend/tests/test_seed_ui_test_db.py` — two tests rewritten

These assert the pre-fix fixture and the pre-fix guard. They cannot "stay green"
(§11 D-3); they are inverted in this commit.

**(a) `test_quickset_done_is_tier_saved_but_has_no_ranking_method` (`:845`)** →
rename to `test_quickset_done_is_tier_saved_and_unlocked` and flip three
assertions:

```python
    assert row["ranking_method"] == "quickset"
    assert sorted(json.loads(row["unlocked_formats"] or "[]")) == ["1qb_ppr", "sf_tep"]
    assert swipes == 0          # unchanged — the whole point is zero trios
```

Docstring rewritten to describe the fixed contract and to name the pre-seeded floor
as the fan-out suppression. `tiers_saved` / `tier_overrides` assertions unchanged.

**(b) `test_quickset_with_an_unlocking_method_is_refused` (`:898`)** → replace with
the inverted guard's test:

```python
def test_quickset_all_four_with_unlocked_false_is_refused(tmp_path):
    """Post-P0-1 the incoherent profile is the LOCKED one: the server answers
    unlocked:true for a complete Quick Set board, and the startup backfill
    writes ranking_method='quickset' at boot regardless of what the profile
    says. Refused rather than allowed to rot."""
    with pytest.raises(SeederError) as e:
        seed_profile(
            _mutated_profile(tmp_path, "quickset-done",
                             lambda d: d["app_user"].update(unlocked=False)),
            out_dir=tmp_path, seed=SEED, now=FIXED_NOW)
    assert e.value.code == EXIT_REFUSED
    assert "unlocked:true" in str(e.value)
```

Add one positive twin, because the `ranking_method: null` path must stay *seedable*
(the backfill, not the seeder, is what fixes it) while the locked claim must not:

```python
def test_quickset_done_may_leave_ranking_method_null(tmp_path):
    """The seeder does not require the method — the startup backfill writes it.
    Only the unlocked:false CLAIM is refused."""
    seed_profile(
        _mutated_profile(tmp_path, "quickset-done",
                         lambda d: d["app_user"].update(ranking_method=None)),
        out_dir=tmp_path, seed=SEED, now=FIXED_NOW)
```

**Unchanged and must stay green:** `test_quickset_done_overrides_are_the_public_profile_source`
(`:879` — the manifest counts `quickset_tier_overrides == 96` /
`quickset_positions_saved == 8` are untouched by this change),
`test_unknown_ranking_method_is_refused` (`:909` — the method-validity check
survives), `test_existing_profiles_keep_their_trio_method` (`:919`).

### 5.5 One expected fixture-shape delta, stated so it is not a surprise

`_seed_db` `:1093-1099` appends the app user to `ranked_uids` when
`app.get("unlocked")`, so the post-inversion `quickset-done` gains
`member_rankings` rows for `qa_quickset` in both formats (`rankings` is `None`, so
the `fmts` fallback at `:1098` is `db.SCORING_FORMATS`). **Leave that code alone.**
It is more faithful, not less: in production `/api/tiers/save` publishes
`member_rankings` on every save (`server.py:7331-7345`), so the pre-fix fixture was
already understating the user's footprint. No test asserts `member_ranking_rows` for
this profile (the two that assert member_rankings counts are on `standard`,
`test_seed_ui_test_db.py:160-172`). The capture is re-run regardless (§8.2), which
is where this is eyeballed.

---

## 6. Mobile — one `testID`

`mobile/src/screens/RankScreen.tsx:685-687`, grep `styles.unlockedBanner`:

```tsx
685        {isUnlockedEverywhere && (
686          <View style={styles.unlockedBanner}>
687            <View style={styles.bannerTick} />
```

becomes

```tsx
        {isUnlockedEverywhere && (
          <View testID="rank.unlocked-banner" style={styles.unlockedBanner}>
            <View style={styles.bannerTick} />
```

- **No visual change, no logic change.** `isUnlockedEverywhere` is
  `progress?.unlocked ?? false` (`:356`), the same boolean that gates `pushEnabled`
  in `RootNav.tsx:267`. That identity is what makes the id an honest proxy for the
  push gate (the SpringBoard alert is not Maestro-assertable — waiver W-1).
- **Why an id and not the copy.** The banner's text forks on
  `ux.outlook_inline_default` (`:109`, `:691-694`): *"Your board now prices your
  trades — see the Acquire tab"* vs *"Trade Finder unlocked — check the Acquire
  tab"*. A full-match text regex (law 1) would bind the flow to a flag value.
  `capture/trios@near-unlock.yaml`'s header already files this exact gap ("The
  banner carries no testID … Flagged for the P4 testID sweep").
- **Lint.** Plain string literal ⇒ `mobile/scripts/testid-lint.sh` finds it by
  source grep over `mobile/src`. **No `testid-lint-allow.txt` entry** (law 4 covers
  template literals only) and **no `mobile/src/components/CLAUDE.md` edit** — the
  script never opens that file (`hld.md` §10.3). The registry row is W3-DOCS's, in
  wave 3.
- `cd mobile && npx tsc --noEmit` must be clean. **Never run `npm install`** —
  `mobile/node_modules` is a symlink.

---

## 7. Backend tests — `test_ranking_method_point_of_use.py`

New file, `backend/tests/test_ranking_method_point_of_use.py`. Pattern of record:
`backend/tests/test_rookie_scope.py` (in-memory SQLite via
`monkeypatch/patch.object(db_module, "engine", engine)`, an injected fake
`RankingService`, a real Flask test client with a seeded `server._sessions` entry
and an `X-Session-Token` header).

### 7.1 Fixtures

**`db`** — engine only, for the helper and backfill unit tests:

```python
@pytest.fixture()
def db(monkeypatch):
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)
    with engine.begin() as conn:
        conn.execute(users_table.insert().values(
            sleeper_user_id=UID, created_at="2026-08-10T00:00:00+00:00"))
    return engine
```

**`client`** — route harness. Copy `test_rookie_scope.py:411-465` and change four
things:

1. Seed `users` + one `leagues` row + enough `players` rows for the fake service's
   pool (the anchor route needs `service.apply_anchor` to return a player object
   with `.position`).
2. The session dict gains **`"verified": True`** so `_gate_unverified_read` returns
   `None` at `server.py:2442` and `/api/rankings/progress` is reachable.
   (`_verified_read_denial` only denies when an unverified session collides with a
   verified controller; setting `verified` makes that unreachable and keeps the test
   about P0-1.)
3. The fake service additionally implements what `/api/rankings/progress` calls:
   `POSITION_THRESHOLDS = {"QB": 10, "RB": 10, "WR": 10, "TE": 10}` and
   `get_progress(position=…) -> {"interaction_count": N, …}` backed by a mutable
   per-position counter the test can set; plus `apply_anchor`, `apply_reorder`,
   `record_ranking`, `has_player`, `tier_for_elo`, `get_rankings`, `_elo_overrides`.
4. `patch.object(server, "is_enabled", lambda k: k in flags)` with `flags` a
   per-test set — `{"ranks.rookie_subset"}` for T-7, empty otherwise.

**Helper** `_method(uid=UID) -> str | None` reading the column directly, and
`_save_tiers(c, position, **body)` / `_post(c, path, body)` thin wrappers with the
`X-Session-Token` header, so each case below is 3-5 lines.

### 7.2 Point-of-use writes

| # | Arrange | Act | Assert |
|---|---|---|---|
| **T-1** | `users.ranking_method` NULL | `POST /api/tiers/save {position:'RB', tiers:{…}, via:'quickset'}` → 200 | `_method() == 'quickset'` |
| **T-2** | NULL | same, **no `via` key** | `_method() == 'tiers'` — the route's own default (`server.py:7383-7386`), proving the write reuses the whitelisted local and does not re-read the body |
| **T-3** | NULL | `POST /api/rank3 {ranked:[a,b,c]}` → 200 | `_method() == 'trio'` |
| **T-4** | NULL | `POST /api/rankings/reorder {position:'RB', ordered_ids:[a,b]}` → 200 | `_method() == 'manual'` |
| **T-5** | NULL | `POST /api/anchor/save {player_id, anchor:'2_firsts', via:'anchors'}` → 200 | `_method() == 'anchor'` |
| **T-5b** | NULL | same, **no `via`** | `_method() == 'anchor'` — the `_ANCHOR_VIA` fallback at `:7459` is wizard traffic (old binaries) |
| **T-6** | NULL | `POST /api/anchor/save {…, via:'draft_room'}` → 200 | `_method() is None` |
| **T-7** | NULL, flag `ranks.rookie_subset` **on** | `POST /api/tiers/save {scope:'rookie', via:'rookie_quickset', …}` → 200 | `_method() is None` |
| **T-7b** | NULL, flag **on** | `POST /api/tiers/save {scope:'rookie', via:'quickset', …}` → 200 | `_method() is None` — proves the `scope != "rookie"` guard is not redundant with the `via` whitelist |
| **T-8** | NULL | `POST /api/rankings/reorder {via:'rookie_ranks', …}` → 200 | `_method() is None` |
| **T-8b** | NULL | `POST /api/rankings/reorder {via:'quickrank', …}` → 200 | `_method() == 'manual'` — Quick Rank is a full-board flow and must **not** be excluded |

### 7.3 Idempotence / precedence (first-use wins)

| # | Arrange | Act | Assert |
|---|---|---|---|
| **T-9** | method `'trio'` | tiers/save `via:'quickset'` | **still `'trio'`** — the re-lock guard, and the single most important assertion in the file |
| **T-10** | method `'manual'` | `POST /api/rank3` | still `'manual'` |
| **T-11** | method `'anchor'` | tiers/save `via:'quickset'` | **`'quickset'`** — the one approved upgrade (S-01) |
| **T-11b** | method `'anchor'` | tiers/save with **no `via`** | `'tiers'` — the upgrade is not `via`-specific |
| **T-11c** | method `'anchor'` | `POST /api/rank3` | still `'anchor'` — `allow_over` is passed by the tiers call **only** |
| **T-12** | method `'anchor'`, flag on | tiers/save `scope:'rookie'` | still `'anchor'` — a subset save never upgrades |
| **T-13** | NULL | two identical tiers/saves | after both, `'quickset'`; second call's `set_ranking_method_if_unset` returns `False` (assert via `unittest.mock.patch.object(server, "_invalidate_league_members_cache")` call count == 1 across the two requests — this is also the cache-drop-only-on-write assertion) |
| **T-14** | NULL | tiers/save with `position:'XX'` → **400** | `_method() is None` — a failed save leaves no method |
| **T-14b** | NULL | `POST /api/rank3 {ranked:[a]}` → **400** (fewer than 2 ids) | `_method() is None` |

### 7.4 Helper-level unit tests (no route)

| # | Arrange | Act | Assert |
|---|---|---|---|
| **T-H1** | `db` fixture, method NULL | `set_ranking_method_if_unset(UID, "trio")` | returns `True`; column `'trio'` |
| **T-H2** | method `'trio'` | same call again | returns `False`; column unchanged |
| **T-H3** | method `''` | `set_ranking_method_if_unset(UID, "tiers")` | returns `True` — empty string counts as unset |
| **T-H4** | method `'anchor'` | `set_ranking_method_if_unset(UID, "quickset", allow_over=("anchor",))` | returns `True`; column `'quickset'` |
| **T-H5** | no `users` row for `"ghost"` | `set_ranking_method_if_unset("ghost", "trio")` | returns `False`; **no row created** (`SELECT count(*) FROM users` unchanged) |
| **T-H6** | method NULL | `set_ranking_method_if_unset(UID, "vibes")` | returns `False`; column still NULL — an unknown method never lands |

### 7.5 Acceptance, end to end

| # | Arrange | Act | Assert |
|---|---|---|---|
| **T-15** | Fresh user: method NULL, `unlocked_formats` NULL, fake service reporting `interaction_count == 0` for all four positions | Four `POST /api/tiers/save` (QB, RB, WR, TE) with `via:'quickset'`, then `GET /api/rankings/progress` | `unlocked is True` **and** `ranking_method == 'quickset'` **and** `QB == RB == WR == TE == 0`. *This is the machine-checkable half of the acceptance criterion: unlocked with zero trio interactions.* |
| **T-16** | Same, but only QB/RB/WR saved | `GET /api/rankings/progress` | `unlocked is False` — the fix must not unlock a partial board |
| **T-17** | T-15's state | `GET /api/rankings/progress` **twice** | `ranking_complete_first_time` appears in `user_events` **exactly once** (`was_first` gating, `server.py:6228`) |
| **T-17b** | T-15's state, then a second `GET` | — | `_send_typed_push` (patched) called only in the first request's fan-out, never in the second |

### 7.6 Backfill

All against the `db` fixture, calling `db_module.backfill_ranking_method_from_tiers()`
directly.

| # | Arrange (`users` row) | Assert after one run |
|---|---|---|
| **T-18** | `tiers_saved = {"1qb_ppr": ["QB","RB","WR","TE"]}`, method NULL | method `'quickset'`; **`unlocked_formats == ["1qb_ppr"]`**; return value `1` |
| **T-18b** | complete in **both** formats, method NULL | `unlocked_formats == ["1qb_ppr","sf_tep"]` (order = `SCORING_FORMATS`) |
| **T-18c** | complete in `sf_tep` only, `unlocked_formats` already `["1qb_ppr"]` | `unlocked_formats == ["1qb_ppr","sf_tep"]` — merge, never clobber |
| **T-19** | `tiers_saved = {"1qb_ppr": ["QB","RB"]}`, method NULL | **method still NULL**, `unlocked_formats` untouched — the narrow cohort, which is what stops a mixed-method user being re-locked |
| **T-20** | method `'trio'`, complete tier board | still `'trio'`; `unlocked_formats` untouched |
| **T-21** | T-18's row, backfill run **twice** | second call returns `0`; no value churn (`unlocked_formats` still one entry, method still `'quickset'`) |
| **T-22** | four rows, method NULL, `tiers_saved` ∈ {`NULL`, `''`, `'{}'`, `'not json'`, `'["QB","RB","WR","TE"]'` (legacy list shape)} | no crash; **no writes**; return `0` |
| **T-22b** | method `''`, complete board | method `'quickset'` — the empty-string cohort matches the helper's unset predicate |

**T-24 — the suppression itself (the S-03 assertion; add it, it is not in the
plan's T-list).** Arrange a route-harness user whose row was produced by the
backfill (complete board, method `'quickset'`, `unlocked_formats` pre-seeded), patch
`server._send_typed_push` and count `user_events`, then `GET /api/rankings/progress`:

- `unlocked is True`
- `_send_typed_push` **never called**
- **no** `ranking_complete_first_time` row in `user_events`

And its control twin, **T-24b**: the identical row with `unlocked_formats` left
`'[]'` **does** produce exactly one `ranking_complete_first_time`. Without the
control, T-24 would pass on a build where the whole fan-out was accidentally dead.

### 7.7 Regression guard

| # | Arrange | Act | Assert |
|---|---|---|---|
| **T-23** | method `'trio'`, all four positions at `interaction_count == 10`, `unlocked_formats` already `["1qb_ppr"]` | one tiers/save (which is a no-op on the method, T-9), then `GET /api/rankings/progress` | still `unlocked: True` — the monotonic floor at `:6188` still carries them. *Nobody loses an unlock.* |

### 7.8 Suites that must stay green, unchanged

`test_test_users.py`, `test_account_first.py`, `test_accounts.py`,
`test_verified_sessions.py`, `test_verified_reads.py`, `test_trio_cross_position.py`,
`test_rookie_scope.py`, `test_deck_first_session.py`, `test_analytics_p0.py`,
`test_rank_action_weighting.py`. `test_seed_ui_test_db.py` is green **after** the
§5.4 rewrites and not before.

Command: `python3 -m pytest backend/tests/ -q` (must be green for commit 2 in
isolation — `hld.md` §3).

---

## 8. Maestro delta

### 8.1 New flow — `mobile/.maestro/flows/p0-1-quickset-unlock.yaml`

**Why one flow and not two.** The acceptance criterion is *4/4 **and**
`unlocked:true` **together***. Two flows could each pass on different sessions and
never prove simultaneity.

**Header** (law 16 — `# flags:` names a resolved fixture under
`backend/tests/fixtures/flags/`):

```yaml
appId: com.fantasytradefinder.app
# tc: TC-P0-1-QUICKSET-UNLOCK
# profile: quickset-done
# flags: release
# source: backend/server.py get_rankings_progress, mobile/src/screens/RankScreen.tsx,
#         mobile/src/screens/LeagueScreen.tsx, mobile/src/navigation/RootNav.tsx:267
tags: [p0-1, unlock]
```

Plus a header comment block stating: the profile is the **post-inversion**
`quickset-done` (§5); the flow **fails on the unfixed tree** at the banner
assertion, and a pre-fix control run is required (R5) because a test that never
observed the bug proves nothing; and the push-permission alert is deliberately not
asserted (waiver W-1) with the proxy chain `rank.unlocked-banner` ⇔
`progress.unlocked` ⇔ `pushEnabled` (`RootNav.tsx:267`) spelled out.

**Step outline** — every step's law is named:

| # | Step | Law |
|---|---|---|
| 1 | `launchApp: {clearState: true, clearKeychain: true, stopApp: true}` | **6** — the react-query cache is persisted; `RootNav`'s progress query would answer from disk on a warm launch and the run would prove nothing about the server |
| 2 | `extendedWaitUntil: {visible: {id: "signin.username-input"}, timeout: 15000}` | — |
| 3 | `retry: {maxRetries: 2, commands: [tapOn signin.username-input, eraseText, inputText "qa_quickset", assertVisible text ".*qa_quickset.*", tapOn signin.continue-btn, extendedWaitUntil id "leagues.row.*" 30000]}` | **10** (assert the typed username; `eraseText` first makes the retry idempotent) + **1** (full-match regex) |
| 4 | `tapOn: {id: "leagues.row.*"}` | selector is profile-agnostic, per `capture/trios@near-unlock.yaml`'s note |
| 5 | `extendedWaitUntil: {visible: {id: "tab.trades"}, timeout: 60000}` | authed tree is up |
| 6 | `extendedWaitUntil: {visible: {id: "rank.more-ways"}, timeout: 60000}` then `waitForAnimationToEnd` | **8** — #244 launch routing steals early tab taps; `rank.more-ways` is the Rank surface's own header control, so its presence proves routing already ran |
| 7 | `tapOn: {id: "tab.league"}` → `extendedWaitUntil league-summary.league-home 30000` → `tapOn: {id: "league-summary.league-home"}` → `extendedWaitUntil league.hero 30000` | the ordinary pushed path, matching `capture/league@quickset-done.yaml` |
| 8 | `scrollUntilVisible: {element: {id: "league.progress-module"}, direction: DOWN, visibilityPercentage: 100, timeout: 30000}` | **2** — and **no `centerElement`**: the module is a tall card and centring overshot/cropped it in that capture's RUN-2 |
| 9 | **Assertion A** `assertVisible: {text: ".*4 of 4 positions ranked.*"}` | **3** — `PositionsRing`'s wrapper is `accessible`, which collapses its subtree on iOS, so the in-ring "4/4" numeral is invisible to Maestro; the accessibilityLabel is the only matchable string (and the more restyle-stable one). **1** — wrapped in `.*` |
| 10 | `takeScreenshot: p0-1__ring-4-4` | evidence for the ledger; eyeballed (**23**) |
| 11 | `tapOn: {id: "tab.rank"}` → `extendedWaitUntil rank.more-ways 20000` → `tapOn: {id: "rank.more-ways"}` → `extendedWaitUntil rankmenu.trios 10000` → `tapOn: {id: "rankmenu.trios"}` → `extendedWaitUntil trios.card.a 40000` | the only reachable path to `RankScreen` under release flags (`ux.rank_tab_destination` on ⇒ the header control opens the RankMenu sheet); verbatim from `capture/trios@near-unlock.yaml:88-104` |
| 12 | **Assertion B-negative** `assertNotVisible: {id: "rank.unlock-payoff"}` | that element renders **only** while `unlockCopyOn && !isUnlockedEverywhere` (`RankScreen.tsx:518`), and `ux.outlook_inline_default` is ON in the release fixture — so it is the locked state's fingerprint. Because law **2** means off-screen ScrollView children still count as visible, `assertNotVisible` here is a **strong** claim: absent from the hierarchy entirely |
| 13 | `scrollUntilVisible: {element: {id: "rank.unlocked-banner"}, direction: DOWN, visibilityPercentage: 100, timeout: 20000}` | **2** — the banner is the last child of the screen's `ScrollView`, below the Skip actions row; without the forced scroll the shutter would frame the trio cards |
| 14 | **Assertion B** `assertVisible: {id: "rank.unlocked-banner"}` | the id from §6; **not** the copy (laws **1** + the `ux.outlook_inline_default` fork) |
| 15 | `waitForAnimationToEnd` | safe here — **5** forbids it on an `ActivityIndicator`, and this is settled static content, not a spinner |
| 16 | `takeScreenshot: p0-1__quickset-unlocked` | **23** — eyeball it; a green run is not a good capture |

**No injections** (`fail_next` / `latency`): every state asserted is the fixture's
own resting answer, so laws **11-13** do not apply and there is nothing to leak into
a later leg (law 13's ordering hazard is absent by construction).

**No `openLink`** (law **17**) and no launch-argument entry — the flow walks the
real user path, which is the point of the finding.

### 8.2 Amended capture — `mobile/.maestro/capture/league@quickset-done.yaml`

The file's entire 40-line header argues the 4/4-but-locked contradiction. Post-fix
that contradiction is gone and the capture would keep passing under a name asserting
a bug that no longer exists (S-07: re-captured, not preserved — history lives in
git).

1. **Rename in three places** — `# captures:`, `# interactive-stop:`, and the
   `takeScreenshot:` at `:150`: `progress-ring--4-4-locked` →
   `progress-ring--4-4-unlocked` (the shutter name is
   `league__progress-ring--4-4-unlocked`).
2. **Rewrite the header** (`:9-45`): the profile now shows a Quick Set user whose
   ring reads 4/4 **and** whose account is unlocked, which is what the P0-1 fix
   produces; keep two sentences of history pointing at
   `docs/plans/audit-p0-remediation/`. The paragraph at `:26-29` claiming *"The
   seeder REFUSES a profile that would un-reproduce this"* is now false in its old
   direction and must be restated as the inverted guard (§5.3c).
3. **Keep** `assertVisible: {text: ".*4 of 4 positions ranked.*"}` (`:141-142`)
   verbatim — still correct, still the accessibilityLabel.
4. **`league.works-now` (`:143-148`) — re-justify or drop.** It renders while mutual
   matches are zero (`matches_seed {mutual: 0, awaiting: 0}`), which is still true,
   so the step still passes — but its stated reason ("pins the frame to the locked
   reading") becomes false. Replace the comment with the honest one (it pins the
   frame to a zero-match league, which is why `moduleVisible`'s second clause keeps
   the progress module on screen at a complete ring) or delete the step. **Do not
   leave the comment.**
5. **Re-run is unconditional** — the frame is renamed, so `screen-freshness.sh`'s
   opinion does not matter here.

### 8.3 Smoke-suite crossing surfaces

`flows/smoke/04-tiers.yaml` (tier-save path), `06-trades-deck.yaml` (unlock-gated
deck), `09-league.yaml` (the ring). All expected unchanged and green: none of their
profiles completes a four-position Quick Set board, so `unlocked` does not move for
them. **Verified in the tier-1 run, not assumed** (`hld.md` §4 W3-QA owns the run;
this LLD owns the expectation).

---

## 9. Build order inside the commit

Every step is verifiable on its own; the commit lands as one unit (S-06).

1. `database.py` — helper (§2.1), backfill (§2.2), `_migrate_db` call (§2.3),
   column comment (§2.4).
2. `pytest backend/tests/test_ranking_method_point_of_use.py -k "T_H or backfill"`
   green (helper + backfill are testable before any route edit).
3. `server.py` — import (§3.1), `_note_ranking_method` (§3.2), the four call sites
   (§3.3-3.6), the ladder comment (§3.7). **Re-grep every anchor first** (R1: the
   plan's line numbers were taken at `ab9368f` and sibling agents are editing this
   file in the same wave).
4. Full new test file green.
5. Fixture + seeder inversion (§5.2, §5.3) and the two `test_seed_ui_test_db.py`
   rewrites (§5.4).
6. `python3 -m pytest backend/tests/ -q` — **whole suite** green.
7. `RankScreen.tsx` testID (§6) → `cd mobile && npx tsc --noEmit` →
   `bash mobile/scripts/testid-lint.sh`.
8. Maestro flow + capture amendment (§8).
9. **Pre-fix control run** (R5): stash the `server.py`/`database.py` hunks, seed the
   *pre*-inversion fixture, run the new flow, confirm it **fails** at step 14. Then
   restore and run it green. Record both in the evidence the scope block requires.

---

## 10. What this LLD deliberately does not do

- **Does not change the unlock ladder** (`server.py:6163-6175`). `'anchor'` still
  falls to the trio branch (**A-16**); `'manual'` still unlocks unconditionally
  (**A-17**). Both are out of scope (`hld.md` §9 LLD-1 "must not").
- **Does not add a feature flag** (S-04). A flag's OFF position would be the known
  bug.
- **Does not add an analytics event** (S-04). `ranking_method_changed` means "the
  user chose"; the implicit writes are not choices.
- **Does not touch any `docs/**` or `living-memory/**` file** (`hld.md` §4 W3-DOCS).
- **Does not touch `mobile/src/components/CLAUDE.md`** (§10.3).
- **Does not create the pre-merge experiment check** — that is an operator step
  (`prd-p0-1.md` §7).
- **Does not preserve the pre-fix capture PNG.** `plan-p0-1.md` Q6 proposed a
  `--historic` copy; S-07 settles it the other way. Git history is the archive.

---

## 11. Deviations

Four, all surfaced rather than absorbed. **None contradicts an `hld.md` §2 row.**

**D-1 — `plan-p0-1.md` item 8's "move the `via` assignment a few lines up" is
unnecessary.** The insertion goes *after* the existing `via` assignment
(`server.py:7386`) rather than after `all_done` (`:7371`), because the guard depends
on `scope` and `via` only. No code motion, a smaller diff, and the existing
`record_event(tier_save)` block stays byte-identical. HLD-neutral (§4 W1-BE says
only "inserts in … `save_tiers_route`").

**D-2 — the seeder inversion is THREE edits, not one; and the fixture cannot set
`unlocked: true` without them.** `plan-p0-1.md` item 13 and `scope-p0-1.md` §3 name
only `_validate_quickset`. Verified in this worktree:
`seed_ui_test_db.py:278-280` refuses `unlocked:true` without a rankings block, and
`World.unlocked_formats` (`:688-692`) does `list(self.app_rankings()["formats"])`,
which raises `TypeError` when `rankings` is `null`. `quickset-done` has
`"rankings": null` **by design** — zero trio interactions is the fixture's whole
point, and adding a rankings block would destroy both the fixture and T-15's
"all counts still 0" proof. §5.3 therefore edits all three sites. This is a
*completion* of S-06, not a departure from it.

**D-3 — `scope-p0-1.md` §3 lists `test_seed_ui_test_db.py` under "must stay green";
two of its tests must be rewritten instead.** `test_quickset_done_is_tier_saved_but_has_no_ranking_method`
(`:845`) asserts `ranking_method is None` and `unlocked_formats == []`;
`test_quickset_with_an_unlocking_method_is_refused` (`:898`, parametrized over
`tiers`/`quickset`/`manual`) asserts the **old** guard. Both encode the bug. §5.4
inverts them in this commit, which is exactly the S-06 posture applied to the tests
that guard the fixture. The other three quickset tests in that file are genuinely
untouched.

**D-4 — two test cases added beyond the plan's T-1…T-23.** **T-24 / T-24b** assert
the S-03 suppression directly (no `ranking_complete_first_time`, no
`_send_typed_push`, plus the control that proves the fan-out is not simply dead).
`hld.md` §9 LLD-1 requires this LLD to specify "the exact `unlocked_formats`
pre-seed that suppresses the fan-out — this is the one part of the backfill the plan
describes only as an option"; specifying it without pinning it in a test would leave
the batch's only data-mutating behaviour unverified. The smaller additions (T-5b,
T-7b, T-8b, T-11b, T-11c, T-14b, T-18b/c, T-22b, T-H1…T-H6) each close a branch the
numbered list left unpinned.

**Not a deviation, recorded for the reader:** `hld.md` §10.3 already removed
`plan-p0-1.md` item 15 (the `mobile/src/components/CLAUDE.md` registration claimed
to be a `testid-lint.sh` dependency). §6 follows the HLD; the plan's claim is false.
Likewise the plan's `D-011`/`G-013` ids are stale — `hld.md` §10.4 assigns
**D-025**, and W3-DOCS allocates it.
