# G419 mobile build evidence

2026-09-06 · implementation owner · runtime/guard commit `396d92fc`.
Base `741710c1` includes the independently reviewed backend contract and approved
R4/T7 specification. This is local code/test evidence, not physical-device or
release verification. See [mobile code walk](mobile-code-walk.md).

## Delivered boundary

The current mobile session records locally acknowledged exact passes across
stacked Trades screens and remounts. It projects that record over every retained
working-deck render, using the actual acted package, counterparty, account and
league. Structured reason evidence commits only when `passed === true`; a
successful ordinary swipe retains its existing acknowledgement semantics without
claiming verified durable persistence. Held Undo does not commit. Total write
failure restores retryability, including a removed browse row. An open layer-2
episode keeps its card until its existing advance/dismiss transition.

Remote-only invalidation of an already retained append-only deck remains HELD.
This change does not infer a pass from a missing card in a server snapshot, create
a durable local ban, redesign acceptance, or alter market/personal-value policy.

## Recorded checks

Commands ran from `mobile/` under Node 24.14.1 using the existing lockfile and
installed dependencies. No dependency, package-script or lockfile edit belongs
to this commit; root owns integration of the new script registration.

| Check | Result |
|---|---|
| `node tests/check-trade-disposition.js` | **28 passed, 0 failed** on `396d92fc`. |
| Every `tests/check-*.js` via a Node `spawnSync` loop | **94 scripts passed, 0 failed**, 13.452 seconds, on `396d92fc`. This includes the new guard and all existing decline, canvas, browse, Undo, failure-recovery and shop guards. |
| `npx tsc --noEmit` | Passed, exit 0, on `396d92fc`. |
| `bash scripts/testid-lint.sh` | `testid-lint OK`, exit 0, on `396d92fc`. |
| `git diff --check` | Passed before runtime commit. |
| `FTF_TRADE_DISPOSITION_BASELINE=4026ebc8 node tests/check-trade-disposition.js` | **0 passed, 4 expected behavioral failures**, exit 1; unchanged original-runtime RED described below. |

The guard transpiles and executes the real production helper and API adapter.
It also extracts and executes the actual screen's shared subscription bus,
reason observer, cursor setter, browse remove/restore/advance functions and
swipe-error callback. Assertions at the remaining React seams are explicitly
wiring checks, not a mounted React Native integration test.

The 28 cases cover exact oriented identity and negative boundaries; edited versus
raw package; new card IDs and same-length/restored/reordered decks; current and
behind-cursor commitment; layer-2 no-skip; forward/backward and bounds; shared
session/remount publication; account/league A→B→A stale callbacks; independent
reason/swipe settlement; total-failure retry; late verified reason suppressing
rollback; actual failure after newer actions or reordered/later deck positions;
browse middle/last removal and retry restoration; pre-single-pin cursor wiring;
four progressive requests; and held-Undo's no-write path.

## Honest RED → GREEN

The baseline mode reads `4026ebc8` with `git show`; it does not alter source files,
disable production code, or require the new helper in the old revision. Four
assertions execute valid old production code and fail for the intended reasons:

1. The old reason adapter returns `true` for `{ok:true, passed:false}` instead of
   preserving the structured evidence.
2. The old adapter omits the actual edited give-side context from the payload.
3. The old adapter does not expose verified `passed:true` as structured evidence.
4. The old lane projection retains exact passed P alongside Q when Q alone is
   expected; no local committed-pass projection exists in that implementation.

The same applicable behavior assertions pass with the new implementation. The
broader state/callback cases run only against the new real production seams.
Early harness authoring mistakes were corrected and are not counted as RED
evidence. Named source-sabotage testing was **not run**, per root's explicit
instruction to use unchanged-baseline behavior after the earlier mutation was
denied. No denied action was retried through another mechanism.

## Narrow oracle correction and scope accounting

Only one existing structural oracle changed: `check-shop-deck.js` cs1 recognizes
the same deck-reset effect with `[leagueId, userId]` instead of `[leagueId]`.
It still requires deck and chooser clearing; account replacement now has the
same protection as league replacement. Root approved that exact structural
transition. No other existing guard or behavioral expectation was weakened.

Runtime files: `TradesScreen.tsx`, `api/declineReasons.ts`, and the new small
dependency-free `utils/tradeDisposition.ts`. The new guard and the two owned
evidence documents complete this subtask. No edits to API client, session store,
Win Now, global docs, version, package file, backend, schema, flags, analytics
event/property names, strings, designer components or native configuration.

Browse failure restoration is the bounded implementation refinement: the old
rollback searched for a row already spliced out of the working set, so it could
not make that failed pass retryable. The attempt now retains a removal receipt
until settlement. A failed attempt restores that row once; successful sibling
evidence prevents restoration. The reason wait is detached from the mutation
lifecycle so next-card controls are not held pending by the separate request.

## Manual acceptance — NOT RUN

Use controlled accounts/league and record device build and backend revision.
No real fantasy-platform proposal is needed.

- Layer 1, every layer-2 completion and dismissal: card stays usable while the
  reason panel is open; completion fronts the immediate next card once. Repeat
  on the last browse row and with earlier locally masked rows.
- Pass, change lanes, Find more, return/back from a stacked results screen,
  restore a single-pin source deck, and receive a regenerated ID/same-length
  snapshot: the exact locally committed package does not re-front. A different
  package or counterparty still can.
- Edit a package, then pass: the existing edited ID and actual assets are echoed
  and masked. The original unedited package is not excluded by raw ID alone.
- Controlled verified reason `passed:true` plus companion swipe failure: no
  rollback or misleading failure toast. Repeat with a late true sibling and a
  later false/missing refinement.
- Both writes fail, or reason is banked without verified pass and swipe fails:
  retry uses normal controls. In browse, the removed row returns once without
  corrupting sibling order/tally. A newer action must not be undone by an older
  failure callback.
- With reason capture off and Undo enabled, Undo during the existing hold window:
  no pass request/history row and no committed local mask; the card remains
  actionable. After the hold, normal commitment behavior applies.
- Switch account/league A→B→A with writes in flight: late callbacks do not mutate
  the new scope's cursor, reason panel, guard, toast or mask.

Maestro, simulator, native captures, physical-device checks, TestFlight upload,
GitHub push and production mutations were not performed by this mobile subtask.
Backend bank→repair without a companion swipe is covered by the separately
reviewed backend tests; this mobile guard does not claim to execute a real DB
repair or prove remote-only retained-deck invalidation.
