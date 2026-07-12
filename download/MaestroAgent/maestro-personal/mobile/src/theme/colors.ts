/**
 * Maestro Personal — Bumble-inspired theme
 * Production color system with dark/light mode support
 */

export const colors = {
  // Bumble brand
  yellow: '#FFC629',
  yellowDark: '#E0AB1F',
  honey: '#F8F0DD',
  black: '#1A1A1A',
  gray: '#7A7A7A',
  lightGray: '#E8E8E8',
  white: '#FFFFFF',
  royalBlue: '#2E1C53',
  alertRed: '#FF3B3B',
  successGreen: '#00C853',

  // Dark mode surfaces
  darkBg: '#1A1A1A',
  darkSurface: '#2A2A2A',
  darkBorder: '#3A3A3A',

  // Light mode surfaces
  lightBg: '#FFFFFF',
  lightSurface: '#F8F0DD',
  lightBorder: '#E8E8E8',
} as const;

export type ThemeMode = 'dark' | 'light';

export interface Theme {
  mode: ThemeMode;
  bg: string;
  surface: string;
  cardBg: string;
  textPrimary: string;
  textSecondary: string;
  border: string;
  yellow: string;
  honey: string;
  success: string;
  danger: string;
}

export function getTheme(mode: ThemeMode): Theme {
  if (mode === 'dark') {
    return {
      mode: 'dark',
      bg: colors.darkBg,
      surface: colors.darkSurface,
      cardBg: colors.darkSurface,
      textPrimary: colors.white,
      textSecondary: colors.gray,
      border: colors.darkBorder,
      yellow: colors.yellow,
      honey: colors.honey,
      success: colors.successGreen,
      danger: colors.alertRed,
    };
  }
  return {
    mode: 'light',
    bg: colors.lightBg,
    surface: colors.lightSurface,
    cardBg: colors.white,
    textPrimary: colors.black,
    textSecondary: colors.gray,
    border: colors.lightBorder,
    yellow: colors.yellow,
    honey: colors.honey,
    success: colors.successGreen,
    danger: colors.alertRed,
  };
}

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
  xxxl: 32,
} as const;

export const radius = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  full: 9999,
} as const;

export const typography = {
  title: { fontSize: 32, fontWeight: 'bold' as const },
  heading: { fontSize: 20, fontWeight: 'bold' as const },
  subheading: { fontSize: 16, fontWeight: '600' as const },
  body: { fontSize: 15, fontWeight: '400' as const },
  caption: { fontSize: 13, fontWeight: '400' as const },
  micro: { fontSize: 11, fontWeight: '400' as const },
  label: { fontSize: 11, fontWeight: '600' as const, letterSpacing: 1 },
} as const;
