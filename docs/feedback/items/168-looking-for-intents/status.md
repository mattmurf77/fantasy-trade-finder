# #168 / #172 — "Looking for" intents on the guided finder — status

**Status:** open · 2026-07-25 · n/a

`prd.md` header states "**State:** NOT BUILT (2026-07-25). Stretch item in
the #156 finish batch; the clean-mapping condition was not met, so this PRD
proposes the design instead of code." Proposal-only spec for letting users
express categorical trade intents ("looking for a stud", "split my stud
into depth") on the guided finder. No code, no downstream references found.

Backfilled 2026-08-08 — original session did not record state; classified
from the PRD's own explicit "NOT BUILT" marker.

**2026-08-08 update:** #172's specific consolidate/tier-up/tier-down ask
has since been built separately — see
`docs/feedback/items/172-trade-intents/status.md` — as a post-generation
filter (the approach this PRD's "why no code this round" section rejected
as dishonest), with an explicit honest-empty-state mitigation and a
reconciliation note explaining the divergence. This item stays `open` for
the BROADER #168 ask (categorical "looking for" intents beyond
consolidate/tier, and the heavier engine-level shape-restriction design
sketched below) — that part remains proposal-only.
