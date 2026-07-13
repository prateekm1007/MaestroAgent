/**
 * AskScreen — extracted from the original App.tsx, unchanged in logic.
 *
 * Free-text question against the Maestro knowledge graph. Renders the
 * answer, provenance sentence, confidence bar, counterevidence, and
 * unknowns. Recent queries are persisted in AsyncStorage.
 */

import React, { useState, useEffect } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, ScrollView, ActivityIndicator, Alert, SafeAreaView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';

import * as api from '../api/client';
import { colors, getTheme, spacing, typography } from '../theme/colors';
import { useAuth, useTheme } from '../contexts';
import { Card, ConfidenceBar, TopBar } from '../components';
import { styles } from '../styles';

export default function AskScreen() {
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
