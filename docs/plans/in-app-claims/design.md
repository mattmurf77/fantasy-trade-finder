# In-app add/drop and waiver claims: where it stands, and Update 1 (MFL)

> The operator asked (2026-11-11) for the claim sheet's "Open in Sleeper to claim" button, and its ESPN and MFL equivalents, to make the move itself instead of sending the user to the platform. This thread **resumes D1** (`docs/plans/sleeper-fa-write/`), which already built most of it dark. This doc records what exists, what each platform still needs, the design for **Update 1** (MFL, built here, dark) and what the operator must do to verify each platform. Written by the `feat/in-app-claims` builder, checked against `origin/main` @ `6108b8c3`. No Sleeper, ESPN or MFL endpoint was called to write it.

## Contents

1. [Answer per platform](#1-answer-per-platform)
2. [What already existed (D1)](#2-what-already-existed-d1)
3. [What each platform needs](#3-what-each-platform-needs)
4. [Design: one move contract, one adapter per platform](#4-design-one-move-contract-one-adapter-per-platform)
5. [Capability matrix](#5-capability-matrix)
6. [Pre-flight, confirm, results, roster cache, analytics, untouchables](#6-pre-flight-confirm-results-roster-cache-analytics-untouchables)
7. [What was built in this thread vs specified but unverified](#7-what-was-built-in-this-thread-vs-specified-but-unverified)
8. [Verification: one supervised real transaction per platform](#8-verification-one-supervised-real-transaction-per-platform)
9. [Open decisions](#9-open-decisions)

---

## 1. Answer per platform

| Platform | Credential we hold today | Request shape known from | Can the app submit add/drop itself? | Waiver claims? |
|---|---|---|---|---|
| **Sleeper** | Yes: the user's Sleeper JWT, captured on the device by `SleeperConnectScreen`'s WebView and stored Fernet-encrypted server-side (`sleeper_credentials`); the write runs **on the server**, exactly like Send in Sleeper | **Nothing we can trust.** Sleeper has no public write API; the add/drop and claim mutations are known only from two community repos (capture.md §3, UNVERIFIED) | **Built, dark, blocked on one ~30-minute supervised capture.** Everything else (route, consent, records, client, copy, analytics, kill switch `sleeper.send_add_drop`) is on `main` | Built the same way; needs the claim capture + legal's consent v2 (R15.8 D5) |
| **MFL** | Yes: the MFL session cookie (`mfl_credentials`, the one Send in MFL uses); the write runs on the server | **MFL's official API docs** (`fcfsWaiver`, `blindBidWaiverRequest`, `waiverRequest`); no recorded request | **Built in this thread, dark** (`mfl.send_add_drop` off + `mfl_write.FA_MOVE_SHAPES_VERIFIED = False`). Needs one supervised real MFL add/drop, then legal's final MFL consent text | Request builder built and tested; kept off (`claims: false`) until a claim is verified and MFL consent v2 exists |
| **ESPN** | Yes: `espn_s2` + `SWID` cookies (`espn_credentials`, the Send in ESPN jar) | **Nothing.** ESPN publishes no API; our 2026-08-11 capture covers trade proposals only, and no public source documents the free-agent / waiver transaction body | **No, not responsibly yet.** Needs a capture like the trade one before any builder is written | Same |

**In one line:** Sleeper is one capture session away; MFL is one verification transaction (plus legal's MFL wording) away; ESPN needs a capture before any code.

## 2. What already existed (D1)

All on `main`, all dark. Sources: `living-memory/TEST_LEDGER.md` 2026-11-01 entries, `docs/plans/sleeper-fa-write/{contract,code-walk,testflight-additions}.md`, `origin/plan/fa-moves-launch:docs/plans/sleeper-fa-write/scope.md`, `origin/plan/sleeper-fa-write:docs/plans/sleeper-fa-write/capture.md`.

- **Server** (`backend/server.py` D1 block, `backend/fa_move_copy.py`, `backend/sleeper_write.py` §D1): `POST /api/league/free-agents/move` (platform-neutral; platform from the league row), `GET`/`DELETE /api/platform-write-consent`, the additive `move` capability on `GET /api/league/free-agents`, two append-only tables (`platform_write_consents`, `platform_write_moves`), per-user `attempt_id` idempotency, an atomic double-move block (Postgres advisory lock), the 30 s preflight budget / 76 s worst case, `write_outcome.py` classification, the roster save + fingerprint stamp on `complete`. 151 + 46 + 47 tests, 35 sabotages.
- **Client** (`mobile/src/components/ClaimSheet.tsx`, `src/api/faMove.ts`, `src/utils/claimSheetPlan.ts`): the whole flow for the 11-06 binary, rendering only from the server's capability: named CTA, the consent step (unticked box, server text), "Still sending" at 8 s, the 91 s timeout, state 12 "Check before resending" (never a retry), codes mapped **by suffix** for `sleeper_` / `mfl_` / `espn_`, an ESPN connect mapping, MFL treated as `unsupported` unless `connect: ok`. `check-fa-move.js`, 115 checks.
- **Analytics:** `fa_move_*` events registered and classified (`backend/analytics_taxonomy.py`, `docs/business/analytics/2026-11-01-fa-move-events.md`); every row carries `league_platform`.
- **Legal:** Sleeper consent v1 final (adds/drops); v2 (claims) pending; MFL and ESPN texts are **drafts** (`fa_move_copy.DRAFT_CONSENT_VERSIONS`), never served.
- **Designed, not built:** "Update 1", MFL and ESPN server-only (scope §E). This thread builds MFL's half.
- **What blocks Sleeper:** only the capture (capture.md §4, operator-driven; "Nothing below may guess one", `sleeper_write.py:492`). Abandoned? **No.** Nothing in DECISIONS or MISTAKES abandons D1; the capture has simply not been run. The no-guessing rule still holds and this thread keeps it: no Sleeper builder was written from the community hints.

## 3. What each platform needs

UNVERIFIED marks a field known only from documentation (MFL) or community code (Sleeper), never from a recorded request.

### Sleeper (capture.md §2 is the full question list)

| Need | Known | Source |
|---|---|---|
| Endpoint / auth | `POST https://sleeper.com/graphql`, raw JWT in `authorization`, `x-sleeper-graphql-op`, browser headers | **verified** (trade capture 2026-07-02) |
| Add / add+drop | `league_create_transaction(league_id, type: "free_agent", k_adds, v_adds, k_drops, v_drops)` | UNVERIFIED (community CH1) |
| Waiver claim + bid | `submit_waiver_claim(…, k_settings: ["waiver_bid"], v_settings: [amount])` | UNVERIFIED (CH1 + CH2) |
| Edit / cancel claim | `update_waiver_claim` / `cancel_waiver_claim(league_id, transaction_id, leg)` | UNVERIFIED (CH1) |
| My pending claims | `league_transactions_filtered` (already used, verified, for trade offers: `sleeper_write.league_trade_offers`) with waiver filters | op verified, waiver filter UNVERIFIED |
| Immediate vs pending | FA add → a transaction `complete`; claim → `pending`, processed at the waiver run | UNVERIFIED |
| League rules | `waiver_type` (0 rolling, 1 reverse standings, 2 FAAB), `waiver_budget`, roster `waiver_budget_used`, `roster_positions` + `reserve_slots` + `taxi_slots` | **verified** public REST, already read (`_sleeper_waivers`, `_sleeper_roster_limit`) |
| Waiver status of a player before the tap | unknown (capture Q8) | — |
| Lock after kickoff, errors (roster full, taken, FAAB, window) | unknown (capture Q9) | — |

### MFL (api_info, read 2026-11-11)

| Need | Known | Source |
|---|---|---|
| Endpoint / auth | `GET https://{wwwNN host}/{year}/import?TYPE=…`, the `MFL_USER_ID` cookie; "Access restricted to league owners" | docs + **verified** for trades |
| Add / add+drop (immediate) | `TYPE=fcfsWaiver&L=&ADD=<id>&DROP=<id,…>` | UNVERIFIED (docs) |
| Blind-bid claim | `TYPE=blindBidWaiverRequest&L=&PICKS=<add>_<bid>_<drop or 0000>` (ROUND only for conditional blind bidding) | UNVERIFIED (docs) |
| Priority claim | `TYPE=waiverRequest&L=&ROUND=<n>&PICKS=<add>_<drop>` | UNVERIFIED (docs) |
| **REPLACE** | claims are *added* to the round unless `REPLACE` is set, which *replaces the user's other claims* | docs. **We never send it** |
| Cancel a claim | the same claim import with an empty `PICKS` clears the whole round (no single-claim cancel) | docs |
| My pending claims | `export?TYPE=pendingWaivers` (owners only) | docs |
| Free agents | `export?TYPE=freeAgents` | docs |
| League rules | `export?TYPE=league`: roster size, IR/taxi size (field names not documented on api_info); FAAB balance: not documented | gap |
| Answer body | `<status>OK</status>` / `<error>…</error>` (or JSON with `JSON=1`), the trade path's TODO(live-verify) 1 | UNVERIFIED |
| Errors | auth words in `<error>` → auth (existing `_raise_import_error`); 401/403; 429 | partly verified (trade path) |

### ESPN

| Need | Known | Source |
|---|---|---|
| Endpoint / auth | `POST lm-api-writes…/leagues/{id}/transactions/`, `espn_s2` + `SWID`, `x-fantasy-*` headers | **verified** for `TRADE_PROPOSAL` (2026-08-11) |
| Free-agent add/drop, waiver claim, bid, cancel | **unknown**. The envelope (`type`, `executionType`, `teamId`, `memberId`, `scoringPeriodId`, `items[]`, `bidAmount`) is the trade one; the free-agent `type` and item shapes are not documented anywhere we found | — |
| Pending claims | `?view=mPendingTransactions` (verified for trades) | partly |

## 4. Design: one move contract, one adapter per platform

1. **The contract is the existing wire contract** (`docs/plans/sleeper-fa-write/contract.md`), already platform-neutral: one route, the platform from the league row, `{platform}_` codes mapped by suffix, server-authored copy. No new route, no new field, no client change.
2. **One adapter per platform**, each a pure module function with an injectable opener, returning the same neutral result: `{status: complete|pending, result: accepted|partial, transaction_id|None, added[], dropped[], raw}` and raising its module's error with a `write_outcome` kind (`config`/`input` = nothing sent, `network` = nothing sent, `error` = refused, `outcome_unknown` = may have landed). Sleeper: `sleeper_write.fa_move` (shape pending). MFL: `mfl_write.fa_move` (built here). ESPN: none yet.
3. **Two locks per platform, both shipped off:** the `*.send_add_drop` flag (operator's lever, `FTF_FLAGS`) **and** a module constant set only by the commit that records a real transaction (`FA_MOVE_SHAPES_CAPTURED` / `FA_MOVE_SHAPES_VERIFIED`). The adapter refuses before building while its constant is false; the capability and route read both through `_fa_move_live`.
4. **MFL server path** (`_fa_move_core_mfl`): after the shared steps 1–7b (test mode, flags, verified session, body, platform, kill switch, `attempt_id` replay, double-move block), MFL's own 8 (stored credential + the league row bound to this user), 9 (the shared consent step, bound to the lowered `mfl_username`, committed before any MFL call), 10 (crosswalk, stored host, the live `rosters` export, ownership/availability), 11 (claims off), then the shared tail.
5. **The shared tail** (`_fa_move_send`): grant re-read → `sent` row under the atomic double-move block → **one** `write()` call, never retried → `result` row → roster save on `complete` → `fa_move_write_succeeded`. Sleeper keeps its inline copy of the same steps for now: its core is pinned in source order by `test_fa_move_route.py`, and folding it into `_fa_move_send` is best done once, in the Sleeper capture commit, under one review (decision 4 below).
6. **A dead MFL cookie** (on the rosters read or the write) deletes the credential **and** withdraws MFL grants in the same transaction (`delete_mfl_credential(withdrawn_via=…)`, the Sleeper rule), so a reconnect means re-consent.
7. **ESPN stays `unsupported`**: no flag, no builder, until a capture (§8).

## 5. Capability matrix

| | Sleeper | MFL | ESPN | Fleaflicker / local |
|---|---|---|---|---|
| Today (`main`) | `handoff` ("Open in Sleeper to claim") | `unsupported` (NO_ADD_REASON) | `unsupported` | `unsupported` |
| After this branch, flags off | `handoff` | `unsupported`, byte-identical (pinned) | `unsupported` | `unsupported` |
| Flag on, shapes unverified | `handoff` | `unsupported`, byte-identical (pinned) | — | — |
| Flag on, verified, user connected + verified | `submit` (add, add+drop) | `submit` (add, add+drop) | — | — |
| …user not connected / unverified / other account | `submit` → Connect / Verify step | `unsupported` (no MFL connect screen in the binary, contract §6) | — | — |
| Claims | after D5 (claim shape + consent v2) | `claims: false`; a claim → 422 `waiver_claim_unsupported` | — | — |
| Fallback in the sheet | "Open in Sleeper to claim" on every Sleeper failure/hand-off | a neutral line (no MFL opener exists) | NO_ADD_REASON | NO_ADD_REASON |

**Why MFL claims are off at launch:** the claim imports need a waiver round we don't read, MFL's FAAB balance isn't documented, the user's other claims are at stake (REPLACE semantics), and MFL consent v2 doesn't exist. The builder is there and tested so the claim verification is a diff, not a build.

## 6. Pre-flight, confirm, results, roster cache, analytics, untouchables

- **Pre-flight before anything is sent** (each a clear server message, nothing sent): not linked / other account; consent; a player we can't crosswalk; the add already yours or on any roster; the drop no longer yours; a claim (off); the 30 s preflight budget. **Not checked for MFL** (MFL decides, shown as "MFL didn't accept this move, so nothing changed"): roster limit, IR/taxi rules, lock after kickoff, waiver status of the player. Sleeper additionally checks a known roster limit and FAAB (budget, remaining, no unchosen $0).
- **Confirm:** unchanged from D1: the named CTA ("Add A, drop B"), the league named beside it, the finality line, the consent box unticked on first use, and nothing sends without the tap. One `attempt_id` per tap; the server replays a repeated id and blocks a second move of the same player for 15 minutes while an outcome is unconfirmed.
- **Results:** `complete` → "Done" with what was added/dropped; `pending` → "Claim submitted" (Sleeper only for now); failed → the reason and, on Sleeper, the hand-off button; outcome unknown → "Check before resending", no retry, the user checks the platform. MFL returns no transaction id.
- **Roster cache:** on `complete` the server rewrites the user's `league_members` row (dropped off, added on) before answering, then moves the league's fingerprint off-thread; the phone drops its held trade page on the move. For MFL the row is the franchise's (`mfl:{league}.f{franchise}`). Pending, failed and unknown moves never touch it.
- **Analytics:** no new events. The existing `fa_move_*` set already carries `league_platform` (`mfl` is in its closed set); the server's three events fire from the MFL path with the same props (`fa_move_consent_recorded`, `fa_move_consent_withdrawn`, `fa_move_write_succeeded`).
- **Untouchables / Keep:** the drop list leaves them out (`compute_drop_candidates(exclude_ids=untouchables)`), for MFL exactly as for Sleeper, and says how many were left out. The server does not refuse dropping an untouchable the user picks some other way (there is no other way in the sheet); recommendation in §9.

## 7. What was built in this thread vs specified but unverified

**Built (tests green, dark):**
- `backend/mfl_write.py`: `FaMoveRequest`, `build_fa_move_params` (fcfsWaiver / blindBidWaiverRequest / waiverRequest; never REPLACE or FRANCHISE_ID), `fa_move` (refuses before building while unverified), `FA_MOVE_SHAPES_VERIFIED = False`, `FA_CLAIM_SHAPE_VERIFIED = False`, `FA_MOVE_WRITE_TIMEOUTS_S`.
- `backend/server.py`: `mfl.send_add_drop` in `_FA_MOVE_FLAGS`; `_fa_move_live("mfl")`; `_fa_move_capability_mfl`; `_fa_move_core_mfl`; `_fa_move_send`; the free-agents route's MFL drop list (live only).
- `backend/database.py`: `delete_mfl_credential` withdraws MFL grants (a no-op today: no MFL grant can exist).
- `backend/fa_move_copy.py`: one draft message, `player_unmapped`.
- Flag `mfl.send_add_drop` (false) in `feature_flags.py`, `config/features.json` and the three flag fixtures.
- Tests: `backend/tests/test_mfl_fa_move.py` (62); `mobile/tests/check-in-app-claims.js` (13, `npm run test:in-app-claims`).

**Specified but UNVERIFIED (must not be presented as working):** every MFL request (W3–W5) and its answer; MFL claims as a whole; all Sleeper write shapes; everything ESPN.

## 8. Verification: one supervised real transaction per platform

The operator's own league, the operator's own click or explicit go for each write; the agent never sends one. Record the redacted request and answer in this folder (`verification-<platform>.md`), then the verification commit flips the constant and pins the recorded shape as a fixture.

**MFL (add + drop, first):**
1. Pick a free agent the operator actually wants and a bench player to drop, in a league the operator owns a franchise in (a test league is better if there is one).
2. Run one request by hand, outside the app: in a browser signed in to MFL, open `https://{wwwNN}/{year}/import?TYPE=fcfsWaiver&L={league}&ADD={mfl id}&DROP={mfl id}&JSON=1` (the operator's own click). Save the response body (no cookie).
3. Check in MFL: the transaction log shows the add and the drop, once; the roster shows the change; nothing else moved.
4. Then the verification commit: the recorded body as a fixture, `FA_MOVE_SHAPES_VERIFIED = True`, legal's final MFL consent text and `CURRENT_CONSENT_VERSION["mfl"]`.
5. Then, with `mfl.send_add_drop` on (`FTF_FLAGS`), one move from the app in the same league: the sheet names the move, asks for consent, shows "Done"; MFL shows exactly one transaction; Fleeced's Find a Trade no longer offers the dropped player. Flag back off on any surprise.
6. Deliberately try one refusal (an add with a full roster and no drop) and record MFL's `<error>` text, so the 10f line can be checked against it.
7. Claims are a separate run: one blind-bid claim with a drop, then `pendingWaivers`, then clear the round only if the operator has no other claims in it.

**Sleeper:** capture.md §4 exactly as written (the dummy league, the operator's clicks, a redacting interceptor or DevTools copy). Q1, Q2 (add, add+drop) unblock add/drop; Q3 (claim), Q7b (cancel) and legal's v2 unblock claims. Then `docs/plans/sleeper-fa-write/testflight-additions.md`.

**ESPN:** a capture modelled on `docs/plans/espn-send-live-capture-2026-08-11.md`: in a browser signed in to ESPN, one free-agent add with a drop, one waiver claim (with a bid if the league uses FAAB), and a cancel of that claim, each read back through `?view=mPendingTransactions` / the transactions view. Record: the transaction `type` values, the `items[]` entries for ADD and DROP, `bidAmount`, `executionType`, how `scoringPeriodId` is chosen, and the immediate vs pending status. Only then write `espn_write.fa_move` and add `espn.send_add_drop`.

## 9. Open decisions

1. **Run the Sleeper capture session (capture.md §4) this week?** Recommendation: **yes**. It is the only thing between the screenshot's button and an in-app Sleeper add/drop, and the binary is already out.
2. **Verify MFL with one hand-made `fcfsWaiver` in the operator's league (§8 MFL steps 1–3)?** Recommendation: **yes**, and ask legal for the final MFL consent text in parallel.
3. **Schedule an ESPN capture before building anything for ESPN?** Recommendation: **yes**; until then ESPN keeps NO_ADD_REASON.
4. **Fold Sleeper's move tail into `_fa_move_send` in the Sleeper capture commit?** Recommendation: **yes** (one copy of the idempotency/roster-save logic), with `test_fa_move_route.py`'s source-order pin moved to cover both functions.
5. **Should the server refuse a drop of a Keep/untouchable player?** Recommendation: **no** for now: the sheet never offers one, and refusing would need a new code the binary doesn't map (it would show the neutral panel).
6. **Keep MFL claims off at Update 1 launch?** Recommendation: **yes** (round, FAAB balance and REPLACE semantics unverified).
