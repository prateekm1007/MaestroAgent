/**
 * OnboardingScreen — 3-screen first-launch flow.
 *
 * Phase 2: New users see this before login.
 *   1. Why Maestro — the value proposition
 *   2. How it works — The Moment + Ask + Copilot
 *   3. Get started — connect to login
 *
 * On finish, calls completeOnboarding() which persists to AsyncStorage.
 */

import React, { useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, getTheme } from '../theme/colors';
import { useOnboarding } from '../contexts';

export default function OnboardingScreen() {
  const { completeOnboarding } = useOnboarding();
  const [step, setStep] = useState(0);
  const t = getTheme('light');

  const steps = [
    {
      icon: 'flash' as const,
      title: 'Maestro remembers\nwhat you promised',
      body: 'Every commitment you make — in email, Slack, or meetings — becomes a signal. Maestro surfaces the one thing that needs your attention right now.',
      cta: 'Next',
    },
    {
      icon: 'search' as const,
      title: 'Ask Maestro anything',
      body: 'Every answer cites the exact source sentence, entity, and timestamp. Not a hallucination — your own evidence, retrieved and verified.',
      cta: 'Next',
    },
    {
      icon: 'chatbubbles' as const,
      title: 'Live Copilot during calls',
      body: 'Maestro listens (with consent), detects commitments in real time, and whispers what matters — grounded in your organizational memory.',
      cta: 'Get Started',
    },
  ];

  const current = steps[step];
  const isLast = step === steps.length - 1;

  const handleNext = () => {
    if (isLast) {
      completeOnboarding();
    } else {
      setStep(s => s + 1);
    }
  };

  return (
    <ScrollView style={[styles.container, { backgroundColor: t.bg }]} contentContainerStyle={styles.content}>
      {/* Progress dots */}
      <View style={styles.dots} accessibilityRole="tablist" accessibilityLabel="Onboarding progress">
        {steps.map((_, i) => (
          <View
            key={i}
            style={[styles.dot, i === step && styles.dotActive]}
            accessibilityRole="text"
            accessibilityLabel={`Step ${i + 1} of ${steps.length}${i === step ? ', current' : ''}`}
          />
        ))}
      </View>

      {/* Icon */}
      <View style={[styles.iconCircle, { backgroundColor: colors.honey }]} accessibilityRole="image" accessibilityLabel={`Onboarding step icon: ${current.icon}`}>
        <Ionicons name={current.icon} size={48} color={colors.black} />
      </View>

      {/* Title */}
      <Text
        style={[styles.title, { color: t.textPrimary }]}
        accessibilityRole="header"
        accessibilityLabel={current.title.replace(/\n/g, ' ')}
      >{current.title}</Text>

      {/* Body */}
      <Text
        style={[styles.body, { color: t.textSecondary }]}
        accessibilityRole="text"
        accessibilityLabel={current.body}
      >{current.body}</Text>

      {/* CTA */}
      <TouchableOpacity
        style={[styles.cta, { backgroundColor: colors.yellow }]}
        onPress={handleNext}
        accessibilityRole="button"
        accessibilityLabel={isLast ? 'Get started' : 'Next onboarding step'}
        accessibilityHint={isLast ? 'Completes onboarding and proceeds to login' : 'Advances to the next onboarding step'}
      >
        <Text style={styles.ctaText}>{current.cta}</Text>
      </TouchableOpacity>

      {/* Skip */}
      {!isLast && (
        <TouchableOpacity
          onPress={completeOnboarding}
          style={styles.skip}
          accessibilityRole="button"
          accessibilityLabel="Skip onboarding"
          accessibilityHint="Skips the rest of onboarding and proceeds to login"
        >
          <Text style={[styles.skipText, { color: t.textSecondary }]}>Skip</Text>
        </TouchableOpacity>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 32, paddingBottom: 60 },
  dots: { flexDirection: 'row', gap: 8, marginBottom: 48 },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: '#ccc' },
  dotActive: { backgroundColor: colors.yellow, width: 24 },
  iconCircle: { width: 96, height: 96, borderRadius: 48, justifyContent: 'center', alignItems: 'center', marginBottom: 32 },
  title: { fontSize: 28, fontWeight: '900', textAlign: 'center', marginBottom: 16, lineHeight: 36 },
  body: { fontSize: 16, textAlign: 'center', lineHeight: 24, marginBottom: 48 },
  cta: { width: '100%', paddingVertical: 16, borderRadius: 12, alignItems: 'center' },
  ctaText: { color: colors.black, fontSize: 17, fontWeight: '700' },
  skip: { marginTop: 16 },
  skipText: { fontSize: 15 },
});
