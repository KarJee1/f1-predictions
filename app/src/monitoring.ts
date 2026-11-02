import * as Sentry from '@sentry/react-native';
import Constants from 'expo-constants';

// Crash reports go to Sentry when EXPO_PUBLIC_SENTRY_DSN is set; without it nothing is sent.
// No personal data: default PII is off, and screens are identified by route only.
const dsn = process.env.EXPO_PUBLIC_SENTRY_DSN;

Sentry.init({
  dsn,
  enabled: !!dsn && !__DEV__,
  release: `f1-predictions@${Constants.expoConfig?.version ?? 'dev'}`,
  sendDefaultPii: false,
  tracesSampleRate: 0,
});

export { Sentry };
