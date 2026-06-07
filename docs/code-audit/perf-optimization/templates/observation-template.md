# Observation Template

Copy this block verbatim for **each** finding. One finding = one observation
block. Group multiple observations in a single `.md` file per sub-area (see
your agent brief for the file naming). Keep each observation self-contained —
the synthesis phase reads these without re-reading the code.

Do **not** change code. You are documenting only. Every claim must cite a
`path:line` reference so a reader can verify it.

---

```
## OBS-<AREA>-<NN> — <short imperative title>

- **Area:** <e.g. API client / data-fetching / backend routes / DB / RN rendering / network>
- **Severity:** P0 | P1 | P2 | P3
- **Status:** observed            <!-- audit phase is observation-only; always "observed" -->
- **Evidence type:** measured | static-analysis | hypothesis

### What happens today
<Plain-language description of the current behavior. Cite the exact code:
`mobile/src/api/foo.ts:42`. Include the relevant snippet if short.>

### Why it's slow / costly
<Root cause. Name the anti-pattern if there is one (N+1, waterfall request,
full-payload serialization, missing memo, re-render storm, blocking await,
unbounded query, no cache, cold-start on critical path, etc.).>

### Evidence
<Concrete support: a timed `curl` with `-w "%{time_total} %{size_download}"`,
a payload byte count, a render-count reasoning, a query plan, or the specific
lines that prove the claim. If you measured, paste the numbers. If static,
explain the deduction.>

### Recommendation(s)
<One or more options. If multiple, label them Option A / B / C with the
trade-off for each (effort vs impact vs risk). Reference the relevant research
doc in ../research/ if your fix follows a documented best practice. Do NOT
write the code — describe the change at the level of "what + where + why".>

- **Option A (preferred):** <change> — <trade-off>
- **Option B:** <change> — <trade-off>

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| <1-10> | <0.25-3> | <20-100%> | <0.5-8> | **<R×I×C/E>** |

- **Estimated latency delta:** <e.g. −1.2 s warm league pick; cold-start stall removed from critical path>
- **Confidence note:** <why this confidence level; what would raise it>

### Related components
<Files / modules / endpoints this touches or interacts with.>

### Prerequisites / dependencies
<Anything that must land first (another OBS, a schema change, an infra change
like enabling gzip or a paid dyno). "None" is a valid answer.>

### Regression risk
<What could break; what to test. Note any FTF cross-client invariant
(tier colors, K-factors, enum strings, ELO math) the change could disturb.>
```

---

## Rules

1. **Observation only — no code edits, no git, no builds, no `npm`/`tsc`.**
   You may run read-only `curl` against the live backend to measure latency.
2. **Every claim cites `path:line`.** Unsupported assertions are dropped in
   synthesis.
3. **Always fill RICE-P + the latency delta.** A finding without a score
   cannot be prioritized.
4. **Prefer measured over assumed.** If you can time it, time it, and set
   Confidence accordingly.
5. **Multiple options are welcome** when there's a real trade-off; pick a
   preferred one and say why.
6. **Stay in your lane.** Only audit the area in your brief. If you spot
   something major outside it, add a one-line `## CROSS-REF` note at the end
   of your file rather than a full observation — synthesis will route it.
