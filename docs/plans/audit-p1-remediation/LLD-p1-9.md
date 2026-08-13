# LLD — P1-9 · Quality-gated `trade_found` push (audit A-18)

> **Status:** DESIGN ONLY — no source file is changed by this document.
> **Worktree:** `/Users/teresadickens/Documents/Claude/Projects/ftf-p1-remediation`,
> branch `p1-remediation-2026-08-11` @ `ab9368f` (== `origin/main` at authoring time).
> **Inputs:** [`plan-p1-9.md`](plan-p1-9.md), [`scope-p1-9.md`](scope-p1-9.md),
> [`HLD-p1.md`](HLD-p1.md) (wave B / owner **B2**), [`DECISIONS-p1.md`](DECISIONS-p1.md).
> **Companion:** [`PRD-p1-9.md`](PRD-p1-9.md) — acceptance criteria, Maestro specs, rollout.
> **Every `file:line` below was read first-hand in this worktree at `ab9368f`.** Where the
> plan and the code disagree, the code is cited and the plan is corrected in
> [§1](#1-corrections-to-the-plan).
>
> **This document invents no new design.** It converts `plan-p1-9.md`'s design into exact
> diff sites and evaluable predicates, corrects twelve places where the plan is wrong or
> silent against the code, and resolves nothing that belongs to the operator — every
> product, copy, privacy and threshold call stays in [§8](#8-parameter-table--operator-decisions).

## Contents

- [0. Position in the round](#0-position-in-the-round)
- [1. Corrections to the plan](#1-corrections-to-the-plan)
- [2. Exact diff sites](#2-exact-diff-sites)
- [3. The nine gate clauses as evaluable predicates](#3-the-nine-gate-clauses-as-evaluable-predicates)
- [4. The extracted actionability predicate](#4-the-extracted-actionability-predicate)
- [5. The daily-tick pass](#5-the-daily-tick-pass)
- [6. Payload shape and `dedup_key`](#6-payload-shape-and-dedup_key)
- [7. Client wiring](#7-client-wiring)
- [8. Parameter table — operator decisions](#8-parameter-table--operator-decisions)
- [9. Failure and no-op paths](#9-failure-and-no-op-paths)
- [10. Re-verify after P0 merge](#10-re-verify-after-p0-merge)

---

## 0. Position in the round

| Fact | Source |
|---|---|
| **Wave B, owner B2.** P1-9 holds `backend/server.py`, `backend/database.py`, `backend/trade_service.py`, `backend/feature_flags.py`, `config/features.json`, `backend/tests/fixtures/flags/release.json`, `backend/tests/fixtures/seed_ui_test_db.py`, `mobile/src/hooks/usePushNotifications.ts`, `mobile/src/components/TopBar.tsx`, `mobile/src/screens/SettingsScreen.tsx`, `mobile/src/utils/deepLinks.ts` — **exclusively for that wave**. | `HLD-p1.md` §B, Wave B |
| **P1-7 (wave A) releases `server.py` before B2 opens it.** They must never both hold the file. | `HLD-p1.md` §A.4, §D |
| **P0 merges first; P1-9 additionally sequences after P0-1** (push permission reachable for the default path; dry-run baseline meaningless before it). | `HLD-p1.md` §C step 0, `plan-p1-9.md` §OC-5 |
| **`deepLinks.ts` has two prior writers** (P0-3, then P1-1/2 in wave A) and `SettingsScreen.tsx` has three (P0-5, P1-10). **Re-grep, never edit by line.** | `HLD-p1.md` §A.3 |
| **P1-9 is the round's only real kill switch.** Four of seven P1 items ship user-visible change live on merge; `notif.trade_found` (default **OFF**) plus `trade_found_dry_run = 1` is the only deploy-free stop in the round. | `HLD-p1.md` §F R-1 |
| **P1-9 introduces no new analytics event name**, so it is immune to the round's most contended file (`analytics_taxonomy.py`, frozen after commit T1). | `HLD-p1.md` §A.4 |
| **A-18 is stale as written** — see [§1.0](#10-the-audit-finding-is-stale-the-true-finding). | `plan-p1-9.md` §"The thing that most changes the shape of this item" |

---

## 1. Corrections to the plan

Twelve. **C1, C2, C4, C6 and C12 are build-blocking as written** — a builder following the
plan literally would ship a dead cooldown, a `NameError`, an unattributable counter, an id
that contradicts the testID registry, and a Maestro flow that cannot render.

### 1.0 The audit finding is stale — the true finding

`04-priority-backlog.md` §P1-9 says "no new-trade notification". **False at `ab9368f`.**
F10's `deck_replenished` push exists (`backend/server.py:15797-15803`), `deck.replenishment`
is **`true`** (`config/features.json:148`), and the pass fires weekly per active user-league
(`_run_weekly_replenishment`, `backend/server.py:15751-15808`).

The true finding, and the problem statement the PRD carries:

> **The only new-trade push that exists is calendar-driven, quality-blind, and opted out by
> default.** It fires on a weekday gate (`replenish_weekday`, `backend/trade_service.py:373`)
> whenever `deck_size > 0` (`backend/server.py:15790`) — no quality condition of any kind —
> and it is deliberately mapped to the `reengagement` bucket
> (`backend/database.py:9847-9850`), which `notif.reengagement_default_off`
> (`config/features.json:123` = `true`) forces to `0` for any user with no stored pref row
> (`backend/database.py:9853-9871`). A user who never opened Settings **never receives it**.

Both halves matter. P1-9's job is a push whose trigger is *evidence*, not the calendar — and
one that is actually reachable, which is the pref-bucket question in [§8](#8-parameter-table--operator-decisions).

### C1 — **`_freq_cap_blocks` short-circuits: `trade_found` in both cap maps means the cooldown never runs** *(build-blocking)*

`plan-p1-9.md` change #5 adds `trade_found` to `_NOTIF_FREQ_CAPS` and change #6 adds it to
`_NOTIF_DEDUP_CAPS`. The two are **mutually exclusive** in the dispatcher:

```python
# backend/server.py:15312-15327
def _freq_cap_blocks(user_id, kind, dedup_key) -> bool:
    if kind in _NOTIF_DEDUP_CAPS and dedup_key:
        return notification_dedup_sent(user_id, kind, dedup_key)   # ← returns here
    cap = _NOTIF_FREQ_CAPS.get(kind)
    ...
```

A `trade_found` push always carries a `dedup_key` (§6), so the dedup branch returns first and
**the 7-day window cap is dead code**. Shipping the plan verbatim yields a feature whose
headline cadence guarantee ("one great push a week") is not enforced by the mechanism the
plan says enforces it.

**Resolution — two enforcement points, both specified:**

1. **Primary: in the pass.** `_trade_found_blocked()` (§3, **G6**) evaluates the cooldown
   itself via `count_notification_sends_since`. It has to: `_send_typed_push` returns nothing
   (C4), so a dispatcher-level block is invisible to the counters, and per-reason counters are
   the item's stated most valuable output (`plan-p1-9.md:544-549`).
2. **Defence in depth: make the dispatcher check non-exclusive.** Change `_freq_cap_blocks`
   so the dedup gate and the window cap are both evaluated:

   ```python
   if kind in _NOTIF_DEDUP_CAPS and dedup_key and notification_dedup_sent(...):
       return True
   cap = _freq_cap_for(kind)          # call-time read, see C11
   ...
   ```

   **Inert for every existing kind**, because the two maps are disjoint today:
   `_NOTIF_DEDUP_CAPS` = {`match_expiring`, `first_match`, `match_accepted`,
   `league_member_joined`, `league_member_unlocked_trades`, `deck_replenished`}
   (`:15230-15237`); `_NOTIF_FREQ_CAPS` = {`winback_matches`, `winback_dormant`,
   `finish_ranking`, `season_start`} (`:15212-15217`). No kind is in both, so no existing
   push's behaviour changes. A test asserts that (PRD **AC-24**).

### C2 — **G7 needs `device_tokens.created_at`, and no loader returns it** *(build-blocking)*

`scope-p1-9.md` §2 states "All existing loaders; **one new loader is not needed**." That is
wrong. `load_device_tokens_for_users` selects exactly three columns —
`user_id`, `device_token`, `platform` (`backend/database.py:9293-9297`) — and `created_at` is
never read anywhere outside `save_device_token`'s own preserve-on-upsert branch
(`:9257-9261`). Verified by grep: the only `device_tokens` references in `database.py` are
`:1212`, `:9234-9280`, `:9282-9305`.

**Resolution:** one new read-only helper in `backend/database.py` (a file B2 owns), beside
`load_device_tokens_for_users`:

```python
def load_earliest_device_token_at(user_id: str) -> str | None:
    """ISO timestamp of the user's OLDEST device_tokens row, or None when the
    user has never registered a token. P1-9 gate clause G7 — a trade_found
    push requires a token at least `trade_found_grace_hours` old, so a
    freshly-permissioned user's first-ever push is never this one."""
```

`MIN(created_at)` over `device_tokens WHERE user_id = :u`, non-throwing, returning `None` on
any error (same posture as every helper in that block). **Do not widen
`load_device_tokens_for_users`** — it is on the hot path of all 13 live push kinds.

### C3 — **`users.last_active_at` has no per-user loader** *(specification gap)*

G7's second half compares `users.last_active_at` against the token timestamp. The only
existing reader is `load_all_signed_up_users()` (`backend/database.py:10125-10154`), a full
table scan returning `sleeper_user_id`, `username`, `display_name`, `signup_at`,
`last_active_at`, `last_rank_at`, `unlocked_formats`.

**Resolution:** `_run_trade_found_pass` calls `load_all_signed_up_users()` **once**, at the
top, and indexes it into `{sleeper_user_id: row}`. Cost: one extra full scan per day, on a
tick that already performs the identical scan in its own loop (`backend/server.py:16080`).
Zero new DB code, and the map also supplies `username` for the copy (§6) and the demo/test
filter (**G2**).

*Alternative, if the user table ever outgrows one scan:* a `load_user_activity(user_ids)`
helper. Not built now — speculative abstraction, and the pass is bounded by
`trade_found_max_per_tick` at the send end regardless.

### C4 — **`_send_typed_push` returns `None`; `pushed` cannot mean "pushed"** *(build-blocking for the counters)*

`_send_typed_push` (`backend/server.py:15344-15412`) returns nothing on all six of its exit
paths: bad args (`:15364`), bucket off (`:15370`), cap (`:15374`), quiet-hours queue
(`:15386`), no device tokens (`:15391`), success (`:15409`), plus the swallowing `except`
(`:15410`). The plan's counter set (`pushed`, `plan-p1-9.md:333`) therefore counts
**attempts**, not sends — and the two differ for exactly the users the operator most needs to
distinguish (bucket-off, quiet-hours-deferred, no-device).

**Resolution:** make the return additive.

```python
def _send_typed_push(...) -> str:
    """... Returns a status string: 'sent' | 'queued' | 'skipped_bucket'
    | 'skipped_cap' | 'no_device' | 'invalid' | 'error'. Every existing
    call site ignores the return value; the P1-9 pass is the first reader."""
```

Verified safe: **no call site uses the return value.** All 13 live kinds call it as a
statement (`:10116`, `:10125`, `:12891`, `:6254`, `:14788`, `:15797`, `:15909`, `:16026`,
`:16040`, `:16088`, `:16099`, `:16126`, `:16134`, `:16147`). The pass then counts
`pushed` = `sent`, `queued_quiet` = `queued`, `blocked_bucket` = `skipped_bucket`,
`no_device` = `no_device` — honest names for what actually happened.

*If the operator or reviewer rejects touching the shared dispatcher signature:* the fallback
is to rename the plan's counter `pushed` → `attempted` and accept that the pass cannot report
delivery. **Say which was chosen in the scope block; do not ship a counter named `pushed`
that counts attempts.**

### C5 — **The extracted predicate cannot take the injector's object shapes** *(design detail the plan leaves open)*

The injector reads `opp.roster` off a `LeagueMember` dataclass
(`backend/trade_service.py:1967-1970`, `backend/server.py:2873`) and the already-swiped set
off in-memory engine state (`trade_service._past_decision_keys`, `:2893`). The cron pass has
neither: it has `load_league_members(league_id)` dicts whose roster is decoded into
**`player_ids`** (`backend/database.py:5314-5331`) and must read past decisions from
`load_trade_decisions` (`:4123-4151`).

**Resolution:** the extraction is **primitives-only** and covers exactly
`backend/server.py:2871-2885` — roster containment plus the two asset-preference filters.
The already-swiped check (`:2892-2894`) stays at each call site with its own data source,
because its *source* legitimately differs while its *semantics* do not. Signature in
[§4](#4-the-extracted-actionability-predicate).

### C6 — **The proposed testIDs contradict the registry** *(build-blocking for `testid-lint.sh`)*

`plan-p1-9.md` #17 proposes `topbar.notif-bell`. The testID registry —
`docs/plans/mobile-testing/lld.md` Appendix A, `:313` — **already reserves `topbar.bell`**
(and `topbar.bell-badge`) under "Shared chrome". Minting a second name for the same control
splits the grammar for no gain.

Two further sub-corrections:

- **The registry is not `mobile/src/components/CLAUDE.md`.** That file says so itself
  (`:3`: *"testID grammar/registry: `docs/plans/mobile-testing/lld.md` Appendix A"*), and
  Appendix A's own line `:311` still points back at `components/CLAUDE.md` — the two
  disagree. `mobile/scripts/testid-lint.sh` reads **neither**; it greps `mobile/src` for the
  literal and consults `mobile/scripts/testid-lint-allow.txt` (`:40-53`). Plan change #19
  ("register in `mobile/src/components/CLAUDE.md`") is therefore filed against a doc that is
  not the registry. **Update Appendix A** (`docs/plans/mobile-testing/lld.md:313` and `:329`)
  and leave a one-line pointer in `components/CLAUDE.md`; note the doc-vs-doc contradiction
  in the ship notes rather than resolving it here (it is not P1-9's to arbitrate).
- **`settings.notif.<pref>` is already the reserved shape** (`:329`). The four ids follow it:
  `settings.notif.trade-matches`, `settings.notif.weekly-digest`,
  `settings.notif.reengagement`, `settings.notif.quiet-hours`. All static strings, so no
  allow-list entry is needed.
- **`topbar.notif-row.<id>` needs no allow-list entry.** Verified against the lint's own
  extraction: an id containing `*` is truncated at the star and the trailing dot stripped
  (`testid-lint.sh:43`), then grepped as a prefix — and
  `` testID={`topbar.notif-row.${it.id}`} `` (`TopBar.tsx:342`) matches the
  `` testID={\`?["'\`]*<base> `` pattern at `:44`. The plan's hedge is unnecessary; **do not
  add a blanket `topbar.*` glob**, which would exempt real static ids from checking.

### C7 — **The stale `notifications.type` enumeration lives in three places, not one**

`plan-p1-9.md`'s docs table cites `backend/database.py:820`. There are three:

| Site | Text |
|---|---|
| `backend/database.py:812` | block comment — *"type: one of 'trade_match', 'trade_accepted', 'trade_declined'"* |
| `backend/database.py:820` | inline — `# trade_match \| trade_accepted \| trade_declined` |
| `backend/database.py:8446` | `create_notification` docstring — *"type_ : 'trade_match', 'trade_accepted', or 'trade_declined'"* |

All three are already false (`league_member_joined` and friends write inbox rows via other
paths only in the match flows, but the enumeration was never widened). A-33 rule: correct all
three in the same pass, or the next reader inherits the same wrong list from whichever one
they open.

### C8 — **HLD §F R-6 ("dead notification tap on web") is answered: it degrades safely**

`HLD-p1.md` §G.6 marks this a **blocking** build-time check. It can be closed now, from the
code:

- `notifTypeIcon` (`web/js/app.js:4676-4681`) is a three-way `if` chain with
  `return ICON.bell` as the fallback — an unknown `type` renders the generic bell, exactly as
  mobile's `DEFAULT_ROW_GLYPH` (`TopBar.tsx:73-76`) does.
- `_renderNotifList` (`:4714-4751`) does not branch on `type` beyond the icon.
- `clickNotif` (`:4807-4835`) marks read for every type and only navigates for
  `trade_match | trade_accepted | trade_declined` (`:4830`) — an unknown type is an **inert
  tap with no error**.

**Verdict: no `web/js/app.js` edit is required, and none is made** (no P1 item may edit that
file this round — `HLD-p1.md` §A.4). The behaviour — generic glyph, inert tap, no error — is
recorded in `docs/cross-client-invariants.md` as the documented degradation, and re-verified
in [§10](#10-re-verify-after-p0-merge) because P0 could have touched the file.

### C9 — **G2's demo/test exclusion is half-covered by the loader**

`load_active_deck_user_leagues` already excludes `league_id != "league_demo"` at the SQL level
(`backend/database.py:4270-4271`), so the plan's league check is redundant (harmless; keep it
as a cheap assertion). It does **not** filter demo or test **users**. The pass must do that
itself, using the same predicate shape the tz-sync helper uses
(`str(user_id).startswith("demo_user") or user_id == DEMO_USER_ID`,
`backend/server.py:15444`), plus the seeded QA ids if the operator wants them excluded in a
seeded environment. Stated so it is not assumed.

### C10 — **The Maestro flow depends on `notif.tap_routing_v2`, twice**

The bell only hydrates from the server inbox when `tapV2` is true (`TopBar.tsx:115`,
`:121-141`) and rows are only tappable `Pressable`s under the same flag (`:339-352`); with the
flag off the sheet shows the in-session feed and inert `View`s. `notif.tap_routing_v2` is
`true` in `config/features.json:121`, and the flow's `# flags:` fixture must resolve to a set
that keeps it true (law 16 — `# flags:` is a **resolved fixture filename**, not prose). Also:
the seeded profile does **not** need `notif.trade_found: true` — that flag gates the backend
cron pass only, and the flow seeds the inbox row directly. Harmless if present; note it so no
one concludes the flow proves the flag.

### C11 — **`_NOTIF_FREQ_CAPS` is a module-level literal read at import**

Confirmed (`backend/server.py:15212-15217`, read once at import; `_freq_cap_blocks` reads the
dict at `:15321`). `plan-p1-9.md` change #5 is right to flag it. Exact resolution: a
`_freq_cap_for(kind)` helper next to the map that returns the literal entry for existing
kinds and, for `trade_found`, builds the tuple from `_deck_cfg("trade_found_cooldown_days",
7)` at call time. `_deck_cfg` reads `trade_service._cfg` (`backend/server.py:3074-3082`,
`backend/trade_service.py:449`), which is the live, `PUT /api/admin/config`-mutable dict — so
the knob is genuinely deploy-free. **Do not** call `_deck_cfg` at module scope; that freezes
it at import and is exactly the silent failure the plan warns about.

### C12 — **Dry-run must suppress the inbox row too, which makes dry-run invisible end-to-end**

`plan-p1-9.md` T-17 requires dry-run to write **zero** `notification_events_log` rows **and
zero** inbox rows. That is the right call (a dry run must not mutate user-visible state), but
it has a consequence the plan does not state: **in dry-run the feature produces nothing a
user or a simulator can observe** — the entire first release is counters in a cron response.
The Maestro flow therefore cannot exercise the pass at all; it exercises the **rendering and
routing** of a seeded row (see PRD §Maestro). Stated so the coverage claim stays honest.

---

## 2. Exact diff sites

Ordered by file. **Every line number is `ab9368f` and will have moved** — P0 edits six
functions in `server.py`, P1-7 edits the unlock ladder in wave A, and three items move
`SettingsScreen.tsx` and `deepLinks.ts` ahead of B2. Re-grep by the anchor in the last
column; never edit by line ([§10](#10-re-verify-after-p0-merge)).

### 2.1 `backend/feature_flags.py`

| # | Site | Current | Intended | Re-grep anchor |
|---|---|---|---|---|
| D1 | `:267-271` (`FLAG_KEYS`, `notif.*` block) | five `notif.*` keys, last is `"notif.honest_winbacks"` | append `"notif.trade_found",  # P1-9: quality-gated counterparty-intent push (docs/plans/audit-p1-remediation/LLD-p1-9.md)` **inside the block**, not at the end of the tuple | `"notif.honest_winbacks"` |

Default `False` is automatic — `DEFAULT_FLAGS = {key: False for key in FLAG_KEYS}` (`:619`).
The attribute form `FLAGS.notif_trade_found` follows from `_key_to_attr` (`:630`); no second
mapping to maintain.

### 2.2 `config/features.json` and `backend/tests/fixtures/flags/release.json`

| # | Site | Current | Intended |
|---|---|---|---|
| D2 | `config/features.json:120-124` | `notif.tz_sync` … `notif.honest_winbacks`, all `true` | add `"notif.trade_found": false` after `:124`, preceded by a `_comment_notif_trade_found` string in house style (cf. `:143` `_comment_rookie_draft`) stating: what ON does (runs `_run_trade_found_pass` inside `POST /api/cron/daily-tick`), the gate's trigger (a leaguemate's `like` whose mirror is actionable — never a model score), that OFF is **byte-identical** (no pass, no push, no inbox row, no response key), and that cadence/thresholds are `model_config` keys, **not** this flag |
| D3 | `backend/tests/fixtures/flags/release.json` (mirror of `:124`) | same five keys | `"notif.trade_found": false` — the release fixture must carry the same default or seeded runs diverge from prod |

### 2.3 `backend/trade_service.py`

| # | Site | Current | Intended |
|---|---|---|---|
| D4 | `_DEFAULT_CFG` (`:40`), immediately after the F10 block ending `"replenish_weekday": 2.0,` at `:373` | F10 block | eight Float-typed keys under a `# ── P1-9 — trade_found push gate (flag: notif.trade_found …) ──` header, each with an inline unit/consequence comment. Names, defaults and semantics: [§8](#8-parameter-table--operator-decisions) |

Float typing is the convention for this dict (`dict[str, float]`, `:40`); the pass casts with
`int(...)` where a count or day-window is needed, as F10 does at `backend/server.py:15757`.

### 2.4 `backend/database.py`

| # | Site | Current | Intended | Anchor |
|---|---|---|---|---|
| D5 | `NOTIF_KIND_TO_BUCKET` `:9830-9851` | 14 kinds → 3 buckets; `deck_replenished` → `reengagement` with its rationale comment at `:9847-9850` | add **`"trade_found": <bucket>`** per the operator's answer to **[P-1](#8-parameter-table--operator-decisions)**. The comment must (a) state the reason for the chosen bucket, (b) **cross-reference the `deck_replenished` comment three lines above** so the asymmetry is deliberate on the page, and (c) record the coupling: *if the gate ever widens beyond counterparty intent, this kind moves to `reengagement` in the same change* | `"deck_replenished":` |
| D6 | `:812`, `:820`, `:8446` | three stale enumerations of `notifications.type` (C7) | correct all three to the live set, adding `trade_found` | `trade_declined` |
| D7 | after `load_device_tokens_for_users` (`:9282-9305`) | no reader of `device_tokens.created_at` | new `load_earliest_device_token_at(user_id) -> str | None` (C2) | `def load_device_tokens_for_users` |

**No schema change. No migration. No index.** Every write lands in `notifications` (`:817`),
`notification_events_log` (`:1249`), `notification_queue` (`:1259`).

### 2.5 `backend/server.py`

| # | Site | Current | Intended | Anchor |
|---|---|---|---|---|
| D8 | `_NOTIF_FREQ_CAPS` `:15212-15217` | module-level literal, 4 kinds | **leave the literal alone**; add `_freq_cap_for(kind) -> tuple[int,int] | None` beneath it that returns `_NOTIF_FREQ_CAPS.get(kind)` for existing kinds and, for `"trade_found"`, `(int(_deck_cfg("trade_found_cooldown_days", 7)), 1)` at call time (C11) | `_NOTIF_FREQ_CAPS: dict` |
| D9 | `_NOTIF_DEDUP_CAPS` `:15230-15237` + its comment block `:15219-15229` | 6 kinds | add `"trade_found"` and a comment row: `trade_found → dedup_key = "lk:{league_id}:{sig}"` where `sig` is the stable trade signature (§6) — the same logical trade never re-pushes, ever | `"deck_replenished",` |
| D10 | `_freq_cap_blocks` `:15312-15327` | dedup branch **returns**, short-circuiting the window cap | non-exclusive evaluation (C1): dedup gate → `True` only when it blocks; otherwise fall through to `_freq_cap_for(kind)`. **Inert for all existing kinds** (the maps are disjoint) | `def _freq_cap_blocks` |
| D11 | `_send_typed_push` `:15344-15412` | returns `None`; payload `{**(data or {}), "type": kind}` at `:15397` | (a) return a status string (C4); (b) payload gains `dedup_key`: `{**(data or {}), "type": kind, "dedup_key": dedup_key}` — required for `push_opened.dedup_key`, inert for clients (`data` is opaque except `type`/`match_id`/`league_id`) | `"data":  {**(data or {})` |
| D12 | near `_inject_likes_you_cards_impl` `:2813`, above it | actionability inline at `:2871-2885` | **extract** `_likes_you_actionable(...)` (§4) and call it from the injector | `def _inject_likes_you_cards_impl` |
| D13 | `:2871-2885` (inside the injector loop) | four inline `continue` guards | replaced by one call to `_likes_you_actionable`; behaviour byte-identical (parity test, PRD **AC-23**) | `# Still actionable? Rosters change` |
| D14 | next to `_deck_replenishment_enabled` `:2979-2985` | F10 flag helper | `_trade_found_enabled() -> bool: return getattr(FLAGS, "notif_trade_found", False)` — same shape and docstring convention ("off ⇒ byte-identical behavior") | `def _deck_replenishment_enabled` |
| D15 | new, above `cron_daily_tick` | — | `_trade_found_candidate(uid, lid, now, ctx) -> dict | None` (G2–G5) and `_trade_found_blocked(uid, now) -> str | None` (G6, G7) — both pure reads, both non-throwing (§3, §5) | — |
| D16 | new, above `cron_daily_tick`, modelled on `_run_weekly_replenishment` `:15751-15808` | — | `_run_trade_found_pass(now) -> dict` (§5) | `def _run_weekly_replenishment` |
| D17 | `cron_daily_tick` `:16060`, beside the F10 hook `:16156-16164` | `replenish_stats` block | `trade_found_stats: dict | None = None`; `if _trade_found_enabled(): try: trade_found_stats = _run_trade_found_pass(now) except Exception as e: log.warning(...); trade_found_stats = {"error": str(e)}`; serialize into the response **only when non-`None`**. Flag off ⇒ byte-identical response | `if _deck_replenishment_enabled():` |

### 2.6 Mobile

| # | Site | Current | Intended | Anchor |
|---|---|---|---|---|
| D18 | `mobile/src/utils/deepLinks.ts:262` | `const V2_TRADE_KINDS = new Set(['deck_replenished']);` | add `'trade_found'`, with a comment mirroring the F10 one above it (`:258-261`) | `V2_TRADE_KINDS` |
| D19 | `mobile/src/hooks/usePushNotifications.ts:200` | legacy `const tradeKinds = new Set(['deck_replenished']);` | add `'trade_found'`. `notif.tap_routing_v2` is on today, but a flag-off path that silently performs no navigation is the A-33 class of bug | `const tradeKinds` |
| D20 | `mobile/src/hooks/usePushNotifications.ts:61-82` (cold-start replay) and `:166-213` (live listener) | no `track()` anywhere in the file | `track('push_opened', { kind, dedup_key })` in **both** paths, **inside the existing `handledTapIdsRef` dedupe guard** (`:71-72`, `:176-177`) so a warm tap surfacing through both routes counts once. `kind = String(data?.type ?? '')`, `dedup_key = data?.dedup_key`. Import `track` from `../api/events` (signature `track(eventType, props?, screen?)`, `mobile/src/api/events.ts:188`) | `handledTapIdsRef.current.add(respId)` |
| D21 | `mobile/src/components/TopBar.tsx:65-72` `ROW_GLYPHS` | 6 entries; unknown types fall to `DEFAULT_ROW_GLYPH` (`:73-76`) | add a `trade_found` entry — **glyph choice is operator decision [P-6](#8-parameter-table--operator-decisions)** (`match`/ice, mirroring the match family, or its own stroke icon) | `const ROW_GLYPHS` |
| D22 | `mobile/src/components/TopBar.tsx:215-238` (bell `Pressable`) | `onPress={openSheet}`, `accessibilityLabel`, **no `testID`** | add `testID="topbar.bell"` — the reserved name (C6) | `accessibilityLabel={\n unreadCount > 0` |
| D23 | `mobile/src/screens/SettingsScreen.tsx:986-1006` | three bucket `Row`s, no `testID` | (a) add `testID` to all three + the quiet-hours row at `:1010-1016`; the `Row` helper already accepts one and forwards it to the `Switch` (`:1449-1470`). (b) **conditional on [P-1](#8-parameter-table--operator-decisions):** if `trade_found` lands in `trade_matches`, the row `sub` — *"New matches, counter-offers, league activity"* — must change or it is false | `sub="New matches, counter-offers` |
| D24 | `mobile/src/components/PushPrimingModal.tsx:59-64` | three consent bullets | **conditional on [P-1](#8-parameter-table--operator-decisions):** a fourth bullet if the kind lands in a bucket the primer's consent covers. **Build-blocking dependency** — see [§8](#8-parameter-table--operator-decisions) note. The file is not in B2's HLD ownership list; if this lands, B2 must claim it explicitly (no other item touches it — verified in `HLD-p1.md` §A.3) | `• A match is about to expire` |

### 2.7 Tests, fixtures, docs

| # | Site | Intended |
|---|---|---|
| D25 | `backend/tests/fixtures/seed_ui_test_db.py` `~:1137-1163` | (a) `matches_seed.likes_you: N` — seed **counterparty** likes via `db.save_trade_decision(partner, lid, f"seed-likesyou-{lid}-{i}", give=<from partner's roster>, receive=<from app user's roster>, "like")` (signature at `backend/database.py:4102-4109`); note the give/receive orientation is **the partner's perspective**, which is exactly what `load_recent_league_likes` returns and what G4 mirrors. (b) a generic `notifications_seed: [{type, title, body, metadata}]` block calling `db.create_notification` (`:8439`) so a profile can plant a `trade_found` inbox row |
| D26 | `backend/tests/fixtures/profiles/likes-you-waiting.json` (new) | from `near-unlock.json`'s shape: app user **unlocked**, one ranked leaguemate, `matches_seed: {mutual: 0, awaiting: 0, likes_you: 1}`, one `notifications_seed` `trade_found` row, `flags_base: "release"`. No flag override is required (C10) |
| D27 | `backend/tests/test_trade_found.py` (new) | the 26-case matrix — enumerated as acceptance criteria in the PRD |
| D28 | `mobile/.maestro/flows/p1-9-trade-found-inbox.yaml` (new) | PRD §Maestro |
| D29 | `docs/plans/mobile-testing/lld.md:313`, `:329` | register `topbar.bell` (already reserved — confirm) and the four `settings.notif.*` ids (C6) |
| D30 | docs + `living-memory` | PRD §Docs impact |

---

## 3. The nine gate clauses as evaluable predicates

**The gate is a conjunction evaluated in this order.** Order is chosen so the cheapest and
most-often-false clauses run first and the expensive per-league reads run last. Every failure
is a silent, **counted** no-op: the pass never "almost" sends. The organising principle is
binding: **the trigger is another human's revealed intent — a leaguemate's `like` — never a
model score, and never a change in the recipient's own account state**
(`plan-p1-9.md` §Design; `HLD-p1.md` §E PR-16).

| # | Clause | Predicate (evaluable) | Reads | On false | Counter |
|---|---|---|---|---|---|
| **G1** | Feature on | `_trade_found_enabled()` → `getattr(FLAGS, "notif_trade_found", False)` | `feature_flags` | **return before any work**; `cron_daily_tick` response omits the key entirely | — (no counters exist) |
| **G2** | Real, recently-active deck user | `(uid, lid) ∈ load_active_deck_user_leagues(days=int(cfg.trade_found_active_days))` **and** `lid != "league_demo"` **and** `uid` not demo/test **and** `uid ∈ users_by_id` | `backend/database.py:4253-4281`; user map from C3 | pair never enumerated | `eligible_pairs` counts survivors |
| **G7** | Grace — no surprise for a freshly-permissioned user | `tok = load_earliest_device_token_at(uid)`; require `tok is not None` **and** `tok ≤ now − cfg.trade_found_grace_hours` **and** `users_by_id[uid].last_active_at > tok` | C2's loader; `users.last_active_at` | short-circuit **before** any league read | `blocked_grace` |
| **G6a** | Own-kind cooldown | `count_notification_sends_since(uid, "trade_found", now − cfg.trade_found_cooldown_days) == 0` | `backend/database.py:9982-9998` | short-circuit | `blocked_cooldown` |
| **G6b** | Cross-kind quiet period | for every `k ∈ {deck_replenished, trade_found, winback_matches, winback_dormant, weekly_digest}`: `count_notification_sends_since(uid, k, now − cfg.trade_found_global_quiet_days) == 0` | same | short-circuit | `blocked_quiet` |
| **G3** | Counterparty intent exists | `likes = load_recent_league_likes(lid, exclude_user_id=uid, days=int(cfg.trade_found_max_age_days))`, then drop rows younger than `cfg.trade_found_min_like_age_minutes` | `backend/database.py:4154-4200` (already newest-first by `id desc`) | next pair | `candidates` counts pairs with ≥1 surviving like; `blocked_stale` when the only likes fell outside the age window |
| **G4** | Actionable right now | `_likes_you_actionable(...)` (§4) returns a mirrored `(my_give, my_recv)` — i.e. their give ⊆ their current roster, their receive ⊆ the user's current roster, mirrored give ∩ untouchables = ∅, mirrored receive ∩ not-interested = ∅ | `load_league_members` `:5314`, `load_asset_preferences` `:7069` | try the next like | `blocked_unactionable` |
| **G5** | Genuinely new to this user | (a) `like.created_at > shown_at` of `load_latest_trade_impression_batch(uid, lid)` when that batch exists, else `> users.last_active_at`; **and** (b) `(frozenset(my_give), frozenset(my_recv)) ∉ {keys from load_trade_decisions(uid, lid, since_days=90)}` | `:4284-4316`, `:4123-4151` | try the next like | `blocked_seen` (a) / `blocked_swiped` (b) |
| **G8** | Prefs, quiet hours, devices | inherited verbatim from `_send_typed_push` steps 1–5 (`:15367-15400`): bucket gate, cap gate, quiet-hours deferral, device fan-out | zero new code | dispatcher decides; the pass records the returned status (C4) | `blocked_bucket`, `queued_quiet`, `no_device` |
| **G9** | Blast radius | `sent_this_tick < int(cfg.trade_found_max_per_tick)`; and if `cfg.trade_found_dry_run >= 1`, compute everything and **write nothing** | `model_config` | stop the send loop / count only | `dry_run_would_push`, `blocked_max_per_tick` |

**Short-circuit contract.** G1 gates the whole pass. G7/G6a/G6b are **per user** and are
evaluated once per user before any of that user's leagues are read — a blocked user costs
three indexed counts and nothing else. G3/G4/G5 are **per (user, league, like)** and abort to
the next like, not the next pair. G8/G9 run at send time.

**Selection when several likes pass.** Exactly one push per user per run, describing **one**
trade: the *most recent* qualifying like. `load_recent_league_likes` already returns newest-
first (`ORDER BY id DESC`, `backend/database.py:4184`), so this is "take the first survivor" —
no sort, no score. Deliberately not "the highest-scoring": a model ranking would reintroduce
the judgement the gate exists to avoid, and recency is the property the user can verify.

**What the gate deliberately does NOT read.** No `composite_score`, no `fairness_score`, no
mutual-gain threshold. Those order the deck; they are not evidence that a trade is worth
interrupting someone for. Widening to a model-scored lane is **[P-2](#8-parameter-table--operator-decisions)**,
and is coupled to the bucket choice.

**Why backfill protection is structural, not a filter.** There is no code path by which a
change in the *recipient's own* progression state produces a `trade_found` push — the trigger
is G3, someone else's `like`. P0-1's backfill can flip `unlocked`, mint tokens and light the
primer for the whole cohort and this pass still sends **zero**, because none of those events
is a like. G7 (token ≥ grace old **and** `last_active_at` postdating it) and G3's age window
are belt and braces on top: for the first `trade_found_grace_hours` after P0-1's deploy the
entire backfilled cohort is ineligible **by construction**, anyone who accepts the primer and
never returns stays ineligible **forever**, and 90 days of accumulated league likes produce
no candidates because only the last `trade_found_max_age_days` count. **A user's first-ever
push from this product is therefore never a `trade_found`.** P0-1 deliberately suppresses its
own backfill's push fan-out (`plan-p0-1` §R2 / Q5); this design must not re-create the
surprise-push problem it avoided, and by construction it cannot.

---

## 4. The extracted actionability predicate

**This is the load-bearing part of the item.** If the deck's definition of "actionable" and
the push's ever drift apart, the product pushes about trades its own deck would not show —
a silent, unfalsifiable bug. The predicate is extracted **once** and called from **both**
sites.

### Signature

```python
def _likes_you_actionable(
    their_give: list[str],
    their_recv: list[str],
    opp_roster: set[str],
    user_roster: set[str],
    untouchable_ids: set[str] | None = None,
    not_interested_ids: set[str] | None = None,
) -> tuple[list[str], list[str]] | None:
    """The single definition of 'a leaguemate's like is still actionable for
    this user', mirrored into the user's perspective.

    Returns (my_give, my_recv) — the mirror, my_give = their_recv and
    my_recv = their_give — or None when any condition fails:

      * either side empty
      * their give is no longer entirely on their roster
      * their receive is no longer entirely on the user's roster
      * the mirrored GIVE side touches an untouchable (backlog #2 / #95 —
        untouchables never leave the user's roster, even when the
        counterparty already liked the mirror)
      * the mirrored RECEIVE side touches a not-interested player (#163 —
        never offered TO the user, even via a counterparty like)

    Pure: no I/O, no mutation, no ordering. Extracted from
    _inject_likes_you_cards_impl (server.py:2867-2887 at ab9368f) so the
    deck injector and the P1-9 trade_found push can never disagree about
    what 'actionable' means. Primitives only — the two call sites hold
    different object shapes (LeagueMember dataclass vs load_league_members
    dicts), which is precisely why this takes sets.
    """
```

### Semantics, clause by clause — byte-identical to today

| Current line | Guard | In the extraction |
|---|---|---|
| `backend/server.py:2867-2870` | `their_give` / `their_recv` empty → skip | first check |
| `:2873-2874` | `set(their_give) <= set(opp.roster)` | `set(their_give) <= opp_roster` |
| `:2875-2876` | `set(their_recv) <= user_roster_set` | `set(their_recv) <= user_roster` |
| `:2880-2881` | `untouchable_ids and set(their_recv) & untouchable_ids` | unchanged (their receive **is** the user's give after mirroring) |
| `:2884-2885` | `not_interested_ids and set(their_give) & not_interested_ids` | unchanged (their give **is** the user's receive) |
| `:2887` | `my_give, my_recv = list(their_recv), list(their_give)` | becomes the return value |

**Deliberately NOT extracted** (C5): the opponent lookup (`:2864-2866`), the per-deck
`seen_keys` dedupe (`:2888-2891`), and the already-swiped check
(`if (key[0], key[1]) in trade_service._past_decision_keys`, `:2892-2894`). The last one is
G5(b) at the push site, sourced from `load_trade_decisions` instead of engine state — same
semantics, different substrate. The cap (`_LIKES_YOU_CAP`, `:2798`, `:2862`) is deck-only.

### Call site A — the deck injector (behaviour must not change)

`backend/server.py:2861-2894`, inside `for like in likes:`

```python
opp = members_by_id.get(like["user_id"])
if opp is None or opp.user_id == user_id:
    continue
mirrored = _likes_you_actionable(
    like["give_player_ids"], like["receive_player_ids"],
    set(opp.roster), user_roster_set,
    untouchable_ids, not_interested_ids,
)
if mirrored is None:
    continue
my_give, my_recv = mirrored
# … unchanged from :2888 onward
```

`opp.roster` is the `LeagueMember` dataclass field (`backend/trade_service.py:1970`).

### Call site B — the push pass (new)

```python
members   = {m["user_id"]: set(m["player_ids"]) for m in load_league_members(lid)}
prefs     = load_asset_preferences(uid, lid)          # database.py:7069
untouch   = set(prefs["untouchables"])
not_int   = set(prefs["not_interested"])
user_ros  = members.get(uid, set())
opp_ros   = members.get(like["user_id"])
if opp_ros is None or like["user_id"] == uid:
    continue
mirrored = _likes_you_actionable(
    like["give_player_ids"], like["receive_player_ids"],
    opp_ros, user_ros, untouch, not_int,
)
```

`load_league_members` decodes the roster into `player_ids` (`backend/database.py:5325-5329`)
— **not** `roster`. Reading `m["roster"]` is a `KeyError`; reading `m["roster_data"]` gets
the raw JSON string. Named because it is the obvious way to get this wrong.

**One asset-preference nuance, stated rather than assumed:** the injector loads asset prefs
only when `FLAGS.trade_preference_lists` is on (`backend/server.py:4780-4787`) and passes
`or None` when empty (`:4901-4902`). The push pass must apply the same flag condition, or a
`trade_found` push could offer a player the deck would filter out. The predicate itself is
flag-agnostic; the **call sites** carry the flag check.

### Parity is proved, not asserted

The extraction is the one refactor in this item touching live, flag-on deck code
(`trade.likes_you` = `true`, `config/features.json:30`). PRD **AC-23** is a table-driven
differential test: the same fixture rows are fed to the extracted helper and to a verbatim
copy of the pre-extraction predicate, asserting identical accept/reject on every row.
**If that test cannot be made clean, do not extract** — duplicate the predicate with a comment
binding the two and accept the divergence risk knowingly (`plan-p1-9.md` R5). That is a build-
time judgement, recorded in the scope block either way.

---

## 5. The daily-tick pass

### Placement

Inside the existing `POST /api/cron/daily-tick` (`backend/server.py:16060`), beside the F10
hook (`:16156-16164`). No new endpoint, no new schedule, no new `CRON_SECRET` consumer, no
change to `.github/workflows/render-cron.yml`. Auth is inherited from `_require_cron_auth`
(`:16068`, definition `:15840-15859`; fails **closed** in prod when the secret is unset).

Four properties, adopted from F10's precedent (`_run_weekly_replenishment`, `:15751-15808`):

1. **Flag off ⇒ byte-identical response.** The key is added to the JSON body only when the
   stats object is non-`None`.
2. **No deck generation.** Unlike `_replenish_deck_for` (`:15699`), which runs a full
   synchronous trade job, this pass is four indexed reads per surviving user-league. It cannot
   time the cron out.
3. **The inbox row is written before the push** — F10's marker-before-push rule
   (`:15785-15788`): a row without a push beats a push without a row.
4. **Wrapped so a failure cannot touch the winback loop above it** (D17).

### Control flow

```
_run_trade_found_pass(now) -> dict
├─ cfg = {k: _deck_cfg(k, default) for the eight keys}        # call-time read (C11)
├─ dry  = cfg.trade_found_dry_run >= 1
├─ users_by_id = {r["sleeper_user_id"]: r for r in load_all_signed_up_users()}   # C3
├─ pairs = load_active_deck_user_leagues(days=int(cfg.trade_found_active_days))  # G2
├─ group pairs by user_id                                     # per-user gates run once
│
├─ for uid, leagues in grouped:
│    ├─ G2 demo/test filter                     → skip (not counted as blocked)
│    ├─ stats.eligible_pairs += len(leagues)
│    ├─ reason = _trade_found_blocked(uid, now, cfg, users_by_id)   # G7, G6a, G6b
│    │    └─ if reason: stats[f"blocked_{reason}"] += 1 ; continue
│    ├─ for lid in leagues:                                   # newest-first candidate hunt
│    │    ├─ cand = _trade_found_candidate(uid, lid, now, cfg, users_by_id, stats)
│    │    │        # G3 → G4 → G5, per like, newest first; increments blocked_* by reason
│    │    └─ if cand: break                                   # one push per user per run
│    ├─ if not cand: continue
│    ├─ stats.candidates += 1
│    ├─ if dry:  stats.dry_run_would_push += 1 ; continue     # G9 — writes NOTHING (C12)
│    ├─ if stats.pushed >= int(cfg.trade_found_max_per_tick):
│    │        stats.blocked_max_per_tick += 1 ; continue      # G9
│    ├─ create_notification(uid, "trade_found", title, body, metadata)   # inbox FIRST
│    ├─ status = _send_typed_push(uid, "trade_found", title=…, body=…,
│    │                            data={"league_id": lid, …},
│    │                            dedup_key=f"lk:{lid}:{sig}")           # G8
│    └─ stats[_STATUS_TO_COUNTER[status]] += 1                # C4
└─ return stats
```

### Counters (the pass's entire operator-facing output)

| Counter | Meaning |
|---|---|
| `eligible_pairs` | (user, league) pairs surviving **G2** |
| `users_considered` | distinct users among them |
| `blocked_grace` | **G7** — token too young, or granted-and-never-returned |
| `blocked_cooldown` | **G6a** — a `trade_found` inside the own-kind window |
| `blocked_quiet` | **G6b** — another push of a listed kind inside the cross-kind window |
| `blocked_stale` | **G3** — likes exist but all older than `trade_found_max_age_days`, or younger than `trade_found_min_like_age_minutes` |
| `blocked_unactionable` | **G4** — rosters moved, or an asset-preference filter |
| `blocked_seen` | **G5a** — a deck was generated after the like (the injector already showed it) |
| `blocked_swiped` | **G5b** — the user already decided on the mirrored trade |
| `candidates` | users with a fully qualifying candidate |
| `dry_run_would_push` | candidates suppressed only by dry-run |
| `pushed` | dispatcher returned `sent` |
| `queued_quiet` | dispatcher returned `queued` (quiet hours) |
| `blocked_bucket` | dispatcher returned `skipped_bucket` |
| `blocked_dispatch_cap` | dispatcher returned `skipped_cap` (defence in depth; should be 0 given G6a) |
| `no_device` | dispatcher returned `no_device` |
| `blocked_max_per_tick` | **G9** blast cap |
| `errors` | per-user exceptions swallowed by the loop |

**This counter set is the deliverable of the dry-run window.** `candidates == 0` is a
*density* problem (expected today, per the audit's own replicability finding). `candidates ==
40, blocked_seen == 40` is a *gate* problem. Those look identical from outside and completely
different here.

---

## 6. Payload shape and `dedup_key`

### Trade signature

```python
def _trade_found_sig(my_give: list[str], my_recv: list[str]) -> str:
    """Stable 12-hex signature of a mirrored trade: sha1 over the sorted
    give ids, a separator, and the sorted receive ids. Order-independent
    and direction-aware — 'A for B' and 'B for A' are different trades."""
```

`dedup_key = f"lk:{league_id}:{sig}"`. With `trade_found` in `_NOTIF_DEDUP_CAPS` (D9) this is
a **lifetime** gate: the same logical trade never re-pushes, ever, for that user
(`notification_dedup_sent`, `backend/database.py:9960-9980`).

### Expo `data` payload

```python
data = {"league_id": lid, "target_user_id": opp_uid}
# _send_typed_push adds: "type": "trade_found", "dedup_key": <key>   (D11)
```

Result on device: `{league_id, target_user_id, type: "trade_found", dedup_key: "lk:…"}`.
`resolveNotificationTarget` reads only `data.type` (`mobile/src/utils/deepLinks.ts:275`) and,
for match kinds, `data.match_id` (`:279`) — the extra keys are inert. `dedup_key` exists
solely so `push_opened.dedup_key` can be non-null (`analytics_taxonomy.py:213` already
declares the prop).

**D11 is cross-cutting**: every one of the 13 live kinds gains `dedup_key` in `data`. Inert
(no client reads unknown `data` keys) and required — without it the prop is permanently null.
PRD **AC-25** regresses that an existing kind's `title`/`body` are byte-identical and only
`data` grew.

### Inbox row

```python
create_notification(uid, "trade_found", title, body,
                    {"league_id": lid, "target_username": opp_username,
                     "give": [...names...], "receive": [...names...]})
```

Signature at `backend/database.py:8439-8447` (`type_` is positional). The mobile bell maps the
row to `data = {type: row.type, ...row.metadata}` (`TopBar.tsx:130-132`), so the same
`resolveNotificationTarget` path serves the row tap — which is what makes the routing table
addition (D18) testable on a simulator even though the push leg is not.

### Copy

**Not resolved here — operator decision [P-5](#8-parameter-table--operator-decisions).** The
plan's draft (`title: "@{username} wants {PlayerName}"`, `body: "They liked {give} for
{receive} · {league_name}"`) mirrors `_match_body`'s shape (`backend/server.py:10065-10070`).
Binding constraints regardless of which option is chosen: **no emoji** (ADR-004, and #225
de-chalked the existing templates), no countdown, no fake urgency, and the copy names concrete
inventory rather than saying "come back" (F10's PRD guardrail, applied at
`backend/server.py:15791-15796`).

---

## 7. Client wiring

| Concern | Mechanism | Failure mode if missed |
|---|---|---|
| Push tap → Trades tab (flag-on path) | D18, `V2_TRADE_KINDS` | `resolveNotificationTarget` returns `null` → **no navigation at all**, no error, no log |
| Push tap → Trades tab (flag-off path) | D19, legacy `tradeKinds` | same, silently, only when `notif.tap_routing_v2` is off |
| Bell row glyph | D21, `ROW_GLYPHS` | generic bell (`DEFAULT_ROW_GLYPH`, `TopBar.tsx:73-76`) — degraded, not broken |
| Bell row tap → Trades tab | none needed — `onRowTap` (`TopBar.tsx:148-155`) already routes through `resolveNotificationTarget`, so D18 covers it | inert row |
| Web inbox row | **none needed** (C8) — generic glyph + inert tap, verified | n/a |
| `push_opened` emission | D20, both tap paths | `push_open_rate` stays `"dark"` (`analytics_queries.py:479`, caveat at `:501`) and the gate's quality is unmeasurable |

**Two cross-client enum values are added** — push `kind` `trade_found` and
`notifications.type` `trade_found` — and **both fail silently** when a client misses them.
That is why they belong in `docs/cross-client-invariants.md` with the failure mode written
down, not just the value.

**Analytics posture, unchanged from the plan:** no new event **name**; `push_sent`
(`analytics_taxonomy.py:117`, fired at `backend/server.py:15403-15407`) gains a new *value* of
`kind`; `push_opened` is **registered and dark** (`:68`, props `:213`) and gets lit for the
first time ever. It is absent from `NON_INTENT_EVENTS` (`analytics_queries.py:60-63`), so by
the deny-list default it lands **INTENT** and enters DAU/WAU/retention on first emission —
[P-7](#8-parameter-table--operator-decisions), and per `HLD-p1.md` §A.4 any change to that
routes into **commit T1**, never into P1-9's commit. Either way the emission date is a metric
seam and belongs in `CHANGELOG.md`.

---

## 8. Parameter table — operator decisions

**None of these is an engineering question.** Defaults below are the plan's recommendations,
carried forward unchanged; they are **not settled**. Each row states the consequence of moving
the value in each direction so the operator is choosing between outcomes, not numbers.

### 8.1 The eight `model_config` knobs (D4)

All Float-typed, all changeable via `PUT /api/admin/config` **without a deploy**, all read at
call time.

| Key | Recommended | Lower means | Higher means |
|---|---|---|---|
| `trade_found_cooldown_days` | **7.0** | more than one `trade_found` a week per user — the exact "three mediocre pushes" failure the gate exists to prevent | fewer, rarer pushes; a genuinely new second like inside the window is never surfaced by push (the deck still shows it) |
| `trade_found_global_quiet_days` | **5.0** | `trade_found` can land next to `deck_replenished`/winbacks/digest — two "we found you trades" pushes in one week; **0 disables the cross-kind rule entirely** | the kind is crowded out by any other push; at ≥7 a weekly digest subscriber may never receive one |
| `trade_found_max_age_days` | **7.0** | only very fresh likes qualify — fewer candidates, higher truthfulness | likes older than the 7-day `TradeCard` expiry qualify: "a leaguemate wants X" about a card that has already expired |
| `trade_found_active_days` | **21.0** | narrower recency; a user away 3 weeks gets nothing (they are a winback case, which has its own kind) | reaches dormant users with a transactional-feeling push instead of a winback |
| `trade_found_grace_hours` | **48.0** | shrinks the P0-1 backfill guard; at low values a freshly-permissioned user could receive `trade_found` as an early push | safer, at the cost of delaying legitimate pushes to genuinely new users |
| `trade_found_min_like_age_minutes` | **30.0** | a like from an in-progress swipe session counts as a considered signal | more settling time; a same-day like may miss the tick |
| `trade_found_max_per_tick` | **50.0** | a hard ceiling that binds sooner; excess users are counted, not lost | a larger single-tick blast radius if a gate bug ever fires wide |
| `trade_found_dry_run` | **1.0 (on)** | `0` sends for real from the first tick, with no observed firing rate | — (binary) |

### 8.2 The consequential ones

| ID | Decision | Options | Blocks | Notes |
|---|---|---|---|---|
| **P-1** | **Which pref bucket does `trade_found` live in?** (D5) — *also `HLD-p1.md` **RL-3*** | **(a) `trade_matches`** — default ON for anyone who granted push; maximum reach. **(b) `reengagement`** — default OFF via `notif.reengagement_default_off`, the `deck_replenished` treatment; ~nobody receives it. **(c) unmapped/transactional** — no bucket gate; the user cannot turn it off separately | **BUILD — this changes the file list and the sim tier** | **(a) additionally requires D23(b) (the Settings row `sub` copy) and D24 (a fourth `PushPrimingModal` consent bullet), and escalates the sim gate from tier 2 to tier 1** because Settings becomes a visible screen change. (b) requires neither. The plan recommends (a) *conditional on the gate staying counterparty-intent-only*, and records (c) as "do not do this" — a push a user cannot switch off is how the permission gets revoked. **Bucket strength and gate strength are one decision**: if the gate ever widens (P-2), the kind moves to `reengagement` in the same change |
| **P-2** | **Gate strength** — *`HLD-p1.md` **PR-16*** | (a) counterparty intent only; (b) + a dual-board lane riding F10's existing generation; (c) + a model-score threshold | **BUILD — the entire gate design** | The plan recommends A for v1, B specced and deferred, **C never** (a numeric threshold on a model score is a product judgement disguised as a parameter). Not resolved here |
| **P-5** | **Push copy, and how much it reveals about a leaguemate** — *`HLD-p1.md` **PR-17** + **PV-4*** | (a) name the leaguemate and the player; (b) name the player only; (c) neutral | **BUILD — §6 copy and the inbox row** | Privacy dimension: a lock-screen banner naming a leaguemate exposes their trade interest to anyone glancing at the phone. In-app this is already disclosed (`TradeCard.tsx:344-347`). Not resolved here |
| **P-6** | **Bell-row glyph** (D21) | the `match` glyph in ice, like the match family, or its own stroke icon | BUILD (one map entry) | Design-system constrained either way: Chalkline tokens, no emoji |
| **P-7** | **`push_opened` INTENT or NON_INTENT** — *`HLD-p1.md` **AN-7*** | leave INTENT (deny-list default) or add to `NON_INTENT_EVENTS` | release; **routes into T1 if changed** | `analytics_queries.py` is P0-7-owned and frozen after T1 — P1-9 must not edit it |
| **P-8** | **Rollout and graduation** — *`HLD-p1.md` **RL-4*** | see PRD §Rollout | release | Governs the post-merge window, not the build |

**Build-blocking dependency, stated loudly:** **P-1 must be answered before B2 starts.**
It decides (i) whether `SettingsScreen.tsx` copy and `PushPrimingModal.tsx` are in the diff at
all, (ii) whether B2 must claim `PushPrimingModal.tsx` (no other item touches it, but it is
not in B2's HLD ownership list), (iii) whether the simulator gate is tier 2 or tier 1, and
(iv) whether `capture/settings.yaml` and `capture/settings@two-leagues.yaml` join the R1
re-capture. Building before it is answered means building the wrong thing twice.

---

## 9. Failure and no-op paths

Every one of these is a **silent, counted no-op**. Nothing in this feature raises to a user,
and nothing can fail the cron tick.

| Path | Behaviour |
|---|---|
| Flag off | `_run_trade_found_pass` never called; response byte-identical; zero DB reads |
| Dry-run on | Full gate computed; `dry_run_would_push` incremented; **no inbox row, no push, no `notification_events_log` row** (C12) |
| `load_active_deck_user_leagues` raises | logged, `stats` returned as-is with `errors` — mirrors F10's `:15769-15771` |
| Any per-user exception | caught inside the loop, `errors += 1`, next user — mirrors F10's `:15805-15807` |
| The whole pass raises | caught at the `cron_daily_tick` hook (D17); `trade_found: {"error": …}` in the response; **the winback loop above is untouched** |
| `_send_typed_push` raises internally | already swallowed at `:15410-15412`; returns `"error"` after C4 |
| Expo unreachable / non-2xx | `_send_expo_push` swallows and logs (`:15276-15277`), but `log_notification_send` still runs (`:15401`) — the cap is charged for an undelivered push. **Pre-existing for all 13 kinds; not changed here.** Recorded so it is not rediscovered as a P1-9 bug |
| Quiet hours | `queue_notification` row with `deliver_after` = next local 08:00 (`:15380-15387`); the hourly drain (`:15966-15994`) collapses it into one `bundle_summary` and back-logs the original kind + `dedup_key`, so the caps stay accurate |
| No device tokens | dispatcher returns early (`:15391`); **the inbox row still exists** — the user learns via the bell |
| Bucket off | dispatcher returns early (`:15369-15371`); **the inbox row still exists** |
| tz unresolvable | `_local_hour_in_quiet_window` returns `False` (`:15285-15286`) and `_next_8am_utc` falls back to 13:00 UTC (`:15304-15309`) — unchanged |
| Client missing the kind | `resolveNotificationTarget` → `null` → no navigation, no error (mobile); generic glyph + inert tap (web, C8) |
| Timestamp shapes | `trade_decisions.created_at` is naive-UTC; `trade_impressions.shown_at` carries `+00:00`. **Reuse the idiom `load_active_deck_user_leagues` already documents** (`backend/database.py:4260-4262`: both compare correctly against the naive prefix lexically). Do not invent a new comparison |

---

## 10. Re-verify after P0 merge

**Run before B2's first edit**, per `HLD-p1.md` §G. Answer every row **in writing in
`scope-p1-9.md`**. A row that comes back "the premise no longer holds" **stops the build and
returns the item to planning** — it is not patched around at the keyboard.

### 10.1 Universal (HLD §G.0)

- [ ] `git fetch origin && git rev-parse origin/main` — record the sha in the scope block.
- [ ] P0-1, -2, -3, -5, -6, -7, -8/9 commits present on `origin/main`.
- [ ] Rebase the P1 branch; resolve nothing blind.
- [ ] **Re-read `living-memory/DECISIONS.md`, `GOTCHAS.md`, `MISTAKES.md`, `OPEN_QUESTIONS.md`
      for the next free IDs.** Nine claimants exist for `D-011`; **do not use any ID printed in
      a plan.** Allocation is at write time in merge order (T1 → P1-7 → P1-10 → P1-1/2 → P1-5 →
      **P1-9** → P1-11 → P1-3).
- [ ] Confirm `mobile/node_modules` is still symlinked. **Never run `npm install`.**
- [ ] Confirm wave A has merged and released `server.py`, `deepLinks.ts`,
      `SettingsScreen.tsx`, `seed_ui_test_db.py`.

### 10.2 P1-9 specific (HLD §G.6, extended)

- [ ] **Re-locate every `server.py` anchor**: `_send_typed_push` (`:15344`), `_NOTIF_FREQ_CAPS`
      (`:15212`), `_NOTIF_DEDUP_CAPS` (`:15230`), `_freq_cap_blocks` (`:15312`),
      `_inject_likes_you_cards_impl` (`:2813`), `cron_daily_tick` (`:16060`). P0 edited six
      other functions in this file **and P1-7 edited the unlock ladder in wave A**.
- [ ] Confirm `server.py:6218-6255` (the first-unlock fan-out) is P0-1's and P1-7's, and that
      **P1-9 adds nothing to it**.
- [ ] `deepLinks.ts` — **two** writers moved it (P0-3, then P1-1/2). Re-grep `V2_TRADE_KINDS`;
      do not edit `:262` by line.
- [ ] `SettingsScreen.tsx` — **three** writers moved it (P0-5 extracted the inline Sleeper form
      into `LinkSleeperSheet`; P1-10 edited `:488`/`:1261`). Re-grep the notification bucket
      rows and the `Row` helper, and confirm `Row` still forwards `testID` to the `Switch`.
- [ ] `seed_ui_test_db.py` — P0-1 and P1-7 both edited it. **Re-run the seeder end to end**
      rather than trusting a clean merge.
- [ ] `feature_flags.py` `notif.*` block and `config/features.json` `notif.*` keys — confirm
      positions after P0-3 B5/B6 added `growth.invite_join_link`.
- [ ] Confirm `push_opened` is still registered at `analytics_taxonomy.py:68` with `dedup_key`
      in its prop row (`:213`). If P0-7 changed the row, re-check before wiring D20.
- [ ] **`web/js/app.js` notification renderer** — HLD §G.6 lists this as blocking. It is
      **answered in C8** at `ab9368f`; re-confirm `notifTypeIcon`'s `return ICON.bell` fallback
      and that `clickNotif` still only branches on the three legacy types. If P0 changed either,
      R-6 reopens.
- [ ] **New rows this LLD adds to the checklist:**
  - [ ] `load_device_tokens_for_users` still selects only three columns (C2 still needed).
  - [ ] `_freq_cap_blocks` still short-circuits on the dedup branch (C1 still needed).
  - [ ] `_send_typed_push` still returns `None` and **no call site reads a return value** (C4).
  - [ ] `_inject_likes_you_cards_impl`'s predicate is still at the shape §4 extracts, and
        `trade.likes_you` is still `true` (`config/features.json:30`).
  - [ ] `notif.reengagement_default_off` is still `true` and `deck.replenishment` still `true`
        — the true problem statement (§1.0) depends on both.
  - [ ] `docs/plans/mobile-testing/lld.md:313` still reserves `topbar.bell` and `:329` still
        reserves `settings.notif.<pref>` (C6).
  - [ ] `notif.tap_routing_v2` is still `true` in `config/features.json` **and** in the flags
        fixture the new flow resolves (C10) — the Maestro flow cannot render without it.
  - [ ] Re-read `PushPrimingModal.tsx`'s bullet list; P0-1 exercises the primer and may have
        edited the copy. D24's premise depends on the current text.

---

## Appendix — what this document deliberately does not do

- **It resolves no product, copy, privacy or threshold question.** All eight live in
  [§8](#8-parameter-table--operator-decisions) with the plan's recommendation attached and
  marked as a recommendation.
- **It invents no new design.** The only additions to `plan-p1-9.md` are the twelve
  corrections in [§1](#1-corrections-to-the-plan) — each one a place where the plan is wrong or
  silent against code read at `ab9368f` — and the mechanisms those corrections force
  (a loader, a return status, a call-time cap read, a primitives-only predicate signature).
- **It edits no source file.**
- **It does not re-litigate the merge order or the wave plan.** Those are `HLD-p1.md`'s.
