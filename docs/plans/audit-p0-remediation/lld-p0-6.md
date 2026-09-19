# LLD — P0-6: platform-generic send gate + copy-trade fallback

> **Code-level design.** No code changed by this document. Worktree
> `/Users/teresadickens/Documents/Claude/Projects/ftf-p0-remediation`, branch
> `p0-remediation-2026-08-10`.
>
> **Build agent:** `W1-P06` (wave 1, commit 8). **Authority:** [`hld.md`](hld.md) — §2 S-23…S-29,
> §3 commit 8, §4 wave 1 `W1-P06`, §6 rows 4/9/12, §7, §8 R9/R14/R15, §9 LLD-5, §10.5.
> **Source plan:** [`plan-p0-6.md`](plan-p0-6.md) · **scope block:** [`scope-p0-6.md`](scope-p0-6.md)
> · **requirements:** [`prd-p0-6.md`](prd-p0-6.md).
>
> Every line number below was re-read in this worktree while writing this document. Per HLD §8 R1
> the build agent **re-greps every anchor immediately before editing** and trusts the quoted text,
> not the number.

## Contents

- [0. What this commit is, in one paragraph](#0-what-this-commit-is-in-one-paragraph)
- [1. `mobile/src/utils/tradeText.ts` — the pure module](#1-mobilesrcutilstradetextts--the-pure-module)
- [2. `mobile/src/utils/clipboard.ts` — the seam](#2-mobilesrcutilsclipboardts--the-seam)
- [3. `SendInSleeperButton.tsx` — the component](#3-sendinsleeperbuttontsx--the-component)
- [4. The `surface` prop: optional now, required in commit 13](#4-the-surface-prop-optional-now-required-in-commit-13)
- [5. Mount-point diffs, one per call site](#5-mount-point-diffs-one-per-call-site)
- [6. `mobile/src/api/trades.ts` — the wrapper deletion](#6-mobilesrcapitradests--the-wrapper-deletion)
- [7. `mobile/tests/check-trade-text.js` + `package.json`](#7-mobiletestscheck-trade-textjs--packagejson)
- [8. Maestro: the capture edit and the new flow](#8-maestro-the-capture-edit-and-the-new-flow)
- [9. `backend/tests/fixtures/profiles/espn.json`](#9-backendtestsfixturesprofilesespnjson)
- [10. The P0-7 handoff — frozen regions and insertion regions](#10-the-p0-7-handoff--frozen-regions-and-insertion-regions)
- [11. Verification order](#11-verification-order)
- [12. Deviations from the HLD](#12-deviations-from-the-hld)

---

## 0. What this commit is, in one paragraph

One boolean (`isEspn`) becomes a resolved platform; one silent `return null` becomes a stated reason
plus a working action. Nothing on the Sleeper path changes — a Sleeper league renders byte-for-byte
what it renders today, and `trade.send_in_sleeper` off still renders nothing anywhere (S-24). Two new
pure-ish leaf utilities carry all platform-specific behaviour so the MFL/Fleaflicker half, which has
no simulator profile, can be pinned by unit test (S-25). The component's prop signature and render
path are settled **here, in wave 1**, so that P0-7 can insert `track()` calls into `onPress` and the
`doPropose` catch in wave 2 without a three-way merge (S-23).

**Eight files edited, four created, in one commit (HLD §3 commit 8).** `TradesScreen.tsx` is *not*
one of them — see §5.3.

---

## 1. `mobile/src/utils/tradeText.ts` — the pure module

**New file. Zero React imports, zero `react-native` imports, zero project imports.** That purity is
load-bearing twice over: `check-trade-text.js` transpiles this exact file and runs it under plain
node with a `require` shim that throws on any runtime import (§7), and it is the reason `copyText`
lives in a *second* file (§2).

Three exports, in this order.

### 1.1 `SendPlatform` and `resolveSendPlatform()`

```ts
/** Platforms a league can be linked from. Mirrors LeagueSummary.platform's
 *  four values (shared/types.ts) — deliberately NOT `string`, so a new
 *  platform is a compile error here and in NO_SEND_REASON, not a silent
 *  fall-through to "sendable". */
export type SendPlatform = 'sleeper' | 'espn' | 'mfl' | 'fleaflicker';

const NON_SLEEPER: readonly string[] = ['espn', 'mfl', 'fleaflicker'];

/** Which platform a send would target, from the SESSION's cached league list.
 *
 *  #146 fail-open, preserved verbatim: a league id that is not in the cache
 *  (demo league, stale cache, a launch that skipped the picker), or a cached
 *  row with no `platform` stamp, resolves to 'sleeper' and therefore keeps
 *  the Send button. Failing CLOSED would hide Send on real Sleeper leagues
 *  whenever the cache is cold, which is strictly worse (HLD §8 R15). */
export function resolveSendPlatform(
  leagueId: string | undefined,
  leagues: ReadonlyArray<{ league_id: string; platform?: string }>,
): SendPlatform {
  if (!leagueId) return 'sleeper';
  const row = leagues.find((lg) => lg.league_id === leagueId);
  const p = row?.platform;
  return p && NON_SLEEPER.includes(p) ? (p as SendPlatform) : 'sleeper';
}
```

**Why `leagues` is typed structurally** (`{league_id: string; platform?: string}[]`) rather than as
`LeagueSummary[]`: importing `../shared/types` would be a type-only import that `ts.transpileModule`
erases — so it would in fact still run under node — but a structural parameter keeps this module's
"no project imports" rule mechanical rather than a judgement call, and it is a strict supertype of
`LeagueSummary` (`platform?: string`, `shared/types.ts:83`), so `useSession((s) => s.leagues)` passes
unchanged.

**The block it replaces.** Verbatim, `mobile/src/components/SendInSleeperButton.tsx:59-66`:

```ts
  const enabled = useFlag('trade.send_in_sleeper');
  // #146 — reactive twin of api/espn.isEspnLeague: hide on imported ESPN
  // leagues. Fail-open: a league id missing from the cached list (demo
  // league, stale cache) keeps the button, matching pre-#146 behavior.
  const leagues = useSession((s) => s.leagues);
  const isEspn = leagues.some(
    (lg) => lg.league_id === leagueId && lg.platform === 'espn',
  );
```

**The `#146` comment convention this preserves, stated explicitly** so the build agent does not
"clean it up":

1. **The `#146` ticket reference stays in the comment.** House style throughout this component
   (`#180` at `:194`, `#146` at `:60`, `F1`/`F10` at `:35`/`:38`) is that a non-obvious branch names
   the ticket that produced it. The rewritten comment keeps `#146` and *adds* the P0-6 reference.
2. **"reactive twin of `api/espn.isEspnLeague`" is a real contract, not prose.** `isEspnLeague`
   (`api/espn.ts`) and `isMflLeague` / `isFleaflickerLeague` (`api/platformLink.ts`) are the
   **imperative** twins used from callbacks (`FreeAgentsScreen.resolveAddPlatform` calls all three).
   This component runs its check **during render**, so it must read the store through the
   `useSession` selector, not `useSession.getState()`. Keeping that sentence is what stops the next
   agent from "simplifying" to `getState()` and silently losing re-render on league switch.
3. **"Fail-open" is named as the design, with its consequence.** The sentence
   "a league id missing from the cached list (demo league, stale cache) keeps the button" is quoted
   by `capture/matches@espn.yaml`'s CRITICAL PRECONDITION block as the reason its flow must enter
   through the league picker. Changing the wording without changing that flow would orphan the
   capture's own justification.

The replacement, in place, with the same three claims plus the widening:

```ts
  const enabled = useFlag('trade.send_in_sleeper');
  // #146 + audit P0-6 — reactive twin of api/espn.isEspnLeague, widened from
  // "is it ESPN" to "which platform is it". Reactive (a useSession SELECTOR,
  // not getState()) because this runs in render, unlike the imperative twins
  // FreeAgentsScreen uses from callbacks. Fail-open, unchanged: a league id
  // missing from the cached list (demo league, stale cache) resolves to
  // 'sleeper' and keeps the button, matching pre-#146 behavior.
  //
  // The widening is a bug fix, not a generalization for its own sake: MFL and
  // Fleaflicker league ids are NUMERIC, so POST /api/sleeper/propose's
  // `league_id.isdigit()` check does not exclude them — those leagues rendered
  // a live Send button that always 400s roster_not_found. Non-Sleeper leagues
  // now render the copy fallback instead of a send that cannot work.
  const leagues = useSession((s) => s.leagues);
  const platform = resolveSendPlatform(leagueId, leagues);
  const canSend = platform === 'sleeper';
```

### 1.2 `NO_SEND_REASON`

```ts
/** One honest, platform-NAMED reason per non-Sleeper platform. Structurally
 *  mirrors FreeAgentsScreen's NO_ADD_REASON (#179) — see the note below on the
 *  one intentional difference. */
export const NO_SEND_REASON: Record<Exclude<SendPlatform, 'sleeper'>, string> = {
  espn:        'Sending is Sleeper-only for now — copy this trade to propose it in ESPN.',
  mfl:         'Sending is Sleeper-only for now — copy this trade to propose it in MyFantasyLeague.',
  fleaflicker: 'Sending is Sleeper-only for now — copy this trade to propose it in Fleaflicker.',
};
```

**The pattern being mirrored**, verbatim from `mobile/src/screens/FreeAgentsScreen.tsx:75-103`
(abridged to two of its four rows; the `Record<Exclude<…, 'sleeper'>, …>` shape and the
platform-named copy are the parts that transfer):

```ts
const NO_ADD_REASON: Record<Exclude<AddPlatform, 'sleeper'>, { title: string; body: string }> = {
  espn: {
    title: "Can't add in ESPN leagues yet",
    body:
      'This league is imported from ESPN with read-only access, so ' +
      'Fantasy Trade Finder can’t make roster moves there. Open the ' +
      'ESPN Fantasy app to add this player.',
  },
  mfl: {
    title: "Can't add in MFL leagues yet",
    body:
      'This league is linked to MyFantasyLeague with read-only access, so ' +
      'Fantasy Trade Finder can’t make roster moves there. Open MFL ' +
      'to add this player.',
  },
  …
};
```

**Three things carried over, one deliberately dropped.**

| Carried | Why it matters |
|---|---|
| `Record<Exclude<Platform,'sleeper'>, …>` keyed exhaustively | Adding a fifth platform to `SendPlatform` is then a **compile error** in this record. That is the whole enforcement value of the idiom. |
| The platform is **named in the copy** ("in ESPN", "in MyFantasyLeague") | `#179`'s rule: never say "this league type". The user knows which platform they linked; saying it is what makes the sentence honest rather than boilerplate. |
| `variant="ghost"` as the visual "this exists but can't fire here" (`FreeAgentsScreen.tsx:537-544`) | One vocabulary for "dimmed affordance" across the app; no second convention invented here. |
| **Dropped: `{title, body}` → a bare `string`** | FreeAgents' reason is the payload of an `Alert.alert(title, body)` (`explainNoAdd`, `:108-111`), so it needs a title. Here the reason renders **inline** and there is no alert, so a title would be a second line of chrome above a one-line explanation. See §3.3 for the full argument on inline-vs-alert, which is where this difference comes from. |

Copy is fixed at build time — it is not templated on league name, opponent, or count. `MyFantasyLeague`
is spelled out (not "MFL") because that is what the user saw on the link screen; `Fleaflicker` and
`ESPN` match `NO_ADD_REASON`'s spelling exactly.

### 1.3 `SendSurface`

```ts
/** Which mount the affordance is rendering in. Declared here, in the pure
 *  module, on P0-7's behalf (HLD §4 W1-P06 note): every value P0-7 will
 *  register as an analytics dimension is greppable in one place, importable
 *  without dragging React into the transpile, and pinned by check-trade-text.js.
 *  P0-6 fires no events — see §10. */
export type SendSurface = 'deck' | 'match' | 'awaiting' | 'calculator';

/** Exported only so the unit test can assert the union's exact membership —
 *  a TS type erases at transpile and cannot be checked at runtime. */
export const SEND_SURFACES: readonly SendSurface[] = ['deck', 'match', 'awaiting', 'calculator'];
```

Four values, matching the `surface` property in the P0-6 → P0-7 event contract
(`scope-p0-6.md` §1). See §12 D-1 for why this is `awaiting` and not HLD §4's `suggested`.

### 1.4 `formatTradeForClipboard()`

```ts
export function formatTradeForClipboard(input: {
  giveNames?: string[];
  giveIds?: string[];
  receiveNames?: string[];
  receiveIds?: string[];
  opponentUsername?: string;
  leagueName?: string;
}): string
```

**Exact output template.** Five candidate lines, assembled and then
`lines.filter(Boolean).join('\n')` — the same idiom as
`TradeCalculatorScreen.shareTrade` (`:501-538`, which builds an array with possibly-empty entries and
filters at `Share.share({ message: lines.filter(Boolean).join('\n') })`).

```
Trade proposal — {leagueName}
To: @{opponentUsername}
I send: {give.join(', ')}
I get: {receive.join(', ')}
(Built with Fantasy Trade Finder)
```

Rendered example, all fields present:

```
Trade proposal — QA ESPN League
To: @tdickens
I send: Justin Jefferson, 2027 1st
I get: Ja'Marr Chase, Jaxon Smith-Njigba
(Built with Fantasy Trade Finder)
```

Per-line rules, exhaustively:

| Line | Emitted when | Degraded form |
|---|---|---|
| 1 | always | `leagueName` absent, empty, or whitespace-only ⇒ `Trade proposal` (no dash, no trailing space) |
| 2 | `opponentUsername` non-blank | omitted entirely (never `To: @`, never `To: @them`) |
| 3 | resolved give side is non-empty | omitted entirely |
| 4 | resolved receive side is non-empty | omitted entirely |
| 5 | always | — |

The em dash on line 1 is `—` (U+2014) with spaces either side, matching the app's existing caption
style (`InLeagueCalculator`'s share caption at `:783`). The `@` on line 2 is literal and the username
is inserted raw — every call site already sources it from
`TradeCard`'s `data.opponent_username` or `opponent?.username`, both of which are bare usernames with
no `@`.

**The id-fallback rule** (this is the property that makes "the action never produces an empty
clipboard" true, and it is unit-pinned):

```ts
function sideNames(names: string[] | undefined, ids: string[] | undefined): string[] {
  if (ids && ids.length > 0) {
    // Per-INDEX fallback, not per-array: a partially-resolved names array
    // (the MatchesScreen adapters do exactly this — `m.my_side_player_names?.[i] || id`)
    // must not discard the names it does have.
    return ids.map((id, i) => (names?.[i] || '').trim() || id);
  }
  return (names ?? []).map((n) => (n || '').trim()).filter(Boolean);
}
```

Three consequences worth stating because a reviewer will ask:

1. **Ids are a real fallback, not a placeholder.** A raw Sleeper player id in the pasted text is ugly
   but *correct and actionable* — the recipient can look it up. An empty side is neither. The same
   trade-off is already made by `matchToTradeCardShape` (`MatchesScreen.tsx:835-846`:
   `name: m.my_side_player_names?.[i] || id`) and by `InLeagueCalculator`'s share fallback
   (`:791-792`: `playerById[id]?.name ?? id`).
2. **Whitespace-only names count as absent.** Trimmed before the `||`, so a `" "` name falls through
   to the id rather than producing `I send: , Ja'Marr Chase`.
3. **Both arrays empty ⇒ the line is dropped, not blanked.** The clipboard then still carries lines 1,
   2 and 5, so a paste is never zero-length. No mount can reach that state today (every mount has at
   least one id on each side), but the helper is total and the test pins it.

**No URL, and the reason is not "we forgot".** `growth.share_landing` owns share attribution: it is
the flag that appends `Build your own: {baseUrl}/?ref={username}` to
`TradeCalculatorScreen.shareTrade` (`:525-535`) and it fires `calc_trade_shared` when it does. Adding
a landing URL here would (a) put a `?ref=` attribution link into a surface the flag does not gate,
silently widening the attribution surface without a flag or an event, and (b) make an analytics
change inside a *Bug, effort S* item — the exact bright line `CLAUDE.md` draws. This payload is a
**paste-into-ESPN-chat message**, not a share; the two stay separate. If share-attribution from the
copy affordance is wanted later it is a `growth.share_landing` change with its own event, not a
string edit here.

**No trailing newline**, no leading blank line, no double blank lines — `filter(Boolean)` guarantees
all three, and the test asserts `out === out.trim()` and `!out.includes('\n\n')`.

---

## 2. `mobile/src/utils/clipboard.ts` — the seam

**New file, one function, ~10 lines including the comment.** It is a separate file from
`tradeText.ts` for a mechanical reason: it imports `react-native`, and `check-trade-text.js` runs
`tradeText.ts` under plain node with a `require` shim that **throws** on any runtime import (§7). One
file for both would make the unit test impossible.

```ts
import { Clipboard } from 'react-native';

// The app's ONE clipboard write. RN core's Clipboard is deprecated —
// react-native/index.js exports it behind a getter that calls warnOnce()
// ("Clipboard has been extracted from react-native core…") on first access,
// once per JS session: visible in Metro dev logs, invisible in release. The
// implementation (Libraries/Components/Clipboard/Clipboard.js) and the iOS
// native module (React/CoreModules/RCTClipboard.mm) both still ship in
// react-native@0.81.5, and Clipboard.d.ts exports ClipboardStatic, so this
// typechecks with no cast.
//
// Why not expo-clipboard: it is a NATIVE module — `npm install` + `expo
// prebuild` + a fresh EAS/simulator build — and mobile/node_modules is a
// symlink in this worktree, so npm install is unavailable to this build.
// Migrating is a ONE-FILE edit at the next scheduled native rebuild: swap the
// import and the call below; no call site changes (HLD §8 R14).
export function copyText(s: string): void {
  Clipboard.setString(s);
}
```

**The `warnOnce` reality, precisely** — so nobody treats the Metro warning as a build break:
`react-native@0.81.5`'s `index.js` defines `Clipboard` as a lazy getter that calls
`warnOnce('Clipboard-deprecation', …)` before returning
`require('./Libraries/Components/Clipboard/Clipboard')`. `warnOnce` is a no-op after the first call
and `console.warn` is stripped in release bundles. The warning fires **once per dev session, on first
copy**, i.e. only when the user is a developer who tapped the button.

**Return type is `void`, deliberately.** RN core's `setString` is synchronous and returns nothing;
there is no success signal to await and no failure to catch. The component's "Copied" flip is
therefore an acknowledgement of *the tap*, not proof of *the write* — which is exactly why the manual
paste in `TEST_LEDGER.md` is the only end-to-end evidence and is non-negotiable (PRD § acceptance).
When the seam migrates to `expo-clipboard` (whose `setStringAsync` returns `Promise<boolean>`) the
signature may become `Promise<boolean>` and the component gains a real success gate; that is noted
here so the migration is a considered change rather than a silent behaviour shift.

---

## 3. `SendInSleeperButton.tsx` — the component

### 3.1 Imports and module scope

```ts
// added to the existing react-native import
import { Alert, Linking, StyleSheet, Text, View, ViewStyle } from 'react-native';
// new
import { chalk, space, type } from '../theme/chalkline';
import { copyText } from '../utils/clipboard';
import {
  formatTradeForClipboard,
  resolveSendPlatform,
  NO_SEND_REASON,
  type SendSurface,
} from '../utils/tradeText';
```

`Text` is RN's, not `./chalkline/Text` — matching `TradeCard.tsx`, which renders its reason lines as
`<Text style={type.bodySm}>` (`:558`) on the very same card. `type.bodySm` already carries
`color: chalk.dim` (`theme/chalkline.ts:135-140`), so the reason line is dim by token, not by an
override. (`chalk` is still imported for `styles.reason`'s explicit `color` — see §3.4 — so the
intent survives a future token edit.)

### 3.2 Props

Five additions to `interface Props` (`:30-45`), all optional, in the file's existing comment style
(every non-obvious prop there carries a `//` block naming its ticket and its
undefined-changes-nothing contract — see `impressionId` at `:35-37` and `onSent` at `:38-41`):

```ts
  // audit P0-6 — copy-trade fallback payload. Names are preferred; the
  // formatter falls back per-index to givePlayerIds/receivePlayerIds, so a
  // mount that forgets a prop degrades to ids, never to an empty clipboard.
  // Undefined changes nothing on a Sleeper league (the branch never renders).
  givePlayerNames?: string[];
  receivePlayerNames?: string[];
  opponentUsername?: string;
  // Matches only — TradeMatch/AwaitingTrade carry league_name; the deck and
  // the calculator do not, and the copy text drops the line when absent.
  leagueName?: string;
  // P0-7 (analytics): which mount this is. Declared HERE, in wave 1, so
  // wave 2's instrumentation is a pure insertion into onPress/catch with no
  // signature change (HLD §2 S-23, §4 W1-P06 note). OPTIONAL in this commit
  // because TradesScreen's mount is plumbed in commit 11; commit 13 makes it
  // required, at which point a missed mount is a compile error. P0-6 itself
  // reads it nowhere and fires no events.
  surface?: SendSurface;
```

`SendSurface` is imported **as a type** (`import { …, type SendSurface }`) so no runtime binding is
added for it.

Destructure the five in the parameter list at `:49-58`, in the same order.

### 3.3 The copy handler and its state

Added beside the existing `const [state, setState] = useState<State>('idle');` (`:68`) and
`awaitingLinkRef` (`:71`):

```ts
  // Copy-affordance acknowledgement. Local label flip, not a toast: this
  // component mounts inside three different screens and has no toast host,
  // and an Alert would put a dismiss between the user and their next action.
  const [copied, setCopied] = useState(false);
  const copiedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (copiedTimer.current) clearTimeout(copiedTimer.current);
    },
    [],
  );

  const onCopy = useCallback(() => {
    copyText(
      formatTradeForClipboard({
        giveNames: givePlayerNames,
        giveIds: givePlayerIds,
        receiveNames: receivePlayerNames,
        receiveIds: receivePlayerIds,
        opponentUsername,
        leagueName,
      }),
    );
    haptics.success();
    setCopied(true);
    if (copiedTimer.current) clearTimeout(copiedTimer.current);
    copiedTimer.current = setTimeout(() => setCopied(false), COPIED_MS);
  }, [
    givePlayerNames, givePlayerIds, receivePlayerNames, receivePlayerIds,
    opponentUsername, leagueName,
  ]);
```

with `const COPIED_MS = 2500;` at module scope beside `NO_SEND_REASON`'s import.

Five specified behaviours:

1. **No confirm.** Copying is non-destructive, instant and reversible by not pasting. A confirm on a
   clipboard write is chrome.
2. **`haptics.success()`**, routed through `utils/haptics` — never `expo-haptics` directly. The
   taxonomy doc (`utils/haptics.ts:10`) reserves `success` for "an action completed", and explicitly
   names this component as the one file that used to bypass the taxonomy. The write is synchronous
   and cannot fail, so "completed" is honest here in a way it would not be for an async call.
3. **`Copied` for 2.5 s, then back to `Copy trade`.** The flip is the acknowledgement; the revert is
   what lets the user copy again (e.g. after switching apps and back).
4. **Re-tap while `copied` is true is allowed** and re-arms the timer (`clearTimeout` first). The
   button is never `disabled` — unlike the send path, there is no in-flight state to protect.
5. **Timer cleared on unmount.** `MatchesScreen` renders these inside a virtualized `FlatList`; a
   `setCopied` after unmount is a warning in dev and a leak in principle. The cleanup effect is
   mount-scoped (`[]`), which is correct because `copiedTimer` is a ref.

**Why inline prose rather than FreeAgents' `Alert`-behind-the-tap.** `explainNoAdd`
(`FreeAgentsScreen.tsx:108-111`) puts its reason behind the tap because the alert *is* the payload —
there is nothing else to offer. Here there is a real action, and putting the reason behind a modal
would (a) make the action worse by adding a dismiss, and (b) leave the reason invisible until tapped,
which fails the "**stated** reason" half of the acceptance criterion on the screenshot alone. Two
supporting reasons: the match card is already a mixed content+action surface with room for a line of
prose, unlike a dense FA list row; and native `Alert` buttons carry no `testID`, so an alert-gated
action could only be driven by a text-selector tap, which `docs/plans/mobile-testing/lld.md` §4.4
rule 1 bans and `testid-lint.sh` fails on (exit 2).

### 3.4 The render replacement at `:273`

Current, verbatim (`:273-290`):

```tsx
  if (!enabled || isEspn) return null;

  const label =
    state === 'sent' ? 'Proposal sent'
    : state === 'sending' ? 'Sending…'
    : state === 'checking' ? 'Send in Sleeper'
    : 'Send in Sleeper';

  return (
    <Button
      label={label}
      variant="secondary"
      compact={compact}
      disabled={state === 'sending' || state === 'checking' || state === 'sent'}
      onPress={onPress}
      style={style}
    />
  );
```

Replacement — the flag check narrows to the flag alone, and the platform branch becomes a render
branch above the unchanged Sleeper return:

```tsx
  // The flag is still the kill switch for the WHOLE component on EVERY
  // platform: off ⇒ null everywhere, i.e. exactly today's ESPN behaviour
  // applied universally. That is why the copy fallback needs no flag of its
  // own (HLD §2 S-24) and why `trade.send_in_sleeper` is its rollback lever.
  if (!enabled) return null;

  // Non-Sleeper league: a send is impossible (ESPN/MFL/Fleaflicker are
  // read-only imports and POST /api/sleeper/propose talks only to Sleeper's
  // roster space). State the reason, offer the one action that works.
  if (!canSend) {
    return (
      <View testID="send-in-sleeper.unavailable" style={[styles.unavailable, style]}>
        <Text style={styles.reason} numberOfLines={2}>
          {NO_SEND_REASON[platform]}
        </Text>
        <Button
          testID="send-in-sleeper.copy"
          label={copied ? 'Copied' : 'Copy trade'}
          variant="ghost"
          compact={compact}
          onPress={onCopy}
        />
      </View>
    );
  }

  const label = /* …unchanged… */;

  return (/* …unchanged Button… */);
```

`NO_SEND_REASON[platform]` typechecks without a cast: inside `if (!canSend)` TypeScript narrows
`platform` to `Exclude<SendPlatform, 'sleeper'>` because `canSend` is declared
`const canSend = platform === 'sleeper'`. **The build agent must keep `canSend` a `const` derived
from a literal comparison** — hoisting it into a `useMemo` or a function breaks the narrowing and
forces a cast, which is how the exhaustiveness guarantee in §1.2 gets lost.

New styles (the file currently has no `StyleSheet` — this is a new `const styles` at the bottom,
after the component, matching `TradeCard.tsx`'s layout):

```ts
const styles = StyleSheet.create({
  // Column, not row: the reason is a sentence and the action sits under it,
  // so a narrow mount (the deck's compact action column) wraps the prose
  // instead of squeezing the button.
  unavailable: { gap: space.xs, alignItems: 'flex-start' },
  reason: { ...type.bodySm, color: chalk.dim },
});
```

`style` (the caller's `ViewStyle`) is applied to the wrapper `View`, mirroring how the Sleeper branch
passes it to `Button` — so `TradeCard`'s `styles.actionBtn` (`flex`-based sizing in the match action
row) and `TradesScreen`'s `styles.sendInSleeper` keep their layout intent. `numberOfLines={2}` caps
the prose at two lines; the longest string (`MyFantasyLeague`, 100 chars) wraps to two lines at the
narrowest mount and is not truncated at default text size. At very large OS text sizes it *can*
truncate — accepted, because the action beneath it is self-describing and the alternative (unbounded
growth) breaks the deck's card height.

### 3.5 The file-header comment

`:16-28` currently states the ESPN behaviour as "returns null":

```
// "Send in Sleeper". Renders on any real trade surface (found / matched /
// suggested). Flag-gated: returns null when `trade.send_in_sleeper` is off.
// Platform-gated too (#146): returns null when `leagueId` is an imported
// ESPN league — the button proposes a REAL Sleeper trade, which is
// meaningless there. Gated centrally here (every mount passes leagueId)
// so future mounts can't forget it.
```

Leaving that would reproduce the audit's own "do not trust comments over code" trap. Replace the
platform sentences (lines 18-21 of the file) with:

```
// Platform-gated too (#146, widened by audit P0-6): the button proposes a
// REAL Sleeper trade, which is meaningless on an imported ESPN / MFL /
// Fleaflicker league. Those leagues now render a stated reason plus a
// "Copy trade" action instead of nothing — the send path itself is
// untouched and unreachable there. Gated centrally here (every mount
// passes leagueId) so future mounts can't forget it.
```

The flag sentence, the two-path description (`:22-28`) and the `#146` attribution all stay.

---

## 4. The `surface` prop: optional now, required in commit 13

This is the one piece of P0-6's diff that exists **entirely for P0-7** (HLD §4, "Note the deliberate
delegation"), and its two-step shape is a commit-greenness requirement, not a style choice.

| | Commit 8 (this LLD) | Commit 13 (`W2-P07` close-out) |
|---|---|---|
| Declaration | `surface?: SendSurface;` | `surface: SendSurface;` |
| Mounts plumbed | `TradeCard` ×2, `InLeagueCalculator` ×1 (this commit) | + `TradesScreen` ×1 (commit 11, `W2-TS`) |
| `tsc --noEmit` | green — the unplumbed `TradesScreen` mount omits an optional prop | green — all four plumbed |
| Enforcement | none | **a missed mount is a compile error** |

Commit 13's entire diff is deleting one `?`. It cannot land before commit 11 (HLD §3 hard ordering:
`8 before 10, 11, 13` · `11 before 13`), because between commits 8 and 11 the `TradesScreen` mount
does not pass `surface` and a required declaration would red the build.

**What P0-6 does with the value: nothing.** The component reads `surface` at zero sites in this
commit. That is intentional and must survive review — a P0-6 read would create a second consumer of a
prop whose only purpose is an analytics dimension, and would make commit 13's `?` deletion a
behavioural change rather than a type change. Reviewers who flag "unused prop" should be pointed at
this section.

---

## 5. Mount-point diffs, one per call site

Four mounts, three files owned by `W1-P06`; the fourth (`TradesScreen`) is a **specification handed
to `W2-TS`**, not an edit in this commit.

### 5.1 `mobile/src/components/TradeCard.tsx` — both mounts

**Props addition.** One optional prop on `interface Props` (the file's props block runs `:20-77`),
placed after `showSend` (`:29`) since it is the same feature area, in house comment style:

```ts
  // audit P0-6 — league display name for the copy-trade fallback's first
  // line. Matches passes TradeMatch/AwaitingTrade.league_name; every other
  // caller omits it and the copy text drops the line.
  leagueName?: string;
```

Destructured at the existing parameter list beside `showSend = false,` (`:109`).

**Context, verbatim** (`:565-596`) — the comment being corrected and both mounts:

```tsx
      {/* Mutual-match CTAs: Dismiss (archive, ELO-neutral) + Send in Sleeper
          (the real "execute the trade" action — flag-gated, renders null when
          the beta flag is off, so a flag-off build shows Dismiss alone). */}
      {variant === 'match' ? (
        <View style={styles.actions}>
          <Button
            variant="pass"
            label="Dismiss"
            onPress={onDismiss}
            disabled={acting}
            style={styles.actionBtn}
          />
          {showSend && (
            <SendInSleeperButton
              leagueId={data.league_id}
              theirUserId={data.opponent_user_id}
              givePlayerIds={data.give_player_ids}
              receivePlayerIds={data.receive_player_ids}
              style={styles.actionBtn}
            />
          )}
        </View>
      ) : (
        showSend && (
          <View style={styles.sendRow}>
            <SendInSleeperButton
              leagueId={data.league_id}
              theirUserId={data.opponent_user_id}
              givePlayerIds={data.give_player_ids}
              receivePlayerIds={data.receive_player_ids}
            />
          </View>
        )
      )}
```

**Comment rewrite.** The parenthetical "so a flag-off build shows Dismiss alone" is now only half
true — it is still exactly right for the flag, and no longer right as a description of the ESPN case:

```tsx
      {/* Mutual-match CTAs: Dismiss (archive, ELO-neutral) + the send column.
          Flag-gated: with trade.send_in_sleeper off the button renders null on
          every platform, so a flag-off build shows Dismiss alone. On a
          non-Sleeper league (audit P0-6) the same slot renders a stated reason
          plus "Copy trade" instead of a send that cannot work. */}
```

**Mount 1 — `:577`, match variant, `surface="match"`:**

```tsx
            <SendInSleeperButton
              leagueId={data.league_id}
              theirUserId={data.opponent_user_id}
              givePlayerIds={data.give_player_ids}
              receivePlayerIds={data.receive_player_ids}
              givePlayerNames={data.give_players.map((p) => p.name)}
              receivePlayerNames={data.receive_players.map((p) => p.name)}
              opponentUsername={data.opponent_username}
              leagueName={leagueName}
              surface="match"
              style={styles.actionBtn}
            />
```

**Mount 2 — `:589`, non-match send row, `surface="awaiting"`:** identical five additions minus
`style`, with `surface="awaiting"`.

Both name expressions are safe without guards: `give_players` / `receive_players` are non-optional
`Player[]` on `TradeCard` (`shared/types.ts:152-153`) and `Player.name` is a required `string`, and
both `MatchesScreen` adapters populate them (`matchToTradeCardShape` `:835-846`,
`awaitingToTradeCardShape` `:866-880`) with the same `names?.[i] || id` fallback the formatter uses —
so ids reach the clipboard only when the server sent no name, which is the intended degradation.

`surface` is a literal per branch rather than
`surface={variant === 'match' ? 'match' : 'awaiting'}` because the two mounts are already in
different JSX branches; a ternary would re-derive information the branch has already established.

### 5.2 `mobile/src/components/InLeagueCalculator.tsx:771`

Context, verbatim (`:768-778`):

```tsx
      {anySide ? (
        <View style={styles.actions}>
          {bothSides && opponentId ? (
            <SendInSleeperButton
              leagueId={leagueId}
              theirUserId={opponentId}
              givePlayerIds={giveIds}
              receivePlayerIds={receiveIds}
            />
          ) : null}
```

Diff — reusing the **exact** name expression already at `:791-792` inside `ShareTradeImage`'s
`fallbackText`, so the calculator has one way of resolving names:

```tsx
            <SendInSleeperButton
              leagueId={leagueId}
              theirUserId={opponentId}
              givePlayerIds={giveIds}
              receivePlayerIds={receiveIds}
              givePlayerNames={giveIds.map((id) => playerById[id]?.name ?? id)}
              receivePlayerNames={receiveIds.map((id) => playerById[id]?.name ?? id)}
              opponentUsername={opponent?.username}
              surface="calculator"
            />
```

No `leagueName` — the calculator has a `leagueId` but no league display name in scope, and the copy
text drops line 1's suffix cleanly. (Do **not** reach for the session's league list to synthesize
one; that would add a store read to a component that does not have one today, for one line of text.)

`opponent?.username` may be `undefined`; the formatter drops the `To:` line rather than emitting
`@them` (which is what the *share* fallback does at `:787-796` — that string is prose and reads fine
with a placeholder; a proposal header does not).

### 5.3 `mobile/src/screens/TradesScreen.tsx:4713` — **specification for `W2-TS`, not an edit here**

HLD §4 gives `TradesScreen.tsx` exclusively to `W2-TS` for the whole of wave 2 and lists it in commit
11, not commit 8; §8 R6 makes "no other agent may open the file" explicit. `W1-P06` therefore does
not touch it, and commit 8 stays green because `surface` is optional (§4).

Context, verbatim (`:4710-4726`):

```tsx
              {/* Send in Sleeper — flagged beta. Directly proposes THIS found
                  trade to the opponent (skips the mutual-match wait). Hides
                  itself when trade.send_in_sleeper is off. */}
              <SendInSleeperButton
                leagueId={topCard.league_id}
                theirUserId={topCard.opponent_user_id}
                givePlayerIds={topCard.give_player_ids}
                receivePlayerIds={topCard.receive_player_ids}
                impressionId={signalV2On ? rawTopCard?.impression_id : undefined}
                onSent={…}
                compact
                style={styles.sendInSleeper}
              />
```

The one-liner `W2-TS` applies in commit 11 — four P0-6 props plus P0-7's `surface="deck"`, which is
why HLD §3 describes it as one inherited edit rather than two:

```tsx
                givePlayerNames={topCard.give_players.map((p) => p.name)}
                receivePlayerNames={topCard.receive_players.map((p) => p.name)}
                opponentUsername={topCard.opponent_username}
                surface="deck"
```

No `leagueName` (the deck card carries no league display name). `topCard` is a `TradeCard`, so
`give_players` / `receive_players` are non-optional — same guarantee as §5.1. **`compact` is already
passed here**, which is what routes this mount into the compact reason line specified in §3.4 and
verified by S-27's `#276` check.

### 5.4 `mobile/src/screens/MatchesScreen.tsx` — both `TradeCardComp` mounts

HLD §4 lists this file's change as `leagueName={item.league_name}`. There are **two** `TradeCardComp`
mounts, both passing `showSend`, and both feed a `SendInSleeperButton`; the second is the very mount
`capture/matches@espn.yaml`'s `populated--espn-awaiting` shutter photographs. Both get the prop
(see §12 D-2).

Mutual segment, `:616-624`:

```tsx
                <TradeCardComp
                  variant="match"
                  data={matchToTradeCardShape(item, activeLeague?.league_id)}
                  leagueName={item.league_name}
                  onDismiss={() => handleDismiss(item)}
                  …
```

Awaiting segment, `:706-711`:

```tsx
                <TradeCardComp
                  variant="swipe"
                  data={awaitingToTradeCardShape(item, activeLeague?.league_id)}
                  leagueName={item.league_name}
                  showSend
                  …
```

`league_name` is `string | undefined` on both `TradeMatch` (`shared/types.ts:244`) and
`AwaitingTrade` (`:274`) — populated by `/api/trades/matches/all`'s enrichment, absent on legacy
single-league responses — and the prop is optional all the way down, so no guard is needed and the
copy text degrades to `Trade proposal`.

---

## 6. `mobile/src/api/trades.ts` — the wrapper deletion

S-29: **delete the mobile wrapper; the route and the live `web/js/app.js:4342` caller are untouched;
accept/decline UX is deferred to `NEXT.md`.**

The 13 dead lines, verbatim (`:504-516`, comment lines included — `:504-507` are the two-plus-two
comment lines the plan counts, `:508-516` the function):

```ts
// POST /api/trades/matches/:id/disposition
// Backend body shape: { decision: 'accept' | 'decline' }
// Translate from the frontend's 'accepted'/'declined' vocabulary at the
// API edge so screen code keeps its existing wording.
export async function setMatchDisposition(
  matchId: string,
  disposition: 'accepted' | 'declined',
) {
  const decision = disposition === 'accepted' ? 'accept' : 'decline';
  return api.post<any>(`/api/trades/matches/${matchId}/disposition`, {
    decision,
  });
}
```

All 13 lines go, plus the blank line that separated them from the following
`undoDeckSuppression` block. **Verified zero call sites** at build time by
`grep -rn "setMatchDisposition" mobile/ web/ extension/ backend/ --exclude-dir=node_modules` — which
must return only this definition before the delete and nothing after it.

**What stays, and why the delete is safe.** `normalizeTradeMatch` (`:460-486`) keeps mapping
`my_disposition` / `their_disposition` through `decisionToDisposition`; `TradeMatch` keeps both
fields (`shared/types.ts:263-264`). Those are **reads** of server-authoritative state and are the raw
material for the deferred accept/decline feature. The route
(`POST /api/trades/matches/<int:match_id>/disposition`, `backend/server.py:12742+`) and
`record_match_disposition` (`backend/database.py:6783+`, K-factors at `:6738`) are live and carry ELO
consequences; `web/js/app.js:4342` calls the route today. **P0-6 touches no backend file and no web
file.**

One comment line added at the normalizer, immediately above the `my_disposition` mapping (`:484`):

```ts
    // Mobile READS dispositions and does not write them (audit P0-6): the
    // client wrapper was unused and is gone; the writer is web/js/app.js
    // (POST /api/trades/matches/<id>/disposition). Accept/decline UX on
    // mobile is a NEXT.md item, not a missing call site.
    my_disposition:              decisionToDisposition(raw?.my_decision),
```

That comment is the whole point of the deletion: an exported, typed, unused API wrapper reads as
"mobile has an accept path" to the next person — which is precisely how this finding was framed. The
comment replaces the false signal with a true one.

**`mobile/src/api/CLAUDE.md`: verified n/a.** Its `trades.ts` row reads
`| `trades.ts` | Trade card fetch + decisions |` (`:13`) and does not name `setMatchDisposition`
anywhere in the file. The scope block's "check at build" resolves to **no edit**; `W3-DOCS` records
it as verified-n/a rather than leaving the row ambiguous.

---

## 7. `mobile/tests/check-trade-text.js` + `package.json`

**This is the compensating coverage for the MFL/Fleaflicker simulator waiver (S-25).** After §1, the
*entire* platform-specific behaviour of the fix is three pure exports; the component contributes only
"which branch renders". So the waiver is honest exactly to the extent that this file is thorough.

Idiom, copied from `mobile/tests/check-session-rerank.js`: read `src/utils/tradeText.ts`, transpile
with the project's `typescript` (`ts.transpileModule`, CommonJS/ES2019), run under
`new Function('module','exports','require', js)` with a `require` shim that **throws** —

```js
  throw new Error(
    `tradeText.ts gained a runtime import ("${name}") — it must stay pure ` +
      'so this check can run it under plain node.',
  );
```

— which is what mechanically enforces §1's purity rule, and is why `copyText` is in a different file.
Same `check()` helper, same `process.exit(1)` on failure, same closing
`console.log('\nAll trade-text checks passed.')`.

`mobile/package.json` gains one script beside the existing eight (`:11-19`):

```json
    "test:trade-text": "node tests/check-trade-text.js",
```

### Cases — `resolveSendPlatform` (all four platforms + the fail-open invariant)

| # | Input | Expect |
|---|---|---|
| 1 | `('L1', [{league_id:'L1', platform:'sleeper'}])` | `'sleeper'` |
| 2 | `('L1', [{league_id:'L1', platform:'espn'}])` | `'espn'` |
| 3 | `('L1', [{league_id:'L1', platform:'mfl'}])` | `'mfl'` |
| 4 | `('L1', [{league_id:'L1', platform:'fleaflicker'}])` | `'fleaflicker'` |
| 5 | **id absent from the list** — `('L9', [{league_id:'L1', platform:'espn'}])` | `'sleeper'` — **the fail-open invariant**, the single most load-bearing property in the design (HLD §8 R15) |
| 6 | empty list — `('L1', [])` | `'sleeper'` |
| 7 | row present, `platform` undefined | `'sleeper'` |
| 8 | row present, `platform: 'yahoo'` (unknown future value) | `'sleeper'` — fail-open is by allow-list, not by deny-list |
| 9 | `leagueId` `undefined` / `''` | `'sleeper'` |
| 10 | duplicate ids, first is `'espn'` | `'espn'` — `find`, first match wins, matching the old `some()` semantics |
| 11 | derived: `platform !== 'sleeper'` ⇔ not sendable, asserted for all four values | the `canSend` contract |

### Cases — `NO_SEND_REASON`

| # | Assertion |
|---|---|
| 12 | keys are exactly `['espn','mfl','fleaflicker']` — no `sleeper` key, no extras |
| 13 | every value is a non-empty string |
| 14 | every value **names its platform** in prose: `espn`→`/ESPN/`, `mfl`→`/MyFantasyLeague/`, `fleaflicker`→`/Fleaflicker/` (the `#179` honesty rule; catches a copy-paste that leaves all three saying "ESPN") |
| 15 | every value contains `Sleeper-only` — the shared explanation is the same on all three |

### Cases — `SEND_SURFACES`

| # | Assertion |
|---|---|
| 16 | exactly `['deck','match','awaiting','calculator']` — pins the dimension P0-7 registers |

### Cases — `formatTradeForClipboard`

| # | Input | Expect |
|---|---|---|
| 17 | all fields present, 2 give / 2 receive | the five-line block in §1.4, exactly, `===` against a literal |
| 18 | `leagueName` absent | line 1 is `Trade proposal` — no dash, no trailing whitespace |
| 19 | `leagueName: '   '` | same as 18 |
| 20 | `opponentUsername` absent | no `To:` line; the other four survive |
| 21 | **names absent, ids present** | `I send: 4034, 6794` — ids reach the clipboard, never blank |
| 22 | **names partially present** (`['Justin Jefferson', undefined]`, ids `['4034','6794']`) | `I send: Justin Jefferson, 6794` — per-INDEX fallback |
| 23 | one name is `'  '` | that slot falls through to its id |
| 24 | multi-asset joining | `', '` separator, no trailing comma |
| 25 | both sides empty (no names, no ids) | output is 3 lines (title, `To:`, footer); **never `''`** |
| 26 | any input | `out === out.trim()` and `!out.includes('\n\n')` — no trailing/leading/double blank lines |
| 27 | any input | `!/https?:\/\//.test(out)` — **pins the no-URL rule** so a future edit cannot quietly widen the `growth.share_landing` attribution surface (§1.4) |
| 28 | any input | first line starts `Trade proposal`, last line is `(Built with Fantasy Trade Finder)` |

---

## 8. Maestro: the capture edit and the new flow

### 8.1 `mobile/.maestro/capture/matches@espn.yaml` — the positive assertion (S-28)

The file's existing pair, verbatim (mutual segment):

```yaml
- assertVisible:
    text: ".*Dismiss.*"
- assertNotVisible:
    text: ".*Send in Sleeper.*"
```

`assertNotVisible: ".*Send in Sleeper.*"` **passes both before and after the fix** — before, because
the component returns null; after, because the new label is "Copy trade". A regression that restored
the silent-null would leave this flow green while it documents behaviour that no longer exists. The
edit is one added step immediately after the pair:

```yaml
- assertVisible:
    text: ".*Dismiss.*"
- assertNotVisible:
    text: ".*Send in Sleeper.*"
# audit P0-6 — the POSITIVE half. The assertNotVisible above passes before AND
# after the fix (the new label is "Copy trade"), so on its own it is a
# regression detector that can never go red. This id is the detector.
- assertVisible:
    id: "send-in-sleeper.copy"
```

The same single step is added after the awaiting segment's `assertNotVisible` (before its
`waitForAnimationToEnd` / `takeScreenshot: matches__populated--espn-awaiting`) — that shutter
photographs the `TradeCard.tsx:589` mount, whose send row previously collapsed to nothing.

Three comment regions in the same file describe the bug in the present tense and are rewritten
without touching a single step:

1. **Header, "CAPTURE REQUEST #9" block** — reframe from "P0-6's finding is that a user … gets a
   mutual match with NO send action" to: this frame is now the **after** evidence; the pre-fix PNGs
   remain the before-evidence in git history and in the screen library's committed frames, and per
   `screens/CLAUDE.md` a mockup's "current" pane is not redrawn.
2. **The `Dismiss PRESENT + Send ABSENT` comment** (above the assertion pair) — the line
   "the component returns null outright on an ESPN league (:272)" is now false; replace with "the
   component renders the P0-6 copy fallback on an ESPN league — `Send in Sleeper` stays absent, and
   `send-in-sleeper.copy` must be present."
3. **The `populated--espn-awaiting` comment** — "a dedicated send ROW (TradeCard.tsx:586-595) which,
   here, collapses to nothing at all" becomes "…which, here, renders the copy fallback instead of
   collapsing to nothing."

**The CRITICAL PRECONDITION block stays.** It is more load-bearing after the fix, not less: the
fail-open resolver still returns `'sleeper'` for a league id missing from the session cache, so an
entry that skips the picker would photograph the **Send** button and mislabel the frame. Extend it
by one sentence naming `resolveSendPlatform` as the new home of the check (the block currently quotes
the old `isEspn` expression — update the quote so the flow's own justification stays true).

Both shutters are **re-captured** (`mobile/scripts/screen-capture.sh --screen matches`, ESPN profile)
and the screen-library index rows move with them via `W3-DOCS`.

### 8.2 `mobile/.maestro/flows/p0-6-espn-copy-trade.yaml` — outline

```yaml
appId: com.fantasytradefinder.app
# tc: TC-P0-6-ESPN-COPY
# profile: espn
# flags: release
# tags: [p0, matches, espn]
```

Header comment states, in this order: the acceptance criterion being proved verbatim ("a matched ESPN
user has a stated reason and at least one useful action"); that the preamble is copied verbatim from
`capture/matches@espn.yaml` **including its retry-hardened `inputText` block**, and that entering
through the league picker is load-bearing because `resolveSendPlatform` fails open (a
launch-argument jump would test the Sleeper branch under an ESPN filename); and that **Maestro cannot
read the iOS pasteboard**, so this flow proves the affordance and the acknowledgement while the
*string* is proved by `check-trade-text.js` plus one manual paste recorded in `TEST_LEDGER.md`.

Steps:

| # | Step | Note |
|---|---|---|
| 1 | `launchApp` `clearState: true, clearKeychain: true, stopApp: true` | law 6 — the react-query cache is persisted |
| 2 | `extendedWaitUntil visible id: signin.username-input`, 15 000 | |
| 3 | `retry maxRetries: 2` → `tapOn` id, `eraseText`, `inputText: "qa_espn"`, **`assertVisible ".*qa_espn.*"`**, `tapOn signin.continue-btn`, `extendedWaitUntil id: leagues.row.*` 30 000 | law 10, copied verbatim |
| 4 | `tapOn id: leagues.row.*` | **the picker merge is what stamps `platform: 'espn'`** |
| 5 | `extendedWaitUntil id: tab.trades` 60 000, then `extendedWaitUntil id: rank.more-ways` 60 000, then `waitForAnimationToEnd` | law 8 — settle before any tab tap (#244) |
| 6 | `tapOn id: tab.matches` | |
| 7 | `extendedWaitUntil text: ".*New match with @.*"` 60 000 | the mutual tile's header, renders on no other branch |
| 8 | `assertVisible id: "send-in-sleeper.unavailable"` | structural half |
| 9 | `assertVisible text: ".*Sending is Sleeper-only.*"` | **the STATED REASON half of acceptance** |
| 10 | `assertNotVisible text: ".*Send in Sleeper.*"` | the non-Sleeper league still offers no send |
| 11 | `scrollUntilVisible element: {id: "send-in-sleeper.copy"}, direction: DOWN, visibilityPercentage: 100, centerElement: true, timeout: 20000` | the capture's RUN-1 finding: a 2-for-1 tile is taller than the viewport, so the action row must be **framed**, not merely mounted. `id:` element, not text |
| 12 | `tapOn id: "send-in-sleeper.copy"` | **the USEFUL ACTION half.** Every tap is an id selector |
| 13 | `assertVisible text: ".*Copied.*"` | the 2.5 s flip — assert immediately, never after a wait |
| 14 | `takeScreenshot: p0-6-espn-copy-trade` | law 23 — eyeballed during the tier-1 run |

**Law conformance, stated so review does not re-derive it:** law 1 — every text matcher is wrapped in
`.*`; law 4 — both new ids are plain string literals, so no `testid-lint-allow.txt` entry; law 5 — no
`waitForAnimationToEnd` between the copy tap and the `Copied` assertion (the 2.5 s window is short and
a wait would race it); law 16 — `# flags: release`, a resolved fixture under
`backend/tests/fixtures/flags/`; law 17 — no `openLink`; banned patterns — no fixed sleeps, no
coordinate taps, no `tapOn: text:`.

**Timing note for the build agent:** step 13 must follow step 12 with no intervening step. `COPIED_MS`
is 2 500 ms and Maestro's default `assertVisible` timeout is ample, but any inserted
`waitForAnimationToEnd` or screenshot between them spends part of the window. The screenshot at step
14 is inside the window by construction.

**New `testID`s:** `send-in-sleeper.unavailable`, `send-in-sleeper.copy` — both plain literals,
matching HLD §6's registry. `bash mobile/scripts/testid-lint.sh` must exit 0; it greps
`mobile/src` for `testID=` and never opens any `CLAUDE.md` (HLD §10.3), so no docs file is a wave-1
dependency.

### 8.3 What is *not* covered, restated

MFL and Fleaflicker have **no simulator coverage** — no profile exists for either and authoring one
(fixture seed + league snapshot, raw material at
`backend/tests/fixtures/mfl_league_snapshot_2026-07-17.json` and
`fleaflicker_league_snapshot_2026-07-17.json`) is out of proportion inside a *Bug, effort S* wave.
Compensated by §7's cases 3, 4, 8, 11, 14 over the pure module, which after §1 is where **all**
platform-specific behaviour lives. Filed to `NEXT.md` by `W3-DOCS`. This is S-25, signed off in the
scope block as W2.

---

## 9. `backend/tests/fixtures/profiles/espn.json`

**Description tail only — no logic, no seed, no flag.** The profile's `description` (`:4`) states the
bug as current behaviour:

> That is the point — SendInSleeperButton returns NULL for a league whose cached platform is 'espn'
> (#146), so the card shows Dismiss and nothing else, with no copy explaining why.

Replace that sentence with the post-fix statement, keeping the CAPTURE PRECONDITION sentence that
follows it **intact** (it is still true and the capture still depends on it):

> That is the point — before audit P0-6, SendInSleeperButton returned NULL for a league whose cached
> platform is 'espn' (#146), so the card showed Dismiss and nothing else with no copy explaining why;
> it now renders the stated reason plus a "Copy trade" action, and this profile is the only harness
> coverage of that branch.

`flag_overrides` are untouched — `trade.send_in_sleeper: true` is what makes the frame evidence rather
than a flag artifact, and `matches_seed {mutual: 1, awaiting: 1}` already seeds both mounts. This edit
ships **in the same commit as the fix** (HLD §8 R5: every fixture inversion moves with its fix).

Nothing else under `backend/` changes: `python3 -m pytest backend/tests/ -q` is expected
untouched-green, and a failure there is a concurrent session's commit, not this one.

---

## 10. The P0-7 handoff — frozen regions and insertion regions

HLD §9 LLD-5 requires this LLD to state "**the line-range proposal P0-7 inserts into** — an explicit
statement of which regions of the post-fix file are P0-7's and which are frozen". S-23 makes this a
**sequential handoff**, not a parallel line-range split (HLD §10.5 rejects the parallel version
outright): P0-6 lands the whole file in commit 8; P0-7 inserts in commit 10.

Regions are named by **grep anchor**, not line number — the file grows by ~60 lines in commit 8 and
every number in `plan-p0-6.md` §9 is already stale.

### 10.1 P0-7 may insert here, and only here

| Region | Anchor | What may be added |
|---|---|---|
| `onPress` body | `const onPress = useCallback(async () => {` | `track('sleeper_send_attempted', …)` after the `state !== 'idle'` guard and the `haptics.pickup()` call |
| `doPropose`'s `catch` | `} catch (err) {` inside `const doPropose = useCallback(async () => {` | `track('sleeper_send_failed', {…, error_code})` — the `code`/`detail` locals are already destructured there |

Both are **callback bodies**. Reads inside them use `useSession.getState()` / imperative accessors
if any store read is needed — never a new hook, which would change the render path.

### 10.2 Frozen — P0-7 must not modify

| Frozen region | Why |
|---|---|
| `interface Props` — except deleting the `?` on `surface` in **commit 13** | the signature is P0-6's; commit 13's entire diff is one character |
| The gate: `const platform = resolveSendPlatform(leagueId, leagues); const canSend = platform === 'sleeper';` | changing `canSend` off a literal comparison breaks the type narrowing in §3.4 |
| `if (!enabled) return null;` and the whole `if (!canSend) { … }` block | **no impression event may fire at mount** — see §10.3 |
| `onCopy`, `copied`, `copiedTimer`, the cleanup effect | P0-6's action path; `trade_copied` is specified in §10.3 as a **future** insertion, not one commit 10 makes |
| `styles`, the file header comment, `mobile/src/utils/tradeText.ts`, `mobile/src/utils/clipboard.ts` | P0-6's, and the utils are pinned by a unit test P0-7 does not own |

### 10.3 The two events specced for P0-7, and the trap

`scope-p0-6.md` §1 hands P0-7 two events. Neither is fired by P0-6 — the taxonomy is default-deny
(`ALLOWED_CLIENT_EVENTS`, enforced in `analytics_ingest.py`), so an unregistered name is
counted-and-dropped behind a 200 OK, and registration is commit 1's exclusive territory (S-36).

| Event | Fires when | Properties |
|---|---|---|
| `send_unavailable_shown` | the `!canSend` branch is shown | `platform` (`espn`\|`mfl`\|`fleaflicker`), `league_id`, `surface` |
| `trade_copied` | `Copy trade` tapped, after `copyText` returns | `platform`, `league_id`, `surface`, `give_count`, `receive_count` |

`platform` is an explicit property on both — it is the dimension the whole finding is about, and the
NULL-`platform` incident is the reason it is stated rather than inferred.

**The trap, stated once.** `send_unavailable_shown` is an **impression** event, and the frozen render
path is why P0-6 does not fire it. Any impression event that fires unconditionally at mount would
conflate copy-affordance impressions with send-button impressions and corrupt the send-funnel
denominator. HLD §1.4 resolves this: commit 10 instruments `onPress` / `catch` **only**. If
`send_unavailable_shown` is wanted later it needs a `firedRef`-guarded effect keyed on
`(leagueId, platform, surface)` — one row per mount per session, never one per render — and it must
be registered as `NON_INTENT` (HLD §2 S-32: `INTENT` is a deny-list, and a high-frequency impression
event landing as INTENT step-changes DAU/WAU on ship day). That design is **not** in this batch;
neither event is in commit 1's registered list (HLD §4 Wave 0). This section is the record of the
handoff, not a licence to build it.

---

## 11. Verification order

Run in this order; each gate is cheap and localizes the failure.

1. `node mobile/tests/check-trade-text.js` — the pure module, before anything imports it. Also the
   purity guard: a stray `react-native` import fails here with a named error.
2. `cd mobile && npx tsc --noEmit` — clean. Two things to watch: `Clipboard`'s deprecation is a
   runtime `warnOnce`, not a type error (`Clipboard.d.ts` exports `ClipboardStatic`, so no cast is
   needed — if the project's config makes it one, cast **at the seam in `clipboard.ts`** and nowhere
   else); and `NO_SEND_REASON[platform]` must typecheck **without** a cast, which is the proof that
   §3.4's narrowing survived.
3. `bash mobile/scripts/testid-lint.sh` — exit 0. New ids `send-in-sleeper.unavailable`,
   `send-in-sleeper.copy`; both plain literals, no allow-list entry.
4. `python3 -m pytest backend/tests/ -q` — expected untouched-green. **No backend file changes except
   `espn.json`'s description string**, so a failure means a concurrent session's commit.
5. `grep -rn "setMatchDisposition" mobile/ web/ extension/ backend/ --exclude-dir=node_modules` —
   must return nothing.
6. Simulator (part of the batch's single tier-1 run, `W3-QA`):
   `flows/p0-6-espn-copy-trade.yaml` green · `capture/matches@espn.yaml` green **with** the new
   assertions, both shutters re-captured · `flows/smoke/08-matches.yaml` green **unmodified**
   (profile `standard`, a Sleeper league — the primary regression proof).
7. Manual, on-sim, both recorded verbatim in `TEST_LEDGER.md`:
   - **The paste.** After the flow's copy tap, paste into Notes and confirm the string matches §1.4
     line for line — right sides, right perspective, right names. This is the **only** end-to-end
     proof the clipboard write lands (`copyText` returns `void`; §2).
   - **`#276` vertical cost (S-27).** On the ESPN profile, confirm the deck's top card plus the
     compact reason line still fits an 852 pt viewport. If it does not, the fallback is `!compact`-only
     reason text and that becomes a **recorded operator deviation**, not an agent decision.
8. Flag-off check: `trade.send_in_sleeper=false` ⇒ nothing renders on any platform (today's
   behaviour, preserved) — the rollback lever, exercised rather than assumed.
9. `mobile/scripts/screen-freshness.sh` — expect it to flag **ESPN-profile screens only**. Any
   Sleeper-profile frame going stale is a regression in the branch that was supposed to be
   byte-identical.

---

## 12. Deviations from the HLD

Two, both refinements of a one-cell summary rather than contradictions of a settled `§2` decision.
Neither reopens an S-row.

**D-1 — `surface` for `TradeCard`'s non-match mount is `'awaiting'`, not `'suggested'`.**
HLD §4's `W1-P06` row writes `surface={variant === 'match' ? 'match' : 'suggested'}`. The P0-6 → P0-7
event contract that HLD §9 LLD-5 requires this document to specify — `scope-p0-6.md` §1, quoted
verbatim in §10.3 — enumerates `surface` as `match | deck | awaiting | calculator`. Verified in the
tree: `showSend` has exactly two call sites (`MatchesScreen.tsx:621` and `:709`), so the non-match
send row is reached **only** from the Awaiting-them segment; nothing "suggested" mounts it. Using
both names would hand P0-7 a dimension value that never matches its registered enum, i.e. the
silent-drop class of defect this batch's commit 1 exists to prevent. Resolution: the union is
`'deck' | 'match' | 'awaiting' | 'calculator'` and the mount passes `"awaiting"`. If the HLD author
prefers `'suggested'`, it is a one-word change in `SendSurface` + one mount + one unit-test case, and
it must be made **before** commit 10 registers the property.

**D-2 — `MatchesScreen.tsx` gets `leagueName` on *both* `TradeCardComp` mounts.**
HLD §4 lists the file's change as `leagueName={item.league_name}`, singular. There are two mounts
(`:616` mutual, `:706` awaiting), both pass `showSend`, and both therefore render a
`SendInSleeperButton`; the awaiting one is the mount `capture/matches@espn.yaml`'s
`populated--espn-awaiting` shutter photographs. Omitting the second would give two identical
affordances on one screen different copy text for no reason. `AwaitingTrade.league_name` exists
(`shared/types.ts:274`) and is optional, so this is one line with no type risk.

**Explicitly *not* deviations** (recorded because a reviewer may mistake them for one): the split of
`SendSurface` into the pure module rather than the component (§1.3) — HLD §4 requires only that
P0-6 *declare* it in wave 1; `TradesScreen.tsx:4713` being a specification rather than an edit (§5.3)
— HLD §4 assigns the file to `W2-TS` and omits it from `W1-P06`'s list; and `NO_SEND_REASON` being
`Record<…, string>` rather than `NO_ADD_REASON`'s `Record<…, {title, body}>` (§1.2) — the reason
renders inline, so there is no alert title to carry.
