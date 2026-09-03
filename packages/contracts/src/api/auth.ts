import { z } from 'zod';
import { accountSchema, planLimitsSchema } from '../identity/account.js';
import { deviceIdSchema } from '../common/identifier.js';
import { deviceSchema } from '../identity/session.js';

/// Everything HawkVance's own API returns behind a Neon Auth bearer token.
///
/// The OTP exchange itself is NOT modelled here: the desktop app talks to Neon Auth directly, so
/// codes and session tokens never traverse a HawkVance endpoint and have no HawkVance wire type.

export const currentAccountSchema = z.object({
  account: accountSchema,
  limits: planLimitsSchema,
});
export type CurrentAccount = z.infer<typeof currentAccountSchema>;

export const deviceRegisteredSchema = z.object({
  deviceId: deviceIdSchema,
});
export type DeviceRegistered = z.infer<typeof deviceRegisteredSchema>;

export const deviceListSchema = z.object({
  devices: z.array(deviceSchema),
});
export type DeviceList = z.infer<typeof deviceListSchema>;

export const apiErrorSchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    retryAfterSeconds: z.number().int().nonnegative().optional(),
  }),
});
export type ApiError = z.infer<typeof apiErrorSchema>;

// ---------------------------------------------------------------------------
// Neon Auth wire shapes. Modelled so the desktop client is typed end to end,
// even though these requests go to Neon rather than to HawkVance.
// ---------------------------------------------------------------------------

export const otpPurposeSchema = z.enum([
  'sign-in',
  'email-verification',
  'forget-password',
  'change-email',
]);
export type OtpPurpose = z.infer<typeof otpPurposeSchema>;

export const otpCodeSchema = z
  .string()
  .trim()
  .regex(/^\d{6}$/, 'The code is six digits. Check the email and try again.');

export const sendOtpRequestSchema = z.object({
  email: z.string().email(),
  type: otpPurposeSchema.default('sign-in'),
});
export type SendOtpRequest = z.infer<typeof sendOtpRequestSchema>;

export const sendOtpAcceptedSchema = z.object({
  success: z.boolean(),
});
export type SendOtpAccepted = z.infer<typeof sendOtpAcceptedSchema>;

export const neonUserSchema = z.object({
  id: z.string(),
  email: z.string().email(),
  name: z.string().nullish(),
  emailVerified: z.boolean().nullish(),
});
export type NeonUser = z.infer<typeof neonUserSchema>;

export const neonSignInSchema = z.object({
  token: z.string().min(1),
  user: neonUserSchema,
});
export type NeonSignIn = z.infer<typeof neonSignInSchema>;

export const neonIdentityTokenSchema = z.object({
  token: z.string().min(1),
});
export type NeonIdentityTokenResponse = z.infer<typeof neonIdentityTokenSchema>;
