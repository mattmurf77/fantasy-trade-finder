# Research execution scope — September 21, 2026

Owner requested revision and subagent execution of the latency research plan. Target: three seconds from Find a Trade tap to first actionable tile, preferably 20–30 usable offers initially, without shortening candidate search or eligible inventory. This phase produces isolated benchmarks/prototypes and a reviewed implementation decision, not a production rollout.

## Analytics

Existing `trades_generated.props.gen_ms`, `bakeoff_runs.total_ms` and service logs support read-only observation. Research harnesses collect local stage/candidate/byte counts; no new live emitters or analytics taxonomy changes. No raw private boards, credentials or personal identifiers in committed results. Explicitly distinguish computed/available cards from actual user exposure. Full client tap-to-tile instrumentation remains a separately scoped application change.

## Schema and flags

No application schema, runtime flag, model setting, search budget or environment changes. No production writes, load tests, deployments, subscriptions or scheduled services. Read-only production observations use bounded queries/timeouts and sanitized output. Prototype persistence must use isolated local data and blocked external networking. No paid host benchmarks without further approval.

## Evidence

Each agent supplies code-cited traces, reproducible commands, isolated tests, exact fixture/version/environment provenance, parity counts/hashes where applicable and measured/unmeasured boundaries. CPU benchmark windows are serialized. Frozen historical fixtures may omit live pick metadata and do not establish an exact reproduction of the latest production run. No simulator/Maestro. Physical tap-to-tile and TestFlight verification are unexecuted in this research phase; the decision report must include a concrete device checklist rather than claim success.

## Documentation and ownership

Parent owns revised research plan, this scope, infrastructure/precompute report and decision/results index. Pipeline agent owns `pipeline.md` and isolated pipeline script/tests; delivery agent owns `delivery.md` and isolated delivery script/tests; compute agent owns `compute.md` and isolated compute script/tests. Shared app source is read-only unless parent explicitly scopes a later experiment. Canonical API/data/architecture references remain unchanged because no app contracts change. HLD/LLD historical stubs are not targets. Research evidence is under this directory; private raw inputs remain outside Git.

## Completion and release gates

Research deliverables must distinguish measured findings from hypotheses and uncovered spans. The 95%-accounted end-to-end timing gate cannot pass without client/network coverage. Parent independently reviews agent outputs and reruns lightweight tests; benchmark claims require uncontended reruns. Any implementation proposal needs its own applicable feature scope, canonical references, regression/CI proof, rollback and device checklist. No release is implied by local prototype success. No gate waiver or express lane.
