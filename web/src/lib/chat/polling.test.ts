import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { type ChatApi, PollingTransport } from "./polling";
import type { ChatMessage, HistoryPage } from "./transport";

const message = (cursor: string): ChatMessage => ({
  id: `m${cursor}`,
  cursor,
  sender: "u1",
  mine: false,
  body: `hello ${cursor}`,
  masked: false,
  attachments: [],
  client_id: "",
  read_at: null,
  created_at: "2026-11-15T10:00:00Z",
});

const page = (cursors: string[], cursor: string): HistoryPage => ({
  messages: cursors.map(message),
  cursor,
  otherReadUpTo: "0",
  hasEarlier: false,
});

function fakeApi(pages: HistoryPage[]) {
  const queue = [...pages];
  return {
    list: vi.fn<ChatApi["list"]>(() => Promise.resolve(queue.shift() ?? page([], "9"))),
    send: vi.fn<ChatApi["send"]>(() =>
      Promise.resolve({ message: { ...message("10"), mine: true }, notice: "" }),
    ),
    read: vi.fn<ChatApi["read"]>(() => Promise.resolve()),
  };
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("PollingTransport", () => {
  it("polls after the cursor and moves it forward", async () => {
    const rest = fakeApi([page(["3", "4"], "4"), page([], "4")]);
    const transport = new PollingTransport(rest, { intervalMs: 1000, isVisible: () => true });
    const onMessages = vi.fn();
    const stop = transport.subscribe("c1", "2", { onMessages });

    expect(rest.list).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1000);
    expect(rest.list).toHaveBeenLastCalledWith("c1", { after: "2" });
    expect(onMessages.mock.calls[0]![0].messages.map((m: ChatMessage) => m.cursor)).toEqual([
      "3",
      "4",
    ]);
    await vi.advanceTimersByTimeAsync(1000);
    expect(rest.list).toHaveBeenLastCalledWith("c1", { after: "4" });
    stop();
  });

  it("stops polling when unsubscribed", async () => {
    const rest = fakeApi([]);
    const transport = new PollingTransport(rest, { intervalMs: 1000, isVisible: () => true });
    const stop = transport.subscribe("c1", "0", { onMessages: vi.fn() });
    await vi.advanceTimersByTimeAsync(1000);
    stop();
    await vi.advanceTimersByTimeAsync(10000);
    expect(rest.list).toHaveBeenCalledTimes(1);
  });

  it("doesn't poll while the tab is hidden", async () => {
    let visible = false;
    const rest = fakeApi([]);
    const transport = new PollingTransport(rest, { intervalMs: 1000, isVisible: () => visible });
    const stop = transport.subscribe("c1", "0", { onMessages: vi.fn() });
    await vi.advanceTimersByTimeAsync(5000);
    expect(rest.list).not.toHaveBeenCalled();
    visible = true;
    await vi.advanceTimersByTimeAsync(1000);
    expect(rest.list).toHaveBeenCalledTimes(1);
    stop();
  });

  it("backs off after errors and reports them", async () => {
    const rest = fakeApi([]);
    rest.list.mockRejectedValue(new Error("offline"));
    const onError = vi.fn();
    const transport = new PollingTransport(rest, { intervalMs: 1000, isVisible: () => true });
    const stop = transport.subscribe("c1", "0", { onMessages: vi.fn(), onError });
    await vi.advanceTimersByTimeAsync(1000); // 1st try fails, next in 2s
    await vi.advanceTimersByTimeAsync(1999);
    expect(rest.list).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(rest.list).toHaveBeenCalledTimes(2);
    expect(onError).toHaveBeenCalledTimes(2);
    stop();
  });

  it("polls straight away after a send", async () => {
    const rest = fakeApi([]);
    const transport = new PollingTransport(rest, { intervalMs: 4000, isVisible: () => true });
    const stop = transport.subscribe("c1", "0", { onMessages: vi.fn() });
    await transport.send("c1", { body: "hi", clientId: "x" });
    await vi.advanceTimersByTimeAsync(0);
    expect(rest.list).toHaveBeenCalledTimes(1);
    stop();
  });
});
