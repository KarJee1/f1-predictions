import {
  TitilliumWeb_400Regular,
  TitilliumWeb_600SemiBold,
  TitilliumWeb_700Bold,
  TitilliumWeb_900Black,
  useFonts,
} from '@expo-google-fonts/titillium-web';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import 'react-native-reanimated';

import { palette, useScheme } from '@/src/theme';
import { ThemePreferenceProvider } from '@/src/ThemePreference';

export { ErrorBoundary } from 'expo-router';

export const unstable_settings = { anchor: '(tabs)' };

SplashScreen.preventAutoHideAsync();

const queryClient = new QueryClient();

export default function RootLayout() {
  const [loaded, error] = useFonts({
    TitilliumWeb_400Regular,
    TitilliumWeb_600SemiBold,
    TitilliumWeb_700Bold,
    TitilliumWeb_900Black,
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
      <QueryClientProvider client={queryClient}>
        <ThemePreferenceProvider>
          <RootNav />
        </ThemePreferenceProvider>
      </QueryClientProvider>
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
          options={{ presentation: 'formSheet', sheetAllowedDetents: [0.6, 1], sheetGrabberVisible: true, contentStyle: { backgroundColor: c.background } }}
        />
        <Stack.Screen name="settings" options={{ presentation: 'modal' }} />
      </Stack>
    </ThemeProvider>
  );
}
