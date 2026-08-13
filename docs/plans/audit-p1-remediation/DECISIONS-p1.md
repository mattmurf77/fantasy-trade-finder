# P1 Round — Operator Decisions

> Decisions made by the operator during the 2026-08-11 planning round. These are
> binding on any subsequent build. Where a decision contradicts a plan, HLD, LLD or
> PRD written before it, **this file wins** and the affected section is superseded.
>
> Superseded entries are kept, struck through in place, with the reason — so the
> reasoning trail survives rather than being quietly rewritten.

---

## Table of Contents
- [D-P1-01 — P1-11 dropped: "Acquire" stays](#d-p1-01--p1-11-dropped-acquire-stays)
- [D-P1-02 — ~~P1-7 fixes the anchor lane only~~ SUPERSEDED by D-P1-10](#d-p1-02--p1-7-fixes-the-anchor-lane-only-superseded-by-d-p1-10)
- [D-P1-03 — invite event name (ASSUMED)](#d-p1-03--invite-event-name-assumed)
- [D-P1-04 — Invite CTA ships on both surfaces](#d-p1-04--invite-cta-ships-on-both-surfaces)
- [D-P1-05 — Push gate and bucket are one decision](#d-p1-05--push-gate-and-bucket-are-one-decision)
- [D-P1-06 — Privacy policy: in-repo draft, dated note](#d-p1-06--privacy-policy-in-repo-draft-dated-note)
- [D-P1-07 — Accept live-on-merge; split-flag pattern to backlog](#d-p1-07--accept-live-on-merge-split-flag-pattern-to-backlog)
- [D-P1-08 — Test gates relaxed; TestFlight is primary QA](#d-p1-08--test-gates-relaxed-testflight-is-primary-qa)
- [D-P1-09 — Analytics: quarantine unknown events, classify by field](#d-p1-09--analytics-quarantine-unknown-events-classify-by-field)
- [D-P1-10 — Every ranking method must unlock; manual folded in](#d-p1-10--every-ranking-method-must-unlock-manual-folded-in)
- [D-P1-11 — P0 has merged; the round's base is stale](#d-p1-11--p0-has-merged-the-rounds-base-is-stale)
- [Still open](#still-open)

---

## D-P1-01 — P1-11 dropped: "Acquire" stays

**Decided 2026-08-11. Operator: keep "Acquire". P1-11 is removed from the round.**

The audit (A-20) and `plan-p1-11.md` both rest on the premise that #245's rationale for
"Acquire" — a tab covering more than trades — was undercut by #246 removing the
free-agency hub. **That premise is wrong.**

Verified at `ab9368f`: #246 unrouted the *launcher hub screen*, not the free-agent
finder. The FA destination survives as a chip in `TradeFinderModeBar.tsx:44`; the Draft
Room joined the same strip on 2026-08-06; `Calc` pushes the Manual Calculator. The tab
is an umbrella over four functional areas, so renaming it "Trades" would name an
umbrella after one of its own children. Also verified: there is **no user-visible
"Trades" label anywhere in `mobile/src`** — the word exists only as a route name,
testID and analytics value.

**Consequences.** `plan-p1-11.md` / `scope-p1-11.md` retained as history, superseded.
Two observations from them remain true and are kept for P0's sake: P0-7's conflict
matrix rows for `TabNav.tsx` and `LeagueScreen.tsx` are stale, and
`screens/manifest.json:55` under-reports capture staleness.

**Carried forward, not dropped:** the ASO argument. "Acquire" is not a term anyone
searches the App Store for — that belongs in the listing title, subtitle and keyword
field, owned by `mkt-aso`, filed against the first public release.

**Lesson for the next audit:** the audit reasoned from a commit message ("hub removed")
to a UI conclusion ("the tab now only does trades") without checking whether the
destinations survived. Same family as A-33 — the artifact described intent, the code
held the truth.

---

## D-P1-02 — ~~P1-7 fixes the anchor lane only~~ SUPERSEDED by D-P1-10

**Decided 2026-08-11, superseded the same day.**

~~The manual lane is not a priority; P1-7 fixes anchors only, and the manual-lane lock
is recorded as a known accepted condition.~~

**Superseded because the premise changed.** This decision was made on the understanding
that the manual-lane lock was a *pre-existing* gap being declined. It is not: the P0
batch **introduces** it, by adding `_note_ranking_method(sess, "manual")` to
`reorder_rankings`, which pins manual-first users to `'manual'` and drops them through
to the trio rule. P0 has since merged (see [D-P1-11](#d-p1-11--p0-has-merged-the-rounds-base-is-stale)),
so the regression is live in production now. See [D-P1-10](#d-p1-10--every-ranking-method-must-unlock-manual-folded-in).

---

## D-P1-03 — invite event name (ASSUMED)

**Not explicitly decided. Proceeding on the low-risk default; overturnable.**

`HLD-p1.md` §AN-3: `invite_shared` (what the code fires and P0-3 registered) vs
`invite_sent` (the written tracking plan). **Assumption in force: keep
`invite_shared`**, and amend the tracking plan to match runtime.

Renaming requires a coordinated edit in two places landing together; if they desync the
event drops silently behind a 200. Cheap to reverse at document level, expensive after
the taxonomy registration commit lands.

---

## D-P1-04 — Invite CTA ships on both surfaces

**Decided 2026-08-11. Operator: ship both, verify on TestFlight personally.**

`HLD-p1.md` §H OG-12 found the Matches empty state has **no scroll container**, so the
promoted invite block lands inside an already-clipped region. Consequences, accepted
knowingly:

1. The CTA may not be reachable on smaller devices.
2. `assertVisible` structurally cannot detect the failure.
3. **`invite_cta_shown{matches_empty}` is a mount counter, not an impression.**

**Required of the build:** the PRD must state plainly that the Matches-surface
impression metric is unreliable until the clipping is fixed, so it is not later read as
a real impression rate. The League Home surface is unaffected and its metric is sound.

---

## D-P1-05 — Push gate and bucket are one decision

**Decided 2026-08-11.** Gate: **counterparty intent only** — a leaguemate's like whose
mirror is actionable on the user's roster. Never a model score. Bucket: **`trade_matches`**
(default ON for anyone who granted push).

**The coupling is binding:** bucket strength and gate strength are one decision. If the
gate is ever widened to model-scored candidates, the kind **must** move to
`reengagement` in the same change. Record in `DECISIONS.md` at build time.

Adds `SettingsScreen` copy and a `PushPrimingModal` consent bullet to the diff.

---

## D-P1-06 — Privacy policy: in-repo draft, dated note

**Decided 2026-08-11.** Draft via the in-repo `/legal-privacy` skill, with a dated
header note in `web/privacy.html` recording that professional legal review did not
happen.

Unchanged: **no build agent merges final policy text unreviewed**, and the policy
update ships in the **same commit** as the flag flip, so collection can never go live
against a stale policy.

---

## D-P1-07 — Accept live-on-merge; split-flag pattern to backlog

**Decided 2026-08-11.** `HLD-p1.md` §E RL-1: **accept** that the share work is live the
moment it merges. No new flag this round.

**The generalisation the operator drew, for the backlog — not this round:** feature
flags should be able to disable *front-end access* to a feature independently of
*back-end support* for it. The share work is the illustrating case: `growth.share_landing`
gates the **server routes** (`server.py:16838` mint, `:16881` landing, `:16904` preview
image — all 404 when off), so flipping it off to roll back would **break every link
already shared**, including ones sitting in other people's message threads. The flag is
therefore not a usable rollback lever; rollback here means a revert commit.

Operator note: in practice feature flags have not been used to roll back, so the split
is a pattern to adopt deliberately rather than a gap to close now.

**Consequence for PV-5:** gating the tier-share affordance on `growth.share_landing`
inherits the same coupling. Acceptable under this decision, but the affordance gate and
the route gate are the same switch — record it so it is not mistaken for a clean lever.

---

## D-P1-08 — Test gates relaxed; TestFlight is primary QA

**Decided 2026-08-11. This is a standing change, not a one-round exception.**

The simulator/Maestro/screenshot apparatus costs more than it returns: it consumes
significant budget on nice-to-haves rather than critical paths, and its quality has
degraded as the feature surface grew. **TestFlight is the primary QA method going
forward.** The original hope — automating the UI bugs the operator finds by hand — has
not paid for itself.

**Immediate effect on this round:**

| Item | Disposition |
|---|---|
| **RL-13** — re-shoot all tab-stack screenshots | **Dropped.** Was the round's largest single cost item |
| **RL-10** — Sleeper Connect Maestro flow | **Dropped** (not deferred) |
| **RL-11** — testID rename | **Dropped** — was conditional on RL-10 |
| **RL-9** — `anchors-done` seed fixture | **KEPT.** Different cost profile: a backend fixture, not a UI test, and the absence of exactly this fixture is why the anchor bug survived to the audit |

**Required doc changes** (otherwise every future session re-derives the old requirement
and the cost is paid again elsewhere):

- Root `CLAUDE.md` — the "Maestro delta" feature gate is no longer mandatory for every
  user-visible mobile change. Rewrite it to describe TestFlight as primary QA, with
  Maestro optional where it is cheap and load-bearing.
- Root `CLAUDE.md` — the pre-ship simulator gate and `githooks/pre-push` enforcement
  relax accordingly.
- `docs/runbook.md` § Pre-ship simulator gate — update the tier matrix to match.

**Trade-off recorded honestly:** this round's own evidence is that missing fixtures let
bugs survive (RL-9's rationale, and A-16 generally). The decision accepts a higher rate
of UI regressions reaching TestFlight in exchange for the budget the apparatus consumes.
That is an operator call about where their own time is best spent.

---

## D-P1-09 — Analytics: quarantine unknown events, classify by field

**Decided 2026-08-11. A new workstream, not part of the P1 build.**

**Problem.** `ALLOWED_CLIENT_EVENTS` is default-deny and silent: an unregistered event
is dropped, and the client is told the request succeeded. Data not captured is
unrecoverable. The mock-draft failure — 100% of users unable to pick, for two days —
produced no signal but two typed feedback reports.

**Decision, two parts:**

1. **Quarantine, don't drop.** Unknown event names are accepted and stored in a raw
   table. They **never** touch any metric until classified. An admin view surfaces them
   ("seen but unclassified — N this week"), so a new name arriving is a *signal* rather
   than silence. Storing and counting are separated deliberately: admitting unknown
   events straight into the metric store would let a client-side typo silently restate
   DAU.
2. **Classification as a field, not a deny-list.** Today `NON_INTENT_EVENTS` is a
   separate roster of exclusions, which **fails open** — forget an entry and the event
   silently counts. A required classification field on the event definition **fails
   closed**: an event cannot be registered without declaring its kind.

**Ordering:** after the P1 taxonomy registration commit (operator confirmed T1 goes
first). It does not retire T1 for this round — the wall behaves as it behaves today —
but it retires that ceremony for everything after it, which matters given how many
workstreams currently queue on one file.

**Knock-on:** the queued mock-draft instrumentation shrinks. With quarantine in place,
its urgent half disappears — those events would land whether or not anyone registered
them in time.

---

## D-P1-10 — Every ranking method must unlock; manual folded in

**Decided 2026-08-11. Supersedes [D-P1-02](#d-p1-02--p1-7-fixes-the-anchor-lane-only-superseded-by-d-p1-10).**

**Governing principle: every ranking method must be able to unlock trades.** No method
may be a dead end.

**Scope change:** P1-7 fixes **both** the anchor lane and the manual lane. The earlier
decision to fix anchors only rested on the manual lock being a pre-existing gap. It is
not — P0 introduced it, and P0 has merged, so a cohort that unlocked fine last week no
longer does.

**Required of the build:**
- The `anchor` branch, as specced in `LLD-p1-7.md` (threshold 40, derived labels,
  anti-divergence test) — unchanged.
- A manual-lane fix in the same pass. `LLD-p1-7.md` names `_tiers_rule()` as the shared
  seam; the evidence rule for manual is **not** specced in any document in this round
  and must be designed before build.
- Both verified against the **post-P0 code**, not the `ab9368f` base the LLD was
  written against.

**Note:** the audit's original P1-8 framing was "manual unlocks *too easily* on one
chooser tap." Post-P0 the failure inverts to "manual cannot unlock at all." The fix must
address the live behaviour, not the audit's description of it.

---

## D-P1-11 — P0 has merged; the round's base is stale

**Established 2026-08-11 by direct verification, not assumption.**

`origin/main` is at `53bd19f`. The P0 batch merged (`716c2b7`, "commit 15/15, sim gate
skipped by operator") and its worktree was swept (`1d20208`). The feedback #297–302
batch **also** merged (`f8acd71`, v1.12.1) carrying its own analytics changes.

**The P1 planning base `ab9368f` is 23 commits behind**, and the drift lands squarely on
the files this round claims:

| File | Δ since `ab9368f` |
|---|---|
| `backend/analytics_taxonomy.py` | +238 |
| `backend/server.py` | +259 |
| `mobile/src/screens/TradesScreen.tsx` | +537 |
| `mobile/src/navigation/RootNav.tsx` | +79 |
| `mobile/src/screens/LeagueScreen.tsx` | +66 |
| `mobile/src/screens/SettingsScreen.tsx` | −109 net (extraction) |
| `mobile/src/screens/MatchesScreen.tsx` | +7 |

**Consequences:**

1. Every "Re-verify after P0 merge" section in all six LLDs is now **live work**, not a
   contingency. Nothing gets built until its item's section is walked.
2. **T1's contents are stale.** `analytics_taxonomy.py` grew by 238 lines across two
   merges; the registration commit must be recomputed against `53bd19f`, not designed
   from the LLDs as written.
3. The worktree must be rebased onto `origin/main` before any build.
4. `mobile/node_modules` in the P1 worktree is a symlink to a **stale** install
   (2026-07-27; six `package.json` commits since). Replace with `npm ci` in the worktree
   before any build or typecheck.

---

## D-P1-12 — Ranking/tier-board sharing is not a product surface

**Decided 2026-08-11. Operator: sharing of rankings must not be live in any form.**

This goes further than any option offered in `HLD-p1.md` §E PV-5.

**Verified state on `origin/main` @ `53bd19f`** — the operator's recollection that this
was already disabled is **incorrect**, and the exposure is live:

| Route | Guard |
|---|---|
| `server.py:16833` `/og/tiers/<pos>/<username>.png` | **none** |
| `server.py:16929` `/s/tiers/<pos>/<username>` | **none** |
| `server.py:16838/:16881/:16904` (package routes) | `is_enabled("growth.share_landing")` |

What *was* disabled is the public **profile** surface (`profiles.public_pages`,
`profiles.user_toggle`, and #221 hiding the Settings row). Different surface. Any
username's rankings image is fetchable today by URL guess, with no in-app link required.

**Consequences:**
1. **P1-2 loses its tier half.** Linking the tiers landing from the tier-board completion
   state is cancelled. Only the trade-package half of P1-1/2 proceeds.
2. **`tier_board_shared` is not registered** — remove it from T1's contents. `AN-4` now
   covers two events, not three.
3. **PR-12 is moot** (landing on the shared position) — cancelled, not deferred.
4. **The routes themselves should be taken down or gated off**, and that is not P1 work
   sequenced behind a build — it is live exposure. Raise separately and immediately.

---

## D-P1-13 — Operator decisions, batch of 2026-08-11

Recorded from operator review of the decision sheet. Unless noted, the recommendation in
`HLD-p1.md` §E stands as accepted.

| ID | Decision | Note |
|---|---|---|
| **RL-1** | Accept live-on-merge | Per [D-P1-07](#d-p1-07--accept-live-on-merge-split-flag-pattern-to-backlog) |
| **PR-11** | Fix both share paths | |
| **PR-12** | **Cancelled** | Superseded by [D-P1-12](#d-p1-12--rankingtier-board-sharing-is-not-a-product-surface) — no board sharing at all |
| **PR-14** | Fall back to the simple link when picks are present | **Follow-up required:** the rich landing page's inability to render picks is a real gap to fix properly later, not permanently |
| **PV-5** | Superseded | See [D-P1-12](#d-p1-12--rankingtier-board-sharing-is-not-a-product-surface) |
| **OG-1** | Mint the share link **on tap** | |
| **AN-4** | `calc_trade_shared` INTENT; `share_package_created` NON_INTENT | `tier_board_shared` **dropped** per D-P1-12 |
| **PR-13** | *Not explicitly answered.* Default stands: leave it | Flag if wrong |
| **PR-15** | Fix the landing/image fairness mismatch later | |
| **PV-1** | **Skip the probe.** Not worth validating — the user base is 3–5 people, so backfill urgency is moot either way | Deviates from the recommendation, on grounds the recommendation didn't have |
| **PV-2** | Flip via `config/features.json`, paired with the policy commit | |
| **PV-6** | Describe the current state truthfully; promise no unsubscribe | |
| **PV-7** | Capture on now; App Store label at next submission | |
| **AN-6** | Skip the `email_captured` event | |
| **PR-5** | Factual framing | **Copy direction:** emphasise that trade suggestions get better and trade activity rises as leaguemates join — the user's direct incentive to invite |
| **PR-6** | **Reversed from the recommendation.** Invite leads on the Matches empty state | **Refinement:** make it conditional on league penetration — **under 50% joined ⇒ invite leads; 50%+ ⇒ "Find a trade" leads.** The aggregate needed for this is already on `/api/league/summary` |
| **PR-7** | **Recommendation withdrawn — unverified** | See [D-P1-14](#d-p1-14--pr-7s-premise-is-unverified) |
| **PR-8** | Hide the existing inline invite link when the card renders | |
| **PR-9** | Include the members-overlay invite button | |
| **PR-10** | Hide the card when everyone has joined | |
| **OG-13** | Demote the invite button; the existing primary keeps precedence | |
| **AN-3** | Keep `invite_shared`; correct the tracking plan | [D-P1-03](#d-p1-03--invite-event-name-assumed) promoted from assumption to decision |
| **AN-5** | Add `invite_cta_tapped` | |
| **AN-8** | Ship one copy variant; no A/B | |

---

## D-P1-14 — PR-7's premise is unverified

**Established 2026-08-11.** `plan-p1-5.md` and `HLD-p1.md` §E PR-7 assert that invite
links cannot resolve for non-Sleeper leagues, citing P0-3 D4, and recommend withholding
the promoted invite card on those leagues. **That assertion is not supported by the code
that was checked.**

On `origin/main` @ `53bd19f`:

- `InviteLeaguematesBanner.tsx:56` `buildInviteUrl(leagueId, username)` emits
  `?league=<id>` (or the flagged `/app/league/join/<id>`). **No platform branch.**
- `LeagueJoinScreen.tsx` contains no platform-conditional logic.

The link is a plain URL; nothing prevents sharing it via Discord, Telegram or anywhere
else, as the operator noted. **If a constraint exists it is on the resolve/join side and
must be traced before any gate is designed around it.**

**Provenance note:** this claim reached the operator as fact after passing from a P0
planning document, through the P1-5 planning agent, into the HLD and the decision sheet
— without anyone reading the URL builder. Same failure class as A-33.

---

## New workstreams raised during review

- **Email re-engagement stream.** Capture addresses from users who *don't* complete
  onboarding, then re-engage them — including telling them how many of their leaguemates
  have since joined. Pairs directly with the PR-5 incentive framing. Depends on
  [D-P1-09](#d-p1-09--analytics-quarantine-unknown-events-classify-by-field)-era
  infrastructure and on email capture (P1-3) being live. **Backlog.**
- **Split feature flags: front-end access vs back-end support.** See
  [D-P1-07](#d-p1-07--accept-live-on-merge-split-flag-pattern-to-backlog). **Backlog.**
- **Rich landing page: render draft picks.** Follow-up to PR-14's fallback. **Backlog.**
- **Take down or gate the tier-board routes.** Live exposure — not backlog. See
  [D-P1-12](#d-p1-12--rankingtier-board-sharing-is-not-a-product-surface).

---

## Still open

- **`HLD-p1.md` §E** — the remaining decisions not resolved above, less the items
  dropped by [D-P1-08](#d-p1-08--test-gates-relaxed-testflight-is-primary-qa) and
  [D-P1-01](#d-p1-01--p1-11-dropped-acquire-stays).
- **The five marked "before T1"** — AN-1, AN-3, AN-4, AN-5, PR-9. Cheap now, a second
  verified deployment later.
- **The manual-lane evidence rule** ([D-P1-10](#d-p1-10--every-ranking-method-must-unlock-manual-folded-in))
  — no document in this round specifies it.
