/**
 * SITE-CLICK-FALLTHROUGH-1 (UX-BATCH-2026-11-20) — compact HLS / LDP site card.
 *
 * Labels are W&UX 97e6d05b (20 Nov 2026). The note and source lines reuse the
 * locked PR-B strings 2, 3, 5 and 6 from the map layer registry, unchanged.
 * Values come only from the tile keep_fields (hls-open: local_auth, hla_year,
 * site_refer; ldp-highland: allocation, code, sda). A missing, empty or
 * whitespace value drops its row; nothing else is ever shown in its place.
 */
import { getMapLayer } from "./mapLayerRegistry";

export const SITE_CARD_HLS_LAYER = "tile-hls-open-fill";
export const SITE_CARD_LDP_LAYER = "tile-ldp-highland-fill";

export const SITE_CARD_HLS_HEADING = "Housing land supply site";
export const SITE_CARD_LDP_HEADING = "Local Development Plan allocation";
export const SITE_CARD_CLOSE_LABEL = "Close";
export const SITE_CARD_CLOSE_ARIA_LABEL = "Close site card";

export const SITE_CARD_HLS_ROWS = [
  { field: "local_auth", label: "Council" },
  { field: "hla_year", label: "Housing land audit year" },
  { field: "site_refer", label: "Site reference" },
] as const;

export const SITE_CARD_LDP_ROWS = [
  { field: "allocation", label: "Allocated for" },
  { field: "sda", label: "Place" },
  { field: "code", label: "Plan site code" },
] as const;

export type SiteCardRow = { label: string; value: string };

export type SiteCardSection = {
  kind: "hls" | "ldp";
  heading: string;
  rows: SiteCardRow[];
  note: string;
  source: string;
};

export type SiteCardData = { sections: SiteCardSection[] };

type Props = Record<string, unknown> | null | undefined;

/** Trimmed text, or null when missing / empty / whitespace / not a scalar. */
export function siteCardValue(raw: unknown): string | null {
  if (typeof raw === "number" && Number.isFinite(raw)) return String(raw);
  if (typeof raw !== "string") return null;
  const value = raw.trim();
  return value === "" ? null : value;
}

function rowsFrom(
  props: Props,
  spec: readonly { field: string; label: string }[],
): SiteCardRow[] {
  const rows: SiteCardRow[] = [];
  for (const { field, label } of spec) {
    const value = siteCardValue(props?.[field]);
    if (value !== null) rows.push({ label, value });
  }
  return rows;
}

function registryText(id: string, key: "subline" | "sourceCaption"): string {
  const text = getMapLayer(id)?.[key];
  if (typeof text !== "string" || text.trim() === "") {
    throw new Error(`siteCard: registry ${id}.${key} missing`);
  }
  return text;
}

/**
 * One card for a click: HLS section first, then LDP. Null when neither layer
 * was hit (the caller then falls through to the Data Zone / place lookup).
 */
export function buildSiteCard(
  hlsProps: Props,
  ldpProps: Props,
): SiteCardData | null {
  const sections: SiteCardSection[] = [];
  if (hlsProps) {
    sections.push({
      kind: "hls",
      heading: SITE_CARD_HLS_HEADING,
      rows: rowsFrom(hlsProps, SITE_CARD_HLS_ROWS),
      note: registryText("hls-open", "subline"),
      source: registryText("hls-open", "sourceCaption"),
    });
  }
  if (ldpProps) {
    sections.push({
      kind: "ldp",
      heading: SITE_CARD_LDP_HEADING,
      rows: rowsFrom(ldpProps, SITE_CARD_LDP_ROWS),
      note: registryText("ldp-highland", "subline"),
      source: registryText("ldp-highland", "sourceCaption"),
    });
  }
  return sections.length ? { sections } : null;
}
