/**
 * CommitmentsScreen — extracted from the original App.tsx.
 *
 * Phase 2: data fetching now goes through react-query hooks
 * (useTheOne / useCommitments) instead of manual useEffect+useState.
 * Loading/error/empty states use the shared components from
 * src/components/ErrorState.tsx. Active-list cards now support
 * swipe-to-complete (right) and swipe-to-dismiss (left) with haptic
 * feedback, implemented via PanResponder (no gesture-handler provider
 * required).
 *
 * UI/logic is otherwise unchanged.
 */


import React, { useRef, useState, useMemo } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, Alert, SafeAreaView,
  Animated, PanResponder, StyleSheet, LayoutAnimation, UIManager, Platform,
  FlatList,
} from 'react-native';

import * as Haptics from 'expo-haptics';

import AsyncStorage from '@react-native-async-storage/async-storage';


import * as api from '../api/client';

import { useTheOne, useCommitments, useSignals, useDealHealth, useMeetingGrades } from '../api/hooks';

import { useQueryClient } from '@tanstack/react-query';

import { colors, getTheme, spacing, typography } from '../theme/colors';

import { useAuth, useTheme } from '../contexts';

import { Card, Badge, TopBar } from '../components';

import { ErrorState, LoadingState, EmptyState } from '../components/ErrorState';

import { DraftApprovalModal } from '../components/DraftApprovalModal';

import { styles } from '../styles';
import { showAlert } from '../utils/alert';

// Android LayoutAnimation enable (for swipe-off removal animation).
if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

const SWIPE_THRESHOLD = 80; // px — past this, the action commits
const OFFSCREEN = 400;      // px — how far the card flies before removal

// ── SwipeableCommitmentCard ───────────────────────────────────────────
// Wraps a commitment card with a horizontal pan. Right-swipe = complete
// (green), left-swipe = dismiss (gray). Haptic on commit.

interface SwipeableCommitmentCardProps {
  commitment: api.Commitment;
  onComplete: (signalId: string) => void;
  onDismiss: (signalId: string) => void;
  children: React.ReactNode;
}

function SwipeableCommitmentCard({
  commitment, onComplete, onDismiss, children,
}: SwipeableCommitmentCardProps) {
  const { mode } = useTheme();
  const t = getTheme(mode);
  const pan = useRef(new Animated.Value(0)).current;

  // Background opacity tracks pan position so the green/gray wash
  // fades in as the card slides away.
  const bgOpacity = useRef(new Animated.Value(0)).current;
  const isRightSwipe = useRef(true);

  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => false,
      onMoveShouldSetPanResponder: (_e, g) => Math.abs(g.dx) > 8,
      onPanResponderGrant: () => {
        // Freeze current value so dx-relative pan starts cleanly.
        pan.extractOffset();
      },
      onPanResponderMove: (_e, g) => {
        isRightSwipe.current = g.dx > 0;
        bgOpacity.setValue(Math.min(Math.abs(g.dx) / SWIPE_THRESHOLD, 1));
        pan.setValue(g.dx);
      },
      onPanResponderRelease: (_e, g) => {
        if (g.dx > SWIPE_THRESHOLD) {
          // Commit complete — fly off right.
          Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
          Animated.timing(pan, {
            toValue: OFFSCREEN,
            duration: 200,
            useNativeDriver: true,
          }).start(() => {
            onComplete(commitment.signal_id);
            // Reset for the next render cycle.
            pan.setValue(0);
            pan.setOffset(0);
            bgOpacity.setValue(0);
          });
        } else if (g.dx < -SWIPE_THRESHOLD) {
          // Commit dismiss — fly off left.
          Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
          Animated.timing(pan, {
            toValue: -OFFSCREEN,
            duration: 200,
            useNativeDriver: true,
          }).start(() => {
            onDismiss(commitment.signal_id);
            pan.setValue(0);
            pan.setOffset(0);
            bgOpacity.setValue(0);
          });
        } else {
          // Snap back.
          Animated.parallel([
            Animated.spring(pan, { toValue: 0, useNativeDriver: true }),
            Animated.spring(bgOpacity, { toValue: 0, useNativeDriver: true }),
          ]).start();
        }
      },
    })
  ).current;

  return (
    <View style={{ marginBottom: spacing.md }}>
      {/* Swipe action background — green (complete) or gray (dismiss) */}
      <View style={[swipeStyles.bgLayer, { backgroundColor: t.cardBg }]}>
        <Animated.View
          style={[
            swipeStyles.bgFill,
            {
              backgroundColor: isRightSwipe.current ? colors.successGreen : t.border,
              opacity: bgOpacity,
            },
          ]}
        />
        <View style={swipeStyles.bgLabelRow}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            <Text style={swipeStyles.bgIconRight}>✓</Text>
            <Text style={[swipeStyles.bgLabel, { color: colors.white, opacity: bgOpacity }]}>
              Complete
            </Text>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            <Text style={[swipeStyles.bgLabel, { color: t.textSecondary, opacity: bgOpacity }]}>
              Dismiss
            </Text>
            <Text style={swipeStyles.bgIconLeft}>✕</Text>
          </View>
        </View>
      </View>

      {/* The actual card on top, panning horizontally */}
      <Animated.View
        {...panResponder.panHandlers}
        style={{
          transform: [{ translateX: pan }],
          backgroundColor: t.cardBg,
          borderRadius: 16,
          borderLeftWidth: 4,
          borderLeftColor: commitment.is_at_risk
            ? colors.alertRed
            : (commitment.days_stale ?? 0) > 2
              ? colors.yellow
              : colors.successGreen,
        }}
        accessibilityRole="summary"
        accessibilityLabel={`Commitment from ${commitment.entity}. Swipe right to complete, left to dismiss.`}
        accessibilityHint="Swipe right to complete, left to dismiss"
      >
        <View style={{ padding: 20 }}>
          {children}
        </View>
      </Animated.View>
    </View>
  );
}

const swipeStyles = StyleSheet.create({
  bgLayer: {
    ...StyleSheet.absoluteFillObject,
    borderRadius: 16,
    overflow: 'hidden',
  },
  bgFill: {
    ...StyleSheet.absoluteFillObject,
  },
  bgLabelRow: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 24,
  },
  bgIconRight: { color: colors.white, fontSize: 22, fontWeight: '700' },
  bgIconLeft: { color: colors.gray, fontSize: 22, fontWeight: '700' },
  bgLabel: { fontSize: 13, fontWeight: '700', letterSpacing: 1 },
});

// ── CommitmentsScreen ────────────────────────────────────────────────

export default function CommitmentsScreen() {
  const { mode } = useTheme();
  const t = getTheme(mode);
  const { token } = useAuth();
  const qc = useQueryClient();

  // V2: segmented control — Commitments | Signals
  const [activeTab, setActiveTab] = useState<'commitments' | 'signals'>('commitments');

  // ── react-query hooks ─────────────────────────────────────────────
  const theOneQ = useTheOne();
  const commitmentsQ = useCommitments();
  const signalsQ = useSignals();
  // Phase 11 + 16: deal health per entity + meeting grades
  const dealHealthQ = useDealHealth();
  const meetingGradesQ = useMeetingGrades();
  const dealHealthByEntity = useMemo(() => {
    const map: Record<string, api.DealHealthScore> = {};
    (dealHealthQ.data?.deals ?? []).forEach((d) => { map[d.entity] = d; });
    return map;
  }, [dealHealthQ.data]);
  const meetingGrades = meetingGradesQ.data?.grades ?? [];

  const theOne = theOneQ.data ?? null;
  const commitments: api.Commitment[] = commitmentsQ.data ?? [];
  const signals: any[] = signalsQ.data ?? [];

  // Change 10: Trust health per entity
  const entityHealth = useMemo(() => {
    const groups: Record<string, { commitments: any[]; maxStatus: 'green' | 'yellow' | 'red' }> = {};
    (commitments || []).forEach((c: any) => {
      const entity = c.entity || 'Unknown';
      if (!groups[entity]) groups[entity] = { commitments: [], maxStatus: 'green' };
      groups[entity].commitments.push(c);
      const daysStale = c.days_stale || 0;
      if (daysStale > 5 || c.status === 'broken') {
        groups[entity].maxStatus = 'red';
      } else if (daysStale > 2 && groups[entity].maxStatus !== 'red') {
        groups[entity].maxStatus = 'yellow';
      }
    });
    return groups;
  }, [commitments]);

  const handleCorrect = async (signalId: string, action: 'complete' | 'dismiss' | 'cancel') => {
    if (!token || !signalId) return;
    showAlert(
      `${action.charAt(0).toUpperCase() + action.slice(1)} this commitment?`,
      undefined,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Confirm',
          onPress: async () => {
            await api.correctSignal(signalId, action);
            // Refetch via react-query invalidation.
            qc.invalidateQueries({ queryKey: ['theOne'] });
            qc.invalidateQueries({ queryKey: ['commitments'] });
          },
        },
      ]
    );
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
      showAlert('Error', 'Failed to generate draft. Is the backend running?');
    }
  };

  // Swipe handlers — bypass the Alert confirm for speed. Haptic is fired
  // in the card itself; the actual API call happens here.
  // Change 11: Optimistic UI — immediately remove card, rollback on error
  // Change 15: Offline write queue — failed actions saved to AsyncStorage for retry
  const handleSwipeComplete = async (signalId: string) => {
    if (!token || !signalId) return;
    // Optimistic: immediately remove from cache
    const previous = qc.getQueryData(['commitments']);
    qc.setQueryData(['commitments'], (old: any[]) => old?.filter(c => c.signal_id !== signalId) || []);
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    try {
      await api.correctSignal(signalId, 'complete');
      qc.invalidateQueries({ queryKey: ['theOne'] });
      qc.invalidateQueries({ queryKey: ['commitments'] });
      // Clear any pending action for this ID
      try { await AsyncStorage.removeItem(`pending_action_${signalId}`); } catch { /* ignore */ }
    } catch (e: any) {
      // Change 15: If network error, queue for retry instead of rolling back
      const isNetworkError = e?.message?.includes('Network') || e?.message?.includes('timeout');
      if (isNetworkError) {
        // Save to AsyncStorage queue — will retry on next app launch
        try {
          await AsyncStorage.setItem(`pending_action_${signalId}`, JSON.stringify({ id: signalId, action: 'complete' }));
        } catch { /* ignore */ }
        showAlert('Offline', 'Saved. Will sync when you reconnect.');
      } else {
        // Non-network error: rollback
        qc.setQueryData(['commitments'], previous);
        showAlert('Error', 'Failed to update. Please try again.');
      }
    }
  };

  const handleSwipeDismiss = async (signalId: string) => {
    if (!token || !signalId) return;
    // Optimistic: immediately remove from cache
    const previous = qc.getQueryData(['commitments']);
    qc.setQueryData(['commitments'], (old: any[]) => old?.filter(c => c.signal_id !== signalId) || []);
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    try {
      await api.correctSignal(signalId, 'dismiss');
      qc.invalidateQueries({ queryKey: ['theOne'] });
      qc.invalidateQueries({ queryKey: ['commitments'] });
      try { await AsyncStorage.removeItem(`pending_action_${signalId}`); } catch { /* ignore */ }
    } catch (e: any) {
      const isNetworkError = e?.message?.includes('Network') || e?.message?.includes('timeout');
      if (isNetworkError) {
        try {
          await AsyncStorage.setItem(`pending_action_${signalId}`, JSON.stringify({ id: signalId, action: 'dismiss' }));
        } catch { /* ignore */ }
        showAlert('Offline', 'Saved. Will sync when you reconnect.');
      } else {
        qc.setQueryData(['commitments'], previous);
        showAlert('Error', 'Failed to update. Please try again.');
      }
    }
  };

  const isLoading = theOneQ.isLoading && commitmentsQ.isLoading;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: t.bg }}>
      <TopBar title="Commitments" />

      {/* V2: Segmented control — Commitments | Signals */}
      <View style={{ flexDirection: 'row', marginHorizontal: spacing.xl, marginBottom: spacing.md, backgroundColor: t.surface, borderRadius: 12, padding: 4 }}>
        {(['commitments', 'signals'] as const).map(tab => (
          <TouchableOpacity
            key={tab}
            onPress={() => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light); setActiveTab(tab); }}
            style={{ flex: 1, paddingVertical: 8, borderRadius: 8, backgroundColor: activeTab === tab ? colors.yellow : 'transparent', alignItems: 'center' }}
            accessibilityLabel={`Show ${tab}`}
            accessibilityRole="tab"
          >
            <Text style={{ fontSize: 12, fontWeight: '700', color: activeTab === tab ? colors.black : t.textSecondary, textTransform: 'capitalize' }}>{tab}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* V2: Signals view (FlatList) */}
      {activeTab === 'signals' ? (
        <FlatList
          data={signals}
          keyExtractor={(item: any) => item.signal_id || Math.random().toString()}
          contentContainerStyle={{ padding: spacing.xl }}
          renderItem={({ item }: { item: any }) => (
            <Card style={{ marginBottom: spacing.sm }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
                <Text style={{ fontSize: 13, fontWeight: '700', color: t.textPrimary }}>{item.entity}</Text>
                <Text style={{ fontSize: 9, color: colors.yellow, fontWeight: '600', textTransform: 'uppercase' }}>{item.signal_type}</Text>
              </View>
              <Text style={{ fontSize: 12, color: t.textSecondary }}>{item.text}</Text>
              <Text style={{ fontSize: 10, color: t.textSecondary, marginTop: 4 }}>{item.timestamp?.slice(0, 10)}</Text>
            </Card>
          )}
          ListEmptyComponent={
            signalsQ.isLoading ? <LoadingState label="Loading signals…" /> :
            <EmptyState title="No signals yet" subtitle="Signals appear when connectors sync." icon="radio" />
          }
        />
      ) : (
      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: spacing.xl }}>
        {isLoading ? (
          <LoadingState label="Loading commitments…" />
        ) : theOneQ.error && commitmentsQ.error ? (
          <ErrorState message="Couldn't load commitments." onRetry={() => { theOneQ.refetch(); commitmentsQ.refetch(); }} />
        ) : (
          <>
            {/* THE ONE */}
            {theOne?.primary && (
              <>
                <Text
                  style={[typography.label, { color: colors.yellow, marginBottom: spacing.md }]}
                  accessibilityRole="header"
                  accessibilityLabel="The One section"
                >⭐ THE ONE</Text>
                <Card accent="yellow" style={{ marginBottom: spacing.xl }}>
                  <Text
                    style={{ fontSize: 20, fontWeight: 'bold', color: t.textPrimary }}
                    accessibilityRole="header"
                    accessibilityLabel={`Primary commitment: ${theOne.primary.entity}`}
                  >{theOne.primary.entity}</Text>
                  <Text
                    style={{ fontSize: 16, color: t.textSecondary, fontStyle: 'italic', marginTop: spacing.xs }}
                    accessibilityRole="text"
                    accessibilityLabel={`Commitment: ${theOne.primary.text}`}
                  >
                    "{theOne.primary.text}"
                  </Text>
                  {theOne.primary.deadline ? <Badge text={`📅 ${theOne.primary.deadline}`} color="yellow" /> : null}
                  {theOne.primary.is_at_risk ? <Badge text="🔥 At Risk" color="red" /> : null}
                  {(theOne.primary.days_stale ?? 0) > 0 ? <Text
                    style={{ fontSize: 13, color: t.textSecondary, marginTop: spacing.xs }}
                    accessibilityRole="text"
                    accessibilityLabel={`${theOne.primary.days_stale} days stale`}
                  >{theOne.primary.days_stale}d stale</Text> : null}
                  {theOne.why_primary ? <Text
                    style={{ fontSize: 14, color: t.textSecondary, marginTop: spacing.sm }}
                    accessibilityRole="text"
                    accessibilityLabel={`Why this is primary: ${theOne.why_primary}`}
                  >{theOne.why_primary}</Text> : null}
                  <View style={{ flexDirection: 'row', gap: spacing.md, marginTop: spacing.lg }}>
                    <TouchableOpacity
                      style={[styles.smallBtn, { backgroundColor: colors.successGreen }]}
                      onPress={() => handleCorrect(theOne.primary?.signal_id ?? '', 'complete')}
                      accessibilityRole="button"
                      accessibilityLabel="Complete primary commitment"
                      accessibilityHint="Completes this commitment"
                    >
                      <Text style={{ color: colors.white, fontSize: 13, fontWeight: '600' }}>✓ Complete</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      style={[styles.smallBtn, { backgroundColor: t.border }]}
                      onPress={() => handleCorrect(theOne.primary?.signal_id ?? '', 'dismiss')}
                      accessibilityRole="button"
                      accessibilityLabel="Dismiss primary commitment"
                      accessibilityHint="Dismisses this commitment"
                    >
                      <Text style={{ color: t.textSecondary, fontSize: 13, fontWeight: '600' }}>✕ Dismiss</Text>
                    </TouchableOpacity>
                  </View>
                </Card>
              </>
            )}

            {/* ACTIVE LIST */}
            <Text
              style={[typography.label, { color: t.textSecondary, marginBottom: spacing.md }]}
              accessibilityRole="header"
              accessibilityLabel="Active commitments section"
            >ACTIVE COMMITMENTS</Text>
            {commitments.length === 0 ? (
              <EmptyState
                title="No active commitments"
                subtitle="Swipe right to complete · left to dismiss."
                icon="checkmark-done-outline"
              />
            ) : (
              commitments.map((c) => (
                <SwipeableCommitmentCard
                  key={c.signal_id}
                  commitment={c}
                  onComplete={handleSwipeComplete}
                  onDismiss={handleSwipeDismiss}
                >
                  <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                    <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: c.is_at_risk ? colors.alertRed : (c.days_stale ?? 0) > 2 ? colors.yellow : colors.successGreen, marginRight: spacing.md }} />
                    <Text
                      style={{ fontSize: 15, fontWeight: 'bold', color: t.textPrimary, flex: 1 }}
                      accessibilityRole="text"
                      accessibilityLabel={c.entity}
                    >{c.entity}</Text>
                    {/* Change 10: Trust health badge per entity */}
                    {entityHealth[c.entity]?.maxStatus === 'red' && (
                      <Text style={{ fontSize: 9, color: colors.alertRed, fontWeight: '700', marginRight: 4 }}>🔴 Trust at risk</Text>
                    )}
                    {entityHealth[c.entity]?.maxStatus === 'yellow' && (
                      <Text style={{ fontSize: 9, color: colors.yellow, fontWeight: '600', marginRight: 4 }}>🟡 Needs attention</Text>
                    )}
                    {entityHealth[c.entity]?.maxStatus === 'green' && (
                      <Text style={{ fontSize: 9, color: colors.successGreen, fontWeight: '600', marginRight: 4 }}>🟢</Text>
                    )}
                    {c.deadline ? <Badge text={c.deadline} color="yellow" /> : null}
                    {/* Phase 11: Deal health pill per entity */}
                    {dealHealthByEntity[c.entity] && (
                      <View style={{
                        backgroundColor: dealHealthByEntity[c.entity].status === 'critical' ? colors.alertRed
                          : dealHealthByEntity[c.entity].status === 'at_risk' ? colors.yellow
                          : dealHealthByEntity[c.entity].status === 'strong' ? colors.successGreen
                          : t.border,
                        borderRadius: 6,
                        paddingHorizontal: 6,
                        paddingVertical: 2,
                        marginLeft: 4,
                      }}>
                        <Text style={{ fontSize: 10, fontWeight: '700', color: colors.black }}>
                          {Math.round(dealHealthByEntity[c.entity].score)}%
                        </Text>
                      </View>
                    )}
                  </View>
                  <Text
                    style={{ fontSize: 13, color: t.textSecondary, marginTop: spacing.xs }}
                    numberOfLines={2}
                    accessibilityRole="text"
                    accessibilityLabel={`Commitment: ${c.text}`}
                  >"{c.text}"</Text>
                  <View style={{ flexDirection: 'row', gap: spacing.md, marginTop: spacing.sm }}>
                    <TouchableOpacity
                      onPress={() => handleCorrect(c.signal_id, 'complete')}
                      accessibilityRole="button"
                      accessibilityLabel={`Complete ${c.entity} commitment`}
                      accessibilityHint="Completes this commitment"
                    >
                      <Text style={{ color: colors.successGreen, fontSize: 12, fontWeight: '600' }}>✓ Complete</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      onPress={() => handleCorrect(c.signal_id, 'dismiss')}
                      accessibilityRole="button"
                      accessibilityLabel={`Dismiss ${c.entity} commitment`}
                      accessibilityHint="Dismisses this commitment"
                    >
                      <Text style={{ color: t.textSecondary, fontSize: 12, fontWeight: '600' }}>✕ Dismiss</Text>
                    </TouchableOpacity>
                    {/* Issue 7: Draft email button */}
                    <TouchableOpacity
                      onPress={() => handleDraft(c.entity)}
                      accessibilityRole="button"
                      accessibilityLabel={`Draft email to ${c.entity}`}
                      accessibilityHint="Generates a commitment-aware email draft"
                    >
                      <Text style={{ color: colors.yellow, fontSize: 12, fontWeight: '600' }}>✉ Draft</Text>
                    </TouchableOpacity>
                  </View>
                </SwipeableCommitmentCard>
              ))
            )}

            {/* Phase 16: Meeting History with grades */}
            {meetingGrades.length > 0 && (
              <>
                <Text
                  style={[typography.label, { color: t.textSecondary, marginBottom: spacing.md, marginTop: spacing.xl }]}
                  accessibilityRole="header"
                  accessibilityLabel="Meeting history section"
                >MEETING HISTORY</Text>
                {meetingGrades.slice(0, 5).map((g) => (
                  <Card key={g.meeting_id || g.entity} style={{ marginBottom: spacing.sm }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                      <View style={{ flex: 1 }}>
                        <Text style={{ fontSize: 14, fontWeight: 'bold', color: t.textPrimary }}>
                          {g.entity || g.title || 'Meeting'}
                        </Text>
                        {g.title && g.title !== g.entity && (
                          <Text style={{ fontSize: 12, color: t.textSecondary, marginTop: 2 }} numberOfLines={1}>
                            {g.title}
                          </Text>
                        )}
                        <Text style={{ fontSize: 11, color: t.textSecondary, marginTop: 4 }}>
                          {g.confidence_label}
                        </Text>
                      </View>
                      <View style={{
                        backgroundColor: g.grade === 'A' ? colors.successGreen
                          : g.grade === 'B' ? colors.yellow
                          : g.grade === 'C' ? colors.yellowDark
                          : colors.alertRed,
                        borderRadius: 8,
                        width: 36,
                        height: 36,
                        alignItems: 'center',
                        justifyContent: 'center',
                      }}>
                        <Text style={{ fontSize: 18, fontWeight: '900', color: colors.black }}>
                          {g.effective_grade || g.grade}
                        </Text>
                      </View>
                    </View>
                    {g.action_items && g.action_items.length > 0 && (
                      <Text style={{ fontSize: 11, color: t.textSecondary, marginTop: 6 }}>
                        {g.action_items.length} action item{g.action_items.length !== 1 ? 's' : ''} · {Math.round(g.action_item_completion_rate || 0)}% complete
                      </Text>
                    )}
                  </Card>
                ))}
              </>
            )}
          </>
        )}
      </ScrollView>
      )}
      {/* Issue 7: Draft approval modal */}
      <DraftApprovalModal
        visible={draftModal.visible}
        draft={draftModal.draft}
        onClose={() => setDraftModal({ visible: false, draft: null })}
      />
    </SafeAreaView>
  );
}
