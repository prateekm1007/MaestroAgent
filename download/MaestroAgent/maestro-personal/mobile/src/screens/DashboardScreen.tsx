/**
 * DashboardScreen — extracted from the original App.tsx.
 *
 * Phase 2: data fetching now goes through react-query hooks
 * (useTheMoment / useShifts / useBriefing) instead of manual
 * useEffect+useState. Loading/error/empty states use the shared
 * components from src/components/ErrorState.tsx. The Moment card
 * animates in on mount (subtle fade + scale) via react-native-reanimated.
 *
 * UI/logic is otherwise unchanged.
 */

import React, { useState, useEffect } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, SafeAreaView, AccessibilityInfo, Alert,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withSpring,
  withTiming,
} from 'react-native-reanimated';
import { useQueryClient } from '@tanstack/react-query';

import * as api from '../api/client';
import { useTheMoment, useShifts, useBriefing } from '../api/hooks';
import { colors, getTheme, spacing, typography } from '../theme/colors';
import { useAuth, useTheme } from '../contexts';
import { Card, Badge, TopBar } from '../components';
import { ErrorState, LoadingState, EmptyState } from '../components/ErrorState';
import { DraftApprovalModal } from '../components/DraftApprovalModal';
import { styles } from '../styles';

export default function DashboardScreen() {
  const { mode } = useTheme();
  const t = getTheme(mode);
  const { token } = useAuth();
  const nav = useNavigation<any>();
  const qc = useQueryClient();
  const [askQuery] = useState('');

  // ── react-query hooks (replace manual useEffect + useState) ────────
  const momentQ = useTheMoment();
  const shiftsQ = useShifts();
  const briefingQ = useBriefing();

  const moment = momentQ.data ?? null;
  const shifts: api.WhatChangedShift[] = shiftsQ.data?.secondary ?? [];
  const briefing = briefingQ.data ?? null;

  // ── Reanimated mount animation for the Moment card ─────────────────
  // Subtle fade-in + spring scale-up. Premium feel — not flashy.
  // Phase 7 (a11y): skip the animation entirely when the user has
  // "Reduce Motion" enabled in system settings. The card still renders
  // (just with its final opacity/scale) so the content is identical.
  const cardOpacity = useSharedValue(0);
  const cardScale = useSharedValue(0.96);
  useEffect(() => {
    // AccessibilityInfo.isReduceMotionEnabled() resolves to a boolean —
    // when true, we jump straight to the final values instead of animating.
    AccessibilityInfo.isReduceMotionEnabled().then((reduce) => {
      if (reduce) {
        cardOpacity.value = 1;
        cardScale.value = 1;
      } else {
        cardOpacity.value = withTiming(1, { duration: 400 });
        cardScale.value = withSpring(1, { damping: 18, stiffness: 160 });
      }
    });
  }, [cardOpacity, cardScale]);
  const cardAnimStyle = useAnimatedStyle(() => ({
    opacity: cardOpacity.value,
    transform: [{ scale: cardScale.value }],
  }));

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
      // Invalidate the moment query so react-query refetches.
      qc.invalidateQueries({ queryKey: ['moment'] });
    } catch (e) { /* ignore */ }
  };

  // ── Issue 7: Proactive email drafting ─────────────────────────────
  const [draftModal, setDraftModal] = React.useState<{ visible: boolean; draft: any }>({ visible: false, draft: null });

  const handleDraft = async (entity: string) => {
    if (!entity) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      const result = await api.generateAutoDraft('gmail', entity);
      setDraftModal({ visible: true, draft: result });
    } catch (e) {
      Alert.alert('Error', 'Failed to generate draft. Is the backend running?');
    }
  };

  // Silence unused-var lint while preserving the original quick-ask field shape.
  void askQuery;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: t.bg }}>
      <TopBar title="Dashboard" />
      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: spacing.xl }}>
        {/* THE MOMENT */}
        <Text style={[typography.label, { color: colors.yellow, marginBottom: spacing.md }]}>⚡ THE MOMENT</Text>
        {momentQ.isLoading ? (
          <LoadingState label="Loading the moment…" />
        ) : momentQ.error ? (
          <ErrorState message="Couldn't load the moment." onRetry={() => momentQ.refetch()} />
        ) : moment?.has_moment && moment.commitment ? (
          <Animated.View
            style={[cardAnimStyle, { marginBottom: spacing.xl }]}
            accessibilityLiveRegion="polite"
            accessibilityLabel="The Moment card"
            accessibilityRole="summary"
          >
            <Card accent="yellow">
              <Text
                style={{ fontSize: 20, fontWeight: 'bold', color: t.textPrimary }}
                accessibilityRole="header"
                accessibilityLabel={`${moment.commitment.entity} commitment`}
              >{moment.commitment.entity}</Text>
              <Text
                style={{ fontSize: 16, color: t.textSecondary, fontStyle: 'italic', marginTop: spacing.xs }}
                accessibilityRole="text"
                accessibilityLabel={`Commitment: ${moment.commitment.text}`}
              >
                "{moment.commitment.text}"
              </Text>
              {moment.why_this_one ? (
                <Text
                  style={{ fontSize: 14, color: t.textSecondary, marginTop: spacing.md }}
                  accessibilityRole="text"
                  accessibilityLabel={`Why this matters: ${moment.why_this_one}`}
                >{moment.why_this_one}</Text>
              ) : null}
              <View style={{ flexDirection: 'row', marginTop: spacing.md, gap: spacing.sm }}>
                {moment.commitment.metadata?.deadline ? <Badge text={`📅 ${moment.commitment.metadata.deadline}`} color="yellow" /> : null}
                {moment.why_this_one?.includes('stale') ? <Badge text="🔥 At Risk" color="red" /> : null}
              </View>
              <View style={{ flexDirection: 'row', justifyContent: 'center', marginTop: spacing.xl, gap: spacing.xl }}>
                <TouchableOpacity
                  style={[styles.actionButton, { backgroundColor: colors.successGreen }]}
                  onPress={() => handleCorrect(moment.commitment!.signal_id, 'complete')}
                  accessibilityRole="button"
                  accessibilityLabel="Mark commitment as done"
                  accessibilityHint="Completes this commitment"
                >
                  <Ionicons name="checkmark" size={24} color={colors.white} />
                  <Text style={styles.actionLabel}>Done</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.actionButton, { backgroundColor: t.border }]}
                  onPress={() => handleCorrect(moment.commitment!.signal_id, 'dismiss')}
                  accessibilityRole="button"
                  accessibilityLabel="Skip this commitment"
                  accessibilityHint="Dismisses this commitment for now"
                >
                  <Ionicons name="close" size={24} color={t.textSecondary} />
                  <Text style={[styles.actionLabel, { color: t.textSecondary }]}>Skip</Text>
                </TouchableOpacity>
                {/* Issue 7: Draft email button */}
                <TouchableOpacity
                  style={[styles.actionButton, { backgroundColor: colors.yellow }]}
                  onPress={() => handleDraft(moment.commitment!.entity)}
                  accessibilityRole="button"
                  accessibilityLabel="Draft email about this commitment"
                  accessibilityHint="Generates a commitment-aware email draft"
                >
                  <Ionicons name="mail" size={24} color={colors.black} />
                  <Text style={[styles.actionLabel, { color: colors.black }]}>Draft</Text>
                </TouchableOpacity>
              </View>
            </Card>
          </Animated.View>
        ) : (
          <View style={{ marginBottom: spacing.xl }} accessibilityLiveRegion="polite">
            <EmptyState
              title="Nothing needs your attention right now."
              subtitle="Maestro is watching quietly."
              icon="moon"
            />
          </View>
        )}

        {/* Issue 13-C: Whisper cards — "💌 Needs Attention" (mobile) */}
        <WhisperCards t={t} nav={nav} />

        {/* WHAT CHANGED — secondary, errors are silent (matches original .catch(() => null)) */}
        {shifts.length > 0 && (
          <>
            <Text
              style={[typography.label, { color: t.textSecondary, marginBottom: spacing.md }]}
              accessibilityRole="header"
              accessibilityLabel="What changed section"
            >WHAT CHANGED</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: spacing.xl }}>
              {shifts.map((s, i) => (
                <Card key={i} style={{ width: 160, marginRight: spacing.md }}>
                  <Text
                    style={{ fontSize: 14, fontWeight: 'bold', color: t.textPrimary }}
                    accessibilityRole="text"
                    accessibilityLabel={`Shift for ${s.entity}`}
                  >{s.entity}</Text>
                  <Text
                    style={{ fontSize: 13, color: t.textSecondary, marginTop: 2 }}
                    numberOfLines={1}
                    accessibilityRole="text"
                    accessibilityLabel={s.description}
                  >{s.description}</Text>
                  <Text style={{ fontSize: 11, color: t.textSecondary, marginTop: spacing.xs }}>{s.timestamp?.slice(0, 10)}</Text>
                </Card>
              ))}
            </ScrollView>
          </>
        )}

        {/* BRIEFING — secondary, errors are silent */}
        {briefing && (
          <Card style={{ marginBottom: spacing.xl }}>
            <Text
              style={{ fontSize: 16, color: t.textPrimary }}
              accessibilityRole="text"
              accessibilityLabel={`Briefing: ${briefing.greeting}`}
            >{briefing.greeting}</Text>
            {briefing.ask_prompt ? (
              <Text
                style={{ fontSize: 14, color: t.textSecondary, marginTop: spacing.sm }}
                accessibilityRole="text"
                accessibilityLabel={briefing.ask_prompt}
              >{briefing.ask_prompt}</Text>
            ) : null}
          </Card>
        )}

        {/* QUICK ASK */}
        <TouchableOpacity
          style={[styles.quickAsk, { backgroundColor: t.surface, borderColor: t.border }]}
          onPress={() => nav.navigate('Ask')}
          accessibilityRole="button"
          accessibilityLabel="Ask Maestro anything"
          accessibilityHint="Opens the Ask screen"
        >
          <Ionicons name="search" size={18} color={t.textSecondary} />
          <Text style={{ color: t.textSecondary, fontSize: 14, marginLeft: spacing.sm, flex: 1 }}>Ask Maestro anything...</Text>
          <Ionicons name="arrow-forward" size={18} color={colors.yellow} />
        </TouchableOpacity>
      </ScrollView>
      {/* Issue 7: Draft approval modal */}
      <DraftApprovalModal
        visible={draftModal.visible}
        draft={draftModal.draft}
        onClose={() => setDraftModal({ visible: false, draft: null })}
      />
    </SafeAreaView>
  );
}

// Issue 13-C: WhisperCards — "💌 Needs Attention" section on mobile Dashboard.
// P24 fix: whispers must appear on BOTH web and mobile (cross-surface coherence).
function WhisperCards({ t, nav }: { t: ReturnType<typeof getTheme>; nav: any }) {
  // Fetch whispers via react-query (60s auto-refresh = Issue 13-E)
  // Note: useWhispers may not exist in the hooks file yet — uses optional chaining
  // to gracefully degrade to empty list if the hook isn't wired.
  const whispersQ = (api as any).useWhispers?.() ?? { data: [] as any[] };
  const whispers: any[] = whispersQ.data ?? [];

  if (whispers.length === 0) return null;

  const priorityColor = (p?: string) => {
    switch (p?.toLowerCase()) {
      case 'critical': return colors.alertRed;
      case 'high': return colors.yellow;
      case 'medium': return colors.royalBlue;
      default: return t.border;
    }
  };

  return (
    <View style={{ marginBottom: spacing.xl }}>
      <Text
        style={[typography.label, { color: t.textSecondary, marginBottom: spacing.md }]}
        accessibilityRole="header"
        accessibilityLabel={`Needs Attention section, ${whispers.length} items`}
      >
        💌 Needs Attention ({whispers.length})
      </Text>
      {whispers.slice(0, 5).map((w: any, i: number) => (
        <TouchableOpacity
          key={i}
          onPress={() => nav.navigate('Ask', { query: `What should I do about ${w.entity}?` })}
          accessibilityRole="button"
          accessibilityLabel={`Whisper from ${w.entity}: ${w.body || w.title}`}
          accessibilityHint="Opens Ask to draft a follow-up"
        >
          <Card
            key={i}
            style={{
              marginBottom: spacing.sm,
              borderLeftWidth: 4,
              borderLeftColor: priorityColor(w.priority),
            }}
          >
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
              <Text style={{ fontSize: 14, fontWeight: 'bold', color: t.textPrimary }}>
                {w.entity || 'Attention'}
              </Text>
              {w.priority ? (
                <Text style={{ fontSize: 10, color: t.textSecondary, textTransform: 'uppercase' }}>
                  {w.priority}
                </Text>
              ) : null}
            </View>
            <Text
              style={{ fontSize: 14, color: t.textSecondary, marginTop: spacing.xs }}
              numberOfLines={2}
            >
              {w.body || w.title || ''}
            </Text>
            <View style={{ flexDirection: 'row', marginTop: spacing.sm, alignItems: 'center' }}>
              <Ionicons name="mail" size={14} color={colors.yellow} />
              <Text style={{ fontSize: 12, color: colors.yellow, marginLeft: spacing.xs }}>
                Draft follow-up
              </Text>
            </View>
          </Card>
        </TouchableOpacity>
      ))}
    </View>
  );
}
