import { redirect } from "next/navigation";

/** Fallback if middleware is bypassed. Canonical redirect: middleware.ts (307). */
export default function DownloadsRedirectPage() {
  redirect("/developers?moved=1#downloads");
}
