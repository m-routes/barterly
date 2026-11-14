"use client";

import { useId, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/StatusChip";
import { api, unwrap } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import type { Property, PropertyPhoto } from "@/lib/api/types";
import { readPhotoMetadata, uploadFile, uploadProblem } from "@/lib/media/upload";
import { MAX_PROPERTY_PHOTOS, MIN_VERIFICATION_PHOTOS } from "@/lib/validation/property";

type Upload = { name: string; state: "uploading" | "failed"; message?: string };

/**
 * Upload photos straight to storage, then attach them to the property with where and
 * when they were taken (from the photo's own data), which verification checks.
 */
export function PropertyPhotos({
  property,
  onChange,
}: {
  property: Property;
  onChange: (photos: PropertyPhoto[]) => void;
}) {
  const inputId = useId();
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [removing, setRemoving] = useState<string | null>(null);
  const [error, setError] = useState("");
  const photos = property.photos;
  const located = photos.filter((p) => p.latitude != null).length;
  const room = MAX_PROPERTY_PHOTOS - photos.length;

  async function addFiles(files: File[]) {
    setError("");
    const picked = files.slice(0, room);
    if (files.length > room) {
      setError(
        `You can add ${room} more photo${room === 1 ? "" : "s"} (${MAX_PROPERTY_PHOTOS} at most).`,
      );
    }
    let current = photos;
    for (const file of picked) {
      const problem = uploadProblem(file, "photo");
      if (problem) {
        setUploads((u) => [...u, { name: file.name, state: "failed", message: problem }]);
        continue;
      }
      setUploads((u) => [
        ...u.filter((x) => x.name !== file.name),
        { name: file.name, state: "uploading" },
      ]);
      try {
        const metadata = await readPhotoMetadata(file);
        const { mediaId } = await uploadFile(file, "photo");
        const photo = await unwrap(
          api.POST("/api/v1/properties/{property_id}/photos/", {
            params: { path: { property_id: property.id } },
            body: { media_id: mediaId, ...metadata },
          }),
        );
        current = [...current, photo];
        onChange(current);
        setUploads((u) => u.filter((x) => x.name !== file.name));
      } catch (err) {
        setUploads((u) =>
          u.map((x) =>
            x.name === file.name ? { ...x, state: "failed", message: describeError(err) } : x,
          ),
        );
      }
    }
  }

  async function remove(photo: PropertyPhoto) {
    setRemoving(photo.id);
    setError("");
    try {
      await unwrap(
        api.DELETE("/api/v1/properties/{property_id}/photos/{photo_id}/", {
          params: { path: { property_id: property.id, photo_id: photo.id } },
        }),
      );
      onChange(photos.filter((p) => p.id !== photo.id));
    } catch (err) {
      setError(describeError(err));
    } finally {
      setRemoving(null);
    }
  }

  return (
    <section className="panel stack" aria-labelledby={`${inputId}-title`}>
      <div className="panel__header">
        <h2 id={`${inputId}-title`} className="panel__title">
          Photos
        </h2>
        <p className="field__hint">
          {photos.length} of {MAX_PROPERTY_PHOTOS} · {located} with a location. Verification needs{" "}
          {MIN_VERIFICATION_PHOTOS} photos taken at the property with location turned on.
        </p>
      </div>

      {photos.length ? (
        <ul className="photo-grid">
          {photos.map((photo, index) => (
            <li key={photo.id} className="photo-grid__item">
              {photo.thumb_url || photo.url ? (
                // Signed storage URLs: next/image can't optimise them.
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={photo.thumb_url || photo.url || undefined}
                  alt={photo.caption || `Property photo ${index + 1}`}
                  className="photo-grid__img"
                  loading="lazy"
                />
              ) : (
                <div className="photo-grid__placeholder">Processing…</div>
              )}
              <div className="photo-grid__meta">
                {photo.latitude != null ? (
                  <Chip tone="success">Location found</Chip>
                ) : (
                  <Chip tone="warning">No location</Chip>
                )}
                <Button
                  variant="ghost"
                  onClick={() => void remove(photo)}
                  busy={removing === photo.id}
                  busyLabel="Removing…"
                  aria-label={`Remove photo ${index + 1}`}
                >
                  Remove
                </Button>
              </div>
            </li>
          ))}
        </ul>
      ) : null}

      {uploads.length ? (
        <ul className="upload-list" aria-live="polite">
          {uploads.map((u) => (
            <li key={u.name} className={u.state === "failed" ? "field__error" : undefined}>
              {u.state === "uploading" ? `Uploading ${u.name}…` : u.message}
            </li>
          ))}
        </ul>
      ) : null}

      {room > 0 ? (
        <div className="file-picker">
          <input
            id={inputId}
            className="visually-hidden file-picker__input"
            type="file"
            accept="image/jpeg,image/png,image/webp"
            multiple
            onChange={(e) => {
              const files = Array.from(e.target.files ?? []);
              e.target.value = "";
              if (files.length) void addFiles(files);
            }}
          />
          <label htmlFor={inputId} className="button button--secondary">
            Add photos
          </label>
          <p className="field__hint">JPEG, PNG or WebP, up to 10 MB each.</p>
        </div>
      ) : null}
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}
