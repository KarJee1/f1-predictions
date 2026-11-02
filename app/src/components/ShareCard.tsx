import { ComponentRef, forwardRef } from 'react';
import { Image, StyleSheet, Text, View } from 'react-native';

import { fonts, palette, teamColor } from '../theme';
import type { DriverPrediction } from '../types';

// The image people send to their group chat: their top 10 for the race, always in the dark style.
// Rendered off screen and captured with react-native-view-shot.

export const SHARE_WIDTH = 360;
const c = palette.dark;

type Props = { raceName: string; season: number; drivers: DriverPrediction[]; modelWinner?: DriverPrediction };

export const ShareCard = forwardRef<ComponentRef<typeof View>, Props>(function ShareCard({ raceName, season, drivers, modelWinner }, ref) {
  return (
    <View ref={ref} collapsable={false} style={styles.card}>
      <View style={styles.redBar} />
      <Text style={styles.kicker}>MY PREDICTION · {season}</Text>
      <Text style={styles.race}>{raceName}</Text>

      <View style={{ marginTop: 14 }}>
        {drivers.slice(0, 10).map((d, i) => (
          <View key={d.driver_id} style={[styles.row, i === 0 && styles.firstRow]}>
            <Text style={[styles.pos, i < 3 && { color: c.text }]}>{i + 1}</Text>
            <View style={[styles.stripe, { backgroundColor: teamColor(d.team_color) }]} />
            <Text numberOfLines={1} style={styles.name}>
              <Text style={{ fontFamily: fonts.regular }}>{d.first_name} </Text>
              <Text style={{ fontFamily: fonts.bold }}>{d.last_name.toUpperCase()}</Text>
            </Text>
            <Text numberOfLines={1} style={styles.team}>
              {d.team_name}
            </Text>
          </View>
        ))}
      </View>

      <View style={styles.footer}>
        <Image source={require('../../assets/images/icon.png')} style={styles.icon} />
        <View style={{ flex: 1 }}>
          <Text style={styles.brand}>F1 PREDICTIONS</Text>
          {modelWinner ? <Text style={styles.footNote}>The model has {modelWinner.last_name} to win. Think you can beat it?</Text> : null}
        </View>
      </View>
    </View>
  );
});

const styles = StyleSheet.create({
  card: { width: SHARE_WIDTH, backgroundColor: c.background, padding: 20, paddingTop: 0 },
  redBar: { height: 6, backgroundColor: c.accent, marginHorizontal: -20, marginBottom: 18 },
  kicker: { fontFamily: fonts.semibold, fontSize: 11, letterSpacing: 1.2, color: c.accent },
  race: { fontFamily: fonts.black, fontSize: 22, lineHeight: 28, color: c.text, marginTop: 4 },
  row: { flexDirection: 'row', alignItems: 'center', height: 34, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: c.border },
  firstRow: { borderTopWidth: 0 },
  pos: { width: 32, fontFamily: fonts.wide, fontSize: 15, color: c.muted },
  stripe: { width: 4, height: 18, borderRadius: 2, marginRight: 10 },
  name: { flex: 1, color: c.text, fontSize: 15 },
  team: { maxWidth: 110, fontFamily: fonts.regular, fontSize: 11, color: c.muted, marginLeft: 8 },
  footer: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 16, paddingTop: 14, borderTopWidth: 1, borderTopColor: c.border },
  icon: { width: 34, height: 34, borderRadius: 8 },
  brand: { fontFamily: fonts.wide, fontSize: 12, letterSpacing: 0.5, color: c.text },
  footNote: { fontFamily: fonts.regular, fontSize: 11, color: c.muted, marginTop: 2 },
});
