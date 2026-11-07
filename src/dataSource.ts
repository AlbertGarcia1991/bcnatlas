// Public URL configuration only. R2 access keys remain inside the Python API.
const base = (import.meta.env.VITE_DATA_BASE_URL || '/api/data').replace(/\/$/, '');
export function dataUrl(name: string): string {
  const filename = name.split('/').pop() || '';
  if (!/^[a-z0-9-]+\.json$/.test(filename)) throw Error('Invalid data asset name');
  return `${base}/${filename}`;
}
