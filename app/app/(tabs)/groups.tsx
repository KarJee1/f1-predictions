import * as AppleAuthentication from 'expo-apple-authentication';
import { router } from 'expo-router';
import { useState } from 'react';
import { Platform, Pressable, StyleSheet, View } from 'react-native';

import { USE_SAMPLE } from '@/src/api';
import { isCancel, useAccount } from '@/src/account';
import { Button, Card, Divider, Field, Loading, Message, Screen, SectionTitle, Txt } from '@/src/components/ui';
import { useGroupActions, useGroups } from '@/src/groups';
import { POINTS_PER_DRIVER } from '@/src/picks';
import { useColors, useScheme } from '@/src/theme';

export default function GroupsScreen() {
  const account = useAccount();
  const groups = useGroups();

  return (
    <Screen
      title="Groups"
      subtitle="Compete with friends"
      refreshing={groups.isRefetching}
      onRefresh={account.signedIn ? () => groups.refetch() : undefined}
    >
      {!account.ready ? (
        <Loading />
      ) : !account.signedIn ? (
        <SignedOut />
      ) : account.me?.needs_name ? (
        <NameCard />
      ) : (
        <>
          <SectionTitle>Your groups</SectionTitle>
          {groups.isLoading ? (
            <Loading />
          ) : groups.error ? (
            <Message title="Couldn't load your groups." body="Pull down to try again." />
          ) : groups.data?.groups.length ? (
            <Card>
              {groups.data.groups.map((g, i) => (
                <View key={g.id}>
                  {i > 0 ? <Divider /> : null}
                  <Pressable onPress={() => router.push(`/group/${g.id}`)} style={({ pressed }) => [styles.groupRow, pressed && { opacity: 0.7 }]}>
                    <View style={{ flex: 1 }}>
                      <Txt variant="heading">{g.name}</Txt>
                      <Txt variant="caption" muted>
                        {g.member_count} {g.member_count === 1 ? 'member' : 'members'}
                      </Txt>
                    </View>
                    <View style={{ alignItems: 'flex-end' }}>
                      <Txt variant="title">P{g.my_rank}</Txt>
                      <Txt variant="caption" muted>
                        your spot
                      </Txt>
                    </View>
                  </Pressable>
                </View>
              ))}
            </Card>
          ) : (
            <Message title="You're not in a group yet." body="Start one and share the code, or join a friend's." />
          )}
          <StartOrJoin />
          <Txt variant="caption" muted style={styles.footnote}>
            Your picks from the Predict tab count in every group you&apos;re in.
          </Txt>
        </>
      )}
    </Screen>
  );
}

function SignedOut() {
  const c = useColors();
  const scheme = useScheme();
  const { signIn, appleAvailable } = useAccount();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const go = async () => {
    setError(null);
    setBusy(true);
    try {
      await signIn();
    } catch (e) {
      if (!isCancel(e)) setError((e as Error).message || 'Sign-in failed. Try again.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card style={{ padding: 18 }}>
      <Txt variant="title">Race your friends</Txt>
      <Txt muted style={{ marginTop: 8 }}>
        Start a group, share the invite code, and everyone&apos;s finishing-order picks are scored after each race. Top of the
        table at the end of the season takes the title.
      </Txt>
      <View style={{ marginTop: 14, gap: 6 }}>
        {[
          'Make your picks in the Predict tab before lights out',
          `Up to ${POINTS_PER_DRIVER} points per driver, one less for each place off`,
          'See everyone’s picks once the race starts',
        ].map((t) => (
          <View key={t} style={{ flexDirection: 'row', gap: 8 }}>
            <View style={[styles.dot, { backgroundColor: c.accent }]} />
            <Txt style={{ flex: 1 }}>{t}</Txt>
          </View>
        ))}
      </View>
      <View style={{ marginTop: 18 }}>
        {Platform.OS === 'ios' && !USE_SAMPLE ? (
          appleAvailable ? (
            <AppleAuthentication.AppleAuthenticationButton
              buttonType={AppleAuthentication.AppleAuthenticationButtonType.SIGN_IN}
              buttonStyle={
                scheme === 'dark'
                  ? AppleAuthentication.AppleAuthenticationButtonStyle.WHITE
                  : AppleAuthentication.AppleAuthenticationButtonStyle.BLACK
              }
              cornerRadius={10}
              style={{ height: 48 }}
              onPress={go}
            />
          ) : (
            <Txt muted>Sign in with Apple isn&apos;t available on this device.</Txt>
          )
        ) : (
          <Button label="Sign in with Apple" onPress={go} busy={busy} disabled={!appleAvailable} />
        )}
      </View>
      {error ? (
        <Txt variant="caption" color={c.down} style={{ marginTop: 8 }}>
          {error}
        </Txt>
      ) : null}
      <Txt variant="caption" muted style={{ marginTop: 10 }}>
        Only your Apple ID&apos;s user number is shared with us, never your email.
      </Txt>
    </Card>
  );
}

function NameCard() {
  const c = useColors();
  const { setName } = useAccount();
  const [name, setValue] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await setName(name.trim());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card style={{ padding: 18 }}>
      <Txt variant="title">What should friends call you?</Txt>
      <Txt muted style={{ marginTop: 6, marginBottom: 12 }}>
        This name shows on group leaderboards. You can change it later in Settings.
      </Txt>
      <Field value={name} onChangeText={setValue} placeholder="Your name" maxLength={30} autoFocus returnKeyType="done" onSubmitEditing={save} />
      <Button label="Continue" onPress={save} busy={busy} disabled={!name.trim()} style={{ marginTop: 10 }} />
      {error ? (
        <Txt variant="caption" color={c.down} style={{ marginTop: 8 }}>
          {error}
        </Txt>
      ) : null}
    </Card>
  );
}

function StartOrJoin() {
  const c = useColors();
  const { create, join } = useGroupActions();
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const error = (create.error ?? join.error) as Error | null;

  const onCreate = () =>
    create.mutate(name.trim(), {
      onSuccess: (g) => {
        setName('');
        router.push(`/group/${g.id}`);
      },
    });
  const onJoin = () =>
    join.mutate(code.trim(), {
      onSuccess: (g) => {
        setCode('');
        router.push(`/group/${g.id}`);
      },
    });

  return (
    <>
      <SectionTitle>Start or join</SectionTitle>
      <Card style={{ padding: 14, gap: 14 }}>
        <View>
          <Txt variant="label" muted style={{ marginBottom: 6 }}>
            START A GROUP
          </Txt>
          <View style={styles.inline}>
            <Field value={name} onChangeText={setName} placeholder="Group name" maxLength={40} style={{ flex: 1 }} />
            <Button label="Create" onPress={onCreate} busy={create.isPending} disabled={!name.trim()} />
          </View>
        </View>
        <View>
          <Txt variant="label" muted style={{ marginBottom: 6 }}>
            JOIN WITH A CODE
          </Txt>
          <View style={styles.inline}>
            <Field
              value={code}
              onChangeText={(t) => setCode(t.toUpperCase())}
              placeholder="ABC123"
              autoCapitalize="characters"
              autoCorrect={false}
              maxLength={8}
              style={{ flex: 1, letterSpacing: 2 }}
            />
            <Button label="Join" kind="secondary" onPress={onJoin} busy={join.isPending} disabled={code.trim().length < 6} />
          </View>
        </View>
        {error ? (
          <Txt variant="caption" color={c.down}>
            {error.message}
          </Txt>
        ) : null}
      </Card>
    </>
  );
}

const styles = StyleSheet.create({
  groupRow: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 14 },
  inline: { flexDirection: 'row', gap: 8, alignItems: 'center' },
  dot: { width: 6, height: 6, borderRadius: 3, marginTop: 8 },
  footnote: { textAlign: 'center', marginTop: 16, paddingHorizontal: 24 },
});
