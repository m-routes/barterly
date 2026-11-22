import Link from "next/link";

import { LEGAL_DOCUMENTS, legalPath } from "@/lib/legal/documents";

/** Links to the legal pages and the grievance officer, on every public page. */
export function LegalFooter() {
  return (
    <footer className="legal-footer">
      <nav aria-label="Legal">
        <ul className="legal-footer__links">
          {LEGAL_DOCUMENTS.map((doc) => (
            <li key={doc.slug}>
              <Link href={legalPath(doc.slug)}>{doc.title}</Link>
            </li>
          ))}
          <li>
            <Link href="/grievance">Grievance Officer</Link>
          </li>
        </ul>
      </nav>
    </footer>
  );
}
