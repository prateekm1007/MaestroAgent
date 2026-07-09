/**
 * WhisperScreen — one sentence when it matters, silence otherwise.
 *
 * Bumble-inspired: warm, honey accent for high priority, purple for medium,
 * trusted silence as a warm empty state.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, FlatList, RefreshControl, StyleSheet, TouchableOpacity } from 'react-native';
import { useAuth } from '../api/auth';
import { getWhispers, WhisperItem } from '../api/client';
import { theme } from '../theme';

export default function WhisperScreen({ navigation }: { navigation: any }) {
  const { token } = useAuth();
  const [whispers, setWhispers] = useState<WhisperItem[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
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

  useEffect(() => { load(); }, [load]);

  const accentFor = (priority: string) => {
    switch (priority) {
      case 'high': return theme.honey;
      case 'medium': return theme.purple;
      default: return theme.textSecondary;
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Whisper</Text>
      <Text style={styles.subtitle}>Things that deserve attention right now</Text>
      <FlatList
        data={whispers}
        keyExtractor={(item, i) => `${item.type}-${i}`}
        renderItem={({ item }) => {
          const accent = accentFor(item.priority);
          return (
            <TouchableOpacity
              style={[styles.card, { borderLeftColor: accent }]}
              onPress={() => {
                if (item.action_url?.includes('commitments')) navigation.navigate('Commitments');
                else if (item.action_url?.includes('prepare')) navigation.navigate('Prepare');
              }}
            >
              <View style={styles.header}>
                <Text style={styles.entity}>{item.entity}</Text>
                <Text style={[styles.priority, { color: accent }]}>
                  {item.priority.toUpperCase()}
                </Text>
              </View>
              <Text style={styles.whisperTitle}>{item.title}</Text>
              <Text style={styles.body}>{item.body}</Text>
              <Text style={styles.type}>{item.type.replace(/_/g, ' ')}</Text>
            </TouchableOpacity>
          );
        }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={load} tintColor={theme.honey} />}
        ListEmptyComponent={
          <View style={styles.silenceContainer}>
            <View style={styles.silenceIcon}>
              <Text style={styles.silenceIconText}>✦</Text>
            </View>
            <Text style={styles.silenceTitle}>Nothing needs your attention right now.</Text>
            <Text style={styles.silenceBody}>Trusted silence. We'll whisper when something matters.</Text>
          </View>
        }
      />
      {error && <Text style={styles.error}>{error}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 20, backgroundColor: theme.bg },
  title: { ...theme.font.title, marginBottom: 4 },
  subtitle: { fontSize: 14, color: theme.textSecondary, marginBottom: 20 },
  card: {
    backgroundColor: theme.cardBg,
    padding: 20,
    borderRadius: theme.radius.lg,
    marginBottom: 10,
    borderLeftWidth: 4,
    ...theme.shadow.card,
  },
  header: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 10 },
  entity: { fontSize: 14, fontWeight: '700', color: theme.textPrimary },
  priority: { fontSize: 11, fontWeight: '700' },
  whisperTitle: { fontSize: 17, fontWeight: '700', color: theme.textPrimary, marginBottom: 6 },
  body: { fontSize: 15, color: theme.textPrimary, lineHeight: 22 },
  type: { fontSize: 11, color: theme.textSecondary, marginTop: 10, textTransform: 'capitalize' },
  silenceContainer: { alignItems: 'center', padding: 40, marginTop: 40 },
  silenceIcon: {
    width: 64, height: 64, borderRadius: 32,
    backgroundColor: theme.bgSecondary,
    justifyContent: 'center', alignItems: 'center', marginBottom: 24,
  },
  silenceIconText: { fontSize: 28, color: theme.honeyDark },
  silenceTitle: { fontSize: 18, fontWeight: '700', color: theme.textPrimary, textAlign: 'center', marginBottom: 8 },
  silenceBody: { fontSize: 15, color: theme.textSecondary, textAlign: 'center', lineHeight: 22 },
  error: { color: theme.error, padding: 16 },
});
