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
