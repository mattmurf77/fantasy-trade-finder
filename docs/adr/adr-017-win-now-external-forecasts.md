# ADR-017: External weekly forecasts and an independent Win Now season model

Date: 2026-09-04
Status: Implemented and parent-reviewed; experimental release authorized 2026-09-05

## Context

Dynasty preference values cannot establish expected weekly fantasy points. A season-oriented buyer may rationally sacrifice dynasty value; sending that preference through the existing like/pass Elo path would teach the wrong ranking. The legacy outlook title model has not demonstrated sufficient skill for display.

## Decision

Use externally supplied weekly stat/availability forecasts, initially Sleeper's experimental feed carrying RotoWire revisions, behind a normalized provider adapter. Fleeced applies supported league scoring, chooses legal forecast-based lineups and simulates the real remaining schedule/bracket for both sides of a trade. Dynasty values are used only for fixed-baseline sacrifice, market plausibility and partner attraction. Search and calculator share hard eligibility policy; no weighted score or retry rescues a failed gate.

Store immutable forecast/projection/scenario evidence and viewer-scoped durable jobs. Record Win Now decisions separately from dynasty Elo and real proposals. Keep three independent serving/title kill switches, with code fallback defaults false. The operator explicitly accepted exploratory revised-input evidence on 2026-09-05 and authorized enabling all three in release configuration, including championship estimates labeled uncalibrated. This authorizes a beta trial; it does not establish calibration. Legacy title estimates remain unrenderable.

## Alternatives considered

Reusing roster-value or trailing-score outlook strength would not make a trade-sensitive player forecast. Building a trained player projection model now lacks frozen training/calibration evidence. A contracted provider can replace the initial adapter later without rewriting league scoring and simulation. Endpoint availability is not a commercial-license decision.

## Consequences

The beta can measure roster-sensitive season tradeoffs with reproducible inputs while preserving existing dynasty discovery. It cannot claim calibrated championship improvement or acceptance propensity. Current-status injuries, independent normal residuals, absent NFL game/team and multiweek injury correlations, conservative game-date cutoff, incomplete source coverage and unsupported formats restrict serving. Hosted Python 3.12 CI and deployment verification gate this release. Forecast-source quality, prospective calibration and the physical TestFlight checklist remain documented follow-ups under the operator's explicit beta authorization; existing Sleeper authorization governs use. See [BUILD](../plans/win-now/BUILD.md) and [EVIDENCE](../plans/win-now/EVIDENCE.md).

Historical validation uses separate outcome collection and archived-input scoring. Running a replay today is valid when its complete remaining-season inputs were actually archived before the forecast origin; stitching later weekly forecasts is not. Supplied references and hashes remain unverified assertions until reviewed. The initial historical endpoint audit supplies outcomes but no authenticated pregame projections. See [validation evidence and protocol](../plans/win-now/HISTORICAL-VALIDATION.md).
