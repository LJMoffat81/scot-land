/**
 * LOGO-H3: after `next build`, `.next/` and `public/` must not contain the
 * retired mark filename. `public/swagger-ui/` is excluded.
 *
 * A temporary dirty tree proves the scanner still fails when the old name
 * is re-added. Run: npm run test:logo-h3
 */
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");
const NEEDLE = "scot-land-mark";
const OLD_FILE = "scot-land-mark.png";

function isSwagger(relPosix) {
  return (
    relPosix === "swagger-ui" ||
    relPosix.startsWith("swagger-ui/") ||
    relPosix === "public/swagger-ui" ||
    relPosix.startsWith("public/swagger-ui/")
  );
}

/** @returns {string[]} repo-relative hit descriptions */
export function findRetiredMark(root) {
  const hits = [];
  const needle = Buffer.from(NEEDLE);

  function walk(dir) {
    if (!existsSync(dir)) return;
    for (const name of readdirSync(dir)) {
      const full = join(dir, name);
      const rel = relative(root, full).split(sep).join("/");
      if (isSwagger(rel)) continue;
      const st = statSync(full);
      if (st.isDirectory()) {
        walk(full);
        continue;
      }
      if (name === OLD_FILE) hits.push(`${rel}: file name`);
      const buf = readFileSync(full);
      if (buf.includes(needle)) hits.push(`${rel}: contains ${NEEDLE}`);
    }
  }

  walk(root);
  return hits;
}

const dirty = mkdtempSync(join(tmpdir(), "logo-h3-scan-"));
try {
  writeFileSync(join(dirty, "note.txt"), `still using ${NEEDLE} in a bundle`);
  writeFileSync(join(dirty, OLD_FILE), "not a real image");
  writeFileSync(join(dirty, "swagger-ui-decoy.txt"), "public/swagger-ui is not this tree");
  const found = findRetiredMark(dirty);
  assert.ok(
    found.some((hit) => hit.includes("note.txt")),
    "scanner must report the retired name when it is re-added",
  );
  assert.ok(
    found.some((hit) => hit.includes(OLD_FILE)),
    "scanner must report a file named with the retired mark",
  );

  const clean = mkdtempSync(join(tmpdir(), "logo-h3-clean-"));
  try {
    writeFileSync(join(clean, "logo-mark-h3.png"), "ok");
    assert.deepEqual(findRetiredMark(clean), []);
  } finally {
    rmSync(clean, { recursive: true, force: true });
  }
} finally {
  rmSync(dirty, { recursive: true, force: true });
}

const publicDir = join(frontendRoot, "public");
const nextDir = join(frontendRoot, ".next");
assert.ok(existsSync(publicDir), "public/ is missing");
assert.ok(
  existsSync(nextDir),
  "LOGO-H3 build scan requires .next — run after next build",
);

const hits = [
  ...findRetiredMark(publicDir).map((hit) => `public/${hit}`),
  ...findRetiredMark(nextDir).map((hit) => `.next/${hit}`),
];
assert.deepEqual(
  hits,
  [],
  `retired mark name must not ship:\n${hits.join("\n")}`,
);

console.log("test-logo-h3: ok");
