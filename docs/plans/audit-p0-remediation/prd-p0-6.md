# PRD — P0-6: a matched non-Sleeper user gets a reason and an action

> **Requirements + acceptance.** No code changed by this document. Worktree
> `/Users/teresadickens/Documents/Claude/Projects/ftf-p0-remediation`, branch
> `p0-remediation-2026-08-10`. Build agent **`W1-P06`**, wave 1, HLD §3 **commit 8**.
>
> **Companions:** [`lld-p0-6.md`](lld-p0-6.md) (code-level design) · [`plan-p0-6.md`](plan-p0-6.md)
> (verified current state + options evaluated) · [`scope-p0-6.md`](scope-p0-6.md) (feature-scope
> block, three waivers) · [`hld.md`](hld.md) (**binding** — §2 S-23…S-29, §4 `W1-P06`, §9 LLD-5).
>
> **Source finding:** `docs/business/product/2026-08-09-mobile-ux-audit/07-build-handoff-prompt.md`
> § P0-6. **Type:** Bug, effort S. **Flag:** none added — rides `trade.send_in_sleeper` (S-24).

## Contents

- [1. Problem](#1-problem)
- [2. Users and surfaces affected](#2-users-and-surfaces-affected)
- [3. Requirements](#3-requirements)
- [4. Copy spec](#4-copy-spec)
- [5. Acceptance criteria](#5-acceptance-criteria)
- [6. Non-goals](#6-non-goals)
- [7. The P0-7 handoff contract](#7-the-p0-7-handoff-contract)
- [8. Docs rows](#8-docs-rows)
- [9. Rollback](#9-rollback)
- [10. Open items for the operator](#10-open-items-for-the-operator)

---

## 1. Problem

`SendInSleeperButton` gates on one boolean. Verbatim, `SendInSleeperButton.tsx:273`:

```ts
  if (!enabled || isEspn) return null;
```

Two distinct failures follow from that one line, on three platforms.

**ESPN — silent absence.** A user in an imported ESPN league can get a mutual trade match; nothing in
the matching pipeline excludes them (`backend/server.py:10012-10014` excludes only the demo league,
and `trade_matches` is league-scoped with no platform column). Their match card renders `Dismiss` and
nothing else. There is no send action, no copy explaining why, and no alternative offered. The user
reached the single highest-intent moment the product has — a leaguemate wants the same trade — and
the app's answer is a blank space.

**MFL / Fleaflicker — a live button that always fails.** `isEspn` tests `platform === 'espn'` only,
but `LeaguePickerScreen` stamps `'mfl'` and `'fleaflicker'` into the same cached list. So on those
leagues the button **renders and is enabled**. `POST /api/sleeper/propose` validates only
`league_id.isdigit()` (`backend/server.py:12336`) — and MFL and Fleaflicker league ids are numeric —
so the request passes validation, queries Sleeper's roster space for a league that does not exist
there, and returns `400 roster_not_found`. The client maps that to *"Couldn't send — Couldn't match
one of the teams to a roster in this Sleeper league"* — a confusing dead end **after** the user has
already been through the link/verify webview. This half was not in the audit; it is worse than the
graded finding.

The fix is one change with two effects: replace the boolean with a resolved platform, and replace the
silent `null` with a stated reason plus a real action.

## 2. Users and surfaces affected

| Cohort | Today | After |
|---|---|---|
| Sleeper league (the overwhelming majority) | Send button | **Byte-identical.** Nothing on this path changes |
| ESPN league | nothing renders | reason line + `Copy trade` |
| MFL / Fleaflicker league | a Send button that always 400s | reason line + `Copy trade` |
| Any platform, `trade.send_in_sleeper` **off** | nothing renders | **nothing renders** — unchanged |
| Any platform, league id missing from the session cache | Send button (fail-open, `#146`) | **Send button** — fail-open preserved deliberately |

Four mounts, three of them behind `showSend`:

| Surface | Mount | Reached from |
|---|---|---|
| Match card action row | `TradeCard.tsx:577` (`variant='match'`) | Matches → Mutual segment |
| Awaiting send row | `TradeCard.tsx:589` | Matches → Awaiting-them segment |
| Deck top-card action column | `TradesScreen.tsx:4713` (`compact`) | Trades tab |
| Calculator "In league" action row | `InLeagueCalculator.tsx:771` | Calculator |

Player names are already in scope at **every** mount (the `MatchesScreen` adapters resolve
`my_side_player_names` → `Player.name` with an id fallback; the calculator already builds the same
expression for its share text). **No new fetch, no new endpoint, no schema change.**

## 3. Requirements

### Functional

| # | Requirement | Verified by |
|---|---|---|
| **FR-1** | The send gate resolves a **platform** (`sleeper`/`espn`/`mfl`/`fleaflicker`) from the session's cached league list, not a single `isEspn` boolean | unit: `resolveSendPlatform` cases 1-4 |
| **FR-2** | The gate **fails open**: an unknown league id, a row with no `platform`, or an unrecognized platform value resolves to `sleeper` and renders the Send button, preserving `#146` | unit: cases 5-9; `capture/matches@espn.yaml`'s picker preamble |
| **FR-3** | The gate is **reactive** — it re-evaluates when the session's league list changes (a store selector, not an imperative read) | code review; league-switch smoke |
| **FR-4** | On a non-Sleeper league the component renders a **stated reason** naming the platform, visible without any interaction | flow step 9; the re-captured ESPN frames |
| **FR-5** | On a non-Sleeper league the component renders a **`Copy trade` action** that writes a plain-text proposal to the clipboard | flow steps 11-12; manual paste |
| **FR-6** | The copied text is never empty and never contains a blank side: absent player names fall back **per index** to player ids | unit: cases 21-23, 25 |
| **FR-7** | The copy action acknowledges: success haptic + the label flips to `Copied` for 2.5 s, then reverts | flow step 13 |
| **FR-8** | The copied text carries **no URL** | unit: case 27 |
| **FR-9** | The Sleeper path — link check, validate, propose, every error mapping, every alert string — is unchanged | Sleeper-profile captures pixel-identical; `smoke/08-matches.yaml` green unmodified |
| **FR-10** | `trade.send_in_sleeper` off ⇒ the component renders `null` on **every** platform | manual flag-off check |
| **FR-11** | The unused mobile `setMatchDisposition` wrapper is deleted; the route, `record_match_disposition`, the live `web/js/app.js:4342` caller, and the read-only `my_disposition`/`their_disposition` fields are untouched | repo-wide grep; pytest untouched-green |
| **FR-12** | `SendInSleeperButton` declares `surface?: SendSurface` (optional in this commit) and the three mounts this agent owns pass it | `tsc --noEmit`; HLD §3 commit 13 tightens it |

### Non-functional

| # | Requirement |
|---|---|
| **NFR-1** | **No new dependency.** Clipboard access uses React Native core's `Clipboard` behind a one-function seam. `mobile/node_modules` is a symlink and `npm install` is unavailable to this build; a native module would also force `expo prebuild` + a fresh EAS build |
| **NFR-2** | **No new feature flag** (S-24). The change rides `trade.send_in_sleeper`, whose OFF position is exactly today's ESPN behaviour on every platform |
| **NFR-3** | **No backend, web, or extension file changes** except one fixture *description* string. `python3 -m pytest backend/tests/ -q` untouched-green |
| **NFR-4** | **No analytics events fired** by this change (§7) |
| **NFR-5** | All platform-specific behaviour lives in pure exports with no React/RN imports, so the platforms with no simulator profile are still pinned by test (S-25) |
| **NFR-6** | The reason line costs ≤ 2 lines of `bodySm` on every mount including the compact deck column; the `#276` vertical-cost check is **verified on sim**, not assumed (S-27) |

## 4. Copy spec

### The reason line — one per platform, platform named

| Platform | String |
|---|---|
| `espn` | `Sending is Sleeper-only for now — copy this trade to propose it in ESPN.` |
| `mfl` | `Sending is Sleeper-only for now — copy this trade to propose it in MyFantasyLeague.` |
| `fleaflicker` | `Sending is Sleeper-only for now — copy this trade to propose it in Fleaflicker.` |

Rules: the platform is **named** (never "this league type") — the `#179` honesty rule inherited from
`NO_ADD_REASON`. `MyFantasyLeague` is spelled out because that is what the user saw on the link
screen. `for now` states a limit, not a promise of a date. The sentence explains **and** points at
the action in the same breath, so the screenshot alone satisfies "a stated reason".

### The action label

`Copy trade` → (on tap) `Copied` for 2.5 s → back to `Copy trade`. Ghost button variant — the app's
existing "this exists but can't fire the primary path here" treatment (`FreeAgentsScreen`'s dimmed
`Add`). No emoji, no checkmark glyph (ADR-004).

### The clipboard payload

```
Trade proposal — {leagueName}
To: @{opponentUsername}
I send: {give, comma-separated}
I get: {receive, comma-separated}
(Built with Fantasy Trade Finder)
```

Example:

```
Trade proposal — QA ESPN League
To: @tdickens
I send: Justin Jefferson, 2027 1st
I get: Ja'Marr Chase, Jaxon Smith-Njigba
(Built with Fantasy Trade Finder)
```

- `I send` / `I get` are the **caller's** perspective, matching every existing share string in the
  app and the match card's own give/receive labelling.
- Any line whose data is absent is **dropped**, never blanked: no `To: @`, no `Trade proposal — `,
  no trailing blank line, no double newline. Lines 1 and 5 always render, so a paste is never empty.
- Player names fall back per index to player ids.
- **No URL.** `growth.share_landing` owns share attribution (it is the flag that appends
  `Build your own: …?ref=` to the calculator's share and fires `calc_trade_shared`). This payload is
  a paste-into-league-chat message, not a share; adding a link here would silently widen the
  attribution surface without a flag or an event.

### What the user is *not* told

No "we're working on ESPN sending", no ETA, no upsell. The sentence states today's limit and hands
over the action.

## 5. Acceptance criteria

### A-1 — the audit's criterion, verbatim

> **A matched ESPN user has a stated reason and at least one useful action.**

Proved by `mobile/.maestro/flows/p0-6-espn-copy-trade.yaml` on the `espn` profile, in one session,
through the league picker (the fail-open gate makes the picker entry load-bearing — a
launch-argument jump would test the Sleeper branch under an ESPN filename):

- *stated reason* — `assertVisible id: send-in-sleeper.unavailable` **and**
  `assertVisible text: ".*Sending is Sleeper-only.*"`, both before any tap.
- *useful action* — `tapOn id: send-in-sleeper.copy` → `assertVisible text: ".*Copied.*"`.
- plus `takeScreenshot: p0-6-espn-copy-trade`, eyeballed during the tier-1 run.

Reinforced by `capture/matches@espn.yaml` gaining `assertVisible: id: send-in-sleeper.copy` on both
shutters (S-28): its existing `assertNotVisible ".*Send in Sleeper.*"` passes **before and after** the
fix, so without the positive assertion the regression detector can never go red.

### A-2 — MFL and Fleaflicker users no longer see a live send button that always 400s

No simulator profile exists for either platform (waiver W2, signed off in the scope block), so this
is proved by the pure-module unit tests, which is where **all** platform-specific behaviour lives
after the fix:

- `resolveSendPlatform('L1', [{league_id:'L1', platform:'mfl'}]) === 'mfl'` (and the same for
  `fleaflicker`) ⇒ `canSend === false` ⇒ the Send button cannot render.
- `NO_SEND_REASON` has exactly three keys and each names its own platform in prose.
- `SEND_SURFACES` is exactly `['deck','match','awaiting','calculator']`.

**This is a behaviour removal, and it is named rather than discovered** (HLD §8 R9): an MFL user who
had learned to tap Send and read an error now sees a copy affordance instead. No capability is lost —
the removed control had a 0 % success rate by construction. `CHANGELOG.md` must say so explicitly.

### A-3 — Sleeper leagues are byte-identical

The primary regression assertion, and the one worth failing the build over:

- `flows/smoke/08-matches.yaml` (profile `standard`, a Sleeper league) passes **unmodified**;
  `05-trades-render.yaml`, `06-trades-deck.yaml`, `07-calculator` likewise.
- Sleeper-profile captures are pixel-identical; `mobile/scripts/screen-freshness.sh` flags
  **ESPN-profile screens only**. Any Sleeper frame going stale is a regression.
- Code-level: the flag check narrows from `if (!enabled || isEspn)` to `if (!enabled)` and the
  Sleeper `label` / `Button` return is untouched; the new branch returns above it.

### A-4 — the clipboard write actually lands

`copyText` returns `void` (RN core's `setString` is synchronous with no success signal), so the
`Copied` flip acknowledges the **tap**, not the **write**. Maestro cannot read the iOS pasteboard.
Therefore: **one manual paste into Notes on the simulator, after the flow's copy tap, with the pasted
string recorded verbatim in `living-memory/TEST_LEDGER.md`.** This is the only end-to-end proof in
the batch and it is not optional (HLD §10.6 item 9 flags it for the operator's attention explicitly).

### A-5 — the kill switch still kills

With `trade.send_in_sleeper=false`, nothing renders on any platform — verified manually, not assumed.
This is both FR-10 and the rollback lever (§9).

### A-6 — the compact mount fits

On the ESPN profile, the deck's top card plus the compact reason line fits an 852 pt viewport
(`#276`). If it does not, the fallback is `!compact`-only reason text and that is a **recorded
operator deviation**, not an agent decision (S-27).

### Static gates (all must pass before the sim run)

`node mobile/tests/check-trade-text.js` green · `cd mobile && npx tsc --noEmit` clean ·
`bash mobile/scripts/testid-lint.sh` exit 0 · `python3 -m pytest backend/tests/ -q` green ·
`grep -rn "setMatchDisposition" mobile/ web/ extension/ backend/ --exclude-dir=node_modules` empty.

### Ship gate

**Tier 1** (mobile screen/state change with visual deltas). One tier-1 run covers the whole P0
batch (HLD §10.5); evidence to `TEST_LEDGER.md` + `qa/sim-runs/last-sim-run.json`, owned by `W3-QA`.

## 6. Non-goals

Each of these was evaluated and deliberately excluded. Every one leaves a record.

### 6.1 Accept / decline match UX — **deferred, with the evaluation on the record**

The audit's framing invited "surface it or delete it" for `setMatchDisposition`. Verification changed
the question: the **route is not dead**. `POST /api/trades/matches/<int:match_id>/disposition`
(`backend/server.py:12742+`) has a live caller in `web/js/app.js:4342` and its persistence layer
(`record_match_disposition`, `backend/database.py:6783+`) applies K-factored ELO signal and
deck-suppression side effects. Deleting it would break production. Only the **~13-line unused mobile
client wrapper** is dead.

Building the feature instead is out of scope for a *Bug, effort S* item: it needs two-sided state
design (`my_disposition` × `their_disposition` × dismissed), settled-state copy on the tile, an
honest answer to "what does Accept mean when FTF cannot execute the trade" (on ESPN it means
*nothing* — the same hollow action this finding exists to delete), irreversible ELO consequences the
user must be warned about, and its own analytics events. That is a PRD, a Maestro flow family and a
tier-1 run of its own — and it lands in the exact files P0-7 is instrumenting.

**Decision (S-29):** delete the mobile wrapper, keep the route and the read-only fields, add one
comment at the normalizer recording that mobile reads dispositions and `web/js/app.js` writes them.
**Record:** `living-memory/NEXT.md` gains "Match accept/decline UX (P0-6 option B, with the
evaluation)" — HLD §7 already assigns the row to `W3-DOCS`. Reversibility: `git revert` restores 13
lines and the server contract they wrapped is untouched and documented in `docs/api-reference.md`.

### 6.2 The backend `is_linked_platform_league` guard — **NEXT.md, not this build**

`POST /api/sleeper/propose` validates only `league_id.isdigit()` (`backend/server.py:12336`), and
MFL/Fleaflicker league ids are numeric — so a hand-crafted request with an MFL league id still
reaches Sleeper's roster space, even though `is_linked_platform_league` is imported in the same file
(`:147`) and used at five other sites. This is a real server-side hole and it **survives this build**
(HLD §10.6 item 7).

Excluded because a backend + API-contract change is `CLAUDE.md`'s bright line, and P0-6's client fix
is the whole of the acceptance criterion — after it, no FTF client can originate such a request.
**Record:** `NEXT.md` item ("`is_linked_platform_league` guard on `/api/sleeper/propose`" — one line
beside the existing `isdigit()` check, returning `400 bad_request`) plus `GOTCHAS.md` **G-030**
("MFL/Fleaflicker league ids are numeric, so `league_id.isdigit()` does not exclude them from the
Sleeper propose path"). Both rows are already in HLD §7 and owned by `W3-DOCS`. Operator waiver W3.

### 6.3 Everything else excluded

| Non-goal | Why |
|---|---|
| A new feature flag (`trade.copy_fallback`) | S-24 / waiver W1. The change lives inside `trade.send_in_sleeper`'s blast radius; a new flag is itself a feature-flag-surface change that the bright line excludes from "quick fix" |
| An MFL / Fleaflicker harness profile | S-25 / waiver W2. Fixture seed + league snapshot is real scope inside a *Bug, effort S* wave. Filed to `NEXT.md`; compensated by unit tests over all four platform values |
| Refactoring the three existing ad-hoc trade-text formatters (`TradeCalculatorScreen.shareTrade`, `TradesScreen.shareLikedTrade`, `InLeagueCalculator`'s `fallbackText`) | Surgical-changes rule. They disagree today and will keep disagreeing; unifying them is a separate cleanup with its own visual-diff surface |
| Migrating to `expo-clipboard` | Native module ⇒ `npm install` + `expo prebuild` + a fresh EAS build, none available here (`mobile/node_modules` is a symlink). The whole surface is one function, so the migration is a one-file edit at the next scheduled native rebuild (HLD §8 R14) |
| Deep-linking into the ESPN/MFL app to open its trade screen | No such addressable URL exists for a pre-filled proposal; a link to the app's home is not "a useful action" |
| Sharing the trade image from this surface | `ShareTradeImage` exists and is a *different* affordance (a PNG for a share sheet). Adding it here doubles the action row for no acceptance gain |
| Firing analytics from P0-6 | §7 |
| Touching `TradesScreen.tsx` | HLD §4/§8 R6: `W2-TS` owns that file exclusively. P0-6 **specifies** its one-liner; commit 11 applies it |
| Changing the fail-open contract to fail closed | It would hide Send on real Sleeper leagues whenever the cache is cold — strictly worse (HLD §8 R15) |

## 7. The P0-7 handoff contract

P0-6 fires **zero** `track()` calls. The taxonomy is default-deny (`ALLOWED_CLIENT_EVENTS`, enforced
in `analytics_ingest.py`): an unregistered name is counted-and-dropped behind a 200 OK, and
registration is commit 1's exclusive territory (S-36). Emitting from P0-6 would either require a
taxonomy edit — an analytics-surface change, the bright line, inside a *Bug, effort S* item — or
produce a plausible-looking dashboard with no rows, which is the exact failure this batch's first
commit exists to prevent.

### 7.1 The two events, specced for P0-7 to register and emit

| Event | Fires when | Properties |
|---|---|---|
| `send_unavailable_shown` | the non-Sleeper branch of `SendInSleeperButton` is shown | `platform` (`espn`\|`mfl`\|`fleaflicker`), `league_id`, `surface` (`match`\|`deck`\|`awaiting`\|`calculator`) |
| `trade_copied` | `Copy trade` tapped, after a successful `copyText` | `platform`, `league_id`, `surface`, `give_count`, `receive_count` |

`platform` is an **explicit property on both** — it is the dimension the entire finding is about, and
the NULL-`platform` incident on the record in `CLAUDE.md` is why it is stated rather than inferred
from a league lookup at query time.

**Neither event is in commit 1's registered set** (HLD §4 Wave 0). This table is the handoff record,
not a licence to build them in this batch.

**The trap P0-7 must not walk into** (HLD §1.4, S-23): P0-6 changes what *"the send button was shown"*
means. After the fix a non-Sleeper mount renders an affordance that is **not** a send button. An
impression event firing unconditionally at mount would conflate copy-affordance impressions with send
impressions and corrupt the send-funnel denominator. If `send_unavailable_shown` is built later it
needs a `firedRef`-guarded effect keyed on `(leagueId, platform, surface)` — one row per mount per
session, never one per render — **and** registration in `NON_INTENT_EVENTS`, because `INTENT` is a
deny-list and a high-frequency impression event landing as INTENT step-changes DAU/WAU on ship day
(S-32).

### 7.2 What P0-7 may touch in `SendInSleeperButton.tsx`, and what is frozen

Sequential handoff, not a parallel line-range split (HLD §10.5 rejects the parallel version). P0-6
lands the whole file in **commit 8**; P0-7 inserts in **commit 10**. Regions are named by grep anchor
because the file grows ~60 lines in commit 8 and every line number in `plan-p0-6.md` §9 is stale.

**Open to P0-7 in commit 10 — insertions only, no signature or render change:**

| Anchor | Insertion |
|---|---|
| `const onPress = useCallback(async () => {` … | `sleeper_send_attempted`, after the `state !== 'idle'` guard and `haptics.pickup()` |
| `} catch (err) {` inside `const doPropose = useCallback(async () => {` | `sleeper_send_failed` with the `error_code` derived from the already-destructured `code`/`detail` locals |

**Frozen — P0-7 must not modify:**

- `interface Props`, **except** deleting the `?` on `surface` in **commit 13** (that commit's entire
  diff is one character).
- The gate — `resolveSendPlatform(...)` / `const canSend = platform === 'sleeper'`. `canSend` must
  stay a `const` off a literal comparison; anything else breaks the type narrowing that makes
  `NO_SEND_REASON[platform]` compile without a cast.
- `if (!enabled) return null;` and the whole `if (!canSend) { … }` render block — **no impression
  event at mount** (§7.1).
- `onCopy`, `copied`, `copiedTimer` and its cleanup effect; `styles`; the file header comment.
- `mobile/src/utils/tradeText.ts` and `mobile/src/utils/clipboard.ts` — pinned by a unit test P0-7
  does not own.

### 7.3 The `surface` prop's two-step life

| | Commit 8 (`W1-P06`) | Commit 11 (`W2-TS`) | Commit 13 (`W2-P07`) |
|---|---|---|---|
| Declaration | `surface?: SendSurface` | unchanged | `surface: SendSurface` |
| Mounts plumbed | `TradeCard` ×2, `InLeagueCalculator` | + `TradesScreen` | all four |
| Effect | commit 8 is green with `TradesScreen` unplumbed | — | **a missed mount becomes a compile error** |

P0-6 reads `surface` at zero sites. That is intentional: a P0-6 read would make commit 13's `?`
deletion a behavioural change rather than a type change. Reviewers flagging "unused prop" should be
pointed here.

## 8. Docs rows

**No build agent edits a `docs/` or `living-memory/` file** — HLD §4 gives every row to `W3-DOCS`,
which removes eight would-be contentions. P0-6 *supplies* the content below; the ids are HLD §7's,
which are authoritative over the stale "next ID" columns in root `CLAUDE.md` (HLD §10.4).

| Doc | Row | Status |
|---|---|---|
| `mobile/src/components/CLAUDE.md` | `SendInSleeperButton` row currently reads "self-gates to Sleeper leagues" (`:29`) — misleading after the change. Replace with: platform-generic gate (Sleeper sends; ESPN/MFL/Fleaflicker get a stated reason + `Copy trade`), fail-open on an uncached league id. Register `send-in-sleeper.unavailable` and `send-in-sleeper.copy` in the `testID` registry | **updated** |
| `mobile/src/api/CLAUDE.md` | **Verified n/a.** Its `trades.ts` row is "Trade card fetch + decisions" (`:13`) and the file never names `setMatchDisposition`. Record as verified rather than leaving "check at build" open | **n/a (verified)** |
| `living-memory/DECISIONS.md` | **D-030** — (a) React Native core `Clipboard` over `expo-clipboard`, with the native-rebuild constraint and the one-function `utils/clipboard.ts` migration seam; (b) delete the mobile `setMatchDisposition` wrapper while keeping the route (live web caller + ELO consequences) and deferring accept/decline UX | **updated** |
| `living-memory/GOTCHAS.md` | **G-030** — MFL/Fleaflicker league ids are numeric, so `league_id.isdigit()` at `backend/server.py:12336` does not exclude them from the Sleeper propose path; same bug class as `#200` / `#220` | **updated** |
| `living-memory/NEXT.md` | Three items: match accept/decline UX (§6.1, with the evaluation) · MFL/Fleaflicker harness profile (waiver W2) · `is_linked_platform_league` guard on `/api/sleeper/propose` (§6.2, waiver W3) | **updated** |
| `living-memory/CHANGELOG.md` | Dated H2 at ship. **Must name the MFL/Fleaflicker behaviour change explicitly** — this is not a purely additive change; a currently-tappable control is removed | **updated at ship** |
| `living-memory/TEST_LEDGER.md` | Tier-1 sim run result **plus the manual clipboard paste, verbatim** (A-4) and the `#276` compact-mount verdict (A-6) | **updated at ship**, `W3-QA` |
| `screens/CLAUDE.md` | Re-captured `matches__populated--espn-mutual` and `matches__populated--espn-awaiting` frames; the pre-fix PNGs stay in git history as the audit's before-evidence (a mockup's "current" pane is not redrawn) | **updated** |
| `living-memory/DEPENDENCIES.md` | **n/a — no dependency added, bumped or removed.** That is the point of NFR-1 | **n/a** |
| `docs/api-reference.md` | **n/a** — no route added, renamed, removed or contract-changed. `/api/sleeper/propose`, `/api/trades/matches/<id>/disposition` and `/dismiss` are untouched; the change is client-only | **n/a** |
| `docs/data-dictionary.md` | **n/a** — no table, column or index | **n/a** |
| `docs/config-reference.md` | **n/a** — no flag, env var or `model_config` key added | **n/a** |
| `docs/cross-client-invariants.md` | **n/a** — no shared constant, enum or colour. `NO_SEND_REASON` is mobile-only copy; web has no send-in-Sleeper surface | **n/a** |
| `docs/design/components.md` | **n/a** — reuses the specced `ghost` Button variant, `type.bodySm` and `chalk.dim`; no new component spec, no new token | **n/a** |
| `docs/glossary.md` | **n/a** — no new domain term ("platform-linked league" is already in use) | **n/a** |
| `docs/architecture.md` / `living-memory/HLD.md` | **n/a** — no module wiring or data-flow change; two new leaf utilities under `mobile/src/utils/` | **n/a** |
| `living-memory/LLD.md` | **n/a** — no schema/route/invariant *convention* shift. The platform-generic gate is a component-local rule | **n/a** |
| `docs/runbook.md` | **n/a** for P0-6 specifically — no operational procedure changes | **n/a** |

## 9. Rollback

**Three levers, in increasing cost. Nothing here requires a code deploy.**

**1. The kill switch — `trade.send_in_sleeper` → false (no deploy).** The flag is checked *above* the
platform branch, so off means the component renders `null` on **every** platform — Sleeper included.
That is exactly today's ESPN behaviour applied everywhere: no send button, no copy affordance, no
crash surface. This is why the fix needs no flag of its own (S-24, waiver W1) — the knob is already
shipped and already the rollback lever for the whole component. Cost: Sleeper users lose the Send
button too, so this is a blast-radius trade, not a free undo. Verified by A-5, not assumed.

**2. `git revert` of commit 8.** The commit is self-contained: two new files, one component, three
mount files, one API deletion, one unit test + its npm script, one flow, one capture edit, one
fixture description. It touches **no** backend logic, **no** schema, **no** flag registry, and **no**
web or extension file, so a revert cannot leave a half-migrated state. What comes back: the `isEspn`
boolean, the silent `null` on ESPN, the always-failing Send button on MFL/Fleaflicker, and the
13-line `setMatchDisposition` wrapper.

**Two ordering constraints on a revert**, because commit 8 is a wave-1 commit others build on:

- Commit 13 (`surface` required) **must be reverted first or together** — it depends on the prop
  declaration commit 8 introduces.
- Commits 10 and 11 insert into files commit 8 shaped (`SendInSleeperButton`'s handlers,
  `TradesScreen`'s mount). A revert of 8 alone after 10/11 have landed will conflict; revert
  10-and-13's touches to this component in the same operation, or revert the range.

**3. Partial rollback — keep the gate, drop the affordance.** If the copy *text* turns out wrong in
the field but the gate is right, deleting the `Copy trade` `Button` from the `!canSend` branch leaves
the reason line standing. That satisfies half the acceptance criterion ("a stated reason") and is
strictly better than today on all three platforms. ~6 lines, no other file. Recorded as an option, not
a plan.

**What no lever restores:** the MFL/Fleaflicker Send button's *success rate*, because it was 0 % by
construction (the propose route queries Sleeper's roster space for a league that does not exist
there). Reverting restores a control, not a capability.

## 10. Open items for the operator

| # | Item | Default if unanswered |
|---|---|---|
| **W1** | No new feature flag — the change rides `trade.send_in_sleeper` (S-24) | **proceed with no new flag** |
| **W2** | MFL / Fleaflicker get unit coverage, not simulator coverage (S-25) | **proceed; file the profile in `NEXT.md`** |
| **W3** | `/api/sleeper/propose` keeps its missing platform guard this build (S-26) | **proceed client-only; file the guard in `NEXT.md`** |
| **D-1** | `surface` for `TradeCard`'s non-match mount is `'awaiting'`, not HLD §4's `'suggested'` — the only `showSend` non-match mount in the tree is the Awaiting segment, and `awaiting` is the value in the event contract P0-7 will register. Changing it later is a one-word edit but must happen **before** commit 10 | **proceed with `'awaiting'`** |
| **A-4** | The manual paste is the only end-to-end proof the clipboard write lands, and it is a human step in the tier-1 run | **required; record verbatim in `TEST_LEDGER.md`** |
| **A-6** | If the compact deck mount overflows an 852 pt viewport, the fallback is `!compact`-only reason text — an **operator** deviation, recorded in the scope block | **verify on sim before deciding** |
