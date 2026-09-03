import { and, eq, gte, sql } from 'drizzle-orm';
import type { AccountId, PlanLimits } from '@hawkvance/contracts';
import type { Database } from '../db/client.js';
import { usageRecords } from '../db/schema.js';

export type QuotaUsage = {
  readonly dailyRequests: number;
  readonly monthlyRequests: number;
  readonly monthlyTokens: number;
  readonly monthlyCostMicros: number;
  /// What the person has spent, in the unit they are shown. Derived by summing the same
  /// append-only rows as everything else, so the balance on screen and the bill agree.
  readonly creditsSpent: number;
  readonly creditsRemaining: number;
};

export type QuotaVerdict = {
  readonly allowed: boolean;
  readonly reason: string;
  readonly usage: QuotaUsage;
  readonly limits: PlanLimits;
  readonly resetsAt: string;
};

export class QuotaExceeded extends Error {
  readonly verdict: QuotaVerdict;

  constructor(verdict: QuotaVerdict) {
    super(verdict.reason);
    this.name = 'QuotaExceeded';
    this.verdict = verdict;
  }
}

/// Derives consumption by summing the append-only usage records over a window.
///
/// Deliberately not a mutable counter. A counter loses its own audit trail, races under
/// concurrency, and cannot answer the per-model and per-provider questions spec section 27
/// requires. Summing costs an indexed aggregate; being wrong about someone's bill costs more.
export class QuotaLedger {
  private readonly database: Database;

  constructor(database: Database) {
    this.database = database;
  }

  static startOfDay(moment: Date): Date {
    return new Date(Date.UTC(moment.getUTCFullYear(), moment.getUTCMonth(), moment.getUTCDate()));
  }

  static startOfMonth(moment: Date): Date {
    return new Date(Date.UTC(moment.getUTCFullYear(), moment.getUTCMonth(), 1));
  }

  static nextMonth(moment: Date): Date {
    return new Date(Date.UTC(moment.getUTCFullYear(), moment.getUTCMonth() + 1, 1));
  }

  async usageFor(
    accountId: AccountId,
    moment: Date,
    monthlyCredits = 0,
  ): Promise<QuotaUsage> {
    const [daily] = await this.database.drizzle
      .select({ requests: sql<number>`count(*)::int` })
      .from(usageRecords)
      .where(
        and(
          eq(usageRecords.accountId, accountId),
          gte(usageRecords.occurredAt, QuotaLedger.startOfDay(moment)),
        ),
      );

    const [monthly] = await this.database.drizzle
      .select({
        requests: sql<number>`count(*)::int`,
        tokens: sql<number>`coalesce(sum(${usageRecords.inputTokens} + ${usageRecords.outputTokens}), 0)::int`,
        cost: sql<number>`coalesce(sum(${usageRecords.estimatedCostMicros}), 0)::bigint`,
        credits: sql<number>`coalesce(sum(${usageRecords.creditsSpent}), 0)::int`,
      })
      .from(usageRecords)
      .where(
        and(
          eq(usageRecords.accountId, accountId),
          gte(usageRecords.occurredAt, QuotaLedger.startOfMonth(moment)),
        ),
      );

    const creditsSpent = Number(monthly?.credits ?? 0);

    return {
      dailyRequests: Number(daily?.requests ?? 0),
      monthlyRequests: Number(monthly?.requests ?? 0),
      monthlyTokens: Number(monthly?.tokens ?? 0),
      monthlyCostMicros: Number(monthly?.cost ?? 0),
      creditsSpent,
      // Never negative. An allowance lowered mid-month would otherwise report a balance below zero,
      // which reads as a debt the person owes rather than an empty allowance.
      creditsRemaining: Math.max(0, monthlyCredits - creditsSpent),
    };
  }

  /// Checked before the request, never after. A user who is over quota should be told, not billed.
  async check(
    accountId: AccountId,
    limits: PlanLimits,
    moment: Date,
    cost = 0,
  ): Promise<QuotaVerdict> {
    const usage = await this.usageFor(accountId, moment, limits.monthlyCredits);
    const resetsAt = QuotaLedger.nextMonth(moment).toISOString();

    // Checked first, because credits are the allowance the person was shown. Being refused for a
    // limit they were never told about reads as a fault in the product.
    if (usage.creditsSpent + cost > limits.monthlyCredits) {
      return {
        allowed: false,
        reason:
          usage.creditsRemaining === 0
            ? `You have used all ${limits.monthlyCredits.toLocaleString()} of this month's credits. They renew on the 1st.`
            : `This needs ${cost} credits and you have ${usage.creditsRemaining} left. They renew on the 1st.`,
        usage,
        limits,
        resetsAt,
      };
    }

    if (usage.dailyRequests >= limits.dailyRequests) {
      return {
        allowed: false,
        reason: `You have used today's ${limits.dailyRequests} requests. It resets at midnight UTC.`,
        usage,
        limits,
        resetsAt,
      };
    }
    if (usage.monthlyRequests >= limits.monthlyRequests) {
      return {
        allowed: false,
        reason: `You have used this month's ${limits.monthlyRequests} requests. Upgrade or use your own API key.`,
        usage,
        limits,
        resetsAt,
      };
    }
    if (usage.monthlyTokens >= limits.monthlyTokens) {
      return {
        allowed: false,
        reason: `You have used this month's ${limits.monthlyTokens.toLocaleString()} tokens. Upgrade or use your own API key.`,
        usage,
        limits,
        resetsAt,
      };
    }

    return { allowed: true, reason: 'within quota', usage, limits, resetsAt };
  }

  async record(entry: {
    accountId: AccountId;
    workspaceId: string | null;
    provider: string;
    model: string;
    inputTokens: number;
    outputTokens: number;
    estimatedCostMicros: number;
    latencyMs: number;
    outcome: string;
    occurredAt: Date;
    creditsSpent: number;
  }): Promise<void> {
    await this.database.drizzle.insert(usageRecords).values({
      accountId: entry.accountId,
      workspaceId: entry.workspaceId,
      occurredAt: entry.occurredAt,
      provider: entry.provider,
      model: entry.model,
      inputTokens: entry.inputTokens,
      outputTokens: entry.outputTokens,
      estimatedCostMicros: entry.estimatedCostMicros,
      latencyMs: entry.latencyMs,
      outcome: entry.outcome,
      creditsSpent: entry.creditsSpent,
    });
  }
}
