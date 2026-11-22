import { useId } from "react";

type Props = Omit<React.ComponentProps<"input">, "type"> & {
  label: React.ReactNode;
  error?: string;
};

/** One checkbox per agreement, so each consent is given separately and explicitly. */
export function Agreement({ label, error, ref, ...input }: Props) {
  const id = useId();
  return (
    <div className="field">
      <label className="agreement" htmlFor={`${id}-box`}>
        <input
          ref={ref}
          id={`${id}-box`}
          type="checkbox"
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : undefined}
          {...input}
        />
        <span>{label}</span>
      </label>
      {error ? (
        <p className="field__error" id={`${id}-error`}>
          {error}
        </p>
      ) : null}
    </div>
  );
}
