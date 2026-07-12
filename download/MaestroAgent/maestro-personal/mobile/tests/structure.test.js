/**
 * Mobile app structure tests — 7-screen production spec.
 *
 * Verifies the mobile app has:
 *   - App.tsx with all 7 screens (Login, Dashboard, Ask, Commitments, Signals, Copilot, Settings)
 *   - API client with all endpoints
 *   - Bumble Yellow (#FFC629) color palette
 *   - Dark mode default
 *   - Bottom tab navigation (5 tabs)
 *   - app.json with Android package
 *   - eas.json for Play Store builds
 */

const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const APP_FILE = path.join(ROOT, 'App.tsx');
const API_FILE = path.join(ROOT, 'src', 'api', 'client.ts');
const THEME_FILE = path.join(ROOT, 'src', 'theme', 'colors.ts');
const APP_JSON = path.join(ROOT, 'app.json');

describe('Mobile app structure — 7-screen production spec', () => {
  describe('App.tsx', () => {
    const source = fs.readFileSync(APP_FILE, 'utf-8');

    test('App.tsx exists and has content', () => {
      expect(source.length).toBeGreaterThan(500);
    });

    test('has LoginScreen', () => {
      expect(source).toMatch(/function LoginScreen/);
    });

    test('has DashboardScreen', () => {
      expect(source).toMatch(/function DashboardScreen/);
    });

    test('has AskScreen', () => {
      expect(source).toMatch(/function AskScreen/);
    });

    test('has CommitmentsScreen', () => {
      expect(source).toMatch(/function CommitmentsScreen/);
    });

    test('has SignalsScreen', () => {
      expect(source).toMatch(/function SignalsScreen/);
    });

    test('has CopilotScreen', () => {
      expect(source).toMatch(/function CopilotScreen/);
    });

    test('has SettingsScreen', () => {
      expect(source).toMatch(/function SettingsScreen/);
    });

    test('has ThemeProvider with dark mode default', () => {
      expect(source).toMatch(/function ThemeProvider/);
      expect(source).toMatch(/'dark'/);
    });

    test('has AuthProvider with AsyncStorage', () => {
      expect(source).toMatch(/function AuthProvider/);
      expect(source).toMatch(/AsyncStorage/);
    });

    test('has bottom tab navigator with 5 tabs', () => {
      expect(source).toMatch(/createBottomTabNavigator/);
      expect(source).toMatch(/Dashboard/i);
      expect(source).toMatch(/Ask/i);
      expect(source).toMatch(/Commitments/i);
      expect(source).toMatch(/Copilot/i);
      expect(source).toMatch(/Settings/i);
    });

    test('has ConfidenceBar component', () => {
      expect(source).toMatch(/function ConfidenceBar/);
    });

    test('has Card component with accent support', () => {
      expect(source).toMatch(/function Card/);
      expect(source).toMatch(/accent/);
    });

    test('has LLMDot component', () => {
      expect(source).toMatch(/function LLMDot/);
    });
  });

  describe('API client', () => {
    const source = fs.readFileSync(API_FILE, 'utf-8');

    test('client.ts exists', () => {
      expect(fs.existsSync(API_FILE)).toBe(true);
    });

    test('exports login', () => {
      expect(source).toMatch(/export async function login/);
    });

    test('exports getTheMoment', () => {
      expect(source).toMatch(/export async function getTheMoment/);
    });

    test('exports ask', () => {
      expect(source).toMatch(/export async function ask/);
    });

    test('exports getCommitments', () => {
      expect(source).toMatch(/export async function getCommitments/);
    });

    test('exports getTheOne', () => {
      expect(source).toMatch(/export async function getTheOne/);
    });

    test('exports getSignals', () => {
      expect(source).toMatch(/export async function getSignals/);
    });

    test('exports createSignal', () => {
      expect(source).toMatch(/export async function createSignal/);
    });

    test('exports correctSignal', () => {
      expect(source).toMatch(/export async function correctSignal/);
    });

    test('exports sendTranscriptChunk (copilot)', () => {
      expect(source).toMatch(/export async function sendTranscriptChunk/);
    });

    test('exports getLLMStatus', () => {
      expect(source).toMatch(/export async function getLLMStatus/);
    });

    test('exports getPrivacyMode', () => {
      expect(source).toMatch(/export async function getPrivacyMode/);
    });

    test('exports getCalibration', () => {
      expect(source).toMatch(/export async function getCalibration/);
    });

    test('exports getAuditLog', () => {
      expect(source).toMatch(/export async function getAuditLog/);
    });

    test('exports exportData', () => {
      expect(source).toMatch(/export async function exportData/);
    });

    test('exports deleteAccount', () => {
      expect(source).toMatch(/export async function deleteAccount/);
    });
  });

  describe('Theme — Bumble color palette', () => {
    const source = fs.readFileSync(THEME_FILE, 'utf-8');

    test('colors.ts exists', () => {
      expect(fs.existsSync(THEME_FILE)).toBe(true);
    });

    test('has Bumble Yellow #FFC629', () => {
      expect(source).toMatch(/#FFC629/i);
    });

    test('has Bumble Honey #F8F0DD', () => {
      expect(source).toMatch(/#F8F0DD/i);
    });

    test('has Bumble Black #1A1A1A', () => {
      expect(source).toMatch(/#1A1A1A/i);
    });

    test('has Alert Red #FF3B3B', () => {
      expect(source).toMatch(/#FF3B3B/i);
    });

    test('has Success Green #00C853', () => {
      expect(source).toMatch(/#00C853/i);
    });

    test('has dark mode as default', () => {
      expect(source).toMatch(/dark/);
    });

    test('exports getTheme function', () => {
      expect(source).toMatch(/export function getTheme/);
    });

    test('exports spacing', () => {
      expect(source).toMatch(/export const spacing/);
    });

    test('exports radius', () => {
      expect(source).toMatch(/export const radius/);
    });
  });

  describe('app.json — Expo config', () => {
    test('app.json exists', () => {
      expect(fs.existsSync(APP_JSON)).toBe(true);
    });

    const config = JSON.parse(fs.readFileSync(APP_JSON, 'utf-8'));

    test('has name "Maestro Personal"', () => {
      expect(config.expo.name).toBe('Maestro Personal');
    });

    test('has slug', () => {
      expect(config.expo.slug).toBeTruthy();
    });

    test('has android package', () => {
      expect(config.expo.android?.package).toMatch(/com\.maestro/);
    });

    test('has version', () => {
      expect(config.expo.version).toBeTruthy();
    });
  });

  describe('eas.json — Play Store build config', () => {
    const easFile = path.join(ROOT, 'eas.json');
    test('eas.json exists', () => {
      expect(fs.existsSync(easFile)).toBe(true);
    });

    if (fs.existsSync(easFile)) {
      const eas = JSON.parse(fs.readFileSync(easFile, 'utf-8'));
      test('has preview profile (APK)', () => {
        expect(eas.build?.preview).toBeTruthy();
      });
      test('has production profile (AAB)', () => {
        expect(eas.build?.production).toBeTruthy();
      });
    }
  });
});
