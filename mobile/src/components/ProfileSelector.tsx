import { ScrollView, StyleSheet, Text, Pressable, View } from 'react-native';

import { useCareProfiles } from '@/providers/CareProfileProvider';
import { colors } from '@/theme/colors';

export function ProfileSelector() {
  const { profiles, activeProfile, setActiveProfileId } = useCareProfiles();
  if (profiles.length === 0) return null;

  return (
    <View style={styles.container}>
      <Text style={styles.label}>Care profile</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.row}>
        {profiles.map((profile) => {
          const selected = profile.id === activeProfile?.id;
          return (
            <Pressable
              key={profile.id}
              accessibilityRole="button"
              accessibilityState={{ selected }}
              onPress={() => setActiveProfileId(profile.id)}
              style={[styles.chip, selected && styles.selectedChip]}
            >
              <Text style={[styles.chipText, selected && styles.selectedText]}>{profile.name}</Text>
            </Pressable>
          );
        })}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { marginTop: 22 },
  label: { color: colors.muted, fontSize: 12, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 9 },
  row: { gap: 8 },
  chip: { minHeight: 44, paddingHorizontal: 17, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center' },
  selectedChip: { backgroundColor: colors.primarySoft, borderColor: colors.primary },
  chipText: { color: colors.muted, fontSize: 15, fontWeight: '700' },
  selectedText: { color: colors.primary },
});

