import React, { createContext, useContext, useReducer, useCallback } from 'react';
import { storage } from '../utils/storage';

const AppContext = createContext();

const initialState = {
  user: null,           // { user_id, display_name, avatar_id }
  league: null,         // { league_id, league_name }
  leagues: [],          // all user's leagues
  currentOutlook: null,
  acquirePositions: [],
  tradeAwayPositions: [],
  notifications: [],
  isLoading: false,
  isInitialized: false,
};

function reducer(state, action) {
  switch (action.type) {
    case 'SET_USER':
      return { ...state, user: action.payload };
    case 'SET_LEAGUE':
      return { ...state, league: action.payload };
    case 'SET_LEAGUES':
      return { ...state, leagues: action.payload };
    case 'SET_OUTLOOK':
      return {
        ...state,
        currentOutlook: action.payload.outlook,
        acquirePositions: action.payload.acquire || [],
        tradeAwayPositions: action.payload.away || [],
      };
    case 'SET_NOTIFICATIONS':
      return { ...state, notifications: action.payload };
    case 'SET_LOADING':
      return { ...state, isLoading: action.payload };
    case 'SET_INITIALIZED':
      return { ...state, isInitialized: true };
    case 'LOGOUT':
      return { ...initialState, isInitialized: true };
    default:
      return state;
  }
}

export function AppProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, initialState);

  const setUser = useCallback((user) => {
    dispatch({ type: 'SET_USER', payload: user });
    if (user) storage.saveUser(user);
  }, []);

  const setLeague = useCallback((league) => {
    dispatch({ type: 'SET_LEAGUE', payload: league });
    if (league) storage.saveLeague(league);
  }, []);

  const setLeagues = useCallback((leagues) => {
    dispatch({ type: 'SET_LEAGUES', payload: leagues });
  }, []);

  const setOutlook = useCallback((outlook, acquire, away) => {
    dispatch({ type: 'SET_OUTLOOK', payload: { outlook, acquire, away } });
  }, []);

  const setNotifications = useCallback((notifs) => {
    dispatch({ type: 'SET_NOTIFICATIONS', payload: notifs });
  }, []);

  const setLoading = useCallback((val) => {
    dispatch({ type: 'SET_LOADING', payload: val });
  }, []);

  const setInitialized = useCallback(() => {
    dispatch({ type: 'SET_INITIALIZED' });
  }, []);

  const logout = useCallback(async () => {
    await storage.clearAll();
    dispatch({ type: 'LOGOUT' });
  }, []);

  const value = {
    ...state,
    setUser,
    setLeague,
    setLeagues,
    setOutlook,
    setNotifications,
    setLoading,
    setInitialized,
    logout,
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within AppProvider');
  return ctx;
}
