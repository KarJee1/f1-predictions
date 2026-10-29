import { useQuery } from '@tanstack/react-query';
import { router, Stack, useLocalSearchParams } from 'expo-router';
import { Alert, Platform, ScrollView, Share, StyleSheet, View } from 'react-native';

import { fetchResults, NotFound, useMeta } from '@/src/api';
import { Button, Card, Divider, Loading, Message, SectionTitle, Txt } from '@/src/components/ui';
import { useGroup, useGroupActions, useGroupRace } from '@/src/groups';
import { useColors } from '@/src/theme';

export default function GroupScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const c = useColors();
  const group = useGroup(id);
  const { leave } = useGroupActions();
  const g = group.data;

  const share = () =>
    Share.share({ message: `Join my F1 Predictions group "${g?.name}" with the code ${g?.code}. Let's see who calls the races best.` });

  const confirmLeave = () => {
    const go = () => leave.mutate(id!, { onSuccess: () => router.back() });
    if (Platform.OS === 'web') return go();
    Alert.alert('Leave this group?', 'Your points stay with you, and you can rejoin with the code.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Leave', style: 'destructive', onPress: go },
    ]);
  };

  return (
    <>
      <Stack.Screen options={{ title: '' }} />
      <ScrollView style={{ backgroundColor: c.background }} contentContainerStyle={{ paddingBottom: 40 }}>
        {group.isLoading ? (
          <Loading />
        ) : !g ? (
          <Message title="Couldn't load this group." body="It may have been deleted, or you're offline." />
        ) : (
          <>
            <View style={styles.hero}>
              <Txt variant="display">{g.name}</Txt>
              <Txt variant="label" muted>
                {g.member_count} {g.member_count === 1 ? 'member' : 'members'} · {g.season} season
              </Txt>
            </View>

            <Card style={styles.invite}>
              <View style={{ flex: 1 }}>
                <Txt variant="label" muted>
                  INVITE CODE
                </Txt>
                <Txt variant="title" selectable style={{ letterSpacing: 4, marginTop: 2 }}>
                  {g.code}
                </Txt>
              </View>
              <Button label="Share" onPress={share} />
            </Card>

            <SectionTitle>Leaderboard</SectionTitle>
            <Card>
              <View style={[styles.row, styles.headRow]}>
                <Txt variant="caption" muted style={styles.pos}>
                  POS
                </Txt>
                <View style={styles.stripe} />
                <Txt variant="caption" muted style={{ flex: 1 }}>
                  NAME
                </Txt>
                <Txt variant="caption" muted style={styles.num}>
                  RACES
                </Txt>
                <Txt variant="caption" muted style={styles.num}>
                  PTS
                </Txt>
              </View>
              {g.members.map((m, i) => (
                <View key={`${m.name}-${i}`}>
                  <Divider />
                  <View style={styles.row}>
                    <Txt variant="number" style={styles.pos}>
                      {m.rank}
                    </Txt>
                    <View style={[styles.stripe, { backgroundColor: m.is_me ? c.accent : 'transparent' }]} />
                    <Txt variant={m.is_me ? 'heading' : 'body'} numberOfLines={1} style={{ flex: 1 }}>
                      {m.name}
                      {m.is_me ? ' (you)' : ''}
                    </Txt>
                    <Txt muted style={styles.num}>
                      {m.races}
                    </Txt>
                    <Txt variant="number" style={styles.num}>
                      {m.points}
                    </Txt>
                  </View>
                </View>
              ))}
            </Card>
            <Txt variant="caption" muted style={styles.note}>
              Points are added after each race. Ties go to whoever nailed more exact positions.
            </Txt>

            <LastRacePicks id={g.id} />

            <View style={{ paddingHorizontal: 16, marginTop: 28 }}>
              <Button label="Leave group" kind="danger" onPress={confirmLeave} busy={leave.isPending} />
            </View>
          </>
        )}
      </ScrollView>
    </>
  );
}

function LastRacePicks({ id }: { id: string }) {
  const c = useColors();
  const meta = useMeta();
  const last = meta.data?.last_race;
  const race = useGroupRace(id, last?.season, last?.round);
  const results = useQuery({
    queryKey: ['results', last?.season, last?.round],
    queryFn: () => fetchResults(last!.season, last!.round),
    enabled: !!last,
    retry: (n, e) => !(e instanceof NotFound) && n < 2,
  });
  if (!last || !race.data?.locked) return null;
  const codes = new Map((results.data?.results ?? []).map((r) => [r.driver_id, r.code ?? r.last_name.slice(0, 3).toUpperCase()]));
  const winner = results.data?.results[0];

  return (
    <>
      <SectionTitle>{last.race_name}</SectionTitle>
      <Card>
        {race.data.members.map((m, i) => (
          <View key={`${m.name}-${i}`}>
            {i > 0 ? <Divider /> : null}
            <View style={styles.row}>
              <View style={{ flex: 1 }}>
                <Txt variant={m.is_me ? 'heading' : 'body'}>
                  {m.name}
                  {m.is_me ? ' (you)' : ''}
                </Txt>
                <Txt variant="caption" muted>
                  {m.order ? `Top 3: ${m.order.slice(0, 3).map((d) => codes.get(d) ?? d).join(', ')}` : 'No picks'}
                  {m.order && winner && m.order[0] === winner.driver_id ? ' · called the win' : ''}
                </Txt>
              </View>
              <Txt variant="number" color={m.score !== null ? c.text : c.muted}>
                {m.score ?? '–'}
              </Txt>
            </View>
          </View>
        ))}
      </Card>
    </>
  );
}

const styles = StyleSheet.create({
  hero: { paddingHorizontal: 16, paddingTop: 12, paddingBottom: 16 },
  invite: { flexDirection: 'row', alignItems: 'center', padding: 14 },
  row: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, gap: 8 },
  headRow: { paddingVertical: 8 },
  pos: { width: 28 },
  num: { width: 52, textAlign: 'right' },
  stripe: { width: 3, height: 18, borderRadius: 2 },
  note: { paddingHorizontal: 20, marginTop: 8 },
});
