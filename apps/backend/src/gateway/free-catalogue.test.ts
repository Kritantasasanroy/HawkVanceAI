import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import { freeCatalogue } from '@hawkvance/llm';

/// The catalogue is offered to people on every plan, including the free one, on the understanding
/// that nothing in it costs them anything. That only stays true if it stays enforced.
describe('the model catalogue', () => {
  it('contains only models that are free on OpenRouter', () => {
    const paid = freeCatalogue.filter(
      (entry) => !entry.id.endsWith(':free') && entry.id !== 'openrouter/free',
    );
    assert.deepEqual(
      paid.map((entry) => entry.id),
      [],
      'a paid model reached a catalogue every plan is allowed to use',
    );
  });

  it('offers capable models, not only small ones', () => {
    const capable = freeCatalogue.filter(
      (entry) => entry.enabled && (entry.tier === 'premium' || entry.tier === 'standard'),
    );
    assert.ok(capable.length > 0, 'nothing capable is on offer');
  });

  it('gives every model a label a person could recognise', () => {
    for (const entry of freeCatalogue) {
      assert.ok(entry.label.trim().length > 0, `${entry.id} has no label`);
      assert.notEqual(entry.label, entry.id, `${entry.id} shows its raw id as a label`);
    }
  });
});
