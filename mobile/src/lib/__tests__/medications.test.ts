import {
  doseStatusLabel,
  formatMedicationClock,
  medicationScheduleSummary,
} from '@/lib/medications';
import { Medication, MedicationDoseOccurrence } from '@/lib/api';

const medication: Medication = {
  id: 'med', care_profile_id: 'profile', name: 'Metformin', strength_text: '500 mg',
  form: 'tablet', instructions_text: null, notes: null, schedule_type: 'scheduled',
  active: true, start_date: null, end_date: null, created_by_user_id: 'user',
  created_at: '2026-09-22T00:00:00Z', updated_at: '2026-09-22T00:00:00Z',
  schedules: [{
    id: 'schedule', medication_id: 'med', local_time: '20:00:00',
    days_of_week: [0, 2, 4], active: true, start_date: null, end_date: null,
    created_at: '2026-09-22T00:00:00Z', updated_at: '2026-09-22T00:00:00Z',
  }],
};

function occurrence(due_state: MedicationDoseOccurrence['due_state']): MedicationDoseOccurrence {
  return {
    occurrence_key: 'key', medication_id: 'med', medication_name: 'Metformin',
    medication_strength: '500 mg', schedule_id: 'schedule',
    scheduled_for: '2026-09-22T10:00:00Z', scheduled_local_date: '2026-09-22',
    scheduled_local_time: '20:00:00', scheduled_timezone: 'Australia/Melbourne',
    status: 'not_recorded', dose_record: null, due_state,
  };
}

describe('medication presentation', () => {
  it('formats local schedules without converting the intended clock time', () => {
    expect(formatMedicationClock('20:00:00')).toBe('8:00 PM');
    expect(medicationScheduleSummary(medication)).toBe('Mon, Wed, Fri at 8:00 PM');
  });

  it('keeps no record distinct from missed', () => {
    expect(doseStatusLabel(occurrence('elapsed'))).toBe('Not recorded');
    expect(doseStatusLabel(occurrence('upcoming'))).toBe('Not due yet');
  });
});
