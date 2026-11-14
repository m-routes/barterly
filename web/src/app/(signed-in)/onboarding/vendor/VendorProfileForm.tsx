"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/Button";
import { FormError, SelectField, TextArea, TextField } from "@/components/ui/fields";
import { api, unwrap } from "@/lib/api/client";
import { describeError, fieldErrors, ApiError } from "@/lib/api/errors";
import type { VendorProfile } from "@/lib/api/types";
import {
  BUSINESS_TYPE_LABELS,
  BUSINESS_TYPES,
  INDIAN_STATES,
  VENDOR_FIELDS,
  vendorFormDefaults,
  vendorProfileSchema,
  type VendorProfilePayload,
  type VendorProfileValues,
} from "@/lib/validation/vendorProfile";

const BUSINESS_TYPE_OPTIONS = BUSINESS_TYPES.map((value) => ({
  value,
  label: BUSINESS_TYPE_LABELS[value],
}));
const STATE_OPTIONS = INDIAN_STATES.map((value) => ({ value, label: value }));

function isVendorField(name: string): name is (typeof VENDOR_FIELDS)[number] {
  return (VENDOR_FIELDS as readonly string[]).includes(name);
}

/**
 * Create or edit the vendor profile. The first PATCH creates it (201); after that it
 * updates. Server-side field errors are shown on the matching fields.
 */
export function VendorProfileForm({
  initial,
  onSaved,
}: {
  initial: VendorProfile | null;
  onSaved: (profile: VendorProfile) => void | Promise<void>;
}) {
  const form = useForm<VendorProfileValues, unknown, VendorProfilePayload>({
    resolver: zodResolver(vendorProfileSchema),
    defaultValues: vendorFormDefaults(initial),
    mode: "onTouched",
  });
  const { errors, isSubmitting } = form.formState;

  async function submit(values: VendorProfilePayload) {
    try {
      const profile = await unwrap(api.PATCH("/api/v1/profiles/vendor/me/", { body: values }));
      await onSaved(profile);
    } catch (error) {
      const byField = error instanceof ApiError ? fieldErrors(error) : {};
      let shown = false;
      for (const [field, message] of Object.entries(byField)) {
        if (isVendorField(field)) {
          form.setError(field, { message }, { shouldFocus: !shown });
          shown = true;
        }
      }
      if (!shown) form.setError("root", { message: byField.root ?? describeError(error) });
    }
  }

  return (
    <form
      noValidate
      onSubmit={form.handleSubmit(submit)}
      className="stack"
      aria-label="Business profile"
    >
      <fieldset className="form-section">
        <legend className="form-section__title">Your business</legend>
        <TextField
          label="Business name"
          autoComplete="organization"
          error={errors.business_name?.message}
          {...form.register("business_name")}
        />
        <SelectField
          label="Business type"
          options={BUSINESS_TYPE_OPTIONS}
          error={errors.business_type?.message}
          {...form.register("business_type")}
        />
        <TextArea
          label="About your place"
          hint="What's it like, who stays, and what kind of help you're after."
          rows={5}
          error={errors.about?.message}
          {...form.register("about")}
        />
      </fieldset>

      <fieldset className="form-section">
        <legend className="form-section__title">Where and who</legend>
        <TextField
          label="Contact name"
          hint="The person talent will hear from."
          autoComplete="name"
          error={errors.contact_name?.message}
          {...form.register("contact_name")}
        />
        <div className="form-grid">
          <TextField
            label="City or town"
            autoComplete="address-level2"
            error={errors.city?.message}
            {...form.register("city")}
          />
          <SelectField
            label="State or union territory"
            options={STATE_OPTIONS}
            error={errors.state?.message}
            {...form.register("state")}
          />
        </div>
        <TextArea
          label="Address"
          optional
          rows={2}
          autoComplete="street-address"
          error={errors.address?.message}
          {...form.register("address")}
        />
      </fieldset>

      <fieldset className="form-section">
        <legend className="form-section__title">Business details</legend>
        <TextField
          label="GSTIN"
          optional
          hint="15 characters, e.g. 29ABCDE1234F1Z5"
          autoCapitalize="characters"
          spellCheck={false}
          maxLength={15}
          error={errors.gstin?.message}
          {...form.register("gstin")}
        />
        <TextField
          label="Website"
          optional
          type="url"
          inputMode="url"
          placeholder="https://"
          error={errors.website?.message}
          {...form.register("website")}
        />
      </fieldset>

      <FormError message={errors.root?.message} />
      <Button type="submit" block busy={isSubmitting} busyLabel="Saving…">
        {initial ? "Save profile" : "Create profile"}
      </Button>
    </form>
  );
}
