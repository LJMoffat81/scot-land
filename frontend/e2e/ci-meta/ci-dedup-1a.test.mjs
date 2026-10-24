/**
 * CI-DEDUP-1a pin tests P1–P7 (+ P4b).
 * Run: npm run test:ci-dedup-1a
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { isFrontendChange } from "../../scripts/ci-paths-gate.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "../..");
const repoRoot = join(frontendRoot, "..");
const ciYml = readFileSync(join(repoRoot, ".github/workflows/ci.yml"), "utf8");
const quarantineMd = readFileSync(
  join(frontendRoot, "e2e/ci/QUARANTINE.md"),
  "utf8",
);

const EXPECTED_CONCURRENCY = `concurrency:
  group: ci-\${{ github.workflow }}-\${{ github.event.pull_request.head.ref || github.ref }}
  cancel-in-progress: \${{ github.ref != 'refs/heads/main' }}`;

test("P1 triggers are push [main], pull_request, weekly schedule, workflow_dispatch", () => {
  const onMatch = ciYml.match(/^on:\n([\s\S]*?)\n\npermissions:/m);
  assert.ok(onMatch, "expected on: block before permissions");
  const onBlock = `on:\n${onMatch[1]}`;
  // ARCH-6: weekly offline refresh guard (never fetches WFS/upstreams).
  const expected = `on:
  push:
    branches: [main]
  pull_request:
  schedule:
    - cron: "15 5 * * 1"
  workflow_dispatch:`;
  assert.equal(
    onBlock,
    expected,
    `triggers mismatch:\n--- actual ---\n${onBlock}\n--- expected ---\n${expected}`,
  );
});

test("P2 concurrency block matches item 2 exactly", () => {
  assert.ok(
    ciYml.includes(EXPECTED_CONCURRENCY),
    `concurrency block missing or wrong.\nExpected:\n${EXPECTED_CONCURRENCY}`,
  );
  assert.ok(
    !/^ {2}cancel-in-progress:\s*true\s*$/m.test(ciYml),
    "cancel-in-progress must not be bare true",
  );
});

test("P3 e2e jobs need changes + exact if; on: has no paths", () => {
  const onMatch = ciYml.match(/^on:\n([\s\S]*?)\n\npermissions:/m);
  assert.ok(onMatch);
  assert.doesNotMatch(
    onMatch[1],
    /paths(-ignore)?:/,
    "workflow on: must not use paths/paths-ignore",
  );

  for (const job of ["e2e:", "e2e-quarantine:"]) {
    const idx = ciYml.indexOf(`  ${job}`);
    assert.ok(idx >= 0, `missing job ${job}`);
    const slice = ciYml.slice(idx, idx + 400);
    assert.match(
      slice,
      /needs:\s*changes/,
      `${job} must have needs: changes`,
    );
    assert.match(
      slice,
      /if:\s*needs\.changes\.outputs\.frontend == 'true'/,
      `${job} must have exact if on frontend output`,
    );
  }
});

test("P4 isFrontendChange path matrix", () => {
  assert.equal(isFrontendChange(["frontend/app/x.tsx"]), true);
  assert.equal(isFrontendChange(["frontend/playwright.ci.config.ts"]), true);
  assert.equal(isFrontendChange([".github/workflows/ci.yml"]), true);
  assert.equal(isFrontendChange(["backend/x.py"]), false);
  assert.equal(isFrontendChange(["docs/a.md"]), false);
  assert.equal(isFrontendChange(["frontendx/a"]), false);
});

test("P4b CLI with invalid base ref exits non-zero", () => {
  const res = spawnSync(
    process.execPath,
    [
      join(frontendRoot, "scripts/ci-paths-gate.mjs"),
      "--base",
      "origin/definitely-not-a-real-ref-ci-dedup-1a",
    ],
    { encoding: "utf8", cwd: repoRoot },
  );
  assert.notEqual(res.status, 0, "invalid base must not exit 0");
  assert.match(res.stderr || "", /git diff failed/);
});

test("P5 grep-invert on e2e; grep + continue-on-error on quarantine", () => {
  const e2eIdx = ciYml.indexOf("  e2e:\n");
  const qIdx = ciYml.indexOf("  e2e-quarantine:\n");
  assert.ok(e2eIdx >= 0 && qIdx >= 0);
  const e2eBlock = ciYml.slice(e2eIdx, qIdx);
  const qBlock = ciYml.slice(qIdx);
  assert.match(e2eBlock, /--grep-invert @quarantine/);
  assert.match(qBlock, /--grep @quarantine/);
  assert.match(qBlock, /continue-on-error:\s*true/);
});

test("P6 quarantine tags match QUARANTINE.md exactly (4), no skip/fixme", () => {
  const mdTitles = [...quarantineMd.matchAll(/^\| Q\d+ \| `[^`]+` \| ([^|]+) \|/gm)]
    .map((m) => m[1].trim())
    .sort();
  assert.equal(
    mdTitles.length,
    4,
    `QUARANTINE.md expected 4 rows, got ${mdTitles.length}`,
  );

  const ciDir = join(frontendRoot, "e2e/ci");
  const tagged = [];
  for (const name of readdirSync(ciDir)) {
    if (!name.endsWith(".spec.ts")) continue;
    const src = readFileSync(join(ciDir, name), "utf8");
    const re =
      /(?:test\.skip|test\.fixme|test)\(\s*["'`]([^"'`]*@quarantine[^"'`]*)["'`]/g;
    let m;
    while ((m = re.exec(src))) {
      const title = m[1];
      const call = m[0];
      assert.ok(
        !call.startsWith("test.skip") && !call.startsWith("test.fixme"),
        `quarantined test must not be skipped: ${title}`,
      );
      assert.ok(
        existsSync(join(ciDir, name)),
        `file missing: ${name}`,
      );
      const base = title.replace(/\s*@quarantine\s*$/, "").trim();
      tagged.push(base);
    }
  }
  tagged.sort();
  assert.equal(
    tagged.length,
    4,
    `expected 4 quarantined, got ${tagged.length}`,
  );
  assert.deepEqual(
    tagged,
    mdTitles,
    `tagged titles must equal QUARANTINE.md list\ntagged=${JSON.stringify(tagged)}\nmd=${JSON.stringify(mdTitles)}`,
  );

  for (const file of [
    "layers-perf-3.spec.ts",
    "sea-stub-card.spec.ts",
    "ui-fix-4.spec.ts",
  ]) {
    assert.ok(existsSync(join(ciDir, file)), `${file} must still exist`);
  }
});

test("P7 word-area-1 openPlace has no waitForTimeout or card.count gate", () => {
  const src = readFileSync(
    join(frontendRoot, "e2e/ci/word-area-1.spec.ts"),
    "utf8",
  );
  assert.doesNotMatch(src, /waitForTimeout/);
  const openPlace = src.match(
    /async function openPlace\([\s\S]*?\n\}\n\nfor \(const viewport/,
  );
  assert.ok(openPlace, "openPlace function not found");
  assert.doesNotMatch(
    openPlace[0],
    /card\.count\s*\(/,
    "openPlace must not use card.count() gate",
  );
  assert.match(openPlace[0], /\.toPass\(/);
  assert.match(openPlace[0], /toBeVisible/);
});
