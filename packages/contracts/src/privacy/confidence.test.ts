import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import { Confidence, ConfidenceOutOfRange } from './confidence.js';

describe('Confidence', () => {
  it('auto-redacts above the 0.85 threshold', () => {
    assert.equal(Confidence.of(0.94).disposition, 'autoRedact');
    assert.equal(Confidence.of(0.99).disposition, 'autoRedact');
  });

  it('sends the 0.5 to 0.85 band to review, which is what the Privacy Gate renders amber', () => {
    assert.equal(Confidence.of(0.5).disposition, 'needsReview');
    assert.equal(Confidence.of(0.71).disposition, 'needsReview');
    assert.equal(Confidence.of(0.85).disposition, 'needsReview');
  });

  it('ignores detections below 0.5 rather than surfacing them', () => {
    assert.equal(Confidence.of(0.49).disposition, 'ignored');
    assert.equal(Confidence.of(0).disposition, 'ignored');
  });

  it('never leaves a value between the bands unclassified', () => {
    for (let raw = 0; raw <= 100; raw += 1) {
      const disposition = Confidence.of(raw / 100).disposition;
      assert.ok(['autoRedact', 'needsReview', 'ignored'].includes(disposition));
    }
  });

  it('rejects values outside 0 to 1', () => {
    assert.throws(() => Confidence.of(1.01), ConfidenceOutOfRange);
    assert.throws(() => Confidence.of(-0.01), ConfidenceOutOfRange);
    assert.throws(() => Confidence.of(Number.NaN), ConfidenceOutOfRange);
  });

  it('compares by value', () => {
    assert.ok(Confidence.of(0.9).exceeds(Confidence.of(0.7)));
    assert.ok(!Confidence.of(0.7).exceeds(Confidence.of(0.9)));
  });

  it('reports a whole percent for display', () => {
    assert.equal(Confidence.of(0.716).percent, 72);
  });
});
