# Existing evidence source audit

Source inspection at `73bfa41e358e8780b823f652cf8388ae209b977d`, September 22, 2026.
This is a column/writer audit, not a production extraction or a measured completeness
report. The runtime is unchanged. Counts and coverage must come from an explicit,
authorized frozen export through [the evidence adapter](../../backend/eval/scorecard_evidence.py).
The reviewed [scorecard](../plans/model-evaluation-framework/scorecard-spec.md) remains
the semantic contract; availability is not correctness or a passing grade.

## Source-to-contract map

Line anchors below refer to the pinned source revision, not a claim that its comments
alone establish behavior. Each row pairs storage with the observed writer/consumer.

| Source and grain | Captured fields / writer | Supported interpretation | Missing or unsafe inference |
|---|---|---|---|
| `deck_impressions`, one persisted viewer occurrence | [schema, database.py:807](../../backend/database.py#L807); `impression_id`, `user_id`, `league_id`, `deck_job_id`, `card_index`, `served_at`, `trade_hash`, `assets_json`, `trade_concept_id`; [writer, server.py:5100](../../backend/server.py#L5100), [transaction, database.py:6557](../../backend/database.py#L6557) | Exact raw asset IDs/direction when `assets_json` is present; durable row and source keys; ghost versus non-ghost inventory | A row is not a view or proof the whole job finished. `served_at` is assembly time, not distinct generation/commit/delivery/render times. No actual offer expiry column; no pre-policy candidate census |
| Same occurrence, constructor/policy | `model_arm`, `arm_rank`, `policy_version`, `policy_variant`, `card_index`, `group_key/group_rank/lane_slot`, `fairness_threshold`, `trade_intent`; [schema, database.py:847](../../backend/database.py#L847), [writer, server.py:5340](../../backend/server.py#L5340) | Constructor, native/deck/group ranks and effective policy are separate observations when populated | Arm name alone is not immutable version/config identity. `propensity` ordinarily is an ordering multiplier, not randomized cohort assignment |
| Same occurrence, context and lineage | `features_json.partner_user_id`, positions, board count/update, fit, significance, roster and owner diagnostics; `source_like_impression_id`; `features_json.also_proposed_by`; [server.py:5116](../../backend/server.py#L5116), [server.py:5207](../../backend/server.py#L5207), [server.py:5348](../../backend/server.py#L5348) | Partner identity, injection lineage and overlapping constructor discovery, when retained | `likes_you` is delivery context; it does not give a second constructor causal credit. Source-like key does not by itself verify actor, identical terms or simultaneous interest |
| `valuation_json`, original serve-time policy snapshot | [trade_policy.py:900](../../backend/trade_policy.py#L900): schema/stage/format, `market`, viewer/partner raw and effective values/confidence, floors, per-direction per-asset rows, market and board timestamps; [asset binding, server.py:5359](../../backend/server.py#L5359) | Captured prices and manager-specific value evidence remain separate from current state | Raw value/confidence is not automatically explicit tier/order provenance or independently calibrated fairness. Missing vintages cannot be inferred from capture time |
| `valuation_json`, owner schema instead of policy schema | [trade_gen_owner.py:341](../../backend/trade_gen_owner.py#L341), [trade_gen_owner.py:424](../../backend/trade_gen_owner.py#L424); [bilateral enrichment, trade_gen_bilateral.py:253](../../backend/trade_gen_bilateral.py#L253); [write, server.py:5412](../../backend/server.py#L5412) | Generator/version; market package totals; both owner contexts; flat give-then-receive per-asset market/personal/source values; v2 adds preference diagnostics and board/seed hashes | Schema version `1` does not uniquely distinguish owner and policy structures. Model support/utility/preference directions are model outputs, not independent labels. Flat owner assets lack explicit per-row direction; adapter verifies ordered concatenation and reports that weaker binding class |
| Owner context / frozen inputs | [trade_gen_owner.py:267](../../backend/trade_gen_owner.py#L267) captures both rosters, inactive IDs, outlook/source, selected slots/source/capacity, unresolved assets and market depth proxy. [server.py:14787](../../backend/server.py#L14787) projects request inputs to package assets and target manager | Selected versus inferred context; per-asset position/age/raw Elo/source where owner request diagnostic remains | Estimated slots are not observed complete rules. `market_usable_depth_v1` is dynasty value, never fantasy points. Per-card projected inputs omit unrelated board/player rows needed for a full counterfactual replay |
| `deck_diagnostic_snapshots`, user/job-scoped JSON nodes | [database.py:967](../../backend/database.py#L967), [deck_diagnostics.py:11](../../backend/deck_diagnostics.py#L11); interned `owner_request`, `owner_experiment`, `owner_generation`, `roster_evaluation`, referenced by `$deck_diagnostic_v1` | Lossless expansion only while all user/job-scoped nodes exist; shared hashes reduce repetition | Missing nodes may be purged or absent in the export. No cross-user/job join by hash alone. Current ranks cannot restore deleted historical inputs |
| `deck_outcomes`, append-only action rows | [database.py:1095](../../backend/database.py#L1095), [writer, database.py:6739](../../backend/database.py#L6739): `id`, `impression_id`, `action`, engagement fields, `acted_at` | `viewed`, `like`, `pass`, `not_interested`, `propose`, `undo` are distinct. Actor comes from unique source impression. Views are capped at one, other actions can repeat after undo | No actor column or globally stable client gesture ID. A valid join and time are needed. Pass/reason duplicate emissions need reducer semantics. A propose event is not a confirmed send or completion |
| Actual-view client seams | [TradesScreen.tsx:267](../../mobile/src/screens/TradesScreen.tsx#L267), [usePresentationSignals.ts:42](../../mobile/src/hooks/usePresentationSignals.ts#L42), [useSelectedOfferSignals.ts:38](../../mobile/src/hooks/useSelectedOfferSignals.ts#L38) | Surface-specific existing view qualification; deck/presentation requires 500 ms and selected offers use visibility/activity clock | Generated/offscreen list rows do not count as views. Client telemetry absence is not a rejection and not complete observation |
| `trade_decisions`, older decision ledger | [database.py:475](../../backend/database.py#L475), [writer, database.py:5973](../../backend/database.py#L5973): actor, league, trade/package IDs, decision time, impression/concept links where available, `retracted_at` | Adds retraction evidence and legacy actions; original actions remain present | Mutable retraction field is not a complete append-only action history. Legacy missing impression/target links are not safe exact occurrence joins |
| `trade_pass_reasons`, latest explanation per key | [database.py:1283](../../backend/database.py#L1283), [database.py:6898](../../backend/database.py#L6898), [database.py:6949](../../backend/database.py#L6949): `key_source`, actor/league, `reason/detail`, created/updated times, switched-from, signal time | Reason codes are explanation evidence with explicit local-versus-impression keys | Not another pass event; updates overwrite prior reason details. Free text is sensitive and excluded from the adapter allowlist |
| `trade_matches`, persistent match with current disposition | [schema, database.py:605](../../backend/database.py#L605), [writer, database.py:9422](../../backend/database.py#L9422), [attribution, server.py:5619](../../backend/server.py#L5619): users, terms, matched time, decisions/times, dismissed flags, original two impression IDs, concept, first/second-like times, third `match_valuation_json` | Separate historical match record, later user decisions/archive state, and three distinct contemporaneous valuations if present | Historical match existence alone does not validate exact overlapping-interest/expiry semantics. Fuzzy matching is possible. Dismissal is not rejection. Chronological A/B naming conflicts; see below |
| `trade_proposals`, confirmed provider send | [database.py:655](../../backend/database.py#L655), [save_trade_proposal, database.py:6673](../../backend/database.py#L6673), [server.py:6034](../../backend/server.py#L6034): event ID, provider/transaction, original occurrence/match, exact FINAL assets/hash, edit flag, new valuation, send time | Confirmed send only; original and final package identities and valuation snapshots remain separate | Provider success is not counterparty acceptance or completed trade. Client retries may mint fresh event IDs; only specific writer keys deduplicate |
| `bakeoff_runs`, one generation run | [database.py:1031](../../backend/database.py#L1031), [owner writer, server.py:14862](../../backend/server.py#L14862): arm order/counts/timings/errors/agreement/groups/config, deck/job/user/league, timestamp | Constructor errors/empty results and captured run configuration. Owner `config_json.input` is full frozen request; request hash can join per-card reduced copy | Best-effort run ledger is not a complete census of all eligible users or failed requests. Aggregate agreement does not preserve every exact shared candidate. Non-owner config has a different shape |
| Owner assignment record | [server.py:14811](../../backend/server.py#L14811): `unit=request_inputs`, deterministic input hash, surface, arm, probability, exclusive mode, captured input, `market_as_of='unavailable'` | Describes the captured request routing/comparison unit | Not preassignment fixed eligible manager-league membership or cluster randomization. No-request users are absent. Source vintage remains unavailable; do not use today's market |
| `deck_candidate_sets`, post-gate/pre-withhold inventory | [database.py:976](../../backend/database.py#L976): candidate/job/user/league keys, size/hash, candidates JSON, creation time | A retained common post-gate action set and provenance when telemetry is enabled | Does not include all constructor vetoes or prove exhaustive search/recall. No implicit sampling probabilities for missing rejects |
| `sleeper_trades`, captured provider-completed transactions | [database.py:534](../../backend/database.py#L534), [filter, sleeper_trades_service.py:102](../../backend/sleeper_trades_service.py#L102): transaction/league/time, roster IDs, adds/drops/picks/FAAB | Provider completion corpus; adapter excludes full `raw` payload | No exact episode link, frozen participant mapping or demonstrated observation completeness. Positive-only transactions provide no refusal labels |
| `suggestion_trade_links`, matcher result per transaction | [database.py:1005](../../backend/database.py#L1005), [suggestion_telemetry.py:193](../../backend/suggestion_telemetry.py#L193), [suggestion_telemetry.py:361](../../backend/suggestion_telemetry.py#L361) | Existing recommended/ghost/partial similarity links, preserved as evidence requiring review | Existing “exact” can pair a generic pick with any real pick of that round. Non-ghost is not verified viewed. Matcher can fetch current roster ownership. Therefore not automatically exact episode completion evidence |

## Six-dimension coverage

| Dimension | Existing inputs worth retaining | Unresolved inputs / independent evidence |
|---|---|---|
| Fairness | Raw/adjusted package prices, own-manager values/confidence, policy floor, actions, matches, proposals | Independent acceptable-price/overpay comparison, blinded judgments, verified temporal milestones, calibrated probability target/labels; no fake joint probability from support |
| Outlook | Both owner outlooks and declared/inferred source; per-card request age/positions/preferences; raw pick IDs | Full selected and inferred histories/timestamps, independently justified age/position/exception classification, exact pick provenance; inferred intent is not selected intent |
| Team needs | Frozen rosters, selected/estimated slots, inactive IDs/capacity and legality diagnostics | Contemporaneous scoring/projections with point units/horizon, complete reserve/taxi/cut rules and availability, independently reconstructed best lineup. Market depth proxy does not fill this gap |
| Personal ranks | Per-asset raw/effective personal values and sources; v2 board hashes, tiers/percentiles; full owner run raw Elo/source universe when retained | Independently normalized same-universe tiers/order, complete explicit-source semantics and as-of provenance. Do not reuse model `.7/.3` preference directions as the answer or claim hash alone restores a board |
| Meaningful packages | Raw exact asset IDs/counts, per-asset prices/positions, significance result, explicit selected request | Independently versioned second-round player threshold and participant-specific usefulness/opportunity cost; second-round pick is not automatically a qualifying player |
| Stud tax | Raw values and adjusted market totals, headliner/shape/picks, captured config | Independent contextual premium bands, raw-to-adjusted attribution and exact first-round exemption provenance; policy agreement is not ideal compensation |

## Chronology, retention, and irrecoverable gaps

The `trade_matches.user_a_id` schema comment says “user who swiped first”
(`database.py:608`). The actual `create_trade_match` contract says A is the current
second liker (`database.py:9438`), and `_match_attribution` passes the current viewer
as A (`server.py:5624`). `first_like_at` belongs to B under these writers. Preserve
stored A/B and resolve chronology from actor-linked actions/timestamps; never infer
it from a column letter. Legacy matches can lack every impression link. Fuzzy
matching (`database.py:9334`) also requires exact-term validation before applying
the scorecard's exact-concept milestone definition.

`purge_deck_diagnostics` (`database.py:6638`) deletes bounded batches of debug nodes
older than 14 days by default. The cleanup loop reads
`FTF_DECK_DIAGNOSTIC_RETENTION_DAYS` (`server.py:2744`). This does not delete durable
impressions, valuation snapshots or outcomes. A missing reference is reported as
expired/missing/ambiguous, because a partial export cannot prove why it is absent.
After deletion, its unique historical content is unreconstructable unless an
authorized retained copy exists. The adapter neither reads current boards nor
backfills old nodes. Full owner run inputs may preserve overlapping evidence,
but are a separate snapshot with their own source/time and must not replace an
earlier occurrence silently.

No inspected table defines preassignment eligible manager-league windows including
no-request members. No legacy numerator may therefore be divided by generated
episodes and relabeled as the planned primary fixed-cohort yield. The adapter
always marks that cohort absent. Complete observation, actual expiry, ingestion
cutoff, carry-in/new-episode rules and exact actor identity also require explicit
evidence before a lifecycle reducer can verify milestones.

See [evidence contract](evidence-contract.md) for implemented read boundaries and
separate prospective instrumentation work. No new tables, retention job, emission,
source rights, privacy access, or production extraction are introduced here.
