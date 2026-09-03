import { createRemoteJWKSet, jwtVerify, type JWTVerifyGetKey } from 'jose';
import { z } from 'zod';

/// Better Auth's JWT plugin puts the user on the token. `sub` is the Neon user id; the rest is a
/// convenience so a first sign-in can provision an account without a second round trip.
const claimsSchema = z.object({
  sub: z.string().min(1),
  email: z.string().email(),
  name: z.string().optional(),
  emailVerified: z.boolean().optional(),
});

export class IdentityTokenRejected extends Error {
  readonly reason: string;

  constructor(reason: string) {
    super('Your sign-in has expired or is not valid. Sign in again.');
    this.name = 'IdentityTokenRejected';
    this.reason = reason;
  }
}

/// A verified Neon Auth identity token. Constructing one is the only way to obtain it, so holding
/// an instance is itself proof that the signature, issuer and expiry checked out.
export class NeonIdentityToken {
  readonly neonUserId: string;
  readonly email: string;
  readonly displayName: string;

  private constructor(neonUserId: string, email: string, displayName: string) {
    this.neonUserId = neonUserId;
    this.email = email;
    this.displayName = displayName;
    Object.freeze(this);
  }

  static fromClaims(claims: z.infer<typeof claimsSchema>): NeonIdentityToken {
    const fallbackName = claims.email.slice(0, claims.email.lastIndexOf('@'));
    return new NeonIdentityToken(
      claims.sub,
      claims.email.toLowerCase(),
      claims.name !== undefined && claims.name.length > 0 ? claims.name : fallbackName,
    );
  }

  static claimsSchema = claimsSchema;
}

/// Verifies bearer tokens against Neon Auth's published keys. The key set is fetched once and
/// cached by `jose`, with rotation handled by refetching on an unknown `kid`.
///
/// The key resolver is injectable so tests can sign with a local key pair instead of reaching the
/// network, which is what keeps the auth tests fast and offline.
export class NeonIdentityVerifier {
  private readonly keys: JWTVerifyGetKey;
  private readonly issuer: string;

  constructor(keys: JWTVerifyGetKey, issuer: string) {
    this.keys = keys;
    this.issuer = issuer;
  }

  static forJwksUrl(jwksUrl: string, issuer: string): NeonIdentityVerifier {
    return new NeonIdentityVerifier(createRemoteJWKSet(new URL(jwksUrl)), issuer);
  }

  async verify(rawToken: string): Promise<NeonIdentityToken> {
    if (rawToken.length === 0) {
      throw new IdentityTokenRejected('no bearer token was presented');
    }

    const verified = await jwtVerify(rawToken, this.keys, { issuer: this.issuer }).catch(
      (cause: unknown) => {
        throw new IdentityTokenRejected(
          cause instanceof Error ? cause.message : 'signature verification failed',
        );
      },
    );

    const claims = claimsSchema.safeParse(verified.payload);
    if (!claims.success) {
      throw new IdentityTokenRejected('the token payload did not carry a subject and email');
    }

    return NeonIdentityToken.fromClaims(claims.data);
  }
}

/// Reads the bearer token out of an Authorization header without trusting its shape.
export class BearerHeader {
  static tokenFrom(header: string | undefined): string {
    if (header === undefined) {
      return '';
    }
    const prefix = 'Bearer ';
    return header.startsWith(prefix) ? header.slice(prefix.length).trim() : '';
  }
}
