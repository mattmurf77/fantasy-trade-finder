# Retired mobile tooling

**Historical reference only.** D-056 retired Maestro and the simulator on
2026-08-15. The files were relocated here on 2026-09-06 to keep dormant workflows
out of active mobile tooling.

| Path | Preserved purpose |
|---|---|
| [maestro/](maestro/README.md) | Frozen flow specifications and expensive flow-authoring lessons |
| `scripts/sim-build.sh`, `scripts/sim-run.sh` | Old simulator build and execution harness |
| `scripts/screen-capture.sh`, `scripts/screen-freshness.sh` | Old screen-library capture and freshness commands |
| [scripts/mutations.md](scripts/mutations.md) | Historical drills for testing the retired system |

The shell scripts refuse execution immediately. Their original bodies remain as
historical evidence; embedded paths and commands describe the old layout.

The active [testID lint](../../../mobile/scripts/testid-lint.sh) reads `maestro/`
and fails if the required archive is absent or empty. Preserve those YAML inputs
unless the lint contract is deliberately migrated. Do not author new flows.

Current automated evidence lives in [mobile tests](../../../mobile/tests/README.md)
and CI. Runtime evidence is a written manual TestFlight checklist.
