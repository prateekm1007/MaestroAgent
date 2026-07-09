/**
 * Prepare screen — preparation for upcoming meetings/situations.
 *
 * Calls GET /api/prepare. Uses Core's SituationPreparationBridge
 * via the shell.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, FlatList, RefreshControl, StyleSheet } from 'react-native';
import { useAuth } from '../api/auth';
import { getPrepare, PrepareItem } from '../api/client';

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

  useEffect(() => {
    loadPreps();
  }, [loadPreps]);

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Prepare</Text>
      <FlatList
        data={preps}
        keyExtractor={(item) => item.situation_id}
        renderItem={({ item }) => (
          <View style={styles.card}>
            <Text style={styles.situationId}>Situation: {item.situation_id.substring(0, 8)}...</Text>
            {item.is_stale && <Text style={styles.stale}>⚠ Preparation is stale — reality changed</Text>}
            {item.prep_points.length > 0 ? (
              item.prep_points.map((point, i) => (
                <Text key={i} style={styles.prepPoint}>• {point}</Text>
              ))
            ) : (
              <Text style={styles.empty}>No prep points yet.</Text>
            )}
          </View>
        )}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={loadPreps} />}
        ListEmptyComponent={
          <Text style={styles.empty}>No situations need preparation right now.</Text>
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
  situationId: { fontSize: 12, color: '#78766f', marginBottom: 8 },
  stale: { fontSize: 13, color: '#9e5852', marginBottom: 8, fontWeight: 'bold' },
  prepPoint: { fontSize: 14, color: '#1b1a18', marginTop: 4, lineHeight: 20 },
  empty: { color: '#78766f', fontStyle: 'italic', padding: 16 },
  error: { color: '#9e5852', padding: 16 },
});
