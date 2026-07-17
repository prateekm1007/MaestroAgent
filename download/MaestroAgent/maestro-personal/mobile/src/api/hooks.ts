/**
 * React Query hooks for data fetching + offline cache.
 *
 * Phase 2: All screens use these hooks instead of direct API calls.
 * Benefits:
 *  - stale-while-revalidate (instant cached data, background refresh)
 *  - offline support (cached data shows when network fails)
 *  - automatic retry on network recovery
 *  - consistent loading/error states
 *
 * Usage in screens:
 *   const { data, isLoading, error, refetch } = useTheMoment();
 *   if (isLoading) return <LoadingState />;
 *   if (error) return <ErrorState message="..." onRetry={refetch} />;
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as api from './client';

// ─── Query Keys ────────────────────────────────────────────────────

export const queryKeys = {
  moment: ['moment'] as const,
  commitments: ['commitments'] as const,
  theOne: ['theOne'] as const,
  signals: ['signals'] as const,
  whatChanged: ['whatChanged'] as const,
  shifts: ['shifts'] as const,
  briefing: ['briefing'] as const,
  llmStatus: ['llmStatus'] as const,
  privacyMode: ['privacyMode'] as const,
  calibration: ['calibration'] as const,
  auditLog: ['auditLog'] as const,
  metrics: ['metrics'] as const,
};

// ─── Default options (offline-friendly + background sync) ──────────

const defaultOptions = {
  staleTime: 30_000,       // 30s before refetch
  gcTime: 5 * 60_000,      // 5 min cache retention
  retry: 2,                 // retry failed requests
  retryDelay: 1000,         // 1s between retries
  refetchOnWindowFocus: true,  // sync when app comes to foreground
  refetchOnReconnect: true,    // sync when network reconnects
};

// Critical data: refresh every 60s in background
const backgroundSyncOptions = {
  ...defaultOptions,
  refetchInterval: 60_000,  // poll every 60s
};

// ─── Hooks ─────────────────────────────────────────────────────────

export function useTheMoment() {
  return useQuery({
    queryKey: queryKeys.moment,
    queryFn: () => api.getTheMoment(),
    ...backgroundSyncOptions, // critical — refresh every 60s
  });
}

export function useCommitments() {
  return useQuery({
    queryKey: queryKeys.commitments,
    queryFn: () => api.getCommitments(),
    ...backgroundSyncOptions, // critical — refresh every 60s
  });
}

export function useTheOne() {
  return useQuery({
    queryKey: queryKeys.theOne,
    queryFn: () => api.getTheOne(),
    ...defaultOptions,
  });
}

export function useSignals() {
  return useQuery({
    queryKey: queryKeys.signals,
    queryFn: () => api.getSignals(),
    ...defaultOptions,
  });
}

export function useWhatChanged() {
  return useQuery({
    queryKey: queryKeys.whatChanged,
    queryFn: () => api.getWhatChanged(),
    ...defaultOptions,
  });
}

export function useShifts() {
  return useQuery({
    queryKey: queryKeys.shifts,
    queryFn: () => api.getWhatChangedShifts(),
    ...defaultOptions,
  });
}

export function useBriefing() {
  return useQuery({
    queryKey: queryKeys.briefing,
    queryFn: () => api.getBriefing(),
    ...defaultOptions,
  });
}

export function useLLMStatus() {
  return useQuery({
    queryKey: queryKeys.llmStatus,
    queryFn: () => api.getLLMStatus(),
    staleTime: 60_000, // 1 min (LLM status doesn't change often)
  });
}

export function usePrivacyMode() {
  return useQuery({
    queryKey: queryKeys.privacyMode,
    queryFn: () => api.getPrivacyMode(),
    staleTime: 60_000,
  });
}

export function useCalibration() {
  return useQuery({
    queryKey: queryKeys.calibration,
    queryFn: () => api.getCalibration(),
    staleTime: 60_000,
  });
}

export function useAuditLog() {
  return useQuery({
    queryKey: queryKeys.auditLog,
    queryFn: () => api.getAuditLog(),
    staleTime: 10_000,
  });
}

export function useMetrics() {
  return useQuery({
    queryKey: queryKeys.metrics,
    queryFn: () => api.getMetrics(),
    staleTime: 30_000,
  });
}

// ─── Mutations ─────────────────────────────────────────────────────

export function useCreateSignal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ entity, text, signal_type }: { entity: string; text: string; signal_type: string }) =>
      api.createSignal(entity, text, signal_type),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.signals });
      qc.invalidateQueries({ queryKey: queryKeys.moment });
      qc.invalidateQueries({ queryKey: queryKeys.commitments });
      qc.invalidateQueries({ queryKey: queryKeys.whatChanged });
    },
  });
}

export function useAsk(sessionId?: string) {
  return useMutation({
    mutationFn: (query: string) => api.ask(query, sessionId),
  });
}

export function useDeleteAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.deleteAccount(),
    onSuccess: () => qc.clear(),
  });
}

export function useExportData() {
  return useMutation({
    mutationFn: () => api.exportData(),
  });
}

// ─── Ambient Intelligence Hooks (Phases 9, 11, 14, 16, 19, 20) ────

// Phase 19: Smart notifications — poll every 60s (critical for ambient awareness)
export function useSmartNotifications(context: api.SmartNotificationContext = {}) {
  return useQuery({
    queryKey: ['smartNotifications', context] as const,
    queryFn: () => api.getSmartNotifications(context),
    ...backgroundSyncOptions,
  });
}

// Phase 9: Commitment escalations — poll every 60s (overdue detection is time-sensitive)
export function useEscalations() {
  return useQuery({
    queryKey: ['escalations'] as const,
    queryFn: () => api.getEscalations(),
    ...backgroundSyncOptions,
  });
}

// Phase 9: Calendar awareness — refresh every 5 min (meetings don't change often)
export function useCalendarAwareness(hoursAhead: number = 48) {
  return useQuery({
    queryKey: ['calendarAwareness', hoursAhead] as const,
    queryFn: () => api.getCalendarAwareness(hoursAhead),
    ...defaultOptions,
  });
}

// Phase 11: Deal health — refresh every 5 min
export function useDealHealth() {
  return useQuery({
    queryKey: ['dealHealth'] as const,
    queryFn: () => api.getDealHealth(),
    ...defaultOptions,
  });
}

// Phase 14: Cross-meeting threads — refresh every 5 min
export function useThreads(entityFilter: string = '') {
  return useQuery({
    queryKey: ['threads', entityFilter] as const,
    queryFn: () => api.getThreads(entityFilter),
    ...defaultOptions,
  });
}

export function useThreadsForEntity(entity: string | null) {
  return useQuery({
    queryKey: ['threadsForEntity', entity] as const,
    queryFn: () => api.getThreadsForEntity(entity!),
    enabled: !!entity,
    ...defaultOptions,
  });
}

// Phase 16: Meeting grades — refresh every 5 min
export function useMeetingGrades() {
  return useQuery({
    queryKey: ['meetingGrades'] as const,
    queryFn: () => api.getMeetingGrades(),
    ...defaultOptions,
  });
}

// Phase 20: Advanced analytics — refresh every 5 min
export function useAnalyticsTrends() {
  return useQuery({
    queryKey: ['analyticsTrends'] as const,
    queryFn: () => api.getAnalyticsTrends(),
    ...defaultOptions,
  });
}

export function useAnalyticsFlywheel() {
  return useQuery({
    queryKey: ['analyticsFlywheel'] as const,
    queryFn: () => api.getAnalyticsFlywheel(),
    ...defaultOptions,
  });
}

// Phase 16: Meeting grade override mutation
export function useOverrideMeetingGrade() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ meetingId, grade }: { meetingId: string; grade: string }) =>
      api.overrideMeetingGrade(meetingId, grade),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['meetingGrades'] });
    },
  });
}
