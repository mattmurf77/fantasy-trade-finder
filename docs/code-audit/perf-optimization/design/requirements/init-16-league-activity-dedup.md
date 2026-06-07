# REQ — INIT-16: League Activity Double-Fetch

- **Initiative / Wave / Scope:** INIT-16 · Deferred · [M]
- **Source observations:** OBS-API-06
- **Peak RICE-P:** 0.8

## Problem statement

`getNewPartners(leagueId)` (`league.ts:282–303`) derives its result by issuing a
full `GET /api/league/activity?league_id=…&limit=50` network request. The League
screen separately renders the activity feed, typically via its own call at
`limit=20`. When both the feed and the "new partners" banner are shown on the
same screen, the underlying activity data is fetched twice — once at limit 20
for the feed display, and once at limit 50 for the partners derivation — with no
shared cache between the two calls at the API layer. The partners derivation is
intentionally client-side (the function's own comment at `league.ts:275–281`
notes there is "no dedicated backend route"), making this a straightforward
client-side consolidation opportunity.

## User stories

- As a **dynasty manager** opening the League tab, I want the screen to load with
  a single network request for activity data rather than two, so that the tab
  paints faster and uses less data on cellular.

## Functional requirements

- **FR-1 (single fetch at limit 50):** The League screen should fetch the
  activity feed once at `limit=50` and pass the result to both the feed view and
  the new-partners banner derivation. The separate `getNewPartners` network call
  is eliminated; its `getActivityFeed(leagueId, 50)` sub-call is replaced with
  the already-loaded events.

- **FR-2 (pure derivation helper):** Extract the partners-derivation logic from
  `getNewPartners` into a pure `derivePartnersFromEvents(events)` helper so it
  can be called client-side without a network hop.

- **FR-3 (limit ≥ 50):** The consolidated single fetch must use `limit=50` (not
  20) to ensure `derivePartnersFromEvents` sees a wide enough window to surface
  older `unlock` events. The activity feed display may render fewer items from
  the 50-event window.

## Acceptance criteria

- [ ] **AC-1 — Single request:** Opening the League tab while both the activity
  feed and the new-partners banner are visible results in exactly one
  `GET /api/league/activity` request (not two). Verify with a network inspector
  or by checking that the `limit=50` response is used for both surfaces.

- [ ] **AC-2 — Partners banner correct:** The new-partners banner surfaces the
  same `unlock` events it did before the consolidation. Partners discovered more
  than 20 events ago (but within the 50-event window) continue to appear.

- [ ] **AC-3 — Feed display correct:** The activity feed renders the same events
  it did before the consolidation (order and content unchanged).

## Related components

- `mobile/src/api/league.ts:282–303` — `getNewPartners` (OBS-API-06)
- `mobile/src/api/league.ts:287` — `getActivityFeed(leagueId, 50)` sub-call
- `mobile/src/api/league.ts:178–205` — `getActivityFeed` (full network GET)
- `mobile/src/api/league.ts:275–281` — comment confirming client-side derivation
- League screen (consumer of both feed and partners banner)

## Prerequisite components / dependencies

None. This is a self-contained client-side refactor of the League tab's data
fetching. Best coordinated with whoever owns the League screen's query
structure, in case the screen has already been reworked by the time this is
picked up.

## Non-functional requirements & invariants

- **Off the critical path:** The League tab is not on the player/trade first-
  paint path. This change does not affect cold-start latency, trio rendering, or
  trade generation. It is a polish/efficiency improvement for a secondary tab.
- **No ELO or tier invariant:** Activity feed data is social/transactional.
  No ranking math is touched.
- **Rollback:** If the consolidated fetch reveals a limit-sizing bug (banner
  missing events outside limit=20), widen the limit; the architecture change
  (single fetch) is not the risk.

## Out of scope

- Adding a dedicated backend route for new partners (the client-side derivation
  is explicitly the documented approach).
- Any change to other tabs or the player/trade critical path.
- Performance improvements to the activity feed backend endpoint itself.

---

> **Defer rationale:** RICE-P 0.8 (Reach 2, Impact 0.5, Confidence 80%, Effort 1).
> This is a clean double-fetch that is worth fixing, but it is off the player/trade
> critical path, affects only the secondary League tab, and the body saved is small
> (activity feed is not a large payload). It is explicitly deferred until the
> higher-priority player/trade initiatives (Waves 1–3) are shipped. Revisit when
> the team has League tab capacity.
