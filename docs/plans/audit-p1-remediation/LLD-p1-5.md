# LLD — P1-5 · Promote and measure the league invite (audit A-14)

> **Low-level design.** Every diff site, signature, predicate, payload shape and edge case
> for P1-5, pinned to file:line as read in this worktree.
>
> **Status:** design only. **No source file is changed by this document.**
> **Worktree:** `/Users/teresadickens/Documents/Claude/Projects/ftf-p1-remediation`, branch
> `p1-remediation-2026-08-11` @ `ab9368f` (== `origin/main` at time of writing).
> **Author:** P1-5 LLD/PRD agent, 2026-08-11.
> **Binding inputs, in precedence order:** [`DECISIONS-p1.md`](DECISIONS-p1.md) →
> [`HLD-p1.md`](HLD-p1.md) → [`plan-p1-5.md`](plan-p1-5.md) / [`scope-p1-5.md`](scope-p1-5.md).
> Where this LLD contradicts the plan, the contradiction is stated and evidenced in
> [§11 Corrections to the plan](#11-corrections-to-the-plan) — it is never silent.
>
> **Every line number below is PRE-P0.** P0 (`p0-remediation-2026-08-10`) has not merged.
> `LeagueScreen.tsx`, `MatchesScreen.tsx` and `InviteLeaguematesBanner.tsx` all take P0 edits.
> [§10 Re-verify after P0 merge](#10-re-verify-after-p0-merge) is a **gate**, not a courtesy:
> P1-5 carries the heaviest P0-3 dependency in the round.
>
> **Pair:** [`PRD-p1-5.md`](PRD-p1-5.md) — problem, acceptance criteria, Maestro specs, gates.

## Table of contents

- [0. Inherited decisions and their status](#0-inherited-decisions-and-their-status)
- [1. Data path for the social-proof number](#1-data-path-for-the-social-proof-number)
- [2. `inviteSocialProof` — the one formatter](#2-invitesocialproof--the-one-formatter)
- [3. `shareInvite` — the one share path](#3-shareinvite--the-one-share-path)
- [4. `InviteLeaguematesCard` — component contract](#4-inviteleaguematescard--component-contract)
- [5. The platform gate](#5-the-platform-gate)
- [6. Impression-event placement and the hooks constraint](#6-impression-event-placement-and-the-hooks-constraint)
- [7. Exact diff sites — current → intended](#7-exact-diff-sites--current--intended)
- [8. Event payload shapes and the T1 registry rows](#8-event-payload-shapes-and-the-t1-registry-rows)
- [9. Component placement, hierarchy and testIDs](#9-component-placement-hierarchy-and-testids)
- [10. Re-verify after P0 merge](#10-re-verify-after-p0-merge)
- [11. Corrections to the plan](#11-corrections-to-the-plan)
- [12. What this LLD does not decide](#12-what-this-lld-does-not-decide)

---

## 0. Inherited decisions and their status

| Source | Decision | Status for this LLD |
|---|---|---|
| `DECISIONS-p1.md` **D-P1-03** | The invite event name stays **`invite_shared`** | **WORKING ASSUMPTION, NOT AN OPERATOR DECISION.** Every event name, prop row and payload in §8 is written to it. It is cheap to reverse *at document level* and expensive after the T1 taxonomy commit freezes `backend/analytics_taxonomy.py`. **If it is to become `invite_sent`, that must land in P0-3 B4 and in T1 in the same wave, before T1 merges.** After T1, reversal is a T1 amendment commit with the full deploy-and-verify gate (`HLD-p1.md` §B, "frozen for the rest of the round"). |
| `HLD-p1.md` §A.2 / §C step 1 | The two new names + the `invite_shared` prop-row extension land in the **shared T1 commit**, not in a P1-5 commit | Binding. §8 is written as *T1 content owned by the T1 agent*, specified here, not as a P1-5 diff. |
| `HLD-p1.md` §B Wave B | P1-5 (B1) owns `LeagueScreen.tsx` and `MatchesScreen.tsx` exclusively for Wave B | Binding. All §7 diff sites are inside B1's file set. |
| `HLD-p1.md` §A.3 / R-7 | **If P0-7's OPTIONAL-A shipped, its `action` enum must NOT contain `invite`** | Named risk, carried into §10 as a hard re-verify row. Not resolvable by this agent. |
| `HLD-p1.md` §F R-1 | P1-5 **ships live on merge**. No feature flag. Rollback = `git revert` | Binding. Design must be revert-safe: see §7's "revert unit" column. |
| `plan-p1-5.md` §Design, scope §2 design note | Social proof uses the **aggregate** `leaguemates_total` / `leaguemates_joined` from `GET /api/league/summary` — **never** the flag-gated `/api/league/member-unlock-states` | **Settled.** §1 pins the path. This LLD contains no read of `league.unlock_badges_per_member`. |
| `plan-p1-5.md` D1/D2 | Both CTAs emit through **P0-3's rewritten `buildInviteUrl`**, imported — never copied, never re-implemented | Binding. §3 pins the single import site. |
| `plan-p1-5.md` OC-4 / `HLD-p1.md` PR-7 | The promoted card is **withheld on non-Sleeper leagues** (P0-3 D4: an ESPN/MFL league id cannot resolve) | Part of the design, not an edge case. §5 pins the predicate. |
| `plan-p1-5.md` OC-1…OC-10 / `HLD-p1.md` §E | **11 operator checkpoints unresolved** | This LLD does **not** resolve any of them. Each is marked at its diff site as `[GATE: PR-x / AN-x]`. The PRD lists them with blocking consequences. |

---

## 1. Data path for the social-proof number

**Zero new requests. Zero new fields. Zero new endpoints.** Verified end to end at `ab9368f`:

| Hop | Evidence |
|---|---|
| Backend computes the aggregate | `backend/database.py:5617` `leaguemates_joined = len(joined_rows)`; returned at `:5641-5642` (`"leaguemates_total"`, `"leaguemates_joined"`); confirmed-zero early return at `:5596-5609` returns both as `0` |
| Served unflagged | `GET /api/league/summary` — `backend/server.py:13363-13389`. No flag read on this route. |
| Typed on the client | `mobile/src/api/league.ts:182-183` — `leaguemates_total?: number; leaguemates_joined?: number;` on `LeagueSummaryRollup` (**both optional**) |
| Already in scope on League Home | `mobile/src/screens/LeagueScreen.tsx:310-311` — `const totalMates = num((summary as any)?.leaguemates_total); const joinedMates = num((summary as any)?.leaguemates_joined);` |
| Already fetched on Matches | `mobile/src/screens/MatchesScreen.tsx:142-148` (`leagueSummaryQuery`, keyed `['league-summary', activeLeagueId]` — **the same react-query key LeagueScreen uses at `:168`**, so the two surfaces share one cache entry and can never disagree); consumed at `:385-397` |

**Derived quantity.** `notJoined = totalMates - joinedMates`.

**Never fabricated.** `num()` (`LeagueScreen.tsx:301-302`) coerces a missing/non-finite value to `0`.
A `0` produced by *absence* is indistinguishable from a `0` produced by *truth* — so visibility is
gated on `!!summary` (the object having arrived), **not** on the numbers being non-zero. This
mirrors the screen's existing confirmed-zero discipline at `:336-349` and `summaryPending` at
`:297`.

> **Cache staleness is bounded and self-correcting.** `staleTime: 60_000` on both screens
> (`LeagueScreen.tsx:171`, `MatchesScreen.tsx:146`); pull-to-refresh calls `refetchAll`
> (`LeagueScreen.tsx:267-276`). The backend members cache is invalidated on membership writes
> (`_invalidate_league_members_cache`, `backend/server.py:5789-5798`). Worst case the card
> overstates `notJoined` by 1 for <60 s. **Accepted, cosmetic** (plan R8).

---

## 2. `inviteSocialProof` — the one formatter

**File:** `mobile/src/utils/leagueUnlocks.ts` (19 lines today; already the home of
`matchesUnlockRemaining` at `:17-19`, already imported by `LeagueProgressModule.tsx:7`).

**Why this file and not a new one:** its header comment at `:1-4` states the constraint the new
function must also honour — *"Zero runtime imports — keep it that way"* — because
`mobile/tests/check-league-unlocks.js` transpiles this exact file with `ts.transpileModule` and
runs it under bare node, throwing on any `require` (`check-league-unlocks.js:33-41`).

### Signature

```ts
/** Social-proof line for the invite CTAs. Returns null whenever the ask is
 *  not real — so "should the CTA render" and "what does it say" are ONE
 *  decision, in one place, testable without a screen.
 *  Pure; no imports; safe under tests/check-league-unlocks.js. */
export function inviteSocialProof(
  totalMates: number,
  joinedMates: number,
): string | null
```

### Contract — every branch enumerated

| # | Input condition | Return |
|---|---|---|
| C1 | `!Number.isFinite(totalMates) \|\| !Number.isFinite(joinedMates)` | `null` |
| C2 | `totalMates <= 0` | `null` — solo / unknown league. Mirrors `LeagueProgressModule.tsx:113` (`if (totalTeams <= 1) return null`) |
| C3 | `joinedMates < 0` or `joinedMates > totalMates` (impossible per `database.py:5617`, defended anyway) | `null` |
| C4 | `notJoined === 0` (everyone joined) | `null` — **[GATE: PR-10 / OC-8]** |
| C5 | `notJoined === 1 && totalMates === 1` | `Your leaguemate hasn't joined yet` |
| C6 | `notJoined === 1 && totalMates >= 2` | `1 of your {totalMates} leaguemates hasn't joined yet` |
| C7 | `notJoined >= 2` | `{notJoined} of your {totalMates} leaguemates haven't joined yet` |

**Copy is `[GATE: PR-5 / OC-1]`.** The table above is option (a) — *factual / self-interested* —
as written in `plan-p1-5.md:432-436`. **This LLD does not choose it.** If the operator selects
(b) or (c), only this function's string literals change; every caller, both render ladders and all
three event payloads are unaffected. That insulation is the reason the formatter exists.

**Trailing punctuation.** The function returns the sentence **without** a trailing period; callers
render it inside a `<Text>` that supplies none. Rationale: the Maestro `text:` matcher is
full-match regex (README law 1) and a period inside a regex is a wildcard — keeping punctuation out
of the returned string keeps the assertion honest. If copy option (b)/(c) needs sentence-final
punctuation, it belongs in the literal, and the flow's regex must be re-derived from source bytes.

### Unit test — **this is testable, contrary to the plan**

`plan-p1-5.md:370` and `scope-p1-5.md` W3 declare "there is no jest in `mobile/`" and waive unit
coverage of the four branches. **True about jest, misleading about coverage.** The repo already
runs pure-function tests over *this exact module*:

- `mobile/tests/check-league-unlocks.js` — transpiles `src/utils/leagueUnlocks.ts` and asserts
  `matchesUnlockRemaining` under plain node.
- Registered as `npm run test:league-unlocks` (`mobile/package.json` scripts).
- Six sibling harnesses use the same idiom (`check-feedback-badge.js`, `check-session-rerank.js`, …).

**Required by this LLD:** extend `mobile/tests/check-league-unlocks.js` with the seven cases C1–C7.
Cost is ~25 lines in an existing file with an existing npm script. **W3 should be withdrawn**, not
signed off — see [§11 correction 6](#11-corrections-to-the-plan).

---

## 3. `shareInvite` — the one share path

**File:** `mobile/src/utils/inviteShare.ts` (**new**). Sole owner of URL construction *by
delegation*, the OS share sheet, and two of the three events.

### Signature

```ts
import { Share } from 'react-native';
import { track } from '../api/events';
import { buildInviteUrl } from '../components/InviteLeaguematesBanner';

export type InviteSurface =
  | 'league_home'
  | 'matches_empty'
  | 'trades_banner'
  | 'members_overlay';          // members_overlay only if PR-9 / OC-7 = in

export interface ShareInviteArgs {
  leagueId:   string;
  leagueName?: string | null;
  username?:  string | null;    // referrer attribution; omitted if unknown
  surface:    InviteSurface;
  notJoined:  number | null;    // null = honestly unknown. NEVER substitute 0.
  totalMates: number | null;
  platform:   string;           // LEAGUE platform: sleeper|espn|mfl|fleaflicker|unknown
  screen:     string;           // track()'s 3rd arg — the route name
}

export async function shareInvite(args: ShareInviteArgs): Promise<void>
```

### Body — exact order of operations, and why each step is where it is

```
1.  if (!args.leagueId) return;                       // mirrors LeagueScreen.tsx:372
2.  track('invite_cta_tapped', <props §8>, args.screen);
3.  const url = buildInviteUrl(args.leagueId, args.username);   // P0-3's — D1
4.  const where = args.leagueName || 'our league';
5.  try {
6.    const res = await Share.share({
7.      message: `Join me on Dynasty Trade Finder to find trades in ${where} → ${url}`,
8.    });
9.    if (res.action !== Share.dismissedAction) {
10.     track('invite_shared', <props §8 + league_id>, args.screen);
11.   }
12. } catch { /* user dismissed the sheet — nothing to do */ }
```

- **Step 2 before step 6 is load-bearing.** Firing the tap event before the sheet opens is what
  makes `invite_cta_tapped` − `invite_shared` equal the share-sheet abandon rate. Firing it after
  would make the two events tautologically equal and the funnel step invisible.
  **[GATE: AN-5 / OC-6]** — if `invite_cta_tapped` is declined, delete step 2 only; nothing else
  in this file changes.
- **Step 3 imports `buildInviteUrl`; it never re-implements it.** The import direction
  util → component is unusual and deliberate: it preserves P0-3's exclusive ownership of
  `InviteLeaguematesBanner.tsx:27-31` and produces a **zero-line conflict** in that file
  (`plan-p1-5.md:190`, `HLD-p1.md` §A.3 last row). `buildInviteUrl` is called **after** the tap
  event so a throw inside it (post-P0-3 it may read a flag) cannot swallow the tap.
- **Step 7's message string is copied verbatim from the two existing call sites**
  (`InviteLeaguematesBanner.tsx:44`, `LeagueScreen.tsx:377`) — byte-identical today, which is why
  collapsing them is safe. Do not "improve" it here; that is a copy change and a `[GATE: PR-5]`.
- **Step 9 preserves today's semantics exactly** (`InviteLeaguematesBanner.tsx:46`). The
  `growth.share_landing` conjunct that currently guards it is **dropped** — `[GATE: OC-9]`, see §7 B12.
- **Step 12 swallows.** All three existing call sites already do
  (`InviteLeaguematesBanner.tsx:49-51`, `LeagueScreen.tsx:379-381`). A share-sheet throw must never
  surface as an error to the user.
- `track()` is fire-and-forget and never throws (`mobile/src/api/events.ts:188-193`, whole body is
  inside `try`), so no step needs its own guard.

### Call sites — exactly four (three if PR-9 = out)

| # | File:line (pre-P0) | Surface | Notes |
|---|---|---|---|
| 1 | `LeagueScreen.tsx:371-382` — body of `inviteLeaguemates` | `league_home` | Reached from the promoted card **and** (when the card is withheld) from `LeagueProgressModule`'s inline link via `onInvite` at `:700` |
| 2 | `MatchesScreen.tsx` — new handler in the mutual-empty branch | `matches_empty` | New |
| 3 | `InviteLeaguematesBanner.tsx:39-52` — body of `handleInvite` | `trades_banner` | `notJoined`/`totalMates` = **`null`** — the banner's props (`:20-25`) carry `total` but no join counts. Null is honest; `0` would be a lie |
| 4 | `LeagueScreen.tsx:803-815` — members-overlay head | `members_overlay` | **OPTIONAL-M, `[GATE: PR-9 / OC-7]`.** Drop the call site, the enum value, and the T1 prop-row comment's fourth value together |

> **Consequence worth stating:** call site 1 means the *legacy inline link also becomes measured*.
> On ESPN leagues — where the promoted card is withheld — the inline link now fires
> `invite_cta_tapped` with `platform: 'espn'`, which is the only way the round learns how much
> invite demand exists on the platform whose invites are broken (P0-3 D4). That is a feature of the
> design, not a leak.

---

## 4. `InviteLeaguematesCard` — component contract

**File:** `mobile/src/components/InviteLeaguematesCard.tsx` (**new**).

### Props

```ts
interface Props {
  leagueId:    string;
  leagueName?: string | null;
  username?:   string | null;
  totalMates:  number;          // from LeagueScreen.tsx:310
  joinedMates: number;          // from LeagueScreen.tsx:311
  platform:    string;          // §5
  summaryArrived: boolean;      // !!summaryQuery.data — see §1 "never fabricated"
  onShare: () => void;          // delegates to shareInvite({surface:'league_home'})
}
```

`onShare` is a callback rather than the card calling `shareInvite` itself, so the screen keeps a
single `inviteLeaguemates` function serving both the card and `LeagueProgressModule`'s `onInvite`
— one handler, one surface value, no chance of the two paths reporting different surfaces.

### Render ladder — every branch, in evaluation order

| # | Condition | Result | Gate |
|---|---|---|---|
| L1 | `!summaryArrived` | `null` — no skeleton, no `—`, no placeholder | — |
| L2 | `platform !== 'sleeper'` | `null` — the promoted card is withheld; the legacy inline link stays (§5) | `[GATE: PR-7 / OC-4]` |
| L3 | `inviteSocialProof(totalMates, joinedMates) === null` | `null` — covers `totalMates <= 0` (C2) and `notJoined === 0` (C4) in one call | `[GATE: PR-10 / OC-8]` |
| L4 | otherwise | Render | — |

**One decision, one source.** L3 delegates *both* "is there anything to say" and "what does it say"
to §2's formatter. There is no second visibility predicate that could drift from the string.

### Rendered structure (L4)

```
<View testID="league.invite-card">
  <Card>
    <TickLabel>Grow your league</TickLabel>                       ← existing primitive
    <Text testID="league.invite-social-proof" …>{proof}</Text>    ← heading-weight
    <Text …>{rationale copy}</Text>                               ← type.bodySm  [GATE: PR-5]
    <Button testID="league.invite-cta"
            label="Invite leaguemates"
            variant="primary"
            onPress={onShare} />
  </Card>
</View>
```

- Primitives only: `Card` (`mobile/src/components/chalkline/Card.tsx:19`), `Button`
  (`Button.tsx:29`, `VARIANTS` at `:88` — `primary` / `secondary` / `ghost` are the real values),
  `TickLabel` (`TickLabel.tsx:16`). **No new token, colour, radius or type step. No emoji, no
  gradient, no blur** (ADR-004/005, root `CLAUDE.md` §UI rules).
- The `Button` primitive already supplies `accessibilityRole="button"` and a 44 pt target
  (`Button.tsx:52-59`) — which is precisely what the inline text link cannot do
  (`LeagueProgressModule.tsx:263-272`, *"Nested-Text link ⇒ no 44pt target; documented deviation"*).
  **Closing that deviation is the finding's core deliverable**, not a side effect.
- **`InviteLeaguematesCard` fires no analytics.** The impression event lives on the screen — §6.

### `LeagueProgressModule.tsx` is NOT edited

Suppression is expressed entirely as a prop value at the call site (`LeagueScreen.tsx:700`).
The component already treats a missing `onInvite` as "render no link" at **both** of its two
invite branches — `:125` (`!compact && onInvite`) and `:200` (`remaining === 0 && onInvite`).
Zero diff to the #243-approved mock; the legacy affordance stays intact in every state the card
does not cover. `[GATE: PR-8 / OC-5]`

---

## 5. The platform gate

**`isEspn` is not the predicate.** `LeagueScreen.tsx:123-125` computes

```ts
const isEspn = cachedLeagues.some(
  (lg) => lg.league_id === leagueId && lg.platform === 'espn',
);
```

`!isEspn` is **not** the same as `platform === 'sleeper'`: `LeagueSummary.platform` is
`platform?: string` (`mobile/src/shared/types.ts:82`) and MFL / Fleaflicker values are live in the
type system (`mobile/src/api/auth.ts:536` → `'sleeper' | 'espn' | 'mfl' | 'fleaflicker'`). An MFL
league would pass `!isEspn` and get the promoted card — scaling exactly the dead end PR-7 exists to
prevent.

**The canonical idiom is already in the codebase** — `useSession.ts:436` reads
`(lg.platform ?? 'sleeper') !== 'sleeper'`, i.e. *absent means Sleeper*. Mirror it:

```ts
// League platform, canonical form. Absent ⇒ 'sleeper' (useSession.ts:436 idiom):
// a Sleeper league cached before the field shipped has no `platform`.
const leaguePlatform =
  cachedLeagues.find((lg) => lg.league_id === leagueId)?.platform ?? 'sleeper';
```

- `isEspn` at `:123-125` is **left exactly as it is** — it drives the ESPN badge (`:427`), the
  read-only note (`:466-471`), the re-sync block (`:741`) and `showPickAssign` (`:126`). Adding a
  sibling derivation is additive; rewriting `isEspn` in terms of `leaguePlatform` would be a
  drive-by refactor against coding-guideline 3.
- **`leaguePlatform` feeds two things at once:** the L2 gate (`!== 'sleeper'` ⇒ card withheld) and
  the `platform` prop on all three events (§8). One derivation, no chance of the gate and the
  telemetry disagreeing about what platform a league is.
- **A league missing from the session cache resolves to `'sleeper'` and the card renders.**
  This is the same fail-open `SendInSleeperButton` has (`profiles/espn.json` capture precondition:
  *"the button's ESPN test reads useSession().leagues and FAILS OPEN on a league id missing from
  that cache"*). Documented, matched deliberately for consistency, and recorded as residual risk
  R-P1-5-b in the PRD.

### On `MatchesScreen`

`MatchesScreen` has `leagues` (`:61`, `LeagueSummary[]`) and `activeLeagueId` (`:141`), so the same
derivation is available verbatim. The block renders only for the active league anyway (`:388`), so
the platform read and the count read describe the same league by construction.

---

## 6. Impression-event placement and the hooks constraint

### The constraint the plan does not mention

`LeagueScreen` has a **conditional early return** at `:280-291` (`if (!leagueId) { return … }`), and
**every value the card's visibility depends on is computed *after* it** — `summary` at `:293`,
`totalMates` / `joinedMates` at `:310-311`. A `useEffect` placed among those derivations would sit
below a conditional return and **violate the Rules of Hooks**: on a render where `leagueId` is null
the hook count changes and React throws.

`LeagueScreen.tsx` currently imports only `useState, useMemo` (`:1`) — `useEffect` is a new import.

### Resolution

The `invite_cta_shown` effect is placed **above the early return**, immediately after the query
block (after `unlocksById`, `:256-265`, before `refetchAll` at `:267`), and derives everything it
needs from `summaryQuery.data` directly:

```ts
// P1-5 — invite CTA impression. MUST sit above the `!leagueId` early return
// at :280 (Rules of Hooks); it therefore reads summaryQuery.data directly
// rather than the derived `summary`/`totalMates` below it.
const inviteShownRef = useRef<string | null>(null);
useEffect(() => {
  const s = summaryQuery.data;
  if (!leagueId || !s) return;                       // L1
  if (leaguePlatform !== 'sleeper') return;          // L2
  const total  = numSafe(s.leaguemates_total);
  const joined = numSafe(s.leaguemates_joined);
  if (inviteSocialProof(total, joined) === null) return;   // L3 — SAME predicate
  if (inviteShownRef.current === leagueId) return;         // fire-once, per league
  inviteShownRef.current = leagueId;
  track('invite_cta_shown', { …§8 }, 'LeagueHome');
}, [leagueId, summaryQuery.data, leaguePlatform]);
```

- **`inviteShownRef` is keyed by `leagueId`, not a boolean.** A bare boolean would suppress the
  impression forever after a league switch; `LeagueScreen` is not unmounted by a switch (the
  session's `league` changes under it). Keying by id fires once per league per screen lifetime.
- **The guard re-uses §2's formatter as its visibility predicate** — the effect and the card cannot
  disagree about whether a CTA was on screen. This is what keeps the impression denominator
  meaningful. (Directly mitigates plan R7 — `placeholderData: (prev) => prev` on six queries
  (`:172, :192, :203, :216, :224, :232, :243, :250`) makes this screen re-render often.)
- `numSafe` is a module-scope copy of the `num` helper at `:301-302` (which is declared *below* the
  early return and so is not in scope for the effect). Two lines; alternative is hoisting `num` to
  module scope, which is a wider diff in a file P0-7 also edits — **prefer the local copy.**
- **`screen` = `'LeagueHome'`** (the route name, per `TabNav.tsx:455-461`; the convention across 34
  `track()` call sites is the route/screen name). **Re-verify against P0-7's `league_view` call and
  use whatever screen string it uses** — §10.

### On `MatchesScreen`

`MatchesScreen` already imports `useEffect` (`:1`) and has **no** early return before the empty
branch, so its effect may sit beside the existing derivations at `:385-397`. Guard conditions:
`emptyModule !== null` **and** `segment === 'mutual'` **and** `visibleMatches.length === 0` **and**
`!isLoading && !isError` **and** the §2 formatter is non-null **and** platform is Sleeper.
`firedRef` keyed by `activeLeagueId`.

> **A caveat that must be recorded, not buried.** On `MatchesScreen` the CTA is mounted but, on the
> canonical device, is **clipped below the viewport** — see [§11 correction 1](#11-corrections-to-the-plan).
> Until that is resolved, `invite_cta_shown` with `surface: 'matches_empty'` counts *mounts*, not
> *sightings*, and its tap-through rate will read as artificially near-zero. This is a data-integrity
> consequence of a layout defect and is escalated as operator gate **OG-12** in the PRD. **Do not
> "fix" it by weakening the impression guard.**

---

## 7. Exact diff sites — current → intended

All line numbers **pre-P0**; re-locate by content per §10. "Revert unit" names what a `git revert`
must take to undo the change cleanly (there is no flag — `HLD-p1.md` R-1).

### New files (no conflict surface)

| # | File | Contents | Revert unit |
|---|---|---|---|
| N1 | `mobile/src/utils/inviteShare.ts` | §3 | whole file |
| N2 | `mobile/src/components/InviteLeaguematesCard.tsx` | §4 | whole file |
| N3 | `mobile/.maestro/flows/growth/invite-promotion.yaml` | PRD §Maestro, file A | whole file |
| N4 | `mobile/.maestro/flows/growth/invite-promotion@espn.yaml` | PRD §Maestro, file B (**split — see correction 3**) | whole file |

### `mobile/src/utils/leagueUnlocks.ts`

| # | Site | Current | Intended |
|---|---|---|---|
| B1 | after `:19` (EOF) | file ends after `matchesUnlockRemaining` | append `inviteSocialProof` per §2. **No import may be added** (`:1-4` constraint + `check-league-unlocks.js:36-41` throws on `require`) |
| B1t | `mobile/tests/check-league-unlocks.js` | asserts `matchesUnlockRemaining` only | append cases C1–C7 (§2). Run via `npm run test:league-unlocks` |

### `mobile/src/screens/LeagueScreen.tsx` — **B1 owns this file for Wave B** (`HLD-p1.md` §B)

| # | Site (pre-P0) | Current | Intended | Gate |
|---|---|---|---|---|
| B4a | `:1` | `import React, { useState, useMemo } from 'react';` | `+ useEffect, useRef` | — |
| B4b | `:62-65` (import block) | — | `+ import InviteLeaguematesCard from '../components/InviteLeaguematesCard';`<br>`+ import { shareInvite } from '../utils/inviteShare';`<br>`+ import { inviteSocialProof } from '../utils/leagueUnlocks';`<br>`+ import { track } from '../api/events';` | — |
| B4c | after `:125` | `isEspn` only | `+ leaguePlatform` derivation (§5). **`isEspn` unchanged.** | PR-7 |
| B7 | between `:265` and `:267` | `unlocksById` memo … `refetchAll` | `+ inviteShownRef` + the `invite_cta_shown` effect (§6). **Above the `:280` early return.** | AN-5, PR-7, PR-10 |
| B6a | `:369-370` | comment: *"the OS share sheet with the same referral URL the InviteLeaguematesBanner builds (`?league=&ref=`)"* | **Rewrite.** The parenthetical becomes false the moment `growth.invite_join_link` flips (P0-3 M1). New comment states the format is owned by `buildInviteUrl` and is deliberately not restated here. (A-33 class — `plan-p1-5.md:102`.) | — |
| B6b | `:371-382` | `inviteLeaguemates` body: `buildInviteUrl` + `Share.share`, **no analytics** | Body delegates to `shareInvite({ leagueId, leagueName: summary?.league_name \|\| league?.league_name, username: user?.username, surface: 'league_home', notJoined: totalMates - joinedMates, totalMates, platform: leaguePlatform, screen: 'LeagueHome' })`. Function stays `async`, stays at this position (it is referenced at `:700` and by B4d). | AN-5 |
| B4d | between `:473` (`</View>` closing `league.hero`) and `:475` (the action-row comment) | hero block then action row | `+ <InviteLeaguematesCard … onShare={inviteLeaguemates} />`. **Not** gated on `moduleVisible` — a fully-unlocked league still has un-joined members (§4). | PR-5, PR-7, PR-10 |
| B5 | `:700` | `onInvite={inviteLeaguemates}` | `onInvite={inviteCardVisible ? undefined : inviteLeaguemates}`, where `inviteCardVisible` is **the same predicate as §4's L1∧L2∧L3**, computed once near `:360` and passed to both the card and this prop. **One predicate, two consumers.** | PR-8 |
| B8 | `:803-815` (overlay head, beside the close control at `:806-814`) | header text + close button | `+ <Button testID="league.members-invite" label="Invite leaguemates" variant="secondary" compact onPress={() => shareInvite({…, surface:'members_overlay'})} />` | **OPTIONAL-M — PR-9** |
| B4e | `:65` | `import { buildInviteUrl } from '../components/InviteLeaguematesBanner';` | **Becomes unused** once B6b lands. **Remove the import.** Leaving it is a lint/dead-code carry and, worse, a decoy for the next reader looking for the URL format. | — |

> `inviteCardVisible` must be computed **after** `summary` (`:293`) and `totalMates`/`joinedMates`
> (`:310-311`) — i.e. in the derivation block around `:360`, alongside `moduleVisible` (`:358-359`).
> It is a *value*, not a hook, so the early return does not constrain it. The §6 effect deliberately
> re-derives the same predicate above the return rather than reading this variable; the duplication
> is forced by the Rules of Hooks and both derivations call §2's single formatter, so they cannot
> disagree about the answer.

### `mobile/src/screens/MatchesScreen.tsx` — **B1 owns this file for Wave B**

| # | Site (pre-P0) | Current | Intended | Gate |
|---|---|---|---|---|
| B9a | `:61-62` | `leagues`, `activeLeague` from session | `+ const user = useSession((s) => s.user);` — **`user` is not in scope on this screen today**, and without it the shared invite URL loses its `?ref=<username>` attribution on this surface (plan does not mention this) | — |
| B9b | `:387-397` (`emptyModule` memo) | returns `{ rankedMates, totalTeams }` | `+ totalMates: matchesSummary.leaguemates_total ?? null`<br>`+ joinedMates: matchesSummary.leaguemates_joined ?? null`<br>`+ platform:` (§5 derivation over `leagues` / `activeLeagueId`) | PR-7 |
| B11 | after `:397` | — | `+ firedRef` + `invite_cta_shown` effect, `surface: 'matches_empty'`, `screen: 'Matches'` (§6) | AN-5 |
| B10 | between `:548` (`/>` closing `matches.go-to-trades`) and `:549` (the compact-module comment) | primary button, then compact module | `+ {inviteBlockVisible ? (<><Text testID="matches.invite-social-proof">{proof}</Text><Button testID="matches.invite-cta" label="Invite leaguemates" variant="secondary" onPress={…} /></>) : null}` | **PR-6** (primary vs secondary), PR-5, PR-7, PR-10 |
| B10h | inside the empty branch | — | `+ const onInviteFromMatches = () => shareInvite({ leagueId: activeLeagueId!, leagueName: matchesSummary?.league_name ?? activeLeague?.league_name, username: user?.username, surface:'matches_empty', notJoined, totalMates, platform, screen:'Matches' })` | — |

`inviteBlockVisible` = `emptyModule !== null` (which already encodes *active league only* **and**
*both league reads confirmed*, `:388-390`) ∧ `platform === 'sleeper'` ∧
`inviteSocialProof(totalMates, joinedMates) !== null`. The `emptyModule` conjunct is what stops a
per-league count rendering under another league's filter chip (`:388`).

### `mobile/src/components/InviteLeaguematesBanner.tsx` — **P0-3 owns `buildInviteUrl`; P1-5 owns only `handleInvite`'s body**

| # | Site | Current | Intended | Gate |
|---|---|---|---|---|
| B12a | `:34-37` | comment: *"the invite URL already IS the landing page … the flag adds the share→open funnel event only"* | **Both halves are false today** and P0-3 M1 rewrites this block. **P1-5 must not reintroduce it.** If P0-3 left any of it, replace with a comment stating the URL comes from `buildInviteUrl` and the events come from `shareInvite` | — |
| B12b | `:38` | `const shareLandingOn = useFlag('growth.share_landing');` | **Remove** if it becomes unused after B12c. The flag key, its `true` default (`config/features.json:125`), `backend/feature_flags.py:272`, the release fixture and every other read are **untouched** | **OC-9** |
| B12c | `:39-52` | `handleInvite`: `buildInviteUrl` → `Share.share` → `if (shareLandingOn && res.action !== dismissedAction) track('invite_shared', {league_id}, 'Trades')` | Delegates: `shareInvite({ leagueId, leagueName, username, surface:'trades_banner', notJoined: null, totalMates: null, platform: 'sleeper', screen:'Trades' })`. **`notJoined`/`totalMates` are `null`, never `0`** — the banner's Props (`:20-25`) have no join counts | OC-9 |
| — | `:27-31` `buildInviteUrl` | — | **NOT TOUCHED.** Imported by `inviteShare.ts` | — |

> **B12c's `platform: 'sleeper'` is an assumption that must be re-checked.** The banner is mounted
> from `TradesScreen.tsx:3543`; whether a non-Sleeper league can reach that mount is not established
> in this LLD. If the banner's host has a platform in scope after P0, pass it; otherwise pass
> `'unknown'` rather than asserting `'sleeper'`. **Recorded as a §10 re-verify row, not decided here.**

### Docs and capture metadata

| # | File | Change |
|---|---|---|
| C2 | `docs/design/components.md` | Record `InviteLeaguematesCard` beside the other named League Home modules; record the Matches-empty invite block |
| C3 | `living-memory/DECISIONS.md` | Two entries: (1) the promoted card **suppresses** the inline link rather than coexisting; (2) one `shareInvite` owns all four emitters and both events, **layered on** P0-3's `buildInviteUrl`. **Allocate the ID at write time by re-reading the file** — nine claimants on `D-011` (`HLD-p1.md` §A.6). Do **not** use the ID printed in the plan |
| C5 | `screens/manifest.json` | `league.sources` is `["mobile/src/screens/LeagueScreen.tsx", "mobile/src/components/LeagueProgressModule.tsx"]` — **add `InviteLeaguematesCard.tsx`**. `matches.sources` is `[MatchesScreen.tsx, TradeCard.tsx, SendInSleeperButton.tsx]` — unchanged (the block is inline). Without C5, `screen-freshness.sh` under-reports the next time the card changes — the same manifest gap `HLD-p1.md` §A.5 files as RL-13b |
| C1 | `docs/cross-client-invariants.md:268-271` | **Folded into T1**, not a P1-5 commit (`HLD-p1.md` §A.5: three analytics writers target `:268`; T1 makes it one edit) |
| C4 | `living-memory/CHANGELOG.md` · `TEST_LEDGER.md` | On ship. TEST_LEDGER carries the tier-1 sim run **and** the row-landed verification |

---

## 8. Event payload shapes and the T1 registry rows

### T1 content owned by the T1 agent — specified here, **not** built by P1-5

Per `HLD-p1.md` §A.2 / §C step 1, `backend/analytics_taxonomy.py` and `backend/analytics_queries.py`
are written **once**, by the T1 agent, before any P1 client `track()` exists, and are **frozen**
afterwards.

| T1 ref | Structure | P1-5's content |
|---|---|---|
| T1.1 | `ALLOWED_CLIENT_EVENTS` (`analytics_taxonomy.py:38-99`) | **ADD 2 names:** `"invite_cta_shown"`, `"invite_cta_tapped"`. **`invite_shared` is NOT re-added** — P0-3 B4 registers it. Verified at `ab9368f`: `grep -n "invite" backend/analytics_taxonomy.py backend/analytics_queries.py` → **zero matches in either file** |
| T1.2a | `CLIENT_EVENT_PROPS` (`:165-255`) | **ADD 2 rows:**<br>`"invite_cta_shown":  frozenset({"surface","not_joined","total_mates","platform"}),`<br>`"invite_cta_tapped": frozenset({"surface","not_joined","total_mates","platform"}),` |
| T1.2b | `CLIENT_EVENT_PROPS` | **MODIFY P0-3 B4's `invite_shared` row** → `frozenset({"league_id","surface","not_joined","total_mates","platform"})`. **This is an extension, never an add.** A merge that keeps the pre-existing row leaves the *name* working and delivers **every row propless, with no error** (`HLD-p1.md` R-3). This is the single highest-value assertion in the round |
| T1.2c | comment on all three rows | Must state: **`platform` is the LEAGUE platform** (`sleeper\|espn\|mfl\|fleaflicker\|unknown`), matching the `league_selected` precedent at `analytics_taxonomy.py:185`. **Device platform is a server-derived column on `user_events`** — the NULL-`platform` incident. No event here carries a device-platform prop, and a test pins that |
| T1.3 | `NON_INTENT_EVENTS` (`analytics_queries.py:60-63`) | **ADD `"invite_cta_shown"` — MANDATORY, NOT OPTIONAL.** Verified at `ab9368f`: the set is `{app_opened, app_backgrounded, app_open, screen_viewed, push_sent, client_error, api_call, api_request}` and `:65` computes `INTENT_EVENTS = (SERVER_FIRED ∪ ALLOWED_CLIENT) - NON_INTENT` — **a deny-list.** Silence means INTENT. **An impression event fired on every League Home and every Matches-empty mount, left in INTENT, step-changes DAU/WAU on ship day and breaks every retention and churn series at that seam, silently and permanently.** `invite_cta_tapped` and `invite_shared` stay INTENT (real growth intent) |
| T1.4 | `backend/tests/test_events_api.py` | `test_p1_5_invite_events_accepted` — one envelope per name with the **full** prop set. Assert `accepted == N`, **`dropped == 0`**, exact `set(by_type)`, and — load-bearing — that `props.surface`, `props.not_joined`, `props.total_mates`, `props.platform` **survive on `invite_shared`**. Plus: a misspelled `invite_cta_shwon` is counted-and-dropped (default-deny still armed); a bogus `device_platform` prop is stripped while the event lands |
| T1.6 | `backend/tests/test_analytics_p0.py` | Membership for the two new names folded into the **single** combined edit of `test_live_taxonomy_is_disjoint`. Plus direct assertions: `"invite_cta_shown" in NON_INTENT_EVENTS` and `"invite_cta_tapped" not in NON_INTENT_EVENTS` |
| T1.8 | `docs/business/analytics/2026-08-11-p1-5-addendum.md` (new) | (a) **no invite baseline** — `invite_shared` has fired into a default-deny wall since it shipped, so post-ship reads are absolute, never a lift; (b) the `invite_shared` vs tracking-plan-§S3 `invite_sent` fork and its resolution (**D-P1-03, assumed**); (c) league-`platform` vs device-`platform`; (d) the **DAU/WAU seam date**; (e) the closed `surface` enum; (f) what is deliberately not instrumented (share-sheet channel, per-recipient attribution, invite→install) |

**T1's gate (blocking on P1-5's build):** merge → Render deploys → `GET /api/analytics/health` →
a hand-rolled `POST /api/events` per new name with its full prop set → **`dropped == 0` and every
prop echoed back**. `analytics_ingest.py:379-383` returns **200** on an unknown type and `:384-389`
strips unknown props — there is no error signal on either side, so this is verified, never assumed.

### Payload shapes as emitted by the client

```jsonc
// 1. invite_cta_shown — NON_INTENT. Once per surface per league.
{ "event_type": "invite_cta_shown",
  "screen": "LeagueHome",            // or "Matches"
  "props": { "surface": "league_home", "not_joined": 9,
             "total_mates": 11, "platform": "sleeper" } }

// 2. invite_cta_tapped — INTENT. First statement of shareInvite(), before the sheet.
{ "event_type": "invite_cta_tapped",
  "screen": "Matches",
  "props": { "surface": "matches_empty", "not_joined": 7,
             "total_mates": 9, "platform": "sleeper" } }

// 3. invite_shared — INTENT. Existing name (P0-3 B4). Sheet resolved non-dismissed.
{ "event_type": "invite_shared",
  "screen": "Trades",
  "props": { "league_id": "990000000000000001", "surface": "trades_banner",
             "not_joined": null, "total_mates": null, "platform": "sleeper" } }
```

**Rules that bind every emitter:**

1. `surface` ∈ `league_home | matches_empty | trades_banner | members_overlay` — **closed, 4 values.**
   If PR-9 (OPTIONAL-M) is declined, `members_overlay` is dropped from the enum, the T1 comment and
   the code together.
2. `not_joined` / `total_mates` are `int | null`. **`null` is honest; `0` is a lie.** The banner has
   no join counts; a stale summary can produce an unknown. Never substitute `0`.
3. `platform` is the **league** platform, from §5's single derivation. Never the device platform.
4. `league_id` appears **only** on `invite_shared` — that is P0-3 B4's existing row, and P1-5 extends
   it rather than reshaping it. The two new events do not carry `league_id`; **if the operator wants
   per-league invite analysis on the impression event, that is a T1 prop-row decision and must be
   made before T1 freezes** (surfaced, not decided).
5. **The `screen` field is envelope-level, not a prop** (`mobile/src/api/events.ts:188-192` third
   argument; envelope shape in `docs/cross-client-invariants.md:272-276`). It is not in any prop row
   and is not stripped.

---

## 9. Component placement, hierarchy and testIDs

### League Home — vertical order after the change

| Position | Element | Change |
|---|---|---|
| 1 | `league.whats-new` CoachMark (`:401-410`) | unchanged |
| 2 | `league.hero` Card (`:417-473`) | unchanged — **`smoke/09-league.yaml` waits on `league.hero`, which stays above the insert; the flow must stay green unmodified** |
| **3** | **`league.invite-card`** | **NEW** |
| 4 | day-one action row `league.action.rank` / `league.action.find` (`:478-495`) | unchanged, **pushed down** |
| 5… | Matches tiles, Explore, progress module, works-now, leaderboards | unchanged; `league.progress-invite` conditionally suppressed (B5) |

**Hierarchy.** The card owns the only `variant="primary"` in its own section. It sits above the
action row — whose `league.action.find` is also `primary` (`:490`) — so two solid-ice buttons are
adjacent in the scroll. **This is a real Chalkline-hierarchy question and it is not resolved here:**
`plan-p1-5.md:157` reasons about the Matches pairing (PR-6) but never about this one on League Home.
`plan-p1-5.md:423` (R10) treats the insert purely as a *fold* risk. Both the fold and the
double-primary are **decided from the re-captured screenshots** — `league/populated.png`,
`league/progress-module.png`, `league/works-now.png` — per README law 23. **Escalated as PRD gate
OG-13.** If the operator moves the card below the action row it is a one-line move of B4d.

### Matches empty state — vertical order after the change

`matches.empty-text` (`:526`) → body copy (`:531`) → `matches.go-to-trades` **primary** (`:543-548`)
→ **`matches.invite-social-proof` + `matches.invite-cta` secondary** (NEW) → `matches.progress-module`
(`:552-561`) → `Refresh` ghost (`:562`) → `matches.matching-help` (`:565-583`).

**`variant="secondary"` is `[GATE: PR-6 / OC-2]`.** The recommendation is (b) — "Find a trade" keeps
primary. **This LLD does not choose.** Changing it is one string in B10.

### testIDs

| testID | Site | State |
|---|---|---|
| `league.invite-card` | `InviteLeaguematesCard` root `View` | new |
| `league.invite-social-proof` | the proof `<Text>` | new |
| `league.invite-cta` | the `Button` | new |
| `matches.invite-social-proof` | `MatchesScreen` B10 | new |
| `matches.invite-cta` | `MatchesScreen` B10 | new |
| `league.members-invite` | `LeagueScreen` B8 | new — **PR-9 only** |
| `league.progress-invite` | `LeagueProgressModule.tsx:127, 202` | **unchanged.** Gains an *assert-absent* use. Not renamed, not removed |
| `matches.go-to-trades`, `matches.empty-text`, `league.hero`, `league.progress-module` | — | **unchanged.** Existing flows depend on all four |

All six new ids are **static string literals** ⇒ `mobile/scripts/testid-lint.sh` passes with no
`testid-lint-allow.txt` entry (README law 4 applies only to template literals). Register them in
`mobile/src/components/CLAUDE.md` / `mobile/src/screens/CLAUDE.md` per the repo's registry
convention — **noting that `HLD-p1.md` §A.5 lists those registries as multi-writer files; append,
re-read before writing.**

---

## 10. Re-verify after P0 merge

**Run every row before the first edit. Answer in writing in `scope-p1-5.md`. A row that comes back
"the premise no longer holds" STOPS the build and returns the item to planning** — it is not patched
around at the keyboard (`HLD-p1.md` §C step 0.5).

### From `HLD-p1.md` §G.0 (universal)

- [ ] `git fetch origin && git rev-parse origin/main` — record the sha in the scope block.
- [ ] All P0 commits present (P0-1, -2, -3, -5, -6, -7, -8/9).
- [ ] Rebase (do not merge); resolve nothing blind.
- [ ] Re-read `living-memory/DECISIONS.md` (+ `GOTCHAS`, `MISTAKES`, `OPEN_QUESTIONS`) for the next
      free IDs. **Do not use the ID printed in the plan** — nine claimants on `D-011`.
- [ ] Re-grep every `file:line` cited in this LLD.
- [ ] `mobile/node_modules` still symlinked. **Never run `npm install`.**

### From `HLD-p1.md` §G.5 (P1-5-specific)

- [ ] **THE LOAD-BEARING ONE.** `grep -n "buildInviteUrl" -A 8 mobile/src/components/InviteLeaguematesBanner.tsx`
      — confirm **P0-3 M1's flag-resolved format** is present *before writing a line*. Promoting a
      CTA that emits today's `${getBaseUrl()}/?league=…&ref=…` (`:27-31`) would **scale the broken
      link** — the single worst outcome available in this item.
- [ ] Confirm `hld.md:491-493` held: **P0-3 M3 was removed**, so `LeagueScreen.tsx:373` is untouched
      by P0-3 and `buildInviteUrl` reads the flag imperatively.
- [ ] Record **where P0-7's `league_view` mount effect landed** in `LeagueScreen.tsx`, and **which
      `screen` string it passes**. P1-5's `invite_cta_shown` effect goes **beside** it, not instead
      of it, and adopts the same screen string (§6).
- [ ] **If P0-7's OPTIONAL-A shipped, read its `action` enum. It must NOT contain `invite`**
      (`HLD-p1.md` R-7). If it does, **one invite tap fires two events** and double-counts the
      product's most important growth action. **Not agent-resolvable — escalate before B1 builds.**
- [ ] Re-read `invite_shared`'s `CLIENT_EVENT_PROPS` row on `main`, confirm **T1's extension landed**,
      then **prove it live**: a `POST /api/events` carrying `surface` **and** `not_joined` that
      **echoes both back**. `dropped == 0` is necessary but not sufficient — props strip silently.
- [ ] `mobile/src/screens/MatchesScreen.tsx` — P0-6 edited `:616-623`. Re-locate `:387-397`
      (`emptyModule`) and `:543-561` (the empty branch) **by content**.
- [ ] Confirm `growth.invite_join_link`'s current state. **Either state is safe** (plan D5) — but
      **record which**, because it determines which URL format the promoted CTAs emit on ship day.

### Additional rows this LLD adds

- [ ] `LeagueScreen.tsx` — confirm the **`if (!leagueId)` early return still sits between the query
      block and the derivations** (`:280-291` pre-P0). §6's hook placement depends on it. If P0-7's
      effect landed *below* that return, **P0-7 has a latent Rules-of-Hooks bug** — report it, do not
      copy it.
- [ ] `LeagueScreen.tsx:65` — confirm the `buildInviteUrl` import is still present and still unused
      after B6b, then remove it (B4e). If P0-3/P0-7 added another consumer, keep it.
- [ ] `LeagueProgressModule.tsx` — confirm **both** `onInvite` guards survive P0 unchanged: `:125`
      (`!compact && onInvite`) and `:200` (`remaining === 0 && onInvite`). **B5's zero-diff
      suppression depends on both.** If either changed, suppression must be re-designed and the
      "no change to `LeagueProgressModule.tsx`" claim is void.
- [ ] `mobile/src/shared/types.ts:82` — confirm `LeagueSummary.platform` is still `platform?: string`
      and that `useSession.ts:436`'s `?? 'sleeper'` idiom still holds. §5 rests on both.
- [ ] `MatchesScreen.tsx` — confirm the empty branch still has **no scrollable ancestor**
      (`styles.centered` at `:997-1003`, `flex: 1` + `justifyContent: 'center'`; the only `ScrollView`
      is the horizontal chip row at `:464`). If P0 or another item added one, **correction 1 is
      resolved and gate OG-12 closes.**
- [ ] `backend/tests/fixtures/profiles/*.json` — re-derive `leaguemates_total` / `leaguemates_joined`
      per profile from the seeder loop (`seed_ui_test_db.py:563-593`). **P0-1 rewrote
      `_validate_quickset` (`:314-366`) and P1-7 (Wave A) edits this file** — the Maestro `text:`
      assertions in the PRD are exact-count regexes and break if a fixture's roster count moves.
- [ ] `InviteLeaguematesBanner.tsx` — establish whether a **non-Sleeper** league can reach the
      banner's mount (`TradesScreen.tsx:3543`, a file P0-2 and P0-8/9 rewrite). If it can, B12c must
      pass a real platform, not the literal `'sleeper'` (§7 B12 note).
- [ ] `mobile/.maestro/flows/growth/` — P1-1/2 (Wave A) creates `share-links.yaml` in this directory.
      **Confirm the directory exists and the two files do not collide on name or tag.**

---

## 11. Corrections to the plan

Each is a place where `plan-p1-5.md` or `scope-p1-5.md` is wrong against the code as read at
`ab9368f`. Nothing here is a preference.

### 1. The Matches empty state **has no scroll container**, and the new block lands in the clipped region — **BLOCKING**

`plan-p1-5.md:424` (R11) rates the bottom-area layout hazard **Low-medium** and says *"The Matches
invite button sits mid-column, above the compact module and Refresh, not pinned to the bottom.
Confirm in the `matches@fresh` capture."*

**The defect is already diagnosed, already photographed, and already filed** —
`mobile/.maestro/capture/matches@near-unlock.yaml` carries a 40-line investigation:

> *"the empty branch is a plain `<View style={styles.centered}>` (flex: 1, justifyContent: 'center',
> MatchesScreen.tsx:997-1003) with NO scroll container anywhere in its ancestry … that column is
> taller than the visible area … Everything after 'Find a trade' is therefore unreachable to a user
> AND to a camera — the progress module, the 'Refresh' ghost button, and the 'How matching works'
> help link are all clipped away."*

Confirmed at HEAD: `styles.centered` at `:997-1003`; the only `ScrollView` on the screen is the
horizontal chip row at `:464`; the two `FlatList`s (`:586`, `:678`) belong to the populated branch.
The audit accepted it as **a new finding of the same class as A-34**
(`docs/business/product/2026-08-09-mobile-ux-audit/09-capture-requests-response.md:32-34`).

**Consequences for P1-5, all three of which the plan misses:**

1. **B10 inserts the invite block immediately below `matches.go-to-trades` — the exact boundary
   where clipping begins.** The block is not "at risk"; on the canonical device it is **born
   invisible**.
2. **The Maestro assertion cannot detect it.** README law 2: off-screen children stay in the
   hierarchy, so `assertVisible id: matches.invite-cta` passes while nothing is on screen. The
   capture file says so explicitly: *"a bare [scrollUntilVisible] would have 'succeeded' anyway"*.
   A green run would certify an invisible CTA.
3. **`invite_cta_shown` on `surface: 'matches_empty'` becomes a mount counter, not an impression
   counter** — inflating the denominator of the one metric this item exists to create, and making
   the Matches surface look like a failed CTA when it is an unrendered one.

**Not resolvable by this agent.** Adding a `ScrollView` (or top-anchoring the column) to
`MatchesScreen`'s empty branch is a layout change on a screen P1-5 owns for Wave B but that is **not
in P1-5's scope block**, and it would change `matches/empty--mutual.png`, `matches/progress-module.png`
and the near-unlock and fresh variants. **Escalated as operator gate OG-12** with three options
(fix in P1-5 / ship P1-5's block into the clipped region knowingly / defer the Matches surface
entirely to the A-34 owner). **The recommendation is not this agent's to make.**

### 2. `smoke/08-matches.yaml` asserts `matches.empty-text` is **NOT** visible

`plan-p1-5.md:314` and `scope-p1-5.md` §3 both state the flow *"waits on `matches.empty-text`, which
stays above the new block"*. **It does not wait on it — it asserts its absence.**

```yaml
- assertNotVisible:
    id: "matches.empty-text"
```

…on `# profile: standard`, whose header comment says *"standard seeds `matches_seed {mutual: 2}` —
the empty state must NOT render."*

The flow still stays green (P1-5 adds nothing to the populated branch), **but the plan's stated
reason is wrong**, and the wrong reason would let a future reader conclude the smoke suite covers
the empty state. It does not.

### 3. The four Maestro blocks **cannot live in one file** — one profile per run

`plan-p1-5.md:316-321` specifies one file, `flows/growth/invite-promotion.yaml`, with block 1–3 on
`standard` and block 4 on `espn`.

The seeded backend takes **one** `--profile` for the whole run (`mobile/scripts/sim-run.sh:21, 31,
54` — `--profile` is a required run argument feeding `seed_ui_test_db.py --print-env`), and the
handshake **hard-asserts** the served profile matches (`sim-run.sh:114`: `assert
w['profile']==os.environ.get('FTF_TEST_PROFILE'), 'profile mismatch'`). README law 16 makes the
same point for `# flags:` (a resolved fixture filename **and** a cell-grouping key). A single YAML
file therefore cannot span two profiles.

**⇒ Two files** (PRD §Maestro): `invite-promotion.yaml` (Sleeper profile, blocks 1–3) and
`invite-promotion@espn.yaml` (blocks 4–5), matching the `capture/<screen>@<profile>.yaml` convention
already in use.

### 4. Block 3 **cannot run on `standard`** — that profile has no empty Matches state

`plan-p1-5.md:320` says *"Matches empty state. Same profile"* (i.e. `standard`).
`profiles/standard.json` seeds `"matches_seed": { "mutual": 2, "awaiting": 1 }`, so
`visibleMatches.length === 0` is false and the empty branch never renders. Blocks 1–2 (League Home)
and block 3 (Matches empty) are mutually exclusive on `standard`.

**`near-unlock` satisfies all three**: `total_rosters: 12`, 2 listed members, `matches_seed
{mutual: 0, awaiting: 0}` ⇒ `leaguemates_total = 11`, `leaguemates_joined = 2`, `notJoined = 9`, and
an empty mutual inbox. **The same "9 of your 11" string is then assertable on both surfaces in one
run** — a stronger proof of the shared-formatter design than the plan's split. (`fresh` also has an
empty inbox but yields "7 of your 9": 10 rosters − app user − 2 joined.)

Verified further on `near-unlock`: `app_user.unlocked: false` with `trios_per_position:
"threshold-1"` ⇒ `positionsRanked < 4` ⇒ `moduleVisible` true (`LeagueScreen.tsx:357-359`), and
`rankedMates = 1` ⇒ `matchesUnlockRemaining = 0` ⇒ the inline link renders via
`LeagueProgressModule.tsx:200-212`. **So block 2's `assertNotVisible: league.progress-invite` is a
real assertion on this profile** — the link genuinely would be there.

### 5. On `espn`, `league.progress-invite` **is** present — but only because `contrarian` is insufficient

`plan-p1-5.md:321` asserts block 4 should see `league.progress-invite` on the `espn` profile. **True,
and worth pinning because it is not obvious:** `profiles/espn.json` has `"members": []`, so
`ranked_user_count = 1 < 3` ⇒ `insufficient_data: true` (`backend/server.py:13753-13763`) ⇒
`contrarianInsufficient` ⇒ `moduleVisible` (`LeagueScreen.tsx:358-359`) — even though the ESPN app
user is fully ranked and the league has a seeded mutual match. `rankedMates = 0` ⇒ `remaining = 1`
⇒ the link renders via the **`:124-137` inline-sentence** branch (not the `:200` branch).

**Fragile.** If a future fixture change gives the ESPN league three ranked members, `moduleVisible`
goes false, the module unmounts, and block 4's `assertVisible: league.progress-invite` fails for a
reason unrelated to P1-5. The flow must carry this in a comment.

### 6. `inviteSocialProof` **is** unit-testable — withdraw waiver W3

`plan-p1-5.md:370` / `scope-p1-5.md` W3 waive unit coverage: *"there is no jest in `mobile/`"*.
True about jest, wrong about coverage. `mobile/tests/check-league-unlocks.js` already transpiles
**`src/utils/leagueUnlocks.ts` — the exact target file** — and runs it under plain node; it is wired
as `npm run test:league-unlocks`; six sibling harnesses use the same idiom. See §2.

### 7. The plan's "capture variants" are **profiles**; the manifest tracks **states**

`plan-p1-5.md:329` / `scope-p1-5.md` §3 list eleven `screen@profile` names. `screens/manifest.json`
tracks *states*: `league` has 11 (`coverage--single-format`, `draft-picks-row`, `espn-auth-expired`,
`espn-badge`, `espn-resyncing`, `first-paint-pending`, `hero--second-league`, `populated`,
`progress-module`, `progress-ring--4-4-locked`, `works-now`) and `matches` has 9 (`empty--mutual`,
`error`, `populated--all-filter`, `populated--awaiting`, `populated--espn-awaiting`,
`populated--espn-mutual`, `populated--mutual`, `progress-module`, `skeleton`). **20 frames**, not 11.
All 20 are re-taken in the consolidated R1 pass (`HLD-p1.md` §A.5) — none of them by P1-5's own
commit.

### 8. `screens/manifest.json` does not declare the new component as a source

`league.sources` is `["mobile/src/screens/LeagueScreen.tsx",
"mobile/src/components/LeagueProgressModule.tsx"]`. `InviteLeaguematesCard.tsx` must be added or
`screen-freshness.sh` will silently under-report the next time the card changes — the same
under-declaration `HLD-p1.md` §A.5 files as follow-up RL-13b. §7 C5.

### 9. `MatchesScreen` has no `user` in scope

`plan-p1-5.md` B9/B10 do not mention it. `MatchesScreen.tsx:61-62` pulls `leagues` and
`activeLeague` from the session but **not `user`**, so `?ref=<username>` attribution would be
silently dropped on this surface. §7 B9a adds the selector.

### 10. `LeagueScreen`'s `buildInviteUrl` import becomes dead

`LeagueScreen.tsx:65` imports `buildInviteUrl` for the sole use at `:373`. After B6b that use is
gone. The plan does not mention removing the import. §7 B4e.

### 11. The double-primary on League Home is unexamined

The plan reasons carefully about the Matches hierarchy (OC-2 / PR-6) but the card's `primary` CTA
lands directly above `league.action.find`, also `primary` (`LeagueScreen.tsx:487-493`). Neither the
plan nor the audit addresses two adjacent solid-ice buttons on League Home. §9 / PRD gate OG-13.

### 12. The plan's Maestro claim that `smoke/09-league.yaml:34` "waits on `league.hero`" — **correct**

Verified: `extendedWaitUntil: visible: id: "league.hero"`, and the card is inserted *below* the hero.
Recorded so the audit trail shows this one was checked rather than assumed.

---

## 12. What this LLD does not decide

- **No product or copy question.** OC-1/PR-5 (framing), OC-2/PR-6 (Matches hierarchy),
  OC-4/PR-7 (platform gate), OC-5/PR-8 (suppression), OC-6/AN-5 (`invite_cta_tapped`),
  OC-7/PR-9 (members overlay), OC-8/PR-10 (zero-not-joined), OC-9 (`growth.share_landing` gate),
  OC-10/AN-8 (the A/B) are marked `[GATE]` at their diff sites and enumerated in the PRD with
  blocking consequences. **None is resolved here.**
- **AN-3 / D-P1-03** is written to as a stated assumption (§0), not as a decision.
- **Correction 1's remedy (OG-12)** and the double-primary (OG-13) are surfaced with options and
  no recommendation.
- **It invents no new design.** Everything above is the plan's design, pinned to real lines, with
  the plan's own errors corrected against the code and marked as corrections.
