# Reproducing security validation

Run from the repository root on the reviewed branch. These tools exercise synthetic data and do not source the project's credential files. No runtime dependency or product schema was added.

## Python 3.12 and SQLite

Create an isolated Python 3.12 environment and install the repository's backend/test requirements. `python312-dependencies.txt` records the exact environment used for this review (Python 3.12.14; the configured deployment patch version is 3.12.3).

```sh
python3.12 docs/plans/security-data-hardening/validation-tools/run_python312.py
```

The harness selects a scratch SQLite database, disables the optional AI key, blocks urllib upstream calls before importing the server, and pins startup market data to a repository fixture. Individual tests still supply their ordinary upstream mocks. Calibration tests are included and can run for several minutes without new output. This is not a live upstream integration test.

## Actual PostgreSQL

Create a disposable local PostgreSQL database whose name begins with `ftf_security_validation`. The review used PostgreSQL 18.3, a private Unix socket, and no TCP listener. Supply its URL through an explicitly named environment variable:

```sh
export FTF_SYNTHETIC_PG_URL='postgresql+psycopg2://localhost/ftf_security_validation'
python3.12 docs/plans/security-data-hardening/validation-tools/run_postgres.py \
  --database-url-env FTF_SYNTHETIC_PG_URL --confirm-synthetic
```

The helper rejects nonlocal hosts, other database names and custom PostgreSQL options. Each fixture owns a random schema; cleanup drops only those schemas. Coverage includes dry-run/apply/idempotent token maintenance, rollback, session restoration/deletion races, stale queued work, alias export/deletion, outcome caps, and simultaneous ingestion conflicts. Never point this harness at production. Production maintenance is a separate operator-reviewed action documented in `docs/runbook.md`.

## Browser and extension

```sh
node qa/web/check_browser_auth.mjs
python3 qa/web/check_web_structure.py
node qa/web/check_browser_auth_runtime.cjs
```

The runtime harness needs Playwright and Chromium with MV3 support. If they are installed outside the repository, set `NODE_PATH` to the containing `node_modules` and `PLAYWRIGHT_CHROMIUM_EXECUTABLE` to that Chromium executable. It creates a disposable profile, loads this checkout's extension, and fulfills or aborts all web requests. It never uses a user's browser profile. Some macOS environments require permission to launch the isolated browser.

## Mobile

From `mobile/`, run `node_modules/.bin/tsc --noEmit`, `bash scripts/testid-lint.sh` and every `tests/check-*.js` with Node. The ownership guard executes real source modules against stubbed React/native boundaries, including deferred responses and account switches.

The review also exported an iOS Hermes JavaScript bundle:

```sh
EXPO_NO_TELEMETRY=1 EXPO_OFFLINE=1 FTF_ENV=test \
FTF_API_BASE_URL=http://127.0.0.1:5000 EXPO_PUBLIC_SENTRY_DSN='' \
node node_modules/expo/bin/cli export --platform ios \
  --output-dir /private/tmp/ftf-security-ios-export
```

This is a bundle check, not an iOS build or native runtime pass. Complete the [TestFlight checklist](../mobile-evidence.md) on a physical device; simulator/Maestro are retired by D-056.
