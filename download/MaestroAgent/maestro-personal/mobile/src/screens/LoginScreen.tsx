/**
 * LoginScreen — extracted from the original App.tsx, unchanged in logic.
 *
 * Honey-accented access-code entry. Shows the LLM provider dot at the
 * bottom and a collapsible server URL override (saved to AsyncStorage).
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

export default function LoginScreen() {
  const { mode } = useTheme();
  const t = getTheme(mode);
  const { login, llmStatus, token: existingToken, setToken } = useAuth() as any;
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [serverUrl, setServerUrl] = useState('http://localhost:8766');
  const [showServerConfig, setShowServerConfig] = useState(false);

  // Load saved server URL on mount
  useEffect(() => {
    AsyncStorage.getItem('maestro_host').then(url => {
      if (url) setServerUrl(url);
    });
  }, []);

  const handleLogin = async () => {
    setLoading(true);
    setError(false);
    // Save server URL before login
    await AsyncStorage.setItem('maestro_host', serverUrl);
    // Demo mode: skip auth, use a hardcoded demo token
    try {
      await SecureStore.setItemAsync('maestro_token', 'demo-bypass-token')
        .catch(() => AsyncStorage.setItem('maestro_token', 'demo-bypass-token'));
      setToken('demo-bypass-token');
    } catch {
      setError(true);
    }
    setLoading(false);
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

        <TextInput
          style={[
            styles.loginInput,
            { backgroundColor: t.surface, color: t.textPrimary, borderColor: error ? colors.alertRed : 'transparent' },
          ]}
          placeholder="Demo mode — just tap ENTER"
          placeholderTextColor={t.textSecondary}
          value={password}
          onChangeText={setPassword}
          onSubmitEditing={handleLogin}
          autoCapitalize="none"
          accessibilityLabel="Access code"
          accessibilityHint="Demo mode — just tap ENTER to explore"
          accessibilityRole="text"
        />

        <TouchableOpacity
          style={[styles.loginButton, { backgroundColor: colors.yellow, opacity: loading ? 0.5 : 1 }]}
          onPress={handleLogin}
          disabled={loading}
          accessibilityRole="button"
          accessibilityLabel="Log in"
          accessibilityHint={loading ? 'Signing in' : 'Logs you into Maestro'}
        >
          {loading ? (
            <ActivityIndicator color={colors.black} />
          ) : (
            <Text style={{ color: colors.black, fontSize: 16, fontWeight: 'bold' }}>ENTER →</Text>
          )}
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
