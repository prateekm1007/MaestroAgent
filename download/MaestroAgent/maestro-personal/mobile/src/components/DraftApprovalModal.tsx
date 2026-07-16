/**
 * DraftApprovalModal — 3-action approval modal for email/message drafts.
 *
 * Issue 7 / Step 5: Shows subject, body, provenance (grounded in), and
 * 3 buttons: Approve & Send, Use as Draft, Discard.
 */


import React from 'react';

import { View, Text, TouchableOpacity, Modal, ScrollView, StyleSheet, Share, Alert } from 'react-native';

import { colors, getTheme } from '../theme/colors';

import { useTheme } from '../contexts';

import * as api from '../api/client';

import * as Haptics from 'expo-haptics';
import { showAlert } from '../utils/alert';

export function DraftApprovalModal({ visible, draft, onClose }: {
  visible: boolean;
  draft: any;
  onClose: () => void;
}) {
  const { mode } = useTheme();
  const t = getTheme(mode);

  if (!draft) return null;

  const handleApprove = async () => {
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    try {
      await api.resolveDraft(draft.draft_id, 'approve');
      showAlert('Sent', 'Your email has been sent.');
      onClose();
    } catch (e) {
      showAlert('Error', 'Failed to send. Is Gmail connected?');
    }
  };

  const handleUseAsDraft = async () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      await Share.share({ message: draft.body || '' });
    } catch (e) { /* non-fatal */ }
    onClose();
  };

  const handleDiscard = async () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    try {
      await api.resolveDraft(draft.draft_id, 'deny');
    } catch (e) { /* non-fatal */ }
    onClose();
  };

  return (
    <Modal visible={visible} animationType="slide" transparent={false}>
      <ScrollView style={{ flex: 1, backgroundColor: t.bg, padding: 20 }}>
        <Text style={{ fontSize: 18, fontWeight: '800', color: t.textPrimary, marginBottom: 16 }}>
          📧 DRAFT
        </Text>
        <Text style={{ fontSize: 14, fontWeight: '600', color: t.textSecondary, marginBottom: 4 }}>
          Subject: {draft.subject || '(no subject)'}
        </Text>
        <View style={{ backgroundColor: t.surface, borderRadius: 12, padding: 16, marginBottom: 16 }}>
          <Text style={{ fontSize: 14, color: t.textPrimary, lineHeight: 22 }}>
            {draft.body || draft.draft_text || ''}
          </Text>
        </View>
        {draft.evidence_refs && draft.evidence_refs.length > 0 && (
          <View style={{ backgroundColor: colors.honey, borderRadius: 12, padding: 12, marginBottom: 16 }}>
            <Text style={{ fontSize: 11, fontWeight: '700', color: colors.yellowDark, marginBottom: 6 }}>
              📎 GROUNDED IN:
            </Text>
            {draft.evidence_refs.map((ref: any, i: number) => (
              <Text key={i} style={{ fontSize: 12, color: t.textPrimary, marginBottom: 4 }}>
                • "{ref.text || ref}" ({ref.entity || 'unknown'})
              </Text>
            ))}
          </View>
        )}
        <TouchableOpacity
          onPress={handleApprove}
          accessibilityLabel="Approve and send email"
          accessibilityRole="button"
          style={{ backgroundColor: colors.successGreen, paddingVertical: 14, borderRadius: 12, marginBottom: 8, alignItems: 'center' }}
        >
          <Text style={{ fontSize: 16, fontWeight: '700', color: colors.white }}>✅ Approve & Send</Text>
        </TouchableOpacity>
        <TouchableOpacity
          onPress={handleUseAsDraft}
          accessibilityLabel="Use as draft in mail app"
          accessibilityRole="button"
          style={{ backgroundColor: colors.yellow, paddingVertical: 14, borderRadius: 12, marginBottom: 8, alignItems: 'center' }}
        >
          <Text style={{ fontSize: 16, fontWeight: '700', color: colors.black }}>✏️ Use as Draft</Text>
        </TouchableOpacity>
        <TouchableOpacity
          onPress={handleDiscard}
          accessibilityLabel="Discard draft"
          accessibilityRole="button"
          style={{ backgroundColor: t.border, paddingVertical: 14, borderRadius: 12, alignItems: 'center' }}
        >
          <Text style={{ fontSize: 16, fontWeight: '600', color: t.textSecondary }}>❌ Discard</Text>
        </TouchableOpacity>
      </ScrollView>
    </Modal>
  );
}
