/**
 * Recursive liberty scan for FRONTEND-BATCH-2 T-M5 / R5.
 * Replaces spawnSync("rg") so CI runners without ripgrep still fail correctly.
 */
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const SCAN_EXTS = new Set([".ts", ".tsx", ".mjs", ".css", ".json"]);

export function scanLibertyHits(
  rootDirs: string[],
  cwd: string = process.cwd(),
): { hits: string[]; filesScanned: number } {
  const hits: string[] = [];
  let filesScanned = 0;
  const walk = (dir: string) => {
    if (!existsSync(dir)) return;
    let entries: string[];
    try {
      entries = readdirSync(dir);
    } catch {
      return;
    }
    for (const name of entries) {
      if (name === "node_modules" || name === ".next" || name === "dist") continue;
      const full = join(dir, name);
      let st;
      try {
        st = statSync(full);
      } catch {
        continue;
      }
      if (st.isDirectory()) {
        walk(full);
        continue;
      }
      const dot = name.lastIndexOf(".");
      const ext = dot >= 0 ? name.slice(dot) : "";
      if (!SCAN_EXTS.has(ext)) continue;
      filesScanned += 1;
      let text: string;
      try {
        text = readFileSync(full, "utf8");
      } catch {
        continue;
      }
      const lines = text.split(/\r?\n/);
      for (let i = 0; i < lines.length; i += 1) {
        if (/liberty/i.test(lines[i]!)) {
          hits.push(`${relative(cwd, full)}:${i + 1}`);
        }
      }
    }
  };
  for (const d of rootDirs) walk(join(cwd, d));
  return { hits, filesScanned };
}
