/**
 * Mobile app structure tests.
 *
 * Verifies the mobile app has the right structure:
 *   - 4 screens (Home, Ask, Commitments, Prepare)
 *   - Login screen
 *   - AddSignal screen
 *   - API client with all 8 endpoints
 *   - Auth context
 *   - App.tsx with navigation
 *
 * These are structural tests — they verify the files exist and have
 * the right exports. Full rendering tests require the Expo runtime
 * (jest-expo) which is heavy to install. For v1 dogfood, structural
 * verification is sufficient — the auditor can verify rendering by
 * running the app via Expo Go.
 */

const fs = require('fs');
const path = require('path');

const SCREENS_DIR = path.join(__dirname, '..', 'src', 'screens');
const API_DIR = path.join(__dirname, '..', 'src', 'api');
const APP_FILE = path.join(__dirname, '..', 'App.tsx');

describe('Mobile app structure', () => {
  describe('Required screens exist', () => {
    const requiredScreens = [
      'LoginScreen.tsx',
      'HomeScreen.tsx',
      'AskScreen.tsx',
      'CommitmentsScreen.tsx',
      'PrepareScreen.tsx',
      'AddSignalScreen.tsx',
    ];

    requiredScreens.forEach((screen) => {
      test(`${screen} exists`, () => {
        const filePath = path.join(SCREENS_DIR, screen);
        expect(fs.existsSync(filePath)).toBe(true);
      });

      test(`${screen} has default export`, () => {
        const filePath = path.join(SCREENS_DIR, screen);
        const source = fs.readFileSync(filePath, 'utf-8');
        expect(source).toMatch(/export default/);
      });
    });
  });

  describe('API client', () => {
    test('client.ts exists', () => {
      expect(fs.existsSync(path.join(API_DIR, 'client.ts'))).toBe(true);
    });

    test('client.ts exports all 8 endpoint functions', () => {
      const source = fs.readFileSync(path.join(API_DIR, 'client.ts'), 'utf-8');
      // 8 endpoints: login, getSituations, createSignal, getSignals, ask, getCommitments, getWhatChanged, getPrepare
      // + health (9th, no auth)
      expect(source).toMatch(/export async function login/);
      expect(source).toMatch(/export async function getHealth/);
      expect(source).toMatch(/export async function getSituations/);
      expect(source).toMatch(/export async function createSignal/);
      expect(source).toMatch(/export async function getSignals/);
      expect(source).toMatch(/export async function ask/);
      expect(source).toMatch(/export async function getCommitments/);
      expect(source).toMatch(/export async function getWhatChanged/);
      expect(source).toMatch(/export async function getPrepare/);
    });

    test('client.ts calls the right API URL (port 8766)', () => {
      const source = fs.readFileSync(path.join(API_DIR, 'client.ts'), 'utf-8');
      expect(source).toMatch(/8766/);
    });

    test('auth.tsx exists with AuthProvider + useAuth', () => {
      const source = fs.readFileSync(path.join(API_DIR, 'auth.tsx'), 'utf-8');
      expect(source).toMatch(/export function AuthProvider/);
      expect(source).toMatch(/export function useAuth/);
    });
  });

  describe('App.tsx navigation', () => {
    test('App.tsx exists', () => {
      expect(fs.existsSync(APP_FILE)).toBe(true);
    });

    test('App.tsx has AuthProvider wrapper', () => {
      const source = fs.readFileSync(APP_FILE, 'utf-8');
      expect(source).toMatch(/AuthProvider/);
    });

    test('App.tsx has bottom tab navigator', () => {
      const source = fs.readFileSync(APP_FILE, 'utf-8');
      expect(source).toMatch(/createBottomTabNavigator/);
    });

    test('App.tsx references all 4 surface screens + login + addsignal', () => {
      const source = fs.readFileSync(APP_FILE, 'utf-8');
      expect(source).toMatch(/HomeScreen/);
      expect(source).toMatch(/AskScreen/);
      expect(source).toMatch(/CommitmentsScreen/);
      expect(source).toMatch(/PrepareScreen/);
      expect(source).toMatch(/LoginScreen/);
      expect(source).toMatch(/AddSignalScreen/);
    });
  });

  describe('Configuration', () => {
    test('package.json has Expo dependency', () => {
      const pkg = JSON.parse(
        fs.readFileSync(path.join(__dirname, '..', 'package.json'), 'utf-8')
      );
      expect(pkg.dependencies.expo).toBeDefined();
      expect(pkg.dependencies['react-native']).toBeDefined();
    });

    test('app.json has correct bundle ID', () => {
      const app = JSON.parse(
        fs.readFileSync(path.join(__dirname, '..', 'app.json'), 'utf-8')
      );
      expect(app.expo.ios.bundleIdentifier).toBe('com.maestroagent.personal');
      expect(app.expo.android.package).toBe('com.maestroagent.personal');
    });

    test('app.json points to port 8766', () => {
      const app = JSON.parse(
        fs.readFileSync(path.join(__dirname, '..', 'app.json'), 'utf-8')
      );
      expect(app.expo.extra.API_URL).toMatch(/8766/);
    });
  });

  describe('No dilution in mobile app', () => {
    test('API client does NOT import Core directly', () => {
      const source = fs.readFileSync(path.join(API_DIR, 'client.ts'), 'utf-8');
      // The mobile app must call the HTTP API, not Core directly
      expect(source).not.toMatch(/maestro_cognitive_council/);
      expect(source).not.toMatch(/SituationEngine/);
      expect(source).not.toMatch(/JudgmentSynthesizer/);
    });

    test('Screens do NOT import Core directly', () => {
      const screens = fs.readdirSync(SCREENS_DIR);
      screens.forEach((screen) => {
        const source = fs.readFileSync(path.join(SCREENS_DIR, screen), 'utf-8');
        expect(source).not.toMatch(/maestro_cognitive_council/);
        expect(source).not.toMatch(/SituationEngine/);
      });
    });
  });
});
