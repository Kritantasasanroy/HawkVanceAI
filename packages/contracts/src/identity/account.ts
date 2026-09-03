import { z } from 'zod';
import { accountIdSchema, byteCountSchema, requestCountSchema, tokenCountSchema } from '../common/identifier.js';

export const accountStatusSchema = z.enum(['pending', 'active', 'suspended', 'deleted']);
export type AccountStatus = z.infer<typeof accountStatusSchema>;

export const accountRoleSchema = z.enum(['member', 'support', 'analyst', 'admin', 'superAdmin']);
export type AccountRole = z.infer<typeof accountRoleSchema>;

export const planTierSchema = z.enum(['free', 'beta', 'pro', 'enterprise']);
export type PlanTier = z.infer<typeof planTierSchema>;

export const modelTierSchema = z.enum(['economy', 'standard', 'premium']);
export type ModelTier = z.infer<typeof modelTierSchema>;

export const planLimitsSchema = z.object({
  dailyRequests: requestCountSchema,
  monthlyRequests: requestCountSchema,
  monthlyTokens: tokenCountSchema,
  storageBytes: byteCountSchema,
  maxWorkspaces: z.number().int().nonnegative(),
  memoryRetentionDays: z.number().int().positive(),
  byokAllowed: z.boolean(),
  allowedModelTiers: z.array(modelTierSchema).nonempty(),
  /// The allowance the interface reports and enforces. Requests and tokens remain as a backstop.
  monthlyCredits: z.number().int().nonnegative(),
});
export type PlanLimits = z.infer<typeof planLimitsSchema>;

export const accountSchema = z.object({
  id: accountIdSchema,
  email: z.string().email(),
  displayName: z.string().min(1).max(120),
  occupation: z.string().max(120).nullable(),
  /// Null until the person has been asked for their name and occupation, which is what tells the
  /// desktop app to show that step rather than guessing from an empty name.
  onboardedAt: z.string().datetime().nullable(),
  status: accountStatusSchema,
  role: accountRoleSchema,
  plan: planTierSchema,
  createdAt: z.string().datetime(),
  lastSeenAt: z.string().datetime(),
});
export type Account = z.infer<typeof accountSchema>;

/// What a person may change about themselves. Deliberately not the whole account: plan, role and
/// status are ours to set, and a profile edit must not be a route to changing them.
export const profileUpdateSchema = z
  .object({
    displayName: z.string().min(1).max(120).optional(),
    occupation: z.string().max(120).nullable().optional(),
  })
  .refine(
    (fields) => fields.displayName !== undefined || fields.occupation !== undefined,
    { message: 'Nothing to update.' },
  );
export type ProfileUpdate = z.infer<typeof profileUpdateSchema>;

export const adminRoleSchema = z.enum(['support', 'analyst', 'admin', 'superAdmin']);
export type AdminRole = z.infer<typeof adminRoleSchema>;
