"use client";

import { useEffect, useId, useRef } from "react";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * A modal dialog: a side drawer or a centred box. Focus moves in when it opens, Tab
 * stays inside, Escape or the close button closes it, and focus goes back to whatever
 * opened it.
 */
export function Dialog({
  title,
  description,
  onClose,
  variant = "box",
  children,
  footer,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  onClose: () => void;
  variant?: "box" | "drawer";
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  const ids = useId();
  const panel = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  useEffect(() => {
    close.current = onClose;
  });

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    const first = panel.current?.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? panel.current)?.focus();
    return () => opener?.focus?.();
  }, []);

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === "Escape") {
      event.stopPropagation();
      close.current();
      return;
    }
    if (event.key !== "Tab" || !panel.current) return;
    const items = [...panel.current.querySelectorAll<HTMLElement>(FOCUSABLE)];
    if (!items.length) return;
    const first = items[0]!;
    const last = items[items.length - 1]!;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  return (
    <div className={`dialog-backdrop dialog-backdrop--${variant}`} onMouseDown={onClose}>
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${ids}-title`}
        aria-describedby={description ? `${ids}-desc` : undefined}
        tabIndex={-1}
        className={`dialog dialog--${variant}`}
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={onKeyDown}
      >
        <header className="dialog__header">
          <div className="dialog__heading">
            <h2 id={`${ids}-title`} className="dialog__title">
              {title}
            </h2>
            {description ? (
              <div id={`${ids}-desc`} className="dialog__description">
                {description}
              </div>
            ) : null}
          </div>
          <button type="button" className="dialog__close" aria-label="Close" onClick={onClose}>
            <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
              <path d="M6 6l12 12M18 6 6 18" stroke="currentColor" strokeWidth="2" />
            </svg>
          </button>
        </header>
        <div className="dialog__body">{children}</div>
        {footer ? <footer className="dialog__footer">{footer}</footer> : null}
      </div>
    </div>
  );
}

/** Keyboard tabs (arrow keys move between them), for the drawer's sections. */
export function Tabs<T extends string>({
  label,
  tabs,
  active,
  onChange,
  idPrefix,
}: {
  label: string;
  tabs: ReadonlyArray<{ id: T; label: React.ReactNode }>;
  active: T;
  onChange: (id: T) => void;
  idPrefix: string;
}) {
  const refs = useRef(new Map<T, HTMLButtonElement>());
  function onKeyDown(event: React.KeyboardEvent, index: number) {
    const delta = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
    let next: number | undefined;
    if (delta) next = (index + delta + tabs.length) % tabs.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = tabs.length - 1;
    if (next === undefined) return;
    event.preventDefault();
    const id = tabs[next]!.id;
    onChange(id);
    refs.current.get(id)?.focus();
  }
  return (
    <div role="tablist" aria-label={label} className="tabs">
      {tabs.map((tab, index) => (
        <button
          key={tab.id}
          ref={(el) => {
            if (el) refs.current.set(tab.id, el);
          }}
          type="button"
          role="tab"
          id={`${idPrefix}-tab-${tab.id}`}
          aria-controls={`${idPrefix}-panel-${tab.id}`}
          aria-selected={tab.id === active}
          tabIndex={tab.id === active ? 0 : -1}
          className="tabs__tab"
          onClick={() => onChange(tab.id)}
          onKeyDown={(e) => onKeyDown(e, index)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
