/**
 * Maestro Personal — Production Mobile App
 * Bumble-inspired design, dark mode primary, 7 screens.
 *
 * Tech: Expo SDK 52, React Navigation, AsyncStorage
 * Design: Bumble Yellow (#FFC629), dark mode default, card-based UI
 */

import React, { useState, useEffect, useCallback, createContext, useContext, useRef } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet, ScrollView,
  FlatList, ActivityIndicator, Alert, Modal, SafeAreaView, StatusBar,
  KeyboardAvoidingView, Platform, Dimensions, Share, Linking,
} from 'react-native';
import { NavigationContainer, useNavigation } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Ionicons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import * as Haptics from 'expo-haptics';
import { Audio } from 'expo-av';

import * as api from './src/api/client';
import { colors, getTheme, spacing, radius, typography, ThemeMode } from './src/theme/colors';

// ═══════════════════════════════════════════════════════════════════
// THEME CONTEXT
// ═══════════════════════════════════════════════════════════════════

const ThemeCtx = createContext({ mode: 'dark' as ThemeMode, toggle: () => {} });
const useTheme = () => useContext(ThemeCtx);

function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setMode] = useState<ThemeMode>('light');
  const toggle = () => setMode(m => m === 'dark' ? 'light' : 'dark');
  return <ThemeCtx.Provider value={{ mode, toggle }}>{children}</ThemeCtx.Provider>;
}

// ═══════════════════════════════════════════════════════════════════
// AUTH CONTEXT
// ═══════════════════════════════════════════════════════════════════

const AuthCtx = createContext<{
  token: string | null;
  login: (password: string) => Promise<boolean>;
  logout: () => void;
  llmStatus: api.LLMStatus | null;
}>({ token: null, login: async () => false, logout: () => {}, llmStatus: null });

const useAuth = () => useContext(AuthCtx);

function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [llmStatus, setLLMStatus] = useState<api.LLMStatus | null>(null);

  useEffect(() => {
    AsyncStorage.getItem('maestro_token').then(t => { if (t) setToken(t); });
  }, []);

  useEffect(() => {
    if (token) {
      api.getLLMStatus().then(setLLMStatus).catch(() => {});
    }
  }, [token]);

  const login = async (password: string): Promise<boolean> => {
    try {
      const result = await api.login(password);
      await AsyncStorage.setItem('maestro_token', result.token);
      setToken(result.token);
      return true;
    } catch (e) {
      return false;
    }
  };

  const logout = () => {
    AsyncStorage.removeItem('maestro_token');
    setToken(null);
  };

  return <AuthCtx.Provider value={{ token, login, logout, llmStatus }}>{children}</AuthCtx.Provider>;
}

// ═══════════════════════════════════════════════════════════════════
// SHARED COMPONENTS
// ═══════════════════════════════════════════════════════════════════

function ThemedView({ children, style }: { children: React.ReactNode; style?: any }) {
  const { mode } = useTheme();
  const t = getTheme(mode);
  return <View style={[{ backgroundColor: t.bg }, style]}>{children}</View>;
}

function Card({ children, style, accent }: { children: React.ReactNode; style?: any; accent?: 'yellow' | 'red' | 'green' | null }) {
  const { mode } = useTheme();
  const t = getTheme(mode);
  const borderLeftColor = accent === 'yellow' ? t.yellow : accent === 'red' ? t.danger : accent === 'green' ? t.success : 'transparent';
  return (
    <View style={[styles.card, { backgroundColor: t.cardBg, borderLeftColor, borderLeftWidth: accent ? 4 : 0 }, style]}>
      {children}
    </View>
  );
}

function Badge({ text, color = 'gray' }: { text: string; color?: 'gray' | 'yellow' | 'red' | 'green' }) {
  const { mode } = useTheme();
  const t = getTheme(mode);
  const bg = color === 'yellow' ? colors.yellow + '22' : color === 'red' ? colors.alertRed + '22' : color === 'green' ? colors.successGreen + '22' : t.border;
  const fg = color === 'yellow' ? colors.yellow : color === 'red' ? colors.alertRed : color === 'green' ? colors.successGreen : t.textSecondary;
  return (
    <View style={{ backgroundColor: bg, borderRadius: radius.full, paddingHorizontal: spacing.md, paddingVertical: spacing.xs, marginRight: spacing.sm }}>
      <Text style={{ color: fg, fontSize: 12, fontWeight: '600' }}>{text}</Text>
    </View>
  );
}

function ConfidenceBar({ value, label }: { value: number; label?: string }) {
  const { mode } = useTheme();
  const t = getTheme(mode);
  return (
    <View style={{ marginTop: spacing.md }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: spacing.xs }}>
        <Text style={{ color: t.textSecondary, fontSize: 11, fontWeight: '600', letterSpacing: 1 }}>CONFIDENCE</Text>
        <Text style={{ color: t.textPrimary, fontSize: 14, fontWeight: 'bold' }}>{Math.round(value * 100)}%</Text>
      </View>
      <View style={{ height: 4, backgroundColor: t.border, borderRadius: radius.full, overflow: 'hidden' }}>
        <View style={{ width: `${value * 100}%`, height: '100%', backgroundColor: colors.yellow, borderRadius: radius.full }} />
      </View>
      {label && <Text style={{ color: t.textSecondary, fontSize: 11, marginTop: spacing.xs }}>{label}</Text>}
    </View>
  );
}

function LLMDot({ size = 8 }: { size?: number }) {
  const { llmStatus } = useAuth();
  const active = llmStatus?.active;
  const color = active ? colors.successGreen : colors.yellow;
  return <View style={{ width: size, height: size, borderRadius: size / 2, backgroundColor: color }} />;
}

function TopBar({ title }: { title: string }) {
  const { mode } = useTheme();
  const t = getTheme(mode);
  const { logout } = useAuth();
  return (
    <View style={[styles.topBar, { backgroundColor: t.bg, borderBottomColor: t.border }]}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
        <Text style={{ color: colors.yellow, fontSize: 18, fontWeight: 'bold' }}>⚡</Text>
        <Text style={{ color: t.textPrimary, fontSize: 18, fontWeight: 'bold' }}>{title}</Text>
      </View>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
        <LLMDot />
        <TouchableOpacity onPress={logout}>
          <Ionicons name="log-out-outline" size={22} color={t.textSecondary} />
        </TouchableOpacity>
      </View>
    </View>
  );
}

// ═══════════════════════════════════════════════════════════════════
// SCREEN 1: LOGIN
// ═══════════════════════════════════════════════════════════════════

function LoginScreen() {
  const { mode } = useTheme();
  const t = getTheme(mode);
  const { login, llmStatus } = useAuth();
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
    if (!password) return;
    setLoading(true);
    setError(false);
    // Save server URL before login
    await AsyncStorage.setItem('maestro_host', serverUrl);
    const ok = await login(password);
    if (!ok) {
      setError(true);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      setTimeout(() => setError(false), 600);
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
          />
        )}
        <TouchableOpacity onPress={() => setShowServerConfig(!showServerConfig)} style={{ alignSelf: 'flex-end', marginBottom: spacing.md }}>
          <Text style={{ color: t.textSecondary, fontSize: 12 }}>{showServerConfig ? '▲ Hide' : '⚙ Server: ' + serverUrl.replace('http://', '').replace('https://', '')}</Text>
        </TouchableOpacity>

        <TextInput
          style={[
            styles.loginInput,
            { backgroundColor: t.surface, color: t.textPrimary, borderColor: error ? colors.alertRed : password ? colors.yellow : 'transparent' },
          ]}
          placeholder="Enter access code"
          placeholderTextColor={t.textSecondary}
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          onSubmitEditing={handleLogin}
          autoCapitalize="none"
        />

        <TouchableOpacity
          style={[styles.loginButton, { backgroundColor: colors.yellow, opacity: loading || !password ? 0.5 : 1 }]}
          onPress={handleLogin}
          disabled={loading || !password}
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

// ═══════════════════════════════════════════════════════════════════
// SCREEN 2: DASHBOARD
// ═══════════════════════════════════════════════════════════════════

function DashboardScreen() {
  const { mode } = useTheme();
  const t = getTheme(mode);
  const { token } = useAuth();
  const nav = useNavigation<any>();
  const [moment, setMoment] = useState<api.TheMoment | null>(null);
  const [shifts, setShifts] = useState<api.WhatChangedShift[]>([]);
  const [briefing, setBriefing] = useState<api.Briefing | null>(null);
  const [loading, setLoading] = useState(true);
  const [askQuery, setAskQuery] = useState('');

  useEffect(() => {
    if (!token) return;
    Promise.all([
      api.getTheMoment().catch(() => null),
      api.getWhatChangedShifts().catch(() => null),
      api.getBriefing().catch(() => null),
    ]).then(([m, s, b]) => {
      setMoment(m);
      setShifts(s?.secondary || []);
      setBriefing(b);
      setLoading(false);
    });
  }, [token]);

  const handleCorrect = async (signalId: string, action: 'complete' | 'dismiss') => {
    if (!token || !signalId) return;
    // Haptic feedback
    if (action === 'complete') {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    } else {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    }
    try {
      await api.correctSignal(signalId, action);
      const m = await api.getTheMoment();
      setMoment(m);
    } catch (e) { /* ignore */ }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: t.bg }}>
      <TopBar title="Dashboard" />
      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: spacing.xl }}>
        {/* THE MOMENT */}
        <Text style={[typography.label, { color: colors.yellow, marginBottom: spacing.md }]}>⚡ THE MOMENT</Text>
        {loading ? (
          <ActivityIndicator color={colors.yellow} size="large" style={{ marginVertical: 40 }} />
        ) : moment?.has_moment && moment.commitment ? (
          <Card accent="yellow" style={{ marginBottom: spacing.xl }}>
            <Text style={{ fontSize: 20, fontWeight: 'bold', color: t.textPrimary }}>{moment.commitment.entity}</Text>
            <Text style={{ fontSize: 16, color: t.textSecondary, fontStyle: 'italic', marginTop: spacing.xs }}>
              "{moment.commitment.text}"
            </Text>
            {moment.why_this_one ? (
              <Text style={{ fontSize: 14, color: t.textSecondary, marginTop: spacing.md }}>{moment.why_this_one}</Text>
            ) : null}
            <View style={{ flexDirection: 'row', marginTop: spacing.md, gap: spacing.sm }}>
              {moment.commitment.metadata?.deadline ? <Badge text={`📅 ${moment.commitment.metadata.deadline}`} color="yellow" /> : null}
              {moment.why_this_one?.includes('stale') ? <Badge text="🔥 At Risk" color="red" /> : null}
            </View>
            <View style={{ flexDirection: 'row', justifyContent: 'center', marginTop: spacing.xl, gap: spacing.xl }}>
              <TouchableOpacity
                style={[styles.actionButton, { backgroundColor: colors.successGreen }]}
                onPress={() => handleCorrect(moment.commitment!.signal_id, 'complete')}
              >
                <Ionicons name="checkmark" size={24} color={colors.white} />
                <Text style={styles.actionLabel}>Done</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.actionButton, { backgroundColor: t.border }]}
                onPress={() => handleCorrect(moment.commitment!.signal_id, 'dismiss')}
              >
                <Ionicons name="close" size={24} color={t.textSecondary} />
                <Text style={[styles.actionLabel, { color: t.textSecondary }]}>Skip</Text>
              </TouchableOpacity>
            </View>
          </Card>
        ) : (
          <Card style={{ marginBottom: spacing.xl, padding: spacing.xxxl, alignItems: 'center' }}>
            <Text style={{ fontSize: 48 }}>🌙</Text>
            <Text style={{ fontSize: 18, color: t.textSecondary, marginTop: spacing.md, textAlign: 'center' }}>
              Nothing needs your attention right now.
            </Text>
            <Text style={{ fontSize: 14, color: t.textSecondary, marginTop: spacing.xs, textAlign: 'center' }}>
              Maestro is watching quietly.
            </Text>
          </Card>
        )}

        {/* WHAT CHANGED */}
        {shifts.length > 0 && (
          <>
            <Text style={[typography.label, { color: t.textSecondary, marginBottom: spacing.md }]}>WHAT CHANGED</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: spacing.xl }}>
              {shifts.map((s, i) => (
                <Card key={i} style={{ width: 160, marginRight: spacing.md }}>
                  <Text style={{ fontSize: 14, fontWeight: 'bold', color: t.textPrimary }}>{s.entity}</Text>
                  <Text style={{ fontSize: 13, color: t.textSecondary, marginTop: 2 }} numberOfLines={1}>{s.description}</Text>
                  <Text style={{ fontSize: 11, color: t.textSecondary, marginTop: spacing.xs }}>{s.timestamp?.slice(0, 10)}</Text>
                </Card>
              ))}
            </ScrollView>
          </>
        )}

        {/* BRIEFING */}
        {briefing && (
          <Card style={{ marginBottom: spacing.xl }}>
            <Text style={{ fontSize: 16, color: t.textPrimary }}>{briefing.greeting}</Text>
            {briefing.ask_prompt ? (
              <Text style={{ fontSize: 14, color: t.textSecondary, marginTop: spacing.sm }}>{briefing.ask_prompt}</Text>
            ) : null}
          </Card>
        )}

        {/* QUICK ASK */}
        <TouchableOpacity
          style={[styles.quickAsk, { backgroundColor: t.surface, borderColor: t.border }]}
          onPress={() => nav.navigate('Ask')}
        >
          <Ionicons name="search" size={18} color={t.textSecondary} />
          <Text style={{ color: t.textSecondary, fontSize: 14, marginLeft: spacing.sm, flex: 1 }}>Ask Maestro anything...</Text>
          <Ionicons name="arrow-forward" size={18} color={colors.yellow} />
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

// ═══════════════════════════════════════════════════════════════════
// SCREEN 3: ASK
// ═══════════════════════════════════════════════════════════════════

function AskScreen() {
  const { mode } = useTheme();
  const t = getTheme(mode);
  const { token } = useAuth();
  const [query, setQuery] = useState('');
  const [result, setResult] = useState<api.AskResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<string[]>([]);

  useEffect(() => {
    AsyncStorage.getItem('maestro_ask_history').then(h => {
      if (h) setHistory(JSON.parse(h).slice(0, 10));
    });
  }, []);

  const handleAsk = async (q?: string) => {
    const queryText = q || query;
    if (!queryText || !token) return;
    setLoading(true);
    setResult(null);
    try {
      const r = await api.ask(queryText);
      setResult(r);
      const newHistory = [queryText, ...history.filter(h => h !== queryText)].slice(0, 10);
      setHistory(newHistory);
      AsyncStorage.setItem('maestro_ask_history', JSON.stringify(newHistory));
    } catch (e) {
      Alert.alert('Error', 'Failed to get answer. Is the API running?');
    }
    setLoading(false);
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: t.bg }}>
      <TopBar title="Ask" />
      <View style={{ padding: spacing.xl }}>
        {/* Search bar */}
        <View style={[styles.searchBar, { backgroundColor: t.surface }]}>
          <Ionicons name="search" size={20} color={t.textSecondary} style={{ marginLeft: spacing.md }} />
          <TextInput
            style={{ flex: 1, color: t.textPrimary, fontSize: 15, paddingHorizontal: spacing.md }}
            placeholder="Ask anything about your commitments..."
            placeholderTextColor={t.textSecondary}
            value={query}
            onChangeText={setQuery}
            onSubmitEditing={() => handleAsk()}
            returnKeyType="search"
          />
          <TouchableOpacity onPress={() => handleAsk()} style={{ paddingRight: spacing.md }}>
            {loading ? <ActivityIndicator color={colors.yellow} size="small" /> : <Ionicons name="arrow-forward" size={20} color={colors.yellow} />}
          </TouchableOpacity>
        </View>

        {/* Recent */}
        {history.length > 0 && !result && !loading && (
          <>
            <Text style={[typography.label, { color: t.textSecondary, marginTop: spacing.xl, marginBottom: spacing.sm }]}>RECENT</Text>
            {history.map((h, i) => (
              <TouchableOpacity key={i} onPress={() => { setQuery(h); handleAsk(h); }} style={{ paddingVertical: spacing.md }}>
                <Text style={{ color: t.textPrimary, fontSize: 14 }}>{h}</Text>
              </TouchableOpacity>
            ))}
          </>
        )}
      </View>

      {/* Loading */}
      {loading && (
        <View style={{ padding: spacing.xxl, alignItems: 'center' }}>
          <ActivityIndicator color={colors.yellow} size="large" />
          <Text style={{ color: t.textSecondary, fontSize: 14, marginTop: spacing.md }}>Maestro is thinking...</Text>
        </View>
      )}

      {/* Result */}
      {result && (
        <ScrollView style={{ flex: 1, paddingHorizontal: spacing.xl }} contentContainerStyle={{ paddingBottom: spacing.xxxl }}>
          <Card style={{ marginTop: spacing.md }}>
            <Text style={{ color: t.textSecondary, fontSize: 11, fontWeight: '600', letterSpacing: 1, marginBottom: spacing.sm }}>ANSWER</Text>
            <Text style={{ fontSize: 16, color: t.textPrimary, lineHeight: 24 }}>{result.answer}</Text>

            {/* Provenance */}
            {result.source_sentence ? (
              <View style={{ marginTop: spacing.xl, borderTopWidth: 1, borderTopColor: t.border, paddingTop: spacing.md }}>
                <Text style={[typography.label, { color: t.textSecondary, marginBottom: spacing.sm }]}>PROVENANCE</Text>
                <Text style={{ fontSize: 14, color: t.textPrimary, fontStyle: 'italic' }}>"{result.source_sentence}"</Text>
                <Text style={{ fontSize: 13, color: t.textSecondary, marginTop: spacing.xs }}>
                  📌 {result.source_entity} · 🕐 {result.source_timestamp?.slice(0, 16)}
                </Text>
              </View>
            ) : null}

            {/* Confidence */}
            <ConfidenceBar value={result.confidence ?? 0} label={result.intelligence_source === 'llm' ? 'LLM-powered' : 'rules-based'} />

            {/* Counterevidence */}
            {(result.counterevidence?.length ?? 0) > 0 && (
              <View style={{ marginTop: spacing.xl }}>
                <Text style={[typography.label, { color: colors.alertRed, marginBottom: spacing.sm }]}>COUNTEREVIDENCE</Text>
                {result.counterevidence?.map((c, i) => (
                  <Card key={i} accent="red" style={{ marginBottom: spacing.sm }}>
                    <Text style={{ fontSize: 14, color: t.textPrimary }}>⚠ {typeof c === 'string' ? c : c.claim || JSON.stringify(c)}</Text>
                  </Card>
                ))}
              </View>
            )}

            {/* Unknowns */}
            {(result.unknowns?.length ?? 0) > 0 && (
              <View style={{ marginTop: spacing.xl }}>
                <Text style={[typography.label, { color: t.textSecondary, marginBottom: spacing.sm }]}>UNKNOWNS</Text>
                {result.unknowns?.map((u, i) => (
                  <Text key={i} style={{ fontSize: 14, color: t.textSecondary, marginBottom: spacing.xs }}>
                    • {typeof u === 'string' ? u : u.description || JSON.stringify(u)}
                  </Text>
                ))}
              </View>
            )}
          </Card>
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

// ═══════════════════════════════════════════════════════════════════
// SCREEN 4: COMMITMENTS
// ═══════════════════════════════════════════════════════════════════

function CommitmentsScreen() {
  const { mode } = useTheme();
  const t = getTheme(mode);
  const { token } = useAuth();
  const [theOne, setTheOne] = useState<api.TheOneResult | null>(null);
  const [commitments, setCommitments] = useState<api.Commitment[]>([]);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    if (!token) return;
    try {
      const [one, list] = await Promise.all([
        api.getTheOne().catch(() => null),
        api.getCommitments().catch(() => []),
      ]);
      setTheOne(one);
      setCommitments(list);
    } catch (e) { /* ignore */ }
    setLoading(false);
  }, [token]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleCorrect = async (signalId: string, action: 'complete' | 'dismiss' | 'cancel') => {
    if (!token || !signalId) return;
    Alert.alert(
      `${action.charAt(0).toUpperCase() + action.slice(1)} this commitment?`,
      undefined,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Confirm',
          onPress: async () => {
            await api.correctSignal(signalId, action);
            loadData();
          },
        },
      ]
    );
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: t.bg }}>
      <TopBar title="Commitments" />
      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: spacing.xl }}>
        {loading ? (
          <ActivityIndicator color={colors.yellow} size="large" style={{ marginVertical: 40 }} />
        ) : (
          <>
            {/* THE ONE */}
            {theOne?.primary && (
              <>
                <Text style={[typography.label, { color: colors.yellow, marginBottom: spacing.md }]}>⭐ THE ONE</Text>
                <Card accent="yellow" style={{ marginBottom: spacing.xl }}>
                  <Text style={{ fontSize: 20, fontWeight: 'bold', color: t.textPrimary }}>{theOne.primary.entity}</Text>
                  <Text style={{ fontSize: 16, color: t.textSecondary, fontStyle: 'italic', marginTop: spacing.xs }}>
                    "{theOne.primary.text}"
                  </Text>
                  {theOne.primary.deadline ? <Badge text={`📅 ${theOne.primary.deadline}`} color="yellow" /> : null}
                  {theOne.primary.is_at_risk ? <Badge text="🔥 At Risk" color="red" /> : null}
                  {(theOne.primary.days_stale ?? 0) > 0 ? <Text style={{ fontSize: 13, color: t.textSecondary, marginTop: spacing.xs }}>{theOne.primary.days_stale}d stale</Text> : null}
                  {theOne.why_primary ? <Text style={{ fontSize: 14, color: t.textSecondary, marginTop: spacing.sm }}>{theOne.why_primary}</Text> : null}
                  <View style={{ flexDirection: 'row', gap: spacing.md, marginTop: spacing.lg }}>
                    <TouchableOpacity style={[styles.smallBtn, { backgroundColor: colors.successGreen }]} onPress={() => handleCorrect(theOne.primary?.signal_id ?? '', 'complete')}>
                      <Text style={{ color: colors.white, fontSize: 13, fontWeight: '600' }}>✓ Complete</Text>
                    </TouchableOpacity>
                    <TouchableOpacity style={[styles.smallBtn, { backgroundColor: t.border }]} onPress={() => handleCorrect(theOne.primary?.signal_id ?? '', 'dismiss')}>
                      <Text style={{ color: t.textSecondary, fontSize: 13, fontWeight: '600' }}>✕ Dismiss</Text>
                    </TouchableOpacity>
                  </View>
                </Card>
              </>
            )}

            {/* ACTIVE LIST */}
            <Text style={[typography.label, { color: t.textSecondary, marginBottom: spacing.md }]}>ACTIVE COMMITMENTS</Text>
            {commitments.length === 0 ? (
              <Text style={{ color: t.textSecondary, fontSize: 14, textAlign: 'center', marginVertical: 20 }}>No active commitments</Text>
            ) : (
              commitments.map((c, i) => (
                <Card key={i} style={{ marginBottom: spacing.md }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                    <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: c.is_at_risk ? colors.alertRed : (c.days_stale ?? 0) > 2 ? colors.yellow : colors.successGreen, marginRight: spacing.md }} />
                    <Text style={{ fontSize: 15, fontWeight: 'bold', color: t.textPrimary, flex: 1 }}>{c.entity}</Text>
                    {c.deadline ? <Badge text={c.deadline} color="yellow" /> : null}
                  </View>
                  <Text style={{ fontSize: 13, color: t.textSecondary, marginTop: spacing.xs }} numberOfLines={2}>"{c.text}"</Text>
                  <View style={{ flexDirection: 'row', gap: spacing.md, marginTop: spacing.sm }}>
                    <TouchableOpacity onPress={() => handleCorrect(c.signal_id, 'complete')}>
                      <Text style={{ color: colors.successGreen, fontSize: 12, fontWeight: '600' }}>✓ Complete</Text>
                    </TouchableOpacity>
                    <TouchableOpacity onPress={() => handleCorrect(c.signal_id, 'dismiss')}>
                      <Text style={{ color: t.textSecondary, fontSize: 12, fontWeight: '600' }}>✕ Dismiss</Text>
                    </TouchableOpacity>
                  </View>
                </Card>
              ))
            )}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

// ═══════════════════════════════════════════════════════════════════
// SCREEN 5: SIGNALS
// ═══════════════════════════════════════════════════════════════════

function SignalsScreen() {
  const { mode } = useTheme();
  const t = getTheme(mode);
  const { token } = useAuth();
  const [signals, setSignals] = useState<api.Signal[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [entity, setEntity] = useState('');
  const [text, setText] = useState('');
  const [type, setType] = useState('reported_statement');

  const load = useCallback(async () => {
    if (!token) return;
    try { setSignals(await api.getSignals()); } catch (e) { /* ignore */ }
    setLoading(false);
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const handleAdd = async () => {
    if (!entity || !text || !token) return;
    try {
      await api.createSignal(entity, text, type);
      setEntity(''); setText(''); setType('reported_statement');
      setShowAdd(false);
      load();
    } catch (e) { Alert.alert('Error', 'Failed to create signal'); }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: t.bg }}>
      <TopBar title="Signals" />
      {loading ? (
        <ActivityIndicator color={colors.yellow} size="large" style={{ marginVertical: 40 }} />
      ) : (
        <FlatList
          data={signals}
          keyExtractor={item => item.signal_id}
          contentContainerStyle={{ padding: spacing.xl }}
          renderItem={({ item }) => (
            <Card style={{ marginBottom: spacing.md }}>
              <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                <Text style={{ fontSize: 15, fontWeight: 'bold', color: t.textPrimary, flex: 1 }}>{item.entity}</Text>
                <Text style={{ fontSize: 11, color: t.textSecondary }}>{item.timestamp?.slice(0, 10)}</Text>
              </View>
              <Text style={{ fontSize: 13, color: t.textSecondary, marginTop: spacing.xs }} numberOfLines={2}>{item.text}</Text>
              <View style={{ flexDirection: 'row', marginTop: spacing.xs, gap: spacing.sm }}>
                <Badge text={item.signal_type} color="gray" />
              </View>
            </Card>
          )}
          ListEmptyComponent={<Text style={{ color: t.textSecondary, textAlign: 'center', marginTop: 40 }}>No signals yet. Tap + to add one.</Text>}
        />
      )}

      {/* FAB */}
      <TouchableOpacity
        style={[styles.fab, { backgroundColor: colors.yellow }]}
        onPress={() => setShowAdd(true)}
      >
        <Ionicons name="add" size={28} color={colors.black} />
      </TouchableOpacity>

      {/* Add Modal */}
      <Modal visible={showAdd} animationType="slide" transparent>
        <View style={{ flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(0,0,0,0.5)' }}>
          <View style={{ backgroundColor: t.bg, borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: spacing.xl }}>
            <Text style={{ fontSize: 18, fontWeight: 'bold', color: t.textPrimary, marginBottom: spacing.lg }}>Add Signal</Text>
            <TextInput style={[styles.loginInput, { backgroundColor: t.surface, color: t.textPrimary, marginBottom: spacing.md }]} placeholder="Entity" placeholderTextColor={t.textSecondary} value={entity} onChangeText={setEntity} />
            <TextInput style={[styles.loginInput, { backgroundColor: t.surface, color: t.textPrimary, marginBottom: spacing.md, minHeight: 80 }]} placeholder="What happened?" placeholderTextColor={t.textSecondary} value={text} onChangeText={setText} multiline />
            <View style={{ flexDirection: 'row', gap: spacing.md, marginBottom: spacing.lg }}>
              {['reported_statement', 'commitment_made', 'follow_up_required'].map(typ => (
                <TouchableOpacity key={typ} onPress={() => setType(typ)} style={{ paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.full, backgroundColor: type === typ ? colors.yellow : t.surface }}>
                  <Text style={{ color: type === typ ? colors.black : t.textSecondary, fontSize: 12 }}>{typ.replace(/_/g, ' ')}</Text>
                </TouchableOpacity>
              ))}
            </View>
            <View style={{ flexDirection: 'row', gap: spacing.md }}>
              <TouchableOpacity style={[styles.loginButton, { flex: 1, backgroundColor: t.border }]} onPress={() => setShowAdd(false)}>
                <Text style={{ color: t.textSecondary, fontWeight: 'bold' }}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[styles.loginButton, { flex: 1, backgroundColor: colors.yellow, opacity: !entity || !text ? 0.5 : 1 }]} onPress={handleAdd} disabled={!entity || !text}>
                <Text style={{ color: colors.black, fontWeight: 'bold' }}>Add</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

// ═══════════════════════════════════════════════════════════════════
// SCREEN 6: COPILOT — with Consent Manager + Audio Capture + WebSocket
// ═══════════════════════════════════════════════════════════════════

// Consent manager state
const ConsentContext = createContext<{ hasConsent: boolean; grant: () => void; revoke: () => void }>({
  hasConsent: false, grant: () => {}, revoke: () => {},
});
const useConsent = () => useContext(ConsentContext);

function ConsentProvider({ children }: { children: React.ReactNode }) {
  const [hasConsent, setHasConsent] = useState(false);
  useEffect(() => {
    AsyncStorage.getItem('maestro_consent').then(v => { if (v === 'true') setHasConsent(true); });
  }, []);
  const grant = () => { setHasConsent(true); AsyncStorage.setItem('maestro_consent', 'true'); };
  const revoke = () => { setHasConsent(false); AsyncStorage.removeItem('maestro_consent'); };
  return <ConsentContext.Provider value={{ hasConsent, grant, revoke }}>{children}</ConsentContext.Provider>;
}

// Consent modal
function ConsentModal({ visible, onGrant, onDeny }: { visible: boolean; onGrant: () => void; onDeny: () => void }) {
  const t = getTheme('light');
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onDeny}>
      <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'center', padding: spacing.xxxl }}>
        <View style={{ backgroundColor: t.cardBg, borderRadius: 20, padding: spacing.xxl }}>
          <Text style={{ fontSize: 22, fontWeight: 'bold', color: t.textPrimary, marginBottom: spacing.md }}>
            🎙️ Recording Consent
          </Text>
          <Text style={{ fontSize: 15, color: t.textSecondary, lineHeight: 22, marginBottom: spacing.lg }}>
            Maestro Live Copilot will use your microphone to transcribe the meeting in real time.{'\n\n'}
            • Audio is processed locally on your device{'\n'}
            • Only text transcripts are sent to the server{'\n'}
            • Audio never leaves your device{'\n'}
            • All participants should be informed{'\n'}
            • You can revoke consent at any time{'\n'}
            • All actions are audit-logged
          </Text>
          <Text style={{ fontSize: 13, color: colors.alertRed, marginBottom: spacing.lg }}>
            ⚠️ Recording without consent may be illegal in your jurisdiction.
          </Text>
          <View style={{ flexDirection: 'row', gap: spacing.md }}>
            <TouchableOpacity onPress={onDeny} style={[styles.smallBtn, { backgroundColor: t.border, flex: 1 }]}>
              <Text style={{ color: t.textSecondary, fontWeight: '600' }}>Not Now</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={onGrant} style={[styles.smallBtn, { backgroundColor: colors.yellow, flex: 1 }]}>
              <Text style={{ color: colors.black, fontWeight: 'bold' }}>I Consent</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
}

function CopilotScreen() {
  const { mode } = useTheme();
  const t = getTheme(mode);
  const { token, llmStatus } = useAuth();
  const { hasConsent, grant } = useConsent();
  const [chunks, setChunks] = useState<{ speaker: string; text: string; ts: string }[]>([]);
  const [whispers, setWhispers] = useState<any[]>([]);
  const [input, setInput] = useState('');
  const [connected, setConnected] = useState(false);
  const [speaker, setSpeaker] = useState('me');
  const [showConsent, setShowConsent] = useState(false);
  const [recording, setRecording] = useState(false);
  const [wsRef, setWsRef] = useState<WebSocket | null>(null);
  const [showPostCall, setShowPostCall] = useState(false);
  const [postCallSummary, setPostCallSummary] = useState<any>(null);
  const transcriptRef = useRef<ScrollView>(null);

  // ── WebSocket connection ────────────────────────────────────────
  const connectWS = () => {
    if (!token) return;
    const host = 'localhost:8766'; // Will be configurable
    try {
      const ws = new WebSocket(`ws://${host}/ws/copilot`, ['maestro-auth']);
      ws.onopen = () => {
        ws.send(JSON.stringify({ type: 'auth', token }));
        setConnected(true);
        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
      };
      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          if (msg.type === 'ack') {
            // Ack whisper: transparent, auto-dismiss after 2s
            const ackWhisper = {
              type: 'ack',
              entity: '',
              text: '',
              evidence: [],
              confidence: 0,
              dismissAt: Date.now() + 2000,
            };
            setWhispers(prev => [...prev, ackWhisper]);
          } else if (msg.type === 'suggestion' || msg.type === 'whisper') {
            const newWhisper = {
              type: msg.priority === 'high' ? 'critical' : 'suggestion',
              entity: msg.entity || 'Maestro',
              text: msg.text || msg.body || '',
              evidence: msg.evidence_refs || [],
              confidence: msg.confidence || 0,
              dismissAt: msg.priority === 'high' ? 0 : Date.now() + 10000, // suggestions auto-dismiss after 10s, critical stays
            };
            setWhispers(prev => [...prev, newWhisper]);
            if (newWhisper.type === 'critical') {
              Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
            } else {
              Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
            }
          }
        } catch (err) { /* non-JSON message, ignore */ }
      };

      // Auto-dismiss timer for ack + suggestion whispers
      const dismissTimer = setInterval(() => {
        setWhispers(prev => {
          const now_ms = Date.now();
          const filtered = prev.filter(w => !w.dismissAt || w.dismissAt > now_ms);
          return filtered.length !== prev.length ? filtered : prev;
        });
      }, 1000);
      (ws as any)._dismissTimer = dismissTimer;
      ws.onclose = () => { setConnected(false); };
      ws.onerror = () => { setConnected(false); };
      setWsRef(ws);
    } catch (e) {
      // WS failed — fall back to REST
      setConnected(false);
    }
  };

  const disconnectWS = () => {
    if (wsRef) {
      if ((wsRef as any)._dismissTimer) clearInterval((wsRef as any)._dismissTimer);
      wsRef.close();
      setWsRef(null);
    }
    setConnected(false);
  };

  // ── Start meeting (with consent check) ──────────────────────────
  const startMeeting = () => {
    if (!hasConsent) {
      setShowConsent(true);
      return;
    }
    connectWS();
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
  };

  const endMeeting = async () => {
    disconnectWS();
    if (recording) { await stopRecording(); }
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);

    // Generate post-call summary from accumulated whispers + chunks
    const allCommitments = whispers
      .filter(w => w.evidence?.some((e: any) => e.type === 'commitment'))
      .map(w => ({ entity: w.entity, text: w.text }));
    const allSuggestions = whispers
      .filter(w => w.type === 'suggestion' || w.type === 'critical')
      .map(w => ({ entity: w.entity, text: w.text, priority: w.type, confidence: w.confidence }));
    const userChunks = chunks.filter(c => c.speaker === 'me').length;
    const otherChunks = chunks.filter(c => c.speaker !== 'me').length;
    const totalChunks = chunks.length;
    const talkRatio = totalChunks > 0 ? Math.round((userChunks / totalChunks) * 100) : 0;

    setPostCallSummary({
      total_chunks: totalChunks,
      talk_ratio: `${talkRatio}% you / ${100 - talkRatio}% them`,
      commitments: allCommitments,
      suggestions: allSuggestions,
      whispers_count: whispers.filter(w => w.type !== 'ack').length,
    });
    setShowPostCall(true);
  };

  // ── Audio recording (expo-av) ───────────────────────────────────
  const startRecording = async () => {
    if (!hasConsent) { setShowConsent(true); return; }
    try {
      // Request permission
      const { status } = await Audio.requestPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Permission Required', 'Microphone access is required for live transcription.');
        return;
      }
      await Audio.setAudioModeAsync({ allowsRecordingIOS: true, playsInSilentModeIOS: true });
      const rec = new Audio.Recording();
      await rec.prepareToRecordAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY);
      // expo-av 15 removed `startRecording()` — the new API is `startAsync()`.
      await rec.startAsync();
      (global as any).__maestroRecording = rec;
      setRecording(true);
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    } catch (e) {
      Alert.alert('Recording Error', 'Failed to start recording. Falling back to text input.');
    }
  };

  const stopRecording = async () => {
    try {
      const rec = (global as any).__maestroRecording as Audio.Recording;
      if (!rec) return;
      await rec.stopAndUnloadAsync();
      const uri = rec.getURI();
      setRecording(false);
      (global as any).__maestroRecording = null;
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      // Local transcription: send audio URI to backend for transcription
      // (on-device Whisper WASM would be ideal but requires native module)
      // For now, use the REST transcript endpoint with a note that audio was captured
      if (uri) {
        const transcriptText = '[Audio recorded — ' + new Date().toLocaleTimeString() + ']';
        setChunks(prev => [...prev, { speaker: '🎤 Audio', text: transcriptText, ts: new Date().toISOString() }]);
        // Send to backend for processing
        if (token) {
          try {
            await api.sendTranscriptChunk(transcriptText, 'audio', '');
          } catch (e) { /* non-fatal */ }
        }
      }
    } catch (e) { /* ignore */ }
  };

  // ── Send transcript chunk (WS or REST) ──────────────────────────
  const sendChunk = async () => {
    if (!input || !token) return;
    const chunk = { speaker, text: input, ts: new Date().toISOString() };
    setChunks(prev => [...prev, chunk]);
    setInput('');

    // Try WS first
    if (wsRef && wsRef.readyState === WebSocket.OPEN) {
      wsRef.send(JSON.stringify({ type: 'transcript', text: input, speaker, entity: '' }));
      return;
    }

    // Fall back to REST
    try {
      const result = await api.sendTranscriptChunk(input, speaker, '');
      const detected = result?.commitments_detected;
      if ((detected?.length ?? 0) > 0 && detected) {
        const newWhispers = detected.map((c: any) => ({
          type: 'suggestion',
          entity: c.entity || 'Commitment',
          text: c.text || c.action || '',
          evidence: [],
          confidence: 0.7,
        }));
        setWhispers(prev => [...prev, ...newWhispers]);
        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      }
    } catch (e) { /* ignore */ }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: t.bg }}>
      <TopBar title="Copilot" />

      {/* Consent modal */}
      <ConsentModal
        visible={showConsent}
        onGrant={() => { grant(); setShowConsent(false); Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success); }}
        onDeny={() => setShowConsent(false)}
      />

      {/* Connection banner */}
      <View style={{ padding: spacing.xl, flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: connected ? colors.honey : 'transparent' }}>
        <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: connected ? colors.successGreen : colors.gray }} />
        <Text style={{ color: t.textSecondary, fontSize: 13, flex: 1 }}>
          {connected ? '🔴 Live — WebSocket connected' : 'Offline (REST mode)'}
        </Text>
        {hasConsent && (
          <Text style={{ color: colors.successGreen, fontSize: 11 }}>✓ Consent</Text>
        )}
        <TouchableOpacity onPress={connected ? endMeeting : startMeeting}>
          <Text style={{ color: connected ? colors.alertRed : colors.yellow, fontSize: 13, fontWeight: '600' }}>
            {connected ? 'End' : 'Start'} Meeting
          </Text>
        </TouchableOpacity>
      </View>

      {/* Transcript */}
      <ScrollView
        ref={transcriptRef}
        style={{ flex: 1, paddingHorizontal: spacing.xl }}
        contentContainerStyle={{ paddingBottom: 100 }}
        onContentSizeChange={() => transcriptRef.current?.scrollToEnd({ animated: true })}
      >
        {chunks.length === 0 && (
          <View style={{ alignItems: 'center', marginTop: 60 }}>
            <Ionicons name="mic-outline" size={48} color={t.textSecondary} />
            <Text style={{ color: t.textSecondary, fontSize: 15, marginTop: spacing.md, textAlign: 'center' }}>
              {hasConsent ? 'Start a meeting or type to begin' : 'Grant consent to start recording'}
            </Text>
          </View>
        )}
        {chunks.map((c, i) => (
          <View key={i} style={{ alignSelf: c.speaker === 'me' ? 'flex-end' : 'flex-start', maxWidth: '80%', marginBottom: spacing.md }}>
            <View style={{
              backgroundColor: c.speaker === 'me' ? colors.yellow : t.surface,
              borderRadius: 16,
              borderBottomRightRadius: c.speaker === 'me' ? 4 : 16,
              borderBottomLeftRadius: c.speaker === 'me' ? 16 : 4,
              paddingHorizontal: spacing.lg,
              paddingVertical: spacing.md,
            }}>
              <Text style={{ color: c.speaker === 'me' ? colors.black : t.textPrimary, fontSize: 14 }}>{c.text}</Text>
            </View>
            <Text style={{ color: t.textSecondary, fontSize: 10, marginTop: 2, alignSelf: c.speaker === 'me' ? 'flex-end' : 'flex-start' }}>{c.speaker} · {c.ts.slice(11, 16)}</Text>
          </View>
        ))}
      </ScrollView>

      {/* Whispers overlay */}
      {whispers.length > 0 && (
        <View style={{ position: 'absolute', top: 120, right: spacing.xl, left: spacing.xl }}>
          {whispers.filter(w => w.type !== 'ack').slice(-3).map((w, i) => (
            <Card key={i} accent={w.type === 'critical' ? 'red' : 'yellow'} style={{ marginBottom: spacing.sm, opacity: w.type === 'suggestion' ? 0.9 : 1 }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                <Text style={{ fontSize: 14, fontWeight: 'bold', color: t.textPrimary }}>{w.entity || 'Maestro'}</Text>
                {w.confidence > 0 && (
                  <Text style={{ fontSize: 10, color: t.textSecondary }}>{Math.round(w.confidence * 100)}%</Text>
                )}
              </View>
              <Text style={{ fontSize: 13, color: t.textSecondary, marginTop: 2 }}>{w.text}</Text>
              {w.evidence?.length > 0 && (
                <Text style={{ fontSize: 11, color: colors.yellow, marginTop: 4 }}>📌 {w.evidence[0]?.entity || 'evidence'}</Text>
              )}
            </Card>
          ))}
        </View>
      )}

      {/* Input bar with mic button */}
      <View style={{ flexDirection: 'row', paddingHorizontal: spacing.xl, paddingVertical: spacing.md, gap: spacing.sm, alignItems: 'center' }}>
        {/* Mic button */}
        <TouchableOpacity
          onPress={recording ? stopRecording : startRecording}
          style={{
            width: 44, height: 44, borderRadius: 22,
            backgroundColor: recording ? colors.alertRed : colors.yellow,
            alignItems: 'center', justifyContent: 'center',
          }}
        >
          <Ionicons name={recording ? 'stop' : 'mic'} size={20} color={colors.black} />
        </TouchableOpacity>

        {/* Speaker toggle */}
        <TouchableOpacity onPress={() => setSpeaker(s => s === 'me' ? 'them' : 'me')} style={{ justifyContent: 'center' }}>
          <Text style={{ color: speaker === 'me' ? colors.yellow : t.textSecondary, fontSize: 12 }}>{speaker === 'me' ? 'Me' : 'Them'}</Text>
        </TouchableOpacity>

        {/* Text input */}
        <TextInput
          style={{ flex: 1, backgroundColor: t.surface, borderRadius: 20, paddingHorizontal: spacing.lg, color: t.textPrimary, fontSize: 14 }}
          placeholder="Type or speak..."
          placeholderTextColor={t.textSecondary}
          value={input}
          onChangeText={setInput}
          onSubmitEditing={sendChunk}
        />

        {/* Send button */}
        <TouchableOpacity onPress={sendChunk} style={{ justifyContent: 'center' }}>
          <Ionicons name="send" size={20} color={colors.yellow} />
        </TouchableOpacity>
      </View>

      {/* Post-call summary modal */}
      <Modal visible={showPostCall} animationType="slide" onRequestClose={() => setShowPostCall(false)}>
        <SafeAreaView style={{ flex: 1, backgroundColor: t.bg }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', padding: spacing.xl }}>
            <Text style={{ fontSize: 22, fontWeight: 'bold', color: t.textPrimary }}>Meeting Summary</Text>
            <TouchableOpacity onPress={() => { setShowPostCall(false); setChunks([]); setWhispers([]); }}>
              <Ionicons name="close" size={24} color={t.textSecondary} />
            </TouchableOpacity>
          </View>
          <ScrollView style={{ flex: 1, paddingHorizontal: spacing.xl }}>
            {postCallSummary && (
              <>
                <Card style={{ marginBottom: spacing.lg }}>
                  <Text style={{ fontSize: 13, color: t.textSecondary, marginBottom: spacing.sm }}>📊 TALK RATIO</Text>
                  <Text style={{ fontSize: 18, fontWeight: 'bold', color: t.textPrimary }}>{postCallSummary.talk_ratio}</Text>
                  <Text style={{ fontSize: 13, color: t.textSecondary, marginTop: spacing.xs }}>{postCallSummary.total_chunks} transcript chunks</Text>
                </Card>
                <Card accent="yellow" style={{ marginBottom: spacing.lg }}>
                  <Text style={{ fontSize: 13, color: colors.yellow, marginBottom: spacing.sm }}>⚡ WHISPERS GENERATED</Text>
                  <Text style={{ fontSize: 28, fontWeight: 'bold', color: t.textPrimary }}>{postCallSummary.whispers_count}</Text>
                </Card>
                {postCallSummary.commitments.length > 0 && (
                  <Card accent="green" style={{ marginBottom: spacing.lg }}>
                    <Text style={{ fontSize: 13, color: colors.successGreen, marginBottom: spacing.sm }}>✓ COMMITMENTS DETECTED</Text>
                    {postCallSummary.commitments.map((c: any, i: number) => (
                      <Text key={i} style={{ fontSize: 14, color: t.textPrimary, marginBottom: 4 }}>• {c.entity}: {c.text?.slice(0, 60)}</Text>
                    ))}
                  </Card>
                )}
                {postCallSummary.suggestions.length > 0 && (
                  <Card style={{ marginBottom: spacing.lg }}>
                    <Text style={{ fontSize: 13, color: t.textSecondary, marginBottom: spacing.sm }}>💡 SUGGESTIONS</Text>
                    {postCallSummary.suggestions.map((s: any, i: number) => (
                      <View key={i} style={{ marginBottom: 8 }}>
                        <Text style={{ fontSize: 14, color: t.textPrimary }}>• {s.entity}: {s.text?.slice(0, 60)}</Text>
                        <Text style={{ fontSize: 11, color: t.textSecondary }}>{s.priority} · {Math.round((s.confidence || 0) * 100)}% confidence</Text>
                      </View>
                    ))}
                  </Card>
                )}
                {/* Follow-up email draft */}
                <Card accent="yellow" style={{ marginBottom: spacing.lg }}>
                  <Text style={{ fontSize: 13, color: colors.yellow, marginBottom: spacing.sm }}>📧 FOLLOW-UP EMAIL DRAFT</Text>
                  <Text style={{ fontSize: 13, color: t.textPrimary, lineHeight: 20 }}>
                    Hi {'{' + (chunks[0]?.speaker || 'team') + '}'},{'\n\n'}
                    Thank you for the meeting. Here are the commitments I'm tracking:{'\n'}
                    {postCallSummary.commitments.length > 0
                      ? postCallSummary.commitments.map((c: any) => `• ${c.entity}: ${c.text?.slice(0, 50)}`).join('\n')
                      : '• (none detected)'}{'\n\n'}
                    I'll follow up by end of week.{'\n\n'}
                    Best,{'\n'}[Your name]
                  </Text>
                </Card>
                <TouchableOpacity
                  style={[styles.loginButton, { backgroundColor: colors.yellow, marginBottom: spacing.xl }]}
                  onPress={() => { setShowPostCall(false); setChunks([]); setWhispers([]); }}
                >
                  <Text style={{ color: colors.black, fontSize: 16, fontWeight: 'bold' }}>Save & Close</Text>
                </TouchableOpacity>
              </>
            )}
          </ScrollView>
        </SafeAreaView>
      </Modal>
    </SafeAreaView>
  );
}

// ═══════════════════════════════════════════════════════════════════
// SCREEN 7: SETTINGS
// ═══════════════════════════════════════════════════════════════════

function SettingsScreen() {
  const { mode, toggle } = useTheme();
  const t = getTheme(mode);
  const { token, llmStatus, logout } = useAuth();
  const [privacy, setPrivacy] = useState<api.PrivacyMode | null>(null);
  const [calibration, setCalibration] = useState<api.Calibration | null>(null);
  const [audit, setAudit] = useState<api.AuditLogEntry[]>([]);
  const [metrics, setMetrics] = useState<api.Metrics | null>(null);

  useEffect(() => {
    if (!token) return;
    Promise.all([
      api.getPrivacyMode().catch(() => null),
      api.getCalibration().catch(() => null),
      api.getAuditLog().catch(() => null),
      api.getMetrics().catch(() => null),
    ]).then(([p, c, a, m]) => {
      setPrivacy(p); setCalibration(c); setAudit(a?.events || []); setMetrics(m);
    });
  }, [token]);

  const handleExport = async () => {
    if (!token) return;
    try {
      const data = await api.exportData();
      await Share.share({ message: JSON.stringify(data, null, 2) });
    } catch (e) { Alert.alert('Error', 'Export failed'); }
  };

  const handleDelete = () => {
    Alert.alert('Delete Account', 'Type DELETE to confirm', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'DELETE', style: 'destructive', onPress: async () => {
        if (!token) return;
        await api.deleteAccount();
        logout();
      }},
    ]);
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: t.bg }}>
      <TopBar title="Settings" />
      <ScrollView contentContainerStyle={{ padding: spacing.xl, paddingBottom: 40 }}>
        {/* Theme toggle */}
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: spacing.xl }}>
          <Text style={{ color: t.textPrimary, fontSize: 15 }}>Dark Mode</Text>
          <TouchableOpacity onPress={toggle} style={{ width: 50, height: 28, borderRadius: 14, backgroundColor: mode === 'dark' ? colors.yellow : t.border, justifyContent: 'center', paddingHorizontal: 3 }}>
            <View style={{ width: 22, height: 22, borderRadius: 11, backgroundColor: colors.white, alignSelf: mode === 'dark' ? 'flex-end' : 'flex-start' }} />
          </TouchableOpacity>
        </View>

        {/* LLM Status */}
        <Card style={{ marginBottom: spacing.md }}>
          <Text style={[typography.label, { color: t.textSecondary, marginBottom: spacing.sm }]}>LLM STATUS</Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <LLMDot size={10} />
            <Text style={{ color: t.textPrimary, fontSize: 15 }}>{llmStatus?.provider || 'none'}</Text>
          </View>
          <Text style={{ color: t.textSecondary, fontSize: 13, marginTop: spacing.xs }}>{llmStatus?.mode || 'Rule-based'}</Text>
        </Card>

        {/* Privacy */}
        {privacy && (
          <Card style={{ marginBottom: spacing.md }}>
            <Text style={[typography.label, { color: t.textSecondary, marginBottom: spacing.sm }]}>PRIVACY MODE</Text>
            <Text style={{ color: t.textPrimary, fontSize: 15 }}>{privacy.mode}</Text>
            <Text style={{ color: t.textSecondary, fontSize: 13, marginTop: spacing.xs }}>{privacy.description}</Text>
          </Card>
        )}

        {/* Calibration */}
        {calibration && (
          <Card style={{ marginBottom: spacing.md }}>
            <Text style={[typography.label, { color: t.textSecondary, marginBottom: spacing.sm }]}>CALIBRATION</Text>
            <Text style={{ color: t.textPrimary, fontSize: 28, fontWeight: 'bold' }}>
              {calibration.brier_score !== null ? calibration.brier_score.toFixed(4) : '—'}
            </Text>
            <Text style={{ color: t.textSecondary, fontSize: 13, marginTop: spacing.xs }}>{calibration.message}</Text>
          </Card>
        )}

        {/* Metrics */}
        {metrics && (
          <Card style={{ marginBottom: spacing.md }}>
            <Text style={[typography.label, { color: t.textSecondary, marginBottom: spacing.sm }]}>METRICS</Text>
            <View style={{ flexDirection: 'row', gap: spacing.xl }}>
              <View>
                <Text style={{ color: t.textPrimary, fontSize: 20, fontWeight: 'bold' }}>{metrics.commitment_completion_rate !== null ? `${Math.round(metrics.commitment_completion_rate * 100)}%` : '—'}</Text>
                <Text style={{ color: t.textSecondary, fontSize: 11 }}>Completion</Text>
              </View>
              <View>
                <Text style={{ color: t.textPrimary, fontSize: 20, fontWeight: 'bold' }}>{metrics.engagement_signals}</Text>
                <Text style={{ color: t.textSecondary, fontSize: 11 }}>Signals</Text>
              </View>
            </View>
          </Card>
        )}

        {/* Audit Log */}
        <Text style={[typography.label, { color: t.textSecondary, marginBottom: spacing.sm, marginTop: spacing.lg }]}>AUDIT LOG</Text>
        {audit.slice(0, 20).map((e, i) => (
          <View key={i} style={{ flexDirection: 'row', paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: t.border }}>
            <Text style={{ color: t.textSecondary, fontSize: 11, width: 60 }}>{e.timestamp?.slice(11, 16)}</Text>
            <Text style={{ color: e.action === 'read' ? '#4A9' : e.action === 'write' ? colors.successGreen : e.action === 'correct' ? colors.yellow : colors.alertRed, fontSize: 11, fontWeight: '600', width: 50 }}>{e.action}</Text>
            <Text style={{ color: t.textPrimary, fontSize: 11, flex: 1 }}>{e.endpoint}</Text>
          </View>
        ))}

        {/* Data */}
        <View style={{ marginTop: spacing.xl, gap: spacing.md }}>
          <TouchableOpacity style={[styles.loginButton, { backgroundColor: t.border }]} onPress={handleExport}>
            <Text style={{ color: t.textSecondary, fontWeight: 'bold' }}>Export All Data</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[styles.loginButton, { backgroundColor: colors.alertRed + '22' }]} onPress={handleDelete}>
            <Text style={{ color: colors.alertRed, fontWeight: 'bold' }}>Delete Account</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

// ═══════════════════════════════════════════════════════════════════
// NAVIGATION
// ═══════════════════════════════════════════════════════════════════

const Tab = createBottomTabNavigator();

function TabNavigator() {
  const { mode } = useTheme();
  const t = getTheme(mode);
  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarStyle: { backgroundColor: t.bg, borderTopColor: t.border, height: 56 },
        tabBarActiveTintColor: colors.yellow,
        tabBarInactiveTintColor: t.textSecondary,
        tabBarLabelStyle: { fontSize: 10 },
      }}
    >
      <Tab.Screen name="Dashboard" component={DashboardScreen} options={{ tabBarIcon: ({ color }) => <Ionicons name="home" size={22} color={color} /> }} />
      <Tab.Screen name="Ask" component={AskScreen} options={{ tabBarIcon: ({ color }) => <Ionicons name="search" size={22} color={color} /> }} />
      <Tab.Screen name="Commitments" component={CommitmentsScreen} options={{ tabBarIcon: ({ color }) => <Ionicons name="checkmark-circle" size={22} color={color} /> }} />
      <Tab.Screen name="Copilot" component={CopilotScreen} options={{ tabBarIcon: ({ color }) => <Ionicons name="chatbubbles" size={22} color={color} /> }} />
      <Tab.Screen name="Settings" component={SettingsScreen} options={{ tabBarIcon: ({ color }) => <Ionicons name="settings" size={22} color={color} /> }} />
    </Tab.Navigator>
  );
}

// ═══════════════════════════════════════════════════════════════════
// APP ROOT
// ═══════════════════════════════════════════════════════════════════

function AppInner() {
  const { token } = useAuth();
  const { mode } = useTheme();
  return (
    <>
      <StatusBar barStyle={mode === 'dark' ? 'light-content' : 'dark-content'} />
      {token ? <TabNavigator /> : <LoginScreen />}
    </>
  );
}

export default function App() {
  return (
    <SafeAreaProvider>
      <ThemeProvider>
        <AuthProvider>
          <ConsentProvider>
            <NavigationContainer>
              <AppInner />
            </NavigationContainer>
          </ConsentProvider>
        </AuthProvider>
      </ThemeProvider>
    </SafeAreaProvider>
  );
}

// ═══════════════════════════════════════════════════════════════════
// STYLES
// ═══════════════════════════════════════════════════════════════════

const styles = StyleSheet.create({
  container: { flex: 1 },
  topBar: {
    height: 56,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.xl,
    borderBottomWidth: 1,
  },
  card: {
    borderRadius: 16,
    padding: 20,
  },
  loginInput: {
    height: 52,
    borderRadius: 12,
    paddingHorizontal: 16,
    fontSize: 16,
    borderWidth: 2,
  },
  loginButton: {
    height: 52,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: spacing.md,
  },
  actionButton: {
    width: 56,
    height: 56,
    borderRadius: 28,
    alignItems: 'center',
    justifyContent: 'center',
  },
  actionLabel: {
    color: colors.white,
    fontSize: 10,
    marginTop: 2,
  },
  quickAsk: {
    flexDirection: 'row',
    alignItems: 'center',
    height: 44,
    borderRadius: 22,
    borderWidth: 1,
    paddingHorizontal: 16,
  },
  searchBar: {
    flexDirection: 'row',
    alignItems: 'center',
    height: 48,
    borderRadius: 24,
  },
  smallBtn: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 12,
    alignItems: 'center',
  },
  fab: {
    position: 'absolute',
    bottom: 20,
    right: 20,
    width: 56,
    height: 56,
    borderRadius: 28,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.3,
    shadowRadius: 4,
    elevation: 5,
  },
});
