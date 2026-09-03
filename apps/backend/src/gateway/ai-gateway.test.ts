import assert from 'node:assert/strict';
import { afterAll, beforeAll, beforeEach, describe, it } from 'vitest';
import type {
  ChatMessage,
  Generation,
  GenerationRequest,
  ModelProvider,
  ProviderHealth,
  ProviderName,
} from '@hawkvance/llm';
import {
  CostEstimate,
  ModelRouter,
  NoModelAvailable,
  ProviderFailure,
  TaskClassifier,
  defaultCatalogue,
} from '@hawkvance/llm';
import type { PlanLimits } from '@hawkvance/contracts';
import { accounts, usageRecords } from '../db/schema.js';
import { Account } from '../identity/account.js';
import { EmailAddress } from '@hawkvance/contracts';
import { freeCatalogue } from '@hawkvance/llm';
import { AiGateway, GatewayUnconfigured, ModelBusy } from './ai-gateway.js';
import { QuotaExceeded, QuotaLedger } from './quota-ledger.js';
import { TestHarness } from '../testing/harness.js';

const limits: PlanLimits = {
  dailyRequests: 3 as PlanLimits['dailyRequests'],
  monthlyRequests: 10 as PlanLimits['monthlyRequests'],
  monthlyTokens: 1000 as PlanLimits['monthlyTokens'],
  storageBytes: 1_000_000 as PlanLimits['storageBytes'],
  maxWorkspaces: 5,
  memoryRetentionDays: 30,
  byokAllowed: true,
  allowedModelTiers: ['economy', 'standard'],
};

const premiumLimits: PlanLimits = { ...limits, allowedModelTiers: ['economy', 'standard', 'premium'] };

const ask = (text: string): [ChatMessage, ...ChatMessage[]] => [{ role: 'user', content: text }];

/// A provider that never leaves the process. Only the third-party HTTP call is faked; the router,
/// quota ledger and usage accounting under test are all real.
class ScriptedProvider implements ModelProvider {
  readonly name: ProviderName = 'openrouter';
  readonly calls: string[] = [];
  private readonly failFor: Set<string>;
  private readonly failure: ProviderFailure;

  constructor(failFor: string[] = [], failure?: ProviderFailure) {
    this.failFor = new Set(failFor);
    this.failure =
      failure ?? new ProviderFailure('openrouter', 503, 'upstream is unwell', true);
  }

  async generate(request: GenerationRequest): Promise<Generation> {
    this.calls.push(request.model);
    if (this.failFor.has(request.model)) {
      throw this.failure;
    }
    return {
      text: `answered by ${request.model}`,
      model: request.model,
      provider: this.name,
      usage: { inputTokens: 100, outputTokens: 50 },
      latencyMs: 42,
      finishReason: 'stop',
    };
  }

  async stream(request: GenerationRequest, onChunk: (delta: string) => void): Promise<Generation> {
    const generated = await this.generate(request);
    onChunk(generated.text);
    return generated;
  }

  countTokens(messages: ReadonlyArray<ChatMessage>): number {
    return Math.max(1, Math.ceil(messages.reduce((n, m) => n + m.content.length, 0) / 4));
  }

  async healthCheck(): Promise<ProviderHealth> {
    return { provider: this.name, reachable: true, latencyMs: 1, detail: 'scripted' };
  }
}

let harness: TestHarness;
let account: Account;

const gatewayWith = (provider: ScriptedProvider | null) =>
  new AiGateway(provider, new ModelRouter(), new QuotaLedger(harness.database));

/// The catalogue the server actually runs (`server.ts:72`), rather than the router's built-in
/// default. A test of "the model I picked is the model that answers" has to use the models a person
/// can really pick, or it proves nothing about what they see.
const liveCatalogueGateway = (provider: ScriptedProvider) =>
  new AiGateway(provider, new ModelRouter(freeCatalogue), new QuotaLedger(harness.database));

beforeAll(async () => {
  harness = await TestHarness.start();
});

afterAll(async () => {
  await harness.stop();
});

beforeEach(async () => {
  await harness.reset();
  account = Account.register({
    email: EmailAddress.parse('gateway@lemonideas.in'),
    registeredAt: new Date(),
    neonUserId: 'neon-gateway',
    displayName: 'Gateway',
  });
  await harness.database.drizzle.insert(accounts).values({
    id: account.id,
    neonUserId: account.snapshot.neonUserId,
    email: account.email,
    emailDomain: account.snapshot.emailDomain,
    displayName: account.snapshot.displayName,
    status: 'active',
    role: 'member',
    plan: 'beta',
    suspendedReason: null,
    createdAt: account.snapshot.createdAt,
    lastSeenAt: account.snapshot.lastSeenAt,
  });
});

describe('task classification', () => {
  it('routes a rewrite to the cheapest tier', () => {
    assert.equal(TaskClassifier.classify(ask('rewrite this sentence'), 100), 'simple');
  });

  it('routes ordinary questions to the middle tier', () => {
    assert.equal(TaskClassifier.classify(ask('what does clause 4 mean here?'), 500), 'moderate');
  });

  it('routes multi-document comparison to the premium tier', () => {
    assert.equal(
      TaskClassifier.classify(ask('compare the liability clauses across these agreements'), 500),
      'complex',
    );
  });

  it('treats a very large context as complex however it is phrased', () => {
    assert.equal(TaskClassifier.classify(ask('summarise'), 40_000), 'complex');
  });
});

describe('model routing', () => {
  const router = new ModelRouter();

  it('picks an economy model for a simple task', () => {
    const choice = router.route({
      messages: ask('rewrite this'),
      contextTokens: 100,
      allowedTiers: ['economy', 'standard', 'premium'],
    });
    assert.equal(choice.model.tier, 'economy');
    assert.equal(choice.downgraded, false);
  });

  it('downgrades rather than failing when the plan excludes the tier', () => {
    const choice = router.route({
      messages: ask('compare the indemnity clauses across both contracts'),
      contextTokens: 500,
      allowedTiers: ['economy'],
    });
    assert.equal(choice.requestedTier, 'premium');
    assert.equal(choice.model.tier, 'economy');
    assert.equal(choice.downgraded, true);
    assert.match(choice.reason, /does not include premium/);
  });

  it('honours an explicit model choice the plan allows', () => {
    const choice = router.route({
      messages: ask('anything'),
      contextTokens: 10,
      allowedTiers: ['economy', 'standard'],
      preferredModelId: 'deepseek/deepseek-chat',
    });
    assert.equal(choice.model.id, 'deepseek/deepseek-chat');
  });

  it('ignores a preferred model the plan does not allow', () => {
    const choice = router.route({
      messages: ask('anything'),
      contextTokens: 10,
      allowedTiers: ['economy'],
      preferredModelId: 'anthropic/claude-sonnet-4.5',
    });
    assert.notEqual(choice.model.id, 'anthropic/claude-sonnet-4.5');
  });

  it('refuses when the plan enables nothing', () => {
    assert.throws(
      () => router.route({ messages: ask('hi'), contextTokens: 10, allowedTiers: [] }),
      NoModelAvailable,
    );
  });

  it('will not pick a model whose context window is too small', () => {
    const narrow = new ModelRouter([
      { ...defaultCatalogue[0]!, contextWindow: 1000 },
    ]);
    assert.throws(
      () => narrow.route({ messages: ask('x'), contextTokens: 50_000, allowedTiers: ['economy'] }),
      NoModelAvailable,
    );
  });
});

describe('cost estimation', () => {
  it('computes integer micros, never a float', () => {
    const model = defaultCatalogue[1]!;
    const cost = CostEstimate.micros(model, 1_000_000, 1_000_000);
    assert.equal(cost, model.inputMicrosPerMillion + model.outputMicrosPerMillion);
    assert.ok(Number.isInteger(cost));
  });

  it('rounds up so a partial million is never free', () => {
    assert.ok(CostEstimate.micros(defaultCatalogue[1]!, 1, 1) > 0);
  });
});

describe('AiGateway', () => {
  it('completes a request and records the usage', async () => {
    const provider = new ScriptedProvider();
    const result = await gatewayWith(provider).complete({
      account,
      limits,
      messages: ask('what is in clause 4?'),
      workspaceId: null,
      maxOutputTokens: 512,
    });

    assert.match(result.text, /answered by/);
    assert.equal(result.usage.inputTokens, 100);

    const rows = await harness.database.drizzle.select().from(usageRecords);
    assert.equal(rows.length, 1);
    assert.equal(rows[0]?.outcome, 'succeeded');
    assert.ok((rows[0]?.estimatedCostMicros ?? 0) > 0);
  });

  it('refuses when no server credential is configured', async () => {
    await assert.rejects(
      gatewayWith(null).complete({
        account,
        limits,
        messages: ask('hello'),
        workspaceId: null,
        maxOutputTokens: 512,
      }),
      GatewayUnconfigured,
    );
  });

  it('enforces the daily request limit before spending anything', async () => {
    const provider = new ScriptedProvider();
    const gateway = gatewayWith(provider);
    const request = {
      account,
      limits,
      messages: ask('question'),
      workspaceId: null,
      maxOutputTokens: 128,
    };

    for (let attempt = 0; attempt < limits.dailyRequests; attempt += 1) {
      await gateway.complete(request);
    }
    const callsBefore = provider.calls.length;

    await assert.rejects(gateway.complete(request), QuotaExceeded);
    assert.equal(provider.calls.length, callsBefore, 'a blocked request must not reach the provider');
  });

  /// The bug behind "no matter which model I choose I get the small one".
  ///
  /// The candidate walk exists for free-pool saturation, which is common and usually transient. It
  /// is right when HawkVance chose the model and wrong when the person did, because answering from
  /// something they did not pick, without saying so, looks exactly like the picker being ignored.
  it('never substitutes a model the person chose, even when it is busy', async () => {
    const chosen = 'z-ai/glm-5.2:free';
    const provider = new ScriptedProvider([chosen]);

    await assert.rejects(
      liveCatalogueGateway(provider).complete({
        account,
        limits,
        messages: ask('question'),
        workspaceId: null,
        preferredModelId: chosen,
        maxOutputTokens: 128,
      }),
      ModelBusy,
    );

    assert.deepEqual(provider.calls, [chosen], 'a second model was tried behind the person back');
  });

  it('answers from the model the person chose when it is available', async () => {
    const chosen = 'z-ai/glm-5.2:free';
    const provider = new ScriptedProvider();
    const result = await liveCatalogueGateway(provider).complete({
      account,
      limits,
      messages: ask('question'),
      workspaceId: null,
      preferredModelId: chosen,
      maxOutputTokens: 128,
    });

    assert.equal(result.model, chosen);
    assert.equal(provider.calls.length, 1, 'more than one model was contacted');
  });

  it('says which model was busy, so the person can pick another', async () => {
    const chosen = 'z-ai/glm-5.2:free';
    try {
      await liveCatalogueGateway(new ScriptedProvider([chosen])).complete({
        account,
        limits,
        messages: ask('question'),
        workspaceId: null,
        preferredModelId: chosen,
        maxOutputTokens: 128,
      });
      assert.fail('a busy chosen model should not have produced an answer');
    } catch (cause) {
      assert.ok(cause instanceof ModelBusy);
      assert.match(cause.message, /busy/i);
      assert.match(cause.message, /another model/i);
    }
  });

  it('falls back to another model on a retryable failure', async () => {
    const provider = new ScriptedProvider(['z-ai/glm-4-32b']);
    const result = await gatewayWith(provider).complete({
      account,
      limits,
      messages: ask('rewrite this line'),
      workspaceId: null,
      maxOutputTokens: 128,
    });

    assert.equal(result.attemptedFallback, true);
    assert.equal(provider.calls.length, 2);
    assert.notEqual(provider.calls[1], 'z-ai/glm-4-32b');
  });

  it('does not retry a rejected credential, because it would fail identically', async () => {
    const provider = new ScriptedProvider(
      ['z-ai/glm-4-32b'],
      new ProviderFailure('openrouter', 401, 'bad key', false),
    );

    await assert.rejects(
      gatewayWith(provider).complete({
        account,
        limits,
        messages: ask('rewrite this line'),
        workspaceId: null,
        maxOutputTokens: 128,
      }),
      ProviderFailure,
    );
    assert.equal(provider.calls.length, 1, 'a non-retryable failure must not spend twice');
  });

  it('records a failed attempt rather than losing it', async () => {
    const provider = new ScriptedProvider(
      ['z-ai/glm-4-32b'],
      new ProviderFailure('openrouter', 400, 'malformed', false),
    );
    await gatewayWith(provider)
      .complete({
        account,
        limits,
        messages: ask('rewrite this line'),
        workspaceId: null,
        maxOutputTokens: 128,
      })
      .catch(() => undefined);

    const rows = await harness.database.drizzle.select().from(usageRecords);
    assert.equal(rows.length, 1);
    assert.equal(rows[0]?.outcome, 'failed:400');
    assert.equal(rows[0]?.estimatedCostMicros, 0);
  });

  it('serves a premium plan a premium model', async () => {
    const provider = new ScriptedProvider();
    const result = await gatewayWith(provider).complete({
      account,
      limits: premiumLimits,
      messages: ask('compare the indemnity clauses across these agreements'),
      workspaceId: null,
      maxOutputTokens: 512,
    });
    assert.equal(result.downgraded, false);
    assert.equal(result.complexity, 'complex');
  });

  it('records BYOK usage at zero cost, because the user paid their own provider', async () => {
    await gatewayWith(null).recordExternalUsage({
      account,
      workspaceId: null,
      provider: 'openai',
      model: 'gpt-4o-mini',
      inputTokens: 500,
      outputTokens: 200,
      latencyMs: 900,
      outcome: 'succeeded',
    });

    const rows = await harness.database.drizzle.select().from(usageRecords);
    assert.equal(rows.length, 1);
    assert.equal(rows[0]?.estimatedCostMicros, 0);
    assert.equal(rows[0]?.provider, 'openai');
  });

  it('reports usage without spending anything', async () => {
    const verdict = await gatewayWith(new ScriptedProvider()).usage(account, limits);
    assert.equal(verdict.allowed, true);
    assert.equal(verdict.usage.dailyRequests, 0);
    assert.ok(verdict.resetsAt.length > 0);
  });
});

describe('quota windows', () => {
  it('separates today from this month', () => {
    const moment = new Date('2026-06-15T13:45:00Z');
    assert.equal(QuotaLedger.startOfDay(moment).toISOString(), '2026-06-15T00:00:00.000Z');
    assert.equal(QuotaLedger.startOfMonth(moment).toISOString(), '2026-06-01T00:00:00.000Z');
    assert.equal(QuotaLedger.nextMonth(moment).toISOString(), '2026-07-01T00:00:00.000Z');
  });

  it('rolls the month over at the year boundary', () => {
    assert.equal(
      QuotaLedger.nextMonth(new Date('2026-12-20T00:00:00Z')).toISOString(),
      '2027-01-01T00:00:00.000Z',
    );
  });
});
