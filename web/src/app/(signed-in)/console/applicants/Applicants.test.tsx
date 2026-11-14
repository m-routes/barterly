import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { applicant, application, gig, page } from "../../../../../test/fixtures";
import { jsonResponse } from "../../../../../test/http";

import { ApplicantDetail } from "./ApplicantDetail";
import { ApplicantTable } from "./ApplicantTable";

const params = { gigId: gig.id, applicationId: application.id };
vi.mock("next/navigation", () => ({ useParams: () => params }));

let network: ReturnType<typeof vi.fn>;

beforeEach(() => {
  network = vi.fn((request: Request) => {
    const path = new URL(request.url).pathname;
    if (path === `/api/v1/gigs/${gig.id}/`)
      return Promise.resolve(jsonResponse(200, { ...gig, status: "live" }));
    if (path === `/api/v1/gigs/${gig.id}/applications/`) {
      return Promise.resolve(
        jsonResponse(
          200,
          page([applicant(), applicant({ id: "a2", fit: { score: 61, breakdown: {} } })]),
        ),
      );
    }
    if (path === `/api/v1/applications/${application.id}/`) {
      return Promise.resolve(jsonResponse(200, application));
    }
    return Promise.resolve(jsonResponse(404, { code: "not_found", message: "No.", details: {} }));
  });
  vi.stubGlobal("fetch", network);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function applicationQueries() {
  return network.mock.calls
    .map((c) => new URL((c[0] as Request).url))
    .filter((u) => u.pathname.endsWith("/applications/"))
    .map((u) => u.searchParams);
}

describe("ApplicantTable", () => {
  it("shows applicants best fit first with status and badges", async () => {
    render(<ApplicantTable />);
    const rows = await screen.findAllByRole("row");
    expect(rows).toHaveLength(3);
    const first = within(rows[1]!);
    expect(first.getByText("Aarav Mehta", { selector: ".table__title" })).toBeVisible();
    expect(first.getByText("92%")).toBeVisible();
    expect(first.getByText("Applied")).toBeVisible();
    expect(first.getByText("ID verified")).toBeVisible();
    expect(first.getByRole("link", { name: /View Aarav Mehta/ })).toHaveAttribute(
      "href",
      `/console/applicants/${applicant().id}`,
    );
    expect(await screen.findByRole("heading", { level: 1, name: gig.title })).toBeVisible();
    expect(applicationQueries()[0]!.get("sort")).toBe("fit");
  });

  it("sends the filters and sort to the API", async () => {
    const user = userEvent.setup();
    render(<ApplicantTable />);
    await screen.findAllByRole("row");
    await user.selectOptions(screen.getByLabelText("Status"), "shortlisted");
    await user.selectOptions(screen.getByLabelText("Fit"), "70");
    await user.selectOptions(screen.getByLabelText("Sort by"), "newest");
    await screen.findAllByRole("row");
    const query = applicationQueries().at(-1)!;
    expect(query.get("status")).toBe("shortlisted");
    expect(query.get("min_score")).toBe("70");
    expect(query.get("sort")).toBe("newest");
  });
});

describe("ApplicantDetail", () => {
  it("shows the pitch, answers, fit reasons and files, and no contact details", async () => {
    render(<ApplicantDetail />);
    expect(await screen.findByRole("heading", { level: 1, name: "Aarav Mehta" })).toBeVisible();
    expect(screen.getByText(application.pitch)).toBeVisible();
    expect(screen.getByText("Can you commit to the full dates?")).toBeVisible();
    expect(screen.getByText("1 of 1 skills match.")).toBeVisible();
    expect(screen.getByText("Not enough data yet.")).toBeVisible();
    expect(screen.getByRole("link", { name: "https://example.org/portfolio" })).toHaveAttribute(
      "rel",
      "noopener noreferrer",
    );
    expect(screen.getByText(/Contact details are shared once you book/)).toBeVisible();
    expect(document.body.textContent).not.toMatch(/\+91|@|phone/i);
  });
});
