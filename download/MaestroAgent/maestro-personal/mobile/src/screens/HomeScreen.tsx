/**
 * HomeScreen — THE MOMENT.
 *
 * Not a dashboard. Not a list. One card.
 *
 * The single most important thing Maestro knows right now.
 * If nothing deserves attention: trusted silence.
 *
 * This is the Spotlight moment. The Tesla unlock. The inevitable interaction.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, ScrollView, RefreshControl, StyleSheet, TouchableOpacity } from 'react-native';
import { useAuth } from '../api/auth';
import { getTheMoment, TheMoment } from '../api/client';

export default function HomeScreen({ navigation }: { navigation: any }) {
  const { token } = useAuth();
  const [moment, setMoment] = useState<TheMoment | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadMoment = useCallback(async () => {
    if (!token) return;
    setRefreshing(true);
    setError(null);
    try {
      const m = await getTheMoment(token);
      setMoment(m);
    } catch (e) {
      setError(String(e));
    } finally {
      setRefreshing(false);
    }
  }, [token]);

  useEffect(() => {
    loadMoment();
  }, [loadMoment]);

  return (
    <View style={styles.container}>
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={loadMoment} />}
      >
        {error && <Text style={styles.error}>{error}</Text>}

        {moment && moment.has_moment && moment.commitment && (
          <View style={styles.momentCard}>
            <Text style={styles.kicker}>The moment</Text>
            <Text style={styles.entity}>{moment.commitment.entity}</Text>
            <Text style={styles.commitmentText}>{moment.commitment.text}</Text>

            {moment.why_this_one && (
              <Text style={styles.why}>{moment.why_this_one}</Text>
            )}

            {moment.situation && (
              <View style={styles.situationRow}>
                <Text style={styles.situationLabel}>Situation:</Text>
                <Text style={styles.situationState}>{moment.situation.state}</Text>
                <Text style={styles.situationEvidence}>
                  {moment.situation.evidence_count} evidence refs
                </Text>
              </View>
            )}

            {moment.source_evidence.length > 0 && (
              <View style={styles.evidenceContainer}>
                <Text style={styles.evidenceLabel}>Source:</Text>
                <Text style={styles.evidenceText}>
                  {moment.source_evidence[0].text}
                </Text>
                <Text style={styles.evidenceSource}>
                  via {moment.source_evidence[0].source}
                </Text>
              </View>
            )}

            <TouchableOpacity
              style={styles.actButton}
              onPress={() => navigation.navigate('Ask', {
                query: `What's the full situation with ${moment.commitment.entity}?`
              })}
            >
              <Text style={styles.actButtonText}>Ask about this</Text>
            </TouchableOpacity>
          </View>
        )}

        {moment && !moment.has_moment && (
          <View style={styles.silenceCard}>
            <Text style={styles.silenceTitle}>Nothing needs your attention right now.</Text>
            <Text style={styles.silenceBody}>
              Trusted silence. Maestro will surface the moment something matters.
            </Text>
            <TouchableOpacity
              style={styles.addLink}
              onPress={() => navigation.navigate('AddSignal')}
            >
              <Text style={styles.addLinkText}>Add a signal to get started</Text>
            </TouchableOpacity>
          </View>
        )}

        {!moment && !error && (
          <View style={styles.loadingCard}>
            <Text style={styles.loadingText}>Maestro is thinking...</Text>
          </View>
        )}
      </ScrollView>

      <TouchableOpacity
        style={styles.fab}
        onPress={() => navigation.navigate('AddSignal')}
      >
        <Text style={styles.fabText}>+</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#1b1a18',
  },
  scrollContent: {
    flexGrow: 1,
    justifyContent: 'center',
    padding: 24,
    minHeight: '100%',
  },
  momentCard: {
    backgroundColor: '#262422',
    borderRadius: 16,
    padding: 28,
    borderWidth: 1,
    borderColor: '#64593a',
  },
  kicker: {
    fontSize: 11,
    fontWeight: '600',
    letterSpacing: 2,
    color: '#897128',
    textTransform: 'uppercase',
    marginBottom: 16,
  },
  entity: {
    fontSize: 14,
    color: '#78766f',
    marginBottom: 8,
  },
  commitmentText: {
    fontSize: 22,
    fontWeight: '600',
    color: '#f5f4f3',
    lineHeight: 30,
    marginBottom: 20,
  },
  why: {
    fontSize: 13,
    color: '#897128',
    marginBottom: 20,
    fontStyle: 'italic',
  },
  situationRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 16,
    paddingBottom: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#3a3835',
  },
  situationLabel: {
    fontSize: 12,
    color: '#78766f',
  },
  situationState: {
    fontSize: 12,
    color: '#f5f4f3',
    fontWeight: '600',
    textTransform: 'capitalize',
  },
  situationEvidence: {
    fontSize: 11,
    color: '#78766f',
    marginLeft: 'auto',
  },
  evidenceContainer: {
    backgroundColor: '#1b1a18',
    borderRadius: 8,
    padding: 12,
    marginBottom: 20,
  },
  evidenceLabel: {
    fontSize: 10,
    color: '#78766f',
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: 4,
  },
  evidenceText: {
    fontSize: 13,
    color: '#bfbaac',
    lineHeight: 18,
  },
  evidenceSource: {
    fontSize: 11,
    color: '#78766f',
    marginTop: 4,
    fontStyle: 'italic',
  },
  actButton: {
    backgroundColor: '#897128',
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: 'center',
  },
  actButtonText: {
    color: '#1b1a18',
    fontSize: 15,
    fontWeight: '600',
  },
  silenceCard: {
    alignItems: 'center',
    padding: 40,
  },
  silenceTitle: {
    fontSize: 20,
    color: '#78766f',
    textAlign: 'center',
    marginBottom: 12,
    fontWeight: '500',
  },
  silenceBody: {
    fontSize: 14,
    color: '#5a5854',
    textAlign: 'center',
    lineHeight: 22,
  },
  addLink: {
    marginTop: 24,
  },
  addLinkText: {
    color: '#897128',
    fontSize: 14,
  },
  loadingCard: {
    alignItems: 'center',
    padding: 40,
  },
  loadingText: {
    color: '#78766f',
    fontSize: 16,
  },
  error: {
    color: '#9e5852',
    padding: 20,
    textAlign: 'center',
  },
  fab: {
    position: 'absolute',
    bottom: 24,
    right: 24,
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: '#897128',
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 8,
  },
  fabText: {
    color: '#1b1a18',
    fontSize: 28,
    fontWeight: '300',
  },
});
