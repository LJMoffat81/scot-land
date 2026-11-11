"use client";

import { useEffect, useRef } from "react";
import type { ApiErrorKind } from "../lib/api";

/**
 * Reusable retry surface for a failed load.
 * Next users: MAP-LOAD-FAIL-STATE-1 and LAYERS-EMPTY-STATE-1.
 * Do not wire this component into those flows from LOOKUP-DEADLINES-1.
 */
export const RETRY_STATE_GENERIC_COPY = "This didn't load just now.";

export type RetryStateProps = {
  message: string;
  retryLabel: string;
  onRetry: () => void;
  busy?: boolean;
  kind?: ApiErrorKind | null;
  testIdPrefix: string;
  autoFocus?: boolean;
  className?: string;
  lineClassName?: string;
  buttonClassName?: string;
  buttonTestId?: string;
};

function joinClass(parts: Array<string | undefined>): string {
  return parts.filter((part) => Boolean(part)).join(" ");
}

/** Message and retry control only. Never raw error text or a status code. */
export default function RetryState({
  message,
  retryLabel,
  onRetry,
  busy = false,
  kind = null,
  testIdPrefix,
  autoFocus = false,
  className,
  lineClassName,
  buttonClassName,
  buttonTestId,
}: RetryStateProps) {
  const buttonRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!autoFocus) return;
    buttonRef.current?.focus();
  }, [autoFocus]);

  return (
    <div
      className={joinClass(["retry-state", className])}
      data-testid={`${testIdPrefix}-retry-state`}
      data-error-kind={kind ?? "unknown"}
    >
      <p
        className={joinClass(["retry-state-line", lineClassName])}
        role="status"
        aria-live="polite"
      >
        {message}
      </p>
      <button
        ref={buttonRef}
        type="button"
        className={joinClass(["retry-state-button", buttonClassName])}
        data-testid={buttonTestId}
        aria-busy={busy ? "true" : "false"}
        disabled={busy}
        onClick={onRetry}
      >
        {retryLabel}
      </button>
    </div>
  );
}
