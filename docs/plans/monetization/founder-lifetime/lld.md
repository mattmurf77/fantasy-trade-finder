# Founder Lifetime — LLD

Companion to [hld.md](hld.md). Foundation primitives per
[../00-platform-foundation.md](../00-platform-foundation.md).

**Labeled assumption A0:** the foundation build lands its entitlement service +
webhook projector in `backend/entitlements.py` and the paywall-config / webhook /
admin-grant routes in `backend/server.py` (foundation doesn't pin filenames). If the
foundation implementer picks different module names, substitute throughout — the
function-level contracts below are the spec, not the paths.

## 1. Flag registration

`backend/feature_flags.py` → `FLAG_KEYS`: `monetize.founder` ships in the
foundation's flag batch (foundation §1 table). This plan **consumes** it; verify it
is present before building, add it (default False) if the foundation batch hasn't
landed yet. No founder-specific flags beyond it.

## 2. Constants (one place)

`backend/entitlements.py`:

```python
FOUNDER_PRODUCT_IDS = {"ftf_founder", "ftf_founder_b"}   # b = $59 A/B arm (D1)
FOUNDER_CAP = int(os.environ.get("FTF_FOUNDER_CAP", "100"))   # D2; env so the
    # operator can adjust without a deploy-code change; document in config-reference
```

## 3. Backend changes

### 3.1 `is_founder` helper — `backend/entitlements.py`

```python
def founder_row(user_id: str) -> dict | None:
    """The active founder entitlement row for user_id (or its account), else None.

    Founder := status='active' AND expires_at IS NULL AND (
        source='founder_iap'
        OR product_id IN FOUNDER_PRODUCT_IDS               # stripe rail
        OR (source='manual_grant' AND metadata.founder)    # operator comp
    ). Resolution via the foundation's user_id/account_id join (§2.2).
    """
```

`is_founder(user_id) = founder_row(user_id) is not None`. Every surface calls these
two; the predicate exists nowhere else. Returns the row so callers can read
`metadata.founder_number` / wall opt-in.

### 3.2 Remaining-count query — paywall-config route

```sql
SELECT COUNT(*) FROM entitlements
WHERE status = 'active' AND expires_at IS NULL
  AND (source = 'founder_iap' OR product_id IN (:founder_skus))
  AND source != 'manual_grant'          -- comps excluded per D4
```

`remaining = max(0, FOUNDER_CAP - count)`. Computed per request (SQLite scale, same
stance as foundation §2.2 — no cross-request cache). One user holding rows on both
rails would double-count; prevented by the projector's per-account founder dedupe
(§3.3, "already a founder" case).

### 3.3 Projector — non-consumable case (`backend/entitlements.py`)

Extend the foundation projector's event handling:

- **RevenueCat `NON_RENEWING_PURCHASE` / `INITIAL_PURCHASE` with
  `product_id ∈ FOUNDER_PRODUCT_IDS`**, and the Stripe one-time-payment webhook for
  the founder price: insert
  `{entitlement: "pro", source: "founder_iap" | "stripe", product_id, status:
  "active", starts_at: now, expires_at: NULL, metadata: {rail, price_arm,
  founder_number, original_transaction_id | stripe_payment_intent,
  wall_opt_in: false}}`.
- **Already a founder** (restore, cross-rail re-buy, replayed event): no second row —
  idempotent on `event_id` (foundation) *and* on `founder_row(user)` existing; log
  and return. Keeps the cap count honest.
- **Founder-number assignment**: inside the same transaction,
  `SELECT COALESCE(MAX(json_extract(metadata,'$.founder_number')), 0) + 1` over
  founder rows (all sources — comps share the sequence, D4 note). Fine under
  SQLite's writer lock; **Postgres note:** wrap in `SELECT … FOR UPDATE` on a
  sequence row or retry on a unique partial index — flag in the Postgres-path
  checklist, not needed now.
- **`REFUND` / `EXPIRATION`-equivalent for the founder SKU**: `status='refunded'` →
  badge predicate goes false, wall entry disappears, slot reopens while the window
  is open (D7). Founder numbers are **not** reissued (gaps are honest).
- **Sub-overlap check** (HLD §7): after any founder insert, and after any sub
  `INITIAL_PURCHASE`/`RENEWAL` for a user where `is_founder`, compute
  `overlap = active sub row with future expires_at`; store nothing new — the
  entitlements read (§3.4) recomputes it, the projector just emits the
  `founder_sub_overlap` `record_event`. (Cheap: both checks are on the projector
  write path, which is rare.)
- Emit `founder_purchased` + a `founder_cap_remaining` event with the post-insert
  count on every founder purchase; daily cron (foundation §4 rollup) snapshots
  `founder_cap_remaining` too.

### 3.4 Entitlements + profile payloads — `backend/server.py`

- `GET /api/me/entitlements` (foundation §2.3) gains:
  `founder: {is_founder, founder_number, wall_opt_in} | null` and
  `sub_overlap: bool` (recomputed at read: `is_founder ∧ active sub row`).
- Public-profile route (`profiles.public_pages` payload built near
  `accounts.get_user_profile`) gains `is_founder`, `founder_number`.
- Match/trade-card payloads: the match serializer adds `counterparty_founder: bool`
  (one `is_founder` call per card build; memoize per request like flags).

### 3.5 Paywall-config founder block — `backend/server.py`

Per HLD §2. State derivation:

```python
if not is_enabled("monetize.founder"):
    state = "anchor" if (purchases > 0 and is_enabled("monetize.paywall")) else "hidden"
elif remaining <= 0:
    state = "cap_hit"
else:
    state = "open"
```

`checkout_url` (Stripe, window phase) minted per request with the caller's arm +
account id in Stripe metadata so the webhook can key the row (foundation §4 web
rail). Copy fields (`headline`, `sub_line`) hardcoded server-side, value-first per
PRD messaging.

### 3.6 Founders-wall route — `backend/server.py`

`GET /api/founders/wall` — public, no session, no flag gate (HLD §6):

```json
{"cap": 100, "count": 37, "closed": false,
 "founders": [{"n": 1, "name": "mattm", "avatar": "..."},
              {"n": 2, "name": null, "avatar": null}, ...]}
```

`name/avatar` NULL unless `metadata.wall_opt_in`. Sorted by `n`. Opt-in toggle:
`POST /api/me/founder-wall {opt_in: bool}` (session-authed; 404 unless
`is_founder`) updates row metadata.

### 3.7 Manual founder comp — admin grant route

Foundation `POST /api/admin/entitlements/grant` accepts one new body key
`founder: true` (only valid with `perpetual: true`, else 400): sets
`metadata.founder = true`, assigns the next `founder_number`, defaults
`wall_opt_in: false`. `DELETE /api/admin/entitlements/<id>` (revoke) already removes
badge + wall via the predicate — no extra code.

## 4. Mobile changes (`mobile/src/`)

| File | Change |
|---|---|
| `api/entitlements.ts` (new, with foundation) | Types for the founder block + wall route + opt-in POST |
| `screens/FounderOfferSheet.tsx` (new) | Offer surface (modal sheet off the paywall/announcement): headline, live "N of 100 left", price, buy CTA. Window phase: CTA = `Linking.openURL(checkout_url)`; launch phase: RevenueCat purchase of the assigned offering. Fires `founder_offer_viewed`. Renders nothing unless paywall config `state == "open"` |
| `screens/ProfileScreen.tsx` | Founder badge chip next to the display name when payload `is_founder` — flare-bordered `Badge` ("FOUNDER · #17"), informational only per design-system flare rule. Screen is read-only display; the chip is one conditional row |
| `components/TradeCard.tsx` | Match-variant only: small flare `Badge` "FOUNDER" beside the counterparty name when `counterparty_founder`. No layout shift when absent |
| `screens/SettingsScreen.tsx` | Account section: founder row ("Founder #17 · Lifetime") when `is_founder`, with the wall opt-in toggle. Sub-overlap prompt lives here **and** as a one-time Toast/banner post-purchase: "You still have an active subscription — cancel it" → `Linking.openURL('https://apps.apple.com/account/subscriptions')` (or Stripe portal URL from the payload) |
| `screens/FoundersWallScreen.tsx` (new, or a section in the offer sheet) | Renders `GET /api/founders/wall`; entry from the offer sheet and the paywall anchor row |
| share-card renderer (foundation §5) | "Founder #N" card variant; fires `founder_share_card_created` |

RevenueCat SDK integration itself is foundation §4 (eng-mobile); this plan only adds
the founder offering purchase call.

## 5. Web changes

| File | Change |
|---|---|
| `web/founders.html` (new) | Founders wall page — Chalkline, flare badge chips, "N of 100" header, closed banner when `closed`. Fetches `/api/founders/wall`. Link from `index.html` during/after the window |
| `web/profile.html` | Founder badge chip when the profile payload says `is_founder` |
| Web paywall/offer surface (Plan A scope) | Founder block per paywall config; anchor-mode sold-out row. Only the wall + profile chip are *this* plan's web deliverables; the web paywall ships with Plan A |

## 6. API examples

```
GET /api/paywall/config            (window open, arm B)
→ { ..., "founder": {"state": "open", "product_id": "ftf_founder_b",
       "price_display": "$59", "price_arm": "b", "cap": 100, "remaining": 31,
       "headline": "Everything FTF ever ships. One price. Locked forever.",
       "sub_line": "Founder badge + wall spot. Supports a solo dev.",
       "checkout_url": "https://checkout.stripe.com/c/pay/cs_..." } }

GET /api/paywall/config            (anchor mode)
→ { ..., "founder": {"state": "anchor", "cap": 100, "remaining": 0,
       "headline": "Founder Lifetime — 100/100 claimed" } }

GET /api/me/entitlements           (founder w/ live sub)
→ { "pro": true, "sources": ["founder_iap", "apple_iap"], "expires_at": null,
    "founder": {"is_founder": true, "founder_number": 17, "wall_opt_in": true},
    "sub_overlap": true, "flags_snapshot": { ... } }

POST /api/admin/entitlements/grant   (X-Cron-Secret)
  {"user": "mattm", "entitlement": "pro", "perpetual": true,
   "founder": true, "note": "top-10 beta tester"}
→ 200 {row incl. metadata: {"founder": true, "founder_number": 38, ...}}
```

## 7. Edge cases

### 7.1 Purchase race at the cap boundary
Two users load config at `remaining: 1`; both complete Apple purchases before either
webhook lands. **Decision: accept oversell by a few.** A completed non-consumable
purchase cannot be server-rejected without a refund war with Apple and a furious
user; the projector always applies founder events (HLD §1). `remaining` clamps at 0;
101–102 founders is an honest rounding error on "first 100". Hard-reject is
explicitly rejected. The window's small warm audience makes >1–2 oversell
implausible.

### 7.2 Refund
`status='refunded'` → badge/wall gone, slot reopens while window open (D7), number
gapped, `founder_cap_remaining` re-snapshot. After close: moot (nothing to resell).
Apple decides refunds, not FTF; no in-app refund surface.

### 7.3 Deleted account (`backend/accounts.py` delete matrix)
`delete_user_data` must add `entitlements` (and the user's `subscription_events`
linkage — foundation decides; recommend keep ledger rows but NULL `user_id`, matching
the app_feedback anonymize pattern) to the DELETE matrix, and update the matrix
comment block + `docs/data-dictionary.md`. Consequences: wall entry disappears
(count drops — acceptable and honest), badge gone. If the person returns and
restores purchases, RevenueCat replays the original transaction → projector
re-creates the row → **new** founder number (original is gapped; number is display
data, not a promise). Foundation should own the matrix edit; this plan is the first
consumer — coordinate so it isn't missed.

### 7.4 A/B price fairness
Both arms get identical perpetual entitlement + badge; arm stored in metadata, never
displayed. Blowback risk handled at PRD R6 (short window / D1 decline). Do not
refund the $20 delta retroactively — sets a precedent; if the operator wants
goodwill, a manual gesture outside the product is the lane.

### 7.5 Founder buys on both rails
Stripe during window, then taps restore/buys IAP at launch: projector dedupe (§3.3)
keeps one row; RevenueCat restore of an unowned SKU is a no-op; an actual second
*charge* can only happen via Apple (Apple blocks re-buying owned non-consumables, so
in practice impossible).

### 7.6 `monetize.entitlements` OFF
Founder purchases during the window still project rows (foundation: grants dormant
until the master flag enforces). Badge surfaces read `is_founder` from data, not the
master flag — badges may show while nothing is enforced. Intended: recognition ≠
gating.

## 8. Test plan

**pytest (`backend/tests/test_founder.py`, plus foundation suites):**
1. Projector: founder purchase event → perpetual row, number 1..N monotonic,
   idempotent on replayed `event_id` and on cross-rail duplicate.
2. Cap: remaining math excludes comps + refunded; clamps at 0; `state` derivation
   table (all five states from flag × count × paywall flag).
3. Oversell: two purchase events applied at `remaining == 1` → both rows exist,
   `remaining == 0`, no error.
4. Refund: row → `refunded`, `is_founder` False, wall shrinks, slot reopens.
5. Badge resolution: founder on Sleeper uid → re-link new uid under same account →
   `is_founder` still True (rides foundation §2.2 tests).
6. Manual comp: grant with `founder: true` → badge + number + no cap consumption;
   revoke → gone. `founder: true` without `perpetual` → 400.
7. Sub-overlap: active sub + founder → `sub_overlap: true`; expired sub → False.
8. Wall route: opt-in visibility, anonymous entries, public (no session) access,
   sorted by number.
9. Delete matrix: `delete_user_data` removes entitlement rows; wall drops the entry.

**Maestro (`mobile/.maestro/`):**
- `NN-founder-offer.yaml`: flag on + seeded config → offer sheet shows price and
  live remaining; flag off → no offer anywhere. (Real StoreKit purchase is not
  Maestro-testable; drive the UI against a seeded backend, sandbox-purchase manually
  once per release.)
- `NN-founder-badge.yaml`: seeded founder account → badge on Profile, Settings
  founder row, wall screen renders entries.
- Extend the trade-card flow: seeded counterparty founder → chip visible on match
  card, absent otherwise.

**Manual pre-ship:** one real sandbox IAP end-to-end (webhook → row → badge), one
Stripe test-mode checkout end-to-end, restore-purchases after reinstall.

## 9. Docs-to-update checklist (root CLAUDE.md table)

- `docs/api-reference.md` — `/api/founders/wall`, `/api/me/founder-wall`, founder
  blocks on paywall-config + entitlements, `founder` key on the admin grant route.
- `docs/config-reference.md` — `monetize.founder` behavior detail, `FTF_FOUNDER_CAP`.
- `docs/cross-client-invariants.md` — SKU ids (`ftf_founder`, `ftf_founder_b`),
  founder `state` enum strings, badge label string, event names (PRD §5), flare
  badge usage.
- `docs/data-dictionary.md` — founder metadata keys convention on `entitlements`;
  delete-matrix row (with foundation).
- `docs/glossary.md` — Founder, founder number, founders wall, anchor mode,
  pull-forward.
- `docs/design/components.md` — Founder badge chip spec (flare, informational).
- `docs/runbook.md` — window open/close procedure (flag flip + announcement + cap
  watch), oversell/refund handling.
- ADR only if the implementer deviates from the foundation's RevenueCat/server-truth
  ADR — no new decision here otherwise.
