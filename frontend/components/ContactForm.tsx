"use client";

import { useEffect, useState, type FormEvent, Suspense } from "react";
import { useSearchParams } from "next/navigation";

import {
  CONTACT_FORM_FLAG_ENV,
  contactFormEnabled,
} from "@/lib/contactFormFlag";

export { CONTACT_FORM_FLAG_ENV, contactFormEnabled };

export const CONTACT_FORM_ID_ENV = "NEXT_PUBLIC_CONTACT_FORM_ID";
export const CONTACT_SOON = "Contact form not open yet. Please check back.";
export const CONTACT_USE_LINE = "We use your message only to reply to you.";
export const CONTACT_SENT = "Message sent.";
export const CONTACT_ERROR = "The message could not be sent. Try again.";
export const CONTACT_TOO_LONG = "Message must be 5,000 characters or fewer.";
export const CONTACT_MAX_CHARS = 5000;

/** Prefill when /about?topic=layer#contact is opened from the roadmap. */
export const LAYER_SUGGESTION_PREFIX = "Layer suggestion: ";

/** Public form id. The destination address lives only in the form service. */
export function contactFormIdFromBuild(): string {
  return (process.env.NEXT_PUBLIC_CONTACT_FORM_ID ?? "").trim();
}

export function contactFormEndpoint(formId: string): string {
  return `https://formspree.io/f/${formId}`;
}

type E2eContactOverride = {
  enabled?: boolean;
  formId?: string;
};

function readE2eContactOverride(): E2eContactOverride {
  if (typeof window === "undefined") return {};
  // Production builds leave NEXT_PUBLIC_E2E_HOOKS unset so this block is dropped.
  // Use __E2E_* names only — never __SC_CONTACT_FORM_ID (banned in visitor bundles).
  if (process.env.NEXT_PUBLIC_E2E_HOOKS !== "1") return {};
  const w = window as Window & {
    __E2E_CONTACT_FORM_ENABLED__?: boolean;
    __E2E_CONTACT_FORM_ID__?: string;
  };
  const out: E2eContactOverride = {};
  if (typeof w.__E2E_CONTACT_FORM_ENABLED__ === "boolean") {
    out.enabled = w.__E2E_CONTACT_FORM_ENABLED__;
  }
  if (
    typeof w.__E2E_CONTACT_FORM_ID__ === "string" &&
    w.__E2E_CONTACT_FORM_ID__.trim()
  ) {
    out.formId = w.__E2E_CONTACT_FORM_ID__.trim();
  }
  return out;
}

function ContactFormInner() {
  const searchParams = useSearchParams();
  const [e2e, setE2e] = useState<E2eContactOverride>({});
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [honeypot, setHoneypot] = useState("");
  const [status, setStatus] = useState<"idle" | "sent" | "error">("idle");
  const [note, setNote] = useState("");
  const [topicPrefillDone, setTopicPrefillDone] = useState(false);

  useEffect(() => {
    setE2e(readE2eContactOverride());
  }, []);

  useEffect(() => {
    if (topicPrefillDone) return;
    if (searchParams.get("topic") !== "layer") return;
    setMessage(LAYER_SUGGESTION_PREFIX);
    setTopicPrefillDone(true);
  }, [searchParams, topicPrefillDone]);

  const formEnabled = e2e.enabled ?? contactFormEnabled();
  const buildId = e2e.formId ?? contactFormIdFromBuild();
  const formId = formEnabled ? buildId : "";
  if (!formId) {
    return (
      <p data-testid="contact-form-soon">{CONTACT_SOON}</p>
    );
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNote("");
    if (message.length > CONTACT_MAX_CHARS) {
      setStatus("error");
      setNote(CONTACT_TOO_LONG);
      return;
    }
    if (honeypot.trim()) {
      setStatus("sent");
      setNote(CONTACT_SENT);
      return;
    }
    try {
      const response = await fetch(contactFormEndpoint(formId), {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name,
          email,
          message,
        }),
      });
      if (!response.ok) {
        setStatus("error");
        setNote(CONTACT_ERROR);
        return;
      }
      setStatus("sent");
      setNote(CONTACT_SENT);
      setName("");
      setEmail("");
      setMessage("");
    } catch {
      setStatus("error");
      setNote(CONTACT_ERROR);
    }
  }

  return (
    <form
      className="contact-form"
      data-testid="contact-form"
      action={contactFormEndpoint(formId)}
      method="post"
      onSubmit={onSubmit}
    >
      <p className="contact-form-use">{CONTACT_USE_LINE}</p>
      <label>
        Name (optional)
        <input
          name="name"
          type="text"
          autoComplete="name"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      <label>
        Email
        <input
          name="email"
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
      </label>
      <label>
        Message
        <textarea
          name="message"
          required
          maxLength={CONTACT_MAX_CHARS}
          value={message}
          onChange={(event) => setMessage(event.target.value)}
        />
      </label>
      <input
        className="contact-honeypot"
        type="text"
        name="company"
        tabIndex={-1}
        autoComplete="off"
        aria-hidden="true"
        data-testid="contact-honeypot"
        value={honeypot}
        onChange={(event) => setHoneypot(event.target.value)}
      />
      <button type="submit">Send</button>
      {note ? (
        <p data-testid="contact-form-status" role="status">
          {status === "error" ? note : note}
        </p>
      ) : null}
    </form>
  );
}

export default function ContactForm() {
  return (
    <Suspense
      fallback={<p data-testid="contact-form-soon">{CONTACT_SOON}</p>}
    >
      <ContactFormInner />
    </Suspense>
  );
}
