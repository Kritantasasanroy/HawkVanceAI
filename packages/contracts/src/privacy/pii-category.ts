import { z } from 'zod';

export const piiCategorySchema = z.enum([
  'apiKey',
  'accessToken',
  'password',
  'privateKey',
  'connectionString',
  'credentialInUrl',
  'email',
  'phone',
  'creditCard',
  'bankAccount',
  'iban',
  'nationalId',
  'ipAddress',
  'person',
  'organization',
  'location',
  'gpe',
  'streetAddress',
  'date',
  'dateOfBirth',
  'monetaryAmount',
  'customRule',
]);
export type PiiCategory = z.infer<typeof piiCategorySchema>;

export const detectorGroupSchema = z.enum([
  'secretsAndCredentials',
  'directIdentifiers',
  'namesOrgsAndPlaces',
  'datesAddressesAndMoney',
  'customRules',
]);
export type DetectorGroup = z.infer<typeof detectorGroupSchema>;

export const detectorKindSchema = z.enum(['regex', 'checksum', 'entropy', 'ner', 'customRule']);
export type DetectorKind = z.infer<typeof detectorKindSchema>;

export const redactionDispositionSchema = z.enum(['autoRedact', 'needsReview', 'ignored']);
export type RedactionDisposition = z.infer<typeof redactionDispositionSchema>;

export const detectorGroupSelectionSchema = z.object({
  secretsAndCredentials: z.boolean().default(true),
  directIdentifiers: z.boolean().default(true),
  namesOrgsAndPlaces: z.boolean().default(true),
  datesAddressesAndMoney: z.boolean().default(true),
  customRules: z.boolean().default(true),
});
export type DetectorGroupSelection = z.infer<typeof detectorGroupSelectionSchema>;
