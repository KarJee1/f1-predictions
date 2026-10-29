import { Link } from 'expo-router';
import { View } from 'react-native';

import { Message, Txt } from '@/src/components/ui';
import { useColors } from '@/src/theme';

export default function NotFoundScreen() {
  const c = useColors();
  return (
    <View style={{ flex: 1, justifyContent: 'center', backgroundColor: c.background }}>
      <Message title="This page doesn't exist." />
      <Link href="/" style={{ alignSelf: 'center' }}>
        <Txt variant="label" color={c.accent}>
          Go to Home
        </Txt>
      </Link>
    </View>
  );
}
