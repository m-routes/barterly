/**
 * The public legal pages and the version of each text. When a text changes, bump its
 * version here AND in the API (PRIVACY_*_VERSION): sign-up and the consent page send the
 * version they showed, and the API refuses a version that isn't current.
 *
 * Every page is a DRAFT until a lawyer has reviewed it (see docs/privacy.md).
 */

export const LEGAL_VERSION = "2026-11-draft-1";

export type LegalSlug = "terms" | "privacy" | "community-rules" | "refunds";

export type LegalDocument = {
  slug: LegalSlug;
  title: string;
  version: string;
  summary: string;
};

export const LEGAL_DOCUMENTS: readonly LegalDocument[] = [
  {
    slug: "terms",
    title: "Terms of service",
    version: LEGAL_VERSION,
    summary: "The agreement between you and Barterly for using the platform.",
  },
  {
    slug: "privacy",
    title: "Privacy policy",
    version: LEGAL_VERSION,
    summary: "What personal data we collect, why, how long we keep it, and your rights.",
  },
  {
    slug: "community-rules",
    title: "Community rules",
    version: LEGAL_VERSION,
    summary: "How hosts and talent treat each other on and off the platform.",
  },
  {
    slug: "refunds",
    title: "Refund and cancellation policy",
    version: LEGAL_VERSION,
    summary: "When stipends held in escrow and plan fees are refunded.",
  },
];

export function legalDocument(slug: string): LegalDocument | undefined {
  return LEGAL_DOCUMENTS.find((doc) => doc.slug === slug);
}

export function legalPath(slug: LegalSlug): string {
  return `/legal/${slug}`;
}
