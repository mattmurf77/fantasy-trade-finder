# Sleeper free-agent add/drop and waiver-claim writes: capture spike prep (2026-10-20)

> Spike prep for #351 **D1**: FTF executes a Sleeper add/drop or waiver claim itself, through Sleeper's private GraphQL API, the way `propose_trade` already does. This doc is preparation only. **The capture is pending the operator**: nothing here was observed on Sleeper, and nobody called Sleeper to write it. Checked against `origin/main` @ `678834ab` on 2026-10-20.

**Operator decision (2026-10-20, relayed by platforms-eng):** #351 D1, "Yes. With User authorization to do so. (A checkbox for the first attempt every 7 days)". This follows #351's finding that no deep link can prefill an add/drop (`docs/plans/sleeper-fa-deeplink/feasibility.md` § Decisions needed, D1, on branch `origin/plan/sleeper-fa-deeplink`).

**Precedent:** [`../sleeper-write-capture-runbook.md`](../sleeper-write-capture-runbook.md), the 2026-07-02 capture behind `propose_trade`. This spike reuses its method, safety preamble and hand-back shape.

## Contents

1. [What we already know](#1-what-we-already-know)
2. [What the capture must answer](#2-what-the-capture-must-answer)
3. [Community hints (UNVERIFIED)](#3-community-hints-unverified--community)
4. [Operator steps](#4-operator-steps)
5. [Redaction rules](#5-redaction-rules)
6. [Hand-back template](#6-hand-back-template)
7. [What the build needs after capture](#7-what-the-build-needs-after-capture)
8. [Risks](#8-risks)

---

## 1. What we already know

Everything below is cited to `origin/main` @ `678834ab`, and all of it comes from the trade-write precedent. **None of it has been observed for an add, a drop or a waiver claim.**

**Endpoint and body.** Every op goes to `POST https://sleeper.com/graphql` with a body of `{operationName, variables, query}` (runbook :141; `backend/sleeper_write.py:51`).

**Headers** (runbook :142; `backend/sleeper_write.py:338-354`):
- `content-type: application/json`.
- `x-sleeper-graphql-op: <operationName>`.
- `authorization: <JWT>`. This is the **raw token with no `Bearer ` prefix**. A `Bearer `-prefixed token returns 401 "Your token is invalid." (verified 2026-07-08).
- A real browser User-Agent plus `origin`/`referer`/`accept`/`accept-language` (`_BROWSER_HEADERS`, `backend/sleeper_write.py:62-71`). Without them Cloudflare answers error **1010** before the request reaches Sleeper.
- No cookie, CSRF token or signature is needed (runbook :142).

**Error mapping** (`backend/sleeper_write.py:78-97`, `:366-398`):
- HTTP 401/403 → `SleeperAuthError`.
- Other HTTP errors → `SleeperWriteError`.
- `URLError` → `kind="network"`.
- GraphQL `errors[]` arrives on an HTTP 200. The first error's `message` becomes `detail`. If the dump contains auth words (`auth`, `token`, `forbidden`, `login`), the error is classified as auth.
- On success the function returns `data[op]`, reduced to `{transaction_id, status, raw}`. That return shape is trade-specific and would need widening for these ops.

**A second GraphQL client.** `backend/trade_block_service.py:65-96` sends the public `league_players` query with no `authorization` header and the same browser headers. Sleeper's Players tab probably reads waiver state through that same query; the capture confirms or refutes it (§2, Q8).

**Token custody.**
- The token is Sleeper's own 365-day HS256 JWT. It is a **full-account credential** (runbook :128, :134; `docs/integrations/sleeper.md` §2.2).
- It is captured from `localStorage['token']` by `SleeperConnectScreen`'s WebView, so FTF never handles the password.
- It is stored Fernet-encrypted (`SLEEPER_TOKEN_KEY`, `backend/sleeper_write.py:105-138`) in the **`sleeper_credentials`** table (`backend/database.py:2358-2381`; helpers at `:13389-13466`). That table is the "interim home". The `linked_sources` table the runbook names (:118, :175) **does not exist** on `origin/main` (`database.py:2371`).
- The write route requires a **verified** session with no grace period (`backend/server.py:19454`, `:19506`).
- Expiry is checked before every send, and an expired credential is deleted (`:19522`).
- When Sleeper rejects the token, the credential is deleted and the route returns `409 sleeper_rejected` (`:19610`). Any other failure returns `502 sleeper_write_failed` (`:19620`).
- Under `FTF_TEST_MODE` the route fails closed (`:19436`, `:19499`).
- The current flag, `trade.send_in_sleeper`, is `true` (`config/features.json:52`).
- §6 of `docs/integrations/sleeper.md` defines what is safe to log and what must be redacted, by key name. The JWT and the `authorization` value are never logged, and GraphQL error bodies are truncated to 500 characters because they can echo variables back.

**How `roster_id` is known.**
- `propose_trade` takes no proposer roster argument. Sleeper derives the proposer from the token (runbook :158).
- FTF still resolves both rosters server-side from the public `GET /v1/league/<id>/rosters`, using `_fetch_league_rosters` (`server.py:17118`) and `_roster_id_for_owner` (`server.py:19224`). The second is co-owner aware and never trusts a client roster id. The call happens at `server.py:19529-19530`, keyed by `sleeper_credentials.sleeper_user_id`.
- An add/drop can reuse this unchanged. The capture tells us whether Sleeper wants the roster id as a variable (§2, Q3).

**What FTF already knows at the claim-sheet tap** (`mobile/src/components/ClaimSheet.tsx:111-145`; `GET /api/league/free-agents`, `server.py:30415`):
- The FA's `player_id` (a Sleeper id), `name`, `position` and `team`.
- `dropId`, chosen from `drop_candidates` (value-ascending, capped at 8).
- `bid`, when `waivers.type == 'faab'`, checked against `faab.remaining` (`ClaimSheet.tsx:126-132`). Waiver type is mapped from league `settings.waiver_type` (`server.py:30386`: 0 rolling, 1 reverse standings, 2 FAAB). Remaining FAAB is the league `waiver_budget` minus the roster's `settings.waiver_budget_used` (`server.py:30389-30412`).
- `open_slots` (`server.py:30367`; lineup + bench + IR + taxi).

What FTF does **not** know at the tap:
- Whether the player is a free agent or **on waivers**, and until when.
- Whether the drop sits in IR or taxi.

**How FAAB is encoded in `propose_trade` (Q-016, unresolved).**
- `waiver_budget` is inlined into the query. The only value ever captured is `[]`.
- FTF's builder emits `[{sender, receiver, amount}]` as a GraphQL object literal. That shape is an **inference** (`backend/sleeper_write.py:27-34`, `:321-325`).
- The public `__schema` dump cited in `docs/plans/sleeper-pending-trades-feasibility-2026-08-12.md:79` types the argument as `[String]`.
- No caller sends FAAB today (`living-memory/OPEN_QUESTIONS.md:289`).
- A waiver-claim **bid** is a different argument on a different op (§3). Don't conflate the two.

**Public transactions.**
- The public read is `GET /v1/league/<id>/transactions/<week>`. `backend/sleeper_trades_service.py` already reads it, filtered to completed trades (`docs/integrations/sleeper.md` §1.1, row 11).
- The 2026-08-12 sweeps saw **781 `waiver` rows with `status: "failed"`** in public payloads (`sleeper-pending-trades-feasibility-2026-08-12.md:27`). So waiver outcomes publish, including failures.
- Whether a **pending** claim publishes is unknown (§2, Q12).

---

## 2. What the capture must answer

**Ops.** For each action, the capture needs the `operationName`, the `x-sleeper-graphql-op` value, the **full** query or mutation string, and whether ids are inlined or passed as variables:

- **Q1 (a)** Free-agent add **with** a drop.
- **Q2 (b)** Free-agent add **without** a drop (an open roster slot).
- **Q3 (c)** Waiver claim with a FAAB bid and a drop.
- **Q4 (d)** Edit a pending claim (change the bid; reorder if the UI offers it) and **cancel** a pending claim.
- **Q5 (e)** The read that lists **my pending claims**. Also capture the read the Players tab fires to show waiver status.

**Variables and encodings:**
- **Q6** Are player ids strings? Is `roster_id` an int? Is the drop a list? Are adds and drops parallel arrays (`k_adds`/`v_adds`, as in `propose_trade`) or something else?
- **Q6, continued** Is our own `roster_id` a variable, or derived from the token as in `propose_trade`?
- **Q6, continued** How is the FAAB bid carried? What carries the leg or week?
- **Q6, continued** Are there any arguments the UI sends that we haven't seen before, such as a sequence or priority, or `expires_at`?

**Success responses:**
- **Q7** Does a FA add return an **immediate** transaction (record its `type` and `status` values)?
- **Q7, continued** Does a waiver claim return a **pending** claim with a `transaction_id`? Record the exact status string, and the `leg` the claim is filed under.

**Free agent vs waiver:**
- **Q8** Is the choice made **client-side** or **server-side**?
- **Q8, continued** Which field tells the client that a player is on waivers, and until when? Is it `league_players.settings` or another read?
- **Q8, continued** Does the UI ever let a FA-add request go out for a player who is on waivers?

**Error shapes.** For each case, record the HTTP status and the GraphQL `errors[].message` verbatim, **or** "UI blocked it, no request sent":
- **Q9.1** Roster full with no drop.
- **Q9.2** FA add on a player who is on waivers.
- **Q9.3** Player locked after kickoff. This can only be produced while that player's game is in progress.
- **Q9.4** Bid greater than remaining FAAB.
- **Q9.5** An add during the waiver-processing window.
- **Q9.6** IR/taxi rules: a drop from IR or taxi, an add while IR holds an ineligible player, and whether taxi counts toward roster size.
- **Q9.7** An expired or invalid token. Already known: 401 "Your token is invalid." **Do not reproduce it.**

**Rate and abuse signals:**
- **Q10** Any rate-limit or retry response header, any 429, any Cloudflare challenge or 1010, any captcha/Turnstile, any extra request header the web client adds on writes that `propose_trade` didn't need.

**Side effects:**
- **Q11** Does Sleeper fire companion ops around the write (a league chat post, a notification), the way `create_message` follows `propose_trade` (runbook :161)? FTF would not reproduce those.

**Public visibility:**
- **Q12** After (a) and (b), does the public `/v1/league/<id>/transactions/<week>` show the move immediately? Record its `type` (`free_agent`?) and `status`.
- **Q12, continued** Does the pending claim from (c) appear there before processing (expected: no)?
- **Q12, continued** After the league's waiver run, does it appear as `waiver` with `complete` or `failed`?
- **Q12, continued** Which week is it filed under?

---

## 3. Community hints (UNVERIFIED — community)

**Everything in this section is UNVERIFIED — community.** It is public open-source code read on **2026-10-20**. FTF never sent these requests and never called Sleeper to check them. Use it as a checklist to confirm or refute, never as a spec.

**Sources:**
- **CH1:** [`joscaz/sleeper-mcp`](https://github.com/joscaz/sleeper-mcp), file `src/sleeper/graphql.ts`. Last commits 2026-09-14, 2026-09-16 and 2026-10-17. Its comments say the op names were "taken from the live schema via introspection".
- **CH2:** [`bealmot/sleeper-mcp`](https://github.com/bealmot/sleeper-mcp), file `API-NOTES.md`. Last commit 2026-10-11. It says introspection is open, with about 349 mutations.
- **CH3:** FTF's own 2026-08-12 memo, `docs/plans/sleeper-pending-trades-feasibility-2026-08-12.md:67-79`. It cites a public `__schema` dump dated 2025-10-17 and treats `league_transactions_filtered` as reachable.

| Action | Op (UNVERIFIED) | Arguments (UNVERIFIED) | Sources |
|---|---|---|---|
| (a)/(b) FA add/drop, immediate | `league_create_transaction` | `league_id: Snowflake!`, `type: String!` (= `"free_agent"`), `k_adds: [String]`, `v_adds: [Int]`, `k_drops: [String]`, `v_drops: [Int]`. Parallel arrays, player_id → roster_id; an empty side is sent as `null`. No `leg` argument | CH1 only |
| (c) Waiver claim | `submit_waiver_claim` | `league_id`, `k_adds`/`v_adds`, `k_drops`/`v_drops`, `k_settings: [String]`, `v_settings: [Int]`. Bid = `k_settings: ["waiver_bid"]`, `v_settings: [<amount>]`. CH1 also packs `seq` (order among your own claims, 1 = first). No `type` or `leg` argument | CH1 + CH2 agree on the op and the `waiver_bid` encoding |
| (d) Edit claim | `update_waiver_claim` | `league_id`, `transaction_id`, `leg: Int!`, `k_settings`/`v_settings` (`waiver_bid`, `seq`); no adds or drops | CH1 only |
| (d) Cancel claim | `cancel_waiver_claim` | `league_id`, `transaction_id`, `leg: Int!` | CH1 only |
| (e) My pending claims | `league_transactions_filtered` (query) | `league_id`, `type_filters`, `status_filters`, `leg_filters: [Int]`, `roster_id_filters: [Int]`, `limit`. CH2's observed types: `free_agent`, `waiver`, `trade`, `draft_pick`. CH2's observed statuses: `complete`, `cancelled`, `rejected`, `failed` (it never lists a pending value). CH1 says it needs league membership | CH1, CH2, CH3 |

Other community notes, also UNVERIFIED:
- **Headers.** CH1 sends the raw token in `authorization` with no `Bearer`, and sends `x-sleeper-graphql-op`. That matches FTF's verified headers.
- **Selection set.** CH1's selection set: `transaction_id type status status_updated created creator leg league_id roster_ids consenter_ids adds drops draft_picks waiver_budget settings metadata`.
- **Rate limits.** CH1 handles HTTP 429 as a rate limit.
- **Public endpoint.** CH2 says the public REST endpoint never returns pending transactions, and that GraphQL and REST disagree on cancelled/failed rows.
- **Other roster writes.** CH1 also lists `roster_update_reserve` (IR) and `roster_update_taxi`. Those are out of scope here, but relevant to Q9.6.
- **Not ours to copy.** CH1 also has a password `login` op. FTF does not, and must not, use it; FTF's token custody is the WebView capture (§1).

---

## 4. Operator steps

**Who does what.**
- The capture runs **in the `platforms-eng` session, with the operator present and saying "go"** before each action.
- **Every Sleeper mutation is the operator's own click.** The agent never clicks a Sleeper button that writes, never logs in, never sees or stores the token, and never replays a request.
- The agent only reads the traffic of the operator's actions and writes the redacted results.

### Before the session (operator)

1. **Pick the account.**
   - **Default:** the dummy Sleeper account and dummy league from the 2026-07-02 capture (runbook §0 safety preamble).
   - **Never** a real account or a real league. If you'd rather use a fresh throwaway account, say so before starting.
2. **Check the dummy league is usable.**
   - It is in season with drafted rosters (an autodraft is fine).
   - At least two rosters are occupied.
   - If it's still pre-draft, finish a draft first, or make a new dummy league.
3. **As commissioner, open the league settings.**
   - Set waivers to **FAAB** with a budget, for example $100.
   - Note the **waiver clear day and time**, and how long a dropped player stays on waivers.
   - We have not verified Sleeper's exact menu labels.
4. **Stage the roster.**
   - Leave **one open roster slot** for step 9 (b).
   - Make sure **at least one player is on waivers**. Dropping a rostered player usually puts him there for the waiver period. Step 10 (a) also does this.
5. **Set up the browser.**
   - Desktop Chrome with the **Claude-in-Chrome extension connected**.
   - The `platforms-eng` session open and ready.

### In the session

6. **Log in.** In a Chrome tab, log in to sleeper.com **yourself**, then open the dummy league's **Players** tab. The agent does nothing during login.
7. **Say "go" to start capture.** The agent then turns on network reading for that tab.
   - In 2026-07-02, the extension's network reader returned **URLs only** (runbook :163). Bodies came from an injected, **redacting** `fetch`/XHR interceptor. If that is still true, the agent installs one, **with your go**.
   - **Allowlist recorded:** request URL, method, the `x-sleeper-graphql-op` value, `operationName`, `query`, `variables`, response status, the response body (truncated), and the names and values of any response header containing `rate`, `limit` or `retry`.
   - **Never recorded:** the `authorization` header or any cookie. The interceptor never reads `localStorage` or `document.cookie`.
   - A page reload removes the interceptor. The agent reinstalls it after any navigation and says "ready" each time.
   - **Fallback, if you'd rather not inject:** after each action, right-click the `graphql` request in DevTools → Network, Copy as fetch, **delete the `authorization` line yourself**, and paste the rest into the session.
8. **Pause after every action.** For each action below, you click; the agent reads that request and says "captured"; then you move on.
9. **(b) FA add, no drop.** Add a free agent into the open slot.
10. **(a) FA add with a drop.** With the roster now full, add another free agent and choose a drop. The dropped player is likely now on waivers, which makes him a target for step 12.
11. **Public check after (a) and (b).** Open `https://api.sleeper.app/v1/league/<dummy league id>/transactions/<current week>` in a new tab. The agent reads the page text. This is a public, unauthenticated GET.
12. **(c) Waiver claim.** Claim a player who is on waivers, with a FAAB bid (for example $7) and a drop.
13. **(e) Read pending claims.** Open wherever Sleeper lists your pending claims. The agent notes which query fires and what status the claim shows.
14. **(d) Edit, then cancel.**
    - Change the claim's bid (and reorder it, if offered).
    - Then **cancel** the claim.
    - Then **re-submit** one claim the same way as step 12, and **leave it pending** for step 17.
15. **One deliberate error, required.** Try these in order and stop at the first that reaches Sleeper's server:
    - (i) roster full, add with **no** drop;
    - (ii) bid above remaining FAAB;
    - (iii) a FA add on a player who is on waivers.
    For each attempt, the agent records whether the UI blocked it, meaning no request was sent, or what error came back.
    - **Opportunistic:** the locked-after-kickoff case (Q9.3) is only possible during a game window (Thursday night or Sunday). Do it then, or leave it for the build's TestFlight checklist.
16. **Optional, closes Q-016.** If the league allows FAAB in trades, propose one trade to the dummy team that includes FAAB, then reject it. The agent records how `waiver_budget` is encoded.
17. **Tear down.**
    - The agent removes the interceptor by reloading the tab and confirms it recorded nothing it shouldn't have.
    - You **log out of the dummy account** on sleeper.com (runbook §0) and close the tab.
    - After the league's next waiver run, repeat step 11 so the agent can record the claim's final public row. That repeat is a read only and needs no login.

### After the session (agent)

18. Write only the redacted results into a "Captured results" section at the bottom of this doc, using the §6 template. Check every line against the §5 rules before committing.

---

## 5. Redaction rules

**May be written to this doc:**
- Op names and `x-sleeper-graphql-op` values.
- Full query and mutation strings, with inlined ids swapped for placeholders.
- Variable **shapes**, with every id replaced by a typed placeholder: `<LEAGUE_ID:string>`, `<PLAYER_ADD:string>`, `<PLAYER_DROP:string>`, `<ROSTER_ID:int>`, `<TXN_ID>`, `<LEG:int>`. A FAAB amount may stay as a number.
- HTTP status codes.
- GraphQL `errors[].message` strings, truncated to 500 characters, with any echoed ids swapped for placeholders.
- Response field **names**, and enum values such as `type` and `status`.
- Response header names, and rate-limit values.
- Yes/no observations, such as "UI blocked it, no request sent".

**May not be written anywhere: doc, commit, chat, scratch file or log:**
- The token or JWT in any form, whether full, truncated or hashed.
- Any `authorization` header value, cookies, and the `SLEEPER_TOKEN_KEY`.
- The dummy account's email, phone or password.
- Real user ids, usernames, display names or avatars of anyone. Response `creator`, `metadata`, `consenter_ids` and `player_map` blocks get stripped to field names.
- League ids of any real league. Even the dummy league's id goes in as a placeholder.
- Raw HAR exports, screenshots of signed-in pages, and unredacted response bodies.

**Raw notes.** Any raw capture lives only in the session scratchpad, never in the repo, and is deleted once this doc is written. The rule is the same as `docs/integrations/sleeper.md` §6.2: **redact by key name**, don't rely on hoping a value never appears.

---

## 6. Hand-back template

```
### Capture — <date>, dummy account + dummy league (operator-driven, agent read-only)
- capture method: extension network reader / injected redacting interceptor / manual Copy-as-fetch
- request: POST https://sleeper.com/graphql   headers beyond the known 5 + browser UA: <none / list names>

### (a) FA add WITH drop
- operationName / x-sleeper-graphql-op: <…>
- mutation (full, ids → placeholders): <…>
- variables (shape): <…>      ids as: string / int      own roster_id sent? yes / no (derived from token)
- success response: { transaction_id, type: <…>, status: <…>, leg: <…>, … }   immediate? yes / no
- companion ops fired (e.g. chat post): <none / list>

### (b) FA add WITHOUT drop
- op / mutation / variables: <same op as (a)? yes / no — diff: …>
- success response: <…>

### (c) Waiver claim (FAAB bid + drop)
- op / mutation / variables: <…>      bid carried as: <…>      leg/week carried as: <…>
- success response: { transaction_id, status: <exact string>, leg: <…>, … }
- FA-vs-waiver decided: client-side (field: <…> from read <…>) / server-side

### (d) Edit + cancel pending claim
- edit op / mutation / variables: <…>
- cancel op / mutation / variables: <…>
- responses: <…>

### (e) Read my pending claims
- query op / variables / filters: <…>
- pending claim's status string: <…>
- players-tab waiver-status read: <op + field name>

### Errors (HTTP status + errors[].message verbatim, or "UI blocked, no request")
- roster full, no drop:            <…>
- FA add on a waiver player:       <…>
- locked after kickoff:            <… / not attempted>
- bid > remaining FAAB:            <…>
- add during waiver processing:    <… / not attempted>
- IR/taxi:                         <… / not attempted>

### Public /v1/league/<LEAGUE_ID>/transactions/<week>
- after (a)/(b): visible? yes / no   type: <…>   status: <…>
- pending claim before processing: visible? yes / no
- after waiver run: type: <…>   status: complete / failed   week filed under: <…>

### Rate / abuse signals
- rate-limit headers / 429 / Cloudflare / captcha: <none / list>

### Optional — Q-016 FAAB-in-trade
- waiver_budget encoding observed: <…>   → close Q-016 / not attempted

### Teardown
- interceptor removed: yes   operator logged out of dummy account: yes   raw notes deleted: yes
```

---

## 7. What the build needs after capture

This is a short list, not the build spec. The build also goes through the four feature gates in CLAUDE.md: scope block, evidence, docs, ledger.

1. **`backend/sleeper_write.py`.** Add pure body builders and issue functions for the captured ops (add/drop, claim, edit, cancel, read pending). Reuse `_post_graphql`; its `{transaction_id, status}` return shape needs widening. Extend error classification so the captured error strings map to structured codes. Unit tests use the injected `_opener` and never touch the network.
2. **A new route** that follows `POST /api/trades/propose` and `_sleeper_propose_core` (`server.py:19419-19669`):
   - Fail closed under test mode, then the flag gate, then a verified session with no grace period.
   - Decrypt the credential and check its expiry.
   - Resolve `roster_id` server-side.
   - Check server-side that the drop is on the user's roster and that the bid is no more than remaining FAAB (`_sleeper_waivers`).
   - Decide free agent vs waiver however the capture says Sleeper decides it.
   - Show the user an explicit confirm step.
   - Note: the propose route has no cross-request idempotency (`server.py:19476-19477`), and a retried add/drop needs a decision on that.
3. **The 7-day consent gate.** A per-user consent timestamp, enforced server-side; the client checkbox alone is not enough. The **schema proposal goes to head-eng**. One thing to settle there: does "the first attempt every 7 days" mean per user or per user and league?
4. **A new default-OFF flag**, **named by release-lead**, in `config/features.json`.
5. **Docs:**
   - `docs/api-reference.md` (the route).
   - `docs/data-dictionary.md` (the consent column or table).
   - `docs/config-reference.md` (the flag).
   - `docs/integrations/sleeper.md` (§1.2 ops table and its endpoint count, §3.3 shapes, §4 errors).
   - A DECISIONS entry superseding D-019's "FAAB claims have no API at all" and the #179 posture. `ClaimSheet`'s footer, "Sleeper doesn't allow apps to submit claims", becomes false wherever the flag is on.
6. **Analytics only with analytics-lead's grant.** A grant means registering the events in the taxonomy and in `NON_INTENT_EVENTS` in the same commit; D-031's server-success / client-attempt split is the precedent.
7. **Evidence.** Unit tests, a code-walk, and a concrete manual TestFlight checklist run against the dummy league, including the game-window and waiver-processing cases the capture couldn't reach.

---

## 8. Risks

- **ToS / E2, open with legal-lead.**
  - Runbook C4 (:136-138) recorded that a Sleeper write path is ToS-adverse on several counts. The operator accepted that risk on 2026-07-02 as a flagged, opt-in beta.
  - **E2** was opened 2026-10-15 in the platform risk register (`.claude/skills/pm-partnerships/references/platform-risk-register.md`, branch `origin/skill/pm-partnerships`). Sleeper's Terms were revised 2026-10-06, with §11.1 and §11.3 barring automated or commercial use without written consent. The operator stated an agreement with Sleeper on 2026-08-12, but it is not filed in the repo.
  - #351's PRD says the D1 write spike waits on E2. This doc is preparation only. Whether the capture session itself runs before E2 closes is the operator's call (E2, decision 3).
- **Account bans.** §11.2 lets Sleeper revoke sessions and block third parties. A roster write made from FTF's servers with an impersonated Chrome User-Agent puts the **user's** Sleeper account at risk, not just FTF's access. That risk falls on users who opted in.
- **No undo.** A FA add with a drop **executes at once**: the dropped player goes to waivers, and FTF cannot reverse it. A `propose_trade` waits for the other side to accept; this does not. It would be FTF's highest-blast-radius write, which is why the confirm step and the server-side drop and bid checks are not optional.
- **App Store.** Apple guidelines 5.2.2 and 4.x (runbook C4). A new write class widens the same exposure Send in Sleeper already carries.
- **Token custody.** The same full-account JWT in `sleeper_credentials` gets a new, more consequential use. The 7-day checkbox is the **user's** authorization, but §11.3 says a user's grant is not Sleeper's authorization.
- **Timing.**
  - Waiver claims process on the league's schedule, so the result is not immediate. FTF must say "claim submitted" and never "added".
  - Learning the outcome means reconciling later, either from public transactions (where waiver results, including failures, do publish) or through an authed `league_transactions_filtered` read, which is one more private call.
  - Adds may be blocked during the processing window and after kickoff.
- **Schema drift.** The API is undocumented, and the community notes warn it can change without notice. Every captured shape is true only as of its capture date.
