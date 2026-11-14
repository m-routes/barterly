"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api, unwrap, writeBody } from "@/lib/api/client";
import { ApiError, describeError, fieldErrors } from "@/lib/api/errors";
import type { Gig } from "@/lib/api/types";

import { canCreate, toPayload, type GigDraft } from "./draft";

export type SaveState =
  | { kind: "idle" }
  | { kind: "waiting" } // a new gig needs a property, title, role and pay model first
  | { kind: "invalid" } // fix the highlighted fields first
  | { kind: "saving" }
  | { kind: "saved"; at: Date }
  | { kind: "error"; message: string };

const key = (draft: GigDraft) => JSON.stringify(toPayload(draft));

/**
 * Saves the gig builder's draft: the first save creates the gig (POST), later ones
 * update it (PATCH). Saves run one at a time, always with the newest draft, and are
 * skipped when nothing changed since the last one.
 */
export function useGigSaver(initial: Gig | null, initialDraft: GigDraft) {
  const [gig, setGig] = useState<Gig | null>(initial);
  const [state, setState] = useState<SaveState>({ kind: "idle" });
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({});
  const gigRef = useRef<Gig | null>(initial);
  const latest = useRef(initialDraft);
  // What the server has. For a new gig, the empty form: nothing to lose yet.
  const savedKey = useRef(key(initialDraft));
  const chain = useRef<Promise<Gig | null>>(Promise.resolve(initial));

  const isDirty = useCallback(() => key(latest.current) !== savedKey.current, []);

  const run = useCallback(async (): Promise<Gig | null> => {
    const draft = latest.current;
    const current = gigRef.current;
    const body = toPayload(draft);
    const bodyKey = JSON.stringify(body);
    if (current && bodyKey === savedKey.current) return current;
    if (!current && !canCreate(draft)) {
      setState({ kind: "waiting" });
      return null;
    }
    setState({ kind: "saving" });
    try {
      const saved = current
        ? await unwrap(
            api.PATCH("/api/v1/gigs/{gig_id}/", { params: { path: { gig_id: current.id } }, body }),
          )
        : await unwrap(api.POST("/api/v1/gigs/", { body: writeBody<Gig>(body) }));
      if (!current) {
        // Keep the page; make its address the edit page so a reload finds the gig.
        window.history.replaceState(null, "", `/console/gigs/${saved.id}/edit`);
      }
      gigRef.current = saved;
      savedKey.current = bodyKey;
      setGig(saved);
      setServerErrors({});
      setState({ kind: "saved", at: new Date() });
      return saved;
    } catch (error) {
      const byField = error instanceof ApiError ? fieldErrors(error) : {};
      setServerErrors(byField);
      setState({
        kind: "error",
        message: Object.keys(byField).length
          ? "Some fields need fixing before this can be saved."
          : describeError(error),
      });
      return null;
    }
  }, []);

  /** Save now (after any save already running). Resolves to the saved gig, or null. */
  const save = useCallback(
    (draft: GigDraft) => {
      latest.current = draft;
      chain.current = chain.current.then(run, run);
      return chain.current;
    },
    [run],
  );

  /** Remember the newest draft without saving it (e.g. while it has errors). */
  const track = useCallback((draft: GigDraft, invalid: boolean) => {
    latest.current = draft;
    if (invalid) setState({ kind: "invalid" });
  }, []);

  const clearServerError = useCallback((field: string) => {
    setServerErrors((errors) => {
      if (!(field in errors)) return errors;
      const next = { ...errors };
      delete next[field];
      return next;
    });
  }, []);

  // Warn before leaving with unsaved changes.
  useEffect(() => {
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      if (isDirty()) event.preventDefault();
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [isDirty]);

  return {
    gig,
    setGig,
    state,
    serverErrors,
    setServerErrors,
    clearServerError,
    save,
    track,
    isDirty,
  };
}
