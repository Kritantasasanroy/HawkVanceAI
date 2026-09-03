import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import { CreditCost } from './credit-cost.js';

describe('credit cost', () => {
  it('prices a question at one credit', () => {
    assert.equal(CreditCost.of('question'), 1);
  });

  it('charges more for a more thorough document scan', () => {
    assert.ok(
      CreditCost.of('documentScanQuick') < CreditCost.of('documentScanNormal'),
      'a normal scan should cost more than a quick one',
    );
    assert.ok(
      CreditCost.of('documentScanNormal') < CreditCost.of('documentScanThorough'),
      'a thorough scan should cost more than a normal one',
    );
  });

  /// Work done on the user's own machine costs them nothing, because it costs us nothing.
  it('charges nothing for a summary, which runs locally', () => {
    assert.equal(CreditCost.of('chatSummary'), 0);
  });

  it('charges nothing for a request that failed', () => {
    assert.equal(CreditCost.failure, 0);
  });

  it('hands out a copy, so a caller cannot reprice an action', () => {
    const table = CreditCost.table() as Record<string, number>;
    table.question = 999;
    assert.equal(CreditCost.of('question'), 1);
  });
});
