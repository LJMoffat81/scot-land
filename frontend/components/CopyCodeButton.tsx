"use client";

import { useState } from "react";

type CopyCodeButtonProps = {
  value: string;
  label?: string;
};

/** Copy a code-box value to the clipboard (API addresses on /developers). */
export default function CopyCodeButton({
  value,
  label = "Copy",
}: CopyCodeButtonProps) {
  const [done, setDone] = useState(false);

  async function onCopy() {
    try {
      await navigator.clipboard.writeText(value);
      setDone(true);
      window.setTimeout(() => setDone(false), 1500);
    } catch {
      setDone(false);
    }
  }

  return (
    <button
      type="button"
      className="copy-code-btn"
      onClick={() => void onCopy()}
      data-testid="copy-code-btn"
      aria-label={`${label} ${value}`}
    >
      {done ? "Copied" : label}
    </button>
  );
}
