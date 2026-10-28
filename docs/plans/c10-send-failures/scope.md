# Feature Scope — C10: readable ESPN/MFL send failures + outcome unknown

<!--
Copied from docs/templates/feature-scope.md. The template's retired Maestro
delta and simulator-gate tier (D-056) are left out on purpose.
-->

**Date:** 2026-10-27
**Entry point:** direct ask: head-eng's pre-launch triage item C10 ("the only C item that prevents a real-money-adjacent harm"), via the platforms-eng lead
**Builder:** C10 backend worker (platforms-eng), branch `fix/espn-mfl-send-failures`
**Operator sign-off on waivers:** not needed. The waivers below (structural guard, TestFlight checklist) carry their reasons: the change is server-only and mobile is untouched.

**Copy status:** every user-facing string below is a **placeholder**, pending marketing via head-eng. A swap is a change to the constants in `backend/server.py` (`_SEND_REJECTED_COPY`, `_SEND_OUTCOME_UNKNOWN_COPY`, `_RESPOND_REJECTED_COPY`, `_RESPOND_OUTCOME_UNKNOWN_COPY`) and the matching test strings.

## 0. Problem and behavior

**Problem.**
- When an ESPN or MFL trade write failed, `POST /api/trades/propose-espn` and `POST /api/trades/propose-mfl` returned `espn_write_failed` / `mfl_write_failed` with the provider's raw HTML/JSON body in `detail`.
- `SendInEspnButton` / `SendInMflButton` print that body after "ESPN/MFL rejected the request:".
- A timeout or reset **after** the request went out was either the same ordinary failure or an uncaught 500. The client's catch-all says "Please try again", so the user retried, and a first send that had landed went out twice.
- `POST /api/trades/respond-mfl` (accept / reject / revoke) shares the MFL adapter and had the same two defects.

**Behavior after C10 (server only).**

| Outcome | Code (status) | `detail` == `message` |
|---|---|---|
| Provider refused, or nothing was sent (DNS / refused / no route, MFL 429, input) — propose | `espn_write_failed` / `mfl_write_failed` (502, **unchanged**) | "{ESPN\|MFL} didn’t accept this trade, so nothing was sent. Check the trade on {ESPN\|MFL} and try again." |
| May have reached the provider, no definitive answer — propose | **new** `espn_outcome_unknown` / `mfl_outcome_unknown` (502) | "Couldn’t confirm whether this trade reached {ESPN\|MFL}. Check {ESPN\|MFL} before sending it again." |
| Refused / not sent — respond-mfl | `mfl_write_failed` (502, unchanged) | "MFL didn’t accept this response, so nothing changed. Check the trade on MFL and try again." |
| May have landed — respond-mfl | **new** `mfl_outcome_unknown` (502) | "Couldn’t confirm whether this response reached MFL. Check the trade on MFL before trying again." |
| Auth rejected on the write (all three routes) | `espn_auth_expired` / `mfl_auth_expired` (409, unchanged) | the existing message; the raw body is no longer returned |

- Every outcome carries `kind`.
- **Logging:** the provider's raw body goes to one `WARNING` line on the `trade_finder` logger via `_provider_body_for_log`. The helper flattens whitespace, masks SWID-shaped GUIDs, `espn_s2` / `SWID` / `MFL_USER_ID` values and long opaque blobs, then caps the line at 300 characters.
- **No retries:** nothing retries automatically.
- **Unknown is not a send:** an outcome-unknown result fires no `trade_sent` / `trade_responded` and writes no `trade_proposals` row.

**Before vs. after the send** (`backend/write_outcome.py`; adapters `backend/espn_write.py`, `backend/mfl_write.py`).
- `urllib`'s `do_open` wraps only the connect and the request write in `URLError`. Errors from `getresponse()` / `read()` come out raw.
- **Not sent:** a `URLError` caused by `socket.gaierror` (DNS), `ConnectionRefusedError` or `ENETUNREACH` / `EHOSTUNREACH`, or a non-exception reason (urllib's own pre-connect refusals).
- **Outcome unknown:**
  - a raw `OSError` / `http.client.HTTPException` from `getresponse()` / `read()`: read timeout, reset, `RemoteDisconnected`, `BadStatusLine`, `IncompleteRead`;
  - any HTTP 5xx;
  - a `URLError` wrapping a timeout or reset. This is conservative: urllib can't say whether the connect or the write failed, and a redirect's follow-up can fail after the first leg reached the provider;
  - an ESPN 2xx that isn't JSON or UTF-8;
  - an MFL 200 that is empty or neither OK nor `<error>`.
- **Unchanged:** a 4xx or an MFL `<error>` stays `kind: "error"`; MFL 429 stays `kind: "network"`.

**Team overhaul** (`backend/overhaul_api.py`).
- A core result of `*_outcome_unknown` becomes an `outcome_unknown` attempt: an existing state with an allowed `sending → outcome_unknown` transition, `state_source: server`.
- The attempt is counted in `unknown_count` and keeps the package reservation like any live attempt.
- `error.message` is the plain copy.
- Rejections stay `send_failed` with the plain copy.
- No new attempt state, so the trades-eng contract is unchanged.

**Out of scope, owner mobile (server-only PR):**
- **`*_write_failed` reads twice:** both buttons prefix it with "ESPN/MFL rejected the request:", so the plain sentence reads as a repeat.
- **Unknown title:** `*_outcome_unknown` reaches each button's catch-all, which shows `detail` but is titled "Couldn’t send".
- **Overhaul plan screen:** `OverhaulPlanScreen` shows `error.message` only for `send_failed`, so an unknown attempt shows just its "Send status unknown" pill.
- **Client timeout:** the client's 15 s request timeout is shorter than the server's pre-flight read plus its 15 s write. A client-side timeout is therefore its own unknown outcome, still shown as "Something went wrong … Please try again."

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [x] **(b) Existing events cover it:**
  - **`api_call`** (obs, outbound) `error_kind` can now be **`outcome_unknown`** on `espn write.trade_proposal` and `mfl import.tradeProposal` / `import.tradeResponse`. The prop already exists and is free-form, so no taxonomy change. It answers "how often does a send end ambiguous, per provider?" without logging content.
  - **`api_request`** (obs, inbound) `error_code` can now be `espn_outcome_unknown` / `mfl_outcome_unknown` on the three routes. It is the JSON `error` field as before.
  - **`trade_sent` / `trade_responded`** are unchanged and still fire on confirmed success only. An unknown outcome fires neither.
  - **`overhaul_batch_reconciled.unknown_count`** now also counts core outcome-unknowns, not just escaped exceptions.
  - No new event and no new prop. `SendInEspnButton` / `SendInMflButton` fire no failure event, so there is no client enum to extend (unlike `sleeper_send_failed.error_code`).
- [ ] **(c) WAIVED:** n/a, (b) applies.

## 2. Schema & flag scope

- New/changed tables or columns: none.
- New/changed feature flags: none. The routes stay behind `espn.send` / `trade.send_in_mfl`.
- New env vars / `model_config` keys: none. Rollback lever: revert the commit. The new codes are additive and the old codes keep their statuses.

## 3. Evidence scope

- [ ] **Structural guard:** WAIVED, because mobile is unchanged (server-only).
- [x] **Unit tests:** `backend/tests/test_c10_send_failures.py`, 70 tests.
  - **Adapters**, through the real `propose_trade` with an injected opener:
    - 4 not-sent cases → `network`;
    - 13 after-send cases → `outcome_unknown`, per platform;
    - an unreadable 2xx/200 → `outcome_unknown`;
    - an ESPN 4xx, MFL `<error>` / 4xx → `error`;
    - MFL 429 → `network`.
  - **Propose routes:**
    - HTML and JSON rejections keep their code; the marker is absent from the response and appears in exactly one log line, truncated, SWID and cookie masked;
    - timeout / reset / 5xx / `IncompleteRead` → `*_outcome_unknown`;
    - DNS / refused → `*_write_failed`;
    - unknown fires no `trade_sent`;
    - auth bodies are not returned.
  - **respond-mfl:**
    - an HTML-400 and an `<error>`-200 rejection are never returned and are logged once, masked;
    - timeout / reset / 504 → `mfl_outcome_unknown`;
    - refused → `mfl_write_failed`;
    - the auth body is not returned.
  - **Overhaul**, through the real cores:
    - ESPN mixed batch: a tie that times out → 2 × `outcome_unknown`, still reserved; a rejection → `send_failed` with the copy, released; 2 × `proposed`; `GET /api/overhauls/{id}` shows the same;
    - MFL batch with every offer reset → 5 × `outcome_unknown`, all reserved.
- **Sabotage**, each red, then restored byte-identical:

  | Sabotage | Red |
  |---|---|
  | Raw `detail` returned again (propose ESPN + MFL, respond-mfl) | 24 |
  | Adapters' after-send branch classified `network` | 13 |
  | Every `URLError` treated as not sent | 4 |
  | Routes ignore `outcome_unknown` (`_send_write_failed`) | 13 |
  | Overhaul records the codes as `send_failed` | 2 |

- [x] **Code-walk proof:**
  - `backend/espn_write.py` `_post_transaction` and `backend/mfl_write.py` `_issue_import` / `_parse_import_response` classify each failure.
  - `backend/server.py` `_send_write_failed` maps `kind` to code and copy.
  - The cores' `except EspnWriteError` / `except MflWriteError` branches, and the same branch in `respond_trade_in_mfl`, log through `_provider_body_for_log` and return it.
  - `backend/overhaul_api.py`'s send loop routes `_OUTCOME_UNKNOWN_CODES` to `outcome_unknown` without `release_if_idle`.
- [ ] **Manual TestFlight checklist:** WAIVED. Mobile is unchanged, and the failure paths (a provider timeout or reset after send, a provider 5xx) can't be triggered on demand from a device. The route tests drive the real adapters through each path.
- `testID`s added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | Send in MFL: the `propose-mfl` error table (`mfl_auth_expired`, `mfl_write_failed`, new `mfl_outcome_unknown`) and the `respond-mfl` row. Send in ESPN: the `propose-espn` table (`espn_auth_expired`, `espn_write_failed`, new `espn_outcome_unknown`). Team overhaul: the `POST /api/overhauls/{id}/send` row |
| `docs/integrations/espn.md` / `docs/integrations/mfl.md` | updated | espn §6.8 (trade-send write: logging + before/after send); mfl §7 Error modes (the new kind, the before/after-send rule, logging, respond-mfl) |
| `living-memory/LLD.md` | n/a | No schema, route-shape or invariant convention moved. The before/after-send rule is local to the two write adapters and documented in `backend/write_outcome.py` and the integration docs |
| `docs/architecture.md` | n/a | No module wiring or data flow changed. `write_outcome.py` is a leaf helper the two adapters import |
| `living-memory/HLD.md` | n/a | No architecture shift. The League-write adapters row still describes the modules |
| `docs/cross-client-invariants.md` | n/a | No client branches on the new codes, and ESPN/MFL send failures have no client analytics enum (unlike `sleeper_send_failed.error_code`). The overhaul attempt-state list is unchanged |
| `docs/glossary.md` | n/a | "Outcome unknown" is already the overhaul attempt state; no new domain term |
| ADR or `DECISIONS.md` entry | n/a | The conservative classification (timeouts are unknown) is head-eng's stated rule for C10, and its reasoning is in `backend/write_outcome.py`. No design choice was overturned |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` + `maestro-testid-lint` on the pushed sha. The full backend suite runs in CI only; locally the targeted files were run (TEST_LEDGER 2026-10-27).
- **Evidence recorded:** `living-memory/TEST_LEDGER.md`, 2026-10-27 C10 entry.
- **TestFlight verification:** none written (§3 waiver).
- Express lane declared by the operator? No. Full gates. `FTF_SKIP_SIM_GATE=1` is the D-056 standing posture.
