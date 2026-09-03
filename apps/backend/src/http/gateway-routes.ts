import type { FastifyInstance, FastifyReply, FastifyRequest } from 'fastify';
import { z } from 'zod';
import { chatMessageSchema } from '@hawkvance/llm';
import type { AccountRepository } from '../identity/account-repository.js';
import type { AccountWriter } from '../identity/account-writer.js';
import type { Account } from '../identity/account.js';
import { BearerHeader, type NeonIdentityVerifier } from '../identity/neon-identity-token.js';
import type { PlanLimitsRepository } from '../identity/plan-limits-repository.js';
import type { AiGateway } from '../gateway/ai-gateway.js';
import { CreditCost } from '../gateway/credit-cost.js';
import { HttpProblem } from './errors.js';

const completionSchema = z.object({
  messages: z.array(chatMessageSchema).nonempty(),
  workspaceId: z.string().uuid().nullish(),
  preferredModelId: z.string().min(1).optional(),
  /// Set when the conversation is not pointed at a workspace, so the assistant is told plainly that
  /// it has no documents here rather than inventing an answer about them.
  globalMemory: z.boolean().optional(),
  maxOutputTokens: z.number().int().positive().max(8192).default(2048),
});

const externalUsageSchema = z.object({
  provider: z.string().min(1),
  model: z.string().min(1),
  inputTokens: z.number().int().nonnegative(),
  outputTokens: z.number().int().nonnegative(),
  latencyMs: z.number().int().nonnegative(),
  outcome: z.string().min(1).default('succeeded'),
  workspaceId: z.string().uuid().nullish(),
});

export type GatewayDependencies = {
  readonly verifier: NeonIdentityVerifier;
  readonly accounts: AccountRepository;
  readonly accountWriter: AccountWriter;
  readonly planLimits: PlanLimitsRepository;
  readonly gateway: AiGateway;
};

/// The external-inference boundary. Everything that arrives here has already been sanitised,
/// compressed and approved on the user's machine.
export class GatewayRoutes {
  private readonly dependencies: GatewayDependencies;

  constructor(dependencies: GatewayDependencies) {
    this.dependencies = dependencies;
  }

  register(server: FastifyInstance): void {
    server.get('/ai/models', async (request, reply) => this.models(request, reply));
    server.get('/ai/usage', async (request, reply) => this.usage(request, reply));
    server.post('/ai/complete', async (request, reply) => this.complete(request, reply));
    server.post('/ai/usage/external', async (request, reply) => this.recordExternal(request, reply));
  }

  private async models(request: FastifyRequest, reply: FastifyReply): Promise<FastifyReply> {
    try {
      const account = await this.authenticate(request);
      const limits = await this.dependencies.planLimits.forTier(account.plan);
      const available = this.dependencies.gateway.models.filter((entry) =>
        limits.allowedModelTiers.includes(entry.tier),
      );
      return reply.code(200).send({
        hawkvanceConfigured: this.dependencies.gateway.isConfigured,
        byokAllowed: limits.byokAllowed,
        creditCosts: CreditCost.table(),
        models: available.map((entry) => ({
          id: entry.id,
          label: entry.label,
          tier: entry.tier,
          provider: entry.provider,
          contextWindow: entry.contextWindow,
        })),
      });
    } catch (cause) {
      return HttpProblem.from(cause).send(reply);
    }
  }

  private async usage(request: FastifyRequest, reply: FastifyReply): Promise<FastifyReply> {
    try {
      const account = await this.authenticate(request);
      const limits = await this.dependencies.planLimits.forTier(account.plan);
      const verdict = await this.dependencies.gateway.usage(account, limits);
      return reply.code(200).send(verdict);
    } catch (cause) {
      return HttpProblem.from(cause).send(reply);
    }
  }

  private async complete(request: FastifyRequest, reply: FastifyReply): Promise<FastifyReply> {
    try {
      const account = await this.authenticate(request);
      const limits = await this.dependencies.planLimits.forTier(account.plan);
      const body = completionSchema.parse(request.body);

      const result = await this.dependencies.gateway.complete({
        account,
        limits,
        messages: body.messages,
        workspaceId: body.workspaceId ?? null,
        ...(body.preferredModelId === undefined
          ? {}
          : { preferredModelId: body.preferredModelId }),
        globalMemory: body.globalMemory === true,
        maxOutputTokens: body.maxOutputTokens,
      });

      return reply.code(200).send(result);
    } catch (cause) {
      return HttpProblem.from(cause).send(reply);
    }
  }

  private async recordExternal(request: FastifyRequest, reply: FastifyReply): Promise<FastifyReply> {
    try {
      const account = await this.authenticate(request);
      const body = externalUsageSchema.parse(request.body);
      await this.dependencies.gateway.recordExternalUsage({
        account,
        workspaceId: body.workspaceId ?? null,
        provider: body.provider,
        model: body.model,
        inputTokens: body.inputTokens,
        outputTokens: body.outputTokens,
        latencyMs: body.latencyMs,
        outcome: body.outcome,
      });
      return reply.code(202).send({ recorded: true });
    } catch (cause) {
      return HttpProblem.from(cause).send(reply);
    }
  }

  private async authenticate(request: FastifyRequest): Promise<Account> {
    const token = await this.dependencies.verifier.verify(
      BearerHeader.tokenFrom(request.headers.authorization),
    );
    return this.dependencies.accountWriter.fromIdentity(token, new Date());
  }
}
