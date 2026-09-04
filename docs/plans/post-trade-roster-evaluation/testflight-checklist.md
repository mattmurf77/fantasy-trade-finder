# Manual TestFlight checklist — not yet executed

Use a development/staging build and linked test league. Never enable a global production gate for this checklist. The HTML prototype is independently reviewable and is not mounted in mobile.

1. With all four switches off, generate and swipe a deck. Existing cards, progressive loading, value and lineup evidence remain unchanged.
2. Enable only roster shadow. Generate the same fixture deck: served order is unchanged; impressions contain both-team roster evidence and rejection records identify blocked/unknown candidates.
3. In an observed Sleeper fixture, enable protection. Watch generation: progress advances, but cards appear only after final checks. A trade losing the only usable TE, a shared FLEX starter or last established backup does not appear for either team.
4. Use an already deficient roster and a same-position upgrade. The unrelated pre-existing weakness does not by itself veto the deal. A trade worsening that weakness is withheld.
5. Add a sweetener, or inject a previously liked mirror, that now removes a required starter or exceeds capacity. Confirm the final package is withheld. Switch protection while a cached completed deck exists and confirm a new request regenerates it.
6. Use an ESPN/MFL/Fleaflicker estimated template, unsupported starting slot, unresolved player, stale availability or failed roster fetch. Confirm no checked/safe claim and no enforced unchecked card. Job diagnostics distinguish incomplete data from a covered roster.
7. Force market-context failure with enforcement on. The job completes with no unchecked cards; shadow-only failure preserves the existing deck.
8. Review both-team evidence for contender and rebuilder fixtures: structural protection is identical; utility changes reflect the declared horizon. No fantasy-point or acceptance-probability claims appear.
9. Confirm logging correlates final assets with the same user/league/package impression, and records confirmed sends only after provider success. A client retry is not guaranteed to be deduplicated by the request-local ledger ID.

Record build SHA, fixture, switches, observed result and operator in TEST_LEDGER. No simulator, captures or Maestro flows.
