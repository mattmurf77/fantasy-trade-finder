# Send-a-trade-to-MFL — feasibility (exploration only, NOT built)

Part of #177. Question: can FTF propose a trade directly back into MFL the
way "Send in Sleeper" does for Sleeper?

## Short answer

Yes — and unlike Sleeper, it would ride a **sanctioned, documented API**.
MFL's import API includes first-class trade endpoints. Verified against
`api.myfantasyleague.com/2026/api_info?STATE=details` (2026-07-25):

- `import?TYPE=tradeProposal` — params `L` (league id), `OFFEREDTO` (target
  franchise id), `WILL_GIVE_UP` / `WILL_RECEIVE` (comma-separated asset id
  lists), optional `COMMENTS`, `EXPIRES` (unix ts), `FRANCHISE_ID`
  (commissioner impersonation only). "Access restricted to league owners" —
  i.e. requires the authed cookie #177 now stores.
- `import?TYPE=tradeResponse` — `L`, `TRADE_ID` (from the pending-trades
  export), `RESPONSE` = `accept` | `reject` | `revoke`, optional `COMMENTS`.
  Means accept/withdraw flows are also possible later, not just propose.

This is the opposite risk profile from Sleeper's path: no ToS exposure, no
Cloudflare evasion, no captured private GraphQL. The blockers are all
plumbing on our side.

## What FTF would need

1. **Cookie freshness.** #177 stores the `MFL_USER_ID` cookie
   (Fernet-encrypted). Lifetime is undocumented; MFL supports a
   `login?...&PERIOD=` style persistence but we treat any 401/403 as
   `mfl_auth_expired` and re-prompt. A send flow needs the same treatment:
   pre-flight the cookie (cheap `myleagues` call) and route to re-sign-in on
   failure. Season boundary: cookies are minted per `{year}` path — verify
   whether a 2026 cookie authenticates 2027 requests before relying on it.
2. **Franchise mapping.** Sender franchise comes free (myleagues
   `franchise_id`, already persisted as `platform_my_team`). `OFFEREDTO`
   needs the counterparty franchise id — we already store synthetic member
   ids `mfl:{league}.f{franchise}`, so it's parseable today.
3. **Asset id mapping (the real work).**
   - *Players:* FTF works in Sleeper player ids; `WILL_GIVE_UP`/`WILL_RECEIVE`
     take MFL player ids. Reverse crosswalk exists (DP `mfl_id` is the
     primary key) but coverage must be checked send-side: an unmapped player
     must **hard-block** the send (never silently drop an asset from an
     offer).
   - *Picks:* MFL trades can include picks. **UNVERIFIED assumption** (from
     common MFL client behavior, not the docs fetched): future picks encode
     like `FP_0005_2027_1` (franchise/year/round) and current-year draft
     picks like `DP_02_05` (round/slot, zero-based). We already store
     `futureDraftPicks` raw per league, which carries the ground-truth ids —
     verify the exact wire format against a live sandbox league before
     building.
4. **Server surface.** A `POST /api/trades/propose-mfl` (or a `platform`
   switch on the existing propose route) gated behind a new flag, hard-gated
   like Sleeper's (verified session), with the same #180 pre-flight pattern
   (roster membership + roster-limit checks against a fresh `rosters`
   export).
5. **Mobile surface.** `SendInSleeperButton` currently self-gates to Sleeper
   leagues; an MFL send needs either a platform-aware send button or a
   sibling component, plus copy that is honest about where the offer lands.

## Risks / open questions

- **Response semantics unverified**: the import API's success/error body
  shape for `tradeProposal` (XML `<status>OK</status>` vs error text) needs
  a live probe; build the adapter with an injected opener + recorded
  fixtures, same as the rest of `mfl_service.py`.
- **Pick id wire format unverified** (above) — highest-risk assumption.
- **Commissioner-mediated leagues**: leagues can disable owner-initiated
  trades; expect and surface a clean rejection.
- **Rate limits**: same ≥1s spacing + registered `MFL_USER_AGENT` guidance
  applies to imports.
- **Asymmetry warning for UX**: MFL offers expire (`EXPIRES`); default it
  (e.g. 7 days) rather than sending never-expiring offers.

## Recommendation

Feasible and lower-risk than the Sleeper write path. Sequence it after
`mfl.auth_link` proves cookie durability in the field (we'll learn real
cookie lifetimes from `mfl_auth_expired` rates), and only after the pick id
format is verified against a sandbox league. Estimated build: adapter +
route + tests ~1 day; reverse-crosswalk guardrails + mobile surface ~1 day.
