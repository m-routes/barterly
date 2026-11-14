"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type Load<T> =
  { status: "loading" } | { status: "ready"; data: T } | { status: "error"; error: unknown };

/**
 * Load data when the component mounts or `key` changes; `reload()` fetches again and
 * `setData()` updates it after a save. `refresh()` fetches again but keeps showing the
 * current data meanwhile (no loading state). A late answer for an old key is ignored.
 */
export function useLoad<T>(load: () => Promise<T>, key: string) {
  const [state, setState] = useState<Load<T>>({ status: "loading" });
  const loader = useRef(load);
  useEffect(() => {
    loader.current = load;
  });
  const generation = useRef(0);

  const fetchData = useCallback(async (quiet: boolean) => {
    const mine = ++generation.current;
    if (!quiet) setState({ status: "loading" });
    try {
      const data = await loader.current();
      if (mine === generation.current) setState({ status: "ready", data });
    } catch (error) {
      if (mine === generation.current && !quiet) setState({ status: "error", error });
    }
  }, []);
  const reload = useCallback(() => fetchData(false), [fetchData]);
  const refresh = useCallback(() => fetchData(true), [fetchData]);

  useEffect(() => {
    // Fetching is this effect's job; its result is state.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void reload();
  }, [reload, key]);

  const setData = useCallback((update: (current: T) => T) => {
    setState((s) => (s.status === "ready" ? { status: "ready", data: update(s.data) } : s));
  }, []);

  return { state, reload, refresh, setData };
}
