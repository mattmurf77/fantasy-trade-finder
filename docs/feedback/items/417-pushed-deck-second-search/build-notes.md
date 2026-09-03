# FB-417 — build notes

**Branch:** `feat/fb417-pushed-deck-research` (off `c529abc8`) · **Date:** 2026-09-03
Requirements: [prd.md](prd.md) R-1…R-5. Gate block: [scope.md](scope.md).

## 1. What changed

### `mobile/src/screens/TradesScreen.tsx` (the only source file)

| Post-change line(s) | Change | Requirement |
|---|---|---|
| :776 | New state `const [fairSweepPending, setFairSweepPending] = useState(false);` — the jobless fair sweep's in-flight marker (neither `generateMutation.isPending` nor `job?.status` is true while it runs) | R-3 |
| :1130 | `handleFindTrades`: `if (fairDeck) resetDeckForNewTargets();` — inserted **before** `setFairDeck(false)` (:1131) and `dispatchGenerate({})` (:1134), so the reset's epoch bump precedes the dispatch it stamps | R-2 |
| :2906 | `resetDeckForNewTargets`: `setFairSweepPending(false);` — a reset supersedes any sweep in flight, and that sweep (epoch-guarded) will not disarm the flag itself | R-3 |
| :3552 | `runFairPackages`: `setFairSweepPending(true);` at entry, beside `const epoch = deckEpochRef.current;` | R-3 |
| :3584 | …disarmed on the success exit, after the `#330` epoch guard (:3572), beside `setFairDeck(true)` | R-3 |
| :3594 | …disarmed on the failure exit, after the same guard (:3586), beside `setFairDeck(false)` | R-3 |
| :5820 | New derivation `const findCtaHiddenForAnchoredDeck = isResultsPushed && fairDeck;`, next to `inlineAnchorShown` (:5807) — one predicate read by both CTA arms so they cannot drift | R-1 |
| :7229 | Legacy `!consolidateOn` arm gate: `canvasHost !== 'flag' && !findCtaHiddenForAnchoredDeck` | R-1 |
| :7238-7243 | …its `disabled` gains `\|\| fairSweepPending` | R-3 |
| :7251 | …its `onPress` becomes `() => handleFindTrades()` (was `track(…) + setPinIdeaResumed(false) + dispatchGenerate({})`) | R-2, R-4 |
| :7443 | Consolidated arm gate: same conjunct | R-1 |
| :7452-7457 | …its `disabled` gains `\|\| fairSweepPending` | R-3 |
| :7667 | `TradeBuildCanvas` mount: `onFindATrade={canvasHost === 'flag' && !fairSweepPending ? handleInlineFindATrade : undefined}` — `InLeagueCalculator:1297` renders that cell `disabled={!onFindATrade}`, so withholding the handler IS its disabled state (no prop added, `InLeagueCalculator.tsx` untouched) | R-3 |

Not changed: any copy string, style token, `testID`, flag, route, event name or payload shape.
`resetDeckForNewTargets` still does not touch the pin store — pins are the user's targets and
the next dispatch reads them out of it (assertion 8f pins this explicitly).

### `mobile/tests/check-results-push.js`

New **§ 8** (18 assertions, `8` and `8a`–`8q`) — see the sabotage table below. One re-spec
inside the existing § 4 (`4f`, dispatch census).

## 2. Declared re-specs (existing pins that encoded the old behavior)

All four are consequences of routing the legacy CTA arm through `handleFindTrades`, plus two
window widths. Each is annotated in place with a dated `#417` note.

| File | Pin | Was → is | Why it is not a weakening |
|---|---|---|---|
| `check-canvas-results.js` | `12a` dispatch census | `dispatchGenerate(` count `9` → `8` (7 routed + definition) | The legacy arm no longer dispatches for itself; it calls `handleFindTrades`, already one of the routed sites. A **new** site still breaks the count |
| `check-results-push.js` | `4f` same census | `9` → `8` | Same; the raw `generateMutation.mutate(` count stays pinned at 1 |
| `check-offer-prefill-330.js` | `S-2` same census | `9` → `8` | Same |
| `check-inline-home.js` | `7f` same census | `9` → `8` | Same |
| `check-analytics-297-302.js` | `#298` emitter census | `find_trades_tapped` call sites `4` → `3` | The legacy arm's inline emitter is gone; its row is now `handleFindTrades`'s no-`source` branch — same name, same `{mode: deckMode}` shape (pinned by the assertion directly above it). A new emitter still breaks the count |
| `check-analytics-297-302.js` | `#298 the legacy-layout CTA sends mode too` | Rewritten to pin the arm's `onPress={() => handleFindTrades()}` **and** the absence of `dispatchGenerate(` in it | The intent — "the legacy CTA's tap still produces a `{mode}` row" — is preserved and strengthened: routing through the entry point is also what gives that arm the #417 reset |
| `check-inline-home.js` | `11b` T-2 CTA gate regex | Accepts an optional `&& !findCtaHiddenForAnchoredDeck` conjunct | `canvasHost !== 'flag'` is still required and still the FIRST conjunct, which is all T-2 was about; `check-results-push.js` § 8a owns the new one |
| `check-inline-home.js` | `3c` `onFindATrade` wiring | Regex updated for the `&& !fairSweepPending` conjunct | The host gate is unchanged and still first |
| `check-inline-home.js` | `3` / `11d` mount slice widths | `900` → `1800`, `1100` → `2000` chars | Mechanical: the mount's prop list grew a comment block and `onLikeTrade` / `hideFormatChips` fell outside the old windows. The assertions themselves are byte-identical |

## 3. Sabotage table — every new assertion proven red, then restored

Harness: apply the sabotage to the working tree, run `node tests/check-results-push.js`, record
which `8*` ids fail, restore the file, re-run and confirm zero failures. Every sabotage restored
green and both mutated files were byte-compared to their originals at the end.

| # | Sabotage | Assertions that went red | Restored green |
|---|---|---|---|
| S1 | per-arm predicates: delete the shared derivation and inline it in both gates | 8, 8a | yes |
| S2 | pre-#417 gate on the consolidated arm (CTA renders on the anchored deck) | 8a | yes |
| S3 | delete the legacy arm's mount instead of gating it | 8b | yes |
| S4 | the receipt's Clear (the anchored deck's search control) is removed | 8c | yes |
| S5 | pre-#417 `handleFindTrades`: no reset on a fair deck | 8d, 8e | yes |
| S6 | the reset runs AFTER the dispatch (epoch kills the search it started) | 8e | yes |
| S7 | the reset also clears the pin store (drops the user's targets) | 8f | yes |
| S8 | `handleSearchAllTrades` dispatches privately instead of through `handleFindTrades` | 8g | yes |
| S9 | the legacy arm goes back to its own `track` + `dispatchGenerate` | 8h, 8i | yes |
| S10 | the sweep never arms the in-flight flag | 8j, 8m | yes |
| S11 | the success exit never disarms (controls stay dead after a good sweep) | 8k, 8m | yes |
| S12 | the failure exit never disarms (a failed sweep bricks the CTA) | 8l, 8m | yes |
| S13 | a third disarm placed AHEAD of the `#330` epoch guard (a dead sweep re-enables a live one's controls) | 8m | yes |
| S14 | a deck reset no longer disarms the flag (a superseded sweep strands a disabled control) | 8n | yes |
| S15 | pre-#417 `disabled` on the consolidated arm (no jobless-sweep guard) | 8o | yes |
| S16 | pre-#417 landing canvas wiring (cell stays live during the sweep) | 8p | yes |
| S17 | #417 grows a feature flag of its own | 8q | yes |

Every id in `{8, 8a…8q}` appears in at least one red column, so no assertion is asleep.
Two assertions were rewritten during authoring after self-review found them tautological
(a `/^[\s\S]*$/` conjunct and an `|| true` tail) — both were replaced with real predicates
(8f now asserts `resetDeckForNewTargets` references no `useFinderTargets`; 8q asserts the
absence of an #417 key in `config/features.json`) and are proven red by S7 and S17.

## 4. Command results (all from the worktree)

| Command | Result |
|---|---|
| `cd mobile && npx tsc --noEmit` | clean, exit 0 |
| `cd mobile && npm run test:results-push` | **70 assertions, all passed** — 23 of them printed by the new § 8 (18 distinct ids; `8c` prints one line per replacement control) |
| all 89 `mobile/tests/check-*.js` suites | **0 red** — including the 32 that mention `TradesScreen`: `check-analytics-297-302` (37 PASS), `check-canvas-results` (151 ✓), `check-inline-home` (71 ✓), `check-offer-prefill-330` (48 PASS), `check-calc-merged-behavior`, `check-single-pin-actions`, `check-shop-deck` (untouched), … |
| `bash mobile/scripts/testid-lint.sh` | `testid-lint OK` |

`backend/tests` not run — no backend file was touched; CI covers it on push.
