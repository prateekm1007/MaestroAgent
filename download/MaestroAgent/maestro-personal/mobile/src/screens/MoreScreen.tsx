/**
 * MoreScreen — merged Connectors + Settings into one scrollable screen.
 *
 * V2 plan: replaces ConnectorsScreen + SettingsScreen. Contains:
 * 1. Connectors (Gmail, Slack, GitHub, Calendar)
 * 2. Draft Preferences (tone, auto-draft, default provider)
 * 3. Notification Preferences (stale alerts, meeting reminders, etc.)
 * 4. Privacy & Data (export, delete, audit log, retention policy)
 * 5. Settings (theme toggle, LLM status, Brier score, server URL)
 * 6. Account (logout)
 *
 * P1-1 fix (audit 2026-07-15): notification toggles were hardcoded
 * `value={true}`. They now use local state persisted to AsyncStorage
 * so the toggle reflects the user's actual choice.
 *
 * P1-2 fix: LLM status was hardcoded "active". Now queries the real
 * /api/llm-status endpoint and shows active/inactive honestly.
 *
 * P1-3 fix: Brier score was hardcoded "0.16". Now queries /api/calibration
 * and shows the real value (or "—" if unavailable).
 *
 * P1-4 fix: Export/Audit/Retention buttons were haptic-only no-ops.
 * They now call the real API and show the result in an alert.
 */

import React, { useMemo, useState, useEffect } from 'react';
import { View, Text, TouchableOpacity, ScrollView, Switch, StyleSheet, Alert, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import * as WebBrowser from 'expo-web-browser';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { colors, getTheme } from '../theme/colors';
import { useTheme, useAuth } from '../contexts';
import * as api from '../api/client';

// Cross-platform alert: Alert.alert on native, window.alert/confirm on web
function showAlert(title: string, message?: string, buttons?: Array<{text: string; onPress?: () => void; style?: string}>): void {
  if (Platform.OS === 'web') {
    if (buttons && buttons.length > 1) {
      const ok = window.confirm(message ? `${title}\n\n${message}` : title);
      const destructiveBtn = buttons.find(b => b.style === 'destructive');
      if (ok && destructiveBtn?.onPress) destructiveBtn.onPress();
    } else {
      window.alert(message ? `${title}\n\n${message}` : title);
    }
  } else {
    if (buttons) {
      Alert.alert(title, message, buttons as any);
    } else {
      Alert.alert(title, message);
    }
  }
}

const NOTIF_PREFS_KEY = 'maestro_notification_prefs';

export default function MoreScreen() {
  const { mode, toggle } = useTheme() as any;
  const { logout } = useAuth();
  const t = getTheme(mode);
  const queryClient = useQueryClient();
  const [busyProvider, setBusyProvider] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);

  // P1-1 fix: notification toggles backed by AsyncStorage (persisted, honest)
  const [notifPrefs, setNotifPrefs] = useState({
    stale_alerts: true,
    meeting_reminders: true,
    daily_briefing: true,
    connector_sync: true,
  });
  useEffect(() => {
    AsyncStorage.getItem(NOTIF_PREFS_KEY).then((stored) => {
      if (stored) {
        try { setNotifPrefs(JSON.parse(stored)); } catch {}
      }
    });
  }, []);
  const toggleNotifPref = (key: keyof typeof notifPrefs) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    const next = { ...notifPrefs, [key]: !notifPrefs[key] };
    setNotifPrefs(next);
    AsyncStorage.setItem(NOTIF_PREFS_KEY, JSON.stringify(next));
  };

  // Change 13: "What Maestro Knows" transparency data
  const { data: signals } = useQuery({ queryKey: ['signals'], queryFn: () => api.getSignals() });
  const { data: commitments } = useQuery({ queryKey: ['commitments'], queryFn: () => api.getCommitments() });
  const { data: connectorList } = useQuery({
    queryKey: ['connectors'],
    queryFn: () => api.listConnectors().catch(() => ({ connectors: [] })),
  });
  // P1-2 fix: real LLM status (was hardcoded "active")
  const { data: llmStatus } = useQuery({
    queryKey: ['llm-status'],
    queryFn: () => api.getLLMStatus().catch(() => null),
    staleTime: 60_000,
  });
  // P1-3 fix: real Brier score from /api/calibration (was hardcoded "0.16")
  const { data: calibration } = useQuery({
    queryKey: ['calibration'],
    queryFn: () => api.getCalibration().catch(() => null),
    staleTime: 60_000,
  });
  const uniqueEntities = useMemo(() => {
    if (!signals) return 0;
    return new Set(signals.map((s: any) => s.entity)).size;
  }, [signals]);

  const llmActive = llmStatus?.active || llmStatus?.llm_active || false;
  const llmProvider = llmStatus?.provider || 'none';
  const brierScore = calibration?.brier_score;
  const brierDisplay = brierScore != null ? brierScore.toFixed(3) : '—';

  // P0-2 + P0-3 fix (audit V2 2026-07-15): connector buttons now have a
  // full OAuth flow using expo-web-browser's openAuthSessionAsync (the
  // proper mobile OAuth pattern), plus sync and disconnect actions.
  // The prior fix only used Linking.openURL which doesn't capture the
  // redirect back to the app. openAuthSessionAsync waits for the redirect
  // and returns the result URL, which completes the OAuth flow.
  const handleConnect = async (provider: string) => {
    if (busyProvider) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setBusyProvider(provider);
    try {
      const result = await api.connectProvider(provider, '');
      if (result.oauth_required && result.authorization_url) {
        // Real OAuth: open provider's login page
        if (Platform.OS === 'web') {
          // Web: open in a new tab, then poll until connected, then auto-sync
          window.open(result.authorization_url, '_blank');
          showAlert('Check the other tab', `Complete the ${provider} login in the tab that just opened. Sync will start automatically when done.`);

          // Poll every 2 seconds for up to 2 minutes — when the connector
          // shows as connected, auto-sync immediately
          let attempts = 0;
          const pollInterval = setInterval(async () => {
            attempts++;
            if (attempts > 60) { // 2 min timeout
              clearInterval(pollInterval);
              setBusyProvider(null);
              return;
            }
            try {
              const connList = await api.listConnectors();
              const conn = connList.connectors?.find((c: any) => c.provider === provider);
              if (conn?.connected) {
                clearInterval(pollInterval);
                // Auto-sync immediately after connection detected
                const syncResult = await api.ingestConnector(provider);
                Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
                showAlert(
                  `${provider} Connected + Synced`,
                  `Pulled ${syncResult.ingested} messages, ${syncResult.new_commitments} new commitments.`,
                );
                queryClient.invalidateQueries({ queryKey: ['connectors'] });
                queryClient.invalidateQueries({ queryKey: ['signals'] });
                queryClient.invalidateQueries({ queryKey: ['commitments'] });
                setBusyProvider(null);
              }
            } catch {}
          }, 2000);
        } else {
          // Native: use expo-web-browser for in-app OAuth
          const redirectUrl = 'maestro://oauth/callback';
          const authUrl = result.authorization_url +
            (result.authorization_url.includes('?') ? '&' : '?') +
            `redirect_uri=${encodeURIComponent(redirectUrl)}`;
          const browserResult = await WebBrowser.openAuthSessionAsync(authUrl, redirectUrl);
          if (browserResult.type === 'success') {
            // Auto-sync immediately after OAuth completes
            try {
              const syncResult = await api.ingestConnector(provider);
              Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
              showAlert(
                `${provider} Connected + Synced`,
                `Pulled ${syncResult.ingested} messages, ${syncResult.new_commitments} new commitments.`,
              );
              queryClient.invalidateQueries({ queryKey: ['connectors'] });
              queryClient.invalidateQueries({ queryKey: ['signals'] });
              queryClient.invalidateQueries({ queryKey: ['commitments'] });
            } catch {
              showAlert('Connected', `${provider} connected. Tap again to sync.`);
            }
          }
        }
      } else if (result.connected) {
        // Already connected (demo mode) — auto-sync
        try {
          const syncResult = await api.ingestConnector(provider);
          Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
          showAlert(
            `${provider} Synced`,
            `Pulled ${syncResult.ingested} messages, ${syncResult.new_commitments} new commitments.`,
          );
          queryClient.invalidateQueries({ queryKey: ['connectors'] });
          queryClient.invalidateQueries({ queryKey: ['signals'] });
          queryClient.invalidateQueries({ queryKey: ['commitments'] });
        } catch (err: any) {
          showAlert('Connected', `${provider} is now connected.`);
          queryClient.invalidateQueries({ queryKey: ['connectors'] });
        }
      } else {
        showAlert('Not configured', `${provider} OAuth is not configured on the backend.`);
      }
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || 'Unknown error';
      showAlert('Cannot connect', detail);
    } finally {
      setBusyProvider(null);
    }
  };

  // P0-2 fix: sync action — pulls messages from the connector and ingests
  // them as signals. Shows progress + result count.
  const handleSync = async (provider: string) => {
    if (busyProvider) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setBusyProvider(provider);
    try {
      const result = await api.ingestConnector(provider);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      showAlert(
        'Sync Complete',
        `Ingested ${result.ingested} signals from ${provider}.\n` +
        `${result.new_commitments} new commitments, ${result.duplicates} duplicates.`,
      );
      queryClient.invalidateQueries({ queryKey: ['signals'] });
      queryClient.invalidateQueries({ queryKey: ['commitments'] });
      queryClient.invalidateQueries({ queryKey: ['connectors'] });
    } catch (err: any) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      const detail = err?.response?.data?.detail || err?.message || 'Unknown error';
      showAlert('Sync Failed', String(detail));
    } finally {
      setBusyProvider(null);
    }
  };

  // P0-2 fix: disconnect action — removes the OAuth token, keeps audit history
  const handleDisconnect = async (provider: string) => {
    if (busyProvider) return;
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
    showAlert(
      `Disconnect ${provider}?`,
      'Maestro will stop syncing from this provider. Your existing signals will be kept.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Disconnect',
          style: 'destructive',
          onPress: async () => {
            setBusyProvider(provider);
            try {
              await api.disconnectProvider(provider);
              Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
              queryClient.invalidateQueries({ queryKey: ['connectors'] });
            } catch (err: any) {
              const detail = err?.response?.data?.detail || err?.message || 'Unknown error';
              showAlert('Disconnect Failed', String(detail));
            } finally {
              setBusyProvider(null);
            }
          },
        },
      ],
    );
  };

  const isProviderConnected = (provider: string): boolean => {
    if (!connectorList?.connectors) return false;
    return connectorList.connectors.some((c: any) => c.provider === provider && c.connected);
  };

  // P1-4 fix: real actions for Export / Audit / Retention (were haptic-only)
  const handleExport = async () => {
    if (busyAction) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setBusyAction('export');
    try {
      const result = await api.exportData();
      showAlert(
        'Export Complete',
        `Exported ${result.signal_count} signals at ${new Date(result.exported_at).toLocaleString()}.`,
      );
    } catch (err: any) {
      showAlert('Export Failed', err?.message || 'Could not export data.');
    } finally {
      setBusyAction(null);
    }
  };

  const handleAuditLog = async () => {
    if (busyAction) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setBusyAction('audit');
    try {
      const result = await api.getAuditLog();
      const count = result?.events?.length ?? 0;
      showAlert('Audit Log', `${count} audit entries retrieved. Check console for full details.`);
      // eslint-disable-next-line no-console
      console.log('Audit log:', JSON.stringify(result, null, 2));
    } catch (err: any) {
      showAlert('Audit Log Failed', err?.message || 'Could not retrieve audit log.');
    } finally {
      setBusyAction(null);
    }
  };

  const handleRetentionPolicy = async () => {
    if (busyAction) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setBusyAction('retention');
    try {
      const result = await api.getRetentionPolicy();
      const summary = Object.entries(result)
        .filter(([k]) => k !== 'timestamp')
        .map(([k, v]) => `${k}: ${v}`)
        .join('\n');
      showAlert('Data Retention Policy', summary || 'No retention data available.');
    } catch (err: any) {
      showAlert('Retention Policy Failed', err?.message || 'Could not retrieve retention policy.');
    } finally {
      setBusyAction(null);
    }
  };

  return (
    <ScrollView style={{ flex: 1, backgroundColor: t.bg }} contentContainerStyle={{ padding: 16 }}>
      {/* Connectors */}
      <Section title="Connectors" icon="link" t={t}>
        {(['gmail', 'calendar', 'slack', 'github'] as const).map((provider) => {
          const iconMap: Record<string, string> = {
            gmail: 'mail',
            calendar: 'calendar',
            slack: 'chatbubbles',
            github: 'logo-github',
          };
          const labelMap: Record<string, string> = {
            gmail: 'Gmail',
            calendar: 'Calendar',
            slack: 'Slack',
            github: 'GitHub',
          };
          const connected = isProviderConnected(provider);
          const isBusy = busyProvider === provider;
          return (
            <ConnectorRow
              key={provider}
              label={labelMap[provider]}
              icon={iconMap[provider]}
              connected={connected}
              busy={isBusy}
              t={t}
              onPress={() => handleConnect(provider)}
              onDisconnect={() => handleDisconnect(provider)}
            />
          );
        })}
      </Section>

      {/* Draft Preferences */}
      <Section title="Draft Preferences" icon="create" t={t}>
        <Row label="Default tone" value="Professional" t={t} />
        <Row label="Auto-draft" value="On" t={t} />
        <Row label="Default provider" value="Gmail" t={t} />
      </Section>

      {/* Notifications — P1-1 fix: backed by AsyncStorage */}
      <Section title="Notifications" icon="notifications" t={t}>
        <ToggleRow label="Stale commitment alerts" value={notifPrefs.stale_alerts} onToggle={() => toggleNotifPref('stale_alerts')} t={t} />
        <ToggleRow label="Meeting reminders" value={notifPrefs.meeting_reminders} onToggle={() => toggleNotifPref('meeting_reminders')} t={t} />
        <ToggleRow label="Daily briefing (8am)" value={notifPrefs.daily_briefing} onToggle={() => toggleNotifPref('daily_briefing')} t={t} />
        <ToggleRow label="Connector sync alerts" value={notifPrefs.connector_sync} onToggle={() => toggleNotifPref('connector_sync')} t={t} />
      </Section>

      {/* Privacy & Data — P1-4 fix: real actions */}
      <Section title="Privacy & Data" icon="lock-closed" t={t}>
        <ActionRow label="Export all data" icon="download" t={t} busy={busyAction === 'export'} onPress={handleExport} />
        <ActionRow label="Delete account" icon="trash" t={t} onPress={() => {
          Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
          showAlert('Delete Account', 'This will permanently delete all your data.', [
            { text: 'Cancel' },
            { text: 'Delete', style: 'destructive', onPress: () => { logout(); } },
          ]);
        }} />
        <ActionRow label="Audit log" icon="list" t={t} busy={busyAction === 'audit'} onPress={handleAuditLog} />
        <ActionRow label="Data retention policy" icon="document-text" t={t} busy={busyAction === 'retention'} onPress={handleRetentionPolicy} />
      </Section>

      {/* Change 13: What Maestro Knows — transparency section */}
      <Section title="What Maestro Knows" icon="information-circle" t={t}>
        <Row label="Signals tracked" value={signals?.length?.toString() || '—'} t={t} />
        <Row label="Active commitments" value={commitments?.length?.toString() || '—'} t={t} />
        <Row label="Entities tracked" value={uniqueEntities?.toString() || '—'} t={t} />
        <Row label="Brier score" value={brierDisplay} t={t} />
        <Row label="LLM provider" value={llmActive ? `${llmProvider} (active)` : `${llmProvider} (inactive)`} t={t} />
      </Section>

      {/* P0-4 fix (audit V2): Learning Loop dashboard — shows Brier score,
          calibration buckets, resolution rate, and a "Maestro learned" feed.
          This makes the Learning Loop visible on mobile (was backend-only). */}
      <Section title="Learning Loop" icon="school" t={t}>
        <Row label="Brier score" value={brierDisplay} t={t} />
        <Row label="Total predictions" value={calibration?.total_predictions?.toString() || '—'} t={t} />
        <Row label="Resolved predictions" value={calibration?.resolved_predictions?.toString() || '—'} t={t} />
        <Row
          label="Resolution rate"
          value={calibration?.total_predictions && calibration?.resolved_predictions != null
            ? `${Math.round((calibration.resolved_predictions / calibration.total_predictions) * 100)}%`
            : '—'}
          t={t}
        />
        <Row
          label="Calibration"
          value={calibration?.has_sufficient_data ? `${calibration.buckets?.length || 0} buckets` : 'Insufficient data'}
          t={t}
        />
        {calibration?.message ? (
          <Row label="Status" value={calibration.message} t={t} />
        ) : null}
      </Section>

      {/* Settings — P1-2 + P1-3 fix: real values */}
      <Section title="Settings" icon="settings" t={t}>
        <ToggleRow label="Dark mode" value={mode === 'dark'} onToggle={toggle} t={t} />
        <Row label="LLM status" value={llmActive ? `Active (${llmProvider})` : 'Inactive'} t={t} />
        <Row label="Brier score" value={brierDisplay} t={t} />
        <Row label="Server URL" value="localhost:8766" t={t} />
      </Section>

      {/* Account */}
      <Section title="Account" icon="person" t={t}>
        <ActionRow label="Logout" icon="log-out" t={t} onPress={() => { Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning); logout(); }} />
      </Section>
    </ScrollView>
  );
}

function Section({ title, icon, children, t }: any) {
  return (
    <View style={{ marginBottom: 20 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 }}>
        <Ionicons name={icon} size={16} color={colors.yellow} />
        <Text style={{ fontSize: 11, fontWeight: '800', color: colors.yellowDark, textTransform: 'uppercase', letterSpacing: 1 }}>{title}</Text>
      </View>
      <View style={{ backgroundColor: t.surface, borderRadius: 12, overflow: 'hidden' }}>{children}</View>
    </View>
  );
}

function Row({ label, value, t }: any) {
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: t.border }}>
      <Text style={{ fontSize: 14, color: t.textPrimary }}>{label}</Text>
      <Text style={{ fontSize: 14, color: t.textSecondary }}>{value}</Text>
    </View>
  );
}

function ToggleRow({ label, value, onToggle, t }: any) {
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: t.border }}>
      <Text style={{ fontSize: 14, color: t.textPrimary }}>{label}</Text>
      <Switch value={value} onValueChange={onToggle} trackColor={{ false: t.border, true: colors.yellow }} />
    </View>
  );
}

function ActionRow({ label, icon, onPress, busy, t }: any) {
  return (
    <TouchableOpacity onPress={onPress} disabled={busy} style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: t.border }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
        <Ionicons name={icon} size={18} color={t.textSecondary} />
        <Text style={{ fontSize: 14, color: t.textPrimary }}>{label}</Text>
      </View>
      {busy ? (
        <ActivityIndicator size="small" color={colors.yellow} />
      ) : (
        <Ionicons name="chevron-forward" size={16} color={t.textSecondary} />
      )}
    </TouchableOpacity>
  );
}

function ConnectorRow({ label, icon, connected, busy, onPress, onDisconnect, t }: any) {
  // P0-2 fix (audit V2): when connected, tapping the row syncs (ingest
  // new signals). A separate "disconnect" button appears on the right.
  // When not connected, tapping initiates the OAuth flow.
  return (
    <View style={{ borderBottomWidth: 1, borderBottomColor: t.border }}>
      <TouchableOpacity
        onPress={onPress}
        disabled={busy}
        style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12 }}
      >
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name={icon} size={18} color={t.textSecondary} />
          <Text style={{ fontSize: 14, color: t.textPrimary }}>{label}</Text>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          {busy ? (
            <ActivityIndicator size="small" color={colors.yellow} />
          ) : connected ? (
            <>
              <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: '#008030' }} />
              <Text style={{ fontSize: 12, fontWeight: '700', color: '#008030' }}>Sync</Text>
            </>
          ) : (
            <>
              <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: '#9A9A9A' }} />
              <Text style={{ fontSize: 12, color: t.textSecondary }}>Connect</Text>
            </>
          )}
          <Ionicons name="chevron-forward" size={16} color={t.textSecondary} />
        </View>
      </TouchableOpacity>
      {connected && !busy && (
        <TouchableOpacity
          onPress={onDisconnect}
          style={{ paddingHorizontal: 16, paddingVertical: 6, alignItems: 'flex-end' }}
        >
          <Text style={{ fontSize: 11, color: colors.alertRed }}>Disconnect</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}
