import { eq } from 'drizzle-orm';
import type { PlanLimits, PlanTier } from '@hawkvance/contracts';
import { planLimitsSchema } from '@hawkvance/contracts';
import type { Database } from '../db/client.js';
import { planLimits } from '../db/schema.js';

export class PlanLimitsMissing extends Error {
  readonly tier: PlanTier;

  constructor(tier: PlanTier) {
    super(`No limits are configured for the ${tier} plan. Seed plan_limits before serving traffic.`);
    this.name = 'PlanLimitsMissing';
    this.tier = tier;
  }
}

export class PlanLimitsRepository {
  private readonly database: Database;

  constructor(database: Database) {
    this.database = database;
  }

  async forTier(tier: PlanTier): Promise<PlanLimits> {
    const [row] = await this.database.drizzle
      .select()
      .from(planLimits)
      .where(eq(planLimits.tier, tier))
      .limit(1);

    if (row === undefined) {
      throw new PlanLimitsMissing(tier);
    }

    return planLimitsSchema.parse({
      dailyRequests: row.dailyRequests,
      monthlyRequests: row.monthlyRequests,
      monthlyTokens: row.monthlyTokens,
      monthlyCredits: row.monthlyCredits,
      storageBytes: row.storageBytes,
      maxWorkspaces: row.maxWorkspaces,
      memoryRetentionDays: row.memoryRetentionDays,
      byokAllowed: row.byokAllowed,
      allowedModelTiers: row.allowedModelTiers,
    });
  }
}
