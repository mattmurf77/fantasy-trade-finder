# Rev-3 spec — the shop window rework (authored by the orchestrator, 2026-08-28)

> The buildable contract for the four `rulings-2026-08-28b.md` rulings.
> Where this conflicts with the rev-2 sections of prd.md / lld-delta.md,
> THIS WINS. Ships as v1.16.10. Everything not named here keeps its rev-2
> behavior (like/queue semantics, held dismiss + honest Undo + suppression
> set, chooser, analytics shapes, SHOP_MODE_GROUP, Chalkline).

## 1. Surface — pushed screen (supersedes LLD §0.3's inline strip)

- `ShopAssetScreen`, registered **unconditionally** in `RootNav` (house
  rule: the flag gates the entry point, not the route), pushed with
  `{assetId, assetName, leagueId, source}` params plus the resolved asset.
  `gestureEnabled: false` (rev-1 D-1: iOS interactive pop is a left-edge
  horizontal drag that would fight the pager).
- Mounts `<FeedbackFAB activeScreen="ShopAsset" aboveTabBar={false} />`
  (#188 — root-stack push; the tab-screen exemption no longer applies).
- Native back header ("‹" per the app's stack header) returns to the deck,
  which was never touched — no restore logic exists because nothing moves.
- **Entry unchanged:** give-side "More offers" on a deck card → 1 give
  asset: `navigation.navigate('ShopAsset', …)`; several: the chooser sheet,
  pick → navigate. `shopEnabled` conjunction unchanged
  (`trade.shop_asset && trade.asset_ideas && calc.merged_layout`).
- **DELETE the inline machinery**, don't strand it: the strip mount on
  `TradesScreen`, `shopAsset`/`shopOpen` state, the pan `.enabled(!shopOpen)`
  gate, the `dispositionDisabled` / VoiceOver / reason-tile / flag-button
  shop gates, the `topRawId` close-effect, the shop clears in
  `resetDeckForNewTargets`/`handleClearPin`, and the `onToastRetract`
  host wiring (the window owns its own Toast mount now — same retraction
  semantics, host = the screen itself). `ShopOffersStrip` becomes the
  screen's body component (rename or wrap; keep the internals — pager,
  suppression set, react-don't-race scrolls, empties).
- Analytics: `screen` prop on all shop events becomes `'ShopAsset'`;
  `shop_opened` still fires exactly once, now at the single navigate call
  site (the P-3 rule holds). Taxonomy comment updated; shapes unchanged.

## 2. Position filters on ALL modes (supersedes R-10's same-value-only)

- The chip row renders at the TOP of the window, above the mode chips, and
  applies to whichever mode is active. Domain: the league's positions
  (own position INCLUDED per R-2026-08-28-B; PICK excluded; #360 avoided
  positions omitted with the explanation line). Multi-select. Selection is
  one state shared across modes — switching modes keeps it.
- **Semantics per mode** with a selection {P…}:
  - `tier_up` (upgrade): ideas whose incoming headline piece plays P ∈ {P…}
    — "trade him (+ sweetener) for a better player at these positions."
  - `tier_down` (downgrade): incoming headline piece plays P ∈ {P…}.
  - `same_value` (lateral): as today (swap_positions).
  - Empty selection = each mode's default: upgrade/downgrade at his own
    position (today's #198 behavior, byte-identical request); same-value
    = his own position under tier scope (§3), **with auto-widen on zero**
    (OPERATOR-RULED 2026-08-28, multiple-choice answer): if the
    own-position tier sweep returns zero laterals, the client
    automatically re-requests with ALL offerable positions and renders a
    visible notice line ("Nothing at WR — showing all positions"); the
    user's own chip selections always win over the auto-widen (any
    explicit selection disables it). Client-side only — no backend
    change; the widened request simply sends the full position set.
- **Backend:** `swap_positions` now also constrains the `upgrade` and
  `downgrade` groups when present (supersedes HLD D-3's lateral-only rule
  and PRD R-11's "never affected"). Absent ⇒ all three groups behave
  exactly as today — additive, old clients byte-identical. Validation
  unchanged (named 400s, PICK rejected). Mirror both give/receive
  directions. New tests: filters-apply-per-group, absent-is-identical
  (assert against existing expected shapes), never-cross-contaminates
  (upgrade filter never changes lateral results and vice versa).

## 3. Same value = same TIER (supersedes the ±band + #108 gate for this group)

- New optional request field on `POST /api/trades/asset-ideas`:
  `lateral_scope: "band" | "tier"`, default `"band"` (= today, for every
  existing caller including the single-pin panel — the scoping decision in
  rulings §R-4). The shop client always sends `"tier"`.
- `"tier"` semantics: the lateral pool is every asset whose tier (per
  `ranking_service.tier_for_elo` against `tier_config.json`, in the
  league's scoring format, position-appropriate bands) EQUALS the pinned
  asset's tier. The ±10% band and the #108 `user_gain_epsilon` gate do
  NOT apply to this group under `"tier"`. Both directions mirrored.
  Everything downstream (idea shaping, counterparty resolution, caps,
  dedupe, D-067 cooldown exclusion) unchanged.
- Tier is position-banded in tier_config — the cross-position comparison
  uses each asset's tier INDEX (tier 1..8) equality, not raw ELO overlap;
  verify how tier indices are exposed and state the exact comparison in a
  code comment. If tier indices are not comparable cross-position in the
  current config, STOP and flag before building — do not invent a mapping.
- Validation: invalid `lateral_scope` values → named 400.
- Docs: api-reference row; the fairness-gate removal for this group is a
  user-facing semantics change — note it in the flag comment and the
  api-reference entry ("same-value under tier scope shows tier-mates, not
  band-mates; the card's two-board verdict still prices each idea").
- Expected effect: the Same value default (own position, tier scope) lands
  populated far more often; the honest empty + per-mode counts remain for
  the cases it still can't fill.

## 4. Suite + evidence

- `check-shop-deck.js`: delete the inline-era assertions (pan gate, deck-
  holds-still k-section, l-section state seams, host toast retract wiring),
  add: route registered unconditionally + gestureEnabled false; FeedbackFAB
  mounted on the screen; entry navigates (no strip mount on TradesScreen —
  assert its ABSENCE); filter row applies to all three modes (one shared
  selection identifier); `lateral_scope:"tier"` always sent by the shop
  client and `swap_positions` still omitted when empty; screen prop
  'ShopAsset' on all four events with exactly one shop_opened emitter.
  Everything kept from rev-2 that still applies (mode map, counter honesty,
  suppression set, undo-never-lies, Chalkline scan, label source).
- Backend tests as §2/§3 name them; full pytest green.
- TestFlight checklist rewritten for the window (back-nav step replaces the
  deck-holds-still step; tier-width step added: "a Same value result may
  differ from his value noticeably — that is the tier, and the card's
  verdict prices it honestly").
- Sabotage: ≥4 per agent, red→green, snapshots not `git checkout --`.

## 4a. Ruling confirmations (2026-08-28 multiple choice)

Item 2 (window) CONFIRMED · item 3 default = **own position, auto-widen on
zero** (changed from the plain own-position assumption) · item 4 scope
CONFIRMED (shop-only parameter). Item 1 (merge/Wave B) remains parked; the
operator asked for confirmation that `calc.inline_home` reuses the manual
calc UI — verified: `TradeBuildCanvas.tsx:4` imports and mounts the SAME
`InLeagueCalculator`, per D-158's functionality-by-construction rule, and
the parity audit is `docs/reviews/2026-08-27-calc-vs-guided-finder-audit.md`.

## 5. Sequencing

Backend (§2 params + §3 tier scope + tests) and mobile (§1 window + §2 UI +
suite) are file-disjoint and run in parallel. QA static pass after both.
Ship = PR → CI green → operator's word (NOT auto-merged; the operator
explicitly gates this one). Version 1.16.10 bump rides the PR.
Wave B / `calc.inline_home` remains PARKED — not in this round.

## 6. Scoped tour gate (2026-08-28, post-ruling addition)

Context: after §4a was written the operator lit `calc.inline_home` (the
guided Trades page hosts the manual calculator inline, live in prod) and
ruled it tour-free — "disable the tour for the find a trade and manual calc
since both pages are retired in favor of this one for now." The only lever
at the time was flipping `onboarding.guide_v2` false **globally**, which
also killed guidance on unrelated screens (Rank, Matches, LeagueSummary,
QuickSetTiers, …). That global off is live and recorded as temporary in
`config/features.json` (`_comment_inline_home`) and the pinned test in
`backend/tests/test_events_api.py`.

**Shipped mechanism** — one choke point, D-158's shape (suppress at the
START; the beat is never begun):

- `useGuide.requestStep` refuses any beat declaring `screen: 'Trades'`
  while `calc.inline_home` is on (`inlineHomeTradesTourFree()` in
  `mobile/src/state/useGuide.ts` — a bare flag read on purpose, so killing
  the onboarding master can never un-suppress the merged page). The refusal
  is silent and side-effect-free: no bubble, no arbiter claim, no `seen`
  mark, no retirement, no suppression episode — every Trades beat stays
  unspent for Wave B to retarget.
- Every start/advance path funnels through it: TradesScreen's auto-start
  and chain effects, spine sequences arriving from other screens, and the
  calc-tour runner's deck half (`calcTourDeckArrived` → `requestAt`). The
  gate sits **above** the #384 tour-owned exemption, so a mid-run tour
  crossing into Trades has its deck beats (n19–n24/n23b) refused too; the
  runner steps over each refusal and `endTour` tears down any standing
  bubble and releases the interrupt hold — the run ends cleanly, never a
  half-open overlay. The pushed calculator keeps its own D-158 guards
  (auto-start + "Show me around" both suppressed); beats on every other
  screen are untouched.
- Suite: `check-shop-deck.js` §t (t1–t8) transpiles and **executes** the
  real engine — start suppression + silence, Trades-only scope, the
  tour-owned arrival path, the flag-off re-light, gate placement, and the
  deck-half → `screen: 'Trades'` linkage.

**Re-light plan**: once v1.16.10 is the installed base, flip
`onboarding.guide_v2` back to true in `config/features.json` and flip the
pinned expectation in `backend/tests/test_events_api.py` with it (one
operator-gated change, not part of this build). Guidance then returns
everywhere **except** the merged Trades page, which this gate keeps
tour-free until Wave B retargets its beats.
