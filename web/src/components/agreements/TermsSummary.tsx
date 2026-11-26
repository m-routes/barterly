import type { Terms } from "@/lib/api/types";
import { rowChanged, termRows } from "@/lib/agreements/terms";

/** The terms as a list; rows in `changed` are marked so a counter or change stands out. */
export function TermsSummary({
  terms,
  changed = [],
}: {
  terms: Terms;
  changed?: readonly string[];
}) {
  return (
    <dl className="summary terms">
      {termRows(terms).map(([field, label, value]) => {
        const isChanged = rowChanged(field, changed);
        return (
          <div key={field} className={isChanged ? "terms__row terms__row--changed" : "terms__row"}>
            <dt>
              {label}
              {isChanged ? <span className="terms__badge">Changed</span> : null}
            </dt>
            <dd>{value}</dd>
          </div>
        );
      })}
    </dl>
  );
}
