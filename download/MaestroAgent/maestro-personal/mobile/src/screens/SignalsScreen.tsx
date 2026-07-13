/**
 * SignalsScreen — extracted from the original App.tsx, unchanged in logic.
 *
 * FlatList of all signals with a floating + button. The + opens a modal
 * sheet that posts a new signal via POST /api/signals.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, FlatList, ActivityIndicator, Alert, Modal, SafeAreaView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import * as api from '../api/client';
import { colors, getTheme, spacing, radius } from '../theme/colors';
import { useAuth, useTheme } from '../contexts';
import { Card, Badge, TopBar } from '../components';
import { styles } from '../styles';

export default function SignalsScreen() {
  const { mode } = useTheme();
  const t = getTheme(mode);
  const { token } = useAuth();
  const [signals, setSignals] = useState<api.Signal[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [entity, setEntity] = useState('');
  const [text, setText] = useState('');
  const [type, setType] = useState('reported_statement');

  const load = useCallback(async () => {
    if (!token) return;
    try { setSignals(await api.getSignals()); } catch (e) { /* ignore */ }
    setLoading(false);
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const handleAdd = async () => {
    if (!entity || !text || !token) return;
    try {
      await api.createSignal(entity, text, type);
      setEntity(''); setText(''); setType('reported_statement');
      setShowAdd(false);
      load();
    } catch (e) { Alert.alert('Error', 'Failed to create signal'); }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: t.bg }}>
      <TopBar title="Signals" />
      {loading ? (
        <ActivityIndicator color={colors.yellow} size="large" style={{ marginVertical: 40 }} />
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
          ListEmptyComponent={<Text style={{ color: t.textSecondary, textAlign: 'center', marginTop: 40 }}>No signals yet. Tap + to add one.</Text>}
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
            <View style={{ flexDirection: 'row', gap: spacing.md }}>
              <TouchableOpacity style={[styles.loginButton, { flex: 1, backgroundColor: t.border }]} onPress={() => setShowAdd(false)}>
                <Text style={{ color: t.textSecondary, fontWeight: 'bold' }}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[styles.loginButton, { flex: 1, backgroundColor: colors.yellow, opacity: !entity || !text ? 0.5 : 1 }]} onPress={handleAdd} disabled={!entity || !text}>
                <Text style={{ color: colors.black, fontWeight: 'bold' }}>Add</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}
