"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Controller, useForm, useWatch } from "react-hook-form";

import { LocationPicker } from "@/components/map/LocationPicker";
import { Button } from "@/components/ui/Button";
import { FormError, SelectField, TextArea, TextField } from "@/components/ui/fields";
import { api, unwrap, writeBody } from "@/lib/api/client";
import { ApiError, describeError, fieldErrors } from "@/lib/api/errors";
import type { IndianState, Property } from "@/lib/api/types";
import { AMENITY_LABELS, PROPERTY_TYPE_LABELS, options } from "@/lib/vendor/labels";
import {
  PROPERTY_FIELDS,
  propertyDefaults,
  propertyPayload,
  propertySchema,
  type PropertyParsed,
  type PropertyValues,
} from "@/lib/validation/property";
import { INDIAN_STATES } from "@/lib/validation/vendorProfile";

const TYPE_OPTIONS = options(PROPERTY_TYPE_LABELS);
const STATE_OPTIONS = INDIAN_STATES.map((value) => ({ value, label: value }));
const AMENITY_OPTIONS = options(AMENITY_LABELS);

function isPropertyField(name: string): name is keyof PropertyValues {
  return (PROPERTY_FIELDS as string[]).includes(name);
}

/**
 * Create or edit a property: the details talent see, and the exact spot on the map
 * (only shown to talent once they're booked).
 */
export function PropertyForm({
  initial,
  onSaved,
}: {
  initial: Property | null;
  onSaved: (property: Property) => void | Promise<void>;
}) {
  const form = useForm<PropertyValues, unknown, PropertyParsed>({
    resolver: zodResolver(propertySchema),
    defaultValues: propertyDefaults(initial),
    mode: "onTouched",
  });
  const { errors, isSubmitting } = form.formState;
  const [latitude, longitude] = useWatch({
    control: form.control,
    name: ["latitude", "longitude"],
  });
  const point = latitude != null && longitude != null ? { latitude, longitude } : null;

  async function submit(values: PropertyParsed) {
    const body = propertyPayload(values);
    try {
      const saved = initial
        ? await unwrap(
            api.PATCH("/api/v1/properties/{property_id}/", {
              params: { path: { property_id: initial.id } },
              body,
            }),
          )
        : await unwrap(api.POST("/api/v1/properties/", { body: writeBody<Property>(body) }));
      form.reset(propertyDefaults(saved));
      await onSaved(saved);
    } catch (error) {
      const byField = error instanceof ApiError ? fieldErrors(error) : {};
      let shown = false;
      for (const [field, message] of Object.entries(byField)) {
        if (isPropertyField(field)) {
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
      aria-label="Property details"
    >
      <fieldset className="form-section panel">
        <legend className="form-section__title">About the property</legend>
        <div className="form-grid">
          <TextField
            label="Property name"
            error={errors.name?.message}
            {...form.register("name")}
          />
          <SelectField
            label="Kind of property"
            options={TYPE_OPTIONS}
            error={errors.property_type?.message}
            {...form.register("property_type")}
          />
        </div>
        <fieldset className="checkbox-group">
          <legend className="field__label">Amenities</legend>
          {AMENITY_OPTIONS.map((amenity) => (
            <label key={amenity.value} className="checkbox">
              <input type="checkbox" value={amenity.value} {...form.register("amenities")} />
              {amenity.label}
            </label>
          ))}
        </fieldset>
        <TextArea
          label="House rules"
          optional
          hint="One per line, e.g. Quiet hours after 10 pm."
          rows={4}
          error={errors.house_rules?.message}
          {...form.register("house_rules")}
        />
        <label className="checkbox">
          <input type="checkbox" {...form.register("women_friendly")} />
          Women-friendly: women-only rooms or dorms and staff on site at night
        </label>
      </fieldset>

      <fieldset className="form-section panel">
        <legend className="form-section__title">Address</legend>
        <TextArea
          label="Street address"
          rows={2}
          autoComplete="street-address"
          error={errors.address?.message}
          {...form.register("address")}
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
          <TextField
            label="PIN code"
            optional
            inputMode="numeric"
            maxLength={6}
            autoComplete="postal-code"
            error={errors.pincode?.message}
            {...form.register("pincode")}
          />
        </div>
      </fieldset>

      <fieldset className="form-section panel">
        <legend className="form-section__title">Exact location</legend>
        <p className="field__hint">
          Put the pin on the entrance. Talent see an approximate area until they&apos;re booked.
        </p>
        <LocationPicker
          value={point}
          suggestedQuery={[initial?.name, initial?.city].filter(Boolean).join(", ")}
          error={errors.latitude?.message ?? errors.longitude?.message}
          onChange={(next) => {
            const options = { shouldDirty: true };
            form.setValue("latitude", next.latitude, options);
            form.setValue("longitude", next.longitude, options);
            // A moved pin needs confirming again.
            form.setValue("location_confirmed", false, options);
          }}
          onPlaceFound={(place) => {
            if (place.city && !form.getValues("city")) form.setValue("city", place.city);
            if (place.postcode && !form.getValues("pincode")) {
              form.setValue("pincode", place.postcode.replace(/\s/g, "").slice(0, 6));
            }
            if (
              place.state &&
              !form.getValues("state") &&
              (INDIAN_STATES as string[]).includes(place.state)
            ) {
              form.setValue("state", place.state as IndianState);
            }
          }}
        />
        <Controller
          control={form.control}
          name="location_confirmed"
          render={({ field }) => (
            <label className="checkbox">
              <input
                type="checkbox"
                checked={field.value}
                disabled={!point}
                onChange={(e) => field.onChange(e.target.checked)}
                onBlur={field.onBlur}
                ref={field.ref}
              />
              The pin is on the property&apos;s entrance
            </label>
          )}
        />
        {errors.location_confirmed?.message ? (
          <p className="field__error">{errors.location_confirmed.message}</p>
        ) : null}
      </fieldset>

      <FormError message={errors.root?.message} />
      <div className="actions-row">
        <Button type="submit" busy={isSubmitting} busyLabel="Saving…">
          {initial ? "Save property" : "Add property"}
        </Button>
      </div>
    </form>
  );
}
