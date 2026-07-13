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

// ─── Default options (offline-friendly) ────────────────────────────

const defaultOptions = {
  staleTime: 30_000,       // 30s before refetch
  gcTime: 5 * 60_000,      // 5 min cache retention
  retry: 2,                 // retry failed requests
  retryDelay: 1000,         // 1s between retries
};

// ─── Hooks ─────────────────────────────────────────────────────────

export function useTheMoment() {
  return useQuery({
    queryKey: queryKeys.moment,
    queryFn: () => api.getTheMoment(),
    ...defaultOptions,
  });
}

export function useCommitments() {
  return useQuery({
    queryKey: queryKeys.commitments,
    queryFn: () => api.getCommitments(),
    ...defaultOptions,
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

export function useAsk() {
  return useMutation({
    mutationFn: (query: string) => api.ask(query),
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
