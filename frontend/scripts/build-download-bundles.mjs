/**
 * Build public download bundles + manifest for /developers#downloads.
 *
 * Outputs under frontend/public/downloads/:
 *   manifest.json
 *   vacant-derelict-land-dz2022.csv  (main VDL pack — DZ2022 vintage)
 *   vacant-derelict-land-dz2011.csv  (DZ2011 vintage)
 *   source-catalogue.csv
 *
 * Every packaged CSV carries estimate_label + licence_attribution columns
 * inside the file (not only in the manifest).
 *
 * Bundles without a redistributable file have file: null → UI shows
 * "JSON (for developers)" → #api.
 *
 * Run: npm run build:downloads
 */
import assert from "node:assert/strict";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");
const repoRoot = join(frontendRoot, "..");
const outDir = join(frontendRoot, "public", "downloads");

const {
  inspireRosOsAttribution,
  INSPIRE_HARVEST_YEAR,
} = await import(
  pathToFileURL(join(frontendRoot, "lib/inspireAttribution.ts")).href
);

const OGL = "OGL v3.0";
const ESTIMATE_NA =
  "not applicable: hectares and counts, not a value";
const ESTIMATE_CATALOGUE = "not applicable: source list, not a value";

/** Public VDL attribution (zone rollup — matches README_svdls_hls.md). */
const VDL_LICENCE_ATTRIBUTION =
  "OGL v3.0 — Scottish Vacant and Derelict Land Survey 2025 © Scottish Government; " +
  "Contains data from Improvement Service under OGL, supplied by Scotland's local " +
  "planning authorities and Loch Lomond & The Trossachs National Park Authority. " +
  "Data Zone boundaries © Scottish Government, contains OS data © Crown copyright " +
  "and database right 2026.";

const INSPIRE_LICENCE_ATTRIBUTION =
  `${inspireRosOsAttribution(INSPIRE_HARVEST_YEAR)} ${OGL} — Registers of Scotland INSPIRE Index Polygons`;

/** Open catalogue rows — no £ / AGR metrics (publication guard). */
const CATALOGUE_ROWS = [
  {
    id: "inspire_parcels",
    name: "Registers of Scotland land outlines",
    what_it_shows: "The shape of land parcels",
    licence: OGL,
    licence_url:
      "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    licence_attribution: INSPIRE_LICENCE_ATTRIBUTION,
    estimate_label: ESTIMATE_NA,
    status: "on_map",
    vintage: String(INSPIRE_HARVEST_YEAR),
  },
  {
    id: "data_zones_2022",
    name: "Scottish Government Data Zones (2022)",
    what_it_shows: "Small statistics areas",
    licence: OGL,
    licence_url:
      "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    licence_attribution:
      `${OGL} — Scottish Government Data Zones 2022; contains OS data © Crown copyright and database right 2026`,
    estimate_label: ESTIMATE_NA,
    status: "on_map",
    vintage: "2022",
  },
  {
    id: "uk_hpi",
    name: "UK House Price Index",
    what_it_shows: "Average house prices by council",
    licence: OGL,
    licence_url:
      "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    licence_attribution: `${OGL} — UK House Price Index (ONS / Land Registry)`,
    estimate_label: ESTIMATE_NA,
    status: "on_map",
    vintage: "2025",
  },
  {
    id: "vdl_register",
    name: "Scottish Vacant and Derelict Land Survey",
    what_it_shows: "Empty and derelict sites",
    licence: OGL,
    licence_url:
      "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    licence_attribution: VDL_LICENCE_ATTRIBUTION,
    estimate_label: ESTIMATE_NA,
    status: "on_map",
    vintage: "2025",
  },
  {
    id: "ldp_allocations",
    name: "Local Development Plans (Spatial Hub / councils)",
    what_it_shows:
      "Land set aside for future uses. Edinburgh is missing for now",
    licence: OGL,
    licence_url:
      "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    licence_attribution:
      `${OGL} — Local Development Plans (Spatial Hub / Improvement Service / councils)`,
    estimate_label: ESTIMATE_NA,
    status: "on_map",
    vintage: "2024",
  },
  {
    id: "sepa_hydro",
    name: "SEPA hydropower sites and water licences",
    what_it_shows: "Hydro schemes and water use",
    licence: OGL,
    licence_url:
      "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    licence_attribution: `${OGL} — SEPA hydropower sites and CAR water licences`,
    estimate_label: ESTIMATE_NA,
    status: "on_map",
    vintage: "2024",
  },
  {
    id: "naturescot_sites",
    name: "NatureScot protected sites (SSSI, SPA, SAC, NNR)",
    what_it_shows:
      "Nature protection areas. Constraint: changes best use, adds no value",
    licence: OGL,
    licence_url:
      "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    licence_attribution: `${OGL} — NatureScot protected sites (SSSI, SPA, SAC, NNR)`,
    estimate_label: ESTIMATE_NA,
    status: "on_map",
    vintage: "2024",
  },
  {
    id: "lca_hutton",
    name: "James Hutton Institute Land Capability",
    what_it_shows: "How good land is for farming",
    licence: "James Hutton Open Data Licence",
    licence_url:
      "https://www.hutton.ac.uk/wp-content/uploads/2024/05/The-James-Hutton-Institute-Open-Data-Licence-download.pdf",
    licence_attribution:
      "James Hutton Open Data Licence — Land Capability for Agriculture (James Hutton Institute)",
    estimate_label: ESTIMATE_NA,
    status: "on_map",
    vintage: "2017",
  },
  {
    id: "crofting_register",
    name: "Crofting Commission registers",
    what_it_shows: "Crofts and common grazings (lists only)",
    licence: OGL,
    licence_url:
      "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    licence_attribution:
      `${OGL} — Crofting Commission Register of Crofts and common grazings lists`,
    estimate_label: ESTIMATE_NA,
    status: "on_map",
    vintage: "2024",
  },
  {
    id: "scotlis",
    name: "ScotLIS",
    what_it_shows: "Official title record (linked, not copied)",
    licence: "linked",
    licence_url: "",
    licence_attribution:
      "Linked only — ScotLIS (Registers of Scotland); not republished",
    estimate_label: ESTIMATE_CATALOGUE,
    status: "linked",
    vintage: String(INSPIRE_HARVEST_YEAR),
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

/** Split a simple CSV line (VDL rollup has no quoted commas). */
function splitCsvLine(line) {
  return line.split(",");
}

function readSimpleCsv(path) {
  const text = readFileSync(path, "utf8");
  const lines = text.replace(/^\uFEFF/, "").split(/\r?\n/).filter((l) => l.length);
  assert.ok(lines.length >= 1, `empty csv: ${path}`);
  const headers = splitCsvLine(lines[0]);
  const rows = lines.slice(1).map((line) => {
    const values = splitCsvLine(line);
    const obj = {};
    for (let i = 0; i < headers.length; i++) {
      obj[headers[i]] = values[i] ?? "";
    }
    return obj;
  });
  return { headers, rows };
}

function assertCreditColumns(path) {
  const text = readFileSync(path, "utf8");
  const header = text.split(/\r?\n/, 1)[0];
  assert.match(header, /estimate_label/, `${path} missing estimate_label`);
  assert.match(
    header,
    /licence_attribution/,
    `${path} missing licence_attribution`,
  );
  assert.equal(text.includes("£"), false, `${path} must not contain £`);
}

// Wipe previous generated packs so stale combined files cannot linger.
if (existsSync(outDir)) {
  for (const name of [
    "vacant-derelict-land.csv",
    "vacant-derelict-land-dz2011.csv",
    "vacant-derelict-land-dz2022.csv",
    "source-catalogue.csv",
    "manifest.json",
  ]) {
    const p = join(outDir, name);
    if (existsSync(p)) rmSync(p);
  }
}
mkdirSync(outDir, { recursive: true });

/** @type {Array<Record<string, unknown>>} */
const bundles = [];

// --- VDL: one file per Data Zone vintage; DZ2022 is the main pack ---
{
  const source = join(repoRoot, "data/processed/gis/dz_svdls_rollup.csv");
  const vintages = [
    {
      id: "vdl-dz2022",
      vintage: "2022",
      name: "Vacant and derelict land (Data Zones 2022)",
      outName: "vacant-derelict-land-dz2022.csv",
      main: true,
    },
    {
      id: "vdl-dz2011",
      vintage: "2011",
      name: "Vacant and derelict land (Data Zones 2011)",
      outName: "vacant-derelict-land-dz2011.csv",
      main: false,
    },
  ];

  if (existsSync(source)) {
    const { headers, rows } = readSimpleCsv(source);
    assert.ok(headers.includes("vintage"), "VDL rollup needs vintage column");
    assert.ok(headers.includes("code"), "VDL rollup needs code column");

    for (const pack of vintages) {
      const filtered = rows.filter((r) => String(r.vintage) === pack.vintage);
      assert.ok(
        filtered.length > 0,
        `no VDL rows for vintage ${pack.vintage}`,
      );
      const outHeaders = [...headers, "estimate_label", "licence_attribution"];
      const outRows = filtered.map((r) => ({
        ...r,
        estimate_label: ESTIMATE_NA,
        licence_attribution: VDL_LICENCE_ATTRIBUTION,
      }));
      const dest = join(outDir, pack.outName);
      writeCsv(dest, outHeaders, outRows);
      assertCreditColumns(dest);
      const bytes = statSync(dest).size;
      bundles.push({
        id: pack.id,
        name: pack.name,
        whats_in_it:
          `Data Zone ${pack.vintage} rollup of vacant and derelict land hectares ` +
          `(SVDLS 2025 / OGL inputs). Zone level only — not single sites as a title plan.` +
          (pack.main ? " Main download (DZ2022)." : ""),
        format: "CSV",
        licence: OGL,
        updated: pack.vintage,
        file: pack.outName,
        bytes,
        api_anchor: "api-vdl",
        href: `/downloads/${pack.outName}`,
      });
      console.log(
        `${pack.id}: wrote ${relative(frontendRoot, dest)} (${bytes} bytes, ${filtered.length} rows)`,
      );
    }
  } else {
    console.warn(`vdl: source missing (${source}); cards will use JSON fallback`);
    for (const pack of vintages) {
      bundles.push({
        id: pack.id,
        name: pack.name,
        whats_in_it:
          `Data Zone ${pack.vintage} rollup of vacant and derelict land hectares. ` +
          "Packaged CSV is not available in this build.",
        format: "CSV",
        licence: OGL,
        updated: pack.vintage,
        file: null,
        bytes: null,
        api_anchor: "api-vdl",
        href: null,
      });
    }
  }
}

// API-only packs (keep pointing at #api until real files exist)
bundles.push(
  {
    id: "ldp",
    name: "Planned land use (Local Development Plans)",
    whats_in_it:
      "Sites planned for new homes and other allocated uses. National GeoJSON pack is not published here yet.",
    format: "GeoJSON",
    licence: OGL,
    updated: "2024",
    file: null,
    bytes: null,
    api_anchor: "api-ldp",
    href: null,
  },
  {
    id: "dz2022",
    name: "Data Zone boundaries (2022)",
    whats_in_it:
      "Scottish Government 2022 Data Zone outlines. Packaged GeoJSON is not published here yet.",
    format: "GeoJSON",
    licence: OGL,
    updated: "2022",
    file: null,
    bytes: null,
    api_anchor: "api-catalog",
    href: null,
  },
  {
    id: "crofting",
    name: "Crofting and common grazings lists",
    whats_in_it:
      "Crofting Commission Register of Crofts and common grazings tables (no personal names). Packaged CSV is not published here yet.",
    format: "CSV",
    licence: OGL,
    updated: "2024",
    file: null,
    bytes: null,
    api_anchor: "api-crofting",
    href: null,
  },
);

// Source catalogue — always generated (credits inside the file)
{
  const outName = "source-catalogue.csv";
  const dest = join(outDir, outName);
  const headers = [
    "id",
    "name",
    "what_it_shows",
    "licence",
    "licence_url",
    "licence_attribution",
    "estimate_label",
    "status",
    "vintage",
  ];
  writeCsv(dest, headers, CATALOGUE_ROWS);
  assertCreditColumns(dest);
  const text = readFileSync(dest, "utf8");
  assert.match(
    text,
    /Contains OS data © Crown copyright and database right 2026/,
  );
  assert.match(text, /Registers of Scotland/);
  assert.equal(/agr_plot|rent_per_sqm|site_capital/i.test(text), false);

  const inspireLine = text
    .split(/\r?\n/)
    .find((line) => line.startsWith("inspire_parcels,"));
  assert.ok(inspireLine, "inspire_parcels row missing");
  assert.match(inspireLine, /Registers of Scotland/);
  assert.match(
    inspireLine,
    /Contains OS data © Crown copyright and database right 2026/,
  );

  const bytes = statSync(dest).size;
  const catalogVintage = String(
    Math.max(...CATALOGUE_ROWS.map((r) => Number(r.vintage) || 0)),
  );
  bundles.push({
    id: "catalog",
    name: "Source catalogue",
    whats_in_it:
      "What is on the map, what is only linked, and what is missing — with licences.",
    format: "CSV",
    licence: OGL,
    updated: catalogVintage,
    file: outName,
    bytes,
    api_anchor: "api-catalog",
    href: `/downloads/${outName}`,
  });
  console.log(`catalog: wrote ${relative(frontendRoot, dest)} (${bytes} bytes)`);
}

const packagedUpdated = bundles
  .filter((b) => b.file)
  .map((b) => String(b.updated));
const manifestUpdated =
  packagedUpdated.sort().at(-1) ??
  String(Math.max(...bundles.map((b) => Number(b.updated) || 0)));

const manifest = {
  version: 1,
  updated: manifestUpdated,
  note:
    "Open downloads only. Missing files show as JSON (for developers) on /developers#downloads. " +
    "Each CSV carries estimate_label and licence_attribution columns inside the file.",
  bundles,
};

const manifestPath = join(outDir, "manifest.json");
writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
console.log(`manifest: wrote ${relative(frontendRoot, manifestPath)}`);
console.log(
  `build-download-bundles: ${manifest.bundles.filter((b) => b.file).length}/${manifest.bundles.length} files ready`,
);
