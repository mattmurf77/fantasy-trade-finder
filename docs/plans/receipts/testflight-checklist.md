# Receipts — manual TestFlight checklist (operator)

**Date:** 2026-08-21 · **Source:** [PRD.md](PRD.md) §8.3, expanded for the build ·
**Who runs it:** the operator, on a TestFlight build.

Under [D-056](../../../living-memory/DECISIONS.md) the simulator and Maestro are retired, so
**this is the only runtime evidence Receipts gets.** The pytest suite (54 tests) and the
structural check (`npm run test:receipts`, 12 checks) cover shape and math; nothing
automated has ever seen this screen render on a device.

Run it **before** flipping `receipts.screen`, and record the outcome in
`living-memory/TEST_LEDGER.md`.

---

## Before you start

Flags are flipped in `config/features.json`, then `POST /api/feature-flags/reload` — no
deploy needed.

| Step | Command / action |
|---|---|
| 0a | `receipts.grading` → `true`, reload flags. Confirm with `POST /api/cron/receipts-grade` (X-Cron-Secret) → expect **202** with `remaining_resolvable` > 0 on the first run. |
| 0b | Drain the backlog: `python3 scripts/receipts_backfill.py` (add `--batch 1000` if it is large). It stops on **two consecutive zero-work runs**. |
| 0c | `GET /api/admin/receipts/metrics` (X-Cron-Secret) → sanity-check `n`, the Wilson intervals, and `effective_window` before any user sees a number. **This is the A-2 checkpoint: a bad number changes COPY, never the cohort, window or metric.** |
| 0d | Only then set `receipts.screen` → `true` and reload. |

---

## The checks

Each step names what a failure would mean, so a "looks fine" is a real pass.

- [ ] **1 — Fresh league, no grades yet.** Entry point ("Track record") is visible on the
      Trades home utility row. The screen shows the **maturity/ledger state**: a tracked
      count, the date tracking started, and an ETA — **and no percentage anywhere**.
      *A number here would be the first debunkable claim we ship.*

- [ ] **2 — Your own league, post-backfill.** Headline shows a win share **with its n**
      ("17 of 30 suggestions…"), all three window chips render, and 56d shows
      `pending`/`insufficient` rather than being blank or hidden.
      *A hidden window is how a three-window payload becomes a one-window screen.*

- [ ] **3 — Row detail.** Every row shows **both sides** with serve values and per-window
      deltas. Find at least one **negative-edge row** and confirm it renders in exactly the
      same layout as a positive one — same size, same position, no de-emphasis.
      *If losses render smaller or lower, this stopped being a track record.*

- [ ] **4 — Pick row.** A row containing a draft pick shows the picks-held-flat note.
      *Picks are delta 0 because their prices are our own commits; the note is why the row's
      edge looks small.*

- [ ] **5 — Best AND worst call.** Both markers are present, or neither is.
      *A best call without a worst call is banned copy (PRD §4.4).*

- [ ] **6 — Window chips.** Tapping 14D / 56D changes the numbers **instantly with no
      loading spinner and no network request** — same cohort, different window.
      *A refetch here means the client could request one window, which is the mechanism the
      whole design exists to prevent.*

- [ ] **7 — Ghost check.** Scan the rows: every trade shown is one you actually saw on a
      deck. No card you never saw appears.
      *Ghosts are excluded at both the queue and the route layer (operator ruling
      2026-08-21); a ghost row on screen means both failed.*

- [ ] **8 — Flag off.** Set `receipts.screen` → `false`, reload flags, reload the app.
      The entry point is **gone**, and there is no error dialog, no empty screen, no crash.
      *An error state here means a dark feature is visible to users.*

- [ ] **9 — FeedbackFAB.** With the flag back on: the FAB is present on Receipts, and there
      is **no double FAB** on the Trades tab.
      *Receipts is a root-stack push, so it carries its own FAB; a second one on a tab
      screen is the #196/#197 bug.*

- [ ] **10 — Error path.** Kill connectivity and open Receipts. You get the retry state, and
      the **FeedbackFAB is still present**.
      *The user hitting an error is the one most likely to have something to report.*

- [ ] **11 — Dark mode + Dynamic Type.** Cycle appearance and bump text size to the largest
      accessibility setting. Numbers stay readable and nothing clips; deltas carry a **sign
      glyph** (`+` / `−` / `±`), so meaning survives without colour.

- [ ] **12 — Copy review against the banned list (PRD §4.4).** Read every string on screen
      and confirm none of these appear: an acquire-side percentage standing alone; any
      aggregate without its n; the word "accuracy"; "right"/"wrong" for graded/ungraded; a
      best call without a worst call.

---

## Recording the result

In `living-memory/TEST_LEDGER.md`, add a dated entry naming the build, which steps passed,
and any step that failed with what you saw. If step 2's numbers look bad, that is an **A-2
framing decision, not a filtering one** — the pre-commitment is on the record: copy may
change, the cohort, window and metric may not.
