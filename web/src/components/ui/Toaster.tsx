"use client";

import { useEffect, useState } from "react";

import { describeError } from "@/lib/api/errors";
import { onApiEvent } from "@/lib/api/events";

type Toast = { id: number; message: string };

const MAX_TOASTS = 3;
const TOAST_MS = 8000;

/**
 * The visible half of the global error handler: API failures no screen handles
 * itself (server errors, rate limits, permission errors, offline) appear here.
 */
export function Toaster() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => {
    let nextId = 1;
    const timers = new Set<ReturnType<typeof setTimeout>>();
    const unsubscribe = onApiEvent((event) => {
      if (event.type !== "error") return;
      const id = nextId++;
      const message = describeError(event.error);
      setToasts((current) => {
        // The same failure from parallel calls shows once.
        if (current.some((t) => t.message === message)) return current;
        return [...current, { id, message }].slice(-MAX_TOASTS);
      });
      const timer = setTimeout(() => {
        timers.delete(timer);
        setToasts((current) => current.filter((t) => t.id !== id));
      }, TOAST_MS);
      timers.add(timer);
    });
    return () => {
      unsubscribe();
      for (const timer of timers) clearTimeout(timer);
    };
  }, []);

  return (
    <div className="toaster" aria-live="assertive" aria-relevant="additions">
      {toasts.map((toast) => (
        <div key={toast.id} className="toast" role="alert">
          <p className="toast__message">{toast.message}</p>
          <button
            type="button"
            className="toast__close"
            aria-label="Dismiss"
            onClick={() => setToasts((current) => current.filter((t) => t.id !== toast.id))}
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
