# Feature scope — preference-led bilateral owner engine

Date: 2026-09-20. Entry: owner explicitly requested subagent implementation, parent validation, production deployment/activation replacing the prior model, Discord confirmation, and TestFlight only if required. No express waivers. Root owns release, core/wiring/validation agents have disjoint files.

## 1. Analytics scope

Existing deck impressions/outcomes, match/proposal records and private valuation snapshots cover generation provenance and side responses. Use a new model_arm/generator version (`owner_v2_bilateral`) plus versioned private bilateral evidence in existing JSON. Record intent, two-side support components, missing-preference coverage and captured market basis. Scores are not acceptance probabilities. No new client event emitter or table planned. Do not treat missing exposure as rejection, or a send as completion. Existing sparse/missing historical match attribution is not retroactively repaired.

## 2. Schema and flag scope

No new tables/columns/env variables. Registered numeric `model_config` selector `owner_bilateral_enabled`, default 0, replaces owner_v1 generation/serving/revalidation with owner_v2_bilateral when 1. Uses the logged admin configuration workflow; setting 0 is deploy-free rollback to prior owner model. Existing owner-only/include/serve controls remain; preserve unrelated flags/arms and unlimited returned offers. Cache keys and immutable proof validation must distinguish policy version. No independent client feature flag: this is a backend model-config selector, documented in config reference. Seed/config-default parity tested.

Initial activation uses the existing production market reference. Numeric KTC Tradesourced blends remain explicit offline alternatives: research has not validated a winning weight, and a new price source must not be confused with bilateral objective improvements. No training on synthetic rejections or uncalibrated probability claims.

## 3. Evidence scope

Backend unit/integration tests for bilateral construction/order, declared ranking authority, missing-board evidence, exact request pins/partial alternatives, price tolerance, untouchable/pick/outlook contracts, privacy and no artificial offer cap; cache/config selector and actual-arm attribution tests. Independent adversarial review and parent replay against frozen owner input. Full backend, web structural, mobile structural/TypeScript and test-ID CI at exact pushed head required before merge/deployment.

Native compatibility change discovered: featured-offer selection recognizes both owner model identifiers, preserving server ordering instead of market-gain resorting. Existing `check-owner-trial-order.js` and `check-owner-offer-signals.js` gain executable new-arm ordering/privacy tests; no layout/copy/testID changes. TestFlight 1.17.4 required for this compatibility correction (remote build number assigned by EAS); earlier clients still receive cards but do not preserve featured bilateral rank. Manual device acceptance checklist: fresh organic search, selected send/get, More Offers, league buy/sell, back navigation, liking identical package from both sides, and stale cached cards after switch. Physical-device execution cannot be inferred from source/CI. Retired simulator/Maestro not used.

## 4. Documentation scope

| Reference | Treatment |
|---|---|
| docs/config-reference.md | Register selector/default/activation/rollback and cache behavior |
| docs/architecture.md | Bilateral generator, intent/side support, serving/revalidation/provenance |
| docs/api-reference.md | Note new model-arm identifier without changing card JSON contracts |
| docs/data-dictionary.md | Describe versioned private bilateral evidence in existing valuation JSON, no columns |
| docs/engineering-notes.md | n/a: no new general schema/route convention |
| docs/cross-client-invariants.md | Native featured ordering recognizes both owner arm identifiers |
| docs/glossary.md | n/a: existing personal rankings, outlook, market terms and match vocabulary retained |
| Initiative design | Proposed score components and uncalibrated nature, decisions and model contract |

## 5. Ship gates

No gate waived. Parent must inspect combined diff, independent findings and scoped/full tests. Push review branch and get all four CI jobs green at exact head, merge only tested tree, explicitly verify Render deployment SHA/status and health. Read live config before and after one selector activation; owner-exclusive and zero output caps must remain. Verify generation/serving paths use new version and prior model no longer newly serves; history retained. Roll back selector if new model fails deployment/runtime checks. Notify owner in existing private Discord destination only after live verification. No other-person/channel messages. TestFlight requires build/submission proof if needed; not inferred from a build request.
