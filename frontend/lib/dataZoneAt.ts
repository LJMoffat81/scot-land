/**
 * True for an empty data-zones/at body: null, or an object with no fields.
 * `{ code: null }` is a stub that still continues to the place card.
 * A FeatureCollection is a geo stub for other /layers/ paths.
 */
export function isEmptyDataZoneAt(data: unknown): boolean {
  if (data == null) return true;
  if (typeof data !== "object" || Array.isArray(data)) return true;
  const record = data as { type?: unknown };
  if (record.type === "FeatureCollection") return false;
  return Object.keys(record).length === 0;
}
