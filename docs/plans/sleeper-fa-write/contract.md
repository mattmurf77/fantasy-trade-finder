# Free-agent moves (D1): the client–server contract

> The wire contract between the 11-06 binary's claim sheet and the D1 server. The binary ships dark, so **the server must honour every field below exactly as written**; the client can't change after 11-06. Fixed by `platforms-eng` on 2026-11-01 from the scope block (`docs/plans/sleeper-fa-write/scope.md` on PR #571 @ `6fd15dd2`, §B–§C). Where this file and the scope block disagree on a wire detail, this file wins; on product behaviour, the scope block wins.

## Contents

- [1. Capability on GET /api/league/free-agents](#1-capability-on-get-apileaguefree-agents)
- [2. Consent routes](#2-consent-routes)
- [3. POST /api/league/free-agents/move](#3-post-apileaguefree-agentsmove)
- [4. Codes and the states they drive](#4-codes-and-the-states-they-drive)
- [5. Timing](#5-timing)
- [6. Connect mapping](#6-connect-mapping)
- [7. Copy slots and templates](#7-copy-slots-and-templates)

## 1. Capability on GET /api/league/free-agents

Additive. An old server sends none of it, and the client then behaves exactly as before.

```
move: {
  mode:            "submit" | "handoff" | "unsupported",
  claims:          boolean,
  league_platform: "sleeper" | "mfl" | "espn" | null,
  connect:         "ok" | "not_linked" | "expired" | "unverified" | "other_account",
  consent_until:   "<ISO-8601 UTC>" | null,
  copy:            { ...§7 pre-tap slots, every key optional... }
}
free_agents[i].move_kind:  "add" | "claim" | null     // null = the server can't tell
free_agents[i].move_mode:  "handoff"                  // optional per-row override
free_agents[i].move_line:  string                     // optional; the server's reason for the override
```

- **`move` absent, or `mode` not one of the three:** legacy behaviour (today's `resolveAddPlatform` routing).
- **`mode: "submit"` with `league_platform: null`:** treated as legacy. The server never sends it.
- **Unknown `connect` value:** the plain connect step, never Ready.
- **`move_kind: null` in `submit` mode:** the CTA names an add, and the request sends `move_kind: "add"`. If the player is really on waivers, the server answers `move_kind_changed` (no write).

## 2. Consent routes

**The consent routes are never gated by a kill switch.**
- GET always answers 200, with `valid: false` and no status line when there's no grant. The Settings row then stays hidden, and dark periods log no failures.
- DELETE always works. A user can withdraw a grant even while moves are switched off.
- Only the move route and the capability follow `*.send_add_drop`.
- `platform` ∈ `sleeper | mfl | espn`; anything else is 400 `bad_request`.

**`GET /api/platform-write-consent?platform=sleeper`** → 200:

```
{
  platform:     "sleeper",
  valid:        boolean,
  until:        "<ISO-8601 UTC>" | null,
  consent: {                       // the text to show if the user must consent now
    copy_version:  "sleeper-roster-moves-v1",
    locale:        "en-US",
    title:         string,
    body:          [string, ...],  // paragraphs, rendered in order, verbatim
    checkbox_label: string,
    this_move:     string,         // template with {cta} and {league} (R15.8 D10(d))
    button_label:  string,         // "Make the move"
    links?:        [{ label: string, url: string }, ...],  // legal's "Terms · Privacy" row; when absent the client shows the app's own Terms and Privacy links
    reason?:       "first" | "lapsed" | "version" | "withdrawn"  // for fa_move_consent_shown; when absent the client infers it
  },
  status_line:  string | null,     // Settings: "Roster moves: on until {date}" already filled, or null when not valid
  stop_label:   string | null      // Settings: "Stop roster moves"
}
```

**`DELETE /api/platform-write-consent?platform=sleeper`** → 200 `{ platform, valid: false, notice: string }`. `notice` is R15.2.6's withdrawal text, verbatim. Idempotent: a second DELETE returns the same body.

- **Both routes need a verified session** (head-eng's security check, 11-01). An unverified session can carry another user's id: a username-only sign-in yields the victim's user_id. Such a session could then forge a withdrawal into the append-only record, or read whether someone consented.
  - This still keeps withdrawal as easy as consent (R15.2.6). A grant can only be created from a verified session (the move route's step 3), so anyone holding a grant can withdraw it the same way.
  - GET answers 403 `verification_required` (`_verified_read_denial`); DELETE answers 403 `verification_required` (`_verified_write_denial`).
- **Errors:** 401 with no session; 403 `verification_required`; 400 `bad_request` for an unknown platform. A 404 means an older server.
- **Client handling:**
  - Settings treats a GET 404 or 403 like `valid: false` (no row).
  - On any DELETE failure, Settings keeps the row and shows a neutral "couldn't turn it off, try again" line. The grant stays in force until a DELETE succeeds.
  - In the sheet, a consent GET 403 `verification_required` goes to state 4 (Verify), like the move route's 403.

## 3. POST /api/league/free-agents/move

**Request** (through the shared API client, never a bare `fetch`):

```
{
  league_id:       string,
  add_player_id:   string,          // FTF canonical (Sleeper) id
  drop_player_id?: string,
  move_kind:       "add" | "claim", // what the CTA named
  faab_bid?:       number,          // claims only
  consent?:        { copy_version: string, locale: string },  // only from the consent step
  attempt_id:      string,          // one per tap; see the rule below
  surface?:        "free_agents" | "usage_trends"  // the sheet's host; the server records it on fa_move_consent_recorded and ignores any other value
}
```

**`attempt_id` rule:**
- The client sends a v4-UUID-**shaped** string (8-4-4-4-12 hex). Hermes has no Web Crypto, so it may come from `Math.random`, not a CSPRNG.
- The server treats it as **opaque**: it accepts 8–64 characters of `[A-Za-z0-9._-]` and never parses it as a UUID or stores it in a `uuid` column.
- **Idempotency is scoped per user:** (user, `attempt_id`) identifies a move. Another user's identical id is a different move, never a replay.

**200:**

```
{
  status:            "complete" | "pending",
  move_kind:         "add" | "claim",
  result:            "accepted" | "partial",
  league_platform:   "sleeper" | "mfl" | "espn",
  attempt_id:        string,
  title:             string,
  lines:             [string, ...],
  platform_transaction_id?: string
}
```

- `complete` → state 8 (Added). `pending` → state 9 (Claim submitted).
- A repeat of the same `attempt_id` returns the recorded body unchanged.

**Errors:** every body is

```
{
  error:    "<code>",          // §4
  message:  string,            // server-authored, shown as is
  detail:   string,            // == message
  title?:   string,
  kind?:    "network" | "roster_read",   // only on {platform}_write_failed
  remaining?: number,          // only on waiver_bid_over_budget
  consent?: { ...the §2 consent block... }  // only on consent_required
}
```

## 4. Codes and the states they drive

Platform codes are `{platform}_<suffix>`. The client maps by **suffix**, so MFL and ESPN need no build. `error_code` in analytics is the bare suffix (or the code itself when it has no platform prefix).

| Status | Code | State |
|---|---|---|
| 404 | `feature_disabled` | 1 Hand-off |
| 400 | `bad_request` | 12-style neutral failure panel, no retry (a client bug; never shown in practice) |
| 403 | `verification_required` | 4 Verify |
| 409 | `{p}_not_linked` | 3 Connect |
| 409 | `{p}_expired` | 4 Verify |
| 409 | `consent_required` | 5 Consent (with the body's consent block; unticked; a "terms changed" line when its `copy_version` differs from the one shown) |
| 422 | `roster_full_drop_required` | 10a |
| 422 | `asset_not_owned` | 10b |
| 422 | `player_unavailable` | 10c |
| 422 | `waiver_bid_over_budget` | 10d (uses `remaining`) |
| 409 | `move_kind_changed` | 10e (re-read the list) |
| 422 | `waiver_claim_unsupported` | 14 (→ hand-off, bid and drop kept) |
| 409 | `{p}_rejected` | 13 Connection rejected |
| 502 | `{p}_write_failed` + `kind` ∈ `network`, `roster_read` | 11 Not sent (the same named CTA retries) |
| 502 | `{p}_write_failed`, no `kind` | 10f Rejected by the platform |
| 503 | `{p}_unconfigured` | 10g Unavailable |
| 502 | `{p}_outcome_unknown` | 12 |
| 409 | `move_in_progress` | 12 |
| 500 | `internal_error` | 12 |
| — | client timer fired (`timeout`) | 12 |
| 0 | network after the request started (`network`) | 12 |
| ≥ 500 | no usable code (`unknown`) | 12 |
| offline at the tap (NetInfo) | — | 11, and **nothing is sent** |

Any other 4xx with an unrecognised code: the 12-style panel with the server's `message`, no retry.

## 5. Timing

- **Server worst case: 76 s** from request receipt to response (`FA_MOVE_SERVER_WORST_CASE_S`). The server enforces it: a 30 s preflight budget, checked immediately before the platform write (the `_SEND_PREFLIGHT_BUDGET_S` pattern), and the write path's own timeouts sum to ≤ 46 s. A server test pins the sum.
- **Client timeout:** `(76 + 15) × 1000 = 91_000` ms, its own named constant (not the 15 s default).
- **"Still sending" line** after 8 s.
- iOS may drop an idle request at ~60 s. That surfaces as status 0 → state 12, which is the safe reading.

## 6. Connect mapping

| `league_platform` | Connect / Verify opens | Notes |
|---|---|---|
| `sleeper` | the `SleeperConnect` modal route | The sheet hides (keeps bid, drop and step) and re-shows on return, refetching the capability. It resumes at the next step needed and never sends by itself |
| `espn` | the `EspnConnect` route | Same rules |
| `mfl` | none in the 11-06 binary | The server must not answer `submit` to an MFL user whose `connect` isn't `ok` until a later binary maps it. If it does, the client shows `unsupported` |

## 7. Copy slots and templates

Every slot is optional. Missing → the client's neutral fallback (never consent text, never "Sleeper doesn't allow apps to submit claims"). Templates use `{add}`, `{drop}`, `{bid}`, `{league}`, `{date}`, `{name}`, `{cta}`; the client fills them and leaves any unknown placeholder as is.

- **`{bid}` is filled with the dollar sign**, e.g. `$7`, so server templates never add their own `$`. An empty bid on a claim fills as `$0`.
- **`{date}` is a short local date with no time**, e.g. `Nov 8`.
- **A slot whose known placeholder has no value** (e.g. `{drop}` on an add with no drop) isn't shown; the client uses its fallback for that slot instead. Server templates for the drop variants live in `cta_add_drop` / `cta_claim_drop`, so this shouldn't arise.

`move.copy` keys:

| Key | Used in | Example (not final) |
|---|---|---|
| `header_add`, `header_claim` | sheet header by `move_kind` | `Add {name}` / `Claim {name}` |
| `cta_add`, `cta_add_drop`, `cta_claim`, `cta_claim_drop` | state 6 CTA (D10(a)); the claim forms carry `{bid}` | `Add {add}, drop {drop}` / `Claim {add} for {bid}, drop {drop}` |
| `cta_claim_no_bid`, `cta_claim_drop_no_bid` | a claim with no bid (a priority-waiver league) | `Claim {add}` / `Claim {add}, drop {drop}` |
| `league_line` | beside the CTA | `In {league}` |
| `finality` | under the CTA, always | legal-final G7 |
| `waiver_line` | a claim **with** a drop, under the CTA | R15.1 (`:766`): "This places a waiver claim for {add} (dropping {drop} if it clears). Sleeper processes it on its waiver schedule." |
| `waiver_line_no_drop` | a claim **without** a drop | the same sentence with no parenthetical |
| `bid_line` | under the waiver line, **only when the claim has a bid** | R15.1: "Bid: {bid}" |
| `window_line` | inside a consent window | `Adds authorized until {date}` |
| `turn_off` | the window line's action | `Turn off` |
| `do_in_platform` | every submit step | `Do it in Sleeper instead` |
| `open_platform` | hand-off CTA. **Reserved: the 11-06 binary doesn't read it** and shows #509's approved literal (check-sleeper-handoff S2 pins it) | `Open in Sleeper to claim` |
| `handoff_footer` | state 1 | G1 |
| `connect_line`, `verify_line`, `other_account_line` | states 3, 4 | G2, G3, F3 |
| `not_sent_line` | state 11 | G15 |
| `unknown_title`, `unknown_body` | state 12 | 8i "Check before resending" / G16 |
| `unavailable_line` | F4 (consent text unreachable) | "Moves from Fleeced aren't available right now" |
| `still_sending` | state 7, after 8 s | |
| `offline_line` | state 11 when **Fleeced's server** wasn't reached: offline at the tap, or a consent GET with no answer. Not used for the server's `{p}_write_failed` + `kind: network`, which keeps `not_sent_line` | `Couldn't connect right now, so nothing was sent.` |

Result and refusal text comes from the response (`title`, `lines`, `message`), never from `move.copy`.
