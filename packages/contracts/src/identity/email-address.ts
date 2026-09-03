import { z } from 'zod';

export class InvalidEmailAddress extends Error {
  readonly attempted: string;

  constructor(attempted: string) {
    super('That does not look like an email address. Check for a typo and try again.');
    this.name = 'InvalidEmailAddress';
    this.attempted = attempted;
  }
}

export class EmailAddress {
  static readonly schema = z
    .string()
    .trim()
    .min(3)
    .max(254)
    .email()
    .transform((raw) => EmailAddress.parse(raw));

  readonly localPart: string;
  readonly domain: string;

  private constructor(localPart: string, domain: string) {
    this.localPart = localPart;
    this.domain = domain;
    Object.freeze(this);
  }

  static parse(raw: string): EmailAddress {
    const trimmed = raw.trim();
    const separator = trimmed.lastIndexOf('@');
    if (separator <= 0 || separator === trimmed.length - 1) {
      throw new InvalidEmailAddress(raw);
    }

    const localPart = trimmed.slice(0, separator);
    const domain = trimmed.slice(separator + 1).toLowerCase();
    if (!EmailAddress.isPlausibleDomain(domain) || localPart.includes(' ')) {
      throw new InvalidEmailAddress(raw);
    }

    return new EmailAddress(localPart, domain);
  }

  private static isPlausibleDomain(domain: string): boolean {
    if (domain.length < 3 || domain.length > 253) {
      return false;
    }
    if (domain.startsWith('.') || domain.endsWith('.') || domain.includes('..')) {
      return false;
    }
    return domain.includes('.') && /^[a-z0-9.-]+$/.test(domain);
  }

  get canonical(): string {
    return `${this.localPart}@${this.domain}`;
  }

  equals(other: EmailAddress): boolean {
    return this.canonical === other.canonical;
  }

  toString(): string {
    return this.canonical;
  }

  toJSON(): string {
    return this.canonical;
  }
}
