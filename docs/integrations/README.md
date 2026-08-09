# docs/integrations/

Per-external-service API references — what FTF actually calls on each third-party
platform, verified against the code (not the vendor's docs, which for ESPN's
unofficial API don't exist). Written for the instrumentation program: each file
gives an instrumentation build agent the endpoint list, auth model, payload
shapes, error modes, call frequency, and a safe-to-log / must-redact split so
logging can be added without guessing at what a call site actually does.

This is a sibling to `docs/references/<site>/<api-name>/` (see `docs/CLAUDE.md`),
which holds raw reverse-engineered wire-shape notes; files here are the
consumer-facing distillation — one file per external service, organized around
"what do we call and why," not around capturing a single verification session.

| File | Service |
|---|---|
| [espn.md](espn.md) | ESPN Fantasy Football unofficial v3 API (`lm-api-reads.fantasy.espn.com`) — league linking, roster import, standings-derived draft order |

Keep current: when a call site is added, removed, or its shape changes, update
the relevant file in the same change.
