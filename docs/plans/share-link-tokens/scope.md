# Feature Scope — Unguessable share links for trades (build O8)

**Date:** 2026-10-23 (build started 2026-10-20)
**Entry point:** direct ask: org-bringup build O8, brief `docs/plans/org-bringup/briefs/build-o8-share-tokens-engagement-eng.md` (with head-eng's rulings) and the lead's design `docs/plans/org-bringup/leads/engagement-eng-o8.md`; operator direction "Unguessable random links should be the solve" (2026-10-20, relayed); old-link behaviour confirmed by head-product (P29)
**Builder:** O8 build worker under engagement-eng, branch `build/o8-share-tokens`
**Operator sign-off on waivers:** pending: the §1 analytics waiver is surfaced to the operator through engagement-eng → head-eng before merge

**The problem.** `/s/trade/<x>` and `/og/trade/<x>.png` took the sequential `trade_matches.id` with no auth, and `og_image.render_trade_card` loaded the row directly. Anyone could walk the ids and read every mutual match's give/get and fairness verdict, across leagues.

**The change.** A party to a match mints a 128-bit token (`POST /api/share/trade`); the two GET routes resolve only through that token. Every miss, including every old numeric link, gets one generic "expired" page and PNG, status 200, byte-identical. Mobile shares the server-minted link; the web's dead numeric URL builder is deleted.

---

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [ ] **(b) Existing events cover it:** `trade_card_shared {trade_id, landing}` keeps its meaning (`landing` = the message carried a rich `/s/trade/` or `/s/p/` landing). `share_package_created` fires from its existing call site, now also when a matched trade's token mint fails and the share falls back to the package rung.
- [x] **(c) WAIVED — no new analytics because:** the brief allows none, and the questions an event would answer (how often links are minted, opened, or hit the expired page) are not decisions anyone is waiting on. Mint volume is countable from `trade_share_tokens.created_at` if it is ever needed. A link-open event would put an unauthenticated, crawler-driven route into the event stream. No analytics files were touched, so the same-commit taxonomy rule does not apply.

## 2. Schema & flag scope

- **New table:** `trade_share_tokens` (`token` VARCHAR PK, `match_id` INTEGER NOT NULL, `created_by` VARCHAR NOT NULL, `created_at` VARCHAR NOT NULL, `revoked_at` VARCHAR NULL; indexes `ix_trade_share_tokens_match (match_id)`, `ix_trade_share_tokens_creator (created_by, created_at)`), approved by head-eng as written. Created by `metadata.create_all` on fresh and existing databases on both SQLite and Postgres (a new table gets its inline indexes with it), the precedent `shared_packages` set; no `_migrate_db` row. → `docs/data-dictionary.md` updated.
- **Account deletion:** `accounts._delete_user_data` deletes the user's rows by `created_by` (every alias). The counterparty's own tokens survive: account deletion anonymizes `trade_matches`, it does not delete it.
- **Feature flags:** none new. The mint reuses `growth.share_landing` (already ON), 404ing like `/api/share/package` when it is off. The GET routes stay unflagged, as they were.
- **Env vars / `model_config` keys:** none. Rollback lever: revert the deploy (old numeric links would then resolve again, so a revert reopens the hole); to kill a single link, set `revoked_at` (runbook).
- **API:** new `POST /api/share/trade`; changed semantics for `GET /s/trade/<token>` and `GET /og/trade/<token>.png` (token-only, generic 200 miss). → `docs/api-reference.md` updated.
- **Rate limits:** 30 mints per user per hour (count from the table). No per-IP GET limiter (head-eng ruling: a 2^128 space can't be walked, the left-most `X-Forwarded-For` hop is spoofable, and an in-process window is module-level mutable state).
- **Older TestFlight builds:** they keep sharing `/s/trade/<match_id>`, which now opens the generic "expired" page. Intended: keeping old links working would keep the hole open. The minimum-version gate (launch item 19) moves users onto a build that mints tokens.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-share-trade-token.js` (`npm run test:share-trade-token`, dependency-free, plain node). Pins: (1) no file under `mobile/src`, `web/js` or `extension/` builds `/s/trade/` or `/og/trade/` from an interpolated or concatenated value; (2) `shareLikedTrade` gets the matched-trade URL from `resolveTradeShareUrl` and falls through to `resolveShareUrl`; `api/share.ts` posts `{match_id}` to `/api/share/trade`; the mint wait is bounded at 2 s (executed against a mint that never answers); (3) `rewriteUniversalPath` maps `/s/trade/<x>` to `app/matches` with no id, keeping the query (executed). Each assertion sabotaged once and confirmed red.
- [x] **Unit tests:** new `backend/tests/test_trade_share_tokens.py` (14 tests): numeric ids never return trade content on either route (no player names or verdict in the HTML; PNG byte-equal to the generic one); a non-participant, a missing match and twelve malformed ids all get the identical 404; demo refused; flag off → 404; 401/403 without a verified session; tokens are 22 chars, URL-safe alphabet, decode to 16 bytes, unique over 200 mints; re-mint idempotent per sharer, each party their own; revoked, unknown, malformed, orphaned and numeric misses give byte- and header-identical page and PNG; a lookup failure degrades to the generic miss; the 30/hour limit (and the window rolling off); account deletion removes only the sharer's tokens. `backend/tests/test_account_deletion_coverage.py` gains the table (all aliases deleted, counterparty kept). Sabotaged: numeric resolves again, non-participant mints, miss PNG/page bytes differ, token shortened to 8 chars, deletion hunk removed — each red, then restored.
- [x] **Code-walk proof:** below.
- [x] **Manual TestFlight checklist:** below.
- `testID`s added/renamed: none.

### Code-walk (file:line at the build tip)

- **Mint.** `backend/server.py:25728-25776` `create_share_trade_route`: `@_gate_unverified_write` (:25729) → flag off 404 (:25743) → `_require_session` → demo 400 (:25748) → `_share_trade_match_id` (:25715, int or ASCII digits, 1..2^31−1, else 404 :25753) → hourly count (:25756, `database.py:14907`) ≥ 30 → 429 (:25760) → `create_trade_share_token` (:25765, `database.py:14844`): one transaction loads the match, returns None unless the session user is `user_a_id` or `user_b_id` (`database.py:14870`, the predicate of `dismiss_match` `database.py:10196`, `record_match_disposition` :10255 and `load_matches` :9790), returns the caller's live token if any (:14876), else inserts `token_urlsafe(16)` (:14864), retrying on `IntegrityError` (:14887). None → the same 404 (:25769). The response carries only the token and the two relative URLs.
- **GET `/s/trade/<token>`** `server.py:25597` `share_trade_page`: `_resolve_trade_share` (:25468) requires `fullmatch` of `[A-Za-z0-9_-]{22}` (:25470) before any DB read, then `resolve_trade_share_token` (`database.py:14892`) joins `trade_share_tokens` → `trade_matches` where `revoked_at IS NULL` (:14901-14902); a lookup error is a miss. **Miss** → `_share_html(..., noindex=True)` (:25608-25615) with the `og_image.TRADE_LINK_EXPIRED_*` copy and `og:image` `/og/trade/expired.png`; no request value reaches the bytes. **Hit** → today's page, `image_url = /og/trade/<token>.png` (:25618).
- **GET `/og/trade/<token>.png`** `server.py:25480` `og_trade_card`: same resolver; **miss** → `render_expired_trade_card()` (`og_image.py:553-554`, `lru_cache` of a no-argument render, so every miss is the same bytes) with status 200 (:25490); **hit** → `render_trade_card(match)` (:25492, `og_image.py:504`), which reads only the resolved row's `user_a_give` / `user_a_receive` (no `int(match_id)`, no lookup by a URL value).
- **C1 mobile share** `mobile/src/screens/TradesScreen.tsx:5276` `shareLikedTrade`: `matchId` comes from the swipe response (:2463). :5302 awaits `resolveTradeShareUrl(matchId)` (`utils/shareLinks.ts:178`), which aborts after `TRADE_SHARE_MINT_TIMEOUT_MS = 2_000` (:163, :182) through `createTradeShare`'s signal (`api/share.ts`, POST `/api/share/trade`; `apiRequest` rejects on caller abort, `api/client.ts:311-319`), and returns `getBaseUrl() + url` or null. Non-null → `url = <server url>?ref=<user>`, `landing = true` (:5305-5307). Null → the unchanged package branch (`resolveShareUrl`, :5309), whose floor is the `?ref=` root.
- **C2 deep link** `mobile/src/utils/deepLinks.ts:236`: `/s/trade/<x>` → `app/matches` + the query suffix, no id. `Matches: 'matches/:match_id?'` (:201) resolves with no params. `git grep match_id mobile/src` finds no reader of `route.params.match_id`: MatchesScreen reads only `guidedArrival`, `segment`, `leagueId` and `at` from its route.

### Operator TestFlight checklist (needs a build cut from this branch, after deploy)

1. On the new build, like a trade that completes a mutual match, then tap Share. **Expect** the message link to read `…/s/trade/<22 letters, digits, - or _>?ref=<you>`, never a number.
2. Open that link on another phone without the app (or in a private browser). **Expect** the "Trade Match" page and a card showing the trade.
3. Paste the link into iMessage. **Expect** the unfurl to show the trade card.
4. Open an old link, `…/s/trade/<any number>`. **Expect** "This trade link has expired. Open Fleeced to see your trades." and, in iMessage, the generic expired card.
5. Share the same trade again. **Expect** the identical link as step 1.
6. Have the other party to that match share it. **Expect** a different token, which also opens the trade.
7. On a phone with the app installed, tap a shared `/s/trade/…` link. **Expect** the app to open on Matches (no crash, no blank screen).
8. In airplane mode, like-and-share a mutual match. **Expect** the share sheet within about 2 s, with the plain `?ref=` link.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | **updated** | Profiles + Sharing: `POST /api/share/trade` row; `/s/trade/<token>` and `/og/trade/<token>.png` rows rewritten |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | n/a | No convention shifted: the table follows the `shared_packages` precedent (create_all, inline indexes, rate limit from the table). Living-memory is release-lead's scribe's at merge in any case |
| `docs/architecture.md` (module wiring / data flow changed) | n/a | No module added or re-wired; `og_image.py` is still "share images for tiers and trades" (:610) |
| `living-memory/HLD.md` (architecture genuinely shifted) | n/a | No new module, client or major flow |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | n/a | No share-URL shape is recorded there; the token shape is server-owned and clients never build it |
| `docs/glossary.md` (new domain term) | n/a | "Trade share token" is defined in `docs/data-dictionary.md` (`trade_share_tokens`); no UI term added |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | n/a here | The choices (separate token table, 128 bits, idempotent mint, no GET limiter, generic 200 miss) are head-eng's rulings in the brief and head-product's P29; logging them in DECISIONS.md is the scribe's at merge |
| `docs/data-dictionary.md` | **updated** | New `trade_share_tokens` section + TOC entry |
| `docs/runbook.md` | **updated** | "Trade share links: enumeration fix (build O8, 2026-10-20)": the hole, the fix, old links, symptoms, revoking a token (a prod write: release-lead, on the operator's go) |
| `docs/config-reference.md` | **follow-up** | `growth.share_landing` (:496) still says mobile composes `/s/trade/<id>`; it now also gates the mint. Outside this build's file grant |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (with the `check-*.js` suites) + `web-structure` + `maestro-testid-lint`, on the pushed sha. Not yet run: push needs the operator's word.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry by release-lead's scribe at merge (this build may not edit `living-memory/`).
- **TestFlight verification:** the §3 checklist, run by the operator after the deploy and a build from this branch; outcome logged in TEST_LEDGER.
- **Express lane declared by the operator?** No. Full gates: schema + API change.
- **Merge:** DRAFT until release-lead QA and the operator's go in release-lead's session.
