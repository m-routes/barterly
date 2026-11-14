/** "12 Dec 2026" for a date ("2026-12-12") or a timestamp; "–" when there is none. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "–";
  const date = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso);
  return Number.isNaN(date.getTime())
    ? "–"
    : date.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}
