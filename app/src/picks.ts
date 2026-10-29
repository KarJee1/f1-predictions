import AsyncStorage from '@react-native-async-storage/async-storage';
import { useCallback, useEffect, useState } from 'react';

import type { ResultRow } from './types';

const PREFIX = 'picks:';

// synced: whether this exact order has been saved to the server for friend groups.
export type Picks = { season: number; round: number; race_name: string; order: string[]; saved_at: string; synced?: boolean };

export const picksKey = (season: number, round: number) => `${PREFIX}${season}-${round}`;

export function usePicks(season: number | undefined, round: number | undefined) {
  const [picks, setPicks] = useState<Picks | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!season || !round) return;
    setLoaded(false);
    AsyncStorage.getItem(picksKey(season, round))
      .then((raw) => setPicks(raw ? (JSON.parse(raw) as Picks) : null))
      .catch(() => setPicks(null))
      .finally(() => setLoaded(true));
  }, [season, round]);

  const save = useCallback((next: Picks) => {
    setPicks(next);
    AsyncStorage.setItem(picksKey(next.season, next.round), JSON.stringify(next)).catch(() => {});
  }, []);

  return { picks, loaded, save };
}

export async function allPicks(): Promise<Picks[]> {
  const keys = (await AsyncStorage.getAllKeys()).filter((k) => k.startsWith(PREFIX));
  const entries = await AsyncStorage.multiGet(keys);
  return entries
    .map(([, v]) => (v ? (JSON.parse(v) as Picks) : null))
    .filter((p): p is Picks => !!p)
    .sort((a, b) => b.season - a.season || b.round - a.round);
}

/** Up to 5 points per driver: 5 for the exact position, one less for each place off. */
export const POINTS_PER_DRIVER = 5;

export function scoreOrder(order: string[], results: ResultRow[]): { score: number; max: number; exact: number } {
  const actual = new Map(results.map((r) => [r.driver_id, r.position]));
  let score = 0;
  let exact = 0;
  let counted = 0;
  order.forEach((id, i) => {
    const pos = actual.get(id);
    if (pos === undefined) return;
    counted += 1;
    const off = Math.abs(i + 1 - pos);
    if (off === 0) exact += 1;
    score += Math.max(0, POINTS_PER_DRIVER - off);
  });
  return { score, max: counted * POINTS_PER_DRIVER, exact };
}
