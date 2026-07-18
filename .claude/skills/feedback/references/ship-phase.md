# Phase 5 — Final review & ship

Runs once per batch, after every group is QA-green.

## 1. Orchestrator final pass

- Merge all green group branches into one release branch
  `feat/feedback-<date>` (e.g. `feat/feedback-2026-07-12`); resolve conflicts
  yourself (ownership tables should have prevented any — a conflict here is a
  lesson to record).
- Read the full batch diff end-to-end once more, fresh eyes: leftover debug
  code, TODOs, console.logs, accidental file drops (screenshots, scratch
  files), secrets.
- Gates: `cd mobile && npx tsc --noEmit` clean; backend `pytest` green; web
  pages load without console errors on the local server.
- **Docs sync** per the CLAUDE.md table: routes → `docs/api-reference.md`,
  schema → `docs/data-dictionary.md`, config/flags → `docs/config-reference.md`,
  shared enums/colors → `docs/cross-client-invariants.md`, new terms →
  `docs/glossary.md`, notable decisions → `docs/adr/`. Verify build agents did
  these; fill gaps.
- Version bump: `mobile/app.config.js` `version` (semver: features → minor,
  fix/polish-only batch → patch), matching the `mobile: bump version to X`
  commit convention.
- Finalize the batch `plan.md` in the lowest selected item's
  `docs/feedback/items/<id>-<slug>/` folder (final status per item, links to
  PRDs and QA reports), and each item's `status.md`.

## 2. Operator go/no-go (hard gate — never skip)

Present a ship summary and **wait for explicit approval**:

- Items addressed (#id → one-liner → status), items attempted-but-dropped.
- Diff stats per platform; version bump; QA rounds run and final verdicts.
- Exactly what "go" triggers: push to `main` (Render auto-deploy of backend +
  web) and an EAS production build + TestFlight submit.
- Anything the operator must do by hand (e.g. App Store Connect steps — see
  `docs/runbook.md`).

Deploys are outward-facing and effectively irreversible; approval for a
previous batch does not carry over.

## 3. Ship (on "go")

```bash
# Git: release branch → trade-engine-v2 → main
git checkout trade-engine-v2 && git merge --no-ff feat/feedback-<date>
git checkout main && git merge trade-engine-v2 && git push origin main   # Render auto-deploys
git checkout trade-engine-v2 && git push origin trade-engine-v2
```

If `main` and `trade-engine-v2` have diverged in a way that makes this merge
non-trivial, stop and confirm the merge plan with the operator — branch
topology has changed before.

```bash
# Mobile: EAS production build → TestFlight (profiles in mobile/eas.json)
cd mobile
eas build --platform ios --profile production --non-interactive
eas submit --platform ios --profile production --latest --non-interactive
```

- Verify Render: poll `https://fantasy-trade-finder.onrender.com/` (and one
  changed endpoint) until the deploy is live; check for 500s.
- EAS builds take ~15–30 min: start the build, monitor
  (`eas build:list --limit 1`), then submit. If the build fails, fix and
  re-run — do not leave the batch half-shipped (backend live, app not) any
  longer than necessary; note the mismatch to the operator if it persists.

## 4. Close the loop

- Set each shipped item `fixed`
  (`fetch_feedback.py set <id> fixed`). "Fixed" is the tester-visible
  "in next update" chip. Do **not** set `shipped` — that happens when testers
  actually have the TestFlight build, outside this pipeline.
- Report to the user: what shipped where, version numbers, TestFlight build
  status, per-item status changes, links to the batch docs.
- Append end-of-run lessons to `lessons.md` (pipeline friction, prompt
  improvements, anything the next run should do differently) and apply any
  that change skill behavior to the skill files themselves.
