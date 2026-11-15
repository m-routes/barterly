import type { MediaKind } from "@/lib/api/types";

const MB = 1024 * 1024;

/** Mirrors backend apps/chat/services.py: photos or PDFs, 10 MB each, 3 per message. */
export const CHAT_ATTACHMENTS = {
  images: ["image/jpeg", "image/png", "image/webp"],
  documents: ["application/pdf"],
  maxBytes: 10 * MB,
  maxCount: 3,
} as const;

export const CHAT_ACCEPT = [...CHAT_ATTACHMENTS.images, ...CHAT_ATTACHMENTS.documents].join(",");

/** The upload kind for a chat attachment. */
export function chatMediaKind(file: File): MediaKind {
  return (CHAT_ATTACHMENTS.images as readonly string[]).includes(file.type) ? "photo" : "document";
}

/** Why these files can't be attached, or null when they can. */
export function attachmentProblem(files: File[], alreadyAttached = 0): string | null {
  if (files.length + alreadyAttached > CHAT_ATTACHMENTS.maxCount) {
    return `Attach at most ${CHAT_ATTACHMENTS.maxCount} files.`;
  }
  const allowed: readonly string[] = [...CHAT_ATTACHMENTS.images, ...CHAT_ATTACHMENTS.documents];
  for (const file of files) {
    if (!allowed.includes(file.type))
      return `${file.name}: send a photo (JPEG, PNG, WebP) or a PDF.`;
    if (file.size === 0) return `${file.name} is empty.`;
    if (file.size > CHAT_ATTACHMENTS.maxBytes) return `${file.name} is over 10 MB.`;
  }
  return null;
}
