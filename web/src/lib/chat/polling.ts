import { api, unwrap } from "@/lib/api/client";

import type {
  ChatTransport,
  Draft,
  HistoryPage,
  MessageBatch,
  SendResult,
  Subscription,
} from "./transport";

export const POLL_MS = 4000;
const MAX_BACKOFF_MS = 30000;

/** The REST calls the polling transport makes; tests pass fakes. */
export type ChatApi = {
  list(conversationId: string, query: { after?: string; before?: string }): Promise<HistoryPage>;
  send(conversationId: string, draft: Draft): Promise<SendResult>;
  read(conversationId: string, upTo: string): Promise<void>;
};

export const restChatApi: ChatApi = {
  async list(conversationId, query) {
    const page = await unwrap(
      api.GET("/api/v1/conversations/{conversation_id}/messages/", {
        params: { path: { conversation_id: conversationId }, query },
      }),
    );
    return {
      messages: page.results,
      cursor: page.cursor,
      otherReadUpTo: page.other_read_up_to,
      hasEarlier: page.has_earlier,
    };
  },
  async send(conversationId, draft) {
    return unwrap(
      api.POST("/api/v1/conversations/{conversation_id}/messages/", {
        params: { path: { conversation_id: conversationId } },
        body: {
          body: draft.body,
          attachment_ids: draft.attachmentIds ?? [],
          client_id: draft.clientId,
        },
      }),
    );
  },
  async read(conversationId, upTo) {
    await unwrap(
      api.POST("/api/v1/conversations/{conversation_id}/read/", {
        params: { path: { conversation_id: conversationId } },
        body: { up_to: upTo },
      }),
    );
  },
};

type Options = {
  intervalMs?: number;
  /** Whether the page is visible; polling pauses while it isn't. */
  isVisible?: () => boolean;
};

/**
 * Short polling: asks for messages after the cursor every few seconds, only while a
 * chat screen is subscribed and the tab is visible. Backs off after failures, and
 * polls straight away after a send so the other side's replies show up quickly.
 */
export class PollingTransport implements ChatTransport {
  private readonly intervalMs: number;
  private readonly isVisible: () => boolean;
  private readonly wake = new Map<string, () => void>();

  constructor(
    private readonly rest: ChatApi = restChatApi,
    options: Options = {},
  ) {
    this.intervalMs = options.intervalMs ?? POLL_MS;
    this.isVisible =
      options.isVisible ??
      (() => typeof document === "undefined" || document.visibilityState !== "hidden");
  }

  history(conversationId: string, before?: string): Promise<HistoryPage> {
    return this.rest.list(conversationId, before ? { before } : {});
  }

  subscribe(conversationId: string, cursor: string, subscription: Subscription): () => void {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let delay = this.intervalMs;
    let current = cursor;
    let inFlight = false;

    const schedule = (ms: number) => {
      if (stopped) return;
      clearTimeout(timer);
      timer = setTimeout(() => void tick(), ms);
    };

    const tick = async () => {
      if (stopped || inFlight) return;
      if (!this.isVisible()) return schedule(this.intervalMs);
      inFlight = true;
      try {
        const page = await this.rest.list(conversationId, { after: current });
        if (stopped) return;
        current = page.cursor;
        delay = this.intervalMs;
        const batch: MessageBatch = {
          messages: page.messages,
          cursor: page.cursor,
          otherReadUpTo: page.otherReadUpTo,
        };
        subscription.onMessages(batch);
      } catch (error) {
        if (stopped) return;
        delay = Math.min(delay * 2, MAX_BACKOFF_MS);
        subscription.onError?.(error);
      } finally {
        inFlight = false;
      }
      schedule(delay);
    };

    this.wake.set(conversationId, () => schedule(0));
    schedule(this.intervalMs);
    return () => {
      stopped = true;
      clearTimeout(timer);
      this.wake.delete(conversationId);
    };
  }

  async send(conversationId: string, draft: Draft): Promise<SendResult> {
    const result = await this.rest.send(conversationId, draft);
    this.wake.get(conversationId)?.();
    return result;
  }

  markRead(conversationId: string, upTo: string): Promise<void> {
    return this.rest.read(conversationId, upTo);
  }
}
