/**
 * AskScreen — extracted from the original App.tsx.
 *
 * Phase 2: the ask() call is now wrapped in the `useAsk` react-query
 * mutation hook instead of a manual try/catch + loading state. The
 * recent-queries history stays in AsyncStorage (local UI state, not
 * server data). Loading/error states use the shared components from
 * src/components/ErrorState.tsx.
 *
 * UI/logic is otherwise unchanged.
 */

import React, { useState, useEffect } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, ScrollView, Alert, SafeAreaView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';

import { useAsk } from '../api/hooks';
import { colors, getTheme, spacing, typography } from '../theme/colors';
import { useAuth, useTheme } from '../contexts';
import { Card, ConfidenceBar, TopBar } from '../components';
import { ErrorState, LoadingState } from '../components/ErrorState';
import { styles } from '../styles';

export default function AskScreen() {
  const { mode } = useTheme();
  const t = getTheme(mode);
  const { token } = useAuth();
  const [query, setQuery] = useState('');
  const [history, setHistory] = useState<string[]>([]);

  // ── react-query mutation (replaces manual try/catch + loading) ─────
  const askMutation = useAsk();
  const result = askMutation.data ?? null;
  const loading = askMutation.isPending;

  // Recent-queries history stays in AsyncStorage (local UI state).
  useEffect(() => {
    AsyncStorage.getItem('maestro_ask_history').then(h => {
      if (h) setHistory(JSON.parse(h).slice(0, 10));
    });
  }, []);

  const handleAsk = (q?: string) => {
    const queryText = q || query;
    if (!queryText || !token) return;
    askMutation.mutate(queryText, {
      onSuccess: () => {
        const newHistory = [queryText, ...history.filter(h => h !== queryText)].slice(0, 10);
        setHistory(newHistory);
        AsyncStorage.setItem('maestro_ask_history', JSON.stringify(newHistory));
      },
      onError: () => {
        Alert.alert('Error', 'Failed to get answer. Is the API running?');
      },
    });
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: t.bg }}>
      <TopBar title="Ask" />
      <View style={{ padding: spacing.xl }}>
        {/* Search bar */}
        <View style={[styles.searchBar, { backgroundColor: t.surface }]} accessibilityRole="search" accessibilityLabel="Ask search bar">
          <Ionicons name="search" size={20} color={t.textSecondary} style={{ marginLeft: spacing.md }} />
          <TextInput
            style={{ flex: 1, color: t.textPrimary, fontSize: 15, paddingHorizontal: spacing.md }}
            placeholder="Ask anything about your commitments..."
            placeholderTextColor={t.textSecondary}
            value={query}
            onChangeText={setQuery}
            onSubmitEditing={() => handleAsk()}
            returnKeyType="search"
            accessibilityLabel="Ask Maestro a question"
            accessibilityHint="Type your question and submit to get an answer"
          />
          <TouchableOpacity
            onPress={() => handleAsk()}
            style={{ paddingRight: spacing.md }}
            accessibilityRole="button"
            accessibilityLabel="Submit question"
            accessibilityHint={loading ? 'Loading answer' : 'Get the answer to your question'}
          >
            {loading ? (
              <Text style={{ color: colors.yellow, fontSize: 13 }}>…</Text>
            ) : (
              <Ionicons name="arrow-forward" size={20} color={colors.yellow} />
            )}
          </TouchableOpacity>
        </View>

        {/* Recent */}
        {history.length > 0 && !result && !loading && (
          <>
            <Text
              style={[typography.label, { color: t.textSecondary, marginTop: spacing.xl, marginBottom: spacing.sm }]}
              accessibilityRole="header"
              accessibilityLabel="Recent questions"
            >RECENT</Text>
            {history.map((h, i) => (
              <TouchableOpacity
                key={i}
                onPress={() => { setQuery(h); handleAsk(h); }}
                style={{ paddingVertical: spacing.md }}
                accessibilityRole="button"
                accessibilityLabel={`Recent question: ${h}`}
                accessibilityHint="Repeats this question"
              >
                <Text style={{ color: t.textPrimary, fontSize: 14 }}>{h}</Text>
              </TouchableOpacity>
            ))}
          </>
        )}
      </View>

      {/* Loading */}
      {loading && (
        <LoadingState label="Maestro is thinking…" />
      )}

      {/* Error */}
      {!loading && askMutation.isError && (
        <ErrorState
          message="Couldn't get an answer. Tap to try again."
          onRetry={() => query && handleAsk(query)}
        />
      )}

      {/* Result */}
      {result && !loading && (
        <ScrollView
          style={{ flex: 1, paddingHorizontal: spacing.xl }}
          contentContainerStyle={{ paddingBottom: spacing.xxxl }}
          accessibilityLiveRegion="polite"
        >
          <Card style={{ marginTop: spacing.md }}>
            <Text
              style={{ color: t.textSecondary, fontSize: 11, fontWeight: '600', letterSpacing: 1, marginBottom: spacing.sm }}
              accessibilityRole="header"
              accessibilityLabel="Answer section"
            >ANSWER</Text>
            <Text
              style={{ fontSize: 16, color: t.textPrimary, lineHeight: 24 }}
              accessibilityRole="text"
              accessibilityLabel={`Answer: ${result.answer}`}
            >{result.answer}</Text>

            {/* Provenance */}
            {result.source_sentence ? (
              <View style={{ marginTop: spacing.xl, borderTopWidth: 1, borderTopColor: t.border, paddingTop: spacing.md }}>
                <Text
                  style={[typography.label, { color: t.textSecondary, marginBottom: spacing.sm }]}
                  accessibilityRole="header"
                  accessibilityLabel="Provenance section"
                >PROVENANCE</Text>
                <Text
                  style={{ fontSize: 14, color: t.textPrimary, fontStyle: 'italic' }}
                  accessibilityRole="text"
                  accessibilityLabel={`Source: ${result.source_sentence}`}
                >"{result.source_sentence}"</Text>
                <Text
                  style={{ fontSize: 13, color: t.textSecondary, marginTop: spacing.xs }}
                  accessibilityRole="text"
                  accessibilityLabel={`Source entity ${result.source_entity}, timestamp ${result.source_timestamp?.slice(0, 16)}`}
                >
                  📌 {result.source_entity} · 🕐 {result.source_timestamp?.slice(0, 16)}
                </Text>
              </View>
            ) : null}

            {/* Confidence */}
            <ConfidenceBar value={result.confidence ?? 0} label={result.intelligence_source === 'llm' ? 'LLM-powered' : 'rules-based'} />

            {/* Counterevidence */}
            {(result.counterevidence?.length ?? 0) > 0 && (
              <View style={{ marginTop: spacing.xl }}>
                <Text
                  style={[typography.label, { color: colors.alertRed, marginBottom: spacing.sm }]}
                  accessibilityRole="header"
                  accessibilityLabel="Counterevidence section"
                >COUNTEREVIDENCE</Text>
                {result.counterevidence?.map((c, i) => (
                  <Card key={i} accent="red" style={{ marginBottom: spacing.sm }}>
                    <Text
                      style={{ fontSize: 14, color: t.textPrimary }}
                      accessibilityRole="text"
                      accessibilityLabel={`Counterevidence: ${typeof c === 'string' ? c : c.claim || JSON.stringify(c)}`}
                    >⚠ {typeof c === 'string' ? c : c.claim || JSON.stringify(c)}</Text>
                  </Card>
                ))}
              </View>
            )}

            {/* Unknowns */}
            {(result.unknowns?.length ?? 0) > 0 && (
              <View style={{ marginTop: spacing.xl }}>
                <Text
                  style={[typography.label, { color: t.textSecondary, marginBottom: spacing.sm }]}
                  accessibilityRole="header"
                  accessibilityLabel="Unknowns section"
                >UNKNOWNS</Text>
                {result.unknowns?.map((u, i) => (
                  <Text
                    key={i}
                    style={{ fontSize: 14, color: t.textSecondary, marginBottom: spacing.xs }}
                    accessibilityRole="text"
                    accessibilityLabel={`Unknown: ${typeof u === 'string' ? u : u.description || JSON.stringify(u)}`}
                  >
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
