import { redirect } from "next/navigation";

/** Permanent redirect — also declared in next.config.ts. */
export default function MissionRedirectPage() {
  redirect("/about");
}
