import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import { EmailAddress, InvalidEmailAddress } from './email-address.js';

describe('EmailAddress', () => {
  it('lowercases the domain but preserves local-part case', () => {
    const address = EmailAddress.parse('Deepak@LemonIdeas.IN');
    assert.equal(address.canonical, 'Deepak@lemonideas.in');
    assert.equal(address.domain, 'lemonideas.in');
    assert.equal(address.localPart, 'Deepak');
  });

  it('trims surrounding whitespace', () => {
    assert.equal(EmailAddress.parse('  user@example.com  ').canonical, 'user@example.com');
  });

  it('treats addresses differing only by domain case as equal', () => {
    const left = EmailAddress.parse('user@Example.COM');
    const right = EmailAddress.parse('user@example.com');
    assert.ok(left.equals(right));
  });

  it('treats addresses differing by local-part case as distinct', () => {
    const left = EmailAddress.parse('User@example.com');
    const right = EmailAddress.parse('user@example.com');
    assert.ok(!left.equals(right));
  });

  it('splits on the last @ so quoted local parts survive', () => {
    const address = EmailAddress.parse('a@b@example.com');
    assert.equal(address.localPart, 'a@b');
    assert.equal(address.domain, 'example.com');
  });

  it('rejects addresses without a domain dot', () => {
    assert.throws(() => EmailAddress.parse('user@localhost'), InvalidEmailAddress);
  });

  it('rejects a missing local part', () => {
    assert.throws(() => EmailAddress.parse('@example.com'), InvalidEmailAddress);
  });

  it('rejects a missing domain', () => {
    assert.throws(() => EmailAddress.parse('user@'), InvalidEmailAddress);
  });

  it('rejects consecutive dots in the domain', () => {
    assert.throws(() => EmailAddress.parse('user@ex..ample.com'), InvalidEmailAddress);
  });

  it('rejects a space in the local part', () => {
    assert.throws(() => EmailAddress.parse('first last@example.com'), InvalidEmailAddress);
  });

  it('serialises to its canonical string', () => {
    assert.equal(JSON.stringify({ to: EmailAddress.parse('User@EXAMPLE.com') }), '{"to":"User@example.com"}');
  });

  it('is frozen once constructed', () => {
    const address = EmailAddress.parse('user@example.com');
    assert.ok(Object.isFrozen(address));
  });
});
