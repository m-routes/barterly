import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  ChatMessage,
  ChatTransport,
  ConversationDetail,
  Subscription,
} from "@/lib/chat/transport";

import { jsonResponse } from "../../../test/http";

import { ChatThread } from "./ChatThread";

const conversation: ConversationDetail = {
  id: "c1",
  application: "a1",
  gig_title: "Front desk in Goa",
  application_status: "shortlisted",
  other: { id: "u2", name: "Aarav Mehta", role: "talent" },
  unread: 0,
  last_message: null,
  last_message_at: null,
  opened_at: "2026-11-15T09:00:00Z",
  can_send: true,
  cant_send_reason: "",
  contact_sharing_allowed: false,
  blocked_by_me: false,
};

const msg = (cursor: string, overrides: Partial<ChatMessage> = {}): ChatMessage => ({
  id: `m${cursor}`,
  cursor,
  sender: "u2",
  mine: false,
  body: `Message ${cursor}`,
  masked: false,
  attachments: [],
  client_id: "",
  read_at: null,
  created_at: "2026-11-15T10:00:00Z",
  ...overrides,
});

function fakeTransport() {
  let subscription: Subscription | undefined;
  const transport = {
    history: vi.fn<ChatTransport["history"]>(() =>
      Promise.resolve({
        messages: [msg("1"), msg("2", { mine: true, sender: "me", body: "Hi from me" })],
        cursor: "2",
        otherReadUpTo: "2",
        hasEarlier: false,
      }),
    ),
    subscribe: vi.fn<ChatTransport["subscribe"]>((_id, _cursor, s) => {
      subscription = s;
      return () => (subscription = undefined);
    }),
    send: vi.fn<ChatTransport["send"]>((_id, draft) =>
      Promise.resolve({
        message: msg("3", {
          mine: true,
          body: "[hidden] me",
          masked: true,
          client_id: draft.clientId,
        }),
        notice:
          "We hid a phone number. Contact details can be shared once the booking is confirmed.",
      }),
    ),
    markRead: vi.fn<ChatTransport["markRead"]>(() => Promise.resolve()),
  };
  return {
    transport,
    push: (messages: ChatMessage[], cursor: string) =>
      subscription?.onMessages({ messages, cursor, otherReadUpTo: "2" }),
    subscribed: () => !!subscription,
  };
}

let network: ReturnType<typeof vi.fn>;
let detail: ConversationDetail;

beforeEach(() => {
  detail = { ...conversation };
  network = vi.fn((request: Request) => {
    const url = new URL(request.url);
    if (url.pathname === "/api/v1/conversations/c1/" && request.method === "GET") {
      return Promise.resolve(jsonResponse(200, detail));
    }
    if (url.pathname === "/api/v1/conversations/c1/block/") {
      detail = { ...detail, blocked_by_me: request.method === "POST" };
      return Promise.resolve(jsonResponse(200, detail));
    }
    if (url.pathname === "/api/v1/messages/m1/report/") {
      return Promise.resolve(jsonResponse(201, { id: "r1", status: "open" }));
    }
    return Promise.resolve(jsonResponse(404, { code: "not_found", message: "No.", details: {} }));
  });
  vi.stubGlobal("fetch", network);
});

afterEach(() => vi.unstubAllGlobals());

describe("ChatThread", () => {
  it("shows history, subscribes from its cursor, and marks the other side read", async () => {
    const { transport, push, subscribed } = fakeTransport();
    render(<ChatThread conversationId="c1" transport={transport} backHref="/console/messages" />);
    expect(await screen.findByRole("heading", { level: 1, name: "Aarav Mehta" })).toBeVisible();
    expect(await screen.findByText("Message 1")).toBeVisible();
    expect(screen.getByText(/Seen/)).toBeVisible();
    expect(screen.getByText(/hidden until the booking is confirmed/)).toBeVisible();
    await waitFor(() => expect(subscribed()).toBe(true));
    expect(transport.subscribe.mock.calls[0]![1]).toBe("2");
    expect(transport.markRead).toHaveBeenCalledWith("c1", "1");

    push([msg("3", { body: "New one" })], "3");
    expect(await screen.findByText("New one")).toBeVisible();
    await waitFor(() => expect(transport.markRead).toHaveBeenLastCalledWith("c1", "3"));
  });

  it("sends and tells the sender what was hidden", async () => {
    const user = userEvent.setup();
    const { transport } = fakeTransport();
    render(<ChatThread conversationId="c1" transport={transport} backHref="/console/messages" />);
    await user.type(await screen.findByLabelText("Message"), "Call 98765 43210");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("status")).toHaveTextContent("We hid a phone number");
    expect(screen.getByText("[hidden] me")).toBeVisible();
    const draft = transport.send.mock.calls[0]![1];
    expect(draft.body).toBe("Call 98765 43210");
    expect(draft.clientId).toBeTruthy();
    expect(screen.getByLabelText("Message")).toHaveValue("");
  });

  it("reports a message with a reason", async () => {
    const user = userEvent.setup();
    const { transport } = fakeTransport();
    render(<ChatThread conversationId="c1" transport={transport} backHref="/console/messages" />);
    await screen.findByText("Message 1");
    await user.click(screen.getByRole("button", { name: "Report" }));
    await user.selectOptions(screen.getByLabelText("Why are you reporting this?"), "scam");
    await user.click(screen.getByRole("button", { name: "Send report" }));
    expect(await screen.findByText(/Our team will review/)).toBeVisible();
    const call = network.mock.calls.find(
      (c) => new URL((c[0] as Request).url).pathname === "/api/v1/messages/m1/report/",
    );
    expect(await (call![0] as Request).json()).toEqual({ reason: "scam" });
  });

  it("blocks after confirming, and shows why it can't send", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("confirm", () => true);
    const { transport } = fakeTransport();
    render(<ChatThread conversationId="c1" transport={transport} backHref="/console/messages" />);
    await user.click(await screen.findByRole("button", { name: "Block" }));
    expect(await screen.findByRole("button", { name: "Unblock" })).toBeVisible();
  });

  it("is read-only when the chat is closed", async () => {
    detail = { ...conversation, can_send: false, cant_send_reason: "This application is closed." };
    const { transport } = fakeTransport();
    render(<ChatThread conversationId="c1" transport={transport} backHref="/console/messages" />);
    expect(await screen.findByText("This application is closed.")).toBeVisible();
    expect(screen.queryByLabelText("Message")).toBeNull();
  });
});
