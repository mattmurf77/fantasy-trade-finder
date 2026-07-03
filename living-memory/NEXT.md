# Next — Fantasy Trade Finder

> **Purpose:** forward priority queue. 3–7 items, ordered, each with a one-line *why now*.
>
> **Read at:** session start, after CHANGELOG and HANDOFF. **Write at:** when something finishes or priorities shift.
>
> Companion files: [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) for items blocked on external input; [`CHANGELOG.md`](CHANGELOG.md) for what was done.

---

## Table of Contents
- [2026-06-10 — Priority Queue](#2026-06-10--priority-queue)
- [Queue Hygiene Rules](#queue-hygiene-rules)

---

## 2026-06-10 — Priority Queue

*(Refreshed after the trade-engine v2/v3 ship: PR #86 → main → Render live, TestFlight build 14. The 2026-05-21 queue was fully overtaken — iPhone app shipped, pytest baseline exists (125 tests), dup DB archived, Render Starter live.)*

### Immediate

1. **Q-005 — recruit 1–2 league-mates for the real-match validation.** *(operator action)*
   *Why now:* the two-sided match loop is unproven with real people; pre-season trade churn is the window. In-app invite nudges shipped 2026-06-10 (mobile banner + web coverage button).

2. **Watch `/api/admin/engine-metrics` as real usage lands.**
   *Why now:* fairness_threshold / package_adj_gamma tuning is blocked on like/match-rate data by basis and deck position. Endpoint shipped 2026-06-10; check it each session once league-mates start swiping.

### Near-term

3. **Bump iOS marketing version off 1.0.0 before the next build.**
   *Why now:* eas.json uses `appVersionSource=remote`, so app.json bumps don't apply. Run `eas build:version:set` before the next `eas build` (operator or with operator present).

4. **Tune engine thresholds once metrics show signal.**
   *Why now:* deferred-by-design at ship time (~20 swipe labels). Revisit the learned acceptance model when trade_impressions volume supports it; Thompson sampling covers the interim.

### Medium-term

5. **FB-47 — standalone needs-based trade finder.** Operator request (feedback id 47): pick a player/position to move or acquire → rank league rosters by positional strength → target the weakest/strongest counterparties. Overlaps the shipped consensus-basis cards + pinned-give flow; the genuinely new piece is positional-strength counterparty targeting (`analyze_roster_strengths` already computes the inputs). Needs scoping before build.

6. **3-team trades client UI** — held by operator decision (2026-06-10) until 2-team matches prove out. Backend is live behind `trade.three_team=false`.

7. **FantasyCalc value-source experiment** — deferred by operator (2026-06-10): keep DynastyProcess seeds; revisit behind a flag only if telemetry shows fairness-calibration complaints. API is free/keyless (no published license — courtesy-contact maintainer if commercializing).

### Reserved

- **Browser-extension Chrome Web Store submission.** Decide distribution strategy first (Q-008).
- **Mascot naming (Q-009)** — branding, no code dependency.

---

## Queue Hygiene Rules
- **Cap at 7 active items.** If you'd be adding an 8th, archive an old one or move it to "Reserved."
- **Each item has a clear *why now*.** Not a wish-list; an actionable next step.
- **Time-horizon labels** ("Immediate / Near-term / Medium-term") make commitment level explicit.
- **"Reserved" items have prerequisites** — note them.
- **After completing an item,** move it to [`CHANGELOG.md`](CHANGELOG.md) with the date and outcome; don't leave checkmarks here.
