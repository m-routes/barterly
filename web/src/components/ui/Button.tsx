type ButtonProps = React.ComponentProps<"button"> & {
  variant?: "primary" | "secondary" | "ghost";
  /** Shows a spinner, disables the button and keeps its label for screen readers. */
  busy?: boolean;
  busyLabel?: string;
  block?: boolean;
};

export function Button({
  variant = "primary",
  busy = false,
  busyLabel,
  block = false,
  disabled,
  className,
  children,
  type = "button",
  ...rest
}: ButtonProps) {
  const classes = ["button", `button--${variant}`, block ? "button--block" : null, className]
    .filter(Boolean)
    .join(" ");
  return (
    <button
      type={type}
      className={classes}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      {...rest}
    >
      {busy ? <span className="spinner__ring" aria-hidden="true" /> : null}
      <span>{busy && busyLabel ? busyLabel : children}</span>
    </button>
  );
}
