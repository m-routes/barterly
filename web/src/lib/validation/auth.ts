import { z } from "zod";

/**
 * Indian mobile numbers only for now: 10 digits starting 6-9, with an optional
 * +91 / 91 / 0 prefix, spaces or dashes. Normalised to E.164 (+91XXXXXXXXXX).
 */
const INDIAN_MOBILE = /^[6-9]\d{9}$/;

export function normalizeIndianMobile(input: string): string | null {
  let digits = input.replace(/[\s\-()]/g, "");
  if (digits.startsWith("+91")) digits = digits.slice(3);
  else if (digits.length === 12 && digits.startsWith("91")) digits = digits.slice(2);
  else if (digits.length === 11 && digits.startsWith("0")) digits = digits.slice(1);
  return INDIAN_MOBILE.test(digits) ? `+91${digits}` : null;
}

export const phoneSchema = z.object({
  phone: z
    .string()
    .trim()
    .min(1, "Enter your mobile number.")
    .refine((value) => normalizeIndianMobile(value) !== null, {
      message: "Enter a 10-digit Indian mobile number.",
    }),
});
export type PhoneForm = z.infer<typeof phoneSchema>;

export const otpSchema = z.object({
  code: z
    .string()
    .trim()
    .regex(/^\d{6}$/, "Enter the 6-digit code we sent you."),
});
export type OtpForm = z.infer<typeof otpSchema>;

export const roleSchema = z.object({
  role: z.enum(["vendor", "talent"], { message: "Choose how you'll use Barterly." }),
});
export type RoleForm = z.infer<typeof roleSchema>;
