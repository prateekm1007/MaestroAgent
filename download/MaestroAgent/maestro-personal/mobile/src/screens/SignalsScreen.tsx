/**
 * SignalsScreen — extracted from the original App.tsx.
 *
 * Phase 2: data fetching now goes through react-query hooks
 * (useSignals / useCreateSignal) instead of manual useEffect+useState.
 * Loading/error/empty states use the shared components from
 * src/components/ErrorState.tsx. The `useCreateSignal` mutation
 * invalidates the `signals` query (per src/api/hooks.ts) so the list
 * auto-refreshes after a successful add.
 *
 * UI/logic is otherwise unchanged.
 */

import React, { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, FlatList, Modal, SafeAreaView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import * as api from '../api/client';
import { useSignals, useCreateSignal } from '../api/hooks';
import { colors, getTheme, spacing, radius } from '../theme/colors';
import { useAuth, useTheme } from '../contexts';
import { Card, Badge, TopBar } from '../components';
import { ErrorState, LoadingState, EmptyState } from '../components/ErrorState';
import { styles } from '../styles';

export default function SignalsScreen() {
  const { mode } = useTheme();
  const t = getTheme(mode);
  const { token } = useAuth();
  const [showAdd, setShowAdd] = useState(false);
  const [entity, setEntity] = useState('');
  const [text, setText] = useState('');
  const [type, setType] = useState('reported_statement');

  // ── react-query hooks (replace manual useEffect + useState) ────────
  const signalsQ = useSignals();
  const createSignalMut = useCreateSignal();

  const signals: api.Signal[] = signalsQ.data ?? [];

  const handleAdd = () => {
    if (!entity || !text || !token) return;
    createSignalMut.mutate(
      { entity, text, signal_type: type },
      {
        onSuccess: () => {
          setEntity(''); setText(''); setType('reported_statement');
          setShowAdd(false);
        },
        onError: () => {
          // Surface error in the modal — keep the user's draft.
          // (Falls back to non-fatal: list still shows cached data.)
        },
      }
    );
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: t.bg }}>
      <TopBar title="Signals" />
      {signalsQ.isLoading ? (
        <LoadingState label="Loading signals…" />
      ) : signalsQ.error ? (
        <ErrorState message="Couldn't load signals." onRetry={() => signalsQ.refetch()} />
      ) : (
        <FlatList
          data={signals}
          keyExtractor={item => item.signal_id}
          contentContainerStyle={{ padding: spacing.xl }}
          renderItem={({ item }) => (
            <Card style={{ marginBottom: spacing.md }}>
              <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                <Text style={{ fontSize: 15, fontWeight: 'bold', color: t.textPrimary, flex: 1 }}>{item.entity}</Text>
                <Text style={{ fontSize: 11, color: t.textSecondary }}>{item.timestamp?.slice(0, 10)}</Text>
              </View>
              <Text style={{ fontSize: 13, color: t.textSecondary, marginTop: spacing.xs }} numberOfLines={2}>{item.text}</Text>
              <View style={{ flexDirection: 'row', marginTop: spacing.xs, gap: spacing.sm }}>
                <Badge text={item.signal_type} color="gray" />
              </View>
            </Card>
          )}
          ListEmptyComponent={
            <EmptyState
              title="No signals yet"
              subtitle="Tap + to add one."
              icon="radar-outline"
            />
          }
        />
      )}

      {/* FAB */}
      <TouchableOpacity
        style={[styles.fab, { backgroundColor: colors.yellow }]}
        onPress={() => setShowAdd(true)}
      >
        <Ionicons name="add" size={28} color={colors.black} />
      </TouchableOpacity>

      {/* Add Modal */}
      <Modal visible={showAdd} animationType="slide" transparent>
        <View style={{ flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(0,0,0,0.5)' }}>
          <View style={{ backgroundColor: t.bg, borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: spacing.xl }}>
            <Text style={{ fontSize: 18, fontWeight: 'bold', color: t.textPrimary, marginBottom: spacing.lg }}>Add Signal</Text>
            <TextInput style={[styles.loginInput, { backgroundColor: t.surface, color: t.textPrimary, marginBottom: spacing.md }]} placeholder="Entity" placeholderTextColor={t.textSecondary} value={entity} onChangeText={setEntity} />
            <TextInput style={[styles.loginInput, { backgroundColor: t.surface, color: t.textPrimary, marginBottom: spacing.md, minHeight: 80 }]} placeholder="What happened?" placeholderTextColor={t.textSecondary} value={text} onChangeText={setText} multiline />
            <View style={{ flexDirection: 'row', gap: spacing.md, marginBottom: spacing.lg }}>
              {['reported_statement', 'commitment_made', 'follow_up_required'].map(typ => (
                <TouchableOpacity key={typ} onPress={() => setType(typ)} style={{ paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.full, backgroundColor: type === typ ? colors.yellow : t.surface }}>
                  <Text style={{ color: type === typ ? colors.black : t.textSecondary, fontSize: 12 }}>{typ.replace(/_/g, ' ')}</Text>
                </TouchableOpacity>
              ))}
            </View>
            {createSignalMut.isError ? (
              <Text style={{ color: colors.alertRed, fontSize: 13, marginBottom: spacing.md }}>Failed to create signal. Please try again.</Text>
            ) : null}
            <View style={{ flexDirection: 'row', gap: spacing.md }}>
              <TouchableOpacity style={[styles.loginButton, { flex: 1, backgroundColor: t.border }]} onPress={() => setShowAdd(false)}>
                <Text style={{ color: t.textSecondary, fontWeight: 'bold' }}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.loginButton, { flex: 1, backgroundColor: colors.yellow, opacity: !entity || !text || createSignalMut.isPending ? 0.5 : 1 }]}
                onPress={handleAdd}
                disabled={!entity || !text || createSignalMut.isPending}
              >
                <Text style={{ color: colors.black, fontWeight: 'bold' }}>{createSignalMut.isPending ? 'Adding…' : 'Add'}</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}
