import { fireEvent, render, screen } from '@testing-library/react-native';

import { ScoreControl } from '@/components/ScoreControl';

describe('ScoreControl', () => {
  it('uses large explicit controls and clamps scores to 0–100', () => {
    const onChange = jest.fn();
    render(<ScoreControl value={98} onChange={onChange} />);

    fireEvent.press(screen.getByLabelText('Increase wellbeing score by 5'));
    expect(onChange).toHaveBeenLastCalledWith(100);

    fireEvent.press(screen.getByLabelText('Set wellbeing score to 0'));
    expect(onChange).toHaveBeenLastCalledWith(0);
  });

  it('accepts a directly entered score', () => {
    const onChange = jest.fn();
    render(<ScoreControl value={50} onChange={onChange} />);
    fireEvent.changeText(screen.getByLabelText('Wellbeing score from 0 to 100'), '72');
    expect(onChange).toHaveBeenCalledWith(72);
  });
});

