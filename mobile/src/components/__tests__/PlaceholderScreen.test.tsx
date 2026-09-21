import { render, screen } from '@testing-library/react-native';
import { Text } from 'react-native';

import { PlaceholderScreen } from '@/components/PlaceholderScreen';

describe('PlaceholderScreen', () => {
  it('explains that deferred features are not active', () => {
    render(
      <PlaceholderScreen
        eyebrow="Timeline"
        title="A clear story"
        description="Confirmed events will appear here."
        icon={<Text>icon</Text>}
      />,
    );

    expect(screen.getByRole('header', { name: 'A clear story' })).toBeTruthy();
    expect(screen.getByText('Coming in a later phase')).toBeTruthy();
  });
});

