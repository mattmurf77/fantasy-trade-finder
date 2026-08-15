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
- **Trades:** `POST /api/trades/generate`, `GET /api/trades`, `POST /api/trades/swipe`, `GET /api/trades/liked`
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
