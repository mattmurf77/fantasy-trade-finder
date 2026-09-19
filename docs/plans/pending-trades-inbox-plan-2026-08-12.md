# Pending Trades Inbox — Plan (2026-08-12)

> Cross-platform pending-trade inbox: pull open offers from **Sleeper, ESPN, and MFL**, let the user **Accept / Decline** what they received and **Revoke** what they sent, surfaced as a third tab on Matches.
>
> Companion evidence: [`sleeper-pending-trades-feasibility-2026-08-12.md`](sleeper-pending-trades-feasibility-2026-08-12.md) · [`espn-send-live-capture-2026-08-11.md`](espn-send-live-capture-2026-08-11.md) · [`send-in-mfl-research-2026-08-11.md`](send-in-mfl-research-2026-08-11.md)
>
> **This unblocks competitor feature #11 (received-offer analyzer)**, parked since 2026-06-11 on the question of whether pending offers were reachable at all. They are, on all three platforms.

---

## 0. First: the Sleeper egress question

Sleeper warned that automated systems may block FTF's API calls and suggested "varying where the calls come from." Restating the problem in concrete terms, because the fix follows from it:

FTF's backend runs on Render behind a **small, fixed set of egress IPs**. Every user's Sleeper call — all of them — leaves from those few addresses. From Sleeper's side that looks like one machine making thousands of requests an hour, which is indistinguishable from a scraper. Their anti-abuse blocks it. The agreement doesn't help, because the automated system never sees the agreement; it sees an IP and a request rate.

"Vary where the calls come from" means **spread that traffic across many source addresses** so no single one looks abusive.

There are three ways to do it, and they are not equally good.

### A. Move user-scoped calls to the user's device — *recommended*

Make each user's **authenticated** Sleeper calls (pending trades, propose, accept, reject) from their own phone instead of from Render. Traffic then originates from thousands of ordinary residential IPs.

This is the strongest option and worth being precise about why: **it isn't evasion at all.** The call is the user's own session acting on their own league, so their device is genuinely where it should originate. Nothing is disguised. It also shrinks FTF's credential custody — the JWT can stay on the device rather than being stored server-side, which independently reduces the §11.1 surface.

Costs, honestly: the JWT moves to device storage (Keychain), we lose server-side caching for those calls, retry/backoff has to be implemented client-side, and central observability gets thinner. Public, non-user-scoped data (player lists, league metadata) should **stay** server-side and cached — it's shared, so serving it once from Render is strictly better than N devices fetching it.

### B. Rotating egress pool / proxies — what was literally suggested

Route backend Sleeper calls through a pool of IPs. It works and it's well-understood infrastructure, but three caveats. It costs money and adds a dependency in the request path. It gives up the honest story option A has — you're making authorized traffic *look* like it comes from elsewhere, which is fine with permission but reads identically to abuse without it. And done crudely (cheap datacenter proxies, random rotation per request) it can look **more** abusive than the single IP did and get you blocked harder.

If you go this route: use a small, stable pool, pin each user to one IP rather than rotating per request, and tell Sleeper the ranges.

### C. Be a well-behaved, identifiable client — *do this regardless*

Independent of A or B, and mostly free:

- **Ask Sleeper to allowlist FTF's Render egress IPs.** With an agreement in place this is the cleanest interim fix and costs nothing. It may make A and B unnecessary before launch.
- **Set a stable, identifying `User-Agent`** so Sleeper *can* recognize FTF's traffic. Anti-abuse can't grant an exception to traffic it can't identify. (MFL already requires this — see the load-bearing UA finding.)
- **Cut call volume**: cache public data aggressively, batch, and never poll pending trades on a timer when a pull-to-refresh or a push will do.
- **Honour backoff**: on 429/403, back off exponentially and stop. Retrying through a block is what escalates a rate-limit into a ban.

### Recommendation

**Do C now** — it's free, immediate, and may solve it outright. **Build toward A** for authenticated user-scoped calls; it's the correct architecture regardless of rate limits and it reduces credential risk. **Hold B in reserve** for if A can't land before launch.

Sleeper's forthcoming "enhancement" is almost certainly a partner OAuth flow (their Privacy Notice already hints at one), which would supersede all of this. Design so that swapping in an official auth path later touches one adapter, not the whole call graph.

---

## 1. Pull pending trades from all three platforms

### Per-platform sources

| Platform | Source | State |
|---|---|---|
| **MFL** | `export?TYPE=pendingTrades` (owner-restricted, cookie) | **Shipped and now LIVE-VERIFIED** — `GET /api/mfl/pending-trades` |
| **ESPN** | `?view=mPendingTransactions`, **reconciled against** `?view=mTransactions2` | Not built |
| **Sleeper** | `league_transactions_filtered(league_id, type_filters:["trade"], status_filters:["proposed"])` | Not built (GraphQL; cleared by the Sleeper agreement) |

### The ESPN trap — REVISED 2026-08-12 after live validation, and the fix is simpler than first written

An earlier revision of this plan said to read `mPendingTransactions` and reconcile it against `mTransactions2`. **That was backwards.** Validated end-to-end against league 11896 with six real proposals of known outcome:

| Proposal | `status` in `mTransactions2` | `isPending` | Linked terminal row | Truth |
|---|---|---|---|---|
| c7bc15ef | **PENDING** | true | `TRADE_DECLINE` | declined |
| 50241ec8 | **PENDING** | true | `TRADE_DECLINE` | declined |
| 75aa61d4 | **PENDING** | true | `TRADE_DECLINE` | declined |
| 85d0215a / 7f4fff26 / ec752a14 | CANCELED | **true** | none | canceled |

**`mPendingTransactions` returned `[]` — correctly.** It listed exactly 2 while those offers were live yesterday, and 0 now that all six are resolved. **It is self-pruning and authoritative; trust it.**

The unreliable surface is `mTransactions2`, the *history* view, where a proposal row's `status` is frozen at creation — a declined proposal still reads `PENDING` there forever, because the decline lives in a separate `TRADE_DECLINE` row. Reconstructing "what's open" from history is what requires reconciliation by `relatedTransactionId`; reading the live pending feed does not.

Two field-level warnings that survive the revision:

- **`isPending` is always `true` on proposal rows — even ones whose own `status` is `CANCELED`.** It is junk. Never branch on it.
- **`teamActions` can never show a decline.** It only ever contains `{proposer: "ACCEPTED"}`; a team that hasn't acted is simply absent.
- There is a third terminal state beyond declined/accepted: **`CANCELED`** (revoked or expired). Filter on `status === "PENDING"` when reading history, *in addition to* the terminal-row check — either filter alone is insufficient.

**Net effect on the build: the ESPN read is simpler than planned.** `mPendingTransactions` alone is sufficient for the inbox. `mTransactions2` is only needed if we later want outcome history ("your offer was declined") rather than just open offers.

Also: acceptance is **not** finality on ESPN. `processDate = acceptedDate + revisionHours`, and the trade can still be vetoed inside that window. `expirationDate` (offer clock) and `processDate` (review clock) are two different countdowns and the UI must not conflate them.

### MFL — live-verified 2026-08-12, response shape confirmed

Logged in with the stored credentials and read `export?TYPE=pendingTrades&L=62846&JSON=1`. **Returned a real pending trade**, retiring the `TODO(live-verify)` on the parser's field vocabulary:

```jsonc
{"pendingTrades": {"pendingTrade": {
  "trade_id": "1057",
  "offeringteam": "0002", "offeredto": "0013",
  "will_give_up": "17105,FP_0002_2028_2,",     // trailing comma; player ids + pick assets, mixed
  "will_receive": "15749,16187,",
  "expires": "1787116590", "timestamp": "1786511790",   // unix SECONDS, not ms
  "comments": "",
  "description": "Boston Brawlers proposed a trade to Dakota Hicks: …"
}}}
```

Four things worth building against:

- **Every documented field is present and correctly named** — the parser's vocabulary was guessed from MFL's docs and is now observed.
- **`FP_0002_2028_2` appears in the wild**, confirming the `FP_{franchise}_{year}_{round}` encoder against a real trade rather than only against a `futureDraftPicks` snapshot.
- **Asset lists are comma-joined strings with a trailing comma**, mixing player ids and pick assets in one field — split and drop empties.
- **`expires`/`timestamp` are unix SECONDS.** ESPN's equivalents are epoch **milliseconds**. The normalized model must convert; getting this wrong yields expiry dates in 1970 or 56,000 AD.
- **Single pending trade returns an object, not an array** — MFL's usual XML-to-JSON quirk. Coerce to a list, as `mfl_service` already does elsewhere.

**Host correction:** `api.myfantasyleague.com` served this identically to `www45`. The recorded gotcha that the `api.` host "returns empty for league data" now looks **misattributed** — the real cause was the missing `User-Agent` (an empty UA returns an empty body from either host). Keep using the league's `wwwNN` host since it is known-good, but the wwwNN-only claim in `docs/integrations/mfl.md` should be re-tested rather than trusted.

### Normalized model

Normalize all three to one shape — `mfl_service.parse_pending_trades` already emits something close, so extend that shape rather than inventing a third:

```jsonc
{
  "platform": "sleeper" | "espn" | "mfl",
  "league_id": "...", "league_name": "...",
  "trade_id": "...",                       // platform's own id; required for every action
  "direction": "incoming" | "outgoing",
  "counterparty": { "id": "...", "name": "..." },
  "give":    [ { "kind": "player"|"pick"|"faab", "id": "...", "label": "..." } ],
  "receive": [ ... ],
  "status": "pending" | "in_review",       // in_review = ESPN accepted-awaiting-veto
  "proposed_at": 0, "expires_at": 0,       // epoch ms; null where unknown
  "actions": ["accept","decline"] | ["revoke"]
}
```

**Direction** is derived differently per platform and is easy to get backwards:

- **MFL** — `OFFEREDTO` equals our franchise ⇒ incoming.
- **ESPN** — the row's `teamId` is the **proposer**. Ours ⇒ outgoing; theirs ⇒ incoming. Confirm by scanning `items[].fromTeamId` / `toTeamId`.
- **Sleeper** — `creator` is the proposer. Also `roster_ids − consenter_ids` = who still owes a response.

**Ownership rule:** the server derives direction and `actions` authoritatively. The client never decides what it's allowed to do — same posture as the existing propose routes.

### Route

`GET /api/trades/pending` — one endpoint, all platforms, fanning out across the user's linked leagues. Per-platform failures degrade to a partial result with a named error rather than failing the whole response; one expired ESPN cookie must not blank a working MFL inbox.

---

## 2. Accept / Decline / Revoke

| | MFL | Sleeper | ESPN |
|---|---|---|---|
| **Accept** | **Shipped** `RESPONSE=accept` | `accept_trade(leg, league_id, transaction_id)` — **confirmed signature** | **Envelope validated** (2026-08-12 negative probe) |
| **Decline** | **Shipped** `RESPONSE=reject` | `reject_trade(...)` — **built, unrouted** | **Envelope validated** (same probe) |
| **Revoke** | **Shipped** `RESPONSE=revoke` | no `cancel_trade`; likely `reject_trade` on own offer — *inferred* | `executionType:"CANCEL"` + `relatedTransactionId` — **confirmed, built, unrouted** |

**ESPN accept/decline is no longer blocked.** A negative probe — `TRADE_ACCEPT` and `TRADE_DECLINE` posted with a deliberately nonexistent `relatedTransactionId`, so nothing real could be touched — returned **409 `TRAN_NOT_FOUND`** for both. That is the *deepest* failure a fake id can reach: auth, league authorization, envelope validation, and `type` recognition all passed; only the lookup failed. The write shape is validated against ESPN's live validator rather than inferred.

Three narrow unknowns remain, all requiring a *real* transaction: whether ESPN checks that `teamId` is genuinely the counterparty (or derives it from SWID); whether `items` should be `[]` or omitted (persisted records disagree — accept carries `[]`, decline omits it); and the success-response body the adapter must parse. **Build it behind `espn.send` and treat the first real accept as the confirming test** — the posture MFL shipped under. `force_cancel_transaction` on Sleeper is **commissioner-only** per the server's own description — do not use it for user revoke.

Route: `POST /api/trades/respond` taking `{platform, league_id, trade_id, action}`, dispatching to the per-platform adapter. Mirrors `respond-mfl`'s error vocabulary. Fires `trade_responded` with non-null `platform` on confirmed success only.

**Accept must be treated as irreversible** — destructive confirm, and the copy must not promise finality on ESPN, where a veto window follows.

---

## 3. UI — third tab on Matches

Third tab alongside the existing Matches surfaces, which is right: it's trade activity, in the place users already go for trade activity.

```
┌─────────────────────────────────────────────┐
│  Matches   │   Sent   │   Offers ③          │  ← badge = incoming count
├─────────────────────────────────────────────┤
│  RECEIVED                                    │
│  ┌───────────────────────────────────────┐   │
│  │ [MFL]  Dependables        expires 2d  │   │
│  │                                       │   │
│  │  You get      │  You give             │   │
│  │  Rachaad White│  Tez Johnson          │   │
│  │  2027 1st     │                       │   │
│  │                                       │   │
│  │  ▸ FTF read: +8.4 for you   [Good]    │   │  ← the differentiator
│  │                                       │   │
│  │   [ Decline ]         [ Accept ]      │   │
│  └───────────────────────────────────────┘   │
│                                              │
│  SENT                                        │
│  ┌───────────────────────────────────────┐   │
│  │ [ESPN] Newton Dynasty   in review ⓘ   │   │
│  │  … awaiting league veto period        │   │
│  │                    [ Revoke ]         │   │
│  └───────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

Design notes, all Chalkline-governed (tokens only; no emoji icons, no gradients):

- **The valuation line is the reason to build this.** Anyone can list offers; FTF can tell you whether to take one. This is exactly competitor feature **#11**, and it should be the visual anchor of the card, not a footnote.
- **Badge count on the tab** for incoming offers — the natural re-engagement hook, and it pairs with a push notification later.
- **Platform chip per card** — users hold leagues across platforms, and the available actions differ by platform.
- **Two clocks, never conflated**: offer expiry vs ESPN review window. `in_review` is its own state with its own copy.
- **Empty state** should route to the deck ("no open offers — find a trade"), not dead-end.
- **Optimistic UI is wrong here.** These are real, externally-visible actions; show a pending state and reconcile from the server response.
- Accept gets a destructive-style confirm naming both sides of the trade.

---

## 4. Build order

1. **`GET /api/trades/pending`** with MFL (already built) + Sleeper (confirmed signatures). Ship backend-first, as MFL's lifecycle was.
2. **ESPN read**, including the `mTransactions2` reconciliation — more work than the other two combined, and wrong without it.
3. **`POST /api/trades/respond`** — MFL and Sleeper fully; ESPN revoke only.
4. **ESPN accept/decline** — envelope validated by negative probe; build behind `espn.send`, first real accept is the confirming test.
5. **The Offers tab** — the client work, platform-agnostic. Serves all three at once, and MFL's shipped-but-invisible lifecycle finally becomes visible.
6. **Push notification on incoming offer** — natural follow-on, out of scope here.

Feature gates apply throughout: scope block, Maestro delta, docs, sim run.

## 5. Open questions for the operator

- **Polling cadence.** Pull-to-refresh only, on-open refresh, or background? This is the main driver of Sleeper call volume, so it interacts directly with §0.
- **Does the Offers tab replace or sit beside the existing Matches tabs?** The mockup assumes beside.
- **Accept confirmation depth** — single confirm, or type-to-confirm for high-value trades?
