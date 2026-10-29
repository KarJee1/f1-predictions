import Constants from 'expo-constants';
import { router } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { useState } from 'react';
import { Alert, Platform, Pressable, ScrollView, StyleSheet, View } from 'react-native';

import { useAccount } from '@/src/account';
import { API_URL } from '@/src/api';
import { Button, Card, Divider, Field, SectionTitle, Txt } from '@/src/components/ui';
import { useColors } from '@/src/theme';
import { Preference, useThemePreference } from '@/src/ThemePreference';

const THEMES: { value: Preference; label: string }[] = [
  { value: 'system', label: 'Match system' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
];

const CREDITS = [
  { label: 'Results and standings: Jolpica F1 API', url: 'https://github.com/jolpica/jolpica-f1' },
  { label: 'Practice timing: OpenF1', url: 'https://openf1.org' },
  { label: 'Weather: Open-Meteo', url: 'https://open-meteo.com' },
];

export default function SettingsScreen() {
  const c = useColors();
  const { preference, setPreference } = useThemePreference();
  return (
    <ScrollView style={{ backgroundColor: c.background }} contentContainerStyle={{ paddingBottom: 40 }}>
      <View style={styles.header}>
        <Txt variant="title">Settings</Txt>
        <Pressable onPress={() => router.back()} hitSlop={12}>
          <Txt variant="label" color={c.accent}>
            Done
          </Txt>
        </Pressable>
      </View>

      <SectionTitle>Appearance</SectionTitle>
      <Card>
        {THEMES.map((t, i) => (
          <View key={t.value}>
            {i > 0 ? <Divider /> : null}
            <Pressable onPress={() => setPreference(t.value)} style={styles.row}>
              <Txt style={{ flex: 1 }}>{t.label}</Txt>
              {preference === t.value ? (
                <Txt variant="label" color={c.accent}>
                  ✓
                </Txt>
              ) : null}
            </Pressable>
          </View>
        ))}
      </Card>

      <AccountSection />

      <SectionTitle>About</SectionTitle>
      <Card style={{ padding: 14 }}>
        <Txt>
          Race predictions come from a machine learning model trained on every Grand Prix since 2016. It simulates each
          race thousands of times to get every driver&apos;s chances.
        </Txt>
        <Txt variant="caption" muted style={{ marginTop: 10 }}>
          This is an unofficial fan app. It isn&apos;t associated with Formula 1 companies. F1, FORMULA ONE and related
          marks are trademarks of Formula One Licensing B.V.
        </Txt>
      </Card>

      <SectionTitle>Data</SectionTitle>
      <Card>
        {[...CREDITS, { label: 'Privacy policy', url: `${API_URL}/privacy` }].map((cr, i) => (
          <View key={cr.url}>
            {i > 0 ? <Divider /> : null}
            <Pressable onPress={() => WebBrowser.openBrowserAsync(cr.url)} style={styles.row}>
              <Txt style={{ flex: 1 }}>{cr.label}</Txt>
            </Pressable>
          </View>
        ))}
      </Card>
      <Txt variant="caption" muted style={{ textAlign: 'center', marginTop: 20 }}>
        Version {Constants.expoConfig?.version}
      </Txt>
    </ScrollView>
  );
}

function AccountSection() {
  const c = useColors();
  const { signedIn, me, setName, signOut, deleteAccount } = useAccount();
  const [editing, setEditing] = useState(false);
  const [name, setValue] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!signedIn) return null;

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const confirmDelete = () => {
    const go = () => run(deleteAccount);
    if (Platform.OS === 'web') return go();
    Alert.alert(
      'Delete your account?',
      'This permanently deletes your account, your synced picks and points, and removes you from every group. Picks saved on this phone stay.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Delete account', style: 'destructive', onPress: go },
      ],
    );
  };

  return (
    <>
      <SectionTitle>Account</SectionTitle>
      <Card>
        {editing ? (
          <View style={{ padding: 14, gap: 8 }}>
            <Field value={name} onChangeText={setValue} placeholder="Your name" maxLength={30} autoFocus />
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <Button
                label="Save"
                busy={busy}
                disabled={!name.trim()}
                onPress={() => run(async () => { await setName(name.trim()); setEditing(false); })}
                style={{ flex: 1 }}
              />
              <Button label="Cancel" kind="secondary" onPress={() => setEditing(false)} style={{ flex: 1 }} />
            </View>
          </View>
        ) : (
          <Pressable onPress={() => { setValue(me?.name ?? ''); setEditing(true); }} style={styles.row}>
            <Txt style={{ flex: 1 }}>Name in groups</Txt>
            <Txt muted>{me?.name}</Txt>
          </Pressable>
        )}
        <Divider />
        <Pressable onPress={() => run(signOut)} style={styles.row}>
          <Txt style={{ flex: 1 }}>Sign out</Txt>
        </Pressable>
        <Divider />
        <Pressable onPress={confirmDelete} style={styles.row} disabled={busy}>
          <Txt color={c.down} style={{ flex: 1 }}>
            Delete account
          </Txt>
        </Pressable>
      </Card>
      {error ? (
        <Txt variant="caption" color={c.down} style={{ paddingHorizontal: 20, marginTop: 6 }}>
          {error}
        </Txt>
      ) : null}
    </>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 16, paddingTop: 20 },
  row: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14, paddingVertical: 14 },
});
