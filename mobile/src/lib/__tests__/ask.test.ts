import { evidenceKindLabel, wellbeingDisclaimer } from '@/lib/ask';

describe('Ask CareRelay presentation rules', () => {
  it('keeps self reports and care events visibly distinct', () => {
    expect(evidenceKindLabel('wellbeing_checkin')).toBe('SELF REPORT');
    expect(evidenceKindLabel('care_event')).toBe('CARE EVENT');
  });

  it('does not label subjective wellbeing as a clinical score', () => {
    expect(wellbeingDisclaimer).toContain('not a clinical health score');
  });
});
