import type { ExtractionTemplateZoneInput } from '../contracts';

export interface ZoneIssue { index: number; message: string }

function overlap(left: ExtractionTemplateZoneInput, right: ExtractionTemplateZoneInput): boolean {
  if (left.page_number !== right.page_number) return false;
  const [lx, ly, lw, lh] = [Number(left.x), Number(left.y), Number(left.width), Number(left.height)];
  const [rx, ry, rw, rh] = [Number(right.x), Number(right.y), Number(right.width), Number(right.height)];
  return lx < rx + rw && lx + lw > rx && ly < ry + rh && ly + lh > ry;
}

export function validateZones(zones: readonly ExtractionTemplateZoneInput[]): readonly ZoneIssue[] {
  const issues: ZoneIssue[] = [];
  zones.forEach((zone, index) => {
    const x = Number(zone.x); const y = Number(zone.y); const width = Number(zone.width); const height = Number(zone.height);
    if (x < 0 || y < 0 || width <= 0 || height <= 0 || x + width > 1 || y + height > 1) issues.push({ index, message: 'Zone must remain inside the normalized page.' });
    zones.slice(index + 1).forEach((candidate, offset) => { if (overlap(zone, candidate)) { issues.push({ index, message: `Overlaps ${candidate.zone_name}.` }); issues.push({ index: index + offset + 1, message: `Overlaps ${zone.zone_name}.` }); } });
  });
  return issues;
}
