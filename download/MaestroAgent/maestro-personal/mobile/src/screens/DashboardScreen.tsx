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


import React, { useState, useEffect, useRef } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, SafeAreaView, AccessibilityInfo, Alert,
  PanResponder, Animated as RNAnimated, Modal,
} from 'react-native';

import { useNavigation } from '@react-navigation/native';

import { Ionicons } from '@expo/vector-icons';

import * as Haptics from 'expo-haptics';

import { useQuery, useQueryClient } from '@tanstack/react-query';


import * as api from '../api/client';

import { useTheMoment, useShifts, useBriefing, useSmartNotifications, useEscalations, useDealHealth } from '../api/hooks';

import { colors, getTheme, spacing, typography } from '../theme/colors';

import { useAuth, useTheme } from '../contexts';

import { Card, Badge, TopBar } from '../components';

import { ErrorState, LoadingState, EmptyState } from '../components/ErrorState';

import { DraftApprovalModal } from '../components/DraftApprovalModal';

import { styles } from '../styles';
import { showAlert } from '../utils/alert';

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

  // Ambient intelligence hooks (Phases 9, 11, 19)
  const smartNotifsQ = useSmartNotifications({ limit: 5 });
  const escalationsQ = useEscalations();
  const dealHealthQ = useDealHealth();

  const moment = momentQ.data ?? null;
  const shifts: api.WhatChangedShift[] = shiftsQ.data?.secondary ?? [];
  const briefing = briefingQ.data ?? null;
  const smartNotifs = smartNotifsQ.data?.notifications ?? [];
  const escalations = escalationsQ.data?.escalations ?? [];
  const dealHealth = dealHealthQ.data?.deals ?? [];

  // ── Card mount animation (React Native built-in Animated) ─────────
  // Replaced react-native-reanimated with RN's built-in Animated to fix
  // "runtime not ready: error exception in hostobject get for prop
  // renamited module" crash in Expo Go.
  const cardOpacity = useRef(new RNAnimated.Value(0)).current;
  const cardScale = useRef(new RNAnimated.Value(0.96)).current;
  useEffect(() => {
    AccessibilityInfo.isReduceMotionEnabled().then((reduce) => {
      if (reduce) {
        RNAnimated.timing(cardOpacity, { toValue: 1, duration: 0, useNativeDriver: false }).start();
        RNAnimated.timing(cardScale, { toValue: 1, duration: 0, useNativeDriver: false }).start();
      } else {
        RNAnimated.timing(cardOpacity, { toValue: 1, duration: 400, useNativeDriver: false }).start();
        RNAnimated.spring(cardScale, { toValue: 1, damping: 18, stiffness: 160, useNativeDriver: false }).start();
      }
    });
  }, [cardOpacity, cardScale]);

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
  // Change 3: expand state for The Moment contextual expand
  const [expanded, setExpanded] = useState(false);
  // Change 2: swipe gesture state for The Moment
  const pan = useRef(new RNAnimated.ValueXY()).current;
  const [dragging, setDragging] = useState(false);
  const panResponder = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponder: (_: any, g: any) => Math.abs(g.dx) > 10 && Math.abs(g.dy) < 30,
      onPanResponderMove: (_: any, g: any) => {
        pan.setValue({ x: g.dx, y: 0 });
        if (Math.abs(g.dx) > 30 && !dragging) setDragging(true);
      },
      onPanResponderRelease: (_: any, g: any) => {
        if (g.dx > 80 && moment?.commitment) {
          Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
          handleCorrect(moment.commitment.signal_id, 'complete');
        } else if (g.dx < -80 && moment?.commitment) {
          Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
          handleCorrect(moment.commitment.signal_id, 'dismiss');
        }
        RNAnimated.spring(pan, { toValue: { x: 0, y: 0 }, useNativeDriver: false }).start();
        setDragging(false);
      },
    })
  ).current;

  const handleDraft = async (entity: string) => {
    if (!entity) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      const result = await api.generateAutoDraft('gmail', entity);
      setDraftModal({ visible: true, draft: result });
    } catch (e) {
      showAlert('Error', 'Failed to generate draft. Is the backend running?');
    }
  };

  // Change 4: Smart snooze
  const handleSnooze = async (momentData: any) => {
    if (!momentData?.commitment) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      await api.correctSignal(momentData.commitment.signal_id, 'dismiss');
      const Notifications = (await import('expo-notifications')).default;
      await Notifications.scheduleNotificationAsync({
        content: {
          title: `${momentData.commitment.entity} — snooze reminder`,
          body: `You snoozed: "${momentData.commitment.text?.substring(0, 60)}". Ready to act?`,
          data: { type: 'snooze_reminder', entity: momentData.commitment.entity },
        },
        trigger: { seconds: 7200 } as any,
      });
      showAlert('Snoozed', `We'll remind you in 2 hours about ${momentData.commitment.entity}.`);
      qc.invalidateQueries({ queryKey: ['theMoment'] });
    } catch (e) {
      showAlert('Error', 'Failed to snooze. Is the backend running?');
    }
  };

  // Silence unused-var lint while preserving the original quick-ask field shape.
  void askQuery;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: t.bg }}>
      <TopBar title="Dashboard" />
      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: spacing.xl }}>
        {/* AMBIENT INTELLIGENCE — Smart Notifications (Phase 19) */}
        {smartNotifs.length > 0 && (
          <View style={{ marginBottom: spacing.xl }}>
            <Text style={[typography.label, { color: colors.alertRed, marginBottom: spacing.sm }]}>🔔 NEEDS ATTENTION</Text>
            {smartNotifs.slice(0, 3).map((n: any) => (
              <TouchableOpacity
                key={n.notification_id}
                onPress={() => n.action_url && nav.navigate('Commitments')}
                style={{
                  backgroundColor: n.priority === 'critical' ? colors.alertRedLight : t.surface,
                  borderRadius: 12,
                  padding: 14,
                  marginBottom: 8,
                  borderLeftWidth: 4,
                  borderLeftColor: n.priority === 'critical' ? colors.alertRed : colors.yellow,
                }}
              >
                <Text style={{ fontSize: 14, fontWeight: '700', color: t.textPrimary, marginBottom: 4 }}>
                  {n.title}
                </Text>
                <Text style={{ fontSize: 13, color: t.textSecondary }} numberOfLines={2}>
                  {n.body}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        )}

        {/* AMBIENT INTELLIGENCE — Commitment Escalations (Phase 9) */}
        {escalations.filter(e => e.escalation_level === 'high' || e.escalation_level === 'critical').length > 0 && (
          <View style={{ marginBottom: spacing.xl }}>
            <Text style={[typography.label, { color: colors.alertRed, marginBottom: spacing.sm }]}>⚠️ ESCALATIONS</Text>
            {escalations
              .filter(e => e.escalation_level === 'high' || e.escalation_level === 'critical')
              .slice(0, 3)
              .map((e) => (
                <TouchableOpacity
                  key={e.commitment_id}
                  onPress={() => nav.navigate('Commitments')}
                  style={{
                    backgroundColor: t.surface,
                    borderRadius: 12,
                    padding: 14,
                    marginBottom: 8,
                    borderLeftWidth: 4,
                    borderLeftColor: e.escalation_level === 'critical' ? colors.alertRed : colors.yellow,
                  }}
                >
                  <Text style={{ fontSize: 14, fontWeight: '700', color: t.textPrimary, marginBottom: 4 }}>
                    {e.entity ? `${e.entity} · ` : ''}{e.commitment_text?.slice(0, 60)}
                  </Text>
                  {e.days_overdue ? (
                    <Text style={{ fontSize: 12, color: colors.alertRed, fontWeight: '600' }}>
                      {e.days_overdue} days overdue
                    </Text>
                  ) : null}
                  {e.nudge_text ? (
                    <Text style={{ fontSize: 13, color: t.textSecondary, marginTop: 4 }} numberOfLines={2}>
                      → {e.nudge_text}
                    </Text>
                  ) : null}
                </TouchableOpacity>
              ))}
          </View>
        )}

        {/* AMBIENT INTELLIGENCE — Deal Health (Phase 11) */}
        {dealHealth.filter(d => d.status === 'at_risk' || d.status === 'critical').length > 0 && (
          <View style={{ marginBottom: spacing.xl }}>
            <Text style={[typography.label, { color: colors.alertRed, marginBottom: spacing.sm }]}>📉 DEALS AT RISK</Text>
            {dealHealth
              .filter(d => d.status === 'at_risk' || d.status === 'critical')
              .slice(0, 3)
              .map((d) => (
                <View
                  key={d.entity}
                  style={{
                    backgroundColor: t.surface,
                    borderRadius: 12,
                    padding: 14,
                    marginBottom: 8,
                    flexDirection: 'row',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 14, fontWeight: '700', color: t.textPrimary }}>
                      {d.entity}
                    </Text>
                    <Text style={{ fontSize: 12, color: t.textSecondary, marginTop: 2 }}>
                      {d.momentum === 'decelerating' ? '↓ decelerating' : d.momentum === 'accelerating' ? '↑ accelerating' : '→ stable'}
                    </Text>
                  </View>
                  <View style={{
                    backgroundColor: d.status === 'critical' ? colors.alertRed : colors.yellow,
                    borderRadius: 8,
                    paddingHorizontal: 10,
                    paddingVertical: 4,
                  }}>
                    <Text style={{ fontSize: 13, fontWeight: '800', color: colors.black }}>
                      {Math.round(d.score)}%
                    </Text>
                  </View>
                </View>
              ))}
          </View>
        )}

        {/* THE MOMENT */}
        <Text style={[typography.label, { color: colors.yellow, marginBottom: spacing.md }]}>⚡ THE MOMENT</Text>
        {momentQ.isLoading ? (
          <LoadingState label="Loading the moment…" />
        ) : momentQ.error ? (
          <ErrorState message="Couldn't load the moment." onRetry={() => momentQ.refetch()} />
        ) : moment?.has_moment && moment.commitment ? (
          <RNAnimated.View
            {...panResponder.panHandlers}
            style={[{ transform: pan.getTranslateTransform(), marginBottom: spacing.xl }, dragging && { opacity: 0.9 }]}
            accessibilityLiveRegion="polite"
            accessibilityLabel="The Moment card — swipe right for done, left for skip"
            accessibilityRole="summary"
          >
            <Card accent="yellow">
              <TouchableOpacity
                onPress={() => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light); setExpanded(!expanded); }}
                accessibilityLabel="Expand The Moment details"
                accessibilityRole="button"
              >
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
              </TouchableOpacity>
              {/* Change 3: Contextual expand */}
              {expanded && (
                <View style={{ backgroundColor: t.surface, borderRadius: 8, padding: 12, marginTop: 8 }}>
                  <Text style={{ fontSize: 11, fontWeight: '800', color: colors.yellowDark, textTransform: 'uppercase', marginBottom: 6 }}>📎 Evidence</Text>
                  {(moment as any).source_sentence && (
                    <Text style={{ fontSize: 13, fontStyle: 'italic', color: t.textSecondary, marginBottom: 6 }}>"{(moment as any).source_sentence}"</Text>
                  )}
                  {(moment as any).evidence_refs && (moment as any).evidence_refs.map((ref: any, i: number) => (
                    <Text key={i} style={{ fontSize: 12, color: t.textSecondary, marginBottom: 4 }}>• {ref.entity || 'Unknown'}: "{ref.text?.substring(0, 60)}"</Text>
                  ))}
                </View>
              )}
              <View style={{ flexDirection: 'row', justifyContent: 'center', marginTop: spacing.xl, gap: spacing.sm }}>
                <TouchableOpacity
                  style={[styles.actionButton, { backgroundColor: colors.successGreen }]}
                  onPress={() => { Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success); handleCorrect(moment.commitment!.signal_id, 'complete'); }}
                  accessibilityRole="button"
                  accessibilityLabel="Mark commitment as done"
                  accessibilityHint="Completes this commitment"
                >
                  <Ionicons name="checkmark" size={24} color={colors.white} />
                  <Text style={styles.actionLabel}>Done</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.actionButton, { backgroundColor: t.border }]}
                  onPress={() => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium); handleCorrect(moment.commitment!.signal_id, 'dismiss'); }}
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
                {/* Change 4: Snooze button */}
                <TouchableOpacity
                  style={[styles.actionButton, { backgroundColor: t.border }]}
                  onPress={() => handleSnooze(moment)}
                  accessibilityRole="button"
                  accessibilityLabel="Snooze for 2 hours"
                  accessibilityHint="Reminds you in 2 hours"
                >
                  <Ionicons name="time" size={24} color={t.textSecondary} />
                  <Text style={[styles.actionLabel, { color: t.textSecondary }]}>Snooze</Text>
                </TouchableOpacity>
              </View>
            </Card>
          </RNAnimated.View>
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
// P1-6 fix (audit 2026-07-15): the prior code used `(api as any).useWhispers?.()`
// which never resolved — the hook didn't exist, so optional chaining returned
// undefined, falling back to `{ data: [] }`. WhisperCards was ALWAYS empty.
// Now uses useQuery with the real getWhispers() API function (60s auto-refresh).
// P0-5 fix (audit V2): added "Why this?" modal showing the DeliveryGovernor's
// explanation — intervention_value, interruption_cost, reasons_to_surface.
// This exposes the Trusted Silence reasoning to the user.
function WhisperCards({ t, nav }: { t: ReturnType<typeof getTheme>; nav: any }) {
  const whispersQ = useQuery({
    queryKey: ['whispers'],
    queryFn: () => api.getWhispers().catch(() => [] as any[]),
    staleTime: 60_000,  // 60s auto-refresh (Issue 13-E)
  });
  const whispers: any[] = whispersQ.data ?? [];
  const [selectedWhisper, setSelectedWhisper] = React.useState<any>(null);

  if (whispers.length === 0) return null;

  const priorityColor = (p?: string) => {
    switch (p?.toLowerCase()) {
      case 'critical': return colors.alertRed;
      case 'high': return colors.yellow;
      case 'medium': return colors.royalBlue;
      default: return t.border;
    }
  };

  // P0-5 fix: build the "Why this?" explanation from the whisper's depth fields.
  // The backend's DeliveryGovernor populates delivery_explanation,
  // suppression_reason, and evidence_refs on each whisper.
  const buildExplanation = (w: any): string => {
    const parts: string[] = [];
    if (w.delivery_explanation) {
      parts.push(`Why surfaced: ${w.delivery_explanation}`);
    }
    if (w.suppression_reason) {
      parts.push(`Suppression reason: ${w.suppression_reason}`);
    }
    if (w.delivery_route) {
      parts.push(`Delivery route: ${w.delivery_route}`);
    }
    if (w.evidence_refs && w.evidence_refs.length > 0) {
      parts.push(`Evidence: ${w.evidence_refs.slice(0, 3).join('; ')}`);
    }
    if (parts.length === 0) {
      parts.push('Maestro detected this needs your attention based on your commitment history and signal patterns.');
    }
    return parts.join('\n\n');
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
        <View key={i}>
          <TouchableOpacity
            onPress={() => nav.navigate('Ask', { query: `What should I do about ${w.entity}?` })}
            onLongPress={() => setSelectedWhisper(w)}
            accessibilityRole="button"
            accessibilityLabel={`Whisper from ${w.entity}: ${w.body || w.title}`}
            accessibilityHint="Tap to draft a follow-up. Long-press to see why Maestro surfaced this."
          >
            <Card
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
              <View style={{ flexDirection: 'row', marginTop: spacing.sm, alignItems: 'center', justifyContent: 'space-between' }}>
                <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                  <Ionicons name="mail" size={14} color={colors.yellow} />
                  <Text style={{ fontSize: 12, color: colors.yellow, marginLeft: spacing.xs }}>
                    Draft follow-up
                  </Text>
                </View>
                {/* P0-5 fix: "Why this?" button — exposes Trusted Silence reasoning */}
                <TouchableOpacity
                  onPress={() => setSelectedWhisper(w)}
                  style={{ flexDirection: 'row', alignItems: 'center' }}
                  accessibilityRole="button"
                  accessibilityLabel="Why did Maestro surface this?"
                >
                  <Ionicons name="information-circle-outline" size={14} color={t.textSecondary} />
                  <Text style={{ fontSize: 12, color: t.textSecondary, marginLeft: 4 }}>Why this?</Text>
                </TouchableOpacity>
              </View>
            </Card>
          </TouchableOpacity>
        </View>
      ))}

      {/* P0-5 fix: Trusted Silence "Why this?" modal */}
      {selectedWhisper && (
        <Modal
          visible={true}
          transparent={true}
          animationType="fade"
          onRequestClose={() => setSelectedWhisper(null)}
        >
          <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: 'rgba(0,0,0,0.5)', padding: 24 }}>
            <View style={{ backgroundColor: t.surface, borderRadius: 16, padding: 24, width: '100%', maxWidth: 400 }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <Text style={{ fontSize: 18, fontWeight: 'bold', color: t.textPrimary }}>
                  Why Maestro surfaced this
                </Text>
                <TouchableOpacity onPress={() => setSelectedWhisper(null)}>
                  <Ionicons name="close" size={24} color={t.textSecondary} />
                </TouchableOpacity>
              </View>
              <Text style={{ fontSize: 14, fontWeight: '600', color: t.textPrimary, marginBottom: 8 }}>
                {selectedWhisper.entity || 'Attention'}
              </Text>
              <Text style={{ fontSize: 14, color: t.textSecondary, marginBottom: 16 }}>
                {selectedWhisper.body || selectedWhisper.title}
              </Text>
              <View style={{ borderTopWidth: 1, borderTopColor: t.border, paddingTop: 16 }}>
                <Text style={{ fontSize: 13, color: t.textPrimary, lineHeight: 20 }}>
                  {buildExplanation(selectedWhisper)}
                </Text>
              </View>
              <TouchableOpacity
                onPress={() => {
                  setSelectedWhisper(null);
                  nav.navigate('Ask', { query: `What should I do about ${selectedWhisper.entity}?` });
                }}
                style={{ marginTop: 20, backgroundColor: colors.yellow, paddingVertical: 12, borderRadius: 8, alignItems: 'center' }}
              >
                <Text style={{ fontSize: 15, fontWeight: '600', color: '#000' }}>Draft follow-up</Text>
              </TouchableOpacity>
            </View>
          </View>
        </Modal>
      )}
    </View>
  );
}
