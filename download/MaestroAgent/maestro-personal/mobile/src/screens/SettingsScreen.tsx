/**
 * SettingsScreen — extracted from the original App.tsx.
 *
 * Phase 2: data fetching now goes through react-query hooks
 * (usePrivacyMode / useCalibration / useAuditLog / useMetrics) instead
 * of a manual useEffect+useState + Promise.all. The Export and
 * Delete-account actions use the `useExportData` / `useDeleteAccount`
 * mutation hooks. Each section renders independently — failures are
 * silent (the original swallowed errors via `.catch(() => null)` and
 * just hid the section).
 *
 * UI/logic is otherwise unchanged.
 */

import React, { useState } from 'react';
import {
  View, Text, TouchableOpacity, ScrollView, Alert, Share, SafeAreaView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import * as api from '../api/client';
import {
  usePrivacyMode, useCalibration, useAuditLog, useMetrics,
  useExportData, useDeleteAccount,
} from '../api/hooks';
import { colors, getTheme, spacing, typography } from '../theme/colors';
import { useAuth, useTheme } from '../contexts';
import { Card, LLMDot, TopBar } from '../components';
import { styles } from '../styles';

export default function SettingsScreen() {
  const { mode, toggle } = useTheme();
  const t = getTheme(mode);
  const { token, llmStatus, logout } = useAuth();
  const [confirmText, setConfirmText] = useState('');

  // ── react-query hooks (replace manual useEffect + Promise.all) ─────
  const privacyQ = usePrivacyMode();
  const calibrationQ = useCalibration();
  const auditQ = useAuditLog();
  const metricsQ = useMetrics();

  const privacy = privacyQ.data ?? null;
  const calibration = calibrationQ.data ?? null;
  const audit: api.AuditLogEntry[] = auditQ.data?.events ?? [];
  const metrics = metricsQ.data ?? null;

  // ── Mutations (Export / Delete) ────────────────────────────────────
  const exportMut = useExportData();
  const deleteMut = useDeleteAccount();

  const handleExport = async () => {
    if (!token) return;
    exportMut.mutate(undefined, {
      onSuccess: async (data) => {
        try {
          await Share.share({ message: JSON.stringify(data, null, 2) });
        } catch (e) { /* share cancelled — non-fatal */ }
      },
      onError: () => Alert.alert('Error', 'Export failed'),
    });
  };

  const handleDelete = () => {
    // Phase 1: require typed DELETE confirmation (not just a button tap)
    Alert.prompt(
      'Delete Account',
      'This will permanently delete ALL your data (signals, commitments, audit log). This cannot be undone.\n\nType DELETE to confirm:',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Delete Forever', style: 'destructive', onPress: (text) => {
          if (text !== 'DELETE') {
            Alert.alert('Cancelled', 'You must type DELETE exactly to confirm.');
            return;
          }
          if (!token) return;
          deleteMut.mutate(undefined, {
            onSettled: () => {
              // `useDeleteAccount` clears the query cache on success.
              // Always logout afterwards (matches original behavior).
              logout();
            },
          });
        }},
      ],
      'plain-text',
      '',
      'default'
    );
  };

  // Silence unused — kept for parity with the original confirm field.
  void confirmText;
  void setConfirmText;

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

        {/* LLM Status (sourced from AuthContext, unchanged) */}
        <Card style={{ marginBottom: spacing.md }}>
          <Text style={[typography.label, { color: t.textSecondary, marginBottom: spacing.sm }]}>LLM STATUS</Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <LLMDot size={10} />
            <Text style={{ color: t.textPrimary, fontSize: 15 }}>{llmStatus?.provider || 'none'}</Text>
          </View>
          <Text style={{ color: t.textSecondary, fontSize: 13, marginTop: spacing.xs }}>{llmStatus?.mode || 'Rule-based'}</Text>
        </Card>

        {/* Privacy — silent on error (matches original) */}
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

        {/* Data actions */}
        <View style={{ marginTop: spacing.xl, gap: spacing.md }}>
          <TouchableOpacity
            style={[styles.loginButton, { backgroundColor: t.border, opacity: exportMut.isPending ? 0.5 : 1 }]}
            onPress={handleExport}
            disabled={exportMut.isPending}
          >
            <Text style={{ color: t.textSecondary, fontWeight: 'bold' }}>{exportMut.isPending ? 'Exporting…' : 'Export All Data'}</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.loginButton, { backgroundColor: colors.alertRed + '22', opacity: deleteMut.isPending ? 0.5 : 1 }]}
            onPress={handleDelete}
            disabled={deleteMut.isPending}
          >
            <Text style={{ color: colors.alertRed, fontWeight: 'bold' }}>{deleteMut.isPending ? 'Deleting…' : 'Delete Account'}</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
