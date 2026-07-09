/**
 * LoginScreen — warm, inviting, Bumble-style.
 *
 * Honey accent, cream background, bold title. Feels human, not corporate.
 */

import React, { useState } from 'react';
import { View, Text, TextInput, Button, StyleSheet, Alert, TouchableOpacity } from 'react-native';
import { useAuth } from '../api/auth';
import { theme } from '../theme';

export default function LoginScreen() {
  const { login } = useAuth();
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = async () => {
    setLoading(true);
    try {
      await login(password || 'any');
    } catch (error) {
      Alert.alert('Login Failed', String(error));
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.content}>
        <View style={styles.logoCircle}>
          <Text style={styles.logoText}>M</Text>
        </View>
        <Text style={styles.title}>Maestro</Text>
        <Text style={styles.subtitle}>Make me effective today</Text>

        <View style={styles.formContainer}>
          <TextInput
            style={styles.input}
            placeholder="Password (any for now)"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            autoCapitalize="none"
            placeholderTextColor={theme.textSecondary}
          />
          <TouchableOpacity
            style={[styles.loginBtn, loading && styles.loginBtnDisabled]}
            onPress={handleLogin}
            disabled={loading}
          >
            <Text style={styles.loginBtnText}>{loading ? 'Logging in...' : 'Get Started'}</Text>
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.bg,
    justifyContent: 'center',
  },
  content: {
    alignItems: 'center',
    paddingHorizontal: 32,
  },
  logoCircle: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: theme.honey,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 24,
    ...theme.shadow.card,
  },
  logoText: {
    fontSize: 36,
    fontWeight: '900',
    color: theme.textOnHoney,
  },
  title: {
    fontSize: 36,
    fontWeight: '900',
    color: theme.textPrimary,
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 17,
    color: theme.textSecondary,
    marginBottom: 48,
  },
  formContainer: {
    width: '100%',
  },
  input: {
    backgroundColor: theme.cardBg,
    borderWidth: 1,
    borderColor: theme.border,
    borderRadius: theme.radius.lg,
    padding: 16,
    fontSize: 16,
    color: theme.textPrimary,
    marginBottom: 16,
  },
  loginBtn: {
    backgroundColor: theme.honey,
    borderRadius: theme.radius.lg,
    paddingVertical: 16,
    alignItems: 'center',
  },
  loginBtnDisabled: { opacity: 0.6 },
  loginBtnText: {
    color: theme.textOnHoney,
    fontSize: 17,
    fontWeight: '700',
  },
});
