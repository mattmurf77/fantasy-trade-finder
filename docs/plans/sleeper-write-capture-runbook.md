# Sleeper Write API — Capture Runbook (Spikes C1–C4)

*Companion to [auth-multiplatform-plan-2026-06-11.md](auth-multiplatform-plan-2026-06-11.md) Part C. Goal: capture the real, current shape of Sleeper's undocumented **login→token** flow and **trade-create** call so FTF can build in-app "Send in Sleeper" **against captured traffic, not a guess.** Everything in Part C is gated on C1+C2. Created 2026-07-02.*

> **Why a human has to run this.** These are undocumented, auth-gated endpoints that only appear in the traffic of a *logged-in* Sleeper session. Capturing them requires logging into Sleeper and proxying live requests — it can't be done from the public API or by an agent. Run it once, paste the (redacted) results back using the "Hand-back template" at the bottom, and the build becomes mechanical.

---

## 0. Safety preamble (read first)

- **Use a throwaway Sleeper account**, not your real one. Create a fresh account + a **test league with 2 rosters** (you + one dummy team) so you can propose a real trade to capture C2. (You can reuse the synthetic Lakeview test setup conceptually, but Sleeper trades need a *real Sleeper league*, so make one on Sleeper itself.)
- **The captured token is a live credential** — treat the capture files as secrets. Do not commit them, do not paste raw tokens into chat. Redact per the template.
- **Read-only reconnaissance of your own account is the benign case**, but see C4 before building anything that ships.
- After capture, **log the throwaway account out / rotate** so the captured token dies.

## 1. Tooling (pick one capture path)

| Path | Tool | Best for | Notes |
|---|---|---|---|
| **Web** (easiest) | Browser DevTools → Network tab, filter `graphql` / `Fetch/XHR` | C1 + C2 quickly | sleeper.com is a web app; everything the app does is visible here. **Start here.** |
| **Mobile** | [mitmproxy](https://mitmproxy.org/) or Charles Proxy + device cert install | Confirming the *mobile* flow (may differ from web) | Needs the mitm CA cert trusted on the device; iOS also needs cert trust toggled in Settings. Some apps cert-pin — if requests don't appear, the app pins and you fall back to the web capture. |

**Recommendation:** do C1 + C2 on **web DevTools first** (fastest, no cert dance), then optionally confirm on mobile if the mobile app's flow matters for the RN webview approach.

## 2. C1 — Capture login → token  *(gates everything)*

**What you're answering:** where the token comes from, what it looks like, where it rides on later requests, and — the decisive one — **whether FTF can obtain it without handling the password** (webview/cookie extraction) or whether only direct credential submission works (App-Store-risky).

Steps (web):
1. Open DevTools → Network, check **"Preserve log"**, filter to `Fetch/XHR`.
2. Go to sleeper.com, **log in** with the throwaway account.
3. Find the **login request** (look for a POST around the moment you submit — likely to `sleeper.com/graphql` with a `login`-type operation, or a REST login endpoint). Record:
   - Request URL + method.
   - Request body shape (does it send email/password? phone? a device id?).
   - **Response**: the token field name + format (JWT? opaque?), and any refresh token / expiry.
4. Now click around (open your league). Inspect a couple of **authenticated** requests and record **where the token rides**: `Authorization: Bearer …` header? a cookie? a custom header?
5. **The decisive question:** after login, is the token sitting somewhere a webview could read (a readable cookie, `localStorage`, or a response body FTF's own code fires) — or is it only ever in an `httpOnly` cookie / in-memory JS state? 
   - Check DevTools → Application → Cookies (is the token cookie `HttpOnly`?) and Local Storage / Session Storage.
   - **If readable → the no-password webview capture is viable (preferred).**
   - **If only httpOnly/in-memory → FTF would have to submit credentials itself (password-handling path — flag the App Store risk).**

**C1 output = the login handshake + a go/no-go on no-password capture.** This determines the whole UX and the App Store posture.

## 3. C2 — Capture the trade-create call  *(do not build without this)*

**What you're answering:** the exact request FTF must reproduce to propose a trade.

Steps:
1. With capture still running and logged in, **propose a real trade** to the dummy team in your test league (offer a player, request a player, optionally include a draft pick).
2. Find the request fired at the moment you hit "Send"/"Propose" (filter `graphql`; look for a mutation, or a POST to `api.sleeper.com`). Record **all** of:
   - URL + method + the auth header/cookie it carries.
   - **Operation name** (GraphQL `operationName`) and the **full query/mutation string**.
   - **Variables**, exactly: league id, **your `roster_id`** (note: trades key on `roster_id`, not `user_id` — record how the app knows your roster_id), the **adds/drops as player_ids** (and the encoding — array? object keyed by roster?), **draft picks** (how a future pick is encoded: season+round+original-roster?), and the **counterparty/consenter** target.
   - **Success response**: the created transaction id + status (is it `pending`?).
3. Capture the **adjacent flows** too (cheap while you're here, needed for the full feature):
   - **Accept** and **Reject** a pending trade (from the other side / another session) → the disposition mutation.
   - **Cancel** a proposal you sent.
   - **Read pending offers**: check whether open proposals appear in the **public** `/league/<id>/transactions/<week>` REST, or only in an authenticated call (Part C flagged this — confirm here).
4. Record a couple of **error responses**: propose an invalid trade (a player you don't own, a locked league) and capture the error shape → drives FTF's error handling + degradation.

**C2 output = a validated, reproducible propose-trade request** (operation, variables, auth, response, errors).

## 4. C3 — Token lifetime + failure modes

- How long is the token good for? Is there a refresh token / refresh call, or does the user re-login?
- What does an **expired-token** response look like (so FTF can detect it and re-prompt)?
- Any obvious **rate limiting** on repeated writes?

## 5. C4 — ToS / legal gut-check  *(cheapest gate — do before investing in C1/C2 capture effort)*

- Read Sleeper's current **Terms of Service** re: automated/programmatic access and acting on your own account.
- Note how exposed the competitor appears to be (are they doing exactly this openly?).
- **Decision:** proceed / proceed-with-flag-and-beta / don't. Part C treats this as best-effort-with-degradation regardless, but confirm the appetite before betting the flagship on it.

---

## Hand-back template (fill in, redact secrets, paste back)

```
### C1 — login/token
- login request:  <METHOD> <URL>
- login body sends password?  yes / no   (if no: what? phone OTP / device / …)
- token field in response:    <name>     format: JWT / opaque     expiry: <…>
- refresh token?               yes / no   (call: <…>)
- token rides on authed reqs as:  Authorization: Bearer  /  cookie <name>  /  <header>
- token readable by a webview?    yes (cookie non-httpOnly / localStorage)  /  NO (httpOnly / in-memory)
   → no-password capture viable?   YES / NO
- REDACT the actual token value.

### C2 — propose trade
- request:        <METHOD> <URL>   auth: <header/cookie name>
- operationName:  <…>
- mutation/query: <paste full string>
- variables (shape, with sample values — redact ids if you like):
    league_id, roster_id (how obtained: <…>), adds: <…>, drops: <…>,
    draft_picks: <encoding>, consenter/target: <…>
- success response: { transaction_id, status: <pending?>, … }
- accept mutation:  <op + vars>
- reject mutation:  <op + vars>
- cancel mutation:  <op + vars>
- pending offers readable via public transactions REST?  yes / no
- error response (invalid trade): <shape>

### C3 — lifetime
- token TTL: <…>   refresh: <…>   expired-token response: <…>   rate limits: <…>

### C4 — ToS
- verdict: proceed / flag+beta / no   notes: <…>
```

---

## What happens after you hand this back

With C1+C2 in hand, the build is mechanical and slots into Part C exactly as scoped:
1. `backend/sleeper_write.py` — a `SleeperWriteAdapter` configured from the captured request (operation, variables, auth placement).
2. `POST /api/trade/propose` — authenticated FTF session → decrypt the user's stored Sleeper token → issue the captured request → return `{status, transaction_id}` or a structured failure that triggers the deep-link fallback.
3. Sleeper-login capture flow (webview if C1 says no-password is viable; otherwise the flagged credential path) → store the token **encrypted** in `linked_sources.credentials_ref`.
4. Mobile: the **"Send in Sleeper"** button on all four trade surfaces (see the build plan in the accompanying message / Part C) → calls `/api/trade/propose` → "proposal sent" on success, deep-link fallback on any failure.

---

## Captured results — live capture 2026-07-02 (Chrome extension, browser DevTools path)

*Captured by driving the Chrome extension over a **dummy Sleeper account + dummy league** (operator logged in and drove all credentialed actions; agent read traffic only). No secrets recorded — token values were redacted at capture. **C1 / C3 / C4 complete; C2 pending** a second occupied roster.*

### C1 — login → token  ✅
- **Decisive question — is no-password capture viable? → YES.** After login, the auth token sits in **`localStorage['token']`** as a readable JWT (len ~312) **and** as a readable (non-`HttpOnly`) cookie. A webview can read it directly, so **FTF never handles the password and does not need to reproduce the login handshake** — it opens Sleeper's own login page in a webview, lets Sleeper handle password / OTP / passkey / 2FA, then reads `localStorage['token']`.
- **Token format:** JWT, **HS256**, self-contained. Claim keys only: `user_id, display_name, real_name, avatar, is_bot, is_master, valid_2fa, iat, exp`.
- **Login POST shape:** not captured (the post-login redirect wiped the network log) — and **not needed** for the webview path. If ever required, capture it with the injected interceptor below, not the network reader.
- **Token placement on authed requests:** to confirm alongside C2 (expected `Authorization: Bearer <jwt>`).

### C3 — lifetime  ✅
- **TTL = 365 days** (iat→exp exactly one year). **No refresh token needed.** On expiry/logout → re-prompt the webview login. `valid_2fa` is embedded in the token, so 2FA is fully resolved on Sleeper's side during the webview login.

### C4 — ToS  ⚠️ (risk accepted)
- Sleeper publishes a **read-only** public API (docs.sleeper.com) and **no sanctioned write API**. The General Terms of Use grant a **personal, non-commercial** license and prohibit **reverse-engineering, scraping "in any form for any purpose without written consent," circumventing technological measures,** and derivative works (§9.2 + the prohibited-conduct list). The "Send in Sleeper" write path is **ToS-adverse on multiple counts.** Stacked risks: App Store (Apple 5.2.2 / 4.x), end-user account bans, and server-side custody of full-account tokens.
- **Operator decision (2026-07-02): proceed as a flagged, opt-in beta — risk accepted.** A ToS-clean alternative (deep-link / prefill handoff so the user taps Send inside Sleeper's own UI) remains the recommended fallback and degradation path.

### C2 — propose trade  ✅ (captured 2026-07-02)
- **Endpoint:** `POST https://sleeper.com/graphql` — one GraphQL endpoint for every op. Body is a standard `{ operationName, variables, query }`.
- **Headers:** `content-type: application/json`, `x-sleeper-graphql-op: <operationName>`, and **`authorization: Bearer <JWT>`** (the stored token — this confirms "where the token rides"; nothing else auth-bearing). Token value never recorded (redacted at capture).
- **`propose_trade` mutation** (verbatim structure):

  ```graphql
  mutation propose_trade($k_adds:[String],$v_adds:[Int],$k_drops:[String],$v_drops:[Int]) {
    propose_trade(
      league_id: "<LEAGUE_ID>",
      draft_picks: ["<pick>", ...],
      k_adds: $k_adds, v_adds: $v_adds, k_drops: $k_drops, v_drops: $v_drops,
      waiver_budget: []
    ) { adds consenter_ids created creator drops league_id leg metadata
        roster_ids settings status status_updated transaction_id draft_picks
        type player_map waiver_budget }
  }
  ```
  `league_id` and `draft_picks` are **inlined into the query string**; adds/drops ride as **variables**.
- **Player encoding (non-obvious):** every traded player appears in **both** `k_adds` and `k_drops` (identical player_id list), paired positionally with roster_ids — `v_adds[i]` = roster that **receives** `k_adds[i]`; `v_drops[i]` = roster that **gives up** `k_drops[i]`. e.g. player `4866` with `v_adds=1, v_drops=2` ⇒ roster 2 sends 4866 to roster 1. The **proposer's own roster is not a param** — it's derived from the bearer token's user.
- **Draft-pick encoding:** each pick is a comma-string `"<f1>,<season>,<round>,<from_roster>,<to_roster>"` (e.g. `"11,2026,1,1,2"`, `"1,2027,4,2,1"`). Field 1 is likely the original-owner roster id — confirm on a multi-owner pick. **FAAB** rides in `waiver_budget: [{sender, receiver, amount}]`.
- **Success response:** the transaction object — `{ transaction_id, status: "proposed", consenter_ids, adds{pid:roster}, drops{pid:roster}, draft_picks, league_id, leg, creator, player_map{…} }`. Fresh proposal ⇒ `status: "proposed"`.
- **Adjacent ops:** **`reject_trade`** ✅ captured — `reject_trade(league_id, transaction_id, leg)` → returns the txn with updated `status` + `metadata.rejecter_id`. **accept / cancel** not captured; by the naming pattern almost certainly `accept_trade` / `cancel_trade` with the same `(league_id, transaction_id, leg)` args — confirm on a later capture. Sleeper also fires a `create_message` op to post a "X proposed a trade" DM — **FTF does not reproduce this** (propose_trade alone creates the transaction).
- **Roster_ids:** obtainable from the **public** read API — `GET /v1/league/<id>/rosters` maps `owner_id → roster_id` (user's own + counterparty's). No authed call needed.
- **Capture-method note:** the extension's network reader returns request **URLs only** (no bodies/headers) — bodies/headers were captured with an **injected, redacting `fetch`/`XHR` interceptor** installed immediately before "Propose."

### Status: all four spikes complete — build unblocked
C1 (webview token) + C2 (propose/reject mutations) in hand; C3 (365-day JWT) + C4 (flagged, risk-accepted) recorded. The build (`SleeperWriteAdapter`, `POST /api/trade/propose`, webview capture, "Send in Sleeper" button) is now mechanical per Part C.

### Build status — 2026-07-03 (slices 1–3 landed, uncommitted, flag OFF)
- **Slice 1 (backend):** `backend/sleeper_write.py` adapter (`propose_trade`/`reject_trade`, Fernet crypto, JWT introspection); `sleeper_credentials` table + helpers; `POST/GET/DELETE /api/sleeper/link` + `POST /api/trades/propose` (resolves both roster_ids server-side from user_ids). Flag `trade.send_in_sleeper` (default off). 25 tests; full suite 242 green. Needs `SLEEPER_TOKEN_KEY` + `cryptography` (added to requirements).
- **Slice 2 (mobile):** `react-native-webview` added (⚠️ **needs an EAS/dev-client rebuild** — native module). `SleeperConnectScreen` (webview → reads `localStorage['token']` → `POST /api/sleeper/link`). `src/api/sendInSleeper.ts`.
- **Slice 3 (mobile):** `SendInSleeperButton` (flag-gated) wired into **found** (Trades deck top card), **matched** + **awaiting/suggested** (Matches). `tsc` clean.
- **Open gap:** the **manual calculator** (`TradeCalculatorScreen`) is mock-only (no real league/opponent), so it has NO live Send — that surface needs the in-league calculator mode (see manual-trade-calculator-plan.md) before its button can send. Deep-link fallback opens the Sleeper league on any write failure.

### Build implications (refines "What happens after you hand this back")
- Step 3 resolves to the **webview no-password path** (C1 confirmed): store the JWT encrypted in `linked_sources.credentials_ref`, treat as valid ~1 year, re-prompt on expiry.
- Steps 1–2 (`SleeperWriteAdapter`, `POST /api/trade/propose`) remain gated on **C2**.
