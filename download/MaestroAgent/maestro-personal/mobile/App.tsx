/**
 * App.tsx — main entry point for Maestro Personal mobile app.
 *
 * Structure:
 *   AuthProvider (token management)
 *     → if no token: LoginScreen
 *     → if token: BottomTabNavigator (Home, Ask, Commitments, Prepare)
 *       + AddSignal modal
 *
 * Per build directions: 4 screens map to 4 surfaces, bottom tab nav,
 * login screen. No push, no offline, no App Store — Expo Go + QR.
 */

import React from 'react';
import { StatusBar } from 'expo-status-bar';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { SafeAreaView, Text, ActivityIndicator, StyleSheet } from 'react-native';

import { AuthProvider, useAuth } from './src/api/auth';
import LoginScreen from './src/screens/LoginScreen';
import HomeScreen from './src/screens/HomeScreen';
import AskScreen from './src/screens/AskScreen';
import CommitmentsScreen from './src/screens/CommitmentsScreen';
import PrepareScreen from './src/screens/PrepareScreen';
import AddSignalScreen from './src/screens/AddSignalScreen';
import WhisperScreen from './src/screens/WhisperScreen';

const Tab = createBottomTabNavigator();

function LoadingScreen() {
  return (
    <SafeAreaView style={styles.loading}>
      <ActivityIndicator size="large" color="#897128" />
      <Text style={styles.loadingText}>Loading Maestro...</Text>
    </SafeAreaView>
  );
}

function MainApp() {
  const { token, isLoading } = useAuth();

  if (isLoading) return <LoadingScreen />;
  if (!token) return <LoginScreen />;

  return (
    <Tab.Navigator
      screenOptions={{
        tabBarActiveTintColor: '#897128',
        tabBarStyle: { backgroundColor: '#f5f4f3', borderTopColor: '#bfbaac' },
      }}
    >
      <Tab.Screen name="Home" component={HomeScreen} options={{ title: 'Home' }} />
      <Tab.Screen name="Whisper" component={WhisperScreen} options={{ title: 'Whisper' }} />
      <Tab.Screen name="Ask" component={AskScreen} options={{ title: 'Ask' }} />
      <Tab.Screen name="Commitments" component={CommitmentsScreen} options={{ title: 'Commitments' }} />
      <Tab.Screen name="Prepare" component={PrepareScreen} options={{ title: 'Prepare' }} />
      <Tab.Screen name="AddSignal" component={AddSignalScreen} options={{ title: '+ Add' }} />
    </Tab.Navigator>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <NavigationContainer>
        <StatusBar style="dark" />
        <MainApp />
      </NavigationContainer>
    </AuthProvider>
  );
}

const styles = StyleSheet.create({
  loading: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#f5f4f3' },
  loadingText: { marginTop: 16, fontSize: 16, color: '#78766f' },
});
