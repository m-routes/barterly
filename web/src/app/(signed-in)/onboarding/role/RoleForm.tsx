"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, useWatch } from "react-hook-form";

import { Button } from "@/components/ui/Button";
import { FormError } from "@/components/ui/fields";
import { api, unwrap } from "@/lib/api/client";
import { ApiError, describeError } from "@/lib/api/errors";
import type { User } from "@/lib/api/types";
import { roleSchema, type RoleForm as RoleValues } from "@/lib/validation/auth";

const OPTIONS = [
  {
    value: "vendor",
    title: "I run a place",
    description: "Hostels, homestays, cafés, camps and tours. Post gigs and find talent.",
  },
  {
    value: "talent",
    title: "I'm talent",
    description: "Artists, creators, chefs and more. Trade your skills for stays.",
  },
] as const;

/** Choose vendor or talent. The API allows this once; admins are made in the admin. */
export function RoleForm({ onChosen }: { onChosen: (user: User | null) => void | Promise<void> }) {
  const form = useForm<RoleValues>({ resolver: zodResolver(roleSchema) });
  const selected = useWatch({ control: form.control, name: "role" });

  async function submit({ role }: RoleValues) {
    try {
      const user = await unwrap(api.POST("/api/v1/me/role/", { body: { role } }));
      await onChosen(user);
    } catch (error) {
      if (error instanceof ApiError && error.code === "role_already_set") {
        // Chosen in another tab or device: carry on with what's saved.
        await onChosen(null);
        return;
      }
      form.setError("root", { message: describeError(error) });
    }
  }

  return (
    <form noValidate onSubmit={form.handleSubmit(submit)} className="stack">
      <fieldset
        className="choice-group"
        aria-describedby={form.formState.errors.role ? "role-error" : "role-note"}
      >
        <legend className="visually-hidden">How will you use Barterly?</legend>
        {OPTIONS.map((option) => (
          <label
            key={option.value}
            className={`choice-card${selected === option.value ? " choice-card--selected" : ""}`}
          >
            <input
              type="radio"
              value={option.value}
              className="choice-card__input"
              {...form.register("role")}
            />
            <span className="choice-card__title">{option.title}</span>
            <span className="choice-card__text">{option.description}</span>
          </label>
        ))}
      </fieldset>
      {form.formState.errors.role ? (
        <p id="role-error" className="field__error">
          {form.formState.errors.role.message}
        </p>
      ) : (
        <p id="role-note" className="field__hint">
          You can&apos;t change this later, so pick the one that fits.
        </p>
      )}
      <FormError message={form.formState.errors.root?.message} />
      <Button type="submit" block busy={form.formState.isSubmitting} busyLabel="Saving…">
        Continue
      </Button>
    </form>
  );
}
