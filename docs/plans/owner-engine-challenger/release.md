# Owner-construction trial — verified release record

## Current state

Backend **LIVE**, new constructor **shadow-enabled, not serving**. iOS
**1.17.2 (150)** built successfully and its exact-ID TestFlight submission is
**FINISHED**. Apple availability, tester installation and the
[12 device checks](manual-testflight.md) remain unverified/UNRUN. No claim of
improved acceptance or completed production trial.

## Reviewed source and gates

- [PR #285](https://github.com/mattmurf77/fantasy-trade-finder/pull/285)
  squash-merged at **2026-09-06 21:19:11 UTC**, merge
  `0e3d6b703c1351f51a7b38d3a561d340eda5e44b`.
- Final reviewed head `65fa7720b41adc480502d798aa754378105aa896` passed all four
  [hosted CI jobs](https://github.com/mattmurf77/fantasy-trade-finder/actions/runs/34059989947).
  Backend **5,765 passed / 1 skipped in655.89s**. Parent frozen local backend:
  **5,765 passed / 1 skipped in400.05s**. Mobile TypeScript/all97 guard programs,
  testID lint, web190 and native plist/project syntax checks passed.
- Parent fetched the merged source and verified full tree equality against the
  tested head. No direct-main push or CI bypass. Existing control goldens and
  profiles were not recaptured. Final hot-flip/cache repairs have independent
  RED/GREEN evidence and focused review; prior `13b94161` CI is a superseded
  checkpoint, not the source built or deployed.
- Public publication uses the previously explicitly approved
  `mattmurf77/fantasy-trade-finder` destination. The first push used the other
  signed-in account and returned403 without publishing; the successful scoped
  retry used the existing owner account without changing global authentication.
  Original dirty files, secrets and unrelated organization work remain untouched.

## Backend deployment and shadow-only activation

Render's normal auto-deploy created `dep-daethkbbc2fs73cmot5g` at
**21:19:13.935753 UTC** on exact merged `0e3d6b70`; it reached **LIVE at
21:20:25.109775 UTC**. No manual deployment, service/environment change or new
infrastructure resource was required.

GET-only checks before and after deployment verified public/operator success,
anonymous trade/admin401, unchanged207 effective flags, unchanged259 existing
configuration values, and unchanged tier/experiment/root hashes. The five new
owner keys were seeded with their documented defaults. Measurement prerequisites
`deck.signal_v2`, `analytics.ingest`, `analytics.client_events` and the existing
bakeoff/interleaving controls were already enabled.

The existing audited `scripts/set_knob.py` changed only
`bakeoff_include_owner` **0→1**, request timestamp **21:21:19.888685 UTC**, source
`owner-constructor-v1-shadow-20260906`. Readback **21:21:21.177 UTC** verifies
include1, **serve0**, pool16, pair budget4096 and total budget60000. Existing
settings/flags remain unchanged; the event index is present and ingest
transaction failures are0. This authorizes generation/logging on fresh eligible
requests; it is not evidence of an actual generated/served/viewed impression.
No direct production DB connection, synthetic seed, user trade generation or user decision
was performed for this release.

Serving remains0 until the intended tester is confirmed to have installed
1.17.2 or later. There is no client-version allowlist on the global serving
switch: older clients can ignore ordering, partial notices and selected-offer
measurement. Do not call their mixed-version outcomes a clean test. Existing
three arms and the previous personal-market policy remain intact.

## Exact mobile build

Clean source and actual EAS archive at `65fa7720` were independently inspected:
3,097 tracked source files, 2,673 retained archive files; 424 omissions match the
existing EAS policy. All 635 mobile files and all retained archive files are
byte-identical. No local DBs, caches, dependencies, credentials or private scratch
files. Archive history contains one shallow commit, with no unreachable objects.
Effective configuration: production API, testMode=false, version 1.17.2, existing
owner/project/bundle identity. Dependencies were resolved through NODE_PATH,
not copied into the release checkout.

One production build was dispatched with frozen existing credentials:
[fd9537fb-fead-46c2-a3b7-efd4a5516b11](https://expo.dev/accounts/mattmurf77/projects/dtf-dynasty-trade-finder/builds/fd9537fb-fead-46c2-a3b7-efd4a5516b11),
created **21:20:56.721 UTC**, source `65fa7720`, version **1.17.2 (150)**.
EAS reported monthly included build credits exhausted and existing pay-as-you-go
billing; no plan, billing or credential configuration was changed.
Build completed **21:26:38.848 UTC**. Exact build-linked readback at
**21:28:21.620 UTC** confirmed FINISHED and no prior submission. One standard
exact-ID submission was then scheduled without optional Enterprise-only release
notes, tester-group changes or public App Store release:
[76b98762-44dc-430d-862d-8b5141cbe9a9](https://expo.dev/accounts/mattmurf77/projects/dtf-dynasty-trade-finder/submissions/76b98762-44dc-430d-862d-8b5141cbe9a9).
Readback **21:30:23.188 UTC**: IN_PROGRESS, correct existing Apple app6771488431,
error=null. No duplicate build/submission. Upload completion remains separate
from Apple processing/tester availability and installation.

Final exact-submission readback **21:32:08.141 UTC** verifies **FINISHED**,
error=null, correct project/owner and Apple app6771488431. The final GET-only
production readback at **21:30:23.937 UTC** again verifies exact source LIVE,
include1/serve0, unchanged existing flags/settings/tier/experiment hashes and
healthy analytics. No Apple tester-availability or physical-device pass is implied.

## Remaining boundary

Verify actual Apple availability and intended tester installation. Only
afterward enable serving
through the audited knob route and verify the single-key delta. Native manual
checks and empirical model-quality readout remain separate work. Setting
serve=0 prevents treatment exposure for newly captured requests; include=1 may
continue shadow generation/logging. Already captured jobs/cards are not revoked.
