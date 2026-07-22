import { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { ZoneEditor } from './ZoneEditor';
import type { ExtractionTemplateZoneInput } from '../contracts';
import type { DocumentIntelligenceConfigurationDocument } from '../contracts';

const editorConfiguration: DocumentIntelligenceConfigurationDocument['editor'] = {
  new_zone: { x: 0.1, y: 0.1, width: 0.3, height: 0.1, page_number: 1, zone_type: 'text', expected_data_type: 'string', is_required: false },
  coordinate_snap: 0.01,
  coordinate_precision: 4,
  undo_history_limit: 20,
  zoom_min_percent: 70,
  zoom_max_percent: 150,
  zoom_step_percent: 10,
};

function EditorHarness() {
  const [zones, setZones] = useState<readonly ExtractionTemplateZoneInput[]>([]);
  return <ZoneEditor zones={zones} configuration={{ editor: editorConfiguration }} onChange={setZones} />;
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
