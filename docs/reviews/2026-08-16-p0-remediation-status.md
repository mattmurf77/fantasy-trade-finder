# P0 remediation status — verified against `origin/main`, 2026-08-16

> Point-in-time snapshot. Source audit: [`docs/business/product/2026-08-09-mobile-ux-audit/`](../business/product/2026-08-09-mobile-ux-audit/).
> Specs: [`docs/plans/audit-p0-remediation/`](../plans/audit-p0-remediation/).
> Method: seven independent verifiers, one per item, each reading the spec then checking
> the **`origin/main` tree** (`git grep … origin/main`) — never the working checkout, which
> was ~70 commits stale at review time. Each was told a symbol existing is not proof the
> behavior is wired, and to check for flags leaving a fix dark.

## Headline

**All eight live P0 items are shipped, and all eight are live for real users — none is
dark behind a flag.** P0-4 was withdrawn at audit time. Nothing on this list requires
code to be written.

What remains is **verification and operator debt**, concentrated in three places: an
unrun Maestro set, an unverified production flag config, and one accepted UX residual.

## Status table

| Item | Status | Live for users? | What remains |
|---|---|---|---|
| **P0-1** Default path never completes; push permission blocked | SHIPPED | Yes — no flag | Stale `screens/manifest.json` frame reference (cosmetic) |
| **P0-2** Failed trade search looks like no search | SHIPPED | Yes — no flag | Nothing; one accepted toast overlap from feedback #314 |
| **P0-3** Invite loop broken at both ends | SHIPPED | Yes — reader unflagged | Operator: AASA validation → 24h CDN wait → on-device tap → flip `growth.invite_join_link` |
| **P0-5** Sign-in branch strands users with no league | SHIPPED | Yes — no new flag | Stale comment in `SignInScreen.tsx:227` |
| **P0-6** Matched ESPN users have no action | SHIPPED | Yes — both flag positions | Repoint `capture/matches@espn.yaml`; run flow; record the manual clipboard paste |
| **P0-7** Blind on launch day | SHIPPED | Yes — ingest + client_events `true` | Confirm Render's **live** config matches repo defaults; watch health endpoint day 1 |
| **P0-8** Tour signs off before it teaches | SHIPPED | Yes — no flag | Run `guide-no-false-signoff@release.yaml`, ideally once pre-fix to prove it catches the bug |
| **P0-9** 32-tap chore before any value | SHIPPED | Yes — `onboarding.trades_first: true` | Flag-pinned beat validation; D1 residual (see below) |

## The flag question, settled

A reasonable prior going in was that P0-8/P0-9 were built but dark behind
`onboarding.guide_v2`. **That is wrong.** `onboarding.guide_v2` is `false`
(`config/features.json:93`) but gates only the *Guided Onboarding v2 additions* — the new
N-beats and N6.1's takeover of the first-like moment. Every P0 fix was verified present on
the **flag-off arm**:

- P0-8's sign-off gate is unconditional, inside an effect guarded only by
  `guidedAvatarActive()` (`onboarding.guided_avatar: true`).
- P0-9's trades-first routing is `onboarding.trades_first: true`, flipped **default-on for
  everyone** by PR #129 on 2026-08-15 — "the built v2 flow is the product, not an
  experiment overlay". A first-session user lands on the trade deck, not Quick Set Tiers.
- The D1/D2/D3 fixes (first-like celebration, `celebration_shown` naming, the s5.1 render
  bug) are all unconditional.

The one genuinely OFF flag, `growth.invite_join_link`, gates **only the emitter's new URL
format**. The `?league=` reader, the `LeagueJoin` route, the AASA claim, the 302 and
`invite-meta` are all live. Invite links already sitting in Sleeper chats work today.

## Corrections to earlier claims

Two things previously stated in session notes are now refuted by code:

1. **"The invite loop is broken — `/?league=` is never read by mobile."** False as of
   `deepLinks.ts:387`, which reads it unflagged, in both router modes, above the bare-path
   short-circuit.
2. **"s5.1 never renders."** It was true, and was fixed by PR #132 — the regen-diff effect
   now reads `job.cards` instead of a stale `deck` closure. TEST_LEDGER records s5.1
   rendering for the first time.

## What actually remains

### 1. Simulator debt — the largest gap
The whole P0 batch shipped with the tier-1 sim gate **skipped by operator**
(`FTF_SKIP_SIM_GATE=1`, no `qa/sim-runs/last-sim-run.json`). Consequently several
regression flows were *authored but never executed*:

- `guide-no-false-signoff@release.yaml` (P0-8) — never run, and never run against the
  pre-fix tree, so it has never observed the bug it exists to catch.
- `p0-6-espn-copy-trade.yaml` — never run since being repointed.
- The P0-9 flag-pinned beat validation — owed, now folded into the Guided Onboarding v2
  TestFlight checklist.

### 2. One provably stale test artifact
`mobile/.maestro/capture/matches@espn.yaml` declares `# flags: release`, but release now
has `espn.send: true`, which renders `trades.send-espn-btn` instead of
`send-in-sleeper.copy`. Its two assertions would fail. The sibling flow was repointed to
`release-espn-send-off`; this capture was missed.

### 3. Production config is unverified
`config/features.json` is the repo default, not proof of what Render serves. Analytics
ingest **fails closed behind a 200** (G-031), so a mismatch is silent. Confirm
`analytics.client_events` and `analytics.ingest` on the live config before launch.

### 4. One accepted UX residual (P0-9 D1)
A user who likes exactly once and never again still never reaches tour sign-off — the
`s6.1` beat is re-armed, not rescheduled. Filed as a `NEXT.md` candidate, not built.

## Superseded: the `ux-audit-p0-remediation` branch

The branch behind the 2.9 GB `ftf-ux-audit-p0` worktree holds one commit (`399d521`,
2026-08-10, *"six P0 launch-blocker fixes + the P0-7 analytics subset"*). It was **never
merged** — the work was redone on the `p0-remediation` branch as a 15-commit series.
Evidence: the branch's own plan directory `docs/plans/ux-audit-p0-remediation/` and its
`ux-audit-p0-*.yaml` flows are **absent from `main`**, while main carries a fuller
`docs/plans/audit-p0-remediation/` spec set and differently-named flows that this review
verified in place.

Recommendation: retire the branch and worktree via the recovery ledger. It is the single
largest item of worktree disk and holds a superseded first attempt.
