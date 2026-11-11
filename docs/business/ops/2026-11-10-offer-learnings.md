# Offer learnings and fast deck release — 2026-11-10

**Status: backend and web live with the features on; iOS 1.22.0 (184) built and uploaded to App Store Connect; Apple processing, tester availability and device checks unverified.**
The operator's instruction (2026-11-10, then away): "see these changes through to completion of
code and merge them, push to testflight and turn it on". Later the same day: "New wording
approved" (the Terms and Privacy wording for the Sleeper offers read).

All times UTC, 2026-11-11.

## Release scope

Two merges to `main`, both merge commits (not squashes):

| PR | Merge | What |
|---|---|---|
| [#641](https://github.com/mattmurf77/fantasy-trade-finder/pull/641) | `0baf6360`, 05:02 | The fast deck (contains #638) and the offer-learnings programme, every new flag off. Deck pipeline 15 → 21 |
| [#643](https://github.com/mattmurf77/fantasy-trade-finder/pull/643) | `13865d73`, 05:27 | Seven flags on; the approved Terms and Privacy wording published; four test files that assumed the flags ship off |

On in production from `13865d73`:

| Flag | Effect |
|---|---|
| `trade.fast_deck` | A cold Find a Trade build serves the proven first 150 cards instead of the full inventory |
| `trade.fit_first_copy` | The fit block (version 3): league ranks before and after, an outlook tag for both teams |
| `trade.pass_reason_cadence` | Pass reasons asked after 3 passes, then quiet for 5 |
| `trade.outcome_tracking` | Outcomes of offers sent from the app |
| `trade.next_move` | Revised-offer and middle-ground cards lead the deck |
| `grading.revision4_round` | The revision 4 Calibration round (`outlook-v2-v4-1`) beside the current one |
| `trade.sleeper_offer_import` | The private read of a user's own Sleeper trade offers, only after they turn on the Settings switch |

Off on purpose: revision 4 as the serving engine (`owner_bilateral_revision_4_enabled`),
`trade.partner_activity` (both graded first), `trade.fast_deck_shadow` (ignored while serve is
on), `grading.revision4_arm` (inert while the round is on).

Specs: [offer-learnings plan](../../plans/offer-learnings/plan.md) ·
[fast deck scope](../../plans/realtime-trade-engine/scope.md) ·
[configuration](../../config-reference.md).

## Evidence and limits

- **CI:** all four checks passed on `2fa889ff` (#641, run `42958684033`, backend tests 40 min)
  and on `6df59c3f` (#643, run `42963163983`). Each merge was pinned to the tested head.
- **Local, Python 3.12:** full backend suite on `6df59c3f`: **14,346 passed, 42 skipped, 0
  failed**. Mobile on the release checkout: `tsc --noEmit` clean, **172 of 172** structural
  checks, testID lint, the EAS archive check. Web: **260 of 260** structure checks.
- **The first full run of the turn-on found 15 failures**, all tests that read the shipped
  config and assumed the new flags were off. Fixed in the tests; no product code changed.
- **Not verified:** anything on a device (D-056: no simulator). The fast deck was turned on
  without the shadow day the plan recommended, so its agreement with the full engine is proven
  on 247 recorded requests offline and not on Render. The private Sleeper read has run from the
  server only against fixtures. No user had searched between the deploy and 06:18, so no
  `fast deck:` line had been logged; the same log search found no `ERROR` or `Traceback` line.

## Execution record

| Time | Step | Result |
|---|---|---|
| 05:02 | Merge #641 | `0baf6360` |
| 05:04 | Render deploy `dep-dbpvdrjncjis73cgor40` | live; all ten new flags present and off; the three new tables present; `/`, `/terms`, `/privacy`, `/api/feature-flags` 200 |
| 05:27 | Merge #643 | `13865d73` |
| 05:28 | Render deploy `dep-dbpvpfm7bikc738d3vng` | live; the seven flags read on; `pass_reason_cadence` = `{ask_after: 3, quiet_for: 5}`; `/terms` and `/privacy` carry the new wording |
| 05:28 | `eas build --profile production --platform ios --auto-submit` from `13865d73` (tree identical to `6df59c3f`) | build `55914797-24b5-4035-a5cf-c894facbad57`, **1.22.0 (184)**; submission `f439db03-04e9-48b9-ae3f-0a8a05174932`. Build FINISHED 05:35:21; submission FINISHED 05:35:34 (uploaded). Apple processing and tester availability were not checked |
| 05:29 | `POST /api/admin/grading/pregenerate`, `round_id: outlook-v2-v4-1` | 16 connected account/league pairs queued (12 Sleeper, 2 ESPN, 2 MFL; 7 verified users, 2 with no connected league). By 06:17: **11 ready, 5 failed** (`provider_settings_unsupported` 2, `league_membership_required` 1, `provider_account_binding_unavailable` 1, `provider_cross_domain_eligibility` 1; the current round's rebuild on 2026-11-09 also had 5 provider failures). 200 cards selected, 175 per engine, 150 shared; both engines hold the same 337 unique trades, so revision 4 changed order, not inventory |

**Version.** The app stays 1.22.0: the What's New entry (the policy-change notice) is keyed to
that version, and builds 181 to 183 are 1.22.0 as well. Only the build number moved.

## Terms and Privacy

The operator approved the wording. Published in `web/terms.html` §6 ("Trade outcomes", verbatim
from the [scope block](../../plans/offer-learnings/scope-sleeper-offer-read.md) §0.7) and in
`web/privacy.html` §1, §3, §4, §5 and §6. Both effective dates moved from November 6 to
November 10, 2026, as the Terms promise for a material change. Consent version
`offer-import-1`.

At release the app was stricter than the published line: it read nothing until the user turned
on "Use my Sleeper trade offers". **Changed 2026-11-11** on the operator's answer ("Yes to
sleeper data"): trades sent from the app are followed without the switch, as the line says, so
revised-offer cards reach every Send in Sleeper user. The switch adds the user's other offers.

## Follow-up, 2026-11-11 (#645, `811341f8`, live 08:12)

Two server-only changes from the operator's first look at build 184; no new build.

- **Fit block copy (D-228).** A team with no supported reason read "Gets X, gives Y", repeating the card. It now reads a league-rank fact ("Still RB 2nd", "Up at RB, down at WR"). On 21 recorded production requests about four leads in ten are this fallback; none names a player.
- **Sleeper read (D-227).** Trades sent from the app are followed without the Settings switch.

## Rollback

| Surface | Trigger | Step |
|---|---|---|
| Any one feature | Wrong cards, errors in the deck worker, a complaint | Set its flag false in `config/features.json`, merge, then `POST /api/feature-flags/reload`. Code defaults are all false |
| Fast deck | A `fast deck:` error line, or decks that end early with an error | `trade.fast_deck` false. Every failure already falls back to the full solve inside the job |
| Sleeper offers read | Auth failures logged for many users, or a request from Sleeper | `trade.sleeper_offer_import` false. Consent rows and imported offers stay until each user withdraws or deletes their account |
| Revision 4 round | Bad decks | `grading.revision4_round` false: unopened revision 4 decks pause (`round_paused`), opened ones stay gradable |
| Backend code | A defect not behind a flag | Render redeploy of `37a65777` (the last `main` before #641) |
| iOS | — | Build 184 has no code a flag does not gate; turn the flag off. 183 remains available in TestFlight |

## Decisions needed

1. ~~App behaviour or wording for the Sleeper read.~~ Answered 2026-11-11: the app follows trades
   sent from it without the switch.
2. **models-eng review of the deck pipeline bump** (15 → 21) is still owed.
3. **The fast deck ends at 150 cards.** The deepest card acted on since September is index 65.
   Appending the rest of the inventory behind the page is unbuilt.

## Handoffs

- Run the TestFlight checklists on build 184: fast deck
  ([scope §3](../../plans/realtime-trade-engine/scope.md)) and each
  [offer-learnings scope block](../../plans/offer-learnings/).
- After the first real searches, read the `fast deck: served cards=…` lines in Render's logs and
  compare `gen_ms` in `trades_generated` with the days before.
- Read `GET /api/admin/grading/report?round_id=outlook-v2-v4-1&include_open=1` once testers have
  graded; revision 4 and `trade.partner_activity` wait on that read.
