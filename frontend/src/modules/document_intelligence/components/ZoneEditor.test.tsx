import { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { ZoneEditor } from './ZoneEditor';
import type { ExtractionTemplateZoneInput } from '../contracts';

function EditorHarness() {
  const [zones, setZones] = useState<readonly ExtractionTemplateZoneInput[]>([]);
  return <ZoneEditor zones={zones} onChange={setZones} />;
}

describe('ZoneEditor accessibility', () => {
  it('supports adding, keyboard movement, zoom, and undo without a pointer', () => {
    render(<EditorHarness />);
    expect(screen.getByLabelText('Editor zoom')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Zone' }));
    const visualZone = screen.getByRole('button', { name: 'Field 1' });
    fireEvent.keyDown(visualZone, { key: 'ArrowRight' });
    expect(screen.getByLabelText('x')).toHaveValue(0.11);
    fireEvent.click(screen.getByRole('button', { name: 'Undo zone change' }));
    expect(screen.getByLabelText('x')).toHaveValue(0.1);
  });
});
