import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { useAccuracy, useMeta, usePrediction, useStandings } from '@/src/api';
import { Bar, Card, Divider, DriverName, Loading, Message, Screen, Segmented, TeamStripe, Txt } from '@/src/components/ui';
import { pct, stageLabel, timeAgo } from '@/src/format';
import { useColors } from '@/src/theme';
import type { Accuracy, DriverPrediction, DriverStanding, Prediction, Standings, TeamStanding } from '@/src/types';

type Tab = 'race' | 'drivers' | 'teams' | 'accuracy';
const TABS: { value: Tab; label: string }[] = [
  { value: 'race', label: 'Race' },
  { value: 'drivers', label: 'Drivers' },
  { value: 'teams', label: 'Teams' },
  { value: 'accuracy', label: 'Accuracy' },
];

export default function PredictionsScreen() {
  const params = useLocalSearchParams<{ tab?: Tab }>();
  const [tab, setTab] = useState<Tab>(params.tab ?? 'race');
  useEffect(() => {
    if (params.tab) setTab(params.tab);
  }, [params.tab]);

  const meta = useMeta();
  const prediction = usePrediction(meta.data?.prediction_path);
  const standings = useStandings();
  const accuracy = useAccuracy(meta.data?.last_race?.season ?? meta.data?.season);

  const refresh = () => {
    meta.refetch();
    prediction.refetch();
    standings.refetch();
    accuracy.refetch();
  };

  return (
    <Screen
      title="Predictions"
      subtitle={meta.data?.next_race.race_name}
      refreshing={prediction.isRefetching || standings.isRefetching}
      onRefresh={refresh}
    >
      <Segmented options={TABS} value={tab} onChange={setTab} />
      <View style={{ height: 16 }} />
      {tab === 'race' && (prediction.data ? <RaceTab prediction={prediction.data} /> : <Pending loading={meta.isLoading || prediction.isLoading} />)}
      {tab === 'drivers' && (standings.data ? <DriversTab standings={standings.data} /> : <Pending loading={standings.isLoading} />)}
      {tab === 'teams' && (standings.data ? <TeamsTab standings={standings.data} /> : <Pending loading={standings.isLoading} />)}
      {tab === 'accuracy' && (accuracy.data ? <AccuracyTab accuracy={accuracy.data} /> : <Pending loading={accuracy.isLoading} empty="No races scored yet this season." />)}
    </Screen>
  );
}

function Pending({ loading, empty }: { loading: boolean; empty?: string }) {
  return loading ? <Loading /> : <Message title={empty ?? "Couldn't load this right now."} body="Pull down to try again." />;
}

// -- Race -----------------------------------------------------------------------------------------

function RaceTab({ prediction }: { prediction: Prediction }) {
  const c = useColors();
  const rain = prediction.weather?.rain_prob;
  return (
    <>
      <View style={styles.metaRow}>
        <View style={[styles.chip, { backgroundColor: c.surfaceAlt }]}>
          <Txt variant="caption">{stageLabel[prediction.stage]}</Txt>
        </View>
        {rain != null ? (
          <View style={[styles.chip, { backgroundColor: c.surfaceAlt }]}>
            <Txt variant="caption">{Math.round(rain * 100)}% chance of rain</Txt>
          </View>
        ) : null}
        <Txt variant="caption" muted style={{ marginLeft: 'auto' }}>
          Updated {timeAgo(prediction.generated_at)}
        </Txt>
      </View>
      <Card>
        <View style={[styles.tableHead, { borderBottomColor: c.border }]}>
          <Txt variant="caption" muted style={{ width: 28 }}>
            POS
          </Txt>
          <Txt variant="caption" muted style={{ flex: 1 }}>
            DRIVER
          </Txt>
          <Txt variant="caption" muted>
            WIN CHANCE
          </Txt>
        </View>
        {prediction.drivers.map((d, i) => (
          <View key={d.driver_id}>
            {i > 0 ? <Divider /> : null}
            <DriverRow d={d} leader={prediction.drivers[0].win_pct} />
          </View>
        ))}
      </Card>
      <Txt variant="caption" muted style={styles.footnote}>
        Listed in the model&apos;s predicted finishing order. Tap a driver to see why.
      </Txt>
    </>
  );
}

function DriverRow({ d, leader }: { d: DriverPrediction; leader: number }) {
  const c = useColors();
  return (
    <Pressable
      onPress={() => router.push({ pathname: '/driver/[id]', params: { id: d.driver_id } })}
      style={({ pressed }) => [styles.row, pressed && { backgroundColor: c.surfaceAlt }]}
    >
      <Txt variant="number" style={{ width: 28 }}>
        {d.predicted_position}
      </Txt>
      <TeamStripe color={d.team_color} />
      <View style={{ flex: 1, marginLeft: 10 }}>
        <DriverName first={d.first_name} last={d.last_name} />
        <Txt variant="caption" muted>
          {d.team_name}
        </Txt>
      </View>
      <View style={{ width: 92, alignItems: 'flex-end' }}>
        <Txt variant="number">{pct(d.win_pct)}</Txt>
        <View style={{ width: 80, marginTop: 4 }}>
          <Bar value={leader > 0 ? (d.win_pct / leader) * 100 : 0} />
        </View>
      </View>
    </Pressable>
  );
}

// -- Standings ------------------------------------------------------------------------------------

function Change({ value }: { value: number }) {
  const c = useColors();
  if (value === 0) {
    return (
      <Txt variant="label" muted style={styles.change}>
        –
      </Txt>
    );
  }
  const up = value > 0;
  return (
    <Txt variant="label" color={up ? c.up : c.down} style={styles.change}>
      {up ? '▲' : '▼'}
      {Math.abs(value)}
    </Txt>
  );
}

function StandingsNote({ standings }: { standings: Standings }) {
  return (
    <Txt variant="caption" muted style={[styles.footnote, { marginTop: 0, marginBottom: 12 }]}>
      Arrows show the standings after {standings.after_race?.race_name ?? 'the next race'} if the model&apos;s predicted
      order comes true.
    </Txt>
  );
}

function PointsCell({ points, predicted }: { points: number; predicted: number }) {
  const c = useColors();
  const gain = predicted - points;
  return (
    <View style={{ alignItems: 'flex-end', width: 70 }}>
      <Txt variant="number">{points}</Txt>
      <Txt variant="caption" color={gain > 0 ? c.up : c.muted}>
        {gain > 0 ? `+${gain} → ${predicted}` : `${predicted}`}
      </Txt>
    </View>
  );
}

function DriversTab({ standings }: { standings: Standings }) {
  return (
    <>
      <StandingsNote standings={standings} />
      <Card>
        {standings.drivers.map((d: DriverStanding, i) => (
          <View key={d.driver_id}>
            {i > 0 ? <Divider /> : null}
            <View style={styles.row}>
              <Txt variant="number" style={{ width: 28 }}>
                {d.position}
              </Txt>
              <TeamStripe color={d.team_color} />
              <View style={{ flex: 1, marginLeft: 10 }}>
                <DriverName first={d.first_name} last={d.last_name} />
                <Txt variant="caption" muted>
                  {d.team_name}
                </Txt>
              </View>
              <Change value={d.position_change} />
              <PointsCell points={d.points} predicted={d.predicted_points} />
            </View>
          </View>
        ))}
      </Card>
    </>
  );
}

function TeamsTab({ standings }: { standings: Standings }) {
  return (
    <>
      <StandingsNote standings={standings} />
      <Card>
        {standings.constructors.map((t: TeamStanding, i) => (
          <View key={t.team_id}>
            {i > 0 ? <Divider /> : null}
            <View style={styles.row}>
              <Txt variant="number" style={{ width: 28 }}>
                {t.position}
              </Txt>
              <TeamStripe color={t.team_color} />
              <Txt variant="heading" style={{ flex: 1, marginLeft: 10 }}>
                {t.team_name}
              </Txt>
              <Change value={t.position_change} />
              <PointsCell points={t.points} predicted={t.predicted_points} />
            </View>
          </View>
        ))}
      </Card>
    </>
  );
}

// -- Accuracy -------------------------------------------------------------------------------------

function AccuracyTab({ accuracy }: { accuracy: Accuracy }) {
  const c = useColors();
  const { summary, races } = accuracy;
  const backfilled = races.some((r) => r.backfilled);
  return (
    <>
      <View style={styles.tiles}>
        <Tile label="Winner called" value={`${Math.round(summary.winner_correct_pct)}%`} />
        <Tile label="Podium drivers" value={`${summary.avg_podium_hits.toFixed(1)} / 3`} />
        <Tile label="Races" value={`${summary.races}`} />
      </View>

      <Card style={{ padding: 14 }}>
        <Txt variant="label" muted>
          PODIUM DRIVERS CALLED, BY ROUND
        </Txt>
        <View style={styles.chart}>
          {races.map((r) => (
            <View key={r.round} style={styles.chartCol}>
              <View style={styles.chartTrack}>
                <View
                  style={{
                    height: `${(r.podium_hits / 3) * 100}%`,
                    backgroundColor: r.winner_correct ? c.accent : c.muted,
                    borderRadius: 3,
                    minHeight: 2,
                  }}
                />
              </View>
              <Txt variant="caption" muted style={{ fontSize: 10 }}>
                {r.round}
              </Txt>
            </View>
          ))}
        </View>
        <View style={{ flexDirection: 'row', gap: 14, marginTop: 8 }}>
          <Legend color={c.accent} label="Winner called" />
          <Legend color={c.muted} label="Winner missed" />
        </View>
      </Card>

      <Card style={{ marginTop: 12 }}>
        {[...races].reverse().map((r, i) => (
          <View key={r.round}>
            {i > 0 ? <Divider /> : null}
            <View style={styles.row}>
              <Txt variant="number" style={{ width: 28 }}>
                {r.round}
              </Txt>
              <View style={{ flex: 1 }}>
                <Txt variant="label">{r.race_name}</Txt>
                <Txt variant="caption" muted>
                  Predicted {r.predicted_top3.join(', ')} · Actual {r.actual_top3.join(', ')}
                </Txt>
              </View>
              <Txt variant="number" color={r.winner_correct ? c.up : c.muted}>
                {r.podium_hits}/3
              </Txt>
            </View>
          </View>
        ))}
      </Card>
      {backfilled ? (
        <Txt variant="caption" muted style={styles.footnote}>
          Earlier rounds were predicted after the fact, using a model trained only on the races before each one and the
          qualifying result.
        </Txt>
      ) : null}
    </>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  const c = useColors();
  return (
    <View style={[styles.tile, { backgroundColor: c.surface, borderColor: c.border }]}>
      <Txt variant="title">{value}</Txt>
      <Txt variant="caption" muted>
        {label}
      </Txt>
    </View>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
      <View style={{ width: 10, height: 10, borderRadius: 2, backgroundColor: color }} />
      <Txt variant="caption" muted>
        {label}
      </Txt>
    </View>
  );
}

const styles = StyleSheet.create({
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginHorizontal: 16, marginBottom: 10 },
  chip: { borderRadius: 999, paddingHorizontal: 10, paddingVertical: 3 },
  tableHead: { flexDirection: 'row', paddingHorizontal: 14, paddingVertical: 8, borderBottomWidth: StyleSheet.hairlineWidth },
  row: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14, paddingVertical: 10, minHeight: 56 },
  change: { width: 40, textAlign: 'right', marginRight: 8 },
  footnote: { marginHorizontal: 20, marginTop: 12 },
  tiles: { flexDirection: 'row', gap: 8, marginHorizontal: 16, marginBottom: 12 },
  tile: { flex: 1, borderRadius: 12, borderWidth: StyleSheet.hairlineWidth, padding: 12 },
  chart: { flexDirection: 'row', alignItems: 'flex-end', gap: 3, height: 90, marginTop: 10 },
  chartCol: { flex: 1, alignItems: 'center', gap: 4 },
  chartTrack: { height: 70, width: '100%', justifyContent: 'flex-end' },
});
