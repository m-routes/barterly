import type { components } from "./schema";

type Schemas = components["schemas"];

export type User = Schemas["User"];
export type Role = Schemas["UserRoleEnum"];
export type SelfServiceRole = Schemas["ChooseRoleRoleEnum"];
export type VendorProfile = Schemas["VendorProfile"];
export type BusinessType = Schemas["BusinessTypeEnum"];
export type IndianState = Schemas["StateEnum"];

/** The exchange response as the browser sees it: the BFF keeps the tokens in cookies. */
export type SignInResult = Omit<Schemas["ExchangeResponse"], "access" | "refresh">;

export type Property = Schemas["Property"];
export type PropertyType = Schemas["PropertyTypeEnum"];
export type Amenity = Schemas["AmenitiesEnum"];
export type PropertyPhoto = Schemas["Photo"];
export type VerificationStatus = Schemas["VerificationStatusEnum"];
export type GeocodeResult = Schemas["GeocodeResponse"];
export type MediaKind = Schemas["KindEnum"];
export type UploadContentType = Schemas["ContentTypeEnum"];
export type MyVerification = Schemas["MyVerification"];
export type VerificationCase = Schemas["Case"];
export type CheckSummary = Schemas["CheckSummary"];
export type BadgeKind = Schemas["BadgeKindEnum"];
export type IdDocumentType = Schemas["IdDocumentTypeEnum"];

export type Gig = Schemas["Gig"];
export type GigStatus = Schemas["GigStatusEnum"];
export type RoleTemplate = Schemas["RoleTemplateEnum"];
export type CompensationModel = Schemas["CompensationModelEnum"];
export type StayType = Schemas["StayTypeEnum"];
export type Meals = Schemas["MealsEnum"];
export type StipendPeriod = Schemas["StipendPeriodEnum"];
export type Deliverable = Schemas["Deliverable"];
export type DeliverableType = Schemas["DeliverableTypeEnum"];
export type Language = Schemas["LanguagesEnum"];
export type RequiredVerification = Schemas["RequiredVerificationEnum"];
export type Skill = Schemas["Skill"];

export type ApplicationListItem = Schemas["ApplicationListItem"];
export type Application = Schemas["Application"];
export type ApplicationStatus = Schemas["ApplicationStatusEnum"];

export type Terms = Schemas["Terms"];
export type CancellationPolicy = Schemas["CancellationPolicyEnum"];
export type UsageScope = Schemas["ScopeEnum"];
export type Offer = Schemas["Offer"];
export type OfferThread = Schemas["OfferThread"];
export type Agreement = Schemas["Agreement"];
export type AgreementVersion = Schemas["AgreementVersion"];
export type AgreementListItem = Schemas["AgreementListItem"];
export type SignChallenge = Schemas["Challenge"];
export type Party = Schemas["PartyEnum"];
export type OfferStatus = Schemas["OfferStatusEnum"];
export type BookingStatus = Schemas["BookingStatusEnum"];
export type Booking = Schemas["Booking"];
export type CancelPreview = Schemas["CancelPreview"];
export type CancellationReason = Schemas["CancellationReasonEnum"];
export type Unlocked = Schemas["Unlocked"];
export type Reliability = Schemas["Reliability"];

export type AppNotification = Schemas["Notification"];
export type NotificationPreferences = Schemas["Preferences"];
export type NotificationChannel = Schemas["NotificationChannelEnum"];
export type NotificationPreferenceChange = Schemas["PreferenceChange"];

/**
 * A request body for an endpoint whose schema reuses its response shape: the generated
 * types mark the server-filled fields (id, created_at, ...) as required there too.
 */
export type RequestBody<T, K extends keyof T> = Pick<T, K>;
export function requestBody<T>(body: Partial<T>): T {
  return body as T;
}

export type BillingPlan = Schemas["Plan"];
export type BillingOverview = Schemas["BillingOverview"];
export type BillingSubscription = Schemas["Subscription"];
export type Invoice = Schemas["Invoice"];

export type Arrivals = Schemas["Arrivals"];
export type Arrival = Schemas["Arrival"];
export type InHouse = Schemas["InHouse"];
export type CheckInRequest = Schemas["CheckInRequest"];
export type SyncResult = Schemas["SyncResult"];
export type PendingHourLog = Schemas["PendingHourLog"];

export type TrackedDeliverable = Schemas["TrackedDeliverable"];
export type LibraryItem = Schemas["LibraryItem"];
export type PostStats = Schemas["PostStats"];

export type StayReview = Schemas["StayReview"];
export type BookingReviews = Schemas["BookingReviews"];
export type Reputation = Schemas["Reputation"];
export type ReportReason = Schemas["ReportReasonEnum"];
