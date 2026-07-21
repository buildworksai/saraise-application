import { validateZones } from './zone-utils';
import type { ExtractionTemplateZoneInput } from '../contracts';

const zone = (name: string, x: string, y: string): ExtractionTemplateZoneInput => ({ zone_name: name, extraction_key: name.toLowerCase(), zone_type: 'text', x, y, width: '0.2500', height: '0.1000', page_number: 1, expected_data_type: 'string', is_required: true });

describe('template zone geometry', () => {
  it('accepts separated normalized zones', () => {
    expect(validateZones([zone('Supplier', '0.1000', '0.1000'), zone('Total', '0.1000', '0.4000')])).toEqual([]);
  });

  it('reports overlap on both affected zones', () => {
    const issues = validateZones([zone('Supplier', '0.1000', '0.1000'), zone('Total', '0.2000', '0.1500')]);
    expect(issues.map((issue) => issue.index)).toEqual([0, 1]);
    expect(issues.every((issue) => issue.message.startsWith('Overlaps'))).toBe(true);
  });

  it('rejects out-of-bounds geometry', () => {
    expect(validateZones([zone('Overflow', '0.9000', '0.9500')])).toEqual([{ index: 0, message: 'Zone must remain inside the normalized page.' }]);
  });
});
