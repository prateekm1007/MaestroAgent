/**
 * LoginScreen — with registration support.
 *
 * Ports the login/register toggle pattern from web/src/components/maestro/Login.tsx.
 * Adds:
 *   - Email field (shown for register, optional for login)
 *   - Toggle between "Sign In" and "Create Account"
 *   - Calls /api/auth/register when in register mode
 *
 * Fixes the 4-round-old finding: zero references to /api/auth/register
 * anywhere in mobile/src.
 */

import React, { useState, useEffect } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet, ActivityIndicator,
  SafeAreaView, StatusBar, KeyboardAvoidingView, Platform,
} from 'react-native';
import * as Haptics from 'expo-haptics';
import * as SecureStore from 'expo-secure-store';
import AsyncStorage from '@react-native-async-storage/async-storage';

import { colors, getTheme, spacing } from '../theme/colors';
import { useAuth, useTheme } from '../contexts';
import { LLMDot } from '../components';
import { styles } from '../styles';
import { login, register } from '../api/client';

export default function LoginScreen() {
  const { mode } = useTheme();
  const t = getTheme(mode);
  const { llmStatus, token: existingToken, setToken } = useAuth() as any;
  const [password, setPassword] = useState('');
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [serverUrl, setServerUrl] = useState('http://localhost:8766');
  const [showServerConfig, setShowServerConfig] = useState(false);
  const [isRegister, setIsRegister] = useState(false);

  // Load saved server URL on mount
  useEffect(() => {
    AsyncStorage.getItem('maestro_host').then(url => {
      if (url) setServerUrl(url);
    });
  }, []);

  const handleLogin = async () => {
    // Validate inputs
    if (!password || !password.trim()) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
      setError('Enter your password.');
      return;
    }
    if (isRegister && !email.trim()) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
      setError('Enter your email to register.');
      return;
    }

    setLoading(true);
    setError(null);

    // Save server URL before login
    await AsyncStorage.setItem('maestro_host', serverUrl);

    try {
      const result = isRegister
        ? await register(email.trim(), password)
        : await login(password);

      if (result && result.token) {
        // Store token securely
        await SecureStore.setItemAsync('maestro_token', result.token)
          .catch(() => AsyncStorage.setItem('maestro_token', result.token));
        setToken(result.token);
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      } else {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
        setError(result?.message || (isRegister ? 'Registration failed' : 'Login failed'));
      }
    } catch (err: any) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      const msg = err?.response?.data?.detail || err?.message || 'Network error';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const toggleMode = () => {
    setIsRegister(r => !r);
    setError(null);
    setPassword('');
    setEmail('');
  };

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: t.bg }]}>
      <StatusBar barStyle={mode === 'dark' ? 'light-content' : 'dark-content'} />
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1, justifyContent: 'center', paddingHorizontal: spacing.xxxl }}>
        <View style={{ alignItems: 'center', marginBottom: 48 }}>
          <Text style={{ color: colors.yellow, fontSize: 32, fontWeight: 'bold', letterSpacing: 2 }}>MAESTRO</Text>
          <Text style={{ color: t.textSecondary, fontSize: 14, marginTop: spacing.sm }}>Personal Intelligence</Text>
        </View>

        {/* Server URL config (collapsible) */}
        {showServerConfig && (
          <TextInput
            style={[
              styles.loginInput,
              { backgroundColor: t.surface, color: t.textPrimary, borderColor: colors.yellow, marginBottom: spacing.sm, fontSize: 13 },
            ]}
            placeholder="Server URL (http://host:port)"
            placeholderTextColor={t.textSecondary}
            value={serverUrl}
            onChangeText={setServerUrl}
            autoCapitalize="none"
            autoCorrect={false}
            accessibilityLabel="Server URL"
            accessibilityHint="Enter the Maestro backend server URL"
          />
        )}
        <TouchableOpacity
          onPress={() => setShowServerConfig(!showServerConfig)}
          style={{ alignSelf: 'flex-end', marginBottom: spacing.md }}
          accessibilityRole="button"
          accessibilityLabel={showServerConfig ? 'Hide server URL config' : 'Show server URL config'}
        >
          <Text style={{ color: t.textSecondary, fontSize: 12 }}>{showServerConfig ? '▲ Hide' : '⚙ Server: ' + serverUrl.replace('http://', '').replace('https://', '')}</Text>
        </TouchableOpacity>

        {/* Email field — shown for register, optional for login */}
        {isRegister && (
          <TextInput
            style={[
              styles.loginInput,
              { backgroundColor: t.surface, color: t.textPrimary, borderColor: 'transparent', marginBottom: spacing.sm },
            ]}
            placeholder="Email (you@example.com)"
            placeholderTextColor={t.textSecondary}
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="email-address"
            accessibilityLabel="Email"
            accessibilityHint="Enter your email to register"
          />
        )}

        <TextInput
          style={[
            styles.loginInput,
            { backgroundColor: t.surface, color: t.textPrimary, borderColor: error ? colors.alertRed : 'transparent' },
          ]}
          placeholder={isRegister ? 'Choose a password' : 'Password (demo mode: any value)'}
          placeholderTextColor={t.textSecondary}
          value={password}
          onChangeText={setPassword}
          onSubmitEditing={handleLogin}
          secureTextEntry
          autoCapitalize="none"
          accessibilityLabel="Password"
          accessibilityHint={isRegister ? 'Choose a password for your account' : 'Enter your password'}
        />

        {error && (
          <Text style={{ color: colors.alertRed, fontSize: 13, marginTop: spacing.sm, textAlign: 'center' }} accessibilityRole="alert">
            {error}
          </Text>
        )}

        <TouchableOpacity
          style={[styles.loginButton, { backgroundColor: colors.yellow, opacity: loading ? 0.5 : 1, marginTop: spacing.md }]}
          onPress={handleLogin}
          disabled={loading || !password || (isRegister && !email.trim())}
          accessibilityRole="button"
          accessibilityLabel={isRegister ? 'Create account' : 'Log in'}
          accessibilityHint={loading ? (isRegister ? 'Creating account' : 'Signing in') : (isRegister ? 'Creates a new Maestro account' : 'Logs you into Maestro')}
        >
          {loading ? (
            <ActivityIndicator color={colors.black} />
          ) : (
            <Text style={{ color: colors.black, fontSize: 16, fontWeight: 'bold' }}>
              {isRegister ? 'CREATE ACCOUNT →' : 'ENTER →'}
            </Text>
          )}
        </TouchableOpacity>

        {/* Toggle between Login and Register */}
        <TouchableOpacity
          onPress={toggleMode}
          style={{ marginTop: spacing.lg, alignSelf: 'center' }}
          accessibilityRole="button"
          accessibilityLabel={isRegister ? 'Switch to sign in' : 'Switch to register'}
        >
          <Text style={{ color: t.textSecondary, fontSize: 13 }}>
            {isRegister ? 'Already have an account? Sign in' : 'New here? Create an account'}
          </Text>
        </TouchableOpacity>

        <View style={{ position: 'absolute', bottom: 40, left: 0, right: 0, alignItems: 'center' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <LLMDot />
            <Text style={{ color: t.textSecondary, fontSize: 12 }}>
              {llmStatus?.active ? `${llmStatus.provider} · ${llmStatus.probe_latency_ms}ms` : 'rule-based mode'}
            </Text>
          </View>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
