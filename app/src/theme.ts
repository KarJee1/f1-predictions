import { useColorScheme } from 'react-native';

import { useThemePreference } from './ThemePreference';

export const palette = {
  dark: {
    background: '#15151E',
    surface: '#1F1F29',
    surfaceAlt: '#272733',
    border: '#33333F',
    text: '#FFFFFF',
    muted: '#9C9CA8',
    accent: '#E10600',
    accentText: '#FFFFFF',
    up: '#2BD47D',
    down: '#FF4E4E',
    tabBar: '#15151E',
  },
  light: {
    background: '#F4F2EF',
    surface: '#FFFFFF',
    surfaceAlt: '#ECE9E5',
    border: '#E0DCD7',
    text: '#15151E',
    muted: '#67676F',
    accent: '#E10600',
    accentText: '#FFFFFF',
    up: '#0E9F57',
    down: '#D92D20',
    tabBar: '#FFFFFF',
  },
};

export type Colors = typeof palette.dark;

// Saira is the closest open font to F1's own typeface; its wide cut stands in for F1's "Wide" display style.
export const fonts = {
  regular: 'Saira-Regular',
  medium: 'Saira-Medium',
  semibold: 'Saira-SemiBold',
  bold: 'Saira-Bold',
  wide: 'SairaWide-Bold',
  black: 'SairaWide-Black',
};

export function useScheme(): 'light' | 'dark' {
  const system = useColorScheme();
  const { preference } = useThemePreference();
  if (preference === 'system') return system === 'light' ? 'light' : 'dark';
  return preference;
}

export function useColors(): Colors {
  return palette[useScheme()];
}

/** Team color from the data, or a neutral grey if the team is new to us. */
export function teamColor(color: string | null | undefined): string {
  return color && /^#[0-9a-fA-F]{6}$/.test(color) ? color : '#8A8A96';
}
