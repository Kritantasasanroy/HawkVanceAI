import type { FastifyInstance, FastifyReply, FastifyRequest } from 'fastify';
import { desc, gte, sql } from 'drizzle-orm';
import { z } from 'zod';
import { accountRoleSchema, planTierSchema } from '@hawkvance/contracts';
import type { AccountId } from '@hawkvance/contracts';
import type { Database } from '../db/client.js';
import { accounts, adminAuditEntries, devices, usageRecords } from '../db/schema.js';
import type { AccountRepository } from '../identity/account-repository.js';
import type { AccountWriter } from '../identity/account-writer.js';
import type { Account } from '../identity/account.js';
import { BearerHeader, type NeonIdentityVerifier } from '../identity/neon-identity-token.js';
import { HttpProblem } from './errors.js';

export class NotPermitted extends Error {
  readonly required: string;

  constructor(required: string) {
    super('Your role does not permit that action.');
    this.name = 'NotPermitted';
    this.required = required;
  }
}

const readRoles = ['support', 'analyst', 'admin', 'superAdmin'] as const;
const writeRoles = ['admin', 'superAdmin'] as const;

const suspendSchema = z.object({ reason: z.string().min(3).max(200) });
const planSchema = z.object({ plan: planTierSchema });
const roleSchema = z.object({ role: accountRoleSchema });

export type AdminDependencies = {
  readonly verifier: NeonIdentityVerifier;
  readonly accounts: AccountRepository;
  readonly accountWriter: AccountWriter;
  readonly database: Database;
};

/// Spec sections 41 to 49 and 72.
///
/// The privacy boundary here is structural, not a policy. There is no route that returns document
/// content, extracted text, a redaction map or chat content, because the backend never receives any
/// of those. Administrators see operational metadata and nothing else.
export class AdminRoutes {
  private readonly dependencies: AdminDependencies;

  constructor(dependencies: AdminDependencies) {
    this.dependencies = dependencies;
  }

  register(server: FastifyInstance): void {
    server.get('/admin/overview', async (query, reply) => this.overview(query, reply));
    server.get('/admin/accounts', async (query, reply) => this.listAccounts(query, reply));
    server.get('/admin/usage', async (query, reply) => this.usage(query, reply));
    server.get('/admin/audit', async (query, reply) => this.audit(query, reply));
    server.post('/admin/accounts/:id/suspend', async (query, reply) => this.suspend(query, reply));
    server.post('/admin/accounts/:id/reactivate', async (query, reply) =>
      this.reactivate(query, reply),
    );
    server.post('/admin/accounts/:id/plan', async (query, reply) => this.changePlan(query, reply));
    server.post('/admin/accounts/:id/role', async (query, reply) => this.changeRole(query, reply));
  }

  private async overview(request: FastifyRequest, reply: FastifyReply): Promise<FastifyReply> {
    try {
      await this.authorise(request, readRoles);
      const drizzle = this.dependencies.database.drizzle;
      const dayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000);
      const monthAgo = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000);

      const [totals] = await drizzle
        .select({
          total: sql<number>`count(*)::int`,
          active: sql<number>`count(*) filter (where ${accounts.status} = 'active')::int`,
          suspended: sql<number>`count(*) filter (where ${accounts.status} = 'suspended')::int`,
        })
        .from(accounts);

      const [daily] = await drizzle
        .select({ activeUsers: sql<number>`count(*)::int` })
        .from(accounts)
        .where(gte(accounts.lastSeenAt, dayAgo));

      const [spend] = await drizzle
        .select({
          requests: sql<number>`count(*)::int`,
          inputTokens: sql<number>`coalesce(sum(${usageRecords.inputTokens}), 0)::int`,
          outputTokens: sql<number>`coalesce(sum(${usageRecords.outputTokens}), 0)::int`,
          costMicros: sql<number>`coalesce(sum(${usageRecords.estimatedCostMicros}), 0)::bigint`,
          averageLatencyMs: sql<number>`coalesce(avg(${usageRecords.latencyMs}), 0)::int`,
          failures: sql<number>`count(*) filter (where ${usageRecords.outcome} <> 'succeeded')::int`,
        })
        .from(usageRecords)
        .where(gte(usageRecords.occurredAt, monthAgo));

      const [deviceCount] = await drizzle
        .select({ total: sql<number>`count(*)::int` })
        .from(devices);

      const requests = Number(spend?.requests ?? 0);
      const failures = Number(spend?.failures ?? 0);

      return reply.code(200).send({
        accounts: {
          total: Number(totals?.total ?? 0),
          active: Number(totals?.active ?? 0),
          suspended: Number(totals?.suspended ?? 0),
          activeLast24h: Number(daily?.activeUsers ?? 0),
        },
        devices: { total: Number(deviceCount?.total ?? 0) },
        ai: {
          requests,
          inputTokens: Number(spend?.inputTokens ?? 0),
          outputTokens: Number(spend?.outputTokens ?? 0),
          estimatedCostMicros: Number(spend?.costMicros ?? 0),
          averageLatencyMs: Number(spend?.averageLatencyMs ?? 0),
          errorRate: requests === 0 ? 0 : Number((failures / requests).toFixed(4)),
        },
        window: { since: monthAgo.toISOString() },
      });
    } catch (cause) {
      return HttpProblem.from(cause).send(reply);
    }
  }

  private async listAccounts(request: FastifyRequest, reply: FastifyReply): Promise<FastifyReply> {
    try {
      await this.authorise(request, readRoles);
      const search = (request.query as { q?: string }).q ?? '';
      const rows = await this.dependencies.database.drizzle
        .select({
          id: accounts.id,
          email: accounts.email,
          displayName: accounts.displayName,
          status: accounts.status,
          role: accounts.role,
          plan: accounts.plan,
          createdAt: accounts.createdAt,
          lastSeenAt: accounts.lastSeenAt,
        })
        .from(accounts)
        .where(search.length > 0 ? sql`${accounts.email} ilike ${`%${search}%`}` : sql`true`)
        .orderBy(desc(accounts.lastSeenAt))
        .limit(200);

      return reply.code(200).send({
        accounts: rows.map((row) => ({
          ...row,
          createdAt: row.createdAt.toISOString(),
          lastSeenAt: row.lastSeenAt.toISOString(),
        })),
      });
    } catch (cause) {
      return HttpProblem.from(cause).send(reply);
    }
  }

  private async usage(request: FastifyRequest, reply: FastifyReply): Promise<FastifyReply> {
    try {
      await this.authorise(request, readRoles);
      const rows = await this.dependencies.database.drizzle
        .select({
          model: usageRecords.model,
          provider: usageRecords.provider,
          requests: sql<number>`count(*)::int`,
          inputTokens: sql<number>`coalesce(sum(${usageRecords.inputTokens}), 0)::int`,
          outputTokens: sql<number>`coalesce(sum(${usageRecords.outputTokens}), 0)::int`,
          costMicros: sql<number>`coalesce(sum(${usageRecords.estimatedCostMicros}), 0)::bigint`,
          averageLatencyMs: sql<number>`coalesce(avg(${usageRecords.latencyMs}), 0)::int`,
          failures: sql<number>`count(*) filter (where ${usageRecords.outcome} <> 'succeeded')::int`,
        })
        .from(usageRecords)
        .groupBy(usageRecords.model, usageRecords.provider)
        .orderBy(desc(sql`count(*)`));

      return reply.code(200).send({
        models: rows.map((row) => ({ ...row, costMicros: Number(row.costMicros) })),
      });
    } catch (cause) {
      return HttpProblem.from(cause).send(reply);
    }
  }

  private async audit(request: FastifyRequest, reply: FastifyReply): Promise<FastifyReply> {
    try {
      await this.authorise(request, readRoles);
      const rows = await this.dependencies.database.drizzle
        .select()
        .from(adminAuditEntries)
        .orderBy(desc(adminAuditEntries.occurredAt))
        .limit(200);

      return reply.code(200).send({
        entries: rows.map((row) => ({ ...row, occurredAt: row.occurredAt.toISOString() })),
      });
    } catch (cause) {
      return HttpProblem.from(cause).send(reply);
    }
  }

  private async suspend(request: FastifyRequest, reply: FastifyReply): Promise<FastifyReply> {
    return this.mutate(request, reply, writeRoles, async (actor, target) => {
      const body = suspendSchema.parse(request.body);
      const previous = target.status;
      target.suspend(body.reason, new Date());
      await this.dependencies.accounts.save(target);
      await this.writeAudit(
        actor,
        target,
        'account.suspend',
        { status: previous },
        { status: 'suspended', reason: body.reason },
        request.ip,
      );
      return { status: target.status };
    });
  }

  private async reactivate(request: FastifyRequest, reply: FastifyReply): Promise<FastifyReply> {
    return this.mutate(request, reply, writeRoles, async (actor, target) => {
      const previous = target.status;
      target.reactivate(new Date());
      await this.dependencies.accounts.save(target);
      await this.writeAudit(
        actor,
        target,
        'account.reactivate',
        { status: previous },
        { status: 'active' },
        request.ip,
      );
      return { status: target.status };
    });
  }

  private async changePlan(request: FastifyRequest, reply: FastifyReply): Promise<FastifyReply> {
    return this.mutate(request, reply, writeRoles, async (actor, target) => {
      const body = planSchema.parse(request.body);
      const previous = target.plan;
      target.changePlan(body.plan);
      await this.dependencies.accounts.save(target);
      await this.writeAudit(
        actor,
        target,
        'account.changePlan',
        { plan: previous },
        { plan: body.plan },
        request.ip,
      );
      return { plan: target.plan };
    });
  }

  /// Role changes are superAdmin only. An admin who can grant themselves superAdmin is not a
  /// privilege boundary, it is a formality.
  private async changeRole(request: FastifyRequest, reply: FastifyReply): Promise<FastifyReply> {
    return this.mutate(request, reply, ['superAdmin'], async (actor, target) => {
      const body = roleSchema.parse(request.body);
      const previous = target.role;
      target.changeRole(body.role);
      await this.dependencies.accounts.save(target);
      await this.writeAudit(
        actor,
        target,
        'account.changeRole',
        { role: previous },
        { role: body.role },
        request.ip,
      );
      return { role: target.role };
    });
  }

  private async mutate(
    request: FastifyRequest,
    reply: FastifyReply,
    permitted: ReadonlyArray<string>,
    change: (actor: Account, target: Account) => Promise<unknown>,
  ): Promise<FastifyReply> {
    try {
      const actor = await this.authorise(request, permitted);
      const target = await this.target(request);
      return reply.code(200).send(await change(actor, target));
    } catch (cause) {
      return HttpProblem.from(cause).send(reply);
    }
  }

  private async target(request: FastifyRequest): Promise<Account> {
    const id = z.string().uuid().parse((request.params as { id: string }).id);
    const target = await this.dependencies.accounts.findById(id as AccountId);
    if (target === null) {
      throw new NotPermitted('an account that exists');
    }
    return target;
  }

  /// Every administrative change is recorded before the response is sent, per spec section 49.
  private async writeAudit(
    actor: Account,
    subject: Account,
    action: string,
    previousValue: unknown,
    nextValue: unknown,
    requestIp: string,
  ): Promise<void> {
    await this.dependencies.database.drizzle.insert(adminAuditEntries).values({
      actorAccountId: actor.id,
      subjectAccountId: subject.id,
      action,
      previousValue: previousValue as object,
      nextValue: nextValue as object,
      requestIp,
    });
  }

  private async authorise(
    request: FastifyRequest,
    permitted: ReadonlyArray<string>,
  ): Promise<Account> {
    const token = await this.dependencies.verifier.verify(
      BearerHeader.tokenFrom(request.headers.authorization),
    );
    const account = await this.dependencies.accountWriter.fromIdentity(token, new Date());
    if (!permitted.includes(account.role)) {
      throw new NotPermitted(permitted.join(' or '));
    }
    return account;
  }
}
