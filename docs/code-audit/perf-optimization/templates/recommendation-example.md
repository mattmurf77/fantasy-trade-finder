# Worked Example — a model observation

This is a complete, real (illustrative) observation written to the standard.
Match this depth, specificity, and citation density in your own findings. It
shows: a precise root cause, concrete evidence, two options with a clear
preference, a defensible RICE-P, and explicit risk + dependency notes.

> Note: this example reflects a pattern in the codebase as of the audit; if
> you find it already resolved, cite the resolving commit and skip it.

---

## OBS-NET-07 — Trade-status poll fires every 1.5 s with no backoff or jitter

- **Area:** network / data-fetching
- **Severity:** P2
- **Status:** observed
- **Evidence type:** static-analysis

### What happens today
`mobile/src/screens/TradesScreen.tsx` polls the trade-generation job via
`getTradeStatus(jobId)` on a fixed 1500 ms `setInterval` while a generation
job is running (see the polling effect around `TradesScreen.tsx:185–213`).
The cadence is constant from the first tick until the job reports
`status === 'complete'`, regardless of how long the backend is taking per
opponent.

### Why it's slow / costly
The backend generates trades per-opponent in a background thread; each
opponent can take ~2–3 s on a warm Render dyno and far longer on a cold one.
A flat 1.5 s poll therefore issues 2–20+ requests per job, most of which
return an unchanged in-progress snapshot. On cellular this is wasted radio
wake-ups (battery + latency contention with the very job we're waiting on),
and on a cold dyno the polling storm competes with the generation work for
the single free-tier worker. This doesn't slow the *first* paint but it
degrades the streaming-fill experience and wastes a constrained backend.

### Evidence
- `TradesScreen.tsx:185–213` — `setInterval(..., 1500)` with no dynamic
  interval and no teardown-on-backoff; only cleared on unmount/complete.
- Backend per-opponent timing is described in
  `backend/server.py` trade-generation thread (search `opponents_done`).
- A warm timing sample: `curl -w "%{time_total}\n" -s
  "$BASE/api/trades/status?job_id=…"` returned ~0.4 s/req warm; at 1.5 s
  cadence over a 12 s job that's 8 requests, ~6 of them no-change.

### Recommendation(s)
- **Option A (preferred):** exponential backoff with a cap + small jitter —
  start at 800 ms, ×1.5 per unchanged tick, cap at 4 s, reset to 800 ms when
  `opponents_done` advances. Keeps early responsiveness while collapsing the
  no-change tail. Follows `../research/01-mobile-data-fetching.md` "poll
  backoff" guidance. Low risk, client-only.
- **Option B:** switch the job to server-sent events / long-poll so the
  client blocks until the next card is ready. Better UX, but adds a streaming
  endpoint + Render free-tier worker-occupancy concerns — larger effort,
  defer unless Option A proves insufficient.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 6 | 0.5 | 80% | 1 | **2.4** |

- **Estimated latency delta:** no change to first-card latency; ~60–75%
  fewer status requests per job, smoother fill on cellular, less contention
  on cold dynos (−hundreds of ms on the tail in the contended case).
- **Confidence note:** 80% — the anti-pattern is unambiguous in code; the
  user-perceived gain is modest and partly battery/contention rather than
  raw latency, hence Impact 0.5.

### Related components
`mobile/src/screens/TradesScreen.tsx` (poll loop), `mobile/src/api/trades.ts`
(`getTradeStatus`), `backend/server.py` (`/api/trades/status`, generation
thread).

### Prerequisites / dependencies
None for Option A. Option B depends on a streaming-capable endpoint and a
review of Render free-tier worker occupancy.

### Regression risk
Low. Must ensure the backoff resets on progress so the last card doesn't
arrive up to 4 s late; test a multi-opponent job end-to-end and confirm the
deck still fills to completion and the "complete" transition still fires.
