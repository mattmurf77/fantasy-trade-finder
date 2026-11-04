# Scope addendum: paywall hardening (R28.14, P3-1, P3-3, P3-4)

> Addendum to the paywall scope, [`scope.md`](scope.md) in this folder (it lands with
> `plan/monetization-launch`, PR #393, and is not on the paywall stack's ancestry, so the
> addendum is a separate file to keep both merges conflict-free). Branch
> `feat/paywall-hardening`, stacked on #397 `feat/paywall-preview-allowance` @ `83e5eb4b`
> (#394 → #395 → #397). Approved by head-eng; item (a) approved by legal (R28.14, with
> conditions). Lead: platforms-eng. Date: 2026-10-27.

- [What changes](#what-changes)
- [1. Analytics scope](#1-analytics-scope)
- [2. Schema & flag scope](#2-schema--flag-scope)
- [3. Evidence scope](#3-evidence-scope)
- [4. Docs scope](#4-docs-scope)
- [5. Known limitations](#5-known-limitations)
- [6. Waivers](#6-waivers)

## What changes

- **(a) R28.9 fix (legal R28.14).** An unverified, non-demo session is settled from
  verified-ness alone, **before any `paywall_previews` or entitlement read**. On a gated rule
  whose route wears `@_gate_unverified_read` / `@_gate_unverified_write` for the method, the
  hook returns None and the route's own 403 `verification_required` answers. On any other
  gated rule it returns 402 `verify_required`. The unverified `_preview(..., gate=VERIFY_REQUIRED)`
  path is removed (with `Preview.gate`, which only it used), so unverified sessions never get
  the preview and never write `paywall_previews`. The demo session is unchanged. The hook reads
  the route's gate off the live view function (each decorator marks its wrapper, and
  `functools.wraps` carries the mark up), so a dropped decorator turns into the 402, never a
  pass. Docstrings that cited R28.9 for a preview are corrected.
- **(b) P3-1, a durable preview window.** With `trade.first_page_store` off (the prod
  default) the swipe and pass-reason check read only the live job, so after the 4 h job
  retention or any deploy a swipe on a held page-1 card got 402. Each preview serve now records
  the window's trade ids in `paywall_previews.window_trade_ids`. The check reads the live
  window while the process holds the deck, and the stored one once it doesn't.
- **(c) P3-3.** The preview tests run on every P2 deck path in
  `test_trade_pages_p2.DECK_PATHS` (stored, live, rebased_row, rebased_job), not only the
  stored and rebased-row paths.
- **(d) P3-4.** A direct test that, with enforcement dark, the gated deck routes write nothing
  to `paywall_previews` (no statement at all on it) and make no other paywall or billing write.
- **(e) K0 (head-eng, 2026-10-28; analytics-lead's K0 alarm).** `_preview()` answered 402
  `preview_used` to a user never served a card (knob 0, `GET /api/trades`, a swipe or a
  page-2 cursor before page 1), so K0 ("any 402 `preview_used` to a user never served a
  card") would fire for every new non-entitled user on day 1. Now `preview_used` only when
  the user's `paywall_previews` row exists; with no row the 402 is `never_trialed`.
  `gate_reason` follows the same rule. The serve-time claim failures in `server.py` already
  imply a row (another deck holds the preview), so they keep `preview_used`.

## 1. Analytics scope

Waived: no event is added, changed or removed. `paywall_viewed`'s `source: gate` still fires
from the client on a 402. An unverified session on a decorated route now gets the
account-auth 403, which the client already handles as "verify", not as a paywall.

## 2. Schema & flag scope

- **Schema: head-eng's GRANT, one nullable column.** `paywall_previews.window_trade_ids`
  (Text, JSON list of trade ids, nullable). It's added to the `Table(...)` (fresh DBs via
  `metadata.create_all`) and as a `_migrate_db` `migration_cols` row
  `("paywall_previews", "window_trade_ids", "TEXT")` (existing DBs). There's no backfill:
  NULL reads as an empty window, the same fail-closed answer as before P3-1, and only once
  the job is gone.
- **Export and deletion:** the table is already in `accounts._ADDITIONAL_PRIVATE_TABLES`. The
  row is deleted whole, and the export carries every column, `window_trade_ids` included.
  These are the user's own deck's trade ids, not a credential, so nothing is omitted.
- **Flags and knobs:** none added or flipped. Enforcement stays dark (`entitlements.is_enforcing()`).

## 3. Evidence scope

Backend only. There's no mobile or web change, so no TestFlight checklist is needed. All
tests use in-memory SQLite, with no network.

| Item | Tests | Sabotage that turns them red |
|---|---|---|
| (a) | `test_paywall_gate_unverified.py`: every gated rule in `ROUTES` (32) × mobile and web (web knob 1) × four account states (no history, a `paywall_previews` row, active pro, lapsed pro). It compares status, body bytes and headers (Date excluded), pins which rules answer 403 and which 402, and asserts zero `preview_row` / `get_entitlements` / `list_for_user` calls and no `paywall_previews` write. Also: the pure decision on every deck route with the route gate on and off; no SQL statement on `paywall_previews`, `entitlements` or `subscription_events`; the demo exemption. `test_paywall_preview.py` and `test_paywall_gate.py`'s R28.9 tests are restated for the new answer | S1, the entitlement read moved above the verified check: 75 red, all 64 byte-identical cases among them (active pro gets the route's own answer). S2, the unverified `_preview` path restored: 5 red |
| (b) | `test_paywall_preview.py::test_p31_*`: the window persists across the job's disappearance (swipe and pass-reason); a stored-window card is allowed and one outside gets 402; the live window decides while the job is held; a pre-column row fails closed; `record_preview` rewrites the window for the same deck only; `_migrate_db` adds the column to an old table, idempotently; export includes it | `_window_ids` ignores the stored window: 7 red. The `migration_cols` row is dropped: the migration test goes red |
| (c) | `test_p33_*`, parametrized over `DECK_PATHS`: with a 4-page window each path is capped, recorded against the served deck with its window, and swipes hold to it before and after the deck leaves the process; at the default knob, stored and live are 402 with no row, and the rebases record the newer deck | n/a (coverage) |
| (e) | `test_paywall_preview.py::test_get_trades_pending_view_is_not_the_preview` (no row → `never_trialed`; after page 1 → `preview_used`) and `::test_knob_zero_blocks_the_first_request` (knob 0, no row → `never_trialed`; a spent row → `preview_used`); `test_paywall_gate.py::test_never_entitled_reason_is_preview_used_only_once_spent`. The gate matrix, `test_other_gated_routes_block_never_entitled`, `test_decide_pure_matches_hook`, the swipe/pass-reason, R28.9-after-verifying and P3-3 default-knob tests are restated (no row → `never_trialed`) | `_preview` answers `preview_used` regardless of the row: both K0 tests red |
| (d) | `test_p34_*`, flags off and flags on with knob 0: every deck route (including page 2, the unpaged body, `GET /api/trades`, swipes and passes outside the window), plus P1 stored-page and P2 deck-id serves. Full decks, no 402, zero `paywall_previews` statements, no billing write, `record_preview` never called | The hook keys on `classify()` instead of `applies()` (ignores enforcement): 4 red |

Pre-ship gate: `FTF_SKIP_SIM_GATE=1` (D-056). The evidence is logged in
`living-memory/TEST_LEDGER.md` on 2026-10-27.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated** | Paywall gate (402): a new "Unverified sessions" paragraph (decorated → the route's 403; else 402 `verify_required`; no preview read), the deck preview is verified-only, the swipe window fallback plus the P3-2 limitation, and the `verify_required` row |
| `docs/data-dictionary.md` | **updated** | The `paywall_previews.window_trade_ids` row and the table note. Also head-eng's nit: the `sandbox:` prefix on `entitlements.granted_by` |
| `living-memory/LLD.md` | n/a | No convention shift. The gate table, the hook and the additive-column path are unchanged conventions |
| `docs/architecture.md` / `living-memory/HLD.md` | n/a | No module wiring or data-flow change |
| `docs/config-reference.md` | n/a | No flag or knob added. The `paywall_preview_pages` row already scopes the preview to a user who never held pro |
| `docs/cross-client-invariants.md` | n/a | The 402 body and its `gate` enum are unchanged. 403 `verification_required` is account-auth's existing contract |
| `docs/glossary.md` | n/a | No new term |
| ADR / `DECISIONS.md` | n/a | Legal's R28.14 and head-eng's grant are the decision records. Recorded here |

## 5. Known limitations

- **P3-2 (documented, not fixed; head-eng).** A running deck that re-sorts can change its
  first `paywall_preview_pages × trade_page_size` raw cards between polls. The client can then
  see more than that many distinct cards across polls, and a swipe on a card that was
  re-sorted out of the live window answers 402 `preview_used`. The stored window
  (`window_trade_ids`) follows the last serve, so once the job is gone the fallback matches the
  live check as of that serve, not every card ever shown. There's a code comment at
  `paywall_gate._window_ids`.
- **The window fallback is per-process.** "The deck is gone" means this process holds neither
  the job nor a #368 stored page for it. On today's single web worker that is the 4 h
  retention or a deploy.

## 6. Waivers

- Analytics: waived (§1).
- TestFlight checklist: waived. The change is backend only, the paywall is dark, and the
  client contract (402 body, 403 `verification_required`) is unchanged.
