/**
 * CI-DEDUP-1a — decide whether frontend / CI-workflow paths changed.
 * Pure matcher + CLI. Diff failures exit non-zero; never default to false.
 */
import { appendFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const FRONTEND_PREFIX = /^frontend\//;
const PLAYWRIGHT_CONFIG = /^frontend\/playwright.*\.config\.ts$/;
const CI_WORKFLOW = /^\.github\/workflows\/ci\.yml$/;

/**
 * @param {string[]} paths
 * @returns {boolean}
 */
export function isFrontendChange(paths) {
  if (!Array.isArray(paths)) {
    throw new TypeError("isFrontendChange: paths must be an array");
  }
  return paths.some(
    (p) =>
      FRONTEND_PREFIX.test(p) ||
      PLAYWRIGHT_CONFIG.test(p) ||
      CI_WORKFLOW.test(p),
  );
}

/**
 * @param {string[]} argv
 * @param {{ spawnSync?: typeof spawnSync, env?: NodeJS.ProcessEnv, cwd?: string }} [deps]
 * @returns {number} exit code
 */
export function runCli(argv, deps = {}) {
  const spawn = deps.spawnSync ?? spawnSync;
  const env = deps.env ?? process.env;
  const cwd = deps.cwd ?? process.cwd();

  let mode = null;
  let baseRef = null;
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--push-main") mode = "push-main";
    else if (argv[i] === "--base") {
      baseRef = argv[++i];
      mode = mode ?? "pull_request";
    }
  }

  if (mode === "push-main") {
    writeGithubOutput(env, "true");
    process.stdout.write("frontend=true\n");
    return 0;
  }

  if (!baseRef) {
    process.stderr.write(
      "ci-paths-gate: need --push-main or --base <ref>\n",
    );
    return 1;
  }

  const diff = spawn(
    "git",
    ["diff", "--name-only", `${baseRef}...HEAD`],
    { encoding: "utf8", cwd, env },
  );
  if (diff.status !== 0) {
    process.stderr.write(
      `ci-paths-gate: git diff failed (status ${diff.status}): ${diff.stderr || diff.stdout || ""}\n`,
    );
    return diff.status === null ? 1 : diff.status;
  }

  const paths = (diff.stdout || "")
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
  const frontend = isFrontendChange(paths);
  writeGithubOutput(env, frontend ? "true" : "false");
  process.stdout.write(`frontend=${frontend ? "true" : "false"}\n`);
  return 0;
}

/**
 * @param {NodeJS.ProcessEnv} env
 * @param {string} value
 */
function writeGithubOutput(env, value) {
  const out = env.GITHUB_OUTPUT;
  if (!out) return;
  appendFileSync(out, `frontend=${value}\n`);
}

const entry = process.argv[1] && fileURLToPath(import.meta.url);
if (entry && process.argv[1] === entry) {
  process.exit(runCli(process.argv.slice(2)));
}
