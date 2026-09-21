import { buildEventMetadata } from '@/components/QuickAddCareEvent';

const details = {
  symptoms: ['fatigue', 'dizziness'] as const,
  medicationName: 'Example medicine',
  duration: '15',
  provider: 'Local GP',
  injuryObserved: true,
};

describe('buildEventMetadata', () => {
  it('builds only the schema for the selected event type', () => {
    expect(buildEventMetadata('activity', { ...details, symptoms: [...details.symptoms] })).toEqual({
      duration_minutes: 15,
    });
    expect(buildEventMetadata('symptom_observation', { ...details, symptoms: [...details.symptoms] })).toEqual({
      symptoms: ['fatigue', 'dizziness'],
    });
    expect(buildEventMetadata('fall', { ...details, symptoms: [...details.symptoms] })).toEqual({
      injury_observed: true,
    });
  });

  it('does not invent optional structured values', () => {
    expect(buildEventMetadata('general_note', { ...details, symptoms: [...details.symptoms] })).toEqual({});
    expect(buildEventMetadata('activity', { ...details, duration: '', symptoms: [] })).toEqual({});
  });
});

