
import { sql } from 'drizzle-orm';
import { migrate } from 'drizzle-orm/postgres-js/migrator';
import { Configuration } from '../config.js';
import { Database } from './client.js';
import { planLimits } from './schema.js';

const defaultPlanLimits = [
  {
    tier: 'free',
    dailyRequests: 20,
    monthlyRequests: 200,
    monthlyTokens: 100_000,
    storageBytes: 536_870_912,
    maxWorkspaces: 2,
    memoryRetentionDays: 30,
    byokAllowed: true,
    // Also every tier, for the same reason: nothing in the catalogue costs anything. When a paid
    // model is added this becomes the line that has to gate it, and it should be revisited then.
    allowedModelTiers: ['economy', 'standard', 'premium'],
  },
  {
    tier: 'beta',
    monthlyCredits: 500,
    dailyRequests: 100,
    monthlyRequests: 1_000,
    monthlyTokens: 500_000,
    storageBytes: 2_147_483_648,
    maxWorkspaces: 10,
    memoryRetentionDays: 180,
    byokAllowed: true,
    // Every catalogue entry is a free OpenRouter model, so "premium" describes capability, not
    // price. Withholding the largest ones from the free plan gained nothing and hid the models
    // people actually want.
    allowedModelTiers: ['economy', 'standard', 'premium'],
  },
  {
    tier: 'pro',
    monthlyCredits: 5000,
    dailyRequests: 500,
    monthlyRequests: 10_000,
    monthlyTokens: 5_000_000,
    storageBytes: 21_474_836_480,
    maxWorkspaces: 50,
    memoryRetentionDays: 730,
    byokAllowed: true,
    allowedModelTiers: ['economy', 'standard', 'premium'],
  },
  {
    tier: 'enterprise',
    monthlyCredits: 50000,
    dailyRequests: 5_000,
    monthlyRequests: 100_000,
    monthlyTokens: 50_000_000,
    storageBytes: 214_748_364_800,
    maxWorkspaces: 500,
    memoryRetentionDays: 3_650,
    byokAllowed: true,
    allowedModelTiers: ['economy', 'standard', 'premium'],
  },
];

const configuration = Configuration.fromProcessEnv();
const database = Database.connect(configuration.environment.DATABASE_URL, 1);

await migrate(database.drizzle, { migrationsFolder: 'drizzle' });

// Credits are refreshed on every run rather than left alone, because a tier added after the column
// existed would otherwise keep the column default forever and quietly give paying plans the free
// allowance. Every other limit is left untouched, so an administrator's tuning survives.
await database.drizzle
  .insert(planLimits)
  .values(defaultPlanLimits)
  .onConflictDoUpdate({
    target: planLimits.tier,
    set: { monthlyCredits: sql`excluded.monthly_credits` },
  });

await database.close();
process.stdout.write('migrations applied and default plan limits seeded\n');
