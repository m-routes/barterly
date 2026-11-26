"use client";

import Link from "next/link";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/Button";
import { FormError } from "@/components/ui/fields";
import { api, unwrap } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import { LEGAL_VERSION } from "@/lib/legal/documents";
import { consentSchema, type ConsentForm as ConsentValues } from "@/lib/validation/auth";

import { Agreement } from "../Agreement";

/** Accept the current terms and privacy policy: two separate consents, two records. */
export function ConsentForm({ onAccepted }: { onAccepted: () => void | Promise<void> }) {
  const form = useForm<ConsentValues>({
    resolver: zodResolver(consentSchema),
    defaultValues: { terms: false, privacy: false },
  });
  const errors = form.formState.errors;

  async function submit() {
    try {
      for (const purpose of ["terms", "privacy"] as const) {
        await unwrap(
          api.POST("/api/v1/privacy/consents/", {
            body: { purpose, granted: true, version: LEGAL_VERSION, source: "web" },
          }),
        );
      }
      await onAccepted();
    } catch (error) {
      form.setError("root", { message: describeError(error) });
    }
  }

  return (
    <form noValidate onSubmit={form.handleSubmit(submit)} className="stack">
      <Agreement
        error={errors.terms?.message}
        {...form.register("terms")}
        label={
          <>
            I agree to the{" "}
            <a href="/legal/terms" target="_blank" rel="noreferrer">
              terms of service
            </a>{" "}
            (version {LEGAL_VERSION}).
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
            (version {LEGAL_VERSION}).
          </>
        }
      />
      <FormError message={errors.root?.message} />
      <Button type="submit" block busy={form.formState.isSubmitting} busyLabel="Saving…">
        Continue
      </Button>
      <p className="field__hint">
        Don&apos;t agree? You can <Link href="/account/privacy">delete your account</Link> instead.
      </p>
    </form>
  );
}
