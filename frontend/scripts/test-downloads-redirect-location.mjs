/**
 * SW-013: production Location for /downloads and /open-api must keep ?moved=1.
 * Starts `next start` against an existing `.next` build (CI runs `npm run build` first).
 *
 * Run: npm run test:downloads-redirect-location
 */
import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { createServer } from "node:net";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");
const nextDir = join(frontendRoot, ".next");

assert.ok(
  existsSync(nextDir),
  "missing .next — run `npm run build` before this test",
);

function freePort() {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.listen(0, "127.0.0.1", () => {
      const addr = server.address();
      if (!addr || typeof addr === "string") {
        server.close();
        reject(new Error("could not bind ephemeral port"));
        return;
      }
      const { port } = addr;
      server.close((err) => (err ? reject(err) : resolve(port)));
    });
    server.on("error", reject);
  });
}

async function waitForServer(port, child, timeoutMs = 30_000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (child.exitCode !== null) {
      throw new Error(`next start exited early with code ${child.exitCode}`);
    }
    try {
      const res = await fetch(`http://127.0.0.1:${port}/developers`, {
        redirect: "manual",
      });
      if (res.status > 0) return;
    } catch {
      // not up yet
    }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error(`next start on :${port} did not become ready`);
}

async function locationOf(port, path) {
  const res = await fetch(`http://127.0.0.1:${port}${path}`, {
    redirect: "manual",
  });
  return {
    status: res.status,
    location: res.headers.get("location") || "",
    cacheControl: res.headers.get("cache-control") || "",
  };
}

const port = await freePort();
const child = spawn(
  "npx",
  ["next", "start", "-p", String(port), "-H", "127.0.0.1"],
  {
    cwd: frontendRoot,
    env: { ...process.env, NODE_ENV: "production", PORT: String(port) },
    stdio: ["ignore", "pipe", "pipe"],
  },
);

let stderr = "";
child.stderr.on("data", (chunk) => {
  stderr += chunk.toString();
});

try {
  await waitForServer(port, child);

  for (const [path, expectedLocation] of [
    ["/downloads", "/developers?moved=1#downloads"],
    ["/open-api", "/developers?moved=1#api"],
  ]) {
    const { status, location, cacheControl } = await locationOf(port, path);
    assert.equal(
      status,
      307,
      `${path}: expected 307, got ${status} (Location=${location})`,
    );
    assert.equal(
      location,
      expectedLocation,
      `${path}: Location must keep ?moved=1 (got ${JSON.stringify(location)})`,
    );
    assert.match(
      location,
      /\?moved=1/,
      `${path}: Location must include ?moved=1`,
    );
    assert.match(
      cacheControl,
      /no-store/i,
      `${path}: Cache-Control must be no-store (got ${JSON.stringify(cacheControl)})`,
    );
  }

  console.log("test-downloads-redirect-location: ok");
} catch (err) {
  if (stderr.trim()) {
    console.error(stderr.trim());
  }
  throw err;
} finally {
  child.kill("SIGTERM");
  await new Promise((r) => {
    const t = setTimeout(() => {
      child.kill("SIGKILL");
      r();
    }, 5000);
    child.on("exit", () => {
      clearTimeout(t);
      r();
    });
  });
}
