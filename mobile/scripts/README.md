# Active mobile tooling

Run from `mobile/` with its dependencies installed.

| Command / input | Purpose | CI |
|---|---|---|
| `bash scripts/testid-lint.sh` | Checks the retained historical flow specifications against current `src/` testIDs; rejects banned flow patterns. Exits 2 if its archive is missing or empty | Yes |
| `scripts/testid-lint-allow.txt` | Documented glob allowlist for dynamic testIDs that cannot be found by static matching | Lint input |
| `npm run test:contrast` | Checks the Chalkline token contrast floors | Yes, via the mobile verification command |

See [mobile tests](../tests/README.md) for the current structural guards and
[package scripts](../package.json) for the aggregate verification command.

The dormant simulator executables, mutation drill, and retained Maestro flows
live in [the retired tooling archive](../../archive/retired-tooling/mobile/README.md).
They must not be executed. `testid-lint.sh` reads archived YAML as specifications;
it does not invoke Maestro or a simulator.

The mobile configuration environment contract remains in `mobile/app.config.js`.
With no environment overrides, it preserves the shipping `app.json` configuration.
