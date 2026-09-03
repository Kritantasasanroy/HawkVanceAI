import type {
  ChatMessage,
  Generation,
  ModelEntry,
  ModelProvider,
  NonEmptyArray,
  ProviderName,
} from '@hawkvance/llm';
import { CostEstimate, ModelRouter, NoModelAvailable, ProviderFailure } from '@hawkvance/llm';
import type { PlanLimits } from '@hawkvance/contracts';
import type { Account } from '../identity/account.js';
import { AssistantIdentity } from './assistant-identity.js';
import { CreditCost } from './credit-cost.js';
import { QuotaExceeded, QuotaLedger, type QuotaVerdict } from './quota-ledger.js';

export type GatewayRequest = {
  readonly account: Account;
  readonly limits: PlanLimits;
  readonly messages: NonEmptyArray<ChatMessage>;
  readonly workspaceId: string | null;
  readonly preferredModelId?: string;
  readonly maxOutputTokens: number;
  /// True when the conversation is not pointed at a workspace, so the assistant is told it has no
  /// documents to read rather than being left to guess.
  readonly globalMemory?: boolean;
};

export type GatewayResult = {
  readonly text: string;
  readonly model: string;
  readonly modelLabel: string;
  readonly provider: ProviderName;
  readonly complexity: string;
  readonly downgraded: boolean;
  readonly routingReason: string;
  readonly usage: { inputTokens: number; outputTokens: number };
  readonly estimatedCostMicros: number;
  /// What this answer cost the person, in the unit the interface shows them.
  readonly creditsSpent: number;
  readonly latencyMs: number;
  readonly attemptedFallback: boolean;
  readonly attempts: number;
  readonly quota: QuotaVerdict;
};

/// The model the person chose is busy, and they asked not to be given another one.
///
/// A distinct type rather than a generic failure so the route can answer 503 and the interface can
/// offer the obvious next move, which is to wait or pick a different model.
export class ModelBusy extends Error {
  readonly modelLabel: string;

  constructor(modelLabel: string) {
    super(`${modelLabel} is busy right now. Try again in a moment, or choose another model.`);
    this.name = 'ModelBusy';
    this.modelLabel = modelLabel;
  }
}

export class GatewayUnconfigured extends Error {
  constructor() {
    super(
      'HawkVance-managed AI is not configured on this server. Use your own API key in Settings, ' +
        'or ask an administrator to add a provider credential.',
    );
    this.name = 'GatewayUnconfigured';
  }
}

/// Server-side inference for HawkVance-managed mode.
///
/// The provider credential lives here and nowhere else: it is never sent to the desktop, never
/// returned by an endpoint, and never logged. BYOK deliberately does not pass through this class at
/// all, because the user's own key should never reach a HawkVance server.
export class AiGateway {
  /// Bounded so a systemic outage cannot turn one user request into a stampede across the whole
  /// catalogue. Four is enough to ride out the free pool's usual saturation.
  static readonly maximumAttempts = 4;

  private readonly provider: ModelProvider | null;
  private readonly router: ModelRouter;
  private readonly quotas: QuotaLedger;

  constructor(provider: ModelProvider | null, router: ModelRouter, quotas: QuotaLedger) {
    this.provider = provider;
    this.router = router;
    this.quotas = quotas;
  }

  get isConfigured(): boolean {
    return this.provider !== null;
  }

  async complete(request: GatewayRequest, moment: Date = new Date()): Promise<GatewayResult> {
    const provider = this.provider;
    if (provider === null) {
      throw new GatewayUnconfigured();
    }

    const price = CreditCost.of('question');
    const quota = await this.quotas.check(request.account.id, request.limits, moment, price);
    if (!quota.allowed) {
      throw new QuotaExceeded(quota);
    }

    // Applied before routing, not after, so the system message counts towards the context size
    // that picks a model. Counting it afterwards would let a long conversation be routed to a model
    // it no longer fits.
    const messages = AssistantIdentity.apply(request.messages, {
      globalMemory: request.globalMemory === true,
    });

    const contextTokens = provider.countTokens(messages);
    const choice = this.router.route({
      messages,
      contextTokens,
      allowedTiers: request.limits.allowedModelTiers,
      ...(request.preferredModelId === undefined
        ? {}
        : { preferredModelId: request.preferredModelId }),
    });

    // A model the person chose is never swapped for another.
    //
    // The walk below exists because OpenRouter's free pool returns 429 from whichever upstream is
    // saturated, and trying a different free model usually succeeds immediately. That is right when
    // HawkVance picked the model, and wrong when the person did: answering from a model they did
    // not choose, without saying so, is how "no matter what I select I get the small one" happened.
    // When they have chosen, a busy model is reported as busy.
    const chosenExplicitly = request.preferredModelId !== undefined;
    const candidates: ModelEntry[] = chosenExplicitly
      ? [choice.model]
      : [
          choice.model,
          ...this.router
            .fallbacksFor(choice, request.limits.allowedModelTiers)
            .filter((entry) => entry.contextWindow >= contextTokens),
        ].slice(0, AiGateway.maximumAttempts);

    let generation: Generation | null = null;
    let used: ModelEntry = choice.model;
    let attempts = 0;
    let lastFailure: unknown = null;

    for (const candidate of candidates) {
      attempts += 1;
      try {
        generation = await provider.generate({
          model: candidate.id,
          messages,
          maxOutputTokens: request.maxOutputTokens,
          temperature: 0.3,
        });
        used = candidate;
        break;
      } catch (cause) {
        lastFailure = cause;
        // A rejected credential or a malformed request fails identically everywhere. Only a
        // transient upstream problem is worth another model.
        if (!(cause instanceof ProviderFailure) || !cause.retryable) {
          break;
        }
      }
    }

    if (generation === null) {
      await this.recordFailure(request, used, lastFailure, moment);
      if (chosenExplicitly && lastFailure instanceof ProviderFailure && lastFailure.retryable) {
        throw new ModelBusy(used.label);
      }
      throw lastFailure ?? new Error('No model produced a response.');
    }

    const attemptedFallback = attempts > 1;

    const cost = CostEstimate.micros(
      used,
      generation.usage.inputTokens,
      generation.usage.outputTokens,
    );

    await this.quotas.record({
      accountId: request.account.id,
      workspaceId: request.workspaceId,
      provider: generation.provider,
      model: generation.model,
      inputTokens: generation.usage.inputTokens,
      outputTokens: generation.usage.outputTokens,
      estimatedCostMicros: cost,
      creditsSpent: price,
      latencyMs: generation.latencyMs,
      outcome: 'succeeded',
      occurredAt: moment,
    });

    return {
      text: generation.text,
      model: generation.model,
      modelLabel: used.label,
      provider: generation.provider,
      complexity: choice.complexity,
      downgraded: choice.downgraded,
      routingReason: choice.reason,
      usage: generation.usage,
      estimatedCostMicros: cost,
      creditsSpent: price,
      latencyMs: generation.latencyMs,
      attemptedFallback,
      attempts,
      quota,
    };
  }

  /// A failed request still consumed provider capacity and still matters to the admin dashboard,
  /// so it is recorded with zero tokens rather than silently dropped.
  private async recordFailure(
    request: GatewayRequest,
    model: ModelEntry,
    cause: unknown,
    moment: Date,
  ): Promise<void> {
    await this.quotas.record({
      accountId: request.account.id,
      workspaceId: request.workspaceId,
      provider: model.provider,
      model: model.id,
      inputTokens: 0,
      outputTokens: 0,
      estimatedCostMicros: 0,
      creditsSpent: CreditCost.failure,
      latencyMs: 0,
      outcome: cause instanceof ProviderFailure ? `failed:${cause.status}` : 'failed',
      occurredAt: moment,
    });
  }

  /// Reports usage for a BYOK call the desktop already made against the user's own key.
  ///
  /// Accounting only: no quota is enforced, because the user is paying their provider directly.
  /// Recording it anyway is what lets the Privacy and Usage screens tell one story rather than two.
  async recordExternalUsage(entry: {
    account: Account;
    workspaceId: string | null;
    provider: string;
    model: string;
    inputTokens: number;
    outputTokens: number;
    latencyMs: number;
    outcome: string;
  }, moment: Date = new Date()): Promise<void> {
    await this.quotas.record({
      accountId: entry.account.id,
      workspaceId: entry.workspaceId,
      provider: entry.provider,
      model: entry.model,
      inputTokens: entry.inputTokens,
      outputTokens: entry.outputTokens,
      // Zero on both counts: the user paid their provider, not us. Counting it as HawkVance spend
      // would overstate our costs, and charging credits for it would bill them twice.
      estimatedCostMicros: 0,
      creditsSpent: 0,
      latencyMs: entry.latencyMs,
      outcome: entry.outcome,
      occurredAt: moment,
    });
  }

  async usage(account: Account, limits: PlanLimits, moment: Date = new Date()): Promise<QuotaVerdict> {
    return this.quotas.check(account.id, limits, moment);
  }

  get models(): ReadonlyArray<ModelEntry> {
    return this.router.enabled;
  }
}

export { NoModelAvailable, QuotaExceeded };
