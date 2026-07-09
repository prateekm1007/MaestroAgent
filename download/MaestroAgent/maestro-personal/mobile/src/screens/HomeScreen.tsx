/**
 * Home screen — shows detected situations + what changed.
 *
 * This is the landing screen after login. It gives the user an overview
 * of their personal situations and recent meaningful deltas.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, FlatList, RefreshControl, StyleSheet, TouchableOpacity } from 'react-native';
import { useAuth } from '../api/auth';
import { getSituations, getWhatChanged, Situation, WhatChangedItem } from '../api/client';

export default function HomeScreen({ navigation }: { navigation: any }) {
  const { token } = useAuth();
  const [situations, setSituations] = useState<Situation[]>([]);
  const [deltas, setDeltas] = useState<WhatChangedItem[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    if (!token) return;
    setRefreshing(true);
    setError(null);
    try {
      const [sits, changed] = await Promise.all([
        getSituations(token),
        getWhatChanged(token),
      ]);
      setSituations(sits);
      setDeltas(changed.filter((d) => d.is_meaningful));
    } catch (e) {
      setError(String(e));
    } finally {
      setRefreshing(false);
    }
  }, [token]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  return (
    <View style={styles.container}>
      <TouchableOpacity
        style={styles.addButton}
        onPress={() => navigation.navigate('AddSignal')}
      >
        <Text style={styles.addButtonText}>+ Add Signal</Text>
      </TouchableOpacity>

      <Text style={styles.sectionTitle}>Situations ({situations.length})</Text>
      <FlatList
        data={situations}
        keyExtractor={(item) => item.situation_id}
        renderItem={({ item }) => (
          <View style={styles.card}>
            <Text style={styles.entity}>{item.entity}</Text>
            <Text style={styles.state}>{item.state}</Text>
            <Text style={styles.evidence}>{item.evidence_count} evidence refs</Text>
          </View>
        )}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={loadData} />}
        ListEmptyComponent={
          <Text style={styles.empty}>No situations detected. Add signals to get started.</Text>
        }
      />

      <Text style={styles.sectionTitle}>What Changed</Text>
      <FlatList
        data={deltas}
        keyExtractor={(item, i) => `${i}`}
        renderItem={({ item }) => (
          <View style={styles.card}>
            <Text style={styles.entity}>{item.entity}</Text>
            <Text style={styles.text}>{item.text}</Text>
            <Text style={styles.type}>{item.type}</Text>
          </View>
        )}
        ListEmptyComponent={
          <Text style={styles.empty}>No recent changes.</Text>
        }
      />

      {error && <Text style={styles.error}>{error}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 16, backgroundColor: '#f5f4f3' },
  addButton: {
    backgroundColor: '#897128',
    padding: 12,
    borderRadius: 8,
    alignItems: 'center',
    marginBottom: 16,
  },
  addButtonText: { color: '#fff', fontWeight: 'bold', fontSize: 16 },
  sectionTitle: { fontSize: 18, fontWeight: 'bold', marginTop: 16, marginBottom: 8, color: '#1b1a18' },
  card: { backgroundColor: '#fff', padding: 16, borderRadius: 8, marginBottom: 8, borderWidth: 1, borderColor: '#bfbaac' },
  entity: { fontSize: 16, fontWeight: 'bold', color: '#1b1a18' },
  state: { fontSize: 14, color: '#64593a', marginTop: 4 },
  evidence: { fontSize: 12, color: '#78766f', marginTop: 4 },
  text: { fontSize: 14, color: '#1b1a18', marginTop: 4 },
  type: { fontSize: 12, color: '#78766f', marginTop: 4 },
  empty: { color: '#78766f', fontStyle: 'italic', padding: 16 },
  error: { color: '#9e5852', padding: 16 },
});
