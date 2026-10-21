/**
 * Self-test for test-esri-key-guard.mjs — one temp fixture per K1–K8 + clean.
 * Key-like strings are assembled at runtime so nothing is committed.
 */
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  mkdirSync,
  mkdtempSync,
  writeFileSync,
  rmSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const script = join(here, "test-esri-key-guard.mjs");

function run(root) {
  const res = spawnSync(
    process.execPath,
    ["--experimental-strip-types", script, "--root", root],
    { encoding: "utf8" },
  );
  return {
    status: res.status ?? 1,
    stderr: (res.stderr || "").trim(),
    stdout: (res.stdout || "").trim(),
  };
}

function writeTree(root, files) {
  for (const [rel, body] of Object.entries(files)) {
    const full = join(root, rel);
    mkdirSync(dirname(full), { recursive: true });
    writeFileSync(full, body, "utf8");
  }
}

const CLEAN_DOCKERFILE = `FROM node:22-alpine AS builder
WORKDIR /app
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_ESRI_BASEMAP_API_KEY=
ENV NEXT_PUBLIC_ESRI_BASEMAP_API_KEY=$NEXT_PUBLIC_ESRI_BASEMAP_API_KEY
RUN npm run build
`;

const CLEAN_COMPOSE = `services:
  frontend:
    build:
      context: ./frontend
      args:
        NEXT_PUBLIC_API_URL: /backend
        NEXT_PUBLIC_ESRI_BASEMAP_API_KEY: \${NEXT_PUBLIC_ESRI_BASEMAP_API_KEY:-}
`;

const CLEAN_ENV_EXAMPLE = `# Esri basemap key (referrer-locked). Set on the deploy PC only; never commit the value.
NEXT_PUBLIC_ESRI_BASEMAP_API_KEY=
`;

function cleanFiles(extra = {}) {
  return {
    "frontend/Dockerfile": CLEAN_DOCKERFILE,
    "docker-compose.home.yml": CLEAN_COMPOSE,
    "frontend/.env.example": CLEAN_ENV_EXAMPLE,
    "frontend/app/page.tsx": "export default function Page() { return null }\n",
    ...extra,
  };
}

function withFixture(files, fn) {
  const root = mkdtempSync(join(tmpdir(), "esri-key-guard-"));
  try {
    writeTree(root, files);
    return fn(root);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

// Clean → exit 0
withFixture(cleanFiles(), (root) => {
  const res = run(root);
  assert.equal(res.status, 0, `clean failed: ${res.stderr}`);
  assert.match(res.stdout, /test-esri-key-guard: ok/);
});

// K1 — key-like string (assembled at runtime)
{
  const fake = "AAP" + "K" + "x".repeat(24);
  withFixture(
    cleanFiles({ "frontend/leak.txt": `token line ${fake}\n` }),
    (root) => {
      const res = run(root);
      assert.equal(res.status, 1);
      assert.match(
        res.stderr,
        /^esri-key-guard: key-like string in frontend\/leak\.txt:\d+$/,
      );
      assert.doesNotMatch(res.stderr, new RegExp(fake));
    },
  );
}

// K2 — missing .env.example
withFixture(
  (() => {
    const f = cleanFiles();
    delete f["frontend/.env.example"];
    return f;
  })(),
  (root) => {
    const res = run(root);
    assert.equal(res.status, 1);
    assert.equal(res.stderr, "esri-key-guard: frontend/.env.example missing");
  },
);

// K3 — env.example has a value
withFixture(
  cleanFiles({
    "frontend/.env.example": "NEXT_PUBLIC_ESRI_BASEMAP_API_KEY=notempty\n",
  }),
  (root) => {
    const res = run(root);
    assert.equal(res.status, 1);
    assert.equal(
      res.stderr,
      "esri-key-guard: .env.example must have NEXT_PUBLIC_ESRI_BASEMAP_API_KEY= with no value",
    );
  },
);

// K4 — missing Dockerfile
withFixture(
  (() => {
    const f = cleanFiles();
    delete f["frontend/Dockerfile"];
    return f;
  })(),
  (root) => {
    const res = run(root);
    assert.equal(res.status, 1);
    assert.equal(res.stderr, "esri-key-guard: frontend/Dockerfile missing");
  },
);

// K5 — ARG has a default
withFixture(
  cleanFiles({
    "frontend/Dockerfile": `FROM node:22-alpine AS builder
ARG NEXT_PUBLIC_ESRI_BASEMAP_API_KEY=secret
ENV NEXT_PUBLIC_ESRI_BASEMAP_API_KEY=$NEXT_PUBLIC_ESRI_BASEMAP_API_KEY
RUN npm run build
`,
  }),
  (root) => {
    const res = run(root);
    assert.equal(res.status, 1);
    assert.equal(
      res.stderr,
      "esri-key-guard: Dockerfile build arg missing or has a default",
    );
  },
);

// K6 — missing compose
withFixture(
  (() => {
    const f = cleanFiles();
    delete f["docker-compose.home.yml"];
    return f;
  })(),
  (root) => {
    const res = run(root);
    assert.equal(res.status, 1);
    assert.equal(res.stderr, "esri-key-guard: docker-compose.home.yml missing");
  },
);

// K7 — compose literal / missing
withFixture(
  cleanFiles({
    "docker-compose.home.yml": `services:
  frontend:
    build:
      args:
        NEXT_PUBLIC_API_URL: /backend
`,
  }),
  (root) => {
    const res = run(root);
    assert.equal(res.status, 1);
    assert.equal(
      res.stderr,
      "esri-key-guard: compose build arg missing or literal",
    );
  },
);

// K8 — tracked env file
withFixture(cleanFiles({ "frontend/.env.local": "X=1\n" }), (root) => {
  const res = run(root);
  assert.equal(res.status, 1);
  assert.equal(res.stderr, "esri-key-guard: tracked env file frontend/.env.local");
});

process.stdout.write("test-esri-key-guard.selftest: ok\n");
