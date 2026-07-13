/**
 * Shared view-layer types for the Maestro Personal mobile app.
 *
 * The API response types live in `./api/client` (we are NOT allowed to
 * modify that file). This module re-exports them so screens have a single
 * import point for shared types, plus a couple of view-only types
 * (ConsentModalProps) that don't belong on the API surface.
 */

export type {
  Situation,
  Signal,
  Commitment,
  AskResult,
  WhatChangedItem,
  WhatChangedShift,
  WhatChangedMasterpiece,
  PrepareItem,
  LoginResult,
  LLMStatus,
  Briefing,
  TheOneResult,
  PrivacyMode,
  Calibration,
  AuditLogEntry,
  AuditLogResponse,
  Metrics,
  SignalCorrectionResult,
  TranscriptCommitment,
  TranscriptChunkResult,
  TheMoment,
  WhisperItem,
  GmailSyncResult,
} from './api/client';

export type { ThemeMode, Theme } from './theme/colors';
