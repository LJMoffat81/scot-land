"use client";

import { useEffect, useState } from "react";

import { contactFormEnabled } from "@/lib/contactFormFlag";

export const SUGGEST_LAYER_COPY =
  "Know a dataset that would make this map better? Tell us what the layer is, where the data comes from (a link), and why it matters for land value. We check every suggestion against its licence and our method before adding it.";

export const SUGGEST_LAYER_HREF = "/about?topic=layer#contact";

/**
 * SW-082: only mount the suggest section when the contact form flag is on.
 * E2E builds may force the flag via window.__E2E_CONTACT_FORM_ENABLED__.
 */
export default function SuggestLayerSection() {
  const buildEnabled = contactFormEnabled();
  const [enabled, setEnabled] = useState(buildEnabled);

  useEffect(() => {
    if (process.env.NEXT_PUBLIC_E2E_HOOKS !== "1") return;
    const override = (
      window as Window & { __E2E_CONTACT_FORM_ENABLED__?: boolean }
    ).__E2E_CONTACT_FORM_ENABLED__;
    if (typeof override === "boolean") {
      setEnabled(override);
    }
  }, []);

  if (!enabled) return null;

  return (
    <section id="suggest-a-layer" data-testid="roadmap-suggest-layer">
      <h2>Suggest a layer</h2>
      <p>{SUGGEST_LAYER_COPY}</p>
      <p>
        <a href={SUGGEST_LAYER_HREF}>Suggest a layer</a>
      </p>
    </section>
  );
}
