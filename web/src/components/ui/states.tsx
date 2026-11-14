import Link from "next/link";

/**
 * The loading, empty and error states every screen uses, so they look and read the
 * same everywhere. Each is announced to screen readers.
 */

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <span className="spinner" role="status">
      <span className="spinner__ring" aria-hidden="true" />
      <span className="visually-hidden">{label}</span>
    </span>
  );
}

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="state state--loading" aria-busy="true">
      <Spinner label={label} />
      <p className="state__text" aria-hidden="true">
        {label}
      </p>
    </div>
  );
}

type Action = { label: string; href: string } | { label: string; onClick: () => void };

function ActionButton({ action, primary }: { action: Action; primary?: boolean }) {
  const className = primary ? "button button--primary" : "button button--secondary";
  if ("href" in action) {
    return (
      <Link className={className} href={action.href}>
        {action.label}
      </Link>
    );
  }
  return (
    <button type="button" className={className} onClick={action.onClick}>
      {action.label}
    </button>
  );
}

export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string;
  description: string;
  action?: Action;
  icon?: React.ReactNode;
}) {
  return (
    <section className="state state--empty" aria-labelledby="empty-state-title">
      {icon ? (
        <div className="state__icon" aria-hidden="true">
          {icon}
        </div>
      ) : null}
      <h2 id="empty-state-title" className="state__title">
        {title}
      </h2>
      <p className="state__text">{description}</p>
      {action ? <ActionButton action={action} primary /> : null}
    </section>
  );
}

export function ErrorState({
  title = "Something went wrong",
  description,
  retry,
  action,
}: {
  title?: string;
  description: string;
  retry?: () => void;
  action?: Action;
}) {
  return (
    <section className="state state--error" role="alert">
      <h2 className="state__title">{title}</h2>
      <p className="state__text">{description}</p>
      <div className="state__actions">
        {retry ? <ActionButton action={{ label: "Try again", onClick: retry }} primary /> : null}
        {action ? <ActionButton action={action} /> : null}
      </div>
    </section>
  );
}
