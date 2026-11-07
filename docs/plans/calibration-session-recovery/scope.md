# Calibration session recovery

Status: isolated mobile repair on deployed `fabb5e36`; not a deployment or device attribution.

## Problem and boundary

An unexposed prepared exercise can become stale between the current-session read and its first card. The existing backend retires that exercise, creates/resumes the replacement and returns HTTP 409 `comparison_not_ready`. The installed screen keeps the retired session ID; its generic Retry repeatedly requests that same `/next` endpoint while an open cached current session does not poll. A network-blocked Flask reproduction confirms the retired endpoint remains refused while `/current` names the replacement. Executing the installed button confirms it never requests `/current`.

The user reported Calibration failure during a backend rollout and queued cohort preparation. No matching 409 trace has linked this reproduced defect to that specific report. This patch does not claim that attribution or shorten backend generation.

## Change and code walk

`mobile/src/screens/CalibrationScreen.tsx` handles only an actual `ApiError` with status 409 and code `comparison_not_ready` by reading the current exercise. It adopts the returned open/completed exercise or displays its building/failed/empty state. It does not POST enrollment, change grades, or reset server history. All other errors retain their original same-endpoint retry. A failed rediscovery keeps the existing error and permits another explicit read.

The current-session query includes the account ID. A captured account/league scope object fences asynchronous adoption; a changed account, league or unmounted screen cannot adopt an old reply. The existing league reset now also runs for an account change.

Building still polls at 1.5-second intervals for at most 60 seconds per explicit attempt. After that, copy says preparation can take several minutes and continues while the user leaves the screen. Check again resumes the same bounded read loop; it does not create a duplicate build or show an endless spinner.

## Verification

- `mobile/tests/calibration-retry-cases.js` executes the transpiled screen and actual rendered buttons: generic read retry, specific and unrelated conflicts, open/building/failed/completed/no replacement, failed rediscovery, account/league/unmount races, and the long-build Check again action.
- `backend/tests/test_outlook_calibration_routes.py` retains the stale-first-exposure HTTP contract and proves old IDs remain refused while `/current` names a different building exercise. Exposed/answered exercise tests remain intact.
- TypeScript, blind-grading/blinding/test-ID checks, failure-copy controls and all 165 mobile check scripts pass. The backend route suite passes 13 cases in 2.74 seconds. Independent peer review passes six additional boundary controls and the same 13-route suite in 1.81 seconds; final screen bytes are frozen. No simulator, provider requests, production mutation, model change or backend runtime change.

## Device acceptance after integration

On the next TestFlight build, open an exercise replaced before first exposure and tap Retry: the current replacement must load or show bounded preparation, without starting a second exercise. For a long queue, verify Check again and leaving/returning recover the stored exercise. An ordinary connection error must still retry the same card, and already saved answers must remain. These checks are pending physical-device validation, not claimed by source tests.
