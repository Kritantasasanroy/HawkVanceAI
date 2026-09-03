import assert from 'node:assert/strict';
import { afterAll, beforeAll, beforeEach, describe, it } from 'vitest';
import { eq } from 'drizzle-orm';
import { accounts, devices } from '../db/schema.js';
import { TestHarness, TestIdentityProvider, authBaseUrl, issuer } from '../testing/harness.js';

const neonUserId = 'neon-user-01HZX';
const email = 'deepak@lemonideas.in';
const device = { name: 'Test Workstation', platform: 'windows', appVersion: '0.1.0' };

let harness: TestHarness;

const get = async (url: string, token?: string) =>
  harness.server.fastify.inject({
    method: 'GET',
    url,
    ...(token === undefined ? {} : { headers: { authorization: `Bearer ${token}` } }),
  });

const signedIn = async (overrides: Partial<{ sub: string; email: string; name: string }> = {}) =>
  harness.identity.tokenFor({ sub: neonUserId, email, ...overrides });

beforeAll(async () => {
  harness = await TestHarness.start();
});

afterAll(async () => {
  await harness.stop();
});

beforeEach(async () => {
  await harness.reset();
});

describe('identity token verification', () => {
  it('rejects a request with no bearer token', async () => {
    const response = await get('/auth/me');
    assert.equal(response.statusCode, 401);
    assert.equal((response.json() as { error: { code: string } }).error.code, 'identity_token_rejected');
  });

  it('rejects a token signed by a key HawkVance does not trust', async () => {
    const forged = await TestIdentityProvider.foreignToken(neonUserId, email);
    assert.equal((await get('/auth/me', forged)).statusCode, 401);
  });

  it('rejects a token from the wrong issuer', async () => {
    const wrongIssuer = await harness.identity.tokenFor({
      sub: neonUserId,
      email,
      withIssuer: 'https://attacker.example/auth',
    });
    assert.equal((await get('/auth/me', wrongIssuer)).statusCode, 401);
  });

  /// The bug that let a correct sign-in fail at the last step.
  ///
  /// Neon issues tokens from the bare origin, while the auth endpoint lives under a path. The
  /// backend derived the expected issuer from the path, so every genuine token was refused with
  /// "unexpected iss claim value" even though its signature was perfectly valid. The old tests
  /// signed with the same wrong value, so they agreed with the bug instead of catching it.
  it('accepts a token issued by the origin, which is what Neon actually signs', async () => {
    const realistic = await harness.identity.tokenFor({
      sub: neonUserId,
      email,
      withIssuer: issuer,
    });
    assert.equal((await get('/auth/me', realistic)).statusCode, 200);
  });

  it('rejects a token issued by the auth path rather than the origin', async () => {
    const pathIssuer = await harness.identity.tokenFor({
      sub: neonUserId,
      email,
      withIssuer: authBaseUrl,
    });
    assert.equal((await get('/auth/me', pathIssuer)).statusCode, 401);
  });

  it('rejects an expired token', async () => {
    const expired = await harness.identity.tokenFor({ sub: neonUserId, email, expiresIn: '-1s' });
    assert.equal((await get('/auth/me', expired)).statusCode, 401);
  });

  it('rejects a structurally invalid token', async () => {
    assert.equal((await get('/auth/me', 'not.a.jwt')).statusCode, 401);
  });

  it('rejects a valid signature whose payload carries no email', async () => {
    const noEmail = await harness.identity.tokenFor({ sub: neonUserId, email: 'not-an-email' });
    assert.equal((await get('/auth/me', noEmail)).statusCode, 401);
  });
});

describe('PATCH /auth/me', () => {
  const patch = async (token: string, payload: unknown) =>
    harness.server.fastify.inject({
      method: 'PATCH',
      url: '/auth/me',
      headers: { authorization: `Bearer ${token}` },
      payload,
    });

  it('records a name and an occupation', async () => {
    const token = await signedIn();
    await get('/auth/me', token);

    const response = await patch(token, { displayName: 'Deepak', occupation: 'Product designer' });
    assert.equal(response.statusCode, 200);

    const account = (response.json() as { account: { displayName: string; occupation: string } }).account;
    assert.equal(account.displayName, 'Deepak');
    assert.equal(account.occupation, 'Product designer');
  });

  /// Null means the person left it blank, which is a legitimate answer and must not be stored as
  /// the string "null" or rejected.
  it('accepts a cleared occupation', async () => {
    const token = await signedIn();
    await get('/auth/me', token);
    await patch(token, { occupation: 'Architect' });

    const response = await patch(token, { occupation: null });
    assert.equal(response.statusCode, 200);
    assert.equal((response.json() as { account: { occupation: string | null } }).account.occupation, null);
  });

  it('marks the person as asked, so the question is not repeated every launch', async () => {
    const token = await signedIn();
    const before = await get('/auth/me', token);
    assert.equal((before.json() as { account: { onboardedAt: string | null } }).account.onboardedAt, null);

    const response = await patch(token, { displayName: 'Deepak' });
    assert.notEqual(
      (response.json() as { account: { onboardedAt: string | null } }).account.onboardedAt,
      null,
      'a completed profile step was not recorded',
    );
  });

  /// The account comes from the verified token and never from the body, so there is no id a caller
  /// could substitute. This proves an attempt to name one is simply ignored.
  it('changes only the caller own account, whatever the body claims', async () => {
    const mine = await signedIn();
    const theirs = await signedIn({ sub: 'neon-user-other', email: 'other@lemonideas.in' });
    await get('/auth/me', mine);
    await get('/auth/me', theirs);

    await patch(mine, { displayName: 'Mine', id: 'some-other-account', plan: 'enterprise' });

    const other = await get('/auth/me', theirs);
    const account = (other.json() as { account: { displayName: string; plan: string } }).account;
    assert.notEqual(account.displayName, 'Mine', 'one account edit reached another account');
    assert.equal(account.plan, 'beta', 'a profile edit changed a plan');
  });

  it('refuses an empty update rather than pretending it did something', async () => {
    const token = await signedIn();
    await get('/auth/me', token);
    assert.equal((await patch(token, {})).statusCode, 400);
  });

  it('refuses an unauthenticated caller', async () => {
    const response = await harness.server.fastify.inject({
      method: 'PATCH',
      url: '/auth/me',
      payload: { displayName: 'Nobody' },
    });
    assert.equal(response.statusCode, 401);
  });
});

describe('GET /auth/me', () => {
  it('provisions the account on first sight of a Neon identity', async () => {
    const before = await harness.database.drizzle.select().from(accounts);
    assert.equal(before.length, 0);

    const response = await get('/auth/me', await signedIn());

    assert.equal(response.statusCode, 200);
    const body = response.json() as { account: { email: string; status: string; plan: string } };
    assert.equal(body.account.email, email);
    assert.equal(body.account.status, 'active');
    assert.equal(body.account.plan, 'beta');

    const after = await harness.database.drizzle.select().from(accounts);
    assert.equal(after.length, 1);
    assert.equal(after[0]?.neonUserId, neonUserId);
  });

  it('does not create a second account on a repeat sign-in', async () => {
    await get('/auth/me', await signedIn());
    await get('/auth/me', await signedIn());
    await get('/auth/me', await signedIn());

    const rows = await harness.database.drizzle.select().from(accounts);
    assert.equal(rows.length, 1);
  });

  it('returns the plan limits alongside the account', async () => {
    const body = (await get('/auth/me', await signedIn())).json() as {
      limits: { monthlyTokens: number; byokAllowed: boolean; allowedModelTiers: string[] };
    };
    assert.equal(body.limits.monthlyTokens, 500_000);
    assert.equal(body.limits.byokAllowed, true);
    assert.deepEqual(body.limits.allowedModelTiers, ['economy', 'standard']);
  });

  it('uses the token display name when Neon supplies one', async () => {
    const body = (await get('/auth/me', await signedIn({ name: 'Deepak' }))).json() as {
      account: { displayName: string };
    };
    assert.equal(body.account.displayName, 'Deepak');
  });

  it('falls back to the local part of the address when Neon supplies no name', async () => {
    const body = (await get('/auth/me', await signedIn())).json() as {
      account: { displayName: string };
    };
    assert.equal(body.account.displayName, 'deepak');
  });

  it('adopts an existing account when the Neon user id changes for a known address', async () => {
    await get('/auth/me', await signedIn());
    const original = await harness.database.drizzle.select().from(accounts);

    const recreated = await harness.identity.tokenFor({ sub: 'neon-user-RECREATED', email });
    const response = await get('/auth/me', recreated);

    assert.equal(response.statusCode, 200);
    const rows = await harness.database.drizzle.select().from(accounts);
    assert.equal(rows.length, 1, 'a recreated Neon user must not fork the HawkVance account');
    assert.equal(rows[0]?.id, original[0]?.id);
    assert.equal(rows[0]?.neonUserId, 'neon-user-RECREATED');
  });

  it('refuses a suspended account even with a perfectly valid token', async () => {
    await get('/auth/me', await signedIn());
    await harness.database.drizzle
      .update(accounts)
      .set({ status: 'suspended', suspendedReason: 'abuse' })
      .where(eq(accounts.neonUserId, neonUserId));

    const response = await get('/auth/me', await signedIn());
    assert.equal(response.statusCode, 403);
    assert.equal((response.json() as { error: { code: string } }).error.code, 'account_not_eligible');
  });
});

describe('devices', () => {
  const registerDevice = async (token: string, payload: unknown = device) =>
    harness.server.fastify.inject({
      method: 'POST',
      url: '/auth/devices',
      headers: { authorization: `Bearer ${token}` },
      payload,
    });

  it('registers a device against the account', async () => {
    const token = await signedIn();
    const response = await registerDevice(token);

    assert.equal(response.statusCode, 200);
    const rows = await harness.database.drizzle.select().from(devices);
    assert.equal(rows.length, 1);
    assert.equal(rows[0]?.name, device.name);
  });

  it('is idempotent for the same machine rather than piling up duplicates', async () => {
    const token = await signedIn();
    await registerDevice(token);
    await registerDevice(token, { ...device, appVersion: '0.2.0' });

    const rows = await harness.database.drizzle.select().from(devices);
    assert.equal(rows.length, 1);
    assert.equal(rows[0]?.appVersion, '0.2.0', 'a re-registration should update the version in place');
  });

  it('rejects a malformed device registration', async () => {
    const response = await registerDevice(await signedIn(), { name: '', platform: 'toaster' });
    assert.equal(response.statusCode, 400);
  });

  it('lists the account devices', async () => {
    const token = await signedIn();
    await registerDevice(token);

    const response = await get('/auth/devices', token);
    assert.equal(response.statusCode, 200);
    const body = response.json() as { devices: Array<{ name: string; platform: string }> };
    assert.equal(body.devices.length, 1);
    assert.equal(body.devices[0]?.name, device.name);
  });

  it('revokes a device', async () => {
    const token = await signedIn();
    const registered = (await registerDevice(token)).json() as { deviceId: string };

    const removed = await harness.server.fastify.inject({
      method: 'DELETE',
      url: `/auth/devices/${registered.deviceId}`,
      headers: { authorization: `Bearer ${token}` },
    });
    assert.equal(removed.statusCode, 204);

    const rows = await harness.database.drizzle.select().from(devices);
    assert.equal(rows.length, 0);
  });

  it('will not let one account revoke another account’s device', async () => {
    const mine = await signedIn();
    const registered = (await registerDevice(mine)).json() as { deviceId: string };

    const theirs = await harness.identity.tokenFor({
      sub: 'neon-user-OTHER',
      email: 'someone.else@example.com',
    });
    const response = await harness.server.fastify.inject({
      method: 'DELETE',
      url: `/auth/devices/${registered.deviceId}`,
      headers: { authorization: `Bearer ${theirs}` },
    });

    assert.equal(response.statusCode, 404, 'a cross-account delete must not confirm the device exists');
    const rows = await harness.database.drizzle.select().from(devices);
    assert.equal(rows.length, 1);
  });

  it('requires a token for every device route', async () => {
    assert.equal((await get('/auth/devices')).statusCode, 401);
    assert.equal(
      (await harness.server.fastify.inject({ method: 'POST', url: '/auth/devices', payload: device }))
        .statusCode,
      401,
    );
  });
});

describe('what HawkVance never handles', () => {
  it('exposes no OTP endpoint, because codes are Neon’s business and never reach us', async () => {
    for (const url of ['/auth/otp/request', '/auth/otp/verify', '/auth/refresh', '/auth/logout']) {
      const response = await harness.server.fastify.inject({ method: 'POST', url, payload: {} });
      assert.equal(response.statusCode, 404, `${url} should not exist`);
    }
  });

  it('stores no credential column on the account', async () => {
    await get('/auth/me', await signedIn());
    const [row] = await harness.database.drizzle.select().from(accounts);
    const serialised = JSON.stringify(row);

    for (const forbidden of ['password', 'passwordHash', 'otp', 'codeHash', 'refreshToken']) {
      assert.ok(!serialised.includes(forbidden), `account row carries a ${forbidden}`);
    }
  });
});
