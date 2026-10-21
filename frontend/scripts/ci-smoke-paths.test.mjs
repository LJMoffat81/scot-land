/**
 * CI-DEDUP-1b-r2 — smoke.sh / smoke.ps1 /backend default path pins (S1–S3).
 * Run via: npm run test:ci-dedup-1b-r2
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";
import http from "node:http";
import test, { describe } from "node:test";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");
const repoRoot = join(frontendRoot, "..");
const smokeSh = join(repoRoot, "scripts", "smoke.sh");
const smokePs1 = join(repoRoot, "scripts", "smoke.ps1");

async function withSmokeServer(handler, fn) {
  const server = http.createServer(handler);
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address();
  try {
    await fn(port);
  } finally {
    await new Promise((resolve, reject) =>
      server.close((err) => (err ? reject(err) : resolve())),
    );
  }
}

/** Async spawn so the Node HTTP server can answer while smoke.sh curls. */
function runSmoke(args, env) {
  return new Promise((resolve) => {
    const child = spawn("bash", args, {
      cwd: repoRoot,
      env,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (d) => {
      stdout += d;
    });
    child.stderr.on("data", (d) => {
      stderr += d;
    });
    child.on("close", (status) => {
      resolve({ status: status ?? 1, stdout, stderr });
    });
  });
}

function backendOkHandler(paths) {
  return (req, res) => {
    const path = req.url.split("?")[0];
    paths.push(path);
    if (path === "/backend/health") {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ status: "ok", version: "t" }));
      return;
    }
    if (path === "/backend/layers/catalog") {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ layers: [] }));
      return;
    }
    if (path === "/") {
      res.writeHead(200, { "content-type": "text/html" });
      res.end("ok");
      return;
    }
    res.writeHead(404);
    res.end("no");
  };
}

const cleanEnv = {
  PATH: process.env.PATH,
  HOME: process.env.HOME,
};

describe("CI-DEDUP-1b-r2 smoke paths", { concurrency: 1 }, () => {
  test("S1 bash smoke.sh defaults API to SITE_URL/backend", async () => {
    const paths = [];
    await withSmokeServer(backendOkHandler(paths), async (port) => {
      const res = await runSmoke([smokeSh, `http://127.0.0.1:${port}`], cleanEnv);
      assert.equal(res.status, 0, res.stdout + "\n" + res.stderr);
      assert.ok(
        paths.includes("/backend/health"),
        "server log missing /backend/health",
      );
      assert.ok(
        paths.includes("/backend/layers/catalog"),
        "server log missing /backend/layers/catalog",
      );
      assert.ok(!paths.includes("/health"), "server log contains /health");
    });
  });

  test("S2 explicit API_URL=.../backend does not double /backend", async () => {
    const paths = [];
    await withSmokeServer(backendOkHandler(paths), async (port) => {
      const res = await runSmoke([smokeSh], {
        ...cleanEnv,
        SITE_URL: `http://127.0.0.1:${port}`,
        API_URL: `http://127.0.0.1:${port}/backend`,
      });
      assert.equal(res.status, 0, res.stdout + "\n" + res.stderr);
      assert.ok(
        !paths.some((p) => p.includes("/backend/backend")),
        "/backend/backend/health",
      );
    });
  });

  test("S3 health only at /health fails row /backend/health", async () => {
    await withSmokeServer((req, res) => {
      const path = req.url.split("?")[0];
      if (path === "/") {
        res.writeHead(200, { "content-type": "text/html" });
        res.end("ok");
        return;
      }
      if (path === "/health") {
        res.writeHead(200, { "content-type": "application/json" });
        res.end(JSON.stringify({ status: "ok", version: "t" }));
        return;
      }
      res.writeHead(404);
      res.end("no");
    }, async (port) => {
      const res = await runSmoke([smokeSh, `http://127.0.0.1:${port}`], cleanEnv);
      assert.notEqual(res.status, 0);
      assert.match(res.stdout, /FAIL\s+\|\s+\/backend\/health/);
    });
  });

  test("smoke.ps1 default contains $SiteUrl/backend (static pin)", () => {
    const ps1 = readFileSync(smokePs1, "utf8");
    assert.ok(
      ps1.includes('"$SiteUrl/backend"'),
      'smoke.ps1 default must contain "$SiteUrl/backend"',
    );
  });
});
