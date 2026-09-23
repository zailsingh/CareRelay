import { File, Paths } from 'expo-file-system';
import * as Sharing from 'expo-sharing';

import { reportPdf, ReportRequest } from '@/lib/api';

export async function shareCareReport(
  token: string,
  profileId: string,
  profileName: string,
  request: ReportRequest,
): Promise<void> {
  if (!(await Sharing.isAvailableAsync())) {
    throw new Error('Sharing is not available on this device.');
  }
  const safeName = profileName.replace(/[^a-zA-Z0-9_-]+/g, '-').replace(/^-|-$/g, '');
  const file = new File(Paths.cache, `CareRelay-${safeName || 'care-report'}.pdf`);
  try {
    if (file.exists) file.delete();
    file.create();
    file.write(new Uint8Array(await reportPdf(token, profileId, request)));
    await Sharing.shareAsync(file.uri, {
      mimeType: 'application/pdf',
      UTI: 'com.adobe.pdf',
      dialogTitle: 'Share CareRelay report',
    });
  } finally {
    if (file.exists) file.delete();
  }
}
