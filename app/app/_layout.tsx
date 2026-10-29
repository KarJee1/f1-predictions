import AsyncStorage from '@react-native-async-storage/async-storage';
import { createAsyncStoragePersister } from '@tanstack/query-async-storage-persister';
import { QueryClient } from '@tanstack/react-query';
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client';
import Constants from 'expo-constants';
import { useFonts } from 'expo-font';
import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import 'react-native-reanimated';

import { AccountProvider } from '@/src/account';
import { fonts, palette, useScheme } from '@/src/theme';
import { ThemePreferenceProvider } from '@/src/ThemePreference';

export { ErrorBoundary } from 'expo-router';

export const unstable_settings = { anchor: '(tabs)' };

SplashScreen.preventAutoHideAsync();

// The last data the app loaded is kept on the device for a week, so it opens instantly and works offline.
const WEEK = 7 * 24 * 60 * 60 * 1000;
const queryClient = new QueryClient({ defaultOptions: { queries: { gcTime: WEEK } } });
const persister = createAsyncStoragePersister({ storage: AsyncStorage, key: 'query-cache' });
const persistOptions = { persister, maxAge: WEEK, buster: Constants.expoConfig?.version ?? '' };

export default function RootLayout() {
  const [loaded, error] = useFonts({
    'Saira-Regular': require('../assets/fonts/Saira-Regular.ttf'),
    'Saira-Medium': require('../assets/fonts/Saira-Medium.ttf'),
    'Saira-SemiBold': require('../assets/fonts/Saira-SemiBold.ttf'),
    'Saira-Bold': require('../assets/fonts/Saira-Bold.ttf'),
    'SairaWide-Bold': require('../assets/fonts/SairaWide-Bold.ttf'),
    'SairaWide-Black': require('../assets/fonts/SairaWide-Black.ttf'),
  });

  useEffect(() => {
    if (error) throw error;
  }, [error]);

  useEffect(() => {
    if (loaded) SplashScreen.hideAsync();
  }, [loaded]);

  if (!loaded) return null;

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <PersistQueryClientProvider client={queryClient} persistOptions={persistOptions}>
        <AccountProvider>
          <ThemePreferenceProvider>
            <RootNav />
          </ThemePreferenceProvider>
        </AccountProvider>
      </PersistQueryClientProvider>
    </GestureHandlerRootView>
  );
}

function RootNav() {
  const scheme = useScheme();
  const c = palette[scheme];
  const base = scheme === 'dark' ? DarkTheme : DefaultTheme;
  const theme = {
    ...base,
    colors: { ...base.colors, background: c.background, card: c.surface, text: c.text, border: c.border, primary: c.accent },
  };
  return (
    <ThemeProvider value={theme}>
      <StatusBar style={scheme === 'dark' ? 'light' : 'dark'} />
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="(tabs)" />
        <Stack.Screen
          name="driver/[id]"
          options={{ presentation: 'formSheet', sheetAllowedDetents: [0.6, 1], sheetGrabberVisible: true, contentStyle: { backgroundColor: c.background, width: '100%', maxWidth: 760, alignSelf: 'center' } }}
        />
        <Stack.Screen
          name="group/[id]"
          options={{
            headerShown: true,
            headerBackTitle: 'Groups',
            headerShadowVisible: false,
            headerStyle: { backgroundColor: c.background },
            headerTitleStyle: { fontFamily: fonts.bold },
            headerTintColor: c.accent,
            contentStyle: { backgroundColor: c.background, width: '100%', maxWidth: 760, alignSelf: 'center' },
          }}
        />
        <Stack.Screen name="settings" options={{ presentation: 'modal' }} />
      </Stack>
    </ThemeProvider>
  );
}
