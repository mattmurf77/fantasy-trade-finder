# Capture requests — from the mobile UX audit

> For the screen-library / UX documentation agent. Ranked by what it unblocks in the audit, not by effort.
>
> **State of play:** the library is complete and good — 25 screens, 102 captures, release truth, `manifest.json` as the authority. This is not a complaint about the sweep. It is the residue: the block your own sign-off deferred to a separate workstream, plus a handful of states that turned out to be the exact ones an audit finding hangs on.
>
> **Please don't re-capture anything already excluded by ruling** — see §4. Those are correct decisions and I'm not asking to reopen them.

---

## 1. The block your sign-off already authorised but that never landed

Ruling C in [`capture-matrix-signoff.md`](../../../plans/mobile-testing/capture-matrix-signoff.md) authorised two new fixture profiles (`draft`, `espn`) plus three `/__test__` pins, noting that without them *"five screens — draft-room, mock-draft, pick-assignment, record-picks, and LeagueScreen's ESPN branch — get zero coverage,"* and called it **"a P3 backend workstream with its own agent."**

The fixture profiles were built (`c2ba9a1 screens P3-D: draft + espn fixture profiles, determinism pins, flag fixtures`). The captures never landed. Verified 2026-08-10: no PNG matching these names exists anywhere on disk or on any git ref.

> **Reconciled 2026-08-10 — the profiles exist, they're just stranded.** The P0 remediation session independently reported `grep espn backend/tests/fixtures/profiles/*.json` coming back empty and filed it as **Q-017**. Both are true, because the profiles live on **`screen-library-2026-08-09` and were never merged to `origin/main`**:
>
> | Branch | Profiles present |
> |---|---|
> | `origin/main` | `fresh` `near-unlock` `single-format` `standard` `two-leagues` |
> | `screen-library-2026-08-09` | the same five **plus `draft`, `draft-pre`, `espn`, `quickset-done`** |
>
> So this is a merge, not a build. And `quickset-done.json` looks like exactly the profile that produces request **#8** (the 4/4 ring). Landing those four fixtures on `origin/main` plausibly unblocks the two highest-priority items in this document at once, and closes Q-017's ESPN half for the remediation branch's Maestro coverage as a side effect.

| # | Screen dir | Captures today | Notes from the matrix |
|---|---|---|---|
| 1 | `draft-room` | **0** | Registered and reachable; needs the `draft` profile to seed a board, else every state is a notice |
| 2 | `mock-draft` | **0** | Reachable only via the Draft Room's mock entry; needs `draft.mock` + a loaded rookie class |
| 3 | `pick-assignment` | **0** | ESPN-only; needs the `espn` profile |
| 4 | `record-picks` | **0** | ESPN-only **and** requires assigned picks — depends on #3 |
| 5 | `league` — **ESPN branch** | 6 captures, **all Sleeper** | The ESPN variant of League Home is a different render path |
| 6 | `rookie-ranks` | **0** | Matrix rows 73 (`flag-off`) and 74 (`populated`) were authored |
| 7 | `espn-link` sheet | **0** | Sign-off says the sheet steps *are* captured (input / team / done / private-fields) — only the pushed WebView was excluded |

**Why it matters to the audit:** five audit units (Draft Room, Mock Draft, Rookie Ranks, Record Picks, Pick Assignment) are graded **code-only**. Three of them ship flag-ON. I can't make a visual claim about any of them, and the polish-lab convention means nobody can honestly mock them either.

---

## 2. Missing *states* inside screens that are otherwise captured

These are the ones I'd prioritise, because each one is the exact state an audit finding turns on. Small asks against fixtures that mostly already exist.

| # | Screen / state | Why it's needed | Blocks |
|---|---|---|---|
| 8 | `league` — progress ring at **4/4** | Every existing capture shows `0/4`. The finding is that a Quick Set user reaches **4/4 and is still locked** — I can describe it from code but have never seen it. Needs a profile with all four positions tier-saved but `ranking_method` unset. | **P0-1** verification |
| 9 | `matches` — a match card in an **ESPN-linked league** | The finding is that ESPN users get no send action and no explanation. Every match capture is Sleeper, where both Dismiss and Send render. | **P0-6** verification *and* its mockup |
| 10 | `portfolio` — the **single-league gate** | Both captures show the 2-league populated state. The gate is the state the finding is about, and it's what most users will actually hit. | Portfolio brief |
| 11 | `profile` — **populated / flag-on** | Only `flag-off.png` exists ("Public profiles are coming soon"). Nobody has seen the real profile, which is a P2 growth candidate. | Profile brief |
| 12 | `feedback-inbox` | Not captured. `sheets-feedback` is the FAB *capture* sheet — a different surface from the inbox with its severity and lifecycle chips. | Feedback Inbox brief |

**#9 is the one with a dependency chain worth naming.** P0-6 needs a mockup; your own `screens/CLAUDE.md` says a mockup's "current" pane must embed the real capture and must never be redrawn. So: no ESPN capture → no honest mockup → no designed fix. It needs the capture *before* the design work, not after.

---

## 3. Delivered captures that don't show the state their filename implies

Not asking for new coverage — asking whether these are state-misses or whether I'm misreading them. Each was reviewed by an agent that flagged it independently.

| Capture | What it actually shows |
|---|---|
| `trades/locked-gate.png` | No lock UI of any kind — visually identical to `empty.png`. Enabled CTA, no padlock, no gate copy. |
| `matches/progress-module.png` | The empty Mutual Matches state. No progress ring or module visible anywhere on screen. |
| `signin/busy.png` | The Choose-a-League screen, fully loaded. No spinner or busy indicator. |
| `portfolio/populated.png` vs `refreshing.png` | Pixel-identical — same timestamp, same scroll position, no refresh affordance in either. |

If `busy` and `refreshing` are timer states covered by ruling E, that's a fine answer — but then the files existing is confusing, and I'd rather they were absent than present-and-empty. `locked-gate` and `progress-module` look more like the flow didn't reach the state.

---

## 4. Please do **not** capture these — already ruled out, and correctly

Recorded so this request doesn't accidentally reopen settled decisions:

- **Native `Alert` states** (7 matrix rows) — ruling B, OS chrome not app surface.
- **Mid-gesture and timer-only states** (6 rows) — ruling E. This covers the rankings chart's drill-in gray-out, which I listed as a gap in an earlier draft of the audit and have since corrected.
- **SleeperConnect / EspnConnect pushed WebViews** — excluded by the inventory. (The `espn-link` *sheet* steps in §1 #7 are a different thing and were authorised.)
- **TestStages / Placeholder** — excluded as non-product.
- **`TradeFinderHubScreen`** — zero rows, "verified unrouted dead code." The audit reached the same conclusion independently and recommends deleting the file.

---

## 5. Suggested order

1. **#9 ESPN match card** — unblocks a launch blocker *and* its mockup. Highest leverage single capture in this list.
2. **#8 the 4/4 ring** — verifies the highest-severity finding in the audit.
3. **#1–#4 the draft cluster** — five screens currently graded sight-unseen, three shipping flag-ON.
4. **#10–#12** — completes the Tier B briefs.
5. **#3 clarifications** — cheap, and may be answers rather than work.

---

## 6. One thing worth fixing regardless of captures

The capture library is what surfaced this, so it belongs here: **the feedback FAB overlaps content on at least seven screens.** Four independent reviewers hit it. It truncates a mutual match card's button to **"Send in Sleepe"** — the label of the highest-intent action in the product — covers the last player card on Quick Set, and clips a tier chip, a trade-value badge, a leaderboard score and a line of coverage copy elsewhere.

That is a real layout defect, not a capture artifact, and it's tracked as **A-34** in the audit backlog. Flagging it here because the screenshots are the evidence and you're the ones holding them.

---

*Source: independent mobile UX audit, 2026-08-09, against `origin/main @ 72a0770`. Library reviewed at `screen-library-2026-08-09 @ 8091a96`.*
