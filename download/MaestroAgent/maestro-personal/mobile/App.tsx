/**
 * Maestro Personal — V2 4-Tab Architecture.
 *
 * Tabs: Today, Commitments, Ask, More
 * - Today: DashboardScreen (The Moment + Draft + whisper cards)
 * - Commitments: CommitmentsScreen (segmented: Commitments | Signals)
 * - Ask: AskScreen (unchanged)
 * - More: MoreScreen (connectors, settings, privacy, account)
 */

import React, { useEffect } from 'react';
import { StatusBar, InteractionManager } from 'react-native';
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
import MoreScreen from './src/screens/MoreScreen';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, gcTime: 5 * 60_000, retry: 2 },
  },
});

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
      <Tab.Screen name="Today" component={DashboardScreen} options={{ tabBarIcon: ({ color }) => <Ionicons name="home" size={22} color={color} />, tabBarLabel: 'Today' }} />
      <Tab.Screen name="Commitments" component={CommitmentsScreen} options={{ tabBarIcon: ({ color }) => <Ionicons name="checkmark-circle" size={22} color={color} /> }} />
      <Tab.Screen name="Ask" component={AskScreen} options={{ tabBarIcon: ({ color }) => <Ionicons name="search" size={22} color={color} /> }} />
      <Tab.Screen name="More" component={MoreScreen} options={{ tabBarIcon: ({ color }) => <Ionicons name="menu" size={22} color={color} /> }} />
    </Tab.Navigator>
  );
}

function AppInner() {
  const { token } = useAuth();
  const { mode } = useTheme();
  const { hasOnboarded } = useOnboarding();

  // Change 14: Cold launch optimization — defer non-critical init
  useEffect(() => {
    if (!token) return;
    // Critical: The Moment is fetched immediately by the DashboardScreen
    // Non-critical: defer push notification registration until after first render
    InteractionManager.runAfterInteractions(() => {
      import('./src/services/notifications').then(({ registerForPushNotifications }) => {
        registerForPushNotifications().catch(() => { /* non-fatal */ });
      });
    });
  }, [token]);

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
