/**
 * Maestro Personal — Production Mobile App (modular root).
 *
 * Phase 2: Added OnboardingProvider + QueryClientProvider.
 *
 * Structure:
 *   SafeAreaProvider
 *     → ThemeProvider (light/dark)
 *       → OnboardingProvider (first-launch flow)
 *         → AuthProvider (SecureStore token)
 *           → ConsentProvider (mic consent)
 *             → QueryClientProvider (react-query offline cache)
 *               → NavigationContainer
 *                 → OnboardingScreen | LoginScreen | TabNavigator
 */

import React from 'react';
import { StatusBar } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { colors, getTheme } from './src/theme/colors';
import {
  ThemeProvider, AuthProvider, ConsentProvider, OnboardingProvider,
  useTheme, useAuth, useOnboarding,
} from './src/contexts';

import OnboardingScreen from './src/screens/OnboardingScreen';
import LoginScreen from './src/screens/LoginScreen';
import DashboardScreen from './src/screens/DashboardScreen';
import AskScreen from './src/screens/AskScreen';
import CommitmentsScreen from './src/screens/CommitmentsScreen';
import CopilotScreen from './src/screens/CopilotScreen';
import SettingsScreen from './src/screens/SettingsScreen';
import ConnectorsScreen from './src/screens/ConnectorsScreen';

// react-query client (offline cache + stale-while-revalidate)
const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, gcTime: 5 * 60_000, retry: 2 },
  },
});

// ═══════════════════════════════════════════════════════════════════
// NAVIGATION
// ═══════════════════════════════════════════════════════════════════

const Tab = createBottomTabNavigator();

function TabNavigator() {
  const { mode } = useTheme();
  const t = getTheme(mode);
  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarStyle: { backgroundColor: t.bg, borderTopColor: t.border, height: 56 },
        tabBarActiveTintColor: colors.yellow,
        tabBarInactiveTintColor: t.textSecondary,
        tabBarLabelStyle: { fontSize: 10 },
      }}
    >
      <Tab.Screen name="Dashboard" component={DashboardScreen} options={{ tabBarIcon: ({ color }) => <Ionicons name="home" size={22} color={color} /> }} />
      <Tab.Screen name="Ask" component={AskScreen} options={{ tabBarIcon: ({ color }) => <Ionicons name="search" size={22} color={color} /> }} />
      <Tab.Screen name="Commitments" component={CommitmentsScreen} options={{ tabBarIcon: ({ color }) => <Ionicons name="checkmark-circle" size={22} color={color} /> }} />
      <Tab.Screen name="Copilot" component={CopilotScreen} options={{ tabBarIcon: ({ color }) => <Ionicons name="chatbubbles" size={22} color={color} /> }} />
      <Tab.Screen name="Connectors" component={ConnectorsScreen} options={{ tabBarIcon: ({ color }) => <Ionicons name="link" size={22} color={color} /> }} />
      <Tab.Screen name="Settings" component={SettingsScreen} options={{ tabBarIcon: ({ color }) => <Ionicons name="settings" size={22} color={color} /> }} />
    </Tab.Navigator>
  );
}

// ═══════════════════════════════════════════════════════════════════
// APP ROOT
// ═══════════════════════════════════════════════════════════════════

function AppInner() {
  const { token } = useAuth();
  const { mode } = useTheme();
  const { hasOnboarded } = useOnboarding();

  return (
    <>
      <StatusBar barStyle={mode === 'dark' ? 'light-content' : 'dark-content'} />
      {!hasOnboarded ? <OnboardingScreen /> : token ? <TabNavigator /> : <LoginScreen />}
    </>
  );
}

export default function App() {
  return (
    <SafeAreaProvider>
      <ThemeProvider>
        <OnboardingProvider>
          <AuthProvider>
            <ConsentProvider>
              <QueryClientProvider client={queryClient}>
                <NavigationContainer>
                  <AppInner />
                </NavigationContainer>
              </QueryClientProvider>
            </ConsentProvider>
          </AuthProvider>
        </OnboardingProvider>
      </ThemeProvider>
    </SafeAreaProvider>
  );
}
