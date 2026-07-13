/**
 * Shared UI components for the Maestro Personal mobile app.
 *
 * ThemedView, Card, Badge, ConfidenceBar, LLMDot, TopBar — extracted
 * verbatim from the original App.tsx so every screen renders the same
 * card / badge / top-bar treatment. Theme + Auth hooks come from
 * `./contexts`; raw color tokens come from `./theme/colors`.
 */

import React from 'react';
import { View, Text, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { colors, getTheme, spacing, radius, typography } from './theme/colors';
import { useTheme, useAuth } from './contexts';
import { styles } from './styles';

export function ThemedView({ children, style }: { children: React.ReactNode; style?: any }) {
  const { mode } = useTheme();
  const t = getTheme(mode);
  return <View style={[{ backgroundColor: t.bg }, style]}>{children}</View>;
}

export function Card({ children, style, accent }: { children: React.ReactNode; style?: any; accent?: 'yellow' | 'red' | 'green' | null }) {
  const { mode } = useTheme();
  const t = getTheme(mode);
  const borderLeftColor = accent === 'yellow' ? t.yellow : accent === 'red' ? t.danger : accent === 'green' ? t.success : 'transparent';
  return (
    <View style={[styles.card, { backgroundColor: t.cardBg, borderLeftColor, borderLeftWidth: accent ? 4 : 0 }, style]}>
      {children}
    </View>
  );
}

export function Badge({ text, color = 'gray' }: { text: string; color?: 'gray' | 'yellow' | 'red' | 'green' }) {
  const { mode } = useTheme();
  const t = getTheme(mode);
  const bg = color === 'yellow' ? colors.yellow + '22' : color === 'red' ? colors.alertRed + '22' : color === 'green' ? colors.successGreen + '22' : t.border;
  const fg = color === 'yellow' ? colors.yellow : color === 'red' ? colors.alertRed : color === 'green' ? colors.successGreen : t.textSecondary;
  return (
    <View style={{ backgroundColor: bg, borderRadius: radius.full, paddingHorizontal: spacing.md, paddingVertical: spacing.xs, marginRight: spacing.sm }}>
      <Text style={{ color: fg, fontSize: 12, fontWeight: '600' }}>{text}</Text>
    </View>
  );
}

export function ConfidenceBar({ value, label }: { value: number; label?: string }) {
  const { mode } = useTheme();
  const t = getTheme(mode);
  return (
    <View style={{ marginTop: spacing.md }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: spacing.xs }}>
        <Text style={{ color: t.textSecondary, fontSize: 11, fontWeight: '600', letterSpacing: 1 }}>CONFIDENCE</Text>
        <Text style={{ color: t.textPrimary, fontSize: 14, fontWeight: 'bold' }}>{Math.round(value * 100)}%</Text>
      </View>
      <View style={{ height: 4, backgroundColor: t.border, borderRadius: radius.full, overflow: 'hidden' }}>
        <View style={{ width: `${value * 100}%`, height: '100%', backgroundColor: colors.yellow, borderRadius: radius.full }} />
      </View>
      {label && <Text style={{ color: t.textSecondary, fontSize: 11, marginTop: spacing.xs }}>{label}</Text>}
    </View>
  );
}

export function LLMDot({ size = 8 }: { size?: number }) {
  const { llmStatus } = useAuth();
  const active = llmStatus?.active;
  const color = active ? colors.successGreen : colors.yellow;
  return <View style={{ width: size, height: size, borderRadius: size / 2, backgroundColor: color }} />;
}

export function TopBar({ title }: { title: string }) {
  const { mode } = useTheme();
  const t = getTheme(mode);
  const { logout } = useAuth();
  return (
    <View style={[styles.topBar, { backgroundColor: t.bg, borderBottomColor: t.border }]}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
        <Text style={{ color: colors.yellow, fontSize: 18, fontWeight: 'bold' }}>⚡</Text>
        <Text style={{ color: t.textPrimary, fontSize: 18, fontWeight: 'bold' }}>{title}</Text>
      </View>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
        <LLMDot />
        <TouchableOpacity onPress={logout}>
          <Ionicons name="log-out-outline" size={22} color={t.textSecondary} />
        </TouchableOpacity>
      </View>
    </View>
  );
}

// Re-export typography so screens can do a single import:
//   import { Card, typography } from '../components';
export { typography };
