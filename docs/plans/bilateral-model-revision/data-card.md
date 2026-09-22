# Evidence/data card

Read-only production capture: **2026-09-22T05:31:54.003901+00:00**. Source:
Render Postgres `bakeoff_runs.config_json` full owner-request snapshots, bounded
to the latest 100 rows in 14 days with a 15-second SQL statement timeout;
authenticated `/api/admin/config` and `/api/feature-flags` read at capture time.
The capture did not generate offers, write data, deploy or change flags.

94 rows were returned; 17 repeated manager/league/full-input instances were
excluded, leaving **77 captured requests, 19 initiating manager-league
combinations, 12 leagues**. This is a bounded activity sample, not all users or
all dynasty leagues. Selected outlook counts: 16 all-in/championship, 18
contender, 20 tanking/jets, 11 rebuilder, 12 absent/unknown. Formats: 49 1QB/PPR,
28 SF/TEP. Personal-source counterpart evidence is present for 152 of 891
counterpart occurrences; nonempty Elo alone is not treated as conviction.

Shared participants connect these records into **only two independent
components**. The original frozen input-only split yielded 74 development and two held-out
requests, not 76 independent trials. Before candidate output inspection, a
diagnostic panel selected one input per observed outlook×format stratum plus
both held-out requests: 11 real contexts, with 57 explicitly constructed
archetype/sensitivity contexts evaluated separately. Independent review found
that supplied request-hash deduplication had incorrectly omitted one distinct
tanking input. Full-input digest deduplication restored it; all original 76 inputs
and their cluster assignments remain, and the additional input is an explicit
supplement rather than a post-result stratum reselection. The repaired comparison
panel therefore has **12 real plus 57 constructed contexts**. Preserve the full capture
and split; do not imply every captured request received a paired final replay.

Private capture and manifests are mode-0600 artifacts under `/private/tmp`:
`bilateral-revision-prod-capture-20260922-v2.json`,
`bilateral-revision-frozen-split-20260922.json`,
`bilateral-revision-frozen-panel-20260922.json`. They contain private boards and
identities and must not be committed or copied into public reports. Hash binding
and exact final run paths are recorded in evaluation evidence. These temporary
files are not a durable organization-wide research archive; retention/access
ownership and a durable private home remain to be assigned before recurring use.

The comparison holds configuration common across constructors. It is not a claim
that historical served cards were produced with today's config. Market seeds
remain the captured inputs; absent market-publication timestamps are not filled
with capture time. Missing projection/rule/age provenance and absent independent
exact-package review/outcome cohorts are explicit Unknowns. KTC/DP references
and completed Sleeper trades remain reference/positive-only evidence, never
invented rejection labels for these generated offers.

Only 88 of 968 manager-preference occurrences include next-draft/own-next/expired
pick metadata; no request includes actual projected-points evidence. Preserving
available slots/capacity does not turn dynasty-value proxies into real starts.

The captured live settings selected incumbent bilateral exclusively:
`owner_bilateral_enabled=1`, owner include/serve/only each 1, challenger/gen_v2/fit
include each 0, significance enforce=2. The revision knob was absent (new code
defaults it to 0). This is a timestamped production check, not a promise about
future state. No settings were changed during capture or implementation.
