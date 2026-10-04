/** Add the live commit to a CSV export link so each deploy gets a new cache key. */
export function withExportVersion(href: string, commit: string | null): string {
  const path = href.split("?")[0];
  if (!path.endsWith(".csv") || !commit) return href;
  const join = href.includes("?") ? "&" : "?";
  return `${href}${join}v=${encodeURIComponent(commit)}`;
}
