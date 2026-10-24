/**
 * SRC-C C3 — parse a tile manifest version into a visitor-facing as-of date.
 * Version form matches tileLayerFactory VERSION_RE: YYYY-MM-DD.<sha8>.
 */

const VERSION_RE = /^\d{4}-\d{2}-\d{2}\.[0-9a-f]{8}$/;

const MONTHS_EN_GB = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
] as const;

/**
 * Return e.g. "1 Oct 2026" (en-GB, UTC) for a valid calendar date version.
 * Returns null for any other value (wrong type, bad shape, impossible date).
 */
export function asOfFromVersion(v: unknown): string | null {
  if (typeof v !== "string") return null;
  if (!VERSION_RE.test(v)) return null;
  const datePart = v.slice(0, 10);
  const [ys, ms, ds] = datePart.split("-");
  const year = Number(ys);
  const month = Number(ms);
  const day = Number(ds);
  if (!Number.isInteger(year) || !Number.isInteger(month) || !Number.isInteger(day)) {
    return null;
  }
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;
  // Construct in UTC and require the components round-trip (rejects Feb 30 etc.).
  const utc = new Date(Date.UTC(year, month - 1, day));
  if (
    utc.getUTCFullYear() !== year ||
    utc.getUTCMonth() !== month - 1 ||
    utc.getUTCDate() !== day
  ) {
    return null;
  }
  return `${day} ${MONTHS_EN_GB[month - 1]} ${year}`;
}
