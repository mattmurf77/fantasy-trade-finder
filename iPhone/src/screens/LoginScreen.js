import React, { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  KeyboardAvoidingView, Platform, ActivityIndicator, Alert,
} from 'react-native';
import { colors, spacing, fontSize, borderRadius } from '../utils/theme';
import { api } from '../services/api';
import { useApp } from '../context/AppContext';

export default function LoginScreen({ navigation }) {
  const { setUser } = useApp();
  const [username, setUsername] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = async () => {
    const trimmed = username.trim().toLowerCase();
    if (!trimmed) {
      setError('Please enter your Sleeper username.');
      return;
    }
    setError('');
    setLoading(true);

    try {
      const data = await api.lookupUser(trimmed);
      if (!data || !data.user_id) {
        setError('Username not found on Sleeper. Check spelling.');
        setLoading(false);
        return;
      }
      const user = {
        user_id: data.user_id,
        display_name: data.display_name || data.username || trimmed,
        avatar_id: data.avatar || null,
      };
      setUser(user);
      navigation.replace('LeagueSelect');
    } catch (e) {
      setError(e.message || 'Could not reach server. Is the backend running?');
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <View style={styles.card}>
        <Text style={styles.logo}>
          Dynasty <Text style={styles.logoAccent}>Trade Finder</Text>
        </Text>
        <Text style={styles.subtitle}>
          Enter your Sleeper username to import your roster and get personalised trade ideas.
        </Text>

        <View style={styles.field}>
          <Text style={styles.label}>SLEEPER USERNAME</Text>
          <TextInput
            style={[styles.input, error ? styles.inputError : null]}
            value={username}
            onChangeText={(t) => { setUsername(t); setError(''); }}
            placeholder="e.g. dynastyking99"
            placeholderTextColor={colors.muted}
            autoCapitalize="none"
            autoCorrect={false}
            autoComplete="off"
            returnKeyType="go"
            onSubmitEditing={handleLogin}
          />
          {error ? <Text style={styles.error}>{error}</Text> : null}
        </View>

        <TouchableOpacity
          style={[styles.button, loading && styles.buttonDisabled]}
          onPress={handleLogin}
          disabled={loading}
          activeOpacity={0.8}
        >
          {loading ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.buttonText}>Connect with Sleeper →</Text>
          )}
        </TouchableOpacity>

        <Text style={styles.note}>
          No account required — Sleeper's API is public.{'\n'}
          Your data stays on your device.
        </Text>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.xl,
  },
  card: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: borderRadius.xl,
    padding: 36,
    width: '100%',
    maxWidth: 400,
    gap: spacing.xxl,
  },
  logo: {
    fontSize: fontSize.xl,
    fontWeight: '700',
    color: colors.text,
    textAlign: 'center',
    letterSpacing: -0.4,
  },
  logoAccent: { color: colors.accent },
  subtitle: {
    textAlign: 'center',
    fontSize: 14,
    color: colors.muted,
    lineHeight: 21,
    marginTop: -12,
  },
  field: { gap: spacing.sm },
  label: {
    fontSize: fontSize.sm,
    fontWeight: '600',
    color: colors.muted,
    letterSpacing: 0.3,
  },
  input: {
    backgroundColor: 'rgba(255,255,255,0.05)',
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: borderRadius.sm,
    color: colors.text,
    fontSize: fontSize.md,
    padding: 12,
  },
  inputError: { borderColor: colors.red },
  error: { fontSize: fontSize.sm, color: colors.red },
  button: {
    backgroundColor: colors.accent,
    borderRadius: borderRadius.sm,
    padding: 13,
    alignItems: 'center',
  },
  buttonDisabled: { opacity: 0.5 },
  buttonText: { color: '#fff', fontSize: fontSize.md, fontWeight: '600' },
  note: {
    fontSize: 12,
    color: colors.muted,
    textAlign: 'center',
    lineHeight: 18,
  },
});
