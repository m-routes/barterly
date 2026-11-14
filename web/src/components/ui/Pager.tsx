import { Button } from "./Button";

/** Previous / next for page-numbered lists. Hidden when everything fits on one page. */
export function Pager({
  page,
  count,
  pageSize,
  onPage,
  label,
}: {
  page: number;
  count: number;
  pageSize: number;
  onPage: (page: number) => void;
  label: string;
}) {
  const pages = Math.max(1, Math.ceil(count / pageSize));
  if (pages === 1) return null;
  return (
    <nav className="pager" aria-label={label}>
      <Button variant="secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        Previous
      </Button>
      <span>
        Page {page} of {pages}
      </span>
      <Button variant="secondary" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        Next
      </Button>
    </nav>
  );
}
