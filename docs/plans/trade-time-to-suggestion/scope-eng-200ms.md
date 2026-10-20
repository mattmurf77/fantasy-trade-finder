# Feature Scope — Trades eng: the 200 ms path (S0, E2, P1, P2, end of deck, UX, C, M, narrow evidence)

**Date:** 2026-10-20 (v1.2: head-eng's amendment 2 rulings, including ruling 9, folded in; supersedes v1.1, v1 and v0 of the same day)
**Entry point:** direct operator ask, 2026-10-20, relayed by the coordinator.
- "Yes building should resume on the 200 ms path." This covers the whole §3a critical path, including UX, C and
  M (coordinator, 2026-10-20).
- On DEC-2: "yes, with tiny rows for unseen trades."
- On a "finding more trades" card: "This should never happen."
- Briefs (head-eng): `docs/plans/org-bringup/briefs/build-200ms-trades-eng.md`,
  `build-200ms-trades-eng-amend-1.md` and `build-200ms-amend-2-packed-evidence.md`.
**Builder:** trades-eng (lead), with `eng-backend` and `eng-mobile` workers in their own worktrees.
**Operator sign-off on waivers:** pending. §9 is surfaced to head-eng, who takes it to the operator.
**Status:** v1.2. Rows marked **OPEN** block the piece named beside them.

**Supersedes and cites:**
- **Product's acceptance** (binding): `docs/plans/org-bringup/launch-readiness-product.md` §"200 ms by launch":
  U1–U5 and AC-L1 to AC-L8. trades-pm folds them into PR #339 and owns the final wording.
- **PR #339** (`prd.md`, `scope.md`; trades-pm's, not edited here) set 250 ms. **200 ms supersedes it.** Its
  §4.2 clock, §5 freshness bounds and invariants (I-1 to I-5), AC-9 and R1–R3 stand.
- **Eng input:** `eng-input.md` on `plan/trade-time-eng-input` @ `36af2e83`.
- **Plan of record:** `docs/plans/org-bringup/launch-readiness-eng.md` §3a.
- **Evidence policy (the build spec):** `leads/models-lead-launch.md` §DEC-2, the Confirmation block from line 217.
  - The **packed** form is the target: a per-run part once per served job, plus per-card arrays at about 92 B per
    unseen card.
  - The final C1–C9 are binding.
  - Separate narrow rows are the fallback, only if C7 (i)–(ii) slip.
  - The ADR-025 draft is `docs/plans/org-bringup/adr-025-draft.md`. trades-eng lands it in `docs/adr/` with the
    first packed-write PR.
- **Event grants:** `reports/analytics-lead.md` Ask 1b (R1–R3 granted with conditions, R4 refused in favor of a
  prop) and the AC-L1 conditions T1–T6.

---

## 0. Acceptance and the pieces that meet it

| AC (Product) | What it requires | Pieces |
|---|---|---|
| **AC-L1** | p95 ≤ 200 ms, from the tap on a search-starting control to the first frame where a real card is ≥ 50% visible with Like and Pass enabled. Cells: Wi-Fi/cellular × first/repeat tap; n ≥ 40 per cell, ≥ 2 devices | S0, E2, P1, UX, C; proof M |
| **AC-L2** | No animated push or transition on the Find a trade path | UX |
| **AC-L3** | No live Sleeper or platform call on the tap path | S0 (code-walk, plus a server trace for the first-page request) |
| **AC-L4** | Zero page ends reached without the next page already in the deck; no "Finding more" card exists in the build | P2, END |
| **AC-L5** | Zero cards shown with an asset either side no longer owns (I-2); withdraw in place | S0 (I-1 filter), C (revalidation), U2 |
| **AC-L6** | First-page cards pass `deck.quality_filters`; Calibration integrity per D12 | P1 (page = the full deck's top N, built through `_run_trade_job`), narrow evidence (C2, C4) |
| **AC-L7** | A new account's first Find a trade meets AC-L1 | U5 pre-build triggers |
| **AC-L8** | The first-page artifact and evidence writes fit the P23 byte budget and `db-capacity.md` | P1, narrow evidence (§7) |

**Not in these pieces, but gating AC-L1:** E1 (threads and instance class; head-eng and release-lead) and
platforms-eng's S0 background fetch.

## 0b. Pieces, branches, order

- **Base:** `origin/main` `678834ab`. Each branch is cut from a freshly fetched `origin/main` and rebased before
  every merge request.
- **Server pieces** merge one at a time behind `trade.first_page_store` (OFF).
- **Mobile pieces** stack on one integration branch and merge together, because they ship in **one binary**
  (with the minimum-version gate, launch item 19).

| # | Piece | Branch | Depends on |
|---|---|---|---|
| 0 | This scope block | `plan/trades-200ms-eng-scope` | — |
| 1 | **S0 serve:** `roster_snapshot` (`rfp1`), `vsn1`, the job freshness and join checks, the I-1 serve filter ("Updating" and no cards on a check error), the `on_roster_change` hook | `feat/trades-200ms-s0-serve` | Contract §6.1 agreed |
| 2 | **E2:** the opt-in first page on `/generate`; `/status` deltas by cursor; `search_id` echoed (R3) | `feat/trades-200ms-e2-small-responses` | — (parallel with 1) |
| 3 | **P1:** the page store; pages 1–3 (k = `trade_pages_stored`) pre-built together; only from a `complete` job, never `safety_ceiling_hit` or errored (§6.8); triggers (app open and foreground, roster diff, value refresh, knob or `ENGINE_VERSION` change, **league connect, session start** (U5)); serve inline after I-1; flag | `feat/trades-200ms-p1-page-store` | 1, 2; models-eng's count-bounded conversion for AC-9 |
| 4 | **Packed evidence** (C1–C9): C2–C6 now (full-row and no-row rules, including replenishment under C2); the packed writer calls models-eng's `eval/` codec; C7 (v) deletion and export for the pack table; receipts on delivered cards | `feat/trades-200ms-packed-evidence` | C2–C6: none. The packed write: models-eng's C7 (i)–(iv) green **and** models-lead accepting the pack format (the schema isn't frozen before that) |
| 5 | **P2 server:** cursor pages; the end-of-pool signal (§6.5); R3 `first_publish_ms` / `serve_source` | `feat/trades-200ms-p2-server` | 3 |
| 6 | **Mobile integration:** E2/P2 consumer and prefetch (≥ 1 full page ahead), the end-of-deck card, withdraw in place plus the non-blocking "Updating" label (U2), **UX** in-place reveal, **C** device-held first page, **M** events R1/R2/R2b and the Testing readout | `feat/trades-200ms-mobile` (one PR) | 2, 5; ux-lead's spec for UX; analytics addendum for M |

## 1. Analytics scope

- [x] **(a) New and widened events**, under analytics-lead's Ask 1b grant (2026-10-15).
  - Each is registered in `backend/analytics_taxonomy.py` and classified in `analytics_queries.NON_INTENT_EVENTS`
    **in the same commit as its emitter**.
  - A per-feature test asserts the exact prop rows (`==`).
  - No player ids, names or league-identifying values in props.

| Event | Kind | Props | Fires when | Client |
|---|---|---|---|---|
| **R1** `find_trades_tapped` (widened) | INTENT | existing `source`, `mode` + **`search_id`** (client UUID); new `source` values listed in the addendum | **At the tap**, on every search-starting control (#339 table A), not at dispatch | mobile |
| **R1** `calc_find_a_trade_tapped` (widened) | INTENT | existing + **`search_id`** | At the tap (already, `canvasSearch.ts:52-61`) | mobile |
| **R2** `trade_first_card_shown` (new) | NON_INTENT | `search_id`, `ms_from_tap` (monotonic), `entry_point`, `search_type`, `launch_state` (`cold_launch` \| `first_tap` \| `repeat_tap`), **`network_type` prop** (`wifi` \| `cellular` \| `offline` \| `unknown`; R4's replacement), `serve_source` (`device` \| `page` \| `cached` \| `joined` \| `fresh`), `freshness_state`, `job_id`, `card_index` | At AC-L1's frame exactly (T1): a real card ≥ 50% visible with Like and Pass enabled | mobile |
| **R2b** `trade_first_card_failed` (new) | NON_INTENT | `search_id`, `ms_from_tap`, `reason` (`empty` \| `error` \| `abandoned` \| `timeout`), plus R2's context props | Exactly one of R2/R2b per `search_id`. `abandoned` fires on unmount, blur or leaving `active` before a card (T4). `timeout` = **10,000 ms** (proposed; stated in the addendum) | mobile |
| **R3** `trades_generated` (widened) | as today | existing + `first_publish_ms`, `serve_source`, `oldest_input_age_s`, echoed `search_id` | **Binding condition: exactly one per user-visible deck, whatever `serve_source`.** Page serves emit it at serve. **A never-served pre-build emits none** (a job log line only, mirroring C2). Both of today's emitters are covered: the owner/live path (`server.py:9226-9238`, skipped for superseded jobs at `:9232` and for `gen_ms is None` at `:9205-9206`) and the value-core path (`:7617`). `deck_source` (F10, replenish, `:9228-9231`) keeps its meaning; `serve_source` is a separate dimension | server |

- **Follow-through:**
  - the addendum `docs/business/analytics/2026-10-2x-time-to-suggestion-events.md` (trades-eng writes it;
    analytics-lead reviews), **before** the emitter ships (G-031), with a seam line: no R1–R3 history before ship;
  - `search_id` on `/generate` goes in `docs/api-reference.md`;
  - the privacy delta (`network_type`, `search_id`) goes to onboarding-pm under P12 ("check, likely no change").
- **The AC-L1 readout conditions (T1–T6) are build requirements:**
  - T1: the R2 frame;
  - T2: R2b counts;
  - T3: `cold_launch` is its own row;
  - T4: backgrounding ends the search as `abandoned`;
  - T5 and T6 are analytics-lead's query rules.
- **A2, receipts: a definition change, probably with no code change.** head-eng accepted it 2026-10-20 (amendment 2
  §6). **OPEN:** analytics-lead's agreement, through head-product.
  - Receipts values a row from `assets_json`. Its grading queue already requires `assets_json IS NOT NULL` and a
    non-ghost row (`database.py:14984-14990`, with the docstring at `:14960-14965`). `features_json` is read only
    for the `basis` slice (`receipts_service.py:459`), and is forbidden for valuation (`:48-49`).
  - Packed and narrow rows carry no `assets_json`, so they drop out of the queue on their own. **Receipts then
    grades delivered (full-row) cards only**: the models-lead §DEC-2 §4 knock-on.
  - Receipts is trades-eng's. A test pins it, including `assets_json IS NULL` for every packed and narrow card. If
    the narrow-row fallback ever keeps `assets_json`, A2 becomes a code change.

## 2. Schema and flag scope

| Item | Piece | Shape (proposed) | Status |
|---|---|---|---|
| **Page store**, e.g. `trade_page_store` | P1 | Unique `(user_id, league_id, scoring_format, request_scope)`; one row per key, upserted. Columns: `roster_fp`, `values_snapshot_id`, `engine_version`, `config_signature`, `built_at`, `expires_at`, `deck_job_id`, `pages_json` (public projection, pages 1..k), `evidence_blob` (compressed build-time snapshot: full rows for the first 30, the packed block, the candidate set; C6), `pool_exhausted_at`, `state`, `user_id` (deletion and export) | **Granted** (amendment 2 §1–§3). Key ruled as corrected: the fingerprints are stored and compared at serve, not keyed. The **frozen snapshot is compressed**, and each card's snapshot is **dropped once its full row is written at delivery** (C3/C6) |
| Per-run pack table, e.g. `deck_impression_packs` | Packed | models-lead Confirmation §1: per-run part (with the **same** `values_snapshot_id` as `vsn1`), per-card arrays, `pack_version`, `checksum`, `user_id` | **Granted**, but **not frozen until models-lead accepts models-eng's format** (amendment 2 §2) |
| `features_compact` on `deck_impressions` | Narrow fallback | The §DEC-2 §2 key list, frozen at build | Only if C7 (i)–(ii) slip past launch (models-lead line 313) |
| C8 archive marker | Packed | From models-eng's C8 spec | **OPEN** (models-eng) |
| Roster refresh state (`league_roster_state`) | S0 | contract §4 | **Granted to platforms-eng** (amendment 2 §5). `roster_snapshot` reads it once it exists |
| Account deletion and export registration for the new tables (D-183; C7 (v)) | P1, narrow | `_ADDITIONAL_PRIVATE_TABLES` (`accounts.py:652`); export is derived from it by `user_id` (`:988-992`). **So the page store and the pack table each carry their own `user_id` column.** | **Not in my grant:** head-eng or onboarding-eng |

**Feature flag: `trade.first_page_store`** (named by release-lead, 2026-10-20). Default **false**.
- **In the P1 PR, in the same commit as the code that reads it:**
  - `config/features.json` `"trade.first_page_store": false`;
  - `backend/feature_flags.py` `FLAG_KEYS`, next to `trade.prepared_inventory`, with a one-line comment (granted
    for this one key, amendment 2 §8);
  - a `docs/config-reference.md` row: default false, what it gates, rollback = set false and reload.
- **Not** on any launched-defaults list (D-166).
- **The mobile client doesn't read the flag:** it reads the server's response shape (paged vs legacy). If a client
  gate turns out to be needed, mirror it per G-007.
- **The flag gates the server's page-store serve and the pre-build triggers.** Off means `/generate` and
  `/status` are byte-identical to today, even when a client sends the paging params. A test pins this.
- **Graduation:**
  - device p95 ≤ 200 ms (M, analytics-lead's T6);
  - C7 green;
  - the **measured** byte numbers recorded in §7 and within the P23 budget (AC-L8). **The flag stays OFF until
    they are in.**
  - models-lead 13b.
- **Read-back plan for the flip** (G-016): after the operator's flip in release-lead's session, read back the
  live features endpoint plus one page-serve trace (a `serve_source=page` R3 row, or the job log line). That
  confirms the flag isn't inert.

**New `model_config` keys** (`docs/config-reference.md`):

| Key | Default | Purpose |
|---|---|---|
| `trade_page_size` | 30 | Cards per page. C4 holds regardless |
| `trade_pages_stored` | 3 | Pages pre-built and stored per scope (head-eng accepted 1–3, tunable). Page 2 is always alongside page 1 (AC-L4); W3 swipe-rate data sets the final number (§6.4) |
| `trade_page_store_evict_days` | 30 | Evict pages for leagues with no activity in N days (D-178's sweep scope) |
| `trade_prefetch_remaining` | = page size | The client requests the next page when this many ready cards remain, so **at least one full page ahead** (U3). trades-pm sets the final threshold; it's served to the client |
| `trade_prebuild_debounce_s` | 20 | Coalesces input-change triggers |

**Mobile-only state (no server schema):**
- **C device page:** the last validated first page per league, in device storage with its `built_at`,
  `roster_fp` and `vsn`.
- **M readout:** the last `ms_from_tap`, in memory and shown in Testing settings.

**Navigation (granted):** the Find a trade route only, in `mobile/src/navigation/`.

**OPEN TS:** the Testing-settings readout row lives in onboarding-eng's settings shell (`SettingsTesting`). It
needs a grant, or onboarding-eng adds the row reading trades-eng's value.

## 3. Evidence scope (D-056)

- [ ] **Structural guards** (`mobile/tests/`, each with its `npm run test:<name>`):

  | Guard | Pins |
  |---|---|
  | `check-trade-inplace-reveal.js` | No animated push or transition on the Find a trade path (AC-L2): the route option, or no push at all, per ux-lead's spec. No skeleton or spinner on the path where a page or device page exists |
  | `check-no-finding-more.js` | No "Finding more" / keep-going card or copy exists in the build (AC-L4). The end-of-deck card renders only on `pool_exhausted` |
  | `check-trade-pages.js` | `api/trades.ts` sends the opt-in params. Deltas append behind the current card with no reorder and no jump. The prefetch trigger reads the server's `prefetch_remaining` |
  | `check-trade-first-card-events.js` | R1 at the tap on every #339 table A control, with `search_id`. R2 only on the enabled-and-visible path, never in a skeleton branch (T1). Exactly one R2/R2b per `search_id`. `abandoned` on unmount, blur or background (T4) |
  | `check-withdraw-in-place.js` | An invalidated card keeps its slot with a one-line reason. "Updating" never disables Like or Pass (U2) |
  | `check-device-first-page.js` | C: the page is stored per league, shown with no network wait, revalidated in the background, and discarded on the client's own ranking mutation |
- [ ] **Backend pytest** (the brief's must-haves in **bold**):

  | Test file | Pins |
  |---|---|
  | `test_roster_snapshot.py` | The `rfp1` canonical form and exclusions; co-owners; `vsn1` stable across a simulated restart |
  | `test_trade_freshness_roster.py` | Job freshness and join miss on an fp change; no miss on a display-name change |
  | **`test_i1_serve_filter.py`** | A moved player or pick is never served on any path; **the check-error path gives "updating" with no cards** |
  | **`test_trade_page_store.py`** | **Concurrency** (two builders on one key; serve during rebuild; supersede; restart survival); the §6.2 rules; U5 triggers at league connect and session start |
  | **`test_trade_responses_small.py`** | **E2 sizes:** first-page body ≤ 64 KB for 30 cards; `/status` returns only the cards after the cursor; legacy requests and flag-off byte-identical |
  | `test_trade_page_flag_off.py` | **Flag off = today, byte-identical**, for every route and trigger (release-lead's go/no-go evidence) |
  | **`test_narrow_evidence.py`** | **C2:** no rows for unserved pre-builds. **C4:** the first 30 always full. C3, C5, C6, C8 |
  | `test_trades_generated_once.py` | R3: exactly one per user-visible deck across `serve_source` values and both emitters (`:7617`, `:9226-9238`); none for never-served pre-builds |
  | `test_pool_exhausted.py` | The end-of-pool signal fires only when every candidate has been delivered, never while a page is pending |
  | `test_receipts_delivered_only.py` | A2 |
  | Taxonomy registration and the NON_INTENT classification test | R1–R3 |
  | AC-9 identity test (models-eng) | Page 1 = the full deck's top N; later pages never reorder delivered cards |
- [ ] **Code-walk proof** (file:line):
  - tap → in-place reveal → (device page | one request) → page-store read → fingerprint compare → I-1 → first card
    at the R2 frame;
  - no platform call on that path (AC-L3);
  - prefetch timing against the buffer model.
- [ ] **Manual TestFlight checklist:**
  - app-manager writes the device checklist (Product's "The proof").
  - trades-eng supplies the inputs: 40 taps per cell, read from the Testing readout; the U3 three-page run; the
    U5 fresh-account run; the U2 roster-change run; Airplane Mode for the offline state.
- **testIDs:** the "Updating" label, the withdrawn-card reason, the end-of-deck card and its two actions, the
  Testing readout row. Names follow the testid-lint registry.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **Yes** | `/api/trades/generate` (opt-in first page, `search_id`, page metadata, `prefetch_remaining`, `pool_exhausted`); `/api/trades/status` (cursor delta). head-eng reviews |
| `docs/data-dictionary.md` | **Yes** | Page store; `features_compact`; pack table; archive marker |
| `docs/config-reference.md` | **Yes** | `trade.first_page_store`; the four `model_config` keys |
| Analytics addendum (`docs/business/analytics/…-time-to-suggestion-events.md`) | **Yes** | R1–R3, the timeout threshold, new `source` values, the seam line |
| `living-memory/LLD.md` | **Yes** | The `rfp1`/`vsn1` invariants; the tap path reads stored rows only; the page-store convention; one `trades_generated` per user-visible deck |
| `docs/architecture.md` | **Yes** (head-eng reviews) | The page-store tier, pre-build triggers, device page |
| `living-memory/HLD.md` | **Yes** (head-eng reviews) | A new serving tier |
| `docs/cross-client-invariants.md` | n/a | Page size and the prefetch threshold are served per response. Web is out of scope for v1 (#339 §7) |
| `docs/glossary.md` | **Yes** | Roster fingerprint, values snapshot id, first page, delivered card, packed row, device page, end of deck |
| ADR | **Yes** (head-eng writes) | ADR-025, narrow evidence (C9); the page-store ADR (§3a) |

## 5. Ship gate declaration

- **CI green** on every PR: `backend-tests`, `mobile-typecheck` with the `check-*.js` suites,
  `maestro-testid-lint`.
- **Evidence** in `living-memory/TEST_LEDGER.md` at merge (release-lead's scribe).
- **The device checklist:** run by the operator on the launch binary, logged.
- **Express lane:** no.
- **Merge order:** scope → S0 → E2 → P1 → narrow → P2 server, each behind the flag (off) where it changes
  behavior. Then the mobile integration PR, with the launch binary.

## 6. Contracts

### 6.1 Roster fingerprint and values snapshot id (with platforms-eng)

**Status:** v0 **accepted** by head-eng, 2026-10-20 (amendment 2, rulings on the first reply §2).
- `backend/roster_snapshot.py` is trades-eng's; any change needs both leads' review.
- platforms-eng reviews it and names the draft-state columns. models-eng confirms `vsn1`'s inputs (does it
  include pick `pool_value`?).
- **One `values_snapshot_id`:** `vsn1` is also the id in the packed per-run part.
- Copied verbatim into platforms-eng's S0 scope block.
- `rfp1` = sha256[:32] over the canonical stored `league_members` rosters, `draft_picks` ownership and the
  draft-state columns. Names, timestamps, SQL ids and values are excluded. It is recomputed at serve from stored
  rows, with no network.
- One pure `roster_snapshot(conn, league_id)` returns `fp`, `asset_owner`, `refreshed_at` and `status`. The I-1
  filter and the freshness compare share that snapshot.
- platforms-eng commits the rows, then computes the fp, then calls `on_roster_change(league, old, new)`.
  trades-eng invalidates jobs and enqueues debounced pre-builds.
- `vsn1` = sha256[:32] over the format's seed map, memoized on `(fmt, pool_generation())`. It is read-only on the
  pool, because `pool_generation` is process-local.

### 6.2 Page-store serve rules

| Compared at serve | Action |
|---|---|
| Everything equal | Serve page 1 inline |
| `roster_fp` differs | The I-1-filtered cards, "Updating", and a rebuild |
| `values_snapshot_id` differs | Serve-and-refresh |
| `engine_version` or `config_signature` differs | Block (#339 §5.2 exception 2) |
| The check errors | "Updating", no cards |

### 6.3 Identity and order (models-eng)

- Page 1 = the full deck's top N (AC-9).
- Later pages extend the order and never reorder delivered cards.
- Built through `_run_trade_job`, so `deck.quality_filters` applies (AC-L6).

### 6.4 The buffer (AC-L4)

- **Rule:** the next page must be on the device before the user can reach the end of the current one.
- `ready_cards_after_prefetch ≥ prefetch_remaining + page_size`.
- **Build-ahead requirement:** time to deliver the next page ≤ `prefetch_remaining` × the p99 seconds per swipe.
  - Pages 1–3 are pre-built and stored, so pages 2 and 3 are each one round trip away.
  - Page 4+ needs the server to finish the deck within (pages 1–3) × the p99 swipe time.
- **OPEN SWIPE:** the p99 swipe rate (analytics-lead; W3 is granted).
  - **Conservative default until it arrives:** 1 card per 1.5 s at p99. Three stored pages then give ≥ 135 s
    before page 4 is needed, against a production engine of 10–25 s and worker of 40–75 s.
  - `trade_pages_stored` is tunable within the §7 budget.

### 6.5 End of deck (Product's P30)

- The server sets `pool_exhausted: true` only when every generated candidate of the deck has been delivered. It is
  never set while a page is pending or the deck is still building.
- **The client** renders one final card in the deck slot:
  - copy: "You've seen every trade we have for now. New ideas show up as rosters and values change.";
  - actions: "Adjust what I'm looking for" (the targeting builder) and "Back to Home";
  - Like and Pass hidden;
  - visuals: ux-lead's spec and design-lead's styling.

### 6.6 Old binaries

- Opt-in by request params (`page=1`, `cursor`, `search_id`). Without them, responses are byte-identical to
  today.
- The new client ships with the minimum-version gate (launch item 19), so old binaries keep the legacy path until
  head-eng retires it.

### 6.7 U5 and the "Building your first trades" card

- Pre-builds start at league connect and at session start.
- A brand-new user's tap with no page yet shows one honest "Building your first trades" card. It counts against
  the p95 as R2b only if no card arrives (`reason` per R2b). The design target is that it never shows.
- The code-walk proves the pre-build starts before onboarding can reach the control.

### 6.8 Ceiling, timeout and partial decks (head-eng's spec items, amendment 2)

- **The page store refuses a deck that hit the value core's safety ceiling** (`diag.safety_ceiling_hit`,
  models-eng's conversion). `blind_grading` refuses it too, and that's trades-eng's (the Calibration surface; ruling 9).
- **The page store stores only from a `complete` job,** never from `error` (including `timeout`), superseded or
  revoked jobs.
- **Paged and cursor responses return no cards for an errored job** (E2).
- **The legacy path serves a timed-out job's published batches** (`server.py:2792-2796`, `:3207`). **They are
  not blanked** (ruling 9): that would pull cards out from under a mid-swipe user, against U2, and P1/P2 replace
  this path at launch. Instead:
  1. An `error` or `timeout` job is **never reused**: never fresh, never joined, never deduped onto. The next tap
     starts a fresh job. S0 pins this with a test.
  2. Its evidence is tagged so **replay excludes it.** A `partial_run` exclusion reason sits beside models-eng's
     `missing_scorer_inputs` and `pack_integrity`. It's never packed, and the tag's mechanism is agreed with
     models-eng in the packed-evidence piece.
  3. Both go in the models-lead B3 notice with the I-1 diff. If models-lead requires blanking for eval integrity,
     head-eng revisits.
- Progressive first-30/100 publication while a job is still **running** (#303) is allowed. Only a deck cut short by
  a timeout or the ceiling is the violation.

## 7. Storage (AC-L8; the P23 budget set by head-eng, amendment 2 §3)

**The budget (binding):**
- **≤ about 0.2 MB compressed per active pair,** including pages 1–3. Snapshots are stored compressed.
- **A card's frozen snapshot is dropped** once its full row is written at delivery (C3/C6).
- **Evict** pages for leagues with no activity in 30 days (`trade_page_store_evict_days`).
- **A total page-store ceiling of about 250 MB** (5% of 5 GB) at the 52-week plan. It's reported by an H2-style
  size query, which ships with P1.
- **Measured numbers replace the estimates below before the flag can flip.** The flag stays OFF until then.

| Item | Per pair (est.) | Basis |
|---|---|---|
| Public pages 1–3 (90 cards × ~1.25 KB) | ~110 KB | B15 |
| Build-time full-row snapshot, first 30 (C4/C6) | ~230–325 KB physical | models-lead §2 |
| Packed unseen block, held until serve (C1/C2) | ~157 KB raw (~115–130 KB compressed) | models-lead §DEC-2 §1 |
| Candidate set, held until serve | **unknown** (to be measured) | — |
| **Total** | **~0.5–0.6 MB uncompressed, plus the candidate set; est. ~0.1–0.15 MB compressed** (to be measured) | One row per scope, upserted |

- **Against the budget:**
  - The estimate fits ≤ 0.2 MB compressed per pair, if the candidate set compresses as expected. **It's the
    unknown to measure first.**
  - The 250 MB ceiling allows about 1,250–2,500 active pairs at 0.1–0.2 MB. Eviction keeps inactive leagues out.
- The served-deck evidence is ~270 KB of full rows plus ~130 KB packed per served job, against ~17.8 MB today
  (about −98%).
- The device page (C) has no server cost.

## 8. Risks

- **Background CPU:** pre-builds (including U5's) on the one sync worker slow taps until E1 lands. Mitigations:
  debounce, and one build per scope at a time. Measured by M.
- **The device page (C) and I-2:** a device card can predate a roster move the server hasn't seen. Background
  revalidation withdraws it in place (U2), and #339's I-2 action-time checks (platforms-eng) cover sends.
- **The daily worker kill:** pages live in the DB. Only the in-process remainder of a deck past the stored pages
  is lost; page 3+ is then rebuilt within the §6.4 buffer.
- **Check errors** show "Updating" with no cards: a gate miss by design, with I-1 over speed.
- **Contention** in `server.py` and `database.py` with engagement-eng (O8) and platforms-eng: small PRs, rebased
  right before each merge.
- **The UX spec is still in progress.** The mobile integration PR waits on it.

## 9. Waivers (surfaced to head-eng → operator)

None proposed in v1.1. Every §1–§4 row is answered. Open items are listed in §10, not waived.

## 10. Open items

| ID | Item | Owner |
|---|---|---|
| FP | platforms-eng's review of contract v0 (accepted by head-eng); naming the draft-state columns | platforms-eng via head-eng |
| VSN | Whether `vsn1` includes pick `pool_value` | models-eng via head-eng |
| PACK | models-lead accepting models-eng's pack format; the pack schema is frozen only after it | models-eng → head-eng → head-bizops → models-lead |
| A2 | analytics-lead agreeing receipts move to delivered cards only (head-eng accepted) | analytics-lead via head-product |
| DEL | `accounts.py` registration for the new tables (C7 (v) is mine; `accounts.py` itself is onboarding-eng's) | head-eng confirms the grant |
| PR | The `partial_run` replay-exclusion tag mechanism (§6.8) | trades-eng + models-eng |
| CAL | `blind_grading` refuses ceiling-hit decks (trades-eng's; with models-eng's conversion) | trades-eng |
| REPL | Replenishment's evidence writes follow C2 before `deck.replenishment` runs again (the operator was asked to pause it) | trades-eng (in the packed-evidence branch) |
| TS | The Testing-settings readout row (`SettingsTesting`) | onboarding-eng via head-eng |
| UXS | ux-lead's in-place reveal spec | ux-lead via head-eng |
| THR | The final prefetch threshold; the readout spec | trades-pm via head-eng → head-product |
| SWIPE | The p99 swipe rate | analytics-lead via head-eng |
| MEAS | Measured page-store bytes per pair (and the candidate set) recorded in §7 | trades-eng (P1) |
| B3 | Notice: invalid cards stop being served (S0) | models-lead via head-eng |
| ONB | Review of the `on_roster_change` hook and the C session side | onboarding-eng via head-eng |
