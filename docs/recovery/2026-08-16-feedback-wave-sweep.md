# Recovery ledger — 2026-08-16 feedback wave sweep

> Capture-then-delete. Verification by content against `origin/main` (this repo
> squash/no-ff merges, so `git branch -d` refusals and ahead-counts are not
> evidence). **Tips captured BEFORE any removal.** Nothing in this file is
> swept until the wave's merge is confirmed on `origin/main`.

## Status: SWEPT (8 of 10) — 2026-08-17

Pushed to `origin/main`: wave merge `20b40db` → ship record `508c2d3` →
pre-sweep preservation `692ded2`. Containment verified **by commit ancestry**
(`git log origin/main..<branch>` = 0) for every build branch and the
integration branch, before any removal.

**Two branches were NOT contained and would have lost content on deletion** —
caught by the check, preserved onto `main` in `692ded2` before sweeping:

| Branch | What existed only there | Preserved as |
|---|---|---|
| `wave-calc` | G1's entire Phase-1 plan (`plan-2026-08-13.md`, 455 lines) — the spec its build agent worked from | `docs/feedback/items/303-calc-send-placement/plan-2026-08-13.md` |
| `feedback-2026-08-16-specs` | G6's U-R2-3 reconciliation note (the gloss-vs-formula contradiction caught mid-build) | appended to `docs/feedback/items/304-positional-need-filter/reconciliation-log.md` |

**Swept 2026-08-17** (worktree removed + branch deleted): `fb304-presentment`
· `fb328-picks` · `fb322-draftui` · `fb321-espn` · `fb303-calc` · `fb330-offer`
· `fb334-matches` · `specs-2026-08-16` — plus branch `wave-calc` (no worktree).

**Swept last** (after deploy confirmed live + 17 items set `fixed`):
`ship-main` (`1927506`, the release-1.13.5 bump) and `wave-integration`
(`439e256`, branch `feedback-2026-08-16-integration` deleted).

**Sweep complete — 10 of 10.** No wave worktrees or branches remain.

## Deploy record

`origin/main` `1927506`. **Render auto-deploy did not fire** for this push —
`92c31d5` stayed live ~20 min past the push with no queued deploy, despite
`autoDeploy: yes` on `main` and the service healthy (a webhook that never
delivered, not a bad push; commits confirmed on GitHub via `git ls-remote`).
Deploy `dep-da1hsv49v7es73bed330` was triggered explicitly via the Render API
and reached `live`. **Verified by content, not uptime:** `trade.presentment_rules
= True` present in `/api/feature-flags` (170 flags, up from 169).

**Runbook note for next time:** after any push to `main`, confirm a deploy was
actually *created* (`GET /v1/services/<id>/deploys?limit=1` — compare its commit
to `git ls-remote origin main`) before waiting on content. Waiting on a probe
for a deploy that was never queued looks identical to a slow deploy.

## Branches / worktrees to sweep (tips recorded 2026-08-17)

| Worktree | Branch | Tip | Content |
|---|---|---|---|
| `.claude/worktrees/ship-main` | (detached on `main`) | `508c2d3` | The wave merge + ship record — **the thing to push** |
| `.claude/worktrees/wave-integration` | `feedback-2026-08-16-integration` | `439e256` | 7-branch integration + conflict resolutions + Phase 3/4 QA |
| `.claude/worktrees/specs-2026-08-16` | `feedback-2026-08-16-specs` | `56856f7` | All Phase-1 signed-off specs (+ 2 amendments) |
| `.claude/worktrees/fb304-presentment` | `feat/fb304-presentment` | `0f8bff7` | G6 presentment rules |
| `.claude/worktrees/fb328-picks` | `feat/fb328-picks` | `08eb04b` | G3 mock-draft pick ownership |
| `.claude/worktrees/fb322-draftui` | `feat/fb322-draftui` | `13f0d48` | G2 mock-draft room UI (built on G3) |
| `.claude/worktrees/fb321-espn` | `feat/fb321-espn` | `49524ff` | G5 ESPN identity binding |
| `.claude/worktrees/fb303-calc` | `feat/fb303-calc` | `a58fb9a` | G1 calculator labels + send placement |
| `.claude/worktrees/fb330-offer` | `feat/fb330-offer` | `a531167` | G4 offer prefill + auto-run |
| `.claude/worktrees/fb334-matches` | `feat/fb334-matches` | `248ad68` (code) / docs `fdf94a7` | G9 matches dismiss + counts |

Also outstanding from an earlier wave (unchanged by this one): `wave-calc` @
`6b6c513` — its held calculator plan was the G1 spec and is now **shipped via
`feat/fb303-calc`**, so `wave-calc` becomes sweepable with this wave.

## Sweep procedure (after the push lands)

```bash
# 1. prove content is on origin/main (by content, not ahead-count)
git fetch origin
git log --oneline -1 origin/main            # must contain 508c2d3
git diff origin/main..feat/fb304-presentment --stat   # expect: docs/spec-only or empty

# 2. remove worktrees, then delete branches
for w in ship-main wave-integration specs-2026-08-16 fb304-presentment \
         fb328-picks fb322-draftui fb321-espn fb303-calc fb330-offer fb334-matches; do
  git worktree remove ".claude/worktrees/$w"   # a --force refusal means uncommitted files: INSPECT first
done
git branch -D feedback-2026-08-16-integration feedback-2026-08-16-specs \
  feat/fb304-presentment feat/fb328-picks feat/fb322-draftui feat/fb321-espn \
  feat/fb303-calc feat/fb330-offer feat/fb334-matches wave-calc
```

## Notes

- `fb322-draftui` was branched from `fb328-picks`' tip (stamped G3-before-G2
  serialization), so G3's commits appear in both — expected, not duplication.
- Two mid-build incidents were disclosed by their agents and fully recovered:
  a `git checkout` clobbering uncommitted work in `fb330-offer`, and another
  session's stash (`wip-session-169-living-memory`) accidentally popped into
  `fb321-espn` then reverted with the stash entry left intact. Neither reached
  a commit; recorded here because the next sweep should not be surprised by
  stash-list contents.
