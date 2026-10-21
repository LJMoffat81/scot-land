/**
 * ESRI-KEY-PROD-1 — sequential next builds for B1/B2, then both servers.
 * Builds into the default `.next`, copies to `.next-esri-b1` / `.next-esri-b2`,
 * then starts each via the standalone server.js (output: standalone).
 * Starts the no-key server (3201) first so when Playwright sees 3200, both are up.
 * No NEXT_PUBLIC_E2E_HOOKS; dummy key assembled at runtime (never matches K1).
 */
import { spawn } from "node:child_process";
import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { createServer } from "node:http";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");
const DUMMY_ESRI_KEY = "TEST" + "KEY" + "x".repeat(8);
const DIST_B1 = ".next-esri-b1";
const DIST_B2 = ".next-esri-b2";

function baseEnv() {
  const env = { ...process.env };
  delete env.NEXT_PUBLIC_E2E_HOOKS;
  delete env.ESRI_KEY_DIST_DIR;
  return env;
}

function run(cmd, args, env) {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, args, {
      cwd: frontendRoot,
      env,
      stdio: "inherit",
      shell: process.platform === "win32",
    });
    child.on("error", reject);
    child.on("exit", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`${cmd} ${args.join(" ")} exited ${code}`));
    });
  });
}

function waitForUrl(url, timeoutMs) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const tick = () => {
      fetch(url)
        .then(() => resolve())
        .catch(() => {
          if (Date.now() - start > timeoutMs) {
            reject(new Error(`timeout waiting for ${url}`));
            return;
          }
          setTimeout(tick, 500);
        });
    };
    tick();
  });
}

function freePort(port) {
  return new Promise((resolve) => {
    const s = createServer();
    s.once("error", () => resolve(false));
    s.listen(port, "127.0.0.1", () => {
      s.close(() => resolve(true));
    });
  });
}

async function buildAndSnapshot(keyEnv, destName) {
  const env = baseEnv();
  if (keyEnv === undefined) delete env.NEXT_PUBLIC_ESRI_BASEMAP_API_KEY;
  else env.NEXT_PUBLIC_ESRI_BASEMAP_API_KEY = keyEnv;

  const nextDir = join(frontendRoot, ".next");
  if (existsSync(nextDir)) rmSync(nextDir, { recursive: true, force: true });

  process.stdout.write(
    `esri-key-build-servers: building ${destName} (key ${keyEnv === undefined ? "absent" : "present"})…\n`,
  );
  await run("npx", ["next", "build"], env);

  const dest = join(frontendRoot, destName);
  if (existsSync(dest)) rmSync(dest, { recursive: true, force: true });
  cpSync(nextDir, dest, { recursive: true });
}

function prepareStandalone(distName) {
  const dist = join(frontendRoot, distName);
  const standalone = join(dist, "standalone");
  const staticSrc = join(dist, "static");
  const staticDest = join(standalone, ".next", "static");
  const publicSrc = join(frontendRoot, "public");
  const publicDest = join(standalone, "public");

  mkdirSync(join(standalone, ".next"), { recursive: true });
  if (existsSync(staticSrc)) {
    if (existsSync(staticDest)) rmSync(staticDest, { recursive: true, force: true });
    cpSync(staticSrc, staticDest, { recursive: true });
  }
  if (existsSync(publicSrc)) {
    if (existsSync(publicDest)) rmSync(publicDest, { recursive: true, force: true });
    cpSync(publicSrc, publicDest, { recursive: true });
  }
  return standalone;
}

const children = [];

function shutdownChildren() {
  for (const child of children) {
    try {
      if (!child.killed) child.kill("SIGTERM");
    } catch {
      /* ignore */
    }
  }
}

function startStandalone(distName, port) {
  const standalone = prepareStandalone(distName);
  const env = baseEnv();
  env.PORT = String(port);
  env.HOSTNAME = "127.0.0.1";
  const child = spawn(process.execPath, ["server.js"], {
    cwd: standalone,
    env,
    stdio: "inherit",
    shell: false,
  });
  children.push(child);
  child.on("exit", (code, signal) => {
    process.stderr.write(
      `esri-key-build-servers: standalone :${port} exited code=${code} signal=${signal}\n`,
    );
    shutdownChildren();
    process.exit(code ?? 1);
  });
  return child;
}

process.on("SIGTERM", () => {
  shutdownChildren();
  process.exit(0);
});
process.on("SIGINT", () => {
  shutdownChildren();
  process.exit(0);
});

async function main() {
  for (const d of [DIST_B1, DIST_B2]) {
    const full = join(frontendRoot, d);
    if (existsSync(full)) rmSync(full, { recursive: true, force: true });
  }

  for (const port of [3200, 3201]) {
    if (!(await freePort(port))) {
      throw new Error(`port ${port} already in use`);
    }
  }

  await buildAndSnapshot(DUMMY_ESRI_KEY, DIST_B1);
  await buildAndSnapshot(undefined, DIST_B2);

  // No-key first so Playwright's wait on :3200 implies :3201 is already up.
  process.stdout.write("esri-key-build-servers: starting :3201 (no key)…\n");
  startStandalone(DIST_B2, 3201);
  await waitForUrl("http://127.0.0.1:3201", 120_000);

  process.stdout.write("esri-key-build-servers: starting :3200 (key)…\n");
  startStandalone(DIST_B1, 3200);
  await waitForUrl("http://127.0.0.1:3200", 120_000);

  process.stdout.write("esri-key-build-servers: both servers ready\n");
  await new Promise(() => {});
}

main().catch((err) => {
  process.stderr.write(`${err?.stack || err}\n`);
  process.exit(1);
});
