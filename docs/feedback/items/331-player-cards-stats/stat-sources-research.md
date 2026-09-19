# FB #331 + #332 — NFL stat-source research

**Purpose:** decide where FTF sources the player statistics required by feedback **#331** (clickable player cards: age, career year-by-year, per-game splits, weekly game logs) and **#332** (in-season opportunity metrics — snap counts, targets, trending up/down).
**Author:** research task, **2026-08-15**. Research and recommendation only — no production code, config, or feature flags were touched.
**Method:** live web verification, plus **direct probing of Sleeper's live endpoints and nflverse's release files on 2026-08-15**. Every external claim is cited. Unverified items are marked **[unverified]**; conclusions drawn rather than read are marked **[inference]**.
**Covers feedback IDs:** 331, 332 (filed under the lower ID per [items/README.md](../README.md)).

---

## Bottom line

**Both features are buildable, and cheaply — but not from one source, and there is one thing money can't easily buy.**

1. **#331 (player cards) is essentially free and already in-stack.** Sleeper — the API FTF already depends on — has an *undocumented* stats endpoint carrying full weekly game logs, season totals, and per-game splits back to **2009**, keyed by the same `player_id` FTF already stores. Age/DOB is already in the `players/nfl` bulk file FTF already downloads. **No new vendor, no new mapping layer, no new cost.**

2. **#332 (opportunity metrics) is 80% free too — better than expected.** The same Sleeper endpoint carries **`off_snp` and `tm_off_snp`** (so snap share is computable), **`rec_tgt`** (target share computable by summing a team-week), **`rec_air_yd`**, and red-zone fields **`rec_rz_tgt` / `rush_rz_att` / `pass_rz_att`** — all weekly, back to **2020** for snaps. I verified this live, including 2026 preseason data posted the day after the game. That covers every metric #332 names except one.

3. **The one thing nothing affordable covers is _routes run / route participation_.** Free sources have it only *after the postseason ends* (nflverse's participation dataset is an annual February drop and, verbatim, **"does not update during the season"**). The commercial vendor sweep found **no self-serve vendor at any price** selling in-season routes run; it is effectively PFF/FTN-licensed and sales-gated. **If #332's "route participation" line item is load-bearing, it should be cut or explicitly deferred — it cannot be delivered in-season on this budget.** Snap share plus target share are the accepted stand-ins.

4. **The real blocker is licensing, and it is not new.** Sleeper's own docs say the API is **"free to use for non-commercial purposes"** and that commercial use requires contacting them for a licence. Fleeced is a commercial app. **This exposure already exists today for league/roster data** — it is not created by #331/#332, but these features deepen it (showing a user *their own league* is a different posture from redistributing league-wide NFL statistics). **The cheap, honest fix is to email Sleeper and ask for a commercial licence — they explicitly invite the conversation.** That call should be made before #332 ships, and it de-risks the whole app, not just this feature.

5. **If Sleeper says no** (or the operator wants a licence-clean backbone regardless), the fallback is **nflverse** — free, **CC BY 4.0, commercial use explicitly permitted**, snap counts back to 2012 refreshed 4×/day in-season, delivered as sub-megabyte parquet files over plain HTTPS. It costs one thing: a **player-ID mapping layer**, because Sleeper has stopped populating the cross-reference IDs nflverse keys on (verified below — Ja'Marr Chase, Bijan Robinson, Brock Bowers and Jayden Daniels all have `gsis_id: null` in Sleeper today).

6. **Paid fallback if both fail: SportsDataIO commercial** — the only *verified* paid vendor with weekly snap counts (back to 2012, posted 6am ET next day). Caveat: **its $99/mo self-serve tier strips the snap fields out**; snaps require a sales-gated contract at an unpublished price.

**Recommended plan:** ship #331 on Sleeper now (zero marginal cost, zero new integration). Open the Sleeper commercial-licence conversation in parallel. Build the #332 ingestion so the stats source is swappable, so nflverse can replace Sleeper without touching the feature. Cut in-season routes run from scope.

---

## 1. What the two items actually require

| Requirement | Item | Notes |
|---|---|---|
| Bio: DOB/age, team, position, college | #331 | Already in FTF's Sleeper `players/nfl` ingestion |
| Career year-by-year stat lines | #331 | Dynasty users evaluate multi-year trajectories — history depth matters |
| Per-game splits (per-game averages alongside season totals) | #331 | Derivable from season totals ÷ games played, or from weekly rows |
| Weekly game log, drill-down from a season | #331 | Needs per-week rows with opponent |
| Snap counts + snap share | #332 | **Discriminating requirement** |
| Targets + target share | #332 | |
| Carries | #332 | |
| Route participation / routes run | #332 | **Hardest requirement — see §6** |
| Red-zone usage | #332 | |
| Air yards | #332 | |
| Weekly deltas for trending up/down | #332 | Needs weekly granularity on all of the above |

---

## 2. Sleeper's undocumented stats endpoint — the headline finding

**Status: VERIFIED by direct probe on 2026-08-15.** This is not documented at [docs.sleeper.com](https://docs.sleeper.com/) — the official docs cover only Players, Leagues, Drafts, Users, State and Avatars. The stats endpoints live on a *different host* (`api.sleeper.com`, not `api.sleeper.app`) and are undocumented, the same gray-zone posture as the projections endpoint FTF already researched in [#169](../169-outlook-league-summary/projection-source-research.md).

### Endpoints

| Shape | Returns |
|---|---|
| `GET api.sleeper.com/stats/nfl/{season}/{week}?season_type=regular` | Every player's stat line for that week (~2.1 MB, ~2,300 rows) |
| `GET api.sleeper.com/stats/nfl/player/{player_id}?season={y}&season_type=regular&grouping=week` | One player's full weekly game log for a season |
| `GET api.sleeper.com/stats/nfl/player/{player_id}?season={y}&season_type=regular&grouping=season` | One player's season totals |

Third-party documentation of the shapes: [sleeper-api-client.readthedocs.io](https://sleeper-api-client.readthedocs.io/en/latest/endpoints/stats.html). `season_type=post` also works (verified: 893 rows for 2024 postseason week 1).

### Coverage — measured, not assumed

| Question | Answer | Evidence |
|---|---|---|
| **History depth** | **2009 → present.** 2008 and earlier return `[]` | Probed 1999, 2005–2013 individually; 2009 is the first non-empty season |
| **Snap counts** | **2020 → present.** `off_snp`, `def_snp`, `st_snp` + team denominators `tm_off_snp`, `tm_def_snp`, `tm_st_snp` | Bisected 2013–2024; 2019 returns 0 players with `off_snp`, 2020 returns 664 |
| **Field count** | **229 distinct stat fields** in a single regular-season week | Union across all rows, 2024 week 1 |
| **Targets** | `rec_tgt` — present from 2009 | |
| **Red zone** | `rec_rz_tgt`, `rush_rz_att`, `pass_rz_att`, `rz_att`, `rz_conv`, `rz_pct` | |
| **Air yards** | `rec_air_yd`, `pass_air_yd` | |
| **Carries / efficiency** | `rush_att`, `rush_yac`, `rush_btkl`, `rec_drop`, `rec_yar`, `cmp_pct`, `pass_rtg` | |
| **Routes run** | **ABSENT.** No field matching `rout`/`rte` in all 229 | |
| **Per-game splits** | Derivable — `gp`, `gs`, `gms_active` present alongside season totals | |
| **Fantasy points** | `pts_ppr`, `pts_half_ppr`, `pts_std`, plus `pos_rank_*` | |

**Snap share and target share are both computable.** Verified worked example, 2024 week 1: a Baltimore receiver with `off_snp: 43` / `tm_off_snp: 80` → **53.7% snap share**; `rec_tgt: 8` against a team total of 40 → **20% target share**.

> **Ingestion gotcha worth writing down:** the weekly list endpoint mixes player rows with **team-defense rows**, which carry a team abbreviation in `player_id` and use `rec_tgt` to mean *targets allowed*. Summing `rec_tgt` naively doubles every team's target total (BAL week 1 2024 reads 80 instead of 40). Filter to numeric `player_id` before aggregating.

### Freshness — measured live

- **2026 preseason data is already flowing.** Preseason week 1 (games 2026-08-13) returned **3,049 rows with 614 players carrying `off_snp`**, last updated 2026-08-14 15:09 UTC — i.e. **snap counts landed roughly a day after kickoff, right now, in the current season.**
- Across all 2,102 rows of 2025 regular-season week 5, `updated_at` sits at a median of **~38h after the game date**, 10th percentile ~17h. `updated_at` is a *last-modified* stamp, so this measures when values **settle** (after Tuesday/Wednesday stat corrections), not first post. **[inference]** first publication of box-score fields is same-day; snap counts next-day.

### Integration shape

REST/JSON, **no auth, no API key**. A full historical backfill is ~320 calls (2009–2026 × ~18 weeks), trivially inside the published **1,000 calls/minute** guidance. Steady state is **one call per week per week-in-progress** — it slots straight into the existing `/api/cron/*` daemon-thread pattern guarded by `CRON_SECRET` (`backend/server.py`, see the `players-refresh` job at line ~1630 for the established shape). Rows key natively on Sleeper `player_id`, which `players_table` already stores — **zero mapping work**.

### Licensing — the problem

This is the part that decides everything.

> "The Sleeper API is a read-only HTTP API that is **free to use for non-commercial purposes**… For commercial use, please reach out to us directly to discuss licensing."
> — [docs.sleeper.com](https://docs.sleeper.com/), retrieved 2026-08-15

> "…for your **personal and non-commercial use**" / prohibits "rent, lease, lend, sell, redistribute, sublicense, copy, reverse engineer, decompile, translate, modify… or otherwise inappropriately use the Services"
> — [Sleeper General Terms of Use](https://support.sleeper.com/en/articles/5486620-general-terms-of-use) §9.2, last updated 2026-07-24

§11.1 additionally prohibits use of "automated scripts or other automated means." Sleeper also notes its statistics come from third-party providers (§5.25), so it is redistributing under its own upstream licences.

**Assessment:**

- **This exposure already exists.** FTF's core league/roster/player integration runs on the same API under the same clause. #331/#332 do not create the risk.
- **They do change its character.** **[inference]** showing a user their own league data is a materially weaker claim of harm than compiling and redistributing league-wide NFL statistics as a product feature. A licence conversation is more clearly warranted once stats ship.
- **⚠️ Corrects a stale internal claim.** [`docs/business/product/2026-07-17-monetization-research-appendix.md`](../../../business/product/2026-07-17-monetization-research-appendix.md) line 57 states Sleeper has *"no ToS restricting commercial use."* **That is factually wrong** — docs.sleeper.com states the opposite in plain language. That line should be corrected.
- **The fix is cheap.** Sleeper invites the conversation. An email asking for written permission to use the public read-only API (including the stats endpoints) in a paid consumer app costs nothing and, if granted, resolves the largest single legal question hanging over the product.
- **Residual risk even with permission:** the stats endpoints are **undocumented** and can be changed, throttled or removed without notice — same standing caveat already logged for the projections endpoint in #169.

---

## 3. nflverse — the licence-clean fallback

**Verdict: usable in a paid commercial app, with attribution.** This is the only free source that clears licensing outright.

- **Licence: CC BY 4.0** on [`nflverse/nflverse-data`](https://github.com/nflverse/nflverse-data) (SPDX `CC-BY-4.0`, full `LICENSE.md` in repo). CC BY 4.0 permits you to "remix, transform, and build upon the material **for any purpose, even commercially**" ([creativecommons.org](https://creativecommons.org/licenses/by/4.0/deed.en)). Requirement: **visible attribution** — ship a "Data via nflverse (CC BY 4.0)" credit.
- **Exception — FTN-derived datasets are CC BY-**SA** 4.0**: `load_participation()` (2023+) and `load_ftn_charting()` require attribution to "FTN Data via nflverse" and carry a **ShareAlike** obligation ([load_participation docs](https://nflreadr.nflverse.com/reference/load_participation.html)). ShareAlike against a closed-source app is **ambiguous — needs a direct read/legal check** before exposing FTN-derived fields.
- **⚠️ Upstream chain-of-title caveat.** nflverse states: "NFL data accessed by this package belong to their respective owners, and are governed by their terms of use" ([nflverse.nflverse.com](https://nflverse.nflverse.com/)). nflverse can CC-license its *compilation*, not the underlying facts — and its snap counts are scraped from Pro Football Reference, whose own terms forbid that use (§5 below). **[inference]** practical exposure is low (raw sports statistics are largely uncopyrightable facts in the US, and enforcement would target nflverse rather than a downstream consumer), but it is not a clean chain. Flag for the operator, not a blocker.

### Coverage

| Dataset | Years | In-season cadence ([schedule doc](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html)) |
|---|---|---|
| `snap_counts` (from PFR) | **2012–2025** | "updates every day at 0, 6, 12, 18 UTC during the season" |
| `stats_player_week` | 1999–2025 | nightly after each game day, plus intraday on game days |
| `players` | all | daily (file observed refreshed 2026-08-15 08:21 UTC) |
| `rosters` / `weekly_rosters` | 1920 / 2002 → **2026** | daily 07:00 UTC |
| `pbp` | 1999–2025 | nightly; raw data "usually available within 15 minutes after a game has ended" |
| `pfr_advstats` | 2018–2025 | in-season |
| `pbp_participation` (routes) | 2016–2025 | **"It does not update during the season!"** |
| `injuries` | 2009–2024 | **broken** — "Our data source died after the 2024 season" |

`stats_player_week_2025.parquet` is 19,422 rows × **150 columns**, including `targets`, `target_share`, `carries`, `receiving_air_yards`, `air_yards_share`, `racr`, `wopr`, plus EPA fields. `snap_counts` gives `offense_snaps`, `offense_pct`, `defense_snaps`, `defense_pct`, `st_snaps`, `st_pct`. **Red-zone usage is not a column** — derive from `load_pbp()` on `yardline_100 <= 20`.

- ⚠️ **`player_stats` is deprecated** — release body reads `DEPRECATED 2025-08-01: USE stats_player OR stats_team INSTEAD`.
- ⚠️ **`nfl_data_py` is dead** — GitHub reports `archived: true`, "deprecated in favour of nflreadpy… No further maintenance or updates are planned." Use [`nflreadpy`](https://nflreadpy.nflverse.com/) (MIT, active, Polars-native) — or skip the client and read the parquet URLs directly with `pyarrow`.

### Integration shape

Plain HTTPS parquet/CSV, **no auth, no key, no rate limit**, sub-megabyte files (snap counts ~240 KB/season; weekly stats ~855 KB/season):

```
https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_2026.parquet
https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2026.parquet
https://github.com/nflverse/nflverse-data/releases/download/players/players.parquet
```

Each release carries a `timestamp.json` for cheap change detection. A nightly job would fetch 3–5 files, upsert into new tables, and recompute weekly deltas. `pyarrow` is **already installed** in this environment (v23.0.1).

### ⚠️ The cost nobody mentions: the ID-join problem

**VERIFIED by direct probe, 2026-08-15.** nflverse keys on `gsis_id`; `players.csv` (25,033 rows, 39 columns) exposes `gsis_id, esb_id, nfl_id, pfr_id, pff_id, otc_id, espn_id, smart_id` — **and no `sleeper_id`**. Meanwhile Sleeper has largely **stopped populating** the IDs that would bridge the gap:

| Join key | Coverage among Sleeper players who recorded a snap in 2025 wk 1 (n=582) |
|---|---|
| `gsis_id` | **30%** |
| `espn_id` | **38%** |
| `sportradar_id` | **100%** — but nflverse doesn't carry it |

Spot-check: **Ja'Marr Chase, Bijan Robinson, Brock Bowers and Jayden Daniels all return `gsis_id: null` and `espn_id: null` from Sleeper today.** An `espn_id` join matched only **216 of 991** rostered skill players.

**Consequence:** adopting nflverse means building and maintaining a **name + team + position + DOB fuzzy-matching layer** — tractable, but a real source of silent mismatch bugs on exactly the players users care most about (rookies and stars). The alternative, `dynastyprocess/data`'s `db_playerids.csv` (which does map `sleeper_id`), is **GPL-3.0 on a data repo — ambiguous** for bundling into a proprietary app; that would need a legal read too.

**This asymmetry is the strongest practical argument for Sleeper-first:** Sleeper's stats rows key natively on the `player_id` FTF already stores.

---

## 4. Commercial vendors

### SportsDataIO — the only *verified* paid snap-count source

Fields confirmed in the commercial [NFL data dictionary](https://sportsdata.io/developers/data-dictionary/nfl): `OffensiveSnapsPlayed`, `DefensiveSnapsPlayed`, `SpecialTeamsSnapsPlayed`, `OffensiveTeamSnaps`, `SnapCountsConfirmed` — **all from 2012**, documented as "available the morning after the game." `ReceivingTargets` from 2009. Dedicated red-zone endpoints (`Player Game Red Zone Stats`, Inside Five, Inside Ten). **No routes run. No air yards.**

- **⚠️ The catch:** a diff of the [Discovery Lab dictionary](https://discoverylab.sportsdata.io/developers/data-dictionary/nfl) against the commercial one shows the **self-serve tier contains no snap-count integers at all** — only a boolean `Played`. Snap counts require the sales-gated commercial contract.
- **Discovery Lab pricing** ([discoverylab.sportsdata.io](https://discoverylab.sportsdata.io/personal-use-apis/nfl)), branded "**personal use APIs**": Fantasy **$599/season or $99/mo** (100 calls/day); Fantasy + Odds **$899/season or $149/mo** (1,000 calls/day). Free tier = last season's data, no card.
- **Commercial pricing: not published.** Sales contact required ([sportsdata.io/nfl-api](https://sportsdata.io/nfl-api)).
- **Licensing: ambiguous — needs direct read/legal check.** The public [ToS](https://sportsdata.io/terms-of-service) is a generic *website* ToS granting only "a limited, non-exclusive, non-transferable, non-sublicenseable right and license… to access and use our products." It says nothing about caching, storage, or redistribution to end users. Redistribution rights live in the negotiated agreement. The Discovery Lab "personal use" framing means **[inference]** it should not be assumed to cover a paid App Store app.
- **Integration:** REST/JSON + CSV, API-key auth. One `Player Game Stats - by Week [Final]` call per night in-season fits inside even the 100/day cap; the 2012→present backfill is what would blow it.

### MySportsFeeds — cheapest genuine commercial licence

- **Pricing** ([mysportsfeeds.com/feed-pricing](https://www.mysportsfeeds.com/feed-pricing/), **Canadian dollars**): Personal from **$5/mo**, Commercial from **$39/mo** for CORE feeds + non-live. You'd need the **STATS** add-on for game logs, so the real number is above the floor. Rate limits not published.
- **Snap counts / routes / air yards: not documented publicly** (schemas are login-gated). **[inference] NO** on all three — these are premium fields and MSF is a budget provider.
- **⚠️ Data-quality risk:** their own [FAQ](https://www.mysportsfeeds.com/faq/) states "MySportsFeeds is its own data source. We use a **crowd-sourced model**, backed by our own data entry staff." For an app whose trade valuations depend on stat accuracy, that is a different risk class from official feeds.
- **Licensing: ambiguous — needs direct read/legal check.** The [Terms of Use](https://www.mysportsfeeds.com/terms-use/) is a generic website ToU with no data-redistribution grant.

### Fantasy Nerds — best licensing clarity, wrong product

- **Pricing** ([api.fantasynerds.com/getting-started/pricing](https://api.fantasynerds.com/getting-started/pricing)): **Standard $499/yr** — "For personal use, hobby projects, **or commercial use by businesses with fewer than 1,000 paying customers OR less than $500K in annual gross revenue**"; **Extended Commercial $2,999/yr** above those thresholds. **A pre-revenue solo app unambiguously qualifies for $499.** This is the clearest indie-friendly commercial language in the entire field.
- **But the coverage is wrong** ([docs](https://api.fantasynerds.com/docs/nfl)): projections, rankings, ADP, dynasty rankings, depth charts, injuries, add/drops. **No snap counts, no targets, no target share, no routes, no air yards, no red zone, no career history, no weekly game logs of actual stats.** It fails #331 entirely and nearly all of #332.
- **Worth remembering for a different problem:** its consensus **dynasty rankings** and **add/drop trends** endpoints are relevant to FTF's Elo/value work — but that is not this feature.

### Sportradar — out of budget

No public pricing; B2B contract via [developer.sportradar.com](https://developer.sportradar.com/api_packaging). 30-day "Base" trial with real production data. The [NFL overview](https://developer.sportradar.com/football/reference/nfl-overview) mentions "Player participation" entered "1 hour after completion of the game" but does not expose a snap-count schema — **ambiguous, needs a trial key and a direct schema read**. **[inference]** enterprise-priced and implausible pre-revenue. Note the official NFL data rights (official PBP + Next Gen Stats) sit with **Genius Sports through the 2029 season** ([announcement, 2025-06-11](https://www.geniussports.com/newsroom/the-national-football-league-expands-and-extends-strategic-partnership-with-genius-sports-in-multi-year-deal/)) — enterprise only.

### Tank01 (RapidAPI) — has snaps, has no terms

> **Corrected 2026-08-15**, superseding this section's original "[inference] unlikely
> to carry snap counts". A follow-up vendor scan verified the opposite.

Pricing (verified against [tank01.com](https://www.tank01.com/) and the RapidAPI plan
strip): Basic free (1,000 hits/month, no card), Pro **$10/mo** (1,000/day), Ultra
**$25/mo** (15,000/day), Mega **$100/mo** (500,000/day), $0.01 per overage request.

**Coverage — snaps ✅.** `snapCounts {offSnap, defSnap, stSnap}` *and*
`offSnapPct/defSnapPct/stSnapPct` per game; targets, carries, per-game logs
(`getNFLGamesForPlayer`), bio incl. `bDay`/`age`. No routes, no air yards, no
per-player red zone. Career year-by-year is **not exposed** — roster
`statsToGet` is "current season only", and historical rosters only go back to
2023-05-05.

**Field evidence is unofficial.** RapidAPI's playground is JS-rendered, so the
schema evidence comes from a community TypeScript client's Zod definitions
([acypert/tank01-nfl-ts-client](https://github.com/acypert/tank01-nfl-ts-client/blob/main/src/players/schemas.ts)),
not from Tank01's own docs. Treat snap coverage as strongly indicated, not proven.

**The one genuinely interesting thing here:** the player payload carries
cross-reference IDs — `sleeperBotID`, `fRefID`, `espnID`, yahoo, cbs, rotowire.
If that holds, Tank01 could serve as the **ID bridge that makes the nflverse path
cheap**, since the whole cost of the licence-clean route is the missing
Sleeper↔`gsis_id` join (§3). A ~$10/mo mapping table is a very different
proposition from a hand-maintained fuzzy matcher. **Worth a free-tier probe.**

**Licensing: ❌ unusable as-is.** Tank01 publishes **no terms of service at all**.
RapidAPI's own ToS disclaims the relationship: the terms "are between API Providers
and API Consumers (not Rapid)" ([rapidapi.com/page/terms](https://rapidapi.com/page/terms),
updated 2026-05-13). Commercial use, caching, and display are therefore undefined —
needs written confirmation from support@tank01.com before any dependency.

### Highlightly — the cleanest licence found, but no snaps

**Coverage** ([docs](https://highlightly.net/documentation/american-football/)):
per-game box scores with Passing/Rushing/Receiving/Defense groups incl. **Total
Receiving Targets**, receptions, rushing attempts; player bio with **birth date**,
height, weight, positions; `/players/{id}/statistics`. **No snap counts, no snap
share, no routes, no air yards, no per-player red zone.** Career totals are claimed
in marketing but not enumerated in the docs — unverified. Seasons of history not
stated anywhere; needs a probe.

**Cost:** Basic **$0** (100 req/day, player stats included), Pro **$7.99/mo**
(7,500/day), Ultra **$18.99/mo**, Mega **$44.99/mo**. Up to 40% cheaper direct than
via RapidAPI.

**Licensing: ✅ the clearest in this entire report**
([highlightly.net/terms](https://highlightly.net/terms/) §6.1, verified):
"Distribution, transfer, and storage of the data provided by the Service are
allowed. You are free to use the data in your applications and products." The only
bar is reselling API access itself or acting as a pass-through proxy. §6.4 puts
logo/image rights on you.

**So:** Highlightly is a licence-clean, ~$8/mo answer to **#331 alone** — bio, age,
per-game logs, targets — with zero legal ambiguity. It cannot serve #332, because
it has no snaps. Freshness: box scores refresh every minute.

### API-Sports — explicitly disclaims fantasy rights

Free 100/day; PRO 15.00/mo, ULTRA 25.00/mo, MEGA 35.00/mo (currency symbol does not
render on the page — EUR vs USD unconfirmed). Per-game player stats from 2022 for
player statistics endpoints.

**No snaps, no snap share, no routes, no air yards, no target share, no red zone.**

**Ruled out on licensing.** [api-sports.io/terms](https://api-sports.io/terms):
"We do not provide a 'license' for the use and publication of the data provided by
our services on applications, websites or any other products made by the user," and
use "for … **fantasy sports platforms** … may require additional licenses from the
relevant rights holders." A vendor that explicitly disclaims granting you rights for
your exact product category is not a foundation to build on.

### SportsGameOdds — the termination clause disqualifies it for dynasty

Odds-first but does carry `receiving_targets`, `receiving_receptions`,
`rushing_attempts`, plus **team-level** red-zone trips. No snaps, no routes, no air
yards. Only **up to 2 years** of history. Rookie **$99/mo**, Pro **$299/mo**.

Licensing permits display to end users, but
[terms](https://sportsgameodds.com/terms) v3 require that on termination you
"permanently delete or destroy all Data… including from databases, cache, and
backups" within 30 days. For an app whose value *is* accumulated history, renting
data that must be destroyed when you stop paying is a structural product risk, not
just a cost.

### Sportmonks — does not exist for NFL

Soccer, cricket, and Formula 1 only. Ruled out.

---

## 5. Ruled out on licensing — do not use

These are the ones that die on terms, not coverage. Listed explicitly rather than presented as options.

| Source | Why it's out |
|---|---|
| **ESPN endpoints** (`site.api.espn.com`) | Terms resolve to [disneytermsofuse.com](https://disneytermsofuse.com/english/) §2.A: licence is "for **your personal, noncommercial use only**"; §2.B.x separately bars access "using a **robot, spider, script, or other automated means**… or otherwise compiling, building, creating or contributing to any collection of data." Two explicit, unambiguous prohibitions. Coverage is moot — the advanced fields (`offensiveSnapPct`, `targetSharePct`, `yardsPerRouteRun`) exist in the schema but returned **`0.0`** for Ja'Marr Chase 2024. |
| **NFL.com / api.nfl.com / Next Gen Stats** | All probed live 2026-08-15: **401** or dead host. [NFL Terms](https://www.nfl.com/legal/terms/) §1.3: "solely for your own individual **non-commercial** and informational purposes"; "**Systematic retrieval of data**… to create or compile… a **database**… is prohibited absent our express prior written consent." |
| **Pro Football Reference / Sports Reference** | Their [ToU §5](https://www.sports-reference.com/termsofuse.html) opens permissively ("welcomed, whether for commercial or non-commercial purposes") but subordinates it to **5(i)**: you may not use their data "to create any database, archive, or other data store that competes with or constitutes a material substitute for the services or data stores offered on the Site." Their [data-use page](https://www.sports-reference.com/data_use.html) says it plainly: "**you should not create websites or tools based on data you scrape from Sports Reference.**" Weekly game logs are additionally **robots-disallowed** (`Disallow: /players/*/*/gamelog`, `/splits`, `/red-zone-*`), rate-limited to 20 req/min with day-long bans, and now behind a Cloudflare managed challenge. Custom licensing starts at **"a minimum of $5,000"** and "For some of our datasets, our licenses completely preclude any redistribution." **Stathead ($9/mo) confers no redistribution rights.** |
| **FantasyPros** | Premium **$8.99/mo** is a "**Personal-use license**… Personal & non-commercial apps" ([api-data](https://www.fantasypros.com/api-data/)). Commercial licence is sales-gated. Also, per prior internal research in [#169](../169-outlook-league-summary/projection-source-research.md), personal keys bar building "a product that competes with FantasyPros." And it has **no snap counts, routes, or target share** in the API regardless. |
| **`dynastyprocess/data`** ID map | Would solve the Sleeper↔nflverse join, but is **GPL-3.0 applied to a data repo — ambiguous** copyleft exposure for a proprietary app. Needs a legal read before bundling. |

---

## 6. Routes run — the requirement nothing affordable covers

**This is the single most decision-relevant finding in this document.**

#332 asks for "route participation." Here is the complete picture as of 2026-08-15:

- **nflverse `load_participation()` — not discontinued, but functionally dead in-season.** Verbatim: "Participation data prior to 2023 is from NFL NGS. Participation data from 2023 onwards is courtesy of **FTN** and is **provided after all post-season games are completed**" ([docs](https://nflreadr.nflverse.com/reference/load_participation.html)). The schedule article is blunter: "**It does not update during the season!**" Verified from release-asset timestamps: 2023+2024 backfilled 2025-09-04; the 2025 file posted **2026-02-10**. The 2024 season had **no participation data at all for roughly a year** ([nflfastR issue #487](https://github.com/nflverse/nflfastR/issues/487)). It is absent from nflverse's automation-status table — a manual annual drop, not a pipeline.
- **Even when present, it isn't really routes run.** `load_participation()` gives `offense_players` (the gsis_ids on the field per play) and a `route` field that covers **only the primary receiver on the play**. True per-player routes run must be *derived* by counting appearances in `offense_players` on dropbacks — a proxy, not charted routes. And it carries the **CC BY-SA** ShareAlike question (§3).
- **FTN Data** is the realistic paid source — its NFL Participation Feed carries `skp_role(1–5)` with values `RTE, FRTE, BRTE, PPRO, FPRO, RBL, FHO, RUN` (per-play route-running role for five skill players) plus a Charting feed with route type, depth of target and separation. FTN is already nflverse's participation supplier, so a direct deal is the natural upgrade path. **Pricing [unverified]** — `ftndata.com` did not resolve during this research; search results indicate a **~$599 CSV tier** (3 seasons) and a mid-tier REST/JSON API with participation history since 2019. **Needs a direct read / sales contact.**
- **Fantasy Points Data Suite** has routes run by alignment, but it is a **consumer dashboard subscription** ($48–$299/yr per [their plans page](https://www.fantasypoints.com/plans)), **not a redistributable data licence**. Buying it does not give you the right to put the numbers in your app.
- **PFF** is the traditional source of charted routes; no self-serve indie API surfaced. **[unverified] / not researched** in depth.
- **The commercial vendor sweep found no self-serve vendor at any price selling in-season routes run.** SportsDataIO: no route fields. MySportsFeeds, Fantasy Nerds, Tank01: no. Sportradar/Genius: enterprise.

### Recommendation on this requirement

**Cut in-season route participation from #332's scope, or defer it explicitly.** Three honest options, in order of preference:

1. **Drop it.** Ship #332 on snap share + target share + air-yard share + red-zone usage + carries. These are the metrics that actually drive breakout calls, and they're all available weekly and free.
2. **Ship routes as a prior-seasons feature only**, refreshed each February from `load_participation()` — clearly labelled as through-last-season. Requires resolving the CC BY-SA question first.
3. **Buy FTN** if in-season routes are genuinely a headline differentiator. Get a real quote before committing; treat the ~$599 figure as unconfirmed.

---

## 7. Comparison matrix

| Source | Coverage vs requirements | Cost | Licensing (paid consumer app) | Freshness | Integration shape |
|---|---|---|---|---|---|
| **Sleeper stats** (undocumented) | Bio ✅ · career **2009+** ✅ · game logs ✅ · splits ✅ · **snaps + snap share 2020+ ✅** · targets ✅ · target share ✅ (derive) · air yards ✅ · red zone ✅ · **routes ❌** | **Free** | **❌ as-is** — "free… for **non-commercial** purposes"; commercial needs a licence conversation. Exposure already exists today. | Snaps ~T+1 day; verified live in 2026 preseason | REST/JSON, no auth, 1k calls/min. **Keys natively on Sleeper `player_id` — zero mapping.** ~320 calls to backfill |
| **nflverse** | Bio ✅ · career **1999+** ✅ · game logs ✅ · **snaps + share 2012+ ✅** · targets + target_share ✅ · air yards + share ✅ · red zone ⚠️ (derive from pbp) · **routes ⚠️ annual only** | **Free** | **✅ CC BY 4.0** — "even commercially", attribution required. FTN-derived subsets are **CC BY-SA — ambiguous**. Upstream PFR chain = residual risk | Snaps 4×/day in-season (0/6/12/18 UTC); stats nightly + intraday | Plain HTTPS parquet, no auth, <1 MB/file. **Needs a Sleeper↔gsis fuzzy-match layer** |
| **SportsDataIO** (commercial) | Bio ✅ · career ✅ · game logs ✅ · **snaps 2012+ ✅** · targets ✅ · red zone ✅ · **air yards ❌** · **routes ❌** | **Unpublished** (sales-gated). Self-serve $99–149/mo **excludes snaps** | **Ambiguous — needs legal check.** Public ToS grants no redistribution right; that's in the negotiated contract. Discovery Lab is "personal use" | Snaps "the morning after the game"; 6am ET next-day | REST/JSON + CSV, API key. 1 call/night in-season; backfill blows the daily cap |
| **MySportsFeeds** | Bio ✅ · game logs ✅ · targets ✅ · **snaps [inference] ❌** · routes ❌ | **CAD $39/mo** commercial floor + STATS add-on | **Ambiguous — needs direct read.** Commercial tier exists and is explicit about redistribution | Live/non-live tiers | REST/JSON, basic auth. **⚠️ crowd-sourced data entry** |
| **Fantasy Nerds** | ❌ fails #331 and nearly all of #332 — projections/rankings only | **$499/yr** (qualifies at FTF's scale) | **✅ clearest commercial language in the field** | Live | REST/JSON, API key |
| **Tank01** (RapidAPI) | Bio ✅ · career ❌ (current season only) · game logs ✅ · **snaps + snap share ✅** *(community-schema evidence)* · targets ✅ · **routes ❌** · air yards ❌ · red zone ❌ · **carries `sleeperBotID` + `gsis`-adjacent cross-IDs** | **$10–25/mo** | **❌ no ToS published at all**; RapidAPI disclaims the relationship. Needs written OK | Box scores immediate; rosters hourly | REST/JSON via RapidAPI. **Candidate ID bridge for the nflverse path** |
| **Highlightly** | Bio ✅ (incl. DOB) · career ⚠️ claimed, unverified · game logs ✅ · targets ✅ · **snaps ❌** · routes ❌ · air yards ❌ · red zone ❌ | **$0 / $7.99/mo** | **✅ clearest licence in this report** — §6.1 permits distribution, storage, and use in your products | Box scores every minute | REST/JSON. **Serves #331 only** |
| **API-Sports** | Player stats 2022+ · game logs ✅ · **snaps ❌** routes ❌ air yards ❌ red zone ❌ | 15–35/mo (currency unconfirmed) | **❌ explicitly disclaims granting publication rights, and names fantasy platforms as needing further licences** | 30s in-game | REST/JSON |
| **SportsGameOdds** | Targets ✅ · carries ✅ · red zone team-only ⚠️ · **snaps ❌** · **history ≤2 yrs** | **$99–299/mo** | ⚠️ display permitted, but **on-termination purge of all cached data** — structural risk for dynasty | Real-time | REST/JSON |
| **Sportradar / Genius** | Likely full ✅ incl. participation **[unverified]** | Enterprise, unpublished | Contract | 1h post-game | REST + push |
| **FTN Data** | **Routes ✅ in-season** — the only one | ~$599+ **[unverified]** | **[unverified]** — sales contact | In-season | REST/JSON or CSV |
| **ESPN / NFL.com / PFR / Stathead / FantasyPros Premium** | — | Free / $9–$9k | **❌ non-commercial or anti-database clauses** (§5) | — | — |

---

## 8. Recommendation

### Primary: Sleeper's stats endpoint — for **both** items

Not because it's free, but because it is the only source that is *already integrated, already keyed correctly, and covers ~90% of both feature specs*. The measured facts: 2009+ history for #331, 2020+ snaps and full opportunity metrics for #332, next-day freshness verified in the live 2026 preseason, and **no player-ID mapping layer** — which is the hidden cost that makes every alternative meaningfully more expensive to build and more fragile to operate.

**Conditional on the licensing action below.**

### The licensing action — do this first, it's cheap

**Email Sleeper and ask for written permission** to use their public read-only API (explicitly including the `api.sleeper.com/stats/*` endpoints) in a paid consumer app, per the invitation on docs.sleeper.com. This is a one-email task with a large payoff: it resolves the biggest legal question hanging over the *entire product*, not just this feature. **Ship #331 on Sleeper regardless** — it's a strict subset of the risk the app already carries. **Hold #332's public launch until there's an answer, or until the fallback is wired**, because redistributing league-wide usage statistics is a harder posture to defend than showing a user their own league.

### Fallback: nflverse — if Sleeper declines or goes silent

Free, CC BY 4.0, commercially clean, better history (1999+ stats, 2012+ snaps), and better in-season cadence (4×/day vs ~daily). It costs a **name+team+position+DOB matching layer** and a visible attribution line. **Build the ingestion behind a source-abstraction seam from day one** so this swap is a config change, not a rewrite — that seam is the single highest-leverage design decision here.

### Paid fallback: SportsDataIO commercial — only if both above fail

Before spending anything, ask sales two specific questions: **(a)** the price of the smallest package containing `OffensiveSnapsPlayed` / `OffensiveTeamSnaps`, and **(b)** written confirmation that caching and displaying to end users in a paid app is permitted. Take the free Discovery Lab tier meanwhile to validate the ingestion shape — just design for the snap fields being null there.

### Do the two items want different sources?

**No — and that's the useful answer.** Sleeper covers both, and so does nflverse. Splitting sources would mean maintaining two ingestion paths and two ID mappings for no coverage gain. **The one genuine split is routes run**, which neither covers in-season and which should be cut (§6) rather than sourced separately.

### Explicit scope cut

**In-season route participation is not deliverable at this budget.** Nothing free has it during the season; nothing self-serve sells it at any price. Confirm with the operator that #332 ships without it before build starts — this is the item most likely to cause a "that's not what I asked for" moment at QA.

---

## 9. Open questions for the operator

1. **Sleeper commercial licence — send the email?** Y/N. Blocks #332's clean launch; already an unresolved exposure for the whole app.
2. **Routes run — cut, defer to a prior-seasons-only view, or fund FTN?** Needs an answer before #332 is scoped.
3. **CC BY-SA on FTN-derived nflverse fields** — legal read needed if we ever expose participation/charting data.
4. **nflverse upstream chain-of-title (PFR)** — accept the residual risk, or avoid nflverse snap counts specifically?
5. **`dynastyprocess/data` GPL-3.0 ID map** — legal read, or build our own fuzzy matcher?
6. **Attribution surface** — if nflverse is adopted, where does the "Data via nflverse (CC BY 4.0)" credit live in the UI? (Chalkline has no existing pattern for a data-attribution line.)

---

## 10. Follow-ups suggested by this research

- **Correct the stale claim** in `docs/business/product/2026-07-17-monetization-research-appendix.md` line 57 ("no ToS restricting commercial use") — contradicted by docs.sleeper.com.
- **Add a `docs/references/sleeper/stats-api/` entry** capturing the verified endpoint shapes, the 229-field list, the 2009/2020 coverage boundaries, and the team-defense-row aggregation gotcha, per the [references convention](../../../references/README.md). That reverse-engineering work is done and shouldn't be repeated.
- **Feature-scope blocks** for #331 and #332 per the four-gate convention in root `CLAUDE.md`, once the operator answers Q1 and Q2.

---

## Sources

Retrieved **2026-08-15** unless noted.

**Sleeper** — [docs.sleeper.com](https://docs.sleeper.com/) · [General Terms of Use](https://support.sleeper.com/en/articles/5486620-general-terms-of-use) (updated 2026-07-24) · [stats endpoint shapes](https://sleeper-api-client.readthedocs.io/en/latest/endpoints/stats.html) · live probes of `api.sleeper.com/stats/nfl/*` and `api.sleeper.app/v1/players/nfl`

**nflverse** — [nflverse-data](https://github.com/nflverse/nflverse-data) · [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.en) · [load_snap_counts](https://nflreadr.nflverse.com/reference/load_snap_counts.html) · [load_participation](https://nflreadr.nflverse.com/reference/load_participation.html) · [data update schedule](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html) · [nflverse.nflverse.com](https://nflverse.nflverse.com/) · [nflreadpy](https://nflreadpy.nflverse.com/) · [nflfastR issue #487](https://github.com/nflverse/nflfastR/issues/487)

**Commercial vendors** — [SportsDataIO NFL data dictionary](https://sportsdata.io/developers/data-dictionary/nfl) · [Discovery Lab](https://discoverylab.sportsdata.io/personal-use-apis/nfl) · [Discovery Lab dictionary](https://discoverylab.sportsdata.io/developers/data-dictionary/nfl) · [SportsDataIO ToS](https://sportsdata.io/terms-of-service) · [MySportsFeeds pricing](https://www.mysportsfeeds.com/feed-pricing/) · [MySportsFeeds FAQ](https://www.mysportsfeeds.com/faq/) · [MySportsFeeds ToU](https://www.mysportsfeeds.com/terms-use/) · [Fantasy Nerds pricing](https://api.fantasynerds.com/getting-started/pricing) · [Fantasy Nerds NFL docs](https://api.fantasynerds.com/docs/nfl) · [Sportradar packaging](https://developer.sportradar.com/api_packaging) · [Sportradar NFL overview](https://developer.sportradar.com/football/reference/nfl-overview) · [Tank01 on RapidAPI](https://rapidapi.com/tank01/api/tank01-nfl-live-in-game-real-time-statistics-nfl) · [Genius Sports / NFL deal](https://www.geniussports.com/newsroom/the-national-football-league-expands-and-extends-strategic-partnership-with-genius-sports-in-multi-year-deal/)

**Ruled out** — [Disney/ESPN Terms of Use](https://disneytermsofuse.com/english/) · [NFL.com Terms](https://www.nfl.com/legal/terms/) · [Sports Reference ToU](https://www.sports-reference.com/termsofuse.html) · [SR Data Use](https://www.sports-reference.com/data_use.html) · [SR bot traffic](https://www.sports-reference.com/bot-traffic.html) · [FantasyPros API](https://www.fantasypros.com/api-data/)

**Routes run** — [FTN NFL data catalog](https://ftnfantasy.com/ftn-data-nfl-catalog) · [Fantasy Points plans](https://www.fantasypoints.com/plans)

**Internal prior art** — [#169 projection-source research](../169-outlook-league-summary/projection-source-research.md) · `docs/plans/sleeper-write-capture-runbook.md` (Sleeper ToS analysis) · `docs/business/product/2026-07-17-monetization-research-appendix.md` (contains the stale claim corrected above)
