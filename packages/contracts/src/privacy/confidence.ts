import { z } from 'zod';
import type { RedactionDisposition } from './pii-category.js';

export class ConfidenceOutOfRange extends Error {
  readonly attempted: number;

  constructor(attempted: number) {
    super(`Confidence must be between 0 and 1, received ${attempted}.`);
    this.name = 'ConfidenceOutOfRange';
    this.attempted = attempted;
  }
}

export class Confidence {
  static readonly autoRedactAbove = 0.85;
  static readonly reviewAbove = 0.5;

  static readonly schema = z
    .number()
    .min(0)
    .max(1)
    .transform((value) => Confidence.of(value));

  readonly value: number;

  private constructor(value: number) {
    this.value = value;
    Object.freeze(this);
  }

  static of(value: number): Confidence {
    if (!Number.isFinite(value) || value < 0 || value > 1) {
      throw new ConfidenceOutOfRange(value);
    }
    return new Confidence(value);
  }

  get disposition(): RedactionDisposition {
    if (this.value > Confidence.autoRedactAbove) {
      return 'autoRedact';
    }
    if (this.value >= Confidence.reviewAbove) {
      return 'needsReview';
    }
    return 'ignored';
  }

  exceeds(other: Confidence): boolean {
    return this.value > other.value;
  }

  get percent(): number {
    return Math.round(this.value * 100);
  }

  toJSON(): number {
    return this.value;
  }
}
