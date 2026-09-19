# ESPN Send — Live Capture Results (2026-08-11)

> Probe #1 from [`espn-send-spike-verification-2026-08-11.md`](espn-send-spike-verification-2026-08-11.md), executed against a **real** ESPN dynasty league. Resolves the spike's load-bearing unknown. Companion: [`send-in-espn-research-2026-08-11.md`](send-in-espn-research-2026-08-11.md), decision [`D-026`](../../living-memory/DECISIONS.md).
>
> **Credential hygiene:** the proposer's `memberId` is the account **SWID**, which is one of the two ESPN auth cookies. It is redacted as `{SWID}` throughout and must never be committed in raw form.

---

## How this was captured

The operator proposed a trade by hand in the ESPN web UI. The `POST` itself scrolled out of the browser's network buffer before it could be read (the post-send navigation flushes it), so the **stored proposal was read back** through the read API from the operator's authenticated session:

```
GET lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/segments/0/leagues/{L}?view=mPendingTransactions
```

That yields ESPN's own canonical representation of the proposal — which is what we need to construct one.

**Caveat on provenance:** this is the *stored* record, not the literal request body. Fields ESPN derives server-side (rather than accepting from the client) cannot be distinguished from client-supplied ones here. A true request capture is still worth taking opportunistically.

## League context

Real 14-team dynasty league (`previousSeasons` back to 2014), season 2026, offseason (`scoringPeriodId: 0`, `latestScoringPeriod: 0`, undrafted).

## The captured proposal

```json
{
  "type": "TRADE_PROPOSAL",
  "status": "PENDING",
  "isPending": true,
  "executionType": "EXECUTE",
  "id": "50241ec8-ae7e-49ce-a9b4-f7a2e6b5ddbc",
  "memberId": "{SWID}",
  "teamId": 5,
  "teamActions": { "5": "ACCEPTED" },
  "proposedDate": 1786476250306,
  "expirationDate": 1786649050203,
  "scoringPeriodId": 0,
  "bidAmount": 0,
  "rating": 0,
  "isActingAsTeamOwner": false,
  "isLeagueManager": false,
  "items": [
    { "type": "TRADE", "playerId": 4697815, "fromTeamId": 12, "toTeamId": 5,
      "fromLineupSlotId": 20, "toLineupSlotId": -1, "isKeeper": false, "overallPickNumber": 0 },
    { "type": "TRADE", "playerId": 4608810, "fromTeamId": 5,  "toTeamId": 12,
      "fromLineupSlotId": 20, "toLineupSlotId": -1, "isKeeper": false, "overallPickNumber": 0 }
  ]
}
```

## Second capture — structure reproduced

A second proposal (`c7bc15ef-a899-4376-a67b-f801a799a01e`, players `4431268` / `4431545`) was made in the same league and read back identically: same envelope fields, same `teamId`-is-proposer semantics, same `fromLineupSlotId: 20` / `toLineupSlotId: -1`, `scoringPeriodId: 0`, and an `expirationDate` again ≈ 48 h after `proposedDate`. Two independent proposals agreeing rules out a one-off.

**Two attempts to capture the raw request both failed**, and the reason is worth recording: ESPN performs a **full page reload** on send, which wipes *both* an injected `fetch`/XHR interceptor *and* the browser's network buffer. A future attempt must either persist captures to `sessionStorage` synchronously at capture time, or use DevTools' "Preserve log". Consequence: everything below is derived from ESPN's **stored** record, never from an observed request.

## Resolved

### 1. `espn_id` in the DynastyProcess crosswalk IS the write-API `playerId` — the load-bearer, CONFIRMED

All four live ids across both proposals resolved directly against `espn_id` in the DP crosswalk snapshot — 4/4, no misses:

| write-API `playerId` | crosswalk `name` | `sleeper_id` | `mfl_id` |
|---|---|---|---|
| `4697815` | Rachaad White | 8136 | 15721 |
| `4608810` | Tez Johnson | 12485 | 17079 |
| `4431268` | Chimere Dike | 12540 | 17171 |
| `4431545` | Will Shipley | 11577 | 16601 |

**Consequence:** `invert_espn_crosswalk` in `backend/espn_write.py` rests on a valid assumption. This was the single unknown that could have invalidated the whole player-mapping approach. It did not.

### 2. The football (`ffl`) envelope matches the baseball-derived scaffold

`type: "TRADE_PROPOSAL"`, `executionType: "EXECUTE"`, and the `items[]` shape all hold for football. The scaffold's core structure needs no revision.

### 3. Direction semantics — CONFIRMED, matches the scaffold

Ownership was verified via `?view=mTeam`: the proposer's `memberId` owns **team 5**; team 12 is the counterparty.

- **Give** (proposer parts with the player): `fromTeamId: <me>` → `toTeamId: <them>`
- **Receive**: `fromTeamId: <them>` → `toTeamId: <me>`

So the proposer here gives Tez Johnson and receives Rachaad White. The spike's assumption was correct.

### 4. `teamId` on the transaction is the PROPOSING team

`teamId: 5` with `teamActions: {"5": "ACCEPTED"}` — the proposer's own action is recorded as `ACCEPTED` at creation; the recipient's is absent until they act.

> **CORRECTION (2026-08-12).** An earlier revision of this line advised *"Poll `teamActions` for accept/decline state."* **That is wrong and would never work.** Across 2,342 real pending proposals, `teamActions` is *always* exactly `{"<proposerTeamId>": "ACCEPTED"}` and the only value that ever appears is `ACCEPTED` — a team that has not acted is simply **absent**, and there is no `DECLINED` or `PENDING` value. (ESPN's own `transactionTeamActionTypes` enum is `INVOLVED / ACCEPTED / APPROVED / VETOED / PROTESTED`.)
>
> **Worse, the proposal record itself lies about its own state.** A *declined* proposal keeps `status: "PENDING"` and `isPending: true` — verified 5/5 against real `TRADE_DECLINE` rows. The decline exists only as a **separate** `TRADE_DECLINE` transaction linked by `relatedTransactionId`. An *accepted* proposal, conversely, disappears from the pending feed entirely.
>
> **Correct approach:** never trust a proposal row's own status. Read `?view=mTransactions2` and reconcile `TRADE_DECLINE` / `TRADE_ACCEPT` / `TRADE_VETO` rows back to the proposal by `relatedTransactionId`. Gate on `status === "PENDING"` *and* the absence of a linked terminal row. Note also that acceptance is **not** finality: `processDate = acceptedDate + revisionHours`, and the trade can still be vetoed inside that window — the offer clock (`expirationDate`) and the review clock (`processDate`) are two different countdowns.
>
> This advice never reached shipped code (`backend/espn_write.py` references only the proposer's entry), so nothing was built on it. Full evidence: the 2026-08-12 ESPN lifecycle-parity research.

### 5. A proposal lands as a normal PENDING trade

`status: "PENDING"`, visible in `mPendingTransactions`. No league-vote or commissioner-review interstitial appeared at proposal time in this league's settings.

## New fields the scaffold does not yet emit

Not present in the baseball-derived envelope; each `items[]` entry also carried:

| Field | Observed | Note |
|---|---|---|
| `fromLineupSlotId` | `20` | 20 = bench. Both players were benched (offseason). **Unknown whether a starter's real slot id is required** — untested. |
| `toLineupSlotId` | `-1` | Sentinel, consistent across both items. |
| `isKeeper` | `false` | |
| `overallPickNumber` | `0` | |
| `bidAmount` / `rating` | `0` | Transaction-level. |
| `isActingAsTeamOwner` | `false` | Distinct from `isLeagueManager`. |

`scoringPeriodId: 0` in the offseason — do **not** hardcode a real week; read it from league status.

`expirationDate − proposedDate` = 172,799,897 ms ≈ **48 hours**, corroborating the scaffold's ~2-day default. Epoch **milliseconds**, not the `"%Y-%m-%dT%H:%M:%S.000Z"` string the scaffold formats — reconcile before building.

## RESOLVED — cookies alone DO authorize a server-side write

The last blocking unknown, settled by a controlled negative probe rather than another live trade.

A `POST` was issued to the write endpoint carrying **only** `espn_s2` + `SWID` (via `credentials: 'include'`) plus `content-type` and the two `x-fantasy-*` headers — **deliberately no CSRF or session token**, i.e. exactly the header set a server-side call can produce. The payload used `items: []` so that nothing could be created even if auth succeeded.

**Response: HTTP 409**

```json
{"messages":["The proposed trade contains 0 involved teams.  Only 2 team trades are supported."],
 "details":[{"type":"TRAN_INVALID_TRADE_TEAM_COUNT", ...}]}
```

**Why this is dispositive:** `TRAN_INVALID_TRADE_TEAM_COUNT` is a *trade-domain validation* error. Reaching it means the request passed authentication, passed authorization for this league and team, and was evaluated by ESPN's transaction validator. An unauthenticated or CSRF-rejected request cannot produce that error — it fails at the edge with 401/403 and never sees the payload semantics.

**Consequence:** the server-side architecture is viable. `backend/espn_write.py`'s auth model — decrypt the two stored cookies, attach the `x-fantasy-*` headers — is correct and needs no CSRF acquisition step. The `TODO(live-verify)` on the auth assumption can be cleared, and per **D-026** the blocking probes are now complete.

*(Note: 409 rather than the expected 400/422. Treat 409 as a validation-class response, not a conflict, when mapping status → structured error.)*

---

## 2026-08-12 — `TRADE_DECLINE` observed first-hand; the PENDING trap reproduced 3/3 in our own league

The operator declined a real incoming offer while an injected `fetch`/XHR interceptor was armed. **The POST was again not captured** — third consecutive failure, same root cause each time: ESPN performs a full page load around the action, and a page reload destroys the injected hook. `sessionStorage` preserves captured *data* across a reload but cannot preserve the *hook*, and there is no way to re-inject automatically. **Stop attempting injected capture. Use DevTools with "Preserve log" enabled, which is browser-native and survives reloads.**

What the *stored* records gave instead — read back from `?view=mTransactions2` on league 11896, and worth more than the single POST would have been:

**`TRADE_DECLINE` shape, confirmed on real 2026 `ffl` data (3 records):**

```jsonc
{ "type": "TRADE_DECLINE", "status": "EXECUTED", "executionType": "EXECUTE",
  "teamId": <the DECLINING team>,        // 5 when we declined; 12 when they declined ours
  "relatedTransactionId": "<proposal id>",
  "isPending": false, "scoringPeriodId": 0,
  "bidAmount": 0, "rating": 0, "isLeagueManager": false, "isActingAsTeamOwner": false,
  "memberId": "{SWID}", "proposedDate": <epoch ms>, "id": "<uuid>" }
```

Exact key set: `bidAmount, executionType, id, isActingAsTeamOwner, isLeagueManager, isPending, memberId, proposedDate, rating, relatedTransactionId, scoringPeriodId, status, teamId, type`. **There is no `items` key at all** — confirming the earlier third-party finding. `teamId` is the **responder**, not the proposer, which is the inverse of a `TRADE_PROPOSAL` row.

This raises confidence in the inferred accept/decline **write** body (`type` + `relatedTransactionId` + responder `teamId` + `executionType:"EXECUTE"`, no items) by the same logic that validated the original proposal capture — but it is still the persisted record, not an observed request. **Do not ship an inferred write payload.**

**The PENDING trap, reproduced independently:** all **3/3** declined proposals here still read `status: "PENDING"` and `isPending: true` on their own records. Combined with the 5/5 from a third-party capture, that is **8/8 across two unrelated leagues**. This is now settled, not suspected: a proposal record never reflects its own decline, and status must be reconciled from `TRADE_DECLINE` / `TRADE_ACCEPT` / `TRADE_VETO` rows via `relatedTransactionId`.

**Correction to the read plan:** the `x-fantasy-filter` grammar recorded in the 2026-08-12 parity research **returned an empty result** when applied to `mTransactions2` here. Unfiltered, the same request returned 82 transactions (`ROSTER` 70, `TRADE_PROPOSAL` 6, `TRADE_DECLINE` 3, `TRADE_ACCEPT` 2, `TRADE_UPHOLD` 1). Treat that filter grammar as **unverified**; filter client-side until it is proven.

---

## 2026-08-12 — accept/decline envelope VALIDATED by negative probe (no trade touched)

The three failed request-captures left ESPN accept/decline as the last unknown. It was settled instead by the same negative-probe technique that settled the auth question — and it needed no pending trade at all.

**Method.** `POST` the write endpoint twice, once with `type: "TRADE_ACCEPT"` and once with `"TRADE_DECLINE"`, using a **deliberately nonexistent** `relatedTransactionId` (`00000000-0000-4000-8000-000000000000`). Because the id refers to nothing, neither call can affect a real trade regardless of outcome. Body sent:

```jsonc
{ "isLeagueManager": false, "isActingAsTeamOwner": false,
  "teamId": <our team>, "type": "TRADE_ACCEPT" | "TRADE_DECLINE",
  "memberId": "{SWID}", "scoringPeriodId": 0, "executionType": "EXECUTE",
  "bidAmount": 0, "rating": 0, "items": [],
  "relatedTransactionId": "00000000-0000-4000-8000-000000000000" }
```

**Result — identical for both types:**

```
HTTP 409  {"type":"TRAN_NOT_FOUND",
           "message":"Transaction with ID 00000000-… could not be found."}
```

### What this proves

`TRAN_NOT_FOUND` is the **deepest possible failure** for a fake id: the request cleared authentication, cleared authorization for the league, passed structural validation of the envelope, had its `type` recognized as a legal write operation, and failed only at transaction lookup. A rejected `type` or a malformed envelope would have failed *earlier* and differently.

So the accept/decline write shape is **no longer inferred** — it has been validated against ESPN's live validator. This retires the "payloads were never captured — do not implement" caution that the most advanced public ESPN write project recorded, at least as far as the envelope goes.

### What remains unproven — narrow, and each is a real-transaction behaviour

1. **Authorization against a real transaction.** Whether ESPN verifies that `teamId` is genuinely the counterparty of that specific proposal, or derives the responder from the SWID and ignores `teamId`. A fake id can't test this.
2. **`items` handling.** Sent as `[]` here and accepted structurally. Real persisted records disagree with each other: `TRADE_ACCEPT` rows carry `items: []`, `TRADE_DECLINE` rows **omit the key entirely**. Either is likely tolerated on write; unconfirmed.
3. **The success response body**, which the adapter will need to parse.

**Recommendation:** build it, keep it behind `espn.send`, and treat the first real accept/decline as the confirming test — the same posture MFL shipped under, where a live send later confirmed the response parsing. A single DevTools capture (**"Preserve log" enabled**, not an injected hook) on the next organically-received offer closes all three at once.

## Still unresolved — all non-blocking, each with a safe fallback in code

1. ~~**Draft picks in `items[]`.**~~ **RESOLVED 2026-08-12 — and the hard block is permanent, not a TODO.** ESPN *does* carry pick legs, as `{"type":"DRAFT_TRADE","overallPickNumber":N,"playerId":0,…}`. But `overallPickNumber` is a slot in the **current** draft, joinable to `mDraftDetail.picks[]`, whereas FTF's pick assets are multi-season **future rungs** ("2027 1st") — for which ESPN has no representation at all. So there is nothing to encode, not something undecoded. **Operator-confirmed that ESPN leagues don't trade future picks in practice**, which is much of why dynasty players are on Sleeper/MFL — so the block costs users nothing. Keep `espn_pick_unsupported`; only the stated *reason* needed correcting.
2. **`espn_s2` lifetime / refresh UX.** Degrades to a clean `espn_auth_expired` + credential drop + reconnect prompt.
3. **Whether `fromLineupSlotId` must be a player's true slot** for a rostered starter. Real slots are threaded from the roster read; bench-20 is only a fallback.

## Follow-ups

- Update `backend/espn_write.py`: resolve `# UNVERIFIED` tags 1/3/5, add the new item fields, switch `expirationDate` to epoch ms, stop hardcoding `scoringPeriodId`.
- The next opportunistic capture should read the **request** (DevTools → Network → the `transactions/` POST → Payload) before navigating, to close unknown #1.
- `espn.send` stays OFF and absent from `config/features.json` until unknown #1 clears, per D-026.
