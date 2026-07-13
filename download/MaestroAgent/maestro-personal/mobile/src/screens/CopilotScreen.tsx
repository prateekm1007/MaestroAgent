/**
 * CopilotScreen — extracted from the original App.tsx, unchanged in logic.
 *
 * Live meeting copilot with WebSocket whispers, optional audio capture
 * (expo-av), and a post-call summary modal. ConsentModal lives here too
 * because it is only ever rendered from this screen.
 */

import React, { useState, useRef } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, ScrollView, ActivityIndicator, Alert, Modal, SafeAreaView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { Audio } from 'expo-av';

import * as api from '../api/client';
import { colors, getTheme, spacing } from '../theme/colors';
import { useAuth, useTheme, useConsent } from '../contexts';
import { Card, TopBar } from '../components';
import { styles } from '../styles';

// ── Consent modal (only used by Copilot) ──────────────────────────────

function ConsentModal({ visible, onGrant, onDeny }: { visible: boolean; onGrant: () => void; onDeny: () => void }) {
  const t = getTheme('light');
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onDeny}>
      <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'center', padding: spacing.xxxl }}>
        <View style={{ backgroundColor: t.cardBg, borderRadius: 20, padding: spacing.xxl }}>
          <Text style={{ fontSize: 22, fontWeight: 'bold', color: t.textPrimary, marginBottom: spacing.md }}>
            🎙️ Recording Consent
          </Text>
          <Text style={{ fontSize: 15, color: t.textSecondary, lineHeight: 22, marginBottom: spacing.lg }}>
            Maestro Live Copilot will use your microphone to transcribe the meeting in real time.{'\n\n'}
            • Audio is recorded in 5-second segments{'\n'}
            • Each segment is uploaded to the Maestro server for transcription{'\n'}
            • Transcription is performed by the configured STT provider (Wit.ai/Whisper){'\n'}
            • Audio files are NOT stored — only the transcribed text is kept{'\n'}
            • All participants should be informed{'\n'}
            • You can revoke consent at any time{'\n'}
            • All actions are audit-logged
          </Text>
          <Text style={{ fontSize: 13, color: colors.alertRed, marginBottom: spacing.lg }}>
            ⚠️ Recording without consent may be illegal in your jurisdiction.
          </Text>
          <View style={{ flexDirection: 'row', gap: spacing.md }}>
            <TouchableOpacity
              onPress={onDeny}
              style={[styles.smallBtn, { backgroundColor: t.border, flex: 1 }]}
              accessibilityRole="button"
              accessibilityLabel="Not now — decline recording consent"
            >
              <Text style={{ color: t.textSecondary, fontWeight: '600' }}>Not Now</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={onGrant}
              style={[styles.smallBtn, { backgroundColor: colors.yellow, flex: 1 }]}
              accessibilityRole="button"
              accessibilityLabel="I consent to recording"
              accessibilityHint="Grants microphone recording consent for this call"
            >
              <Text style={{ color: colors.black, fontWeight: 'bold' }}>I Consent</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
}

// ── CopilotScreen ─────────────────────────────────────────────────────

export default function CopilotScreen() {
  const { mode } = useTheme();
  const t = getTheme(mode);
  const { token, llmStatus } = useAuth();
  const { hasConsent, grant } = useConsent();
  const [chunks, setChunks] = useState<{ speaker: string; text: string; ts: string }[]>([]);
  const [whispers, setWhispers] = useState<any[]>([]);
  const [input, setInput] = useState('');
  const [connected, setConnected] = useState(false);
  const [speaker, setSpeaker] = useState('me');
  const [showConsent, setShowConsent] = useState(false);
  const [recording, setRecording] = useState(false);
  const [wsRef, setWsRef] = useState<WebSocket | null>(null);
  const [showPostCall, setShowPostCall] = useState(false);
  const [postCallSummary, setPostCallSummary] = useState<any>(null);
  const transcriptRef = useRef<ScrollView>(null);

  // ── WebSocket connection ────────────────────────────────────────
  const connectWS = () => {
    if (!token) return;
    // Phase 4: WS URL derived from configured API host (not hardcoded)
    const apiHost = api.getHost();
    // Convert http://host → ws://host, https://host → wss://host
    const wsUrl = apiHost
      .replace(/^https:\/\//, 'wss://')
      .replace(/^http:\/\//, 'ws://') + '/ws/copilot';
    try {
      const ws = new WebSocket(wsUrl, ['maestro-auth']);
      ws.onopen = () => {
        ws.send(JSON.stringify({ type: 'auth', token }));
        setConnected(true);
        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
      };
      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          if (msg.type === 'ack') {
            // Ack whisper: transparent, auto-dismiss after 2s
            const ackWhisper = {
              type: 'ack',
              entity: '',
              text: '',
              evidence: [],
              confidence: 0,
              dismissAt: Date.now() + 2000,
            };
            setWhispers(prev => [...prev, ackWhisper]);
          } else if (msg.type === 'suggestion' || msg.type === 'whisper') {
            const newWhisper = {
              type: msg.priority === 'high' ? 'critical' : 'suggestion',
              entity: msg.entity || 'Maestro',
              text: msg.text || msg.body || '',
              evidence: msg.evidence_refs || [],
              confidence: msg.confidence || 0,
              dismissAt: msg.priority === 'high' ? 0 : Date.now() + 10000, // suggestions auto-dismiss after 10s, critical stays
            };
            setWhispers(prev => [...prev, newWhisper]);
            if (newWhisper.type === 'critical') {
              Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
            } else {
              Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
            }
          }
        } catch (err) { /* non-JSON message, ignore */ }
      };

      // Auto-dismiss timer for ack + suggestion whispers
      const dismissTimer = setInterval(() => {
        setWhispers(prev => {
          const now_ms = Date.now();
          const filtered = prev.filter(w => !w.dismissAt || w.dismissAt > now_ms);
          return filtered.length !== prev.length ? filtered : prev;
        });
      }, 1000);
      (ws as any)._dismissTimer = dismissTimer;
      ws.onclose = () => { setConnected(false); };
      ws.onerror = () => { setConnected(false); };
      setWsRef(ws);
    } catch (e) {
      // WS failed — fall back to REST
      setConnected(false);
    }
  };

  const disconnectWS = () => {
    if (wsRef) {
      if ((wsRef as any)._dismissTimer) clearInterval((wsRef as any)._dismissTimer);
      wsRef.close();
      setWsRef(null);
    }
    setConnected(false);
  };

  // ── Start meeting (with consent check) ──────────────────────────
  const startMeeting = () => {
    if (!hasConsent) {
      setShowConsent(true);
      return;
    }
    connectWS();
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
  };

  const endMeeting = async () => {
    disconnectWS();
    if (recording) { await stopRecording(); }
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);

    // Generate post-call summary from accumulated whispers + chunks
    const allCommitments = whispers
      .filter(w => w.evidence?.some((e: any) => e.type === 'commitment'))
      .map(w => ({ entity: w.entity, text: w.text }));
    const allSuggestions = whispers
      .filter(w => w.type === 'suggestion' || w.type === 'critical')
      .map(w => ({ entity: w.entity, text: w.text, priority: w.type, confidence: w.confidence }));
    const userChunks = chunks.filter(c => c.speaker === 'me').length;
    const otherChunks = chunks.filter(c => c.speaker !== 'me').length;
    const totalChunks = chunks.length;
    const talkRatio = totalChunks > 0 ? Math.round((userChunks / totalChunks) * 100) : 0;

    setPostCallSummary({
      total_chunks: totalChunks,
      talk_ratio: `${talkRatio}% you / ${100 - talkRatio}% them`,
      commitments: allCommitments,
      suggestions: allSuggestions,
      whispers_count: whispers.filter(w => w.type !== 'ack').length,
    });
    setShowPostCall(true);
  };

  // ── Audio recording with streaming STT ───────────────────────────
  // Phase 4: Instead of recording → stop → upload → get text (batch),
  // we record in 5-second intervals, upload each chunk immediately,
  // and show partial transcriptions in real time.
  const recordingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const chunkCounterRef = useRef(0);

  const startRecording = async () => {
    if (!hasConsent) { setShowConsent(true); return; }
    try {
      const { status } = await Audio.requestPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Permission Required', 'Microphone access is required for live transcription.');
        return;
      }
      await Audio.setAudioModeAsync({ allowsRecordingIOS: true, playsInSilentModeIOS: true });

      // Start first recording segment
      await startRecordingSegment();

      // Phase 4: Stream — every 5 seconds, stop current segment, upload for
      // transcription, start a new segment. This gives near-real-time STT.
      recordingIntervalRef.current = setInterval(async () => {
        await uploadAndRestartSegment();
      }, 5000);

      setRecording(true);
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    } catch (e) {
      Alert.alert('Recording Error', 'Failed to start recording. Falling back to text input.');
    }
  };

  const startRecordingSegment = async () => {
    try {
      const rec = new Audio.Recording();
      await rec.prepareToRecordAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY);
      await rec.startAsync();
      (global as any).__maestroRecording = rec;
    } catch (e) {
      console.warn('Segment start failed:', e);
    }
  };

  const uploadAndRestartSegment = async () => {
    const rec = (global as any).__maestroRecording as Audio.Recording;
    if (!rec) return;

    try {
      // Stop current segment
      await rec.stopAndUnloadAsync();
      const uri = rec.getURI();
      (global as any).__maestroRecording = null;

      // Upload for transcription (non-blocking — don't wait for response
      // before starting next segment, to minimize gap)
      if (uri && token) {
        chunkCounterRef.current += 1;
        const chunkNum = chunkCounterRef.current;
        const placeholderTs = new Date().toISOString();

        // Add placeholder immediately
        setChunks(prev => [...prev, { speaker: '🎤 Audio', text: `[Transcribing chunk ${chunkNum}…]`, ts: placeholderTs }]);

        // Upload in background
        transcribeSegment(uri, chunkNum, placeholderTs);

        // Start next segment immediately
        await startRecordingSegment();
      }
    } catch (e) {
      // Non-fatal — restart segment
      console.warn('Segment upload failed:', e);
      await startRecordingSegment();
    }
  };

  const transcribeSegment = async (uri: string, chunkNum: number, placeholderTs: string) => {
    try {
      const formData = new FormData();
      formData.append('file', { uri, type: 'audio/m4a', name: `chunk-${chunkNum}.m4a` } as any);
      const response = await fetch(`${api.getHost()}/api/copilot/transcribe`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData,
      });
      const result = await response.json();

      if (result.text && result.text.trim()) {
        const transcriptText = result.text.trim();
        // Replace the placeholder with actual transcription
        setChunks(prev => {
          const updated = [...prev];
          const idx = updated.findIndex(c => c.ts === placeholderTs);
          if (idx >= 0) {
            updated[idx] = { speaker: '🎤 Audio', text: transcriptText, ts: new Date().toISOString() };
          }
          return updated;
        });
        // Send through transcript pipeline for commitment detection
        try {
          const transcriptResult = await api.sendTranscriptChunk(transcriptText, 'audio', '');
          // If commitments detected, they'll arrive via WS as whispers
        } catch (e) { /* non-fatal */ }
      } else if (!result.configured) {
        setChunks(prev => {
          const updated = [...prev];
          const idx = updated.findIndex(c => c.ts === placeholderTs);
          if (idx >= 0) {
            updated[idx] = {
              speaker: '🎤 Audio',
              text: '[No transcription provider configured]',
              ts: new Date().toISOString(),
            };
          }
          return updated;
        });
      } else {
        // Remove placeholder if no text
        setChunks(prev => prev.filter(c => c.ts !== placeholderTs));
      }
    } catch (e) {
      setChunks(prev => {
        const updated = [...prev];
        const idx = updated.findIndex(c => c.ts === placeholderTs);
        if (idx >= 0) {
          updated[idx] = { speaker: '🎤 Audio', text: '[Upload failed]', ts: new Date().toISOString() };
        }
        return updated;
      });
    }
  };

  const stopRecording = async () => {
    // Clear the streaming interval
    if (recordingIntervalRef.current) {
      clearInterval(recordingIntervalRef.current);
      recordingIntervalRef.current = null;
    }

    try {
      // Upload the final segment
      const rec = (global as any).__maestroRecording as Audio.Recording;
      if (rec) {
        await rec.stopAndUnloadAsync();
        const uri = rec.getURI();
        (global as any).__maestroRecording = null;

        if (uri && token) {
          chunkCounterRef.current += 1;
          const chunkNum = chunkCounterRef.current;
          const placeholderTs = new Date().toISOString();
          setChunks(prev => [...prev, { speaker: '🎤 Audio', text: `[Transcribing chunk ${chunkNum}…]`, ts: placeholderTs }]);
          await transcribeSegment(uri, chunkNum, placeholderTs);
        }
      }

      setRecording(false);
      chunkCounterRef.current = 0;
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    } catch (e) { /* ignore */ }
  };

  // ── Send transcript chunk (WS or REST) ──────────────────────────
  const sendChunk = async () => {
    if (!input || !token) return;
    const chunk = { speaker, text: input, ts: new Date().toISOString() };
    setChunks(prev => [...prev, chunk]);
    setInput('');

    // Try WS first
    if (wsRef && wsRef.readyState === WebSocket.OPEN) {
      wsRef.send(JSON.stringify({ type: 'transcript', text: input, speaker, entity: '' }));
      return;
    }

    // Fall back to REST
    try {
      const result = await api.sendTranscriptChunk(input, speaker, '');
      const detected = result?.commitments_detected;
      if ((detected?.length ?? 0) > 0 && detected) {
        const newWhispers = detected.map((c: any) => ({
          type: 'suggestion',
          entity: c.entity || 'Commitment',
          text: c.text || c.action || '',
          evidence: [],
          confidence: 0.7,
        }));
        setWhispers(prev => [...prev, ...newWhispers]);
        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      }
    } catch (e) { /* ignore */ }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: t.bg }}>
      <TopBar title="Copilot" />

      {/* Consent modal */}
      <ConsentModal
        visible={showConsent}
        onGrant={() => { grant(); setShowConsent(false); Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success); }}
        onDeny={() => setShowConsent(false)}
      />

      {/* Connection banner */}
      <View style={{ padding: spacing.xl, flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: connected ? colors.honey : 'transparent' }}>
        <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: connected ? colors.successGreen : colors.gray }} />
        <Text
          style={{ color: t.textSecondary, fontSize: 13, flex: 1 }}
          accessibilityRole="text"
          accessibilityLabel={connected ? 'Live — WebSocket connected' : 'Offline REST mode'}
          accessibilityLiveRegion="polite"
        >
          {connected ? '🔴 Live — WebSocket connected' : 'Offline (REST mode)'}
        </Text>
        {hasConsent && (
          <Text
            style={{ color: colors.successGreen, fontSize: 11 }}
            accessibilityRole="text"
            accessibilityLabel="Consent granted"
          >✓ Consent</Text>
        )}
        <TouchableOpacity
          onPress={connected ? endMeeting : startMeeting}
          accessibilityRole="button"
          accessibilityLabel={connected ? 'End meeting' : 'Start meeting'}
          accessibilityHint={connected ? 'Ends the live copilot session' : 'Starts the live copilot session'}
        >
          <Text style={{ color: connected ? colors.alertRed : colors.yellow, fontSize: 13, fontWeight: '600' }}>
            {connected ? 'End' : 'Start'} Meeting
          </Text>
        </TouchableOpacity>
      </View>

      {/* Transcript */}
      <ScrollView
        ref={transcriptRef}
        style={{ flex: 1, paddingHorizontal: spacing.xl }}
        contentContainerStyle={{ paddingBottom: 100 }}
        onContentSizeChange={() => transcriptRef.current?.scrollToEnd({ animated: true })}
      >
        {chunks.length === 0 && (
          <View style={{ alignItems: 'center', marginTop: 60 }}>
            <Ionicons name="mic-outline" size={48} color={t.textSecondary} />
            <Text style={{ color: t.textSecondary, fontSize: 15, marginTop: spacing.md, textAlign: 'center' }}>
              {hasConsent ? 'Start a meeting or type to begin' : 'Grant consent to start recording'}
            </Text>
          </View>
        )}
        {chunks.map((c, i) => (
          <View key={i} style={{ alignSelf: c.speaker === 'me' ? 'flex-end' : 'flex-start', maxWidth: '80%', marginBottom: spacing.md }}>
            <View style={{
              backgroundColor: c.speaker === 'me' ? colors.yellow : t.surface,
              borderRadius: 16,
              borderBottomRightRadius: c.speaker === 'me' ? 4 : 16,
              borderBottomLeftRadius: c.speaker === 'me' ? 16 : 4,
              paddingHorizontal: spacing.lg,
              paddingVertical: spacing.md,
            }}>
              <Text style={{ color: c.speaker === 'me' ? colors.black : t.textPrimary, fontSize: 14 }}>{c.text}</Text>
            </View>
            <Text style={{ color: t.textSecondary, fontSize: 10, marginTop: 2, alignSelf: c.speaker === 'me' ? 'flex-end' : 'flex-start' }}>{c.speaker} · {c.ts.slice(11, 16)}</Text>
          </View>
        ))}
      </ScrollView>

      {/* Whispers overlay */}
      {whispers.length > 0 && (
        <View
          style={{ position: 'absolute', top: 120, right: spacing.xl, left: spacing.xl }}
          accessibilityLiveRegion="polite"
        >
          {whispers.filter(w => w.type !== 'ack').slice(-3).map((w, i) => (
            <Card key={i} accent={w.type === 'critical' ? 'red' : 'yellow'} style={{ marginBottom: spacing.sm, opacity: w.type === 'suggestion' ? 0.9 : 1 }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                <Text
                  style={{ fontSize: 14, fontWeight: 'bold', color: t.textPrimary }}
                  accessibilityRole="header"
                  accessibilityLabel={`Whisper from ${w.entity || 'Maestro'}`}
                >{w.entity || 'Maestro'}</Text>
                {w.confidence > 0 && (
                  <Text
                    style={{ fontSize: 10, color: t.textSecondary }}
                    accessibilityRole="text"
                    accessibilityLabel={`Confidence: ${Math.round(w.confidence * 100)} percent`}
                  >{Math.round(w.confidence * 100)}%</Text>
                )}
              </View>
              <Text
                style={{ fontSize: 13, color: t.textSecondary, marginTop: 2 }}
                accessibilityRole="text"
                accessibilityLabel={w.text}
              >{w.text}</Text>
              {w.evidence?.length > 0 && (
                <Text
                  style={{ fontSize: 11, color: colors.yellow, marginTop: 4 }}
                  accessibilityRole="text"
                  accessibilityLabel={`Evidence: ${w.evidence[0]?.entity || 'evidence'}`}
                >📌 {w.evidence[0]?.entity || 'evidence'}</Text>
              )}
            </Card>
          ))}
        </View>
      )}

      {/* Input bar with mic button */}
      <View style={{ flexDirection: 'row', paddingHorizontal: spacing.xl, paddingVertical: spacing.md, gap: spacing.sm, alignItems: 'center' }}>
        {/* Mic button */}
        <TouchableOpacity
          onPress={recording ? stopRecording : startRecording}
          style={{
            width: 44, height: 44, borderRadius: 22,
            backgroundColor: recording ? colors.alertRed : colors.yellow,
            alignItems: 'center', justifyContent: 'center',
          }}
          accessibilityRole="button"
          accessibilityLabel={recording ? 'Stop recording' : 'Start recording'}
          accessibilityHint={recording ? 'Stops audio recording and transcribes' : 'Starts audio recording (requires consent)'}
        >
          <Ionicons name={recording ? 'stop' : 'mic'} size={20} color={colors.black} />
        </TouchableOpacity>

        {/* Speaker toggle */}
        <TouchableOpacity
          onPress={() => setSpeaker(s => s === 'me' ? 'them' : 'me')}
          style={{ justifyContent: 'center' }}
          accessibilityRole="button"
          accessibilityLabel={`Speaker: ${speaker === 'me' ? 'Me' : 'Them'}`}
          accessibilityHint="Toggles between me and them speaker"
        >
          <Text style={{ color: speaker === 'me' ? colors.yellow : t.textSecondary, fontSize: 12 }}>{speaker === 'me' ? 'Me' : 'Them'}</Text>
        </TouchableOpacity>

        {/* Text input */}
        <TextInput
          style={{ flex: 1, backgroundColor: t.surface, borderRadius: 20, paddingHorizontal: spacing.lg, color: t.textPrimary, fontSize: 14 }}
          placeholder="Type or speak..."
          placeholderTextColor={t.textSecondary}
          value={input}
          onChangeText={setInput}
          onSubmitEditing={sendChunk}
          accessibilityLabel="Transcript input"
          accessibilityHint="Type a transcript chunk and send"
        />

        {/* Send button */}
        <TouchableOpacity
          onPress={sendChunk}
          style={{ justifyContent: 'center' }}
          accessibilityRole="button"
          accessibilityLabel="Send transcript chunk"
          accessibilityHint="Sends the typed text as a transcript chunk"
        >
          <Ionicons name="send" size={20} color={colors.yellow} />
        </TouchableOpacity>
      </View>

      {/* Post-call summary modal */}
      <Modal visible={showPostCall} animationType="slide" onRequestClose={() => setShowPostCall(false)}>
        <SafeAreaView style={{ flex: 1, backgroundColor: t.bg }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', padding: spacing.xl }}>
            <Text
              style={{ fontSize: 22, fontWeight: 'bold', color: t.textPrimary }}
              accessibilityRole="header"
              accessibilityLabel="Meeting summary"
            >Meeting Summary</Text>
            <TouchableOpacity
              onPress={() => { setShowPostCall(false); setChunks([]); setWhispers([]); }}
              accessibilityRole="button"
              accessibilityLabel="Close meeting summary"
            >
              <Ionicons name="close" size={24} color={t.textSecondary} />
            </TouchableOpacity>
          </View>
          <ScrollView style={{ flex: 1, paddingHorizontal: spacing.xl }} accessibilityLiveRegion="polite">
            {postCallSummary && (
              <>
                <Card style={{ marginBottom: spacing.lg }}>
                  <Text
                    style={{ fontSize: 13, color: t.textSecondary, marginBottom: spacing.sm }}
                    accessibilityRole="header"
                    accessibilityLabel="Talk ratio section"
                  >📊 TALK RATIO</Text>
                  <Text
                    style={{ fontSize: 18, fontWeight: 'bold', color: t.textPrimary }}
                    accessibilityRole="text"
                    accessibilityLabel={`Talk ratio: ${postCallSummary.talk_ratio}`}
                  >{postCallSummary.talk_ratio}</Text>
                  <Text
                    style={{ fontSize: 13, color: t.textSecondary, marginTop: spacing.xs }}
                    accessibilityRole="text"
                    accessibilityLabel={`${postCallSummary.total_chunks} transcript chunks`}
                  >{postCallSummary.total_chunks} transcript chunks</Text>
                </Card>
                <Card accent="yellow" style={{ marginBottom: spacing.lg }}>
                  <Text
                    style={{ fontSize: 13, color: colors.yellow, marginBottom: spacing.sm }}
                    accessibilityRole="header"
                    accessibilityLabel="Whispers generated section"
                  >⚡ WHISPERS GENERATED</Text>
                  <Text
                    style={{ fontSize: 28, fontWeight: 'bold', color: t.textPrimary }}
                    accessibilityRole="text"
                    accessibilityLabel={`${postCallSummary.whispers_count} whispers generated`}
                  >{postCallSummary.whispers_count}</Text>
                </Card>
                {postCallSummary.commitments.length > 0 && (
                  <Card accent="green" style={{ marginBottom: spacing.lg }}>
                    <Text
                      style={{ fontSize: 13, color: colors.successGreen, marginBottom: spacing.sm }}
                      accessibilityRole="header"
                      accessibilityLabel="Commitments detected section"
                    >✓ COMMITMENTS DETECTED</Text>
                    {postCallSummary.commitments.map((c: any, i: number) => (
                      <Text
                        key={i}
                        style={{ fontSize: 14, color: t.textPrimary, marginBottom: 4 }}
                        accessibilityRole="text"
                        accessibilityLabel={`Commitment from ${c.entity}: ${c.text?.slice(0, 60)}`}
                      >• {c.entity}: {c.text?.slice(0, 60)}</Text>
                    ))}
                  </Card>
                )}
                {postCallSummary.suggestions.length > 0 && (
                  <Card style={{ marginBottom: spacing.lg }}>
                    <Text
                      style={{ fontSize: 13, color: t.textSecondary, marginBottom: spacing.sm }}
                      accessibilityRole="header"
                      accessibilityLabel="Suggestions section"
                    >💡 SUGGESTIONS</Text>
                    {postCallSummary.suggestions.map((s: any, i: number) => (
                      <View key={i} style={{ marginBottom: 8 }}>
                        <Text
                          style={{ fontSize: 14, color: t.textPrimary }}
                          accessibilityRole="text"
                          accessibilityLabel={`Suggestion for ${s.entity}: ${s.text?.slice(0, 60)}`}
                        >• {s.entity}: {s.text?.slice(0, 60)}</Text>
                        <Text
                          style={{ fontSize: 11, color: t.textSecondary }}
                          accessibilityRole="text"
                          accessibilityLabel={`${s.priority} · ${Math.round((s.confidence || 0) * 100)} percent confidence`}
                        >{s.priority} · {Math.round((s.confidence || 0) * 100)}% confidence</Text>
                      </View>
                    ))}
                  </Card>
                )}
                {/* Follow-up email draft */}
                <Card accent="yellow" style={{ marginBottom: spacing.lg }}>
                  <Text
                    style={{ fontSize: 13, color: colors.yellow, marginBottom: spacing.sm }}
                    accessibilityRole="header"
                    accessibilityLabel="Follow-up email draft section"
                  >📧 FOLLOW-UP EMAIL DRAFT</Text>
                  <Text
                    style={{ fontSize: 13, color: t.textPrimary, lineHeight: 20 }}
                    accessibilityRole="text"
                    accessibilityLabel="Follow-up email draft. See screen for full text."
                  >
                    Hi {'{' + (chunks[0]?.speaker || 'team') + '}'},{'\n\n'}
                    Thank you for the meeting. Here are the commitments I'm tracking:{'\n'}
                    {postCallSummary.commitments.length > 0
                      ? postCallSummary.commitments.map((c: any) => `• ${c.entity}: ${c.text?.slice(0, 50)}`).join('\n')
                      : '• (none detected)'}{'\n\n'}
                    I'll follow up by end of week.{'\n\n'}
                    Best,{'\n'}[Your name]
                  </Text>
                </Card>
                <TouchableOpacity
                  style={[styles.loginButton, { backgroundColor: colors.yellow, marginBottom: spacing.xl }]}
                  onPress={() => { setShowPostCall(false); setChunks([]); setWhispers([]); }}
                  accessibilityRole="button"
                  accessibilityLabel="Save and close meeting summary"
                >
                  <Text style={{ color: colors.black, fontSize: 16, fontWeight: 'bold' }}>Save & Close</Text>
                </TouchableOpacity>
              </>
            )}
          </ScrollView>
        </SafeAreaView>
      </Modal>
    </SafeAreaView>
  );
}
