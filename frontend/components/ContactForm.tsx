"use client";

import { useState, type FormEvent } from "react";

import {
  CONTACT_FORM_FLAG_ENV,
  contactFormEnabled,
} from "@/lib/contactFormFlag";

export { CONTACT_FORM_FLAG_ENV, contactFormEnabled };

export const CONTACT_FORM_ID_ENV = "NEXT_PUBLIC_CONTACT_FORM_ID";
export const CONTACT_SOON = "Contact form coming soon";
export const CONTACT_USE_LINE = "We use your message only to reply to you.";
export const CONTACT_SENT = "Message sent.";
export const CONTACT_ERROR = "The message could not be sent. Try again.";
export const CONTACT_TOO_LONG = "Message must be 5,000 characters or fewer.";
export const CONTACT_MAX_CHARS = 5000;

/** Public form id. The destination address lives only in the form service. */
export function contactFormIdFromBuild(): string {
  return (process.env.NEXT_PUBLIC_CONTACT_FORM_ID ?? "").trim();
}

export function contactFormEndpoint(formId: string): string {
  return `https://formspree.io/f/${formId}`;
}

export default function ContactForm() {
  const buildId = contactFormIdFromBuild();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [honeypot, setHoneypot] = useState("");
  const [status, setStatus] = useState<"idle" | "sent" | "error">("idle");
  const [note, setNote] = useState("");

  const formId = contactFormEnabled() ? buildId : "";
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
