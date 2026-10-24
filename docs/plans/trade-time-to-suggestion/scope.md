# Feature Scope — Time to trade suggestion (first card ≤ 200 ms, up-to-date offers)

<!--
Copied from docs/templates/feature-scope.md on 2026-10-15. Per D-056 the template's
§Maestro delta and §Simulator-gate tier are dead and are not carried here.
This scope is filled at PLAN stage: the build has not been designed (eng owns the HOW).
Rows that can only be finalized once eng picks an approach are marked
"BUILD OBLIGATION" — the build must replace them with an answer or an explicit waiver
before code starts. Silence is not a waiver.
-->

**Date:** 2026-10-15
**Entry point:** direct ask (operator, 2026-10-15): *"Time to trade suggestions. This should be within 250 ms of hitting find a trade and must be up to date trade offers."*
**Builder:** not yet assigned. Plan by trades-pm (PRD worker); build by head-eng → trades-eng / models-eng
**Operator sign-off on waivers:** needed. The waivers proposed below (web/extension out of scope;
pinned and targeted searches measured but not gated; cold-launch taps not gated; table B controls
measured but not gated) are listed as Decisions D1, D2 and D10 in
[prd.md](prd.md#decisions-needed-operator).

PRD: [prd.md](prd.md) · Baseline query spec: [baseline-request.md](baseline-request.md)

---

## 0. Launch revision (2026-10-20)

- **Target:** p95 ≤ **200 ms** (was 250 ms), a **launch MUST** with no interim bar. Operator: "This
  must be ready by launch day. It is possible. We must solve it."
- **Build:** resumes on the 200 ms path ("Yes building should resume on the 200 ms path").
- **No "Finding more" card** ("This should never happen"). The P30 genuine-end card is not one.
- **DEC-2:** narrow rows for unseen trades are approved (§2).
- **Requirements and criteria:** U1–U5 (prd §4.7, §5.5) and launch criteria AC-L1 to AC-L8
  (prd §8.1), with analytics-lead's measurement terms T1–T6 and head-product P30 and P32.
- **Hidden ms readout** for the operator's device runs: prd §9.5, with evidence in §3 below.
  head-eng decides the build.

## 1. Analytics scope

- [x] **(a) New events specced.** analytics-lead reviewed them (Ask 1b, 2026-10-15): R1–R3 are
  granted with conditions, and R4 is refused as specced with an alternative granted. Each event is
  registered in `backend/analytics_taxonomy.py` and classified in
  `analytics_queries.NON_INTENT_EVENTS` **in the same commit as its emitter**.

  | Event | Properties | Fires when | Client | Verdict (analytics-lead) |
  |---|---|---|---|---|
  | **R1** `find_trades_tapped` + `calc_find_a_trade_tapped`, widened | + `search_id` (client UUID per tap); new `source` values, one per prd §4.1 entry point. Monotonic tap time stays client-local and feeds R2's `ms_from_tap` | touch-up on any table A control (and table B controls if D10 makes them search-starting); `find_trades_tapped` moves to the tap, not dispatch | iOS | **Granted as a widening; both stay INTENT.** No `trade_search_started`. New `source` values are listed in the addendum and the prop-row comment. Exact prop rows are asserted (`==`) |
  | **R2** `trade_first_card_shown` (new) | `search_id`, `ms_from_tap`, `entry_point`, `search_type` (organic / pinned / fair_sweep), `launch_state` (cold_launch / first_tap / repeat_tap), `network_type` (wifi / cellular / offline / unknown), `serve_source` (prepared / cached / joined / fresh), `freshness_state` (fresh / updating / withdrawn_some), `job_id`, `card_index` | first frame with an actionable card meeting prd §4.2 | iOS | **Granted, NON_INTENT.** No player ids. Exactly one of R2/R2b per `search_id`, test-asserted |
  | **R2b** `trade_first_card_failed` (new, a separate event) | `search_id`, `ms_from_tap`, `reason` (empty / error / abandoned / timeout), `network_type` | a tap ends without an actionable card; `abandoned` fires on unmount or blur before a card | iOS | **Granted as a separate NON_INTENT event**, not a `result` prop. The addendum states the `timeout` threshold in ms |
  | **R3** `trades_generated` (server, widened) | + `first_publish_ms`, `serve_source`, `oldest_input_age_s`, echoed `search_id` | existing server emit points, **plus every serve path that shows a deck** | server | **Granted, binding condition:** exactly one `trades_generated` per user-visible deck, whatever the `serve_source`, or an `/an-funnel` stage-6 amendment before the build (prd AC-1b). `deck_source` keeps its meaning. The echoed `search_id` puts `docs/api-reference.md` in scope (§4) |
  | ~~R4 envelope column `network_type`~~ | — | — | — | **Refused as specced** (it contends with PR #337 R-E1, and is the G-068 risk). Replaced by the `network_type` prop on R2/R2b. No schema change, no data-dictionary row |

  → follow-through:
  - **Addendum** `docs/business/analytics/<date>-time-to-suggestion-events.md`, written before any
    emitter ships (G-031), with a seam line: R1–R3 have no history before ship.
  - **Privacy delta (P12)** to onboarding-pm: `network_type` (diagnostics) and `search_id` (linked
    identifier) need an App Store label check, "check, likely no change".
  - The new Sleeper send-block value on `sleeper_send_failed.error_code` (platforms-pm R4) goes to
    analytics-lead. ESPN and MFL block events are not requested in v1; they would need a grant.
  - **R5 page-end readiness (AC-L4), a REQUEST pending analytics-lead's grant (2026-10-20).** A
    `next_page_ready_at_end` boolean, plus `page_index` and `search_id`, when the user reaches a
    page's last card. Preferred: props on an existing event, e.g. `trade_card_viewed` on the
    page's last `card_index`, or on R2's sibling outcomes.
  - **AC-L1 measurement terms (analytics-lead T1–T6)** apply to R1/R2/R2b. Notably, every R2b counts
    as above 200 ms (T2), and the readout query includes tester devices (T5).
  - **The hidden ms readout (prd §9.5) adds no event.** It reads R2's `ms_from_tap` locally.
  - **Serve-path tag (models-lead R.b, AC-9e):** if eng carries it as an analytics prop rather than
    an impression field (§2), it needs analytics-lead's grant.
  - No player ids or names in props (`tracking-plan-v2.md:183`). Device platform stays a
    server-derived column (`tracking-plan-v2.md:218`).
- [ ] (b) Existing events cover it: **no**. `deck_card_viewed` requires 500 ms of exposure.
  `find_trades_tapped` misses non-TradesScreen entry points. `trades_generated.gen_ms` is
  full-worker time (prd §4.6).
- [ ] (c) Waived: no.

## 2. Schema & flag scope

- **New or changed tables/columns: BUILD OBLIGATION.**
  - No `user_events` column: R4 was refused, and `network_type` is a prop (analytics-lead).
  - **Serve-path tag on deck impressions** (models-lead R.b, prd AC-9e). Every impression records
    the path that served it: fresh, cached, joined, prepared or device-resident. **BUILD
    OBLIGATION:** eng decides the form.
    - A new `deck_impressions` column needs a `docs/data-dictionary.md` row and a migration entry.
    - A declared key inside `features_json` needs a data-dictionary note.

    Calibration's current-arm sampling filters on it (Decision D12). If eng instead carries it as an
    analytics prop, it needs analytics-lead's grant (§1).
  - Any persistent cache or prepared-page storage must state its footprint per user-league and its
    daily write volume, using prd §10.4's formulas, before it is built. The first page is about
    37 KB per user-league pair, pre-built with page 2 (prd §10.7).
  - **DEC-2 (operator-approved 2026-10-20): unseen candidates are stored as narrow rows, not full
    evidence, and nothing changes for the user.** Displayed cards keep full evidence. The narrow-row
    shape is a schema change: `docs/data-dictionary.md` plus a migration entry (BUILD OBLIGATION).
    analytics-lead and models-lead confirm their readouts work from it (prd AC-L8, D7).
  - Per head-product P23 (2026-10-15), cache data is the first class shed under disk pressure. It
    must be rebuildable and never the system of record, with a fresh-path fallback (prd AC-11b).
  - No rollout without an explicit byte budget, per user-league and in total. head-eng checks it
    against H1–H3 in `docs/plans/db-storage-budget/requirements.md:314-317` (draft PR #337) before
    rollout. The budget number stays open under Decision D7.
  - Rows go to `docs/data-dictionary.md`, plus a migration entry.
- **Feature flags:** none decided. Existing flags and knobs on the path are listed in prd §10.6.
  The likely candidates:
  - `trade.prepared_inventory` + `model_config prepared_trade_inventory_enabled` (dark, default 0);
  - `deck.quality_filters` (on);
  - `deck.replenishment` (on);
  - `trade.value_core` (off);
  - `trades.presentation_v2` (off).

  Any new flag must:
  - default **off**;
  - be listed in `config/features.json`, `backend/feature_flags.py` `FLAG_KEYS` and
    `docs/config-reference.md`;
  - name a graduation criterion (prd AC-3 met on the operator checklist plus analytics);
  - name a deploy-free kill switch.
- **Env vars / `model_config` keys: BUILD OBLIGATION.** Freshness bounds (prd §5.1) should be
  `model_config` knobs so they can be tuned without a deploy (the ship-the-knob rule). Name them in
  the HLD.

## 3. Evidence scope

- [ ] **Structural guard:** `mobile/tests/check-trade-first-card.js`, plus `npm run
  test:trade-first-card`. It pins:
  - every prd §4.1 table A control, plus the deep-link and inbox arrivals, emits R1 with a
    `search_id`;
  - R2 fires only on the enabled, visible card path and never on the `SkeletonTradeCard` branch,
    and R2b fires on unmount or blur before a card;
  - `freshness_state` from the payload drives the "updating" UI, which claims no interrupt slot and
    renders no Toast;
  - the gate-miss and updating strings carry no timing promise and no "Searching…" (prd AC-8b);
  - `animation: 'none'` on every search-starting route, no transition on in-place reveals, and no
    deck stagger (AC-L2);
  - no "Finding more" component or copy on the Find a trade path; the page N+2 request starts when
    page N is fronted; the P30 card never renders while a page is pending and has no Like/Pass
    (AC-L4);
  - no "Find more trades" button on the deck once U3 is on, and Retry only in the error and offline
    states (D13); the P30 card renders the P36 strings and **no tally line at 0 · 0 · 0** (P36);
    P30's "Adjust your search" runs its search in place and emits R1 (D14(a)); and no third
    action or new-trades notice on the P30 card (D14(c));
  - **the hidden ms readout** reads R2's `ms_from_tap` and no other timer, and renders only behind the
    Testing gate (`__DEV__ || testing.stage_users`), applied in the component itself because the
    route is deep-linkable (prd §9.5).
- [ ] **Unit tests (backend pytest):**
  - taxonomy registration and classification, exact prop rows (`==`), and the one-of-R2/R2b
    invariant (analytics-lead);
  - one `trades_generated` per user-visible deck on every serve path (prd AC-1b);
  - one freshness test per prd §5.1 row (serve-and-refresh, the §5.5 U2 gate-miss fallback per
    head-product P40, and block branches);
  - ownership-after-roster-change on every serve path (AC-5);
  - action-time revalidation: per platform send path, including team overhaul, with moved-asset and
    read-failure fixtures (prd AC-6a); likes on moved-asset cards record no like and no match
    (AC-6b);
  - fast-path vs fresh-path differential on frozen inputs with `PYTHONHASHSEED=0` and a frozen
    clock (AC-9b, G-065);
  - filter parity at display: a roster/value mutation between prepare and display, plus the
    unknown-lineup fallthrough (AC-9a); the impression serve-path tag (AC-9e);
  - inventory-count parity (AC-10).
- [ ] **Code-walk proof:** a file:line trace from tap → navigation → request or local read → first
  enabled card, per entry point, naming every blocking hop and every skeleton branch (prd §9.3).
- [ ] **Manual TestFlight checklist:** the 20 steps plus launch runs L1–L4 (with L2b and L2c) in [prd §9.4](prd.md#94-operator-testflight-checklist-the-only-runtime-evidence-run-on-the-builds-testflight-number),
  including frame-timed screen recordings. It is the only runtime evidence and the gate until
  telemetry reaches n ≥ 40 per cell. **app-manager writes the launch device checklist:**
  - 40 taps per cell recording the §9.5 readout;
  - the U3 three-page run and the P30 end;
  - the U5 fresh-account run;
  - the U2 roster-change run;
  - the K-F5 run (L4b; activates when #351 D1 ships; not a launch gate);
  - the §9.6 scripted two-device session, which is the AC-L1 proof.

  Step 13 (blocked sends) runs only in a test league the
  operator names. The operator approves the attempt and cancels any proposal that lands
  (platforms-pm evidence plan).
- [ ] **Waived:** no.
- `testID`s added or renamed: **BUILD OBLIGATION.** Every §4.1 control needs a stable testID for the
  guard. Most already have one (`calc.action.find-a-trade`, `trades.find-btn` until D13 removes it, `home.tile.find-trade`,
  `league.action.find`, `matches.go-to-trades`, `calc.find-a-trade`). They must pass `mobile/scripts/testid-lint.sh`.

## 4. Docs scope (MANDATORY: HLD / LLD / API)

This is a plan; nothing is updated yet. Each row states what the build must do.

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | BUILD OBLIGATION | The echoed `search_id` request field on `/api/trades/generate` (analytics-lead R3). Any other change to `/api/trades/generate` or `/api/trades/status` (response shape, freshness fields, paging) or a new prefetch route. The send routes' new refusal codes `asset_not_owned` / `counterparty_asset_not_owned` and the read-failure block (platforms-pm R3, R4). |
| `living-memory/LLD.md` | BUILD OBLIGATION | Freshness-bound conventions and the serve-time invariant set (prd §5.3) are a new cross-path convention. |
| `docs/architecture.md` | BUILD OBLIGATION | The serve path for the first card, wherever eng puts it (prepared, device or transport). |
| `living-memory/HLD.md` | BUILD OBLIGATION, if the approach adds a client-side cache or a new background worker | Otherwise n/a, with a reason. |
| `docs/cross-client-invariants.md` | Likely n/a | Unless the freshness enum or labels are rendered by more than one client. Web is out of scope in v1. |
| `docs/glossary.md` | BUILD OBLIGATION | New terms: "time to first card", "freshness bound", "serve-and-refresh". |
| ADR or `DECISIONS.md` | BUILD OBLIGATION | The approach choice and the stale-deck rule (Decision D4) are non-obvious choices. |
| `docs/business/analytics/<date>-time-to-suggestion-events.md` addendum | BUILD OBLIGATION | R1–R3 per analytics-lead's grant, plus the R2 `network_type` prop. Written before any emitter (G-031) |
| `docs/data-dictionary.md` | n/a for analytics; BUILD OBLIGATION otherwise | R4 was refused, so no `user_events` column. Still applies if a cache table is added, or if the serve-path tag becomes a `deck_impressions` column or a declared `features_json` key (§2, AC-9e) |
| `docs/integrations/mfl.md` (also `sleeper.md`, `espn.md` if a call's shape changes) | BUILD OBLIGATION | MFL adds one rosters export per send for I-2 (platforms-pm R1). Sleeper and ESPN reuse data already fetched |

## 5. Ship gate declaration

- **Precondition, background replenishment restored:** it must be restored, bounded by DEC-2 narrow
  rows, before the 200 ms build ships. The operator paused it as a DB emergency stopgap on
  2026-10-20 (relayed by head-product). U2's freshness floor and U3's prefetch depend on it.
  head-eng owns it (prd Handoffs, §12).
- **AC-L1 proof:** the scripted two-device session (prd §9.6), run after replenishment is restored.
  Organic telemetry is monitoring only.
- **CI green:** `backend-tests` + `mobile-typecheck` (with the `check-*.js` suites) +
  `maestro-testid-lint`, all passing on the pushed sha.
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry naming the guards and tests that ran,
  the code-walk, and analytics-lead's §9.6 session readout (p95 per cell under T1–T6).
- **TestFlight verification:** prd §9.4, run by the operator. Outcomes, with frame timings, are
  logged in TEST_LEDGER.
- **Pre-push:** `FTF_SKIP_SIM_GATE=1` (D-056 standing posture), noting the evidence above.
- **Express lane declared by the operator?** No. This change touches API contracts, analytics events
  and possibly schema and flags, so it sits above the express-lane bright line.

## 6. Platform scope (platforms-pm R6; template: PR #331 `docs/templates/feature-scope.md` §7)

Reference: `.claude/skills/pm-technical/references/platform-parity.md` (once PR #331 lands). The
detail is in prd §5.1 and §5.3 (I-2).

| Platform | Reads / writes used | Behavior: parity / honest `platform_unsupported` / fallback copy / n/a |
|---|---|---|
| Sleeper | **Reads:** rosters from the background floor, off the tap path, on session-init, app foreground and Trades focus. **Never on the search tap or the first-page serve** (head-product P40, 2026-10-24; AC-L3). **No scheduled or headless server-side roster reads beyond today's pattern until the operator rules on E2** (platforms-pm R7). At send, the live `_fetch_league_rosters` already runs (`server.py:19529`), so the I-2 player check needs no new call. **Writes:** propose, unchanged | **Parity.** Players are checked live at send, at roster level (co-owners pass, D-051); picks are already checked live. Refusal: `asset_not_owned` / `counterparty_asset_not_owned` with their copy; the block is reported through `sleeper_send_failed.error_code`. A failed read (Cloudflare 1010) blocks the send. Dependency: `NEXT.md` 0f, the `isdigit()` G-030 trap, lands before or with I-2 (N1) |
| ESPN | **Reads:** DB import, refreshed only by the background floor on user action off the tap path (P40), with stored credentials. At send, the live `fetch_league` with `view=mRoster` already runs (`server.py:33133`; `espn_service.py:94`), so the check needs no new call. **Writes:** propose (players only), unchanged | **Parity for players.** Picks stay hard-blocked (`espn_pick_unsupported`). Same refusal contract. A failed read blocks the send (`docs/runbook.md` L747) |
| MFL | **Reads:** **new**, one rosters export per send (`mfl_service.fetch_rosters`, `mfl_service.py:432`), including `futureDraftPicks`. Refetches are user-triggered, within 1 request per second. **Writes:** propose, unchanged | **Parity**, players and picks. Same refusal contract. A failed read (`wwwNN` hosts, `docs/runbook.md` L758) blocks the send. Dependency, not a blocker: MFL client registration (`NEXT.md`) |
| Fleaflicker (dark) | none | **n/a:** `fleaflicker.link` is false and there is no write path |

- **Team-overhaul sends** (Sleeper, MFL, ESPN players only; behind `overhaul.enabled` plus each send
  flag) get the same send-time check (platforms-pm R8).
- **Platform pending offers** are not read in v1. Any future read goes to platforms-pm's platform
  risk register first (N2).
- [ ] **WAIVED:** no.
