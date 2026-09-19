# Parent review map

This map cites implementation and automated evidence, not deployed behavior.
All new work is isolated from the original dirty checkout. The baseline is
`4c343a488644299901655bd932f67f52355f42bd`; existing controls were not rewritten.

## Construction

- `backend/trade_gen_owner.py`: `_asset_interest` combines personal divergence,
  outlook and marginal usable depth before `_pool` truncates candidates.
  `candidates` enumerates structural small exchanges; `evaluate` prices packages
  under market stud adjustment and checks both owners, explicit selections,
  requested tier direction and hard safety. It does not call a legacy generator.
- `_team` uses per-entry provenance, consensus fallback and declared-over-inferred
  outlook. Actual supported slot templates use shared FLEX/SUPER_FLEX assignment;
  unknown settings remain labelled estimates. `_owner` records the component
  utility that can justify an outlook/need-funded personal-value loss.
- `OwnerDecisionContext` freezes evidence and binds terms/totals. Batch final
  evaluation shares one captured search context, avoiding repeated all-team
  initialization per candidate while preserving exact-card checks.

## Entry routes and control isolation

- `backend/server.py`: `_owner_generation_context` captures one cloned raw-input
  view; `_run_trade_job` feeds organic and GET/SEND/partner-targeted execution.
  `asset_trade_ideas` and `fair_packages` use `_owner_selected_ideas` and the same
  constructor. `_owner_cards_valid` is not the legacy positive-gain filter;
  separate final roster/disposition protections still apply.
- `backend/bakeoff_runner.py`: `ARM_OWNER` is distinct from the existing
  `challenger`; include and serve are independent. Historical `ARMS`, control
  profiles and golden payloads stay intact. New default-off knobs are inventory
  additions, not golden recaptures.
- `_owner_selected_assignment` records stable normalized inputs and named
  treatment/control identity. Identical repeated requests are one assignment
  unit. Exceptions/empty owner supply cannot relabel legacy output as treatment.

## Visibility, attribution and mobile continuity

- Server impression logging persists frozen owner evidence privately and
  whitelists only public identity/order/selection metadata on card responses.
  Queue linking validates manager, league and exact package hash.
- `mobile/src/screens/TradesScreen.tsx`: `orderedDeck`, `applySessionRerank` and
  `bestIdea` preserve the trial's intended ordering. `openShopWindow` carries
  the current fairness threshold through RootNav/ShopAssetScreen to both Shop
  request/cache keys. No new account preference or ranking write is introduced.
- `useSelectedOfferSignals` and `offerExposure` measure only the focused,
  foreground, visible active offer; `ShopOffersBody` captures a signal at tap
  time before advancing the pager, preserving it through delayed pass commit.
  Featured calculator edits terminate attribution to the original offer.
- Existing Chalkline caption styles disclose partial selected results. No
  private counterparty tiers or values are added to public card presentation.

## Evidence and limits

`test_trade_gen_owner.py`, independently authored
`test_owner_engine_acceptance.py`, `test_owner_generator_routes.py` and
`test_owner_bakeoff.py` exercise actual construction, route calls, final safety,
shadow isolation and joined outcomes. Mobile guards execute extracted production
ordering/query logic plus exposure clocks, not an alternate implementation.

Tests establish behavior, not production quality. Utility weights are
provisional; immediate usefulness is not a projection model; multi-year pick
forecasting, offer lifecycle and causal Undo remain outside this slice.
Physical steps: [manual checklist](manual-testflight.md).
