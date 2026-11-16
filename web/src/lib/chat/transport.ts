import type { components } from "@/lib/api/schema";

type Schemas = components["schemas"];

export type ChatMessage = Schemas["ChatMessage"];
export type Conversation = Schemas["Conversation"];
export type ConversationDetail = Schemas["ConversationDetail"];
export type ReportReason = Schemas["ChatReportReasonEnum"];

export type MessageBatch = {
  messages: ChatMessage[];
  /** Pass back to get only newer messages. */
  cursor: string;
  /** The newest of my messages the other side has read. */
  otherReadUpTo: string;
};

export type HistoryPage = MessageBatch & { hasEarlier: boolean };

export type Draft = { body: string; attachmentIds?: string[]; clientId: string };

export type SendResult = { message: ChatMessage; notice: string };

export type Subscription = {
  onMessages: (batch: MessageBatch) => void;
  onError?: (error: unknown) => void;
};

/**
 * How a chat screen gets and sends messages. Screens only use this interface, so the
 * polling transport (./polling.ts) can be swapped for a WebSocket one without changing
 * them.
 */
export interface ChatTransport {
  /** The newest page, or the page before `before`. */
  history(conversationId: string, before?: string): Promise<HistoryPage>;
  /** Deliver messages after `cursor` until the returned function is called. */
  subscribe(conversationId: string, cursor: string, subscription: Subscription): () => void;
  send(conversationId: string, draft: Draft): Promise<SendResult>;
  markRead(conversationId: string, upTo: string): Promise<void>;
}

/** A new id for a send, so retrying it doesn't post twice. */
export function newClientId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/** Compare two message cursors (they are increasing integers as strings). */
export function cursorAfter(a: string, b: string): boolean {
  return Number(a) > Number(b);
}
