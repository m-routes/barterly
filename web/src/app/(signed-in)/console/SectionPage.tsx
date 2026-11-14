import { EmptyState } from "@/components/ui/states";

import { sectionFor } from "./nav";

/** A console section that isn't built yet: its heading and an empty state. */
export function SectionPage({ href }: { href: string }) {
  const section = sectionFor(href);
  return (
    <div className="page">
      <header className="page__header">
        <h1 className="page__title">{section.label}</h1>
      </header>
      <EmptyState title={section.empty.title} description={section.empty.description} />
    </div>
  );
}
