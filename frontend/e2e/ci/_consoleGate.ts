/**
 * CI-DEDUP-1b-r2 — strict console gate.
 * Same-origin 404/503 and app errors fail; only EXTERNAL_HOSTS locations and
 * the exact AbortError text are ignored. expectError is the sole intentional-error path.
 *
 * assertClean(): after the check (pass or throw), clears recorded errors and
 * expectations so a later teardown assertClean is a no-op once the body (or an
 * earlier assertClean) already ran.
 */
import type { Page } from "@playwright/test";

/** Frozen exact list. Additions need a signed-off spec change. */
export const EXTERNAL_HOSTS = Object.freeze([
  "tiles.openfreemap.org",
  "basemapstyles-api.arcgis.com",
  "ibasemaps-api.arcgis.com",
  "basemaps-api.arcgis.com",
  "cdn.arcgis.com",
  "www.arcgis.com",
] as const);

export type ExternalHost = (typeof EXTERNAL_HOSTS)[number];

const ABORT_EXACT = "AbortError: The user aborted a request.";

export type RecordedError = { text: string; url: string };

export type ExpectErrorSpec =
  | { text: string; count: number; urlPath?: never; status?: never }
  | { urlPath: string; status: number; count: number; text?: never };

type Expectation = {
  key: string;
  count: number;
  match: (rec: RecordedError) => boolean;
};

export type StrictConsoleGate = {
  errors: RecordedError[];
  expectError: (e: ExpectErrorSpec) => void;
  assertClean: () => void;
  /**
   * Compat for e2e/build-key (out of 1b-r2 edit scope) which reads
   * gate.consoleErrors / gate.pageErrors via assertConsoleStrict.
   * consoleErrors = all recorded texts; pageErrors = pageerror texts only.
   */
  readonly consoleErrors: string[];
  readonly pageErrors: string[];
};

/** Page → gate registry so helpers can look up the auto-attached gate. */
const gatesByPage = new WeakMap<Page, StrictConsoleGate>();

export function registerStrictGate(page: Page, gate: StrictConsoleGate): void {
  gatesByPage.set(page, gate);
}

export function getStrictGateForPage(page: Page): StrictConsoleGate | undefined {
  return gatesByPage.get(page);
}

function isExternalHost(hostname: string): hostname is ExternalHost {
  return (EXTERNAL_HOSTS as readonly string[]).includes(hostname);
}

function isIgnored(rec: RecordedError): boolean {
  if (rec.text === ABORT_EXACT) return true;
  if (!rec.url) return false;
  try {
    const host = new URL(rec.url).hostname;
    return isExternalHost(host);
  } catch {
    return false;
  }
}

/**
 * Strict console gate: records console errors + pageerrors.
 * Ignores only EXTERNAL_HOSTS location hosts, or the exact Playwright abort text.
 */
export function attachStrictConsoleGate(page: Page): StrictConsoleGate {
  const errors: RecordedError[] = [];
  const pageErrorTexts: string[] = [];
  const expectations: Expectation[] = [];
  const seenKeys = new Set<string>();

  page.on("console", (msg) => {
    if (msg.type() !== "error") return;
    const loc = msg.location();
    errors.push({ text: msg.text(), url: loc?.url ?? "" });
  });
  page.on("pageerror", (err) => {
    const text = String(err);
    pageErrorTexts.push(text);
    errors.push({ text, url: page.url() });
  });

  function expectError(e: ExpectErrorSpec): void {
    const hasText = Object.prototype.hasOwnProperty.call(e, "text");
    const hasUrlPath = Object.prototype.hasOwnProperty.call(e, "urlPath");

    if (hasText && hasUrlPath) {
      throw new Error(
        "CONSOLE_GATE: expectError takes text or urlPath, not both",
      );
    }
    if (!hasText && !hasUrlPath) {
      throw new Error(
        "CONSOLE_GATE: expectError needs a non-empty text or urlPath",
      );
    }

    if (hasText) {
      const text = (e as { text: unknown }).text;
      if (text instanceof RegExp || typeof text !== "string") {
        throw new Error(
          "CONSOLE_GATE: expectError takes an exact string, not a RegExp",
        );
      }
      if (text.trim() === "") {
        throw new Error(
          "CONSOLE_GATE: expectError needs a non-empty text or urlPath",
        );
      }
    }

    if (hasUrlPath) {
      const urlPath = (e as { urlPath: unknown }).urlPath;
      if (urlPath instanceof RegExp || typeof urlPath !== "string") {
        throw new Error(
          "CONSOLE_GATE: expectError takes an exact string, not a RegExp",
        );
      }
      if (urlPath.trim() === "") {
        throw new Error(
          "CONSOLE_GATE: expectError needs a non-empty text or urlPath",
        );
      }
      const status = (e as { status: unknown }).status;
      if (
        typeof status !== "number" ||
        !Number.isInteger(status) ||
        status < 400 ||
        status > 599
      ) {
        throw new Error(
          `CONSOLE_GATE: expectError status must be 400-599, got ${status}`,
        );
      }
    }

    const count = e.count;
    if (typeof count !== "number" || !Number.isInteger(count) || count < 1) {
      throw new Error(
        `CONSOLE_GATE: expectError count must be an integer >= 1, got ${count}`,
      );
    }

    let key: string;
    let match: (rec: RecordedError) => boolean;
    if (hasText) {
      const text = (e as { text: string }).text;
      key = text;
      match = (rec) => rec.text === text;
    } else {
      const urlPath = (e as { urlPath: string }).urlPath;
      const status = (e as { status: number }).status;
      key = `${status} ${urlPath}`;
      const prefix = `Failed to load resource: the server responded with a status of ${status} (`;
      match = (rec) => {
        if (!rec.text.startsWith(prefix)) return false;
        try {
          return new URL(rec.url).pathname === urlPath;
        } catch {
          return false;
        }
      };
    }

    if (seenKeys.has(key)) {
      throw new Error(`CONSOLE_GATE: duplicate expectError "${key}"`);
    }
    seenKeys.add(key);
    expectations.push({ key, count, match });
  }

  function assertClean(): void {
    const app = errors.filter((rec) => !isIgnored(rec));
    const consumed = new Array(app.length).fill(false);

    for (const exp of expectations) {
      const idxs: number[] = [];
      for (let i = 0; i < app.length; i++) {
        if (consumed[i]) continue;
        if (exp.match(app[i]!)) idxs.push(i);
      }
      const matched = idxs.length;
      if (matched !== exp.count) {
        // Clear so a subsequent teardown assertClean does not re-throw after
        // a deliberate rejects.toThrow check in the test body.
        errors.length = 0;
        expectations.length = 0;
        seenKeys.clear();
        throw new Error(
          `CONSOLE_GATE: expected error "${exp.key}" x${exp.count}, got ${matched}`,
        );
      }
      for (const i of idxs) consumed[i] = true;
    }

    const unconsumed = app.filter((_, i) => !consumed[i]);
    // Clear after check so teardown is a no-op once the body (or teardown) ran.
    errors.length = 0;
    expectations.length = 0;
    seenKeys.clear();

    if (unconsumed.length > 0) {
      const first = unconsumed[0]!;
      throw new Error(
        `CONSOLE_GATE: expected 0 app errors, got ${unconsumed.length}: ${first.text}`,
      );
    }
  }

  return {
    errors,
    expectError,
    assertClean,
    get consoleErrors() {
      return errors.filter((e) => !isIgnored(e)).map((e) => e.text);
    },
    get pageErrors() {
      // Only pageerror texts that are not ignored (EXTERNAL_HOSTS / exact Abort).
      return pageErrorTexts.filter((text) => {
        const rec = errors.find((e) => e.text === text);
        return !rec || !isIgnored(rec);
      });
    },
  };
}

export { isExternalHost };
