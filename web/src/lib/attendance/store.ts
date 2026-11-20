import type { Arrivals, SyncResult } from "@/lib/api/types";

/**
 * What the arrivals screen keeps on the device, so it works without signal: the last
 * arrivals list (with the public keys), check-ins waiting to sync, and what the last
 * sync said. IndexedDB in the browser; in memory where it isn't available.
 */

export type QueuedCheckIn = {
  client_id: string;
  booking_id: string;
  method: "qr" | "code" | "manual";
  token?: string;
  code?: string;
  reason?: string;
  /** When it was scanned or confirmed, on this device's clock. */
  scanned_at: string;
  /** Shown in the queue: who it was. */
  talent_name: string;
};

export type Outcome = SyncResult & { talent_name: string; at: string };

export interface AttendanceStore {
  getDay(): Promise<Arrivals | null>;
  setDay(day: Arrivals): Promise<void>;
  queued(): Promise<QueuedCheckIn[]>;
  enqueue(item: QueuedCheckIn): Promise<void>;
  remove(clientIds: readonly string[]): Promise<void>;
  outcomes(): Promise<Outcome[]>;
  addOutcomes(items: readonly Outcome[]): Promise<void>;
}

const DB = "barterly-attendance";
const KV = "kv";
const QUEUE = "queue";

function request<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function open(): Promise<IDBDatabase> {
  const req = indexedDB.open(DB, 1);
  req.onupgradeneeded = () => {
    req.result.createObjectStore(KV);
    req.result.createObjectStore(QUEUE, { keyPath: "client_id" });
  };
  return request(req);
}

async function withStore<T>(
  name: string,
  mode: IDBTransactionMode,
  run: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  const db = await open();
  try {
    return await request(run(db.transaction(name, mode).objectStore(name)));
  } finally {
    db.close();
  }
}

const MAX_OUTCOMES = 50;

export function indexedDbStore(): AttendanceStore {
  return {
    async getDay() {
      return ((await withStore(KV, "readonly", (s) => s.get("day"))) as Arrivals) ?? null;
    },
    async setDay(day) {
      await withStore(KV, "readwrite", (s) => s.put(day, "day"));
    },
    async queued() {
      const items = (await withStore(QUEUE, "readonly", (s) => s.getAll())) as QueuedCheckIn[];
      return items.sort((a, b) => a.scanned_at.localeCompare(b.scanned_at));
    },
    async enqueue(item) {
      await withStore(QUEUE, "readwrite", (s) => s.put(item));
    },
    async remove(clientIds) {
      for (const id of clientIds) await withStore(QUEUE, "readwrite", (s) => s.delete(id));
    },
    async outcomes() {
      return ((await withStore(KV, "readonly", (s) => s.get("outcomes"))) as Outcome[]) ?? [];
    },
    async addOutcomes(items) {
      const current = await this.outcomes();
      const next = [...items, ...current].slice(0, MAX_OUTCOMES);
      await withStore(KV, "readwrite", (s) => s.put(next, "outcomes"));
    },
  };
}

export function memoryStore(): AttendanceStore {
  let day: Arrivals | null = null;
  const queue = new Map<string, QueuedCheckIn>();
  let outcomes: Outcome[] = [];
  return {
    getDay: async () => day,
    setDay: async (d) => {
      day = d;
    },
    queued: async () =>
      [...queue.values()].sort((a, b) => a.scanned_at.localeCompare(b.scanned_at)),
    enqueue: async (item) => {
      queue.set(item.client_id, item);
    },
    remove: async (ids) => {
      ids.forEach((id) => queue.delete(id));
    },
    outcomes: async () => outcomes,
    addOutcomes: async (items) => {
      outcomes = [...items, ...outcomes].slice(0, MAX_OUTCOMES);
    },
  };
}

export function defaultStore(): AttendanceStore {
  return typeof indexedDB === "undefined" ? memoryStore() : indexedDbStore();
}
