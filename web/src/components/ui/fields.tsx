import { useId } from "react";

/**
 * Labelled form controls. Each wires its hint and error to the control with
 * aria-describedby, and marks it aria-invalid when there's an error.
 */

type FieldProps = {
  label: string;
  error?: string;
  hint?: string;
  optional?: boolean;
};

function useFieldIds() {
  const id = useId();
  return { control: `${id}-control`, hint: `${id}-hint`, error: `${id}-error` };
}

function describedBy(ids: ReturnType<typeof useFieldIds>, hint?: string, error?: string) {
  return [hint ? ids.hint : null, error ? ids.error : null].filter(Boolean).join(" ") || undefined;
}

function FieldFrame({
  ids,
  label,
  error,
  hint,
  optional,
  children,
}: FieldProps & { ids: ReturnType<typeof useFieldIds>; children: React.ReactNode }) {
  return (
    <div className="field">
      <label className="field__label" htmlFor={ids.control}>
        {label}
        {optional ? <span className="field__optional"> (optional)</span> : null}
      </label>
      {hint ? (
        <p className="field__hint" id={ids.hint}>
          {hint}
        </p>
      ) : null}
      {children}
      {error ? (
        <p className="field__error" id={ids.error}>
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function TextField({
  label,
  error,
  hint,
  optional,
  ...input
}: FieldProps & React.ComponentProps<"input">) {
  const ids = useFieldIds();
  return (
    <FieldFrame ids={ids} label={label} error={error} hint={hint} optional={optional}>
      <input
        id={ids.control}
        className="field__control"
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(ids, hint, error)}
        {...input}
      />
    </FieldFrame>
  );
}

export function TextArea({
  label,
  error,
  hint,
  optional,
  ...textarea
}: FieldProps & React.ComponentProps<"textarea">) {
  const ids = useFieldIds();
  return (
    <FieldFrame ids={ids} label={label} error={error} hint={hint} optional={optional}>
      <textarea
        id={ids.control}
        className="field__control field__control--area"
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(ids, hint, error)}
        {...textarea}
      />
    </FieldFrame>
  );
}

export function SelectField({
  label,
  error,
  hint,
  optional,
  options,
  placeholder = "Choose…",
  ...select
}: FieldProps & {
  options: ReadonlyArray<{ value: string; label: string }>;
  placeholder?: string;
} & React.ComponentProps<"select">) {
  const ids = useFieldIds();
  return (
    <FieldFrame ids={ids} label={label} error={error} hint={hint} optional={optional}>
      <select
        id={ids.control}
        className="field__control field__control--select"
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(ids, hint, error)}
        {...select}
      >
        <option value="">{placeholder}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </FieldFrame>
  );
}

/** A form-level error (e.g. from the server), announced when it appears. */
export function FormError({ message }: { message?: string }) {
  if (!message) return null;
  return (
    <p className="form-error" role="alert">
      {message}
    </p>
  );
}
