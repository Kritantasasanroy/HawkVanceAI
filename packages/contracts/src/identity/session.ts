import { z } from 'zod';
import { deviceIdSchema } from '../common/identifier.js';

export const devicePlatformSchema = z.enum(['windows', 'macos', 'linux', 'web']);
export type DevicePlatform = z.infer<typeof devicePlatformSchema>;

export const deviceRegistrationSchema = z.object({
  name: z.string().min(1).max(120),
  platform: devicePlatformSchema,
  appVersion: z.string().min(1).max(40),
});
export type DeviceRegistration = z.infer<typeof deviceRegistrationSchema>;

export const deviceSchema = z.object({
  id: deviceIdSchema,
  name: z.string(),
  platform: devicePlatformSchema,
  appVersion: z.string(),
  firstSeenAt: z.string().datetime(),
  lastSeenAt: z.string().datetime(),
});
export type Device = z.infer<typeof deviceSchema>;
