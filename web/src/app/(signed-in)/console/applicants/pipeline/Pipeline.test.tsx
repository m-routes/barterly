import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { onApiEvent } from "@/lib/api/events";
import type { PipelineApplicant } from "@/lib/vendor/pipeline";

import { applicant, application, gig, offerThread, page } from "../../../../../../test/fixtures";
import { errorBody, jsonResponse } from "../../../../../../test/http";

import { Pipeline } from "./Pipeline";

vi.mock("next/navigation", () => ({
  useParams: () => ({ gigId: gig.id }),
  useRouter: () => ({ push: vi.fn() }),
}));
vi.mock("@/components/chat/ChatThread", () => ({
  ChatThread: ({ conversationId }: { conversationId: string }) => (
    <p>Chat thread {conversationId}</p>
  ),
}));

const card = (
  id: string,
  name: string,
  status: PipelineApplicant["status"],
  extra: Partial<PipelineApplicant> = {},
): PipelineApplicant =>
  ({
    ...applicant({ id, status }),
    applicant: { ...applicant().applicant, display_name: name },
    rejection_code: "",
    tags: [],
    note_count: 0,
    ...extra,
  }) as PipelineApplicant;

let board: PipelineApplicant[];
let network: ReturnType<typeof vi.fn>;
let respond: Record<string, (request: Request) => Response | Promise<Response>>;
let notices: string[];
let stopListening: () => void;

function calls(method: string, suffix: string) {
  return network.mock.calls
    .map((c) => c[0] as Request)
    .filter((r) => r.method === method && new URL(r.url).pathname.endsWith(suffix));
}

function lastQuery() {
  const lists = calls("GET", `/gigs/${gig.id}/applications/`);
  return new URL(lists.at(-1)!.url).searchParams;
}

function column(name: string) {
  return screen.getByRole("heading", { level: 2, name }).closest("section")!;
}

beforeEach(() => {
  board = [
    card("a1", "Aarav Mehta", "applied", {
      fit: { score: 92, breakdown: {} },
      tags: ["call back"],
    }),
    card("a2", "Meera Sood", "applied", {
      applicant: { ...applicant().applicant, display_name: "Meera Sood", badges: [] },
    }),
    card("a3", "Tanya Dogra", "shortlisted", { note_count: 2 }),
    card("a4", "Nisha Patil", "interview"),
    card("a5", "Ishita Verma", "offered"),
  ];
  respond = {};
  notices = [];
  network = vi.fn(async (request: Request) => {
    const url = new URL(request.url);
    const key = `${request.method} ${url.pathname}`;
    if (respond[key]) return respond[key](request);
    if (key === `GET /api/v1/gigs/${gig.id}/`) return jsonResponse(200, { ...gig, status: "live" });
    if (key === `GET /api/v1/gigs/${gig.id}/applications/`) return jsonResponse(200, page(board));
    if (key === "GET /api/v1/applicant-filters/") return jsonResponse(200, []);
    if (key === "GET /api/v1/hiring/rejection-reasons/") {
      return jsonResponse(200, [
        { code: "not_a_fit", label: "Not the right fit", text: "We went another way." },
        { code: "dates", label: "Dates don't work", text: "The dates don't line up." },
      ]);
    }
    if (url.pathname.endsWith("/status/")) return jsonResponse(200, application);
    if (key === `POST /api/v1/gigs/${gig.id}/applications/bulk/`) {
      const body = (await request.clone().json()) as { application_ids: string[] };
      return jsonResponse(
        200,
        body.application_ids.map((id) => ({ id, ok: true, status: "", error: "" })),
      );
    }
    if (url.pathname === `/api/v1/applications/a1/`) {
      return jsonResponse(200, {
        ...application,
        id: "a1",
        notes: [],
        tags: ["call back"],
        rejection_code: "",
      });
    }
    if (url.pathname === `/api/v1/applications/a1/offers/`) return jsonResponse(200, offerThread());
    return jsonResponse(404, errorBody("not_found"));
  });
  vi.stubGlobal("fetch", network);
  stopListening = onApiEvent((e) => {
    if (e.type === "notice") notices.push(e.message);
  });
});

afterEach(() => {
  stopListening();
  vi.unstubAllGlobals();
});

describe("Pipeline board", () => {
  it("shows the four columns from the canvas with each applicant where they are", async () => {
    render(<Pipeline />);
    await screen.findByRole("article", { name: "Aarav Mehta" });
    expect(within(column("Applied")).getAllByRole("article")).toHaveLength(2);
    expect(
      within(column("Shortlisted")).getByRole("article", { name: "Tanya Dogra" }),
    ).toBeVisible();
    expect(within(column("Interview")).getByRole("article", { name: "Nisha Patil" })).toBeVisible();
    expect(within(column("Offered")).getByRole("article", { name: "Ishita Verma" })).toBeVisible();
    const aarav = within(column("Applied")).getAllByRole("article")[0]!;
    expect(within(aarav).getByText("92 fit")).toBeVisible();
    expect(within(aarav).getByText("ID verified")).toBeVisible();
    expect(within(aarav).getByText("call back")).toBeVisible();
    expect(within(column("Shortlisted")).getByText("2 notes")).toBeVisible();
  });

  it("moves a card at once, then keeps it there when the server agrees", async () => {
    const user = userEvent.setup();
    let release!: () => void;
    respond["POST /api/v1/applications/a1/status/"] = () =>
      new Promise((resolve) => {
        release = () => resolve(jsonResponse(200, application));
      });
    render(<Pipeline />);
    await user.click(await screen.findByRole("button", { name: "Shortlist Aarav Mehta" }));
    // Moved before the server answered.
    expect(
      within(column("Shortlisted")).getByRole("article", { name: "Aarav Mehta" }),
    ).toBeVisible();
    expect(await calls("POST", "/a1/status/")[0]!.json()).toEqual({ status: "shortlisted" });
    await act(async () => release());
    expect(
      within(column("Shortlisted")).getByRole("article", { name: "Aarav Mehta" }),
    ).toBeVisible();
  });

  it("puts the card back and says why when the server refuses", async () => {
    const user = userEvent.setup();
    respond["POST /api/v1/applications/a1/status/"] = () =>
      jsonResponse(409, errorBody("transition_refused", "The gig is paused."));
    render(<Pipeline />);
    await user.click(await screen.findByRole("button", { name: "Shortlist Aarav Mehta" }));
    await vi.waitFor(() =>
      expect(within(column("Applied")).getByRole("article", { name: "Aarav Mehta" })).toBeVisible(),
    );
    expect(notices[0]).toMatch(
      /Couldn't move Aarav Mehta to Shortlisted: The gig is paused\..*back in Applied/,
    );
    expect(screen.getByRole("status")).toHaveTextContent(/back in Applied/);
  });

  it("moves with the keyboard: pick up, choose a column, drop", async () => {
    const user = userEvent.setup();
    render(<Pipeline />);
    const handle = await screen.findByRole("button", {
      name: "Move Aarav Mehta with the keyboard",
    });
    handle.focus();
    await user.keyboard(" ");
    expect(handle).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("status")).toHaveTextContent(/Picked up Aarav Mehta.*Over Shortlisted/);
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("status")).toHaveTextContent("Over Interview.");
    await user.keyboard("{Enter}");
    expect(within(column("Interview")).getByRole("article", { name: "Aarav Mehta" })).toBeVisible();
    expect(await calls("POST", "/a1/status/")[0]!.json()).toEqual({ status: "interview" });
  });

  it("cancels a keyboard move with Escape", async () => {
    const user = userEvent.setup();
    render(<Pipeline />);
    const handle = await screen.findByRole("button", { name: "Move Meera Sood with the keyboard" });
    handle.focus();
    await user.keyboard(" {ArrowRight}{Escape}");
    expect(screen.getByRole("status")).toHaveTextContent("Cancelled. Meera Sood stays in Applied.");
    expect(calls("POST", "/status/")).toHaveLength(0);
  });

  it("moves with drag and drop, and refuses columns behind it", async () => {
    render(<Pipeline />);
    await screen.findByRole("article", { name: "Tanya Dogra" });
    const tanya = within(column("Shortlisted")).getByRole("article");
    const data = { setData: vi.fn(), getData: () => "a3", dropEffect: "", effectAllowed: "" };
    fireEvent.dragStart(tanya, { dataTransfer: data });
    expect(column("Interview")).toHaveClass("board__column--target");
    expect(column("Applied")).not.toHaveClass("board__column--target");
    fireEvent.dragOver(column("Interview"), { dataTransfer: data });
    fireEvent.drop(column("Interview"), { dataTransfer: data });
    expect(within(column("Interview")).getByRole("article", { name: "Tanya Dogra" })).toBeVisible();
    await vi.waitFor(() => expect(calls("POST", "/a3/status/")).toHaveLength(1));
  });

  it("has a Move to menu as the button alternative", async () => {
    const user = userEvent.setup();
    render(<Pipeline />);
    await user.selectOptions(await screen.findByLabelText("Move Meera Sood to"), "interview");
    expect(within(column("Interview")).getByRole("article", { name: "Meera Sood" })).toBeVisible();
  });

  it("opens the offer builder instead of moving a card to Offered", async () => {
    const user = userEvent.setup();
    render(<Pipeline />);
    await user.selectOptions(await screen.findByLabelText("Move Aarav Mehta to"), "offered");
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("tab", { name: "Offer" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(within(column("Applied")).getByRole("article", { name: "Aarav Mehta" })).toBeVisible();
  });
});

describe("Bulk actions", () => {
  it("shortlists the selected applicants, putting back any the server refused", async () => {
    const user = userEvent.setup();
    respond[`POST /api/v1/gigs/${gig.id}/applications/bulk/`] = () =>
      jsonResponse(200, [
        { id: "a1", ok: true, status: "shortlisted", error: "" },
        { id: "a2", ok: false, status: "", error: "Gig paused" },
      ]);
    render(<Pipeline />);
    await user.click(await screen.findByRole("checkbox", { name: "Select Aarav Mehta" }));
    await user.click(screen.getByRole("checkbox", { name: "Select Meera Sood" }));
    const bar = screen.getByRole("region", { name: "Bulk actions" });
    expect(bar).toHaveTextContent("2 selected");
    await user.click(within(bar).getByRole("button", { name: "Shortlist" }));
    expect(await calls("POST", "/applications/bulk/")[0]!.json()).toEqual({
      action: "shortlist",
      application_ids: ["a1", "a2"],
    });
    await vi.waitFor(() =>
      expect(within(column("Applied")).getByRole("article", { name: "Meera Sood" })).toBeVisible(),
    );
    expect(
      within(column("Shortlisted")).getByRole("article", { name: "Aarav Mehta" }),
    ).toBeVisible();
    expect(notices).toEqual(["1 of 2 couldn't be changed and were put back."]);
  });

  it("rejects with a reason from the list", async () => {
    const user = userEvent.setup();
    render(<Pipeline />);
    await user.click(await screen.findByRole("button", { name: "Reject Meera Sood" }));
    const dialog = await screen.findByRole("dialog", { name: "Reject Meera Sood" });
    const reject = within(dialog).getByRole("button", { name: "Reject" });
    expect(reject).toBeDisabled();
    await user.selectOptions(await within(dialog).findByLabelText("Reason"), "dates");
    expect(within(dialog).getByText(/The dates don't line up/)).toBeVisible();
    await user.click(reject);
    expect(screen.queryByRole("article", { name: "Meera Sood" })).toBeNull();
    expect(await calls("POST", "/applications/bulk/")[0]!.json()).toEqual({
      action: "reject",
      application_ids: ["a2"],
      reason_code: "dates",
    });
  });
});

describe("Filters", () => {
  it("sends the filters, and saves and reapplies them", async () => {
    const user = userEvent.setup();
    let saved: object[] = [];
    respond["GET /api/v1/applicant-filters/"] = () => jsonResponse(200, saved);
    respond["POST /api/v1/applicant-filters/"] = async (r) => {
      const body = (await r.clone().json()) as { name: string; params: object };
      const created = { id: "f1", gig: gig.id, created_at: "2026-11-16T10:00:00Z", ...body };
      saved = [created];
      return jsonResponse(201, created);
    };
    render(<Pipeline />);
    await screen.findByRole("article", { name: "Aarav Mehta" });
    await user.click(screen.getByLabelText("ID verified only"));
    await vi.waitFor(() => expect(lastQuery().get("badge")).toBe("id_verified"));
    await user.selectOptions(screen.getByLabelText("Fit"), "70");
    await user.type(screen.getByLabelText("Search applicants"), "aar");
    await vi.waitFor(() => expect(lastQuery().get("q")).toBe("aar"), { timeout: 2000 });
    expect(lastQuery().get("min_score")).toBe("70");
    expect(lastQuery().get("status")).toBe("applied,shortlisted,interview,offered");

    await user.click(screen.getByRole("button", { name: "Save these filters" }));
    await user.type(screen.getByLabelText("Name this filter"), "Strong and verified");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await calls("POST", "/applicant-filters/")[0]!.json()).toEqual({
      name: "Strong and verified",
      gig: gig.id,
      params: { sort: "fit", badge: "id_verified", min_score: 70, q: "aar" },
    });
    expect(
      await screen.findByRole("button", { name: "Delete “Strong and verified”" }),
    ).toBeVisible();
  });
});

describe("Applicant drawer", () => {
  async function openAarav(user: ReturnType<typeof userEvent.setup>) {
    render(<Pipeline />);
    await user.click(await screen.findByRole("button", { name: "Aarav Mehta" }));
    return screen.findByRole("dialog");
  }

  it("is a dialog with keyboard tabs that closes on Escape and gives focus back", async () => {
    const user = userEvent.setup();
    const dialog = await openAarav(user);
    expect(await within(dialog).findByRole("heading", { name: "Pitch" })).toBeVisible();
    const profile = within(dialog).getByRole("tab", { name: "Profile" });
    profile.focus();
    await user.keyboard("{ArrowRight}");
    expect(within(dialog).getByRole("tab", { name: "Notes and tags" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("button", { name: "Aarav Mehta" })).toHaveFocus();
  });

  it("adds a note at once and takes it back if saving fails", async () => {
    const user = userEvent.setup();
    respond["POST /api/v1/applications/a1/notes/"] = () =>
      jsonResponse(400, errorBody("validation_error", "Too long."));
    const dialog = await openAarav(user);
    await user.click(await within(dialog).findByRole("tab", { name: "Notes and tags" }));
    await user.type(within(dialog).getByLabelText(/New note/), "Great energy");
    await user.click(within(dialog).getByRole("button", { name: "Add note" }));
    await vi.waitFor(() => expect(notices[0]).toMatch(/Couldn't save the note/));
    expect(within(dialog).getByText("No notes yet.")).toBeVisible();
    expect(within(dialog).getByLabelText(/New note/)).toHaveValue("Great energy");
  });

  it("saves tags", async () => {
    const user = userEvent.setup();
    respond["PUT /api/v1/applications/a1/tags/"] = async (r) =>
      jsonResponse(200, await r.clone().json());
    const dialog = await openAarav(user);
    await user.click(await within(dialog).findByRole("tab", { name: "Notes and tags" }));
    await user.type(within(dialog).getByLabelText("Add a tag"), "Night Shift");
    await user.click(within(dialog).getByRole("button", { name: "Add" }));
    expect(await calls("PUT", "/a1/tags/")[0]!.json()).toEqual({
      tags: ["call back", "night shift"],
    });
    await user.click(within(dialog).getByRole("button", { name: "Remove tag call back" }));
    expect(await calls("PUT", "/a1/tags/")[1]!.json()).toEqual({ tags: ["night shift"] });
  });

  it("proposes interview times", async () => {
    const user = userEvent.setup();
    respond["GET /api/v1/applications/a1/interview/"] = () =>
      jsonResponse(404, errorBody("not_found"));
    respond["POST /api/v1/applications/a1/interview/"] = () =>
      jsonResponse(201, {
        id: "i1",
        status: "proposed",
        slots: [{ id: 1, starts_at: "2026-11-20T10:30:00Z", starts_at_ist: "Fri 20 Nov, 4:00 pm" }],
        starts_at: null,
        starts_at_ist: "",
        duration_minutes: 30,
        video_link: "",
        note: "",
        timezone: "Asia/Kolkata",
        created_at: "2026-11-16T10:00:00Z",
      });
    const dialog = await openAarav(user);
    await user.click(await within(dialog).findByRole("tab", { name: "Interview" }));
    await user.click(await within(dialog).findByRole("button", { name: "Propose times" }));
    fireEvent.change(within(dialog).getByLabelText("Time 1"), {
      target: { value: "2026-11-20T16:00" },
    });
    await user.type(
      within(dialog).getByLabelText("Video call link"),
      "https://meet.google.com/abc",
    );
    await user.click(within(dialog).getByRole("button", { name: "Send times" }));
    expect(await calls("POST", "/a1/interview/")[0]!.json()).toEqual({
      slots: ["2026-11-20T16:00"],
      video_link: "https://meet.google.com/abc",
      duration_minutes: 30,
      note: "",
    });
    expect(await within(dialog).findByText("Fri 20 Nov, 4:00 pm")).toBeVisible();
    expect(within(dialog).getByText("Waiting for them to pick a time")).toBeVisible();
  });

  it("opens the chat inside the drawer", async () => {
    const user = userEvent.setup();
    respond["POST /api/v1/applications/a1/conversation/"] = () => jsonResponse(200, { id: "c9" });
    const dialog = await openAarav(user);
    await user.click(await within(dialog).findByRole("tab", { name: "Chat" }));
    expect(await within(dialog).findByText("Chat thread c9")).toBeVisible();
  });
});
