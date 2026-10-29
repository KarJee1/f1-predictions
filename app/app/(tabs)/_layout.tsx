import { SymbolView } from 'expo-symbols';
import { Tabs } from 'expo-router';

import { fonts, useColors } from '@/src/theme';

export default function TabLayout() {
  const c = useColors();
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: c.accent,
        tabBarInactiveTintColor: c.muted,
        tabBarStyle: { backgroundColor: c.tabBar, borderTopColor: c.border },
        tabBarLabelStyle: { fontFamily: fonts.semibold, fontSize: 11 },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Home',
          tabBarIcon: ({ color }) => <SymbolView name={{ ios: 'house.fill', android: 'home', web: 'home' }} tintColor={color} size={24} />,
        }}
      />
      <Tabs.Screen
        name="predictions"
        options={{
          title: 'Predictions',
          tabBarIcon: ({ color }) => (
            <SymbolView name={{ ios: 'chart.bar.fill', android: 'bar_chart', web: 'bar_chart' }} tintColor={color} size={24} />
          ),
        }}
      />
      <Tabs.Screen
        name="predict"
        options={{
          title: 'Predict',
          tabBarIcon: ({ color }) => (
            <SymbolView name={{ ios: 'list.number', android: 'format_list_numbered', web: 'format_list_numbered' }} tintColor={color} size={24} />
          ),
        }}
      />
    </Tabs>
  );
}
