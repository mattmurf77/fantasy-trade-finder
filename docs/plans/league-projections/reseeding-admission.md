# Admit documented postseason bracket choices

Date: 2026-11-07. Direct production-readiness follow-up, isolated from the released worktree. The operator requested use of best-available inputs without weakening fidelity. No express waiver.

## Problem and scope

The provider adapter rejected every nonzero `settings.playoff_seed_type`, incorrectly treating it as custom regular-season qualification. Sleeper's own settings UI maps exact numeric0 to its fixed bracket and1 to later-round reseeding. The same overbroad gate rejected `playoff_type:1`, which selects a consolation lower bracket instead of a toilet bowl. This capability models regular-season standings, qualification, first-round byes and a non-playoff Max PF draft-order scenario, so both choices for each postseason setting have the same modeled outcome.

For each field admit only native integers0/1; absent remains the provider's default0. Reject booleans, null, strings, floats and unknown values with `unsupported_playoff_reseeding_policy` or `unsupported_playoff_lower_bracket_policy`. Keep nondefault `playoff_round_type` refused. Retain division, league-median, best-ball, manual bracket override, season, identity and scoring guards. No new source assumptions or changes to lineup, simulation math, trade models, ranking, weekly cadence, production flags or credentials.

## Primary evidence

Observed2026-11-07 from the public Sleeper web application, no authentication or customer league payload required:

- [Official league application](https://sleeper.app/leagues/123) references [the provider's JavaScript bundle](https://sleepercdn.com/js/bundle-cc10ee3ec75d745f2cc0302efadfa376.js?vsn=d). SHA256: `f41b630f4362fe9c20991c779f298707c00e4f6f559c0778d5765b2cb6cfc138`.
- The settings component initializes `state.playoffSeedType` from `settings.playoff_seed_type`. Its selector maps the fixed-bracket option to0 and the option labeled “Re-seed” to1. Submission writes that selected value back to the same native field. The adjacent tooltip explains that the choice affects later playoff matchups. The bracket renderer independently branches on1 when connecting playoff rounds. These linked code paths establish the native mapping; this is not an inference from a third-party API wrapper.
- The same component loads `state.playoffType` from `settings.playoff_type`, maps the lower-bracket selector to0 for “Toilet Bowl” and1 for “Consolation Bracket”, and writes it back unchanged. The choice determines whether losing or winning teams advance in the lower bracket; it does not alter regular-season qualification. [Official lower-bracket guidance](https://support.sleeper.com/en/articles/2203534) corroborates that distinction.
- [Official qualification guidance](https://support.sleeper.com/en/articles/2203518-how-do-playoff-teams-get-determined), dated September21,2026, separately describes record/PF/PA qualification, divisions and commissioner overrides. [Official median guidance](https://support.sleeper.com/en/articles/3971690-extra-game-each-week-against-league-median), dated September15,2026, confirms median games add a second weekly result; the median refusal therefore remains until that record model is implemented.

No third-party bundle is copied into this repository. The public source URL/hash and synthetic regressions are the durable reference. Private production identities and rosters remain outside reports and fixtures.

## Contract and compatibility

The snapshot/result coverage records `native_playoff_seed_type`, `native_playoff_type`, `nonplayoff_draft_order_basis:regular_season_maxpf_scenario` and `postseason_rounds_simulated:false`. A result warning displayed on both mobile and web says the pick estimates assume regular-season Max PF draft order, do not model consolation/postseason results, and may differ from custom actual draft rules. These are scenario pick probabilities, not a prediction of a consolation-based actual draft order. The existing league revision already hashes native settings, so a mid-capture mode change remains stale; changed source facts do not reuse a previous snapshot blindly. The coverage addition also changes semantic snapshot identity. Existing saved results remain readable; the simulation engine/model version is unchanged because regular-season algorithms and numeric outputs are unchanged. New queued captures use the corrected typed admission policy; immutable recovery snapshots remain immutable.

No new API, schema, flag, analytics event or UI component is added; both clients already display result warnings. Existing API observability and run-state reasons cover the change. Documentation: API reference and feature implementation updated for the coverage fields and boundary; configuration/data dictionary/design/glossary unchanged because their contracts are unaffected. TEST_LEDGER records validation. The canonical original feature scope and this bounded addendum remain applicable.

## Evidence and release requirements

Synthetic native capture compares all four combinations of the two0/1 settings while preserving all other inputs; full team results, qualification, byes, W-L-T and draft probabilities must match. Separate tests refuse malformed/unknown values and preserve all four other policy guards. Independent review and exact-head CI are required before merge. No simulator/Maestro is appropriate for this backend-only admission fix.

A future deployment changes Calibration's whole-backend source identity even though normal trade behavior is unchanged. Coordinate any affected unexposed Calibration rebuild; exposed/answered comparisons remain frozen. Do not merge/deploy this follow-up during the current release's canary/Calibration validation without root coordination.
