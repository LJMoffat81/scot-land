/**
 * Public VDL download rows.
 * A zone total of 1 or 2 sites publishes n_sites "<3" and no area.
 * A per-type count of 1 or 2 does the same for that type, even when the
 * zone total is 3 or more. A zero count is rounded like any other hectare.
 */

import assert from "node:assert/strict";

/** Nearest 0.5 ha, half up. Matches layers.vdl.round_area_ha. */
export function roundHalfHa(raw) {
  const n = Number(raw);
  if (!Number.isFinite(n)) return "";
  const negative = n < 0;
  const absMilli = Math.round(Math.abs(n) * 1000);
  const doubled = absMilli / 500;
  const nearest = Math.floor(doubled + 0.5);
  const out = ((negative ? -1 : 1) * nearest) / 2;
  return String(out);
}

function hectareKeyForCount(countKey) {
  if (!countKey.startsWith("n_") || countKey === "n_sites") return null;
  return `ha_${countKey.slice(2)}`;
}

function isSmallCount(value) {
  if (value === "1" || value === "2") return true;
  const n = Number(value);
  return n === 1 || n === 2;
}

/**
 * @param {Record<string, string>} row
 * @param {string[]} headers
 */
export function publishVdlDownloadRow(row, headers) {
  const count = Number(row.n_sites);
  const next = { ...row };
  if (!Number.isFinite(count) || count <= 0) {
    for (const key of headers) {
      if (key.startsWith("ha")) next[key] = roundHalfHa(row[key]);
    }
    return next;
  }
  if (count < 3) {
    next.n_sites = "<3";
    for (const key of headers) {
      if (key === "code" || key === "vintage" || key === "crosswalk_method") continue;
      if (key.startsWith("ha") || key.startsWith("n_")) next[key] = "";
    }
    next.n_sites = "<3";
    return next;
  }
  for (const key of headers) {
    if (key.startsWith("ha")) next[key] = roundHalfHa(row[key]);
  }
  for (const key of headers) {
    if (!key.startsWith("n_") || key === "n_sites") continue;
    if (!isSmallCount(row[key])) continue;
    next[key] = "<3";
    const haKey = hectareKeyForCount(key);
    if (haKey && (headers.includes(haKey) || haKey in next)) next[haKey] = "";
  }
  return next;
}

/**
 * Build check. Fails when a zone total or any per-type count is 1 or 2.
 * @param {Record<string, string>[]} rows
 * @param {string[]} headers
 */
export function assertPublishedVdlDownloadRows(rows, headers) {
  const countKeys = headers.filter(
    (key) => key.startsWith("n_") && key !== "n_sites",
  );
  const haKeys = headers.filter((key) => key.startsWith("ha"));
  for (const row of rows) {
    assert.equal(isSmallCount(row.n_sites), false, "n_sites");
    if (row.n_sites === "<3") {
      for (const key of haKeys) assert.equal(row[key], "");
    }
    for (const key of countKeys) {
      assert.equal(isSmallCount(row[key]), false, `${key} per-type count`);
      if (row[key] === "<3") {
        const haKey = hectareKeyForCount(key);
        if (haKey && haKeys.includes(haKey)) assert.equal(row[haKey], "");
      }
    }
    if (row.n_sites === "0") {
      for (const key of haKeys) {
        assert.notEqual(row[key], "0.000000");
        assert.match(row[key], /^-?\d+(?:\.5)?$/, `${key} rounded hectares`);
      }
    }
  }
}
