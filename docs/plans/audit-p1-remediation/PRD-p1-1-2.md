# PRD — P1-1 + P1-2: share artifacts carry a link, and the two dead landings get callers

> **Purpose.** The product-level contract for audit findings **P1-1 (A-10)** and **P1-2 (A-11)**.
> What changes for a user, what must be true before this ships, how it is tested, what the operator
> must decide, and how it comes back out.
>
> **Status:** requirements-only. No source file is changed by this document.
> **Authority order:** `DECISIONS-p1.md` → `HLD-p1.md` → `plan-p1-1-2.md` / `scope-p1-1-2.md` →
> `LLD-p1-1-2.md` → this file.
> **Worktree:** `ftf-p1-remediation`, branch `p1-remediation-2026-08-11` @ `ab9368f` (pre-P0).
> **Wave:** A3 (`HLD-p1.md` §B), after commit **T1** and after `p0-remediation-2026-08-10` merges.
> **Rigor:** full gates. Two bright lines are crossed — a deep-link route alias and the analytics
> taxonomy. No express lane was declared.
>
> ### ⚠ This ships live on merge
> `growth.share_landing` is `true` in `config/features.json:125` **and** in
> `backend/tests/fixtures/flags/release.json:126`. There is **no flag between this code and every
> user**, and no dark period. `HLD-p1.md` §F R-1 records that P1-1/2 is one of **four** P1 items in
> this condition, and that the round's rollback story is `git revert`, not a flag flip, for all
> four. This is a release-planning fact, not a footnote. **[OG-2](#operator-gates)** is where the
> operator accepts or refuses it.

## Contents

- [1. Problem](#1-problem)
- [2. User-visible behaviour: before and after](#2-user-visible-behaviour-before-and-after)
- [3. Out of scope](#3-out-of-scope)
- [4. Acceptance criteria](#4-acceptance-criteria)
- [5. Maestro flow specs](#5-maestro-flow-specs)
- [6. Manual verification](#6-manual-verification)
- [7. Ship gate](#7-ship-gate)
- [8. Docs impact](#8-docs-impact)
- [9. Operator gates](#9-operator-gates)
- [10. Release risk and rollback](#10-release-risk-and-rollback)

---

## 1. Problem

Three things are true at `ab9368f`, and each was verified by reading the code, not the comments.

### 1.1 The app's most shareable artifact carries no way back to the app

`ShareTradeImage` renders a Chalkline card of a trade and captures it to a PNG
(`ShareTradeImage.tsx:60-64`). Its only footer is the literal string `Dynasty Trade Finder`
(`:122`) — a wordmark with **no URL**. iOS shares the image alone: `Share.share({ url: uri })`
(`:65`), with no `message` key, so nothing textual travels with it. Android shares `fallbackText`
(`:55-59`), which contains no URL either — nor does the capture-failure fallback (`:66-72`).

The server's own OG cards have drawn a URL footer since they shipped
(`og_image.py:170-174` → `"Fantasy Trade Finder · fantasy-trade-finder.onrender.com"`). The app's
own PNG is the odd one out.

**A recipient of that screenshot has nothing to type.**

### 1.2 Two complete, tested share landings have zero callers

**Package landing.** `POST /api/share/package` (`server.py:16828-16876`) is session-authed,
rate-limited 20/user/hour, capped at 5 ids per side, and returns `{ok, short_id, url:"/s/p/<id>",
og_image:"/og/p/<id>.png"}`. `GET /s/p/<short_id>` renders the landing (`:16878-16899`) and
`GET /og/p/<short_id>.png` renders the card (`:16901-16912`). Eleven pytest cases cover it
(`backend/tests/test_share_package.py`). The flag that gates all three is **on**.

`grep -rn "share/package" mobile/` → **no matches.** Nor in `web/` or `extension/`.

**Tier landing.** `GET /s/tiers/<pos>/<username>` (`:16759-16779`) and
`GET /og/tiers/<pos>/<username>.png` (`:16663-16680`) both work and neither is flag-gated.
`grep -rn "s/tiers\|og/tiers" mobile/` → **no matches.** On web, `buildTierShareUrl` and
`buildTradeShareUrl` are **defined and never invoked** (`web/js/app.js:5285-5301`). Both clients'
halves were written and abandoned.

### 1.3 Two files claim in a code comment that the route does not exist

| Location | The claim |
|---|---|
| `TradeCalculatorScreen.tsx:523-527` | *"A hand-built calculator trade has no server object (no `/s/` route exists for arbitrary packages — documented W3/backend handoff), so the site root is the landing page."* |
| `TradesScreen.tsx:2735-2741` | *"Liked-but-unmatched trades have no server object yet (no `/s/` route exists for them — documented W3/backend handoff), so those fall back to the site root."* |

Both are false. Both were written before `POST /api/share/package` landed and were never revisited.
**The audit found one; there are two** — and the second sits on the path the audit itself calls "the
more common case". This is the A-33 comment-rot class.

### 1.4 Two silent-failure findings the audit did not have

- **`calc_trade_shared` has never landed a row.** It is fired at `TradeCalculatorScreen.tsx:535` and
  is absent from `ALLOWED_CLIENT_EVENTS` (`analytics_taxonomy.py:38-99`), so `analytics_ingest.py:379-383`
  `_health_bump("dropped_unknown_type")`s the whole envelope and returns **200**.
- **`trade_card_shared.landing` has always been stripped.** The name is registered (`:74`) but its
  prop row is `frozenset({"trade_id", "channel"})` (`:222`), while `TradesScreen.tsx:2760-2766`
  sends `{trade_id, landing}` — stripped at `analytics_ingest.py:384-389`. Neither client has ever
  sent `channel`.

**Consequence: there is no usable telemetry on any share in the product today**, and the "shares
convert zero" premise cannot currently be measured either way. Whatever ships here must register the
names **server-side first** (commit T1), or it repeats the bug.

### 1.5 The trap that makes the tiers half self-sabotaging

AASA claims `/s/*` **wholesale** (`server.py:8100` `{"/": "/s/*"}`, `:8104`
`"paths": ["/u/*", "/s/*"]`), so on an installed device iOS opens the app for **every** `/s/…` URL
rather than Safari. `rewriteUniversalPath` aliases only `/s/trade/<id>` and `/s/p/<id>`
(`deepLinks.ts:196-198`). An unaliased `/s/…` path is unroutable → `navigate('Main')` plus a "link
didn't work" toast (`deepLinks.ts:356-363`), and `ux.deeplink_router_v2` is on, so that is the live
path.

**Shipping a tier-share button without the alias would ship a growth loop that greets every
recipient-who-has-the-app with an error toast.** The alias is part of the fix, not polish.

---

## 2. User-visible behaviour: before and after

| Surface | Today | After |
|---|---|---|
| **Calculator (live) → Share image → iOS** | A PNG whose footer reads `Dynasty Trade Finder`. Nothing else travels. | The PNG's footer reads `Dynasty Trade Finder` **and, on a second line, the share URL**. The share sheet also carries a text message with the same URL alongside the image. |
| **Calculator (live) → Share image → Android** | A text message with no URL. | The same text message **with the URL appended**. |
| **Calculator → Share image → capture fails** | Text fallback with no URL. | Text fallback **with the URL appended**. |
| **Calculator → Share image button** | Fires immediately. | Shows a spinner while the landing is minted, then opens the sheet. A second tap during that window does nothing. |
| **Calculator (live), below the share buttons** | Nothing. | A small, faint, single-line row showing the URL the share will carry. Present from the moment the share button appears. |
| **Calculator → Share trade (text)** | Last line reads `Build your own: <site root>?ref=<user>`. | Last line reads `Build your own: <site>/s/p/<id>?ref=<user>` — a link that renders **that trade** as a preview card in iMessage/Discord, with a "Build your own trade" CTA (`server.py:16893-16897`). Degrades to today's line whenever the landing cannot be minted. |
| **Trades → liked-but-unmatched → Share** *(PR-11)* | Message ends at the bare site root. | Message ends at `/s/p/<id>?ref=<user>`. The **matched** case is unchanged — it already used `/s/trade/<match_id>`. |
| **Tiers → Save** | Toast: "Tiers saved". | Toast: "Tiers saved" **with a trailing Share action**. Tapping it opens the share sheet with a link to the user's public tier board for that position. |
| **Tiers → Save on the ALL board / in demo / flag off** | Toast: "Tiers saved". | **Unchanged** — no Share action. There is no `/s/tiers/all/…` route, demo has no server board, and the flag is the affordance's kill switch. |
| **Receiving a `/s/tiers/…` link with the app installed** | Opens the app, lands on home, shows a "link didn't work" toast. | Opens the app on the **Tiers board**. (At the QB board — the position segment is dropped in v1; see [OG-6](#operator-gates).) |
| **Receiving a `/s/p/…` link without the app** | *(never sent today)* | Safari renders a card of that trade with a "Build your own trade" CTA. |
| **`growth.share_landing` off** | — | **Every one of the above reverts to today's behaviour, byte for byte.** The tier Share action disappears entirely. |

**The invariant the whole change is built around:** *a share artifact always carries a link.* When
the rich landing cannot be produced — offline, rate-limited, demo session, signed out, flag off,
draft picks present — the artifact silently degrades to the referral root it already used, and never
to nothing.

---

## 3. Out of scope

Each is a deliberate decision with a reason, not an omission.

| Not doing | Why | Recorded as |
|---|---|---|
| Wiring `web/js/app.js:5285-5301`'s two dead builders | Web share placement is a design question the mobile audit did not cover; mixing it in doubles the review surface for zero mobile benefit | W-3 / [OG-9](#operator-gates) |
| A share action on the Quick Set completion | It is a native `Alert` (`QuickSetTiersScreen.tsx:272-286`) — untestable by Maestro, and it already carries a "Quick rank" next-step. The save toast one screen later covers the same board | W-4 / [OG-5](#operator-gates) |
| Teaching `TiersScreen` to accept a `position` route param | The alias prevents the error toast, which is the actual bug. Landing on the right position is a nicety | [OG-6](#operator-gates) |
| Fixing `og_image._compute_fairness` so the landing agrees with the app's verdict | Storing the sharer's verdict is a **schema change** — its own bright line and scope block | [OG-8](#operator-gates) |
| Rendering pick labels on the package landing | Backend renderer work with its own scope | [OG-7](#operator-gates) option (c) |
| Adding a server-side opt-in to `/s/tiers` | A **route contract change** — bright line, own scope block | [OG-4](#operator-gates) option (c) |
| Any new feature flag, table, column, migration, or server route | None is needed; `growth.share_landing` already gates exactly this surface | `scope-p1-1-2.md` §2 |

---

## 4. Acceptance criteria

Thirty-four criteria. Each is independently testable and names its verification method:
**[M]** Maestro · **[P]** pytest · **[T]** typecheck/lint · **[H]** manual on-simulator or device ·
**[R]** code read / grep.

### Link presence — the core invariant

1. **[H]** With `growth.share_landing` on, a live-mode calculator share whose mint succeeds produces
   a PNG whose footer carries a `/s/p/<short_id>` URL on its own line below the `Dynasty Trade
   Finder` wordmark.
2. **[H]** The iOS share sheet for that share carries **both** the image and a text message
   containing the same URL.
3. **[H]** With the mint forced to fail (airplane mode), the same share produces a PNG whose footer
   carries the `?ref=<username>` referral URL — **not** an empty footer, and not the wordmark alone.
4. **[H]** On Android (or, if no device is available, by code read **[R]** of the
   `Platform.OS === 'android'` branch), the text share carries the resolved URL.
5. **[H]** When `captureRef` throws, the text fallback that is shared carries the resolved URL.
6. **[R]** No code path in `ShareTradeImage` can invoke `Share.share` with a body that contains
   neither a resolved URL nor an image — grep every `Share.share` call site in the file.
7. **[M]** In live mode with both sides filled and a verdict rendered, an element with id
   `calc.share-link.package`, `calc.share-link.ref` **or** `calc.share-link.root` is visible.
   (Which one is [OG-1](#operator-gates)-dependent; that **at least one** is visible is not.)

### The ladder

8. **[H]** A demo session's calculator share produces the `?ref=` URL and emits
   `share_package_created` with `outcome == "demo"`; **no** `POST /api/share/package` request is
   made (verify with the harness request log or a proxy).
9. **[H]** After 20 successful mints in one hour, the 21st distinct package degrades to the `?ref=`
   URL with **no error dialog and no hang**, and emits `outcome == "rate_limited"`.
10. **[H]** Re-sharing an **unchanged** package does not issue a second `POST /api/share/package`
    and does not emit a second `share_package_created` — the in-memory cache is hit.
11. **[H]** Re-sharing after changing one asset **does** issue a new mint.
12. **[R]** A package with more than five ids on either side never reaches the network — the client
    mirrors `_SHARE_PACKAGE_SIDE_MAX` (`server.py:16812`) before calling.
13. **[H]** A signed-out live-mode share degrades to the bare root (`calc.share-link.root`) and does
    not surface a 401 to the user.
14. **[H]** *(PR-14 = b only)* An in-league calculator share with a **draft pick** on either side
    degrades to `?ref=` and never mints. Verified by confirming no `/s/p/` URL appears and no
    `share_package_created` event fires.

### Deep links

15. **[H]** A `/s/tiers/<pos>/<username>` link opened on a device **with** the app installed lands on
    the **Tiers** board and produces **no** "link didn't work" toast. *(This is the regression the
    alias exists for.)*
16. **[H]** The same link opened on a device **without** the app renders the tier OG card in Safari.
17. **[H]** A `/s/p/<id>` link opened with the app installed lands in-app on Trades (the existing
    alias) with no fallback toast; opened without the app, it renders the package OG card with the
    CTA "Build your own trade".
18. **[R]** `rewriteUniversalPath` handles `/s/tiers/<pos>/<user>` with a query suffix
    (`?fmt=sf_tep`) without dropping the suffix — same treatment as the two existing branches.
19. **[P]** `test_universal_links.py` asserts that the AASA share claim is still **wholesale**
    (`/s/*` in both `components` and `paths`, with no narrower `/s/trade/*` or `/s/p/*` entry).

### Tier board affordance

20. **[M]** After a save on a per-position board, a toast action with id `toast.action` is visible.
21. **[H]** Tapping it opens the share sheet with a message containing
    `/s/tiers/<lowercase-pos>/<username>`.
22. **[H]** The URL omits `?fmt=` when the active format is `1qb_ppr` and includes
    `?fmt=sf_tep` when it is not — byte-identical in shape to `web/js/app.js:5285-5295`.
23. **[M]** After a save on the **ALL** board, **no** `toast.action` is visible.
24. **[H]** In a demo session, and with `growth.share_landing` off, no Share action appears on the
    save toast.

### Analytics

25. **[P]** All four event names — `calc_trade_shared`, `trade_card_shared`, `tier_board_shared`,
    `share_package_created` — survive `POST /api/events` with their **full** prop sets:
    `accepted == 4`, `dropped == 0`, and every prop echoed back. A deliberately misspelled name in
    the same batch is dropped.
26. **[R]** `share_package_created` is in `NON_INTENT_EVENTS`; `calc_trade_shared` and
    `tier_board_shared` are not. *(Gated on [OG-10](#operator-gates).)*
27. **[R]** `trade_card_shared`'s prop row was **modified in place** to
    `{trade_id, channel, landing, surface}` — not deleted and re-added.
28. **[H]** No share event fires when the user dismisses the share sheet;
    `share_package_created` **does** fire regardless of dismissal.
29. **[R]** No client `track()` for any of the four names exists on `main` until T1 has merged,
    deployed, and returned `dropped == 0` from a live probe.

### Comment rot and hygiene

30. **[R]** `grep -rn "no /s/ route exists" mobile/` returns **zero** hits. *(Both stale comments
    deleted; the second is PR-11-conditional — if PR-11 = defer, this criterion is scoped to
    `TradeCalculatorScreen.tsx` and the surviving comment is recorded in `GOTCHAS.md`.)*
31. **[R]** Both replacement comments cite `backend/server.py:16828` **by line**, so the next reader
    can verify the claim in one grep.
32. **[R]** `ShareTradeImage.tsx`'s file-header comment (`:12-21`) no longer describes a
    watermark-only card.

### Non-regression

33. **[T]** `npx tsc --noEmit` clean; `mobile/scripts/testid-lint.sh` exits 0.
34. **[M/P]** With `growth.share_landing` **off**, every changed message body, URL, toast and event
    is byte-identical to `ab9368f`; the full smoke suite (11 flows) is green; the existing 11 route
    cases in `test_share_package.py` are green unchanged.

---

## 5. Maestro flow specs

### 5.1 The coverage boundary, stated as a waiver (W-1)

**No flow taps a share button.** The iOS share sheet is `UIActivityViewController`, out of process.
README law 17 (`mobile/.maestro/README.md:140-145`) records that an undismissable SpringBoard
confirm is why deep links are dead in the harness; law 20 (`:154-160`) records a native confirm
"poisoned every later step". The fix is designed around this: the resolved URL renders **inside the
app** so the thing that was broken is assertable without opening the sheet. The sheet, the produced
PNG and the OG preview are covered by [§6](#6-manual-verification).

**Pre-existing-flow audit:** `grep -rn "share" mobile/.maestro/` returns **only prose**. No flow
references `calc.share-image` or any share affordance, so **no existing flow asserts the bug** and
none needs correcting in the same commit.

**Selectors are id-only.** No step uses a bare text matcher. Rung discrimination is carried in the
testID itself (`calc.share-link.package` / `.ref` / `.root`), not in a text assertion — README law 1
makes text matchers full-match regex, and `mobile/scripts/testid-lint.sh:20` bans text-selector taps
outright.

### 5.2 `mobile/.maestro/flows/growth/share-links.yaml`

New directory `flows/growth/` — shared with P1-5's `invite-promotion.yaml` (Wave B). No filename
collision.

**Header:**

```yaml
appId: com.fantasytradefinder.app
# tc: TC-SHR-01
# profile: standard
# flags: release
# source: docs/plans/audit-p1-remediation/PRD-p1-1-2.md §5.2
# The share sheet is out of process (README law 17/20) — NO step taps
# calc.share-image or tiers' toast action. The resolved URL renders in-app
# (calc.share-link.*) precisely so the fixed behaviour is assertable.
tags: [p1-1-2, growth, share]
```

**Preamble (blocks 1 and 3 share it)** — lifted verbatim from `flows/smoke/07-calculator.yaml:11-46`
so it cannot drift: cold `launchApp` with `clearState: true, clearKeychain: true, stopApp: true` →
`signin.username-input` → `qa_standard` → `signin.continue-btn` →
`leagues.row.990000000000000001` → `tab.trades` → conditional `outlook.save-btn` dismissal.

#### Block 1 — the calculator carries a link (OG-1-independent)

| # | Step | Id | Why |
|---|---|---|---|
| 1 | preamble | — | signed-in standard profile |
| 2 | `extendedWaitUntil visible` (20 000 ms) | `trades.subnav.calculator` | |
| 3 | `tapOn` | `trades.subnav.calculator` | |
| 4 | `extendedWaitUntil visible` (15 000 ms) | `calc.mode-tab.live` | |
| 5 | `tapOn` | `calc.mode-tab.live` | live mode is the only host that mounts `ShareTradeImage` on the calculator screen |
| 6 | `tapOn` | `calc.side-a-add` | |
| 7 | `extendedWaitUntil visible` (10 000 ms) | `calc.picker.search` | |
| 8 | `eraseText` then `tapOn` + `inputText: "Burrow"` | `calc.picker.search` | README law 22 — the picker keeps its text across opens |
| 9 | `pressKey: Enter` | — | README law 20 — **not** `hideKeyboard` |
| 10 | `extendedWaitUntil visible` (15 000 ms) | `calc.picker.row.6770` | Joe Burrow, a fixture-pool member already used by `07-calculator.yaml` |
| 11 | `tapOn` → `tapOn` | `calc.picker.row.6770`, `calc.picker.done` | |
| 12 | repeat 6–11 for side B with a second fixture-pool player | `calc.side-b-add`, `calc.picker.row.<id>` | both sides are required for `ShareTradeImage` to mount (`TradeCalculatorScreen.tsx:866`) |
| 13 | `scrollUntilVisible` `visibilityPercentage: 100`, `centerElement: true`, `direction: DOWN`, 15 000 ms | `calc.verdict` | README law 2 — `visible:` counts off-screen ScrollView children |
| 14 | `scrollUntilVisible` `visibilityPercentage: 100`, `centerElement: true` | `calc.share-image` | the actions row sits below the verdict |
| 15 | `assertVisible` | `calc.share-image` | the affordance exists |
| 16 | `assertVisible` | **`calc.share-link.ref`** *(lazy)* / **`calc.share-link.package`** *(eager)* | **the assertion that proves the artifact is never link-free** — see the note below |
| 17 | `takeScreenshot` | `p1-1-2__calc-share-link` | eyeballed per README law 23 |

**Step 16 is [OG-1](#operator-gates)-dependent, and this is the one place the answer changes the
flow:**

- **Lazy mint (the LLD's default).** Nothing has minted at this point, so the row shows the seeded
  referral rung → assert `calc.share-link.ref`. Rung A is **not** Maestro-provable and is carried by
  manual tests [M-1](#6-manual-verification) and [M-3](#6-manual-verification).
- **Eager mint.** The mint fires when the package settles, so assert `calc.share-link.package`.
  Rung A is then in the automated gate.

Write the flow for whichever answer comes back; do **not** write both and comment one out.

#### Block 2 — rung-B degradation *(EAGER ONLY)*

Under a lazy mint no request is made without a tap, so the injection would never fire and this block
would assert nothing it did not already assert in block 1. **Under eager it is the most valuable
block in the file** — it is what proves the ladder degrades rather than failing closed.

| # | Step | Detail |
|---|---|---|
| 1 | `runScript: helpers/inject.js` | **Armed before the calculator is opened** — README law 13. `INJECT_KIND: fail_next`, `INJECT_PATH: "/api/share/package"` (exact, no trailing `*` — law 15), `INJECT_STATUS: "429"`, `INJECT_COUNT: "1"` (bare POST mutation — law 11), `INJECT_BODY: '{"error": "rate_limited", "message": "Too many shares — try again later."}'` — the route's **real** body, read from `server.py:16864-16866`, per law 12 |
| 2 | `assertTrue: ${output.inject.ok}` | matches the house pattern at `capture/trades.yaml:86` |
| 3 | preamble + steps 2–14 of block 1 | build a **different** package from block 1's, or the mint cache returns block 1's success and the injection is never consumed |
| 4 | `assertVisible: calc.share-link.ref` | the link is **still present** and has degraded to the referral rung |
| 5 | `assertNotVisible: calc.share-link.package` | it degraded, rather than showing a stale rung-A row |
| 6 | `takeScreenshot: p1-1-2__calc-share-link-degraded` | |

#### Block 3 — the tier-board share affordance (OG-1-independent)

Runs from a fresh cold start (the react-query cache is persisted — README law 6).

| # | Step | Id | Why |
|---|---|---|---|
| 1 | preamble through the league row | — | |
| 2 | `extendedWaitUntil visible` (30 000 ms) | `tab.trades` | settle before any tab tap — README law 8 |
| 3 | `tapOn` | `tab.rank` | |
| 4 | `extendedWaitUntil visible` (10 000 ms) | `rankmenu.tiers` | |
| 5 | `tapOn` | `rankmenu.tiers` | |
| 6 | `extendedWaitUntil visible` (20 000 ms) | `tiers.list` | the board defaults to QB — a per-position board, so the affordance is eligible |
| 7 | `assertVisible` | `tiers.save-btn` | enabled whenever not saving/loading (`TiersScreen.tsx:1513`); no dirty-state requirement |
| 8 | `tapOn` | `tiers.save-btn` | |
| 9 | `extendedWaitUntil visible` (15 000 ms) | **`toast.action`** | the save toast's trailing Share action. **No tap** |
| 10 | `takeScreenshot` | `p1-1-2__tiers-share-toast` | |
| 11 | `tapOn` | `tiers.pos-tab.all` … | switch to the ALL board |
| 12 | `tapOn` | `tiers.save-btn` | |
| 13 | `extendedWaitUntil notVisible` (10 000 ms) | `toast.action` | **the negative** — no `/s/tiers/all/…` route exists, so the affordance must be absent |

Step 13 is what keeps the ALL-board suppression from silently regressing. `toast.action` is a
component-level id shared with P0-2's Undo toast; the tier save toast is the only toast in flight at
this point, so the assertion is unambiguous in context.

### 5.3 testIDs added

| testID | Where | Maestro-reachable | Registry |
|---|---|---|---|
| `calc.share-link.package` | `ShareTradeImage.tsx`, on-screen row | **yes** | `mobile/src/components/CLAUDE.md` |
| `calc.share-link.ref` | same | **yes** | same |
| `calc.share-link.root` | same | **yes** | same |
| `share.card-url` | `ShareTradeImage.tsx`, the **off-screen** capture surface (`left: -9999`, `:130`) | **no** | same — recorded so nobody later adds a flaky assertion for it |
| `toast.action` | `Toast.tsx` action `Pressable` (`:112`) | **yes** | same |

All five are **static string literals** written immediately after `testID=`, so
`mobile/scripts/testid-lint.sh:41-47` resolves them by grep and **no
`mobile/scripts/testid-lint-allow.txt` entry is needed** — which matters, because that file is
exclusively P1-7's for the whole of Wave A (`HLD-p1.md` §B). `calc.share-image` is **unchanged**.
Rationale for the three-way split and for `toast.action` over the plan's
`tiers.share-toast-action` is in `LLD-p1-1-2.md` §0 C-3 and C-4.

### 5.4 Existing flows

| Flow | Crosses this surface? | Expected | Action |
|---|---|---|---|
| `flows/smoke/07-calculator.yaml` | reaches `calc.verdict`, one scroll above the actions row | green | **run, not assumed** |
| `flows/smoke/04-tiers.yaml` | asserts `tiers.save-btn`, does not tap it | green | **run, not assumed** |
| all other smoke flows | no | green | run as part of tier 1 |

**No existing flow is edited.**

### 5.5 Screen re-capture delta

`calc`, `tiers`, **and `trades`** — the last one **unconditionally**, correcting
`plan-p1-1-2.md:414-415`. `screens/manifest.json` lists `mobile/src/components/Toast.tsx` in
`trades.source`, and M15 edits `Toast.tsx` whether or not PR-11 is answered "include"
(`LLD-p1-1-2.md` §0 C-2). `quick-set` is **not** in the delta ([OG-5](#operator-gates)).
`ShareTradeImage.tsx` appears in **no** source list and its card never renders on screen, so editing
it alone invalidates nothing.

Per `HLD-p1.md` §A.5, these three fold into the **single consolidated R1 pass** after Wave C — they
are not captured separately. Every shot is eyeballed (README law 23).

---

## 6. Manual verification

The parts Maestro structurally cannot reach. All are on-simulator or on-device, and all are
**decided from what is seen**, not asserted.

| # | Test | Pass condition |
|---|---|---|
| **M-1** | Live calculator → Share image → save the PNG out of the sheet | The footer's second line renders the `/s/p/<id>` URL, is legible at the card's 360 px width, and is not clipped or truncated |
| **M-2** | Same share, inspect the sheet | Both the image **and** a text message containing the URL are offered |
| **M-3** | Paste the produced link into iMessage on a device **without** the app | The OG preview renders the package card (`/og/p/<id>.png`) with the CTA "Build your own trade" |
| **M-4** | Same link on a device **with** the app | Opens in-app to Trades via the existing `/s/p/` alias — **no fallback toast** |
| **M-5** | Tier board → save → toast Share → open the link in Safari (no app) | The tier OG card renders |
| **M-6** | Same link on a device **with** the app | Opens in-app to the **Tiers** board and produces **no** fallback toast. *This is the regression the new alias exists for* |
| **M-7** | Airplane mode → share image | Rung B (`?ref=`) in both the PNG and the message; no error dialog, no hang; the spinner ends |
| **M-8** | Demo session → share image | Rung B, and `share_package_created.outcome == "demo"` with no network call |
| **M-9** | 21 distinct packages shared in one hour | The 21st degrades silently; `outcome == "rate_limited"` |
| **M-10** | *(PR-14 = b)* In-league calculator with a draft pick on a side | Rung B; no mint; no `"Unknown player"` landing is ever produced |
| **M-11** | *(PR-14 = a)* Same, inspecting the produced landing | Decide from the rendered card whether `"Unknown player"` is acceptable — this is the evidence [OG-7](#operator-gates) needs |
| **M-12** | Android device, if available | The text share carries the URL. If unavailable, record Android as an **untested platform** — `Platform.OS === 'android'` is a live branch (`ShareTradeImage.tsx:55-59`) |
| **M-13** | Flip `growth.share_landing` to `false`, rebuild | Every changed surface reverts to `ab9368f` behaviour; the tier Share action is absent |

---

## 7. Ship gate

- **Tier 1** — mobile screen change (`TradeCalculatorScreen`, `InLeagueCalculator`, `TiersScreen`,
  `Toast`, and `TradesScreen` if PR-11 = include). Full smoke suite (11 flows) **plus**
  `flows/growth/share-links.yaml`, plus the R1 capture refresh covering `calc`, `tiers`, `trades`.
  The backend half alone would be tier 4; the mobile change dominates and the higher tier governs.
- **Evidence:** a `living-memory/TEST_LEDGER.md` entry plus `qa/sim-runs/last-sim-run.json`.
  Enforced locally by `githooks/pre-push`. **`FTF_SKIP_SIM_GATE` is not used.**
- **Operator deviation from the matrix:** none proposed.
- **Preconditions, in order** (`HLD-p1.md` §C): P0 merges to `main` → this branch rebases →
  `LLD-p1-1-2.md` §1 answered **in writing** in `scope-p1-1-2.md` → **T1 merges, deploys, and its
  live `POST /api/events` probe returns `dropped == 0` with every prop echoed** → Wave A begins.
  **No client `track()` ships before that probe passes.**

---

## 8. Docs impact

| Doc | Updated? | What |
|---|---|---|
| `docs/api-reference.md` | **YES** | Rows `:544` and `:546` — the tier route's unflagged/QB-RB-WR-TE-only/AASA-alias facts, and that mobile now calls the package mint and from which surfaces. No route added, renamed, or contract-changed |
| `docs/cross-client-invariants.md` | **YES** | New section: the two share-URL shapes as a binding mobile↔web contract, including the `fmt`-omitted-when-`1qb_ppr` rule and the position set. **The `surface` enum bullet lands in `:268` via T1, not here** (`HLD-p1.md` §A.5) |
| `docs/config-reference.md` | **YES** | `growth.share_landing` (`:251`) — it now also gates the mint, the PNG URL and the tier affordance, **and it is already on**, so this ships live. Its rollback limit is stated |
| `docs/glossary.md` | **YES** | **share package**, **share link ladder** |
| `docs/runbook.md` | **YES** | New section: mint failures are expected and benign; the 20/user/hour cap and its 429 body; the diagnosis order when shares stop carrying `/s/p/` links |
| `living-memory/LLD.md` | **YES** | The AASA↔alias convention — it binds every future `/s/…` route, and nothing in CI checks the client half |
| `living-memory/DECISIONS.md` | **YES** | Four entries. **ID allocated at write time** — next free at `ab9368f` was `D-025`, **not** the `D-011` the plan claims |
| `living-memory/GOTCHAS.md` | **YES** | Two entries. Next free at `ab9368f` was `G-027`, **not** `G-013` |
| `docs/business/analytics/` tracking plan | **YES** | The four events; the no-baseline fact; the two semantic redefinitions. Appended at **T1.7's single section** |
| `living-memory/CHANGELOG.md`, `NEXT.md`, `TEST_LEDGER.md` | **YES at ship** | Standard write-back |
| `docs/data-dictionary.md` | **n/a** | No schema change; `shared_packages` documented at `:856` |
| `docs/architecture.md`, `living-memory/HLD.md` | **n/a** | One utility module inside an existing layer |
| `docs/coding-guidelines.md` | **n/a** | No new behavioural rule beyond the DECISIONS entries |
| `docs/adr/` | **n/a** | No choice of architectural weight |
| `docs/design/design-system.md`, `components.md` | **read, not edited** | Existing Chalkline tokens and the existing `Toast` action spec only |
| `living-memory/DEPENDENCIES.md` | **n/a** | `react-native-view-shot@4.0.3` is already installed and already used by this component |
| `docs/feedback/items/` | **n/a** | Audit-driven; home is `docs/plans/audit-p1-remediation/` |
| `docs/recovery/` | **at sweep** | Capture the tip sha and verify by content against `origin/main` before the worktree or branch is removed |

---

## 9. Operator gates

Twelve gates. **None is resolved by any planning document.** Each names what it blocks; a
**BUILD**-blocking gate stops A3 from starting the affected code.

| ID | Gate | Options | Plan's recommendation | Blocks | What is blocked, concretely |
|---|---|---|---|---|---|
| **OG-1** *(new — `LLD-p1-1-2.md` §0 C-1)* | **Eager or lazy mint?** The plan's Design §3 mints on press; its Maestro block 1 asserts the minted URL **without** a press. Both cannot be true | (a) **lazy** — mint on press; the 20/hour cap keeps meaning *shares*; rung A is not Maestro-provable and moves to manual M-1/M-3. (b) **eager** — mint when the package settles; buys automated rung-A and rung-B coverage and removes the paint race entirely; **changes what the server's abuse guard counts** (complete trades *built*, not shared) and writes `shared_packages` rows for builds nobody shares | (a) lazy — it does not silently redefine a server-side rate limit | **BUILD** | The `ShareTradeImage` state machine (`LLD-p1-1-2.md` §5.3 vs §5.6), and **step 16 and the whole of block 2** of `share-links.yaml` |
| **OG-2** *(OC-1 / RL-1)* | **Accept that this ships live on merge, or add `growth.share_v2` default OFF?** `growth.share_landing` is `true` in prod | (a) accept. (b) add a flag — a bright-line surface change, plus a second graduation step | (a) accept — the finding is that these paths convert zero, and a dark flag preserves exactly that | **BUILD** | Whether A3 adds a flag surface at all. `HLD-p1.md` R-1 asks the operator to answer this **for the whole round**, not just this item — **four** P1 items ship unguarded |
| **OG-3** *(OC-2 / PR-11)* | **Include the liked-but-unmatched trade share?** The same false comment lives in `TradesScreen.tsx:2735-2741`, on what the audit calls "the more common case" | (a) include (~20 lines, kills the second stale comment). (b) defer | (a) include | **BUILD** | Whether A3 holds `TradesScreen.tsx` at all (a 6 158-line file P0-2 and P0-8/9 rewrite), and whether AC-30 covers one file or two. **Does not affect the capture delta** — `trades` is in it either way |
| **OG-4** *(OC-3 / PV-5)* | **Tier-share privacy posture.** `/s/tiers` + `/og/tiers` publish a named user's board with **no flag and no opt-in**, while `/u/*` is dark behind two gates and #221 just *hid* the public-profile row | (a) ship as-is. (b) gate the **affordance** on `growth.share_landing`, leave the route unchanged. (c) add a server-side opt-in check — a route contract change | (b) | **BUILD** | `canShareTiers` in `LLD-p1-1-2.md` §8.2. **Separately:** none of the three stops direct enumeration of `/og/tiers/qb/<any-username>.png` today. If that is unacceptable it is a **P0-class finding of its own** and must be filed separately |
| **OG-5** *(OC-5 / PR-13)* | **Does the Quick Set completion also offer a share?** | (a) leave it (native `Alert`, untestable, already carries a next-step). (b) replace the `Alert` with a Chalkline sheet | (a) | release | Whether `quick-set` joins the R1 capture list |
| **OG-6** *(OC-4 / PR-12)* | **Should a tier link land on the shared position?** `TiersScreen` reads no route params, so `/s/tiers/wr/matt` opens at QB | (a) ship v1 without it. (b) teach the screen a `position` param (~15 lines) and make the alias lossless | (a) | **BUILD** | ~15 lines in A3 and whether the alias is lossy by design or by accident |
| **OG-7** *(OC-6 / PR-14)* | **Draft picks render `"Unknown player"` on the package landing** (`og_image.py:646-650`; a `pick_id` is not in the `players` table) | (a) mint anyway. (b) fall back to rung B when any pick is present — zero backend work. (c) teach `og_image` to render pick labels | (b) | **BUILD** | The `hasPickAssets` prop and ladder step 6 (`LLD-p1-1-2.md` §4.3, §6.2), AC-14, and manual M-10 vs M-11 |
| **OG-8** *(OC-7 / PR-15)* | **The landing's fairness bar can contradict the verdict in the PNG the user just shared.** `og_image._compute_fairness` is a cosmetic `search_rank` heuristic | (a) ship and file. (b) store the sharer's verdict on `shared_packages` — a **schema change**. (c) remove the bar | (b) as a fast-follow, not this plan | release | Nothing in this round. It becomes a live product defect the moment the route has callers — which is what this item does |
| **OG-9** *(OC-9 / W-3)* | **Web parity.** `web/js/app.js:5285-5301` has two dead builders | (a) wire now. (b) follow-up | (b) | release | Nothing in A3; doubles the review surface if taken |
| **OG-10** *(AN-4)* | **INTENT vs NON_INTENT for the three new share events.** `INTENT_EVENTS` is a **deny-list** (`analytics_queries.py:65`) — **silence ships all three as INTENT** | `calc_trade_shared` and `tier_board_shared` INTENT; **`share_package_created` NON_INTENT** (it is a system outcome, and under OG-1(b) it fires with no user gesture at all) | as stated | **BUILD — and before T1** | `T1.3`. Getting it wrong step-changes DAU/WAU on ship day, silently and permanently, and T1 **freezes the file** after it merges |
| **OG-11** *(OC-8)* | **Three copy strings.** (i) the PNG footer's rendered form — bare scheme-stripped URL, matching `og_image.py:171`, or a labelled "See this trade → …"; (ii) the iOS share-message caption that accompanies the image; (iii) the tier share message — "See how I tier my WRs → …" or naming the format | (i) bare URL, so the 360 px card stays legible | **BUILD** | Three string literals. The **functions** are specified in the LLD; the strings are not. **The in-flight button label is no longer an OG-11 item** — `Button.loading` already renders a spinner with no copy (`LLD-p1-1-2.md` §0 C-7e) |
| **OG-12** *(new — `LLD-p1-1-2.md` §0 C-6)* | **`living-memory` ID allocation.** Every plan in the round claims `D-011` / `G-013`; at `ab9368f` `DECISIONS.md` already runs to `D-024` and `GOTCHAS.md` to `G-026` | Allocate at write time, in merge order (`HLD-p1.md` §A.6) | as stated | release | The doc pass. Using the plan's IDs would write **duplicates of existing entries**, not just collide with siblings |

**Answered elsewhere, carried here for completeness:** `DECISIONS-p1.md` D-P1-03 keeps
`invite_shared` as the invite event name — no bearing on this item. `HLD-p1.md` §A.2 adjudicates the
shared taxonomy commit; this item does **not** propose a separate registration commit and does not
edit `analytics_taxonomy.py` or `analytics_queries.py` itself.

---

## 10. Release risk and rollback

### 10.1 The risk, named plainly

**There is no dark period.** `growth.share_landing` is on in production. The moment this merges,
every user gets: a URL in every shared PNG, a minted landing behind every calculator share, a Share
action on the tier-save toast, and a new deep-link alias. There is no staged rollout, no allowlist,
and no graduation step, because there is no flag to graduate.

`HLD-p1.md` §F R-1 records that **four of seven P1 items** are in this condition and that the
round's rollback story is therefore `git revert` for most of it. **OG-2 is the only checkpoint in
the round that asks the operator to accept this, and it is scoped to this item alone — the HLD
recommends answering it for the whole round.**

### 10.2 Secondary risks

| Risk | Mitigation | Residual |
|---|---|---|
| `Share.share({message, url})` on iOS — some targets take both activity items, others drop one | **The URL is also inside the PNG.** A target that drops the message still ships a visible link. That redundancy is why both halves of A-10 are done together | none material |
| The mint→paint→capture race captures the PNG before the footer updates | The footer is **seeded with the referral rung at mount** (`LLD-p1-1-2.md` §5.2), so a lost race degrades rung A → rung B, never link → no-link. Double-`requestAnimationFrame` barrier, never a fixed sleep | a silent quality regression, caught by manual M-1 |
| M3's alias hunk is lost in a `deepLinks.ts` rebase (three sequential writers: P0-3 → P1-1/2 → P1-9) | Manual M-6 is the **only** check — nothing in CI guards the client half. The convention entry in `living-memory/LLD.md` is the durable mitigation | real; `HLD-p1.md` R-4 |
| Two clients drift on the URL shape | `docs/cross-client-invariants.md` makes both shapes a recorded contract | low |
| `/s/tiers/all/…` does not exist | The affordance is suppressed on the ALL board, and **AC-23 asserts the absence in Maestro** | closed |
| No baseline for any share metric | `calc_trade_shared` has never landed a row and `trade_card_shared.landing` has always been stripped. **Any post-ship read is absolute, not a lift.** Stated in the tracking-plan addendum | real; do not let a dashboard imply a before/after that does not exist |

### 10.3 Rollback

**Lever 1 — deploy-free, seconds:** set `growth.share_landing` to `false` in
`config/features.json`. This reverts **every mobile behaviour in this item** to its pre-change form
(the flag-off branches are preserved byte-identical — AC-34) **and** 404s the package routes
server-side. One lever, both halves.

**What lever 1 does not cover:**

- `/s/tiers/<pos>/<username>` and `/og/tiers/…` stay live — they are **unflagged server-side**
  (`server.py:16759-16779`, `:16663-16680`). The flag only removes the mobile affordance; already-sent
  links keep resolving. That gap is OG-4.
- The `rewriteUniversalPath` alias stays in the shipped binary. This is **harmless and desirable**:
  with the flag off no new tier links are produced, and the alias only improves the handling of links
  already in the wild.
- **Telemetry stops too.** The `track` calls are gated on the same flag
  (`LLD-p1-1-2.md` §6.1), so flipping it off also removes the signal that would explain why it was
  flipped. This is a deliberate trade for a byte-identical flag-off branch, and it is the reason
  lever 1 should be followed by lever 2 rather than left in place.

**Lever 2 — `git revert` of A3's commit**, then EAS. Required if the defect is in the deep-link
alias, in `Toast.tsx`, or anywhere else the flag does not reach.

**Not a rollback lever:** removing the four names from `analytics_taxonomy.py`. They land in **T1**,
which three items depend on; reverting T1 would silently drop P1-5's and P1-10's events too.
Taxonomy corrections go through a **T1 amendment commit with the same deploy-and-verify gate**
(`HLD-p1.md` §B).
