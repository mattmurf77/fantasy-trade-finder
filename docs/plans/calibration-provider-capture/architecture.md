# Conditional linked-provider comparison

Status: implementation under review, no production actions by implementation agent. Normal serving, all model gates/budgets, provider sending and mobile binaries remain unchanged. This extends the frozen Calibration round, not the provider discovery surface.

## Capture boundary

`calibration_provider_capture.capture_linked` reads only a previously connected account-owned ESPN/MFL league. Existing session-input membership is checked first. The persisted importing account/seat must match; imported opponents are never treated as app users. Existing stored encrypted credentials are decrypted locally, never persisted in capture/proofs/log messages. Private or expired/undecryptable credentials fail explicitly. No bearer session is created. Public manually linked leagues retain that authorized binding as their stated ownership basis; they do not claim authenticated ownership. With ESPN credentials, the fetched primary/coowner list must contain the account's SWID. With MFL credentials, the existing authenticated league-list reader is used solely to validate the already connected league/franchise; other results are not retained, fetched or enqueued.

The fetch/parser preserves all observed teams and holdings, actual provider-native positions, IR/taxi assignments, supported starter slots and active capacity. Declared team counts, league ID, ESPN response season, duplicate player/team identity, unknown assets, metadata identity conflicts and unresolved native mappings fail closed. Native position overrides cross-provider eligibility in the safety context; a ranked position disagreement rejects capture rather than repricing the player. Fresh existing NFL metadata supplies availability; unranked mapped holdings use the separate unknown-price occupancy contract.

## Provable rule subset

ESPN accepts exactly QB/RB/WR/TE, RB-WR, WR-TE, FLEX and SUPER_FLEX slots plus bench/IR. Nonzero unsupported K/DST/IDP/custom slots and unrepresented roster positions fail. Native player eligibleSlots must agree with the declared skill-position slot eligibility. Active capacity is the sum of non-IR slots. Known finite skill-position roster limits below that capacity are unsupported, not treated as unrestricted benches.

MFL requires league, complete rosters, players, scoring positionRules and futureDraftPicks exports. Fail-soft missing exports cannot become a complete snapshot. rosterSize provides active capacity; roster status preserves ROSTER, INJURED_RESERVE and TAXI_SQUAD. Starter minima plus the remaining slots are accepted only when a single supported flex eligibility set represents every allowed positional maximum exactly; other min/max combinations remain unsupported. Known salary/contract/roster-limit settings outside this gate are refused. This does not certify every platform transaction/bylaw constraint: the comparison is a frozen as-of exercise under declared lineup/depth/capacity safety, never an executable offer.

MFL fresh scoring passes the existing canonical two-bucket detector and must match the stored format. ESPN has no native TEP detector: observed SF/2QB vs stored1QB fails; stored/manual sf_tep with a1QB lineup remains explicitly configured valuation with native TEP verification unknown. This does not invent a new price model. Public cards continue to show the existing as-of comparison context, without predictive/native-scoring accuracy claims.

## Owned picks and consistency

MFL uses the existing normalizer on the same raw futureDraftPicks bundle with captured binding checks. Consumed platform pick coordinates/current owner/original owner must exactly match that bundle after the existing completed-draft exclusion. Another cache writer before the first fingerprint therefore cannot substitute ownership. Invalid coordinates, duplicate original slots, unknown owners or absent pick-export evidence fail. No synthetic picks.

ESPN follows the existing asserted-assignment flag/eligibility policy and consumes only allowed user-assigned rows; otherwise the comparison is explicitly player-only even if the global picks switch is on. Sleeper now compares consumed platform ownership to the actual rows returned from its same-snapshot refresh, closing the equivalent cache substitution race; configured asserted additions remain subject to the existing row filter.

After resolving the provider, both versions use the same detached owner context and the unchanged full run_arm pipeline. The source records actual platform, private binding/credential revision (no secret values), native mapping, relevant observed rules, scoring basis, pick policy and complete roster context. Account/participant deletion fences, private exports, first-exposure pinning and immutable answers remain unchanged.

## Currentness and operation

Before/after capture fingerprints include persisted native team/season/host/auth/format binding and credential revision, as well as all captured raw holding metadata IDs. A final binding comparison also closes changes between provider fetch and the fingerprint window. Opening a prepared exercise does not refetch providers: it detects known persisted/cache changes only; new unobserved provider changes remain an as-of limitation. Inactive placement is retained in capture but flat member persistence cannot independently detect later IR/taxi changes at open.

Deploying this backend changes the calibration code identity: reprepare every unexposed snapshot before exposure. Already exposed/answered cohorts retain their original evidence. Unsupported leagues and reconnect failures remain aggregate outcomes, never replaced with a different model or old deck. No blanket all-ready claim is justified until the parent completes bounded production preparation and verifies per-platform outcomes.

## Source and evidence limits

The existing repository ESPN/MFL transport, identity, crosswalk and pick services are reused. Tests use synthetic raw structures, including positionRules/scoring, status/slot and exact team-count evidence; they are not captured customer records and do not establish the four production leagues' configurations. MFL's [official API documentation](https://api.myfantasyleague.com/2026/api_info) describes roster/pick exports and ROSTER/TAXI_SQUAD/INJURED_RESERVE statuses. ESPN's [official roster settings](https://support.espn.com/hc/en-us/articles/115003902651-Roster-Settings) distinguish lineup slots and position maxima. Unsupported or missing fields remain explicit rather than extrapolated from these examples.
