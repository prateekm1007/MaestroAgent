/**
 * Shared error/loading/empty state components.
 *
 * Phase 2: Every screen uses these for consistent UX.
 * - ErrorState: network error / 5xx / generic with retry button
 * - EmptyState: trusted silence / no data
 * - LoadingState: skeleton/spinner
 */

import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, getTheme } from '../theme/colors';

// ─── Error State ───────────────────────────────────────────────────

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  const t = getTheme('light');
  return (
    <View style={styles.center} accessibilityRole="alert" accessibilityLiveRegion="assertive">
      <Ionicons name="alert-circle" size={48} color={colors.alertRed} />
      <Text
        style={[styles.errorText, { color: t.textPrimary }]}
        accessibilityRole="text"
        accessibilityLabel={message}
      >{message}</Text>
      {onRetry && (
        <TouchableOpacity
          style={[styles.retryBtn, { borderColor: colors.yellow }]}
          onPress={onRetry}
          accessibilityRole="button"
          accessibilityLabel="Try again"
          accessibilityHint="Retries the failed operation"
        >
          <Text style={[styles.retryText, { color: colors.yellow }]}>Try Again</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

// ─── Empty State (Trusted Silence) ─────────────────────────────────

export function EmptyState({
  title = 'Nothing needs your attention right now.',
  subtitle = 'Maestro is watching quietly.',
  icon = 'moon',
}: {
  title?: string;
  subtitle?: string;
  icon?: string;
}) {
  const t = getTheme('light');
  return (
    <View style={styles.center} accessibilityRole="summary" accessibilityLiveRegion="polite">
      <Ionicons name={icon as any} size={48} color={colors.gray} />
      <Text
        style={[styles.emptyTitle, { color: t.textPrimary }]}
        accessibilityRole="header"
        accessibilityLabel={title}
      >{title}</Text>
      <Text
        style={[styles.emptySubtitle, { color: t.textSecondary }]}
        accessibilityRole="text"
        accessibilityLabel={subtitle}
      >{subtitle}</Text>
    </View>
  );
}

// ─── Loading State ─────────────────────────────────────────────────

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  const t = getTheme('light');
  return (
    <View style={styles.center} accessibilityRole="progressbar" accessibilityLiveRegion="polite">
      <ActivityIndicator size="large" color={colors.yellow} />
      <Text
        style={[styles.loadingText, { color: t.textSecondary }]}
        accessibilityRole="text"
        accessibilityLabel={label}
      >{label}</Text>
    </View>
  );
}

// ─── Offline Banner ────────────────────────────────────────────────

export function OfflineBanner() {
  return (
    <View
      style={styles.offlineBanner}
      accessibilityRole="alert"
      accessibilityLiveRegion="assertive"
      accessibilityLabel="Offline — showing cached data"
    >
      <Ionicons name="cloud-offline" size={16} color="#fff" />
      <Text style={styles.offlineText}>Offline — showing cached data</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingHorizontal: 32, paddingVertical: 48 },
  errorText: { fontSize: 16, textAlign: 'center', marginTop: 16, marginBottom: 16 },
  retryBtn: { borderWidth: 2, borderRadius: 8, paddingHorizontal: 24, paddingVertical: 10 },
  retryText: { fontSize: 15, fontWeight: '600' },
  emptyTitle: { fontSize: 18, fontWeight: '700', textAlign: 'center', marginTop: 16 },
  emptySubtitle: { fontSize: 14, textAlign: 'center', marginTop: 8 },
  loadingText: { fontSize: 14, marginTop: 12 },
  offlineBanner: { backgroundColor: colors.alertRed, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingVertical: 6 },
  offlineText: { color: '#fff', fontSize: 13, fontWeight: '500' },
});
