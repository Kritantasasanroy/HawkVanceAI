# Security

## The claim we actually make

> Raw documents and sensitive data are processed locally and are not transmitted to external LLMs.
> Only sanitised, user-approved context is sent to the selected AI model.

This is deliberately narrower than "no data ever leaves the device", because HawkVance's whole
purpose is to send *sanitised* context outward. The narrower claim is the one the architecture can
actually keep.

## The invariant that outranks the rest

The mapping from placeholder (`[PERSON_1]`) to original value is written only to the local encrypted
vault. It is never placed in an outbound request body, never written to any log, never included in
telemetry, never synced to the backend, and never reaches any LLM.

This is enforced structurally, not by discipline:

- `RedactionMap` exists only in the desktop process. It has no serialiser targeting the wire and no
  representation in `@hawkvance/contracts`. **The backend has no type that could receive it.**
- The type crossing the boundary is `SanitisedText`, constructible only as the output of applying a
  `RedactionMap`, holding no reference back to the map it came from.
- The `redaction_map_entries` table is the single reason the entire vault is encrypted rather than
  just its sensitive columns.

A code path that could carry the mapping off-device is treated as a CAPITAL-class defect.

## Authentication

Neo email OTP, everywhere, for every credential flow. No passwords exist in the product, so there is
no password hash to breach, no reset flow to abuse, and no reuse risk from another site.

| Control | Implementation |
|---|---|
| Code generation | `crypto.randomInt`, 6 digits, CSPRNG |
| Code at rest | Argon2id hash. Plaintext exists only in memory and the email body. |
| Code lifetime | 10 minutes, single use |
| Attempt cap | 5, then the challenge locks and the correct code stops working |
| Resend cooldown | 60 seconds, per address |
| Access token | JWT HS256, 15 minutes, carries accountId, sessionId, role only |
| Refresh token | 48 random bytes, returned once, only SHA-256 persisted, 30 days |
| Rotation | every refresh issues a new token in the same family |
| Theft detection | presenting an already-rotated token revokes the **entire family** |
| Enumeration | `/auth/otp/request` answers identically for known and unknown addresses |

Refresh-token reuse detection is the important one. A stolen refresh token is only useful until
either party uses it; the moment both do, the family dies and the real user is signed out rather
than silently shadowed.

### Verified by test

`apps/backend/src/http/auth-routes.test.ts` asserts each of these against a real database, not a
mock: the code never appears in a response body, the plaintext never reaches the database, five
failures lock the challenge, an expired challenge rejects a correct code, a consumed code cannot be
replayed, reuse revokes the family, and only a SHA-256 digest is stored.

## Local data security

| Asset | Protection |
|---|---|
| Vault values | AES-256-GCM, authenticated, fresh nonce per write |
| Vault key | 32 CSPRNG bytes in Windows Credential Manager, never on disk |
| Key in memory | zeroed on drop |
| Refresh token | vault `settings`, so encrypted under the same key |
| Provider keys (BYOK) | Windows Credential Manager, never a config file |

`apps/desktop/src-tauri/src/vault.rs` proves the encryption rather than asserting it: one test
writes a canary through the vault, then reads the raw file bytes and fails if the canary appears in
cleartext anywhere in it. Another fails if a different key can open an existing vault. `cipher.rs`
adds five more: a sealed value round-trips, leaks no trace of its plaintext, seals differently every
time (so a repeated value is not detectable), cannot be opened by a different key, and rejects a
tampered ciphertext instead of decrypting it to garbage.

**Scope of this protection, stated precisely.** Table and column *names* are visible in the vault
file; every *value* is sealed. That is weaker than SQLCipher's whole-file encryption, which was the
original design. SQLCipher requires building OpenSSL from source, which needs Strawberry Perl, whose
installer needs elevation this build could not obtain. The switch to `bundled-sqlcipher-vendored-openssl`
in `Cargo.toml` is a one-line change once Strawberry Perl is installed.

Destroying the key destroys the data. That is the intended meaning of "forget everything" for
encrypted-at-rest storage.

## Transport and API

- TLS in every deployed environment.
- Helmet security headers.
- CORS defaults to rejecting all browser origins, which is correct for a desktop-only client. The
  admin portal origin is added explicitly.
- 1 MB body limit.
- Rate limiting per IP, with per-address OTP cooldown layered on top so neither dimension alone can
  brute-force a 6-digit code.
- Every request body is validated by a zod schema at the boundary; nothing downstream re-validates.
- Role is checked server-side on every admin route. The client's copy of its own role is a display
  hint and is never trusted.

## Logging

Structured logs with an explicit redaction list: `authorization`, `cookie`, `body.code`,
`body.refreshToken`, `accessToken`, `refreshToken`. Silent in the test environment.

Never written to any log: OTP codes, refresh tokens, API keys, document content, extracted text,
redaction maps, chat content.

Log streams are separated: application, security, AI usage, privacy, error, admin audit.

## Admin privacy boundary

Administrators see operational metadata, not customer content. The admin portal has no route that
returns document bodies, extracted text, redaction maps or chat content, because the backend never
receives them in the first place.

Roles: `superAdmin`, `admin`, `support`, `analyst`, with support and analyst deliberately limited.
Every administrative change is written to an append-only audit table recording actor, subject,
action, previous value, next value, timestamp and IP.

Any future support-access feature must require explicit customer authorisation, be time-limited,
audited, and gated by role.

## Prompt injection

Uploaded content is data. System instructions, user instructions, document content and memory are
carried as separate labelled channels, and nothing arriving in the document or memory channel can
override system instructions, privacy controls, user permissions or tool permissions.

## Memory poisoning

Nothing the AI says becomes permanent memory automatically:

```
observation -> candidate -> confidence -> importance -> optional confirmation -> permanent
```

Every automatically created memory carries a confidence level and its source count, and remains
user-reviewable, editable and deletable.

## Secrets handling

All credentials come from environment variables. `.env.example` documents every variable and
contains no real value. No credential is committed, and no provider key is ever shipped inside the
desktop application: the desktop talks to the HawkVance gateway, and the gateway holds the keys
server-side.

## Known gaps at this stage

Stated plainly rather than left for someone to discover:

1. The redaction pipeline, context builder and gateway are designed and specified but not yet
   implemented, so the end-to-end privacy claim is not yet exercisable.
2. Admin routes and RBAC enforcement are modelled in the schema but not yet built.
3. TLS is a deployment concern and is not configured in this repository.
4. No independent security review has been performed on this code.
