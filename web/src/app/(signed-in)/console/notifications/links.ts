/** A notification's web link as an in-app path when it points at this console. */
export function consolePath(webUrl: string): string | null {
  try {
    const url = new URL(webUrl);
    return url.pathname.startsWith("/console") ? `${url.pathname}${url.search}` : null;
  } catch {
    return null;
  }
}
