/**
 * Types for /downloads/manifest.json (site rewrite PR3 — items 4–5).
 * Cards on /developers#downloads read this; missing files → JSON (for developers).
 */

export type DownloadBundle = {
  id: string;
  name: string;
  whats_in_it: string;
  format: string;
  licence: string;
  /** Data vintage (e.g. VDL survey year 2025) — not the Data Zone set. */
  updated: string;
  /** Data Zone boundary set when distinct from updated (e.g. "2022" / "2011"). */
  zone_set?: string;
  file: string | null;
  bytes: number | null;
  api_anchor: string;
  href: string | null;
};

export type DownloadManifest = {
  version: number;
  updated: string;
  note?: string;
  bundles: DownloadBundle[];
};

/** Shown in the size slot when a download bundle has no packaged file yet. */
export const DOWNLOAD_NOT_PACKAGED_YET = "Not packaged yet";

/** Format byte size for the download card. */
export function formatDownloadBytes(bytes: number | null | undefined): string {
  if (bytes == null || !Number.isFinite(bytes) || bytes < 0) {
    return DOWNLOAD_NOT_PACKAGED_YET;
  }
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
