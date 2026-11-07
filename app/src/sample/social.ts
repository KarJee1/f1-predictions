// A stand-in for the accounts and groups API, used with EXPO_PUBLIC_USE_SAMPLE_DATA=1 so the
// friend-group screens can be worked on (and screenshotted) without signing in.

type Row = { name: string; is_me: boolean; points: number; races: number; exact: number };

const groups: Record<string, { name: string; code: string; is_owner: boolean; members: Row[] }> = {
  pitwall: {
    name: 'Pit Wall Crew',
    code: 'K7PX2M',
    is_owner: true,
    members: [
      { name: 'Karthik', is_me: true, points: 1462, races: 18, exact: 41 },
      { name: 'Maya', is_me: false, points: 1498, races: 18, exact: 44 },
      { name: 'Dev', is_me: false, points: 1391, races: 17, exact: 35 },
      { name: 'Priya', is_me: false, points: 1377, races: 18, exact: 33 },
      { name: 'Sam', is_me: false, points: 1210, races: 15, exact: 29 },
      { name: 'Leo', is_me: false, points: 988, races: 12, exact: 21 },
    ],
  },
  uni: {
    name: 'Uni F1 Society',
    code: 'R4WQ9T',
    is_owner: false,
    members: [
      { name: 'Karthik', is_me: true, points: 1462, races: 18, exact: 41 },
      { name: 'Jordan', is_me: false, points: 1203, races: 16, exact: 30 },
      { name: 'Alex', is_me: false, points: 1150, races: 14, exact: 27 },
    ],
  },
};

const ORDER = ['antonelli', 'leclerc', 'max_verstappen', 'hamilton', 'norris', 'hadjar', 'piastri', 'russell', 'lawson', 'gasly'];
const picks: Record<string, string[]> = {
  Karthik: ['antonelli', 'max_verstappen', 'leclerc', 'hamilton', 'norris', 'russell', 'piastri', 'hadjar', 'lawson', 'gasly'],
  Maya: ORDER,
  Dev: ['max_verstappen', 'antonelli', 'hamilton', 'leclerc', 'russell', 'norris', 'hadjar', 'piastri', 'gasly', 'lawson'],
  Priya: ['leclerc', 'hamilton', 'antonelli', 'max_verstappen', 'norris', 'piastri', 'russell', 'hadjar', 'lawson', 'gasly'],
  Sam: ['norris', 'piastri', 'antonelli', 'max_verstappen', 'leclerc', 'hamilton', 'russell', 'hadjar', 'gasly', 'lawson'],
};

function score(order: string[]): number {
  return order.reduce((s, id, i) => {
    const pos = ORDER.indexOf(id);
    return pos < 0 ? s : s + Math.max(0, 5 - Math.abs(i - pos));
  }, 0);
}

function summary(id: string) {
  const g = groups[id];
  const members = [...g.members]
    .sort((a, b) => b.points - a.points || b.exact - a.exact)
    .map((m, i) => ({ ...m, rank: i + 1 }));
  return {
    id,
    name: g.name,
    code: g.code,
    is_owner: g.is_owner,
    season: 2026,
    member_count: members.length,
    my_rank: members.find((m) => m.is_me)!.rank,
    members,
  };
}

export function sampleSocial(method: string, path: string, body?: unknown): unknown {
  if (path === '/auth/apple') return { token: 'sample', user: { name: 'Karthik', needs_name: false } };
  if (path === '/me') return { name: 'Karthik', needs_name: false, ...(body as object) };
  if (path === '/groups' && method === 'GET') {
    return { season: 2026, groups: Object.keys(groups).map((id) => ({ ...summary(id), members: undefined })) };
  }
  const race = path.match(/^\/groups\/(\w+)\/races\/\d+\/(\d+)$/);
  if (race) {
    const g = groups[race[1]];
    return {
      locked: true,
      members: g.members
        .map((m) => ({ name: m.name, is_me: m.is_me, order: picks[m.name] ?? null, score: picks[m.name] ? score(picks[m.name]) : null, max: 50 }))
        .sort((a, b) => (b.score ?? -1) - (a.score ?? -1)),
    };
  }
  if (path === '/groups/join') return summary('uni');
  const group = path.match(/^\/groups\/(\w+)$/);
  if (group && groups[group[1]]) return summary(group[1]);
  if (method === 'POST' && path === '/groups') return summary('pitwall');
  if (path.startsWith('/picks/')) {
    if (method === 'GET') throw new Error('No picks for this race.');
    return { ok: true };
  }
  return {};
}
