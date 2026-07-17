# Founder Lifetime — HLD

Companion to [prd.md](prd.md). Builds on
[../00-platform-foundation.md](../00-platform-foundation.md): entitlements schema
(§2.1), resolution (§2.2), API (§2.3), manual grants (§3), IAP/RevenueCat + Stripe
rails (§4), share cards (§5). Nothing there is re-specified here.

## 1. Offer lifecycle state machine

The state is **derived**, not stored — computed from the flag, the cap count, and
`monetize.paywall`:

```
                    flag ON                       remaining == 0
  PRE-WINDOW ───────────────────► WINDOW-OPEN ──────────────────► CAP-HIT
  (flag OFF,                      (flag ON,                       (flag ON,
   0 purchases)                    remaining > 0)                  SKU auto-hidden)
                                        │                              │
                                        │  flag OFF (operator)         │  flag OFF
                                        ▼                              ▼
                                     CLOSED  ◄─────────────────────────┘
                                  (flag OFF, >0 purchases)
                                        │
                                        │  monetize.paywall ON (public launch)
                                        ▼
                                   ANCHOR-MODE
                        (founder row renders sold-out/closed
                         on the 3-option paywall; not purchasable)
```

- **The flag flip IS the window mechanism.** `monetize.founder` OFF→ON opens; ON→OFF
  closes regardless of count. No scheduled jobs, no stored state row.
- **CAP-HIT is automatic**: paywall config computes `remaining` per request; at 0 the
  SKU stops being offered everywhere in the same response cycle. The operator then
  flips the flag off at leisure (belt and suspenders).
- **ANCHOR-MODE is not a stored state either**: it is CLOSED ∧ `monetize.paywall` ON.
  The paywall-config route includes a non-purchasable `founder_anchor` block (D6) so
  the ceiling anchor + "100/100 — closed" social proof render without the founder
  flag ever coming back on.
- Restore-purchases works in **every** state (non-consumable, guideline 3.1.1): the
  webhook projector accepts founder events regardless of flag/cap, because a restore
  or delayed sandbox→prod event is not a new sale.

## 2. Cap + window through paywall config

`GET /api/paywall/config` (foundation §2.3) is the single choke point — clients never
compute founder availability locally.

```
founder block (in paywall config response):
  state:      "hidden" | "open" | "cap_hit" | "anchor"
  product_id: "ftf_founder"            (or A/B arm SKU)
  price_display, headline, sub_line    (server-driven copy — value-first,
                                        dev-support second; no app release to re-word)
  cap:        100
  remaining:  <live count>             (clamped ≥ 0; shown honestly in UI)
  checkout_url: <stripe link>          (window phase only; tokenized per session/arm)
```

- `remaining = cap − COUNT(active founder purchase rows)` (exact query LLD §3.2).
  Manual comps excluded per D4. Refunded rows don't count (slot reopens, D7).
- Clients render the count as-is ("31 of 100 left"). No client-side caching beyond
  the normal config fetch; a stale count is corrected at purchase time by the
  oversell policy (LLD §7.1), never by rejecting a completed purchase.
- Flag OFF → `state: "hidden"` pre-purchases, `"anchor"` once CLOSED ∧ paywall ON.

## 3. Badge data model

**The `entitlements` table is the only truth. A Founder badge is the presence of an
active founder row — there is no badge table, no user column, no cached boolean.**

```
is_founder(user_id) := ∃ row ∈ entitlements resolved per foundation §2.2
    (user_id OR its account — survives Sleeper re-links)
  where status = 'active'
    and expires_at IS NULL
    and (   source = 'founder_iap'                        -- Apple rail
         or (source = 'stripe'       and founder product) -- web rail (window phase)
         or (source = 'manual_grant' and founder marker)) -- operator comp
```

- "Founder product / marker" concretely = `product_id` in the founder SKU set, or
  `metadata.founder = true` (manual comps). Centralized in one backend helper; no
  surface re-implements the predicate (LLD §3.1).
- **Founder number** is assigned once at grant time (monotonic sequence across
  purchases and comps, in `metadata.founder_number`) — display data, not truth.
- Revocation/refund/deletion → row inactive/gone → badge disappears everywhere on
  next read. Nothing to un-cache.
- Consequence of account-keying: the badge follows the account through Sleeper
  re-links and the P2.6 merge flow with zero founder-specific code — it rides
  foundation resolution.

## 4. Purchase rails by phase

| Phase | Rail | Why |
|---|---|---|
| Window (TestFlight) | **Stripe Checkout** (foundation §4 web rail), reached via outbound link on the in-app offer | TestFlight IAP is sandbox-only — cannot take real money. Stripe row is account-keyed and unlocks iOS per foundation cross-platform rule |
| Public launch → close | `ftf_founder` IAP via RevenueCat (primary) + Stripe on web | Normal rails |
| After close | None (restore only) | Window closed forever |

Both rails land in the same projector and produce equivalent perpetual rows; only
`source`/`metadata.rail` differ. US external-link caveat (SCOTUS ~mid-2027) is a
window-phase-only dependency — acceptable because the window is weeks long.

## 5. A/B price mechanics (D1)

- **RevenueCat Experiments** assigns each user an offering: `founder_default`
  (contains `ftf_founder`, $79) vs `founder_b` (contains `ftf_founder_b`, $59).
  Apple prices are per-SKU, so two SKUs are required; both map to the same
  RevenueCat "pro" entitlement and the projector treats both as founder products.
- Paywall config echoes the assigned arm (`price_arm` in the founder block) so web
  and events stay consistent; the Stripe `checkout_url` is generated per-arm.
- Cap counts both arms together. Arm recorded on `founder_purchased` events and in
  row metadata → readout is net-revenue-per-exposed-user by arm.
- Kill switch: ending the experiment collapses everyone to `founder_default`; no
  client change (server-driven offerings).

## 6. Founders-wall surface

- **Backend:** one public read route returning opted-in founders in number order
  (`founder_number`, display name/avatar or anonymous "Founder #N"). Public (no
  session) — it's social proof; serves web, app, and landing page alike. Always
  available once ≥1 founder exists, independent of `monetize.founder` (the wall is
  permanent; the *offer* is windowed).
- **Web:** static-style page `web/founders.html` (Chalkline; flare used for badge
  chips only — informational), linked from the landing page during/after the window.
- **In-app:** a wall section reachable from the offer surface and (post-close) from
  the paywall's anchor row; renders the same route payload. No new tab.
- Opt-in captured at purchase (client → one settings-style POST; LLD §4.4) and
  editable later from Settings.

## 7. Sub-overlap detection

Foundation projector extension: after applying any founder grant, and after applying
any sub renewal for a user who is a founder, check for the overlap
(active `apple_iap`/`stripe` sub row with future `expires_at` ∧ active founder row).
Overlap → emit `founder_sub_overlap` event + expose `sub_overlap: true` in
`GET /api/me/entitlements`. Clients own the prompt UX (deep link to Manage
Subscriptions / Stripe portal). Server never cancels anything — StoreKit can't, and
Stripe auto-cancel on the user's behalf is a support trap; the honest move is the
prompt. Detection at projector time (not read time) keeps the read path cheap; the
entitlements response just replays the latest computed state.

## 8. Flag gating summary

| Flag | Founder behavior |
|---|---|
| `monetize.founder` | Offer visibility + purchasability (the window). OFF hides the offer; never hides badge/wall/restore |
| `monetize.entitlements` | Foundation master switch — OFF means founder rows sit dormant like every grant |
| `monetize.paywall` | Required for any purchase UI incl. the founder offer sheet; drives anchor-mode |
| `growth.referral` | Reads `is_founder` for first-access cohort (pm-growth's program) |

Badge rendering, wall, and restore are deliberately **not** behind `monetize.founder`
— founders keep recognition after the window closes forever. Badge surfaces are
gated only by data presence (`is_founder` in the payload).

## 9. What this plan adds vs the foundation (delta summary)

1. Founder block + remaining-count logic in the paywall-config route.
2. Projector: non-consumable purchase case, founder-number assignment, refund slot
   handling, sub-overlap flagging.
3. `is_founder` helper + founder fields on entitlements/profile payloads.
4. Founders-wall route + web page + in-app section; wall opt-in bit.
5. Founder marker on the manual-grant route.
6. Badge chips: mobile ProfileScreen, TradeCard, web profile.
7. Share-card variant "Founder #N" (rides foundation §5 renderer).
8. Events per PRD §5.

Everything else (tables, webhooks, grants auth, flags plumbing, RevenueCat/Stripe
integration) is the foundation, unchanged.
