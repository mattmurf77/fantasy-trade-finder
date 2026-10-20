# Feature Scope — Trades eng: the 200 ms path (S0 serve, E2, P1, P2, narrow evidence rows)

**Date:** 2026-10-20
**Entry point:** direct operator ask (2026-10-20, relayed): "Yes building should resume on the 200 ms path." On DEC-2:
"yes, with tiny rows for unseen trades." On the "finding more trades" card: "This should never happen." Brief:
`docs/plans/org-bringup/briefs/build-200ms-trades-eng.md` (head-eng).
**Builder:** trades-eng (lead), with `eng-backend` and `eng-mobile` workers in their own worktrees.
**Operator sign-off on waivers:** pending. The waivers in §9 are surfaced to head-eng, who takes them to the operator.
**Status:** DRAFT v0. Items marked **OPEN** block the piece named beside them.

**Supersedes and cites:**
- Product's PRD and scope (PR #339: `prd.md`, `scope.md`, in this folder on `plan/trade-time-to-suggestion`) set
  250 ms. **200 ms supersedes 250 ms** (operator, 2026-10-20). Those files are trades-pm's and are not edited
  here.
- Eng input: `eng-input.md` on `plan/trade-time-eng-input` @ `36af2e83`.
- Plan of record: `docs/plans/org-bringup/launch-readiness-eng.md` §3a.
- Evidence policy: `docs/plans/org-bringup/leads/models-lead-launch.md` §DEC-2. C1–C9 are binding.

---

## 0. Acceptance (the launch MUST) and how each piece serves it

| Acceptance | Pieces | Not in these pieces (gating, owned elsewhere) |
|---|---|---|
| p95 ≤ 200 ms from tapping Find a trade to the first trade card, on Wi-Fi and LTE, cold and warm | E2, P1 (one round trip, small body); S0 (no network on the tap path) | **UX** in-place reveal (the animated push is ~350 ms est.; halted). **E1** threads and instance class. **C** device page (LTE). **M** device proof (halted). |
| Every card up to date: assets on current rosters, values and engine match the server's current snapshot | S0 (fingerprint, I-1 filter, `vsn1`), P1 (serve-time compare) | platforms-eng's background refresh (S0 fetch side) |
| Never the end of ready cards ("finding more trades" never shows) | P2 (prefetch by cursor, buffer model), P1 (pages stored ahead) | models-eng: count-bounded generation, the incremental order contract |

## 1. Analytics scope

- [x] **(c) No new events in these pieces.** M's timing event is halted, and its tap → card proof is not built
  here.
- **OPEN A1, an existing-event behavior change, which needs analytics-lead's grant through head-eng before P1's
  flag can flip:**
  - P1's background pre-builds run full generation jobs, and today every completed job emits `trades_generated`
    (`server.py:9226-9238`). Pre-builds would inflate it, and many are never served.
  - **Proposal:** a never-served pre-build emits no `trades_generated`, only a job log line (mirroring C2). A page
    serve emits `trades_generated` at serve, with `deck_source="page"`.
  - Today's cache hits have the same gap (eng-input §4.2). No new event name and no new property name; only a new
    `deck_source` value and a new firing moment.
- **OPEN A2, receipts (an owner change, not an event):** receipts grades every non-ghost impression from
  `features_json` (`receipts_service.py:48-49`, `:422-456`). Under narrow rows it must grade **delivered
  (full-row) cards only**, the models-lead §DEC-2 §4 knock-on. Receipts is trades-eng's; analytics-lead must
  agree the definition change.

## 2. Schema and flag scope

**New and changed tables or columns** (grants: head-eng 2026-10-20). Every row also goes in
`docs/data-dictionary.md` in the same PR.

| Item | Piece | Shape (proposed) | Status |
|---|---|---|---|
| **Page store**, e.g. `trade_page_store` | P1 | Unique `(user_id, league_id, scoring_format, request_scope)`; one row per key, upserted. Columns: `roster_fp`, `values_snapshot_id`, `engine_version`, `config_signature`, `built_at`, `expires_at`, `deck_job_id`, `pages_json` (public card projection, pages 1..k), `evidence_blob` (compressed build-time snapshot for C6: first-30 full rows, the packed block, the candidate set), `state`. | Granted. **OPEN P1-K:** head-eng confirms the key excludes the fingerprint (§6.2) |
| `features_compact` on `deck_impressions` | Narrow rows | JSON with exactly the §DEC-2 §2 key list, frozen at build time | Granted. The interim form if C7 (i) isn't ready (models-lead §4) |
| **Per-run pack table**, e.g. `deck_impression_packs` | Narrow rows | One row per **served** job: per-run fields and dictionaries, per-card arrays, `pack_version`, `checksum` (models-lead §DEC-2 §1) | **OPEN N-H:** waits on head-eng's call on models-eng's per-run header proposal. The schema isn't frozen before it |
| C8 archive marker | Narrow rows | 2% by deck, 90-day full rows; the marker's shape is from models-eng's C8 spec | **OPEN** (models-eng) |
| **Roster refresh state** (`refreshed_at`, `status`, `last_error_code` per league) | S0 (platforms-eng writes; trades-eng reads) | Columns on `leagues`, or a small table | **NOT in either grant**: a bright line, reported to head-eng |
| Account deletion and export for the page store and pack table | P1, narrow rows | Register in `_ADDITIONAL_PRIVATE_TABLES` and export (D-183; C7 (v)) | **`accounts.py` isn't in my grant**: needs a head-eng grant or onboarding-eng's edit |

**New feature flags:**
- **The P1 page store:** key **OPEN** (release-lead names it, through head-eng). It goes in `config/features.json`
  as `false`, `backend/feature_flags.py` `FLAG_KEYS`, and `docs/config-reference.md`.
  - **Default OFF. trades-eng never flips it.**
  - **Graduation:**
    - device p95 ≤ 200 ms (M);
    - C7 tests green;
    - A1 granted;
    - the byte budget accepted (P23);
    - models-lead's 13b sign-off.
  - **Kill:** flip OFF and reload (`POST /api/feature-flags/reload`). Serving falls back to today's path, and the
    page store is shed-safe (AC-11b).

**New `model_config` keys** (`docs/config-reference.md`; the deploy-free tuning levers):

| Key | Default | Purpose |
|---|---|---|
| `trade_page_size` | 30 | Cards per page. C4 holds regardless (the first 30 are always full rows) |
| `trade_pages_stored` | 3 | Pages pre-built and stored per scope (§7). **OPEN** until the buffer model has swipe-rate data |
| `trade_prefetch_remaining` | 10 | The client asks for the next page when this many ready cards remain (P2). Served to the client, so it's not a constant |
| `trade_prebuild_debounce_s` | 20 | Coalesces the input-change triggers before a background build |

## 3. Evidence scope (D-056)

- [ ] **Structural guard** `mobile/tests/check-trade-pages.js` (plus `npm run test:trade-pages`). It pins that:
  - `api/trades.ts` sends the opt-in paging param;
  - the `TradesScreen` consumer appends `/status` deltas by cursor and never replaces delivered cards;
  - the prefetch trigger reads the server-provided `prefetch_remaining`;
  - no "finding more trades" / keep-going state renders while ready cards remain.
- [ ] **Unit tests** (backend pytest; the brief's must-haves are **bold**):

  | Test file | Pins |
  |---|---|
  | `test_roster_snapshot.py` | Canonical form; names and timestamps excluded; co-owners; `rfp1` prefix; `vsn1` content hash stable across a simulated restart |
  | `test_trade_freshness_roster.py` | A job freshness and join miss on an fp change; no miss on a display-name change |
  | **`test_i1_serve_filter.py`** | A moved player or pick is never served on every path (fresh, cached, joined, page). **The check-error path gives "updating" with no cards.** |
  | **`test_trade_page_store.py`** | **Concurrency:** two builders racing one key, serve during rebuild, supersede, survival across a simulated restart. Plus the §6.2 serve rules. |
  | **`test_trade_responses_small.py`** | **E2 sizes:** the first-page body ≤ 64 KB for 30 cards; `/status` returns only cards after the cursor; a legacy request without the param is byte-identical to today |
  | **`test_narrow_evidence.py`** | **C2:** no `deck_impressions`, pack or candidate-set rows for an unserved pre-build. **C4:** the first 30 are always full. C3 (delivered pages), C5 (ghosts unpacked, with `assets_json`), C6 (rows equal the build-time snapshot, not a recomputation), C8 (2% chosen by deck) |
  | `test_receipts_delivered_only.py` | A2 |
  | AC-9 identity test (from models-eng) | Page 1 = the full deck's top N; later pages never reorder delivered cards |
- [ ] **Code-walk proof** (written by the build, file:line), for each piece:
  - tap → `/generate` (paged) → page-store read → fingerprint compare → I-1 → response → first card render;
  - P2's prefetch timing against the buffer model.
- [ ] **Manual TestFlight checklist** (with the launch binary; it reuses PR #339 §9.4 steps 1–2, 6 and 10–14,
  re-pointed at 200 ms):
  - cold tap, then warm tap: first card with no "Looking for trades…";
  - drop a player in Sleeper, then tap: that player is not shown;
  - swipe 90 cards quickly: "finding more trades" never appears;
  - Airplane Mode: an honest offline state.
- `testID`s: one for the "updating" state (P1 serve path). The name follows the testid-lint registry. No other UI
  is in these pieces.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **Yes** (E2, P1, P2) | `/api/trades/generate` (the opt-in first page, page metadata, `prefetch_remaining`); `/api/trades/status` (`cursor` → delta). head-eng reviews as the doc owner |
| `docs/data-dictionary.md` | **Yes** | The page store, `features_compact`, the pack table, the archive marker |
| `docs/config-reference.md` | **Yes** | The P1 flag; the four `model_config` keys |
| `living-memory/LLD.md` | **Yes** | The fingerprint invariant (`rfp1`/`vsn1`); "the tap path reads stored rows only"; the page-store convention |
| `docs/architecture.md` | **Yes** (head-eng reviews) | The page-store tier and the pre-build trigger in the trade-serving flow |
| `living-memory/HLD.md` | **Yes** (head-eng reviews) | A new serving tier (pre-built pages) |
| `docs/cross-client-invariants.md` | n/a | `prefetch_remaining` and page size are served per response, not hard-coded in clients |
| `docs/glossary.md` | **Yes** | Roster fingerprint, values snapshot id, first page, delivered card, narrow (packed) row |
| ADR | **Yes** (head-eng writes) | ADR-025, narrow evidence for new writes (C9). The page-store ADR follows head-eng's §3a "P1 design (ADR plus page-store schema)" |

## 5. Ship gate declaration

- **CI green** on every piece's PR: `backend-tests`, `mobile-typecheck` (with the `check-*.js` suites),
  `maestro-testid-lint`.
- **Evidence recorded** in `living-memory/TEST_LEDGER.md` at merge (release-lead's scribe).
- **TestFlight checklist:** run by the operator on the launch binary, with the outcome logged.
- **Express lane:** no.
- **Merge order** (release-lead's queue): scope → S0 serve → E2 → P1 (flag OFF) → narrow rows → P2 server. P2's
  mobile half ships in the single launch binary.

## 6. Contracts

### 6.1 The roster fingerprint and values snapshot id (with platforms-eng)

**Status:** proposed 2026-10-20, awaiting platforms-eng's agreement through head-eng. It is copied verbatim into
platforms-eng's S0 scope block.
- `rfp1:` + sha256[:32] over the canonical stored `league_members` rosters, `draft_picks` ownership and the
  draft-state columns. Names, timestamps, SQL ids and values are excluded.
  - It is recomputed at serve from stored rows: no network, a few ms (est.).
  - A version bump changes the prefix.
- One pure function, `roster_snapshot(conn, league_id)`, returns `fp`, the `asset_owner` map, `refreshed_at` and
  `status`. The I-1 filter and the freshness compare use the same snapshot.
- platforms-eng's refresh commits the rows, then computes the fp, then calls `on_roster_change(league, old, new)`.
  trades-eng invalidates jobs and enqueues debounced rebuilds. There is no fetched-vs-stored diff inside
  session-init, which would race the background upsert (`server.py:22975-22979`, `:22804`).
- `vsn1:` + sha256[:32] over the format's seed map, memoized on `(fmt, pool_generation())`. It is read-only on the
  pool. `pool_generation` itself is process-local, so it can't key a DB page.
- Full draft: `trades-eng-roster-fingerprint-contract-draft.md` (shared notes; copied here once agreed).

### 6.2 Page-store serve rules

| Compared at serve | Action |
|---|---|
| Everything equal | Serve page 1 inline |
| `roster_fp` differs | Serve the I-1-filtered cards with "updating", and rebuild |
| `values_snapshot_id` differs | Serve-and-refresh |
| `engine_version` or `config_signature` differs | Block: the fresh path, a gate miss (PRD #339 §5.2 exception 2) |
| The check errors | "Updating", no cards, never unchecked |

### 6.3 Identity and order (from models-eng)

- Page 1 = the full deck's top N (AC-9).
- Later pages extend the order and never reorder delivered cards.
- These depend on the count-bounded conversion. The AC-9 test lands with models-eng's PR, and P1's flag can't
  graduate without it.

### 6.4 Old binaries (E2 and P2)

- **Opt-in by request param** (`page=1` on `/generate`, `cursor` on `/status`). Requests without them get
  today's response, byte-identical (pinned by a test). So no minimum-version gate is needed for these pieces.
- **Stated here as required:** the server-side legacy path remains until head-eng retires it.

## 7. Storage (for head-eng's P23 / H1–H3 check)

| Item | Per pair (est.) | Basis |
|---|---|---|
| Public pages 1–3 (90 cards × ~1.25 KB) | ~110 KB | B15 (37,348 B per 30 cards) |
| Build-time full-row snapshot, first 30 (C4/C6) | ~230–325 KB physical | 30 × 7.6–10.8 KB (models-lead §2) |
| Packed unseen block, held until serve (C1/C2) | ~157 KB raw (~115–130 KB compressed) | models-lead §DEC-2 §1 |
| Candidate set held until serve | **unknown** | Needs a measurement (prepared-inventory chunked plan: the candidate-set singleton's capacity is unmeasured) |
| **Total** | **~0.5–0.6 MB uncompressed, plus the candidate set; est. ~0.1–0.15 MB compressed** | One row per scope, upserted; superseded rows are overwritten, not accumulated |

- At 22 active pairs that's ~2–3 MB compressed; at 100× (2,200 pairs), ~0.2–0.3 GB compressed.
- **This is much larger than eng-input's ~37 KB per pair**, because C4/C6 require holding evidence until delivery.
- The served-deck evidence (C3/C4/C1) replaces today's ~17.8 MB per job with roughly 270 KB of full rows plus
  ~130 KB packed: about −98%.

## 8. Risks

- **Background CPU:** pre-builds run on daemon threads in the single worker. Without E1 (threads, instance class),
  more builds mean slower taps. Mitigated by the debounce key and one build per scope at a time; measured by M.
- **Freshness vs storage:** tighter refresh means more pre-builds; C2 keeps unserved builds row-free.
- **Daily worker kill** (NEXT 2026-10-15): in-process decks die daily. P1 and P2 keep pages in the DB, so a
  restart costs only the in-process remainder of the deck past the stored pages.
- **Check errors** show "updating" with no cards: a gate miss, by design (I-1 over speed).
- **Contention** in `server.py` and `database.py` with engagement-eng (O8) and platforms-eng (S0 fetch, the
  Sleeper write): small PRs, rebased right before each merge.

## 9. Waivers (surfaced to head-eng → operator)

1. §1: no new analytics events in these pieces (M is halted). A1 and A2 are open, not waived.
2. §3: no mobile UI evidence for the in-place reveal (UX is halted, not in these pieces).

## 10. Open items

| ID | Item | Owner |
|---|---|---|
| P1-K | The page-store key excludes the fingerprint (§6.2) | head-eng |
| FP | Fingerprint contract agreement; name the draft-state columns | platforms-eng via head-eng |
| RS | The refresh-state schema grant | head-eng |
| N-H | The per-run header / pack-table decision | head-eng → models-lead |
| A1 | `trades_generated` behavior for pre-builds and page serves | analytics-lead via head-eng |
| A2 | Receipts graded on delivered cards only | analytics-lead via head-eng |
| FLAG | The P1 flag key | release-lead via head-eng |
| DEL | `accounts.py` registration for the new tables | head-eng / onboarding-eng |
| SWIPE | p99 swipe rate, for the buffer model | analytics-lead via head-eng → head-product (may need W3) |
| B3 | Notice: invalid cards stop being served (S0) | models-lead via head-eng |
| ONB | Review of the `on_roster_change` hook | onboarding-eng via head-eng |
| END | The genuine end-of-deck state (every candidate seen): handling proposed to head-eng, copy by head-product | trades-eng → head-eng |
