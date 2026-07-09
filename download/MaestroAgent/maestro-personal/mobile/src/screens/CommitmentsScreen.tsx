/**
 * CommitmentsScreen — ONE at risk, rest secondary.
 *
 * Bumble-inspired: warm, honey accent for at-risk, clean list for rest.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, FlatList, RefreshControl, StyleSheet, TouchableOpacity } from 'react-native';
import { useAuth } from '../api/auth';
import { getCommitments, Commitment } from '../api/client';
import { theme } from '../theme';

export default function CommitmentsScreen({ navigation }: { navigation: any }) {
  const { token } = useAuth();
  const [commitments, setCommitments] = useState<Commitment[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setRefreshing(true);
    setError(null);
    try {
      const data = await getCommitments(token);
      // Sort: at-risk first, then by entity
      data.sort((a, b) => {
        if (a.is_at_risk !== b.is_at_risk) return a.is_at_risk ? -1 : 1;
        return a.entity.localeCompare(b.entity);
      });
      setCommitments(data);
    } catch (e) {
      setError(String(e));
    } finally {
      setRefreshing(false);
    }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Commitments</Text>
      <FlatList
        data={commitments}
        keyExtractor={(item) => item.signal_id}
        renderItem={({ item, index }) => (
          <TouchableOpacity
            style={[styles.card, item.is_at_risk && styles.cardAtRisk]}
            onPress={() => navigation.navigate('Ask', { query: `What's the situation with ${item.entity}?` })}
          >
            {item.is_at_risk && (
              <View style={styles.riskBadge}>
                <Text style={styles.riskBadgeText}>AT RISK · {item.days_stale}d stale</Text>
              </View>
            )}
            <Text style={styles.entity}>{item.entity}</Text>
            <Text style={styles.text}>{item.text}</Text>
            <View style={styles.metaRow}>
              <Text style={styles.claimType}>{item.claim_type}</Text>
              {item.deadline ? (
                <Text style={styles.deadline}>→ {item.deadline}</Text>
              ) : null}
            </View>
          </TouchableOpacity>
        )}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={load} tintColor={theme.honey} />}
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Text style={styles.emptyTitle}>No active commitments.</Text>
            <Text style={styles.emptyBody}>Add a signal with "I will..." to create one.</Text>
            <TouchableOpacity style={styles.emptyBtn} onPress={() => navigation.navigate('AddSignal')}>
              <Text style={styles.emptyBtnText}>Add a signal</Text>
            </TouchableOpacity>
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
  card: {
    backgroundColor: theme.cardBg,
    borderRadius: theme.radius.lg,
    padding: 20,
    marginBottom: 10,
    ...theme.shadow.card,
  },
  cardAtRisk: {
    borderWidth: 2,
    borderColor: theme.honey,
  },
  riskBadge: {
    backgroundColor: theme.honey,
    borderRadius: theme.radius.pill,
    paddingHorizontal: 10,
    paddingVertical: 3,
    alignSelf: 'flex-start',
    marginBottom: 10,
  },
  riskBadgeText: { fontSize: 10, fontWeight: '700', color: theme.textOnHoney, letterSpacing: 1 },
  entity: { fontSize: 16, fontWeight: '700', color: theme.textPrimary, marginBottom: 4 },
  text: { fontSize: 15, color: theme.textPrimary, lineHeight: 22, marginBottom: 10 },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  claimType: {
    fontSize: 11,
    fontWeight: '600',
    color: theme.textSecondary,
    backgroundColor: theme.bgSecondary,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: theme.radius.sm,
    overflow: 'hidden',
    textTransform: 'capitalize',
  },
  deadline: { fontSize: 12, fontWeight: '600', color: theme.warning },
  emptyContainer: { alignItems: 'center', padding: 40, marginTop: 60 },
  emptyTitle: { fontSize: 18, fontWeight: '700', color: theme.textPrimary, marginBottom: 8 },
  emptyBody: { fontSize: 15, color: theme.textSecondary, textAlign: 'center', marginBottom: 24 },
  emptyBtn: { backgroundColor: theme.honey, borderRadius: theme.radius.pill, paddingHorizontal: 24, paddingVertical: 12 },
  emptyBtnText: { color: theme.textOnHoney, fontWeight: '700', fontSize: 15 },
  error: { color: theme.error, padding: 16 },
});
