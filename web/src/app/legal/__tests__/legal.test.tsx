import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LEGAL_DOCUMENTS } from "@/lib/legal/documents";

import { jsonResponse } from "../../../../test/http";
import { GrievanceOfficer } from "../../grievance/GrievanceOfficer";
import LegalDocumentPage, { generateStaticParams } from "../[slug]/page";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("legal pages", () => {
  it("builds one page per document", () => {
    expect(generateStaticParams()).toEqual([
      { slug: "terms" },
      { slug: "privacy" },
      { slug: "community-rules" },
      { slug: "refunds" },
    ]);
  });

  it.each(LEGAL_DOCUMENTS.map((d) => [d.slug, d.title]))(
    "%s is clearly marked as a draft for lawyer review",
    async (slug, title) => {
      render(await LegalDocumentPage({ params: Promise.resolve({ slug }) }));
      expect(screen.getByRole("heading", { level: 1, name: title })).toBeVisible();
      expect(screen.getByRole("note")).toHaveTextContent("Draft for lawyer review.");
      const footer = within(screen.getByRole("navigation", { name: "Legal" }));
      expect(footer.getByRole("link", { name: "Grievance Officer" })).toHaveAttribute(
        "href",
        "/grievance",
      );
    },
  );

  it("the privacy policy explains each optional consent", async () => {
    render(await LegalDocumentPage({ params: Promise.resolve({ slug: "privacy" }) }));
    for (const heading of [/Location/, /Social accounts/, /Marketing/, /Your rights/]) {
      expect(screen.getByRole("heading", { level: 2, name: heading })).toBeVisible();
    }
  });
});

describe("GrievanceOfficer", () => {
  it("shows the officer's contact from the API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(200, {
          name: "A. Officer",
          email: "grievance@barterly.in",
          phone: "",
          address: "Bengaluru",
          hours: "Mon–Fri",
          acknowledge_hours: 24,
          resolve_days: 15,
        }),
      ),
    );
    render(<GrievanceOfficer />);
    expect(await screen.findByText("A. Officer")).toBeVisible();
    expect(screen.getByRole("link", { name: "grievance@barterly.in" })).toHaveAttribute(
      "href",
      "mailto:grievance@barterly.in",
    );
    expect(screen.getByText(/within 24 hours and resolve them within 15 days/)).toBeVisible();
  });
});
