/**
 * Commitments screen — shows active commitments.
 *
 * Calls GET /api/commitments. Uses Core's classify_transcript_chunk
 * + should_treat_as_commitment via the shell.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, FlatList, RefreshControl, StyleSheet } from 'react-native';
import { useAuth } from '../api/auth';
import { getCommitments, Commitment } from '../api/client';

export default function CommitmentsScreen() {
  const { token } = useAuth();
  const [commitments, setCommitments] = useState<Commitment[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadCommitments = useCallback(async () => {
    if (!token) return;
    setRefreshing(true);
    setError(null);
    try {
      const data = await getCommitments(token);
      setCommitments(data);
    } catch (e) {
      setError(String(e));
    } finally {
      setRefreshing(false);
    }
  }, [token]);

  useEffect(() => {
    loadCommitments();
  }, [loadCommitments]);

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Commitments</Text>
      <FlatList
        data={commitments}
        keyExtractor={(item) => item.signal_id}
        renderItem={({ item }) => (
          <View style={styles.card}>
            <Text style={styles.entity}>{item.entity}</Text>
            <Text style={styles.text}>{item.text}</Text>
            <View style={styles.badgeContainer}>
              <Text style={styles.badge}>{item.claim_type}</Text>
              {item.is_commitment && <Text style={styles.commitmentBadge}>COMMITMENT</Text>}
            </View>
          </View>
        )}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={loadCommitments} />}
        ListEmptyComponent={
          <Text style={styles.empty}>No active commitments. Add a signal with "I will..." to create one.</Text>
        }
      />
      {error && <Text style={styles.error}>{error}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 16, backgroundColor: '#f5f4f3' },
  title: { fontSize: 24, fontWeight: 'bold', marginBottom: 16, color: '#1b1a18' },
  card: { backgroundColor: '#fff', padding: 16, borderRadius: 8, marginBottom: 8, borderWidth: 1, borderColor: '#bfbaac' },
  entity: { fontSize: 16, fontWeight: 'bold', color: '#1b1a18' },
  text: { fontSize: 14, color: '#1b1a18', marginTop: 4 },
  badgeContainer: { flexDirection: 'row', marginTop: 8, gap: 8 },
  badge: { fontSize: 11, color: '#64593a', backgroundColor: '#ecebe9', padding: 4, borderRadius: 4, overflow: 'hidden' },
  commitmentBadge: { fontSize: 11, color: '#fff', backgroundColor: '#897128', padding: 4, borderRadius: 4, overflow: 'hidden' },
  empty: { color: '#78766f', fontStyle: 'italic', padding: 16 },
  error: { color: '#9e5852', padding: 16 },
});
