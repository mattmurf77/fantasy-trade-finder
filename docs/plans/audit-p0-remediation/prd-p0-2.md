# PRD — P0-2: a failed trade search must be distinguishable from never having searched

> Requirements and acceptance for finding **P0-2** of the 2026-08-09 mobile-UX-audit
> remediation batch. Worktree `ftf-p0-remediation`, branch `p0-remediation-2026-08-10`,
> base `origin/main @ ab9368f`.
>
> **Binding:** [`hld.md`](hld.md) §2 **S-08…S-12**, §3 commit 11, §4 **W2-TS**, §6 rows 5
> and 10, §7 docs rollup, §8 R5/R6/R13, §9 **LLD-2**. Implementation:
> [`lld-p0-2.md`](lld-p0-2.md). Plan: [`plan-p0-2.md`](plan-p0-2.md). Scope block:
> [`scope-p0-2.md`](scope-p0-2.md).
>
> **Class:** Bug, effort S. **Flag:** none — see §7. **Analytics:** none — see §6.

## Contents

- [1. Problem](#1-problem)
- [2. Goal and success statement](#2-goal-and-success-statement)
- [3. Requirements](#3-requirements)
- [4. Copy spec — exact strings](#4-copy-spec--exact-strings)
- [5. Acceptance criteria](#5-acceptance-criteria)
- [6. Non-goals](#6-non-goals)
- [7. Surface changes](#7-surface-changes)
- [8. Docs rows handed to W3-DOCS](#8-docs-rows-handed-to-w3-docs)
- [9. Test plan and ship gate](#9-test-plan-and-ship-gate)
- [10. Rollback](#10-rollback)
- [11. Risks](#11-risks)

---

## 1. Problem

A trade search can fail in three ways, and **all three currently leave the Trades deck slot
on the same card a user sees before they have ever searched**: `trades.empty-text` —
*"Hit \"Find a Trade\" to start"*. The only failure signal is a toast that auto-dismisses
after ~5 s, leaving nothing behind it.

| Path | What fails | What the user is left with today |
|---|---|---|
| **A** | `POST /api/trades/generate` errors (manual tap) | a `warn` toast, then the never-searched card |
| **B** | the job starts, then reports `status: 'error'` during polling | **nothing at all** — `job.error` is read nowhere in the screen |
| **C** | four consecutive poll failures ⇒ the client abandons and clears the job | a `warn` toast, then the never-searched card |

Two consequences, both real:

1. **The user cannot tell "we tried and failed" from "you never searched."** The correct
   next action differs (retry vs. start), and the app gives the same instruction for both.
2. **G-029 — an infinite skeleton.** On a *first run*, path C leaves a
   `SkeletonTradeCard` on screen **forever**: the ladder's `job?.status !== 'error'` guard
   misses because path C sets `job` to `null`, `autoGenFailed` is only ever set from the
   POST path, and the auto-start effect refuses to re-kick. Found during re-verification;
   **strictly worse than the audit's finding** and closed by the same change.

A third, smaller defect travels with this fix: on the Trades screen the toast is pinned at
`top: 32` and overlaps the mode-bar chip row (y ≈ 16…52), clipping "Guided" to "G". The
audit called this a z-order bug; it is a **vertical offset** bug — the toast's `zIndex: 50`
is correct and lowering it would hide the message (HLD §10.6 item 5).

---

## 2. Goal and success statement

**A failed trade search leaves a named, persistent, actionable state in the deck slot,
distinguishable at a glance from every valid empty state, on every failure path.**

Success is the audit's own criterion, met on **both** forced-failure paths, plus the
G-029 addition:

> Force a generation failure and force a poll failure. Each must produce a **distinct,
> named, persistent** state with a **working retry**. Neither may leave a first-run user on
> an unresolving skeleton.

---

## 3. Requirements

### FR-1 — One failure state, three paths

All three failure paths write to a single piece of screen state (`deckFailure`), so the
deck slot has exactly one failure branch. Last write wins.

### FR-2 — Persistent

The failure state persists until the user acts. It is cleared only by: tapping **Find a
Trade** or **Try again**; a successful generate; a league switch; a fairness toggle. It is
**not** time-limited and does not auto-dismiss.

### FR-3 — Named and visually non-confusable

The deck slot renders a `Card` with an uppercase red headline **SEARCH FAILED**
(`semantic.neg`, `#EF4444`), a mapped cause line, and a **Try again** button. Red is the
distinguishing signal: no valid empty state anywhere in the app is red.

### FR-4 — Working retry

**Try again** re-enters the existing `handleFindTrades` entry point and starts a real
search. From the failure state, a retry that succeeds must populate the deck.

### FR-5 — First-run auto-start failure shows the card (HLD **S-08**)

When the silent first-run auto-start fails twice, the deck slot shows the failure card,
not the never-searched card. The app *did* search on the user's behalf and showed a
skeleton; "Hit Find a Trade to start" is false either way, and only the card carries a
retry.

### FR-6 — G-029: no unresolving skeleton

The first-run skeleton branch additionally excludes the failure state. A first-run user
whose polling is abandoned sees the skeleton **replaced by** the failure card.

### FR-7 — `job.error` is mapped, never echoed

The backend's `job.error` is `str(e)` of a server-side Python exception, or the reaper's
literal `"timeout"`. It is mapped to shipped copy (§4) and **never rendered verbatim**.
This is a deliberate, recorded deviation from the audit handoff's "render the backend
message" (`D-026`).

### FR-8 — Partial decks keep their cards (HLD **S-09**)

The failure branch sits **below** the `deck.length > 0` branch, so a job that errors after
banking cards keeps showing the deck. No inline "search stopped early" note is added.

### FR-9 — The toast is unchanged

Existing toast wording, tone, and hold on every path are byte-identical. The card is a new
surface, not a replacement.

### FR-10 — Valid empty states are unchanged

The never-searched card (`trades.empty-text`, its id and its copy), the deck-done summary,
"That's all for now", and the running placeholder are visually and behaviourally
untouched.

### FR-11 — Toast clears the mode bar

On the Trades screen the toast is offset below the mode-bar region so it never overlaps
the chip row. The offset is measured, with a fallback to today's 32 pt when the mode bar
is not mounted or not yet laid out. Every other screen's toast is byte-identical.

### FR-12 — Automated coverage on all three paths

A new Maestro flow forces paths A, B and C and asserts a named persistent state with a
working retry on each. The existing `capture/trades.yaml` — which today asserts the bug —
is updated **in the same commit**.

---

## 4. Copy spec — exact strings

Copy the strings below **byte-for-byte**, including the typographic apostrophe (`’` is
**not** used — these are ASCII `'`) and the em dashes (`—`, U+2014).

| Element | Exact string |
|---|---|
| Card headline (renders uppercase via `type.heading`'s `textTransform`) | `Search failed` |
| Cause — generic (`DECK_FAIL_GENERIC`) | `We couldn't finish that search — the server may still be waking up. Try again.` |
| Cause — network / poll abandoned (`DECK_FAIL_NETWORK`) | `We lost the connection while searching. Your league is fine — try again.` |
| Cause — timeout (`DECK_FAIL_TIMEOUT`) | `That search took too long. The server may still be waking up — try again.` |
| Cause — unverified session (existing shared constant `VERIFY_READS_COPY`) | `Verify your account to view your data.` |
| Retry button label (HLD **S-11**) | `Try again` |

**Which cause line renders when:**

| Path | Condition | String |
|---|---|---|
| A — manual POST fails | verification-required 403 | `VERIFY_READS_COPY` |
| A — manual POST fails | anything else | `DECK_FAIL_GENERIC` |
| A — first-run auto POST fails twice | always | `DECK_FAIL_GENERIC` |
| B — job reports `status:'error'` | `job.error === 'timeout'` (exact match) | `DECK_FAIL_TIMEOUT` |
| B — job reports `status:'error'` | any other value, including `null` | `DECK_FAIL_GENERIC` |
| C — four consecutive poll failures | always | `DECK_FAIL_NETWORK` |

**Unchanged strings** (do not touch): the manual-failure toast `e.message || 'Generate
failed'`; the poll-abandon toast `Network hiccup — try Find a Trade again in a moment`;
`Hit "Find a Trade" to start`; `We'll pull trade ideas from your league and show them one
at a time.`

---

## 5. Acceptance criteria

Each criterion names how it is proven. "Flow" = `trades-generation-failure.yaml`.

| # | Criterion | Proof |
|---|---|---|
| **AC-1** | **Forced POST failure (path A)** produces a persistent card reading **SEARCH FAILED** with a cause line and a **Try again** button; `trades.empty-text` is **not** visible. | Flow leg 5 + manual M-7 |
| **AC-2** | **Forced poll failure (path C)** produces the same named state with `DECK_FAIL_NETWORK`; `trades.empty-text` is **not** visible. | Flow leg 3 + manual M-9 |
| **AC-3** | **Forced job error (path B)** produces the same named state with `DECK_FAIL_TIMEOUT` for `error:"timeout"`. | Flow leg 1 + manual M-8 |
| **AC-4** | **Retry works from every path** — tapping `trades.deck-error.retry` starts a real search that populates the deck (`trades.card-top`). | Flow legs 2, 4, 6 |
| **AC-5** | **The state is persistent** — it survives ≥30 s with no interaction and is not dismissed by the toast fading. | Manual M-13 |
| **AC-6 (G-029)** | **First run + abandoned polling never leaves an infinite skeleton** — the `SkeletonTradeCard` is *replaced by* the failure card. Proven against the **pre-fix control**, where the skeleton persists indefinitely. | Manual M-10, run twice (before and after) |
| **AC-7** | **No valid empty state changed** — never-searched card, deck-done summary, "That's all for now", and the running placeholder are pixel-unchanged and none is red. | `capture/trades.yaml` `empty` leg + screen-library diff + manual M-12 |
| **AC-8** | **`job.error` is never echoed** — no rendered string on any path contains a Python exception fragment or the bare token `timeout`. | Code review of `jobErrorCopy` + flow leg 1 asserts the mapped copy |
| **AC-9** | **The toast no longer overlaps the mode bar** on Trades; the chip labels are fully legible with a toast on screen. | Re-captured `screens/mobile/trades/error.png`, eyeballed (law 23) |
| **AC-10** | **Every other Toast call site is byte-identical.** | `git diff` shows no change outside `Toast.tsx` + the Trades mount; `npx tsc --noEmit` clean |
| **AC-11** | **`capture/trades.yaml` passes against the fix**, and its error leg asserts `trades.deck-error` rather than the never-searched card. | Capture run, tier-1 gate |
| **AC-12** | **Gates green:** `python3 -m pytest backend/tests/ -q`, `cd mobile && npx tsc --noEmit`, `bash mobile/scripts/testid-lint.sh` (exit 0), full 11-flow smoke suite. | W3-QA tier-1 run |

---

## 6. Non-goals

Explicitly out of scope. Each is a decision, not an omission.

| Not doing | Why | Where it went |
|---|---|---|
| **Any analytics event or taxonomy row** | HLD **S-12**. The retry reuses `find_trades_tapped`, whose prop allowlist is `frozenset()` server-side, so `source` is already stripped for the existing `'prefs_changed_strip'` call. Adding the prop is a taxonomy change and belongs on P0-7's commit. | P0-7 addendum "deliberately NOT here" + `NEXT.md` |
| **A partial-deck inline note** ("Search stopped early — 3 trades found") | HLD **S-09**. Additive, not required by the acceptance criterion; the `deck.length > 0` branch already wins, so partial results still render. | Deferred |
| **A feature flag** | HLD **S-10**. Its OFF position would be the bug — the acceptance criterion would be unmet in the default configuration. | §7, §10 |
| **Rendering `job.error` verbatim** | FR-7. It is `str(e)` of a server-side exception. | `D-026` |
| **Changing any toast wording, tone, or hold** | The card is the new surface; widening the diff buys no acceptance. | — |
| **A shared `ErrorState` component** | No shared error-state component exists in `mobile/src` today; the pattern is copy-pasted across six screens. Extracting one inside a P0 bug fix is a refactor with a blast radius of six screens. | `NEXT.md` candidate, not filed by this PRD |
| **Any backend change** | The fix only *reads* `job.error`, which already ships in the job snapshot and is already typed client-side. | — |
| **An `is_linked_platform_league`-style server guard, a route change, or a schema change** | None is touched. This change does not cross the bright line. | — |
| **Renaming `trades.empty-text`** | It keeps its id and its copy — the new state sits *before* it in the ladder; it is not a replacement. | — |
| **Adding a mascot / guide bubble for the failure** | HLD **S-40**: LLD-7 deletes the unused `err.burst` beat in the same commit. One failure, one surface. | LLD-7 |
| **Flipping any flag default** | HLD **S-44**: no flag defaults change anywhere in this build. | — |

---

## 7. Surface changes

**None.** Each surface checked explicitly, per the feature-gate template.

| Surface | Answer |
|---|---|
| Feature flags | **none** — no key added to `config/features.json`, `backend/feature_flags.py` `FLAG_KEYS`, or `backend/tests/fixtures/flags/release.json`. `ux.toast_v2` (already `true`) is read, not modified. **Waiver, explicit:** the flag-gated-remediation convention wants user-visible changes default-OFF; waived because **the OFF state is the bug** (HLD S-10). |
| API routes | **none** — no route added, renamed, or contract-changed. |
| Schema | **none** — no `backend/database.py` edit, no migration. |
| Analytics events | **none** — see §6. |
| Env vars / `model_config` | **none.** No deploy-free knob is added and none is judged necessary: the change is a client-only render branch with no server behaviour, no data write, and no new network call. Rollback is the commit revert (§10). |

---

## 8. Docs rows handed to W3-DOCS

No build agent edits `docs/` or `living-memory/` (HLD §4 wave 3). These are P0-2's rows,
supplied for the wave-3 docs commit. **The ids below are the HLD §7 / §10.4 assignments —
root `CLAUDE.md`'s "next ID" columns are stale.**

| Doc | Row |
|---|---|
| `living-memory/DECISIONS.md` | **`D-026`** — *"A failed trade search renders a named, persistent deck state; `job.error` is mapped, never echoed."* Records the deviation from the handoff's "render the backend message" and why (`str(e)` of a Python exception, or the literal `"timeout"`), and the one-funnel `deckFailure` choice over a render-time read of `job.status` (recency). |
| `living-memory/GOTCHAS.md` | **`G-029`** — *"First run + four failed polls = a `SkeletonTradeCard` that never resolves."* The ladder's first-run branch excludes `job?.status === 'error'`, but the poll-abandon path sets `job` to `null`, so the guard misses; `autoGenFailed` is only set from the POST path; the auto-start effect refuses to re-kick. Closed by the `!deckFailure` guard. |
| `living-memory/NEXT.md` | `source` prop missing from `find_trades_tapped`'s server-side allowlist — generation-failure rate and retry uptake are unmeasurable until it is added (server-side first). |
| `living-memory/CHANGELOG.md` | At ship, in the batch's dated H2: a failed trade search now says so and offers a retry, instead of looking identical to never having searched. |
| `docs/design/components.md` | **n/a because** the doc's § Feedback & status specs Toast's **visual** treatment and the CSS/component it replaces, not any React prop surface; `topOffset` defaults to today's `space.xxl`, so the specced visual is unchanged. *(Resolved by reading the file — this closes the HLD's "verify at build" row.)* |
| `docs/api-reference.md` | **n/a because** no route is added, renamed, removed, or contract-changed. *Optional courtesy half-clause, flagged not required:* the `/api/trades/status` row never mentions the `error` field. |
| `living-memory/LLD.md` | **n/a because** no schema, route, or invariant *convention* shifts — one screen gains local state, one component gains an optional prop. |
| `living-memory/HLD.md`, `docs/architecture.md` | **n/a because** no new module, client, or major flow; no module wiring or data-flow change. |
| `docs/cross-client-invariants.md` | **n/a because** copy and colour are mobile-only; `semantic.neg` is an existing token already used by five Rank screens. Web and the extension are untouched. |
| `docs/glossary.md` | **n/a because** no new domain term — "deck", "job", "retry" are existing vocabulary. |
| `living-memory/DEPENDENCIES.md` | **n/a because** no dependency added, bumped, or removed. |

---

## 9. Test plan and ship gate

### Automated

| # | Check | Expected |
|---|---|---|
| A-1 | `cd mobile && npx tsc --noEmit` | clean (`DeckFailure` + `topOffset?` are the whole type surface). **Never `npm install`** — `mobile/node_modules` is a symlink |
| A-2 | `python3 -m pytest backend/tests/ -q` | clean — regression only, no backend file changes |
| A-3 | `bash mobile/scripts/testid-lint.sh` | exit 0; both new ids are plain literals, no allowlist entry |
| A-4 | `mobile/.maestro/flows/trades-generation-failure.yaml` | all six legs pass |
| A-5 | `mobile/.maestro/capture/trades.yaml` | passes **after** the §9.3 edit; **fails against the fix if left as-is** — which is itself the regression proof |
| A-6 | 11-flow smoke suite | green; `05-trades-render` and `06-trades-deck` cross this surface and are expected unaffected — **verified, not assumed** |

### Manual / simulator

| # | Step | Expected |
|---|---|---|
| M-7 | `fail_next /api/trades/generate 500 count:1`, tap **Find a Trade** | red **SEARCH FAILED** card carrying the mapped copy; **Try again** works; toast no longer covers the mode-bar chips |
| M-8 | `fail_next /api/trades/status* 200 count:1` with an errored job body | card reads the timeout copy; **Try again** succeeds |
| M-9 | `fail_next /api/trades/status* 500 count:4` | card reads the connection copy after ~12 s; **Try again** succeeds |
| M-10 | **G-029, run twice.** Clear state, sign in fresh, force path C on the auto-started job — once on the **unfixed** tree, once on the fixed one | unfixed: skeleton persists indefinitely (record it). Fixed: skeleton is **replaced by** the failure card |
| M-11 | VoiceOver | title and body are reachable in reading order; the retry announces as a button; the failure is not announced twice |
| M-12 | Visual sweep of every deck-slot state | deck-done summary, "That's all for now", and the never-searched card are unchanged, and none is red |
| M-13 | Leave the failure card idle ≥30 s | still on screen; the toast has long since faded |

### Ship gate

**Tier 1** for the batch (HLD §4 wave 3 / §10.5 — the batch contains navigation and screen
changes, so the strictest class governs). Executed by **W3-QA**, not by this finding's
build agent: full smoke suite + all seven new/changed feature flows +
`mobile/scripts/screen-capture.sh --screen trades` + `screen-freshness.sh`. Evidence to
`living-memory/TEST_LEDGER.md` and `qa/sim-runs/last-sim-run.json`, per `docs/runbook.md`
§ Pre-ship simulator gate. Enforced locally by `githooks/pre-push`
(`git config core.hooksPath githooks`).

**Express was not declared.** Full gates apply (root `CLAUDE.md`: agents never self-select
express).

---

## 10. Rollback

**The change is unflagged (HLD S-10), so the rollback lever is the commit, not a toggle.**

- **Unit of rollback:** HLD §3 **commit 11**
  (`P0-2 + P0-8/9: deck failure state, toast offset, s8.1 beat gate, s6.1 swallow fix,
  celebration_shown rename, send-surface plumbing`). Reverting it reverts P0-2 **and**
  P0-8/9 together — they share one file and one commit by design (HLD §8 R6). If P0-2
  alone must come out, the revert is a hand-authored inverse of the P0-2 hunks in
  `TradesScreen.tsx` + `Toast.tsx` + the two Maestro files; the LLD's §1.3 region map is
  the list of what to invert.
- **Blast radius of a revert:** the deck slot returns to the never-searched card on
  failure, G-029 returns, and the toast returns to `top: 32`. No data is written, no
  schema or route changes, so there is **nothing to migrate back** and no server-side
  state to unwind.
- **`capture/trades.yaml` must be reverted with the code.** Its post-fix error leg asserts
  `trades.deck-error`; reverting the code without it leaves a red flow on `main` — the
  mirror image of HLD §8 R5.
- **Client-only:** no Render deploy is involved. A revert reaches users through the next
  EAS build; there is no server behaviour to roll back independently and no window in
  which client and server disagree.
- **Partial rollback of just the toast offset** is available and cheap if the offset ever
  regresses on an unforeseen layout: pass nothing for `topOffset` at the Trades mount and
  the component reverts to `space.xxl` with no other change.

---

## 11. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| `capture/trades.yaml` breaks the moment the fix lands — it asserts the buggy fallback | **certain** | Its edit is mandatory and ships in the same commit (HLD §6 row 10, §8 R5). A pre-fix control run records that it was asserting the bug |
| `TradesScreen.tsx` merge complexity — 6 158 lines, four findings converging | **high** | Single exclusive owner `W2-TS` for the whole wave; LLD §1.3 proves the regions are disjoint; every anchor re-grepped before editing (HLD §8 R1/R6) |
| `deckFailure` sticks after a successful retry, showing an error over a good deck | med | Cleared on tap, on success, on league switch, on fairness toggle — and structurally impossible anyway, because the `deck.length > 0` branch wins over the failure branch |
| Leg-3's `count: 4` injection leaks into leg 4 | med | HLD §8 R13: assert `/__test__/whoami`'s `active_injections` is drained between legs, or re-arm. Decided on-sim and written into the flow header. `INJECT_KIND: reset` is never used mid-flow — it signs the app out |
| A brand-new user sees red on their first screen (FR-5) | low | Adjudicated: HLD **S-08**. The alternative is a card that lies and offers the same button |
| Mode-bar `onLayout` fires late, so the session's first toast uses the 32 pt default | low | Cosmetic and self-correcting on the next render; `warn`/`error` toasts hold ≥5 s under `ux.toast_v2` |
| The `trades_home_inline` experiment swaps the mode bar for a different-height row | low | The `onLayout` wrapper spans the whole branch and measures whichever variant mounted |
| The wrapper `View` changes spacing under the mode bar | low | `modeBarWrap: { gap: space.lg }` replicates the content container's gap, and the wrapper is conditional so "nothing mounted" stays byte-identical (LLD §8.3 / §12.2) |
| `topOffset` ripples to other screens | low | Optional prop, default identical to today's constant; every other call site untouched |
| Generation-failure rate remains unmeasurable, so the finding's load-bearing assumption stays unfalsifiable | low (accepted) | Deliberate — §6. Recorded on `NEXT.md` as a server-side-first taxonomy change |
