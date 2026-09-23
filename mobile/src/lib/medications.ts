import { Medication, MedicationDoseOccurrence, MedicationSchedule } from '@/lib/api';

const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export function formatMedicationClock(value: string): string {
  const [hourText, minute = '00'] = value.split(':');
  const hour = Number(hourText);
  const suffix = hour >= 12 ? 'PM' : 'AM';
  const displayHour = hour % 12 || 12;
  return `${displayHour}:${minute} ${suffix}`;
}

export function scheduleSummary(schedule: MedicationSchedule): string {
  const days = schedule.days_of_week;
  const dayLabel = days.length === 7
    ? 'Daily'
    : days.map((day) => dayNames[day]).join(', ');
  return `${dayLabel} at ${formatMedicationClock(schedule.local_time)}`;
}

export function medicationScheduleSummary(medication: Medication): string {
  if (medication.schedule_type === 'as_needed') return 'As needed';
  const active = medication.schedules.filter((schedule) => schedule.active);
  if (!active.length) return 'No active schedule';
  return active.map(scheduleSummary).join(' · ');
}

export function doseStatusLabel(dose: MedicationDoseOccurrence): string {
  if (dose.status !== 'not_recorded') {
    return dose.status.charAt(0).toUpperCase() + dose.status.slice(1);
  }
  return dose.due_state === 'upcoming' ? 'Not due yet' : 'Not recorded';
}
