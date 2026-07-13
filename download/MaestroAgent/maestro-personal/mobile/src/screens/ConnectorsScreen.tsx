/**
 * ConnectorsScreen — manage OAuth connectors + draft approval flow.
 *
 * Phase 3: Real data plane on mobile.
 * - Lists all available connectors with connection status
 * - Connect button opens OAuth URL via WebBrowser
 * - Sync button triggers ingestion
 * - Disconnect button removes the connection
 * - Pending drafts with approve/deny/use_draft buttons
 *
 * Uses react-query hooks for data fetching + offline cache.
 */

import React, { useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, ScrollView, StyleSheet, Alert,
  RefreshControl, ActivityIndicator, SafeAreaView, Linking,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as WebBrowser from 'expo-web-browser';
import * as Haptics from 'expo-haptics';

import * as api from '../api/client';
import { colors, getTheme, spacing, typography } from '../theme/colors';
import { useAuth, useTheme } from '../contexts';
import { TopBar, Card, Badge } from '../components';
import { ErrorState, LoadingState, EmptyState } from '../components/ErrorState';

// WebBrowser completion handler (required by expo-web-browser)
WebBrowser.maybeCompleteAuthSession();

const PROVIDER_ICONS: Record<string, string> = {
  gmail: 'mail',
  slack: 'chatbubbles',
  github: 'logo-github',
  calendar: 'calendar',
  whatsapp: 'logo-whatsapp',
  facebook: 'logo-facebook',
  instagram: 'logo-instagram',
  twitter: 'logo-twitter',
};

export default function ConnectorsScreen() {
  const { mode } = useTheme();
  const t = getTheme(mode);
  const { token } = useAuth();
  const [connectors, setConnectors] = useState<any[]>([]);
  const [drafts, setDrafts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyProvider, setBusyProvider] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const [c, d] = await Promise.all([
        api.listConnectors(),
        api.listDrafts(),
      ]);
      setConnectors(c?.connectors || []);
      setDrafts(d?.drafts || []);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [token]);

  React.useEffect(() => { load(); }, [load]);

  // ── Connect a provider via OAuth ──────────────────────────────
  const handleConnect = async (provider: string) => {
    if (!token) return;
    setBusyProvider(provider);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      const data = await api.connectProvider(provider, '');

      if (data?.oauth_required && data?.authorization_url) {
        // Open OAuth URL in browser
        const redirectUrl = 'maestropersonal://oauth/callback';
        const browserResult = await WebBrowser.openAuthSessionAsync(
          data.authorization_url,
          redirectUrl
        );

        if (browserResult?.type === 'success') {
          Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
          await load();
        } else if (browserResult?.type === 'dismiss') {
          await load();
        }
      } else if (data?.connected) {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        await load();
      }
    } catch (e) {
      Alert.alert('Connection Failed', String(e));
    } finally {
      setBusyProvider(null);
    }
  };

  const handleDisconnect = (provider: string) => {
    Alert.alert(
      `Disconnect ${provider}?`,
      'Your OAuth token will be deleted. Ingested signals will remain.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Disconnect', style: 'destructive', onPress: async () => {
          setBusyProvider(provider);
          try {
            await api.disconnectProvider(provider);
            Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
            await load();
          } catch (e) {
            Alert.alert('Error', String(e));
          } finally {
            setBusyProvider(null);
          }
        }},
      ]
    );
  };

  const handleSync = async (provider: string) => {
    if (!token) return;
    setBusyProvider(provider);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    try {
      const data = await api.ingestConnector(provider);
      Alert.alert('Sync Complete', `${provider}: ${data.new_commitments} commitment(s) ingested.`);
      await load();
    } catch (e) {
      Alert.alert('Sync Failed', String(e));
    } finally {
      setBusyProvider(null);
    }
  };

  const handleResolveDraft = async (draftId: string, resolution: 'approve' | 'deny' | 'use_draft') => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      await api.resolveDraft(draftId, resolution);
      if (resolution === 'approve') {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      }
      await load();
    } catch (e) {
      Alert.alert('Error', String(e));
    }
  };

  if (loading) return (
    <SafeAreaView style={{ flex: 1, backgroundColor: t.bg }}>
      <TopBar title="Connectors" />
      <LoadingState label="Loading connectors…" />
    </SafeAreaView>
  );

  if (error) return (
    <SafeAreaView style={{ flex: 1, backgroundColor: t.bg }}>
      <TopBar title="Connectors" />
      <ErrorState message={error} onRetry={load} />
    </SafeAreaView>
  );

  const workConnectors = connectors.filter(c => c.category === 'work');
  const socialConnectors = connectors.filter(c => c.category === 'social');

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: t.bg }}>
      <TopBar title="Connectors" />
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: spacing.xl, paddingBottom: 40 }}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={colors.yellow} />}
      >
        {/* Pending Drafts */}
        {drafts.length > 0 && (
          <View style={{ marginBottom: spacing.xl }}>
            <Text style={[typography.label, { color: colors.yellow, marginBottom: spacing.md }]}>
              📋 PENDING DRAFTS ({drafts.length})
            </Text>
            {drafts.map((draft, i) => (
              <Card key={i} style={{ marginBottom: spacing.md }}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
                  <Badge text={draft.provider} color="yellow" />
                  <Text style={{ fontSize: 12, color: t.textSecondary }}>{draft.recipient}</Text>
                </View>
                <Text style={{ fontSize: 14, color: t.textPrimary, marginTop: 4 }} numberOfLines={2}>
                  {draft.subject || draft.body?.slice(0, 80) + '…'}
                </Text>
                {draft.evidence_refs?.length > 0 && (
                  <Text style={{ fontSize: 12, color: colors.yellow, marginTop: 4 }}>
                    📎 {draft.evidence_refs.length} evidence ref(s)
                  </Text>
                )}
                <View style={{ flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md }}>
                  <TouchableOpacity
                    accessibilityLabel="Approve and send"
                    accessibilityRole="button"
                    style={[styles.draftBtn, { backgroundColor: colors.successGreen }]}
                    onPress={() => handleResolveDraft(draft.draft_id, 'approve')}
                  >
                    <Ionicons name="send" size={16} color={colors.white} />
                    <Text style={styles.draftBtnText}>Send</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    accessibilityLabel="Use as draft"
                    accessibilityRole="button"
                    style={[styles.draftBtn, { backgroundColor: t.border }]}
                    onPress={() => handleResolveDraft(draft.draft_id, 'use_draft')}
                  >
                    <Ionicons name="create" size={16} color={t.textSecondary} />
                    <Text style={[styles.draftBtnText, { color: t.textSecondary }]}>Draft</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    accessibilityLabel="Discard draft"
                    accessibilityRole="button"
                    style={[styles.draftBtn, { backgroundColor: colors.alertRed }]}
                    onPress={() => handleResolveDraft(draft.draft_id, 'deny')}
                  >
                    <Ionicons name="close" size={16} color={colors.white} />
                    <Text style={styles.draftBtnText}>Discard</Text>
                  </TouchableOpacity>
                </View>
              </Card>
            ))}
          </View>
        )}

        {/* Work Connectors */}
        <Text style={[typography.label, { color: t.textSecondary, marginBottom: spacing.md }]}>
          WORK TOOLS
        </Text>
        {workConnectors.map(conn => (
          <ConnectorCard
            key={conn.provider}
            connector={conn}
            t={t}
            busy={busyProvider === conn.provider}
            onConnect={() => handleConnect(conn.provider)}
            onDisconnect={() => handleDisconnect(conn.provider)}
            onSync={() => handleSync(conn.provider)}
          />
        ))}

        {/* Social Connectors */}
        <Text style={[typography.label, { color: t.textSecondary, marginBottom: spacing.md, marginTop: spacing.xl }]}>
          SOCIAL (COMING LATER)
        </Text>
        {socialConnectors.map(conn => (
          <ConnectorCard
            key={conn.provider}
            connector={conn}
            t={t}
            busy={busyProvider === conn.provider}
            onConnect={() => handleConnect(conn.provider)}
            onDisconnect={() => handleDisconnect(conn.provider)}
            onSync={() => handleSync(conn.provider)}
          />
        ))}

        {/* Trust notice */}
        <Card style={{ marginTop: spacing.xl }}>
          <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md }}>
            <Ionicons name="shield-checkmark" size={20} color={colors.successGreen} />
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 14, fontWeight: '600', color: t.textPrimary }}>Your data is yours</Text>
              <Text style={{ fontSize: 12, color: t.textSecondary, marginTop: 4 }}>
                OAuth tokens are encrypted. Maestro extracts commitments only — never stores raw messages. Every action is audited. Disconnect anytime.
              </Text>
            </View>
          </View>
        </Card>
      </ScrollView>
    </SafeAreaView>
  );
}

// ── Connector Card ──────────────────────────────────────────────

function ConnectorCard({
  connector, t, busy, onConnect, onDisconnect, onSync,
}: {
  connector: any;
  t: ReturnType<typeof getTheme>;
  busy: boolean;
  onConnect: () => void;
  onDisconnect: () => void;
  onSync: () => void;
}) {
  const iconName = PROVIDER_ICONS[connector.icon] || 'link';
  const connected = connector.connected;

  return (
    <Card style={{ marginBottom: spacing.md, opacity: busy ? 0.6 : 1 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.md }}>
        {/* Icon */}
        <View style={[
          styles.providerIcon,
          { backgroundColor: connected ? colors.successGreen + '20' : t.border },
        ]}>
          <Ionicons name={iconName as any} size={22} color={connected ? colors.successGreen : t.textSecondary} />
        </View>

        {/* Info */}
        <View style={{ flex: 1 }}>
          <Text style={{ fontSize: 15, fontWeight: '600', color: t.textPrimary }}>{connector.name}</Text>
          {connected ? (
            <Text style={{ fontSize: 12, color: t.textSecondary, marginTop: 2 }}>
              {connector.commitments_ingested} commitments ingested
            </Text>
          ) : (
            <Text style={{ fontSize: 12, color: t.textSecondary, marginTop: 2 }} numberOfLines={1}>
              {connector.ingest_description}
            </Text>
          )}
        </View>

        {/* Status badge */}
        {connected ? (
          <Badge text="Connected" color="green" />
        ) : (
          <Badge text="Not connected" color="gray" />
        )}
      </View>

      {/* Actions */}
      <View style={{ flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md }}>
        {busy ? (
          <ActivityIndicator color={colors.yellow} size="small" />
        ) : connected ? (
          <>
            <TouchableOpacity
              accessibilityLabel={`Sync ${connector.name}`}
              accessibilityRole="button"
              accessibilityHint="Pulls new data from this connector"
              style={[styles.actionBtn, { borderColor: colors.yellow }]}
              onPress={onSync}
            >
              <Ionicons name="sync" size={16} color={colors.yellow} />
              <Text style={[styles.actionBtnText, { color: colors.yellow }]}>Sync</Text>
            </TouchableOpacity>
            <TouchableOpacity
              accessibilityLabel={`Disconnect ${connector.name}`}
              accessibilityRole="button"
              style={[styles.actionBtn, { borderColor: colors.alertRed }]}
              onPress={onDisconnect}
            >
              <Ionicons name="close-circle" size={16} color={colors.alertRed} />
              <Text style={[styles.actionBtnText, { color: colors.alertRed }]}>Disconnect</Text>
            </TouchableOpacity>
          </>
        ) : (
          <TouchableOpacity
            accessibilityLabel={`Connect ${connector.name}`}
            accessibilityRole="button"
            accessibilityHint="Opens OAuth consent screen to connect this account"
            style={[styles.actionBtn, { backgroundColor: colors.yellow }]}
            onPress={onConnect}
          >
            <Ionicons name="link" size={16} color={colors.black} />
            <Text style={[styles.actionBtnText, { color: colors.black }]}>Connect</Text>
          </TouchableOpacity>
        )}
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  providerIcon: {
    width: 40, height: 40, borderRadius: 20,
    justifyContent: 'center', alignItems: 'center',
  },
  actionBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: 16, paddingVertical: 8,
    borderRadius: 8, borderWidth: 1, borderColor: 'transparent',
  },
  actionBtnText: {
    fontSize: 14, fontWeight: '600',
  },
  draftBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: 16, paddingVertical: 8,
    borderRadius: 8,
  },
  draftBtnText: {
    fontSize: 14, fontWeight: '600', color: colors.white,
  },
});
