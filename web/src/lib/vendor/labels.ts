import type {
  Amenity,
  ApplicationStatus,
  BadgeKind,
  CompensationModel,
  DeliverableType,
  GigStatus,
  IdDocumentType,
  Language,
  Meals,
  PropertyType,
  RequiredVerification,
  RoleTemplate,
  StayType,
  StipendPeriod,
  VerificationStatus,
} from "@/lib/api/types";

/**
 * Labels for the API's enums, typed as Record<Enum, …> so a value added to or removed
 * from the OpenAPI schema fails `tsc` until it's listed here.
 */

export const PROPERTY_TYPE_LABELS: Record<PropertyType, string> = {
  hostel: "Hostel",
  homestay: "Homestay",
  cafe: "Café",
  hotel: "Hotel",
  trek_operator: "Trek operator",
};

export const AMENITY_LABELS: Record<Amenity, string> = {
  wifi: "Wi-Fi",
  hot_water: "Hot water",
  kitchen: "Kitchen",
  common_area: "Common area",
  workspace: "Workspace",
  laundry: "Laundry",
  lockers: "Lockers",
  breakfast: "Breakfast",
  air_conditioning: "Air conditioning",
  power_backup: "Power backup",
  parking: "Parking",
  cctv: "CCTV",
  first_aid: "First aid kit",
  female_dorm: "Women-only dorm",
  pet_friendly: "Pet friendly",
};

export const VERIFICATION_STATUS_LABELS: Record<VerificationStatus, string> = {
  not_started: "Not started",
  submitted: "Submitted",
  in_review: "In review",
  approved: "Verified",
  rejected: "Not approved",
  changes_requested: "Changes requested",
  expired: "Expired",
};

export const BADGE_LABELS: Record<BadgeKind, string> = {
  id_verified: "ID verified",
  property_verified: "Property verified",
  licence_verified: "Licence verified",
  social_verified: "Social verified",
  reference_checked: "Reference checked",
  trusted_member: "Trusted member",
};

export const ID_DOCUMENT_LABELS: Record<IdDocumentType, string> = {
  aadhaar: "Aadhaar",
  passport: "Passport",
  driving_licence: "Driving licence",
  voter_id: "Voter ID",
};

export const GIG_STATUS_LABELS: Record<GigStatus, string> = {
  draft: "Draft",
  in_review: "In review",
  live: "Live",
  paused: "Paused",
  filled: "Filled",
  closed: "Closed",
  archived: "Archived",
};

export const ROLE_TEMPLATE_LABELS: Record<RoleTemplate, string> = {
  volunteer: "Volunteer",
  content_creator: "Content creator",
  trip_leader: "Trip leader",
  specialist: "Specialist",
};

/** The pay models as the gig builder offers them (titles from the design canvas). */
export const COMPENSATION_MODELS: Record<
  CompensationModel,
  { badge: string; title: string; text: string }
> = {
  volunteer: {
    badge: "Volunteer",
    title: "Work for stay",
    text: "Hours in exchange for bed and meals",
  },
  barter: {
    badge: "Barter",
    title: "Content for stay",
    text: "Set deliverables for a set number of nights",
  },
  hybrid: {
    badge: "Hybrid",
    title: "Stay plus stipend",
    text: "Stipend is held in escrow until approval",
  },
  paid: { badge: "Paid", title: "Paid", text: "Fee or stipend only, paid through escrow" },
};

export const STAY_TYPE_LABELS: Record<StayType, string> = {
  none: "No stay",
  dorm_bed: "Dorm bed",
  shared_room: "Shared room",
  private_room: "Private room",
  tent: "Tent / camping",
};

export const MEALS_LABELS: Record<Meals, string> = {
  none: "No meals",
  breakfast: "Breakfast",
  two_meals: "Two meals a day",
  all_meals: "All meals",
};

export const STIPEND_PERIOD_LABELS: Record<StipendPeriod, string> = {
  total: "For the whole gig",
  per_week: "Per week",
  per_month: "Per month",
};

export const DELIVERABLE_LABELS: Record<DeliverableType, string> = {
  instagram_post: "Instagram post",
  instagram_reel: "Instagram reel",
  instagram_story: "Instagram story",
  youtube_video: "YouTube video",
  blog_post: "Blog post",
  photo_set: "Edited photo set",
  mural: "Mural / artwork",
  other: "Other",
};

export const REQUIRED_VERIFICATION_LABELS: Record<
  RequiredVerification,
  { title: string; text: string }
> = {
  id_verified: { title: "ID verified", text: "Talent who have verified their ID. Recommended." },
  trusted_member: {
    title: "Trusted members only",
    text: "Talent with a verified ID, references and completed gigs.",
  },
  none: { title: "Anyone", text: "No verification needed to apply." },
};

export const LANGUAGE_LABELS: Record<Language, string> = {
  en: "English",
  hi: "Hindi",
  as: "Assamese",
  bn: "Bengali",
  gu: "Gujarati",
  kn: "Kannada",
  kok: "Konkani",
  ml: "Malayalam",
  mr: "Marathi",
  ne: "Nepali",
  or: "Odia",
  pa: "Punjabi",
  ta: "Tamil",
  te: "Telugu",
  ur: "Urdu",
  ar: "Arabic",
  de: "German",
  es: "Spanish",
  fr: "French",
  he: "Hebrew",
  it: "Italian",
  ja: "Japanese",
  ko: "Korean",
  nl: "Dutch",
  pt: "Portuguese",
  ru: "Russian",
  zh: "Chinese",
};

export const APPLICATION_STATUS_LABELS: Record<ApplicationStatus, string> = {
  applied: "Applied",
  shortlisted: "Shortlisted",
  interview: "Interview",
  offered: "Offered",
  withdrawn: "Withdrawn",
  declined: "Declined",
  rejected: "Rejected",
  expired: "Expired",
};

export function options<T extends string>(labels: Record<T, string>) {
  return (Object.keys(labels) as T[]).map((value) => ({ value, label: labels[value] }));
}
