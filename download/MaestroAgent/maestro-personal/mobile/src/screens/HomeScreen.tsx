/**
 * HomeScreen — THE MOMENT.
 *
 * Bumble-inspired: warm cream background, honey accent, bold typography,
 * soft card shadows. One card. The inevitable interaction.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, ScrollView, RefreshControl, StyleSheet, TouchableOpacity } from 'react-native';
import { useAuth } from '../api/auth';
import { getTheMoment, TheMoment } from '../api/client';
import { theme } from '../theme';

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
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={loadMoment} tintColor={theme.honey} />}
      >
        {error && <Text style={styles.error}>{error}</Text>}

        {moment && moment.has_moment && moment.commitment && (
          <View style={styles.momentCard}>
            <Text style={styles.kicker}>THE MOMENT</Text>
            <Text style={styles.entity}>{moment.commitment.entity}</Text>
            <Text style={styles.commitmentText}>{moment.commitment.text}</Text>

            {moment.why_this_one ? (
              <View style={styles.whyBadge}>
                <Text style={styles.whyText}>{moment.why_this_one}</Text>
              </View>
            ) : null}

            {moment.situation && (
              <View style={styles.situationRow}>
                <View style={styles.statePill}>
                  <Text style={styles.stateText}>{moment.situation.state}</Text>
                </View>
                <Text style={styles.evidenceText}>
                  {moment.situation.evidence_count} evidence refs
                </Text>
              </View>
            )}

            {moment.source_evidence.length > 0 && (
              <View style={styles.evidenceContainer}>
                <Text style={styles.evidenceLabel}>SOURCE</Text>
                <Text style={styles.evidenceText2}>
                  {moment.source_evidence[0].text}
                </Text>
                <Text style={styles.evidenceSource}>
                  via {moment.source_evidence[0].source}
                </Text>
              </View>
            )}

            <TouchableOpacity
              style={styles.askButton}
              onPress={() => navigation.navigate('Ask', {
                query: `What's the full situation with ${moment.commitment?.entity ?? 'this'}?`
              })}
            >
              <Text style={styles.askButtonText}>Ask about this</Text>
            </TouchableOpacity>
          </View>
        )}

        {moment && !moment.has_moment && (
          <View style={styles.silenceCard}>
            <View style={styles.silenceIcon}>
              <Text style={styles.silenceIconText}>✦</Text>
            </View>
            <Text style={styles.silenceTitle}>Nothing needs your attention right now.</Text>
            <Text style={styles.silenceBody}>
              Trusted silence. Maestro will surface the moment something matters.
            </Text>
            <TouchableOpacity
              style={styles.addLinkButton}
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
    backgroundColor: theme.bg,
  },
  scrollContent: {
    flexGrow: 1,
    justifyContent: 'center',
    padding: 20,
    minHeight: '100%',
  },
  momentCard: {
    backgroundColor: theme.cardBg,
    borderRadius: theme.radius.xl,
    padding: 28,
    ...theme.shadow.card,
  },
  kicker: {
    ...theme.font.kicker,
    marginBottom: 16,
  },
  entity: {
    fontSize: 14,
    fontWeight: '600',
    color: theme.textSecondary,
    marginBottom: 8,
  },
  commitmentText: {
    fontSize: 24,
    fontWeight: '800',
    color: theme.textPrimary,
    lineHeight: 32,
    marginBottom: 20,
  },
  whyBadge: {
    backgroundColor: theme.purpleLight,
    borderRadius: theme.radius.md,
    paddingHorizontal: 14,
    paddingVertical: 8,
    marginBottom: 20,
    alignSelf: 'flex-start',
  },
  whyText: {
    fontSize: 13,
    fontWeight: '600',
    color: theme.purple,
  },
  situationRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 16,
    paddingBottom: 16,
    borderBottomWidth: 1,
    borderBottomColor: theme.divider,
  },
  statePill: {
    backgroundColor: theme.honey,
    borderRadius: theme.radius.pill,
    paddingHorizontal: 12,
    paddingVertical: 4,
  },
  stateText: {
    fontSize: 12,
    fontWeight: '700',
    color: theme.textOnHoney,
    textTransform: 'capitalize',
  },
  evidenceText: {
    fontSize: 12,
    color: theme.textSecondary,
    marginLeft: 'auto',
  },
  evidenceContainer: {
    backgroundColor: theme.bgSecondary,
    borderRadius: theme.radius.md,
    padding: 14,
    marginBottom: 20,
  },
  evidenceLabel: {
    fontSize: 10,
    fontWeight: '700',
    color: theme.textSecondary,
    letterSpacing: 1.5,
    marginBottom: 6,
  },
  evidenceText2: {
    fontSize: 14,
    color: theme.textPrimary,
    lineHeight: 20,
  },
  evidenceSource: {
    fontSize: 12,
    color: theme.textSecondary,
    marginTop: 6,
    fontStyle: 'italic',
  },
  askButton: {
    backgroundColor: theme.honey,
    borderRadius: theme.radius.lg,
    paddingVertical: 16,
    alignItems: 'center',
  },
  askButtonText: {
    color: theme.textOnHoney,
    fontSize: 16,
    fontWeight: '700',
  },
  silenceCard: {
    alignItems: 'center',
    padding: 40,
  },
  silenceIcon: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: theme.bgSecondary,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 24,
  },
  silenceIconText: {
    fontSize: 28,
    color: theme.honeyDark,
  },
  silenceTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: theme.textPrimary,
    textAlign: 'center',
    marginBottom: 12,
  },
  silenceBody: {
    fontSize: 15,
    color: theme.textSecondary,
    textAlign: 'center',
    lineHeight: 22,
  },
  addLinkButton: {
    marginTop: 28,
    backgroundColor: theme.honey,
    borderRadius: theme.radius.pill,
    paddingHorizontal: 24,
    paddingVertical: 12,
  },
  addLinkText: {
    color: theme.textOnHoney,
    fontSize: 15,
    fontWeight: '700',
  },
  loadingCard: {
    alignItems: 'center',
    padding: 40,
  },
  loadingText: {
    color: theme.textSecondary,
    fontSize: 16,
  },
  error: {
    color: theme.error,
    padding: 20,
    textAlign: 'center',
  },
  fab: {
    position: 'absolute',
    bottom: 24,
    right: 24,
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: theme.honey,
    justifyContent: 'center',
    alignItems: 'center',
    ...theme.shadow.cardHover,
  },
  fabText: {
    color: theme.textOnHoney,
    fontSize: 32,
    fontWeight: '300',
  },
});
