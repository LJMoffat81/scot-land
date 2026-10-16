/** CONTACT-FORM-1: off until a public form id is supplied. */
export const CONTACT_FORM_FLAG_ENV = "NEXT_PUBLIC_CONTACT_FORM_ENABLED";

/** Default off. Only the exact string "true" turns contact links and the form on. */
export function contactFormEnabled(): boolean {
  return process.env.NEXT_PUBLIC_CONTACT_FORM_ENABLED === "true";
}
