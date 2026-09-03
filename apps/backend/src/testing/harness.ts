import { migrate } from 'drizzle-orm/postgres-js/migrator';
import { sql } from 'drizzle-orm';
import { SignJWT, exportJWK, generateKeyPair, type JWTVerifyGetKey, type KeyLike } from 'jose';
import { createLocalJWKSet } from 'jose';
import { Configuration } from '../config.js';
import { Database } from '../db/client.js';
import { planLimits } from '../db/schema.js';
import { NeonIdentityVerifier } from '../identity/neon-identity-token.js';
import { HawkVanceServer } from '../server.js';

/// The auth endpoint sits under a path, but tokens are issued by the bare origin. Mirroring that
/// split matters: tests that signed with the full base URL passed while every real token was
/// rejected, which is precisely how the issuer bug reached a user.
export const authBaseUrl = 'https://neon-auth.test/neondb/auth';
export const issuer = new URL(authBaseUrl).origin;

/// Signs identity tokens with a locally generated Ed25519 key pair, the same algorithm Neon Auth
/// uses, and hands the server a matching local key set. This exercises the real verification path
/// without reaching the network, so the auth tests stay fast, offline and deterministic.
export class TestIdentityProvider {
  private readonly privateKey: KeyLike;
  readonly keys: JWTVerifyGetKey;

  private constructor(privateKey: KeyLike, keys: JWTVerifyGetKey) {
    this.privateKey = privateKey;
    this.keys = keys;
  }

  static async create(): Promise<TestIdentityProvider> {
    const { privateKey, publicKey } = await generateKeyPair('EdDSA', {
      crv: 'Ed25519',
      extractable: true,
    });
    const jwk = await exportJWK(publicKey);
    jwk.kid = 'test-key';
    jwk.alg = 'EdDSA';
    return new TestIdentityProvider(privateKey, createLocalJWKSet({ keys: [jwk] }));
  }

  async tokenFor(claims: {
    sub: string;
    email: string;
    name?: string;
    expiresIn?: string;
    withIssuer?: string;
  }): Promise<string> {
    const jwt = new SignJWT({
      email: claims.email,
      ...(claims.name === undefined ? {} : { name: claims.name }),
      emailVerified: true,
    })
      .setProtectedHeader({ alg: 'EdDSA', kid: 'test-key' })
      .setSubject(claims.sub)
      .setIssuer(claims.withIssuer ?? issuer)
      .setIssuedAt()
      .setExpirationTime(claims.expiresIn ?? '15m');

    return jwt.sign(this.privateKey);
  }

  /// A token signed by a key the server does not trust, for the forgery tests.
  static async foreignToken(sub: string, email: string): Promise<string> {
    const { privateKey } = await generateKeyPair('EdDSA', { crv: 'Ed25519', extractable: true });
    return new SignJWT({ email, emailVerified: true })
      .setProtectedHeader({ alg: 'EdDSA', kid: 'test-key' })
      .setSubject(sub)
      .setIssuer(issuer)
      .setIssuedAt()
      .setExpirationTime('15m')
      .sign(privateKey);
  }
}

export class TestHarness {
  readonly server: HawkVanceServer;
  readonly database: Database;
  readonly identity: TestIdentityProvider;

  private constructor(server: HawkVanceServer, database: Database, identity: TestIdentityProvider) {
    this.server = server;
    this.database = database;
    this.identity = identity;
  }

  static async start(overrides: Record<string, string> = {}): Promise<TestHarness> {
    const configuration = Configuration.fromProcessEnv({
      NODE_ENV: 'test',
      DATABASE_URL:
        process.env.TEST_DATABASE_URL ??
        'postgresql://hawkvance:hawkvance_local_dev@localhost:5433/hawkvance_test',
      ENCRYPTION_KEY: 'test-encryption-key-that-is-long-enough-ok',
      NEON_AUTH_URL: authBaseUrl,
      NEON_JWKS_URL: `${authBaseUrl}/.well-known/jwks.json`,
      ...overrides,
    });

    const database = Database.connect(configuration.environment.DATABASE_URL, 4);
    await migrate(database.drizzle, { migrationsFolder: 'drizzle' });
    await database.drizzle
      .insert(planLimits)
      .values({
        tier: 'beta',
        dailyRequests: 100,
        monthlyRequests: 1000,
        monthlyTokens: 500_000,
        monthlyCredits: 500,
        storageBytes: 2_147_483_648,
        maxWorkspaces: 10,
        memoryRetentionDays: 180,
        byokAllowed: true,
        allowedModelTiers: ['economy', 'standard', 'premium'],
      })
      .onConflictDoNothing();

    const identity = await TestIdentityProvider.create();
    const server = await HawkVanceServer.assemble(
      configuration,
      database,
      new NeonIdentityVerifier(identity.keys, configuration.identityIssuer),
    );
    await server.fastify.ready();
    return new TestHarness(server, database, identity);
  }

  async reset(): Promise<void> {
    await this.database.drizzle.execute(
      sql`truncate table hawkvance.devices, hawkvance.usage_records, hawkvance.activity_events, hawkvance.admin_audit_entries, hawkvance.accounts restart identity cascade`,
    );
  }

  async stop(): Promise<void> {
    await this.server.shutdown();
  }
}
