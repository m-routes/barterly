import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { LegalPage } from "@/components/legal/LegalPage";
import { LEGAL_DOCUMENTS, legalDocument } from "@/lib/legal/documents";

import { LEGAL_CONTENT } from "../content";

export function generateStaticParams() {
  return LEGAL_DOCUMENTS.map((doc) => ({ slug: doc.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const doc = legalDocument((await params).slug);
  return { title: doc ? `${doc.title} (draft) · Barterly` : "Barterly" };
}

export default async function LegalDocumentPage({ params }: { params: Promise<{ slug: string }> }) {
  const doc = legalDocument((await params).slug);
  if (!doc) notFound();
  const Content = LEGAL_CONTENT[doc.slug];
  return (
    <LegalPage title={doc.title} version={doc.version}>
      <Content />
    </LegalPage>
  );
}
