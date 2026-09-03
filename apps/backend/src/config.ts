import { z } from 'zod';

const environmentSchema = z.object({
  NODE_ENV: z.enum(['development', 'staging', 'production', 'test']).default('development'),
  PORT: z.coerce.number().int().positive().default(8080),
  HOST: z.string().default('0.0.0.0'),

  DATABASE_URL: z.string().url(),

  ENCRYPTION_KEY: z.string().min(32, 'ENCRYPTION_KEY must be at least 32 characters of entropy.'),

  /// Neon Auth owns authentication. HawkVance verifies its tokens and issues none of its own.
  NEON_AUTH_URL: z.string().url(),
  NEON_JWKS_URL: z.string().url(),

  /// Absent is valid: a HawkVance server with no provider credential still serves auth, memory
  /// and quotas, and every user brings their own key. It is not an error, it is a deployment mode.
  OPENROUTER_API_KEY: z.string().default(''),

  CORS_ALLOWED_ORIGINS: z
    .string()
    .default('')
    .transform((value) =>
      value
        .split(',')
        .map((origin) => origin.trim())
        .filter((origin) => origin.length > 0),
    ),
});

export type Environment = z.infer<typeof environmentSchema>;

export class MisconfiguredEnvironment extends Error {
  readonly issues: ReadonlyArray<string>;

  constructor(issues: ReadonlyArray<string>) {
    super(`HawkVance cannot start. Fix these environment variables:\n  - ${issues.join('\n  - ')}`);
    this.name = 'MisconfiguredEnvironment';
    this.issues = issues;
  }
}

export class Configuration {
  readonly environment: Environment;

  private constructor(environment: Environment) {
    this.environment = environment;
    Object.freeze(this);
  }

  static fromProcessEnv(source: NodeJS.ProcessEnv = process.env): Configuration {
    const parsed = environmentSchema.safeParse(source);
    if (!parsed.success) {
      throw new MisconfiguredEnvironment(
        parsed.error.issues.map((issue) => `${issue.path.join('.')}: ${issue.message}`),
      );
    }
    return new Configuration(parsed.data);
  }

  get isProduction(): boolean {
    return this.environment.NODE_ENV === 'production';
  }

  get hasManagedInference(): boolean {
    return this.environment.OPENROUTER_API_KEY.length > 0;
  }

  /// Neon Auth signs its tokens with the *origin* as issuer, not the auth base URL.
  ///
  /// Verified against a real token: the auth endpoint lives at `<origin>/neondb/auth`, but the
  /// `iss` claim is just `<origin>`. Deriving this from the path instead rejected every genuine
  /// token with "unexpected iss claim value" while the signature itself checked out perfectly.
  get identityIssuer(): string {
    return new URL(this.environment.NEON_AUTH_URL).origin;
  }
}
