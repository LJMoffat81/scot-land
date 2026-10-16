/**
 * PRIVACY-1 — visitor source has no email address, no github.com, and no
 * Laurie/Moffat outside the single allowed phrase.
 */
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");
const roots = ["app", "components", "lib", "public"].map((name) =>
  join(frontendRoot, name),
);

const TEXT_EXT = new Set([
  ".ts",
  ".tsx",
  ".js",
  ".mjs",
  ".cjs",
  ".css",
  ".html",
  ".json",
  ".xml",
  ".txt",
  ".svg",
  ".webmanifest",
  ".md",
]);

const EMAIL_RE = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i;
const ALLOWED_PHRASE = "led by Laurie Moffat";
const ALLOWED_FILE = "app/how-we-built-this/page.tsx";

function isSwagger(relPosix) {
  return relPosix === "public/swagger-ui" || relPosix.startsWith("public/swagger-ui/");
}

/** @type {string[]} */
const hits = [];

function walk(dir) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    const rel = relative(frontendRoot, full).split(sep).join("/");
    if (isSwagger(rel)) continue;
    const st = statSync(full);
    if (st.isDirectory()) {
      walk(full);
      continue;
    }
    const dot = name.lastIndexOf(".");
    const ext = dot >= 0 ? name.slice(dot) : "";
    if (!TEXT_EXT.has(ext)) continue;
    const text = readFileSync(full, "utf8");
    if (EMAIL_RE.test(text)) hits.push(`${rel}: email address`);
    if (/github\.com/i.test(text)) hits.push(`${rel}: github.com`);
    let names = text;
    if (rel === ALLOWED_FILE) {
      const count = text.split(ALLOWED_PHRASE).length - 1;
      if (count !== 1) {
        hits.push(`${rel}: allowed phrase count ${count}`);
      }
      names = text.split(ALLOWED_PHRASE).join("");
    }
    if (/Laurie|Moffat/.test(names)) hits.push(`${rel}: name`);
  }
}

for (const root of roots) walk(root);

assert.deepEqual(hits, [], hits.join("\n"));
console.log("test-privacy-1: ok");
