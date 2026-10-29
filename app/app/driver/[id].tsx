import { useLocalSearchParams } from 'expo-router';
import { ScrollView, StyleSheet, View } from 'react-native';

import { useMeta, usePrediction } from '@/src/api';
import { Card, DriverName, Loading, Message, Txt } from '@/src/components/ui';
import { pct, stageLabel } from '@/src/format';
import { teamColor, useColors } from '@/src/theme';

export default function DriverScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const c = useColors();
  const meta = useMeta();
  const prediction = usePrediction(meta.data?.prediction_path);
  const d = prediction.data?.drivers.find((x) => x.driver_id === id);

  if (prediction.isLoading || meta.isLoading) return <Loading />;
  if (!d || !prediction.data) return <Message title="Driver not found." />;

  const color = teamColor(d.team_color);
  const maxP = Math.max(...d.position_distribution, 0.0001);

  return (
    <ScrollView style={{ backgroundColor: c.background }} contentContainerStyle={{ paddingBottom: 40 }}>
      <View style={[styles.hero, { borderLeftColor: color }]}>
        <View style={{ flex: 1 }}>
          <DriverName first={d.first_name} last={d.last_name} size={24} />
          <Txt muted>{d.team_name}</Txt>
        </View>
        {d.number ? (
          <Txt variant="display" color={color} style={{ fontSize: 44, lineHeight: 48 }}>
            {d.number}
          </Txt>
        ) : null}
      </View>

      <View style={styles.stats}>
        <Stat label="Predicted" value={`P${d.predicted_position}`} />
        <Stat label="Win" value={pct(d.win_pct)} accent />
        <Stat label="Podium" value={pct(d.podium_pct)} />
        <Stat label="Points" value={pct(d.points_pct)} />
      </View>

      <Card style={{ padding: 16 }}>
        <Txt variant="label" muted>
          WHY
        </Txt>
        <Txt style={{ marginTop: 6, fontSize: 16, lineHeight: 23 }}>{d.summary}</Txt>
        <View style={{ marginTop: 12, gap: 8 }}>
          {d.factors.map((f) => (
            <View key={f.feature} style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <Txt variant="label" color={f.impact >= 0 ? c.up : c.down} style={{ width: 14 }}>
                {f.impact >= 0 ? '▲' : '▼'}
              </Txt>
              <Txt style={{ flex: 1 }}>{f.text}</Txt>
            </View>
          ))}
        </View>
      </Card>

      <Card style={{ padding: 16, marginTop: 12 }}>
        <Txt variant="label" muted>
          FINISHING POSITION CHANCES
        </Txt>
        <View style={styles.dist}>
          {d.position_distribution.map((p, i) => (
            <View key={i} style={styles.distCol}>
              <View style={styles.distTrack}>
                <View style={{ height: `${(p / maxP) * 100}%`, backgroundColor: i < 3 ? c.accent : color, borderRadius: 2, opacity: i < 3 ? 1 : 0.7 }} />
              </View>
              <Txt variant="caption" muted style={{ fontSize: 9, lineHeight: 12 }}>
                {i % 2 === 0 ? i + 1 : ' '}
              </Txt>
            </View>
          ))}
        </View>
        <Txt variant="caption" muted style={{ marginTop: 8 }}>
          Expected finish P{d.expected_position.toFixed(1)} · {pct(d.dnf_pct)} chance of not finishing
        </Txt>
      </Card>

      <Txt variant="caption" muted style={{ marginHorizontal: 20, marginTop: 12 }}>
        {stageLabel[prediction.data.stage]} prediction for the {prediction.data.race.race_name}, from thousands of
        simulated races.
      </Txt>
    </ScrollView>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  const c = useColors();
  return (
    <View style={[styles.stat, { backgroundColor: c.surface, borderColor: c.border }]}>
      <Txt variant="title" color={accent ? c.accent : c.text}>
        {value}
      </Txt>
      <Txt variant="caption" muted>
        {label}
      </Txt>
    </View>
  );
}

const styles = StyleSheet.create({
  hero: { flexDirection: 'row', alignItems: 'center', margin: 16, marginTop: 24, paddingLeft: 12, borderLeftWidth: 5 },
  stats: { flexDirection: 'row', gap: 8, marginHorizontal: 16, marginBottom: 12 },
  stat: { flex: 1, borderRadius: 12, borderWidth: StyleSheet.hairlineWidth, paddingVertical: 10, alignItems: 'center' },
  dist: { flexDirection: 'row', alignItems: 'flex-end', gap: 2, marginTop: 12 },
  distCol: { flex: 1, alignItems: 'center', gap: 2 },
  distTrack: { height: 80, width: '100%', justifyContent: 'flex-end' },
});
