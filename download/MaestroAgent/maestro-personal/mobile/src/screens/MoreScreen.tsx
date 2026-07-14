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

import React from 'react';
import { View, Text, TouchableOpacity, ScrollView, Switch, StyleSheet, Alert } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, getTheme } from '../theme/colors';
import { useTheme, useAuth } from '../contexts';

export default function MoreScreen() {
  const { mode, toggle } = useTheme() as any;
  const { logout } = useAuth();
  const t = getTheme(mode);

  return (
    <ScrollView style={{ flex: 1, backgroundColor: t.bg }} contentContainerStyle={{ padding: 16 }}>
      {/* Connectors */}
      <Section title="Connectors" icon="link" t={t}>
        <ActionRow label="Gmail" icon="mail" t={t} onPress={() => {}} />
        <ActionRow label="Calendar" icon="calendar" t={t} onPress={() => {}} />
        <ActionRow label="Slack" icon="chatbubbles" t={t} onPress={() => {}} />
        <ActionRow label="GitHub" icon="logo-github" t={t} onPress={() => {}} />
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
        <ActionRow label="Export all data" icon="download" t={t} onPress={() => {}} />
        <ActionRow label="Delete account" icon="trash" t={t} onPress={() =>
          Alert.alert('Delete Account', 'This will permanently delete all your data.', [
            { text: 'Cancel' },
            { text: 'Delete', style: 'destructive', onPress: () => { logout(); } },
          ])
        } />
        <ActionRow label="Audit log" icon="list" t={t} onPress={() => {}} />
        <ActionRow label="Data retention policy" icon="document-text" t={t} onPress={() => {}} />
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
        <ActionRow label="Logout" icon="log-out" t={t} onPress={logout} />
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
