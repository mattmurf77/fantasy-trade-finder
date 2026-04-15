import React from 'react';
import { Platform } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { NavigationContainer } from '@react-navigation/native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { AppProvider } from './src/context/AppContext';
import AppNavigator from './src/navigation/AppNavigator';

// React Navigation v7 requires a `fonts` key in the theme
const AppTheme = {
  dark: true,
  colors: {
    primary: '#4f7cff',
    background: '#0f1117',
    card: '#1a1d27',
    text: '#e8eaf0',
    border: '#2a2d3a',
    notification: '#ef4444',
  },
  fonts: Platform.select({
    ios: {
      regular: { fontFamily: 'System', fontWeight: '400' },
      medium: { fontFamily: 'System', fontWeight: '500' },
      bold: { fontFamily: 'System', fontWeight: '700' },
      heavy: { fontFamily: 'System', fontWeight: '800' },
    },
    default: {
      regular: { fontFamily: 'sans-serif', fontWeight: '400' },
      medium: { fontFamily: 'sans-serif-medium', fontWeight: '500' },
      bold: { fontFamily: 'sans-serif', fontWeight: '700' },
      heavy: { fontFamily: 'sans-serif', fontWeight: '800' },
    },
  }),
};

export default function App() {
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <AppProvider>
          <NavigationContainer theme={AppTheme}>
            <StatusBar style="light" />
            <AppNavigator />
          </NavigationContainer>
        </AppProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
