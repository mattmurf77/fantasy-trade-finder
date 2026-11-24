# League pass — LLD

Owner: eng review pending. Date: 2026-11-22. Status: BUILT (server, phase 1, dark); corrected to the build.
Implements [hld.md](hld.md) against [prd.md](prd.md) R-numbers. File and line
references are to `feat/paid-launch` at `4dba6dda`; re-check them before building.

- [1. Flags and knobs](#1-flags-and-knobs)
- [2. Schema](#2-schema)
- [3. `backend/league_pass.py`](#3-backendleague_passpy)
- [4. Gate changes](#4-gate-changes)
- [5. `backend/entitlements.py` changes](#5-backendentitlementspy-changes)
- [6. Routes](#6-routes)
- [7. Store and RevenueCat setup](#7-store-and-revenuecat-setup)
- [8. Mobile changes](#8-mobile-changes)
- [9. Analytics](#9-analytics)
- [10. Edge cases](#10-edge-cases)
- [11. Test plan](#11-test-plan)
- [12. Docs to update](#12-docs-to-update)
- [13. To settle before building](#13-to-settle-before-building)

## 1. Flags and knobs

**Flag** — `backend/feature_flags.py`, in the monetization block after
`monetize.season_pass`, and `config/features.json` (false). The release fixture
`backend/tests/fixtures/flags/release.json` keeps it false.

```python
"monetize.league_pass",        # league pass: one buyer covers a league (docs/plans/monetization/league-pass/)
```

**`model_config` knobs** (seeded; the inline fallback must match the seed, G-064)

| Key | Default | Meaning |
|---|---|---|
| `league_pass_repoint_cooldown_days` | 30 | Minimum days between buyer re-points |
| `league_pass_seat_allowance` | 2 | Covered accounts allowed above `total_rosters` |
| `league_pass_intent_ttl_minutes` | 60 | How long a chosen league stays usable for a purchase |

**Allow-list (as built).** `model_config` is float-only, so the league allow-list is the
env var `LEAGUE_PASS_LEAGUE_ALLOWLIST` (comma-separated league ids, read live; unset or
empty means every league), like `FOUNDER_ACCOUNTS`.

## 2. Schema

Both tables are new, so `metadata.create_all` creates them on both dialects.

### 2.1 `league_passes`

```python
league_passes_table = Table("league_passes", metadata,
    Column("id",               Integer, primary_key=True, autoincrement=True),
    Column("origin",           String,  nullable=False),  # 'purchase' | 'comp'
    Column("buyer_user_id",    String),                   # working key; NULL for comp
    Column("buyer_account_id", String),
    Column("product_id",       String),                   # ftf_league_annual[_t1|_t2]; NULL for comp
    Column("league_id",        String,  nullable=False),  # leagues.sleeper_league_id (platform-native)
    Column("platform",         String,  nullable=False),  # 'sleeper' | 'espn' | 'mfl'
    Column("status",           String,  nullable=False, server_default="active"),
                                                          # active | released | ended
    Column("tier",             Integer),                  # 0 | 1 | 2 at first bind
    Column("comp_expires_at",  String),                   # ISO UTC; comp only
    Column("show_buyer",       Integer, nullable=False, server_default="0"),
    Column("bound_at",         String,  nullable=False),
    Column("released_at",      String),
    Column("release_reason",   String),   # repoint | rollover | transfer | ended | refund |
                                          # deleted | admin
    Column("note",             String),   # operator note on a comp pass
    Column("created_at",       String,  nullable=False),
    Column("updated_at",       String,  nullable=False),
    Index("ix_league_passes_league", "league_id", "status"),
    Index("ix_league_passes_buyer",  "buyer_user_id", "status"),
)
```

- One active row per `league_id`, and one active `purchase` row per `buyer_user_id`.
  Both are enforced as partial unique indexes and re-checked in the bind transaction.
- A re-point releases the current row and inserts a new one. The cooldown reads the
  buyer's latest `bound_at`, leaving out the binds a rollover made (a rollover's new row
  is bound at the instant its predecessor was released for `rollover`), so a rollover
  never uses the cooldown. No separate history table.
- `status` is reporting state. Whether a pass is live is decided at read time (§3.2).

### 2.2 `league_pass_intents`

```python
league_pass_intents_table = Table("league_pass_intents", metadata,
    Column("id",                Integer, primary_key=True, autoincrement=True),
    Column("user_id",           String,  nullable=False),
    Column("league_id",         String,  nullable=False),
    Column("platform",          String,  nullable=False),
    Column("tier",              Integer, nullable=False),   # 0 | 1 | 2
    Column("product_id",        String,  nullable=False),   # the product offered
    Column("paid_annual_count", Integer, nullable=False),   # the snapshot behind the tier
    Column("created_at",        String,  nullable=False),
    Column("expires_at",        String,  nullable=False),
    Column("consumed_at",       String),
    Column("consumed_event_id", String),
    Index("ix_lpi_user", "user_id", "consumed_at"),
)
```

A user's newest unconsumed, unexpired intent is the one that counts.

### 2.3 `leagues.previous_league_id`

New nullable `String` column, added through the existing `migration_cols` path. League
sync writes Sleeper's `previous_league_id` into it. Today the field is read only in
`backend/season_history.py:199`.

### 2.4 Account deletion and export

`league_passes` and `league_pass_intents` carry `user_id`, so both join account deletion
and the export, in `backend/accounts.py` (as built): intents are in
`_ADDITIONAL_PRIVATE_TABLES` (deleted and exported); `_delete_user_data` calls
`league_pass.release_for_deletion`, which releases the buyer's active pass with
`release_reason='deleted'` and blanks the buyer ids on all their pass rows; `league_passes`
is exported under `buyer_user_id`.

## 3. `backend/league_pass.py`

New module. Plain functions, testable without Flask.

### 3.1 Membership

```python
def is_member(user_id: str, league_id: str, platform: str) -> bool
```

- `sleeper`: a `league_members` row with this `league_id` and the user's Sleeper id. An
  `acct_*` working key is first resolved to its Sleeper id through `accounts`.
- `espn` / `mfl`: a `platform_league_bindings` row for `(user_id, league_id)`.
  `league_members` is not used, because it holds a synthetic id for every team that no
  app user is bound to (`database.replace_espn_league_members`).

```python
def covered_members(league_id: str, platform: str) -> list[str]
```

The app users who are members, oldest first, cut at
`total_rosters + league_pass_seat_allowance` (R7). As built, "oldest" is stable: Sleeper orders by the member's app account age (`users.created_at`,
written once; a missing one sorts first), then user id, because `league_members.id` is
renewed by SQLite's `INSERT OR REPLACE` sync; ESPN / MFL by the binding's `created_at`
(kept on re-link), then user id.

A Sleeper co-owner has no row here: `league_members` lists only a roster's primary
owner. As built, a co-owner rides that owner's seat (covered exactly when the owner is,
§4.1) and takes no seat of its own, so it is not in `covered_members` and not in
`covered_count`. The allowance absorbs extra accounts that do hold their own row: ESPN
and MFL co-managers who each bind the same team, and turnover. So the cap bounds
`covered_members`, not every covered account: a 12-team Sleeper league with allowance 0
covers its 12 owners plus their co-owners. The server stores no co-owner list (ADR-012:
a co-owner is an alias of the roster's owner), so counting them would need a schema
change or a Sleeper read per coverage check; this reads PRD R7 as capping stored
members, which differs from its "co-owner allowance" wording.

### 3.2 Coverage

```python
@dataclass(frozen=True)
class Coverage:
    pass_id: int
    league_id: str
    covered_until: str        # ISO UTC
    role: str                 # 'buyer' | 'member'

def covers(user_id: str, league_id: str) -> Coverage | None
```

In order, returning `None` at the first failure:

1. The active `league_passes` row for `league_id`.
2. The allow-list knob is empty or contains `league_id`.
3. The pass is live: for `origin='purchase'`, the buyer has an active row with source
   `league_pass_iap` in `entitlements._active_rows(buyer)` and `covered_until` is its
   `expires_at`; for `origin='comp'`, `comp_expires_at` is in the future.
4. `user_id` is in `covered_members(league_id, platform)`.

Three indexed reads, on gated requests by non-Pro users only. No cross-request cache in
the first version.

```python
def passes_for(user_id: str, *, league_user_id: str | None = None,
               league_id: str | None = None) -> list[dict]
```

Every live pass covering this user, for `/api/me/entitlements`. It starts from the
user's leagues, not from all passes. As built, it also lists a Sleeper co-owner's pass
by the gate's rule (§4.1): in `league_id` only (the route passes the session's active
league), a pass that does not cover `user_id` is tried under `league_user_id`
(`server._league_user_id`), with role `member`. A sole owner (`league_user_id` equal to
`user_id`) reads nothing more. A co-owner still cannot buy: `create_intent`, `bind` and
`repoint` check membership under the user's own id, never the league identity.

### 3.3 Quote and intent

```python
def paid_annual_leaguemates(buyer_user_id: str, league_id: str, platform: str) -> int
```

Counts members other than the buyer who hold an active `pro` row with
`source='apple_iap'`, `product_id='ftf_pro_annual'`, in the production lane
(`granted_by` not prefixed `sandbox:`), whose ledger shows a `NORMAL` period. It reuses
`paywall_gate._period_types` for the last test (R11).

```python
TIERS = ((0, "ftf_league_annual"), (1, "ftf_league_annual_t1"), (2, "ftf_league_annual_t2"))

def tier_for(count: int) -> int          # 0 → 0, 1–2 → 1, 3+ → 2
def create_intent(user_id: str, league_id: str) -> dict
```

Write paths refuse by raising `Refused(reason, **detail)`; a route answers
`409 {"error": reason, **detail}`. `create_intent` refuses, in this order: `not_member`,
`league_not_allowed`, `already_covered`, `already_buyer`, `refund_blocked`. Otherwise it
inserts the intent and returns `{intent_id, product_id, tier, teams, expires_at}`.

### 3.4 Bind, re-point, rollover

```python
def on_billing_event(user_id: str, product_id: str, event_type: str, event_id: str) -> None
def bind(user_id: str, league_id: str) -> dict            # the manual path (R19)
def repoint(user_id: str, league_id: str) -> dict
def follow_rollover(new_league_id: str, previous_league_id: str) -> bool
def comp(league_id: str, days: int, note: str | None) -> dict
def end(pass_id: int, reason: str) -> bool
```

**`on_billing_event`** runs after the projector, for `ftf_league_*` products only, and
only while the flag is on. On an activating event:

1. If the buyer already has an active pass, return. A renewal changes nothing here.
2. Take the buyer's newest usable intent. If there is none, return: the pass is unbound.
3. Re-check `is_member` and that the league has no active pass.
4. Tier check: the intent's `tier` must be at least the purchased product's tier. A
   cheaper product than the snapshot allows is not bound (R20).
5. Insert the row; mark the intent consumed with the event id.

A failure at steps 3 or 4 leaves the pass unbound and logs
`LEAGUE-PASS-UNBOUND user=… reason=…`. The buyer keeps Pro either way.

**`bind`** applies steps 3 to 5 with a fresh tier computed for the league now.

**`repoint`** checks the cooldown, membership and that the target has no pass. It does
not re-check the tier (plan §9). It releases and inserts in one transaction.

**`follow_rollover`** is called by league sync. It moves the pass when the previous
league has one and the buyer is a member of the new league.

## 4. Gate changes

### 4.1 `paywall_gate.verdict`

New keyword arguments `league_id: str | None = None` and (as built)
`league_user_id: str | None = None`. One block, after the account-level check and before
`_held_pro`:

```python
if entitlements.get_entitlements(user_id)["pro"]:
    return None
if league_id and pass_enabled() and _covered(league_id, user_id, league_user_id):
    return PassAllowed(league_id)
held = _held_pro(user_id)
```

`_covered` tries each identity with `league_pass.covers`; a coverage-read exception is
logged and reads as not covered (the hook fails open on an exception, so the read must
not). `league_user_id` is the Sleeper co-owner case: `league_members` stores only a
roster's primary owner, so the hook also passes the session's league identity
(`server._league_user_id`), only when the resolved league is the session's active league.

`PassAllowed` is a small frozen dataclass, like `Preview`. The hook treats it as
"through" and sets `g.paywall_pass_league`. Everything above the block is unchanged, so
an unverified session is still settled before any coverage read (R8), and the preview
is never reached for a covered request (R9).

### 4.2 `LEAGUE_RESOLVERS`

A table in `paywall_gate.py`, keyed like `ROUTES`, naming how each gated rule finds its
league. `server.py` supplies the lookups that need its state, as it does for
`DeckAsk.page_trade_ids`.

As built (each traced to its handler):

| Kind | Reads | Rules |
|---|---|---|
| `active` | The session's active league; **not covered** when the body names a different `league_id` (raw comparison) | `generate`, `pass-reason`, `swipe`, `queue`, `asset-ideas`, `fair-packages`, `standing-offer` |
| `body` | `body.league_id` stripped, else the session's active league | `propose`, `propose-espn`, `propose-mfl`, `respond-mfl` |
| `query` | `?league_id=`, else the session's active league | `GET /api/trades` |
| `session` | The session's active league | Every `/api/overhauls*` rule (both collection rules and every `<overhaul_id>` rule), the four `/api/win-now/*` rules |
| `job` | The league of the deck `/status` names (the honoured `deck`, else `job_id`): the requester's in-process job key, else its stored page row, else its lineage row | `GET /api/trades/status` |
| `match` | The match row's `league_id` | `matches/<match_id>/disposition` |

Deviations from the draft: the `body` rules that act on session state (the session's
members, rosters or deck as well as the body's league) became `active`, because a body
naming the covered league from another session league is a mixed request and must not be
covered. The `overhaul` kind became `session`: overhaul_api's `load()` refuses any row
whose league is not the session's, so the row read adds nothing. `POST /api/overhauls`
is `session` for the same reason (its handler refuses a body league that is not the
session's). The hook parses the body from the cached raw bytes, as the handlers'
forced `get_json` would, without touching Flask's JSON cache.

Rules:

- A gated rule with no resolver fails a new test (§11), the way a rule missing from
  `ROUTES` fails `test_paywall_gate_allowlist.py`.
- A resolver that finds nothing returns `None`, which means not covered.
- A resolver never raises into the hook. An exception is logged and reads as `None`.
  This differs from the entitlement read, which fails open; a pass must not widen
  access on an error.

### 4.3 The league-match check

```python
def _confirm_pass_league(league_id: str | None) -> None
```

As built, it is called at every point a gated handler fixes the league it acts on.
When `g.paywall_pass_league` is set and differs from the handler's league, it aborts
with the ordinary 402 (`gate_reason(user_id, deck=…)`). When the request came through on
account-level Pro, with the flag off, or on a free rule, it returns at once and reads
nothing.

- **The session switch.** `/api/session/init` updates the session in place, so a session
  switched to another league between the hook and the handler would act there.
  `_require_initialized_session` (which every `session` and `active` handler, and both
  installed modules, use) calls it with the session's league for those kinds
  (`_confirm_pass_session_league`).
- **Overhaul and Win Now.** Both modules call their injected `require_session` and then
  read the league themselves. `server.py` injects `_confirm_pass_league` as
  `confirm_pass_league`, and each module calls it where it fixes its league:
  `overhaul_api.py` on the session's league in `overhaul_create_route` and
  `overhaul_active_route`, and on the row's league in `load` (every `<overhaul_id>`
  rule); `win_now_api.py` in `actor`, and on the row's league in the job and scenario
  reads. The request's session view is a per-request copy, so this repeats the
  session-level check today; it keeps each module's own reads bound to the pass league.
- **`swipe` and `pass-reason`.** Both act on a card from the session's trade service,
  which session init builds for one league, or rebuild a card in the body's `league_id`,
  else the session's; the `active` resolver never covers a body naming another league.
  So a card from another league is not reachable today. Both handlers still check the
  card's league (and `pass-reason` the row's league) before any write.
- **`GET /api/trades`.** `league_id` is optional, and without it the handler returns
  cards from every league. For a pass-allowed request the handler forces the filter to
  `g.paywall_pass_league`.

A future gated handler that fixes its league some other way calls it directly.

### 4.4 The hook

`_paywall_gate_hook` resolves the league only after `applies()` is true and only with
the flag on (`server._paywall_pass_league`), so a free route, and every route with the
flag off, still reads nothing new. It passes `league_id` (and the co-owner's
`league_user_id`) to `verdict`, and on `PassAllowed` sets `g.paywall_pass_league` and
records `league_pass_coverage_used` (`paywall_gate.record_coverage_used`, first per user,
league and UTC day: `record_gate_hit`'s bounded in-process de-dupe is the fast path, and
on its miss one indexed read of `user_events` skips the insert when today's row exists,
so a restart or another worker writes no second row; a failure is swallowed). A
resolver failure is not covered. `record_gate_hit` is unchanged (per process).

**A session with no league yet** (sign-in before `/api/session/init`, or a session
restored after a restart). A `session` or `active` rule has no league to resolve, and a
body-named league never stands in for it. With the flag on, `server._paywall_session_pending`
(no reads) tells `verdict`, which, after the pro check and before the preview, returns
`SESSION_PENDING` when `league_pass.passes_for(user)` is non-empty (a read failure is
not covered). The hook raises `_SessionNotInitialized`, so the answer is the handlers'
own 409 `session_not_initialized`, the body a Pro user gets, and no handler runs. Every
handler behind those rules refuses an uninitialized session before acting (a feature-flag
404 is the only earlier answer), so letting the request through would also have been
safe; the hook answers instead so that no future handler can act first, at the cost that
a covered member gets the 409 where a Pro user would get a handler's flag-off 404. The
cost is `passes_for`'s reads (the alias lookup, two membership reads, one pass read, then
`covers` per active pass in the user's leagues), only for verified non-Pro users with the
flag on, on those rules, on a session without a league. A Sleeper co-owner is not
recognised there (its league identity comes with init) and gets today's answer.

## 5. `backend/entitlements.py` changes

```python
_BILLING_SOURCES = ("apple_iap", "stripe", "founder_iap", "season_pass_iap",
                    "league_pass_iap", "trial")

def _product_mapping(product_id):
    …
    if pid.startswith("ftf_league_"):
        return "pro", "league_pass_iap"
    return "pro", "apple_iap"
```

- Add `league_pass_iap` to the source comment on `entitlements.source` in
  `database.py:3274`.
- `ingest_billing_event` calls `league_pass.on_billing_event` after `_project` succeeds,
  wrapped so a bind failure never fails the webhook.
- `_project_transfer`: after re-keying, re-key the buyer's active pass to the new owner
  when they are a member of the league, else release it.
- `_held_pro` needs no change: a `league_pass_iap` row reads as paid, which is right for
  the buyer. A covered member has no row.
- `is_founder` needs no change.
- The sandbox lane needs no change. A sandbox purchase binds like any other and lapses
  within 24 hours.

## 6. Routes

Every rule below gets a row in `paywall_gate.ROUTES`.

| Method and rule | Auth | Class | Body / result |
|---|---|---|---|
| `POST /api/league-pass/intent` | Verified session | `FREE` | `{league_id}` → `{intent_id, product_id, tier, teams, expires_at}` or `409 {"error": reason}` |
| `GET /api/league-pass` | Verified session | `FREE` | `{pass: {league_id, platform, tier, covered_until, will_renew, covered_count, can_repoint_at, show_buyer} \| null, unbound}` |
| `POST /api/league-pass/bind` | Verified session | `FREE` | `{league_id}`; for an unbound pass → the `GET` view |
| `POST /api/league-pass/repoint` | Verified session | `FREE` | `{league_id}` → the `GET` view, or `409 {"error": "cooldown", "can_repoint_at"}` |
| `PUT`, `POST /api/league-pass/settings` | Verified session | `FREE` | `{show_buyer: bool}` → the `GET` view (`league_pass.set_show_buyer`) |
| `POST /api/admin/league-pass/comp` | `X-Cron-Secret` | `NEVER_GATE` | `{league_id, days, note}` |
| `GET /api/admin/league-pass` | `X-Cron-Secret` | `NEVER_GATE` | `?league_id=` / `?user=` |
| `DELETE /api/admin/league-pass/<int:pass_id>` | `X-Cron-Secret` | `NEVER_GATE` | Ends a pass |

The `/api/league-pass/*` routes return `404 {"error": "feature_disabled"}` while the flag
is off (an unverified session is answered first by the verified gate's 403, as on other
flagged routes). A refusal is `409 {"error": reason, **detail}`. The admin routes are not
flag-gated, like the grant routes: comp → `201` the row; list → `{passes}` (each with
`live_until`); end → `{ended: id}` or 404. `will_renew` is false when the buyer's latest
renewal-state event for the product in `subscription_events` is a `CANCELLATION`.

### 6.1 `GET /api/me/entitlements`

With the flag on and a verified session, one field is added:

```json
"league_passes": [
  {"league_id": "…", "platform": "sleeper", "role": "member",
   "covered_until": "2028-01-15T00:00:00+00:00", "buyer_display": null}
]
```

- `role` is `buyer` or `member`. `buyer_display` is the buyer's display name only when
  `show_buyer` is 1; otherwise null.
- An unverified session gets `[]`, through `empty_entitlements()`.
- `pro`, `sources` and `expires_at` do not change meaning.

### 6.2 `GET /api/paywall/config`

With the flag on **and** `caps=league_pass` in the query, one block is added. The launch
binary sends no `caps`, so it never receives it.

```json
"league_pass": {
  "offering": "league",
  "renews_at_price": "$99.99",
  "products": [
    {"product_id": "ftf_league_annual",    "tier": 0, "display_price": "$99.99"},
    {"product_id": "ftf_league_annual_t1", "tier": 1, "display_price": "$84.99",
     "promo_offer_id": "league_t1_y1"},
    {"product_id": "ftf_league_annual_t2", "tier": 2, "display_price": "$69.99",
     "promo_offer_id": "league_t2_y1"}
  ]
}
```

The existing `products` list is untouched. The strings and ids are a cross-client
contract (`docs/cross-client-invariants.md` § Paywall config).

## 7. Store and RevenueCat setup

**App Store Connect**, group "Fleeced Pro". All three products share one level, above
the individual plans. Family Sharing and multiseat stay off.

| Product | Standard price | Introductory offer | Promotional offer |
|---|---|---|---|
| `ftf_league_annual` | $99.99 / year | None | None |
| `ftf_league_annual_t1` | $99.99 / year | Pay up front, 1 year, $84.99 | `league_t1_y1`: pay up front, 1 year, $84.99 |
| `ftf_league_annual_t2` | $99.99 / year | Pay up front, 1 year, $69.99 | `league_t2_y1`: pay up front, 1 year, $69.99 |

**RevenueCat**

- Attach all three to the `pro` entitlement.
- Put them in a new offering `league`. Keep them out of the default offering:
  `PaywallScreen.tsx:290` renders every configured product that matches a package.
- Upload the in-app purchase key so the SDK can sign promotional offers.
- The webhook and its secret are unchanged.

## 8. Mobile changes

All in `mobile/src/`. JavaScript only; no new native module.

| File | Change |
|---|---|
| `api/billing.ts` | `EntitlementsResponse.league_passes`; `PaywallConfig.league_pass`; `getPaywallConfig` sends `caps=league_pass`; functions for the `/api/league-pass/*` routes |
| `api/purchases.ts` | A wrapper for a promotional-offer purchase (get the signed offer, then purchase with it), behind the same fail-safe and identity-ready rules as `purchasePackage`; `getOfferings` access to the `league` offering |
| `state/useEntitlements.ts` | Store `leaguePasses`; add `proForLeague(leagueId)`: `pro` or a live pass for that league |
| `screens/TradesScreen.tsx:5527` | Read `proForLeague(activeLeagueId)` in place of `pro` |
| `screens/WinNowScreen.tsx:101` | The same |
| `components/ShopOffersBody.tsx:445` | The same, including the refetch-on-entitled effect |
| `components/SendInSleeperButton.tsx:72` | `sendPreCheck(resume, leagueId)`; the MFL and ESPN buttons pass their league |
| `screens/LeaguePassScreen.tsx` (new) | Pick a league → `intent` → price, teams and renewal price → purchase → confirmation. Handles the refusal reasons and an unbound pass |
| `screens/PaywallScreen.tsx` | A separate entry to `LeaguePassScreen`, below the plans (R30); the other-league line when the user is covered elsewhere (R26) |
| `components/SubscriptionSection.tsx` | Member: covered league and date (R25). Buyer: league, renewal, covered count, move, show-my-name (R27, R28) |
| `components/PaywallGateNotice.tsx` | No logic change. It still reads no entitlement field |
| `copy/monetization.ts` | New `mon.lp.*` keys, verbatim from legal. No hard-coded strings elsewhere |
| `tests/check-league-pass.js` (new) | Structural suite, in the style of `check-paid-launch.js` |

**As built (phase 2, `feat/league-pass-client`; [scope-client.md](scope-client.md)).**
Where the build differs from the table above:

- `proForLeague` is not a method on the `useEntitlements` store. The store holds
  `leaguePasses` (and `sources`); the rule is the pure `utils/leaguePass.proForLeague`
  (pro, or a live pass for that league, with the client flag on), read through
  `state/useLeaguePass.useProForLeague` / `proForLeagueNow`. This keeps the store's import
  set, which two suites execute, unchanged, and puts the flag read with the callers.
- `sendPreCheck(resume, leagueId?, afterAsk?)`: the league is the second argument and
  `afterAsk` (added on main after this LLD) third.
- `ShopOffersBody` has no entitlement read on this branch (its refetch-on-entitled
  effect is on `feat/paid-launch`, not merged here). `check-league-pass.js` 7a requires
  `useProForLeague` there as soon as it reads `useEntitlements`.
- `PaywallGateNotice` does not exist on this branch; nothing to change.
- Settings › Subscription shows the member's league and date, the buyer's league and a
  "Manage league pass" row, and an unbound pass's row, from memory only (the Settings
  hub fires no requests). The buyer's renewal state, covered count, Move with its
  cooldown date and the name toggle need `GET /api/league-pass`, so they are on
  `LeaguePassScreen`'s manage view, one tap away.
- R29's notice is a new `components/LeaguePassCoveredNotice` on TradesScreen, keyed
  per user and league in device storage.
- R38 needed no change: the delete-account dialog's sub-note ("Deleting your account
  doesn't cancel an active subscription…") already shows to every account, a pass buyer
  included, with no subscription condition (legal 5c).
- The `mon.lp.*` copy is placeholder, marked pending legal review.

**Purchase path in `LeaguePassScreen`**

1. `createIntent(leagueId)` returns the product for the league's tier.
2. Tier 0: `purchasePackage`.
3. Tier 1 or 2: `checkIntroEligibility(product)`. Eligible → `purchasePackage`, and the
   introductory price applies. Not eligible → the promotional-offer wrapper with the
   config's `promo_offer_id`.
4. After the purchase, refresh entitlements until `league_passes` shows the buyer's
   pass, or fall back to the choose-a-league state.

As built: the path and its prices are resolved before the quote shows
(`utils/leaguePass.purchasePlan`). "Eligible" means StoreKit answers ELIGIBLE and the
product carries an introductory price. The promotional offer is signed at quote time
(`getPromotionalOffer` on the product's `discounts[]` entry with the config's
`promo_offer_id`) and its own price is shown. If it cannot be signed, the quote shows
the full price with a notice and Continue at full price / Cancel. The refresh is 6
polls, 2.5 s apart; after them `GET /api/league-pass` decides (unbound → choose a
league; nothing yet → "can take a few minutes").

The routing rule in `usePaywallGate.ts` is not touched: it still reads no entitlement
field. The pre-checks above are the existing `pro` pre-checks made league-aware.

## 9. Analytics

New events, pending the taxonomy review (`backend/analytics_taxonomy.py`):

| Event | When | Props |
|---|---|---|
| `league_pass_quote_viewed` | An intent is created | `tier`, `platform`, `teams` |
| `league_pass_bound` | A pass row is inserted | `origin`, `tier`, `platform`, `via` (webhook, manual, repoint, rollover) |
| `league_pass_ended` | A pass stops being live | `reason` |
| `league_pass_coverage_used` | A gated request is allowed by a pass | `family`; first per user, league and day, like `record_gate_hit` |

Purchases reuse `paywall_purchase_initiated`, `_completed` and `_failed` with the new
product ids. `entitlement_granted` already fires for the buyer's row.

## 10. Edge cases

| Case | Behaviour |
|---|---|
| Two members buy for the same league at once | The first bind wins. The second buyer's pass is unbound; the app asks them to choose another league. |
| The app closes during purchase | The webhook binds from the intent (R18). |
| The intent expired before the webhook | Unbound; manual bind. |
| A member cancelled their annual plan between the quote and the purchase | The intent's snapshot stands. |
| A discounted product bought with no intent | Manual bind recomputes the tier; a league that no longer qualifies is refused with `tier_mismatch`. |
| The buyer upgrades from an individual plan | Apple prorates. The old row expires through its own events. Event shape to confirm (§13). |
| The buyer downgrades to an individual plan | Takes effect at renewal. The pass ends when the league row expires. |
| A covered member also buys an individual plan | Allowed. Both apply. |
| A covered member in two covered leagues | Two entries in `league_passes`. |
| The league is removed or unlinked in the app | Coverage has no members to cover; the buyer can move the pass. |
| A co-owner takes the seat count over the cap | A Sleeper co-owner takes no seat: it is covered exactly when its roster's primary owner is, in the session's active league only, and `league_passes` lists it there as `member`. ESPN / MFL co-managers each hold a binding: the newest account past the cap is not covered. |
| An unverified session in a covered league | Settled before coverage is read: the route's 403 or `verify_required`. |
| A covered member's session has no league yet | `session` / `active` rules: the handlers' 409 `session_not_initialized`, from the hook (§4.4). Other kinds resolve as usual. |
| A re-sync renews a member's `league_members.id` | No change to who holds a seat: seats follow account age (§3.1). |
| The demo session | Unchanged; exempt on deck routes. |
| A web request | Coverage applies wherever the gate applies, so only when the web knob is on. |
| A comp pass and a purchase for the same league | The purchase is refused as `already_covered` until the comp ends. |

## 11. Test plan

**Backend unit** (new files unless noted; as built, routes also have
`test_league_pass_routes.py`)

- `test_league_pass_coverage.py`: each of the four conditions in §3.2 alone turns
  coverage off; expiry, refund and grace follow the buyer's row; the seat cap; the
  allow-list; comp expiry; Sleeper, ESPN and MFL membership.
- `test_league_pass_bind.py`: the webhook binds from an intent; no intent → unbound; a
  cheaper product than the snapshot → unbound; one pass per league and per buyer; the
  cooldown; rollover does not use the cooldown; transfer.
- `test_league_pass_tiers.py`: only paid annual production rows count; trial, monthly,
  comp, promo and sandbox rows do not; the buyer does not count themselves.
- `test_paywall_league_resolvers.py`: every `GATED` rule in `ROUTES` has a resolver; each
  resolver returns the league its handler acts on; an unresolvable league is not covered;
  a resolver exception is not covered.
- `test_paywall_gate_pass.py`: a covered request passes and writes no `paywall_previews`
  row; the same member in another league gets the ordinary 402; a body naming the
  covered league on a request acting on another league gets 402; an unverified session
  gets the same answer with and without a pass; flag off is byte-identical.
- `test_paywall_gate_allowlist.py` (existing): the new rules are classified and the
  gated set is unchanged.
- `test_entitlements.py` (existing): `ftf_league_*` maps to `league_pass_iap`.

**Mobile structural** — `tests/check-league-pass.js`: the four pre-check sites use
`proForLeague`; no hard-coded copy; the config request carries `caps`; the flag-off path
renders nothing new. Sabotage each check red, then restore, as the paid-launch suite does.

**Sandbox, on device**

1. A never-subscribed buyer, tier 1: the introductory price shows and is charged.
2. A current individual subscriber, tier 1: the promotional offer applies on upgrade.
3. A second account in the league is covered; the same account in another league gets
   the paywall.
4. Expiry (accelerated sandbox renewal): coverage ends for the second account.
5. Refund: coverage ends.
6. The launch binary: no pass row appears on its paywall.

## 12. Docs to update

| Doc | Change |
|---|---|
| `docs/api-reference.md` | The new routes; the two changed responses |
| `docs/data-dictionary.md` | The two tables; `leagues.previous_league_id`; the new source |
| `docs/config-reference.md` | The flag, the three knobs and env `LEAGUE_PASS_LEAGUE_ALLOWLIST` |
| `docs/cross-client-invariants.md` | Product ids, offer ids, the `league_pass` config block, `league_passes` |
| `docs/glossary.md` | League pass, covered member, buyer, re-point |
| `docs/runbook.md` | Comp, list and end a pass; the unbound-pass support case |
| `docs/plans/monetization/README.md` | A league-pass row |
| `living-memory/LLD.md`, `HLD.md` | The derived-coverage rule and the league-match check |
| ADR / `DECISIONS.md` | Hybrid coverage; derived, not stored |
| `mobile/src/screens/CLAUDE.md`, `state/CLAUDE.md`, `api/CLAUDE.md` | The new screen, selector and wrappers |

## 13. To settle before building

Operator answers of 2026-11-22 are recorded against each item.

Nothing is open. The design proceeds on these answers.

**Checked after release, not before**

3. **Refund events.** The projector acts on `REFUND`. The first real refund's row in
   `subscription_events` shows whether RevenueCat sends that or `CANCELLATION` with a
   customer-support reason. This also affects the individual plan.
4. **Upgrade events.** The event sequence for an upgrade from `ftf_pro_annual` to a
   league product, and that the old row ends cleanly. Read from the first sandbox
   upgrade in phase 2.
1. **Promotional offer on an upgrade.** Not verified, by decision. The design assumes a
   current subscriber can take one on a different product in the group. The first
   sandbox upgrade in phase 2 shows whether that holds. If it does not, the client
   falls back to the standard price: an existing subscriber pays $99.99, and the tiers
   then reach only buyers who have never subscribed.

**Closed**

2. **Unproven team links.** Accepted as is. A public ESPN league and an MFL league
   linked without a login let a user pick any team with no proof of ownership
   (`espn_link`, `mfl_link`), so someone outside a covered league could be covered, up
   to the seat cap. Coverage does not require a proven link. Covered accounts per
   league are measured.
5. **Introductory eligibility.** Not verified, by decision. The client asks the SDK for
   eligibility at purchase time and picks the offer route from the answer.
6. **Win Now resolvers.** Traced. All four rules act on the session's active league and
   refuse any other (§4.2).
7. **`GET /api/overhauls`.** Traced. It returns the one active overhaul for the
   session's active league. It is not cross-league.
8. **Ending notices.** Dropped. No notice is sent to members about a pass ending. The
   end date in Settings is the only signal.
9. **MFL league ids across seasons.** Treated as stable. The app stores the bare id and
   the season separately, and third-party integration docs say ids usually carry over.
   The operator expects them to change. If a renewed league does get a new id, the
   buyer moves the pass, and the operator can waive the cooldown.
