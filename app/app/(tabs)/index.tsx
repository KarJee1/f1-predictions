import { router } from 'expo-router';
import { SymbolView } from 'expo-symbols';
import * as WebBrowser from 'expo-web-browser';
import { useEffect, useState } from 'react';
import { Image, Pressable, StyleSheet, View } from 'react-native';

import { useAccuracy, useMeta, useNews, usePrediction } from '@/src/api';
import { Card, Divider, Loading, Message, Screen, SectionTitle, TeamStripe, Txt } from '@/src/components/ui';
import { countdown, pct, raceDates, sessionTime, stageLabel, timeAgo, upcomingSessions } from '@/src/format';
import { teamColor, useColors } from '@/src/theme';
import type { NewsItem, Prediction, RaceInfo } from '@/src/types';

export default function HomeScreen() {
  const c = useColors();
  const meta = useMeta();
  const prediction = usePrediction(meta.data?.prediction_path);
  const accuracy = useAccuracy(meta.data?.last_race?.season);
  const news = useNews();

  const refreshing = meta.isRefetching || news.isRefetching;
  const refresh = () => {
    meta.refetch();
    news.refetch();
    prediction.refetch();
  };

  const lastScored = meta.data?.last_race
    ? accuracy.data?.races.find((r) => r.round === meta.data!.last_race!.round)
    : undefined;

  return (
    <Screen
      title="Home"
      refreshing={refreshing}
      onRefresh={refresh}
      right={
        <Pressable onPress={() => router.push('/settings')} hitSlop={12} accessibilityLabel="Settings">
          <SymbolView name={{ ios: 'gearshape', android: 'settings', web: 'settings' }} tintColor={c.text} size={24} />
        </Pressable>
      }
    >
      {meta.isLoading ? (
        <Loading />
      ) : meta.error || !meta.data ? (
        <Message title="Couldn't load the latest race." body="Pull down to try again." />
      ) : (
        <NextRace race={meta.data.next_race} prediction={prediction.data} />
      )}

      {meta.data?.last_race && lastScored ? (
        <Card style={{ marginTop: 12 }} onPress={() => router.navigate('/predictions?tab=accuracy')}>
          <View style={styles.lastRace}>
            <View style={{ flex: 1 }}>
              <Txt variant="caption" muted>
                LAST RACE · {meta.data.last_race.race_name.toUpperCase()}
              </Txt>
              <Txt variant="heading" style={{ marginTop: 2 }}>
                {lastScored.actual_top3.join('  ·  ')}
              </Txt>
              <Txt variant="caption" muted style={{ marginTop: 2 }}>
                Model picked {lastScored.predicted_top3.join(', ')} · {lastScored.podium_hits}/3 on the podium
              </Txt>
            </View>
            <View style={[styles.badge, { backgroundColor: lastScored.winner_correct ? c.up : c.surfaceAlt }]}>
              <Txt variant="label" color={lastScored.winner_correct ? '#fff' : c.muted}>
                {lastScored.winner_correct ? 'Called the win' : 'Missed the win'}
              </Txt>
            </View>
          </View>
        </Card>
      ) : null}

      <SectionTitle>Latest news</SectionTitle>
      {news.isLoading ? (
        <Loading />
      ) : !news.data?.items.length ? (
        <Message title="No news yet." />
      ) : (
        <Card>
          {news.data.items.map((item, i) => (
            <View key={item.url}>
              {i > 0 ? <Divider /> : null}
              <NewsRow item={item} />
            </View>
          ))}
        </Card>
      )}
      <Txt variant="caption" muted style={{ textAlign: 'center', marginTop: 16, marginHorizontal: 24 }}>
        Headlines link to the publishers&apos; sites.
      </Txt>
    </Screen>
  );
}

function useNow(intervalMs = 30_000) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}

function NextRace({ race, prediction }: { race: RaceInfo; prediction: Prediction | undefined }) {
  const c = useColors();
  const now = useNow();
  const sessions = upcomingSessions(race);
  const next = sessions.find((s) => s.start.getTime() + 60 * 60_000 > now.getTime());
  const top3 = prediction?.drivers.slice(0, 3) ?? [];

  return (
    <Card onPress={() => router.navigate('/predictions')}>
      <View style={[styles.raceHeader, { backgroundColor: c.accent }]}>
        <Txt variant="label" color={c.accentText}>
          ROUND {race.round}
        </Txt>
        <Txt variant="label" color={c.accentText}>
          {raceDates(race)}
        </Txt>
      </View>
      <View style={{ padding: 16 }}>
        <Txt variant="title">{race.race_name}</Txt>
        <Txt muted>{[race.circuit_name, race.locality].filter(Boolean).join(' · ')}</Txt>
        {next ? (
          <View style={[styles.countdown, { borderColor: c.border }]}>
            <View style={{ flex: 1 }}>
              <Txt variant="caption" muted>
                NEXT UP
              </Txt>
              <Txt variant="heading">{next.label}</Txt>
              <Txt variant="caption" muted>
                {sessionTime(next.start.toISOString())}
              </Txt>
            </View>
            <Txt variant="display" color={c.accent}>
              {countdown(next.start, now)}
            </Txt>
          </View>
        ) : null}

        {top3.length ? (
          <>
            <View style={styles.rowBetween}>
              <Txt variant="label" muted>
                MODEL&apos;S PODIUM
              </Txt>
              {prediction ? (
                <Txt variant="caption" muted>
                  {stageLabel[prediction.stage]}
                </Txt>
              ) : null}
            </View>
            <View style={styles.podium}>
              {top3.map((d, i) => (
                <View key={d.driver_id} style={[styles.podiumCell, { backgroundColor: c.surfaceAlt }]}>
                  <View style={[styles.podiumStripe, { backgroundColor: teamColor(d.team_color) }]} />
                  <Txt variant="caption" muted>
                    P{i + 1}
                  </Txt>
                  <Txt variant="heading">{d.code}</Txt>
                  <Txt variant="number" color={c.accent}>
                    {pct(d.win_pct)}
                  </Txt>
                  <Txt variant="caption" muted>
                    to win
                  </Txt>
                </View>
              ))}
            </View>
          </>
        ) : null}
      </View>
    </Card>
  );
}

function NewsRow({ item }: { item: NewsItem }) {
  const c = useColors();
  // Drop the thumbnail if it fails to load rather than leaving an empty box.
  const [imageFailed, setImageFailed] = useState(false);
  const image = imageFailed ? null : item.image;
  return (
    <Pressable onPress={() => WebBrowser.openBrowserAsync(item.url)} style={({ pressed }) => [styles.news, pressed && { opacity: 0.7 }]}>
      <View style={{ flex: 1, paddingRight: image ? 12 : 0 }}>
        <Txt variant="label" numberOfLines={3} style={{ fontSize: 15, lineHeight: 20 }}>
          {item.title}
        </Txt>
        <View style={{ flexDirection: 'row', alignItems: 'center', marginTop: 6, gap: 6 }}>
          <TeamStripe color={c.accent} height={10} />
          <Txt variant="caption" muted>
            {item.source} · {timeAgo(item.published_at)}
          </Txt>
        </View>
      </View>
      {image ? (
        <Image source={{ uri: image }} onError={() => setImageFailed(true)} style={[styles.thumb, { backgroundColor: c.surfaceAlt }]} />
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  raceHeader: { flexDirection: 'row', justifyContent: 'space-between', paddingHorizontal: 16, paddingVertical: 8 },
  countdown: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 14,
    paddingTop: 12,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  rowBetween: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 16, marginBottom: 8 },
  podium: { flexDirection: 'row', gap: 8 },
  podiumCell: { flex: 1, borderRadius: 10, padding: 10, overflow: 'hidden' },
  podiumStripe: { position: 'absolute', left: 0, top: 0, bottom: 0, width: 4 },
  lastRace: { flexDirection: 'row', alignItems: 'center', padding: 14, gap: 12 },
  badge: { borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4 },
  news: { flexDirection: 'row', padding: 14, alignItems: 'center' },
  thumb: { width: 84, height: 60, borderRadius: 8 },
});
