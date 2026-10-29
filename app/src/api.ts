import { useQuery } from '@tanstack/react-query';

import type { Accuracy, Meta, News, Prediction, Results, Standings } from './types';

// Set EXPO_PUBLIC_API_URL to the Cloud Run URL (see infra/deploy.sh).
// EXPO_PUBLIC_USE_SAMPLE_DATA=1 serves the bundled sample files instead, for working on the UI offline.
export const API_URL = (process.env.EXPO_PUBLIC_API_URL ?? '').replace(/\/$/, '');
export const USE_SAMPLE = process.env.EXPO_PUBLIC_USE_SAMPLE_DATA === '1';

export class NotFound extends Error {}

async function getJson<T>(path: string): Promise<T> {
  if (USE_SAMPLE) {
    const { sample } = await import('./sample');
    const doc = sample(path);
    if (doc === undefined) throw new NotFound(path);
    return doc as T;
  }
  const res = await fetch(`${API_URL}/${path}`);
  if (res.status === 404) throw new NotFound(path);
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return (await res.json()) as T;
}

const retry = (count: number, error: Error) => !(error instanceof NotFound) && count < 2;

export const useMeta = () =>
  useQuery({ queryKey: ['meta'], queryFn: () => getJson<Meta>('v1/meta.json'), retry, staleTime: 60_000 });

export const usePrediction = (path: string | undefined) =>
  useQuery({
    queryKey: ['prediction', path],
    queryFn: () => getJson<Prediction>(path!),
    enabled: !!path,
    retry,
    staleTime: 60_000,
  });

export const useStandings = () =>
  useQuery({ queryKey: ['standings'], queryFn: () => getJson<Standings>('v1/standings.json'), retry, staleTime: 60_000 });

export const useAccuracy = (season: number | undefined) =>
  useQuery({
    queryKey: ['accuracy', season],
    queryFn: () => getJson<Accuracy>(`v1/accuracy/${season}.json`),
    enabled: !!season,
    retry,
    staleTime: 5 * 60_000,
  });

export const useNews = () =>
  useQuery({ queryKey: ['news'], queryFn: () => getJson<News>('v1/news.json'), retry, staleTime: 5 * 60_000 });

export const resultsPath = (season: number, round: number) => `v1/races/${season}/${round}/results.json`;
export const predictionPath = (season: number, round: number) => `v1/races/${season}/${round}/prediction.json`;

export const fetchResults = (season: number, round: number) => getJson<Results>(resultsPath(season, round));
export const fetchPrediction = (season: number, round: number) => getJson<Prediction>(predictionPath(season, round));
