#!/usr/bin/env node
/**
 * Live end-to-end check against real services.
 *
 * Unlike the test suites, this one talks to the actual Neon database, the actual Neon Auth JWKS,
 * and the actual OpenRouter free models. It exists to answer the question the unit tests cannot:
 * does this work against the real world, right now, with these credentials.
 *
 *   node scripts/e2e-live.mjs
 *
 * Exits non-zero if any check fails, so it is usable in CI.
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');

/// pnpm keeps packages in a virtual store, so `postgres` is not at the workspace root. Resolving
/// from the backend, where it is a declared dependency, finds it wherever pnpm actually put it.
/// The file:// conversion is needed because Node rejects a bare Windows drive letter as a protocol.
const openDatabase = async () => {
  const { createRequire } = await import('node:module');
  const require = createRequire(pathToFileURL(path.join(root, 'apps/backend/package.json')).href);
  const postgres = (await import(pathToFileURL(require.resolve('postgres')).href)).default;
  return postgres(env.DATABASE_URL, { max: 1, onnotice: () => {} });
};

// -------------------------------------------------------------------------- env

const env = Object.fromEntries(
  readFileSync(path.join(root, '.env'), 'utf8')
    .split('\n')
    .filter((line) => line.trim() && !line.trim().startsWith('#'))
    .map((line) => {
      const at = line.indexOf('=');
      return [line.slice(0, at).trim(), line.slice(at + 1).trim()];
    }),
);

// -------------------------------------------------------------------------- harness

let passed = 0;
let failed = 0;
const failures = [];

const check = async (name, run) => {
  const started = Date.now();
  try {
    const detail = await run();
    passed += 1;
    console.log(`  PASS  ${name}${detail ? `  ${detail}` : ''}  (${Date.now() - started}ms)`);
  } catch (cause) {
    failed += 1;
    const message = cause instanceof Error ? cause.message : String(cause);
    failures.push(`${name}: ${message}`);
    console.log(`  FAIL  ${name}  ${message}`);
  }
};

const expect = (condition, message) => {
  if (!condition) {
    throw new Error(message);
  }
};

const section = (title) => console.log(`\n${title}`);

// -------------------------------------------------------------------------- checks

section('Neon database');

await check('database reachable and hawkvance schema present', async () => {
  const sql = await openDatabase();
  try {
    const tables = await sql`
      select table_name from information_schema.tables where table_schema = 'hawkvance'
    `;
    const names = tables.map((row) => row.table_name).sort();
    expect(names.includes('accounts'), 'accounts table missing');
    expect(names.includes('usage_records'), 'usage_records table missing');
    return `${names.length} tables`;
  } finally {
    await sql.end({ timeout: 5 });
  }
});

await check('plan limits are seeded', async () => {
  const sql = await openDatabase();
  try {
    const rows = await sql`select tier from hawkvance.plan_limits order by tier`;
    expect(rows.length === 4, `expected 4 plans, found ${rows.length}`);
    return rows.map((row) => row.tier).join(', ');
  } finally {
    await sql.end({ timeout: 5 });
  }
});

section('Neon Auth');

await check('JWKS is published and usable', async () => {
  const response = await fetch(env.NEON_JWKS_URL);
  expect(response.ok, `JWKS returned ${response.status}`);
  const jwks = await response.json();
  expect(Array.isArray(jwks.keys) && jwks.keys.length > 0, 'JWKS has no keys');
  return `${jwks.keys.length} key, alg ${jwks.keys[0].alg}`;
});

await check('the OTP endpoint exists and validates its input', async () => {
  // Deliberately malformed: this proves the endpoint is live and validating without sending a
  // real person an email every time the check runs.
  const response = await fetch(`${env.NEON_AUTH_URL}/email-otp/send-verification-otp`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ email: 'not-an-email', type: 'sign-in' }),
  });
  expect(response.status === 400 || response.status === 422, `expected a validation error, got ${response.status}`);
  return `rejects bad input with ${response.status}`;
});

section('OpenRouter');

await check('key is valid', async () => {
  const response = await fetch('https://openrouter.ai/api/v1/key', {
    headers: { authorization: `Bearer ${env.OPENROUTER_API_KEY}` },
  });
  expect(response.ok, `key check returned ${response.status}`);
  const body = await response.json();
  return `free tier: ${body.data.is_free_tier}, usage ${body.data.usage}`;
});

let workingFreeModels = [];

await check('free models are discoverable', async () => {
  const response = await fetch('https://openrouter.ai/api/v1/models');
  expect(response.ok, `model list returned ${response.status}`);
  const body = await response.json();
  const free = body.data.filter(
    (model) =>
      Number(model.pricing?.prompt ?? '0') === 0 &&
      Number(model.pricing?.completion ?? '0') === 0 &&
      (model.architecture?.output_modalities ?? ['text']).includes('text') &&
      !(model.architecture?.output_modalities ?? []).includes('audio'),
  );
  expect(free.length > 0, 'no free chat models found');
  workingFreeModels = free.map((model) => model.id);
  return `${free.length} free chat models`;
});

await check('at least one free model answers', async () => {
  const attempts = workingFreeModels.slice(0, 8);
  const errors = [];

  for (const model of attempts) {
    const response = await fetch('https://openrouter.ai/api/v1/chat/completions', {
      method: 'POST',
      headers: {
        authorization: `Bearer ${env.OPENROUTER_API_KEY}`,
        'content-type': 'application/json',
        'HTTP-Referer': 'https://hawkvance.ai',
        'X-Title': 'HawkVance AI',
      },
      body: JSON.stringify({
        model,
        messages: [{ role: 'user', content: 'Reply with exactly: OK' }],
        max_tokens: 16,
      }),
    });
    const body = await response.json().catch(() => null);
    if (response.ok && body?.choices?.length) {
      return `${model} answered (${body.usage?.prompt_tokens ?? '?'} in / ${body.usage?.completion_tokens ?? '?'} out)`;
    }
    errors.push(`${model}: ${body?.error?.code ?? response.status}`);
  }

  throw new Error(`every model tried was unavailable. ${errors.slice(0, 3).join('; ')}`);
});

await check('the free pool is flaky, which is why fallback exists', async () => {
  // Not a failure condition: this records how many of the first six are up right now, which is
  // the empirical justification for the gateway walking the catalogue instead of trusting one.
  let up = 0;
  for (const model of workingFreeModels.slice(0, 6)) {
    const response = await fetch('https://openrouter.ai/api/v1/chat/completions', {
      method: 'POST',
      headers: {
        authorization: `Bearer ${env.OPENROUTER_API_KEY}`,
        'content-type': 'application/json',
      },
      body: JSON.stringify({ model, messages: [{ role: 'user', content: 'hi' }], max_tokens: 4 }),
    });
    if (response.ok) {
      up += 1;
    }
  }
  expect(up > 0, 'none of the first six free models responded');
  return `${up} of 6 available right now`;
});

section('Local engine');

await check('engine responds over stdio and redacts', async () => {
  const { spawnSync } = await import('node:child_process');
  const python = path.join(root, 'apps/engine/.venv/Scripts/python.exe');

  const requests = [
    { id: 1, method: 'ping' },
    {
      id: 2,
      method: 'privacy.scanText',
      params: { text: 'Mail jane@acme.com, key sk-live-abcdefghijklmnop', mode: 'fast' },
    },
    { id: 3, method: 'privacy.verifyOutbound', params: { text: 'key sk-live-abcdefghijklmnopqr' } },
  ];

  const result = spawnSync(python, ['-m', 'hawkvance_engine'], {
    input: requests.map((request) => JSON.stringify(request)).join('\n') + '\n',
    cwd: path.join(root, 'apps/engine'),
    encoding: 'utf8',
    timeout: 300_000,
  });

  expect(result.status === 0 || result.stdout, `engine exited ${result.status}`);
  const replies = result.stdout
    .split('\n')
    .filter((line) => line.trim())
    .map((line) => JSON.parse(line));

  const scan = replies.find((reply) => reply.id === 2);
  expect(scan?.ok, 'scan failed');
  expect(!scan.result.sanitisedText.includes('jane@acme.com'), 'email leaked');
  expect(scan.result.routing.modelsLoaded.length === 0, 'FAST mode loaded a model');

  const verify = replies.find((reply) => reply.id === 3);
  expect(verify.result.mayTransmit === false, 'the gate allowed a credential through');

  return 'redacted, gate blocked a credential, zero models loaded';
});

await check('no original value crosses the engine boundary', async () => {
  const { spawnSync } = await import('node:child_process');
  const python = path.join(root, 'apps/engine/.venv/Scripts/python.exe');

  const result = spawnSync(python, ['-m', 'hawkvance_engine'], {
    input:
      JSON.stringify({
        id: 1,
        method: 'privacy.scanText',
        params: { text: 'John Doe at john@example.com', mode: 'fast' },
      }) + '\n',
    cwd: path.join(root, 'apps/engine'),
    encoding: 'utf8',
    timeout: 300_000,
  });

  expect(!result.stdout.includes('john@example.com'), 'the original value crossed the boundary');
  expect(result.stdout.includes('[EMAIL_001]'), 'no placeholder was produced');
  return 'placeholder only, mapping stayed inside';
});

// -------------------------------------------------------------------------- report

console.log(`\n${'='.repeat(60)}`);
console.log(`  ${passed} passed, ${failed} failed`);
if (failures.length > 0) {
  console.log('');
  for (const failure of failures) {
    console.log(`  - ${failure}`);
  }
}
console.log('='.repeat(60));

process.exit(failed === 0 ? 0 : 1);
