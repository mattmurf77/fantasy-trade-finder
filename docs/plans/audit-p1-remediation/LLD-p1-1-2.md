# LLD — P1-1 + P1-2: share artifacts carry a link, and the two dead landings get callers

> **Purpose.** Implementation-level detail for audit findings **P1-1 (A-10)** and **P1-2 (A-11)**.
> An engineer builds from this without re-deriving the design: exact modules, signatures, call
> ordering, data shapes, error paths, state handling, and the precise diff sites.
>
> **Status:** design-only. No source file is changed by this document.
> **Authority order:** `DECISIONS-p1.md` → `HLD-p1.md` → `plan-p1-1-2.md` / `scope-p1-1-2.md` → this
> file. Where this file departs from the plan it says so in [§0](#0-corrections-to-the-plan) and
> never silently.
> **Worktree:** `/Users/teresadickens/Documents/Claude/Projects/ftf-p1-remediation`, branch
> `p1-remediation-2026-08-11` @ `ab9368f`. **Every line number below is `ab9368f` and is
> pre-P0.** [§1](#1-re-verify-after-p0-merge) is the gate that revalidates them.
> **Wave:** A3 (`HLD-p1.md` §B, Wave A), after commit **T1**.
> **Author:** LLD/PRD agent, 2026-08-11.

## Contents

- [0. Corrections to the plan](#0-corrections-to-the-plan)
- [1. Re-verify after P0 merge](#1-re-verify-after-p0-merge)
- [2. Shared types and the URL contract](#2-shared-types-and-the-url-contract)
- [3. `mobile/src/api/calc.ts` — `createSharePackage`](#3-mobilesrcapicalcts--createsharepackage)
- [4. `mobile/src/utils/shareLinks.ts` — the ladder](#4-mobilesrcutilssharelinksts--the-ladder)
- [5. `ShareTradeImage.tsx` — state, ordering, capture](#5-sharetradeimagetsx--state-ordering-capture)
- [6. Host wiring — the two calculators](#6-host-wiring--the-two-calculators)
- [7. `TradesScreen.tsx` — the liked-but-unmatched share (PR-11)](#7-tradesscreentsx--the-liked-but-unmatched-share-pr-11)
- [8. `TiersScreen.tsx` + `Toast.tsx` — the tier-board affordance](#8-tiersscreentsx--toasttsx--the-tier-board-affordance)
- [9. `deepLinks.ts` — the third alias](#9-deeplinksts--the-third-alias)
- [10. Analytics — this item's contribution to commit T1](#10-analytics--this-items-contribution-to-commit-t1)
- [11. Backend tests](#11-backend-tests)
- [12. Failure matrix](#12-failure-matrix)
- [13. Precise diff sites](#13-precise-diff-sites)
- [14. Docs deltas — what to write, not just where](#14-docs-deltas--what-to-write-not-just-where)
- [15. What this LLD deliberately does not decide](#15-what-this-lld-deliberately-does-not-decide)

---

## 0. Corrections to the plan

Seven places where `plan-p1-1-2.md` or `scope-p1-1-2.md` is wrong, internally inconsistent, or
under-specified against the code as it stands at `ab9368f`. Each was verified by reading the
file, not by inference.

### C-1 — **The plan's Maestro block 1 contradicts its own Design §3.** *(Material. New operator gate.)*

`plan-p1-1-2.md:212-220` (Design §3) mints **on press**: `onPress → setState('minting') → await
resolveShareUrl() → setState('ready') → rAF → captureRef`. `plan-p1-1-2.md:389-393` (Maestro
block 1) then asserts `calc.share-link` "matching `/s/p/`" — i.e. the **minted** rung-A URL —
**without tapping the share button** ("*No tap on the share button*", `:393`).

Under a lazy mint those two cannot both be true. Before the press there is no `/s/p/<id>`; after
the press the share sheet owns the foreground and Maestro can assert nothing.

This is not resolvable by an agent: it is a rate-limit-semantics question. Options, with the
consequence of each, are written up as **[OG-1](PRD-p1-1-2.md#operator-gates)** in the PRD. This
LLD is written against the **lazy** shape (the plan's Design §3, which is the shape the ladder was
designed for) with one structural change that removes the sharpest edge — see [§5.2](#52-the-seeded-floor).
If OG-1 returns "eager", [§5.6](#56-what-changes-if-og-1-returns-eager) states exactly what moves.

### C-2 — **`Toast.tsx` is a `trades` capture source. The capture delta is wrong.** *(Material.)*

`plan-p1-1-2.md:414-415` and `scope-p1-1-2.md:107-111` both say the capture delta is `calc` +
`tiers`, "+ `trades` **if** M11/M12 are taken". Verified in `screens/manifest.json`:

```
trades.source = ["mobile/src/screens/TradesScreen.tsx",
                 "mobile/src/components/SkeletonTradeCard.tsx",
                 "mobile/src/components/Toast.tsx",          ← here
                 "mobile/src/components/TradeCard.tsx"]
```

M15 edits `Toast.tsx` unconditionally. **`trades` is therefore in the capture delta whether or not
PR-11 is answered "include".** The plan's conditional is void. (`ShareTradeImage.tsx` genuinely is
in no source list — that half of the plan's claim holds.)

### C-3 — **`tiers.share-toast-action` cannot be lint-clean in Wave A.** *(Material. Design change.)*

`plan-p1-1-2.md:328` puts a `testID` passthrough on `Toast`'s action button and has `TiersScreen`
supply `'tiers.share-toast-action'`. `mobile/scripts/testid-lint.sh:41-47` resolves a flow id by
grepping `mobile/src` for `testID={\`?["'\`]*<id>` or `testID=["'{]*.<id>`. Supplying the id from
`TiersScreen` writes it as either `testID: 'tiers.share-toast-action'` (object field — `testID:`,
not `testID=`) or `actionTestID="…"` (capital `T`). **Neither grep matches**, so `testid-lint.sh`
fails. The escape hatch is `mobile/scripts/testid-lint-allow.txt` — which `HLD-p1.md` §B assigns
**exclusively to A1 (P1-7)** for the whole of Wave A.

**Correction:** the action button carries a **static, component-level** `testID="toast.action"`
written literally inside `Toast.tsx` ([§8.3](#83-toasttsx)). It is grep-visible, needs no allow
entry, and applies to every `Toast` action (including P0-2's Undo — an improvement, not a
regression). The flow disambiguates by context: it asserts `toast.action` immediately after
tapping `tiers.save-btn`.

### C-4 — **`calc.share-link` cannot carry a rung assertion under an id-only selector rule.** *(Material.)*

`plan-p1-1-2.md:393` and `:398` distinguish rung A from rung B with **text matchers** (`/s/p/`,
`?ref=`). The build brief for this round mandates id-selectors only; README law 1 additionally
makes text matchers full-match regex, so a substring match on a URL would need `.*` wrapping and
would still be a text matcher.

**Correction:** the rung is encoded in the **testID**, via three sibling JSX branches with string
literals — `calc.share-link.package` / `calc.share-link.ref` / `calc.share-link.root`
([§5.4](#54-the-on-screen-link-row)). A template literal (`` testID={`calc.share-link.${rung}`} ``)
would be README law 4 territory and would again need the allow file that A3 does not own.

### C-5 — **`hasPickAssets` cannot be derived from the id string.** *(Material.)*

`plan-p1-1-2.md:591` (OC-6 option b) says "fall back to rung B when any id is a `pick_id`". A
`pick_id` is `{league}_{season}_{round}_{original_roster}` (`backend/database.py:7588-7598`,
`make_pick_id`). Sleeper player ids are bare digits, but league ids in the pick id are also bare
digits joined by underscores — there is no shape that is safely a pick and not, for example, a
future id format. Regex-sniffing the id is a guess.

**Correction:** the host computes the flag from the data it already holds.
`InLeagueCalculator.tsx:204` sets `pos: 'PICK'` on every pick row and `:506` already tests
`p.pos === 'PICK'`. The prop is `hasPickAssets: boolean`, computed at the call site
([§6.2](#62-inleaguecalculatortsx-m8)). Live-mode calc passes `false` (universal pool = real
Sleeper ids).

### C-6 — **`living-memory` next IDs are not `D-011` / `G-013`; those are long since taken.** *(Factual.)*

`plan-p1-1-2.md:438-439` and `scope-p1-1-2.md:138` claim `D-011` and `G-013`. Verified at
`ab9368f`: `living-memory/DECISIONS.md` runs to **`D-024`** (`:209`), so the next free id is
**`D-025`**; `living-memory/GOTCHAS.md` uses `### G-0NN` headings and its maximum is **`G-026`**
(`:200`), so the next free id is **`G-027`**. `HLD-p1.md` §A.6's allocate-at-write-time rule still
governs — but note the collision it describes is *worse* than "nine claimants on D-011": every one
of the nine would have written a **duplicate of an existing entry**.

### C-7 — Smaller factual drifts, recorded so they are not re-derived

| # | Plan says | Actually |
|---|---|---|
| a | "Law 20 records a native confirm 'poisoned every later step' (`README.md:159-166`)" (`:382`) | Law 20 is at `mobile/.maestro/README.md:154-160` and is about **`hideKeyboard`**, not the share sheet. The nearer precedent is **law 17** (`:140-145`): "Deep links are dead (`openLink` → undismissable SpringBoard confirm on iOS 18)". Both support the W-1 waiver; cite law 17 as the primary. |
| b | "AASA still claims `/s/*` — assertion only" as a **new** test (B4, `:295`) | `backend/tests/test_universal_links.py:50` **already** asserts `{"/": "/s/*"} in components`. B4 as written is a duplicate. The non-duplicative addition is the `paths` half and the negative — see [§11.2](#112-test_universal_linkspy). |
| c | `buildTierShareUrl(pos, username, format)` "mirrors `web/js/app.js:5285-5295` byte-for-byte in shape" (`:305`) | The **URL shape** matches. The **signature** does not: web's `buildTierShareUrl(pos, username)` takes two arguments and reads the format from `window._currentUser.scoring_format` (`web/js/app.js:5290-5292`). Record the *shape* as the cross-client contract, not the signature. |
| d | `scope-p1-1-2.md:28` — `calc_trade_shared.mode` is "(`live`\|`demo`)" | `type CalcMode = 'live' \| 'demo' \| 'league'` (`TradeCalculatorScreen.tsx:86`). `'league'` never reaches `shareTrade` (In-league mode renders `InLeagueCalculator`, and the picker block is gated `mode !== 'league'` at `:922`), so the observed domain is two values — but the type is three and the prop is a free string server-side. Document the observed domain, do not assert the type. |
| e | The button needs a bespoke "in-flight state" (`:313`) | `Button` already has `loading?: boolean` — "Replaces the label with a spinner; implies disabled" (`mobile/src/components/chalkline/Button.tsx:18-19`, `:50`, `:54`, `:73`). No new prop, no new copy, **no OC-8 dependency for the in-flight state**. |

---

## 1. Re-verify after P0 merge

Run **before the first edit**, after `git fetch origin` + rebase onto post-P0 `origin/main`.
Answer each row **in writing in `scope-p1-1-2.md`**. Per `HLD-p1.md` §0.5, a row that comes back
"the premise no longer holds" **stops the build** and returns the item to planning — it is not
patched at the keyboard.

Rows 1–7 are `HLD-p1.md` §G.4 carried in verbatim. Rows 8–13 are this LLD's additions.

| # | Claim to re-check | How | Premise it protects | If it fails |
|---|---|---|---|---|
| 1 | `rewriteUniversalPath` still has the two-branch shape M3's third branch mirrors | `grep -n "rewriteUniversalPath" -A 12 mobile/src/utils/deepLinks.ts` (was `:191-200`) | [§9](#9-deeplinksts--the-third-alias). P0-3 added `LeagueJoin` to `V2_SCREENS` (`:95-178`) and a `?league=` capture at `:344-354` | Re-locate by content; the alias still goes after the `/s/p/` branch and before `return pathWithQuery` |
| 2 | AASA still claims `/s/*` **wholesale** | `sed -n '/apple_app_site_association/,/^# ---/p' backend/server.py` (was `:8076-8109`) | The entire justification for M3. P0-3 B1 adds `/app/league/join/*` to the same block | If P0-3 **narrowed** `/s/*`, R-4 changes shape and M3's comment must be rewritten before it is written |
| 3 | `TradesScreen.tsx:2735-2751` / `:2760-2766` still exist as one `shareLikedTrade` body | `grep -n "shareLikedTrade" -A 45 mobile/src/screens/TradesScreen.tsx` | [§7](#7-tradesscreentsx--the-liked-but-unmatched-share-pr-11). P0-2 makes ~18 edits, P0-8/9 four more, to a 6 158-line file | Re-locate by content only. **Never edit this file by line number.** |
| 4 | `Toast.tsx`'s action `Pressable` is still the element `testID` attaches to | `grep -n "action ?" -A 14 mobile/src/components/Toast.tsx` (was `:111-124`) | [§8.3](#83-toasttsx). P0-2 adds `topOffset` (`:99-102`, `:143-151`) | Re-locate the `Pressable`; the prop set is disjoint from P0-2's |
| 5 | `InLeagueCalculator.tsx:771` merged cleanly — read the merged `SendInSleeperButton` mount before adding M8's props at `:781-798` | Read `:765-800` | [§6.2](#62-inleaguecalculatortsx-m8). **P0-6 and P0-7 both edit `:771`** | Read, then edit below it |
| 6 | `growth.share_landing` is **still `true`** in `config/features.json` (was `:125`) **and** `backend/tests/fixtures/flags/release.json` (was `:126`) | `grep -n share_landing config/features.json backend/tests/fixtures/flags/release.json` | **RL-1's entire premise.** If it went dark, this item ships dark and the release-risk framing in the PRD inverts | Report to the operator before building; RL-1 must be re-answered |
| 7 | `docs/api-reference.md` rows `:544` / `:546` still exist | `grep -n "s/tiers\|api/share/package" docs/api-reference.md` | [§14](#14-docs-deltas--what-to-write-not-just-where). P0-1 and P0-3 both edit that file | Re-locate; the row content is what matters, not the line |
| 8 | `trade_card_shared`'s prop row is **still** `frozenset({"trade_id", "channel"})` and T1 widened it in place | `grep -n "trade_card_shared" backend/analytics_taxonomy.py` (was name `:74`, props `:222`) | [§10](#10-analytics--this-items-contribution-to-commit-t1). T1 owns the edit; A3 must **not** touch the file | If T1 re-added rather than modified the row, R-3 has already happened — stop and report |
| 9 | T1's live probe returned `dropped == 0` **and echoed every prop** for all four share names | `GET /api/analytics/health` + one hand-rolled `POST /api/events` per name | No `track()` in A3 may ship before this. `analytics_ingest.py:379-389` fails silently behind a 200 | No client wiring. `HLD-p1.md` §C step 1 gate |
| 10 | `screens/manifest.json` `trades.source` **still lists `Toast.tsx`** | `python3 -c "import json;print(json.load(open('screens/manifest.json'))['screens']['trades']['source'])"` | [C-2](#c-2--toasttsx-is-a-trades-capture-source-the-capture-delta-is-wrong). Governs the R1 capture list | If it changed, recompute the delta from the merged manifest |
| 11 | `living-memory/DECISIONS.md` and `GOTCHAS.md` maxima | `grep -n "^## D-0" living-memory/DECISIONS.md \| tail -1`; `grep -n "### G-0" living-memory/GOTCHAS.md \| tail -1` | [C-6](#c-6--living-memory-next-ids-are-not-d-011--g-013-those-are-long-since-taken). Was `D-024` / `G-026` at `ab9368f`; P0 will have added more | Allocate at write time, in merge order (`HLD-p1.md` §A.6) |
| 12 | `Button`'s `loading` prop still exists with the documented semantics | `grep -n "loading" mobile/src/components/chalkline/Button.tsx` (was `:18-19`, `:33`, `:50`, `:73`) | [§5.5](#55-the-buttons-in-flight-state) — the in-flight state depends on it | Fall back to `disabled` + a label swap, which reintroduces an OC-8 copy question |
| 13 | `mobile/node_modules` is still a symlink; **never run `npm install`**; do not run `tsc` from this worktree | `ls -l mobile/node_modules` | Standing brief constraint | Typecheck runs from the operator's primary checkout |

---

## 2. Shared types and the URL contract

All new types live in `mobile/src/utils/shareLinks.ts` and are imported from there. Nothing is
added to `mobile/src/shared/types.ts` (that file is a cross-client domain-type module; these are
share-plumbing types with one consumer surface).

```ts
/** Closed enum — mirrors backend/analytics_taxonomy.py CLIENT_EVENT_PROPS
 *  and docs/cross-client-invariants.md. Adding a value is a T1 change. */
export type ShareSurface = 'calc_live' | 'calc_in_league' | 'trades_liked' | 'tiers';

/** Which rung of the ladder produced the URL. Also the on-screen testID suffix. */
export type ShareRung = 'package' | 'ref' | 'root';

/** Why rung A was or wasn't reached. 'skipped' means no mint was attempted
 *  (flag off / no assets / over the side cap / picks present) and therefore
 *  NO share_package_created event is fired. */
export type MintOutcome = 'ok' | 'rate_limited' | 'demo' | 'failed';

export interface ResolvedShareUrl {
  /** Absolute, always non-empty, always safe to concatenate into a message. */
  url: string;
  rung: ShareRung;
  outcome: MintOutcome | 'skipped';
}
```

### 2.1 The three URL shapes (cross-client contract)

| Rung | Exact composition | Byte-equal to today's | Evidence |
|---|---|---|---|
| **A — package** | `${getBaseUrl()}/s/p/${short_id}?ref=${encodeURIComponent(username)}`; `?ref=` omitted when no username | new | `docs/api-reference.md:546` documents exactly `<base><url>?ref=<username>`; `url` comes back as `/s/p/<id>` from `server.py:16870-16875` |
| **B — referral root** | `${getBaseUrl()}/?ref=${encodeURIComponent(username)}` | **yes** — `TradeCalculatorScreen.tsx:529-530` builds `${getBaseUrl()}/${ref}` where `ref = "?ref=…"` | `TradeCalculatorScreen.tsx:529-530`, `TradesScreen.tsx:2749` |
| **C — bare root** | `${getBaseUrl()}/` | **yes** — the no-username branch of the same expressions | same |

**Tier link** (separate ladder-free shape, mirrors the web builder):

```
${getBaseUrl()}/s/tiers/${encodeURIComponent(pos.toLowerCase())}/${encodeURIComponent(username.trim())}
    + (format && format !== '1qb_ppr' ? `?fmt=${encodeURIComponent(format)}` : '')
```

Rules carried from `web/js/app.js:5285-5295` and enforced by the server:

- **`fmt` is omitted when the format is `1qb_ppr`** (web `:5292`; server defaults to `1qb_ppr` at
  `server.py:16760-16763`).
- **Position is lowercased in the path.** `og_image.py:304-309` upper-cases it and accepts only
  `QB | RB | WR | TE`; anything else renders a 404 placeholder. There is no `/s/tiers/all/…`.
- **Empty `pos` or `username` → `${getBaseUrl()}/`** (web's guard at `:5290`).

### 2.2 Client-side mirrors of server constraints

The client must not spend a request the server will reject. Three server rules are mirrored in
`resolveShareUrl` and each is a **cross-client invariant row**:

| Server rule | Value | Evidence | Client mirror |
|---|---|---|---|
| Max ids per side | 5 | `_SHARE_PACKAGE_SIDE_MAX`, `server.py:16812`; enforced `_clean_package_side` `:16818` | Skip the mint (outcome `skipped`) when either side exceeds it |
| At least one id overall | ≥1 | `server.py:16851` `not (give or receive)` → 400 | Skip the mint when both sides are empty |
| Id character class | `^[A-Za-z0-9_.\-]{1,40}$` | `_SHARE_PACKAGE_ID_RE`, `server.py:16813` | **Not** mirrored — a violating id is a data bug, and a 400 is the honest signal. Falls to rung B via `outcome: 'failed'` |
| Demo sessions refused | 400 `demo_session` | `server.py:16845-16847` | Skip the request; report `outcome: 'demo'` from `useSession.isDemo` (`useSession.ts:106`) |
| Rate limit | 20/user/hour | `_SHARE_PACKAGE_HOURLY_LIMIT`, `server.py:16811`; 429 `rate_limited` at `:16864-16866` | Not pre-empted; mapped on the response |

---

## 3. `mobile/src/api/calc.ts` — `createSharePackage`

New export, appended after `evaluateTradeInLeague` (`calc.ts:275`). **Never throws.**

```ts
/** POST /api/share/package — mint a public landing for an arbitrary
 *  give/receive build (backend/server.py:16828 create_share_package_route).
 *  404 while `growth.share_landing` is dark; 400 `demo_session` for demo
 *  users; 429 `rate_limited` at 20/user/hour.
 *
 *  Contract: NEVER throws and never rejects. Every failure is reported as a
 *  MintOutcome so the caller's ladder (utils/shareLinks.ts) can degrade
 *  honestly and so share_package_created.outcome is not a lie.
 */
export async function createSharePackage(
  givePlayerIds: string[],
  receivePlayerIds: string[],
  signal?: AbortSignal,
): Promise<
  | { outcome: 'ok'; short_id: string; url: string; og_image: string }
  | { outcome: 'rate_limited' | 'demo' | 'failed' }
> {
  try {
    const r = await apiRequest<{
      ok: boolean; short_id: string; url: string; og_image: string;
    }>('/api/share/package', {
      method: 'POST',
      signal,
      body: { give_player_ids: givePlayerIds, receive_player_ids: receivePlayerIds },
    });
    if (!r?.ok || !r.url || !r.short_id) return { outcome: 'failed' };
    return { outcome: 'ok', short_id: r.short_id, url: r.url, og_image: r.og_image };
  } catch (e) {
    if (e instanceof ApiError) {
      if (e.status === 429) return { outcome: 'rate_limited' };
      if (e.status === 400 && (e.body as any)?.error === 'demo_session') {
        return { outcome: 'demo' };
      }
    }
    return { outcome: 'failed' };   // 400 bad_package · 401 · 404 dark · 5xx · offline · abort
  }
}
```

**Notes an implementer needs:**

- **Auth.** No `skipAuth`. `/api/share/package` calls `_require_session()` (`server.py:16843`,
  definition `:2257-2273`), which raises `_SessionExpired` → **401** for a signed-out caller. The
  live-mode calculator is reachable signed-out; that path lands on `outcome: 'failed'` → rung C
  (no username either). Correct and intended.
- **Status mapping is exhaustive by design.** `404` (flag dark) is deliberately *not* distinguished
  from `failed`: the client already checked the flag before calling, so a 404 means client/server
  flag disagreement — an operational fault, not a product state. It shows up as
  `outcome: 'failed'` and in `_health` / the runbook diagnosis order ([§14](#14-docs-deltas--what-to-write-not-just-where)).
- **Timeout.** `RequestOptions` (`client.ts:281-289`) has no `timeout` field and adding one would
  edit a shared module for one call site. The caller supplies an `AbortSignal` instead
  ([§5.3](#53-the-mintpaintcapture-sequence)); a caller abort surfaces as a plain `AbortError`,
  which the `catch` maps to `failed`. `_reportApiFailure` excludes caller aborts
  (`client.ts:291-295`), so an abandoned mint does **not** pollute `api_request_failed`.
- **Retries.** The client's standard policy applies unchanged. `RETRY_STATUSES` retry logic lives
  at `client.ts:502-516`; nothing bespoke is added.
- **`ApiError` import.** Already exported from `./client` (`client.ts:162`); `calc.ts:6` imports
  `apiRequest` from the same module — extend that import, do not add a second.

---

## 4. `mobile/src/utils/shareLinks.ts` — the ladder

**New file.** Sole owner: A3. The single place either share URL is constructed on mobile.

### 4.1 Exports

```ts
export type { ShareSurface, ShareRung, MintOutcome, ResolvedShareUrl };

/** Rung B/C. Pure, synchronous, never throws, never empty. */
export function refShareUrl(username?: string | null): ResolvedShareUrl;

/** Cache key for a package. Order-sensitive — it mirrors the payload the
 *  server stores, and [A,B] vs [B,A] are two different rows. */
export function packageCacheKey(giveIds: string[], receiveIds: string[]): string;

/** The A→B→C ladder. NEVER throws, NEVER returns an empty url. */
export function resolveShareUrl(args: ResolveArgs): Promise<ResolvedShareUrl>;

/** Tier board share URL. Pure. Mirrors web/js/app.js:5285-5295 in SHAPE
 *  (see LLD §0 C-7c — the signatures differ). */
export function buildTierShareUrl(
  pos: string,
  username: string | null | undefined,
  format: ScoringFormat | null | undefined,
): string;

/** Test/debug seam only — clears the in-memory mint cache. Not called by
 *  product code. */
export function __resetShareLinkCache(): void;
```

```ts
export interface ResolveArgs {
  giveIds: string[];
  receiveIds: string[];
  username?: string | null;
  /** growth.share_landing, read by the caller via useFlag. */
  enabled: boolean;
  /** useSession.isDemo (useSession.ts:106). */
  isDemo: boolean;
  surface: ShareSurface;
  /** PR-14 (OC-6b): any league draft pick on either side. Computed by the
   *  host from its own data — never sniffed from the id (LLD §0 C-5). */
  hasPickAssets: boolean;
  signal?: AbortSignal;
  /** Injected so the module has no import cycle with api/events.ts and so
   *  a caller can suppress the event (nothing does today). */
  onOutcome?: (outcome: MintOutcome, giveN: number, receiveN: number) => void;
}
```

### 4.2 The mint cache

```ts
const MINT_CACHE = new Map<string, ResolvedShareUrl>();   // module scope
```

- **In-memory only.** No AsyncStorage, no TTL — `scope-p1-1-2.md:57-59` fixes this and it is right:
  a `/s/p/<id>` row is kept indefinitely (`docs/data-dictionary.md:856`) so a stale cache entry is
  never *wrong*, only *old*, and the cache dies with the process.
- **Key:** `` `${giveIds.join('+')}|${receiveIds.join('+')}` ``. Order-sensitive on purpose: the
  server stores the arrays as given (`create_shared_package`, `server.py:16870`), and the OG card
  renders them in order (`og_image.py:646-650`), so a reordered package is a different artifact.
- **Only successes and `demo` are cached.** `rate_limited` and `failed` are transient — caching them
  would make one 429 permanently downgrade a package for the rest of the session. `demo` is a
  property of the session, not the package, and is cheap to re-derive, so it is short-circuited at
  step 3 below and never reaches the cache anyway.
- **A cache hit does not refire `share_package_created`.** The event counts *attempts that reached
  the server*, so the mint rate and the share rate stay distinguishable.

### 4.3 `resolveShareUrl` — exact ordering

Steps run in this order. Every early return produces a link.

```
 1. const floor = refShareUrl(args.username)
        → rung 'ref'  when username is a non-empty trimmed string
        → rung 'root' otherwise
    `floor` is the value returned by EVERY subsequent failure path.

 2. if (!args.enabled)               return {...floor, outcome: 'skipped'}
        growth.share_landing off. No event. Byte-identical to today.

 3. if (args.isDemo)                 onOutcome('demo');   return floor
        The server would 400 (server.py:16845-16847); do not spend the call.

 4. const n = giveIds.length + receiveIds.length
    if (n === 0)                     return {...floor, outcome: 'skipped'}

 5. if (giveIds.length > 5 || receiveIds.length > 5)
                                     return {...floor, outcome: 'skipped'}
        Mirrors _SHARE_PACKAGE_SIDE_MAX (server.py:16812). No event — the
        request was never made, so there is no outcome to report.

 6. if (args.hasPickAssets)          return {...floor, outcome: 'skipped'}
        PR-14 / OC-6(b). Picks render "Unknown player" on the landing
        (og_image.py:646-650) because load_players_by_ids cannot resolve a
        pick_id. Gate: this branch exists ONLY if PR-14 = (b). See §15.

 7. const key = packageCacheKey(...)
    const hit = MINT_CACHE.get(key)
    if (hit)                         return hit                 // no event

 8. const res = await createSharePackage(giveIds, receiveIds, args.signal)
    onOutcome(res.outcome, giveIds.length, receiveIds.length)   // always

 9. if (res.outcome !== 'ok')        return floor               // rung B or C

10. const resolved = {
      url: `${getBaseUrl()}${res.url}` + (username ? `?ref=${enc(username)}` : ''),
      rung: 'package',
      outcome: 'ok',
    }
    MINT_CACHE.set(key, resolved)
    return resolved
```

**Never throws.** The whole body is wrapped so that any unexpected exception (a malformed
`getBaseUrl`, a thrown selector) returns `floor`. The one invariant the rest of the design leans on
is: **`resolveShareUrl` resolves, always, with a non-empty `url`.**

### 4.4 `buildTierShareUrl`

```ts
export function buildTierShareUrl(pos, username, format): string {
  const base = getBaseUrl();
  const posSeg = encodeURIComponent(String(pos ?? '').trim().toLowerCase());
  const u = encodeURIComponent(String(username ?? '').trim());
  if (!posSeg || !u) return `${base}/`;                 // web/js/app.js:5290
  const qs = format && format !== '1qb_ppr'
    ? `?fmt=${encodeURIComponent(format)}` : '';        // web/js/app.js:5291-5292
  return `${base}/s/tiers/${posSeg}/${u}${qs}`;
}
```

It does **not** validate the position against `QB|RB|WR|TE`. That guard belongs at the call site
(`TiersScreen` suppresses the affordance on the `ALL` board — [§8.2](#82-the-share-action-m14)),
because a builder that silently rewrites its input is worse than one that builds what it was asked
for. Recorded so a later reader does not "harden" it.

---

## 5. `ShareTradeImage.tsx` — state, ordering, capture

### 5.1 Props and reads

Props gained (`ShareTradeImage.tsx:34-47`):

```ts
  /** Give/receive ids in server order — the package to mint. */
  giveIds: string[];
  receiveIds: string[];
  surface: ShareSurface;
  /** True when either side holds a league draft pick. PR-14. */
  hasPickAssets: boolean;
```

`fallbackText` **stays** (`:46`) — the hosts still compose the body; the component appends the URL.
Nothing else in the prop list changes.

The component reads session and flag state **itself**, rather than taking four more props:

```ts
const user           = useSession((s) => s.user);
const isDemo         = useSession((s) => s.isDemo);
const shareLandingOn = useFlag('growth.share_landing');
```

Both hosts already do exactly this (`TradeCalculatorScreen.tsx:53-54, :132, :152`;
`InLeagueCalculator.tsx:33, :112`), so this is the house pattern, not a new one. It also keeps the
prop delta at the four the plan specified (M4) plus PR-14's one.

### 5.2 The seeded floor

```ts
const [link, setLink] = useState<ResolvedShareUrl>(() => refShareUrl(user?.username));
```

The footer and the on-screen row read `link` from first paint. **The card is therefore never
link-free at any instant**, including:

- before the user ever presses share,
- while the mint is in flight,
- if the paint barrier ([§5.3](#53-the-mintpaintcapture-sequence)) is somehow wrong.

This is a strict improvement on `plan-p1-1-2.md:212-224`, where the footer is empty until the mint
lands and R-3 ("the PNG captures without the footer") is a live silent-regression risk. Here the
worst case of a lost race is **rung B in the PNG instead of rung A** — degraded, never broken. It
also makes [OG-1](PRD-p1-1-2.md#operator-gates) a *coverage* question rather than a *correctness*
one.

A `useEffect` re-seeds the floor if `user?.username` arrives late (sign-in completing while the
calculator is mounted):

```ts
useEffect(() => {
  setLink((cur) => (cur.rung === 'package' ? cur : refShareUrl(user?.username)));
}, [user?.username]);
```

### 5.3 The mint→paint→capture sequence

State machine — three states, one transition each:

```ts
type SharePhase =
  | { kind: 'idle' }
  | { kind: 'minting' }
  | { kind: 'armed'; resolved: ResolvedShareUrl };
```

```
onPress()                                        // replaces share() at :52-73
├─ if (phase.kind !== 'idle') return;            // re-entrancy guard: a second
│                                                //   tap during the mint is a no-op
├─ haptics.selection();                          // unchanged, :53
├─ setPhase({ kind: 'minting' });                // Button → loading (§5.5)
├─ const ctrl = new AbortController();
│  const t = setTimeout(() => ctrl.abort(), MINT_DEADLINE_MS);   // 6000
├─ const resolved = await resolveShareUrl({
│     giveIds, receiveIds, username: user?.username,
│     enabled: shareLandingOn, isDemo, surface, hasPickAssets,
│     signal: ctrl.signal,
│     onOutcome: (outcome, give_n, receive_n) =>
│       track('share_package_created',
│             { surface, give_n, receive_n, outcome }, screenName),
│  });                                           // never throws (§4.3)
├─ clearTimeout(t);
├─ if (!mountedRef.current) return;               // unmounted mid-mint
├─ setLink(resolved);                             // ← footer + row now carry rung A
└─ setPhase({ kind: 'armed', resolved });         // ← triggers the effect below

useEffect(() => {                                 // NEW — the paint barrier lives here
  if (phase.kind !== 'armed') return;
  let cancelled = false;
  (async () => {
    await nextPaint();                            // ← the ONLY reason this is an effect
    if (cancelled || !mountedRef.current) return;
    await doCapture(phase.resolved);
    if (!cancelled && mountedRef.current) setPhase({ kind: 'idle' });
  })();
  return () => { cancelled = true; };
}, [phase]);
```

**Why the capture cannot live in `onPress`.** `captureRef` snapshots the **native** view hierarchy.
A value awaited inside `onPress` is not in that hierarchy until React commits *and* the batched
native mount operations have been flushed to the iOS UI thread. `setLink` + `setPhase` inside an
`async` handler are not batched with each other on all RN versions, and a `useEffect` body runs
after the JS commit but still before the UI thread has drawn.

**The barrier:**

```ts
const nextPaint = () =>
  new Promise<void>((r) =>
    requestAnimationFrame(() => requestAnimationFrame(() => r())),
  );
```

**Double** `requestAnimationFrame`, not single. One rAF yields one JS frame — which is usually but
not reliably enough for the UI thread to have processed the mount. Two guarantees at least one
complete UI-thread frame after commit. A fixed `setTimeout(…, 300)` is forbidden: it is the exact
"fixed sleep" pattern `mobile/scripts/testid-lint.sh:16` bans in flows, and the same discipline
applies to source (`plan-p1-1-2.md:524`, README law 1's spirit).

`doCapture` — the four platform paths, **all four of which now carry a URL**:

```ts
const withUrl = (text: string, url: string) => `${text}\n${url}`;

async function doCapture(resolved: ResolvedShareUrl) {
  try {
    if (Platform.OS === 'android') {                     // was :55-59
      const res = await Share.share({ message: withUrl(props.fallbackText, resolved.url) });
      report(res, resolved);
      return;
    }
    const uri = await captureRef(shotRef, {              // was :60-64, unchanged
      format: 'png', quality: 1, result: 'tmpfile',
    });
    const res = await Share.share({                      // was :65 — gains `message`
      message: shareCaption(resolved),                   // copy → OC-8
      url: uri,
    });
    report(res, resolved);
  } catch {
    try {                                                // was :67-68
      const res = await Share.share({ message: withUrl(props.fallbackText, resolved.url) });
      report(res, resolved);
    } catch {
      /* user dismissed or share unavailable — nothing to do (was :69-71) */
    }
  }
}
```

`report(res, resolved)` invokes `props.onShared?.(resolved)` **only** when
`res.action !== Share.dismissedAction`. See [§5.7](#57-dismissal-semantics).

### 5.4 The on-screen link row

Rendered as a sibling of the share `Button`, inside the fragment at `ShareTradeImage.tsx:107-113`.
Three literal branches — the reason is [C-4](#c-4--calcsharelink-cannot-carry-a-rung-assertion-under-an-id-only-selector-rule)
(id-only assertions) and [C-3](#c-3--tierssharetoastaction-cannot-be-lint-clean-in-wave-a)
(no allow-file access in Wave A):

```tsx
{link.rung === 'package' ? (
  <Text testID="calc.share-link.package" style={styles.linkRow} numberOfLines={1}>
    {displayUrl(link.url)}
  </Text>
) : link.rung === 'ref' ? (
  <Text testID="calc.share-link.ref" style={styles.linkRow} numberOfLines={1}>
    {displayUrl(link.url)}
  </Text>
) : (
  <Text testID="calc.share-link.root" style={styles.linkRow} numberOfLines={1}>
    {displayUrl(link.url)}
  </Text>
)}
```

- `styles.linkRow`: `{ ...type.label, color: chalk.faint, textAlign: 'center' }` — existing
  Chalkline tokens only, matching the card's own watermark treatment (`:157-164`). No new token, no
  new component (`docs/design/` is **read, not edited**).
- `displayUrl(u)` strips the scheme: `u.replace(/^https?:\/\//, '')`. The exact rendered string is
  **OC-8**; the function is specified, the copy is not.
- The row renders whenever the share `Button` renders. Under a lazy mint it shows rung B until the
  first press and rung A thereafter, for as long as the component stays mounted.

### 5.5 The Button's in-flight state

```tsx
<Button
  label="Share image"                       // UNCHANGED — no copy decision
  variant="secondary"
  testID="calc.share-image"                 // UNCHANGED — existing flows keep working
  loading={phase.kind !== 'idle'}           // spinner; implies disabled (Button.tsx:18-19, :50)
  onPress={onPress}
/>
```

`Button.loading` already replaces the label with a spinner and sets `accessibilityState.busy`
(`Button.tsx:54-57, :73`). No new prop, no new string. This closes `plan-p1-1-2.md:313`'s
"in-flight state" without touching copy.

### 5.6 What changes if OG-1 returns "eager"

Only three things. Recorded so the operator can price the option accurately:

1. `onPress`'s `await resolveShareUrl(...)` moves into a `useEffect` keyed on
   `[giveIds.join('+'), receiveIds.join('+'), shareLandingOn, isDemo, hasPickAssets]`, fired once
   per settled package. The mount conditions in both hosts already debounce this: the component only
   renders when `evalQuery.data` exists for the settled package
   (`TradeCalculatorScreen.tsx:866`, `InLeagueCalculator.tsx:780`).
2. `onPress` becomes `setPhase({kind:'armed', resolved: link})` with no await, and the whole
   `minting` state and the `AbortController` disappear.
3. The paint barrier becomes belt-and-braces rather than load-bearing — the footer is already
   painted before the press.

**What it costs:** the 20/hour limit (`server.py:16811`) stops counting *shares* and starts counting
*complete trades built*, and `shared_packages` accumulates rows for builds nobody shared. That is a
change to what a server-side abuse guard means, and it is why this is an operator gate and not an
LLD decision.

### 5.7 Dismissal semantics

`TradesScreen.tsx:2757` gates its `track` on `res.action !== Share.dismissedAction`.
`TradeCalculatorScreen.tsx:533-536` does **not** — it tracks unconditionally after `await
Share.share(...)`. Two conventions in one product.

**Pin: adopt the TradesScreen convention everywhere in this item.** `calc_trade_shared`,
`trade_card_shared` and `tier_board_shared` all fire only on a non-dismissed result;
`share_package_created` fires on every *mint attempt that reached the server*, dismissal-independent
(it measures the ladder, not the share).

This **narrows** what `calc_trade_shared` counts, from "the sheet opened" to "the share completed".
It is safe to do silently in the data because the event has **never landed a row** — it is absent
from `ALLOWED_CLIENT_EVENTS` (`analytics_taxonomy.py:38-99`) and every envelope has been
accepted-and-dropped since it shipped (`analytics_ingest.py:379-383`). There is no series to break.
Say so in the tracking-plan addendum.

### 5.8 The card footer

`ShareTradeImage.tsx:117-123` — the watermark `<Text>` at `:122` becomes a two-line footer block:

```tsx
<View style={styles.footer}>
  <Text style={styles.watermark}>Dynasty Trade Finder</Text>
  <Text
    testID="share.card-url"
    style={styles.footerUrl}
    numberOfLines={1}
    adjustsFontSizeToFit
    minimumFontScale={0.8}
  >
    {displayUrl(link.url)}
  </Text>
</View>
```

- `styles.footer`: `{ gap: 2, alignItems: 'stretch' }`. The card is fixed `width: 360` with
  `gap: space.md` between children (`:131-138`); collapsing the two lines into one `View` keeps the
  wordmark/URL pair tighter than the card's inter-block gap, which is what makes it read as one
  footer rather than two blocks.
- `styles.footerUrl` = the existing `watermark` style with `letterSpacing: 0` (a URL is not a
  wordmark and does not want tracking). Everything else — `fonts.uiSemi`, 11pt/14, `chalk.faint`,
  centred — is reused verbatim from `:157-164`.
- `adjustsFontSizeToFit` + `minimumFontScale` guard the widest realistic URL
  (`fantasy-trade-finder.onrender.com/s/p/XXXXXXXX?ref=<username>`) against truncation. Legibility at
  360px is decided from the produced PNG in manual test M-1, not asserted — `share.card-url` sits on
  the off-screen surface (`left: -9999`, `:130`) and **is not Maestro-reachable**. Recorded here so
  nobody later adds a flaky assertion for it.
- This mirrors the server's own OG footer, `og_image.py:170-174`
  (`_draw_footer` → `"Fantasy Trade Finder · fantasy-trade-finder.onrender.com"`), so the two
  artifacts finally read as one product.
- **The file header comment (`:12-21`) must be rewritten** — it currently describes a
  "small text-only 'Dynasty Trade Finder' watermark" and says nothing about a URL, a mint, or the
  ladder. Leaving it is exactly the A-33 comment-rot class this item exists to kill.

---

## 6. Host wiring — the two calculators

### 6.1 `TradeCalculatorScreen.tsx`

**M7 — the `ShareTradeImage` mount (`:867-884`).** Add four props; change nothing else:

```tsx
  giveIds={liveSendIds}                    // :124
  receiveIds={liveReceiveIds}              // :125
  surface="calc_live"
  hasPickAssets={false}                    // live pool = real Sleeper ids only
```

Mount condition is unchanged (`isLive && bothSides && evalQuery.data`, `:866`).

**M9 — the text share (`shareTrade`, `:497-538`).**

- **Delete `:523-527`** — the stale comment. Verified false: `POST /api/share/package` is at
  `server.py:16828` and `/s/p/<short_id>` at `:16878`, both live behind a flag that is **on**.
  Replacement comment must cite `backend/server.py:16828` by line so the next reader can check it in
  one grep (`plan-p1-1-2.md:531`, R-10).
- **`:528-531`** becomes:

```ts
    if (shareLandingOn) {
      const resolved = await resolveShareUrl({
        // Demo mode's assets are mock ids (data/tradeCalcMock) and the server
        // refuses demo sessions anyway (server.py:16845) — pass no ids so the
        // ladder short-circuits at step 4 and the demo message is byte-identical
        // to today's.
        giveIds:    isLive ? liveSendIds    : [],
        receiveIds: isLive ? liveReceiveIds : [],
        username: user?.username,
        enabled: shareLandingOn,
        isDemo: useSession.getState().isDemo,
        surface: 'calc_live',
        hasPickAssets: false,
        onOutcome: (outcome, give_n, receive_n) =>
          track('share_package_created',
                { surface: 'calc_live', give_n, receive_n, outcome }, 'Calculator'),
      });
      lines.push(`Build your own: ${resolved.url}`);
      landing = resolved.rung === 'package';
    }
```

`isDemo` is read imperatively via `useSession.getState()` rather than added as a selector — the
screen has no other need for it, and `shareTrade` is an event handler, not render code.

**M10 — the track call (`:532-537`).**

```ts
    try {
      const res = await Share.share({ message: lines.filter(Boolean).join('\n') });
      if (shareLandingOn && res.action !== Share.dismissedAction) {
        track('calc_trade_shared',
              { mode, landing, ...(isLive ? { surface: 'calc_live' } : {}) },
              'Calculator');
      }
    } catch { /* unchanged */ }
```

Three deliberate choices:

- **`surface` is omitted on the demo lane** rather than adding a fifth `ShareSurface` value. The
  enum is frozen by T1 and documented in the prop-row comment; omitting an optional prop is not an
  enum change, and `mode: 'demo'` already carries the distinction. Recorded so nobody "fixes" it by
  adding `calc_demo`.
- **The `track` stays gated on `shareLandingOn`.** P1-5 removes an analogous gate on `invite_shared`
  with the rationale "measurement must not be flag-gated" (`plan-p1-5.md:266`); this item does not
  follow, because `scope-p1-1-2.md:72-77` makes `growth.share_landing → false` the **one-lever
  deploy-free rollback** and that lever's contract is *byte-identical pre-change behaviour*. Keeping
  the gate preserves it. The cost — a rollback also kills the telemetry that would explain the
  rollback — is stated in the PRD's rollback section rather than hidden.
- `landing` is a `let` declared beside `lines` and defaulted `false`, so the flag-off branch still
  compiles and still passes `landing: false`.

### 6.2 `InLeagueCalculator.tsx` (M8)

`:781-798`, the `ShareTradeImage` mount:

```tsx
  giveIds={giveIds}                        // :117
  receiveIds={receiveIds}                  // :118
  surface="calc_in_league"
  hasPickAssets={
    [...giveIds, ...receiveIds].some((id) => playerById[id]?.pos === 'PICK')
  }
```

`pos: 'PICK'` is set on every owned-pick row at `:204`; `:506` already uses this exact predicate to
suppress the tier badge. **This is the whole of PR-14's implementation** — no regex, no backend
work ([C-5](#c-5--haspickassets-cannot-be-derived-from-the-id-string)).

`ShareTradeImage`'s own `useSession`/`useFlag` reads mean this component needs no new imports.

**Re-verify row 5** applies: P0-6 and P0-7 both edit `:771` (the `SendInSleeperButton` mount, ten
lines above). Read the merged block before editing.

---

## 7. `TradesScreen.tsx` — the liked-but-unmatched share (PR-11)

**Conditional on PR-11 = "include".** If PR-11 = "defer", §7 is not built, A3 does not hold
`TradesScreen.tsx`, and the second stale comment stays in the tree (which must then be recorded, not
forgotten).

**M11 — `shareLikedTrade` (`:2728-2769`).**

- **Delete `:2735-2741`** — the second stale comment, the one the audit missed. It carries the same
  false claim as `TradeCalculatorScreen.tsx:523-527` and sits on what the audit itself calls "the
  more common case".
- The URL ladder at `:2745-2751` becomes:

```ts
    const ref = user?.username ? `ref=${encodeURIComponent(user.username)}` : '';
    let landing = false;
    let url: string;
    if (!shareLandingOn) {
      url = 'https://fantasy-trade-finder.onrender.com';        // :2750, byte-identical
    } else if (matchId) {
      url = `${getBaseUrl()}/s/trade/${matchId}${ref ? `?${ref}` : ''}`;   // :2748, unchanged
      landing = true;
    } else {
      const resolved = await resolveShareUrl({
        giveIds:    c.give_player_ids,          // api/trades.ts:285, :319-321
        receiveIds: c.receive_player_ids,       // api/trades.ts:286, :322-324
        username: user?.username,
        enabled: true,
        isDemo: useSession.getState().isDemo,
        surface: 'trades_liked',
        hasPickAssets:
          c.give_players.some(isPickAsset) || c.receive_players.some(isPickAsset),
        onOutcome: (outcome, give_n, receive_n) =>
          track('share_package_created',
                { surface: 'trades_liked', give_n, receive_n, outcome }, 'Trades'),
      });
      url = resolved.url;
      landing = resolved.rung === 'package';
    }
```

`isPickAsset` is a local helper: `(p: Player) => p.position === 'PICK' || p.pick_value != null`
(`mobile/src/shared/types.ts:29`, `:33` — `pick_value?: number | null // for draft picks`).
**Re-verify:** whether finder cards can contain picks at all is not established at `ab9368f`; the
predicate is written to be correct either way and costs nothing if the answer is "never".

The matched branch is **unchanged** — `/s/trade/<match_id>` already resolves and already has an alias
(`deepLinks.ts:196-197`). Only the unmatched branch moves.

**M12 — the track call (`:2755-2767`).**

```ts
      if (res.action !== Share.dismissedAction) {           // unchanged, :2757
        track(
          'trade_card_shared',
          shareLandingOn
            ? { trade_id: c.trade_id, landing, surface: 'trades_liked' }
            : { trade_id: c.trade_id },                     // unchanged flag-off shape
          'Trades',
        );
      }
```

`landing` widens from "a `/s/trade/` landing was used" to "the artifact carried a rich landing
(`/s/trade/` **or** `/s/p/`)". Safe to redefine silently in the data: `landing` has been **stripped
by ingest since it shipped** (`analytics_taxonomy.py:222` = `frozenset({"trade_id", "channel"})`;
strip at `analytics_ingest.py:384-389`), so no row has ever carried it. Record the redefinition in
the tracking-plan addendum.

`channel` is **not** sent — neither client has ever sent it, and inventing a value now would make the
new rows incomparable with the (empty) history. It stays in the allowlist as a reserved name.

---

## 8. `TiersScreen.tsx` + `Toast.tsx` — the tier-board affordance

### 8.1 Toast state (M13, `:125`)

```ts
const [toast, setToast] = useState<{
  msg: string;
  tone?: 'success' | 'warn';
  action?: { label: string; onPress: () => void };
} | null>(null);
```

The `action` shape is copied from `Toast`'s own `Props` (`Toast.tsx:20-22`) so the two cannot drift.

### 8.2 The share action (M14)

New imports required in `TiersScreen.tsx`: `Share` added to the `react-native` import list
(`:2-16`); `track` from `'../api/events'`; `resolveShareUrl` is **not** needed — only
`buildTierShareUrl` from `'../utils/shareLinks'`.

New reads near `:118-135`:

```ts
const user           = useSession((s) => s.user);
const isDemo         = useSession((s) => s.isDemo);
const shareLandingOn = useFlag('growth.share_landing');   // PV-5 recommendation (b)
```

A memoised eligibility predicate, defined next to them:

```ts
// The tier share is offered only where the route can actually serve it:
//   • not the ALL board — og_image.py:304-309 accepts QB|RB|WR|TE only, and
//     there is no /s/tiers/all/... route (server.py:16759).
//   • not a demo session — there is no server-side board to render.
//   • a username exists — it is the route's second path segment.
//   • growth.share_landing is on — PV-5(b): the affordance gets the kill
//     switch that already exists, while /s/tiers itself stays unflagged.
const canShareTiers =
  !isAllView && !isDemo && !!user?.username && shareLandingOn;
```

In `saveMutation.onSuccess` (`:383-384`), the toast gains the action:

```ts
    onSuccess: () => {
      setToast({
        msg: 'Tiers saved',
        tone: 'success',
        ...(canShareTiers
          ? {
              action: {
                label: 'Share',                            // copy → OC-8
                onPress: () => void shareTierBoard(),
              },
            }
          : {}),
      });
      // …existing invalidations unchanged…
    },
```

```ts
async function shareTierBoard() {
  if (!canShareTiers || !user?.username || isAllView) return;
  const fmt = effectiveFormat;             // see the note below
  const url = buildTierShareUrl(position, user.username, fmt);
  try {
    const res = await Share.share({ message: `<OC-8 copy> ${url}` });
    if (res.action !== Share.dismissedAction) {
      track('tier_board_shared',
            { position, format: fmt, surface: 'tiers' }, 'Tiers');
    }
  } catch { /* sheet cancelled or unavailable — nothing to record */ }
}
```

**`effectiveFormat`.** `TiersScreen` already resolves it at `:1009-1011`:
`activeFormat ?? tiersStatusQuery.data?.scoring_format ?? '1qb_ppr'`. Use **that** value, not the
raw `activeFormat` at `:118`, so the URL's `?fmt=` matches the board that was actually saved. It is
declared below `saveMutation` (`:310`) in source order, which is safe: the mutation's callback body
executes after render, so there is no TDZ hazard. Stated explicitly because it looks wrong at a
glance.

**`position` narrowing.** `position` is `BoardTab = Position | 'ALL'` (`:82`, `:123`). The
`!isAllView` guard narrows it for TypeScript in `shareTierBoard`'s body only if the guard is
`position === 'ALL'`-shaped; `isAllView` is a derived boolean and does **not** narrow. Use an
explicit `if (position === 'ALL') return;` inside `shareTierBoard`, or a local
`const pos = position as Position` with the guard above it. The former is preferred — it is a real
runtime guard, not a cast.

### 8.3 `Toast.tsx`

Two changes, both minimal:

1. `Props.action` (`:20-22`) — **unchanged**. No `testID` field is added
   ([C-3](#c-3--tierssharetoastaction-cannot-be-lint-clean-in-wave-a)).
2. The action `Pressable` (`:112-124`) gains a **static literal** `testID="toast.action"`:

```tsx
        {action ? (
          <Pressable
            testID="toast.action"
            onPress={() => { action.onPress(); onDismiss?.(); }}
            …unchanged…
```

Register `toast.action` in `mobile/src/components/CLAUDE.md`'s testID registry. That file has four
other P1 claimants (`HLD-p1.md` §A.5); A3 writes it in Wave A, first.

**Note for the P0-2 owner (informational, no action):** this testID also lands on P0-2's Undo toast
action. That is additive and is an improvement — P0-2's action currently has no id at all.

### 8.4 The Toast mount (M15, `:1129-1134`)

```tsx
      <Toast
        visible={!!toast}
        message={toast?.msg || ''}
        tone={toast?.tone}
        action={toast?.action}
        onDismiss={() => setToast(null)}
      />
```

One line added. `Toast` already dismisses itself after the action fires (`Toast.tsx:114-115`).

### 8.5 Deliberately not touched

`QuickSetTiersScreen.tsx:272-286`'s completion `Alert.alert('Tiers set', …)` gets **no** share
action (W-4 / PR-13). It is a native dialog — untestable by Maestro, and README law 17's precedent
is that a native confirm poisons every later step. It already carries a "Quick rank" next-step. The
save toast one screen later covers the same board. `quick-set` is therefore **not** in this item's
capture delta.

---

## 9. `deepLinks.ts` — the third alias

`rewriteUniversalPath`, `mobile/src/utils/deepLinks.ts:191-200`. Current body:

```ts
export function rewriteUniversalPath(pathWithQuery: string): string {   // :191
  const qi = pathWithQuery.search(/[?#]/);                              // :192
  const rawPath = qi === -1 ? pathWithQuery : pathWithQuery.slice(0, qi);
  const suffix  = qi === -1 ? '' : pathWithQuery.slice(qi);
  const path = rawPath.replace(/^\/+/, '').replace(/\/+$/, '');
  const trade = /^s\/trade\/([^/?#]+)$/i.exec(path);                    // :196
  if (trade) return `app/matches/${trade[1]}${suffix}`;                 // :197
  if (/^s\/p\/[^/?#]+$/i.test(path)) return `app/trades${suffix}`;      // :198
  return pathWithQuery;                                                 // :199
}
```

**Insert one branch between `:198` and `:199`:**

```ts
  // /s/tiers/<pos>/<username> → the Tiers board.
  //
  // MANDATORY, not polish. AASA claims /s/* WHOLESALE — backend/server.py:8104
  // ("paths": ["/u/*", "/s/*"]) and :8100 ({"/": "/s/*"}) — so on an installed
  // device iOS opens the app for EVERY /s/… url. A /s/ shape with no alias
  // here is unroutable, and _routePathV2 returning false lands the user on
  // navigate('Main') + _notifyLinkFallback ("link didn't work") at :356-363.
  // Shipping the tier share without this branch would greet every recipient
  // who has the app with an error toast.
  //
  // The <pos> segment is DROPPED in v1: TiersScreen reads no route params
  // (TiersScreen.tsx:113-125 — `position` is local state defaulting to 'QB'),
  // so /s/tiers/wr/matt opens the board at QB. Teaching the screen to accept
  // a position param is PR-12, deliberately deferred.
  if (/^s\/tiers\/[^/?#]+\/[^/?#]+$/i.test(path)) return `app/rank/tiers${suffix}`;
```

**Verification of the target path.** `app/rank/tiers` is composed from `V2_SCREENS`:
`Main.path = 'app'` (`:141`) → `Main.screens.Rank.path = 'rank'` (`:144`) →
`Rank.screens.Tiers = 'tiers'` (`:147`). Confirmed by reading, not inferred.

**Both resolution paths are covered by one edit** — cold start goes through
`getLinkingV2().getStateFromPath` (`:207-212`), which calls `rewriteUniversalPath`; warm start goes
through `_routePathV2` via `handleDeepLink` (`:352-364`). This is the reason the aliases live in this
function rather than in `V2_SCREENS` (a screen can only own one path — `:184-190`).

**Query suffix is preserved** exactly as the other two branches do, so `?fmt=sf_tep` survives the
rewrite (and is then ignored by `TiersScreen`, per PR-12).

**Ownership.** `plan-p1-9.md:605` has already published that P1-1/2 owns `:189-199` in this file and
that the three writers (P0-3 → P1-1/2 → P1-9) are disjoint. **Do not stray outside
`rewriteUniversalPath`** — `V2_TRADE_KINDS` (`:262`) is P1-9's and the `?league=` capture
(`:344-354`) is P0-3's.

---

## 10. Analytics — this item's contribution to commit T1

**A3 does not edit `backend/analytics_taxonomy.py` or `backend/analytics_queries.py`.** Both files
are owned by the T1 agent and are **frozen after T1 merges** (`HLD-p1.md` §B). This section is the
spec T1 implements on this item's behalf — exact contents, ready to paste.

### 10.1 `ALLOWED_CLIENT_EVENTS` (T1.1) — appended as its own commented block

```python
    # Share loop (audit P1-1/P1-2 — docs/plans/audit-p1-remediation/plan-p1-1-2.md).
    # `calc_trade_shared` is a REPAIR, not a new signal: TradeCalculatorScreen
    # has fired it since it shipped while the name was absent from this set, so
    # analytics_ingest.py:379-383 _health_bump("dropped_unknown_type")'d every
    # envelope behind a 200. There is NO historical series for it.
    # `surface` on all three is the closed enum
    #   calc_live | calc_in_league | trades_liked | tiers.
    "calc_trade_shared", "tier_board_shared", "share_package_created",
```

### 10.2 `CLIENT_EVENT_PROPS` (T1.2) — three new rows

```python
    # Share loop (P1-1/P1-2). `landing` is TRUE when the artifact carried a
    # rich landing (/s/p/<id> or /s/trade/<id>) and FALSE when the link ladder
    # degraded to a bare ?ref= — i.e. it is the rung-A hit rate as seen by the
    # user, not by the mint.
    "calc_trade_shared":     frozenset({"mode", "landing", "surface"}),
    "tier_board_shared":     frozenset({"position", "format", "surface"}),
    # `outcome` ∈ ok | rate_limited | demo | failed — the rung-A SUCCESS rate,
    # the only way to tell "nobody shares" from "sharing is broken". Fired on
    # every attempt that reached the server, dismissal-independent. This is a
    # SYSTEM OUTCOME, not a user action — see NON_INTENT_EVENTS below (AN-4).
    "share_package_created": frozenset({"surface", "give_n", "receive_n", "outcome"}),
```

### 10.3 `CLIENT_EVENT_PROPS` (T1.2) — one **modified** row

`analytics_taxonomy.py:222`, verified at `ab9368f` as:

```python
    "trade_card_shared":     frozenset({"trade_id", "channel"}),
```

becomes:

```python
    # +landing +surface (P1-1/P1-2). `landing` has been STRIPPED since it
    # shipped — TradesScreen.tsx has sent it and analytics_ingest.py:384-389
    # dropped it silently. `channel` is reserved: no client has ever sent it.
    "trade_card_shared":     frozenset({"trade_id", "channel", "landing", "surface"}),
```

**MODIFY IN PLACE.** Do not delete-and-re-add — a three-way merge that takes the pre-existing row
keeps the event working and delivers every row propless, with no error anywhere
(`HLD-p1.md` §F, R-3). Record the pre-edit contents verbatim in the T1 commit message.

### 10.4 `NON_INTENT_EVENTS` (T1.3) — the AN-4 answer, stated explicitly

`backend/analytics_queries.py:60-63`. `INTENT_EVENTS` is a **deny-list** (`:65`:
`(SERVER_FIRED_EVENTS | ALLOWED_CLIENT_EVENTS) - NON_INTENT_EVENTS`), so **silence ships all three
as INTENT**. This item's intended classification, written down rather than left to the default:

| Event | Classification | Why |
|---|---|---|
| `calc_trade_shared` | **INTENT** — no edit | A user tapped share and completed it. A real return. |
| `tier_board_shared` | **INTENT** — no edit | Same. |
| `share_package_created` | **NON_INTENT** — `NON_INTENT_EVENTS += "share_package_created"` | It is a *system outcome* of a user action, not the action. Under the eager variant of [OG-1](PRD-p1-1-2.md#operator-gates) it would fire without any user gesture at all. Leaving it INTENT step-changes DAU/WAU on ship day, silently and permanently — the same class of error `plan-p1-5.md` A3 was written to prevent. |

**This is AN-4 and it is an operator gate, build-blocking, and it must be answered *before* T1**
(`HLD-p1.md` §E.3, §G.1). The LLD states the intent; it does not decide it.

### 10.5 Prop domains (for the addendum and the T1 test)

| Prop | Domain | Source |
|---|---|---|
| `mode` | `live \| demo` observed; the type is `live \| demo \| league` | `TradeCalculatorScreen.tsx:86`; `league` never reaches `shareTrade` ([C-7d](#c-7--smaller-factual-drifts-recorded-so-they-are-not-re-derived)) |
| `landing` | boolean | [§6.1](#61-tradecalculatorscreentsx), [§7](#7-tradesscreentsx--the-liked-but-unmatched-share-pr-11) |
| `surface` | `calc_live \| calc_in_league \| trades_liked \| tiers`; **omitted** on the calculator's demo lane | [§2](#2-shared-types-and-the-url-contract), [§6.1](#61-tradecalculatorscreentsx) |
| `position` | `QB \| RB \| WR \| TE` | `og_image.py:304-309`; `ALL` is suppressed at the affordance |
| `format` | `1qb_ppr \| sf_tep` | `TiersScreen.tsx:1009-1011` |
| `give_n` / `receive_n` | integer 0–5 | `_SHARE_PACKAGE_SIDE_MAX`, `server.py:16812` |
| `outcome` | `ok \| rate_limited \| demo \| failed` | [§2](#2-shared-types-and-the-url-contract). `skipped` is a **client-side** state that fires **no event** |
| `trade_id` | string | unchanged |

---

## 11. Backend tests

A3 owns `backend/tests/test_universal_links.py`. `backend/tests/test_share_package.py` is **T1's**
(`HLD-p1.md` §B, T1.5) — the spec below is what T1 implements for this item.

### 11.1 `test_share_package.py` (T1.5) — the silent-drop regression guard

```
test_p1_1_2_share_events_accepted_with_full_props
```

Post one `/api/events` batch carrying four envelopes — `calc_trade_shared`, `trade_card_shared`,
`tier_board_shared`, `share_package_created` — each with its **complete** prop set from
[§10.5](#105-prop-domains-for-the-addendum-and-the-t1-test). Assert:

1. `accepted == 4` **and `dropped == 0`** — catches a lost name set (R-2).
2. For every envelope, the persisted `props` echo **every key sent** — catches a lost prop row
   modification (R-3). Acceptance alone is not enough; `plan-p1-5.md:246` names prop survival as
   "the assertion that would have caught D3".
3. A negative mirror: one deliberately misspelled name (`calc_trade_share`) in the same batch is
   `dropped`, proving the allowlist is still doing work.

The existing 11 route cases (`test_share_package.py:62-160`) stay green unchanged — **no route is
modified by this item**.

### 11.2 `test_universal_links.py` (B4) — corrected

`test_aasa_claims_invite_and_share_surfaces_only:40-54` **already** asserts
`{"/": "/s/*"} in components` (`:50`). The plan's B4 as written is a duplicate
([C-7b](#c-7--smaller-factual-drifts-recorded-so-they-are-not-re-derived)). The non-duplicative
addition:

```
test_aasa_share_claim_is_wholesale_so_every_s_path_needs_a_client_alias
```

1. `"/s/*" in detail["paths"]` — the legacy fallback half, currently unasserted.
2. No **narrower** share claim exists: `{"/": "/s/trade/*"}` and `{"/": "/s/p/*"}` are **not** in
   `components`, and no entry in `paths` starts with `/s/` other than `/s/*`. A future narrowing
   would silently invalidate `rewriteUniversalPath`'s third branch, and this is the only place that
   would notice.
3. A docstring naming `mobile/src/utils/deepLinks.ts:rewriteUniversalPath` as the client half, so a
   reader who narrows the claim finds the consequence.

**Note the asymmetry, honestly:** this test guards the *server* half. Nothing in CI guards the
*client* half — if M3's hunk is lost in a `deepLinks.ts` rebase (three sequential writers), every
tier share opens the app onto an error toast and **nothing fails**. That is `HLD-p1.md` R-4, and
manual test M-4 is its only check. The mitigation is the convention entry in
`living-memory/LLD.md` ([§14](#14-docs-deltas--what-to-write-not-just-where)).

---

## 12. Failure matrix

Every path, what the user gets, what the data gets. **No cell produces a link-free artifact.**

| # | Condition | Detected | `rung` | PNG footer | Message body | `share_package_created.outcome` | UI |
|---|---|---|---|---|---|---|---|
| 1 | Happy path | — | `package` | `/s/p/<id>?ref=` | caption + `/s/p/<id>?ref=` | `ok` | sheet opens |
| 2 | `growth.share_landing` off | `useFlag` | `ref`/`root` | root URL | today's message, byte-identical | *(no event)* | unchanged |
| 3 | Demo session | `useSession.isDemo` (`:106`) | `ref`/`root` | `?ref=` | `?ref=` | `demo` | sheet opens |
| 4 | Signed out | 401 from `_require_session` (`server.py:2257-2273`) | `root` | bare root | bare root | `failed` | sheet opens |
| 5 | 429 rate limited | `ApiError.status === 429` (`server.py:16864-16866`) | `ref` | `?ref=` | `?ref=` | `rate_limited` | sheet opens, **no error dialog** |
| 6 | Offline / timeout | thrown, caught | `ref` | `?ref=` | `?ref=` | `failed` | sheet opens |
| 7 | Mint exceeds 6 s | `AbortController` ([§5.3](#53-the-mintpaintcapture-sequence)) | `ref` | `?ref=` | `?ref=` | `failed` | spinner ends, sheet opens |
| 8 | >5 ids on a side | client mirror ([§2.2](#22-client-side-mirrors-of-server-constraints)) | `ref` | `?ref=` | `?ref=` | *(no event — never sent)* | sheet opens |
| 9 | Draft pick on a side (PR-14=b) | `pos === 'PICK'` (`InLeagueCalculator.tsx:204`) | `ref` | `?ref=` | `?ref=` | *(no event)* | sheet opens |
| 10 | `captureRef` throws | existing catch (`:66`) | unchanged | *(no PNG)* | `fallbackText` **+ URL** | already fired | text share |
| 11 | Paint barrier loses the race | not detectable | `package` in state | **rung B** (the seeded floor, [§5.2](#52-the-seeded-floor)) | rung A | `ok` | degraded, not broken |
| 12 | `Share.share` throws | inner catch (`:69-71`) | — | — | — | already fired | silent no-op, as today |
| 13 | User dismisses the sheet | `res.action === Share.dismissedAction` | — | — | — | already fired | no share event ([§5.7](#57-dismissal-semantics)) |
| 14 | Component unmounts mid-mint | `mountedRef` | — | — | — | already fired | no state write, no crash |
| 15 | Second tap during the mint | `phase.kind !== 'idle'` guard | — | — | — | — | no-op |
| 16 | Flag on client, route 404 server-side | 404 → `failed` | `ref` | `?ref=` | `?ref=` | `failed` | sheet opens; runbook diagnosis order |

Row **11** is the design's answer to `HLD-p1.md` R-3: the seeded floor converts a silent
correctness bug into a silent *quality* regression, and the two are not the same severity.

---

## 13. Precise diff sites

Every site. **Line numbers are `ab9368f` and are pre-P0** — [§1](#1-re-verify-after-p0-merge) row 5
and the `HLD-p1.md` §G.0.5 rule apply: **re-locate by content, never edit by line.**

| # | File : line | Current | Intended |
|---|---|---|---|
| **M1** | `mobile/src/api/calc.ts` : after `:275` | — | `createSharePackage()` + `ApiError` added to the `./client` import at `:6` ([§3](#3-mobilesrcapicalcts--createsharepackage)) |
| **M2** | `mobile/src/utils/shareLinks.ts` | *(new file)* | Types, `refShareUrl`, `packageCacheKey`, `resolveShareUrl`, `buildTierShareUrl`, `MINT_CACHE` ([§4](#4-mobilesrcutilssharelinksts--the-ladder)) |
| **M3** | `mobile/src/utils/deepLinks.ts` : between `:198` and `:199` | two aliases | third alias `^s/tiers/<pos>/<user>$` → `app/rank/tiers` + the AASA comment ([§9](#9-deeplinksts--the-third-alias)) |
| **M4** | `ShareTradeImage.tsx` : `:34-47` | 9 props | +`giveIds`, `receiveIds`, `surface`, `hasPickAssets` ([§5.1](#51-props-and-reads)) |
| **M4b** | `ShareTradeImage.tsx` : `:12-21` | header comment describes a watermark-only card | rewritten: URL footer, the ladder, the mint→paint→capture ordering ([§5.8](#58-the-card-footer)) |
| **M5** | `ShareTradeImage.tsx` : `:52-73` | `share()` — capture then `Share.share({url})` | `onPress` + `phase` state + the paint-barrier effect + `doCapture` ([§5.3](#53-the-mintpaintcapture-sequence)) |
| **M5b** | `ShareTradeImage.tsx` : `:108-113` | `<Button>` alone | `<Button loading=…>` + the three-branch link row ([§5.4](#54-the-on-screen-link-row), [§5.5](#55-the-buttons-in-flight-state)) |
| **M6** | `ShareTradeImage.tsx` : `:122` | `<Text style={styles.watermark}>Dynasty Trade Finder</Text>` | two-line footer `<View>` + `<Text testID="share.card-url">` ([§5.8](#58-the-card-footer)) |
| **M6b** | `ShareTradeImage.tsx` : `:157-164` | `watermark` style | +`footer`, +`footerUrl`, +`linkRow`; `watermark` unchanged |
| **M7** | `TradeCalculatorScreen.tsx` : `:867-884` | 9 props | +`giveIds`, `receiveIds`, `surface="calc_live"`, `hasPickAssets={false}` ([§6.1](#61-tradecalculatorscreentsx)) |
| **M8** | `InLeagueCalculator.tsx` : `:781-798` | 9 props | +`giveIds`, `receiveIds`, `surface="calc_in_league"`, `hasPickAssets={…'PICK'…}` ([§6.2](#62-inleaguecalculatortsx-m8)) |
| **M9a** | `TradeCalculatorScreen.tsx` : `:523-527` | stale comment: "no `/s/` route exists for arbitrary packages" | **deleted**; replaced with a comment citing `backend/server.py:16828` |
| **M9b** | `TradeCalculatorScreen.tsx` : `:528-531` | `lines.push("Build your own: " + base + ref)` | `await resolveShareUrl(...)` → `lines.push(...)`; `landing` captured ([§6.1](#61-tradecalculatorscreentsx)) |
| **M10** | `TradeCalculatorScreen.tsx` : `:532-537` | `await Share.share(...)`; unconditional `track('calc_trade_shared', {mode})` | `res.action` gate + `{mode, landing, surface?}` ([§5.7](#57-dismissal-semantics)) |
| **M11a** | `TradesScreen.tsx` : `:2735-2741` *(PR-11)* | second stale comment, same false claim | **deleted**; replaced with a citing comment |
| **M11b** | `TradesScreen.tsx` : `:2745-2751` *(PR-11)* | ternary ladder ending at the bare root | matched branch unchanged; unmatched branch → `resolveShareUrl` ([§7](#7-tradesscreentsx--the-liked-but-unmatched-share-pr-11)) |
| **M12** | `TradesScreen.tsx` : `:2755-2767` *(PR-11)* | `{trade_id, landing}` | `{trade_id, landing, surface:'trades_liked'}`; `landing` redefined |
| **M13** | `TiersScreen.tsx` : `:125` | `{msg, tone?}` | `+action?: {label, onPress}` ([§8.1](#81-toast-state-m13-125)) |
| **M13b** | `TiersScreen.tsx` : `:2-16`, `:118-135` | — | `Share` import; `track` import; `buildTierShareUrl` import; `user`/`isDemo`/`shareLandingOn` reads; `canShareTiers` |
| **M14** | `TiersScreen.tsx` : `:383-384` | `setToast({msg:'Tiers saved', tone:'success'})` | + conditional `action`; new `shareTierBoard()` ([§8.2](#82-the-share-action-m14)) |
| **M15a** | `Toast.tsx` : `:112` | `<Pressable onPress={…}>` | `+ testID="toast.action"` ([§8.3](#83-toasttsx)) — **not** the plan's `tiers.share-toast-action` |
| **M15b** | `TiersScreen.tsx` : `:1129-1134` | 4 props | `+action={toast?.action}` ([§8.4](#84-the-toast-mount-m15-11291134)) |
| **M16** | `mobile/src/components/CLAUDE.md` | testID registry | register `toast.action`, `calc.share-link.{package,ref,root}`, `share.card-url` |
| **T1.1/2/3** | `backend/analytics_taxonomy.py`, `analytics_queries.py` | — | **T1's commit, not A3's** ([§10](#10-analytics--this-items-contribution-to-commit-t1)) |
| **B4** | `backend/tests/test_universal_links.py` : after `:56` | — | `test_aasa_share_claim_is_wholesale_…` ([§11.2](#112-test_universal_linkspy)) |
| **MA** | `mobile/.maestro/flows/growth/share-links.yaml` | *(new)* | PRD § Maestro flow specs |

**Not touched, deliberately:** `web/js/app.js:5285-5301` (W-3 / OC-9 — the two dead builders stay
dead this round); `QuickSetTiersScreen.tsx` (W-4 / PR-13); `backend/server.py` (no route added,
renamed, or contract-changed); `config/features.json` (no flag added or re-defaulted);
`backend/database.py` (no schema change).

---

## 14. Docs deltas — what to write, not just where

`scope-p1-1-2.md` §4 lists the files. This section states the **content**, so the doc pass is not
re-derived at ship time.

| Doc | Content to write |
|---|---|
| `docs/api-reference.md:544` | On the `GET /s/tiers/<pos>/<username>` row: it is **unflagged** (`server.py:16759-16779` — no `is_enabled`, unlike `/s/p/*` at `:16881`); it accepts **QB/RB/WR/TE only** (`og_image.py:304-309`); `?fmt=` is omitted for `1qb_ppr`; it is **now linked from the mobile tier board**; and `/s/*` is AASA-claimed so **every client must alias it** or the link lands on the in-app fallback toast. |
| `docs/api-reference.md:546` | On `POST /api/share/package`: mobile now calls it, from `calc_live`, `calc_in_league` and (PR-11) `trades_liked`; the composed URL is `<base><url>?ref=<username>` exactly as already documented; the client mirrors the ≤5-per-side cap before calling; a 429 is **expected and benign**. |
| `docs/cross-client-invariants.md` (new section, **not** `:268`) | The two share-URL shapes from [§2.1](#21-the-three-url-shapes-cross-client-contract) as a binding contract between `mobile/src/utils/shareLinks.ts` and `web/js/app.js:5285-5295`: the `fmt`-omitted-when-`1qb_ppr` rule, the lowercase position segment, the QB/RB/WR/TE-only set, and the empty-input→`/` guard. Note that the **shapes** match and the **signatures** do not ([C-7c](#c-7--smaller-factual-drifts-recorded-so-they-are-not-re-derived)). **The `surface` enum bullet goes into `:268` via T1, not here** (`HLD-p1.md` §A.5 — three analytics writers fold their `:268` edits into T1). |
| `docs/config-reference.md:251` | Rewrite `growth.share_landing`: it now additionally gates the package mint, the URL in the shared PNG, and the tier-board share affordance — **and it is already `true` in `config/features.json:125`**, so this ships live on merge. Name it as the one-lever deploy-free rollback, and state its limit: it does **not** cover `/s/tiers` + `/og/tiers`, which are unflagged server-side. |
| `docs/glossary.md` | **share package** — a `/s/p/<id>` snapshot of an arbitrary give/receive build, minted by `POST /api/share/package`. **share link ladder** — the rung A/B/C degradation in `mobile/src/utils/shareLinks.ts`; the invariant is that no share artifact is ever link-free. |
| `docs/runbook.md` (new short section) | Mint failures are expected and benign — the ladder degrades to `?ref=` and the user sees no error. The 20/user/hour cap (`server.py:16811`) and its exact 429 body. Diagnosis order when shares stop carrying `/s/p/` links: (1) `growth.share_landing` in `config/features.json`; (2) `/api/analytics/health` → `dropped_unknown_type` (a taxonomy regression, not a share regression); (3) the route's own 404. Add: `share_package_created.outcome` is the field that separates "nobody shares" from "sharing is broken". |
| `living-memory/LLD.md` | **The convention, and it is load-bearing:** *any path shape claimed by AASA must have a matching `rewriteUniversalPath` alias, or the link opens the app onto the fallback toast instead of the browser.* `/s/*` is claimed wholesale (`server.py:8100`, `:8104`), so this binds **every future `/s/…` route**. Nothing in CI checks the client half ([§11.2](#112-test_universal_linkspy)). |
| `living-memory/DECISIONS.md` | Four entries, IDs allocated at write time (next free at `ab9368f` was **`D-025`** — [C-6](#c-6--living-memory-next-ids-are-not-d-011--g-013-those-are-long-since-taken)): (1) reuse `growth.share_landing` rather than mint a flag, accepting that this ships live; (2) the ladder degrades rather than blocking the share, so no artifact is ever link-free; (3) the tier affordance is the save toast, **not** the Quick Set native `Alert`; (4) web stays unwired this round. |
| `living-memory/GOTCHAS.md` | Two entries (next free at `ab9368f` was **`G-027`**): (1) `captureRef` snapshots the **native** tree — an awaited value must be committed *and painted* before capture, so a mint cannot live in the same handler body; **double** rAF, never a fixed sleep; the seeded floor is what makes a lost race degrade instead of break. (2) Comment rot: **two** files in two screens carried the same false "no `/s/` route exists" claim for weeks after the route shipped (same class as A-33 and P0-3's `InviteLeaguematesBanner` finding). Both replacements cite `server.py:16828` **by line** so the next reader can check in one grep. |
| `docs/business/analytics/` (tracking-plan addendum) | The four events with the prop domains from [§10.5](#105-prop-domains-for-the-addendum-and-the-t1-test); the AN-4 INTENT/NON_INTENT split; that `calc_trade_shared` has been **dropped** and `trade_card_shared.landing` **stripped** since they shipped, so **there is no baseline**; that `calc_trade_shared` narrows from "sheet opened" to "share completed" ([§5.7](#57-dismissal-semantics)); that `trade_card_shared.landing` widens to cover `/s/p/` as well as `/s/trade/`; that `channel` remains reserved and unsent. **Append point is T1.7's single section** (`HLD-p1.md` §A.5). |
| `docs/data-dictionary.md` | **n/a** — no `backend/database.py` change. `shared_packages` is documented at `:856`, including the public-by-URL note and the keep-indefinitely rule. |
| `docs/architecture.md`, `living-memory/HLD.md` | **n/a** — one utility module inside an existing layer; no backend wiring change. |
| `docs/design/` | **read, not edited** — `type.label`, `chalk.faint`, `fonts.uiSemi`, the existing `Toast` action spec. No new component, no new token, no radius or accent exception. |

---

## 15. What this LLD deliberately does not decide

Nine plan checkpoints plus everything the HLD routed to the operator. **None is resolved here.** The
PRD lists each as a gate with its blocking consequence.

- **RL-1 / OC-1** — ships live on merge, or add `growth.share_v2`. Determines whether A3 adds a flag
  surface at all.
- **PR-11 / OC-2** — include the liked-but-unmatched share. Determines whether §7 exists, whether A3
  holds `TradesScreen.tsx`, and (independently of the answer — [C-2](#c-2--toasttsx-is-a-trades-capture-source-the-capture-delta-is-wrong))
  nothing about the `trades` capture delta.
- **PV-5 / OC-3** — tier-share privacy posture. §8.2's `canShareTiers` is written for recommendation
  (b); (a) removes the `shareLandingOn` term, (c) is a route contract change and out of scope.
- **PR-12 / OC-4** — does a tier link land on the shared position. §9 drops `<pos>`; (b) adds a
  `TiersScreen` route param and a lossless alias.
- **PR-13 / OC-5** — Quick Set completion share. §8.5 declines it.
- **PR-14 / OC-6** — draft picks on the package landing. §4.3 step 6 and §6.2 implement (b); under
  (a) both are deleted; (c) is backend renderer work.
- **PR-15 / OC-7** — the landing's fairness bar contradicting the app's verdict. Nothing in this
  round; (b) is a schema change.
- **OC-8** — three copy strings: the PNG footer's rendered form, the iOS message caption
  (`shareCaption()`, §5.3), and the tier share message (§8.2). The **functions** are specified; the
  **strings** are not. The in-flight button label is **no longer** an OC-8 item
  ([C-7e](#c-7--smaller-factual-drifts-recorded-so-they-are-not-re-derived)).
- **OC-9 / W-3** — web parity. §13 leaves `web/js/app.js:5285-5301` dead.
- **AN-4** — INTENT membership for the three new events. §10.4 states the intent; the gate must clear
  before T1 freezes the file.
- **OG-1 (new, this LLD)** — eager vs lazy mint. See [C-1](#c-1--the-plans-maestro-block-1-contradicts-its-own-design-3-material-new-operator-gate)
  and [§5.6](#56-what-changes-if-og-1-returns-eager).
