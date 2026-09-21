import { fireEvent, render, screen } from '@testing-library/react-native';

import { SymptomSelector } from '@/components/SymptomSelector';

describe('SymptomSelector', () => {
  it('adds and removes only supported symptoms', () => {
    const onChange = jest.fn();
    const { rerender } = render(<SymptomSelector selected={[]} onChange={onChange} />);

    fireEvent.press(screen.getByRole('checkbox', { name: 'Dizziness' }));
    expect(onChange).toHaveBeenLastCalledWith(['dizziness']);

    rerender(<SymptomSelector selected={['dizziness']} onChange={onChange} />);
    fireEvent.press(screen.getByRole('checkbox', { name: 'Dizziness' }));
    expect(onChange).toHaveBeenLastCalledWith([]);
  });
});

