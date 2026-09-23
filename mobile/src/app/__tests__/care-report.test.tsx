import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';

import { AppointmentReportLink } from '@/app/(tabs)/index';
import CareReportScreen from '@/app/care-report';
import { api, CareReport } from '@/lib/api';
import { shareCareReport } from '@/lib/reports';

const mockPush = jest.fn();

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush, back: jest.fn() }),
}));

jest.mock('@expo/vector-icons', () => ({ Ionicons: () => null }));
jest.mock('react-native-svg', () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) => children,
  Circle: () => null,
}));
jest.mock('@/components/ProfileSelector', () => {
  const { Text } = require('react-native');
  return { ProfileSelector: () => <Text>profile selector</Text> };
});
jest.mock('@/components/ScoreControl', () => ({ ScoreControl: () => null }));
jest.mock('@/components/SymptomSelector', () => ({ SymptomSelector: () => null }));
jest.mock('@/components/WellbeingChart', () => {
  const { Text } = require('react-native');
  return { WellbeingChart: () => <Text>wellbeing trend line</Text> };
});
jest.mock('@/lib/reports', () => ({ shareCareReport: jest.fn() }));
jest.mock('@/lib/api', () => ({
  api: {
    reportPreview: jest.fn(),
    checkins: jest.fn().mockResolvedValue([]),
    wellbeingSummary: jest.fn().mockResolvedValue({
      average_score: 55,
      checkin_count: 0,
      daily_averages: [],
    }),
  },
}));
jest.mock('@/providers/AuthProvider', () => ({
  useAuth: () => ({ token: 'token', user: { id: 'owner', display_name: 'Alex' }, signOut: jest.fn() }),
}));
jest.mock('@/providers/CareProfileProvider', () => ({
  useCareProfiles: () => ({
    activeProfile: {
      id: 'profile-1',
      name: 'Mum',
      role: 'admin',
      subject_user_id: 'subject-1',
      timezone: 'Australia/Melbourne',
    },
    profiles: [{ id: 'profile-1' }],
    loading: false,
    error: null,
    createProfile: jest.fn(),
    wellbeingRevision: 0,
    notifyWellbeingChanged: jest.fn(),
  }),
}));

const fullReport: CareReport = {
  care_profile: { id: 'profile-1', name: 'Mum', subject_display_name: 'Mum' },
  period: {
    start_date: '2026-09-01',
    end_date: '2026-09-30',
    timezone: 'Australia/Melbourne',
    description: 'Last 30 days',
  },
  generated_at: '2026-09-30T01:00:00Z',
  wellbeing: {
    average: 64,
    minimum: 50,
    maximum: 76,
    checkin_count: 3,
    daily_averages: [{ date: '2026-09-30', checkin_count: 1, average_score: 64 }],
    trend: 'higher',
    trend_statement: 'The latest self report was 10 points higher than the first.',
    evidence: [{ record_type: 'wellbeing_checkin', record_id: 'checkin-1', occurred_at: '2026-09-30T01:00:00Z', label: 'Self report: 64 / 100' }],
  },
  symptoms: [{
    kind: 'dizziness',
    label: 'Dizziness',
    recorded_count: 2,
    evidence: [{ record_type: 'wellbeing_checkin', record_id: 'checkin-1', occurred_at: '2026-09-30T01:00:00Z', label: 'Dizziness recorded' }],
  }],
  falls: { count: 1, items: [], evidence: [] },
  medications: {
    taken: 5,
    missed: 1,
    skipped: 1,
    not_recorded: 2,
    expected_scheduled_doses: 9,
    doses: [],
    evidence: [{ record_type: 'medication', record_id: 'med-1', occurred_at: '2026-09-30T01:00:00Z', label: 'Metformin scheduled dose' }],
  },
  care_events: { total_count: 1, activity_count: 1, sleep_count: 0, general_observation_count: 0, items: [] },
  appointments: [],
  narrative_summary: 'Verified factual summary.',
  narrative_source: 'ai',
  points_to_discuss: ['Dizziness was recorded 2 times.'],
  evidence: [],
  disclaimer: 'CareRelay summarises recorded information and does not diagnose.',
};

describe('Prepare for appointment', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.mocked(api.reportPreview).mockResolvedValue(fullReport);
    jest.mocked(shareCareReport).mockResolvedValue();
  });

  it('provides a natural Overview entry point without another tab', async () => {
    render(<AppointmentReportLink />);
    fireEvent.press(screen.getByText('Prepare for appointment'));
    expect(mockPush).toHaveBeenCalledWith('/care-report');
  });

  it('selects a period and renders deterministic report visuals and sections', async () => {
    render(<CareReportScreen />);
    fireEvent.press(screen.getByText('90 days'));
    fireEvent.press(screen.getByText('Generate report'));
    await waitFor(() => expect(api.reportPreview).toHaveBeenCalledWith(
      'token',
      'profile-1',
      { period: '90d' },
    ));
    expect(screen.getByText('64 / 100')).toBeTruthy();
    expect(screen.getByText('Average self-reported wellbeing')).toBeTruthy();
    expect(screen.getByText('wellbeing trend line')).toBeTruthy();
    expect(screen.getByText('Dizziness')).toBeTruthy();
    expect(screen.getByText('No record')).toBeTruthy();
    expect(screen.getByText('No record is not counted as missed.')).toBeTruthy();
  });

  it('supports custom date selection and evidence display', async () => {
    render(<CareReportScreen />);
    fireEvent.press(screen.getByText('Custom'));
    fireEvent.changeText(screen.getByLabelText('Start date'), '2026-09-01');
    fireEvent.changeText(screen.getByLabelText('End date'), '2026-09-10');
    fireEvent.press(screen.getByText('Generate report'));
    await screen.findByText('Verified factual summary.');
    fireEvent.press(screen.getAllByText('Show evidence')[0]);
    expect(screen.getByText('Report evidence')).toBeTruthy();
    expect(screen.getByText('Self report: 64 / 100')).toBeTruthy();
  });

  it('renders sparse data and a recoverable loading error', async () => {
    jest.mocked(api.reportPreview).mockResolvedValueOnce({
      ...fullReport,
      wellbeing: { ...fullReport.wellbeing, average: null, minimum: null, maximum: null, checkin_count: 0, daily_averages: [], trend: 'insufficient_data', trend_statement: 'Not enough data.', evidence: [] },
      symptoms: [],
      care_events: { ...fullReport.care_events, total_count: 0, activity_count: 0, items: [] },
      medications: { ...fullReport.medications, taken: 0, missed: 0, skipped: 0, not_recorded: 0, expected_scheduled_doses: 0, evidence: [] },
      narrative_summary: 'No recorded data for this period.',
    });
    render(<CareReportScreen />);
    fireEvent.press(screen.getByText('Generate report'));
    expect(await screen.findByText('No self-reported wellbeing check-ins were recorded during this period.')).toBeTruthy();

    jest.mocked(api.reportPreview).mockRejectedValueOnce(new Error('Report unavailable'));
    fireEvent.press(screen.getByText('Generate report'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Report unavailable');
  });

  it('exports the selected report through native sharing', async () => {
    render(<CareReportScreen />);
    fireEvent.press(screen.getByText('Generate report'));
    await screen.findByText('Verified factual summary.');
    fireEvent.press(screen.getByText('Export and share PDF'));
    await waitFor(() => expect(shareCareReport).toHaveBeenCalledWith(
      'token', 'profile-1', 'Mum', { period: '30d' },
    ));
  });
});
