# Team overhaul — acceptance and evidence

This separates prototype verification from tests engineers must run after implementation. No production or TestFlight verification is claimed by this handoff.

## Prototype evidence

The approved standalone HTML was checked in isolated desktop Chrome: setup Continue labels, removal of the scenario control, one package per priority page, mouse/touch dragging, keyboard and Move controls, saved ranking/navigation state, ties in the send summary, and simulated sent/accepted locks. Layout checks at 320px and 390px found no horizontal overflow and no JavaScript runtime errors. These checks establish prototype behavior only; sending and tracking use sample data.

The handoff contains the approved prototype and current screenshots. The Acquire entry/resume mock was added after the core mock approval and is identified as a placement proposal. See [mockup gallery](mockups/index.html) and [status](status.md) for the current artifact disposition.

## Engine and data acceptance

| ID | Fixture / action | Expected result |
|---|---|---|
| E01 | Select a subset of roster assets; an otherwise attractive candidate needs an unselected sweetener | Candidate is excluded or asks the user to explicitly expand the pool; no hidden addition |
| E02 | Select six assets but a valid roadmap only uses five | Sixth asset remains eligible and visibly unused; not forcibly sold |
| E03 | All-in with selected picks only; rebuild with picks-only incoming return | Supported shapes are generated and represented with exact pick identity |
| E04 | Two next-season firsts have different original owners | Recovery targets the user's exact original first, not an equivalent-round pick |
| E05 | Rebuild owns next-season first / does not own it / ownership unresolved | Correct state and guidance; missing-first output contains highlighted recovery offer; unresolved state does not pretend recovery is unnecessary |
| E06 | Required recovery offer cannot be generated or user passes all recovery ideas | Explain the gap and return to targeted review/pool editing; do not label an incomplete roadmap as satisfying recovery |
| E07 | Two liked trades spend the same outgoing asset | They cannot occupy separate independent packages in the same roadmap |
| E08 | Alternatives share the exact same outgoing set | They can be ranked together in one package; same-tier races are explicit |
| E09 | Different sell partitions are feasible | Alternative roadmaps may regroup assets; selecting one fixes its groups for ranking/execution |
| E10 | Two trades require the same incoming player/pick or conflict on ownership/roster legality | Preflight/assembly identifies the conflict; independent execution is not promised |
| E11 | Too few compatible likes or distinct roadmap combinations | Generate further focused ideas and prompt revisiting the pool; preserve prior decisions and avoid endless identical regeneration |
| E12 | Position preference reduces score but a strong trade returns another position | Preference influences ranking, not a universal strict candidate filter |
| E13 | User changes pick budget or return mix | New generation uses the change; existing drafts/offers cannot silently retain incompatible assumptions |
| E14 | League season boundary changes | 'Next-season first' is resolved from league context with a recorded draft year, not the device's current year alone |
| E15 | Combine all trades or allowed concurrent alternatives | Validate ownership, incoming conflicts and relevant combined roster constraints; exercise each supported acceptance order |

## Execution and persistence acceptance

| ID | Fixture / action | Expected result |
|---|---|---|
| X01 | Double tap Send all offers; retry after a timeout | One logical attempt per intended offer; uncertain provider outcome reconciled before resending |
| X02 | Some submissions succeed, one fails, one remains unknown | Per-offer results; successful offers aren't resent; no single misleading 'all sent' state |
| X03 | Offer accepted while another device is preflighting | Ownership/version refresh and reservations prevent stale independent spending; accepted asset group is resolved |
| X04 | Two top-tier alternatives share assets | Both appear in preview; exact count and first-come, first-served warning; lower tiers are withheld |
| X05 | One tied offer accepted while another remains pending | Mark alternatives incompatible and reconcile/withdraw only where supported; never claim automatic withdrawal without confirmation |
| X06 | Decline or counteroffer arrives | Notify/display state; wait for explicit user action; negotiation remains possible |
| X07 | One tied offer declines, another is still pending | No automatic advance; pending-conflict handling follows the final agreed policy |
| X08 | App closes during a send; user resumes on another session | Durable attempt IDs and provider references recover the actual state, without duplicate sends |
| X09 | User switches alternative roadmap with live offers | Recheck reservations and pending conflicts; do not silently launch overlapping roadmaps |
| X10 | Counter adds an asset from another package | Revalidate affected groups before accepting/promoting; preserve the original attempt history |
| X11 | External trade or waiver changes the roster | Preserve completed history, identify stale remaining offers, require review before sending refreshed terms |
| X12 | Provider lacks sending or tracking capability / credentials expire | Explicit supported action or reconnect/manual path; never simulate successful provider activity |
| X13 | Reopen saved draft under another league or user | Authorization and league scope enforced; no state leakage |

Use meaningful backend unit/integration fixtures for assembly, versions, idempotency and state transitions. Add client structural checks for routing and forbidden shared-preference writes. Follow current CI configuration rather than copying historical test counts.

## Manual physical-device checklist — not yet run

Record app version/build, source SHA, league/platform, date, tester and outcome for each item.

1. Open Acquire. Confirm entry is discoverable without displacing the existing trade builder. Start Team overhaul and navigate back; verify the correct tab and league remain selected.
2. Complete both outlooks. Verify whole-roster position groups, selected recommendations, draft picks, user-adjustable budget/return mix, optional positions, and Continue labels.
3. In a controlled missing-first fixture, inspect the exact draft year/original owner. Verify the warning and overall Priority 1 recovery offer. Verify other offers are still user-executable.
4. Like/pass the complete deck; use insufficient-like fixtures. Verify targeted generation and editable pool, with preserved review decisions.
5. Compare alternative roadmaps, including different outgoing partitions. Open one package's alternatives and swap only through liked, still-valid choices.
6. Rank one package per page. Drag at top/bottom edges with touch, then use accessible movement controls/VoiceOver. Make a tie, navigate forward/back, background/kill/reopen, and verify persisted order and progress.
7. Inspect the final summary: independent package count, total offers, selected recipients, outgoing/incoming terms, ties and explicit first-come, first-served warning. Confirm recovery execution priority is distinct from tier numbers.
8. Against a controlled non-production integration, submit a batch with success/failure/unknown responses. Retry/reopen and verify no duplicate successful submissions.
9. Trigger a decline, acceptance and counter. Confirm no next-tier autosend, accepted assets become unavailable elsewhere, and negotiation/revalidation paths remain visible.
10. Resume from Acquire with saved/pending work. Verify fresh status timestamp, completed history, blocked stale offers and the next manual action. Exercise offline, expired-session and unsupported-provider states.

No Maestro/simulator work is required or authorized by this plan. Real-device runtime evidence and current repository release gates remain required before claiming release.
