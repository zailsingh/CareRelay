import { Pressable, StyleSheet, Text, View } from 'react-native';

import { symptomKinds, symptomLabels, SymptomKind } from '@/lib/api';
import { colors } from '@/theme/colors';

type Props = { selected: SymptomKind[]; onChange: (symptoms: SymptomKind[]) => void };

export function SymptomSelector({ selected, onChange }: Props) {
  const toggle = (kind: SymptomKind) => {
    onChange(selected.includes(kind) ? selected.filter((item) => item !== kind) : [...selected, kind]);
  };
  return (
    <View style={styles.wrap}>
      {symptomKinds.map((kind) => {
        const active = selected.includes(kind);
        return (
          <Pressable
            key={kind}
            accessibilityRole="checkbox"
            accessibilityState={{ checked: active }}
            onPress={() => toggle(kind)}
            style={[styles.chip, active && styles.activeChip]}
          >
            <Text style={[styles.text, active && styles.activeText]}>{symptomLabels[kind]}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 },
  chip: { minHeight: 46, justifyContent: 'center', borderRadius: 14, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 14, backgroundColor: colors.surface },
  activeChip: { borderColor: colors.primary, backgroundColor: colors.primarySoft },
  text: { color: colors.muted, fontSize: 14, fontWeight: '600' },
  activeText: { color: colors.primary },
});

