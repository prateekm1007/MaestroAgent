/**
 * AddSignal screen — manual signal entry for v1 dogfood.
 *
 * Form: entity, text, type → POST /api/signals
 *
 * In v1 (dogfood), users manually enter signals instead of connecting
 * Gmail/Calendar. This lets us test the thesis without OAuth wiring.
 */

import React, { useState } from 'react';
import { View, Text, TextInput, Button, StyleSheet, Alert, ScrollView } from 'react-native';
import { useAuth } from '../api/auth';
import { createSignal } from '../api/client';

const SIGNAL_TYPES = [
  { label: 'Commitment Made', value: 'commitment_made' },
  { label: 'Reported Statement', value: 'reported_statement' },
  { label: 'Observed Fact', value: 'observed_fact' },
  { label: 'Calendar Change', value: 'calendar_change' },
  { label: 'Meeting Scheduled', value: 'meeting.scheduled' },
  { label: 'Meeting Moved', value: 'meeting.moved' },
  { label: 'Follow Up Required', value: 'follow_up.required' },
  { label: 'Personal Promise', value: 'personal.promise' },
  { label: 'Deadline Approaching', value: 'deadline.approaching' },
];

export default function AddSignalScreen({ navigation }: { navigation: any }) {
  const { token } = useAuth();
  const [entity, setEntity] = useState('');
  const [text, setText] = useState('');
  const [signalType, setSignalType] = useState('commitment_made');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    if (!entity.trim() || !text.trim() || !token) return;
    setLoading(true);
    try {
      await createSignal(token, entity, text, signalType);
      Alert.alert('Success', 'Signal added', [{ text: 'OK', onPress: () => navigation.goBack() }]);
    } catch (e) {
      Alert.alert('Error', String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <ScrollView style={styles.container} keyboardShouldPersistTaps="handled">
      <Text style={styles.title}>Add Signal</Text>
      <Text style={styles.label}>Entity (who is this about?)</Text>
      <TextInput
        style={styles.input}
        placeholder="e.g., Alex"
        value={entity}
        onChangeText={setEntity}
      />

      <Text style={styles.label}>What happened?</Text>
      <TextInput
        style={[styles.input, styles.textArea]}
        placeholder="e.g., I will send the proposal by Friday"
        value={text}
        onChangeText={setText}
        multiline
        numberOfLines={3}
      />

      <Text style={styles.label}>Signal Type</Text>
      <View style={styles.pickerContainer}>
        {SIGNAL_TYPES.map((t) => (
          <Text
            key={t.value}
            style={[styles.pickerItem, signalType === t.value && styles.pickerItemSelected]}
            onPress={() => setSignalType(t.value)}
          >
            {t.label}
          </Text>
        ))}
      </View>

      <Button title={loading ? 'Adding...' : 'Add Signal'} onPress={handleSubmit} disabled={loading || !entity.trim() || !text.trim()} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 16, backgroundColor: '#f5f4f3' },
  title: { fontSize: 24, fontWeight: 'bold', marginBottom: 16, color: '#1b1a18' },
  label: { fontSize: 14, fontWeight: 'bold', marginTop: 12, marginBottom: 4, color: '#64593a' },
  input: { borderWidth: 1, borderColor: '#bfbaac', borderRadius: 8, padding: 12, fontSize: 16, backgroundColor: '#fff' },
  textArea: { minHeight: 80, textAlignVertical: 'top' },
  pickerContainer: { borderWidth: 1, borderColor: '#bfbaac', borderRadius: 8, backgroundColor: '#fff', marginBottom: 16, overflow: 'hidden' },
  pickerItem: { padding: 12, fontSize: 14, color: '#1b1a18', borderBottomWidth: 1, borderBottomColor: '#ecebe9' },
  pickerItemSelected: { backgroundColor: '#897128', color: '#fff', fontWeight: 'bold' },
});
