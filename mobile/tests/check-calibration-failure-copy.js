/** Execute the actual failed-session copy function; no renderer or network. */
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');
const screen = fs.readFileSync(path.join(__dirname, '../src/screens/CalibrationScreen.tsx'), 'utf8');
const copy = screen.slice(screen.indexOf('const COPY = {'), screen.indexOf('} as const;', screen.indexOf('const COPY = {')) + 1)
  .replaceAll('(league: string)', '(league)').replaceAll('(date: string)', '(date)').replaceAll('(k: number, n: number)', '(k, n)');
const start = screen.indexOf('const failedCopy = ');
const failure = screen.slice(start, screen.indexOf('\n};', start) + 3)
  .replace('(session: GradingSession): string', '(session)');
const context = vm.createContext({});
vm.runInContext(copy + ';\n' + failure + '\nthis.explain = code => failedCopy({error: {code}}); this.copy = COPY;', context);
for (const code of ['provider_lineup_unsupported', 'provider_cross_domain_eligibility', 'provider_player_eligibility_unsupported', 'provider_position_limits_unsupported']) {
  assert.strictEqual(context.explain(code), context.copy.unsupported);
  assert(!context.explain(code).includes('Try a connected Sleeper'));
}
for (const code of ['league_membership_required', 'league_seat_changed', 'espn_auth_required', 'mfl_auth_required', 'espn_credentials_unavailable', 'mfl_credentials_unavailable']) {
  assert.strictEqual(context.explain(code), context.copy.reconnect);
}
assert.strictEqual(context.explain('provider_account_binding_unavailable'), context.copy.accountLink);
assert.strictEqual(context.explain('comparison_too_few'), context.copy.tooFew);
assert.strictEqual(context.explain('unrecognized_failure'), context.copy.buildFailed);
console.log('Calibration failure copy: actual function checks passed');
