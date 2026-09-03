import {
  bigint,
  boolean,
  index,
  integer,
  jsonb,
  pgSchema,
  text,
  timestamp,
  uniqueIndex,
  uuid,
} from 'drizzle-orm/pg-core';

/// HawkVance owns its own schema rather than `public`. Neon Auth already occupies `neon_auth`, and
/// `public` holds tables from an earlier attempt that are deliberately left untouched.
export const hawkvance = pgSchema('hawkvance');

export const accounts = hawkvance.table(
  'accounts',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    /// The `sub` of the Neon Auth identity token. Authentication is Neon's; everything an account
    /// means to HawkVance (plan, quota, workspaces, usage) is ours and hangs off this id.
    neonUserId: text('neon_user_id').notNull(),
    email: text('email').notNull(),
    emailDomain: text('email_domain').notNull(),
    displayName: text('display_name').notNull(),
    /// What the person does, in their own words. Free text rather than a picked category: the list
    /// would never fit everyone, and a wrong category is worse than none.
    occupation: text('occupation'),
    /// Set once the person has been asked for their name and occupation. Null means they have not
    /// been asked yet, which is what triggers that step after their first sign-in.
    onboardedAt: timestamp('onboarded_at', { withTimezone: true }),
    status: text('status').notNull().default('active'),
    role: text('role').notNull().default('member'),
    plan: text('plan').notNull().default('beta'),
    suspendedReason: text('suspended_reason'),
    createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
    lastSeenAt: timestamp('last_seen_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [
    uniqueIndex('accounts_neon_user_unique').on(table.neonUserId),
    uniqueIndex('accounts_email_unique').on(table.email),
    index('accounts_status_idx').on(table.status),
  ],
);

export const devices = hawkvance.table(
  'devices',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    accountId: uuid('account_id')
      .notNull()
      .references(() => accounts.id, { onDelete: 'cascade' }),
    name: text('name').notNull(),
    platform: text('platform').notNull(),
    appVersion: text('app_version').notNull(),
    firstSeenAt: timestamp('first_seen_at', { withTimezone: true }).notNull().defaultNow(),
    lastSeenAt: timestamp('last_seen_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [
    uniqueIndex('devices_account_name_unique').on(table.accountId, table.name, table.platform),
    index('devices_account_idx').on(table.accountId),
  ],
);

export const planLimits = hawkvance.table('plan_limits', {
  tier: text('tier').primaryKey(),
  dailyRequests: integer('daily_requests').notNull(),
  monthlyRequests: integer('monthly_requests').notNull(),
  monthlyTokens: bigint('monthly_tokens', { mode: 'number' }).notNull(),
  /// The allowance a person actually sees and spends. Token and request ceilings stay as a backstop
  /// against a single runaway conversation, but credits are what the interface reports.
  monthlyCredits: integer('monthly_credits').notNull().default(500),
  storageBytes: bigint('storage_bytes', { mode: 'number' }).notNull(),
  maxWorkspaces: integer('max_workspaces').notNull(),
  memoryRetentionDays: integer('memory_retention_days').notNull(),
  byokAllowed: boolean('byok_allowed').notNull(),
  allowedModelTiers: jsonb('allowed_model_tiers').notNull(),
  updatedAt: timestamp('updated_at', { withTimezone: true }).notNull().defaultNow(),
});

/// Append-only. One row per external inference. Quota consumption is derived by summing over a
/// window rather than kept as a mutable counter, so the audit trail survives and nothing races.
export const usageRecords = hawkvance.table(
  'usage_records',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    accountId: uuid('account_id')
      .notNull()
      .references(() => accounts.id, { onDelete: 'restrict' }),
    workspaceId: uuid('workspace_id'),
    occurredAt: timestamp('occurred_at', { withTimezone: true }).notNull().defaultNow(),
    provider: text('provider').notNull(),
    model: text('model').notNull(),
    inputTokens: integer('input_tokens').notNull(),
    outputTokens: integer('output_tokens').notNull(),
    estimatedCostMicros: bigint('estimated_cost_micros', { mode: 'number' }).notNull(),
    latencyMs: integer('latency_ms').notNull(),
    outcome: text('outcome').notNull(),
    /// What the user was charged, as opposed to what the call cost us. Summed the same way as
    /// everything else here, so the balance shown to a person has the same audit trail as the bill.
    creditsSpent: integer('credits_spent').notNull().default(0),
  },
  (table) => [
    index('usage_records_account_time_idx').on(table.accountId, table.occurredAt),
    index('usage_records_model_idx').on(table.model, table.occurredAt),
  ],
);

/// Privacy-safe activity metadata. Never document content, never chat content, never PII.
export const activityEvents = hawkvance.table(
  'activity_events',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    accountId: uuid('account_id').references(() => accounts.id, { onDelete: 'set null' }),
    occurredAt: timestamp('occurred_at', { withTimezone: true }).notNull().defaultNow(),
    kind: text('kind').notNull(),
    detail: jsonb('detail').notNull(),
    requestIp: text('request_ip').notNull().default(''),
  },
  (table) => [index('activity_events_account_time_idx').on(table.accountId, table.occurredAt)],
);

export const adminAuditEntries = hawkvance.table(
  'admin_audit_entries',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    actorAccountId: uuid('actor_account_id')
      .notNull()
      .references(() => accounts.id, { onDelete: 'restrict' }),
    subjectAccountId: uuid('subject_account_id').references(() => accounts.id, {
      onDelete: 'set null',
    }),
    occurredAt: timestamp('occurred_at', { withTimezone: true }).notNull().defaultNow(),
    action: text('action').notNull(),
    previousValue: jsonb('previous_value').notNull(),
    nextValue: jsonb('next_value').notNull(),
    requestIp: text('request_ip').notNull().default(''),
  },
  (table) => [index('admin_audit_time_idx').on(table.occurredAt)],
);
