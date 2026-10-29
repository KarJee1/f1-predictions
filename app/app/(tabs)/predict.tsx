import { useQuery } from '@tanstack/react-query';
import { useFocusEffect } from 'expo-router';
import { useCallback, useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { fetchPrediction, fetchResults, NotFound, useMeta, usePrediction } from '@/src/api';
import { DragList } from '@/src/components/DragList';
import { Card, Divider, DriverName, Loading, Message, SectionTitle, TeamStripe, Txt } from '@/src/components/ui';
import { sessionTime } from '@/src/format';
import { allPicks, Picks, POINTS_PER_DRIVER, scoreOrder, usePicks } from '@/src/picks';
import { useColors } from '@/src/theme';
import type { DriverPrediction, Prediction } from '@/src/types';

const ROW = 52;

export default function PredictScreen() {
  const c = useColors();
  const insets = useSafeAreaInsets();
  const meta = useMeta();
  const prediction = usePrediction(meta.data?.prediction_path);
  const race = meta.data?.next_race;
  const { picks, loaded, save } = usePicks(race?.season, race?.round);
  const [dragging, setDragging] = useState(false);

  const locked = !!race?.race_start && new Date(race.race_start).getTime() <= Date.now();
  const drivers = prediction.data?.drivers ?? [];
  const byId = useMemo(() => new Map(drivers.map((d) => [d.driver_id, d])), [drivers]);

  // The user's order, kept in step with the current entry list (drivers can change mid-season).
  const order = useMemo(() => {
    const model = drivers.map((d) => d.driver_id);
    if (!picks) return model;
    const kept = picks.order.filter((id) => byId.has(id));
    return [...kept, ...model.filter((id) => !kept.includes(id))];
  }, [drivers, picks, byId]);

  const persist = (ids: string[]) => {
    if (!race) return;
    save({ season: race.season, round: race.round, race_name: race.race_name, order: ids, saved_at: new Date().toISOString() });
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.background }}
      contentContainerStyle={{ paddingTop: insets.top + 12, paddingBottom: 40 }}
      scrollEnabled={!dragging}
    >
      <View style={{ paddingHorizontal: 16, marginBottom: 12 }}>
        <Txt variant="display">Predict</Txt>
        {race ? (
          <Txt variant="label" muted>
            {race.race_name}
          </Txt>
        ) : null}
      </View>

      {meta.isLoading || prediction.isLoading || !loaded ? (
        meta.isLoading || prediction.isLoading ? <Loading /> : null
      ) : !race || !drivers.length ? (
        <Message title="No race to predict right now." body="Check back when the next race weekend starts." />
      ) : (
        <>
          <Card style={{ padding: 14, marginBottom: 12 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center' }}>
              <View style={{ flex: 1 }}>
                <Txt variant="heading">{locked ? 'Picks are locked' : picks ? 'Your picks are saved' : 'Set your finishing order'}</Txt>
                <Txt variant="caption" muted>
                  {locked
                    ? 'Lights are out. Your score appears here when the result is in.'
                    : `Drag the handles to reorder. Picks lock at lights out, ${sessionTime(race.race_start)}.`}
                </Txt>
              </View>
            </View>
            {!locked && picks ? (
              <Pressable onPress={() => persist(drivers.map((d) => d.driver_id))} style={{ marginTop: 10 }}>
                <Txt variant="label" color={c.accent}>
                  Reset to the model&apos;s order
                </Txt>
              </Pressable>
            ) : null}
          </Card>

          {locked ? <CurrentRaceScore picks={picks} prediction={prediction.data!} /> : null}

          <Card>
            <DragList
              ids={order}
              rowHeight={ROW}
              disabled={locked}
              onReorder={persist}
              onDragStateChange={setDragging}
              renderRow={(id, index, handle) => <PickRow d={byId.get(id)!} position={index + 1} handle={locked ? null : handle} />}
            />
          </Card>
        </>
      )}

      <SeasonTally />
    </ScrollView>
  );
}

function PickRow({ d, position, handle }: { d: DriverPrediction; position: number; handle: React.ReactNode }) {
  const c = useColors();
  return (
    <View style={[styles.row, { backgroundColor: c.surface, borderBottomColor: c.border }]}>
      <Txt variant="number" style={{ width: 30 }}>
        {position}
      </Txt>
      <TeamStripe color={d.team_color} height={24} />
      <View style={{ flex: 1, marginLeft: 10 }}>
        <DriverName first={d.first_name} last={d.last_name} size={15} />
      </View>
      <Txt variant="caption" muted style={{ marginRight: 4 }}>
        Model P{d.predicted_position}
      </Txt>
      {handle}
    </View>
  );
}

function CurrentRaceScore({ picks, prediction }: { picks: Picks | null; prediction: Prediction }) {
  const c = useColors();
  const { season, round } = prediction.race;
  const results = useQuery({
    queryKey: ['results', season, round],
    queryFn: () => fetchResults(season, round),
    retry: (n, e) => !(e instanceof NotFound) && n < 2,
  });
  if (!results.data) return null;
  const model = scoreOrder(
    prediction.drivers.map((d) => d.driver_id),
    results.data.results,
  );
  const mine = picks ? scoreOrder(picks.order, results.data.results) : null;
  return (
    <Card style={{ padding: 14, marginBottom: 12 }}>
      <Txt variant="label" muted>
        RESULT
      </Txt>
      <View style={{ flexDirection: 'row', marginTop: 8 }}>
        <ScoreBlock label="You" value={mine ? `${mine.score}` : '–'} color={c.accent} />
        <ScoreBlock label="Model" value={`${model.score}`} color={c.text} />
      </View>
      <Txt variant="caption" muted style={{ marginTop: 8 }}>
        {POINTS_PER_DRIVER} points for each exact position, one less for every place off. Max {model.max}.
      </Txt>
    </Card>
  );
}

function ScoreBlock({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <View style={{ flex: 1 }}>
      <Txt variant="display" color={color}>
        {value}
      </Txt>
      <Txt variant="caption" muted>
        {label}
      </Txt>
    </View>
  );
}

type TallyRow = { picks: Picks; mine: number; model: number; max: number };

function SeasonTally() {
  const c = useColors();
  const [version, setVersion] = useState(0);
  useFocusEffect(useCallback(() => setVersion((v) => v + 1), []));

  const tally = useQuery({
    queryKey: ['tally', version],
    queryFn: async (): Promise<TallyRow[]> => {
      const rows: TallyRow[] = [];
      for (const p of await allPicks()) {
        try {
          const [res, pred] = await Promise.all([fetchResults(p.season, p.round), fetchPrediction(p.season, p.round)]);
          const mine = scoreOrder(p.order, res.results);
          const model = scoreOrder(
            pred.drivers.map((d) => d.driver_id),
            res.results,
          );
          rows.push({ picks: p, mine: mine.score, model: model.score, max: mine.max });
        } catch {
          // Not raced yet, or the result isn't published.
        }
      }
      return rows;
    },
  });

  if (!tally.data?.length) return null;
  const you = tally.data.reduce((s, r) => s + r.mine, 0);
  const model = tally.data.reduce((s, r) => s + r.model, 0);
  return (
    <>
      <SectionTitle>Your season</SectionTitle>
      <Card style={{ padding: 14 }}>
        <View style={{ flexDirection: 'row' }}>
          <ScoreBlock label="You" value={`${you}`} color={c.accent} />
          <ScoreBlock label="Model" value={`${model}`} color={c.text} />
        </View>
      </Card>
      <Card style={{ marginTop: 12 }}>
        {tally.data.map((r, i) => (
          <View key={`${r.picks.season}-${r.picks.round}`}>
            {i > 0 ? <Divider /> : null}
            <View style={styles.tallyRow}>
              <Txt variant="label" style={{ flex: 1 }}>
                {r.picks.race_name}
              </Txt>
              <Txt variant="number" color={r.mine >= r.model ? c.up : c.text} style={{ width: 48, textAlign: 'right' }}>
                {r.mine}
              </Txt>
              <Txt variant="number" muted style={{ width: 48, textAlign: 'right' }}>
                {r.model}
              </Txt>
            </View>
          </View>
        ))}
      </Card>
    </>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', height: ROW, paddingLeft: 14, borderBottomWidth: StyleSheet.hairlineWidth },
  tallyRow: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14, paddingVertical: 12 },
});
