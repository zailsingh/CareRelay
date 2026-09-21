import { ReactNode } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { colors } from '@/theme/colors';

type Props = {
  eyebrow: string;
  title: string;
  description: string;
  icon: ReactNode;
};

export function PlaceholderScreen({ eyebrow, title, description, icon }: Props) {
  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Text style={styles.brand}>CareRelay</Text>
      </View>
      <View style={styles.content}>
        <View style={styles.icon} accessible={false}>{icon}</View>
        <Text style={styles.eyebrow}>{eyebrow}</Text>
        <Text style={styles.title} accessibilityRole="header">{title}</Text>
        <Text style={styles.description}>{description}</Text>
        <View style={styles.badge}>
          <Text style={styles.badgeText}>Coming in a later phase</Text>
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  header: { paddingHorizontal: 24, paddingVertical: 18 },
  brand: { color: colors.primary, fontSize: 19, fontWeight: '800', letterSpacing: -0.4 },
  content: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32, paddingBottom: 100 },
  icon: { width: 72, height: 72, borderRadius: 24, backgroundColor: colors.primarySoft, alignItems: 'center', justifyContent: 'center', marginBottom: 24 },
  eyebrow: { color: colors.primary, fontSize: 13, fontWeight: '700', letterSpacing: 1.2, textTransform: 'uppercase', marginBottom: 8 },
  title: { color: colors.ink, fontSize: 30, fontWeight: '800', letterSpacing: -0.7, textAlign: 'center' },
  description: { color: colors.muted, fontSize: 17, lineHeight: 25, textAlign: 'center', marginTop: 12, maxWidth: 340 },
  badge: { marginTop: 24, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 99, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  badgeText: { color: colors.muted, fontSize: 13, fontWeight: '600' },
});

