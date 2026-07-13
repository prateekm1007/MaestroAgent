/**
 * DashboardScreen — extracted from the original App.tsx, unchanged in logic.
 *
 * Shows THE MOMENT (single most important commitment), WHAT CHANGED strip,
 * the daily briefing, and a quick-ask shortcut that navigates to Ask tab.
 */

import React, { useState, useEffect } from 'react';
import {
  View, Text, ScrollView, ActivityIndicator, TouchableOpacity, SafeAreaView,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';

import * as api from '../api/client';
import { colors, getTheme, spacing, typography } from '../theme/colors';
import { useAuth, useTheme } from '../contexts';
import { Card, Badge, TopBar } from '../components';
import { styles } from '../styles';

export default function DashboardScreen() {
  const { mode } = useTheme();
  const t = getTheme(mode);
  const { token } = useAuth();
  const nav = useNavigation<any>();
  const [moment, setMoment] = useState<api.TheMoment | null>(null);
  const [shifts, setShifts] = useState<api.WhatChangedShift[]>([]);
  const [briefing, setBriefing] = useState<api.Briefing | null>(null);
  const [loading, setLoading] = useState(true);
  const [askQuery, setAskQuery] = useState('');

  useEffect(() => {
    if (!token) return;
    Promise.all([
      api.getTheMoment().catch(() => null),
      api.getWhatChangedShifts().catch(() => null),
      api.getBriefing().catch(() => null),
    ]).then(([m, s, b]) => {
      setMoment(m);
      setShifts(s?.secondary || []);
      setBriefing(b);
      setLoading(false);
    });
  }, [token]);

  const handleCorrect = async (signalId: string, action: 'complete' | 'dismiss') => {
    if (!token || !signalId) return;
    // Haptic feedback
    if (action === 'complete') {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    } else {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    }
    try {
      await api.correctSignal(signalId, action);
      const m = await api.getTheMoment();
      setMoment(m);
    } catch (e) { /* ignore */ }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: t.bg }}>
      <TopBar title="Dashboard" />
      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: spacing.xl }}>
        {/* THE MOMENT */}
        <Text style={[typography.label, { color: colors.yellow, marginBottom: spacing.md }]}>⚡ THE MOMENT</Text>
        {loading ? (
          <ActivityIndicator color={colors.yellow} size="large" style={{ marginVertical: 40 }} />
        ) : moment?.has_moment && moment.commitment ? (
          <Card accent="yellow" style={{ marginBottom: spacing.xl }}>
            <Text style={{ fontSize: 20, fontWeight: 'bold', color: t.textPrimary }}>{moment.commitment.entity}</Text>
            <Text style={{ fontSize: 16, color: t.textSecondary, fontStyle: 'italic', marginTop: spacing.xs }}>
              "{moment.commitment.text}"
            </Text>
            {moment.why_this_one ? (
              <Text style={{ fontSize: 14, color: t.textSecondary, marginTop: spacing.md }}>{moment.why_this_one}</Text>
            ) : null}
            <View style={{ flexDirection: 'row', marginTop: spacing.md, gap: spacing.sm }}>
              {moment.commitment.metadata?.deadline ? <Badge text={`📅 ${moment.commitment.metadata.deadline}`} color="yellow" /> : null}
              {moment.why_this_one?.includes('stale') ? <Badge text="🔥 At Risk" color="red" /> : null}
            </View>
            <View style={{ flexDirection: 'row', justifyContent: 'center', marginTop: spacing.xl, gap: spacing.xl }}>
              <TouchableOpacity
                style={[styles.actionButton, { backgroundColor: colors.successGreen }]}
                onPress={() => handleCorrect(moment.commitment!.signal_id, 'complete')}
              >
                <Ionicons name="checkmark" size={24} color={colors.white} />
                <Text style={styles.actionLabel}>Done</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.actionButton, { backgroundColor: t.border }]}
                onPress={() => handleCorrect(moment.commitment!.signal_id, 'dismiss')}
              >
                <Ionicons name="close" size={24} color={t.textSecondary} />
                <Text style={[styles.actionLabel, { color: t.textSecondary }]}>Skip</Text>
              </TouchableOpacity>
            </View>
          </Card>
        ) : (
          <Card style={{ marginBottom: spacing.xl, padding: spacing.xxxl, alignItems: 'center' }}>
            <Text style={{ fontSize: 48 }}>🌙</Text>
            <Text style={{ fontSize: 18, color: t.textSecondary, marginTop: spacing.md, textAlign: 'center' }}>
              Nothing needs your attention right now.
            </Text>
            <Text style={{ fontSize: 14, color: t.textSecondary, marginTop: spacing.xs, textAlign: 'center' }}>
              Maestro is watching quietly.
            </Text>
          </Card>
        )}

        {/* WHAT CHANGED */}
        {shifts.length > 0 && (
          <>
            <Text style={[typography.label, { color: t.textSecondary, marginBottom: spacing.md }]}>WHAT CHANGED</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: spacing.xl }}>
              {shifts.map((s, i) => (
                <Card key={i} style={{ width: 160, marginRight: spacing.md }}>
                  <Text style={{ fontSize: 14, fontWeight: 'bold', color: t.textPrimary }}>{s.entity}</Text>
                  <Text style={{ fontSize: 13, color: t.textSecondary, marginTop: 2 }} numberOfLines={1}>{s.description}</Text>
                  <Text style={{ fontSize: 11, color: t.textSecondary, marginTop: spacing.xs }}>{s.timestamp?.slice(0, 10)}</Text>
                </Card>
              ))}
            </ScrollView>
          </>
        )}

        {/* BRIEFING */}
        {briefing && (
          <Card style={{ marginBottom: spacing.xl }}>
            <Text style={{ fontSize: 16, color: t.textPrimary }}>{briefing.greeting}</Text>
            {briefing.ask_prompt ? (
              <Text style={{ fontSize: 14, color: t.textSecondary, marginTop: spacing.sm }}>{briefing.ask_prompt}</Text>
            ) : null}
          </Card>
        )}

        {/* QUICK ASK */}
        <TouchableOpacity
          style={[styles.quickAsk, { backgroundColor: t.surface, borderColor: t.border }]}
          onPress={() => nav.navigate('Ask')}
        >
          <Ionicons name="search" size={18} color={t.textSecondary} />
          <Text style={{ color: t.textSecondary, fontSize: 14, marginLeft: spacing.sm, flex: 1 }}>Ask Maestro anything...</Text>
          <Ionicons name="arrow-forward" size={18} color={colors.yellow} />
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}
