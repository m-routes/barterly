import type { Role, User } from "@/lib/api/types";

/** Where a signed-in person belongs, given who they are. */
export function homeFor(
  user: Pick<User, "role" | "profile_complete"> & { needs_consent?: boolean },
): string {
  // Terms or privacy policy changed (or were never accepted): ask before anything else.
  if (user.role && user.needs_consent) return "/onboarding/consent";
  switch (user.role) {
    case "vendor":
      return user.profile_complete ? "/console" : "/onboarding/vendor";
    case "talent":
      return "/talent";
    case "admin":
      // Admins work in the Django admin; the console explains that to them.
      return "/console";
    default:
      return "/onboarding/role";
  }
}

export type Access =
  { kind: "allow" } | { kind: "redirect"; to: string } | { kind: "forbidden"; role: Role };

/**
 * May this user see a page meant for `role`?
 *
 * - No role yet: they pick one first.
 * - Wrong role: forbidden (the page explains, rather than bouncing them around).
 * - A vendor page that needs a complete profile sends them to finish it.
 */
export function accessFor(
  user: Pick<User, "role" | "profile_complete"> & { needs_consent?: boolean },
  role: Role,
  options: { requireComplete?: boolean } = {},
): Access {
  if (!user.role) return { kind: "redirect", to: "/onboarding/role" };
  if (user.needs_consent) return { kind: "redirect", to: "/onboarding/consent" };
  if (user.role !== role) return { kind: "forbidden", role: user.role };
  if (options.requireComplete && !user.profile_complete) {
    return { kind: "redirect", to: homeFor(user) };
  }
  return { kind: "allow" };
}

/**
 * The `next` query value if it is a path on this site, else null.
 * Guards against open redirects such as `//evil.example` or `https://…`.
 */
export function safeNextPath(next: string | null | undefined): string | null {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) {
    return null;
  }
  if (next.startsWith("/login") || next.startsWith("/api/")) return null;
  return next;
}
