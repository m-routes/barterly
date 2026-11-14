import { api, unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { MediaKind, UploadContentType } from "@/lib/api/types";

/**
 * Uploads go straight from the browser to Cloud Storage with a signed URL:
 * ask the API for the URL, PUT the file, then confirm so the API checks it.
 */

const MB = 1024 * 1024;

/** Mirrors backend apps/media/policy.py RULES. */
export const UPLOAD_RULES: Record<
  MediaKind,
  { types: readonly UploadContentType[]; maxBytes: number }
> = {
  avatar: { types: ["image/jpeg", "image/png", "image/webp"], maxBytes: 5 * MB },
  photo: { types: ["image/jpeg", "image/png", "image/webp"], maxBytes: 10 * MB },
  video: { types: ["video/mp4"], maxBytes: 100 * MB },
  document: { types: ["application/pdf", "image/jpeg", "image/png"], maxBytes: 10 * MB },
};

/** Why this file can't be uploaded as `kind`, or null when it can. */
export function uploadProblem(file: File, kind: MediaKind): string | null {
  const rule = UPLOAD_RULES[kind];
  if (!(rule.types as readonly string[]).includes(file.type)) {
    return `${file.name}: use a JPEG, PNG or WebP image.`;
  }
  if (file.size === 0) return `${file.name} is empty.`;
  if (file.size > rule.maxBytes) {
    return `${file.name} is over ${rule.maxBytes / MB} MB. Use a smaller photo.`;
  }
  return null;
}

export async function uploadFile(file: File, kind: MediaKind): Promise<{ mediaId: string }> {
  const problem = uploadProblem(file, kind);
  if (problem) throw new ApiError({ status: 400, code: "invalid_file", message: problem });

  const target = await unwrap(
    api.POST("/api/v1/media/upload-url/", {
      body: { kind, content_type: file.type as UploadContentType, size_bytes: file.size },
    }),
  );
  let stored: Response;
  try {
    stored = await fetch(target.upload_url, {
      method: target.method,
      headers: target.headers as Record<string, string>,
      body: file,
    });
  } catch {
    throw new ApiError({
      status: 0,
      code: "upload_failed",
      message: `${file.name} didn't upload. Check your connection and try again.`,
    });
  }
  if (!stored.ok) {
    throw new ApiError({
      status: stored.status,
      code: "upload_failed",
      message: `${file.name} didn't upload. Try again.`,
    });
  }
  await unwrap(api.POST("/api/v1/media/confirm/", { body: { media_id: target.media_id } }));
  return { mediaId: target.media_id };
}

export type PhotoMetadata = {
  latitude?: string;
  longitude?: string;
  captured_at?: string;
};

/**
 * Where and when a photo was taken, from its EXIF data, as the API wants it.
 * Property verification needs photos taken near the pin. Missing data is fine.
 */
export async function readPhotoMetadata(file: File): Promise<PhotoMetadata> {
  if (file.type !== "image/jpeg" && file.type !== "image/webp" && file.type !== "image/png") {
    return {};
  }
  try {
    const exifr = (await import("exifr")).default;
    const [gps, tags] = await Promise.all([
      exifr.gps(file).catch(() => undefined),
      exifr.parse(file, ["DateTimeOriginal"]).catch(() => undefined),
    ]);
    const result: PhotoMetadata = {};
    if (gps && Number.isFinite(gps.latitude) && Number.isFinite(gps.longitude)) {
      result.latitude = gps.latitude.toFixed(6);
      result.longitude = gps.longitude.toFixed(6);
    }
    const taken: unknown = tags?.DateTimeOriginal;
    if (taken instanceof Date && !Number.isNaN(taken.getTime())) {
      result.captured_at = taken.toISOString();
    }
    return result;
  } catch {
    return {};
  }
}
