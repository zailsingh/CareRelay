import * as Sharing from 'expo-sharing';

import { reportPdf } from '@/lib/api';
import { shareCareReport } from '@/lib/reports';

const mockDelete = jest.fn();
const mockCreate = jest.fn();
const mockWrite = jest.fn();

jest.mock('expo-file-system', () => ({
  Paths: { cache: 'file:///cache' },
  File: jest.fn().mockImplementation(() => ({
    uri: 'file:///cache/CareRelay-Mum.pdf',
    exists: true,
    delete: mockDelete,
    create: mockCreate,
    write: mockWrite,
  })),
}));
jest.mock('expo-sharing', () => ({ isAvailableAsync: jest.fn(), shareAsync: jest.fn() }));
jest.mock('@/lib/api', () => ({ reportPdf: jest.fn() }));

describe('care report sharing', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.mocked(Sharing.isAvailableAsync).mockResolvedValue(true);
    jest.mocked(reportPdf).mockResolvedValue(new Uint8Array([37, 80, 68, 70]).buffer);
  });

  it('writes, shares, and removes the private temporary PDF', async () => {
    await shareCareReport('token', 'profile', 'Mum', { period: '30d' });
    expect(mockCreate).toHaveBeenCalled();
    expect(mockWrite).toHaveBeenCalled();
    expect(Sharing.shareAsync).toHaveBeenCalledWith(
      'file:///cache/CareRelay-Mum.pdf',
      expect.objectContaining({ mimeType: 'application/pdf' }),
    );
    expect(mockDelete).toHaveBeenCalledTimes(2);
  });

  it('removes the temporary PDF when native sharing fails', async () => {
    jest.mocked(Sharing.shareAsync).mockRejectedValueOnce(new Error('cancelled'));
    await expect(shareCareReport('token', 'profile', 'Mum', { period: '7d' }))
      .rejects.toThrow('cancelled');
    expect(mockDelete).toHaveBeenCalledTimes(2);
  });
});
