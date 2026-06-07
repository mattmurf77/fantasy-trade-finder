# Priority Matrix — all 38 observations, scored & routed

Every observation from the six audit agents, with its RICE-P, severity, the
**consolidated initiative** it rolls into (overlapping findings are merged —
see `optimization-plan.md`), the **decision** (Incorporate / Alternative /
Defer / Reject), and the delivery **wave**. Sorted within each wave by RICE-P.

Legend — Decision:
- **Incorporate** = do the agent's preferred option.
- **Alternative** = address the concern a different way than the agent proposed.
- **Defer** = real but low-ROI now; revisit later.
- **Reject/No-op** = verified not worth doing (kept for traceability).

Scope tag: **[M]** mobile critical path · **[W]** web-weighted · **[B]** backend/infra · **[X]** cross-cutting.

---

## The reconciliation that reorders the matrix

Three agents independently surfaced the 4.84 MB `/api/sleeper/players` payload
(OBS-API-02 12.0, OBS-ROUTE-01 5.4, OBS-ROUTE-03 5.1, OBS-NET-05 1.6). The
network agent **measured** two facts that down-rank it for *mobile*:

1. The mobile client never fetches that body — it calls the 25-byte
   `/api/sleeper/players/warm` variant (`sleeper.ts:47`). Only the **web**
   client downloads the full payload.
2. RN's `fetch` (NSURLSession/OkHttp) auto-injects `Accept-Encoding: gzip` and
   decompresses transparently; Cloudflare already compresses at the edge.

→ **OBS-API-02's 12.0 is corrected to ~0 mobile impact** (its own Confidence
was 50% precisely because "does RN already negotiate gzip?" was unverified;
the network agent verified it does). The payload-slim / ETag / compress cluster
is **real and worth doing for the web client + origin CPU**, but it is **not**
the cause of the user-reported *mobile* slowness. The matrix reflects this: the
payload cluster moves to Wave 2 as **[W]**, and the true mobile wins
(boot-sequencing, cold-cache, ELO memo, prefetch, session_init) lead Wave 1.

---

## Wave 1 — Quick wins (≤1 day each, low risk, high mobile leverage)

| OBS | Title | RICE-P | Sev | Initiative | Decision | Scope |
|-----|-------|------:|:---:|------------|----------|:---:|
| OBS-NET-03 | Splash gated on all 4 boot promises incl. network warm ping | **16.0** | P2 | INIT-01 | Incorporate (Opt A) | [M] |
| OBS-NET-01 | Cold dyno re-fetches 5 MB player cache from upstream Sleeper | **9.6** | P1 | INIT-02 | Incorporate (Opt A: bake cache) | [B] |
| OBS-DB-03 | ELO/stats recomputed 3–4× per rank request, no memo | **6.4** | P1 | INIT-03 | Incorporate (Opt A: `_version` memo) | [B] |
| OBS-CACHE-05 | Prefetch warms only Trios; other tabs navigate cold | **6.4** | P2 | INIT-04 | Incorporate | [M] |
| OBS-CACHE-03 | No `focusManager` bridge; dead `refetchOnWindowFocus` | **6.0** | P2 | INIT-05 | Incorporate (Opt A) | [M] |
| OBS-ROUTE-04 | `before_request` blocking `UPDATE users` every authed req | **5.6** | P2 | INIT-06 | Incorporate (Opt A: throttle) | [B] |
| OBS-CACHE-02 | Splash waits on flag network call (no query prewarm) | 5.0 | P2 | INIT-01 | Incorporate (merged into NET-03) | [M] |
| OBS-API-04 | No request timeout; hung dyno → infinite spinner | 4.0 | P1 | INIT-12 | Incorporate (Opt A: default timeout) | [M] |
| OBS-DB-01 | `players.position` unindexed (hot positional reads) | 3.2 | P2 | INIT-14 | Incorporate (Opt A: add index) | [B] |
| OBS-API-01 | Double `warmPlayerCache()` (boot + league pick) | 3.2 | P2 | INIT-12 | Incorporate (Opt A: warmed-once flag) | [M] |
| OBS-ROUTE-05 | Players route decorator mis-bound; `sleeper_players()` dead | 0.8 | P3 | INIT-10 | Incorporate (rebind first — unblocks INIT-10) | [W] |

## Wave 2 — Structural (multi-day, more testing / coordination)

| OBS | Title | RICE-P | Sev | Initiative | Decision | Scope |
|-----|-------|------:|:---:|------------|----------|:---:|
| OBS-ROUTE-01 | Players payload 53→~17 fields | 5.4 | P1 | INIT-10 | Incorporate (Opt A) | [W] |
| OBS-ROUTE-03 | Players ETag / Cache-Control / 304 | 5.1 | P1 | INIT-10 | Incorporate (Opt A) | [W] |
| OBS-NET-04 | `session_init` serial 5–10 s before first paint | 4.0 | P1 | INIT-08 | Incorporate (Opt A: optimistic shell) | [M] |
| OBS-DB-02 | Trade-gen combinatorial; truncates on deadline | 4.3 | P1 | INIT-09 | Incorporate (Opt A: prune + equiv test) | [B] |
| OBS-CACHE-01 | No persisted query cache; cold launch refetches all | 4.3 | P1 | INIT-07 | Incorporate (Opt A: AsyncStorage persister) | [M] |
| OBS-ROUTE-06 | `session_init` full dual-format rebuild on req thread | 3.2 | P1 | INIT-08 | Incorporate (Opt A: defer trade-svc) + profile spike | [B] |
| OBS-RENDER-01 | Tiers renders whole pool, no virtualization | 3.2 | P1 | INIT-11 | Incorporate (Opt A: collapse non-active tiers) → may slip to W3 | [M] |
| OBS-RENDER-02 | OverallRanks rows non-memoized; no `getItemLayout` | 3.2 | P2 | INIT-11 | Incorporate (Opt A) | [M] |
| OBS-CACHE-06 | Over-broad `['rankings']` invalidation | 3.0 | P3 | INIT-11 | Incorporate (Opt A: scope to position) | [M] |
| OBS-RENDER-04 | Trades poll re-renders screen on no-change ticks | 3.0 | P3 | INIT-13 | Incorporate (Opt A: shallow-equal `setJob`) | [M] |
| OBS-RENDER-05 | PlayerCard/TradeCard/DraggableRow not memoized | 3.0 | P2 | INIT-11 | Incorporate (Opt A: `React.memo`) | [M] |
| OBS-DB-05 | `check_for_match` unbounded `SELECT *` + Python compare | 2.4 | P2 | INIT-14 | Incorporate (Opt A: narrow + recency bound) | [B] |
| OBS-API-03 | Trade-status poll fixed 1.5 s, no backoff | 2.4 | P2 | INIT-13 | Incorporate (Opt A: backoff+jitter) | [M] |
| OBS-API-05 | No GET retry/dedup; cold-start 5xx → hard error | 2.0 | P2 | INIT-12 | Incorporate (Opt A: GET-only retry) | [M] |
| OBS-CACHE-04 | Player-data keys omit league/format → stale/bleed | 1.6 | P1 | INIT-07 | Incorporate (Opt A: key scoping) — land with/before CACHE-01 | [M] |
| OBS-RENDER-03 | ManualRanks `renderItem` re-creates per keystroke | 1.6 | P2 | INIT-11 | Incorporate (Opt A: extract edit row) | [M] |
| OBS-NET-05 | Player JSON `DYNAMIC`, no Cache-Control | 1.6 | P2 | INIT-10 | Incorporate (merged into ROUTE-03) | [W] |
| OBS-DB-06 | League member/community-ELO re-read + Python aggregate | 0.8 | P2 | INIT-14 | Incorporate (Opt B: server cache) | [B] |
| OBS-DB-07 | `upsert_league_members` N select-then-write | 0.8 | P3 | INIT-14 | Incorporate (Opt A: bulk upsert) | [B] |

## Wave 3 — Larger / lower-priority / documentation

| OBS | Title | RICE-P | Sev | Initiative | Decision | Scope |
|-----|-------|------:|:---:|------------|----------|:---:|
| OBS-ROUTE-02 | Compression edge-only; origin uncompressed | 4.8 | P2 | INIT-10 | Alternative (document infra invariant; Flask-Compress optional) | [B] |
| OBS-NET-02 | Client never sets `Accept-Encoding` | 5.0 | P3 | INIT-15 | Alternative (document platform-gzip reliance; no code) | [M] |
| OBS-API-02 | Add `Accept-Encoding: gzip` to wrapper | ~~12.0~~→0 | P1→P3 | INIT-15 | **Reject for mobile** (measured no-op); fold into INIT-15 doc | [M] |
| OBS-RENDER-06 | StrengthBar 24 slivers/card | 3.0 | P3 | INIT-11 | Defer (cheap polish; Opt B reduce segments) | [M] |
| OBS-DB-04 | Cold cache: serial dual-CSV + redundant table read | 0.75 | P1 | INIT-02 | Incorporate (Opt A: parallelize CSV; merged into NET-01) | [B] |
| OBS-API-06 | `getNewPartners` double-fetches activity feed | 0.8 | P3 | INIT-16 | Defer | [M] |
| OBS-ROUTE-07 | Single-league matches latent silent-drop (not perf) | 0.75 | P3 | — | Defer (correctness note, not perf) | [B] |
| OBS-RENDER-07 | MatchesScreen derived arrays/chips | 2.0 | P3 | — | Reject/No-op (verified acceptable) | [M] |
| OBS-DB-03 (Opt B) | session_init replay-from-snapshot | (6.4 parent) | P1 | INIT-08 | Defer (golden-ELO test required; W3+) | [B] |

## Standing infra recommendation (not a code initiative)

| Item | Source | Decision |
|------|--------|----------|
| Render free-tier cold start (30–60 s) is the irreducible P0 floor; `--workers 1` is a contention bottleneck | OBS-NET-01/03/04, OBS-ROUTE-03/04/06, OBS-DB-04 (all reference it) | **Escalate to user:** external warm-ping (UptimeRobot, ~10 min) masks ~90% of sessions for $0; the only complete fix is the $7/mo always-on dyno + `--workers 2`. No code change removes a true cold start. |

---

## Roll-up by initiative

| Init | Title | Member OBS | Peak RICE-P | Wave |
|------|-------|-----------|------:|:---:|
| INIT-01 | Decouple splash from network boot legs | NET-03, CACHE-02 | 16.0 | 1 |
| INIT-02 | Cold-start player cache (bake + parallelize) | NET-01, DB-04 | 9.6 | 1 |
| INIT-03 | Memoize ELO/stats recompute | DB-03 | 6.4 | 1 |
| INIT-04 | Extend navigation prefetch beyond Trios | CACHE-05 | 6.4 | 1 |
| INIT-05 | Wire focusManager/onlineManager | CACHE-03 | 6.0 | 1 |
| INIT-06 | Throttle `touch_user_activity` | ROUTE-04 | 5.6 | 1 |
| INIT-07 | Persisted query cache + key scoping | CACHE-01, CACHE-04 | 4.3 | 2 |
| INIT-08 | session_init slim + optimistic shell | NET-04, ROUTE-06 | 4.0 | 2 |
| INIT-09 | Prune trade-generation candidates | DB-02 | 4.3 | 2 |
| INIT-10 | Web player-payload (slim+ETag+compress+rebind) | ROUTE-01/02/03/05, NET-05 | 5.4 | 2 |
| INIT-11 | Render memoization + Tiers virtualization | RENDER-01/02/03/05/06, CACHE-06 | 3.2 | 2–3 |
| INIT-12 | API client resilience (timeout+retry+warm dedup) | API-01/04/05 | 4.0 | 1–2 |
| INIT-13 | Trade-status poll backoff (net+render) | API-03, RENDER-04 | 3.0 | 2 |
| INIT-14 | DB hygiene (index, bulk upsert, match narrow, Trends SQL) | DB-01/05/06/07 | 3.2 | 1–2 |
| INIT-15 | Compression/encoding documentation | NET-02, API-02 | (doc) | 3 |
| INIT-16 | League activity double-fetch | API-06 | 0.8 | defer |
