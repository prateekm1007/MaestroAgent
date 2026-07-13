/**
 * Mobile app structure tests — PRODUCTION spec.
 * Verifies production-grade architecture: secure storage, react-query,
 * haptics, gestures, audio, form validation, axios, all 7 screens.
 */

const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');

describe('Mobile app — PRODUCTION structure', () => {
  // ── Package.json deps ──────────────────────────────────────────
  describe('Production dependencies', () => {
    const pkg = JSON.parse(fs.readFileSync(path.join(ROOT, 'package.json'), 'utf-8'));
    const deps = pkg.dependencies || {};

    test('expo-secure-store (secure token storage)', () => {
      expect(deps['expo-secure-store']).toBeTruthy();
    });
    test('@tanstack/react-query (offline cache)', () => {
      expect(deps['@tanstack/react-query']).toBeTruthy();
    });
    test('expo-haptics (haptic feedback)', () => {
      expect(deps['expo-haptics']).toBeTruthy();
    });
    test('expo-av (audio recording)', () => {
      expect(deps['expo-av']).toBeTruthy();
    });
    test('axios (API client with interceptors)', () => {
      expect(deps['axios']).toBeTruthy();
    });
    test('react-hook-form (form validation)', () => {
      expect(deps['react-hook-form']).toBeTruthy();
    });
    test('zod (schema validation)', () => {
      expect(deps['zod']).toBeTruthy();
    });
    test('react-native-gesture-handler (swipe gestures)', () => {
      expect(deps['react-native-gesture-handler']).toBeTruthy();
    });
    test('react-native-reanimated (animations)', () => {
      expect(deps['react-native-reanimated']).toBeTruthy();
    });
    test('expo-sharing (data export)', () => {
      expect(deps['expo-sharing']).toBeTruthy();
    });
  });

  // ── App.tsx screens ────────────────────────────────────────────
  describe('App.tsx — 7 screens', () => {
    const source = fs.readFileSync(path.join(ROOT, 'App.tsx'), 'utf-8');

    test('has LoginScreen', () => expect(source).toMatch(/function LoginScreen/));
    test('has DashboardScreen', () => expect(source).toMatch(/function DashboardScreen/));
    test('has AskScreen', () => expect(source).toMatch(/function AskScreen/));
    test('has CommitmentsScreen', () => expect(source).toMatch(/function CommitmentsScreen/));
    test('has SignalsScreen', () => expect(source).toMatch(/function SignalsScreen/));
    test('has CopilotScreen', () => expect(source).toMatch(/function CopilotScreen/));
    test('has SettingsScreen', () => expect(source).toMatch(/function SettingsScreen/));
    test('has ThemeProvider with light mode default (Bumble-inspired)', () => {
      expect(source).toMatch(/function ThemeProvider/);
      expect(source).toMatch(/'light'/);
    });
    test('has AuthProvider', () => expect(source).toMatch(/function AuthProvider/));
    test('has bottom tab navigator', () => expect(source).toMatch(/createBottomTabNavigator/));
    test('has ConfidenceBar component', () => expect(source).toMatch(/function ConfidenceBar/));
    test('has Card component', () => expect(source).toMatch(/function Card/));
    test('has LLMDot component', () => expect(source).toMatch(/function LLMDot/));
  });

  // ── API client — production grade ──────────────────────────────
  describe('API client — production', () => {
    const source = fs.readFileSync(path.join(ROOT, 'src', 'api', 'client.ts'), 'utf-8');

    test('uses axios', () => expect(source).toMatch(/import axios/));
    test('uses expo-secure-store for token', () => expect(source).toMatch(/expo-secure-store/));
    test('has request interceptor (auto-attach token)', () => expect(source).toMatch(/interceptors\.request/));
    test('has response interceptor (401 logout)', () => expect(source).toMatch(/interceptors\.response/));
    test('has getHost/setHost (server URL config)', () => {
      expect(source).toMatch(/getHost/);
      expect(source).toMatch(/setHost/);
    });
    test('exports login', () => expect(source).toMatch(/export async function login/));
    test('exports getTheMoment', () => expect(source).toMatch(/export.*getTheMoment/));
    test('exports ask', () => expect(source).toMatch(/export.*ask/));
    test('exports getCommitments', () => expect(source).toMatch(/export.*getCommitments/));
    test('exports getTheOne', () => expect(source).toMatch(/export.*getTheOne/));
    test('exports getSignals', () => expect(source).toMatch(/export.*getSignals/));
    test('exports createSignal', () => expect(source).toMatch(/export.*createSignal/));
    test('exports correctSignal', () => expect(source).toMatch(/export.*correctSignal/));
    test('exports sendTranscriptChunk', () => expect(source).toMatch(/export.*sendTranscriptChunk/));
    test('exports getLLMStatus', () => expect(source).toMatch(/export.*getLLMStatus/));
    test('exports getPrivacyMode', () => expect(source).toMatch(/export.*getPrivacyMode/));
    test('exports getCalibration', () => expect(source).toMatch(/export.*getCalibration/));
    test('exports getAuditLog', () => expect(source).toMatch(/export.*getAuditLog/));
    test('exports exportData', () => expect(source).toMatch(/export.*exportData/));
    test('exports deleteAccount', () => expect(source).toMatch(/export.*deleteAccount/));
  });

  // ── Theme — Bumble palette ─────────────────────────────────────
  describe('Theme — Bumble colors', () => {
    const source = fs.readFileSync(path.join(ROOT, 'src', 'theme', 'colors.ts'), 'utf-8');
    test('has Bumble Yellow #FFC629', () => expect(source).toMatch(/#FFC629/i));
    test('has Bumble Honey #F8F0DD', () => expect(source).toMatch(/#F8F0DD/i));
    test('has Bumble Black #1A1A1A', () => expect(source).toMatch(/#1A1A1A/i));
    test('has Alert Red #FF3B3B', () => expect(source).toMatch(/#FF3B3B/i));
    test('has Success Green #00C853', () => expect(source).toMatch(/#00C853/i));
    test('light mode default (Bumble-inspired, not dark brooding)', () => expect(source).toMatch(/light/));
    test('exports getTheme', () => expect(source).toMatch(/export function getTheme/));
  });

  // ── app.json — production config ───────────────────────────────
  describe('app.json — production', () => {
    const config = JSON.parse(fs.readFileSync(path.join(ROOT, 'app.json'), 'utf-8'));
    test('name is "Maestro Personal"', () => expect(config.expo.name).toBe('Maestro Personal'));
    test('android package com.maestro.personal', () => expect(config.expo.android?.package).toBe('com.maestro.personal'));
    test('has RECORD_AUDIO permission', () => expect(config.expo.android?.permissions).toContain('RECORD_AUDIO'));
    test('has VIBRATE permission', () => expect(config.expo.android?.permissions).toContain('VIBRATE'));
    test('has expo-haptics plugin', () => expect(config.expo.plugins).toContain('expo-haptics'));
    test('has expo-av plugin', () => expect(config.expo.plugins).toContain('expo-av'));
    test('iOS has NSMicrophoneUsageDescription', () => expect(config.expo.ios?.infoPlist?.NSMicrophoneUsageDescription).toBeTruthy());
    test('adaptive icon bg is Bumble Yellow', () => expect(config.expo.android?.adaptiveIcon?.backgroundColor).toBe('#FFC629'));
  });

  // ── eas.json — Play Store ──────────────────────────────────────
  describe('eas.json — Play Store builds', () => {
    const eas = JSON.parse(fs.readFileSync(path.join(ROOT, 'eas.json'), 'utf-8'));
    test('has preview profile (APK)', () => expect(eas.build?.preview).toBeTruthy());
    test('preview builds APK', () => expect(eas.build?.preview?.android?.buildType).toBe('apk'));
    test('has production profile (AAB)', () => expect(eas.build?.production).toBeTruthy());
    test('production builds AAB', () => expect(eas.build?.production?.android?.buildType).toBe('app-bundle'));
  });
});
