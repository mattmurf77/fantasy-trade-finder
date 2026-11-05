# F-152 — subscription FAQ on the held release branch

Date: 2026-11-04. Entry point: operator request through launch coordinator. Builder: billing integration agent. No scope waivers requested.

## 1. Analytics scope

Existing page-view/event behavior remains sufficient: this adds static approved FAQ text to the existing page and creates no new action, emitter, collection or measurement requirement.

## 2. Schema and flag scope

No schema, flags, environment variables, knobs or routes change. This companion is based on held #456 head `f1df18568bbf504122c64889564b5d3ac9fe5c37`; it must not publish before the authorized release flip. No entitlement or billing activation occurs here.

## 3. Evidence scope

The existing FAQ details/summary and paragraph components display Q19 after Q18. No new style, interaction, screen or mobile testID. The added `RELFLIP-faq-subscription[faq.html]` structural check pins all five approved paragraphs, including automatic renewal, cancellation and deletion disclosures. Backend and mobile runtime tests are not applicable to this static-only change. Manual release verification: after the real App Store URL is assigned, open FAQ on desktop/mobile, expand “Does it cost anything?”, check the five paragraphs and confirm the App Store link opens the intended product.

Copy provenance: operator-approved marketing worksheet §9.7 `mon.sweep.faq19`, with legal R28.26 Founder paragraph and legal/privacy §6 deletion sentence. Source worksheet: `docs/plans/org-bringup/leads/marketing-lead-copy.md` in the existing org-bringup worktree. This is provenance, not permission to publish.

## 4. Documentation scope

API, LLD, architecture, HLD, cross-client invariants and glossary: no route, data, architecture, constant or domain-term changes. ADR: no new product decision; approved text is staged at the coordinator's explicit requested destination. Existing design-system components and tokens are retained. Evidence is recorded in TEST_LEDGER.

## 5. Ship gates and maintenance

Local checks: held baseline 240/242; with the new FAQ check 241/243. The same two intentional App Store placeholder failures remain. A temporary synthetic URL/id fixture makes 243/243 pass; corrupting the renewal sentence makes the new guard fail. Files restored after both experiments. No browser, device, purchase or full CI claim.

Before release: refresh held #456 with current main, preserving verified-session/privacy/device changes, replace placeholders with verified real App Store identifiers, run full exact-head CI, and obtain the scheduled release authorization. Do not merge this stale parent directly to main. The Founder paragraph is time-limited through December 31, 2026. Main's fallback new-member prices switch January 2, 2027 at 04:00 UTC; scheduled Store prices must be independently confirmed. Remove expired Founder copy after December 31, but do not publish new plain prices until the actual Store schedule is effective.

## Refresh and confirmed release destination — November 4

Merged current main `065a1ee6` into this held candidate without squashing. Conflict resolution preserves main's colon app title and non-free metadata description, its current landing design and verified browser flow, and both ledger histories. Privacy/Terms and browser-auth JavaScript remain byte-identical to current main. Approved Q19 and held release CTA/FAQ changes remain.

Authenticated ASC bundle lookup `com.fantasytradefinder.app` confirms app ID `6771488431`. Replaced placeholders with the ID-form future link `https://apps.apple.com/us/app/id6771488431` and matching smart banner; this URL needs no product-name slug. **The listing is not public**: read-only iTunes lookup resultCount0; ASC version1.0 PREPARE_FOR_SUBMISSION with no attached build. The real identifier removes the placeholder blocker, not the release hold.

Before publication, confirm the listing is public at that ID, install a current launch binary with the promised verified Apple/Sleeper/ESPN/MFL flows, configure and validate the two subscription products/offers/provider/server path, and activate only the approved billing/preview state consistent with Q19. Until then remain draft and do not merge/deploy this branch. Tips remain later/hidden. No external configuration or production setting is changed by the source refresh.

Refreshed validation:261/261 web structural checks;23 offline browser/extension auth checks;40 ranking-method checks. All three Store anchors (index2,FAQ1) use the confirmed ID and banner matches. Current main retains its prelaunch links; no provider or public-availability claim was changed on main. Local release link audit and source byte-identity audit pass. Browser runtime harness unavailable without Playwright in this clone; no rendered/device claim.
