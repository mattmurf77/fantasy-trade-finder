# The notification list as a growth surface

> **Role:** pm-growth. **Date:** 2026-08-12.
> **Verified against:** `origin/main` @ `4a4b671` (post P1-remediation release v1.13.2).
> **Trigger:** operator reaction to P1-9's in-app inbox row — *"we should also use that
> notification list for other things we want users to do: invite league members, rank
> players every so often, inform them of new league members that have joined the app."*
> **Companions:** [`../../plans/audit-p1-remediation/PRD-p1-9.md`](../../plans/audit-p1-remediation/PRD-p1-9.md),
> [`../../plans/audit-p1-remediation/DECISIONS-p1.md`](../../plans/audit-p1-remediation/DECISIONS-p1.md).
> **This document changes no source file.** Specs and recommendations only.

## Contents

- [1. Question & context](#1-question--context)
- [2. Evidence](#2-evidence)
- [3. Loop / channel analysis](#3-loop--channel-analysis)
- [4. Options considered](#4-options-considered)
- [5. Recommendation & experiment backlog](#5-recommendation--experiment-backlog)
- [6. Riskiest assumption & cheapest test](#6-riskiest-assumption--cheapest-test)
- [7. Decisions needed](#7-decisions-needed)
- [8. Handoffs](#8-handoffs)

---

## 1. Question & context

**The question:** the bell inbox is about to gain its first deliberately-designed row
(P1-9's `trade_found`). Before it calcifies around one event type, what is this surface
*for*, what earns a slot in it, and how is it ordered, capped, emptied and measured?

**The decision it feeds:** P1-9 is next in the build queue and nothing about it has been
built. Whatever shape the inbox row takes there becomes the pattern every later row copies.
This is the cheap moment to set the rules.

**The reframe that organises everything below.** The inbox today is an **event log** —
four types, all of them records of something that already happened to you. The operator's
three seeds are **prompts** — things we would like you to go do. Those are different
objects. An event log is trusted because everything in it is news; a prompt list is
tolerated at best. Mixing them without a rule turns the log into the prompt list, because
prompts are always available and news isn't. **The thing worth protecting here is that
opening the bell is currently always worth it.**

---

## 2. Evidence

Everything in §2.1–§2.3 is **measured from code** at `origin/main` @ `4a4b671` and cited.
Everything labelled *assumed* is unmeasured — the bell has zero instrumentation (§2.2 M11),
so there is no usage data about this surface of any kind, and there never has been.

### 2.1 What the inbox actually is today

| | |
|---|---|
| **Types that exist** | Four: `trade_match`, `trade_accepted`, `trade_declined` (`backend/database.py:812-820`), and `referral_joined` (`backend/server.py:15036-15044`) |
| **Who writes them** | Five call sites total — `create_notification` at `backend/server.py:10298`, `:10307`, `:13290`, `:13299`, and `push_notification` at `:15036` |
| **Storage** | `notifications_table` (`backend/database.py:822-831`) — `id, user_id, type, title, body, metadata_json, is_read, created_at`. No priority column, no expiry column, no dismissed column |
| **Read API** | `GET /api/notifications` (`backend/server.py:15362`) → `get_notifications` (`backend/database.py:8721`): **all unread + the 20 most recent read, `created_at DESC`** |
| **Mobile render** | `TopBar.tsx` — `ROW_GLYPHS` (`:65-72`) knows 6 keys, everything else falls to a grey bell; rows tappable only behind `notif.tap_routing_v2` (**on**) via `resolveNotificationTarget` (`deepLinks.ts:280`) |
| **Web render** | A **second, independent** glyph map (`web/js/app.js:4676`) knowing 3 types, and a second tap router (`:4830`) routing the same 3. Everything else: grey bell, inert tap |

### 2.2 Eleven verified mechanics that shape the design

These are the constraints. Each one either kills a design or forces a choice.

| # | Mechanic | Why it matters here |
|---|---|---|
| **M1** | **`_send_typed_push` does not write an inbox row.** The dispatcher (`backend/server.py:15625-15694`) does prefs → bucket → cap → quiet hours → Expo fan-out → `notification_events_log` + `push_sent`. It never calls `create_notification`. | **11 of the 14 typed push kinds leave no inbox trace at all.** The inbox is not a push mirror and never has been. P1-9's paired row is a *new pattern*, not an existing one. |
| **M2** | **Opening the bell marks everything read** — `markAllRead()` plus a server-side `markAllNotificationsRead()` on `openSheet` (`TopBar.tsx:120-140`). | A prompt is consumed by a *glance*, not by an action. Nothing can persist by staying unread. |
| **M3** | **Ordering is `created_at DESC` and nothing else.** No priority, no pinning (`backend/database.py:8721-8750`). | A prompt competes with a receipt on recency alone. The newest row wins, whatever it is. |
| **M4** | **"Clear all" is local-only on mobile.** `clear()` empties a Zustand store (`useNotifications.ts:78`); the server rows survive; the next `openSheet` re-hydrates them (`TopBar.tsx:126-135`). **Verified: dismissed rows come back.** | Today that's a cosmetic annoyance about old receipts. The moment prompts live here it is a broken promise — the user dismisses a nag and it returns. |
| **M5** | **Web has a dismissal mechanism mobile lacks** — `ftf_dismissed_notifs` in `localStorage` (`web/js/app.js:4629-4637`), per-browser, server rows untouched. | Two clients, two different dismissal semantics, neither server-backed. Any prompt design has to pick one. |
| **M6** | **Two of the three seeds already exist as live push kinds.** `league_member_joined` (`backend/server.py:15069`) and `league_member_unlocked_trades` (`:6395`), both in the `trade_matches` bucket — **default ON** (`backend/database.py:10085-10093`) — both dedup-capped (`:15671-15682`). | Seed #3 is mostly plumbing, not a new feature. The push already fires; it just leaves no trace anyone can find later. |
| **M7** | **The re-rank seed also already exists, and reaches nobody.** `finish_ranking` (`backend/server.py:16380`) sits in the `reengagement` bucket, which `notif.reengagement_default_off` (**true**) forces to `0` for any user without a stored pref row (`backend/database.py:10108-10125`). | Same trap that makes `deck_replenished` reach zero users (PRD-p1-9 §1). Any re-rank prompt routed to `reengagement` is dead on arrival. |
| **M8** | **There is no invite notification of any kind.** Zero push kinds, zero inbox types. The invite loop is entirely in-screen: four surfaces behind a **closed** `InviteSurface` enum (`InviteLeaguematesBanner.tsx:66-71`). | Seed #1 is genuinely new surface — and the enum is a registered analytics prop domain, so a fifth surface is a taxonomy change, not just a new string. |
| **M9** | **`referral_joined` is a dead-end row.** Written and live (`backend/server.py:15036`), but absent from `ROW_GLYPHS` → grey bell, and absent from every `V2_*` kind set (`deepLinks.ts:255-269`) → `resolveNotificationTarget` returns `null` → **tap does nothing**. Web: same. | The single most motivating row this product can show — *your invite worked* — currently renders as an anonymous grey bell you cannot tap. |
| **M10** | **Analytics is default-deny and silent.** Unregistered names are dropped behind a 200; `INTENT_EVENTS` is derived by subtraction (`analytics_queries.py:140`), so a passive event not added to `NON_INTENT_EVENTS` in the same commit permanently inflates DAU/WAU. | Every event below must be registered *before* its emitter, with its classification decided in the same commit. |
| **M11** | **`TopBar.tsx` contains zero `track()` calls.** | The bell has never been measured. Open rate, tap rate, per-type tap rate: all unknown, all unknowable retroactively. **Any decision about which rows earn a slot is currently a guess, and will stay one until this is fixed.** |

### 2.3 What the three seeds actually cost

| Seed | Status today | Real cost |
|---|---|---|
| **Inform them of new league members** | **Already pushes**, default-ON bucket, dedup-capped (M6) | Add `create_notification` beside two existing `_send_typed_push` calls + 2 `ROW_GLYPHS` entries. Routing already exists — both kinds are in `V2_LEAGUE_KINDS` (`deepLinks.ts:261-263`) |
| **Rank players every so often** | A first-completion nudge exists (`finish_ranking`) and reaches nobody (M7). A *periodic* re-rank prompt does not exist | Needs a trigger that isn't a calendar (§3.1). The trigger design is the whole job; the row is trivial |
| **Invite league members** | No notification presence at all (M8). Four in-screen surfaces, all shipped in P1-5 | New row type, new glyph, new routing entry, and an extension to a closed analytics enum |

**One more fact the message flagged and I confirmed:** `invite_shared`'s `league_id` scrubbing
was fixed at `9674439` on `origin/main`. Per-league invite analysis is possible from that
commit forward, and **only** forward — there is no back-history.

---

## 3. Loop / channel analysis

### 3.1 One rule decides most of this: the trigger decides the channel

P1-9's standing principle is that a push must be triggered by **another human's revealed
intent**, never a model score. Generalise it one step and it resolves the push-vs-inbox
question for every candidate without another argument:

> **If the trigger is another human's action → push-worthy.
> If the trigger is the user's own state, or a calendar → inbox-only.**

This is not a compromise, it is what makes the two channels different things. Push
interrupts you because someone else did something you'd want to know. The inbox is where
you find out what the *product* noticed. Applied honestly it means:

- The re-rank prompt is **inbox-only**, by its own nature. It is re-engagement; it is
  triggered by your state; it does not get to interrupt anyone. This also routes around
  M7 entirely — there is no bucket to be trapped in, because there is no push.
- The invite prompt is **inbox-only**, same reasoning.
- `referral_joined` and the two league-member kinds are **push-worthy** — all three are
  another human's action.

**A sequencing benefit falls out of this, and it is the most useful thing in this
document:** inbox rows are not pushes. They are not gated by prefs, buckets, quiet hours,
OS permission, or the operator-only push allowlist. **The entire growth surface can ship to
every user while push stays operator-only.** Nothing here waits on the push rollout.

### 3.2 The slot test

> **A row earns a slot when it carries information the user does not have and could not
> get by opening the app.**

That is the same bar as P1-9's gate, stated for the inbox. It is what a "three mediocre
pushes a day" failure looks like when it happens quietly, inside the app, to a list
nobody complains about — they just stop tapping the bell.

The test's teeth: **a prompt that is true for every user every day fails.** "Invite your
league" is true forever, so it is not news. "Three of your twelve leaguemates have joined
— trades get better as more do" is a fact about *this* user's league that changed, so it
is. The difference is a precondition on real state.

### 3.3 Candidate ledger

Three classes, and the class sets the rules.

- **R — Receipts.** Something happened involving another human. Always earns a slot, never
  counts against a prompt budget. These are why the bell is worth opening.
- **S — Social proof.** Something happened in your league that isn't about you. Earns a
  slot, but **coalesces** — three joins in a week is one row, not three.
- **P — Prompts.** We want you to do something. Earns a slot only on a real precondition,
  hard-capped, and never more than one live at a time.

| Candidate | Class | Verdict | Reasoning |
|---|---|---|---|
| **Someone joined via your invite** (`referral_joined`) | R | **Ship first.** Fix the glyph + routing; add push | The payoff of the only growth action we ask users to take, currently rendered as an untappable grey bell (M9). Cheapest real win on this list — a `ROW_GLYPHS` entry and a `V2_*` set entry |
| **A leaguemate unlocked trades** (`league_member_unlocked_trades`) | S | **Ship.** Add inbox row | Stronger than "joined": a *ranked* counterparty is what the matching engine needs. This row is the moment the product got better for you |
| **A leaguemate joined the app** (`league_member_joined`) | S | **Ship.** Add inbox row, coalesced | Already pushes (M6); leaves no trace. Coalesce so a five-person onboarding wave is one row |
| **Your deck was replenished** (`deck_replenished`) | S | **Ship the inbox row. Leave the push exactly as it is** | It fires weekly and reaches **zero** users (PRD-p1-9 §1). An inbox row reaches everyone at zero push cost and zero bucket risk. Free fix for a dead feature |
| **`trade_found`** (P1-9) | R | **Ship as specced** | Already designed. This document changes nothing about it |
| **Counter-offer received** (`counter_offer`) | R | **Ship.** Add inbox row | Pushes today, no trace. Pure receipt |
| **Match expiring** (`match_expiring`) | R | **Ship.** Add inbox row | Same |
| **Re-rank because your roster changed** | P | **Conditional yes — needs a feasibility check** | The honest version: *"Your roster changed — 3 players you haven't ranked."* Event-driven, names a real state, decays. **Blocked on whether league sync exposes a usable roster diff** — route to eng-backend before speccing |
| **Re-rank on a schedule** | P | **No** | A calendar trigger is exactly what P1-9's problem statement condemns. It is the `deck_replenished` mistake with a different noun |
| **Invite your leaguemates** (as a *row*) | P | **No — put it in the empty state instead** (§3.4) | Five surfaces already ask (M8). A sixth, in the one place that's currently all news, is how you teach someone to stop opening the bell |
| **A player on your roster moved in value** | P | **No** | Model-driven. Fails the trigger rule outright, and it is the highest-volume noise source available — precisely the thing to keep out |
| **Your sent trade was viewed / responded to** | R | **Backlog** | Strong receipt. Depends on the platform send lifecycle (`trade_responded` exists for MFL only). Revisit when send-in-* is general |
| **A new league appeared on your Sleeper account** | S | **Backlog** | Real multi-league expansion signal, but needs a sync-diff we may not have |

**Net for v1: six inbox rows, all of them receipts or social proof, zero prompt rows.**
That is a deliberate outcome and worth stating plainly: the exercise asked whether the
inbox could carry prompts, and the honest answer for a product with 3–5 users and an
uninstrumented bell is *earn the surface first*. Six new rows make the bell worth opening.
Prompts spend that credit. Spend it after there is some.

### 3.4 The empty state is the most-viewed state, and it is where the invite goes

With 3–5 users and a low event rate, most bell opens today land on *"You're all caught up
/ Trade matches and other alerts will appear here"* (`TopBar.tsx:307-313`). That is the
highest-traffic pixel on this surface (**assumed** — M11 means it is unmeasured), and it
currently does nothing.

**Recommendation: the invite ask lives in the empty state, not as a row, and only when
penetration is low.** Reuse the rule the operator already decided and that already shipped
on `MatchesScreen.tsx:431-437` (D-P1-13 PR-6): **under 50% of leaguemates joined ⇒ invite
leads; at 50%+ ⇒ no invite ask.** `inviteSocialProof(total, joined)` already exists and is
already wired to `/api/league/summary`.

Why this beats a prompt row, in one line each:

- It appears **only when there is nothing to bury** — structurally incapable of pushing a
  receipt down.
- It disappears the moment the surface has content, which is the moment the ask stops
  being the most useful thing there.
- It carries a **real precondition** (this league's actual penetration), so it passes the
  slot test that a standing "invite your league" row fails.
- It reuses a shipped, operator-approved rule rather than inventing a second one.
- Copy follows the PR-5 direction the operator already set: *trade suggestions get better
  and trade activity rises as leaguemates join* — the user's own incentive, not ours.

At 50%+ penetration the empty state should say what would fill it, which teaches the loop
without asking for anything: *"Nothing yet. You'll hear when leaguemates rank players,
match a trade, or join."*

### 3.5 Where each loop breaks today

| Loop | Path | Break |
|---|---|---|
| **Invite → join → density → matches** | User shares → leaguemate installs → `invited_by` → `referral_joined` row | **Breaks at the receipt.** The inviter's reward is an untappable grey bell (M9). The one moment that would motivate a second invite is wasted |
| **Leaguemate joins → I notice → I trade** | `league_member_joined` push fires | **Breaks after the banner.** No inbox row, so a missed or quiet-hours-bundled push is gone forever (M1) |
| **Board freshness → suggestion quality → WAT** | `finish_ranking` push | **Breaks at the bucket.** `reengagement` + `notif.reengagement_default_off` = zero recipients (M7) |
| **Deck refresh → return visit → WAT** | Weekly `deck_replenished` push | **Same break, same cause.** Fires weekly to nobody |
| **Any of the above → learning** | — | **Breaks at measurement.** Zero `track()` calls in the bell (M11) |

Four of five breaks are in the *last mile* of loops that already work. That is why the
recommendation is mostly plumbing.

---

## 4. Options considered

### 4.1 Ordering and caps

| | Option | Verdict |
|---|---|---|
| **A** | **Recency-only (today's behaviour), noise controlled purely by what gets written.** No schema change. Enforce a written rule: at most one Class-P row live per user, ever | **Recommended for v1.** With six receipt/social rows and zero prompt rows, recency is honest — every row is news, so newest-first is correct ordering. Costs nothing |
| **B** | **Add `priority` + `expires_at` columns; sort receipts above prompts; expire prompts server-side** | **Deferred, with a named trigger.** Correct design, real cost: schema change, two client renderers (M5), and it is only needed once prompts exist. **Revisit the day the first Class-P row is approved** — not before, and not later |
| **C** | **A separate "for you" section pinned above the feed** | **Rejected.** Two lists in one sheet, on a surface with no measured usage. Solves a crowding problem that six rows a month do not create |

**The honest caveat on A**, stated so it isn't discovered later: unread rows never age out
(`get_notifications` returns *all* unread), and read rows only fall out past 20. At this
product's event volume a row will sit in the list for weeks. That is fine for receipts —
a month-old *"@dave joined your league"* is still true. It is **not** fine for prompts,
which is a second, independent reason prompts wait for option B.

### 4.2 The dismissal gap (M4)

| | Option | Verdict |
|---|---|---|
| **A** | Wire "Clear all" to a server-side dismiss (new column or a bulk `is_read` + client filter) | **Recommended.** Small, and it makes the surface honest. Also closes the mobile/web divergence (M5) |
| **B** | Rename the button to "Mark all read" | Cheaper and truthful, but leaves the user with no way to clear a list that only grows |
| **C** | Leave it | **Not viable if prompts ever ship.** Tolerable for six receipt rows; a trust bug the moment anything asks for something |

**Recommend A.** If it doesn't fit the P1-9 build, B is an acceptable holding position and
A becomes a prerequisite of the first prompt row.

### 4.3 Should the invite ask be a row after all?

Argued honestly, because the operator named it first. **The case for:** the bell is
persistent, cross-screen, and the four in-screen CTAs are all on screens a low-penetration
user may rarely reach. **The case against:** M8 shows five asks already exist; the bell is
the only surface where every item is currently news; and a standing invite row fails the
slot test by construction. **Middle option if the operator wants it:** a **single lifetime**
invite row, fired once, at a moment of demonstrated need (first empty deck, or first
matches-empty with penetration under 50%) — a receipt-shaped prompt, capped at one forever.
That is defensible. A recurring one is not.

---

## 5. Recommendation & experiment backlog

### 5.1 Recommended v1 — "earn the surface"

**Phase 1 — inbox rows only. No push change. Ships to everyone, independent of the
operator-only push allowlist.**

| # | Change | Cost |
|---|---|---|
| 1 | `referral_joined`: add `ROW_GLYPHS` entry + add to a `V2_*` kind set so the tap routes (League tab) | 2 lines mobile, 2 lines web |
| 2 | Write inbox rows beside the existing pushes for `league_member_joined`, `league_member_unlocked_trades`, `counter_offer`, `match_expiring`, `deck_replenished` | 5 × `create_notification` next to an existing `_send_typed_push` |
| 3 | Glyphs + routing for all five new types, **both clients** (M5 — web is a separate map) | ~10 lines each side |
| 4 | Coalesce `league_member_joined` within a rolling window (one row per league per day) | Small; the dedup-key machinery already exists |
| 5 | **Instrument the bell** (§5.2) — `notif_inbox_opened`, `notif_row_tapped`, `notif_empty_state_shown` | The non-negotiable item |
| 6 | Empty state: explain what fills it; carry the invite action **only** when penetration < 50%, reusing `inviteSocialProof` | Reuses shipped logic |
| 7 | Fix "Clear all" (§4.2 option A) | Small |

**Phase 2 — push, operator-only.** Per the operator's new rollout policy, *all* push goes
to the operator's device first. `referral_joined` gains a push at this point; the two
league-member kinds already have one. Nothing else gains a push.

**Phase 3 — prompts, only if phase 1 earns it.** Gate: `notif_row_tapped` shows the bell
is used. Prerequisites: option B ordering (§4.1) and the dismissal fix. First prompt
candidate is the **roster-changed re-rank**, if eng-backend confirms a roster diff exists.

### 5.2 Instrumentation — register before any emitter (M10)

| Event | Class | Props | Why it exists |
|---|---|---|---|
| `notif_inbox_opened` | **NON_INTENT** | `unread_count`, `row_count` | Navigation-class, same family as `tab_selected`. Denominator for everything else. **Must be in `NON_INTENT_EVENTS` in the same commit** or it step-changes DAU |
| `notif_row_tapped` | **INTENT** | `type`, `position`, `age_hours` | **The one number that decides which rows earn a slot.** Without `type`, this whole exercise repeats in six months on the same absence of evidence |
| `notif_empty_state_shown` | **NON_INTENT** | `not_joined`, `total_mates`, `invite_offered` | Sizes the surface's most-viewed state and tells us whether the penetration gate ever opens |
| `invite_shared` / `invite_cta_shown` / `invite_cta_tapped` | unchanged | **add `notif_empty` to the closed `surface` enum** | M8 — the enum is a registered prop domain. Extending it is a taxonomy edit that must land before the client change |

**Guardrail carried from D-P1-04:** if the empty-state invite renders inside a
non-scrolling region, `invite_cta_shown{notif_empty}` is a mount counter, not an
impression. Check before trusting the rate, and say so in the spec.

### 5.3 What each change is trying to move

| Change | Funnel v2 target | North star |
|---|---|---|
| `referral_joined` receipt | Repeat invites per inviter (K-factor input) | Indirect — density → WAT |
| League-member rows | Stage 7 mutual match, stage 8 send — both density-bound | **WAT** |
| `deck_replenished` row | Return visit | **WAT** |
| Empty-state invite | Stage 0, a new person | Indirect |
| Bell instrumentation | None — it makes the rest legible | — |

### 5.4 Experiment backlog additions

| ID | Hypothesis | Cheapest test | Success criterion |
|---|---|---|---|
| **G-N1** | The bell is opened often enough to be a channel at all | `notif_inbox_opened` for 14 days | ≥1 open per weekly-active user |
| **G-N2** | A tappable `referral_joined` receipt raises repeat invites | Ship it; compare `invite_shared` per inviter before/after | Any lift — the base is near zero |
| **G-N3** | Social-proof rows drive returns | `notif_row_tapped{type}` share vs receipts | Social rows ≥20% of taps |
| **G-N4** | The penetration-gated empty-state invite converts | `invite_cta_tapped{notif_empty}` ÷ `notif_empty_state_shown{invite_offered:true}` | Tap rate ≥ the shipped `matches_empty` surface |
| **G-N5** | A `deck_replenished` inbox row recovers a push that reaches nobody | Row taps + next-day return | Any measurable return signal |

---

## 6. Riskiest assumption & cheapest test

**Riskiest assumption:** *that anyone opens the bell.* Every recommendation here — and the
operator's original instinct that the list is a channel worth using — rests on it. It is
**completely unmeasured** (M11): zero `track()` calls, no historical series, nothing
recoverable. If bell opens are rare, then the correct answer to "use the notification list
for growth" is *no, use the screens*, and six rows of plumbing bought nothing.

**Cheapest test:** ship `notif_inbox_opened` + `notif_row_tapped` **alone**, ahead of every
other change in this document. It is two `track()` calls in `TopBar.tsx`, one taxonomy
commit landing first, and two weeks of waiting. It costs a fraction of the row work and it
is the difference between a designed surface and a decorated one.

**Sequencing consequence, stated as a recommendation:** if P1-9 is the next build, put the
two bell events in its taxonomy commit. They are unrelated to `trade_found` and cost
nothing extra there — and P1-9's own inbox row is the first row anyone will ever want the
tap rate for. Missing that commit means waiting for the next one.

**Second-order risk:** at 3–5 users, none of G-N1…G-N5 will reach significance. These are
**directional reads, not experiments**, and should be reported as such. The instrumentation
is worth shipping anyway — it is retroactively unrecoverable, and the population problem
resolves itself as the invite loop works.

---

## 7. Decisions needed

Each carries a recommendation. Product calls are the operator's.

| # | Decision | Recommendation |
|---|---|---|
| **GD-1** | **Does the invite ask get a row, or the empty state?** | **Empty state, penetration-gated at the shipped 50% rule.** No standing invite row. If a row is wanted, take the single-lifetime variant (§4.3), never a recurring one |
| **GD-2** | **Do the six receipt/social rows ship as one batch, or fold into P1-9?** | **One small batch after P1-9.** Five of them are two lines each next to code P1-9 is already touching, but P1-9 has enough surface area |
| **GD-3** | **Ordering: recency-only now, priority later?** | **Yes — option A now, option B the day the first prompt row is approved** (§4.1) |
| **GD-4** | **Fix "Clear all", or rename it?** | **Fix it** (§4.2 A). Rename is an acceptable holding position; the fix becomes a prerequisite of any prompt row |
| **GD-5** | **Does `referral_joined` get a push, or stay inbox-only?** | **Push, in the operator-only phase.** It is another human's action — it passes the P1-9 bar cleanly. `trade_matches` bucket |
| **GD-6** | **Periodic re-rank prompt: build, or wait for an event trigger?** | **Wait.** A calendar trigger repeats the mistake P1-9 exists to fix. Commission the roster-diff feasibility check instead |
| **GD-7** | **Do the two bell events ride P1-9's taxonomy commit?** | **Yes.** §6 — this is the whole cheap test, and it needs a commit that is already happening |
| **GD-8** | **Coalescing window for `league_member_joined`** | **One row per league per day.** A five-person onboarding wave should read as one event, because it is one |

---

## 8. Handoffs

| To | What |
|---|---|
| **an-data-architect** | Formal instrumentation spec for the four §5.2 rows, including the `surface` enum extension to `notif_empty` and the `NON_INTENT_EVENTS` co-commit rule (M10). **Blocking for GD-7** |
| **eng-backend** | Feasibility check: does league sync expose a roster diff usable as a re-rank trigger? **Blocks GD-6.** Also the five `create_notification` sites and the server-side dismiss (GD-4) |
| **eng-mobile** | `ROW_GLYPHS` + `V2_*` routing entries, the empty-state redesign, the two `track()` calls |
| **eng-web** | The **second** glyph map and tap router (`web/js/app.js:4676`, `:4830`) — cross-client parity, and reconciling its `localStorage` dismissal with a server-side one (M5) |
| **pm-technical** | PRD sizing for phase 1 if the operator wants it as a formal item rather than a fold-in |
| **an-funnel** | Whether `referral_joined` → repeat `invite_shared` should be a named K-factor input now that `league_id` is no longer scrubbed (`9674439`) |
| **pm-retention** | Phase 3 prompts are retention mechanics as much as growth ones — co-own the re-rank trigger design if GD-6 unblocks |
| **pm-pfo** | Confirm none of the six rows competes with the core loop's first-run path |

---

### Appendix — claims I checked that did not hold

Recorded in the spirit of D-P1-14, since two premises in this exercise's framing were
mine to verify and one was wrong.

1. **"The inbox row is the artifact independent of push delivery."** True for P1-9 *as
   designed*, but the framing implies the pairing already exists elsewhere. It does not:
   `_send_typed_push` has never written an inbox row (M1), and 11 of 14 kinds have no
   inbox trace. P1-9 establishes the pattern rather than following it.
2. **"Inform them of new league members" is a new feature.** It is not — both kinds ship
   today, push today, in a default-ON bucket (M6). What is missing is the inbox row.
3. **The bell is a known-good channel.** Unverifiable. Zero instrumentation, no history
   (M11). Every usage statement in this document about the bell is labelled assumed, and
   §6 exists because of it.
