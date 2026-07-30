import type { Commitment, LayoutMode } from './types'

/**
 * Calculate importance score (0-100) for a commitment.
 * Based on: time urgency, blocking status, confidence, importance level.
 */
export function calculateImportance(commitment: Commitment): number {
  let score = 0

  // Time urgency (0-40 points)
  const now = new Date()
  const due = new Date(commitment.dueDate)
  const hoursUntilDue = (due.getTime() - now.getTime()) / (1000 * 60 * 60)

  if (hoursUntilDue < 0) score += 40 // Overdue
  else if (hoursUntilDue < 1) score += 40 // Critical
  else if (hoursUntilDue < 4) score += 30 // Urgent
  else if (hoursUntilDue < 24) score += 20 // Soon
  else if (hoursUntilDue < 72) score += 10 // This week
  // else: 0 (low urgency)

  // Blocking others (0-30 points)
  if (commitment.isBlocking) score += 30

  // Confidence (0-15 points)
  if (commitment.confidence > 0.9) score += 15
  else if (commitment.confidence > 0.7) score += 10

  // Importance (0-15 points)
  if (commitment.importance === 'high') score += 15
  else if (commitment.importance === 'medium') score += 8

  return Math.min(score, 100)
}

/**
 * Determine the layout mode based on importance score.
 */
export function getLayoutMode(score: number): LayoutMode {
  if (score >= 80) return 'dominant'
  if (score >= 50) return 'prominent'
  if (score >= 20) return 'present'
  if (score >= 1) return 'quiet'
  return 'empty'
}

/**
 * Get hours until due, formatted for display.
 * F-3 fix (auditor v12): never show "0 hours overdue" or "NaN" for
 * future/empty deadlines. If the due date is missing or invalid,
 * return empty string (no false urgency). If the deadline is in the
 * future, show "Due in X" — never "X hours overdue".
 */
export function formatTimeUntil(dueDate: string): string {
  if (!dueDate || dueDate.trim() === '') return ''

  const now = new Date()
  const due = new Date(dueDate)
  if (isNaN(due.getTime())) return ''  // invalid date — don't show false urgency

  const hours = (due.getTime() - now.getTime()) / (1000 * 60 * 60)
  if (isNaN(hours)) return ''

  // Phase 1 fix (auditor v17): kill "0 hours overdue" on future items.
  // The prior code would show "0 hours overdue" when hours was between
  // -1 and 0 (just barely past due). Fix: if abs(hours) < 1, show
  // "Due in N minutes" or "Just now" — never "0 hours overdue".
  if (hours >= 0) {
    // Future deadline — show "Due in X"
    if (hours < 1) return `Due in ${Math.floor(hours * 60)} minutes`
    if (hours < 4) return `Due in ${Math.floor(hours)} hours`
    if (hours < 24) return `Due today`
    if (hours < 48) return `Due tomorrow`
    return `Due in ${Math.floor(hours / 24)} days`
  } else {
    // Past deadline — show "X overdue"
    const daysOverdue = Math.abs(hours) / 24
    if (daysOverdue > 1) return `${Math.floor(daysOverdue)} days overdue`
    const absHours = Math.floor(Math.abs(hours))
    if (absHours === 0) return `Just now overdue`  // was "0 hours overdue"
    return `${absHours} hours overdue`
  }
}

/**
 * Get confidence styling based on score.
 * Tufte: let confidence influence visual hierarchy, not just display.
 */
export function getConfidenceStyle(confidence: number) {
  if (confidence >= 0.9) {
    return {
      color: '#059669', // green
      bgColor: '#ECFDF5',
      label: 'High confidence',
      language: 'assertive' as const, // "Yes."
    }
  }
  if (confidence >= 0.7) {
    return {
      color: '#D97706', // amber
      bgColor: '#FFFBEB',
      label: 'Moderate confidence',
      language: 'qualified' as const, // "Probably."
    }
  }
  return {
    color: '#6B7280', // gray
    bgColor: '#F9FAFB',
    label: 'Low confidence',
    language: 'uncertain' as const, // "I'm not confident, but..."
  }
}

/**
 * Get confidence language prefix.
 */
export function getConfidencePrefix(confidence: number): string {
  if (confidence >= 0.9) return 'Yes.'
  if (confidence >= 0.7) return 'Probably.'
  return "I'm not fully confident, but"
}
