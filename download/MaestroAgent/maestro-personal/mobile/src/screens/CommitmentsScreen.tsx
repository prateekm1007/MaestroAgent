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

import React, { useRef, useState } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, Alert, SafeAreaView,
  Animated, PanResponder, StyleSheet, LayoutAnimation, UIManager, Platform,
  FlatList,
} from 'react-native';
import * as Haptics from 'expo-haptics';

import * as api from '../api/client';
import { useTheOne, useCommitments, useSignals } from '../api/hooks';
import { useQueryClient } from '@tanstack/react-query';
import { colors, getTheme, spacing, typography } from '../theme/colors';
import { useAuth, useTheme } from '../contexts';
import { Card, Badge, TopBar } from '../components';
import { ErrorState, LoadingState, EmptyState } from '../components/ErrorState';
import { DraftApprovalModal } from '../components/DraftApprovalModal';
import { styles } from '../styles';

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

  const theOne = theOneQ.data ?? null;
  const commitments: api.Commitment[] = commitmentsQ.data ?? [];
  const signals: any[] = signalsQ.data ?? [];

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
      Alert.alert('Error', 'Failed to generate draft. Is the backend running?');
    }
  };

  // Swipe handlers — bypass the Alert confirm for speed. Haptic is fired
  // in the card itself; the actual API call happens here.
  const handleSwipeComplete = async (signalId: string) => {
    if (!token || !signalId) return;
    try {
      await api.correctSignal(signalId, 'complete');
      LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
      qc.invalidateQueries({ queryKey: ['theOne'] });
      qc.invalidateQueries({ queryKey: ['commitments'] });
    } catch (e) { /* ignore — react-query will surface via stale data */ }
  };

  const handleSwipeDismiss = async (signalId: string) => {
    if (!token || !signalId) return;
    try {
      await api.correctSignal(signalId, 'dismiss');
      LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
      qc.invalidateQueries({ queryKey: ['theOne'] });
      qc.invalidateQueries({ queryKey: ['commitments'] });
    } catch (e) { /* ignore */ }
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
                    {c.deadline ? <Badge text={c.deadline} color="yellow" /> : null}
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
