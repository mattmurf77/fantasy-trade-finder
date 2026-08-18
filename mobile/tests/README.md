# mobile/tests/

50 **structural guards** — all 50 run in CI (the `mobile-typecheck` job globs `tests/check-*.js`); 41 also have an `npm run test:<name>` script for local use. Since [D-056](../../living-memory/DECISIONS.md) (2026-08-15) retired Maestro and the simulator, these plus unit tests are the primary automated evidence for any mobile change.

They are not a conventional unit-test suite. Most pin a claim about **code shape** — placement, an unconditional render, a marker's presence, a threshold shared across clients — that a value-based test cannot see and a passing UI would hide. Several transpile a real module and execute it under plain node. Read the `WHY THIS EXISTS` block at the top of any file: nearly every guard was written after a specific defect shipped.

Some files are explicit about their own limits — `check-contrarian-format-key.js` and `check-matches-tile-league-param.js` carry an "HONEST LABEL (G-035)" note saying they prove **presence of exact wirings, not behavior**. Copy that honesty when you add one.

## Running

```bash
cd mobile
npm run test:<name>          # one guard
node tests/check-<name>.js   # same thing, for the ones with no script
```

## The guards

| Area | Guards |
|---|---|
| Deck & trades | `check-card-disposition` · `check-single-pin-actions` · `check-session-rerank` · `check-trade-text` · `check-send-button-platform` · `check-trades-banner-region` (#314/#315) · `check-dna-side-order` (#312, GIVE-LEFT/GET-RIGHT) · `check-fairness-default` (unset ⇒ OFF) · `check-decline-reasons` · `check-offer-prefill-330` + `check-offer-prefill-330-unit` (#330 epoch guard) |
| Calculator | `check-calc-send-placement` (#303) · `check-calc-partner-labels` (#306) · `check-calc-pick-tiers` (#320) · `check-picker-chip-alignment` (#320 defect A) |
| Matches | `check-matches-counts` (#334/#335) · `check-match-value-section` (#319) · `check-matches-calc-handoff` (#319 cross-league) · `check-matches-league-param` + `check-matches-tile-league-param` (#307) · `check-awaiting-dismiss` (#318) |
| League | `check-league-unlocks` (#265/#308) · `check-league-drill-in` (#299/#302) · `check-league-candidates-300` · `check-contrarian-format-key` (#308) · `check-picks-subset-invariance` (#293/#294) · `check-analytics-297-302` · `check-analytics-300` |
| Rankings & import | `check-anchor-labels` · `check-rank-nav-exit` (never-strand topology) · `check-rank-presets` (D-058 CSV parser) · `check-premium-import` (D-058 lanes 1 + 2a) |
| Draft & mock | `check-mock-mode-marker` · `check-mock-lifecycle` (#291/#292) · `check-mock-draft-modes` (#295/#296/#305) · `check-mock-user-not-in-draft` · `check-mock-g2-ui` (#322–#327) · `check-mock-ownership-caption` (#328) · `check-member-entered-marker` (D17) |
| ESPN / credentials | `check-espn-cookies` · `check-espn-connect-clear` (2026-08-12 incident) · `check-espn-nav-policy` · `check-espn-wrong-account` (#321) · `check-keychain-accessible` (every `src/transport/` write pins `WHEN_UNLOCKED_THIS_DEVICE_ONLY`) · `check-vault-subsumes-legacy` (migration deletes the legacy slot) |
| Onboarding & guide | `check-guide-script` (copy budget + eligibility contract — explicitly written *because* D-056 retired Maestro) · `check-s51-regen-diff` (S-43 post-Quick-Set reveal) |
| Feedback & notifications | `check-feedback-badge` (#184) · `check-invite-social-proof` (P1-5) · `check-notif-glyphs` (4-consumer enum parity) |

`npm run test:contrast` lives in [`../scripts/check-contrast.js`](../scripts/README.md), not here — it parses tokens rather than source shape.

## Guards with no npm script

`check-analytics-300.js` and `check-espn-nav-policy.js` are in the tree but absent from `package.json`.

**They still run in CI.** The `mobile-typecheck` job globs the directory rather than calling npm scripts:

```yaml
- run: for f in tests/check-*.js; do echo "── $f"; node "$f" || exit 1; done
```

So a guard is live in CI the moment the file exists — dropping a `check-*.js` here is enough to gate `main`, and a broken one fails the build whether or not anyone wired a script. The missing npm script only costs local ergonomics (`node tests/check-<name>.js` still works). Add the script when you touch either, but do not assume an unscripted guard is inert.

## Writing one

- **Dependency-free.** There is no jest harness in this project (`check-offer-prefill-330-unit.js` says so in its header). Guards run under plain `node`, using `fs` + regex or a hand-rolled transpile of the target module. That is why the modules they execute (`utils/feedbackBadge`, `sessionRerank`, `leagueUnlocks`, `firstSessionMoment`, `anchorRows`, `rankPresets`, `matchesDerive`, `mockPool`, `tickerWindow`, `applyJobResult`) are kept free of runtime imports — check the file header before adding one.
- **Open with `WHY THIS EXISTS`** naming the defect and the failure mode. A guard whose reason is not written down gets deleted by the next person who finds it annoying.
- **Assert shape, not values,** when the bug is structural: "exactly one call site clears the selection", "the rail is outside every conditional", "the label comes from the shared map".
- **Label honestly.** If the guard proves presence and not behavior, say so in the header, the way the G-035-labeled files do.
- **Register an `npm run test:<name>` script** in `mobile/package.json`.
