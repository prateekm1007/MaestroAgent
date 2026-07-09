/**
 * Ask screen — ask a question, get a Situation-centric answer.
 *
 * Calls POST /api/ask. The answer comes from the Core's
 * SituationAwareAskBridge via the shell.
 */

import React, { useState } from 'react';
import { View, Text, TextInput, Button, StyleSheet, ScrollView, ActivityIndicator } from 'react-native';
import { useAuth } from '../api/auth';
import { ask, AskResult } from '../api/client';

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
      <TextInput
        style={styles.input}
        placeholder="What did I promise Alex?"
        value={query}
        onChangeText={setQuery}
        multiline
      />
      <Button title={loading ? 'Asking...' : 'Ask'} onPress={handleAsk} disabled={loading || !query.trim()} />
      {loading && <ActivityIndicator style={{ marginTop: 16 }} />}
      {error && <Text style={styles.error}>{error}</Text>}
      {result && (
        <ScrollView style={styles.resultContainer}>
          <Text style={styles.resultText}>{result.answer}</Text>
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 16, backgroundColor: '#f5f4f3' },
  title: { fontSize: 24, fontWeight: 'bold', marginBottom: 16, color: '#1b1a18' },
  input: { borderWidth: 1, borderColor: '#bfbaac', borderRadius: 8, padding: 12, marginBottom: 16, fontSize: 16, backgroundColor: '#fff', minHeight: 60 },
  resultContainer: { marginTop: 16, backgroundColor: '#fff', padding: 16, borderRadius: 8, borderWidth: 1, borderColor: '#bfbaac' },
  resultText: { fontSize: 16, color: '#1b1a18', lineHeight: 24 },
  error: { color: '#9e5852', marginTop: 16 },
});
