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
  pages load without console errors on the local server. Push the release
  branch and confirm **CI green** (`.github/workflows/ci.yml`: backend-tests,
  mobile-typecheck, maestro-testid-lint) before presenting go/no-go.
- **Evidence fresh** (rewritten 2026-08-18 per
  [D-056](../../../../living-memory/DECISIONS.md)): the `living-memory/TEST_LEDGER.md`
  entry from Phase 3 covers an ancestor of the release SHA, and the operator
  TestFlight checklist is attached to the ship summary. There is no sim gate and no
  `qa/sim-runs/last-sim-run.json` — `githooks/pre-push` is a deliberate no-op; CI is
  the gate. Code changed after the last QA round → back to Phase 3, not around it.
- **Docs sync** per the CLAUDE.md table: routes → `docs/api-reference.md`,
  schema → `docs/data-dictionary.md`, config/flags → `docs/config-reference.md`,
  shared enums/colors → `docs/cross-client-invariants.md`, new terms →
  `docs/glossary.md`, notable decisions → `docs/adr/`. Convention shifts →
  `living-memory/LLD.md`; architecture shifts → `docs/architecture.md` +
  `living-memory/HLD.md`. Verify against each group's `scope.md` docs table —
  every row must read "updated" or "n/a because"; fill gaps.
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
- **The consolidated TestFlight checklist** from Phase 3 — since D-056 this is
  the batch's only runtime evidence, so present it as work the operator is being
  asked to do, not as an appendix.
- Anything else the operator must do by hand (e.g. App Store Connect steps — see
  `docs/runbook.md`).

Deploys are outward-facing and effectively irreversible; approval for a
previous batch does not carry over.

## 3. Ship (on "go")

Use the current repository's normal PR workflow and exact-head green CI; do not
use the historical `trade-engine-v2` merge path or push directly to main.
Inspect the **complete proposed squash message**, not just its subject,
for inherited deployment-skip markers. If an authorized runtime release was
skipped, first verify service settings and absence of a duplicate/active deploy;
then use a single exact-commit deployment API call, preserving auto-deploy and
cache settings, and verify that source reaches LIVE. Intentionally skip Render
for documentation-only release bookkeeping.

Publish the reviewed release branch, create its PR against current main, verify
every required check on its exact head, then merge through the normal PR flow.
Fetch the merged source and verify content equality with the tested tree; any
concurrent overlap requires reconciliation before merge.

```bash
# Mobile: EAS production build → TestFlight (profiles in mobile/eas.json)
cd mobile
eas build --platform ios --profile production --non-interactive
# After verifying that exact build completed and no submission already exists:
eas submit --platform ios --profile production --id <verified-build-id> --non-interactive
```

- Verify Render: poll `https://fantasy-trade-finder.onrender.com/` (and one
  changed endpoint) until the deploy is live; check for 500s.
- EAS builds take ~15–30 min: start the build, monitor
  (`eas build:list --limit 1`), then submit. If the build fails, fix and
  re-run — do not leave the batch half-shipped (backend live, app not) any
  longer than necessary; note the mismatch to the operator if it persists.
- Submit the **verified exact build ID**, not a moving `--latest` target. Read
  submission status before any retry. Optional release-note/changelog submission
  may be plan-restricted; if rejected, inspect submission history to prove no new
  submission exists before retrying the standard exact-ID submission without that
  optional field. Never upgrade billing or regenerate credentials as a workaround.
  FINISHED upload does not prove Apple tester availability or physical-device QA.

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
