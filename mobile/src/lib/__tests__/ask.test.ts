import { evidenceKindLabel, wellbeingDisclaimer } from '@/lib/ask';

describe('Ask CareRelay presentation rules', () => {
  it('keeps self reports and care events visibly distinct', () => {
    expect(evidenceKindLabel('wellbeing_checkin')).toBe('SELF REPORT');
    expect(evidenceKindLabel('care_event')).toBe('CARE EVENT');
    expect(evidenceKindLabel('medication')).toBe('MEDICATION PLAN');
    expect(evidenceKindLabel('medication_dose')).toBe('MEDICATION DOSE');
  });

  it('does not label subjective wellbeing as a clinical score', () => {
    expect(wellbeingDisclaimer).toContain('not a clinical health score');
  });
});
