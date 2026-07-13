/**
 * SettingsScreen — extracted from the original App.tsx, unchanged in logic.
 *
 * Theme toggle, LLM status card, privacy mode, calibration (Brier score),
 * engagement metrics, audit log tail, and Export / Delete-account actions.
 * Delete requires typing DELETE exactly (Phase 1 hardening).
 */

import React, { useState, useEffect } from 'react';
import {
  View, Text, TouchableOpacity, ScrollView, Alert, Share, SafeAreaView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import * as api from '../api/client';
import { colors, getTheme, spacing, typography } from '../theme/colors';
import { useAuth, useTheme } from '../contexts';
import { Card, LLMDot, TopBar } from '../components';
import { styles } from '../styles';

export default function SettingsScreen() {
  const { mode, toggle } = useTheme();
  const t = getTheme(mode);
  const { token, llmStatus, logout } = useAuth();
  const [privacy, setPrivacy] = useState<api.PrivacyMode | null>(null);
  const [calibration, setCalibration] = useState<api.Calibration | null>(null);
  const [audit, setAudit] = useState<api.AuditLogEntry[]>([]);
  const [metrics, setMetrics] = useState<api.Metrics | null>(null);

  useEffect(() => {
    if (!token) return;
    Promise.all([
      api.getPrivacyMode().catch(() => null),
      api.getCalibration().catch(() => null),
      api.getAuditLog().catch(() => null),
      api.getMetrics().catch(() => null),
    ]).then(([p, c, a, m]) => {
      setPrivacy(p); setCalibration(c); setAudit(a?.events || []); setMetrics(m);
    });
  }, [token]);

  const handleExport = async () => {
    if (!token) return;
    try {
      const data = await api.exportData();
      await Share.share({ message: JSON.stringify(data, null, 2) });
    } catch (e) { Alert.alert('Error', 'Export failed'); }
  };

  const handleDelete = () => {
    // Phase 1: require typed DELETE confirmation (not just a button tap)
    Alert.prompt(
      'Delete Account',
      'This will permanently delete ALL your data (signals, commitments, audit log). This cannot be undone.\n\nType DELETE to confirm:',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Delete Forever', style: 'destructive', onPress: async (text) => {
          if (text !== 'DELETE') {
            Alert.alert('Cancelled', 'You must type DELETE exactly to confirm.');
            return;
          }
          if (!token) return;
          try {
            await api.deleteAccount();
          } catch (e) { /* non-fatal — still clear local */ }
          logout();
        }},
      ],
      'plain-text',
      '',
      'default'
    );
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: t.bg }}>
      <TopBar title="Settings" />
      <ScrollView contentContainerStyle={{ padding: spacing.xl, paddingBottom: 40 }}>
        {/* Theme toggle */}
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: spacing.xl }}>
          <Text style={{ color: t.textPrimary, fontSize: 15 }}>Dark Mode</Text>
          <TouchableOpacity onPress={toggle} style={{ width: 50, height: 28, borderRadius: 14, backgroundColor: mode === 'dark' ? colors.yellow : t.border, justifyContent: 'center', paddingHorizontal: 3 }}>
            <View style={{ width: 22, height: 22, borderRadius: 11, backgroundColor: colors.white, alignSelf: mode === 'dark' ? 'flex-end' : 'flex-start' }} />
          </TouchableOpacity>
        </View>

        {/* LLM Status */}
        <Card style={{ marginBottom: spacing.md }}>
          <Text style={[typography.label, { color: t.textSecondary, marginBottom: spacing.sm }]}>LLM STATUS</Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <LLMDot size={10} />
            <Text style={{ color: t.textPrimary, fontSize: 15 }}>{llmStatus?.provider || 'none'}</Text>
          </View>
          <Text style={{ color: t.textSecondary, fontSize: 13, marginTop: spacing.xs }}>{llmStatus?.mode || 'Rule-based'}</Text>
        </Card>

        {/* Privacy */}
        {privacy && (
          <Card style={{ marginBottom: spacing.md }}>
            <Text style={[typography.label, { color: t.textSecondary, marginBottom: spacing.sm }]}>PRIVACY MODE</Text>
            <Text style={{ color: t.textPrimary, fontSize: 15 }}>{privacy.mode}</Text>
            <Text style={{ color: t.textSecondary, fontSize: 13, marginTop: spacing.xs }}>{privacy.description}</Text>
          </Card>
        )}

        {/* Calibration */}
        {calibration && (
          <Card style={{ marginBottom: spacing.md }}>
            <Text style={[typography.label, { color: t.textSecondary, marginBottom: spacing.sm }]}>CALIBRATION</Text>
            <Text style={{ color: t.textPrimary, fontSize: 28, fontWeight: 'bold' }}>
              {calibration.brier_score !== null ? calibration.brier_score.toFixed(4) : '—'}
            </Text>
            <Text style={{ color: t.textSecondary, fontSize: 13, marginTop: spacing.xs }}>{calibration.message}</Text>
          </Card>
        )}

        {/* Metrics */}
        {metrics && (
          <Card style={{ marginBottom: spacing.md }}>
            <Text style={[typography.label, { color: t.textSecondary, marginBottom: spacing.sm }]}>METRICS</Text>
            <View style={{ flexDirection: 'row', gap: spacing.xl }}>
              <View>
                <Text style={{ color: t.textPrimary, fontSize: 20, fontWeight: 'bold' }}>{metrics.commitment_completion_rate !== null ? `${Math.round(metrics.commitment_completion_rate * 100)}%` : '—'}</Text>
                <Text style={{ color: t.textSecondary, fontSize: 11 }}>Completion</Text>
              </View>
              <View>
                <Text style={{ color: t.textPrimary, fontSize: 20, fontWeight: 'bold' }}>{metrics.engagement_signals}</Text>
                <Text style={{ color: t.textSecondary, fontSize: 11 }}>Signals</Text>
              </View>
            </View>
          </Card>
        )}

        {/* Audit Log */}
        <Text style={[typography.label, { color: t.textSecondary, marginBottom: spacing.sm, marginTop: spacing.lg }]}>AUDIT LOG</Text>
        {audit.slice(0, 20).map((e, i) => (
          <View key={i} style={{ flexDirection: 'row', paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: t.border }}>
            <Text style={{ color: t.textSecondary, fontSize: 11, width: 60 }}>{e.timestamp?.slice(11, 16)}</Text>
            <Text style={{ color: e.action === 'read' ? '#4A9' : e.action === 'write' ? colors.successGreen : e.action === 'correct' ? colors.yellow : colors.alertRed, fontSize: 11, fontWeight: '600', width: 50 }}>{e.action}</Text>
            <Text style={{ color: t.textPrimary, fontSize: 11, flex: 1 }}>{e.endpoint}</Text>
          </View>
        ))}

        {/* Data */}
        <View style={{ marginTop: spacing.xl, gap: spacing.md }}>
          <TouchableOpacity style={[styles.loginButton, { backgroundColor: t.border }]} onPress={handleExport}>
            <Text style={{ color: t.textSecondary, fontWeight: 'bold' }}>Export All Data</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[styles.loginButton, { backgroundColor: colors.alertRed + '22' }]} onPress={handleDelete}>
            <Text style={{ color: colors.alertRed, fontWeight: 'bold' }}>Delete Account</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
