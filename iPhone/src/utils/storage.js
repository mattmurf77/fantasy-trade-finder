import AsyncStorage from '@react-native-async-storage/async-storage';

const KEYS = {
  USER: 'sleeper_user',
  LEAGUE: 'sleeper_league',
  AUTO_CONFIRM: 'autoConfirm',
  FAIRNESS: (leagueId) => `fairness_threshold_${leagueId || 'default'}`,
};

export const storage = {
  // User
  async getUser() {
    try {
      const val = await AsyncStorage.getItem(KEYS.USER);
      return val ? JSON.parse(val) : null;
    } catch { return null; }
  },
  async saveUser(user) {
    await AsyncStorage.setItem(KEYS.USER, JSON.stringify(user));
  },
  async clearUser() {
    await AsyncStorage.removeItem(KEYS.USER);
  },

  // League
  async getLeague() {
    try {
      const val = await AsyncStorage.getItem(KEYS.LEAGUE);
      return val ? JSON.parse(val) : null;
    } catch { return null; }
  },
  async saveLeague(league) {
    await AsyncStorage.setItem(KEYS.LEAGUE, JSON.stringify(league));
  },
  async clearLeague() {
    await AsyncStorage.removeItem(KEYS.LEAGUE);
  },

  // Auto-confirm
  async getAutoConfirm() {
    try {
      return (await AsyncStorage.getItem(KEYS.AUTO_CONFIRM)) === 'true';
    } catch { return false; }
  },
  async setAutoConfirm(val) {
    await AsyncStorage.setItem(KEYS.AUTO_CONFIRM, val ? 'true' : 'false');
  },

  // Fairness
  async getFairness(leagueId) {
    try {
      const val = await AsyncStorage.getItem(KEYS.FAIRNESS(leagueId));
      return val ? JSON.parse(val) : { value: 75, equal: false };
    } catch { return { value: 75, equal: false }; }
  },
  async saveFairness(leagueId, data) {
    await AsyncStorage.setItem(KEYS.FAIRNESS(leagueId), JSON.stringify(data));
  },

  // Full clear
  async clearAll() {
    await AsyncStorage.multiRemove([KEYS.USER, KEYS.LEAGUE, KEYS.AUTO_CONFIRM]);
  },
};
