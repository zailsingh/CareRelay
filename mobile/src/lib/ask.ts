import { AskEvidence } from '@/lib/api';

export const wellbeingDisclaimer = 'Subjective self report — not a clinical health score.';

export function evidenceKindLabel(kind: AskEvidence['record_type']): string {
  return kind === 'wellbeing_checkin' ? 'SELF REPORT' : 'CARE EVENT';
}
