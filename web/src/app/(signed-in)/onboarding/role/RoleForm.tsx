"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";

import { Button } from "@/components/ui/Button";
import { FormError, TextField } from "@/components/ui/fields";
import { track } from "@/lib/analytics/track";
import { api, unwrap } from "@/lib/api/client";
import { ApiError, describeError } from "@/lib/api/errors";
import type { User } from "@/lib/api/types";
import { LEGAL_VERSION } from "@/lib/legal/documents";
import { roleSchema, type RoleForm as RoleValues } from "@/lib/validation/auth";

import { Agreement } from "../Agreement";

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

/**
 * Choose vendor or talent. The API allows this once; admins are made in the admin.
 *
 * During the closed beta some roles need an invite code (`inviteRoles`, from
 * GET /api/v1/beta/). If the server asks for one anyway, the field appears then.
 */
export function RoleForm({
  onChosen,
  inviteRoles = [],
}: {
  onChosen: (user: User | null) => void | Promise<void>;
  inviteRoles?: readonly string[];
}) {
  const [askInvite, setAskInvite] = useState(false);
  const [invite, setInvite] = useState("");
  const [inviteError, setInviteError] = useState("");
  const form = useForm<RoleValues>({
    resolver: zodResolver(roleSchema),
    defaultValues: { adult: false, terms: false, privacy: false },
  });
  const selected = useWatch({ control: form.control, name: "role" });
  const errors = form.formState.errors;
  const showInvite = askInvite || (selected !== undefined && inviteRoles.includes(selected));

  async function submit({ role }: RoleValues) {
    const needsInvite = askInvite || inviteRoles.includes(role);
    if (needsInvite && !invite.trim()) {
      setAskInvite(true);
      setInviteError("Enter the invite code we sent you.");
      return;
    }
    setInviteError("");
    try {
      const user = await unwrap(
        api.POST("/api/v1/me/role/", {
          body: {
            role,
            confirm_adult: true,
            terms_version: LEGAL_VERSION,
            privacy_version: LEGAL_VERSION,
            source: "web",
            ...(needsInvite ? { invite_code: invite.trim() } : {}),
          },
        }),
      );
      if (needsInvite) track("invite_entered", { ok: true });
      await onChosen(user);
    } catch (error) {
      if (error instanceof ApiError && error.code === "invite_required") {
        setAskInvite(true);
        setInviteError(error.message);
        return;
      }
      if (error instanceof ApiError && error.code === "invite_invalid") {
        track("invite_entered", { ok: false });
        setInviteError(error.message);
        return;
      }
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
      {showInvite ? (
        <TextField
          label="Invite code"
          hint="Barterly is invite-only for now. It looks like ABCD-2345."
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          maxLength={20}
          value={invite}
          onChange={(e) => setInvite(e.target.value)}
          error={inviteError}
        />
      ) : null}
      <fieldset className="stack-sm">
        <legend className="visually-hidden">Age and agreements</legend>
        <Agreement
          error={errors.adult?.message}
          {...form.register("adult")}
          label="I am 18 or older."
        />
        <Agreement
          error={errors.terms?.message}
          {...form.register("terms")}
          label={
            <>
              I agree to the{" "}
              <a href="/legal/terms" target="_blank" rel="noreferrer">
                terms of service
              </a>
              .
            </>
          }
        />
        <Agreement
          error={errors.privacy?.message}
          {...form.register("privacy")}
          label={
            <>
              I have read the{" "}
              <a href="/legal/privacy" target="_blank" rel="noreferrer">
                privacy policy
              </a>{" "}
              and agree to Barterly using my data as it describes.
            </>
          }
        />
      </fieldset>
      <FormError message={form.formState.errors.root?.message} />
      <Button type="submit" block busy={form.formState.isSubmitting} busyLabel="Saving…">
        Continue
      </Button>
    </form>
  );
}
