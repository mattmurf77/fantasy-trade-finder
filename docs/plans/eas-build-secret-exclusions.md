# EAS build archive secret exclusions (O9)

**Date:** 2026-11-04. **Entry:** authorized launch-PR integration.
**Status:** implemented locally; PR CI and merge are pending. No credentials were read or rotated.

## Scope

When a root `.easignore` exists, EAS uses it instead of the tracked `.gitignore`
files. Repeat their sensitive patterns in `.easignore` so local environment files,
signing material, databases and QA scratch data cannot enter a build upload.
This integrates the previously unmerged `985d767a` fix onto current main.
There is no runtime, API, schema, feature-flag, model or analytics-event change.
No build or upload is performed by this fix or its guard.

## Evidence

- `.easignore:33` begins the unanchored sensitive-file patterns. Local data and
  QA scratch exclusions follow them. Existing app-source exclusions are preserved.
- `mobile/tests/check-easignore.js:24` identifies sensitive tracked ignore rules;
  `:53` checks coverage and `:65` enumerates the tracked ignore files. It fails
  if no sensitive rules were discovered, so a broken scan cannot pass vacuously.
- `mobile/package.json` exposes `npm run test:easignore`; the existing CI glob
  runs every `mobile/tests/check-*.js` file without another workflow change.
- Local guard result: all 14 sensitive tracked patterns covered. Removing the
  `secrets.local.env*` rule fails; anchoring `*.db` fails. Both mutations are
  restored before the final passing run.
- The existing historical commit reports a placeholder-only archive comparison.
  No archive, secret file, EAS environment or signing material was inspected in
  this integration. Exact-head GitHub CI remains the merge gate.

No backend unit test or device checklist is needed: only build-input exclusions,
package-script registration and a static guard change. No `testID` changes.

## Documentation impact

| Reference | Result |
|---|---|
| `docs/runbook.md` | Build exclusion and separate rotation guidance added. |
| `docs/api-reference.md` | Not applicable: no route or wire contract changes. |
| `living-memory/LLD.md` | Not applicable: no runtime convention changes. |
| `docs/architecture.md`, `living-memory/HLD.md` | Not applicable: no module or flow changes. |
| `docs/cross-client-invariants.md`, `docs/glossary.md` | Not applicable: no shared constants or new domain terms. |
| `living-memory/TEST_LEDGER.md` | Local guard and negative-control evidence recorded. |

## Release gate

Pass all existing GitHub CI jobs on the proposed head before merge. Future EAS
builds require the exclusion fix on main. Any credentials present in past uploads
still require separate, explicitly authorized rotation; excluding future archives
does not invalidate previously exposed values. No build or rotation is bundled here.
