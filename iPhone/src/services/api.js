// __DEV__ is a global in React Native, not an import
const BASE_URL = __DEV__ ? 'http://192.168.1.88:5000' : 'https://your-production-server.com';

async function request(path, options = {}) {
  const url = `${BASE_URL}${path}`;
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

export const api = {
  // Auth
  lookupUser: (username) => request(`/api/sleeper/user/${encodeURIComponent(username)}`),
  getLeagues: (userId) => request(`/api/sleeper/leagues/${userId}`),

  // Session
  warmPlayerCache: () => request('/api/sleeper/players'),
  getRosters: (leagueId) => request(`/api/sleeper/rosters/${leagueId}`),
  getLeagueUsers: (leagueId) => request(`/api/sleeper/league_users/${leagueId}`),
  initSession: (body) => request('/api/session/init', { method: 'POST', body: JSON.stringify(body) }),

  // Ranking
  getTrio: (position) => request(`/api/trio?position=${position}`),
  submitRanking: (ranked) => request('/api/rank3', { method: 'POST', body: JSON.stringify({ ranked }) }),
  getProgress: (position) => request(`/api/progress?position=${position}`),
  getRankings: (position) => request(`/api/rankings?position=${position}`),
  getRankingsProgress: () => request('/api/rankings/progress'),
  getRookies: () => request('/api/rookies'),

  // Trades
  generateTrades: (leagueId, fairnessThreshold) => request('/api/trades/generate', { method: 'POST', body: JSON.stringify({ league_id: leagueId, fairness_threshold: fairnessThreshold }) }),
  getTrades: (leagueId) => request(`/api/trades?league_id=${leagueId}`),
  swipeTrade: (tradeId, decision) => request('/api/trades/swipe', { method: 'POST', body: JSON.stringify({ trade_id: tradeId, decision }) }),
  getLikedTrades: () => request('/api/trades/liked'),
  getMatches: () => request('/api/trades/matches'),
  recordDisposition: (matchId, decision) => request(`/api/trades/matches/${matchId}/disposition`, { method: 'POST', body: JSON.stringify({ decision }) }),

  // League
  getCoverage: (leagueId) => request(`/api/league/coverage?league_id=${leagueId}`),
  getPreferences: (leagueId) => request(`/api/league/preferences?league_id=${leagueId}`),
  savePreferences: (body) => request('/api/league/preferences', { method: 'POST', body: JSON.stringify(body) }),

  // Notifications
  getNotifications: () => request('/api/notifications'),
  markNotificationsRead: () => request('/api/notifications/read', { method: 'POST' }),
};
