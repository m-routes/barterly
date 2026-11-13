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
