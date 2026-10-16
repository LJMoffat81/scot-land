/** Shared social preview image (LOGO-H2 / LOGO-FIX-1). Absolute prod URLs. */

export const DEFAULT_SITE_URL = "https://scot-land.scot";

/**
 * Public site origin for metadataBase / OG / Twitter images.
 * Override with NEXT_PUBLIC_SITE_URL; default is always production so a
 * production build never embeds localhost.
 */
export function getSiteUrl(): string {
  const raw = process.env.NEXT_PUBLIC_SITE_URL?.trim();
  if (!raw) return DEFAULT_SITE_URL;
  return raw.replace(/\/+$/, "");
}

export function getMetadataBase(): URL {
  return new URL(`${getSiteUrl()}/`);
}

export const OG_IMAGE_PATH = "/og-image.png";

/** Absolute OG image URL (must start with https://scot-land.scot in prod). */
export function absoluteOgImageUrl(): string {
  return `${getSiteUrl()}${OG_IMAGE_PATH}`;
}

export const OG_IMAGE = {
  url: absoluteOgImageUrl(),
  width: 1200,
  height: 630,
  alt: "Scot-LAND — Land value we all create",
} as const;

export const OG_IMAGES = [OG_IMAGE];
