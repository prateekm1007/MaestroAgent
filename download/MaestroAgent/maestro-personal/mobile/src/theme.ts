/**
 * Maestro Personal Theme — Bumble-inspired.
 *
 * Light, warm, approachable. Honey accent on cream. Bold typography.
 * Rounded cards with soft shadows. Human, not technical.
 *
 * "Picasso didn't ask people what paint to use. But he chose warm
 * colors for warm subjects." — the CEO's standard, applied.
 */

export const theme = {
  // Backgrounds
  bg: '#FFFCF7',           // warm cream — the canvas
  bgSecondary: '#F8F5F0',  // slightly darker cream for sections
  cardBg: '#FFFFFF',       // pure white cards

  // Accents
  honey: '#FFC629',        // Bumble honey — primary accent
  honeyDark: '#E0AB1F',    // pressed state
  purple: '#7B4DFF',       // secondary accent (Bumble purple)
  purpleLight: '#F0EBFF',  // purple background

  // Text
  textPrimary: '#1A1A1A',  // near-black — confident
  textSecondary: '#8E8E93', // gray — supportive
  textOnHoney: '#1A1A1A',  // dark text on honey (high contrast)

  // Borders & dividers
  border: '#F0EEE9',       // subtle warm border
  divider: '#E8E5E0',      // slightly stronger divider

  // Semantic
  success: '#34C759',
  warning: '#FF9500',
  error: '#FF3B30',

  // Shadows — warm, not cold blue
  shadow: {
    card: {
      shadowColor: '#000',
      shadowOffset: { width: 0, height: 2 },
      shadowOpacity: 0.08,
      shadowRadius: 8,
      elevation: 3,
    },
    cardHover: {
      shadowColor: '#000',
      shadowOffset: { width: 0, height: 4 },
      shadowOpacity: 0.12,
      shadowRadius: 12,
      elevation: 5,
    },
  },

  // Spacing
  radius: {
    sm: 8,
    md: 12,
    lg: 16,
    xl: 20,
    pill: 100,
  },

  // Typography
  font: {
    title: { fontSize: 28, fontWeight: '800' as const, color: '#1A1A1A' },
    heading: { fontSize: 22, fontWeight: '700' as const, color: '#1A1A1A' },
    body: { fontSize: 16, fontWeight: '400' as const, color: '#1A1A1A' },
    bodyBold: { fontSize: 16, fontWeight: '600' as const, color: '#1A1A1A' },
    caption: { fontSize: 13, fontWeight: '400' as const, color: '#8E8E93' },
    kicker: { fontSize: 11, fontWeight: '700' as const, color: '#E0AB1F', letterSpacing: 2 },
  },
};
