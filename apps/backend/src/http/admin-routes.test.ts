import assert from 'node:assert/strict';
import { afterAll, beforeAll, beforeEach, describe, it } from 'vitest';
import { eq } from 'drizzle-orm';
import { accounts, adminAuditEntries } from '../db/schema.js';
import { TestHarness } from '../testing/harness.js';

let harness: TestHarness;

const signIn = async (sub: string, email: string) => harness.identity.tokenFor({ sub, email });

/// Provisions an account by signing in, then promotes it directly in the database. Promoting via
/// the API would need an existing superAdmin, which is the bootstrap problem every RBAC system has.
const asRole = async (sub: string, email: string, role: string): Promise<string> => {
  const token = await signIn(sub, email);
  await harness.server.fastify.inject({
    method: 'GET',
    url: '/auth/me',
    headers: { authorization: `Bearer ${token}` },
  });
  await harness.database.drizzle.update(accounts).set({ role }).where(eq(accounts.neonUserId, sub));
  return token;
};

const get = async (url: string, token?: string) =>
  harness.server.fastify.inject({
    method: 'GET',
    url,
    ...(token === undefined ? {} : { headers: { authorization: `Bearer ${token}` } }),
  });

const post = async (url: string, token: string, payload: unknown) =>
  harness.server.fastify.inject({
    method: 'POST',
    url,
    headers: { authorization: `Bearer ${token}` },
    payload,
  });

const idOf = async (sub: string): Promise<string> => {
  const [row] = await harness.database.drizzle
    .select({ id: accounts.id })
    .from(accounts)
    .where(eq(accounts.neonUserId, sub));
  assert.ok(row, 'the account should exist');
  return row.id;
};

beforeAll(async () => {
  harness = await TestHarness.start();
});

afterAll(async () => {
  await harness.stop();
});

beforeEach(async () => {
  await harness.reset();
});

describe('admin access control', () => {
  it('refuses an unauthenticated request', async () => {
    assert.equal((await get('/admin/overview')).statusCode, 401);
  });

  it('refuses an ordinary member', async () => {
    const token = await asRole('neon-member', 'member@lemonideas.in', 'member');
    const response = await get('/admin/overview', token);

    assert.equal(response.statusCode, 403);
    assert.equal((response.json() as { error: { code: string } }).error.code, 'not_permitted');
  });

  it('allows a read-only analyst to see the overview', async () => {
    const token = await asRole('neon-analyst', 'analyst@lemonideas.in', 'analyst');
    assert.equal((await get('/admin/overview', token)).statusCode, 200);
  });

  it('refuses an analyst a write action', async () => {
    const analyst = await asRole('neon-analyst', 'analyst@lemonideas.in', 'analyst');
    await asRole('neon-victim', 'victim@lemonideas.in', 'member');
    const victim = await idOf('neon-victim');

    const response = await post(`/admin/accounts/${victim}/suspend`, analyst, {
      reason: 'testing',
    });
    assert.equal(response.statusCode, 403);
  });

  it('refuses support a write action', async () => {
    const support = await asRole('neon-support', 'support@lemonideas.in', 'support');
    await asRole('neon-victim', 'victim@lemonideas.in', 'member');
    const victim = await idOf('neon-victim');

    assert.equal(
      (await post(`/admin/accounts/${victim}/suspend`, support, { reason: 'testing' })).statusCode,
      403,
    );
  });

  it('will not let an admin promote anyone, including themselves', async () => {
    const admin = await asRole('neon-admin', 'admin@lemonideas.in', 'admin');
    const self = await idOf('neon-admin');

    const response = await post(`/admin/accounts/${self}/role`, admin, { role: 'superAdmin' });

    assert.equal(response.statusCode, 403, 'role escalation must be superAdmin only');
    const [row] = await harness.database.drizzle
      .select({ role: accounts.role })
      .from(accounts)
      .where(eq(accounts.id, self));
    assert.equal(row?.role, 'admin');
  });

  it('allows a superAdmin to change a role', async () => {
    const superAdmin = await asRole('neon-super', 'super@lemonideas.in', 'superAdmin');
    await asRole('neon-target', 'target@lemonideas.in', 'member');
    const target = await idOf('neon-target');

    const response = await post(`/admin/accounts/${target}/role`, superAdmin, { role: 'analyst' });
    assert.equal(response.statusCode, 200);
    assert.equal((response.json() as { role: string }).role, 'analyst');
  });
});

describe('admin actions are audited', () => {
  it('records a suspension with both the old and new value', async () => {
    const admin = await asRole('neon-admin', 'admin@lemonideas.in', 'admin');
    await asRole('neon-victim', 'victim@lemonideas.in', 'member');
    const victim = await idOf('neon-victim');

    const response = await post(`/admin/accounts/${victim}/suspend`, admin, {
      reason: 'payment dispute',
    });
    assert.equal(response.statusCode, 200);

    const [entry] = await harness.database.drizzle.select().from(adminAuditEntries);
    assert.ok(entry);
    assert.equal(entry.action, 'account.suspend');
    assert.deepEqual(entry.previousValue, { status: 'active' });
    assert.deepEqual(entry.nextValue, { status: 'suspended', reason: 'payment dispute' });
    assert.equal(entry.subjectAccountId, victim);
  });

  it('records a plan change', async () => {
    const admin = await asRole('neon-admin', 'admin@lemonideas.in', 'admin');
    await asRole('neon-target', 'target@lemonideas.in', 'member');
    const target = await idOf('neon-target');

    await post(`/admin/accounts/${target}/plan`, admin, { plan: 'pro' });

    const [entry] = await harness.database.drizzle.select().from(adminAuditEntries);
    assert.equal(entry?.action, 'account.changePlan');
    assert.deepEqual(entry?.nextValue, { plan: 'pro' });
  });

  it('rejects a suspension with no stated reason', async () => {
    const admin = await asRole('neon-admin', 'admin@lemonideas.in', 'admin');
    await asRole('neon-victim', 'victim@lemonideas.in', 'member');
    const victim = await idOf('neon-victim');

    assert.equal((await post(`/admin/accounts/${victim}/suspend`, admin, {})).statusCode, 400);
    assert.equal(
      (await harness.database.drizzle.select().from(adminAuditEntries)).length,
      0,
      'a rejected action must not be audited as if it happened',
    );
  });

  it('a suspended account can no longer sign in', async () => {
    const admin = await asRole('neon-admin', 'admin@lemonideas.in', 'admin');
    const victimToken = await asRole('neon-victim', 'victim@lemonideas.in', 'member');
    const victim = await idOf('neon-victim');

    await post(`/admin/accounts/${victim}/suspend`, admin, { reason: 'abuse' });

    assert.equal((await get('/auth/me', victimToken)).statusCode, 403);
  });

  it('reactivation restores access', async () => {
    const admin = await asRole('neon-admin', 'admin@lemonideas.in', 'admin');
    const victimToken = await asRole('neon-victim', 'victim@lemonideas.in', 'member');
    const victim = await idOf('neon-victim');

    await post(`/admin/accounts/${victim}/suspend`, admin, { reason: 'mistake' });
    await post(`/admin/accounts/${victim}/reactivate`, admin, {});

    assert.equal((await get('/auth/me', victimToken)).statusCode, 200);
  });
});

describe('the admin privacy boundary', () => {
  it('exposes no route that could return customer content', async () => {
    const admin = await asRole('neon-admin', 'admin@lemonideas.in', 'admin');

    for (const url of [
      '/admin/documents',
      '/admin/memories',
      '/admin/conversations',
      '/admin/accounts/any/documents',
    ]) {
      assert.equal((await get(url, admin)).statusCode, 404, `${url} must not exist`);
    }
  });

  it('returns only metadata in the account list', async () => {
    const admin = await asRole('neon-admin', 'admin@lemonideas.in', 'admin');
    const body = (await get('/admin/accounts', admin)).json() as {
      accounts: Array<Record<string, unknown>>;
    };

    assert.ok(body.accounts.length > 0);
    const fields = Object.keys(body.accounts[0] ?? {});
    assert.deepEqual(fields.sort(), [
      'createdAt',
      'displayName',
      'email',
      'id',
      'lastSeenAt',
      'plan',
      'role',
      'status',
    ]);
  });

  it('summarises AI usage by model without naming what was asked', async () => {
    const admin = await asRole('neon-admin', 'admin@lemonideas.in', 'admin');
    const response = await get('/admin/usage', admin);

    assert.equal(response.statusCode, 200);
    const body = response.json() as { models: Array<Record<string, unknown>> };
    for (const row of body.models) {
      assert.ok(!('prompt' in row) && !('content' in row) && !('text' in row));
    }
  });
});
