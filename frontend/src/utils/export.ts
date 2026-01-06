/**
 * SPDX-License-Identifier: Apache-2.0
 *
 * Export Utilities
 *
 * Functions for exporting data to CSV/Excel formats.
 */

/**
 * Export data array to CSV file
 */
export function exportToCSV<T extends Record<string, unknown>>(
  data: T[],
  filename: string,
  headers?: string[]
): void {
  if (data.length === 0) {
    return;
  }

  const firstRow = data[0];
  if (!firstRow) {
    return;
  }

  // Get headers from first object if not provided
  const csvHeaders = headers ?? Object.keys(firstRow);

  // Create CSV content
  const csvContent = [
    csvHeaders.join(','), // Header row
    ...data.map((row) =>
      csvHeaders.map((header) => {
        const value = row[header];
        // Handle null/undefined
        if (value === null || value === undefined) {
          return '';
        }
        if (typeof value === 'string') {
          // Handle strings with commas/quotes
          if (value.includes(',') || value.includes('"')) {
            return `"${value.replace(/"/g, '""')}"`;
          }
          return value;
        }
        if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') {
          return String(value);
        }
        if (typeof value === 'symbol' || typeof value === 'function') {
          return '';
        }
        // Handle objects/arrays (stringify)
        return `"${JSON.stringify(value).replace(/"/g, '""')}"`;
      }).join(',')
    ),
  ].join('\n');

  // Create blob and download
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  const url = URL.createObjectURL(blob);
  link.setAttribute('href', url);
  link.setAttribute('download', `${filename}.csv`);
  link.style.visibility = 'hidden';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/**
 * Export timeseries data to CSV
 */
export function exportTimeseriesToCSV(
  data: { timestamp: string; date: string; value: number | null }[],
  metricName: string,
  filename?: string
): void {
  const csvData = data.map((point) => ({
    Date: point.date,
    Timestamp: point.timestamp,
    Value: point.value ?? '',
  }));

  exportToCSV(
    csvData,
    filename ?? `${metricName}_timeseries_${new Date().toISOString().split('T')[0]}`,
    ['Date', 'Timestamp', 'Value']
  );
}
