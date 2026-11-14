import type {
  BadgeKind,
  CheckSummary,
  MyVerification,
  Property,
  VendorProfile,
  VerificationCase,
  VerificationStatus,
} from "@/lib/api/types";
import { MIN_VERIFICATION_PHOTOS } from "@/lib/validation/property";

export type ChecklistStep = {
  id: "business" | "property" | "photos" | "kyc" | "verified";
  title: string;
  description: string;
  done: boolean;
  href: string;
  action: string;
};

export type ChecklistInput = {
  profile: VendorProfile | null;
  properties: Property[];
  verification: MyVerification;
};

/** The newest case of a check (by when it was submitted or last reviewed). */
export function latestCase(check: CheckSummary | undefined): VerificationCase | undefined {
  if (!check?.cases.length) return undefined;
  const when = (c: VerificationCase) => c.reviewed_at ?? c.submitted_at ?? "";
  return [...check.cases].sort((a, b) => when(b).localeCompare(when(a)))[0];
}

export function checkStatus(check: CheckSummary | undefined): VerificationStatus {
  return latestCase(check)?.status ?? "not_started";
}

export function hasBadge(verification: MyVerification, kind: BadgeKind): boolean {
  return verification.badges.some((b) => b.kind === kind);
}

function pinned(p: Property): boolean {
  return p.latitude != null && p.longitude != null && Boolean(p.location_confirmed);
}

/**
 * The vendor's getting-started list, in order. Each step says what to do next and
 * links to where it's done; finished steps stay listed as done.
 */
export function buildChecklist({
  profile,
  properties,
  verification,
}: ChecklistInput): ChecklistStep[] {
  const withPin = properties.find(pinned);
  const first = withPin ?? properties[0];
  const photographed = properties.find(
    (p) => p.photos.filter((photo) => photo.latitude != null).length >= MIN_VERIFICATION_PHOTOS,
  );
  const idCheck = verification.checks.find((c) => c.check_type === "id_selfie");
  const idStarted = checkStatus(idCheck) !== "not_started";
  const propertyVerified = properties.some((p) => p.verification_status === "approved");
  const idVerified = hasBadge(verification, "id_verified");

  return [
    {
      id: "business",
      title: "Business details",
      description: "Your business name, type and where you are. Talent see this first.",
      done: Boolean(profile?.profile_complete),
      href: "/onboarding/vendor",
      action: profile?.profile_complete ? "Edit details" : "Add details",
    },
    {
      id: "property",
      title: "Your property on the map",
      description: "Add the property and put the pin on its entrance.",
      done: Boolean(withPin),
      href: first ? `/console/properties/${first.id}` : "/console/properties/new",
      action: withPin ? "View property" : first ? "Place the pin" : "Add a property",
    },
    {
      id: "photos",
      title: "Property photos",
      description: `At least ${MIN_VERIFICATION_PHOTOS} photos taken at the property, with location turned on.`,
      done: Boolean(photographed),
      href: first ? `/console/properties/${(photographed ?? first).id}` : "/console/properties/new",
      action: "Add photos",
    },
    {
      id: "kyc",
      title: "Start your ID check",
      description: "A quick ID and selfie check with our verification partner.",
      done: idStarted,
      href: "/console/verification",
      action: idStarted ? "See status" : "Start ID check",
    },
    {
      id: "verified",
      title: "Get verified",
      description: "Verified hosts get a badge on every gig and rank higher for talent.",
      done: idVerified && propertyVerified,
      href: "/console/verification",
      action: "See verification",
    },
  ];
}
