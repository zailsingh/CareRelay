import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { colors } from '@/theme/colors';

type Props = { value: number; onChange: (value: number) => void };

const clamp = (value: number) => Math.max(0, Math.min(100, value));

export function ScoreControl({ value, onChange }: Props) {
  const changeText = (text: string) => {
    if (text === '') return;
    const parsed = Number.parseInt(text.replace(/\D/g, ''), 10);
    if (!Number.isNaN(parsed)) onChange(clamp(parsed));
  };

  return (
    <View>
      <View style={styles.control}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Decrease wellbeing score by 5"
          onPress={() => onChange(clamp(value - 5))}
          style={styles.stepButton}
        >
          <Text style={styles.stepText}>−</Text>
        </Pressable>
        <View style={styles.valueWrap}>
          <TextInput
            accessibilityLabel="Wellbeing score from 0 to 100"
            keyboardType="number-pad"
            maxLength={3}
            onChangeText={changeText}
            selectTextOnFocus
            style={styles.input}
            value={String(value)}
          />
          <Text style={styles.outOf}>/ 100</Text>
        </View>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Increase wellbeing score by 5"
          onPress={() => onChange(clamp(value + 5))}
          style={styles.stepButton}
        >
          <Text style={styles.stepText}>+</Text>
        </Pressable>
      </View>
      <View style={styles.presets}>
        {[0, 25, 50, 75, 100].map((preset) => (
          <Pressable
            key={preset}
            accessibilityRole="button"
            accessibilityLabel={`Set wellbeing score to ${preset}`}
            onPress={() => onChange(preset)}
            style={[styles.preset, value === preset && styles.presetSelected]}
          >
            <Text style={[styles.presetText, value === preset && styles.presetTextSelected]}>{preset}</Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  control: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 14 },
  stepButton: { width: 56, height: 56, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primarySoft },
  stepText: { color: colors.primary, fontSize: 30, lineHeight: 34, fontWeight: '600' },
  valueWrap: { flexDirection: 'row', alignItems: 'baseline' },
  input: { color: colors.ink, fontSize: 42, fontWeight: '800', minWidth: 74, textAlign: 'right', padding: 0 },
  outOf: { color: colors.muted, fontSize: 16, marginLeft: 5 },
  presets: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 14, gap: 6 },
  preset: { flex: 1, minHeight: 44, borderRadius: 12, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: colors.border },
  presetSelected: { backgroundColor: colors.primary, borderColor: colors.primary },
  presetText: { color: colors.muted, fontSize: 13, fontWeight: '700' },
  presetTextSelected: { color: colors.surface },
});

