import type { RaceInfo, Stage } from './types';

export const stageLabel: Record<Stage, string> = {
  pre: 'Pre-weekend',
  practice: 'After practice',
  quali: 'After qualifying',
};

export function pct(value: number): string {
  if (value > 0 && value < 0.1) return '<0.1%';
  return `${value.toFixed(value >= 10 ? 0 : 1)}%`;
}

export function sessionTime(iso: string | null): string {
  if (!iso) return 'TBC';
  const d = new Date(iso);
  return d.toLocaleString(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit' });
}

export function raceDates(race: RaceInfo): string {
  const start = race.sessions.fp1 ?? race.race_start;
  const end = race.race_start;
  if (!start || !end) return '';
  const s = new Date(start);
  const e = new Date(end);
  const month = (d: Date) => d.toLocaleString(undefined, { month: 'short' });
  return s.getMonth() === e.getMonth()
    ? `${s.getDate()}–${e.getDate()} ${month(e)}`
    : `${s.getDate()} ${month(s)} – ${e.getDate()} ${month(e)}`;
}

export function timeAgo(iso: string, now = Date.now()): string {
  const mins = Math.round((now - new Date(iso).getTime()) / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export type NextSession = { label: string; start: Date };

export function upcomingSessions(race: RaceInfo): NextSession[] {
  const list: [string, string | null][] = [
    ['Practice 1', race.sessions.fp1],
    ['Practice 2', race.sessions.fp2],
    ['Practice 3', race.sessions.fp3],
    ['Sprint Qualifying', race.sessions.sprint_quali ?? null],
    ['Sprint', race.sessions.sprint],
    ['Qualifying', race.sessions.quali],
    ['Race', race.race_start],
  ];
  return list
    .filter((s): s is [string, string] => !!s[1])
    .map(([label, iso]) => ({ label, start: new Date(iso) }))
    .sort((a, b) => a.start.getTime() - b.start.getTime());
}

export function countdown(target: Date, now: Date): string {
  const ms = target.getTime() - now.getTime();
  if (ms <= 0) return 'Live';
  const d = Math.floor(ms / 86_400_000);
  const h = Math.floor((ms % 86_400_000) / 3_600_000);
  const m = Math.floor((ms % 3_600_000) / 60_000);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}
