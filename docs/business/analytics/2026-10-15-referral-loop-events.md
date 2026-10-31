# Tracking-plan addendum — Referral loop v1 (2026-10-15)

**Status:** granted by `analytics-lead` on 2026-10-15 for the referral loop
([scope](../../plans/referral-loop/scope.md) §1 and [PRD](../../plans/referral-loop/prd.md) §10 (prd.md:868-955 @ ace09cf3), PR #348).
The operator approved the build (PRD D-1, prd.md:1054 @ ace09cf3); this addendum exists before any emitter ships (G-031).
**Nothing is registered yet:** each name and prop lands in its emitter's commit (C7).
**Takes effect:**
- **Server events:** from the Render deploy that carries them, and only while `growth.referral_ledger`
  (new, default off) is on. `invite_landing_cta` also needs `growth.join_landing` (new, default
  off, PRD D-7, prd.md:1060 @ ace09cf3), because the click-through exists only on the landing page.
- **Client changes:** from the first iOS build that carries the emitters (none is cut at 678834ab)
  and the web deploy with the new `FTFTrack` calls. Both need `analytics.client_events` and
  `analytics.ingest` on (`config/features.json:121-122`, both on).
- **Other flags:** `growth.invite_join_link` (`:190`, off) flips in Phase 1 with its meaning
  unchanged; `growth.referral` (`:149`) stays reserved and untouched.

**Registries touched:** `SERVER_FIRED_EVENTS` +4, `NON_INTENT_EVENTS` +4, `ALLOWED_CLIENT_EVENTS` +1
(`share_link_opened`), `CLIENT_EVENT_PROPS` (4 rows widened, 1 new). **Left alone:** `FUNNEL_CRITICAL`
(`analytics_taxonomy.py:893`; no pre-auth primitive here), `WAT_LIVE` (`analytics_queries.py:53`; no
north-star decision), `FUNNEL_STAGES` (`:406`; read by C5, never edited).
Pinned by `backend/tests/test_analytics_taxonomy_referral_loop.py`.

## Questions these events answer

1. **Where does the loop leak, hop by hop (H1→H8, [loop-audit](../../plans/referral-loop/loop-audit.md))?**

| Step | Hop | Event (props that answer it) | Read |
|---|---|---|---|
| shown | H1 | `invite_cta_shown{surface}` | Impressions per surface |
| tapped | H1 | `invite_cta_tapped{surface}` | Tap rate per surface |
| shared | H2 | `invite_shared{surface, invite_id, mint_outcome}` | Share completion; mint health |
| link opened / landing opened | H3b / H3a | `invite_link_opened{format, invite_id}` (installed app, web) and `invite_landing_opened{invite_status, device_class}` (server) | `o`, the two unioned (PRD §7.3, prd.md:673-679 @ ace09cf3) |
| landing CTA | H3a | `invite_landing_cta{cta, device_class}` | Which way a not-installed invitee goes |
| signup attributed | H5 | `signup{attribution, attribution_miss}` and `referral_attributed{attribution_method}` | `j`; the PRD §2.1 (prd.md:92-102 @ ace09cf3) ≥95% target; token vs league match |
| pinned | H4 | `invite_league_pinned{source}` / `invite_pin_failed{reason}` | Pin success; the PRD §2.3 (prd.md:127-136 @ ace09cf3) guardrail |
| activated | H6 | `referral_activated{days_to_activate}` | `a`; time to value |

- **H7 (inviter told)** is `notified` on both referral rows (C8). **H8 (measurement)** is the PRD FR-22
  (prd.md:627-630 @ ace09cf3) readout over these rows plus the ledger, joined on `invite_id` = `share_token` and
  `referral_id` = `referrals.id` (`database.py:2599`).
- **Count an open once.** With `growth.invite_join_link` on, a web `invite_link_opened{format: web}`
  follows a landing CTA (PRD FR-9, prd.md:456-470 @ ace09cf3): it is the next step, not a second open.

2. **What is `K_30`, per inviter and overall?** `i × o × j × a` (PRD §2.2, prd.md:103-126 @ ace09cf3), from the steps above.
3. **Does minting cost shares?** Split `invite_shared` by `mint_outcome`.
4. **Do share links (S1–S3) bring people in?** `share_link_opened{kind, has_ref, auth_state}`.

## Events

| Event | Class | Client / owner | Properties | Fires when |
|---|---|---|---|---|
| `invite_landing_opened` (new) | NON_INTENT | server; owner = the referrer, else `system:invite` | `invite_id`? (C3; the well-formed `t` as received (`^[A-Za-z0-9_-]{8,64}$`, PRD §8.2, prd.md:777 @ ace09cf3), else omitted; whether it resolves is `invite_status`), `league_id`, `invite_status` (`valid`\|`expired`\|`unknown`\|`league_mismatch`\|null, C1), `device_class` (`ios`\|`android`\|`desktop`\|`other`) | A **human** GET (C4) of `/app/league/join/<id>`, in landing or 302 mode (PRD FR-8, prd.md:444-452, and §8.2, prd.md:775-796 @ ace09cf3) |
| `invite_landing_cta` (new) | NON_INTENT | server; same owner rule | `invite_id`?, `league_id`, `cta` (`ios_install`\|`web_app`; path `/go/ios`\|`/go/web`), `device_class` | A **human** GET (C4) of the landing click-through `/app/league/join/<id>/go/<cta>` (PRD §8.2, prd.md:775-796 @ ace09cf3) |
| `referral_attributed` (new) | NON_INTENT | server; owner = the referrer | `invite_id`, `referral_id`, `league_id`, `attribution_method` (`token`\|`league_match`), `league_platform` (`sleeper`\|`espn`\|`mfl`\|`fleaflicker`), `notified` (bool) | Ledger credit at a new user's first session (PRD §7.4 / §7.5, prd.md:680-717 @ ace09cf3). No invitee id (C2) |
| `referral_activated` (new) | NON_INTENT | server; owner = the referrer | `invite_id`, `referral_id`, `league_id`, `days_to_activate` (int 0–14), `notified` (bool) | The invitee's first stage-7 event within 14 days of `joined_at` (C5; PRD FR-17, prd.md:551-556, and D-8, prd.md:1061 @ ace09cf3) |
| `signup` (changed props) | unchanged | server; owner = the new user | adds `attribution` (`token`\|`league_match`\|`legacy_ref`\|`none`) and `attribution_miss` (`unknown`\|`expired`\|`not_member`\|null) | First session (`server.py:22620-22627`) |
| `invite_shared` (changed props, new web emitter) | INTENT | mobile, web | today's row (`analytics_taxonomy.py:1154-1156`) plus `invite_id`? and `mint_outcome` (`ok`\|`failed`\|`timeout`\|`rate_limited`\|`disabled`\|`demo`, PRD AC-1b/1c, prd.md:295-298 @ ace09cf3). `channel` is deferred | The share sheet is not dismissed (PRD AC-1d, prd.md:299-300 @ ace09cf3) |
| `invite_cta_tapped` (new web emitter) | INTENT | mobile, web | keys unchanged (`:1311`); `surface` gains `web_invite` | An invite tap, before the mint call |
| `invite_cta_shown` (new emitters) | NON_INTENT | mobile, web | keys unchanged (`:1309`) | Once per mount: + Trades banner, members overlay, web modal (PRD FR-4/FR-5, prd.md:328-351 @ ace09cf3) |
| `invite_link_opened` (changed props, new web emitter) | INTENT | mobile, web (`captureReferralFromUrl`, `web/js/app.js:6390`) | adds `invite_id`?; `format` gains `web` (`legacy`\|`path`\|`web`) | An invite URL is parsed |
| `invite_league_pinned` (changed props, new web emitter) | INTENT | mobile, web (auto-select) | adds `invite_id`?; `source` gains `web_autoselect` | The invited league becomes active |
| `invite_pin_failed` (changed props, new web emitter) | INTENT | mobile, web | adds `invite_id`? | The invite intent can't be honoured |
| `share_link_opened` (new) | INTENT | mobile `handleDeepLink` (`mobile/src/utils/deepLinks.ts:387`) | `kind` (`trade`\|`package`\|`ref_root`), `has_ref` (bool), `auth_state` (the `invite_link_opened` enum) | A non-league link (`/s/*`, `/?ref=`) is parsed |

**Grant notes:**
- `share_link_opened` was granted by `analytics-lead` on 2026-10-15 (P18); PR #348's scope §1
  does not list it yet.
- `surface` is one closed enum shared by `invite_shared`, `invite_cta_shown` and `invite_cta_tapped`
  (`analytics_taxonomy.py:1132`, `:1293-1296`), so `web_invite` widens all three. A new enum value
  edits the comment beside the row and this addendum, not the keys.
- `invite_id` on every row is C3's share id. The landing rows and the client parse rows
  (`invite_link_opened`, `invite_league_pinned`, `invite_pin_failed`) send the well-formed `t` as
  received, else omit it; a client cannot know whether it resolves. `invite_shared` sends the id
  the mint returned (PRD AC-1b, prd.md:295-296 @ ace09cf3).
- The four server events go into `SERVER_FIRED_EVENTS`, their writes are non-touching (C6), and
  the owner is `system:invite` only when no referrer resolves (the `system:api` precedent,
  `analytics_queries.py:60-62`).

**Why the classes:**
- **The four server names: NON_INTENT, mandatory.** Each row's `user_id` is the referrer, while the
  person acting is the invitee (open, click, signup, swipe). INTENT would give the referrer a
  user-day for someone else's act. Class: system outcome / background job (`system:api`,
  `analytics_queries.py:60-62`; `system:receipts`, `:278`). INTENT is computed by subtraction
  (`:402`), so the four `NON_INTENT_EVENTS` rows land in the emitter's commit.
- **`signup`:** unchanged; the new user's own first session (stage 2, `:409`).
- **`invite_cta_tapped`, `invite_shared`, `invite_link_opened`, `invite_league_pinned`:** INTENT,
  unchanged; each is a deliberate act. **`invite_pin_failed`:** INTENT, because a deliberate act
  the system refused is still intent (the `sleeper_send_failed` precedent).
- **`invite_cta_shown`:** NON_INTENT, unchanged; an impression (`:150-160`).
- **`share_link_opened`:** INTENT, overruling the P18 draft's NON_INTENT (`marketing-inputs.md:589`).
  Its twin `invite_link_opened` is INTENT, and twins land on the same side. Reclassifying the twin
  instead would rewrite past DAU, because classification is applied at query time. Anonymous
  openers are stripped by `device_exclusion()` (`device:%`, `:481`) either way.

**Not tracked:**
- `channel` on `invite_shared` (and on `calc_trade_shared` / `trade_card_shared`): deferred.
- `utm_*` props and `signup`'s `first_utm_*`: deferred until the UTM capture is built (below).
- `share_landing_viewed` (optional in P18): not granted; `/s/*` landing views stay unmeasured.
- A notification-created event (C8). Unfurls and HEAD requests: ledger `unfurled_at` only (PRD FR-8, prd.md:444-452 @ ace09cf3).
- The P18 draft's `has_ref`, `ref_resolved` and `attribution: link|none` on `signup`: superseded
  by the canonical `attribution` / `attribution_miss` vocabulary. `K_30` is a query, not an event.

**PII:** ids only. `invite_id` is the public share id `t`, opaque and granting no access (C3); `referral_id` is
`referrals.id`, an integer; `league_id` is a platform league id, exempt from the 16-digit scrub on
client ingest (`analytics_ingest.py:176-183`). No usernames, display names or league names (C9);
`has_ref` stays a boolean. No invitee user id (C2), no user-agent string or IP (C4), no key
containing `token` (C1). Server props skip ingest's scrub (`record_event` writes `props` as passed,
`database.py:4433`), so the emitter is the only control and the test pins its exact keys.

**Seam:**
- **No history before ship.** The four server names and `share_link_opened` start at zero: report
  forward baselines, never "the rate fell". Server rows begin when `growth.referral_ledger` turns
  on, not at the deploy.
- **`signup` rows before that date carry no props** (`server.py:22620-22627`); a missing
  `attribution` means pre-instrumentation, not `none`.
- **Older invite history has gaps.** `invite_shared` and `calc_trade_shared` were sent from
  2026-07-19 (`2001369d`) but dropped until registered on 2026-08-11 (`26fb5b20`, `cb5cc7de`).
  Invite `league_id` values read `"[scrubbed]"` until 2026-08-12 (G-036).
- **Web emitters start a new series.** Split by the `platform` column; do not trend invite totals
  across the web ship date. The new `invite_cta_shown` emitters step impressions up: compare per
  `surface`, not totals. `matches_empty` stays a mount counter (`analytics_taxonomy.py:1302-1308`).
- **Designed DAU step.** The new INTENT emitters (web invite events, `share_link_opened`) can add a
  user-day for a signed-in user who does nothing else that day. Expect a small step per ship date.

**Privacy delta:** **new category**: first-party referral attribution linked to the account. The
ledger, `referral_attributed`, `referral_activated` and `signup.attribution` together say who
invited whom; a landing open also records a non-user's coarse `device_class` under the referrer's
id, with no identifier. Notify `onboarding-pm` through `head-product` (P12) to diff the label. The
App Store Connect privacy-label check is the operator's.

## Grant conditions

- **C1.** Rename `token_status` to `invite_status`, same values (PRD FR-8 and §10, prd.md:452, :884 @ ace09cf3). Scope
  §1's own rule is that no prop key contains `token`, and the ingest denylist works by key
  substring (`analytics_ingest.py:160`, `:195`). `invite-meta`'s API field (PRD §8.3, prd.md:800 @ ace09cf3) is not a prop.
- **C2.** Drop `referred_user_id` from `referral_attributed`; join through `referral_id` to the
  ledger. Account deletion removes only the user's own events (`accounts.py:754-757`) and NULLs the
  ledger's `referred_user_id` (`:829-834`), so an id inside the referrer's row would escape the
  referred user's deletion. Same gap as PR #337 R-L3.
- **C3.** `invite_id` is the public share id `t` (`share_token`, PRD §7.1, prd.md:651-653 @ ace09cf3): opaque, 72-bit
  random, no PII, an identifier that grants no access. It must never be an auth or session
  credential, and no prop key may contain `token`. Sibling rows' `invite_token` (`<share_token>~…`)
  is never emitted.
- **C4.** "Human GET" for `invite_landing_opened` and for the `invite_landing_cta` click-through
  (`/go/<cta>`), which uses the same filter: HEAD requests are excluded; link-preview and
  unfurl fetchers are excluded by an explicit, tested user-agent list (at least
  `facebookexternalhit`, `Twitterbot`, `Slackbot`, `Discordbot`, `WhatsApp`, `TelegramBot`,
  `Applebot`, `LinkedInBot`, and a generic `bot|crawler|spider|preview` pattern); only the
  `device_class` bucket is stored, never the user-agent string or the IP.
- **C5.** `referral_activated` takes its qualifying events from stage 7 of `FUNNEL_STAGES`
  (`analytics_queries.py:415`) in code, not from a hand list. It never counts `trades_generated`
  (stage 6, `:414`).
- **C6.** A test proves the non-touching writes leave `users.last_active_at` and `events_count`
  unchanged; today `record_event` bumps both (`database.py:4439`, `:4451-4458`). `head-eng` picks
  the mechanism (PRD D-13, prd.md:1066 @ ace09cf3); prior art is `backend/api_observability.py:189-205` (`platform="server"`).
- **C7.** The emitting eng worker registers and classifies under `analytics-lead`'s grant, in the
  emitter's commit; `analytics-lead` grants and does not edit code. Client and server namespaces
  stay disjoint (import-time assert, `analytics_taxonomy.py:1757-1781`).
- **C8.** `notified` is accepted as a prop; there is no separate notification event.
- **C9.** No usernames in any event prop. The `referral_activated` bell row's meta may carry
  `new_username` (PRD FR-19, prd.md:588-611 @ ace09cf3), because it is not an event.

## Requests to growth-pm (not grant conditions)

- **R1.** PRD FR-8 (prd.md:444-452 @ ace09cf3) records only GETs that have a well-formed `t`, so
  `invite_status: null` never fires and opens of mint-failed or legacy links go unmeasured.
  Analytics asks that every human GET be recorded while the ledger flag is on, with
  `invite_status` null when `t` is absent and owner `system:invite` unless a legacy `ref` resolves.
- **R2.** The PRD and scope still use `token_status` (PRD FR-8 and §10, prd.md:452, :884 @ ace09cf3) and
  `referred_user_id` (PRD §10, prd.md:886 @ ace09cf3; scope §1). Both need updating to C1 and C2.
- **R3.** PRD FR-17 (prd.md:551-556 @ ace09cf3) must take its qualifying events from `FUNNEL_STAGES` (C5).

## UTM convention (final, P18). Accepted by analytics-lead 2026-10-15; vocabulary from growth-pm's D5 answers, relayed by head-product 2026-10-15

- **Params and regex are unchanged.** There are four params (`utm_source`, `utm_medium`,
  `utm_campaign`, `utm_content`) and no `utm_term`. Each value matches `^[a-z0-9_]{1,40}$`. At
  ingest, a value outside the regex or the vocabulary is coerced to `other`; it is never dropped.
- **Closed vocabulary per param:**

| Param | Values |
|---|---|
| `utm_source` | `ios_app` \| `web_app` \| `<partner_slug>` (from the partner registry; later) |
| `utm_medium` | `invite` \| `share` \| `creator` \| `partner` |
| `utm_campaign` | `league_invite` \| `trade_share` \| `tier_share` (reserved, not emitted) \| `<yyyy>_<name>` (partners; later) |
| `utm_content` | `image` \| `text` for in-app invites and shares (invites are `text`); `bio_link` \| `video_desc` \| `newsletter` \| `pinned_post` for partners (later) |

  The partner rows and the App Store `ct` row (`ct=<utm_campaign>`, not a UTM) are as drafted in
  [marketing-inputs.md §C](../../plans/referral-loop/marketing-inputs.md) (`:549-550` @ ace09cf3).
- **The surface is never in the URL.** The canonical surface values are the existing `surface`
  prop values:
  - invite: `league_home`, `members_overlay`, `matches_empty`, `notif_empty`, `trades_banner`,
    plus the new `web_invite`;
  - share: `calc_live`, `calc_in_league`, `trades_liked`.

  For an invite, the surface is recovered through `invite_id` → the ledger's `surface` column,
  written at mint (PRD §10 surface vocabulary, prd.md:971-976, and §9 ledger columns,
  prd.md:880 @ 08f324ec).
- **Link format is the `kind` prop** on `share_link_opened` (`package` | `trade` | `ref_root`),
  not a surface.
- **Retired names.** `invite_card`, `invite_banner`, `league_tab`, `share_package` and
  `trade_card` are never emitted as values. The inline League link reports `league_home`.
- **`ref` PII.** The opaque `t` closes the username-in-`ref` risk (PRD FR-2, prd.md:302-308 @
  ace09cf3). Legacy `ref` links already in the wild are still parsed, and `has_ref` stays a boolean.
- **Measurement limit (stated, nothing granted).** A share-link *recipient* open carries `kind`
  but not the sharer's surface, unless the shared artifact stores its surface; the sharer-side
  events carry it. This is acceptable at beta. Revisit if growth asks which share surface converts.
- **`signup.attribution`:** see the Events table (`token|league_match|legacy_ref|none`, plus
  `attribution_miss`). It is canonical and supersedes P18's `link|none`.
- **Registration timing is unchanged:** `utm_*` and `first_utm_*` are registered when their
  emitters ship.

## Verification

`backend/tests/test_analytics_taxonomy_referral_loop.py`, copied from
`test_analytics_taxonomy_home_hub.py` / `_384.py` and driven by one `_CLIENT_PROPS` and one
`_SERVER_PROPS` dict of realistic values, asserts:
1. **Membership.** The four server names are in `SERVER_FIRED_EVENTS`, not `ALLOWED_CLIENT_EVENTS`;
   `share_link_opened` is in `ALLOWED_CLIENT_EVENTS`, not `_SERVER_AUTHORITATIVE`.
2. **Exact prop rows (`==`).** The five touched client rows and `share_link_opened` equal
   `CLIENT_EVENT_PROPS[name]`. Server events have no registry row, so each emitter's props keys,
   captured at the writer, `==` the granted set. No key contains `token`; the C2 id is absent.
3. **No device-`platform` prop** on any new row or server event; `league_platform` is the league
   platform, and the existing invite rows' `platform` keeps its league meaning
   (`analytics_taxonomy.py:1148-1153`).
4. **The intent split.** In `q.NON_INTENT_EVENTS`: the four server names and `invite_cta_shown`. In
   `q.INTENT_EVENTS`: `signup`, `invite_cta_tapped`, `invite_shared`, `invite_link_opened`,
   `invite_league_pinned`, `invite_pin_failed`, `share_link_opened`.
5. **The non-touching write** (C6), and C5's qualifying set equals stage 7 of `FUNNEL_STAGES`.
6. **The bot filter** (C4), on both `invite_landing_opened` and `invite_landing_cta`. Each listed
   user agent and the generic pattern produce no event (and no `open_count` bump); HEAD records
   nothing; no stored row carries a user agent or an IP.
7. **An ingest round-trip** through `POST /api/events` (the 384 harness): `accepted ==
   len(_CLIENT_PROPS)`, `dropped == 0`, every row read back with its props. Plus an
   **unregistered-sibling control** (e.g. `share_link_viewed`) expecting `dropped == 1` and no row.
8. **Deploy liveness**, after each deploy (prod only with the operator's yes): probe
   `share_link_opened` until `accepted ≥ 1 AND dropped == 0` (`.claude/skills/feedback/lessons.md:168-171`);
   then `GET /api/admin/analytics/health` (`server.py:11302`) shows `dropped_unknown_prop == 0` for the
   widened rows; for the server names, read one row of each back after a flag-on run.

The mobile half is also pinned by scope §3's `mobile/tests/check-invite-links.js`: item 3 (event
order) and item 6 (no prop key contains `token`).
