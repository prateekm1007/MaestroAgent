/**
 * AskScreen — the truth, sourced.
 *
 * Bumble-inspired: warm cream, honey accent, clean card.
 * Ask returns the exact sentence + source + situation state.
 */

import React, { useState } from 'react';
import { View, Text, TextInput, Button, StyleSheet, ScrollView, ActivityIndicator, TouchableOpacity } from 'react-native';
import { useAuth } from '../api/auth';
import { ask, AskResult } from '../api/client';
import { theme } from '../theme';

export default function AskScreen() {
  const { token } = useAuth();
  const [query, setQuery] = useState('');
  const [result, setResult] = useState<AskResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAsk = async () => {
    if (!query.trim() || !token) return;
    setLoading(true);
    setError(null);
    try {
      const r = await ask(token, query);
      setResult(r);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Ask</Text>
      <View style={styles.inputContainer}>
        <TextInput
          style={styles.input}
          placeholder="What did I promise Alex?"
          value={query}
          onChangeText={setQuery}
          multiline
          placeholderTextColor={theme.textSecondary}
        />
        <TouchableOpacity
          style={[styles.askBtn, (!query.trim() || loading) && styles.askBtnDisabled]}
          onPress={handleAsk}
          disabled={loading || !query.trim()}
        >
          <Text style={styles.askBtnText}>{loading ? '...' : 'Ask'}</Text>
        </TouchableOpacity>
      </View>

      {loading && <ActivityIndicator style={{ marginTop: 24 }} color={theme.honey} size="large" />}
      {error && <Text style={styles.error}>{error}</Text>}

      {result && !loading && (
        <ScrollView style={styles.resultContainer} showsVerticalScrollIndicator={false}>
          <View style={styles.answerCard}>
            <Text style={styles.kicker}>ANSWER</Text>
            <Text style={styles.answerText}>{result.answer}</Text>
          </View>

          {result.source_sentence ? (
            <View style={styles.sourceCard}>
              <Text style={styles.kicker}>SOURCE — THE EXACT SENTENCE</Text>
              <Text style={styles.sourceText}>"{result.source_sentence}"</Text>
              <View style={styles.sourceMeta}>
                {result.source_entity ? (
                  <Text style={styles.sourceMetaItem}>→ {result.source_entity}</Text>
                ) : null}
                {result.situation_state ? (
                  <View style={styles.statePill}>
                    <Text style={styles.stateText}>{result.situation_state}</Text>
                  </View>
                ) : null}
              </View>
            </View>
          ) : null}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 20, backgroundColor: theme.bg },
  title: { ...theme.font.title, marginBottom: 20 },
  inputContainer: { flexDirection: 'row', gap: 8, marginBottom: 20 },
  input: {
    flex: 1,
    backgroundColor: theme.cardBg,
    borderRadius: theme.radius.lg,
    padding: 16,
    fontSize: 16,
    color: theme.textPrimary,
    minHeight: 56,
    ...theme.shadow.card,
  },
  askBtn: {
    backgroundColor: theme.honey,
    borderRadius: theme.radius.lg,
    paddingHorizontal: 24,
    justifyContent: 'center',
  },
  askBtnDisabled: { opacity: 0.5 },
  askBtnText: { color: theme.textOnHoney, fontSize: 16, fontWeight: '700' },
  resultContainer: { flex: 1 },
  answerCard: {
    backgroundColor: theme.cardBg,
    borderRadius: theme.radius.xl,
    padding: 24,
    marginBottom: 12,
    ...theme.shadow.card,
  },
  kicker: { ...theme.font.kicker, marginBottom: 12 },
  answerText: { fontSize: 17, color: theme.textPrimary, lineHeight: 26 },
  sourceCard: {
    backgroundColor: theme.purpleLight,
    borderRadius: theme.radius.xl,
    padding: 24,
    marginBottom: 12,
  },
  sourceText: {
    fontSize: 18,
    fontWeight: '700',
    color: theme.purple,
    lineHeight: 26,
    marginBottom: 16,
  },
  sourceMeta: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  sourceMetaItem: { fontSize: 14, fontWeight: '600', color: theme.textSecondary },
  statePill: {
    backgroundColor: theme.honey,
    borderRadius: theme.radius.pill,
    paddingHorizontal: 12,
    paddingVertical: 4,
    marginLeft: 'auto',
  },
  stateText: { fontSize: 12, fontWeight: '700', color: theme.textOnHoney, textTransform: 'capitalize' },
  error: { color: theme.error, marginTop: 16, fontSize: 14 },
});
