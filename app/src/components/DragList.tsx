import * as Haptics from 'expo-haptics';
import { ReactNode, useEffect } from 'react';
import { View } from 'react-native';
import { GestureDetector, usePanGesture } from 'react-native-gesture-handler';
import Animated, { SharedValue, useAnimatedStyle, useSharedValue, withSpring } from 'react-native-reanimated';
import { scheduleOnRN } from 'react-native-worklets';

type Positions = Record<string, number>;

function toPositions(ids: string[]): Positions {
  const out: Positions = {};
  ids.forEach((id, i) => (out[id] = i));
  return out;
}

function move(positions: Positions, from: number, to: number): Positions {
  'worklet';
  const next: Positions = {};
  for (const id in positions) {
    const p = positions[id];
    if (p === from) next[id] = to;
    else if (from < to && p > from && p <= to) next[id] = p - 1;
    else if (from > to && p >= to && p < from) next[id] = p + 1;
    else next[id] = p;
  }
  return next;
}

/**
 * A fixed-row-height list the user reorders by dragging each row's handle.
 * renderRow gets the item's current index and a handle element to place in the row.
 */
export function DragList({
  ids,
  rowHeight,
  disabled,
  onReorder,
  onDragStateChange,
  renderRow,
}: {
  ids: string[];
  rowHeight: number;
  disabled?: boolean;
  onReorder: (ids: string[]) => void;
  onDragStateChange?: (dragging: boolean) => void;
  renderRow: (id: string, index: number, handle: ReactNode) => ReactNode;
}) {
  const positions = useSharedValue<Positions>(toPositions(ids));
  const activeId = useSharedValue<string | null>(null);
  const key = ids.join('|');

  useEffect(() => {
    positions.value = toPositions(ids);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const finish = (p: Positions) => {
    onReorder(Object.keys(p).sort((a, b) => p[a] - p[b]));
    onDragStateChange?.(false);
  };

  return (
    <View style={{ height: ids.length * rowHeight }}>
      {ids.map((id, index) => (
        <Row
          key={id}
          id={id}
          count={ids.length}
          rowHeight={rowHeight}
          positions={positions}
          activeId={activeId}
          disabled={!!disabled}
          onStart={() => onDragStateChange?.(true)}
          onEnd={finish}
        >
          {(handle) => renderRow(id, index, handle)}
        </Row>
      ))}
    </View>
  );
}

function Row({
  id,
  count,
  rowHeight,
  positions,
  activeId,
  disabled,
  onStart,
  onEnd,
  children,
}: {
  id: string;
  count: number;
  rowHeight: number;
  positions: SharedValue<Positions>;
  activeId: SharedValue<string | null>;
  disabled: boolean;
  onStart: () => void;
  onEnd: (p: Positions) => void;
  children: (handle: ReactNode) => ReactNode;
}) {
  const startTop = useSharedValue(0);
  const dragTop = useSharedValue(0);

  const tick = () => Haptics.selectionAsync().catch(() => {});

  const pan = usePanGesture({
    enabled: !disabled,
    minDistance: 0,
    onActivate: () => {
      'worklet';
      activeId.value = id;
      startTop.value = positions.value[id] * rowHeight;
      dragTop.value = startTop.value;
      scheduleOnRN(onStart);
    },
    onUpdate: (e) => {
      'worklet';
      dragTop.value = Math.max(0, Math.min((count - 1) * rowHeight, startTop.value + e.translationY));
      const target = Math.round(dragTop.value / rowHeight);
      const current = positions.value[id];
      if (target !== current) {
        positions.value = move(positions.value, current, target);
        scheduleOnRN(tick);
      }
    },
    onFinalize: () => {
      'worklet';
      if (activeId.value === id) {
        activeId.value = null;
        scheduleOnRN(onEnd, positions.value);
      }
    },
  });

  const style = useAnimatedStyle(() => {
    const dragging = activeId.value === id;
    return {
      position: 'absolute',
      left: 0,
      right: 0,
      height: rowHeight,
      top: dragging ? dragTop.value : withSpring(positions.value[id] * rowHeight, { damping: 22, stiffness: 260 }),
      zIndex: dragging ? 10 : 0,
      transform: [{ scale: withSpring(dragging ? 1.02 : 1) }],
      shadowOpacity: withSpring(dragging ? 0.25 : 0),
      shadowRadius: 8,
      shadowOffset: { width: 0, height: 4 },
    };
  });

  const handle = (
    <GestureDetector gesture={pan}>
      <View hitSlop={10} style={{ paddingHorizontal: 12, height: rowHeight, justifyContent: 'center' }}>
        <View style={{ gap: 3 }}>
          {[0, 1, 2].map((i) => (
            <View key={i} style={{ width: 18, height: 2, borderRadius: 1, backgroundColor: '#8A8A96' }} />
          ))}
        </View>
      </View>
    </GestureDetector>
  );

  return <Animated.View style={style}>{children(handle)}</Animated.View>;
}
