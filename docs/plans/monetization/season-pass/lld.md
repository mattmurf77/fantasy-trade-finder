# Season Pass — LLD

Owner: eng-backend / eng-mobile / eng-web. Date: 2026-07-17. Status: DRAFT.
Companion to [prd.md](prd.md) + [hld.md](hld.md). Assumes the
[platform foundation](../00-platform-foundation.md) is built (tables, webhook
routes, projector skeleton, `GET /api/paywall/config`, manual-grant routes,
RevenueCat client, Stripe checkout). Only season-pass deltas below. Everything
dark behind `monetize.season_pass`.

## 1. Flag registration

`backend/feature_flags.py` → append to `FLAG_KEYS` (foundation registers the other
`monetize.*` keys; add only if not already present from the foundation build):

```python
# Monetization — Season Pass (docs/plans/monetization/season-pass/)
"monetize.season_pass",
```

Default False via `DEFAULT_FLAGS` comprehension (no other edit needed — the proxy
resolves attributes dynamically). Flip in `config/features.json` per rollout.

## 2. Backend

### 2.1 `backend/season_skus.py` (new, small)

Static data + two pure helpers; imported by the projector and the paywall route.

```python
SEASON_SKUS = {
    # sku: (league_year, season_end UTC, kind)
    "ftf_season_pass_2026":          {"year": 2026, "season_end": "2027-07-31T23:59:59Z", "kind": "season"},
    "ftf_rookie_pass_2027":          {"year": 2027, "season_end": "2028-07-31T23:59:59Z", "kind": "rookie"},   # PRD §8.1
    "ftf_season_pass_2027_upgrade":  {"year": 2027, "season_end": "2028-07-31T23:59:59Z", "kind": "upgrade"},
    "ftf_season_pass_2027":          {"year": 2027, "season_end": "2028-07-31T23:59:59Z", "kind": "season"},
    "ftf_season_pass_2027_returning":{"year": 2027, "season_end": "2028-07-31T23:59:59Z", "kind": "returning"},
}

SEASON_CALENDAR = {
    2026: {"display_start": "2026-08-01", "early_bird_end": None,        "display_end": "2027-03-31",
           "rookie_start": "2027-04-01", "rookie_end": "2027-05-31"},
    2027: {"display_start": "2027-06-01", "early_bird_end": "2027-06-30", "display_end": "2028-03-31",
           "rookie_start": "2028-04-01", "rookie_end": "2028-05-31"},
}

def season_end(product_id) -> str | None: ...
def current_pass_slot(now) -> dict | None:   # → which kind/SKU the paywall shows today
```

Year rollover = one entry in each dict (HLD §4 checklist). No schema, no migration.

### 2.2 Projector case (foundation's webhook projector, `backend/entitlement_service.py` or wherever the foundation lands it)

Add a branch: `if product_id in SEASON_SKUS:` on grant-shaped events
(`INITIAL_PURCHASE` / `NON_RENEWING_PURCHASE` / `TRANSFER` / restore-derived):

- Upsert by `(user_id-or-account_id, product_id)` — repeated restores/webhook
  replays never create a second row (belt on top of `event_id` idempotency).
- `entitlement="pro"`, `source="season_pass_iap"`, `expires_at=season_end(product_id)`.
- **Post-season restore rule:** if `season_end < now` → write/refresh the row with
  `status="expired"` (audit trail, powers returning-buyer detection) and never
  `active`. This is the whole "store never expires, server does" mismatch in one
  line — year-labeled SKU makes it defensible.
- `REFUND` → `status="refunded"` on the matching row.
- Emit `record_event`: `season_pass_purchased` / `rookie_pass_purchased` /
  `pass_upgrade_purchased` by `kind` (props: `sku`, `price_tier`); plus `pass_rebuy`
  when an earlier-year `season_pass_iap` row exists for the same account.
- Runs regardless of `monetize.season_pass` (HLD §7 — record money even while dark).

Milestone loop (foundation §5 reward granting, gated by `growth.referral`): when a
referrer reaches **8 activated leaguemates in one league** (same activation
definition + fraud controls as foundation), insert
`source="promo_referral"`, `metadata={"program":"milestone_season_pass","year":Y}`,
`expires_at=season_end` of the current season SKU; cap: one per user per season
(check metadata before insert). Emit `pass_milestone_earned`.

### 2.3 Paywall config route (foundation's `GET /api/paywall/config` in `backend/server.py`)

Insert the seasonal selection step (HLD §2 order). Pseudocode:

```python
if flags["monetize.season_pass"]:
    slot = current_pass_slot(now)                       # None outside all windows
    if slot and not caller_entitled:
        if has_row(caller, kind="rookie", year=slot.year, active=True):
            options.add(upgrade_sku(slot.year))         # upgrade ONLY (no full pass)
        elif has_prior_year_pass(caller, slot.year):
            options.add(returning_sku(slot.year))       # substitutes for standard SKU
        else:
            options.add(standard_sku(slot))             # season or rookie per calendar
        hero = "season_pass" if slot.kind == "season" and in_draft_ramp(now) else "annual"
```

Response deltas (additive, non-breaking):

```json
{
  "options": [
    {"slot": "decoy", "sku": "ftf_pro_monthly", "display_price": "$4.99/mo"},
    {"slot": "hero", "sku": "ftf_season_pass_2026", "display_price": "$19.99",
     "label": "2026 Season Pass", "sublabel": "Everything Pro. All season. One price.",
     "access_ends": "2027-07-31", "urgency": {"deadline": "2026-09-07", "copy": "Price locks in for the season"}},
    {"slot": "anchor", "sku": "ftf_founder", "display_price": "$79"}
  ],
  "season": {"year": 2026, "early_bird": false}
}
```

`access_ends` is mandatory for pass options — the client must show the expiry at
point of sale (PRD §7 mismatch mitigation). `urgency.deadline` is always a real
calendar date (no synthetic timers — Chalkline honesty + research: fake timers burn
trust).

### 2.4 Manual comps

No new route. Operator comps a pass via foundation §3:

```bash
curl -s -X POST https://…/api/admin/entitlements/grant \
  -H "X-Cron-Secret: $CRON_SECRET" -H "Content-Type: application/json" \
  -d '{"user": "mattkmurphy", "entitlement": "pro",
       "expires_at": "2027-07-31T23:59:59Z", "note": "podcast comp — 2026 pass"}'
```

(Convenience later, if wanted: accept `"season": 2026` sugar that resolves
`expires_at` server-side — not required to ship.)

### 2.5 Stripe (web) — `backend/server.py` webhook + `web/` checkout page

- One Stripe Price per season SKU; `checkout.session.completed` metadata carries the
  logical `product_id` → same §2.2 projector branch.
- Returning-buyer coupon: server issues the promo code only when
  `has_prior_year_pass` (same check as iOS display gating) — never a public code.
- Web upsell page (`web/` — link from paywall/account surface) lists the same
  options as `/api/paywall/config` (single source; page fetches the config).

## 3. Mobile (`mobile/src/`)

- **PaywallScreen (foundation-built):** render strictly from `/api/paywall/config`
  options — no client-side SKU literals. Pass options render `access_ends`
  ("Access through Jul 31, 2027") under the price, and the urgency line when
  present. Purchase via RevenueCat as any non-consumable; on success, refetch
  `GET /api/me/entitlements` (server row is truth, foundation §2.3).
- **Upgrade flow:** no separate screen. Rookie-pass holders opening the paywall see
  the upgrade option in the hero slot (config-driven, §2.3). Entry points: the
  standard paywall triggers + a one-line upsell row on rookie-adjacent surfaces
  (`PickAnchorScreen`, `QuickSetTiersScreen`) — `TickLabel`-style row, ice action
  chevron, shown only when config offers the upgrade SKU. No new nav routes.
- **`components/SeasonCountdown.tsx` (new, small):** presentational; props
  `{deadline: string, copy: string}` from config urgency. Chalkline terms: chalk
  text on ink, **flare** accent for the date (informational highlight — flare is
  never an action color), ice only on the adjacent CTA button, radius ≤ 8px, no
  gradients/emoji, days-granularity ("18 days") — no ticking seconds theatrics.
  Used inside the paywall hero card and the win-back card.
- **Win-back surface:** on `entitlements` refetch where a previously-active pass is
  now expired, Settings account section + one-time card on Trades show "Your 2026
  Pass has ended" with the next-season option from config. Fires `pass_expired_seen`
  once (AsyncStorage latch).
- **Settings account section:** if entitled via pass, show "2026 Season Pass —
  access through Jul 31, 2027" (SettingsScreen account matrix already renders
  per-session state; add the entitlement row).
- **Share cards** (foundation §5 renderer): when `monetize.season_pass` is on and
  the calendar is in a sales window, card footer carries the seasonal urgency line
  ("Deadline SZN — 2026 Passes close Mar 31") + the invite deep link. Copy from
  config, not hardcoded.

## 4. Edge cases (behavior spec)

| Case | Behavior |
|---|---|
| Purchase Jul 30 (season ends Jul 31) | Granted; 1 day of access. Prevented in practice: SKU off paywall after `display_end` (~Mar 31) and removed from sale in ASC (HLD §4.6). If it still happens (stale store cache), it's honest — the label says 2026 — and operator can comp/refund on request. |
| Refund after season start | RC `REFUND` → `status="refunded"` → access drops at next entitlements read. No clawback of already-seen content; no proration (Apple decides refunds, not us). |
| Upgrade proration | None — fixed-price upgrade SKU ($7.99, PRD §8.2). Rookie $9.99 + upgrade $7.99 = $17.98 total, between early-bird and full. No store-side proration exists for non-consumables; do not build server math. |
| Upgrade bought without rookie pass | Display gating prevents it; if it lands anyway (web race, shared link), projector grants the full season entitlement — buyer got a discount, not an error. Log it; no refusal path. |
| Restore, new device, mid-season | RC restore → grant-shaped event → upsert same row → active until `season_end`. Full remainder, no re-charge. |
| Restore after Jul 31 | Row written/refreshed `status="expired"`; **no access** (§2.2 rule). Client shows "2026 Pass (ended Jul 31, 2027)" + current-season purchase option. |
| Family Sharing | OFF on all pass SKUs at ASC creation (one-way toggle — never enable). No server handling needed. |
| Pass + active Pro sub | Coexisting rows, resolution ORs; paywall hides purchase when entitled (HLD §5); no auto-refund. |
| Milestone earned while dark (`growth.referral` off) | No grant occurs (loop gated at granting, foundation §5); qualification is re-checked when flag flips — activations aren't lost, referral rows persist. |
| Webhook replay / duplicate events | `event_id` unique + upsert-by-(user, product_id): one row, stable expiry. |
| `monetize.season_pass` flipped OFF mid-season | SKUs vanish from paywall; existing rows unaffected (checks consult `monetize.entitlements` only). |

## 5. API examples

`GET /api/me/entitlements` (pass holder):

```json
{"pro": true,
 "sources": [{"source": "season_pass_iap", "product_id": "ftf_season_pass_2026",
              "expires_at": "2027-07-31T23:59:59Z"}],
 "expires_at": "2027-07-31T23:59:59Z",
 "flags_snapshot": {"monetize.season_pass": true}}
```

Milestone grant row (via `GET /api/admin/entitlements?user=…`):

```json
{"entitlement": "pro", "source": "promo_referral", "product_id": null,
 "status": "active", "expires_at": "2027-07-31T23:59:59Z",
 "metadata": {"program": "milestone_season_pass", "year": 2026, "league_id": "…"}}
```

Paywall config: see §2.3.

## 6. Test plan

**pytest — `backend/tests/test_season_pass.py`** (fixtures: foundation's webhook
fixture + frozen clock):

- `test_projector_season_sku_expiry_is_season_end_not_duration`
- `test_projector_purchase_jul30_grants_one_day`
- `test_projector_restore_mid_season_upserts_single_active_row`
- `test_projector_restore_post_season_writes_expired_no_access`
- `test_projector_refund_sets_refunded_and_drops_access`
- `test_projector_upgrade_sku_grants_full_season_without_rookie_row`
- `test_projector_rebuy_event_fired_for_prior_year_buyer`
- `test_projector_runs_while_flag_dark`
- `test_paywall_config_hides_pass_when_flag_off`
- `test_paywall_config_returning_sku_substituted_for_prior_buyer`
- `test_paywall_config_rookie_holder_sees_upgrade_only`
- `test_paywall_config_entitled_caller_sees_no_purchase_options`
- `test_paywall_config_outside_window_omits_pass`
- `test_paywall_config_early_bird_window_2027`
- `test_milestone_grant_season_end_expiry_and_once_per_season`
- `test_manual_grant_pass_comp_via_admin_route`

**Maestro — `mobile/.maestro/`** (display flows only; IAP sandbox purchase is
manual QA per eng-qa charter — Maestro can't drive the App Store sheet):

- `07-paywall-season-pass-display.yaml` — flag on, sales window: paywall shows 3
  options, pass hero card shows price + "Access through Jul 31" + countdown; no
  ticking timer.
- `08-paywall-season-pass-dark.yaml` — flag off: paywall shows Pro-only options,
  no pass strings anywhere.
- `09-season-pass-settings-state.yaml` — entitled fixture session: Settings shows
  pass row with end date; paywall entry shows entitled/manage state.
- `10-rookie-upgrade-row.yaml` — rookie-holder fixture: PickAnchor/QuickSet upsell
  row present; tapping opens paywall showing upgrade SKU only.

**Manual QA (eng-qa pre-ship):** sandbox purchase, sandbox restore on second
device, sandbox refund propagation, web Stripe purchase unlocking iOS session.

## 7. Docs-to-update checklist (on build, per root CLAUDE.md table)

- `docs/config-reference.md` — `monetize.season_pass` flag (foundation adds the
  secrets; nothing new here beyond the flag).
- `docs/api-reference.md` — paywall-config response deltas (`access_ends`,
  `urgency`, `season` block).
- `docs/cross-client-invariants.md` — season SKU id strings, `season_end` dates,
  `source` enum value `season_pass_iap`, urgency-copy source-of-truth = server
  config (clients must not hardcode).
- `docs/glossary.md` — Season Pass, Rookie Pass, league year, returning buyer,
  milestone unlock.
- `docs/data-dictionary.md` — only if foundation hasn't landed the `entitlements`
  table docs yet; no new columns from this plan.
- New ADR — "Season scope enforced server-side on non-consumable IAPs" (the
  store/server expiry mismatch + post-season restore rule) if not folded into the
  foundation's RevenueCat/server-truth ADR.
- `docs/runbook.md` — annual rollover checklist pointer (HLD §4) after the first
  real rollover.
