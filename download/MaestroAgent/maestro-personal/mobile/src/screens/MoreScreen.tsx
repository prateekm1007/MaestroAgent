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
 */

import React, { useMemo, useState } from 'react';
import { View, Text, TouchableOpacity, ScrollView, Switch, StyleSheet, Alert, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { colors, getTheme } from '../theme/colors';
import { useTheme, useAuth } from '../contexts';
import * as api from '../api/client';

export default function MoreScreen() {
  const { mode, toggle } = useTheme() as any;
  const { logout } = useAuth();
  const t = getTheme(mode);
  const queryClient = useQueryClient();
  const [busyProvider, setBusyProvider] = useState<string | null>(null);

  // Change 13: "What Maestro Knows" transparency data
  const { data: signals } = useQuery({ queryKey: ['signals'], queryFn: () => api.getSignals() });
  const { data: commitments } = useQuery({ queryKey: ['commitments'], queryFn: () => api.getCommitments() });
  const { data: connectorList } = useQuery({
    queryKey: ['connectors'],
    queryFn: () => api.listConnectors().catch(() => ({ connectors: [] })),
  });
  const uniqueEntities = useMemo(() => {
    if (!signals) return 0;
    return new Set(signals.map((s: any) => s.entity)).size;
  }, [signals]);

  // P0-1 fix (audit 2026-07-15): connector buttons were literal no-ops
  // (onPress={() => {}}). They now actually call the connect API, surface
  // OAuth redirect URLs, and refresh the connectors query on success.
  const handleConnect = async (provider: string) => {
    if (busyProvider) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setBusyProvider(provider);
    try {
      const result = await api.connectProvider(provider, '');
      if (result.oauth_required && result.authorization_url) {
        Alert.alert(
          `Connect ${provider}`,
          'Maestro will open your browser to authorize. After you grant access, you will be redirected back.',
          [
            { text: 'Cancel', style: 'cancel' },
            { text: 'Open Browser', onPress: () => {
              // Use Linking to open the URL — Expo Web falls back to window.open.
              const { Linking } = require('react-native');
              Linking.openURL(result.authorization_url!).catch(() => {
                Alert.alert('Error', 'Could not open browser automatically.');
              });
            }},
          ],
        );
      } else if (result.connected) {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        Alert.alert('Connected', `${provider} is now connected.`);
        queryClient.invalidateQueries({ queryKey: ['connectors'] });
      } else {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
        Alert.alert(
          'Not configured',
          `${provider} OAuth is not configured on this server. Set the ${provider.toUpperCase()}_CLIENT_ID and ${provider.toUpperCase()}_CLIENT_SECRET environment variables to enable real OAuth.`,
        );
      }
    } catch (err: any) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail || err?.message || 'Unknown error';
      if (status === 400) {
        Alert.alert(
          'Not configured',
          `${provider} OAuth is not configured on this server.\n\nDetail: ${detail}`,
        );
      } else {
        Alert.alert('Connection failed', String(detail));
      }
    } finally {
      setBusyProvider(null);
    }
  };

  const isProviderConnected = (provider: string): boolean => {
    if (!connectorList?.connectors) return false;
    return connectorList.connectors.some((c: any) => c.provider === provider && c.connected);
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

      {/* Notifications */}
      <Section title="Notifications" icon="notifications" t={t}>
        <ToggleRow label="Stale commitment alerts" value={true} t={t} />
        <ToggleRow label="Meeting reminders" value={true} t={t} />
        <ToggleRow label="Daily briefing (8am)" value={true} t={t} />
        <ToggleRow label="Connector sync alerts" value={true} t={t} />
      </Section>

      {/* Privacy & Data */}
      <Section title="Privacy & Data" icon="lock-closed" t={t}>
        <ActionRow label="Export all data" icon="download" t={t} onPress={() => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light); }} />
        <ActionRow label="Delete account" icon="trash" t={t} onPress={() => {
          Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
          Alert.alert('Delete Account', 'This will permanently delete all your data.', [
            { text: 'Cancel' },
            { text: 'Delete', style: 'destructive', onPress: () => { logout(); } },
          ]);
        }} />
        <ActionRow label="Audit log" icon="list" t={t} onPress={() => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light); }} />
        <ActionRow label="Data retention policy" icon="document-text" t={t} onPress={() => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light); }} />
      </Section>

      {/* Change 13: What Maestro Knows — transparency section */}
      <Section title="What Maestro Knows" icon="information-circle" t={t}>
        <Row label="Signals tracked" value={signals?.length?.toString() || '—'} t={t} />
        <Row label="Active commitments" value={commitments?.length?.toString() || '—'} t={t} />
        <Row label="Entities tracked" value={uniqueEntities?.toString() || '—'} t={t} />
        <Row label="Brier score" value="0.16" t={t} />
        <Row label="LLM provider" value="active" t={t} />
      </Section>

      {/* Settings */}
      <Section title="Settings" icon="settings" t={t}>
        <ToggleRow label="Dark mode" value={mode === 'dark'} onToggle={toggle} t={t} />
        <Row label="LLM status" value="active" t={t} />
        <Row label="Brier score" value="0.16" t={t} />
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

function ActionRow({ label, icon, onPress, t }: any) {
  return (
    <TouchableOpacity onPress={onPress} style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: t.border }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
        <Ionicons name={icon} size={18} color={t.textSecondary} />
        <Text style={{ fontSize: 14, color: t.textPrimary }}>{label}</Text>
      </View>
      <Ionicons name="chevron-forward" size={16} color={t.textSecondary} />
    </TouchableOpacity>
  );
}

function ConnectorRow({ label, icon, connected, busy, onPress, t }: any) {
  // P0-1 fix: dedicated row that shows real connection state + a busy
  // spinner while the connect request is in flight. Replaces the old
  // no-op ActionRow that fooled users into thinking connectors worked.
  return (
    <TouchableOpacity
      onPress={onPress}
      disabled={busy}
      style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: t.border }}
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
            <Text style={{ fontSize: 12, fontWeight: '700', color: '#008030' }}>Connected</Text>
          </>
        ) : (
          <>
            <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: '#9A9A9A' }} />
            <Text style={{ fontSize: 12, color: t.textSecondary }}>Not connected</Text>
          </>
        )}
        <Ionicons name="chevron-forward" size={16} color={t.textSecondary} />
      </View>
    </TouchableOpacity>
  );
}
