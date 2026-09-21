import { StyleSheet, Text, View } from 'react-native';
import Svg, { Circle, Line, Path, Text as SvgText } from 'react-native-svg';

import { WellbeingSummary } from '@/lib/api';
import { colors } from '@/theme/colors';

type Props = { days: WellbeingSummary['daily_averages'] };

export function WellbeingChart({ days }: Props) {
  const width = 300;
  const top = 12;
  const bottom = 88;
  const left = 24;
  const right = 292;
  const x = (index: number) => left + (index * (right - left)) / Math.max(days.length - 1, 1);
  const y = (score: number) => bottom - (score / 100) * (bottom - top);
  let path = '';
  let previousHadValue = false;
  days.forEach((day, index) => {
    if (day.average_score === null) {
      previousHadValue = false;
      return;
    }
    path += `${previousHadValue ? ' L' : ' M'} ${x(index)} ${y(day.average_score)}`;
    previousHadValue = true;
  });
  const recorded = days.filter((day) => day.average_score !== null);
  const label = recorded.length
    ? recorded.map((day) => `${day.date}: ${day.average_score}`).join(', ')
    : 'No wellbeing check-ins in this seven day period';

  return (
    <View accessible accessibilityLabel={`Seven day wellbeing chart. ${label}`}>
      {recorded.length === 0 ? <Text style={styles.empty}>No check-ins in this period yet.</Text> : null}
      <Svg width="100%" height={122} viewBox="0 0 300 110" accessibilityElementsHidden>
        {[0, 50, 100].map((score) => (
          <Line key={score} x1={left} x2={right} y1={y(score)} y2={y(score)} stroke={colors.border} strokeWidth={1} />
        ))}
        <SvgText x={2} y={y(100) + 4} fontSize={10} fill={colors.muted}>100</SvgText>
        <SvgText x={8} y={y(50) + 4} fontSize={10} fill={colors.muted}>50</SvgText>
        <SvgText x={14} y={y(0) + 4} fontSize={10} fill={colors.muted}>0</SvgText>
        {path ? <Path d={path} fill="none" stroke={colors.primary} strokeWidth={3} strokeLinecap="round" strokeLinejoin="round" /> : null}
        {days.map((day, index) => day.average_score === null ? null : (
          <Circle key={day.date} cx={x(index)} cy={y(day.average_score)} r={4.5} fill={colors.primary} stroke={colors.surface} strokeWidth={2} />
        ))}
        {days.map((day, index) => (
          <SvgText key={`${day.date}-label`} x={x(index)} y={106} textAnchor="middle" fontSize={9} fill={colors.muted}>
            {day.date.slice(8)}
          </SvgText>
        ))}
      </Svg>
    </View>
  );
}

const styles = StyleSheet.create({
  empty: { color: colors.muted, fontSize: 14, textAlign: 'center', marginTop: 20, marginBottom: -20 },
});

