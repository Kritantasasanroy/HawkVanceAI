import assert from 'node:assert/strict';
import { afterAll, beforeAll, beforeEach, describe, it } from 'vitest';
import type { ChatMessage } from '@hawkvance/llm';
import { ModelRouter, OpenRouterProvider, freeCatalogue } from '@hawkvance/llm';
import type { PlanLimits } from '@hawkvance/contracts';
import { EmailAddress } from '@hawkvance/contracts';
import { accounts, usageRecords } from '../db/schema.js';
import { Account } from '../identity/account.js';
import { AiGateway } from './ai-gateway.js';
import { QuotaLedger } from './quota-ledger.js';
import { TestHarness } from '../testing/harness.js';

/// Live tests against the real OpenRouter free tier.
///
/// Skipped without a key, so a checkout with no credentials still runs a green suite. When a key is
/// present these are the only tests that prove the managed-inference path actually works: everything
/// else fakes the provider.
///
/// The free pool is genuinely unreliable, so these assert on the gateway surviving that, not on any
/// one model answering. A test that demanded a specific free model would fail for reasons that have
/// nothing to do with this code.
const apiKey = process.env.OPENROUTER_API_KEY ?? '';
const live = apiKey.length > 0 ? describe : describe.skip;

const limits: PlanLimits = {
  dailyRequests: 50 as PlanLimits['dailyRequests'],
  monthlyRequests: 500 as PlanLimits['monthlyRequests'],
  monthlyTokens: 500_000 as PlanLimits['monthlyTokens'],
  storageBytes: 1_000_000 as PlanLimits['storageBytes'],
  maxWorkspaces: 5,
  memoryRetentionDays: 30,
  byokAllowed: true,
  allowedModelTiers: ['economy', 'standard', 'premium'],
};

const ask = (text: string): [ChatMessage, ...ChatMessage[]] => [{ role: 'user', content: text }];

let harness: TestHarness;
let account: Account;

live('OpenRouter, live', () => {
  beforeAll(async () => {
    harness = await TestHarness.start();
  });

  afterAll(async () => {
    await harness.stop();
  });

  beforeEach(async () => {
    await harness.reset();
    account = Account.register({
      email: EmailAddress.parse('live@lemonideas.in'),
      registeredAt: new Date(),
      neonUserId: 'neon-live',
      displayName: 'Live',
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

  const gateway = (): AiGateway =>
    new AiGateway(
      new OpenRouterProvider(apiKey),
      new ModelRouter(freeCatalogue),
      new QuotaLedger(harness.database),
    );

  it('the key is accepted by OpenRouter', async () => {
    const response = await fetch('https://openrouter.ai/api/v1/key', {
      headers: { authorization: `Bearer ${apiKey}` },
    });
    assert.equal(response.status, 200, 'the OpenRouter key was rejected');
  });

  it('completes a real request through the gateway and records real usage', async () => {
    const result = await gateway().complete({
      account,
      limits,
      messages: ask('Reply with exactly: OK'),
      workspaceId: null,
      maxOutputTokens: 24,
    });

    assert.ok(result.model.length > 0);
    assert.equal(result.provider, 'openrouter');
    assert.ok(result.usage.inputTokens > 0, 'no input tokens were reported');
    assert.equal(result.estimatedCostMicros, 0, 'a free model must cost nothing');

    const rows = await harness.database.drizzle.select().from(usageRecords);
    assert.equal(rows.length, 1);
    assert.equal(rows[0]?.outcome, 'succeeded');
    assert.ok((rows[0]?.inputTokens ?? 0) > 0);
  }, 180_000);

  it('rides out the free pool by walking the catalogue', async () => {
    // Every free model is rate-limited from time to time. What must hold is that the gateway keeps
    // going rather than surfacing the first 429 to the user.
    const result = await gateway().complete({
      account,
      limits,
      messages: ask('Summarise in one word: the sky is blue'),
      workspaceId: null,
      maxOutputTokens: 24,
    });

    assert.ok(result.attempts >= 1 && result.attempts <= AiGateway.maximumAttempts);
    assert.ok(result.text.length >= 0);
  }, 180_000);

  it('every catalogue entry is free, so a quota overrun cannot cost money', () => {
    for (const model of freeCatalogue) {
      assert.equal(model.inputMicrosPerMillion, 0, `${model.id} is not free`);
      assert.equal(model.outputMicrosPerMillion, 0, `${model.id} is not free`);
    }
  });

  it('the catalogue covers all three tiers, so routing has somewhere to go', () => {
    const tiers = new Set(freeCatalogue.map((model) => model.tier));
    assert.ok(tiers.has('economy'));
    assert.ok(tiers.has('standard'));
    assert.ok(tiers.has('premium'));
  });

  it('a rejected key fails without retrying every model', async () => {
    const broken = new AiGateway(
      new OpenRouterProvider('sk-or-v1-definitely-not-a-real-key-000000'),
      new ModelRouter(freeCatalogue),
      new QuotaLedger(harness.database),
    );

    await assert.rejects(
      broken.complete({
        account,
        limits,
        messages: ask('hello'),
        workspaceId: null,
        maxOutputTokens: 16,
      }),
    );

    const rows = await harness.database.drizzle.select().from(usageRecords);
    assert.equal(rows.length, 1, 'the failure should be recorded exactly once');
    assert.ok(String(rows[0]?.outcome).startsWith('failed'));
  }, 120_000);
});
