/**
 * Same-origin OpenFreeMap proxy.
 * The browser must not fetch https://tiles.openfreemap.org/planet itself:
 * a missing CORS header becomes a console error the place-card gate records.
 */

export const OFM_ORIGIN = "https://tiles.openfreemap.org";

export function ofmProxyUrl(upstreamUrl: string): string {
  const prefix = `${OFM_ORIGIN}/`;
  if (!upstreamUrl.startsWith(prefix)) return upstreamUrl;
  return `/api/ofm/${upstreamUrl.slice(prefix.length)}`;
}

/**
 * Rewrite style and TileJSON documents onto this site.
 * URLs are absolute: MapLibre fetches tiles from a blob worker, and a
 * path-only URL does not resolve there.
 */
export function rewriteOfmUrls(body: string, publicOrigin: string): string {
  const base = publicOrigin.replace(/\/$/, "");
  return body.replaceAll(`${OFM_ORIGIN}/`, `${base}/api/ofm/`);
}

export function ofmUpstreamFromSegments(
  segments: readonly string[],
): string | null {
  if (segments.length === 0) return null;
  for (const segment of segments) {
    if (
      segment === "" ||
      segment === "." ||
      segment === ".." ||
      segment.includes("/") ||
      segment.includes("\\") ||
      segment.includes("\0")
    ) {
      return null;
    }
  }
  return `${OFM_ORIGIN}/${segments.map((segment) => encodeURIComponent(segment)).join("/")}`;
}

export function ofmDocumentIsJson(
  contentType: string,
  segments: readonly string[],
): boolean {
  if (contentType.toLowerCase().includes("json")) return true;
  const last = segments[segments.length - 1] ?? "";
  if (last.endsWith(".json")) return true;
  if (segments[0] === "styles") return true;
  return segments.length === 1 && segments[0] === "planet";
}
