/**
 * Build public download bundles + manifest for /developers#downloads.
 *
 * Outputs under frontend/public/downloads/:
 *   manifest.json
 *   vacant-derelict-land.csv   (when source rollup exists)
 *   source-catalogue.csv       (always)
 *
 * Bundles without a real redistributable file are listed in the manifest with
 * file: null so the UI shows "JSON (for developers)" → #api.
 *
 * Run: node scripts/build-download-bundles.mjs
 */
import assert from "node:assert/strict";
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");
const repoRoot = join(frontendRoot, "..");
const outDir = join(frontendRoot, "public", "downloads");

const UPDATED = "2026-06-08";
const OGL = "OGL v3.0";

/** Open catalogue rows — no £ / AGR metrics (publication guard). */
const CATALOGUE_ROWS = [
  {
    id: "inspire_parcels",
    name: "Registers of Scotland land outlines",
    what_it_shows: "The shape of land parcels",
    licence: OGL,
    licence_url:
      "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    status: "on_map",
  },
  {
    id: "data_zones_2022",
    name: "Scottish Government Data Zones (2022)",
    what_it_shows: "Small statistics areas",
    licence: OGL,
    licence_url:
      "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    status: "on_map",
  },
  {
    id: "uk_hpi",
    name: "UK House Price Index",
    what_it_shows: "Average house prices by council",
    licence: OGL,
    licence_url:
      "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    status: "on_map",
  },
  {
    id: "vdl_register",
    name: "Scottish Vacant and Derelict Land Survey",
    what_it_shows: "Empty and derelict sites",
    licence: OGL,
    licence_url:
      "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    status: "on_map",
  },
  {
    id: "ldp_allocations",
    name: "Local Development Plans (Spatial Hub / councils)",
    what_it_shows:
      "Land set aside for future uses. Edinburgh is missing for now",
    licence: OGL,
    licence_url:
      "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    status: "on_map",
  },
  {
    id: "sepa_hydro",
    name: "SEPA hydropower sites and water licences",
    what_it_shows: "Hydro schemes and water use",
    licence: OGL,
    licence_url:
      "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    status: "on_map",
  },
  {
    id: "naturescot_sites",
    name: "NatureScot protected sites (SSSI, SPA, SAC, NNR)",
    what_it_shows:
      "Nature protection areas. Constraint: changes best use, adds no value",
    licence: OGL,
    licence_url:
      "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    status: "on_map",
  },
  {
    id: "lca_hutton",
    name: "James Hutton Institute Land Capability",
    what_it_shows: "How good land is for farming",
    licence: "James Hutton Open Data Licence",
    licence_url:
      "https://www.hutton.ac.uk/wp-content/uploads/2024/05/The-James-Hutton-Institute-Open-Data-Licence-download.pdf",
    status: "on_map",
  },
  {
    id: "crofting_register",
    name: "Crofting Commission registers",
    what_it_shows: "Crofts and common grazings (lists only)",
    licence: OGL,
    licence_url:
      "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    status: "on_map",
  },
  {
    id: "scotlis",
    name: "ScotLIS",
    what_it_shows: "Official title record (linked, not copied)",
    licence: "linked",
    licence_url: "",
    status: "linked",
  },
];

function csvEscape(value) {
  const s = String(value ?? "");
  if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

function writeCsv(path, headers, rows) {
  const lines = [headers.join(",")];
  for (const row of rows) {
    lines.push(headers.map((h) => csvEscape(row[h])).join(","));
  }
  writeFileSync(path, `${lines.join("\n")}\n`, "utf8");
}

mkdirSync(outDir, { recursive: true });

const bundles = [
  {
    id: "vdl",
    name: "Vacant and derelict land",
    whats_in_it:
      "Data Zone rollup of vacant and derelict land hectares (OGL inputs). Zone level only — not single sites as a title plan.",
    format: "CSV",
    licence: OGL,
    updated: UPDATED,
    file: null,
    bytes: null,
    api_anchor: "api-vdl",
    source: join(repoRoot, "data/processed/gis/dz_svdls_rollup.csv"),
    outName: "vacant-derelict-land.csv",
  },
  {
    id: "ldp",
    name: "Planned land use (Local Development Plans)",
    whats_in_it:
      "Sites planned for new homes and other allocated uses. National GeoJSON pack is not published here yet.",
    format: "GeoJSON",
    licence: OGL,
    updated: UPDATED,
    file: null,
    bytes: null,
    api_anchor: "api-ldp",
  },
  {
    id: "dz2022",
    name: "Data Zone boundaries (2022)",
    whats_in_it:
      "Scottish Government 2022 Data Zone outlines. Packaged GeoJSON is not published here yet.",
    format: "GeoJSON",
    licence: OGL,
    updated: UPDATED,
    file: null,
    bytes: null,
    api_anchor: "api-catalog",
  },
  {
    id: "crofting",
    name: "Crofting and common grazings lists",
    whats_in_it:
      "Crofting Commission Register of Crofts and common grazings tables (no personal names). Packaged CSV is not published here yet.",
    format: "CSV",
    licence: OGL,
    updated: UPDATED,
    file: null,
    bytes: null,
    api_anchor: "api-crofting",
  },
  {
    id: "catalog",
    name: "Source catalogue",
    whats_in_it:
      "What is on the map, what is only linked, and what is missing — with licences.",
    format: "CSV",
    licence: OGL,
    updated: UPDATED,
    file: null,
    bytes: null,
    api_anchor: "api-catalog",
    outName: "source-catalogue.csv",
  },
];

// Vacant & derelict land — copy processed DZ rollup when present.
{
  const vdl = bundles.find((b) => b.id === "vdl");
  assert.ok(vdl);
  if (existsSync(vdl.source)) {
    const dest = join(outDir, vdl.outName);
    copyFileSync(vdl.source, dest);
    const bytes = statSync(dest).size;
    vdl.file = vdl.outName;
    vdl.bytes = bytes;
    console.log(`vdl: wrote ${relative(frontendRoot, dest)} (${bytes} bytes)`);
  } else {
    console.warn(`vdl: source missing (${vdl.source}); card will use JSON fallback`);
  }
  delete vdl.source;
  delete vdl.outName;
}

// Source catalogue — always generated (no £ columns).
{
  const cat = bundles.find((b) => b.id === "catalog");
  assert.ok(cat);
  const dest = join(outDir, cat.outName);
  writeCsv(
    dest,
    ["id", "name", "what_it_shows", "licence", "licence_url", "status"],
    CATALOGUE_ROWS,
  );
  const text = readFileSync(dest, "utf8");
  assert.equal(text.includes("£"), false, "catalogue must not contain £");
  assert.equal(/agr_plot|rent_per_sqm|site_capital/i.test(text), false);
  const bytes = statSync(dest).size;
  cat.file = cat.outName;
  cat.bytes = bytes;
  console.log(`catalog: wrote ${relative(frontendRoot, dest)} (${bytes} bytes)`);
  delete cat.outName;
}

const manifest = {
  version: 1,
  updated: UPDATED,
  note:
    "Open downloads only. Missing files show as JSON (for developers) on /developers#downloads.",
  bundles: bundles.map(
    ({ id, name, whats_in_it, format, licence, updated, file, bytes, api_anchor }) => ({
      id,
      name,
      whats_in_it,
      format,
      licence,
      updated,
      file,
      bytes,
      api_anchor,
      href: file ? `/downloads/${file}` : null,
    }),
  ),
};

const manifestPath = join(outDir, "manifest.json");
writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
console.log(`manifest: wrote ${relative(frontendRoot, manifestPath)}`);
console.log(
  `build-download-bundles: ${manifest.bundles.filter((b) => b.file).length}/${manifest.bundles.length} files ready`,
);
