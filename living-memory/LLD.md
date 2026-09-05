# Low-Level Design — Fantasy Trade Finder

> **Purpose:** the mechanic's-eye view as living memory. Schemas, contracts, naming rules at the level Claude can implement directly. Authoritative database schema and API route detail live in [`../docs/data-dictionary.md`](../docs/data-dictionary.md) and [`../docs/api-reference.md`](../docs/api-reference.md); cross-client invariants in [`../docs/cross-client-invariants.md`](../docs/cross-client-invariants.md). This file points to those and adds living-memory aspects.
>
> **Read at:** before adding/changing a database table, API route, or cross-client constant. **Write at:** when conventions actually shift.
>
> Companion files: [`../docs/data-dictionary.md`](../docs/data-dictionary.md), [`../docs/api-reference.md`](../docs/api-reference.md), [`../docs/cross-client-invariants.md`](../docs/cross-client-invariants.md), [`HLD.md`](HLD.md).

---

## Table of Contents
- [Authoritative References](#authoritative-references)
- [Directory Layout](#directory-layout)
- [Naming Conventions](#naming-conventions)
- [Database Schema (Pointer)](#database-schema-pointer)
- [API Surface (Pointer)](#api-surface-pointer)
- [Cross-Client Invariants (Pointer)](#cross-client-invariants-pointer)
- [Code Conventions](#code-conventions)
- [Living-Memory File Schemas](#living-memory-file-schemas)
- [Tooling & Constraints](#tooling--constraints)
- [One policy evaluator, one choke point (2026-09-04, personal-market policy)](#one-policy-evaluator-one-choke-point-2026-09-04-personal-market-policy)
- [Ownership and telemetry invariants](#ownership-and-telemetry-invariants)
- [Guide beats: the GuideStep eligibility convention (2026-08-15, guide-v2)](#guide-beats-the-guidestep-eligibility-convention-2026-08-15-guide-v2)
- [Trade generation pipeline v2: gen2_* namespace + GenerationReport hand-off (2026-08-16, trade_gen.v2)](#trade-generation-pipeline-v2-gen2_-namespace--generationreport-hand-off-2026-08-16-trade_genv2)
- [Presentment rules: construction-gate vs presentment-filter layering (2026-08-16, trade.presentment_rules)](#presentment-rules-construction-gate-vs-presentment-filter-layering-2026-08-16-tradepresentment_rules)
- [Synthesized cards carry the gates of the surface that shows them (2026-08-19, D-096)](#synthesized-cards-carry-the-gates-of-the-surface-that-shows-them-2026-08-19-d-096)
- [Mock-draft ownership honesty: resolver-owned labels (2026-08-16, #328)](#mock-draft-ownership-honesty-resolver-owned-labels-2026-08-16-328)
- [Finder preselection contract now carries opponent + auto-run intent (2026-08-16, #330)](#finder-preselection-contract-now-carries-opponent--auto-run-intent-2026-08-16-330)
- [Ranking vs gate: what a term may judge (2026-08-18, engine-quality)](#ranking-vs-gate-what-a-term-may-judge-2026-08-18-engine-quality)
- [Bake-off attribution + hygiene seams (2026-08-18, trade.bakeoff)](#bake-off-attribution--hygiene-seams-2026-08-18-tradebakeoff)
- [Presentation surfaces: parity-by-reuse, and the entry-by-optional-prop flag gate (2026-08-18, trades.presentation_v2)](#presentation-surfaces-parity-by-reuse-and-the-entry-by-optional-prop-flag-gate-2026-08-18-tradespresentation_v2)
- [Placements vs comparisons: assertion and sample are different inputs (2026-08-19, D-085)](#placements-vs-comparisons-assertion-and-sample-are-different-inputs-2026-08-19-d-085)
- [Settings tree: one route, two components, per-page query ownership (2026-08-19, account.settings_hub)](#settings-tree-one-route-two-components-per-page-query-ownership-2026-08-19-accountsettings_hub)
- [Derived league state belongs to the writer, not the reader (2026-08-19, D-091)](#derived-league-state-belongs-to-the-writer-not-the-reader-2026-08-19-d-091)

- [Derived display coordinates: store the ORDER, never the SLOT (2026-08-19, D-090)](#derived-display-coordinates-store-the-order-never-the-slot-2026-08-19-d-090)
- [Predicting a user's own vocabulary: objection codes, uniform-key stamps, narration-gated payloads (2026-08-21, D-142)](#predicting-a-users-own-vocabulary-objection-codes-uniform-key-stamps-narration-gated-payloads-2026-08-21-d-142)
- [Consulting a leaf from inside an engine: live module bindings, one kwarg, copy-at-log (2026-08-22, D-147)](#consulting-a-leaf-from-inside-an-engine-live-module-bindings-one-kwarg-copy-at-log-2026-08-22-d-147)
- [Retiring a per-user setting: 410 the write, fix the read (2026-08-21, D-146)](#retiring-a-per-user-setting-410-the-write-fix-the-read-2026-08-21-d-146)
- [Pricing waterfalls: resolve once per scope, pass down, fall soft (2026-08-21, D-146)](#pricing-waterfalls-resolve-once-per-scope-pass-down-fall-soft-2026-08-21-d-146)
- [One number, one seam: aligning surfaces that must agree (2026-08-21, D-148)](#one-number-one-seam-aligning-surfaces-that-must-agree-2026-08-21-d-148)
- [Append-only, version-stamped measurement tables (2026-08-21, D-144, `receipts_*`)](#append-only-version-stamped-measurement-tables-2026-08-21-d-144-receipts_)
- [The opponent sweep is complete; a generation budget is never a deck cap (2026-08-22, D-154, `trade.full_sweep`)](#the-opponent-sweep-is-complete-a-generation-budget-is-never-a-deck-cap-2026-08-22-d-154-tradefull_sweep)
- [Tiers-save route contract shrank: `demoted_pids` is an ignored legacy key (2026-08-24, D-160)](#tiers-save-route-contract-shrank-demoted_pids-is-an-ignored-legacy-key-2026-08-24-d-160)
- [Provider identity is reconciled server-side; presentation is server config (2026-08-28, ADR-016)](#provider-identity-is-reconciled-server-side-presentation-is-server-config-2026-08-28-adr-016)
- [Pick assets ride the mixed arrays on every propose route; the server splits and encodes (2026-09-02, D-176)](#pick-assets-ride-the-mixed-arrays-on-every-propose-route-the-server-splits-and-encodes-2026-09-02-d-172)
- [Request scoring views and captured job ownership (2026-09-04, budget scalability)](#request-scoring-views-and-captured-job-ownership-2026-09-04-budget-scalability)
- [Win Now snapshot and request isolation](#win-now-snapshot-and-request-isolation)

---

## Authoritative References

| Concern | Source of truth |
|---|---|
| Database tables and columns | [`../docs/data-dictionary.md`](../docs/data-dictionary.md) |
| HTTP API routes | [`../docs/api-reference.md`](../docs/api-reference.md) |
| Constants shared across clients (tier colors, K-factors, enums) | [`../docs/cross-client-invariants.md`](../docs/cross-client-invariants.md) |
| Domain vocabulary | [`../docs/glossary.md`](../docs/glossary.md) |
| Env vars / feature flags / `model_config` keys | [`../docs/config-reference.md`](../docs/config-reference.md) |
| Module wiring + data flow | [`../docs/architecture.md`](../docs/architecture.md) |

When you change something on the left, update the doc on the right. The per-trigger table in [`../docs/CLAUDE.md`](../docs/CLAUDE.md) is the canonical update-trigger checklist.

---

## Directory Layout

```
fantasy-trade-finder/
├── CLAUDE.md                     # operator's brief; points to docs/ and living-memory/
├── README.md                     # public project description
├── context.md                    # detailed orientation
├── run.py                        # Flask dev server entry
├── build.sh                      # deployment script
├── render.yaml                   # Render hosting config
├── requirements.txt              # Python deps
├── trade_finder.db               # SQLite DB (root; legacy)
├── backend/
│   ├── server.py                 # Flask routes
│   ├── database.py               # SQLAlchemy Core schema
│   ├── ranking_service.py        # Elo (2- and 3-player)
│   ├── trade_service.py          # mutual-gain generation
│   ├── smart_matchup_generator.py # Claude-powered selection
│   └── data_loader.py            # DynastyProcess → seed Elo
├── data/
│   └── trade_finder.db           # canonical DB location
├── web/                          # vanilla HTML/CSS/JS
├── mobile/                       # React Native / Expo
├── extension/                    # MV3 browser extension
├── config/
│   └── features.json             # feature flags
├── docs/                         # reference documentation
├── living-memory/                # this folder
├── feature-evaluator/            # custom Claude Code skill
├── project-reorganizer/          # custom Claude Code skill
└── scripts/                      # one-off scripts
```

---

## Naming Conventions

### Code
- **Python:** `snake_case` for files, functions, variables. `PascalCase` for classes.
- **JavaScript/TypeScript:** `camelCase` for variables, `PascalCase` for components. `kebab-case` for filenames in web/.
- **Routes:** `/api/<resource>/<action>` pattern. Use plural resource names (`/trades`, `/notifications`). Avoid `/api/get-trades` style.
- **Database tables:** `snake_case`, singular (`user`, `player`, `league`) or plural for join/event tables (`swipe_decisions`, `trade_decisions`).
- **Env vars:** `SCREAMING_SNAKE_CASE`. Document new ones in [`../docs/config-reference.md`](../docs/config-reference.md).

### Documentation
- ADR filenames: `NNNN-kebab-title.md` in `docs/adr/` (e.g. `0001-three-player-matchups.md`).
- `docs/` files: lowercase kebab. Living-memory files: UPPERCASE for foundational, kebab for supplementary.

---

## Database Schema (Pointer)

See [`../docs/data-dictionary.md`](../docs/data-dictionary.md) for full schema. Key tables (summarized):

- **`user`** — Sleeper user identity (user_id, username, last_seen)
- **`league`** — Sleeper league + season metadata
- **`player`** — denormalized Sleeper player + DynastyProcess value seed
- **`roster`** — user-league-player ownership
- **`elo_rating`** — per-user-per-player Elo with history
- **`swipe_decisions`** — pairwise comparison events (powers ranking)
- **`trade_decisions`** — like/pass on generated trade cards
- **`trade_card`** — cached generated trade cards
- **`trade_match`** — mutual-like matches between users
- **`notification`** — inbox events

DB lives in two places (legacy): `data/trade_finder.db` (canonical) AND `trade_finder.db` at repo root. Cleanup TBD — see [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md).

---

## API Surface (Pointer)

See [`../docs/api-reference.md`](../docs/api-reference.md) for full route detail. Quick map (from `../context.md`):

- **Session/Auth:** `POST /api/session/init`, `GET /api/session/ping`
- **Ranking:** `GET /api/trio`, `POST /api/rank3`, `POST /api/rankings/submit`
- **Trades:** `POST /api/trades/generate`, `GET /api/trades`, `POST /api/trades/swipe`, `POST /api/trades/queue` (flag `calc.merged_layout`; the #384 ✓ cell — a hand-built package recorded as a like through the swipe route's own path, refused up front when the likes-you mirror would not fire), `POST /api/trades/fair-packages` (flag `calc.merged_layout`; the #384 W6-B canvas sweep, [D-153] — a FIXED give-side anchor, 1–3-asset returns, `eval_consensus_package` gates shared with asset-ideas, deterministic `fairpk_` card ids so a swipe reconstructs), `GET /api/trades/liked`
- **Trade matching:** `GET /api/trades/matches`, `POST /api/trades/matches/<id>/disposition`
- **Notifications:** `GET/POST /api/notifications`, `POST /api/notifications/read-all`
- **Admin:** `GET/PUT /api/admin/config/<key>`
- **Misc:** `GET /api/league/coverage`, `POST /api/reset`, `GET /api/debug/log?n=100`

---

## Cross-Client Invariants (Pointer)

See [`../docs/cross-client-invariants.md`](../docs/cross-client-invariants.md). Examples of values that must stay in sync across backend + web + mobile + extension:

- Tier color hex codes (Elite, Solid, Bench, Depth, etc.)
- Elo K-factors (per interaction type)
- Slot type enum strings (`STARTER`, `BENCH`, `IR`, `TAXI`)
- Notification type strings
- Trade card disposition states (`pending`, `liked`, `passed`, `matched`, `accepted`, `declined`)

Changes to any of these MUST update [`../docs/cross-client-invariants.md`](../docs/cross-client-invariants.md) AND every client.

---

## Code Conventions

**Per-caller density on shared presentational primitives is an opt-in prop, never a branch change** (2026-08-11, #299). `PlayerCard`'s `dense` row is consumed by three screens with different interaction contracts — the Tiers board's rows are pressable *and* drag-liftable (the 44pt touch minimum binds), the FA list passes a `statsSlot`, the League drill-in is inert and passes neither. When one caller needs different geometry, add a boolean prop defaulting to the existing behaviour so every other caller stays byte-identical; do not reshape the shared branch and then audit the fallout. Enforce with a structural test that pins both the *old* dimension and the non-opt-in of every other caller.

### Karpathy Four Principles (per [`../docs/coding-guidelines.md`](../docs/coding-guidelines.md))
1. **Think before coding** — surface assumptions and tradeoffs; ask when unclear.
2. **Simplicity first** — minimum code that solves the problem; no speculative abstractions.
3. **Surgical changes** — every changed line traces to the request; no drive-by refactors.
4. **Goal-driven execution** — define verifiable success criteria; loop until met.

### Specific patterns
- **Layer code is pure where possible.** `ranking_service.py` and `trade_service.py` operate on inputs + return outputs; persistence is wrapped at the route layer.
- **No magic numbers in service code.** Tunables go in `config/features.json` or `model_config` table. Document new keys in [`../docs/config-reference.md`](../docs/config-reference.md).
- **Use the debug ring buffer.** Backend code logs to the in-memory ring buffer (200 entries, accessible via `GET /api/debug/log?n=100`). No persistent log files.
- **DB calls via SQLAlchemy Core (not ORM).** Stays close to SQL; no migrations framework in use.
- **Capturing HttpOnly third-party cookies on mobile: read the NATIVE cookie store, not injected JS** (ESPN Connect WebView, Phase 1b, flag `espn.webview_capture`). A WebView login can only hand back a credential the page sets as a readable cookie — but `espn_s2` is issued **HttpOnly**, so the WebView's `document.cookie` (and any injected `localStorage`/`cookie` poller, the pattern `SleeperConnectScreen` uses) never sees it. Read it from WKHTTPCookieStore via `@react-native-cookies/cookies` (`CookieManager.get(domain)`) instead. The pure extractor lives in `mobile/src/utils/espnCookies.ts` (`pickEspnCookies` — unit-tested in `mobile/tests/check-espn-cookies.js`); the screen is `EspnConnectScreen`. Injected JS on the login page is limited to a MutationObserver that signals the Disney SSO one-time-code STEP so a native hint can render — it never reads the code or any DOM value. The only data that leaves the WebView is the two cookie strings, and they go to `POST /api/espn/link`, never to analytics. See DECISIONS.md D-021.
- **A save handler may write a column the route contract never mentions — say so in the docs, and make the write conditional.** P0-1 (2026-08-11) added implicit `users.ranking_method` writes to four save routes. The idiom is `set_ranking_method_if_unset(user_id, method, allow_over=(...))`: a **single conditional `UPDATE`** (race-free — no read-then-write window, so two concurrent saves cannot both decide the column is empty), returning *"did I write"* so callers can pay side-effect costs (cache drops, logs) only on a real write. Prefer this over read-then-write for any "first one wins" column. The write must never be able to fail the save it rides on. See DECISIONS.md D-026.
- **Deep-link destinations reachable while signed out belong on the ROOT stack, never inside `Main`.** A link that resolves into the tab stack drops a session-less user into empty tabs with no way forward — the P0-5 stranding bug, arrived at from a second direction. Corollary: **post-auth routing keys off a server sentinel (`no_league`), never off a user flag** like `user.account_only`; the sentinel is the fact, the flag is a label that goes stale the moment the user links a platform league. See DECISIONS.md D-028, D-029.
- **Shared emitters read feature flags imperatively, not through the hook.** A helper called from several screens (`buildInviteUrl`) reads `useFeatureFlags.getState()` at call time, so no two call sites can observe different flag values within a render pass. Hook-based reads are for components.
- **A bell-inbox row is written BESIDE the push, at the call site — never inside `_send_typed_push`.** The dispatcher's gates (prefs → bucket → frequency cap → quiet hours → Expo) are statements about *interrupting* the user; none of them is a statement about what belongs in a list the user chose to open. Use `_write_inbox_row()` next to the push, and decide idempotency explicitly at each site: it **cannot** be borrowed from the push, because `_freq_cap_blocks` reads `notification_events_log`, which is only written when a push actually leaves. A suppressed push logs nothing, so a shared gate lets a cron-driven row re-fire on every tick (the 15-minute `match_expiring` scan: ~96 duplicate rows a day per match). Either the site is structurally once-only, or it uses `notification_exists_with_meta`. The payoff is that inbox rows ship to every user while push stays operator-only. See DECISIONS.md D-045.
- **A cross-client enum whose unknown value degrades silently needs a test that reads every consumer.** `notifications.type` has four independent consumers (two glyph maps, two tap routers, mobile + web) and no shared source; an unrecognised value produces a grey bell with a dead tap — no error, no warning, no log line. `mobile/tests/check-notif-glyphs.js` parses all four from the real files. It found two live defects on its first run that code review had not: `referral_joined` (absent from all four since the referral loop shipped) and `trade_accepted`/`trade_declined` (only the *push* kind `match_accepted` was listed, so two of the four original inbox types had a glyph and a dead tap). **Inbox types are not push kinds** — the DB writes `f"trade_{outcome}"`.
- **League STATE gets an append-only history table; the snapshot tables stay snapshots** (ADR-011). `league_members` / `member_rankings` / `trade_block` keep their replace-on-write semantics — history lives beside them in `league_roster_history` / `league_board_history`, written by triggers, keyed on a **bucket label** (`period_key`, ISO week-numbering year), never an instant. Conventions that ride along: history writes happen in their **own transaction after** the snapshot write commits (never inside `replace_espn_league_members`' `engine.begin()` — a failure there leaves a league with zero members); upserts are **precedence-not-recency** where writers differ in fidelity (`weekly` server-fetched beats `sync` client-posted); a scheduled writer must **fetch live**, never read a client-posted snapshot table and stamp it with the current period (that fabricates history); and stored team identity is the **platform-native team slot** (`team_key`), never derived from a user id — `owner_user_id` is a nullable, re-stampable attribute.
- **A league-SHARED table is keyed on the team, not on whoever synced it** (2026-08-15, [ADR-012](../docs/adr/adr-012-co-owned-roster-identity.md)). `league_members` rows are written by every member's `session_init`, so the key must be an id all of them independently agree on: each Sleeper roster's primary `owner_id`. The convention that falls out is **two session identities**, and picking the wrong one is now the name of a bug class. `sess["user_id"]` is the ACCOUNT — rankings, swipes, tier overrides, entitlements, analytics, notifications, feedback. `_league_user_id(sess)` is the LEAGUE identity, the `owner_id` of the roster the caller owns *or co-owns* — `league_members` keys, `is_you`, "my roster" lookups, the mock-draft owner set. They are the same string for a sole owner and for any session minted before the key existed (the helper falls back), which is precisely what makes swapping a league-scoped comparison from one to the other a safe, testable edit. Corollary: **exclude the caller's own roster by `roster_id`, never by comparing owner ids** — `owner_id != user_id` is true for a roster you co-own, which is how a co-manager's own team was posted to the engine as a trade partner. Predicate + mirrors: `backend/sleeper_roster.py`, [`../docs/cross-client-invariants.md`](../docs/cross-client-invariants.md) § Sleeper roster ownership.
- **One owner per form.** `LinkSleeperSheet` is the single owner of the Sleeper-identity-link form — including the 409 `merge_choice_required` alert, whose failure mode is deleting the wrong ranking board. A second implementation of a destructive-confirmation flow is a defect waiting for the two copies to drift.

---

## Living-Memory File Schemas

See [`FORMAT.md`](FORMAT.md) for the strict spec. Headline:

```markdown
# <FileName> — Fantasy Trade Finder

> **Purpose:** <one sentence>
> **Read at:** <trigger>
> **Write at:** <trigger>
> Companion files: <list>

---

## Table of Contents
- [Section 1](#section-1)
- ...

---

## YYYY-MM-DD  (or topical section)

content...
```

Required: H1 with project suffix, purpose blockquote, Table of Contents, ISO dates, sequential IDs.

---

## Tooling & Constraints

- **Python 3** (see `.python-version` for exact). Currently runs on system Python; venv setup not enforced.
- **Dependencies:** `pip install -r requirements.txt`. Core: `flask`, `sqlalchemy`, `anthropic`.
- **No build step for backend.** Flask dev server via `python3 run.py`.
- **Web client has no build step** — vanilla files served by Flask.
- **Mobile client uses Expo** — `npx expo start --tunnel --clear`.
- **Browser extension is MV3** — load unpacked in Chrome/Edge.
- **Tests:** ad-hoc scripts (`dump_mismatches.py`, `tmp_check_db.py`, etc.). No pytest suite yet — see [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md).
- **Port 5000 conflict on macOS:** AirPlay Receiver uses it. Kill via `lsof -ti:5000 | xargs kill -9`. See [`GOTCHAS.md`](GOTCHAS.md).

## One policy evaluator, one choke point (2026-09-04, personal-market policy)

**The convention:** eligibility thresholds live in exactly one module (`backend/trade_policy.py`), and every card passes it **after its final package is assembled** — not merely at generation. Generation may prefilter cheaply; the evaluator is the *last* check, and no card reaches a user without it.

**Why it is a convention and not just a feature.** Before this, threshold logic was duplicated across `trade_service`'s v2 pair generator, `trade_optimizer`'s v3 package search and several post-generation mutation paths in `server.py`. That made `fairness_floor_divergence` = 0.55, the relaxed fallback, both sweeteners, swap/edit, likes-you injection, wildcards and weekly replenishment **six independent routes to the deck under different bars** — none of them wrong on its own, all of them a bypass in aggregate. The rule that prevents a seventh is structural: the choke point sits on `final_cards` in `_run_trade_job`, immediately before the ghost split, so a new mutation layer is either above it (and therefore gated) or it has to be inserted between two adjacent statements.

**Three rules for anyone adding a threshold:**

1. **A mutation voids the verdict.** Anything that changes a package — a sweetener, a swap, a filler — must re-ask. Both sweetener paths do; that is why `_gap_extra_ok` calls the evaluator rather than only re-running the surplus math.
2. **A user preference composes with `max`, never `min`.** A stated preference may tighten a system policy and can never loosen it. The pre-existing `min(requested, fairness_floor_divergence)` is the counterexample this rule exists to name: it turned a stricter 0.75 request into a looser 0.55 gate.
3. **Fail safe means toward consensus.** Missing evidence prices an asset at consensus and buys no floor relief. `trade_policy.shrink_board` is deliberately NOT `trade_service._shrink_user_elo`, which returns a board **raw** when confidence is None — for a partner board that is precisely backwards.

**Leaf discipline, same as `suggestion_telemetry.py`:** nothing in `trade_policy` imports `server`, and `trade_service` / `trade_optimizer` are imported **lazily inside functions** (both directions cycle otherwise). The lazy `trade_service._c` read is also what makes a bake-off arm's thread-local `_cfg_override` reach the evaluator, so an arm's candidates are judged under the arm's own configuration.

**Flag-off must be an early return, not a no-op branch.** `make_pair_evaluator` returns `None` when the flag is off, so each in-loop gate is one `is None` check with no allocation; the choke point returns the input list after two boolean reads; the impression stamp is gated per JOB (`if policy_results:`), never per card, because `save_deck_impressions` uses `executemany` and compiles from the first row's keys.

**Orthogonal attribution.** `model_arm` (which generator) and `policy_variant` (which policy) are separate columns. Adding a policy as a generator arm would confound two questions in one label and split an already-underpowered sample — see [D-181](DECISIONS.md).

### Roster checks and publication (2026-09-04)

The final roster gate precedes market quotas. A mutation invalidates roster evidence; the context cache key includes both final asset lists and partner. Exact matching shares every slot. Constrained position-group coverage may not worsen, including an established single-absence buffer. Unknown inputs cannot pass; shadow failures preserve the legacy deck, enforcement failures publish an empty deck. `final_checks_pending` guards every provisional card write; flag-off jobs retain their original key shape. Card evidence is public only with protection; frozen impression evidence and capped `roster_check` rejection rows support shadow review. Safety-switch changes invalidate completed caches. See `docs/plans/post-trade-roster-evaluation/code-walk.md`.

## Guide beats: the GuideStep eligibility convention (2026-08-15, guide-v2)

Every Analyst beat declares, in `analystScript.ts`, machine-checked by `mobile/tests/check-guide-script.js` (CI):
`retireAfter` ({event,count} client receipt, or `'never'` + in-file reason) · `maxDisplayCount` · `invalidateOn` (receipt ids) · `adoptionEvent` (a REGISTERED analytics event — the M6 join key; receipts are not events) · degrade contract (`degradeLine` | `degrade:'suppress'` | non-deictic line) · copy class caps (auto 12w + autoMs floor / action 16 / tap 20 / cta 16).
**Client-receipt rule:** retirement/invalidation read only `recordGuideReceipt(...)` receipts written by screens at the real moment — never server-fired event names (`quickset_completed`, `trio_swipe` are the standing traps). Receipt names live in `GUIDE_RECEIPTS` (analystScript.ts) — the single authority; screens import it.
New beats use `n`-prefixed ids (engine's `isV2NewStepId` drives the v1-upgrader release cap). The guided-regen payoff mailbox is `onboardingBus.ts` (`setPendingGuidedRegen(source)`; markers are positions ONLY for `'quickset'` — `isRegenPosition()` before forwarding to analytics).

## Trade generation pipeline v2: gen2_* namespace + GenerationReport hand-off (2026-08-16, trade_gen.v2)

`backend/trade_gen_v2.py` (flag `trade_gen.v2`, dark) sets five conventions:
- **`gen2_*` config namespace** — every tunable of the staged pipeline lives in `trade_service._DEFAULT_CFG` under a `gen2_` prefix (read through the same `_c()` accessor / model_config overlay as every other engine knob). New pipeline knobs go there, never as module constants.
- **Dual-board ε extends #108 to both sides.** `gen2_epsilon` gates BOTH sides' own-board gain on every generated package (consolidation-discounted, `trade_gen_v2.side_gain`) — the two-sided generalization of `user_gain_epsilon`. The directed `side_gain(in, out, value_of)` decomposition is the unit a future 3-team-cycle layer reuses; don't collapse it into a pairwise-only formula.
- **`GenerationReport` is the generation→telemetry interface.** The pipeline owns NO tables: per-suggestion health metrics ride `card.health` (never serialized) and batch health + per-team exposure counts ride the returned `GenerationReport` (also logged as one JSON line, logger `backend.trade_gen_v2`). The suggestion-telemetry layer (own branch) persists from that object — schema decisions belong to that thread.
- **A pass that rewrites a card's assets belongs in `_pair_survivors`, and must rebuild the whole `_Candidate`.** (2026-08-21, [D-145](DECISIONS.md).) The gap sweetener is the worked example: the absolute gap it acts on is only computable from `_consensus_packages`, which `generate_league_suggestions` calls at card-build time — but TEN downstream values are derived from the `_Candidate` before that point (`_dedup_batch`'s exact/bucket/jaccard keys, `_meso_variants`, `_rationale`, `classify_package_shape` — whose `"consolidation"` label is literally `len(ids) == 1` — `card.health`'s seven entries, `mismatch_score`, `fairness_score`, `composite_score`, and the Stage 6/7 exposure + tier ranking). Mutating ids at the card-build site leaves every one of them describing a trade that is no longer being offered. This is the general shape of the v3 stale-`fit_premium` defect, and arm C's surface for it is the largest in the codebase. Two corollaries: **(a)** re-earn the gate stack via an `extra_ok_fn` that touches no `report` counter — a sweetened combo that fails a gate is not a rejected candidate, it is a candidate that ships unsweetened — and re-test `past_decision_keys`, since the rewritten combo is a different trade with a different key that the enumeration never saw; **(b)** arm C is the only generator with `_dedup_batch` downstream, and its bucket key contains the give×receive SHAPE, so a pass that changes a card's shape CAN shrink the deck by evicting a bucket occupant. Invariants asserted by the other generators ("never shrinks the deck") do not transfer here — re-verify them rather than inheriting them.
- **Pruned pools have two layers, and only one of them binds a rewriting pass.** (2026-08-21, [D-146](DECISIONS.md).) When handing a candidate universe to a helper like `trade_optimizer.close_value_gap`, separate the **semantic** pools (`user_assets` = ranked on both boards and not untouchable; `extras_all` = divergence-positive and not not-interested — these encode real rules, and crossing one produces an asset the engine could never legitimately trade) from the **enumeration-budget** slices (`[:gen2_give_pool]`, `[:gen2_recv_extra_pool]`, `gen2_centerpiece_top_k` — documented as bounding search breadth, never output length). Pass the semantic universe; reaching past a budget slice is not the pool-containment defect that `49c1d76` fixed, which crossed a *user instruction* (a #174 pinned give job smuggling in an unpinned player). Confusing the two layers makes the pass a measured no-op: wired to arm C's budget slices, 78 of 112 rejected equalizers were undershoot rather than gate kills.

Additive `TradeCard` fields `rationale` / `meso_variants` / `health` are stamped ONLY by this pipeline; every other path leaves them `None` and `trade_card_to_dict` omits them (flag-off payloads byte-identical). `health` is deliberately never serialized.

## Presentment rules: construction-gate vs presentment-filter layering (2026-08-16, trade.presentment_rules)

G6 ([D-062](DECISIONS.md)) sets three conventions for anything joining the serve-or-don't-serve decision:

- **Two layers, two hook kinds.** Package-quality rules (R1 overpay / R2 pos-net / R3 pick-gap and the R5 need gate) are **construction gates**: module-level predicates in `trade_service.py` (beside `filler_ok`/`pick_swap_ok`), bound once per job into a `presentment_ok_fn` threaded to every v1 generator (v3 loop + `_try_sweeten` re-validation, v2 `_consider`, consensus `_emit`), sitting after `filler_ok` and BEFORE feasibility/surplus/fairness so a killed candidate refills from the enumeration and can never be sweetener-rescued. Per-user duplicate state (R4 windowless awaiting/matched exclusion) is a **presentment filter** at `_dedup_and_sort` + the likes-you injector — the same candidate is fine tomorrow once the match resolves. New "never show this" logic must pick one of these two homes; post-hoc deck filtering converts kills into holes and is the rejected shape.
- **The never-relaxed list grows.** The #189 relaxed pass never loosens R1/R2/R3/R5 (alongside the #108 gates + untouchables — safety properties, not taste); its stage overrides may only touch fairness/surplus knobs.
- **Windowless exclusion-set pattern.** Per-job, league-scoped `(frozenset(give), frozenset(receive))` sets are built server-side (`_load_presentment_exclusions`), passed as a `generate_trades` kwarg with **overwrite-per-call** semantics (`None` ⇒ empty — never keep-previous: the TradeService instance serves multiple leagues). Server-derived job facts (like the R-5b `bypass_need_gate`) are computed in `_run_trade_job` from job fields, never read from the request body.
## Synthesized cards carry the gates of the surface that shows them (2026-08-19, D-096)

The likes-you injector (`server._inject_likes_you_cards_impl`) synthesizes `TradeCard`s **after** every generator has returned, so it sits outside the `presentment_ok_fn` construction-gate seam above. Q-G6-1 originally gave it "exactly R4 dedup, none of the quality rules"; [D-096](DECISIONS.md) reversed that. Three conventions come out of it, for any future path that mints or boosts a card outside the generators:

- **A gate is measured in the units the user reads.** D-055's floor was measured on **raw summed** values while the mobile `TradeValueBar` renders **package-adjusted** ones, and the two diverge by the depth discount and the crown credit in `package_value_v2`. A −500 floor therefore shipped a −6,019 card. The injector now computes `_consensus_packages` ONCE, gates on that delta, and hands the same two numbers to `TradeCard.give_value`/`receive_value` — the gate and the bar cannot disagree by construction. Any new numeric floor states which value space it is in.
- **Symmetric gates get re-derived, not copied, for an evidence-backed surface.** R1 `overpay_ok` is a symmetric credibility bound, correct on a *predicted* card. A likes-you mirror is *observed* — the counterparty already liked this exact package — so the user-favourable half of R1 kills the best cards the surface can produce (measured: 58 of the 83 floor survivors, all user-favourable). It is therefore run **directionally**, honoured only when the viewer is the heavier side. The predicate itself is imported unmodified; the direction check lives at the call site.
- **Reasoned exclusions are pinned, not implied.** `filler_ok` runs (consensus accessor on both board arguments — the injector holds no personal board). R2/R3/R5 and a fairness threshold do not, each for a stated reason in `_likes_you_presentment_ok`'s docstring, with `test_r2_r3_r5_are_deliberately_not_run` standing guard so a future "run everything" sweep has to argue with a test.
- **Failing a gate costs no cap slot, and never deletes an existing card.** A below-floor like is skipped without consuming one of the 3 `_LIKES_YOU_CAP` slots; an *existing* generated card that fails keeps its organic deck position and loses only the flag and the position-1 boost. Deck holes are still the rejected shape.

## Bake-off attribution + hygiene seams (2026-08-18, trade.bakeoff)

`backend/bakeoff_runner.py` ([plan](../docs/plans/three-model-bakeoff/PLAN.md), [scope](../docs/plans/three-model-bakeoff/scope-phase3.md), [composition](../docs/plans/three-model-bakeoff/scope-composition.md)) sets the conventions for anything that runs models side by side:

- **A generator arm is a config context, not a code branch.** Arm `baseline` is the live engine inside `_cfg_override(MODEL_A_PROFILE)` plus a thread-local R4 bypass; there is no forked engine and no duplicated enumeration. Arms run **sequentially on the job's own daemon thread** — the seam is a `threading.local()`, so a sibling thread would silently read live defaults. Never parallelise the arms without giving each thread its own context first.
- **A flag that gates a serving path is not a module guard.** `trade_gen.v2` decides whether `_generate_trades_impl` ROUTES a deck through the v2 pipeline; the bake-off calls `trade_gen_v2.generate_league_suggestions` directly as a third generator with that flag false. Read a flag's docstring for what it gates before assuming a module is unreachable while it is off.
- **Attribution columns are written on EVERY row of a batch, never conditionally.** `save_deck_impressions` inserts with `executemany`, which compiles the statement from the FIRST row's keys — a deck led by an unattributed card (a likes-you injection) would otherwise drop `model_arm` / `arm_rank` for the whole deck, silently. Any future per-card nullable column on this spine follows the same rule.
- **Record the gate a row passed, never the gate that was requested.** `fairness_threshold` arrived per-request from the client and was persisted nowhere, while the engine composed it per card (divergence floor, relaxed band) — so the recorded intent and the applied bar were different numbers, and the applied one was unrecoverable. Any request-scoped parameter that a generator then transforms is stored **as applied, per row**, resolved against the config that row's producer ran under. Corollary: the config itself is snapshotted with the run, because `model_config` has no `updated_at`.
- **A deck built to compare things is composed of the comparison units, and those units are what interleave.** (2026-08-18, [scope-composition](../docs/plans/three-model-bakeoff/scope-composition.md).) The served bake-off deck is three **groups** — (arm, basis) pairs quota'd five value / five outlook — and the groups, not the arms, are the team-draft participants, because arm `current` holds two of the three and a per-arm rotation would push arm `gen_v2` into the deck's tail (measured: mean position 24.5 of 30 vs 14.5). Corollary for anything similar: interleave at the granularity you intend to compare at, and assert the position distribution over many decks rather than inspecting one.
- **A quota that cannot be filled is recorded, never silently substituted.** The per-(group, lane) shortfall lands in `bakeoff_runs.groups_json[key].short` and the default fill policy leaves the slot empty — "can this generator produce this kind of idea at all" is the finding, and a backfill erases it while leaving the deck looking full. When a substitute IS allowed (`bakeoff_fill_policy` = 1) it is flagged per card (`deck_impressions.lane_slot = 'fill'`) and the shortfall is still recorded.
- **A classification's absent value is its own bucket, never folded into a neighbour.** `TradeCard.lane` is None precisely when the outlook axis is *undefined* for that deck (no window direction, or `trade.lanes` off) — not when the card is value-shaped — so it fills neither quota. And when a whole population is unclassified the quota goes **inert** rather than emptying the deck: quota'ing on an axis that does not exist is both a measurement artefact and, in Phase 5, real user harm.
- **Comparing generators means giving them identical post-generation treatment.** `bakeoff_runner.gen_v2_cards` now applies the #172 intent filter and `classify_lane` to arm C's output, because `_generate_trades_impl`'s v2 branch does and calling the module directly skipped both. A missing presentment step reads as a model property: an unlabelled arm C would have under-filled its outlook quota 100% of the time and looked like an arm that cannot produce outlook ideas. Before adding an arm that bypasses a wrapper, diff what that wrapper does to the cards on the way out.
- **Record the gate a row passed** (above) generalises past `fairness_threshold`: `trade_intent` gets the same treatment, because `_generate_trades_impl` resolves the request to `None` whenever `trades.intent_modes` is off and the route already drops out-of-vocabulary values — so the requested and effective values genuinely differ, again.
- **A generator that produced nothing records the STAGE it died at, not just the count.** (2026-08-19, [D-087](DECISIONS.md), [scope](../docs/plans/three-model-bakeoff/scope-arm-c-diagnostics.md).) `GenerationReport.kill_counts()` emits the whole `trade_gen_v2` pipeline in order — `S0` supply, `S1` selection, `S2` enumeration, `S3a-d` the hard gates, `S4`/`S6` — plus a `starvation_reason` that is non-null **only when nothing was ever enumerated**, and it lands on `bakeoff_runs.arms_json[arm].diagnostics`. The convention it encodes: *starved* (no input reached the gates) and *gated* (input reached a gate and died) are different findings with different fixes, and a bare `cards: 0` cannot tell them apart — arm C's zeros were read as a broken generator for a day when they were a property of leagues with no boarded opponent. Model this on `TradeService.presentment_kill_counts()`: one flat dict of counters a query reads without parsing prose. Corollary: **count the early `return []`s too** — the two starvation exits in `_pair_survivors` were bare returns, which is exactly why three different causes produced byte-identical all-zero reports. Second corollary: when an arm looks broken, **find the control** — arm `current`'s divergence pool was also 0 in the same leagues, which is what proved the zero was supply and not the pipeline.

- **Telemetry keyed by participant must be keyed by the SAME participant the producer used.** `BakeoffRun.run_row` read `draft.forfeits.get(arm)` against a dict the composed draft keys by GROUP, so arm `current` — whose groups are `current_divergence` + `current_consensus` — recorded a flat `0` in every run ever written, while arm C's single-group key coincidentally matched and looked like the only arm that forfeits. `forfeits_for_arm()` now sums over an arm's groups. When a refactor changes what the participants ARE (D-078 moved them from arms to groups), grep every reader of the participant-keyed structure — a `.get(k, 0)` default turns the mismatch into a plausible number instead of an error.

- **Measurement hygiene lives in a predicate, not in reviewer discipline.** `elo_freeze_mult()` (swipe K → 0 while the bake-off runs) and `bypass_rerankers()` (no post-generation layer may reorder an interleaved deck) are single functions with tests, because both failures are invisible: contaminated Elo and a re-ranked deck both produce plausible numbers. A new post-generation layer must consult `bypass_rerankers()`; a new swipe path must apply `elo_freeze_mult()` (a structural test scans `server.py` for the second one).

## Mock-draft ownership honesty: resolver-owned labels (2026-08-16, #328)

Create-time resolution owns ownership honesty. The server resolvers
(`server._mock_real_draft`, `server._mock_owned_pick_overlay`, the create
route's MFL step) are the ONLY places an `ownership_source` label is chosen,
and **the resolver that drops an overlay degrades the label at the same
site** — identity drop-all → `none`, partial drop / coverage hole →
`partial`, round-1 order hole → `none`. The engine
(`mock_draft_service.py`) stays I/O-free: it carries the label
(`build_settings` kwarg, coerced closed-vocabulary), degrades it in exactly
one place (the §14-2 short-order branch, where the overlay itself is
dropped), and echoes it via `.get` (pre-#328 rows read `null` — the #305
pre-mode convention; no backfill ever). New resolution sources must ship
their own label decision with the resolution — never a post-hoc inference
from the resolved data. Vocabulary + client contract:
`docs/cross-client-invariants.md` § Mock-draft ownership source.
## Finder preselection contract now carries opponent + auto-run intent (2026-08-16, #330)

The finder preselection contract (store `useFinderTargets`, never route params — #300) now also carries the scoped opponent and a one-shot auto-run intent: `handoff: {opponent {userId,name}, autoRun, seq} | null`, seq store-stamped monotonic (a same-team repeat handoff must still re-fire TradesScreen's choke-point effect, whose deps gain the consumed `autoRunSeq`). Consumed on focus, exactly once; `clear()`/league-switch GC it. Pinned by `mobile/tests/check-offer-prefill-330.js` + `-unit.js`.

## Ranking vs gate: what a term may judge (2026-08-18, engine-quality)

The 2026-08-18 wave ([scope](../docs/plans/engine-quality/scope.md)) sets one convention for anything that touches the composite:

- **A gate judges the REAL package; a ranking term may judge only the divergence-bearing content.** A gate answers "may this be served?", so it prices every asset actually in the trade — a draft pick genuinely transfers value and can genuinely make an unfair trade fair. A ranking term answers "is this a better idea than that one?", and the composite's subject is MUTUAL GAIN, so an asset both boards price identically carries nothing to rank on. Concretely: `_fairness` / `_fairness_v3` still gate and still stamp `fairness_score` on the card; `rank_fairness` re-prices the same ratio on the **signal core** for the composite only. New scoring work picks one of these two roles explicitly — a term that silently does both is how a zero-information asset bought score for a whole quarter of the live deck.
- **Zero-information assets are DROPPED from a ranking package, never zero-weighted.** `package_value_v2`'s 'heavy' crown premium branches on `len(values) < n_other`, so a zero-VALUED asset still changes the asset count and can still move the ratio. Dropping makes the invariance exact in every stud-tax mode.
- **A change that creates ties owns them.** Pricing on the core makes a package and its zero-divergence-padded sibling score identically; the v2 heap's pre-existing tie-break was `_tb` descending (later-enumerated wins) and 1-for-1s enumerate first, so the bare deal lost every tie it now made. The tie-break moved under the same knob that creates the ties, so the kill value reverts both halves together.
- **Per-rule knobs, not a group flag.** Each of the five changes carries its own `model_config` key whose disable value restores byte-identical prior behaviour (proven against `origin/main` goldens in `test_engine_quality_golden.py`). Same convention as the G6 presentment knobs; a shared flag would make the changes un-revertible independently.
- **Deck-wide constraints belong at deck assembly.** The headliner cap lives in `_dedup_and_sort`, alongside the R4 exclusion, not inside a per-pair generator: a constraint on the SERVED SET has to see the served set, and streaming snapshots re-derive it from the same accumulating list for free.


---

## Presentation surfaces: parity-by-reuse, and the entry-by-optional-prop flag gate (2026-08-18, trades.presentation_v2)

The presentation-v2 build ([scope](../docs/plans/trade-presentation-v2/scope.md)) is the first case of a SECOND client surface rendering the same deck as an existing one. Three conventions come out of it, and they generalise to any future alternative presentation.

- **A second surface over an existing feed reuses the instrumentation spine by IMPORTING it, never by re-implementing it.** `mobile/src/hooks/usePresentationSignals.ts` calls the very same `swipeTrade(card, decision, signal)` and `postDeclineReason(...)` the deck calls, imports `SwipeSignal` as a type rather than redeclaring it, and emits the same event NAMES with the same property sets. This is not tidiness: the deck-impressions → outcomes → re-ranker programme (Thompson, taste, fatigue, the bake-off) treats those rows as one population, and a surface that wrote a parallel shape would fork every downstream estimator silently — nothing would break until someone queried it months later. Where a constant genuinely had to be duplicated (`VIEWED_MIN_MS`, `DWELL_CAP_MS` are module-private on `TradesScreen`), the guard asserts the two literals against each other so a change on either side fails CI instead of drifting.
- **Corollary, and the part that is easy to miss:** two surfaces emitting identical events are *indistinguishable in analysis*. Parity buys comparability and costs attributability. A surface-discriminating property (`surface: 'deck' | 'presentation_v2'`) is a taxonomy change, so it was not added unilaterally — but **no second surface may be flipped on for real users until it exists**, or its traffic is unattributable in every query.
- **A second surface must land in the SAME server job-cache slot as the first.** `_trade_job_is_fresh` keys on `fairness_threshold`, so the new surface resolves it through the shared `fairnessOnFromPref` / `fairnessThresholdFor` helpers rather than deriving its own, and never sends `force`. A locally-derived threshold would kick a second full generation AND serve a different card set — and therefore a different set of impressions — to the same user in the same session.
- **A flag gates an entry point by CONTROLLING WHETHER A HANDLER IS PASSED, not by wrapping JSX in a conditional at the leaf.** `TradeFinderModeBar`'s `onDraft?` set the precedent; `onTodaysTrade?` follows it, and `TradeHomeUtilityRow` mirrors it. The host passes `undefined` when the flag is off and the component builds its control list *from the handler's presence*, so flag-off is byte-identical by construction rather than by inspection. The failure this shape prevents is specific and plausible: a "simplification" that renders the control unconditionally and no-ops the callback typechecks, compiles, and ships a new tab to every user. Routes still register unconditionally — the flag gates the entry, not the navigator entry.
- **Presentation derivations live in a pure `utils/` module, not in the screen.** `mobile/src/utils/tradePresentation.ts` holds every rule the design actually encodes (band derivation, the range-band geometry, the ≤3-bullet asymmetry, the deck partition, the empty-state copy) as total functions with no React, no state and no network, so the structural guard can transpile and RUN them. Design laws asserted on executed behaviour ("no band label contains a digit", "the fairness band exposes no winner", "no hero when nothing is endorsable") are the kind that a JSX grep can only pretend to check.

---

## Placements vs comparisons: assertion and sample are different inputs (2026-08-19, D-085)

The placement tier clamp ([scope](../docs/plans/placement-tier-clamp/scope.md)) establishes a convention for anything that reads a user's board.

- **A comparison is a SAMPLE; a placement is an ASSERTION. Do not feed one into a mechanism built for the other.** Confidence shrinkage (`_shrink_user_elo`, `w = n/(n + shrink_pseudocount)`) is a sampling estimator: `n` counts comparisons that moved a player's Elo, and the whole point is that a thinly-sampled opinion should not be trusted over consensus. A tier save / drag-reorder is not a thin sample — it is a direct statement of value — so it does not belong in `n` (the rejected "pseudo-count bonus" option) and it does not license discarding the estimator either (the rejected `w = 1`). It belongs as a **bound on the estimator's output**. New work that wants to honour a placement should ask "what does this constrain?", not "how many votes is it worth?".
- **One derivation, two consumers, one function.** `ranking_service._placement_bands` computes "the tier the user placed him in" exactly once; `_pin_bounds` (how VOTING may move a placed player, `pin_tier_bounded`) and `placement_bands` (how the ENGINE may price him, `placement_tier_clamp`) both call it. Two copies of a tier lookup drift the moment one of them is tuned, and the resulting inconsistency — voting bounded to a tier while pricing was not — is the defect D-085 exists to close.
- **A bound on a valuation is applied AFTER the blend, never in place of it.** That ordering is what keeps a mistake correctable: the user's own later votes still move the value inside the band, and the bound's displacement decays to exactly zero once the estimator lands back inside on its own. A bound applied *instead of* the estimator is a freeze, and a freeze cannot be argued out of.
- **The knob decides whether a placement map is consulted, not whether it is built.** `placement_bands()` is computed off the `RankingService` unconditionally and the kill switch lives at the point of use in `_shrink_user_elo`. This keeps the disable path a pure identity on the valuation (nothing upstream changes shape) and keeps the map available to any future consumer without re-plumbing.
- **This convention does NOT extend to gates.** Per [Ranking vs gate](#ranking-vs-gate-what-a-term-may-judge-2026-08-18-engine-quality), a gate prices the real package on real consensus values. The clamp touches only the personal-valuation path, and `_value_uncertainty` — which feeds the range-overlap fairness gate — is deliberately left placement-blind, asserted via `inspect.signature` so adding a parameter fails CI. Wanting a gate to respect placements is an operator decision, not an implementation detail.

---

## Settings tree: one route, two components, per-page query ownership (2026-08-19, account.settings_hub)

The Settings surface moved from one 1,712-line screen to a tree under `mobile/src/screens/settings/`
([plan](../docs/plans/settings-ia-hub/plan.md)). Four conventions come out of it:

- **A flag that changes what a screen FETCHES branches at the route, not inside the screen.** `Settings`
  is one route mounting one of two components via the `SettingsRoute` wrapper in `RootNav.tsx`. A branch
  *inside* `SettingsScreen` would not have worked: its six `useQuery` calls and two `useEffect` fetches
  are hooks at the top of the body, so the flag-on path would still pay the entire network cost, and an
  early return placed above them makes every later hook conditional. Mount one component or the other
  when the point of the flag is what the screen costs.
- **A page owns the queries for the rows it renders.** Each module under `screens/settings/sections/`
  fetches its own data; no settings page hoists another page's state. The rule this replaces is why
  opening Settings to switch a league waited on `GET /api/notifications/prefs` — one screen owned every
  query, and one full-screen `isLoading` gate blanked all of them.
- **A section renders its own in-flow placeholder; a screen never renders a full-screen spinner for one
  section's data.** A full-screen gate makes the slowest query the cost of the whole surface.
- **A summary/preview value is rendered only if it is free, and never guessed.** A hub row's preview
  reads the session store or a resident React Query cache entry via `getQueryData` (non-reactive, never
  fetches). If neither has it, the subtitle is omitted, or an honest-empty string is rendered in a
  visibly distinct style. Concretely: the Trade values row has NO preview, because stud tax and pick
  pricing are fetched by bare effects with no query key — rendering them would print the code default as
  if it were the user's stored setting. A settings surface that states a setting wrongly is worse than
  one that stays quiet.

Route naming: `Settings` is the hub/root; second-level routes are `Settings<Group>`
(`SettingsLeagues`, `SettingsRanking`, `SettingsTradeValues`, `SettingsNotifications`, `SettingsAccount`,
`SettingsAbout`, `SettingsTesting`), each URL-addressable at `settings/<kebab-slug>` in
`utils/deepLinks.ts`. All register unconditionally — the flag gates the entry row, not the route.

---

## Derived league state belongs to the writer, not the reader (2026-08-19, D-091)

#355 (phantom 2029 picks) turned up a convention that was never written down. Three parts:

- **A row that should not exist is a WRITER bug, and is fixed at the writer.** The serving path for
  draft picks has no season predicate anywhere — `load_draft_picks` (`backend/database.py`) selects
  every row for a league and uses `season` only as a sort key, and `_inject_owned_picks`
  (`backend/server.py`) puts each pick onto team rosters, after which all three engines pick it up
  implicitly because they build their pools *off rosters*. So a filter added at presentation would
  have hidden the pick while still letting it consume generation work and distort every score
  computed over the pool. **New invariant:** a `draft_picks` row's `season` must lie inside the
  league's derived horizon (`draft_status.pick_horizon`), and that is enforced in
  `sync_draft_picks`, not in any reader.
- **A window over league state is anchored to the state, not measured from "now".** The defect was a
  constant (`seasons_ahead = 3` from `current_season`) standing in for a fact that rolls: how many
  draft classes a league carries depends on whether its current class has been drafted. Prefer a
  derived anchor over an offset whenever the underlying thing advances on its own schedule. The
  same bug shape is latent anywhere a "next N seasons" constant exists.
- **Replace-syncs make write-side fixes self-healing in BOTH directions, which is what lets one flag
  be a complete rollback.** `sync_draft_picks` ends in `replace_draft_picks` (delete + bulk-insert
  per league), so stale rows vanish on the next sync and flipping `picks.league_horizon` off
  rebuilds them. A write-side fix behind a flag on a replace-sync needs **no migration and no
  backfill**; a flag on an append-only writer would have needed both, and its "off" state would not
  have been a true restore. Check which of the two you have before calling a flag a kill switch.

## Derived display coordinates: store the ORDER, never the SLOT (2026-08-19, D-090)

A draft pick's slot ("1.08") is a **derived coordinate**: a pure function of the pick's original roster
and the league's draft order. [D-090](DECISIONS.md) makes it visible on owned-pick labels, and the
conventions that fall out generalise past picks.

- **Persist the INPUT that changes rarely, derive the coordinate that changes with it.** The order goes
  on the league (`leagues.draft_slot_order` for Sleeper, `leagues.pick_assignment_settings` for a
  user-assigned board); the slot is computed at read time and never written. A denormalized
  `draft_picks.slot` would go stale on every commissioner reorder, and `draft_picks`' grain
  (`league, season, round, original_roster`) cannot express one — the D18 rule
  `PickAssignmentScreen.tsx:146-152` already states client-side. **If a value can be recomputed from a
  stored input in microseconds, storing it buys nothing and costs a consistency invariant.**
- **A derivation that cannot be made honestly returns `None`, and `None` renders the pre-existing
  string.** `pick_slots.slot_for` has five refusals (unset order, wrong season, unknown roster, slot
  wider than the league, snake with `reversal_round`), and every one degrades to the round ordinal. The
  shape to copy: the *absence* of a resolution is a first-class return value, not an exception and never
  a fallback guess. `draft_board_service`'s `order_confidence` and `_pick_no` are the same pattern.
- **Bind data a caller already fetched instead of re-fetching it.** `_sync_sleeper_owned_picks` was
  already calling `GET /v1/league/<id>/drafts` for the #228 exclusion and already held the
  `roster_id -> user_id` map; the resolver reuses both, so the feature adds **zero** upstream calls.
  Before adding an integration read for a display value, check what the surrounding function already has
  in hand.
- **Resolve once per league, pass down; never look up inside a per-row formatter.**
  `_owned_pick_label(p, slot_order=None)` takes the order as an argument. Each of its five call sites
  calls `_league_slot_order(league_id)` once and threads the result through the loop, because the label
  runs per pick and a 192-slot grid would otherwise do 192 lookups. The optional-argument-defaulting-to-
  `None` shape is also what keeps the function byte-identical for any caller that does not pass it.
- **A display flag short-circuits BEFORE its data read, not after.** `_league_slot_order` returns `None`
  on the disabled flag before touching the DB, so a killed feature costs nothing rather than costing a
  read whose result is discarded. Pinned by `test_flag_off_never_reads_the_order`.
- **A numbering read is not an engine read.** `_assigned_slot_order` names a LITERAL `PICK_SOURCE_ANY`
  rather than `_pick_read_source()`, and is registered in `test_pick_assignment.py`'s
  `_SANCTIONED_SOURCE_CALLERS` rather than its seven engine sites — because what "1.05" means must not
  change when a *pricing* flag moves, or a trade card and the assignment screen would disagree about the
  same slot.

## Predicting a user's own vocabulary: objection codes, uniform-key stamps, narration-gated payloads (2026-08-21, D-142)

`backend/trade_breaker.py` ([plan suite](../docs/plans/counterparty-breaker/), [D-142](DECISIONS.md)) sets three
conventions for any future layer that **predicts something a user will later tell us directly**, or that rides
`features_json` and shows part of itself on a card.

- **A prediction is expressed in the vocabulary the answer will arrive in, and every code names its producer.**
  The breaker's objection codes ARE `database.PASS_REASON_LAYER2` — imported, never copied — so "predicted
  objection" ⨝ "filed pass reason" is a join on `impression_id` and the feature needs **zero new
  instrumentation**. Two rules keep the shared enum honest once more than one thing writes it: every code
  carries a **producer column** (who may emit it), so a sibling plan's code appearing in a breaker payload is a
  test failure rather than a curiosity (`test_breaker_vocabulary_closure`); and a code with **no filed-reason
  anchor** — the one registered extension `roster_crunch` — is declared unmeasurable up front instead of being
  hand-coded against free text later. `other_text` is unmatched by construction and leaves every precision
  denominator. The same closure rule extends past the codes to the **evidence keys**: each code has a closed
  key enum, because an unlisted key is how private partner state leaks past a copy whitelist.
- **A `features_json` key obeys uniform-keys, and its "nothing here" value is a marker object, never a bare
  null.** `save_deck_impressions` compiles its `executemany` from the **first row's keys**, so a key written
  conditionally is dropped for the whole deck, silently. The breaker's copy therefore sits *outside* the
  bake-off guard (organic decks stamp too) and is **attribute-gated, not flag-gated** — a hot flag flip
  mid-job must not let the log site see a state the stamp site never saw, and the copy loop has no per-row
  try/except, so one `AttributeError` would lose an entire deck's impressions including other features' keys.
  Three shapes fall out and generalise: a fresh module-level **sentinel** (`_BK_SENTINEL`, never `None`)
  distinguishes "no attribute" from "stamped null"; every degraded path stamps a labeled minimal marker
  `{ver, degraded, objections: null}` so *why* a row is unscored survives into the corpus and readouts can
  subtract it from coverage; and the synthetic marker written at log time carries `ver: null` **by
  construction**, because at that point the module may never have been imported and no version literal can
  honestly be claimed. Corollary: the failure ladder's outermost rung is constructed with **no module
  reference and no knob read at all** — the import itself may be what failed, and a live knob read at failure
  time would break the one-job-one-knob-state rule anyway.
- **Payload presence is the client gate — narration-gated serialization.** `trade_card_to_dict` emits the
  `breaker` object **only for a card that actually narrated**, and emits three fields of it. During the
  dark-stamp window (compute flag on, narrative flag off) the payload carries no breaker key whatsoever, so:
  the client re-checks no flag and cannot drift from the server's eligibility rules; a class that is scored
  but permanently un-narratable (`other_player_keep` — it would advertise that we read the partner's private
  keep-list) cannot reach a client even as inspectable structured data; and the viewer-seat shadow stamp never
  serializes anywhere. The general rule: **when eligibility is a server-side policy, ship the eligible result
  or ship nothing — never ship the data plus a flag and trust every client to re-implement the policy.** The
  structural guard (`mobile/tests/check-breaker-card.js`) pins the client half — gated on
  `data.breaker?.sentence`, renders the sentence verbatim, switches on no code.
- **One job, one knob state; one call, one pin.** All 25 `breaker_*` knobs plus every engine knob the layer
  reads (`waiver_slot_cost`) are resolved **once** into a frozen per-call snapshot, so a `PUT
  /api/admin/config` landing mid-job cannot produce a deck scored under two configs. Knobs are read through
  the **module** (`ts._c`), never rebound at import, so a monkeypatched knob moves the next call's verdicts —
  the T1 discipline, sabotage-proven. And any layer that values assets outside the generator pins the
  ambient valuation mode explicitly (`ts.stud_tax_override("market")`), because a thread-local left unset is
  a silent dependency on whoever ran before you.

## Consulting a leaf from inside an engine: live module bindings, one kwarg, copy-at-log (2026-08-22, D-147)

`backend/negmem.py` ([plan suite](../docs/plans/negative-results-memory/),
[ADR-015](../docs/adr/adr-015-negmem-soft-prior-not-fourth-filter.md), [D-147](DECISIONS.md)) sets four
conventions for any future **leaf that the generators consult**, as opposed to `trade_breaker.py`'s leaf that
reads the finished deck. The difference matters: a consulted leaf runs *inside* the thing under test, so its
plumbing has to be provably inert when off.

- **T1 — a seam holds a live MODULE binding, never a value import.** Every seam writes `from . import negmem as
  _negmem` and calls `_negmem.effective_mult(...)`. `from .negmem import effective_mult` freezes the binding at
  import time, which silently defeats monkeypatch-based tests and, worse, defeats them *quietly* — the test
  passes, asserting nothing. The rule is enforced two ways rather than trusted: an AST scan over all four seam
  files rejects any `ImportFrom` of the module, and a behavioural test rebinds `negmem.effective_mult` and
  asserts the engines' output actually changes. This is the same trap that produced a measured no-op in the
  2026-08-19 arm-B audit.
- **One kwarg, one dict, no instance slot.** The job's map is threaded as a plain keyword argument, read **once**
  into a call-local, and — where a dict of generator kwargs already exists — assigned as exactly **one key** in
  that one dict. No `self._negmem`: a per-call value that lives on the service can be inherited by the next
  call, and the overwrite-per-call semantics would have to be re-established at every entry point. Because the
  dict is both splatted into the normal generator and handed whole to the relaxed re-run, the relaxed pass
  consults the same map at the same strength with **no special case** — and there is no duplicate-keyword
  hazard, because there is only ever one assignment.
- **The asymmetry between "always passed" and "conditionally spliced" is deliberate, and is a test.** `negmem_map=`
  rides **unconditionally**, carrying `None` when the feature is off, because every seam guards on the *value*
  (`is not None`), never on the kwarg's presence. The M2 feed (`acceptance_stats`) is spliced in **only** when a
  map exists — `**({...} if nm is not None else {})` — and that splat is what makes the flag-off call
  byte-identical. Tidying the two into one form breaks one half or the other, so both call sites assert the
  shape. The general rule: **when a call must be byte-identical while off, say in the code which arguments are
  load-bearing for that identity, and pin it with a test rather than a comment.**
- **A stamp written at log time is a COPY of what the consult site decided — it never recomputes.** By logging
  time every bake-off arm's config overlay has exited, so a recompute at assembly would stamp arm-A rows with the
  *live* arm's multiplier: the provenance would be plausible and wrong. The assembly block therefore contains no
  call into the leaf and no knob read at all, and the recompute is a named sabotage in the suite. Generalises to:
  **any value that depends on a scoped context must be captured inside that scope and carried, never re-derived
  downstream.**
- **Corollary — where a multiplier lands decides whether it changes membership.** The same multiplier applied to
  a candidate's internal score changes what survives selection; applied to the emitted card's published score it
  changes only order. Where the effect is meant to be ordering-only, the multiplication also has to land on the
  correct side of any quantization — inside the rounding that collapses float noise, not after it — or the
  deterministic tie-break loses to the noise the rounding exists to erase.
## Retiring a per-user setting: 410 the write, fix the read (2026-08-21, D-146)

The operator deleted a setting — pick pricing — rather than changing its default. This repo had **no
precedent for retiring a route**: `git grep "410" backend/server.py` returned nothing before this change.
The shape chosen, and the reasoning, so the next one does not have to re-derive it:

- **The write verb answers 410 Gone, not 404.** A 404 is what the route already meant last week (it 404d
  while its flag was dark), so reusing it says "wrong URL / not deployed yet" to a client that is actually
  looking at a resource that existed and was deliberately withdrawn. The body names the replacement state
  (`{error: "gone", message, mode}`), so a human reading a log learns the answer without opening the code.
  Body validation is **removed, not kept**: a once-valid mode and a garbage mode get the same 410, because
  there is nothing left to validate against and a 400 would imply some body would work.
- **The read verb keeps answering, with the FIXED state — never the stored column.** Builds in the field
  still call GET on screen open. Serving `{mode: "market_slots", retired: true}` makes an old build render
  the honest answer; serving the dead `users.pick_pricing_mode` would tell it the setting still means
  something, and 404ing would make the shipped client hide the control as though the feature were dark.
  The extra `retired: true` key is additive and costs an old client nothing.
- **Auth posture does not change.** Retirement is not a reason to make a route public; `_require_session()`
  still runs first on both verbs, so a caller without a session still gets 401 before it gets 410.
- **The column is not dropped, and the flag is not deleted.** Additive-schema rule for the column
  (`users.pick_pricing_mode` becomes dead data); for the flag, `trade.slot_pricing` stays in `FLAG_KEYS` at
  `true` and is simply never read — deleting it would force a six-file change to satisfy
  `test_release_flags_mirror_features_json`, make the key vanish from `/api/feature-flags` for shipped
  builds, and reinterpret any stored override row as an unknown key.
- **The client is deleted, not flag-hidden.** The Settings row, its state, its fetch, its optimistic PUT and
  its analytics emitter all go. What stays behind is an **absence assertion** in the structural suite
  (`check-settings-testids.js` `DELETED_PREFIXES`), so a well-meaning revert that re-adds the control fails
  loudly instead of quietly restoring a setting the operator removed. The analytics EVENT stays registered
  in the taxonomy so historical rows remain queryable — retire the emitter, never the name.

## Pricing waterfalls: resolve once per scope, pass down, fall soft (2026-08-21, D-146)

Per-slot pick pricing needed a per-league fact (the resolved draft order) inside a per-pick function.
The shape that worked, and generalises to any read-time enrichment:

- **Resolve at the widest scope that owns the fact, pass the narrow value down.** The order is looked
  up once per league (`server._league_slot_order`, DB-backed with a 60s cache); `pick_slots.slot_for`
  turns it into one integer per pick; `pick_values.priced_pool_value` takes that integer and resolves
  NOTHING itself. A pricing function that reached for a DB-backed lookup per pick would be correct and
  unshippable.
- **Reuse the existing resolver rather than re-deriving the rule.** `slot_for` already refuses future
  seasons, unknown rosters, malformed blobs and unverifiable snake reversals. Every one of those
  refusals is a pricing safety property now, obtained for free. A second implementation would have had
  to re-earn all four, and would drift.
- **Derive the price and the label from the same resolution.** A card that says "2026 1.03" while
  charging for a generic first is worse than one that says neither. Where a shared helper cannot yet
  take the precomputed value, say so at the call site and explain why the two agree anyway (purity +
  identical arguments) rather than leaving the reader to assume it.
- **Fall soft in named steps, and clamp in exactly one of them.** Slot price -> round curve -> stored
  value, each step returning None to mean "I have nothing honest to say". Round clamping lives only in
  the round-curve step; the per-slot step deliberately does not clamp, because a round-9 slot has no
  published row and no honest analogue. Two clamps would drift apart.
- **Prefer a fallback that falls out of the DATA over one that falls out of a BRANCH.** "Future picks
  stay default" needed no `if season > current` anywhere: DP publishes per-slot rows only for the
  current class, so the lookup misses and the waterfall does the rest. A branch encoding the same rule
  would be a second source of truth about what DP publishes.
- **When a structural guard has to widen, make it stricter in the same edit.** The guard pinning which
  functions may read DP grew a second permitted reader; it was rewritten from a source-line comparison
  to an AST reader-set equality check with a module-level-import refusal, and sabotage-verified. A
  widened guard that is not also tightened is how a bound quietly becomes decorative.
## One number, one seam: aligning surfaces that must agree (2026-08-21, D-148)

D-146 put per-slot pick pricing into the engine and left two league surfaces on the stored column.
Live, the app quoted 2117.0 and 4867.1 for the same pick on two screens. Closing that (Q-026) produced
a convention for any value multiple surfaces must agree on:

- **N surfaces that must agree get ONE named helper, not N copies of one expression.** The five pricing
  sites had been drifting because each held its own copy of `priced_pool_value(row, fmt, slot_for(...))`.
  Extracting `server._priced_pick_value` changed no behaviour at the two already-correct sites — the
  point was to make the agreement *structural* rather than a fact about today's source.
- **Guard the seam by AST, bidirectionally, and sabotage-verify both directions.** One test asserts the
  underlying function is called from exactly one place; a second asserts the seam's caller set is
  exactly the known surfaces. The first catches a new surface going around; the second catches a known
  surface quietly regressing to the raw column. Verified by applying a sabotage that is *behaviourally
  identical* (inlining the same expression) and confirming it still fails — a guard that only catches
  behaviour changes is not a structural guard.
- **The list of callers IS the documentation of "which surfaces price this".** Written as a commented
  set in the test, so adding to it is a deliberate act with a reason attached, and reviewing "what
  changed" is reading one list rather than grepping.
- **When a fallback branch exists, feed it INTO the waterfall rather than around it.** The legacy
  NULL-`pool_value` re-derivation used to short-circuit pricing. It now fills a row COPY and lets all
  three steps run, so the legacy value becomes step 3 instead of bypassing steps 1-2. The alternative
  (an early return) would have re-created the very disagreement being closed, for exactly the rows
  least likely to be noticed.
- **A per-scope lookup must be counted, not trusted.** `_league_slot_order`'s 60s cache would hide a
  per-pick lookup in production, so the test counts calls directly: 48 picks, 12 rosters, one lookup.
- **Name the time-series boundary in the same commit that creates it.** Any derived history table fed
  by a re-priced reader gets a step at the merge. That belongs in the data dictionary, the scope block
  and TEST_LEDGER — plus a test proving the writer has no pricing path of its own, so "append-only with
  a step" is verifiable rather than asserted.

## Append-only, version-stamped measurement tables (2026-08-21, D-144, `receipts_*`)

A table-family convention introduced by Receipts, worth reusing for anything that grades our
own past output.

- **The prefix owns the writer.** `receipts_*` tables are written by exactly one module
  (`backend/receipts_service.py`) and read by that module's two read surfaces. Sibling efforts
  take their own prefixes (`negmem_`, `breaker_`), so "who wrote this row" is answerable from
  the table name.
- **INSERT + SELECT helpers only.** `database.py` deliberately exposes no UPDATE or DELETE
  path for these tables, and a test greps for one. That is what makes "we can't move the
  goalposts" a mechanism rather than a promise — a correction is a `grader_version` bump plus
  a regrade, with the superseded rows retained.
- **Version suffixes are NUMERIC, and reads must sort them that way.** `receipts-10` beats
  `receipts-2`; lexicographic ordering silently pins reads to a stale version the moment a
  tenth correction ships. `receipts_service.parse_grader_version` is the one comparator.
- **The work queue is defined by ABSENCE, never by a progress marker.** "Rows with no grade at
  this `(window, grader_version)`" makes the job idempotent by construction: a crash loses at
  most one batch, a double-fire no-ops, and there is no cursor to corrupt. The corollary bites —
  *pending* states must not be persisted, because a row written for "not ready yet" would
  permanently hide that work from its own queue.
- **Denormalize the slice keys at write time.** Grade rows copy `shape_bucket` / `basis` /
  `model_arm` / `policy_version` from the impression rather than re-deriving them, so a per-cell
  read is one GROUP BY and no read-time recomputation can drift from what was frozen at serve.
- **Constants that encode honesty rules stay constants, not knobs.** The junk-for-junk midpoint
  floor, the window set, the headline window and the frozen pick weights are pinned under
  `grader_version` — a tunable pick weight would let a config write flip existing rows between
  `graded` and `pick_majority` with no regrade and no audit trail.
- **Cross-format work queues take the UNION and skip in-loop.** Where a predicate depends on
  per-format data (here, snapshot coverage), build the queue from the union across formats and
  skip rows whose own format has not resolved — *without* consuming the batch cap. Folding
  resolvability into the WHERE is what stops a head-of-queue block of unresolvable rows
  starving every run.

---

## The opponent sweep is complete; a generation budget is never a deck cap (2026-08-22, D-154, `trade.full_sweep`)

Convention for the generation loops in `backend/trade_service.py`, `backend/trade_gen_v2.py`
and `backend/trade_gen_fit.py`. Plan: [`../docs/plans/full-sweep/`](../docs/plans/full-sweep/plan.md).

- **Every eligible leaguemate is generated against.** Under `trade.full_sweep` the two loops in
  `trade_service.py` (`_generate_trades_impl` and `_generate_trades_v2`) no longer stop early,
  and `_dedup_and_sort` — which already sorted the whole collected set — becomes a **global**
  league rank rather than a rank of whoever came first. The other two arms (`trade_gen_v2`'s
  `boarded` loop, `trade_gen_fit`'s `eligible` loop) already had no opponent-level exit; that
  is now pinned, not assumed, by `backend/tests/test_arm_sweep_parity.py`.
- **`global_target` is a flag-off STOP, never a deck cap.** `max(30, max_per_opponent * 6)` was
  written as a bound on pathological generation cost and got read as a deck-size setting. It
  never was one: because it is checked *after* each opponent's whole batch lands and visit order
  is fixed, its real effect was to silently and *repeatably* exclude the same leaguemates from
  every refresh. Deck size is bounded by `bakeoff_deck_limit` and `first_session_deck_max`, and
  those are the dials. **The general rule:** a loop budget must never be the thing that decides
  what the user sees — if a budget's binding is order-dependent, it is a hidden selection rule.
- **The per-opponent keep is a knob, not a constant.** `exploration_base_per_opp` (default 5.0,
  `trade_service._DEFAULT_CFG` + `database._MODEL_CONFIG_DEFAULTS`) replaces the hardcoded
  `server._EXPLORATION_BASE_PER_OPP`, which stays as the fallback both `_deck_cfg` reads pass so
  an unseeded DB is byte-identical. That constant is why raising `max_per_opponent` was a no-op
  on the served deck — `_split_exploration_pool` re-trimmed to 5 per opponent afterwards. A
  post-generation trim width has to be as tunable as the generation budget it trims, or the two
  disagree silently.
- **Removing a stop is not a ranking change.** No new ranking code shipped: the sort, the caps
  and the streaming callback are untouched, and `global_target` is still computed (not logged — the module has no logger) so
  the flag-off path stays byte-identical. Visit order survives as **streaming** order only.
- **Threads were rejected, and the reason is recorded.** The enumeration is pure-Python CPU work;
  a thread pool buys nothing under the GIL. Latency work (a per-pair result cache keyed on
  roster/board/knob state, and a fork-safety-reviewed process pool) is a phase-2 plan, not this
  one — D-154.

## Tiers-save route contract shrank: `demoted_pids` is an ignored legacy key (2026-08-24, D-160)

- The Quick Set save body is `{position, tiers, cleared_pids, scope?, via?}`. Old binaries
  (v1.10–v1.16) may still send `demoted_pids`; the server accepts and **ignores** it — no pin
  writes, no echo. Unselected previously-tiered players HOLD their tier (the #161 demote rule
  is superseded by the operator's #381 ruling; see [D-160](DECISIONS.md)).
- `DEMOTED_ELO` (1100) stays in `ranking_service.py` — still load-bearing for anchor
  no-value and the D-085 goldens; only the quickset writer path was removed.
- Rollback is a code revert, not a flag; and a backend revert cannot restore demote behavior
  for post-fix clients (they no longer send the key).

## Provider identity is reconciled server-side; presentation is server config (2026-08-28, ADR-016)

Conventions from the IAP-enablement build (`backend/entitlements.py`,
`server.py /api/billing/revenuecat/webhook` + `/api/paywall/config`). Everything ships
dark — all `monetize.*` flags false, no route wears `@_require_pro`.

- **A third-party subscriber id is never assumed to be our key.** RevenueCat addresses
  each event to one `app_user_id` and lists every id it believes is the same subscriber
  in `aliases[]`. `resolve_rc_identity(app_user_id, aliases)` picks the first candidate
  that is a key we already recognise — an `acct_*` with an account row, or a known
  `sleeper_user_id` — `app_user_id` first, then aliases in order. **Unrecognised falls
  back to `app_user_id` verbatim, never to dropping the event:** a pre-sign-in purchase
  is real money, and it merges the moment an alias identifies it.
- **Reconcile before you upsert.** When the event names more than one candidate, the
  projector re-keys prior rows onto the canonical key *before* looking for a row to
  update — otherwise the anonymous purchase and the account purchase become two rows and
  the user is billed once but entitled twice. The re-key is `_BILLING_SOURCES`-only and
  product-scoped, the same rule the upsert already followed: manual grants and promo
  rewards are never moved by provider traffic.
- **Project a store event by its meaning, not by mapping it to the nearest status.**
  `TRANSFER` *moves* the entitlement (re-key `transferred_from` → resolved
  `transferred_to`); `expired` would claim it lapsed and `revoked` would claim we took
  it, and both are false. `BILLING_ISSUE` *extends* `expires_at` to
  `grace_period_expiration_at_ms` — extends only, never shortens, never touches a
  perpetual row. `CANCELLATION` stays a no-op (access runs to period end). Anything
  unmatched is stored with a `process_error` note, never silently applied.
- **Tolerate the vendor's SKU spelling; keep one canonical vocabulary.** `_product_mapping`
  accepts the runbook's ASC ids (`founder_lifetime*`, `season_pass_*`) alongside the
  canonical `ftf_*` ones so either App Store Connect choice reconciles without a deploy.
  The aliases are a reconciliation net only — docs, paywall config and clients use the
  `ftf_*` ids. A mis-sourced founder row is a perpetual grant priced as a subscription.
- **Server-driven presentation, client-driven price.** `GET /api/paywall/config` serves
  pages/features/SKUs so packaging changes without an app release, but its
  `display_price` strings are explicitly **fallback copy**: only StoreKit knows the
  user's storefront and currency, so the client renders the RevenueCat offering's price
  and falls back to ours. A flag-off config returns `{"enabled": false}` and *nothing
  else* — a dark paywall must not ship SKUs or prices.
- **Session auth is checked before the flag gate.** A dark route must never be an open
  one; `test_paywall_config.py` pins both orders.

## Pick assets ride the mixed arrays on every propose route; the server splits and encodes (2026-09-02, D-176)

- `POST /api/trades/propose` (Sleeper), `/propose-mfl` and `/propose-espn` all receive picks INSIDE
  `give_player_ids` / `receive_player_ids` — owned `{league}_{season}_{round}_{orig}` or generic
  `generic_pick_{round}_{tier}` — exactly as the deck, Matches, Awaiting and calculator mounts send
  them. No route accepts a client-encoded pick string (Sleeper's `draft_picks` body key now 400s
  when non-empty).
- Each route splits with `_is_ftf_pick_asset` and resolves picks against its OWN ground truth:
  Sleeper = the platform `draft_picks` grid (existence, literal `source=PICK_SOURCE_PLATFORM`) +
  live `traded_picks` (holder; from/to = giver/receiver rosters); MFL = the stored snapshot;
  ESPN = hard block. Any unresolvable pick refuses the WHOLE send (422 with `picks[]`), never a
  silent drop; the validate routes mirror the misses as blocking advisories (`asset_unmapped`,
  `pick_moved`) and count roster limits over players only.
- Every new `load_draft_picks` caller must be sanctioned by name in
  `test_pick_assignment.py::_SANCTIONED_SOURCE_CALLERS` (ADR-010 AST guard) — bare-default calls
  are forbidden.

Whole-team benefit extension (2026-09-04): `trade_roster.Context.card` calls pure `trade_outlook_utility` for both complete rosters, then `trade_mutual_benefit` for eligibility and ordering. Explicit outlook provenance is captured before inference. Current production requires supplied fresh point data; dynasty-only evidence cannot enable the strict gate. The worker evaluates after all package mutations, withholds provisional cards in enforcement mode and preserves market lane quotas. Collection lives under existing roster telemetry; `trade.mutual_benefit_v1` remains independently dark. See `docs/plans/trade-model-activation/validation.md`.

## Request scoring views and captured job ownership (2026-09-04, budget scalability)

`_require_session` returns `_RequestSession`, a mapping snapshot with ordinary
writes forwarded to the original identity's session. Reads must not update
shared `service`, `trade_svc` or `_effective_format`; `_active_format` honors the
request view and ignores stale scratch keys on raw sessions. Repeated helper
calls within one Flask request reuse the view. Mapping consumers must accept
`collections.abc.Mapping`. The session lock is reentrant because existing callers
can hold it while mutating a request view.

Job kickoff passes its explicit format and captured ownership to a frozen
`_TradeExecutionContext` before scheduling. Interactive and pregen callers pass
already-resolved context instead of rereading a potentially reinitialized token.
Generation gets a private league/member graph, but deliberately retains the
selected service's live card/decision stores for existing pending/swipe behavior.
This does not snapshot ranking versions or make DB-backed reads transactional;
see [architecture](../docs/architecture.md#local-request-and-trade-execution-context)
and [scope/evidence](../docs/plans/budget-scalability/implementation.md).

## Ownership and telemetry invariants

Private reads/writes depend on proof on the current session, never the grace flag or absence of a verified controller. Session initialization cannot change account identity and accepts only server-resolved roster snapshots. New Sleeper source binding proves source ownership before inspecting either board. Recommendation labels require a verified actor, valid owned impression and accepted validated ingestion. Analytics stores domain-separated identifiers instead of bearer tokens. Deletion resolves aliases, drains concurrent account work, revokes durable sessions transactionally and invalidates queued work. Version 2 export covers the expanded private scope while omitting credential material. The work gate assumes the deployed single-worker topology; see [ADR-017](../docs/adr/adr-017-account-deletion-work-leases.md). Browser verification uses the explicit extension bridge restricted to the production web origin.

---

## Win Now snapshot and request isolation

Implementation checkpoint 2026-09-04: immutable whole forecast batches and league/model revisions identify baselines; viewer-scoped job/scenario IDs retain objective, constraints and expiry. A stable exchange asset key groups history without replacing evaluated evidence. Clients cancel by viewer/league/objective/parameter epoch and preserve server order; expired results are not recommendations. Probabilities are fractions and deltas display absolute pp. Budget uses fixed baseline roster value. Like/pass writes only the season decision store. Routes, schema and shared bounds are in the [API](../docs/api-reference.md#season-projections-and-win-now), [data dictionary](../docs/data-dictionary.md#win-now-evidence-tables) and [invariants](../docs/cross-client-invariants.md#win-now-objective-and-evidence-semantics); parent integration review and local mechanical verification are complete. The explicit platform-only pick read in `win_now_service.build_context` is sanctioned in the existing ADR-010 containment test.
