/**
 * FRONTEND-BATCH-2 §4 K1–K8 — Esri key / build-arg guard.
 * Usage: node scripts/test-esri-key-guard.mjs [--root <dir>]
 */
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

function parseArgs(argv) {
  let root = process.cwd();
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === "--root" && argv[i + 1]) {
      root = argv[i + 1];
      i += 1;
    }
  }
  return { root };
}

const KEY_LIKE =
  /AAP[KT][A-Za-z0-9_\-]{20,}|[?&]token=[A-Za-z0-9_\-\.]{20,}/;

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exit(1);
}

function listTrackedFiles(root) {
  const res = spawnSync("git", ["ls-files"], {
    cwd: root,
    encoding: "utf8",
  });
  if (res.status !== 0) {
    // Self-test temp dirs are not always git repos — walk the tree instead.
    const out = [];
    const walk = (dir) => {
      for (const name of readdirSync(dir)) {
        if (name === "node_modules" || name === ".git") continue;
        const full = join(dir, name);
        const st = statSync(full);
        if (st.isDirectory()) walk(full);
        else out.push(relative(root, full).split(sep).join("/"));
      }
    };
    walk(root);
    return out;
  }
  return res.stdout
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean)
    .filter((p) => !p.split("/").includes("node_modules"));
}

function checkK1(root, files) {
  for (const rel of files) {
    const full = join(root, rel);
    if (!existsSync(full) || !statSync(full).isFile()) continue;
    let text;
    try {
      text = readFileSync(full, "utf8");
    } catch {
      continue;
    }
    const lines = text.split(/\r?\n/);
    for (let i = 0; i < lines.length; i += 1) {
      if (KEY_LIKE.test(lines[i] ?? "")) {
        fail(`esri-key-guard: key-like string in ${rel}:${i + 1}`);
      }
    }
  }
}

function checkK2(root) {
  const path = join(root, "frontend", ".env.example");
  if (!existsSync(path)) fail("esri-key-guard: frontend/.env.example missing");
}

function checkK3(root) {
  const path = join(root, "frontend", ".env.example");
  const text = readFileSync(path, "utf8");
  const lines = text.split(/\r?\n/);
  const ok = lines.some((line) => line === "NEXT_PUBLIC_ESRI_BASEMAP_API_KEY=");
  if (!ok) {
    fail(
      "esri-key-guard: .env.example must have NEXT_PUBLIC_ESRI_BASEMAP_API_KEY= with no value",
    );
  }
}

function checkK4(root) {
  const path = join(root, "frontend", "Dockerfile");
  if (!existsSync(path)) fail("esri-key-guard: frontend/Dockerfile missing");
}

function checkK5(root) {
  const path = join(root, "frontend", "Dockerfile");
  const text = readFileSync(path, "utf8");
  const argRe = /^ARG NEXT_PUBLIC_ESRI_BASEMAP_API_KEY=(.*)$/m;
  const envRe = /^ENV NEXT_PUBLIC_ESRI_BASEMAP_API_KEY=\$NEXT_PUBLIC_ESRI_BASEMAP_API_KEY$/m;
  const argMatch = text.match(argRe);
  if (!argMatch || argMatch[1] !== "") {
    fail("esri-key-guard: Dockerfile build arg missing or has a default");
  }
  if (!envRe.test(text)) {
    fail("esri-key-guard: Dockerfile build arg missing or has a default");
  }
  const buildIdx = text.search(/^RUN npm run build$/m);
  const argIdx = text.search(argRe);
  const envIdx = text.search(envRe);
  if (buildIdx < 0 || argIdx < 0 || envIdx < 0 || argIdx > buildIdx || envIdx > buildIdx) {
    fail("esri-key-guard: Dockerfile build arg missing or has a default");
  }
}

function checkK6(root) {
  const path = join(root, "docker-compose.home.yml");
  if (!existsSync(path)) fail("esri-key-guard: docker-compose.home.yml missing");
}

function checkK7(root) {
  const path = join(root, "docker-compose.home.yml");
  const text = readFileSync(path, "utf8");
  const needle =
    "NEXT_PUBLIC_ESRI_BASEMAP_API_KEY: ${NEXT_PUBLIC_ESRI_BASEMAP_API_KEY:-}";
  if (!text.includes(needle)) {
    fail("esri-key-guard: compose build arg missing or literal");
  }
  // Reject a literal non-empty value on the same key.
  if (/NEXT_PUBLIC_ESRI_BASEMAP_API_KEY:\s*['"]?[A-Za-z0-9_\-]{8,}/.test(text)) {
    fail("esri-key-guard: compose build arg missing or literal");
  }
}

function checkK8(root, files) {
  for (const rel of files) {
    const base = rel.split("/").pop() ?? rel;
    if (
      base === ".env" ||
      base === ".env.local" ||
      /^\.env\.production/.test(base)
    ) {
      fail(`esri-key-guard: tracked env file ${rel}`);
    }
  }
}

function checkK9(root) {
  const path = join(root, ".env.example");
  if (!existsSync(path)) {
    fail(
      "esri-key-guard: root .env.example must have NEXT_PUBLIC_ESRI_BASEMAP_API_KEY= with no value",
    );
  }
  const text = readFileSync(path, "utf8");
  const lines = text.split(/\r?\n/);
  const ok = lines.some((line) => line === "NEXT_PUBLIC_ESRI_BASEMAP_API_KEY=");
  if (!ok) {
    fail(
      "esri-key-guard: root .env.example must have NEXT_PUBLIC_ESRI_BASEMAP_API_KEY= with no value",
    );
  }
}

function checkK10(root) {
  for (const rel of [".env", "frontend/.env"]) {
    const res = spawnSync("git", ["check-ignore", "-q", rel], {
      cwd: root,
      encoding: "utf8",
    });
    if (res.status !== 0) {
      fail("esri-key-guard: .env not gitignored");
    }
  }
}

function checkK11(root) {
  const path = join(root, "frontend", ".dockerignore");
  if (!existsSync(path)) {
    fail("esri-key-guard: .dockerignore must exclude .env files");
  }
  const text = readFileSync(path, "utf8");
  const lines = new Set(
    text
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter(Boolean),
  );
  if (!lines.has(".env") || !lines.has(".env.*")) {
    fail("esri-key-guard: .dockerignore must exclude .env files");
  }
}

function isCiJobHeader(line) {
  return /^  [A-Za-z0-9_-]+:\s*(?:#.*)?$/.test(line);
}

function checkK12(root) {
  const ciPath = join(root, ".github", "workflows", "ci.yml");
  if (!existsSync(ciPath)) {
    fail(
      "esri-key-guard: test:esri-key-build must run after playwright install in the same job",
    );
  }
  const ciLines = readFileSync(ciPath, "utf8").split(/\r?\n/);
  let buildIdx = -1;
  for (let i = 0; i < ciLines.length; i += 1) {
    if ((ciLines[i] ?? "").includes("npm run test:esri-key-build")) {
      buildIdx = i;
      break;
    }
  }
  if (buildIdx < 0) {
    fail(
      "esri-key-guard: test:esri-key-build must run after playwright install in the same job",
    );
  }
  let jobStart = 0;
  for (let i = buildIdx; i >= 0; i -= 1) {
    if (isCiJobHeader(ciLines[i] ?? "")) {
      jobStart = i;
      break;
    }
  }
  const before = ciLines.slice(jobStart, buildIdx);
  const hasInstall = before.some((line) =>
    (line ?? "").includes("playwright install --with-deps chromium"),
  );
  if (!hasInstall) {
    fail(
      "esri-key-guard: test:esri-key-build must run after playwright install in the same job",
    );
  }

  const pkgPath = join(root, "frontend", "package.json");
  if (!existsSync(pkgPath)) {
    fail("esri-key-guard: package scripts must not install browsers");
  }
  const pkg = JSON.parse(readFileSync(pkgPath, "utf8"));
  for (const val of Object.values(pkg.scripts ?? {})) {
    if (typeof val !== "string") continue;
    if (/playwright install/.test(val) || /ensure-playwright/.test(val)) {
      fail("esri-key-guard: package scripts must not install browsers");
    }
  }

  // Built at runtime so this file never contains the contiguous banned path.
  const bannedCli = ["playwright", "cli.js"].join("/");
  const scriptsDir = join(root, "frontend", "scripts");
  if (existsSync(scriptsDir)) {
    const walk = (dir) => {
      for (const name of readdirSync(dir)) {
        const full = join(dir, name);
        const st = statSync(full);
        if (st.isDirectory()) {
          walk(full);
          continue;
        }
        let text;
        try {
          text = readFileSync(full, "utf8");
        } catch {
          continue;
        }
        if (text.includes(bannedCli)) {
          fail(`esri-key-guard: do not resolve ${bannedCli}`);
        }
      }
    };
    walk(scriptsDir);
  }
}

function main() {
  const { root } = parseArgs(process.argv.slice(2));
  const files = listTrackedFiles(root);
  checkK1(root, files);
  checkK2(root);
  checkK3(root);
  checkK4(root);
  checkK5(root);
  checkK6(root);
  checkK7(root);
  checkK8(root, files);
  checkK9(root);
  checkK10(root);
  checkK11(root);
  checkK12(root);
  process.stdout.write("test-esri-key-guard: ok\n");
}

main();
