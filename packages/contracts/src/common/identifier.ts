import { z } from 'zod';

export type Branded<TName extends string> = string & { readonly __brand: TName };

export type AccountId = Branded<'AccountId'>;
export type DeviceId = Branded<'DeviceId'>;
export type SessionId = Branded<'SessionId'>;
export type SessionFamilyId = Branded<'SessionFamilyId'>;
export type OtpChallengeId = Branded<'OtpChallengeId'>;
export type WorkspaceId = Branded<'WorkspaceId'>;
export type DocumentId = Branded<'DocumentId'>;
export type MemoryId = Branded<'MemoryId'>;
export type ContextPackId = Branded<'ContextPackId'>;
export type UsageRecordId = Branded<'UsageRecordId'>;

export type NumericBrand<TName extends string> = number & { readonly __numericBrand: TName };

export type TokenCount = NumericBrand<'TokenCount'>;
export type RequestCount = NumericBrand<'RequestCount'>;
export type CostMicros = NumericBrand<'CostMicros'>;
export type ByteCount = NumericBrand<'ByteCount'>;

export const uuidSchema = z.string().uuid();

export const accountIdSchema = uuidSchema.transform((value) => value as AccountId);
export const deviceIdSchema = uuidSchema.transform((value) => value as DeviceId);
export const sessionIdSchema = uuidSchema.transform((value) => value as SessionId);
export const sessionFamilyIdSchema = uuidSchema.transform((value) => value as SessionFamilyId);
export const otpChallengeIdSchema = uuidSchema.transform((value) => value as OtpChallengeId);
export const workspaceIdSchema = uuidSchema.transform((value) => value as WorkspaceId);
export const documentIdSchema = uuidSchema.transform((value) => value as DocumentId);
export const memoryIdSchema = uuidSchema.transform((value) => value as MemoryId);

export const tokenCountSchema = z
  .number()
  .int()
  .nonnegative()
  .transform((value) => value as TokenCount);

export const requestCountSchema = z
  .number()
  .int()
  .nonnegative()
  .transform((value) => value as RequestCount);

export const costMicrosSchema = z
  .number()
  .int()
  .nonnegative()
  .transform((value) => value as CostMicros);

export const byteCountSchema = z
  .number()
  .int()
  .nonnegative()
  .transform((value) => value as ByteCount);
