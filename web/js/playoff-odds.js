/* Playoff odds display rule (D-262; docs/cross-client-invariants.md
   § "Playoff odds: 100% and 0% need a proof"). A chance that would print as
   100% prints 100% only when the server proved the team clinched
   (`playoff_clinched`); otherwise ">99.9%" (one decimal) or ">99%" (whole
   percents). 0% needs `playoff_eliminated`; otherwise "<0.1%" / "<1%".
   Every other value prints as before. Absent flags mean not proven.
   Mirrors mobile/src/utils/playoffOdds.ts and backend clinch.odds_text. */
(() => {
  'use strict';
  const BELOW = {0.1: '<0.1%', 1: '<1%'}, ABOVE = {0.1: '>99.9%', 1: '>99%'};
  const printed = (p, step) => step === 1 ? String(Math.floor(p * 100 + 0.5 + 1e-9)) : (p * 100).toFixed(1);
  function text(probability, proof, step) {
    const p = Math.max(0, Math.min(1, Number.isFinite(probability) ? probability : 0));
    const out = printed(p, step), value = Number(out);
    if (value >= 100 && proof?.playoff_clinched !== true) return ABOVE[step];
    if (value <= 0 && proof?.playoff_eliminated !== true) return BELOW[step];
    return `${out}%`;
  }
  const miss = (probability, proof, step) =>
    text(probability, {playoff_clinched: proof?.playoff_eliminated, playoff_eliminated: proof?.playoff_clinched}, step);
  /* Equal probabilities: a proven clinch first, a proven elimination last. */
  const rank = proof => proof?.playoff_clinched === true ? 1 : proof?.playoff_eliminated === true ? -1 : 0;
  window.FTFPlayoffOdds = {text, miss, rank};
})();
