# Optimization Plan — Mobile Player & Trade Fetch Performance

Synthesis of 5 research docs + 6 codebase audits (38 scored observations) into
a sequenced, decision-bearing plan. Companion data table:
[`priority-matrix.md`](./priority-matrix.md). Source findings:
[`../observations/`](../observations/). Research basis:
[`../research/`](../research/).

---

## 1. The headline finding (read this first)

The user-reported pain is "the mobile app takes too long to fetch players &
trade information." The audit's most important result is a **reframing**:

> The thing that *looks* like the problem — the 4.84 MB player payload — is
> **not on the mobile critical path.** The mobile client fetches a 25-byte
> `/api/sleeper/players/warm` ping, not the full body, and RN already
> negotiates gzip transparently. The 4.8 MB body is a **web-client** concern.

The real mobile latency is spent in four places, in priority order:

1. **Boot sequencing.** The splash screen is gated on *all four* boot promises
   resolving — including a network warm-ping the first screen doesn't need
   (`OBS-NET-03`, RICE-P **16.0**, the single highest-scored finding). On a
   cold dyno the user stares at a spinner for the full 30–60 s wake even though
   the local session restore finished in milliseconds.
2. **Cold-start cache population.** On a cold container the first request
   re-fetches the ~5 MB Sleeper player DB from upstream (no committed/baked
   cache, ephemeral disk) on the single worker, on the user's critical path
   (`OBS-NET-01`, **9.6**).
3. **Redundant backend recompute.** ELO/stats are recomputed 3–4× per rank
   request from the full swipe history with no memoization (`OBS-DB-03`,
   **6.4**); `session_init` rebuilds both scoring formats synchronously before
   the first trio can render (`OBS-ROUTE-06`/`OBS-NET-04`).
4. **Client cache gaps.** Only the Trios tab is prefetched; everything else
   navigates cold (`OBS-CACHE-05`, **6.4**); there is no persisted query cache,
   so every cold launch refetches into a spinner (`OBS-CACHE-01`); and the
   `focusManager` bridge is missing, so `refetchOnWindowFocus` is dead config
   (`OBS-CACHE-03`).

Underneath all of it sits the **Render free-tier cold start** — the irreducible
floor that no client trick fully removes (see §6).

---

## 2. How the 38 findings were consolidated

Overlapping observations from different agents were merged into **16
initiatives** so we plan around problems, not paragraphs. The non-obvious
merges:

- **Splash gating** — `OBS-NET-03` (16.0) and `OBS-CACHE-02` (5.0) describe the
  same root cause from the network and cache lenses → **INIT-01**.
- **Cold cache** — `OBS-NET-01` (bake the cache) + `OBS-DB-04` (parallelize the
  dual-format CSV fetch, stop re-reading the players table per build) →
  **INIT-02**.
- **session_init** — `OBS-NET-04` (client: optimistic shell), `OBS-ROUTE-06`
  (backend: defer trade-service build), `OBS-DB-03 Option B` (replay from
  snapshot) → **INIT-08**.
- **Web player payload** — `OBS-ROUTE-01/02/03/05` + `OBS-NET-05` (slim fields,
  ETag/Cache-Control, Flask-Compress, fix the mis-bound route) → **INIT-10**,
  explicitly tagged **web-weighted**.
- **The Accept-Encoding reconciliation** — `OBS-API-02` scored 12.0 at *50%
  confidence* ("does RN already gzip?"). `OBS-NET-02` **measured** that it does,
  and that mobile doesn't fetch the big body → corrected to ~0 mobile impact;
  both fold into **INIT-15** (documentation only). This is the clearest example
  of why measured findings outrank static ones.

Full mapping in [`priority-matrix.md` → Roll-up by initiative](./priority-matrix.md#roll-up-by-initiative).

---

## 3. Decisions — incorporate vs alternative vs defer vs reject

Most findings are **incorporated** with the auditing agent's preferred option.
The notable non-default decisions:

| Finding | Agent proposal | Our decision | Why |
|---------|---------------|--------------|-----|
| OBS-API-02 (add `Accept-Encoding`) | Add header (12.0) | **Reject for mobile** → INIT-15 doc | Measured no-op: RN auto-gzips, mobile uses `/warm`. Chasing the 12.0 would be motion without movement. |
| OBS-ROUTE-02 (Flask-Compress) | Add Flask-Compress | **Alternative**: document the edge-compression invariant in the runbook; make Flask-Compress optional | Edge already compresses for end users; adding origin compression risks double-encoding. The real value is resilience, not latency. |
| OBS-NET-02 (request `br`) | Optionally set `Accept-Encoding: gzip, br` | **Alternative**: document only | Br vs gzip saves ~14 KB on a payload mobile doesn't fetch. |
| OBS-RENDER-07 (Matches derived arrays) | Leave as-is | **Reject/No-op** | Agent verified it's already correct; recorded for traceability. |
| OBS-DB-03 Option B (replay-from-snapshot) | Snapshot ELO | **Defer to Wave 3** | Touches ELO math — a hard cross-client invariant; needs byte-for-byte golden tests. Option A (memo) gets most of the win at a fraction of the risk. |
| OBS-API-06, OBS-ROUTE-07 | Various | **Defer** | Off the player/trade critical path; low RICE-P. |

Everything tagged **[W]** (web payload cluster) is incorporated but explicitly
**not** counted toward the mobile-latency goal — it improves the web client and
frees origin CPU on the shared single worker (a second-order mobile benefit).

---

## 4. Delivery waves

Sequenced by ROI and risk. Each wave is independently shippable.

### Wave 1 — Quick wins (target: the bulk of perceived mobile latency, ~1 week)
Low-risk, ≤1 day each, and they hit the top of the matrix:

1. **INIT-01 — Decouple splash from network boot legs.** Gate `setBooted` on
   local-state only (session restore + cached flags); let `fetchTierConfig` +
   `warmPlayerCache` run detached. *The single highest-impact change.* Paints
   the shell immediately; on a cold dyno removes tens of seconds from the
   splash.
2. **INIT-02 — Bake the Sleeper player cache into the deploy image** (+
   parallelize the dual-format DP CSV fetch, reuse the players-table read).
   Removes the cold-dyno 5 MB upstream fetch from the first user's path.
3. **INIT-03 — Memoize `_compute_elo`/`_compute_stats`** keyed on the existing
   `_version` counter. Collapses 3–4 full-history passes per rank request to 1.
4. **INIT-04 — Extend the proven Trios prefetch** to Tiers / Overall / Manual /
   Matches / Trades on row-press / tab-press.
5. **INIT-05 — Wire `focusManager` (AppState) + `onlineManager` (NetInfo).**
   Makes the already-intended `refetchOnWindowFocus` work; fixes stale-on-resume.
6. **INIT-06 — Throttle `touch_user_activity`** to ≤1 write/min/user. Removes a
   synchronous DB write from every authed request (worst during status polls).
7. **INIT-12a — Add a default request timeout** + de-dupe the double
   `warmPlayerCache()`. Caps the "infinite spinner on a wedged dyno" failure.
8. **INIT-14a — Add `ix_players_position`.** One-line idempotent index.

### Wave 2 — Structural (multi-day, more testing)
9. **INIT-07 — Persisted query cache + correct query-key scoping.** Add an
   AsyncStorage persister so cold launch paints last-known data instantly; add
   `format`/`leagueId` to the player-data keys (land the scoping *with or
   before* the persister so we don't persist under-scoped, bleeding caches).
10. **INIT-08 — Optimistic Main shell + defer the trade-service build** out of
    `session_init`. Move the 5–10 s off the visible blocking path; profile
    `session_init` to confirm the split (the 5–10 s is the codebase's own
    estimate, unmeasured).
11. **INIT-09 — Prune trade-generation candidate sets** (~10× fewer 3-for-2
    combinations) behind a top-K equivalence test, so deep leagues finish a
    full sweep instead of truncating on the 1 s deadline.
12. **INIT-10 — Web player-payload optimization** (rebind the mis-bound route
    first, then slim 53→~17 fields, add ETag/Cache-Control/304). **[W]**
13. **INIT-11a — Cheap render wins**: `React.memo` PlayerCard/TradeCard/Row,
    `getItemLayout` on OverallRanks, extract the ManualRanks edit row, scope the
    over-broad `['rankings']` invalidation, shallow-equal `setJob` guard.
14. **INIT-12b — GET-only retry/dedup** for cold-start 5xx.
15. **INIT-13 — Trade-status poll backoff** (network cadence + render guard).
16. **INIT-14b — DB hygiene**: narrow `check_for_match`, server-cache the
    community-ELO map, bulk-upsert league members.

### Wave 3 — Larger / lower-priority
17. **INIT-11b — Tiers virtualization** (collapse non-active tiers). Higher
    design risk — must preserve the PR #60 screen-Y drop-coordinate fix and the
    drag-target measurement model.
18. **INIT-08 (Option B) — session_init replay-from-snapshot** (golden-ELO
    tests required).
19. **INIT-15 — Compression/encoding documentation**; StrengthBar sliver
    reduction; INIT-16 league double-fetch.

---

## 5. Expected impact (rolled up, honest)

| Scenario | Today (reasoned) | After Wave 1 | After Wave 2 |
|----------|------------------|--------------|--------------|
| **Warm-dyno cold launch → first shell** | spinner until 4 boot promises settle (~0.2–0.6 s net-bound) | near-instant (local-only gate) | + last-known data painted from persisted cache |
| **Cold-dyno first action** | 30–60 s wake **+** ~5 MB upstream fetch **+** session_init, all on a spinner | wake only; cache baked, shell painted immediately, warm-ping detached | + optimistic Main shell during session_init |
| **Tab navigation (in-session)** | cold round-trip per first visit (0.2–0.5 s warm) | prefetched behind the transition | instant from cache |
| **Rank/trio request (power user)** | 3–4× full-history ELO passes | 1 pass (−30–60% CPU) | + snapshot replay (W3) |
| **Trades fill (deep league)** | up to ~11 s CPU, truncates | — | ~2–3 s, full sweep (INIT-09) |

The single biggest perceived win is **INIT-01** (and **INIT-02** behind it):
together they convert "stare at a spinner through the cold start" into "use the
app immediately while it warms in the background."

---

## 6. The irreducible floor — an infra decision for you

Seven observations across five agents bottom out at the same root cause: the
**Render free-tier web dyno sleeps after ~15 min and takes 30–60 s to wake**,
and runs `--workers 1` (a single point of contention for any multi-MB
serialize or `session_init`). **No client or backend code change removes a true
cold start.** The options, cheapest first:

1. **External warm-ping** (UptimeRobot or a Render cron hitting
   `/api/session/ping` every ~10 min): ~$0, masks the cold start for ~90% of
   sessions. The residual is the gap-session user. Recommended regardless.
2. **`--workers 2`** on gunicorn: removes the single-worker contention, but
   needs a check against free-tier memory limits.
3. **Render Starter dyno ($7/mo, always-on)**: the only *complete* fix.

This is a product/cost call, not a code change — flagged here so it's an
explicit decision rather than an implicit ceiling on everything else.

---

## 7. What's deliberately out of scope

- Implementation. This plan is the audit's output; building the initiatives is a
  separate, gated effort. The HLD/LLD/requirements in
  [`../design/`](../design/) specify *what* to build for each initiative.
- The web client beyond the shared-origin payload work (INIT-10).
- Anything touching ELO math, K-factors, tier bands, or per-format
  independence without a byte-for-byte golden test (flagged per-initiative as a
  cross-client invariant per `docs/cross-client-invariants.md`).
