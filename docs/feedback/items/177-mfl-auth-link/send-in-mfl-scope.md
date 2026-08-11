# Feature Scope — "Send in MFL" (one-click trade proposal into MyFantasyLeague)

**Date:** 2026-08-11
**Entry point:** direct ask (operator-dispatched build agent), building on feedback #177's
`send-trade-feasibility.md` and `docs/plans/send-in-mfl-research-2026-08-11.md`
**Builder:** worktree agent `feat/send-in-mfl` (isolated; no merge/push — operator reviews)
**Operator sign-off on waivers:** **PENDING — this scope block carries waivers (§1c-partial, §3 sim run, live-API confirmations). Surface to operator before ship.**

---

## 1. Analytics scope

- [x] **(b) Existing events cover it** — no new event names are introduced, mirroring the
  Sleeper propose route (which also fires no dedicated client/server event):
  - `api_call` (flag `obs.api_events`, server-fired, `user_id="system:api"`) — the new
    adapter `backend/mfl_write.py` instruments its live HTTP call through
    `api_observability.observe_call("mfl", "import.tradeProposal", ...)` with the same
    safe props the MFL export calls already carry (`league_id`, `host`, status, latency,
    error kind). The `MFL_USER_ID` cookie is **never** an event property (mfl.md §6).
  - `deck_outcomes` `propose` rows (flag `deck.signal_v2`) — the MFL route calls the same
    `_save_deck_outcome_safe(impression_id, "propose")` hook as the Sleeper route, so
    deck-sourced sends land in the existing outcome spine.
  - Question answered: "are MFL sends happening, succeeding, failing, and why" — from
    `api_call` status/error-kind on `import.tradeProposal` plus route logs.
- [ ] (a) New events: none. (c) n/a.
  - **Partial waiver:** no dedicated `trade_sent` funnel event exists for Sleeper sends
    either; parity is deliberate. If the operator wants a send-leg WAT event, spec it for
    BOTH platforms in one taxonomy change (see `analytics_queries.py:498` note).

## 2. Schema & flag scope

- New/changed tables or columns: **none** (reuses `mfl_credentials`,
  `leagues.platform_*`, `sleeper_credentials`' encryption key). → data-dictionary n/a.
- New/changed feature flags: **`trade.send_in_mfl`** — added to
  `backend/feature_flags.py` `FLAG_KEYS` + `config/features.json` (**default OFF**) +
  `docs/config-reference.md`.
  - Graduation criterion: operator completes the live-verification checklist below
    against a real test league (import response shape, `wwwNN` host requirement,
    pick-asset encodings), MFL client registration is done (multi-platform plan §9 Q1),
    and the flag flips on in prod only after one observed end-to-end live send.
  - Rollback lever (ship-the-knob): the flag itself — routes 404 and the mobile button
    unmounts when off; no data migration to unwind.
- New env vars / `model_config` keys: **none** (reuses `SLEEPER_TOKEN_KEY`,
  `MFL_USER_AGENT`).

## 3. Test scope (mobile test platform)

- [x] **New flow:** `mobile/.maestro/flows/trade-send/mfl-send-gating.yaml` — authored
  (id-selectors only, no sleeps/coordinates/text-taps). Covers: MFL league shows
  "Send in MFL" (flag on) and does NOT show "Send in Sleeper"; Sleeper league still
  shows "Send in Sleeper".
  - **WAIVER (explicit, operator gate):** this flow **cannot run yet** — the hermetic
    seed harness (`backend/tests/fixtures/seed_ui_test_db.py`) supports only
    `sleeper`/`espn` platforms; an `mfl` seed profile does not exist, and this build
    agent has no MFL test-league creds for a live run. The flow is authored against the
    planned `qa_mfl` profile and is documented as blocked in its header. Operator gate:
    author the `mfl` seed profile (or run against a live MFL-linked league) + run on-sim
    before ship.
- `testID`s added: `trades.send-sleeper-btn` (registered in lld.md Appendix A, now
  actually wired), `trades.send-mfl-btn` (new). Both pass `mobile/scripts/testid-lint.sh`.
- **Capture delta:** none pre-ship — the button is flag-OFF dark; capture
  `trades`/`matches` on an MFL profile when the flag graduates.
- Smoke-suite impact: none expected — 05-trades-render/06-trades-deck/08-matches run on
  Sleeper-platform seeds where the rendered button is unchanged (`Send in Sleeper`, now
  with a testID). **Sim verification of the smoke subset is part of the operator gate
  below (not runnable in this environment).**
- Backend: pytest added — `backend/tests/test_mfl_write.py` (adapter: URL/payload
  construction incl. both pick encodings, response parsing XML+JSON, auth mapping,
  asset-id validation) and `backend/tests/test_mfl_propose_route.py` (route: happy path,
  reverse-crosswalk hard-block, expired-cookie 409 + credential drop, verification gate,
  flag-off 404, MFL branch of `/api/trades/validate`). Zero live network — injected
  openers/mocks only.
- Mobile structural test: `mobile/tests/check-send-button-platform.js` (npm
  `test:send-button-platform`) — pins the platform branch: ESPN/Fleaflicker render
  neither send button, MFL renders only the MFL button, Sleeper only the Sleeper button.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated** | New `POST /api/trades/propose-mfl` row + "Send in MFL" section + `/api/trades/validate` contract extended (MFL branch + gate now either send flag) |
| `living-memory/LLD.md` | **WAIVED — worktree boundary** | Build agent is barred from `living-memory/` (parent session reconciles centrally). No convention shift beyond what `docs/integrations/mfl.md` now records; parent session to add the route/flag line if it deems it a convention change |
| `docs/architecture.md` | n/a | No module re-wiring: `mfl_write.py` is a sibling of `sleeper_write.py` in the already-documented integrations layer; data flow mirrors the existing Sleeper send path |
| `living-memory/HLD.md` | **WAIVED — worktree boundary** (and no genuine architecture shift — pattern-copy of an existing flow) | |
| `docs/cross-client-invariants.md` | n/a | No shared constants/enums/colors changed; error codes are backend-owned strings consumed by one client |
| `docs/glossary.md` | n/a | No new domain term (franchise id, futureDraftPicks already defined via mfl.md) |
| ADR / `DECISIONS.md` | n/a / **WAIVED — worktree boundary** for DECISIONS.md | Design choice (sibling route over platform-switch on `/api/trades/propose`) is recorded in the api-reference section + this scope block, not ADR-worthy: it follows the platform-adapter pattern ADR-less siblings (ESPN/Fleaflicker) already use |
| `docs/integrations/mfl.md` | **updated** | New §7 "Write surface (Send in MFL)" — import endpoint, auth, asset-id encodings, error modes, unverified-response TODOs |
| `docs/config-reference.md` | **updated** | `trade.send_in_mfl` flag row |

## 5. Ship gate declaration

- **Simulator-gate tier** (matrix in `docs/runbook.md` § Pre-ship simulator gate):
  Tier 2 (feature flow + affected smoke subset) is what this change class requires.
  - **WAIVER (explicit, operator gate):** this build agent cannot run the simulator
    (isolated worktree, no sim/harness execution, no MFL seed profile). **No sim run was
    performed.** TEST_LEDGER + `qa/sim-runs/last-sim-run.json` must be written by the
    operator/parent session when the gate runs. Backend pytest + mobile structural test
    + testid-lint are the verification actually executed here.
- Evidence: pytest output recorded in the final report; sim evidence pending operator.
- Operator deviation: none declared; the waivers above are capability limits, not
  operator-declared express.

---

## Live-verification checklist (operator MUST run before ship — no live calls were made in this build)

Against a real MFL **test league** (create one, or use the operator's own), with a real
`MFL_USER_ID` cookie from `POST /api/mfl/auth-link`:

1. **Import host requirement** — fire `import?TYPE=tradeProposal` once against
   `https://api.myfantasyleague.com/{year}/import?...` and once against the league's
   assigned `https://wwwNN.myfantasyleague.com/{year}/import?...`. Confirm whether the
   `api.` host rejects/empties (exports do — assumed same for imports; the adapter uses
   the `wwwNN` host).
2. **Response shape** — capture the raw success body: is it XML `<status>OK</status>`?
   Does appending `JSON=1` yield `{"status":"OK"}`? Capture an error body too (e.g.
   bogus `OFFEREDTO`) — `<error>...</error>`? HTTP status on error? Drop both captures
   into `docs/references/mfl/import-tradeProposal/` and align
   `mfl_write._parse_import_response` if it disagrees (it currently accepts both,
   TODO-marked).
3. **Pick-asset encodings** — in a league with tradable picks, pull
   `export?TYPE=assets&L=...` (owner-restricted) and `futureDraftPicks`; confirm:
   future picks are `FP_{origFranchiseId}_{year}_{round}` with the franchise **4-digit
   zero-padded** (e.g. `FP_0005_2027_1`) and round **not** padded; current-year picks
   are `DP_{round}_{slot}` **zero-based** and two-digit padded (`DP_02_05`). Then send a
   pick-inclusive proposal and confirm MFL renders the intended picks.
4. **Cookie on imports** — confirm the stored `MFL_USER_ID` cookie authenticates the
   import (APIKEY documented as exports-only) and what a dead cookie returns
   (401/403 vs `<error>` body) so `mfl_auth_expired` mapping is right.
5. **Trade-disabled / commissioner-locked league** — disable owner trades in the test
   league settings and send; capture the error so it can be surfaced cleanly (currently
   falls into generic `mfl_write_failed`).
6. **EXPIRES** — confirm the unix-seconds default lands as "expires in ~7 days" in MFL's
   UI.
7. **End-to-end from the app** — flag ON in a staging env, MFL league linked via #177,
   propose from the Trades deck; confirm the pending offer appears for the counterparty
   franchise in MFL, and revoke it.
8. **Client registration** (pre-GA, not per-send): complete MFL client registration
   (form + phone validation) and set the registered `MFL_USER_AGENT` — unregistered
   write traffic is the most throttle-exposed (429).
