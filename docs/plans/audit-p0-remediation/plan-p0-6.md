# P0-6 — Matched ESPN users have no action, and aren't told why

> **Plan only.** No code changed by this document. Worktree
> `/Users/teresadickens/Documents/Claude/Projects/ftf-p0-remediation`, branch
> `p0-remediation-2026-08-10`, worktree of `origin/main @ ab9368f`.
> Companion scope block: [`scope-p0-6.md`](scope-p0-6.md).

**Source finding:** `docs/business/product/2026-08-09-mobile-ux-audit/07-build-handoff-prompt.md` § P0-6,
`04-priority-backlog.md` § P0-6, `06-resolutions.md` § P0-6.

**Acceptance (verbatim from the handoff):** a matched ESPN user has a stated reason and at least one useful action.

---

## Contents

- [1. Verified current state](#1-verified-current-state)
- [2. Design](#2-design)
- [3. Exact change list](#3-exact-change-list)
- [4. Surface changes](#4-surface-changes)
- [5. Maestro delta](#5-maestro-delta)
- [6. Docs impact](#6-docs-impact)
- [7. Test plan](#7-test-plan)
- [8. Risks and open questions](#8-risks-and-open-questions)
- [9. Note for the HLD — collision with P0-7](#9-note-for-the-hld--collision-with-p0-7)

---

## 1. Verified current state

Every line reference below was re-read in this worktree at `ab9368f`. The audit's claims hold; three
things are **worse or wider** than graded, and are called out as such.

### 1.1 The gate itself

`mobile/src/components/SendInSleeperButton.tsx`

| Line | What is there |
|---|---|
| 59 | `const enabled = useFlag('trade.send_in_sleeper');` — master flag, `true` in `config/features.json:45` |
| 60-62 | The `#146` comment: reactive twin of `api/espn.isEspnLeague`, **fail-open** by design — "a league id missing from the cached list (demo league, stale cache) keeps the button" |
| 63-66 | `const leagues = useSession((s) => s.leagues); const isEspn = leagues.some((lg) => lg.league_id === leagueId && lg.platform === 'espn');` |
| 273 | `if (!enabled \|\| isEspn) return null;` — **the silent null.** No copy, no affordance, no log |

The component is *only* platform-aware at this one line. Every other branch (link check, validate,
propose, error mapping, lines 105-271) is Sleeper-specific and unreachable on a non-Sleeper league —
which is correct, and is why the fix is a new render branch rather than a change to the send path.

### 1.2 Every call site of the button (4 mounts, 3 files)

| File:line | Surface | Variant | Has player *names* in scope? |
|---|---|---|---|
| `mobile/src/screens/TradesScreen.tsx:4713` | Guided/free deck, top card action column | `compact` | Yes — `topCard.give_players[].name` / `receive_players[].name` |
| `mobile/src/components/TradeCard.tsx:577` | **Match card action row** (`variant === 'match'`, beside `Dismiss` at :570) | full | Yes — `data.give_players` / `data.receive_players` |
| `mobile/src/components/TradeCard.tsx:589` | Non-match TradeCard send row (`styles.sendRow`) — this is what the Matches tab's **"Awaiting them"** segment renders | full | Yes — same |
| `mobile/src/components/InLeagueCalculator.tsx:771` | Calculator "In league" mode action row | full | Yes — `playerById[id]?.name` (already used by the `ShareTradeImage` fallback text at :787-796) |

`TradeCard`'s two mounts are both reached from `MatchesScreen.tsx:616-623`, which passes `showSend`
unconditionally and builds its card data through `matchToTradeCardShape()` (`MatchesScreen.tsx`,
the `TradeMatch` → `TradeCard` adapter). That adapter already resolves `my_side_player_names` /
`their_side_player_names` into `Player.name`, falling back to the raw id — so **names for the copy
text are already in scope at every mount**. No new fetch, no new endpoint.

### 1.3 ESPN leagues really do produce matches (the audit's re-check confirmed)

`backend/server.py:10012-10014`:

```python
if decision == "like" and card.target_user_id and card.league_id != "league_demo":
    is_mirror = check_for_match(...)
```

The only exclusion is the demo league. `trade_matches` is league-scoped with **no platform column**,
and `load_matches` resolves both partner names from `league_members` — so an ESPN match renders
through the ordinary `MatchesScreen` path. This is independently corroborated by the harness fixture
`backend/tests/fixtures/profiles/espn.json` (see §5), which seeds a real mutual match in a
`platform='espn'` league specifically to photograph this bug.

### 1.4 The MFL answer — **yes, and it is worse than the ESPN case**

`isEspn` tests `platform === 'espn'` only. `platform` is typed
`'sleeper' | 'espn' | 'mfl' | 'fleaflicker'` (`mobile/src/shared/types.ts:475`), and
`LeaguePickerScreen.tsx:183-195` stamps `platform: 'mfl'` / `'fleaflicker'` into the same cached
league list the button reads. So on an MFL or Fleaflicker league:

1. The button **renders and is enabled** — the user is invited to send.
2. `POST /api/sleeper/propose` (`backend/server.py:12295`) validates only
   `if not league_id.isdigit()` (`:12336`) — **no `is_linked_platform_league` guard**, even though
   that helper is imported at `:147` and used at `:681`, `:14035`, `:14066`, `:19871`. MFL and
   Fleaflicker league ids are numeric, so the request passes validation.
3. `_fetch_league_rosters(league_id)` then queries **Sleeper's** roster space for a league that does
   not exist there, `_roster_id_for_owner` returns `None`, and the route answers
   `400 roster_not_found` / `opponent_roster_not_found`.
4. The client maps those to *"Couldn't send — Couldn't match one of the teams to a roster in this
   Sleeper league."* (`SendInSleeperButton.tsx:180-184`) — a confusing dead end after the user has
   already gone through the link/verify webview.

So the same finding covers three platforms with two different failure shapes: **ESPN = silent
absence, MFL/Fleaflicker = a live button that always fails.** The explanatory state must therefore be
platform-generic, and it closes a bug the audit did not see. This also means the fix is not purely
additive — it *removes* a currently-tappable (always-failing) control on MFL/Fleaflicker.

### 1.5 The FreeAgents idiom (the thing to mirror)

`mobile/src/screens/FreeAgentsScreen.tsx`

| Line | Piece |
|---|---|
| 55-63 | `#179` rationale comment — platform-linked leagues are read-only imports, "no write path, so the Add affordance renders dimmed and explains why on tap" |
| 64-73 | `type AddPlatform = 'sleeper' \| 'espn' \| 'mfl' \| 'fleaflicker' \| 'local'` + `resolveAddPlatform()` (uses `isEspnLeague` / `isMflLeague` / `isFleaflickerLeague`) |
| 75-103 | `NO_ADD_REASON: Record<Exclude<AddPlatform,'sleeper'>, {title, body}>` — one honest, platform-named reason per platform |
| 108-111 | `explainNoAdd()` → `Alert.alert(reason.title, reason.body)` |
| 537-544 | The affordance itself: `<Button label="Add" variant={canDeepLink ? 'secondary' : 'ghost'} compact />` — **ghost is the dim** |

Three transferable parts: the `AddPlatform` union + resolver, the per-platform reason record, and
`variant="ghost"` as the visual "this exists but can't fire here". §2 reuses all three.

### 1.6 Clipboard and trade-text formatting — what exists

- **No clipboard dependency is installed.** `mobile/package.json` has neither `expo-clipboard` nor
  `@react-native-clipboard/clipboard`, and neither is present in `mobile/node_modules/`. Adding
  either is a **native module** → `expo prebuild` + a fresh EAS/simulator build. `mobile/node_modules`
  is a symlink in this worktree and `npm install` is forbidden for this build.
- **React Native core still ships Clipboard.** `react-native@0.81.5` exports it behind a `warnOnce`
  deprecation getter (`node_modules/react-native/index.js:180-188`); the implementation
  (`Libraries/Components/Clipboard/Clipboard.js`) and the iOS native module
  (`React/CoreModules/RCTClipboard.mm`) are both present, and `Clipboard.d.ts` exports
  `ClipboardStatic` so `import { Clipboard } from 'react-native'` typechecks. **Zero new deps, no
  rebuild.**
- **No plain-text trade formatter is shared.** Three ad-hoc ones exist and disagree:
  `TradeCalculatorScreen.tsx:497-540` (`shareTrade`), `TradesScreen.tsx:2734-2772`
  (`shareLikedTrade`), and `InLeagueCalculator.tsx:787-796` (`ShareTradeImage.fallbackText`).
  `ShareTradeImage.tsx` renders a PNG and takes a caller-built `fallbackText` — it formats nothing
  reusable. So the copy text needs a small new helper; §2.3 keeps it pure and testable rather than
  refactoring the three existing shares (out of scope, surgical-changes rule).

### 1.7 `setMatchDisposition` — both ends

| End | Location | State |
|---|---|---|
| Mobile client wrapper | `mobile/src/api/trades.ts:504-516` | **Zero call sites.** Repo-wide grep across `*.ts/tsx/js/html` (node_modules excluded) returns only the definition |
| Mobile type surface | `mobile/src/shared/types.ts:263-264` (`my_disposition`, `their_disposition`) + the normalizer at `api/trades.ts:481-484` | Populated on every read, **rendered nowhere** |
| Route | `POST /api/trades/matches/<int:match_id>/disposition` — `backend/server.py:12742-13060` | Live. Verified session, ELO signal, deck-suppression side effects, `record_event`, cross-league slice refresh |
| Persistence | `record_match_disposition()` — `backend/database.py:6783+`, K-factors at `:6738` | Live |
| **Web client** | **`web/js/app.js:4342`** — `apiFetch('/api/trades/matches/${matchId}/disposition', …)` | **Live caller** |

**This materially changes the "surface it or delete it" question** and is the single most important
verification in this plan: the *route* is not dead — the web app calls it and it carries real ELO
consequences. The only dead code is the ~13-line mobile wrapper. See §2.5.

---

## 2. Design

### 2.1 Principle

Replace one boolean (`isEspn`) with a resolved platform, and replace one silent `null` with a
**stated reason plus a real action**. Nothing about the Sleeper path changes — a Sleeper league
renders byte-for-byte what it renders today.

### 2.2 The explanatory state

**Platform resolution — reactive, platform-generic, fail-open preserved.**

```ts
type SendPlatform = 'sleeper' | 'espn' | 'mfl' | 'fleaflicker';

const leagues = useSession((s) => s.leagues);
const platform: SendPlatform =
  (leagues.find((lg) => lg.league_id === leagueId)?.platform as SendPlatform) ?? 'sleeper';
const canSend = platform === 'sleeper';
```

Deliberate properties:

- **Reactive**, not `useSession.getState()` — keeps the `#146` convention (the FreeAgents helpers use
  the imperative `getState()` twin because they run inside callbacks, not render).
- **Fail-open, unchanged.** A league id absent from the cache (demo league, stale cache, a launch
  that skipped the picker) resolves to `'sleeper'` and renders exactly today's button. The `#146`
  comment's promise is preserved verbatim; the fail-open *precondition* documented in
  `capture/matches@espn.yaml` still holds and is still enforced by that flow.
- Widening `'espn'` → any non-`'sleeper'` value is what closes the MFL/Fleaflicker hole in §1.4.

**Render branches** (replacing line 273):

```
!enabled            → null            (unchanged: the flag is the kill switch for the whole component)
canSend             → the Send button (unchanged, byte for byte)
!canSend            → the new unavailable state
```

**The unavailable state** — a small block that states the reason inline and offers the action:

```
┌──────────────────────────────────────────────┐
│ Sending is Sleeper-only for now — copy this   │  ← type.bodySm, chalk.dim, numberOfLines={2}
│ trade to propose it in ESPN.                  │
│ ┌──────────────┐                              │
│ │ Copy trade   │  ← Button variant="ghost", compact={compact}
│ └──────────────┘                              │
└──────────────────────────────────────────────┘
```

testID `send-in-sleeper.unavailable` on the wrapper `View`, `send-in-sleeper.copy` on the button.

Reason copy comes from a record structurally identical to `NO_ADD_REASON`:

```ts
const NO_SEND_REASON: Record<Exclude<SendPlatform, 'sleeper'>, string> = {
  espn:        'Sending is Sleeper-only for now — copy this trade to propose it in ESPN.',
  mfl:         'Sending is Sleeper-only for now — copy this trade to propose it in MyFantasyLeague.',
  fleaflicker: 'Sending is Sleeper-only for now — copy this trade to propose it in Fleaflicker.',
};
```

**Documented deviation from the FreeAgents idiom, and why.** FreeAgents puts its reason *behind* the
tap (`explainNoAdd` → `Alert.alert`) because there is nothing else to offer — the alert **is** the
payload. Here there is a real action, so gating it behind a modal the user must read and dismiss
makes the action worse, and would leave the reason invisible until tapped — which fails half the
acceptance criterion ("a **stated** reason") on the screenshot alone. So this mirrors the idiom's
substance (ghost affordance for "no write path here", a per-platform honest reason record named after
the platform, no invented second vocabulary) while stating the reason inline. Two supporting
reasons: (a) the match card is already a mixed content+action surface, unlike a dense FA list row
that has no room for a line of prose; (b) native `Alert` buttons carry no `testID`, so an alert-gated
action can only be driven by a text-selector tap, which `lld.md` §4.4 rule 1 bans (see §5.3).

**Tap behaviour.** `Copy trade` copies immediately — no confirm. Then: `haptics.success()`, and the
button label flips to `Copied` for 2.5 s before reverting. No alert, no toast (the component has no
toast host and mounts inside three different screens; a label flip is local, honest, and assertable).

**`compact` handling.** The reason line renders on all four mounts, including the deck's compact
column. It costs ~16-32 pt on non-Sleeper leagues only, which today get *zero* pt and zero
information. `#276`'s vertical-cost audit is a QA check here, not a blocker — see §7.4.

### 2.3 Clipboard text format

New pure helper, `mobile/src/utils/tradeText.ts`:

```ts
export function formatTradeForClipboard(input: {
  giveNames: string[];
  receiveNames: string[];
  opponentUsername?: string;
  leagueName?: string;
}): string
```

Output (blank/absent lines dropped, same `lines.filter(Boolean).join('\n')` idiom as
`TradeCalculatorScreen.shareTrade`):

```
Trade proposal — Lakeview Dynasty
To: @tdickens
I send: Justin Jefferson, 2027 1st
I get: Ja'Marr Chase, Jaxon Smith-Njigba
(Built with Fantasy Trade Finder)
```

Rules:
- `I send` / `I get` are the caller's perspective, matching every existing share string in the app
  and the match card's own give/receive labelling.
- Empty name arrays fall back to the player ids the caller passed — the action **never** produces an
  empty clipboard.
- No URL. `growth.share_landing` owns share-attribution links and adds a `?ref=` query; this is a
  paste-into-ESPN-chat payload, not a share. Keeping them separate avoids quietly changing the
  attribution surface (which would be a P0-7-adjacent analytics change).
- Pure, zero React/RN imports → unit-testable by the existing `mobile/tests/check-*.js` transpile
  idiom (`check-session-rerank.js` is the template).

Clipboard write goes through a one-function seam, `mobile/src/utils/clipboard.ts`:

```ts
import { Clipboard } from 'react-native';
export function copyText(s: string): void { Clipboard.setString(s); }
```

The seam exists so the eventual migration to `expo-clipboard` (when a native rebuild is next
scheduled — see §8 R1) is a one-file change, not a hunt through components.

### 2.4 New props on `SendInSleeperButton` (all optional → every existing mount still compiles)

| Prop | Type | Source at each mount |
|---|---|---|
| `givePlayerNames` | `string[]?` | `data.give_players.map(p => p.name)` / `giveIds.map(id => playerById[id]?.name ?? id)` |
| `receivePlayerNames` | `string[]?` | mirror of the above |
| `opponentUsername` | `string?` | `data.opponent_username` / `opponent?.username` |
| `leagueName` | `string?` | `TradeMatch.league_name` (Matches only; undefined elsewhere) |

When `givePlayerNames` is absent the helper falls back to `givePlayerIds` — so a mount that forgets a
prop degrades to ids, never to a crash or an empty copy.

### 2.5 `setMatchDisposition` — **recommendation: delete the mobile wrapper, keep the route, defer the feature**

Three options were evaluated.

| Option | Verdict |
|---|---|
| **A. Delete the route + `record_match_disposition`** | **Rejected — it would break production.** `web/js/app.js:4342` is a live caller, and `record_match_disposition` (`database.py:6783`) applies K-factored ELO signal and deck-suppression side effects. The handoff's "delete it" cannot have meant this; the audit read the *mobile* surface |
| **B. Surface accept/decline as a primary match action on mobile** | **Rejected for this build.** It is a feature, not a bug fix: it needs two-sided state design (`my_disposition` × `their_disposition` × dismissed), settled-state copy on the tile, an honest answer to "what does Accept mean when FTF cannot execute the trade" (on ESPN it means *nothing* — the same hollow action P0-6 exists to delete), irreversible ELO consequences the user must be told about, and its own analytics events. That is a PRD, a Maestro flow family, and a tier-1 sim run — inside a build whose seven items are all typed *Bug, effort S*. It also lands in the exact files P0-7 is instrumenting |
| **C. Delete only the unused mobile client wrapper** | **Recommended** |

**Recommendation (C), concretely:** delete `setMatchDisposition` from `mobile/src/api/trades.ts`
(lines 504-516, and the two comment lines above it). Keep the route, `record_match_disposition`, the
web caller, and the `my_disposition` / `their_disposition` fields in `TradeMatch` +
`normalizeTradeMatch` — those are *reads* of server-authoritative state and are the raw material for
option B whenever it is scheduled. Add one comment line at the normalizer recording that mobile reads
dispositions but does not write them, and that the writer is `web/js/app.js`.

Why this is the honest call rather than a dodge:
1. It removes 100 % of the dead code that actually exists on the surface the audit examined.
2. It removes the *false signal* — an exported, typed, unused API wrapper reads as "mobile has an
   accept path" to the next person, which is precisely how this finding was framed.
3. It is trivially reversible: `git revert` restores 13 lines, and the server contract it wrapped is
   untouched and documented in `docs/api-reference.md`.
4. Option B is not lost — it is recorded as a `living-memory/NEXT.md` item with the evaluation above,
   so the deferral is a decision on the record rather than an omission.

**This is decided, not deferred.** If the operator prefers B, it is a separate PRD and this plan's
§3 item 6 becomes a no-op — say so before build starts, not during.

---

## 3. Exact change list

Ordered. Items 1-3 are the fix; 4-5 are the call sites; 6 is the disposition decision; 7-9 are gates.

**1. `mobile/src/utils/tradeText.ts`** *(new, ~35 lines, pure)*
`formatTradeForClipboard()` per §2.3. No React, no RN imports.

**2. `mobile/src/utils/clipboard.ts`** *(new, ~8 lines)*
`copyText()` seam per §2.3, with a comment naming the `expo-clipboard` migration and why it was not
taken now (native module, no rebuild available in this build).

**3. `mobile/src/components/SendInSleeperButton.tsx`** *(the fix)*
- Add the four optional props from §2.4 to `Props` (lines 30-45) with comments in the file's existing
  house style.
- Replace `isEspn` (lines 60-66) with the `SendPlatform` resolution from §2.2. **Keep the `#146`
  comment**, extended to record that the gate is now platform-generic and *why* (§1.4: MFL and
  Fleaflicker previously rendered a live button that always 400s).
- Add `NO_SEND_REASON` (module scope, beside the existing header comment block).
- Add `const [copied, setCopied] = useState(false)` and an `onCopy` callback:
  `copyText(formatTradeForClipboard({...}))` → `haptics.success()` → `setCopied(true)` → revert after
  2500 ms via a `useRef`'d timer cleared on unmount.
- Replace line 273 `if (!enabled || isEspn) return null;` with `if (!enabled) return null;` plus, above
  the existing `label`/`return`, the `!canSend` branch rendering the §2.2 block.
- Update the file-header comment (lines 16-28) — it currently states the ESPN behaviour as "returns
  null"; leaving it would reproduce the audit's own "do not trust comments over code" trap.

**4. `mobile/src/components/TradeCard.tsx`** *(both mounts, :577 and :589)*
Pass `givePlayerNames={data.give_players.map(p => p.name)}`,
`receivePlayerNames={data.receive_players.map(p => p.name)}`,
`opponentUsername={data.opponent_username}`, `leagueName={leagueName}`.
Add one optional prop `leagueName?: string` to `TradeCard`'s `Props` (undefined everywhere except
Matches). Update the block comment at :565-567 — it says the row is "Dismiss + Send in Sleeper …
so a flag-off build shows Dismiss alone", which is now only half true.

**5. Remaining call sites**
- `mobile/src/screens/MatchesScreen.tsx:616-623` — add `leagueName={item.league_name}` to the
  `TradeCardComp` mount. One line.
- `mobile/src/screens/TradesScreen.tsx:4713` — pass names + `opponentUsername` from `topCard`.
- `mobile/src/components/InLeagueCalculator.tsx:771` — pass names from `playerById` (reuse the exact
  expression already at :791-792) + `opponentUsername={opponent?.username}`.

**6. `mobile/src/api/trades.ts`** *(the disposition decision, §2.5)*
Delete `setMatchDisposition` and its two-line header comment (lines 504-516). Add one line at the
normalizer's `my_disposition` mapping noting mobile is read-only here and the writer is
`web/js/app.js:4342`.

**7. `mobile/src/components/CLAUDE.md`**
Update the `SendInSleeperButton` registry row — it currently reads "self-gates to Sleeper leagues",
which after this change is misleading.

**8. `mobile/.maestro/…`** — see §5.

**9. `mobile/tests/check-trade-text.js`** *(new)*
Node/transpile unit test for `formatTradeForClipboard` per the `check-session-rerank.js` idiom, plus
an `npm run test:trade-text` script entry in `mobile/package.json`. **This is the only coverage the
MFL/Fleaflicker half of the fix can get** (§5.4) — pin the platform→reason mapping here too by
exporting `NO_SEND_REASON`… **do not** import it from the component (that would drag React into the
transpile). Instead move `NO_SEND_REASON` and the `SendPlatform`/`resolveSendPlatform` pure parts into
`tradeText.ts` alongside the formatter, and have the component import them. One pure module, one test.

**Estimated diff:** ~130 added / ~20 removed across 8 files + 2 flow files. No backend files.

---

## 4. Surface changes

**None server-side. Explicitly:**

| Surface | Change |
|---|---|
| HTTP routes | **None.** No route added, renamed, removed, or contract-changed. `POST /api/sleeper/propose`, `POST /api/trades/matches/<id>/disposition`, `POST /api/trades/matches/<id>/dismiss` are all untouched |
| Schema / migrations | **None.** No table, column, or index |
| Feature flags | **None added.** `trade.send_in_sleeper` keeps its meaning and remains the kill switch: off → the component returns `null` on every platform, i.e. exactly today's ESPN behaviour everywhere. See §8 Q1 for the "should this get its own flag" question |
| Env vars / `model_config` | **None** |
| Analytics events | **None fired by this change.** See §9 — the events belong to P0-7 |
| `docs/api-reference.md` | **Not touched** (nothing to change) |

**One deliberate non-change, flagged for the operator.** §1.4 found that `POST /api/sleeper/propose`
lacks an `is_linked_platform_league` guard, so a hand-crafted request with an MFL league id still
reaches Sleeper's roster space. This plan fixes the *client*, which is the whole of P0-6's acceptance
criterion; hardening the route is a backend change that crosses the bright line (API contract) and is
out of this finding's scope. It should be filed — a one-line guard beside the existing
`league_id.isdigit()` check at `server.py:12336`, returning `400 bad_request`. Recorded in §8 as OQ-3
and proposed for `living-memory/NEXT.md`, not built here.

---

## 5. Maestro delta

### 5.1 The fixture already exists — and it was built for this finding

`backend/tests/fixtures/profiles/espn.json` seeds a 10-team `platform='espn'` league for `qa_espn`
with `matches_seed { mutual: 1, awaiting: 1 }` (`:72`), and its `description` (`:4`) names audit P0-6
and capture request #9 explicitly, right down to the fail-open precondition. `trade.send_in_sleeper`
is `true` in the release flag fixture, so the button is enabled and *would* render but for the gate —
which is what makes the capture evidence rather than a flag artifact. **No new profile is needed for
the ESPN half.**

### 5.2 `mobile/.maestro/capture/matches@espn.yaml` — must be updated *and* re-captured

This existing capture flow is the audit's "before" evidence. Two things:

- Its assertion `assertNotVisible: text: ".*Send in Sleeper.*"` **stays green after the fix** (the new
  label is "Copy trade"), so it will *not* fail loudly — it will silently keep passing while
  documenting behaviour that no longer exists. That is the dangerous failure mode, and it is why this
  file is on the change list rather than left alone.
- Add `assertVisible: id: "send-in-sleeper.copy"` immediately after the existing pair, so the flow
  goes red if the fix regresses in either direction.
- Rewrite the comment block (lines 7-17 and 42-52 describe the bug in the present tense) and the
  screenshot's meaning: `matches__populated--espn-mutual` becomes the **after** frame. Per
  `screens/CLAUDE.md` a mockup's "current" pane may not be redrawn, so the pre-fix PNG in the screen
  library is the artifact of record for the before-state and must be preserved (it is committed) —
  the re-capture replaces the library frame, and the plan's evidence trail cites both.
- Same treatment for the `populated--espn-awaiting` shutter (`TradeCard.tsx:589` mount): the send row
  no longer collapses to nothing.
- `backend/tests/fixtures/profiles/espn.json`'s `description` states the bug as current behaviour;
  update the tail of that paragraph in the same commit. It is a fixture doc-string, not test logic.

### 5.3 New flow: `mobile/.maestro/flows/p0-6-espn-copy-trade.yaml`

Profile `espn`, flags `release`, tags `[p0, matches, espn]`. Skeleton (id selectors only; the
sign-in-through-the-picker preamble is **copied verbatim** from `capture/matches@espn.yaml`, including
its retry-hardened `inputText` block — the fail-open gate means a launch-argument jump to Matches
would test the wrong branch):

```
… preamble → tab.matches → extendedWaitUntil text ".*New match with @.*"
- assertVisible: { id: "send-in-sleeper.unavailable" }
- assertVisible: { text: ".*Sending is Sleeper-only.*" }      # the STATED REASON half of acceptance
- scrollUntilVisible: { element: { id: "send-in-sleeper.copy" }, visibilityPercentage: 100, centerElement: true }
- tapOn: { id: "send-in-sleeper.copy" }                        # the USEFUL ACTION half
- assertVisible: { text: ".*Copied.*" }
- takeScreenshot: p0-6-espn-copy-trade
```

Every tap is an `id:` selector; every text match is an assertion. This satisfies `lld.md` §4.4 rule 1
and `mobile/scripts/testid-lint.sh` — and it is the concrete reason §2.2 rejected an alert-gated
action: native `Alert` buttons have no `testID`, so driving one requires a text-selector tap. (Note
for whoever reviews the lint: `flows/rookie/d3-mock-draft-loop.yaml:214-215` does exactly that today
and slips past the linter because its regex only matches `tapOn:` and `text:` on the *same* line.
Pre-existing; not this plan's to fix, but do not copy it.)

**Clipboard verification is out of Maestro's reach** — it cannot read the iOS pasteboard. The flow
verifies the affordance and the "Copied" acknowledgement; the *string* is verified by the unit test
(§3 item 9) and by one manual paste during the sim run (§7.3).

### 5.4 MFL / Fleaflicker — coverage gap, stated not waived

`backend/tests/fixtures/profiles/` contains `espn.json` but no MFL or Fleaflicker profile, and none of
the other profiles seeds a non-Sleeper league. So the MFL/Fleaflicker half of §1.4 **cannot be
simulator-covered without authoring a new profile** (a fixture seed + a league snapshot; the raw
material exists at `backend/tests/fixtures/mfl_league_snapshot_2026-07-17.json` and
`fleaflicker_league_snapshot_2026-07-17.json`).

**Recommendation:** do not build that profile inside a P0 bug-fix wave. Cover MFL/Fleaflicker by unit
test — `check-trade-text.js` pins `resolveSendPlatform` and `NO_SEND_REASON` for all four platform
values, which is where the entire platform-specific behaviour lives after §2.2 — and file the profile
as a `living-memory/NEXT.md` item. This is a **conscious partial-coverage decision**, recorded here
and in the scope block §3, for the operator to accept or reject before build.

### 5.5 Smoke-suite impact

`flows/smoke/08-matches.yaml` runs profile `standard` (a Sleeper league) and asserts only that the
empty state does not render — unaffected. `05-trades-render.yaml` / `06-trades-deck.yaml` are Sleeper
profiles — unaffected. No smoke flow crosses a non-Sleeper send surface today; that is exactly the
hole §5.3 fills.

---

## 6. Docs impact

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **n/a** | No route added, renamed, removed, or contract-changed (§4) |
| `living-memory/LLD.md` | **n/a** | No schema/route/invariant *convention* shifts. The platform-generic gate is a component-local rule, not a cross-client convention |
| `docs/architecture.md` | **n/a** | No module wiring or data-flow change; two new leaf utils under `mobile/src/utils/` |
| `living-memory/HLD.md` | **n/a** | No new module, client, or major flow |
| `docs/cross-client-invariants.md` | **n/a** | No shared constant, enum, or color. `NO_SEND_REASON` is mobile-only copy; web has no send-in-Sleeper surface |
| `docs/glossary.md` | **n/a** | No new domain term |
| `docs/design/components.md` | **n/a** | Reuses the specced `ghost` Button variant and `type.bodySm`/`chalk.dim`; no new component spec |
| `mobile/src/components/CLAUDE.md` | **updated** | `SendInSleeperButton` row — "self-gates to Sleeper leagues" → platform-generic gate with the copy fallback (§3 item 7) |
| `mobile/src/api/CLAUDE.md` | **check at build** | Only if it names `setMatchDisposition` — verify at edit time |
| `DECISIONS.md` (`D-011`) | **updated** | Two non-obvious choices: (a) RN core `Clipboard` over `expo-clipboard`, with the rebuild constraint and the `utils/clipboard.ts` migration seam; (b) delete the mobile `setMatchDisposition` wrapper while keeping the route (web is a live caller) and deferring accept/decline UX |
| `living-memory/GOTCHAS.md` (`G-013`) | **updated** | MFL/Fleaflicker league ids are numeric, so `league_id.isdigit()` at `server.py:12336` does **not** exclude them from the Sleeper propose path — the class of bug that already produced `#200` and `#220` |
| `living-memory/NEXT.md` | **updated** | Three items: accept/decline UX (deferred option B, §2.5); MFL/Fleaflicker harness profile (§5.4); `is_linked_platform_league` guard on `/api/sleeper/propose` (§4, OQ-3) |
| `living-memory/CHANGELOG.md` | **updated at ship** | Dated H2 |
| `living-memory/TEST_LEDGER.md` | **updated at ship** | Sim-run tier + result (§7) |
| `living-memory/DEPENDENCIES.md` | **n/a** | **No dependency added** — that is the point of §1.6 |

---

## 7. Test plan

### 7.1 Static gates
- `cd mobile && npx tsc --noEmit` — must be clean. Watch for: the deprecated-but-exported `Clipboard`
  type (`Clipboard.d.ts` exports `ClipboardStatic`, so this should pass; if the project runs
  `noImplicitAny` against `types_generated` instead, cast at the seam and note it).
- `python3 -m pytest backend/tests/ -q` — expected untouched-green; **no backend file changes**, so a
  failure here means someone else's concurrent commit, not this one.
- `bash mobile/scripts/testid-lint.sh` — must be 0. New ids `send-in-sleeper.unavailable`,
  `send-in-sleeper.copy`.

### 7.2 Unit
- `node mobile/tests/check-trade-text.js`:
  - `formatTradeForClipboard` — happy path; missing `leagueName`; missing `opponentUsername`; **empty
    name arrays fall back to ids**; multi-asset joining; no trailing blank lines.
  - `resolveSendPlatform` — `'espn' | 'mfl' | 'fleaflicker'` → not sendable; `'sleeper'` → sendable;
    **id absent from the league list → `'sleeper'` (the fail-open invariant, which is the single most
    load-bearing property in §2.2)**; `platform` undefined on a row → `'sleeper'`.
  - `NO_SEND_REASON` — a non-empty, platform-named string for all three non-Sleeper values.

### 7.3 Simulator (hermetic harness)
- `mobile/.maestro/flows/p0-6-espn-copy-trade.yaml` — green (§5.3).
- `mobile/.maestro/capture/matches@espn.yaml` — green with the new assertion, and its two shutters
  re-captured.
- **One manual step the harness cannot do:** after the flow's `tapOn: send-in-sleeper.copy`, paste
  into Notes on the simulator and confirm the string matches §2.3 (both sides, right perspective,
  right names). Record verbatim in `TEST_LEDGER.md` — this is the only end-to-end proof the clipboard
  write actually lands.

### 7.4 Manual / visual regression
- **Sleeper league, unchanged** — the highest-value regression check. `matches` (profile `standard`)
  and `trades` captures must be pixel-identical; run `mobile/scripts/screen-freshness.sh` and expect
  it to flag only ESPN-profile screens.
- Deck vertical cost (`#276`) — on the ESPN profile, confirm the deck's top card plus the new reason
  line still fits an 852 pt viewport. If it does not, the fallback is `!compact`-only reason text,
  and that becomes a recorded operator deviation.
- Flag-off check: `trade.send_in_sleeper=false` → nothing renders on any platform (today's behaviour,
  preserved).
- Matches "Awaiting them" segment on the ESPN profile — the `TradeCard.tsx:589` mount now renders the
  copy affordance where it previously rendered nothing.

### 7.5 Ship gate
**Tier 1** per `docs/runbook.md` § Pre-ship simulator gate — this is a mobile screen/state change with
visual deltas. Full smoke suite (11 flows) + the new P0-6 flow + `screen-capture.sh --screen matches`
(ESPN profile). Log in `TEST_LEDGER.md`, write `qa/sim-runs/last-sim-run.json`. **If this ships as
part of one combined P0 wave, a single tier-1 run covering all seven findings satisfies the gate —
that is the operator's sequencing call, not this plan's.**

---

## 8. Risks and open questions

### Risks

**R1 — RN core `Clipboard` is deprecated and will be removed.** `react-native@0.81.5` warns on first
access and the docs point at `@react-native-clipboard/clipboard`.
*Mitigation:* the whole surface is one function in `mobile/src/utils/clipboard.ts`; migrating to
`expo-clipboard` is a one-file edit whenever a native rebuild is next scheduled. The `warnOnce`
message appears once per dev session in Metro logs and is invisible in release.
*Why accepted:* the alternative — adding a native module — needs `npm install` + `expo prebuild` +
a fresh EAS/simulator build, none of which are available to this build, and would put a
`DEPENDENCIES.md` entry and a native-build risk into a *Bug, effort S* item.

**R2 — this change removes a currently-tappable control on MFL/Fleaflicker.** Not purely additive
(§1.4). An MFL user who had learned to tap Send and see an error will now see a copy affordance
instead. That is the fix, but it should be named in the changelog rather than discovered.

**R3 — `platform` cache trustworthiness.** `mobile/src/state/CLAUDE.md` warns that `platform` "is only
trustworthy while `draft.room` is on — the server stamps it inside that flag's block", and
`useSession.connectLeague` (`:426-437`) has to carry non-Sleeper rows forward by hand because
`getLeagues()` can never return them. A user whose cache lost its platform stamp resolves to
`'sleeper'` and sees the old always-fails button on MFL. **This is the pre-existing `#146` fail-open
contract, not a new hole** — the fix does not widen it, and inverting it (fail *closed*) would hide
the Send button on Sleeper leagues whenever the cache is cold, which is strictly worse. Named here so
it is a known limit rather than a surprise.

**R4 — `matches@espn.yaml` will not fail loudly if the fix regresses.** Its existing
`assertNotVisible "Send in Sleeper"` passes both before and after. §5.2's added `assertVisible` is
what closes this; if that line is dropped in review, the regression detector is gone.

**R5 — concurrent sessions.** Per the handoff, the working tree mutates. `TradesScreen.tsx` (6,158
lines) and `TradeCard.tsx` are hot files, and **P0-7 edits the same component** (§9). Re-diff before
editing; expect the `:4713` and `:577`/`:589` line numbers to have moved.

### Open questions (for the operator, before build)

**Q1 — should the copy fallback get its own feature flag?** This plan says **no**: it lives inside
`trade.send_in_sleeper`'s blast radius (flag off → nothing renders, exactly as today), a new flag is
itself a feature-flag-surface change that `CLAUDE.md`'s bright line calls "not a quick fix", and the
change replaces *nothing* with *something* on the only platforms it touches. If the build convention
for this branch is flag-per-finding, the alternative is one boolean `trade.copy_fallback` guarding
only the `!canSend` branch — ~4 lines, plus `config/features.json`, `backend/feature_flags.py`
`FLAG_KEYS`, and `docs/config-reference.md`. **Operator's call; default is no flag.**

**Q2 — does the reason line render on the compact deck mount?** Plan says yes (§2.2). The counter-case
is `#276`'s vertical-cost audit. Resolvable on-sim in one screenshot during §7.4; flagged only because
the fallback (`!compact` only) would leave the deck with an action and no stated reason.

**OQ-3 — `/api/sleeper/propose` has no `is_linked_platform_league` guard** (§1.4, §4). Out of scope
here (backend, API contract, bright line). Proposed as a `NEXT.md` item: one line beside
`server.py:12336`. Operator decides whether it rides along or waits.

**OQ-4 — is `setMatchDisposition` referenced anywhere outside this repo?** Repo-wide grep is clean,
but the `extension/` MV3 client and any external tooling were checked only by grep over this
worktree. Low risk (it is a mobile-only TS module), stated for completeness.

---

## 9. Note for the HLD — collision with P0-7

**P0-7 (analytics blindness) plans client instrumentation on `SendInSleeperButton` — the same file
this plan restructures. Flag this to both agents and to whoever sequences the merges.**

The collision is not just textual:

1. **Same file, overlapping hunks.** P0-6 rewrites the gate (lines 59-66) and the render tail (line
   273 onward); P0-7 will add `track()` calls in `onPress` / `doPropose` and, most likely, an
   impression event near the render. A three-way merge here is avoidable, not clever.
2. **P0-6 changes what "the send button was shown" *means*.** After this fix, a non-Sleeper mount
   renders an affordance that is *not* a send button. Any P0-7 impression event that fires
   unconditionally at mount would conflate ESPN copy-affordance impressions with Sleeper send
   impressions and quietly corrupt the send-funnel denominator — the same class of defect as the
   NULL-`platform` incident already on the record in `CLAUDE.md`.
3. **Analytics taxonomy is default-deny** (`backend/analytics_taxonomy.py`, `ALLOWED_CLIENT_EVENTS`,
   enforced at `analytics_ingest.py:376`). An unregistered event name is silently dropped. So P0-6
   deliberately **fires no `track()` calls at all** — it would need a server-side taxonomy edit,
   which is an analytics-surface change and crosses the bright line for a *Bug, effort S* item.

**Handoff from P0-6 to P0-7** — the events this surface wants, for P0-7 to spec and register:

| Proposed event | Fires when | Properties |
|---|---|---|
| `send_unavailable_shown` | the `!canSend` branch mounts | `platform` (`espn`/`mfl`/`fleaflicker`), `league_id`, `surface` (`match`/`deck`/`awaiting`/`calculator`) |
| `trade_copied` | `Copy trade` tapped, after a successful `copyText` | `platform`, `league_id`, `surface`, `give_count`, `receive_count` |

`platform` must be an explicit property on both — it is the dimension the whole finding is about.

**Recommended merge order: P0-6 first, P0-7 instruments on top.** P0-6 is structural (new branch, new
props, new render path); P0-7 is additive within whatever branches exist. The reverse order forces
P0-7 to re-instrument the branch P0-6 creates. If the two must land in parallel, the split is:
P0-6 owns `SendInSleeperButton.tsx` lines 30-66 and 273-end plus the two new `utils/` files; P0-7
owns the callbacks at 105-271 — and even then, one of them should rebase rather than merge.
