/**
 * CommitmentsScreen — extracted from the original App.tsx, unchanged in logic.
 *
 * Renders THE ONE (top commitment) followed by the active commitments list.
 * Each row offers Complete / Dismiss actions, which hit the signal-correction
 * endpoint after a confirm prompt.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, ScrollView, ActivityIndicator, TouchableOpacity, Alert, SafeAreaView,
} from 'react-native';

import * as api from '../api/client';
import { colors, getTheme, spacing, typography } from '../theme/colors';
import { useAuth, useTheme } from '../contexts';
import { Card, Badge, TopBar } from '../components';
import { styles } from '../styles';

export default function CommitmentsScreen() {
  const { mode } = useTheme();
  const t = getTheme(mode);
  const { token } = useAuth();
  const [theOne, setTheOne] = useState<api.TheOneResult | null>(null);
  const [commitments, setCommitments] = useState<api.Commitment[]>([]);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    if (!token) return;
    try {
      const [one, list] = await Promise.all([
        api.getTheOne().catch(() => null),
        api.getCommitments().catch(() => []),
      ]);
      setTheOne(one);
      setCommitments(list);
    } catch (e) { /* ignore */ }
    setLoading(false);
  }, [token]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleCorrect = async (signalId: string, action: 'complete' | 'dismiss' | 'cancel') => {
    if (!token || !signalId) return;
    Alert.alert(
      `${action.charAt(0).toUpperCase() + action.slice(1)} this commitment?`,
      undefined,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Confirm',
          onPress: async () => {
            await api.correctSignal(signalId, action);
            loadData();
          },
        },
      ]
    );
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: t.bg }}>
      <TopBar title="Commitments" />
      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: spacing.xl }}>
        {loading ? (
          <ActivityIndicator color={colors.yellow} size="large" style={{ marginVertical: 40 }} />
        ) : (
          <>
            {/* THE ONE */}
            {theOne?.primary && (
              <>
                <Text style={[typography.label, { color: colors.yellow, marginBottom: spacing.md }]}>⭐ THE ONE</Text>
                <Card accent="yellow" style={{ marginBottom: spacing.xl }}>
                  <Text style={{ fontSize: 20, fontWeight: 'bold', color: t.textPrimary }}>{theOne.primary.entity}</Text>
                  <Text style={{ fontSize: 16, color: t.textSecondary, fontStyle: 'italic', marginTop: spacing.xs }}>
                    "{theOne.primary.text}"
                  </Text>
                  {theOne.primary.deadline ? <Badge text={`📅 ${theOne.primary.deadline}`} color="yellow" /> : null}
                  {theOne.primary.is_at_risk ? <Badge text="🔥 At Risk" color="red" /> : null}
                  {(theOne.primary.days_stale ?? 0) > 0 ? <Text style={{ fontSize: 13, color: t.textSecondary, marginTop: spacing.xs }}>{theOne.primary.days_stale}d stale</Text> : null}
                  {theOne.why_primary ? <Text style={{ fontSize: 14, color: t.textSecondary, marginTop: spacing.sm }}>{theOne.why_primary}</Text> : null}
                  <View style={{ flexDirection: 'row', gap: spacing.md, marginTop: spacing.lg }}>
                    <TouchableOpacity style={[styles.smallBtn, { backgroundColor: colors.successGreen }]} onPress={() => handleCorrect(theOne.primary?.signal_id ?? '', 'complete')}>
                      <Text style={{ color: colors.white, fontSize: 13, fontWeight: '600' }}>✓ Complete</Text>
                    </TouchableOpacity>
                    <TouchableOpacity style={[styles.smallBtn, { backgroundColor: t.border }]} onPress={() => handleCorrect(theOne.primary?.signal_id ?? '', 'dismiss')}>
                      <Text style={{ color: t.textSecondary, fontSize: 13, fontWeight: '600' }}>✕ Dismiss</Text>
                    </TouchableOpacity>
                  </View>
                </Card>
              </>
            )}

            {/* ACTIVE LIST */}
            <Text style={[typography.label, { color: t.textSecondary, marginBottom: spacing.md }]}>ACTIVE COMMITMENTS</Text>
            {commitments.length === 0 ? (
              <Text style={{ color: t.textSecondary, fontSize: 14, textAlign: 'center', marginVertical: 20 }}>No active commitments</Text>
            ) : (
              commitments.map((c, i) => (
                <Card key={i} style={{ marginBottom: spacing.md }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                    <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: c.is_at_risk ? colors.alertRed : (c.days_stale ?? 0) > 2 ? colors.yellow : colors.successGreen, marginRight: spacing.md }} />
                    <Text style={{ fontSize: 15, fontWeight: 'bold', color: t.textPrimary, flex: 1 }}>{c.entity}</Text>
                    {c.deadline ? <Badge text={c.deadline} color="yellow" /> : null}
                  </View>
                  <Text style={{ fontSize: 13, color: t.textSecondary, marginTop: spacing.xs }} numberOfLines={2}>"{c.text}"</Text>
                  <View style={{ flexDirection: 'row', gap: spacing.md, marginTop: spacing.sm }}>
                    <TouchableOpacity onPress={() => handleCorrect(c.signal_id, 'complete')}>
                      <Text style={{ color: colors.successGreen, fontSize: 12, fontWeight: '600' }}>✓ Complete</Text>
                    </TouchableOpacity>
                    <TouchableOpacity onPress={() => handleCorrect(c.signal_id, 'dismiss')}>
                      <Text style={{ color: t.textSecondary, fontSize: 12, fontWeight: '600' }}>✕ Dismiss</Text>
                    </TouchableOpacity>
                  </View>
                </Card>
              ))
            )}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}
