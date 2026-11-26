# Add a platform: the go/no-go procedure

> How `platforms-pm` decides whether FTF should link a new league platform, and in what
> order to build it. Distilled from how it was actually done:
> `docs/plans/espn-league-linking-plan-2026-07-11.md` (ESPN, conditional GO) and
> `docs/plans/multi-platform-linking-plan-2026-07-17.md` (MFL GO, Fleaflicker GO,
> Yahoo DEFER, FFPC NO-GO). Read both before starting a new one. They are the quality bar:
> facts with citations, crosswalk coverage measured rather than guessed, live probes, and
> a phased conditional recommendation.

## Contents

- [The steps](#the-steps)
- [Precedent sizes](#precedent-sizes)
- [The go/no-go memo](#the-gono-go-memo)
- [Open instance: Fleaflicker](#open-instance-fleaflicker)

## The steps

1. **Demand evidence.** Who is asking, and how many? Get the numbers from
   `analytics-lead`: feedback mentions of the platform, `signin_*` method values, and
   linked-league platform counts. Never query them yourself. The standing demand gate is
   **≥2 real users asking**. ESPN's mutual features and all of Yahoo were held behind it.
   An operator ask is evidence too; record it verbatim with its date.
2. **API surface and auth model.** Is the API official and documented, or the unofficial
   one the platform's own clients use? List hosts, endpoints, public-vs-private
   semantics (which status codes mean private, absent or purged), how often endpoints
   have churned, and which community clients exist (ffscrapr and the like). Live **read**
   probes are run by `platforms-eng` (through `head-product` → `head-eng`, workers on
   `eng-integrations`). **No write probe without the operator's approval at the time it
   runs.** ESPN's write probe used `items: []`, so nothing could be created (D-039, ESPN
   entry).
3. **Player-id crosswalk coverage.** Measure the platform's id column in DynastyProcess
   `db_playerids.csv` on two bases: the value-relevant pool (skill players with dynasty
   value > 0) and all rows that carry a `sleeper_id`. Report both percentages. Name and
   position matching is a fallback, never the design center. Watch for decoy columns:
   Fleaflicker's own id column was 0.6% filled, so it joins on `sportradar_id` instead.
   A new id column means re-cutting the snapshot fixture. Every linked platform maps to
   **Sleeper player ids**, which ties it to Sleeper's player DB (see the register's E2).
4. **Dynasty relevance.** Are future draft picks available over the API? Taxi squads?
   Rookie drafts? What share of dynasty leagues does the platform hold (cite the
   FantasyPros and DLF platform guides with their dates)? A redraft-heavy platform is a
   product mismatch as well as an integration cost (Yahoo, multi-platform plan §4).
5. **Auth UX and App Store risk.** Rank the options: zero-auth public reads, OAuth,
   WebView credential capture (the Sleeper and ESPN pattern), or the user's password
   transiting FTF. Avoid the last; the MFL auth-link does it today, and device-side
   PRD goal G2 exists to stop it. Rate App Store Guideline 5.2.2 exposure. The consent
   copy must describe the reads *and* writes honestly. ESPN's copy still says read-only
   while `espn.send` is ON, which is the failure mode to avoid.
6. **ToS and rate posture → a new register row.** Read the user terms and any developer
   terms live. Fill every field of a register block in
   [platform-risk-register.md](platform-risk-register.md): rate limits, registration and
   User-Agent rules, what FTF would read and write, kill-switch flag, agreement status,
   warning signs, pre-planned response. The row is written **before** Phase 1 ships.
   If terms bar what the integration needs, say so plainly and mark it **review with a
   professional**.
7. **Effort against precedent.** Size each phase S/M/L against the table below and name
   the platform-specific costs: host routing, client registration, token refresh
   infrastructure, cookie fragility, and so on.
8. **Phasing.** The default order, each step behind its own flag and default OFF:
   - **Phase 0, spike:** an isolated `backend/<platform>_service.py`, CLI-driven and
     fixture-tested, plus one live smoke read against a real public league.
   - **Phase 1, link and read** (flag `<platform>.link`): the storage seam
     (`upsert_platform_league`, synthetic member ids such as `mfl:{league}.f{franchise}`),
     link/leagues/import routes, a link sheet, and the platform badge. The platform enum
     is a cross-client invariant.
   - **Phase 1b, picks:** map future picks into `draft_picks` (MFL was the first
     platform where this worked).
   - **Phase 2, roster features:** the engine is platform-agnostic; this is mostly
     wiring and copy.
   - **Phase 3, mutual features:** held behind the demand gate.
   - **Send (write):** last, on a separate flag, through SKILL.md's write-feature gate.
9. **Parity column.** Add the platform as a column in `/pm-technical`'s
   `references/platform-parity.md`: reads, writes, and honest-unsupported behavior per
   feature. That file is draft PR #346 (branch `skill/platform-parity`); if it has not
   landed, list the column contents in the memo for `/pm-technical` to fold in.
10. **The go/no-go memo** (below), ending in **Decisions needed** + **Handoffs**.

## Precedent sizes

| Platform | Phase 1 | Picks | Notes |
|---|---|---|---|
| ESPN | M | none (ESPN models only current-draft slots) | Unofficial API; cookie capture (D-021); writes reversed to a gated GO (D-039, ESPN entry) |
| MFL | M | +M | Official API; per-league `wwwNN` hosts; registration; ≥1 s spacing |
| Fleaflicker | S | S–M | Official public JSON; zero auth; built, dark |
| Yahoo | L | ? | OAuth2 + hourly refresh infra; 70.1% crosswalk; deferred |
| FFPC | L–XL | n/a | No public API, no crosswalk; NO-GO |

## The go/no-go memo

Save beside the build it feeds: `docs/plans/<platform>-linking/go-no-go-YYYY-MM-DD.md`
(the scope block from `docs/templates/feature-scope.md` lands in the same folder if the
answer is GO). Shape:

```
# <Platform> linking: go/no-go (YYYY-MM-DD)
Recommendation up front: GO / conditional GO / DEFER behind <gate> / NO-GO until <trigger>
## Demand evidence (measured / assumed, via analytics-lead)
## API surface + auth model (cited, probe dates, who ran them)
## Crosswalk coverage (value pool % / all sleeper-mapped rows %)
## Dynasty relevance
## Auth UX + App Store risk
## ToS + rate posture (register row added: link)
## Effort vs precedent, phasing, flags
## Platform-parity column
## Riskiest assumption & cheapest next step
## Decisions needed
## Handoffs
```

## Open instance: Fleaflicker

Phase 1 was built and test-green on 2026-07-18 (multi-platform plan §8b) and has been dark
ever since (`fleaflicker.link` false). Nobody has made the call. A go/no-go needs:
- demand evidence from `analytics-lead` (any Fleaflicker mention in feedback since
  2026-07-18);
- fresh live read probes from `platforms-eng` (the 2026-07-17 probes are stale) and a
  re-check of crosswalk coverage;
- the register row, now a baseline (no terms date, no published limits). Whether to
  write to `info@fleaflicker.com` about limits is the operator's call;
- one of three answers for the operator: light Phase 1 (through `release-lead`), keep it
  dark with a dated revisit trigger, or remove the code (`head-eng`'s call on the code
  itself).
