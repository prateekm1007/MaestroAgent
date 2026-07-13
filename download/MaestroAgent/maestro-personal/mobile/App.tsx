/**
 * Maestro Personal — Production Mobile App (modular root).
 *
 * This file is intentionally tiny: it composes the three shared providers
 * (Theme, Auth, Consent), mounts the bottom-tab navigator, and selects
 * between LoginScreen and the authenticated tab tree. All screen logic
 * lives in ./src/screens/*; shared components live in ./src/components;
 * shared contexts live in ./src/contexts.
 *
 * Tech: Expo SDK 52, React Navigation, AsyncStorage
 * Design: Bumble Yellow (#FFC629), light mode default, card-based UI
 */

import React from 'react';
import { StatusBar } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { colors, getTheme } from './src/theme/colors';
import { ThemeProvider, AuthProvider, ConsentProvider, useTheme, useAuth } from './src/contexts';

import LoginScreen from './src/screens/LoginScreen';
import DashboardScreen from './src/screens/DashboardScreen';
import AskScreen from './src/screens/AskScreen';
import CommitmentsScreen from './src/screens/CommitmentsScreen';
import CopilotScreen from './src/screens/CopilotScreen';
import SettingsScreen from './src/screens/SettingsScreen';

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
  return (
    <>
      <StatusBar barStyle={mode === 'dark' ? 'light-content' : 'dark-content'} />
      {token ? <TabNavigator /> : <LoginScreen />}
    </>
  );
}

export default function App() {
  return (
    <SafeAreaProvider>
      <ThemeProvider>
        <AuthProvider>
          <ConsentProvider>
            <NavigationContainer>
              <AppInner />
            </NavigationContainer>
          </ConsentProvider>
        </AuthProvider>
      </ThemeProvider>
    </SafeAreaProvider>
  );
}
