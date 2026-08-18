# `docs/plans/` — Notes for Claude

Working docs for multi-step initiatives. **Nothing here is evidence that something shipped.**
A plan for a feature that went live in June and a plan abandoned in June look identical on
disk — the status column in [README.md](README.md) is the only discriminator. Read it before
you act on any doc in this tree, and don't infer "current" from a recent file date.

## Before you read a plan

1. **[README.md](README.md)** — the index, with a status per folder and per flat plan.
2. If it says **shipped**, the doc describes intent, not the implementation; the code and
   [`../api-reference.md`](../api-reference.md) / [`../data-dictionary.md`](../data-dictionary.md)
   are truth.
3. If it says **superseded** or **abandoned**, read it for reasoning only.
4. Check the flag in `config/features.json` before believing any "ships ON" claim in a doc.

## Before you write one

- **Feature scope first.** Any change touching user-visible behavior, data collection, schema,
  or API copies [`../templates/feature-scope.md`](../templates/feature-scope.md) into the
  feature's home as `scope.md`. This is the root `CLAUDE.md` §Conventions feature gate, not a
  local preference.
- **Flat vs folder.** One session, one author → flat `<slug>.md`. Multi-session, multi-agent, or
  iterative → `<slug>/` folder.
- **Add the README row in the same session** you create the folder.
- **Match the neighbours.** No single layout is enforced. The current shape is `plan.md` +
  `scope.md` + `prd.md` + `hld.md`/`lld.md` + `reconciliation-log.md`, with `build-*.md` per
  build wave and `research/` for sourced evidence. Batch folders suffix per item
  (`prd-p0-1.md`, `LLD-p1-3.md`).

## Where things aren't

- **Per-feedback-item fixes** → [`../feedback/items/<id>-<slug>/`](../feedback/items/), never here.
  Batches before item #64 are the exception and stay in `feedback-batch-2..4/` as history.
- **Strategy** (market sizing, pricing, positioning, audits) → [`../business/`](../business/).
  A plan here is the build-side counterpart, not the strategy.
- **What actually changed** → [`../../living-memory/CHANGELOG.md`](../../living-memory/CHANGELOG.md).
- **Point-in-time audits** → [`../reviews/`](../reviews/).

## The round-based protocol is legacy

[`_templates/`](_templates/) and [`../agent-collab-protocol.md`](../agent-collab-protocol.md)
describe a `status.md` / `conversation.md` / `round-NN-task.md` / `round-NN-findings.md`
handoff loop. Only `perf-optimization/` ever completed it. `feedback-backend-sync/` and
`mobile-feature-parity/` still say "round 01 not yet seeded" from 2026-06-07. Work since
2026-07 uses dual-agent PRD/HLD/LLD + `reconciliation-log.md` instead. Don't seed a new
round-protocol thread unless you intend to run it.

**Correction to earlier versions of this file:** those files are **tracked in git**. They were
documented as gitignored agent scratch; `.gitignore` has no rule for them and never did, and
`perf-optimization/`, `feedback-backend-sync/`, `mobile-feature-parity/` and `feedback-batch-2/`
all have theirs committed. Treat anything you write in a plan folder as public and permanent.

## Closing a thread

Flip its status row in [README.md](README.md), promote durable changes per the trigger table in
[`../CLAUDE.md`](../CLAUDE.md) (ADRs, data-dictionary, api-reference, glossary, runbook,
cross-client-invariants), and write the dated entry in `living-memory/CHANGELOG.md`. **Folders
are never deleted or archived** — they're the reasoning trail.
