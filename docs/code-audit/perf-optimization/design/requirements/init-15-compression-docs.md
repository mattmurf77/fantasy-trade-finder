# REQ — INIT-15: Compression/Encoding Documentation

- **Initiative / Wave / Scope:** INIT-15 · Wave 3 · [M]/[B]
- **Source observations:** OBS-NET-02, OBS-API-02, OBS-ROUTE-02
- **Peak RICE-P:** documentation only (OBS-API-02 corrected from ~~12.0~~ to ~0 mobile impact)

## Problem statement

Three audit observations independently surfaced the 4.84 MB `/api/sleeper/players`
payload as a compression/encoding concern. Agent 01 (OBS-API-02) scored it at
RICE-P 12.0 and recommended adding `Accept-Encoding: gzip` to the mobile API
wrapper. Agent 06 (OBS-NET-02) **measured** that the mobile client never fetches
the full body (it uses the 25-byte `/warm` endpoint), and that RN's `fetch`
(NSURLSession on iOS, OkHttp on Android) auto-injects `Accept-Encoding: gzip`
and decompresses transparently. This resolves OBS-API-02's 12.0 score as a
**measured ~0 mobile impact** — the high score was correct at the time it was
written (Confidence was explicitly set to 50% because "does RN already negotiate
gzip?" was unverified) but is superseded by OBS-NET-02's direct measurement.

Additionally, OBS-ROUTE-02 observed that Flask/gunicorn origin emits uncompressed
bodies and relies entirely on Cloudflare edge compression. This is a latent infra
dependency, not a user-facing slowdown, and is documented rather than mitigated
with code.

This initiative is **documentation only**: no mobile code changes, no backend
code changes.

## User stories

- As a **developer** reading OBS-API-02 in the findings archive, I want to know
  that the 12.0 RICE-P score was superseded by measurement and is not an open
  action item, so that I do not spend time implementing a no-op change.
- As an **operator** evaluating infra resilience, I want a runbook entry that
  explicitly records the Render/Cloudflare edge-compression dependency, so that
  any future infra change (CDN swap, direct origin access, non-CF proxy) does not
  silently regress end-user compression and inflate the wire payload 7×.
- As a **developer** adding a custom networking layer to the mobile client, I want
  a documented note that platform-default gzip negotiation must not be stripped,
  so that the mobile client does not accidentally start downloading multi-MB
  payloads uncompressed.

## Functional requirements

- **FR-1 (runbook entry — edge compression invariant):** Add an entry to
  `docs/runbook.md` documenting that: (a) the Flask/gunicorn origin emits
  uncompressed response bodies (no Flask-Compress configured as of the audit);
  (b) end-user compression is provided by the Render/Cloudflare edge layer;
  (c) the dependency on edge compression must be re-evaluated if the infra is
  migrated away from Render/Cloudflare. Reference: OBS-ROUTE-02, measured by
  agent-03 (`Accept-Encoding: identity` → origin returns 4,837,423 B;
  `Accept-Encoding: gzip` → edge returns 676,415 B with `server: cloudflare`).

- **FR-2 (runbook entry — mobile gzip auto-negotiation):** Add an entry to
  `docs/runbook.md` documenting that: (a) the mobile client (`client.ts:136–147`)
  does not set an explicit `Accept-Encoding` header; (b) RN's `fetch`
  (NSURLSession/OkHttp) auto-injects `Accept-Encoding: gzip` and decompresses
  transparently — this is the platform default; (c) a future custom networking
  layer (e.g. replacing the native `fetch` bridge) must preserve this behavior
  or explicitly set `Accept-Encoding: gzip` to avoid silent regression to
  uncompressed downloads. Reference: OBS-NET-02 (measured directly by agent-06).

- **FR-3 (reconciliation note — OBS-API-02 corrected RICE-P):** Add a note
  in the optimization plan or as a cross-reference in the observations that
  OBS-API-02's RICE-P 12.0 is corrected to **~0 mobile impact** for the
  following reasons, all measured:
  1. The mobile client calls `/api/sleeper/players/warm` (25 bytes), not
     `/api/sleeper/players` (4.84 MB). Source: `mobile/src/api/sleeper.ts:47`;
     confirmed by agent-06 measurements.
  2. RN auto-injects `Accept-Encoding: gzip` and decompresses without client code.
     Source: agent-06 OBS-NET-02 direct measurement.
  3. All other mobile JSON bodies on the first-paint path are already ≤ ~1.5 KB
     (measured by agent-06, measurements §2/§4), so compression of any flavor
     saves only a few hundred bytes.
  The note must be explicit that this is not a reject of OBS-API-02's concern
  but a **correction of the impact estimate** based on measurement. The
  observation remains relevant for the **web client** (which does fetch the full
  body), and that web-side concern is addressed by INIT-10.

- **FR-4 (optional Flask-Compress note):** Record in the runbook (or as an
  extension of FR-1's entry) that Flask-Compress could be added to the origin to
  provide resilient origin-side compression independent of the edge layer. This
  would reduce the origin→edge transfer size (a secondary benefit) and remove the
  edge dependency for correctness. Any implementation must verify no
  double-encoding (`Vary: Accept-Encoding` must be preserved and the CF edge must
  not double-compress). This is documented as an **optional future hardening**,
  not a required action for any wave of this plan.

## Acceptance criteria

- [ ] **AC-1 — Runbook: edge compression entry:** `docs/runbook.md` contains an
  entry that describes the Render/Cloudflare edge-compression dependency (FR-1).
  The entry references OBS-ROUTE-02 and states the measured uncompressed origin
  size (4,837,423 B) and the compressed wire size (~676 KB via Cloudflare).

- [ ] **AC-2 — Runbook: mobile gzip entry:** `docs/runbook.md` contains an entry
  that documents RN platform-default `Accept-Encoding` auto-injection (FR-2) and
  the requirement that any future custom networking layer preserve this behavior.
  The entry references OBS-NET-02.

- [ ] **AC-3 — OBS-API-02 reconciliation is recorded:** Either the
  `observations/agent-01-api-client/findings.md` file, the
  `plan/optimization-plan.md`, or the `plan/priority-matrix.md` contains a
  clear note that OBS-API-02's 12.0 RICE-P is corrected to ~0 mobile impact,
  with the three measured reasons listed in FR-3. The correction notes that
  the web-side concern is addressed by INIT-10.

- [ ] **AC-4 — No code changes:** Zero lines of source code (`mobile/`, `backend/`,
  `web/`) are modified by this initiative. All changes are in `docs/`.

- [ ] **AC-5 — Flask-Compress option documented:** The runbook entry from FR-1
  (or a linked note) mentions Flask-Compress as an optional future hardening and
  calls out the double-encoding risk.

## Related components

- `mobile/src/api/client.ts:136–147` — header block (no `Accept-Encoding`); OBS-API-02, OBS-NET-02
- `mobile/src/api/sleeper.ts:47` — mobile calls `/warm`, not the full body; OBS-NET-02
- `backend/server.py:803` — Flask app init (no compression middleware); OBS-ROUTE-02
- `render.yaml:13` — `--workers 1`, gunicorn config; context for origin-side risk
- `docs/runbook.md` — target file for the new entries
- `docs/code-audit/perf-optimization/plan/optimization-plan.md` — section §2 "reconciliation" (FR-3 target)
- `docs/code-audit/perf-optimization/plan/priority-matrix.md` — OBS-API-02 row (FR-3 target)

## Prerequisite components / dependencies

None. This initiative is documentation-only and has no code dependencies.
It may land in any order relative to other initiatives, though it is most
useful when landed after INIT-10 (which addresses the web-side payload concern
that OBS-API-02 actually identifies) so the reconciliation note can reference
the completed initiative.

## Non-functional requirements & invariants

- **No code changes:** This is a documentation-only initiative. Any file edit
  outside `docs/` would violate the initiative's scope. If a reviewer finds a
  code change in the diff, it was added in error and must be reverted.
- **Accuracy of reconciliation:** The corrected RICE-P (~0 mobile) must be
  grounded in the three specific measured facts listed in FR-3. It must not
  overstate certainty: the platform gzip auto-injection is a well-documented RN
  behavior confirmed by agent-06's direct measurement, but any future RN
  architecture change (e.g. custom JSI networking) could re-open the question.
  The runbook entry must note this contingency.
- **Distinction from INIT-10:** INIT-15 records the resolution of the mobile
  compression question. INIT-10 addresses the actual web payload problem. The
  runbook entries must not conflate the two.

## Out of scope

- Any code change to `client.ts`, `server.py`, or `web/js/app.js`.
- Adding Flask-Compress (documented as optional in FR-4; not required by this initiative).
- Adding brotli (`Accept-Encoding: gzip, br`) to the mobile client (OBS-NET-02
  Option B — near-zero benefit since the full body is not on the mobile path).
- StrengthBar sliver reduction (OBS-RENDER-06 — deferred separately).
- INIT-16 league activity double-fetch (deferred separately).
