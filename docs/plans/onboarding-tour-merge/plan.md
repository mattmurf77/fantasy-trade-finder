# One tour, not two — merging new-user onboarding with the calculator walkthrough

**Status: PLANNING — nothing here is built.** Source: [Segrave's notes, 2026-08-23](notes-2026-08-23-segrave.md), plus the operator's framing: *"I want to merge that walkthrough with this one once we merge the manual calc with the current trade finder page."*

The short version: about a third of Segrave's notes are **already fixed** by the W7/W8 tour work that shipped in v1.16.1/1.16.2 — but only for the calculator tour's beats, not the new-user onboarding beats, which is exactly the disjointedness the notes describe. Another third is **small copy/flag work**. The remaining third — multi-platform landing, auto-running the first search, and the merge itself — is real design work with operator decisions attached. They are listed in §4.

---

## 1 · What exists today: two tours sharing one engine

One overlay (`mobile/src/components/AnalystGuide.tsx`, mounted once in RootNav), one step store (`mobile/src/state/useGuide.ts`), one copy table (`mobile/src/components/analystScript.ts`). On top of that engine sit **two different control styles**:

| | New-user onboarding | Calculator tour (#384) |
|---|---|---|
| Beats | `s0.1`–`s8.1` (v1 spine) + `n1`–`n9` (v2 singles) | `n10`–`n18` (calculator) + `n19`–`n24` (deck) |
| Who sequences them | **Nobody** — each screen requests its beat when its own trigger fires (sign-in mount, league pick, first swipe, first like…) | **A runner** — `mobile/src/utils/calcTour.ts` owns order, park/resume across screens, the interrupt hold, and a completion receipt |
| Advance style | Mostly `tap` (invisible full-screen catcher) or `action` | `cta` — every talk beat has a **Next/Done button** (W7, device report 6) |
| Re-runnable | No | Yes — "Show me around" resets its display caps |

The calc runner is the newer, better machine. The merge is substantially "put the onboarding beats under a runner like that one, with W7's button rules."

## 2 · Note-by-note disposition

**Sizes:** S = copy/flag/one-file · M = a real change with tests · L = design + multi-file build.

| # | Segrave's note | What's true in the code today | Disposition | Size |
|---|---|---|---|---|
| 1 | Launch page is Sleeper-only; offer Sleeper/ESPN/MFL | `SignInScreen` is Apple-primary/Sleeper-fallback (`auth.accounts`); `onboarding.landing` makes Sleeper primary. ESPN/MFL league linking exists **only after sign-in**, via `LeaguePicker`'s footer sheets (`EspnLinkSheet`, `PlatformLinkSheet`) | New work. The link flows exist and are live in release (D-026) — the work is hoisting entry points onto the landing screen and letting a session begin from a non-Sleeper league. See research answer §5.2 — ESPN/MFL **cannot** do Sleeper-style username lookup, so the landing offers three *different* inputs, not one field | **L** |
| 2 | Remove the demo-league link | Flag `landing.try_before_sync` — currently **true**; "Try the demo" calls `/api/session/demo` | Flag off (config-only, hot-reload) now; delete the code path in the build wave. Only the landing link dies — `TestStagesScreen`'s operator tooling is separate | **S** |
| 3 | Pop-ups only exit via tiny top-right ✕; add a prominent Next to every no-action prompt | Already the LAW for calc beats (W7: `n12`–`n16` are `advance:'cta'` with Next). Onboarding talk beats still advance by **invisible tap-anywhere catcher** (`s0.1`, `s2.1`, `s5.0/s5.1`, `s8.1`, `n1`, the error beats — `guide.tap-catcher` in `AnalystGuide.tsx`), which reads as "✕ is the only way out" and swallows scroll (the W7 report-5 bug, still live on these beats) | Convert every onboarding **talk** beat to `cta` + Next, same as W7 did for the calculator. `action` beats (type username, pick league, swipe) rightly keep the real action as the advance | **S–M** |
| 4 | Initial message should say we'll walk you through | `s0.1`: "I'm The Analyst. I model dynasty trades — you bring the roster." — no walkthrough promise | Copy change, plus a Next button per #3 | **S** |
| 5 | Second pop-up (account entry) should offer all three platforms | `s0.2` points at `signin.username-input`: "Type your Sleeper username. No password needed." | Follows #1's design; the beat splits per platform path | with #1 |
| 6 | League selection is fine as-is | `s1.1`, `advance:'action'` — picking a league advances | No change | — |
| 7 | "Reading rosters, finding a trade" copy runs but nothing happens; auto-click Find a Trade on first landing | True: `s2.wait` says "…scoring candidate trades. First cards land in seconds," but `TradesScreen` waits for the user's tap. (First-run pregen exists — `SkeletonTradeCard` under `onboarding.trades_first` — but it does not dispatch the search) | Keep the copy, auto-dispatch the guided first search through the existing #330 choke point, gated on: first run, guided flow active, no completion receipt, verified-enough session. One new gate, not a new path | **M** |
| 8 | Trade presentation copy should explain provenance (consensus + your rankings) | `n1` already says exactly this ("These prices are the market's. Your swipes are already teaching me yours") but fires **once, at the third disposition**; `s2.1` (the first card beat) says "a market," provenance-free, and is tap-advance | Rework `s2.1`'s copy to carry the provenance line up front (+ Next per #3); keep `n1` as the deepener | **S** |
| 9 | Ending is abrupt ("swipe left or right" … stop); merge with the calculator walkthrough | True: the spine ends at `s8.1` ("That's the tour…") or fizzles at `s2.2`. The "more comprehensive flow on the manual calculator page" is the #384 tour — runner-owned, buttoned, re-runnable, receipt-gated | The centerpiece — proposal in §3, decision in §4 | **M–L** |
| 10 | After accept: kill the "they haven't seen it — send in Sleeper?" CTA; confirm queued instead; invite if leaguemate absent | The CTA is `n6.1` (routable variant): "Logged — they haven't seen it yet. Send it to them now?" → send surface. **Honesty bound in the code comment:** a one-sided like creates no notification and no row on their side — "queued for their review" must not imply they were pinged | Replace `n6.1`-routable with a queued confirmation ("Logged on your side — they'll see it when they're in the app"), and when the counterparty has no board/account, the invite moment — `inviteSocialProof` already governs invite-CTA honesty on three surfaces. Note: `growth.invite_join_link` is **false** today; the invite moment either lights it or uses the share-link rung | **M** |

## 3 · The merged tour — proposed spine

One runner (generalize `calcTour.ts`'s pattern: ordered beats, park/resume across screens, one interrupt hold, one receipt, refuse-when-capped), one spine:

```
Landing (multi-platform)        s0.1 (rewritten: "I'll walk you through it") → per-platform entry
League picked                   s1.1 (unchanged)
Deck, first landing             s2.wait  → AUTO-DISPATCHED first search (#7)
First cards                     s2.1 (provenance copy, Next) → s2.2 (swipe teach, action)
First like                      n6.1' — queued confirmation; invite moment if counterparty absent
Bridge (the new ending)         "Want to build one by hand? I'll show you the calculator →"
Calculator half                 n10 → n18 (exists, shipped, verified)
Find a Trade hand-off           park → deck half n19 → n24 (exists)
Sign-off                        s8.1 (rewritten to land as an ending, not a shrug)
```

What this keeps, closes, and leaves alone:

- **Keep:** the calc tour n10–n24 verbatim (it is the machine the notes praise); `s1.1`; the S4 Quick-Set walk as an *optional side quest*, not spine.
- **Close:** the deprecated builders `s2.3` and `s6.1` (already marked `@deprecated`); the demo link (#2); `n6.1`-routable's send push (#10).
- **Leave event-driven (not spine):** the ranking pitch (`s3.2`, `s5.x`, `n8`) — it triggers off swipes and board state, and forcing it into a fixed sequence would show it before the user has felt consensus prices be wrong.
- The bridge answers Segrave's open question the way their own note leans: **stop at the first trade, then offer to continue** — the deck IS the end state; the calculator half is one CTA away, and "Show me around" remains the re-entry forever after.

## 4 · Decisions for the operator (the plan waits on none of them except D1/D2 for build order)

1. **What does "merge the manual calc with the current trade finder page" mean concretely?** Today the calculator is its own push off TradesHome (D-151: "fine as its own tab for now"). If the calculator is to become an inline region of the trade-finder page, the tour merge should be built *after* that layout lands (beats point at targets; moving targets twice is waste). If D-151 stands for now, the tour merge can be built immediately against the current layout.
2. **Bridge-or-spine:** §3 proposes the tour *stops at the first trade* and offers continuation into the calculator half (Segrave's open question, answered "stop + offer"). The alternative — one mandatory walk through everything — is more cohesive but longer, and every added mandatory beat costs completion rate.
3. **Auto-dispatching the first search (#7)** spends a model generation for every new guided user without a tap. That is the copy finally telling the truth, but it is also cost + a verification question (unverified sessions 403 on generation today — the auto-run must skip, not error, there).
4. **The invite moment (#10)** needs `growth.invite_join_link` lit, or it degrades to the share-link. Lighting it is its own small rollout decision.
5. **Multi-platform landing (#1)** is the largest piece and is separable — everything else in this plan works with today's Sleeper-first landing. Recommend it ships as its own wave.

## 5 · Research answers (from the codebase, not speculation)

**5.1 · Tour length** — answered in §3/§4.2: stop at first trade, offer continuation, keep "Show me around" as permanent re-entry.

**5.2 · Multi-platform account lookup.** Sleeper's username→leagues lookup is unique among our platforms. From the shipped link flows:

| Platform | What entry requires today | Username/email lookup? |
|---|---|---|
| Sleeper | username only (`/api/session` path) | **Yes** — that's the whole trick |
| ESPN | league id or URL; private leagues additionally need `espn_s2`/`SWID` via cookie paste or the `EspnConnectScreen` WebView login (`espn.webview_capture`) | **No** — ESPN's API has no public user→leagues lookup; identity comes from cookies |
| MFL | league id (`PlatformLinkSheet`); optional MFL sign-in (`mfl.auth_link`, `POST /api/mfl/auth-link`) unlocks franchise binding + writes. MFL's API can list a *signed-in* user's leagues | **Sign-in only** — no anonymous lookup |
| Fleaflicker | dark (`fleaflicker.link` false) | out of scope |

Consequence for the landing design: three platform tiles, three different second steps — Sleeper asks a username; ESPN asks a league URL (public) with "private league? sign in" escalation; MFL asks league id *or* sign-in-and-pick. There is no honest single-input version.

**5.3 · Still to capture:** Segrave owes notes on the manual-calculator experience itself; slot them into §2 when they land.

## 6 · What this plan does NOT touch

The trade engine, the fairness sweep (D-153), the ✓ queue contract (D-152), Team Review, the ranking surfaces, and the calc tour's shipped mechanics (W7/W8) — the merge *consumes* them. All Chalkline/analytics/flag gates apply at build time per the standard four gates; each wave gets its own scope block then.

## 7 · Suggested build order

| Wave | Contents | Size |
|---|---|---|
| A — "stop the bleeding" | #2 flag-off · #3 Next buttons on onboarding talk beats · #4 + #8 copy | S, one PR |
| B — the merge | runner generalization · bridge beat · #7 auto-dispatch · #10 queued-confirmation + invite moment · rewritten `s8.1` | M/L |
| C — multi-platform landing | #1/#5 per §5.2, its own scope block | L |

Wave A is shippable this week and fixes everything Segrave could feel in five minutes of use. Wave B is the actual merge. Wave C is separable and should not block A or B.
