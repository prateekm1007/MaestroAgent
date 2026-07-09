/**
 * PrepareScreen — 3 things that matter for THIS meeting.
 *
 * Bumble-inspired: warm cream, 3 cards (forgotten, open question,
 * contradiction), honey accent headers.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, FlatList, RefreshControl, StyleSheet, TouchableOpacity } from 'react-native';
import { useAuth } from '../api/auth';
import { getPrepare, PrepareItem } from '../api/client';
import { theme } from '../theme';

export default function PrepareScreen() {
  const { token } = useAuth();
  const [preps, setPreps] = useState<PrepareItem[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadPreps = useCallback(async () => {
    if (!token) return;
    setRefreshing(true);
    setError(null);
    try {
      const data = await getPrepare(token);
      setPreps(data);
    } catch (e) {
      setError(String(e));
    } finally {
      setRefreshing(false);
    }
  }, [token]);

  useEffect(() => { loadPreps(); }, [loadPreps]);

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Prepare</Text>
      <FlatList
        data={preps}
        keyExtractor={(item) => item.situation_id}
        renderItem={({ item }) => (
          <View style={styles.prepCard}>
            {item.entity ? (
              <Text style={styles.entity}>Meeting with {item.entity}</Text>
            ) : null}
            {item.meeting_context ? (
              <Text style={styles.context}>{item.meeting_context}</Text>
            ) : null}

            {item.the_forgotten ? (
              <View style={styles.thingCard}>
                <Text style={styles.thingLabel}>THE FORGOTTEN</Text>
                <Text style={styles.thingText}>{item.the_forgotten}</Text>
              </View>
            ) : null}

            {item.the_open_question ? (
              <View style={[styles.thingCard, styles.thingCardPurple]}>
                <Text style={[styles.thingLabel, styles.thingLabelPurple]}>THE OPEN QUESTION</Text>
                <Text style={[styles.thingText, styles.thingTextPurple]}>{item.the_open_question}</Text>
              </View>
            ) : null}

            {item.the_contradiction ? (
              <View style={[styles.thingCard, styles.thingCardWarning]}>
                <Text style={[styles.thingLabel, styles.thingLabelWarning]}>THE CONTRADICTION</Text>
                <Text style={[styles.thingText, styles.thingTextWarning]}>{item.the_contradiction}</Text>
              </View>
            ) : null}

            {item.is_stale ? (
              <Text style={styles.staleWarning}>⚠ Preparation is stale — reality changed</Text>
            ) : null}
          </View>
        )}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={loadPreps} tintColor={theme.honey} />}
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Text style={styles.emptyTitle}>No situations need preparation right now.</Text>
            <Text style={styles.emptyBody}>When a meeting approaches, Maestro will surface the 3 things that matter.</Text>
          </View>
        }
      />
      {error && <Text style={styles.error}>{error}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 20, backgroundColor: theme.bg },
  title: { ...theme.font.title, marginBottom: 20 },
  prepCard: {
    backgroundColor: theme.cardBg,
    borderRadius: theme.radius.xl,
    padding: 24,
    marginBottom: 12,
    ...theme.shadow.card,
  },
  entity: { fontSize: 18, fontWeight: '700', color: theme.textPrimary, marginBottom: 4 },
  context: { fontSize: 13, color: theme.textSecondary, marginBottom: 20, textTransform: 'capitalize' },
  thingCard: {
    backgroundColor: theme.honey,
    borderRadius: theme.radius.lg,
    padding: 16,
    marginBottom: 10,
  },
  thingCardPurple: { backgroundColor: theme.purpleLight },
  thingCardWarning: { backgroundColor: '#FFF4E6' },
  thingLabel: { fontSize: 10, fontWeight: '700', color: theme.textOnHoney, letterSpacing: 1.5, marginBottom: 8 },
  thingLabelPurple: { color: theme.purple },
  thingLabelWarning: { color: theme.warning },
  thingText: { fontSize: 16, fontWeight: '600', color: theme.textOnHoney, lineHeight: 22 },
  thingTextPurple: { color: theme.purple },
  thingTextWarning: { color: '#8B5A00' },
  staleWarning: { fontSize: 13, color: theme.warning, marginTop: 12, fontWeight: '600' },
  emptyContainer: { alignItems: 'center', padding: 40, marginTop: 60 },
  emptyTitle: { fontSize: 18, fontWeight: '700', color: theme.textPrimary, textAlign: 'center', marginBottom: 12 },
  emptyBody: { fontSize: 15, color: theme.textSecondary, textAlign: 'center', lineHeight: 22 },
  error: { color: theme.error, padding: 16 },
});
