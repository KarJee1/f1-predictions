import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, ReactNode, useContext, useEffect, useState } from 'react';

export type Preference = 'system' | 'light' | 'dark';
const KEY = 'theme-preference';

const Ctx = createContext<{ preference: Preference; setPreference: (p: Preference) => void }>({
  preference: 'system',
  setPreference: () => {},
});

export function ThemePreferenceProvider({ children }: { children: ReactNode }) {
  const [preference, setState] = useState<Preference>('system');

  useEffect(() => {
    AsyncStorage.getItem(KEY)
      .then((v) => {
        if (v === 'light' || v === 'dark' || v === 'system') setState(v);
      })
      .catch(() => {});
  }, []);

  const setPreference = (p: Preference) => {
    setState(p);
    AsyncStorage.setItem(KEY, p).catch(() => {});
  };

  return <Ctx.Provider value={{ preference, setPreference }}>{children}</Ctx.Provider>;
}

export const useThemePreference = () => useContext(Ctx);
