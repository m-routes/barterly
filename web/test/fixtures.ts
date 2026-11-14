/** API objects for tests, shaped by the generated types so schema changes break them. */
import type {
  Application,
  ApplicationListItem,
  Gig,
  MyVerification,
  Property,
  PropertyPhoto,
  VendorProfile,
} from "@/lib/api/types";

export const photo = (overrides: Partial<PropertyPhoto> = {}): PropertyPhoto => ({
  id: `ph-${Math.random().toString(36).slice(2, 8)}`,
  media_id: "m1",
  status: "ready",
  position: 0,
  caption: "",
  latitude: "15.552700",
  longitude: "73.751700",
  captured_at: null,
  url: "https://storage.example/photo.jpg",
  thumb_url: "https://storage.example/thumb.jpg",
  ...overrides,
});

export const property: Property = {
  id: "11111111-0000-4000-8000-000000000001",
  name: "Sea Salt Homestay",
  property_type: "homestay",
  address: "12 Beach Road",
  city: "Palolem",
  state: "Goa",
  pincode: "403702",
  latitude: "15.552700",
  longitude: "73.751700",
  location_confirmed: true,
  amenities: ["wifi"],
  house_rules: [],
  women_friendly: false,
  verification_status: "not_started",
  photos: [],
  created_at: "2026-11-01T10:00:00Z",
  updated_at: "2026-11-01T10:00:00Z",
};

export const vendorProfile: VendorProfile = {
  id: "v1",
  business_name: "Sea Salt",
  business_type: "homestay",
  contact_name: "Asha",
  city: "Palolem",
  state: "Goa",
  about: "By the beach.",
  address: "",
  gstin: "",
  website: "",
  profile_complete: true,
  missing_fields: [],
  created_at: "2026-11-01T10:00:00Z",
  updated_at: "2026-11-01T10:00:00Z",
};

export const verification: MyVerification = {
  checks: [
    {
      check_type: "id_selfie",
      label: "ID and selfie",
      required: true,
      badge: "id_verified",
      cases: [],
    },
    {
      check_type: "business_registration",
      label: "Business registration",
      required: false,
      badge: "licence_verified",
      cases: [],
    },
    {
      check_type: "property",
      label: "Property",
      required: true,
      badge: "property_verified",
      cases: [],
    },
  ],
  badges: [],
  trusted_member: false,
};

export const gig: Gig = {
  id: "22222222-0000-4000-8000-000000000001",
  property: property.id,
  title: "Reception and social media volunteer",
  description: "Front desk mornings.",
  role_template: "volunteer",
  compensation_model: "volunteer",
  start_date: "2026-12-12",
  end_date: "2027-01-12",
  duration_days: null,
  apply_by: "2026-12-05",
  slots: 2,
  hours_per_day: 4,
  days_per_week: 5,
  stay_type: "dorm_bed",
  meals: "all_meals",
  wifi: true,
  stipend_amount: null,
  stipend_period: "",
  deliverables: [],
  skills: [],
  min_age: 18,
  languages: ["en", "hi"],
  min_followers: null,
  min_stay_days: 14,
  screening_questions: ["Can you commit to the full dates?"],
  required_verification: "id_verified",
  status: "draft",
  status_reason: "",
  submitted_at: null,
  published_at: null,
  closed_at: null,
  created_at: "2026-11-01T10:00:00Z",
  updated_at: "2026-11-01T10:00:00Z",
};

export const applicant = (overrides: Partial<ApplicationListItem> = {}): ApplicationListItem => ({
  id: "33333333-0000-4000-8000-000000000001",
  gig: gig.id,
  gig_title: gig.title,
  status: "applied",
  proposed_start: "2026-12-12",
  proposed_end: "2027-01-05",
  applicant: {
    user_id: "u2",
    display_name: "Aarav Mehta",
    talent_type: "Volunteer traveller",
    home_city: "Pune",
    bio: "Front desk in Manali last winter.",
    languages: ["en", "hi"],
    skills: ["reception"],
    instagram_followers: 1200,
    badges: ["id_verified"],
  },
  fit: { score: 92, breakdown: {} },
  attachment_count: 1,
  applied_at: "2026-11-10T10:00:00Z",
  ...overrides,
});

export const application: Application = {
  ...applicant(),
  status_reason: "",
  pitch: "I ran the desk at a hostel in Manali.",
  answers: [{ question: "Can you commit to the full dates?", answer: "Yes." }],
  attachments: [
    {
      id: "a1",
      kind: "link",
      title: "Portfolio",
      url: "https://example.org/portfolio",
      thumb_url: null,
    },
  ],
  fit: {
    score: 92,
    breakdown: {
      skill_match: {
        value: 1,
        weight: 30,
        points: 30,
        neutral: false,
        reason: "1 of 1 skills match.",
      },
      reliability: { value: 0.5, weight: 20, points: 10, neutral: true, reason: "" },
    },
  },
  decided_at: null,
};

export function page<T>(results: T[], count = results.length) {
  return { count, next: null, previous: null, results };
}
