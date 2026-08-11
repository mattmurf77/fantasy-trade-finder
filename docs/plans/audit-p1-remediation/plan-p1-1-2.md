# P1-1 + P1-2 — Share artifacts carry no link, and two complete landings have zero callers

> Build plan for audit findings **P1-1 (A-10)** and **P1-2 (A-11)**
> (`docs/business/product/2026-08-09-mobile-ux-audit/04-priority-backlog.md` §P1,
> `06-resolutions.md` rows A-10/A-11).
> Branch `p1-remediation-2026-08-11`, worktree `ftf-p1-remediation` @ `ab9368f`.
> Planned **after** `p0-remediation-2026-08-10` merges to `main`; this plan rebases onto it.
>
> **Full feature gates apply.** This touches a deep-link route alias (route surface) and the
> analytics taxonomy (event surface). Per root `CLAUDE.md` §Conventions → Feature gates
> bright line, neither is a "quick fix"; no express lane was declared, so the four gates stand.

## Table of contents

- [Verified current state](#verified-current-state)
- [Design](#design)
- [Exact change list](#exact-change-list)
- [Surface changes](#surface-changes)
- [Maestro delta](#maestro-delta)
- [Docs impact table](#docs-impact-table)
- [Test plan](#test-plan)
- [Risks and cross-item collisions](#risks-and-cross-item-collisions)
- [Operator checkpoints](#operator-checkpoints)

---

## Verified current state

Every claim below was re-read in **this worktree on 2026-08-11**. Line numbers are current,
not the audit's. Comments were never taken as evidence — the constant or branch that decides
behaviour was read in every case.

### P1-1 — the shared PNG

| Fact | Evidence |
|---|---|
| `ShareTradeImage` renders an off-screen Chalkline card and captures it to a PNG | `mobile/src/components/ShareTradeImage.tsx:60-64` (`captureRef`), off-screen surface `:115-124` |
| The card's only footer is a **text watermark with no URL** — literally the string `Dynasty Trade Finder` | `ShareTradeImage.tsx:122`, style `:157-164` |
| iOS shares the image **alone** — `Share.share({ url: uri })`, no `message` key, so nothing textual travels with the PNG | `ShareTradeImage.tsx:65` |
| Android shares `fallbackText` only (core RN `Share` is text-only there) | `ShareTradeImage.tsx:55-59` |
| Capture failure falls back to `fallbackText`, which also contains **no URL** in either host | `ShareTradeImage.tsx:66-72`; hosts' `fallbackText` at `TradeCalculatorScreen.tsx:876-883` and `InLeagueCalculator.tsx:790-797` |
| Two hosts, both live: live-mode calculator and In-league calculator | `TradeCalculatorScreen.tsx:44, 867-884`; `InLeagueCalculator.tsx:30, 781-798` |
| The button is the app's only image share; `testID="calc.share-image"` | `ShareTradeImage.tsx:111` |
| The **server-side** OG cards already draw a URL footer — so the app's own PNG is the odd one out | `backend/og_image.py:170-174` (`_draw_footer` → `"Fantasy Trade Finder · fantasy-trade-finder.onrender.com"`) |

**Confirmed: the audit is right, and the fix surface is a single `<Text>` plus one `Share.share`
call.** The hard part is not drawing the line — it is deciding *which URL* and getting it into
the view **before** `captureRef` runs (see [Design §3](#3-ordering-mint-before-capture)).

### P1-2 — the two landings

**Package landing — built, tested, and caller-less.**

| Fact | Evidence |
|---|---|
| `POST /api/share/package` exists, is session-authed, rate-limited 20/user/hour, ≤5 ids/side, and returns `{ok, short_id, url:"/s/p/<id>", og_image:"/og/p/<id>.png"}` | `backend/server.py:16828-16876` |
| `GET /s/p/<short_id>` renders the OG landing | `backend/server.py:16878-16899` |
| `GET /og/p/<short_id>.png` renders the card | `backend/server.py:16901-16912`, `backend/og_image.py:551-591` |
| All three 404 unless `growth.share_landing` is enabled — and it is **ON** in defaults *and* in the release fixture | gates at `server.py:16838, 16881, 16904`; `config/features.json:125` = `true`; `backend/tests/fixtures/flags/release.json:126` = `true` |
| The flag is client-exposed, so mobile can read it | `backend/feature_flags.py:272` (client-flags block) |
| Storage + retention are already documented | `backend/database.py:1417, 10653-10654`; `docs/data-dictionary.md:856` |
| A full pytest suite already covers the route | `backend/tests/test_share_package.py` (11 cases) |
| **Zero callers anywhere in `mobile/`** | `grep -rn "share/package" mobile/ --include=*.ts --include=*.tsx` → no matches |
| **Zero callers in `web/` or `extension/`** | same grep across the repo returns only `backend/`, `docs/`, `FEATURES.md` |

**Tier landing — built, unflagged, and caller-less on _both_ clients.**

| Fact | Evidence |
|---|---|
| `GET /s/tiers/<pos>/<username>` renders an OG wrapper; `?fmt=` respected | `backend/server.py:16759-16779` |
| `GET /og/tiers/<pos>/<username>.png` renders the board card | `backend/server.py:16663-16680`, `backend/og_image.py:288-336` |
| **Neither route is flag-gated** — no `is_enabled` call in either (`/s/p/*` has one; this pair does not) | `server.py:16759-16779`, `:16663-16680` — read line by line, not inferred |
| Unknown username → 404 placeholder PNG; no tiers yet → an honest "No {POS} tiers yet" card | `og_image.py:311-316, 338-345` |
| **Zero mobile callers** | `grep -rn "s/tiers\|og/tiers" mobile/` → no matches |
| **Zero web callers** — `buildTierShareUrl` and `buildTradeShareUrl` are *defined and never invoked* | `web/js/app.js:5285-5295`, `:5296-5301`; `grep -n "buildTierShareUrl\|buildTradeShareUrl" web/` returns only the two definitions |
| `docs/api-reference.md:544` already documents the route as a share page | — |

**The stale comments — there are TWO, not one.**

| Location | Text | Why it is false |
|---|---|---|
| `mobile/src/screens/TradeCalculatorScreen.tsx:523-527` | *"A hand-built calculator trade has no server object (no `/s/` route exists for arbitrary packages — documented W3/backend handoff), so the site root is the landing page."* | `POST /api/share/package` + `/s/p/<id>` shipped at `server.py:16828-16899`, flag ON. This is the comment the audit named. |
| `mobile/src/screens/TradesScreen.tsx:2735-2741` | *"Liked-but-unmatched trades have no server object yet (no `/s/` route exists for them — documented W3/backend handoff), so those fall back to the site root."* | Same route, same falsehood. **The audit missed this one.** |

Both comments were written when the route genuinely did not exist and were never revisited when
W3B landed it. This is the same comment-over-code failure class as finding A-33 and as P0-3's
`InviteLeaguematesBanner.tsx` finding.

### Analytics reality check (not in the audit; both are silent-drop bugs)

| Fact | Evidence |
|---|---|
| `calc_trade_shared` is fired by the calculator but is **not** in `ALLOWED_CLIENT_EVENTS` — the whole envelope is accepted-and-dropped | fired at `TradeCalculatorScreen.tsx:535`; allowlist `backend/analytics_taxonomy.py:38-99` (no such name); drop at `backend/analytics_ingest.py:379-383` |
| `trade_card_shared` **is** allowed, but its prop allowlist is `{trade_id, channel}` — and TradesScreen sends `{trade_id, landing}`, so **`landing` is silently stripped** | fired at `TradesScreen.tsx:2760-2766`; props `analytics_taxonomy.py:222`; strip at `analytics_ingest.py:384-389` |
| Neither client ever sends `channel`, so the one allowed discriminator is always absent | grep of both share call sites |

**Consequence: there is no usable telemetry on any share in the product today.** Whatever this
plan ships must register names *server-side first*, and the "shares convert zero" premise
cannot currently be measured either way.

### The universal-link trap (not in the audit; blocks the tiers half)

| Fact | Evidence |
|---|---|
| AASA claims `/s/*` wholesale, so **every** `/s/…` URL opens the app on an installed device rather than Safari | `backend/server.py:8094-8107` (`{"/": "/s/*"}` in `components`, `"/s/*"` in `paths`) |
| `rewriteUniversalPath` aliases only `/s/trade/<id>` and `/s/p/<id>` | `mobile/src/utils/deepLinks.ts:189-199` |
| **`/s/tiers/<pos>/<username>` has no alias** | same function — read in full; no third branch |
| An unaliased `/s/…` path is unroutable → `navigate('Main')` + a "link didn't work" fallback toast | `deepLinks.ts:353-364` (`_routePathV2` false → `_notifyLinkFallback`) |
| `ux.deeplink_router_v2` is ON, so that is the live path | `config/features.json`, `backend/tests/fixtures/flags/release.json` |
| A Tiers path already exists in the route table: `app/rank/tiers` | `deepLinks.ts:131-146` (`Main` → `Rank` → `Tiers: 'tiers'`) |
| `TiersScreen` ignores route params entirely — `position` is local state defaulting to `'QB'` | `mobile/src/screens/TiersScreen.tsx:113-124` (`useState<BoardTab>('QB')`, no `useRoute`) |

**Consequence: shipping a tier-share button without a `rewriteUniversalPath` entry would ship a
growth loop that greets every recipient-with-the-app with an error toast.** The alias is not
optional polish; it is part of the fix.

### The privacy asymmetry (not in the audit; a policy question, not a bug)

| Fact | Evidence |
|---|---|
| `/u/<username>` public profiles are dark behind **two** gates | `backend/server.py:17550-17566` — `profiles.public_pages` (`config/features.json:19` = `false`) plus a per-user opt-in when `profiles.user_toggle` is on (`features.json:130` = `false`) |
| The most recent shipped commit on `main` deliberately *hid* the Settings public-profile row | `git log` — `20548ff #221: hide Settings public-profile row … web pages remain dark behind profiles.public_pages` |
| `/s/tiers/<pos>/<username>` + `/og/tiers/...` publish a user's ranked board **by username, with no flag and no opt-in** | `server.py:16759-16779`, `:16663-16680` — verified no `is_enabled`, no consent read |

So the product's stated privacy posture (profiles dark) and one of its live routes disagree.
Wiring the tier share makes that publication *user-initiated*, which is a mitigation but not an
answer. See [Operator checkpoints](#operator-checkpoints) §OC-3.

### Test-harness reality check

| Fact | Evidence |
|---|---|
| No Maestro flow references `calc.share-image` or any share affordance | `grep -rn "share" mobile/.maestro/` → only prose uses of "shares"/"shared"; **no existing flow asserts the bug**, so nothing has to be un-asserted |
| The iOS share sheet is `UIActivityViewController` — out of process. Law 20 records that a native confirm "poisoned every later step" | `mobile/.maestro/README.md:159-166` |
| Deep links are unusable (`openLink` → SpringBoard confirm); launch-argument entry is the substitute | `mobile/.maestro/README.md:140-146` |
| `screens/manifest.json` binds our edits to four screens: `calc` ← `TradeCalculatorScreen.tsx` + `InLeagueCalculator.tsx`; `tiers` ← `TiersScreen.tsx`; `quick-set` ← `QuickSetTiersScreen.tsx`; `trades` ← `TradesScreen.tsx` | `screens/manifest.json` → `screens.<name>.source` |
| `ShareTradeImage.tsx` is in **no** manifest source list, and its card never renders on screen, so editing it alone triggers no capture staleness | same file; `ShareTradeImage.tsx:130` (`left: -9999`) |
| No jest in `mobile/` — verification is `tsc --noEmit` + Maestro + manual | `mobile/package.json` |

### Drift from audit

| # | Audit said | Actually |
|---|---|---|
| 1 | "The calculator even carries a stale comment saying the route doesn't exist" (singular) | **Two** stale comments with the same false claim: `TradeCalculatorScreen.tsx:523-527` **and** `TradesScreen.tsx:2735-2741`. The second is on the liked-but-unmatched path the audit itself calls "the more common case" (`02-tier-a-briefs.md:350`). |
| 2 | `/s/tiers/...` has "zero callers" (framed as a mobile gap) | Zero callers on **both** clients. `web/js/app.js:5285-5295` builds the URL and nothing ever calls the builder. The web half was written and abandoned too. |
| 3 | "OG infrastructure exists; this is a text layer and a string concat" (A-10, `06-resolutions.md:95`) | The text layer is real, the string concat is not: a *useful* link is a minted `/s/p/<id>`, which is an authenticated, rate-limited, failure-prone **async** call that must complete **before** `captureRef`. Effort is S only if the link is static; S–M for the minted link. |
| 4 | P1-1 and P1-2 are two findings | One mechanism. The `POST /api/share/package` call that fixes P1-2's first half **is** the URL that fixes P1-1. Building them separately would build the same thing twice. |
| 5 | (silent) | `calc_trade_shared` is dropped by the ingest allowlist and `trade_card_shared`'s `landing` prop is stripped — the shares that exist today are unmeasurable. |
| 6 | (silent) | AASA claims `/s/*` but `rewriteUniversalPath` has no `/s/tiers` branch — the tiers link would open the app onto a fallback error toast. |
| 7 | (silent) | `/s/tiers` + `/og/tiers` publish a board with no flag and no opt-in while `/u/*` is dark behind two gates. |
| 8 | (silent) | The `/s/p/<id>` OG card's fairness bar is a cosmetic `search_rank` heuristic (`og_image.py:445-480`), **not** the app's verdict, and unresolvable ids render as `"Unknown player"` (`og_image.py:646-650`) — which is exactly what league draft-pick ids do (`pick_id` = `{league}_{season}_{round}_{roster}`, `backend/database.py:7588-7592`; not in the `players` table). |
| 9 | Line numbers | No drift in the cited backend blocks; mobile line numbers all moved. Current numbers used throughout. |

---

## Design

One mechanism, three surfaces. The organising idea: **a share artifact should carry the
strongest link it can get, and degrade honestly when it can't get one.**

### 1. The link ladder

Every share site resolves its URL through one shared helper, `resolveShareUrl()`, which walks
a three-rung ladder and never throws:

| Rung | URL | When |
|---|---|---|
| **A — package landing** | `<base>/s/p/<short_id>?ref=<username>` | `growth.share_landing` on, not a demo session, ≥1 asset, mint succeeded |
| **B — referral root** | `<base>/?ref=<username>` | mint failed / 429 / demo session / offline / flag off but a username exists |
| **C — bare root** | `<base>/` | no username (should be unreachable post-auth; the honest floor) |

Rung B is *today's* behaviour for the calculator text share (`TradeCalculatorScreen.tsx:529-531`),
so the degradation path is a known-good state, not a new one. Rung C is the pre-`share_landing`
behaviour. **No rung ever leaves the artifact link-free** — which is the actual bug.

Why the minted link rather than a static one: the whole point of A-10 is that the screenshot is
the app's most viral artifact. A root URL gets a generic OG preview; `/s/p/<id>` gets a rendered
card of *that trade* (`og_image.py:551-591`) and a "Build your own trade" CTA
(`server.py:16893-16897`). That is the difference between a watermark and a loop.

### 2. Where the link lands

**In the PNG** — the `watermark` `<Text>` at `ShareTradeImage.tsx:122` becomes a two-line
footer block: the wordmark, then the link on its own line at the same 11pt/`chalk.faint`
treatment. This mirrors the server's own OG footer (`og_image.py:170-174`), so the two artifacts
finally read as the same product. No new design tokens; no layout reflow (the card is
fixed-width 360 and content-height).

**In the message body** — iOS gets `Share.share({ message, url: uri })` instead of
`{ url: uri }`, where `message` is a one-line caption plus the URL. Android already shares
`fallbackText`; that string gains the URL too. The capture-failure fallback gains it as well,
so **all four paths** (iOS image, iOS capture-failure, Android, share-sheet error) carry a link.

**In the calculator's text share** — `TradeCalculatorScreen.tsx:529-531` swaps the site-root
line for the ladder's result, and the stale comment at `:523-527` is deleted and replaced with
the truth.

**In the liked-but-unmatched trade share** — `TradesScreen.tsx:2749-2751`'s bare-root fallback
becomes rung A (mint the liked card's give/receive ids); the matched case keeps
`/s/trade/<match_id>` unchanged. Stale comment at `:2735-2741` deleted. *(Separable — see
[OC-2](#operator-checkpoints).)*

### 3. Ordering: mint before capture

This is the subtle part and the reason the effort is S–M, not S.

`captureRef` snapshots the **rendered** view. A URL fetched inside `share()` is not in the view
until React commits and paints. So `share()` cannot be `mint → captureRef` in one function body.

The shape:

```
onPress → setState({ phase: 'minting' })              // button shows a spinner, disabled
        → await resolveShareUrl()                     // ladder; never throws
        → setState({ phase: 'ready', shareUrl })      // footer text now in the tree
useEffect on (phase === 'ready') →
          await new Promise(requestAnimationFrame)    // one commit + paint
          captureRef → Share.share({ message, url })
        → setState({ phase: 'idle' })
```

`requestAnimationFrame` (not a fixed sleep) is the paint barrier. If `captureRef` still throws,
the existing catch already falls back to `fallbackText` — which now carries the same URL, so a
race degrades to rung-equivalent text, never to a link-free share.

The mint is also **cached per package**: keyed on `give.join('+') + '|' + receive.join('+')`,
so re-sharing an unchanged trade does not burn another of the 20 hourly mints
(`server.py:16847-16862`).

### 4. The tiers half

Three pieces, all required together:

1. **The alias (mandatory).** `rewriteUniversalPath` (`deepLinks.ts:189-199`) gains a third
   branch: `/s/tiers/<pos>/<username>` → `app/rank/tiers`. Without it the loop is
   self-sabotaging (see the trap above). The position segment is *dropped* in v1 because
   `TiersScreen` reads no params (`TiersScreen.tsx:113-124`); teaching it to accept one is a
   separate change and is [OC-4](#operator-checkpoints).
2. **The affordance.** `TiersScreen`'s save-success toast (`TiersScreen.tsx:383-384`) gains a
   trailing **Share** action. `Toast` already supports `action?: {label, onPress}`
   (`mobile/src/components/Toast.tsx:20-22, 111-124`); only the screen's local toast-state
   type at `:125` needs widening. This is the moment of pride the audit asked for
   (`02-tier-a-briefs.md:250`), it costs no header real estate (the header row at `:1138-1187`
   already carries three buttons), and — unlike a native `Alert` — **it is assertable by
   Maestro**.
3. **Not the Alert.** The Quick Set walk ends in a native `Alert.alert('Tiers set', …)`
   (`QuickSetTiersScreen.tsx:272-286`). A third button there would be untestable (native
   dialog) and would compete with the existing "Quick rank" next-step. Deliberately declined;
   recorded, not silently skipped. *(Revisit is [OC-5](#operator-checkpoints).)*

The tiers share is text-only: `Share.share({ message })` with
`See how I tier my <POS>s → <base>/s/tiers/<pos>/<username>?fmt=<format>`, matching the web
builder's URL shape exactly (`web/js/app.js:5285-5295`) so the two clients cannot drift.

### 5. No new feature flags

`growth.share_landing` already exists, is already ON, is already client-exposed
(`feature_flags.py:272`), and already gates precisely this surface server-side. Every new
mobile behaviour here reads that one flag. A new flag would itself be a flag-surface change
(bright line) to gate a fix whose premise is that the loop converts zero — that trade is not
worth making.

**The consequence must be stated plainly: because the flag is already ON in production, this
work goes live the moment it merges.** There is no dark period. That is the whole content of
[OC-1](#operator-checkpoints).

### 6. Analytics

Register first, fire second — the P0-3 lesson, and here it applies to events that already exist:

- `calc_trade_shared` → **added** to `ALLOWED_CLIENT_EVENTS` (it has been dropped since it
  shipped), props `{mode, landing, surface}`.
- `trade_card_shared` → props widened from `{trade_id, channel}` to
  `{trade_id, channel, landing, surface}` (fixes the silent strip).
- `tier_board_shared` → **new**, props `{position, format, surface}`.
- `share_package_created` → **new**, props `{surface, give_n, receive_n, outcome}` where
  `outcome ∈ ok | rate_limited | demo | failed` — the rung-A success rate, which is the only
  way to tell "nobody shares" from "sharing is broken".

`surface` values: `calc_live | calc_in_league | trades_liked | tiers`.

---

## Exact change list

Ordered. Backend lands and deploys before any client `track()` ships (B1–B2 first).

### Backend

| # | File | Change |
|---|---|---|
| B1 | `backend/analytics_taxonomy.py:38-99` (`ALLOWED_CLIENT_EVENTS`) | Add `calc_trade_shared`, `tier_board_shared`, `share_package_created`. Comment block explains that `calc_trade_shared` has been fired-and-dropped since it shipped. **Merge point with P0-3's B4 — same block.** |
| B2 | `backend/analytics_taxonomy.py:222` (`CLIENT_EVENT_PROPS`) | Widen `trade_card_shared` → `{trade_id, channel, landing, surface}`; add prop sets for the three new names per [Design §6](#6-analytics). |
| B3 | `backend/tests/test_share_package.py` | Extend: the four share event names are in `ALLOWED_CLIENT_EVENTS` and survive `POST /api/events` with their full prop sets (the regression guard for the silent-drop class). |
| B4 | `backend/tests/test_universal_links.py` | Add: AASA still claims `/s/*` (so the tiers alias has a matching claim) — assertion only, no route change. |

**No route is added, renamed, or contract-changed.** `/api/share/package`, `/s/p/<id>`,
`/s/tiers/<pos>/<username>` and their OG twins ship exactly as they are today.

### Mobile — shared plumbing

| # | File | Change |
|---|---|---|
| M1 | `mobile/src/api/calc.ts` (**new export**) | `createSharePackage(giveIds, receiveIds): Promise<{short_id, url} \| null>` — `POST /api/share/package`, short timeout, **never throws**; returns `null` on 400/429/5xx/offline. Distinguishes `demo_session` and `rate_limited` in a returned reason so `share_package_created.outcome` is honest. |
| M2 | `mobile/src/utils/shareLinks.ts` (**new**) | `resolveShareUrl({giveIds, receiveIds, username, enabled})` — the rung ladder from [Design §1](#1-the-link-ladder), plus the per-package mint cache; and `buildTierShareUrl(pos, username, format)` mirroring `web/js/app.js:5285-5295` byte-for-byte in shape. Pure + one injected api call; the single place either URL is constructed. |
| M3 | `mobile/src/utils/deepLinks.ts:189-199` | Third branch in `rewriteUniversalPath`: `^s/tiers/[^/]+/[^/]+$` → `app/rank/tiers` (query suffix preserved, same as the other two branches). Comment records **why**: AASA claims `/s/*` wholesale (`server.py:8094-8107`), so every `/s/` shape needs an alias or it lands on the fallback toast. |

### Mobile — P1-1 (the PNG)

| # | File | Change |
|---|---|---|
| M4 | `mobile/src/components/ShareTradeImage.tsx:34-47` | Props gain `giveIds: string[]`, `receiveIds: string[]`, `surface: ShareSurface`. `fallbackText` stays but is now composed **with** the resolved URL by the component, not the host. |
| M5 | `mobile/src/components/ShareTradeImage.tsx:52-73` | `share()` becomes the two-phase mint→paint→capture flow of [Design §3](#3-ordering-mint-before-capture). Button shows an in-flight state and is disabled while minting (`testID` unchanged). iOS: `Share.share({ message, url: uri })`. Android + both catch paths: `fallbackText` with the URL appended. Fires `share_package_created` and the host's share event. |
| M6 | `mobile/src/components/ShareTradeImage.tsx:117-123` | Footer block: keep `Dynasty Trade Finder`, add a second `<Text testID="share.card-url">` carrying the resolved URL, same 11pt/`chalk.faint`/centred treatment (styles `:157-164` reused; one new `footerUrl` entry). Update the file-header comment (`:12-21`) — it currently describes a watermark-only card. |
| M7 | `mobile/src/screens/TradeCalculatorScreen.tsx:867-884` | Pass `giveIds={liveSendIds}`, `receiveIds={liveReceiveIds}`, `surface="calc_live"`. |
| M8 | `mobile/src/components/InLeagueCalculator.tsx:781-798` | Pass `giveIds={giveIds}`, `receiveIds={receiveIds}`, `surface="calc_in_league"`. **Note the pick hazard** — see [Risks](#risks-and-cross-item-collisions) R-5. |

### Mobile — P1-2 (the landings)

| # | File | Change |
|---|---|---|
| M9 | `mobile/src/screens/TradeCalculatorScreen.tsx:523-531` | **Delete the stale comment** (`:523-527`) and replace with an accurate one naming `server.py:16828`. Swap the site-root line for `resolveShareUrl(...)`. Keep the flag-off byte-identical branch. |
| M10 | `mobile/src/screens/TradeCalculatorScreen.tsx:534-536` | `track('calc_trade_shared', {mode, landing, surface}, 'Calculator')` — now that B1 makes it land. |
| M11 | `mobile/src/screens/TradesScreen.tsx:2735-2751` | **Delete the second stale comment** and mint a package for the liked-but-unmatched case; matched case unchanged. *(Separable — [OC-2](#operator-checkpoints).)* |
| M12 | `mobile/src/screens/TradesScreen.tsx:2760-2766` | `trade_card_shared` props gain `surface`; `landing` now survives ingest after B2. |
| M13 | `mobile/src/screens/TiersScreen.tsx:125` | Widen the local toast state to carry `action?: {label, onPress}`. |
| M14 | `mobile/src/screens/TiersScreen.tsx:383-384` | Save-success toast gains the **Share** action → `Share.share({message})` with `buildTierShareUrl(position, user.username, activeFormat)`; fires `tier_board_shared`. Suppressed when `isAllView` (there is no `/s/tiers/all/...` route — `server.py:16764` accepts only QB/RB/WR/TE via `og_image.py:304-309`), when the session is demo (`useSession.isDemo`, `useSession.ts:106`), or when `growth.share_landing` is off. |
| M15 | `mobile/src/screens/TiersScreen.tsx:1129-1133` | Pass `action={toast?.action}` through to `<Toast>`; add `testID="tiers.share-toast-action"` to the action (requires a `testID` passthrough on `Toast`'s action button, `Toast.tsx:111-124` — one prop). |

### Web

**No change.** `buildTierShareUrl`/`buildTradeShareUrl` (`web/js/app.js:5285-5301`) stay dead
code this round — wiring web share affordances is a separate surface with its own design
questions (where the button goes on a page the audit did not cover). Recorded as a deliberate
decision, not an oversight, and filed as a follow-up.

---

## Surface changes

Enumerated per the CLAUDE.md bright line. Every category is answered.

### Routes — **YES, one deep-link alias**

| Surface | Entry | Kind |
|---|---|---|
| Deep-link alias (mobile) | `/s/tiers/<pos>/<username>` → `app/rank/tiers` in `rewriteUniversalPath` | **New alias.** Bright-line route surface. Applies to both resolution paths (cold-start `getStateFromPath` at `deepLinks.ts:205-212`, warm `_routePathV2`) because both funnel through the same function. |
| Server routes | none | `/api/share/package`, `/s/p/<id>`, `/s/tiers/...`, `/og/*` all unchanged |
| AASA | none | `/s/*` is already claimed (`server.py:8094-8107`); no new claim, therefore **no CDN wait** |
| Navigation routes | none | no new screen |

### Schema — **none**

No table, column, or migration. `shared_packages` already exists and is already documented
(`docs/data-dictionary.md:856`). Client-side, the mint cache is in-memory only.

### Feature flags — **none new**

Reuses `growth.share_landing` (`config/features.json:125`, `feature_flags.py:272`), already ON.
No default change, no new key, no `FLAG_KEYS` edit. Justification in [Design §5](#5-no-new-feature-flags).

### Analytics events — **YES, four touched**

| Event | Change | Why it is a bright line |
|---|---|---|
| `calc_trade_shared` | **register** (currently dropped by the allowlist) | new taxonomy entry |
| `trade_card_shared` | **widen props** `+landing +surface` (currently stripped) | prop-contract change |
| `tier_board_shared` | **new** | new taxonomy entry |
| `share_package_created` | **new** | new taxonomy entry |

Server-side registration (B1/B2) must be deployed **before** the client build that fires them.

---

## Maestro delta

**Nothing existing asserts the bug.** `grep -rn "share" mobile/.maestro/` returns only prose;
no flow references `calc.share-image` or any share affordance. So there is no flow to un-assert
— an outcome worth stating, because the standing instruction assumes there might be.

**Hard constraint.** The iOS share sheet is `UIActivityViewController`, out of process. README
law 20 records a native dialog "poisoned every later step" (`mobile/.maestro/README.md:159-166`).
**Therefore no flow taps a share button.** Coverage is designed around that: everything the fix
changes is made assertable *inside* the app before the sheet opens.

**New flow — `mobile/.maestro/flows/growth/share-links.yaml`** (`# flags: release`,
`# profile: standard`), three blocks:

1. **Calculator, live mode.** Sign in → Trades → `trades.subnav.calculator` → `calc.mode-tab.live`
   → add Burrow (`calc.picker.row.6770`, the fixture-pool member `07-calculator.yaml` already
   uses) to each side → `scrollUntilVisible` `calc.verdict` → `assertVisible: calc.share-image`
   → `assertVisible: calc.share-link` (the resolved-URL row rendered next to the button once the
   mint settles) → `assertVisible` a text match on `/s/p/` to prove **rung A**, not rung B.
   *No tap on the share button.*
2. **Rung-B degradation.** Same path with `fail_next` armed on `"/api/share/package"`
   (`count: 1`, bare POST — law 11) and the route's real 429 body
   `{"error":"rate_limited","message":"Too many shares — try again later."}` (law 12, read from
   `server.py:16865-16866`) → `assertVisible: calc.share-link` still present, matching `?ref=`.
   **This block is the one that proves the artifact is never link-free.**
3. **Tier board.** Rank tab → `rankmenu.tiers` → `tiers.list` → `tiers.save-btn` →
   `assertVisible: tiers.share-toast-action`. *No tap.*

**`testID`s added** (must pass `mobile/scripts/testid-lint.sh`):
`calc.share-link`, `share.card-url`, `tiers.share-toast-action`.
`share.card-url` lives on the off-screen capture surface (`left: -9999`), so it is asserted
only by `tsc`/manual inspection of the produced PNG, **not** by Maestro — noted so nobody adds
a flaky assertion for it later.

**Smoke impact.** Two of the eleven cross this surface: `flows/smoke/07-calculator.yaml`
(reaches `calc.verdict`, one scroll above the actions row) and `flows/smoke/04-tiers.yaml`
(asserts `tiers.save-btn`, does not tap it). Neither asserts anything that moves; both are
expected green and will be **run, not assumed** (tier 1).

**Capture delta** (per `screens/manifest.json`): re-capture `calc`, `tiers`, and — if M11/M12
are taken — `trades`. `quick-set` is **not** touched (the Alert is deliberately left alone).
Run `mobile/scripts/screen-capture.sh --screen calc --screen tiers [--screen trades]`; verify
with `screen-freshness.sh` before and after.

---

## Docs impact table

One row per `docs/CLAUDE.md` trigger, plus the mandatory feature-gate rows.

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/data-dictionary.md` | **n/a** | No `backend/database.py` schema change. `shared_packages` is already documented at `:856`, including the public-by-URL privacy note. |
| `docs/api-reference.md` | **YES** | No route added or renamed, but two rows become materially wrong-by-omission: `:546` (`POST /api/share/package`) says clients build `<base><url>?ref=<username>` — record that mobile now does, and from which surfaces; `:544` (`/s/tiers/<pos>/<username>`) gains the note that it is **unflagged**, is now linked from the mobile tier board, and that `/s/*` is AASA-claimed so the client must alias it. |
| `docs/glossary.md` | **YES** | Add **share package** (a `/s/p/<id>` snapshot of an arbitrary give/receive build) and **share link ladder** (the A/B/C degradation) — both land in code as named concepts. |
| `docs/cross-client-invariants.md` | **YES** | The two share-URL shapes are now a genuine cross-client contract: `<base>/s/p/<id>?ref=` and `<base>/s/tiers/<pos>/<user>?fmt=`. Mobile's `shareLinks.ts` and web's `buildTierShareUrl` must produce identical shapes; record the `fmt` omission rule for `1qb_ppr` (web `app.js:5292`) and the QB/RB/WR/TE-only position set. |
| `docs/architecture.md` | **n/a** | No backend module wiring or data-flow change; the mobile addition is one util module inside an existing layer. |
| `docs/config-reference.md` | **YES** | `growth.share_landing` at `:251` currently describes only `/s/trade` + `/s/tiers` composition. Rewrite: it now additionally gates the package mint and the tier-board affordance, **and it is already ON**, so the entry must state that this ships live on merge. |
| `docs/runbook.md` | **YES** | New short section: share-package mint failures are expected and benign (ladder degrades to `?ref=`); the 20/user/hour limit (`server.py:16812`) and its 429 body; where to look when shares stop carrying `/s/p/` links (flag → `_health_bump("dropped_unknown_type")` → route 404). |
| `docs/coding-guidelines.md` | **n/a** | No new behavioural rule beyond what DECISIONS records. |
| `docs/adr/` | **n/a** | No architectural choice of ADR weight; the judgement calls are captured in DECISIONS + this plan. |
| `living-memory/LLD.md` | **YES** | Convention shift, and a real one: **any path shape claimed by AASA must have a matching `rewriteUniversalPath` alias, or it opens the app onto the fallback toast.** `/s/*` is claimed wholesale, so this binds every future `/s/…` route. |
| `living-memory/HLD.md` | **n/a** | No new module, client, or major flow. |
| `living-memory/DECISIONS.md` | **YES** (next id `D-011`) | Why no new flag (reuse `growth.share_landing`, accept shipping live); why the link ladder degrades rather than blocks the share; why the tier affordance is the save toast and **not** the Quick Set `Alert`; why web stays unwired this round. |
| `living-memory/GOTCHAS.md` | **YES** (next id `G-013`) | `captureRef` snapshots the rendered tree — an awaited value must be committed **and painted** before capture, so a mint cannot live inside the same `share()` body. Plus: two comments in two files claimed a route that had existed for weeks. |
| `living-memory/CHANGELOG.md` / `TEST_LEDGER.md` / `NEXT.md` | **YES at ship** | Standard session write-back per root `CLAUDE.md`. |
| Analytics tracking plan (`docs/business/analytics/`) | **YES** | Addendum for the four events, including the finding that `calc_trade_shared` has been dropped and `trade_card_shared.landing` stripped since they shipped. |
| `docs/feedback/items/<id>/` | **n/a** | Audit-driven, not feedback-driven; home is `docs/plans/audit-p1-remediation/`. |
| `docs/design/` | **read, not edited** | Footer text and toast action reuse existing Chalkline tokens (`type.label`, `chalk.faint`, `Toast` action spec); no new component or token. |

---

## Test plan

**Backend (pytest)**

1. `test_share_package.py` — existing 11 cases stay green (no route change).
2. `test_share_package.py` (new) — the four share event names are in `ALLOWED_CLIENT_EVENTS`
   and each name's full prop set survives `POST /api/events` unstripped. *This is the
   regression guard for the exact bug found in [Verified current state](#analytics-reality-check-not-in-the-audit-both-are-silent-drop-bugs).*
3. `test_universal_links.py` (new) — AASA still claims `/s/*`, so the new client alias has a
   matching server claim.
4. Existing flag guard — `growth.share_landing` still present in `FLAG_KEYS` and still ON in
   `config/features.json` + `release.json` (no default change).

**Mobile (`npx tsc --noEmit` + Maestro)**

5. Typecheck clean.
6. `flows/growth/share-links.yaml` blocks 1–3.
7. Full smoke suite (11 flows) — tier 1 change class.
8. `mobile/scripts/testid-lint.sh` exit 0.
9. `mobile/scripts/screen-freshness.sh` flags `calc`, `tiers` (+`trades` if M11/M12 taken);
   re-capture those and **eyeball every shot** (law 23).

**Manual / simulator — the parts Maestro structurally cannot reach**

10. Calculator live mode → **Share image** → share sheet opens → save the PNG → confirm the
    footer line renders the `/s/p/<id>` URL, is legible at 360px, and is not clipped.
11. Paste the produced link into iMessage on a device **without** the app → OG preview renders
    the package card (`/og/p/<id>.png`), CTA reads "Build your own trade".
12. Same link on a device **with** the app → opens in-app to Trades (`deepLinks.ts:190-198`
    existing `/s/p/` alias), no fallback toast.
13. Tier board → save → toast **Share** → link opens `/s/tiers/<pos>/<user>` in Safari
    (no app) and **in-app to the Tiers board** (app installed) — the alias check. Confirm it
    does **not** produce the fallback toast; that is the regression this alias exists for.
14. Airplane mode → share image → rung B (`?ref=`) in both PNG and message, no error dialog,
    no hang.
15. Demo session → share image → rung B, and `share_package_created.outcome == 'demo'`.
16. 21 shares in an hour → the 21st degrades to rung B silently; `outcome == 'rate_limited'`.
17. In-league calculator with a **draft pick** on a side → inspect the resulting `/s/p/<id>`
    landing. Expect `"Unknown player"` (R-5). Decide per [OC-6](#operator-checkpoints).
18. Android (if a device is available): text share carries the URL. Otherwise recorded as an
    untested platform, since `Platform.OS === 'android'` is a live branch
    (`ShareTradeImage.tsx:55-59`).

**Ship gate:** tier 1 (mobile screen change) — full smoke + the new flow + capture refresh for
`calc`/`tiers`(/`trades`); log in `living-memory/TEST_LEDGER.md`; write
`qa/sim-runs/last-sim-run.json`.

---

## Risks and cross-item collisions

### Collision with P0-3 (merges first)

`plan-p0-3.md` was read in full. Overlap is **narrow and additive**:

| File | P0-3 | P1-1/2 | Resolution |
|---|---|---|---|
| `backend/analytics_taxonomy.py` | B4 — registers `invite_shared` + 3 invite events | B1/B2 — registers 3 share events, widens `trade_card_shared` | **Textual conflict in the same block, semantically independent.** Rebase after P0-3 lands; both are additions to one frozenset. |
| `backend/server.py` AASA (`:8076-8109`) | B1 — **adds** `/app/league/join/*` | **reads only** | No conflict. P0-3's CDN wait applies to its path, not to `/s/*`, which is already claimed — so this plan has **no AASA lead time**. |
| `mobile/src/utils/deepLinks.ts` | M4 (`V2_SCREENS` +`LeagueJoin`), M5 (`?league=` capture at `:344-354`) | M3 (`rewriteUniversalPath` `:189-199`) | Different functions in one file. Trivial rebase. |
| `docs/api-reference.md`, `docs/config-reference.md`, `docs/cross-client-invariants.md`, `docs/runbook.md`, `living-memory/*` | edits | edits | Doc-level conflicts only. Rebase, don't merge blind. |
| `mobile/src/screens/TradesScreen.tsx` | — | M11/M12 | P0-3 does not touch it. **P0-2 does** (`plan-p0-2.md` §Exact change list — `job.error` rendering + `Toast.tsx` `topOffset`). Same-file, different regions; P0-2 merges first. |
| `growth.share_landing` | P0-3 reads it in `InviteLeaguematesBanner` and notes it gates only the track call | this plan makes it gate three more behaviours | Compatible. If P0-3's `growth.invite_join_link` ships, the two flags stay independent. |

**P0-3 explicitly leaves `buildInviteUrl` and `?league=` to itself; this plan touches neither.**
No overlap on the invite loop.

Recommended sequencing: **P0-2 → P0-3 → P1-1/2**, with P1 rebasing onto merged `main`.
`living-memory/DECISIONS.md` next-id and `GOTCHAS.md` next-id must be re-read after the P0 merge
— P0-3 also claims `D-011`/`G-013`.

### Other risks

| # | Risk | Mitigation |
|---|---|---|
| R-1 | **Ships live on merge.** `growth.share_landing` is already ON, so there is no dark period and no staged rollout. | Stated up front as [OC-1](#operator-checkpoints). If the operator wants a dark period, a new flag is the only mechanism — and that is itself a surface change, to be decided before build, not during. |
| R-2 | **`Share.share({message, url})` on iOS.** Both become activity items; some targets (Mail, Notes) take both, others (some third-party apps) may drop one. | The URL is **inside the PNG** as well, so a target that drops the message still ships a visible link. That redundancy is the reason both halves of A-10 are done together rather than either alone. |
| R-3 | **Mint→paint→capture race.** If the paint barrier is wrong, the PNG captures without the footer — a silent regression that still "works". | `requestAnimationFrame` barrier, never a fixed sleep (README law 1's spirit). Manual test 10 inspects the actual PNG; the footer carries `testID="share.card-url"` so a future harness can reach it. Logged as a GOTCHA. |
| R-4 | **Rate limit / demo / offline** turn the primary rung off. | The ladder never fails closed; every rung produces a link. Block 2 of the Maestro flow asserts the degraded rung explicitly, and `share_package_created.outcome` makes the rate distinguishable in data. |
| R-5 | **Draft picks render as `"Unknown player"` on the package landing.** `load_players_by_ids` cannot resolve a `pick_id` (`{league}_{season}_{round}_{roster}`, `database.py:7588-7592`); `og_image.py:646-650` falls back to that literal string. The in-league calculator routinely contains picks (`InLeagueCalculator.tsx:197-212`). Live-mode calc is safe (universal pool = real Sleeper ids, `server.py:8220-8231`). | Three options in [OC-6](#operator-checkpoints). Do **not** ship the in-league image share to rung A silently while this renders badly. |
| R-6 | **The landing's fairness bar can contradict the PNG the user just shared.** `_compute_fairness` (`og_image.py:445-480`) is a cosmetic `search_rank` symmetry heuristic explicitly documented as *not* authoritative; the PNG carries the real server verdict (`evalQuery.data.verdict`). A recipient can see two different reads of the same trade. | Not in scope to fix the renderer, but it is a real product defect the moment the route has callers. Raised as [OC-7](#operator-checkpoints). |
| R-7 | **Tier share publishes a board with no opt-in.** See the privacy asymmetry above. | [OC-3](#operator-checkpoints). Default recommendation gates the *affordance* on `growth.share_landing` and leaves the route as-is — user-initiated only. |
| R-8 | **`/s/tiers/all/...` does not exist.** `og_image.py:304-309` accepts QB/RB/WR/TE only. | M14 suppresses the action when `isAllView`. Asserted in manual test 13. |
| R-9 | **Two clients could drift on URL shape.** Web already has a builder (dead); mobile gains one. | `docs/cross-client-invariants.md` row makes the two shapes a recorded contract, including the `fmt`-omitted-when-`1qb_ppr` rule. |
| R-10 | **Comment rot recurrence.** Two files carried the same false claim for weeks. | Both comments deleted and replaced with claims that cite `server.py:16828` by line, so the next reader can check them in one grep. Recorded in GOTCHAS as a pattern, not an incident. |

---

## Operator checkpoints

Product, policy, and threshold calls. Each has options and a recommendation; none is decided
here.

**OC-1 · This ships live on merge — accept, or add a flag?**
`growth.share_landing` is ON in `config/features.json:125` and in the release fixture, so every
change here is user-visible the moment it merges.
- (a) **Accept.** No new surface; the loop starts converting immediately. *Recommended* — the
  finding is that these paths convert zero, and a dark flag preserves exactly that.
- (b) Add `growth.share_v2`, default OFF. Buys a staged rollout at the cost of a new flag
  surface (a bright line) and a second graduation step.

**OC-2 · Include the liked-but-unmatched trade share (M11/M12)?**
The audit scoped P1-2 to the calculator, but `TradesScreen.tsx:2735-2741` carries the *same*
stale comment and the audit's own §7 calls the unmatched case "the more common case"
(`02-tier-a-briefs.md:350`).
- (a) **Include.** ~20 lines, same mechanism, kills the second stale comment. *Recommended.*
- (b) Defer. Keeps the diff smaller and `TradesScreen.tsx` (a P0-2 file) untouched; leaves a
  known-false comment in the tree and the highest-volume share on the bare root.

**OC-3 · Tier-share privacy posture.**
`/s/tiers` + `/og/tiers` publish a named user's board with no flag and no opt-in, while `/u/*`
is dark behind `profiles.public_pages` **and** `profiles.user_toggle` — and #221 just *hid* the
public-profile row.
- (a) Ship the affordance as-is; publication becomes user-initiated in practice.
- (b) **Gate the affordance on `growth.share_landing`** (already ON, no new flag) and leave the
  route unchanged. *Recommended for this round* — same practical outcome as (a), plus a
  kill switch that already exists.
- (c) Add a server-side opt-in check to `/s/tiers` mirroring `profiles.user_toggle`. Correct
  long-term, but it is a **route contract change** — bright line, own scope block, not this
  plan.
Note: none of these stops direct enumeration of `/og/tiers/qb/<any-username>.png` today. If
that is unacceptable, it is a P0-class finding of its own and should be filed separately.

**OC-4 · Should a tier link land on the shared position?**
`TiersScreen` reads no route params (`TiersScreen.tsx:113-124`), so `/s/tiers/wr/matt` opens
the board at QB.
- (a) **Ship v1 without it** — the alias prevents the error toast, which is the actual bug.
  *Recommended.*
- (b) Teach `TiersScreen` to accept an optional `position` param and pass it through the alias.
  Better, ~15 lines, and it makes the alias lossy-vs-lossless a design decision rather than an
  accident.

**OC-5 · Should the Quick Set walk's completion also offer a share?**
The audit named walk completion as "the natural moment of pride"
(`02-tier-a-briefs.md` §Growth). This plan declines because that completion is a native
`Alert` (`QuickSetTiersScreen.tsx:272-286`) — untestable by Maestro and already carrying a
"Quick rank" next-step.
- (a) **Leave it.** The save toast covers the same board one screen later. *Recommended.*
- (b) Replace the `Alert` with a Chalkline sheet carrying both next-steps and a share action.
  Better UX and testable, but it is a new component on a screen this plan otherwise does not
  touch (and re-captures `quick-set`).

**OC-6 · Draft picks on the package landing (R-5).**
- (a) Mint anyway; picks render `"Unknown player"` on the shared card.
- (b) **Fall back to rung B when any id is a `pick_id`** — the in-league share with picks keeps
  today's `?ref=` link rather than producing an embarrassing landing. *Recommended for this
  round*; zero backend work.
- (c) Teach `og_image` to render pick labels from `draft_picks`. Correct, but it is backend
  renderer work with its own scope.

**OC-7 · The landing's fairness bar contradicts the app's verdict (R-6).**
`og_image._compute_fairness` is a `search_rank` heuristic, self-documented as cosmetic. Once
these routes have callers, a recipient may see a fairness read that disagrees with the PNG.
- (a) Ship as-is and file it.
- (b) **Store the sharer's server verdict on the `shared_packages` row and render that.**
  Correct, but it is a **schema change** — bright line, own scope block. *Recommended as a
  fast-follow, not as part of this plan.*
- (c) Remove the fairness bar from the package card so the landing makes no claim it cannot
  back. Cheapest honest option.

**OC-8 · Copy.** Three strings need a decision:
- PNG footer: `fantasy-trade-finder.onrender.com/s/p/<id>` (bare, matches `og_image.py:171`) vs
  a labelled `See this trade → …`. *Recommended: bare URL*, so the 360px card stays legible.
- iOS share message caption accompanying the image.
- Tier share message: *"See how I tier my WRs → …"* vs naming the format.

**OC-9 · Web parity.** `web/js/app.js:5285-5301` has two dead URL builders. Wire them this
round, or file as follow-up? *Recommended: follow-up* — the web share placement is a design
question the mobile audit did not cover, and mixing it in doubles the review surface.
