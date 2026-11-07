import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAccount } from './account';

export type Standing = { name: string; is_me: boolean; points: number; races: number; exact: number; rank: number };

export type GroupSummary = {
  id: string;
  name: string;
  code: string;
  is_owner: boolean;
  season: number;
  member_count: number;
  my_rank: number;
};

export type Group = GroupSummary & { members: Standing[] };

export type GroupRace = {
  locked: boolean;
  members: { name: string; is_me: boolean; order: string[] | null; score: number | null; max: number | null }[];
};

export function useGroups() {
  const { signedIn, call } = useAccount();
  return useQuery({
    queryKey: ['social', 'groups'],
    queryFn: () => call<{ season: number; groups: GroupSummary[] }>('GET', '/groups'),
    enabled: signedIn,
    staleTime: 60_000,
  });
}

export function useGroup(id: string | undefined) {
  const { signedIn, call } = useAccount();
  return useQuery({
    queryKey: ['social', 'group', id],
    queryFn: () => call<Group>('GET', `/groups/${id}`),
    enabled: signedIn && !!id,
    staleTime: 60_000,
  });
}

export function useGroupRace(id: string | undefined, season: number | undefined, round: number | undefined) {
  const { signedIn, call } = useAccount();
  return useQuery({
    queryKey: ['social', 'group-race', id, season, round],
    queryFn: () => call<GroupRace>('GET', `/groups/${id}/races/${season}/${round}`),
    enabled: signedIn && !!id && !!season && !!round,
    staleTime: 60_000,
  });
}

export function useGroupActions() {
  const { call } = useAccount();
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: ['social'] });
  const create = useMutation({ mutationFn: (name: string) => call<Group>('POST', '/groups', { name }), onSuccess: refresh });
  const join = useMutation({ mutationFn: (code: string) => call<Group>('POST', '/groups/join', { code }), onSuccess: refresh });
  const leave = useMutation({ mutationFn: (id: string) => call('DELETE', `/groups/${id}/membership`), onSuccess: refresh });
  return { create, join, leave };
}
