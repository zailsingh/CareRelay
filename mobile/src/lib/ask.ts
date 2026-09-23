import { AskEvidence } from '@/lib/api';

export const wellbeingDisclaimer = 'Subjective self report — not a clinical health score.';

export function evidenceKindLabel(kind: AskEvidence['record_type']): string {
  if (kind === 'wellbeing_checkin') return 'SELF REPORT';
  if (kind === 'medication') return 'MEDICATION PLAN';
  if (kind === 'medication_dose') return 'MEDICATION DOSE';
  return 'CARE EVENT';
}
