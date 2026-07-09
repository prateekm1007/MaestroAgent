/**
 * Whisper screen — proactive just-in-time intervention.
 *
 * Shows things that deserve attention RIGHT NOW:
 * - Stale commitments (no follow-up for 3+ days)
 * - Upcoming meeting prep (meeting within 2 hours)
 * - Approaching deadlines (within 24 hours)
 *
 * Per break-test dimension 7 (Restraint): empty list = trusted silence.
 * Whisper does NOT fire when nothing deserves attention.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, FlatList, RefreshControl, StyleSheet, TouchableOpacity } from 'react-native';
import { useAuth } from '../api/auth';
import { getWhispers, WhisperItem } from '../api/client';

export default function WhisperScreen() {
  const { token } = useAuth();
  const [whispers, setWhispers] = useState<WhisperItem[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadWhispers = useCallback(async () => {
    if (!token) return;
    setRefreshing(true);
    setError(null);
    try {
      const data = await getWhispers(token);
      setWhispers(data);
    } catch (e) {
      setError(String(e));
    } finally {
      setRefreshing(false);
    }
  }, [token]);

  useEffect(() => {
    loadWhispers();
  }, [loadWhispers]);

  const priorityColor = (priority: string) => {
    switch (priority) {
      case 'high': return '#9e5852';
      case 'medium': return '#97783b';
      default: return '#78766f';
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Whisper</Text>
      <Text style={styles.subtitle}>Things that deserve attention right now</Text>
      <FlatList
        data={whispers}
        keyExtractor={(item, i) => `${item.type}-${i}`}
        renderItem={({ item }) => (
          <TouchableOpacity style={[styles.card, { borderLeftColor: priorityColor(item.priority) }]}>
            <View style={styles.header}>
              <Text style={styles.entity}>{item.entity}</Text>
              <Text style={[styles.priority, { color: priorityColor(item.priority) }]}>
                {item.priority.toUpperCase()}
              </Text>
            </View>
            <Text style={styles.whisperTitle}>{item.title}</Text>
            <Text style={styles.body}>{item.body}</Text>
            <Text style={styles.type}>{item.type.replace(/_/g, ' ')}</Text>
          </TouchableOpacity>
        )}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={loadWhispers} />}
        ListEmptyComponent={
          <View style={styles.silenceContainer}>
            <Text style={styles.silence}>Nothing needs your attention right now.</Text>
            <Text style={styles.silenceSubtext}>Trusted silence. We'll whisper when something matters.</Text>
          </View>
        }
      />
      {error && <Text style={styles.error}>{error}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 16, backgroundColor: '#f5f4f3' },
  title: { fontSize: 24, fontWeight: 'bold', color: '#1b1a18' },
  subtitle: { fontSize: 14, color: '#78766f', marginBottom: 16 },
  card: { backgroundColor: '#fff', padding: 16, borderRadius: 8, marginBottom: 8, borderLeftWidth: 4, borderWidth: 1, borderColor: '#bfbaac' },
  header: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 },
  entity: { fontSize: 14, fontWeight: 'bold', color: '#1b1a18' },
  priority: { fontSize: 11, fontWeight: 'bold' },
  whisperTitle: { fontSize: 16, fontWeight: 'bold', color: '#1b1a18', marginBottom: 4 },
  body: { fontSize: 14, color: '#1b1a18', lineHeight: 20 },
  type: { fontSize: 11, color: '#78766f', marginTop: 8, textTransform: 'capitalize' },
  silenceContainer: { padding: 32, alignItems: 'center' },
  silence: { fontSize: 18, color: '#78766f', textAlign: 'center', marginBottom: 8 },
  silenceSubtext: { fontSize: 14, color: '#78766f', textAlign: 'center', fontStyle: 'italic' },
  error: { color: '#9e5852', padding: 16 },
});
