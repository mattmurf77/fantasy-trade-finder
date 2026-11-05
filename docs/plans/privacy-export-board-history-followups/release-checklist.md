# Scoped launch privacy/safety review — 2026-11-04

Reviewed code on main `065a1ee6` plus this branch, not production state. Current
open PRs (54) were checked before work; no duplicate implementation was found.

| Area | Evidence / status |
|---|---|
| Verified export/deletion and account aliases | Existing account-rights/deletion regressions run with this branch. No auth relaxation; credentials, session bearers and billing payload exclusions remain. |
| Mixed-owner export payloads | Fixed here: raw internal diagnostic/candidate/pack/page/bakeoff/grading-source payloads omitted; owned metadata/history kept; inline partner valuation filtered and malformed private JSON withheld. Stored evidence is unchanged. |
| Leaguemate board-history deletion race | Fixed here: actual owner locks + fresh board source validation span the write; deletion-before-write, re-signup and PostgreSQL concurrent deletion covered. Public roster retention rules are unchanged. |
| Packaging / App Privacy | `check-easignore.js` covers all 14 sensitive tracked patterns; `check-privacy-manifest.js` confirms Resources registration, required reasons, 13 declared data types, tracking off. Static code checks do not establish installed-build or App Store processing evidence. |
| Stored-page pre-scrub window | **Existing documented policy item, not changed here.** `_redacted_target` recognizes redaction tokens; a raw partner id can serve before async scrub reaches a stored page (scope-deletion-scrub §pre-scrub window: about 0.1 s normally, up to a cleanup tick/5 min if kickoff fails). The scope leaves acceptance with legal. Changing serving policy needs that basis; no acceptance is inferred. |
| Historical entry-user / analytics cleanup | Runbook procedures need operator-reviewed production evidence; code or old counts do not prove execution. No cleanup, restart, snapshot or backup deletion was performed here. |
| Backup retention / physical device checks | Existing 7-day backup promise and native login/WebView/Keychain/install checks require operations/device evidence. No new completion claim is made from repository review. |
| Feature activation | Existing provider/store/consent/enforcement gates remain; this patch changes no source flags or knobs and invokes no provider, purchase, capture, deployment or production action. |

No additional code blocker was found in this scoped export/history review.
This is not a whole-application privacy certification. Full CI on the PR and
independent review remain required before merge.
