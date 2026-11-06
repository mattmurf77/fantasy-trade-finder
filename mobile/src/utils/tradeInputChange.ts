// Classify the next explicit Find a Trade tap after a completed change.
// Process-local only. No league, roster, account or player identifiers leave
// this helper. The age distinguishes an immediate tap from time spent on Home.
type Change = 'after_league_switch' | 'after_preferences_change' | 'after_format_switch' | 'after_account_switch';
let pending: { scenario: Change; at: number } | undefined;
export function noteTradeInputChange(scenario: Change, now = performance.now()) {
  pending = { scenario, at: now };
}
export function takeTradeInputChange(now = performance.now()) {
  const change = pending;
  pending = undefined;
  if (!change) return {};
  return { scenario: change.scenario, input_age_ms: Math.max(0, Math.round(now - change.at)) };
}
