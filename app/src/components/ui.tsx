import { ReactNode } from 'react';
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextProps,
  View,
  ViewStyle,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { fonts, teamColor, useColors } from '../theme';

type Variant = 'display' | 'title' | 'heading' | 'body' | 'label' | 'caption' | 'number';

const variants: Record<Variant, { fontFamily: string; fontSize: number; lineHeight: number; letterSpacing?: number }> = {
  display: { fontFamily: fonts.black, fontSize: 32, lineHeight: 36, letterSpacing: -0.5 },
  title: { fontFamily: fonts.bold, fontSize: 22, lineHeight: 26 },
  heading: { fontFamily: fonts.bold, fontSize: 17, lineHeight: 22 },
  body: { fontFamily: fonts.regular, fontSize: 15, lineHeight: 21 },
  label: { fontFamily: fonts.semibold, fontSize: 13, lineHeight: 17, letterSpacing: 0.2 },
  caption: { fontFamily: fonts.regular, fontSize: 12, lineHeight: 16 },
  number: { fontFamily: fonts.bold, fontSize: 17, lineHeight: 20 },
};

export function Txt({
  variant = 'body',
  muted,
  color,
  style,
  ...rest
}: TextProps & { variant?: Variant; muted?: boolean; color?: string }) {
  const c = useColors();
  return <Text {...rest} style={[variants[variant], { color: color ?? (muted ? c.muted : c.text) }, style]} />;
}

/** A scrolling page with a large title, like the official app's top-level screens. */
export function Screen({
  title,
  subtitle,
  right,
  children,
  refreshing,
  onRefresh,
  scroll = true,
}: {
  title: string;
  subtitle?: string;
  right?: ReactNode;
  children: ReactNode;
  refreshing?: boolean;
  onRefresh?: () => void;
  scroll?: boolean;
}) {
  const c = useColors();
  const insets = useSafeAreaInsets();
  const header = (
    <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
      <View style={{ flex: 1 }}>
        <Txt variant="display">{title}</Txt>
        {subtitle ? (
          <Txt variant="label" muted style={{ marginTop: 2 }}>
            {subtitle}
          </Txt>
        ) : null}
      </View>
      {right}
    </View>
  );
  if (!scroll) {
    return (
      <View style={{ flex: 1, backgroundColor: c.background }}>
        {header}
        {children}
      </View>
    );
  }
  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.background }}
      contentContainerStyle={{ paddingBottom: 32 }}
      refreshControl={onRefresh ? <RefreshControl refreshing={!!refreshing} onRefresh={onRefresh} tintColor={c.muted} /> : undefined}
    >
      {header}
      {children}
    </ScrollView>
  );
}

export function Card({ children, style, onPress }: { children: ReactNode; style?: ViewStyle; onPress?: () => void }) {
  const c = useColors();
  const body = <View style={[styles.card, { backgroundColor: c.surface, borderColor: c.border }, style]}>{children}</View>;
  if (!onPress) return body;
  return (
    <Pressable onPress={onPress} style={({ pressed }) => ({ opacity: pressed ? 0.85 : 1 })}>
      {body}
    </Pressable>
  );
}

export function SectionTitle({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <View style={styles.section}>
      <Txt variant="title" style={{ flex: 1 }}>
        {children}
      </Txt>
      {right}
    </View>
  );
}

export function TeamStripe({ color, height = 28 }: { color: string | null | undefined; height?: number }) {
  return <View style={{ width: 4, height, borderRadius: 2, backgroundColor: teamColor(color) }} />;
}

/** Driver name in the official style: first name light, last name bold and uppercase. */
export function DriverName({ first, last, size = 16 }: { first: string; last: string; size?: number }) {
  const c = useColors();
  return (
    <Text numberOfLines={1} style={{ color: c.text, fontSize: size, lineHeight: size + 4 }}>
      <Text style={{ fontFamily: fonts.regular }}>{first} </Text>
      <Text style={{ fontFamily: fonts.bold }}>{last.toUpperCase()}</Text>
    </Text>
  );
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  const c = useColors();
  return (
    <View style={[styles.segmented, { backgroundColor: c.surfaceAlt }]}>
      {options.map((o) => {
        const active = o.value === value;
        return (
          <Pressable
            key={o.value}
            onPress={() => onChange(o.value)}
            style={[styles.segment, active && { backgroundColor: c.surface, borderColor: c.border }]}
            accessibilityRole="tab"
            accessibilityState={{ selected: active }}
          >
            <Txt variant="label" color={active ? c.text : c.muted}>
              {o.label}
            </Txt>
          </Pressable>
        );
      })}
    </View>
  );
}

export function Bar({ value, color, height = 4 }: { value: number; color?: string; height?: number }) {
  const c = useColors();
  return (
    <View style={{ height, borderRadius: height / 2, backgroundColor: c.surfaceAlt, overflow: 'hidden' }}>
      <View style={{ width: `${Math.max(0, Math.min(100, value))}%`, height, backgroundColor: color ?? c.accent }} />
    </View>
  );
}

export function Loading() {
  const c = useColors();
  return (
    <View style={{ padding: 40, alignItems: 'center' }}>
      <ActivityIndicator color={c.muted} />
    </View>
  );
}

export function Message({ title, body }: { title: string; body?: string }) {
  return (
    <View style={{ padding: 24, alignItems: 'center' }}>
      <Txt variant="heading" style={{ textAlign: 'center' }}>
        {title}
      </Txt>
      {body ? (
        <Txt muted style={{ textAlign: 'center', marginTop: 6 }}>
          {body}
        </Txt>
      ) : null}
    </View>
  );
}

export function Divider() {
  const c = useColors();
  return <View style={{ height: StyleSheet.hairlineWidth, backgroundColor: c.border, marginLeft: 16 }} />;
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'flex-end', paddingHorizontal: 16, paddingBottom: 12 },
  card: { borderRadius: 12, borderWidth: StyleSheet.hairlineWidth, marginHorizontal: 16, overflow: 'hidden' },
  section: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, marginTop: 24, marginBottom: 10 },
  segmented: { flexDirection: 'row', marginHorizontal: 16, borderRadius: 10, padding: 3 },
  segment: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: 7,
    borderRadius: 8,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'transparent',
  },
});
