# Design — Authentication & Identity

Status: accepted
Scope: Phase 1 of the HawkVance MVP. Every credential flow in the product, desktop and admin
portal alike, is Neo email OTP. There are no passwords anywhere in the system.

## Why no passwords

A password is a secret the user must choose, remember, and reuse. Storing one means owning a hash,
a reset flow, a breach surface, and a strength policy. Email OTP moves proof-of-identity to a
channel the user already controls and that we already need for account recovery. Nothing is lost:
the mailbox was always the ultimate recovery factor, so a password only ever added a second,
weaker one in front of it.

## Durable-noun pass

The feature arrived phrased as a question: "can this person sign in?" That question is not a
concept. The nouns that exist whether or not sign-in ships:

| Noun | Survives feature cancellation? | Verdict |
|---|---|---|
| Account | yes, people exist independent of how they authenticate | concept |
| EmailAddress | yes, an address is a thing with its own rules | value type |
| OtpChallenge | yes, a challenge issued at a time to an address is a record | concept |
| Session | yes, an authenticated period is a real interval | concept |
| Device | yes, a machine exists independent of sessions | concept |
| Plan | yes, a commercial tier exists independent of login | concept |
| UsageRecord | yes, consumption happened whether or not we bill it | concept, append-only |
| AuthenticationResult | no, it is "did it work?" wearing a noun costume | rejected |
| OtpVerifier | no, verb plus suffix. The verb is a method on OtpChallenge | rejected (L26/L27) |
| TokenManager | no, suffix hiding Session's own behaviour | rejected (L26) |
| LoggedInUser | no, adjective bolted on a noun. "logged in" can become false | rejected (L26) |

## Concepts

### EmailAddress — value type, general

An RFC-5321 addr-spec that has been normalised to a single canonical form.

Immutable. Constructed only through a parse that either yields a valid address or fails; there is
no way to hold an unvalidated one. Normalisation lowercases the domain. Two addresses are equal
iff their canonical forms are equal. Carries `domain` so plan and enterprise rules can key on it
later without re-parsing.

This earns a type rather than being a plain string: it has an invariant, a normalisation rule, and
an equality that is not string equality. It survives L25's cut pass.

### Account — concept, ours

A person with a HawkVance identity.

| Field | Type | Mutable after create? |
|---|---|---|
| id | AccountId | no |
| email | EmailAddress | no, changing it is a separate audited transfer, not a field patch |
| status | AccountStatus | via named transitions only |
| plan | PlanTier | via `changePlan()` |
| displayName | string | yes |
| role | AccountRole | via named transition |
| createdAt | timestamp | no |
| lastSeenAt | timestamp | yes |

`AccountStatus` is `pending`, `active`, `suspended`, `deleted`. It is one enum, not three booleans,
because the states are mutually exclusive and `isActive` plus `isSuspended` would admit an illegal
combination (L8).

`AccountRole` is `member`, `support`, `analyst`, `admin`, `superAdmin`, satisfying the role list in
spec section 53. The admin portal gates on this, not on a separate admin table: one identity, one
role field.

Transitions are named, never generic patches (L25's CRUD pass): `activate()`, `suspend(reason)`,
`reactivate()`, `softDelete()`. Delete is a terminal status, not a row removal, because UsageRecord
and audit rows reference the account and spec section 49 requires the audit trail to survive.

### OtpChallenge — concept, ours

A time-boxed, attempt-limited proof that someone controls an email address.

| Field | Type | Notes |
|---|---|---|
| id | OtpChallengeId | |
| email | EmailAddress | who it was issued to |
| codeHash | string | Argon2id of the code. Plaintext exists only in memory and the email body. |
| purpose | OtpPurpose | `signIn`, `adminSignIn`, `emailChange` |
| expiresAt | timestamp | issuedAt plus 10 minutes |
| attemptsUsed | int | |
| maxAttempts | int | 5 |
| consumedAt | timestamp or absent | |
| requestIp | string | for the rate limiting in spec section 48 |
| createdAt | timestamp | |

State is **derived, never stored**: `pending` while unconsumed, unexpired and under the attempt
cap; `consumed` once consumedAt is set; `expired` past expiresAt; `locked` at the attempt cap.
Storing a status column alongside these fields would let the two disagree, so status is a computed
property on the entity.

Behaviour lives on the entity, which is why there is no `OtpVerifier` (L27): `verify(code)` returns
the outcome and mutates attemptsUsed; `isRedeemable` guards it; `consume()` is the terminal
transition.

The code is 6 digits from a cryptographically secure source, compared in constant time, and hashed
at rest so a database read cannot mint a login.

### Session — concept, ours

An authenticated period for one Account on one Device.

| Field | Type | Notes |
|---|---|---|
| id | SessionId | |
| accountId | AccountId | |
| deviceId | DeviceId | |
| familyId | SessionFamilyId | the rotation chain this token belongs to |
| refreshTokenHash | string | SHA-256; the raw token is returned once and never stored |
| issuedAt | timestamp | |
| expiresAt | timestamp | |
| rotatedAt | timestamp or absent | |
| revokedAt | timestamp or absent | |

`familyId` is what makes refresh-token reuse detectable. Rotation issues a new Session in the same
family and marks the old one rotated. If a token that is already rotated is presented again, the
only explanations are theft or replay, so the entire family is revoked. This is the standard OAuth
refresh-token-rotation defence, and it is why `familyId` is modelled rather than left implicit in a
parent pointer.

Access tokens are stateless JWTs, 15 minutes, carrying accountId, role and sessionId only. They are
deliberately not an entity: nothing is stored, so there is nothing to model.

### Device — concept, ours

A machine an account signs in from. `id`, `accountId`, `name`, `platform`, `appVersion`,
`firstSeenAt`, `lastSeenAt`. Exists so that "view device count" and "revoke sessions" in spec
section 42 have something real to act on.

### Plan and PlanLimits — concept, ours

`PlanTier` is `free`, `beta`, `pro`, `enterprise` (spec section 52).

`PlanLimits` is a value object holding the caps that travel together: `dailyRequests`,
`monthlyRequests`, `monthlyTokens`, `storageBytes`, `maxWorkspaces`, `byokAllowed`,
`allowedModelTiers`, `memoryRetentionDays`. These are one concept because they are always read
together, always change together, and a limit is meaningless without knowing which tier owns it
(L8: fields that always travel together are a concept).

Counts are typed, not bare ints (L8: an int whose unit you must remember is a value type):
`TokenCount` and `RequestCount` are distinct so a token budget can never be passed where a request
budget is expected.

### UsageRecord — concept, ours, append-only

One row per external inference: `accountId`, `workspaceId`, `occurredAt`, `provider`, `model`,
`inputTokens`, `outputTokens`, `estimatedCostMicros`, `latencyMs`, `outcome`.

Create-and-read only. No update, no delete, and no setter is ever added. Quota consumption is
**derived** by summing over a window rather than kept as a mutable running total, because a mutated
counter loses its own audit trail and races under concurrency (L8). Spec section 27 needs the
per-model, per-provider breakdown anyway, which a single counter could not answer.

Cost is stored in integer micros, never a float. Money in a float is a defect waiting for a
rounding complaint.

## Transaction units

Four units, each with one entity as the way in, referenced across boundaries by id and never by
held object:

1. **Account**, with Device, since a device is meaningless without its account.
2. **OtpChallenge**, standalone. It deliberately does not hold an Account, because a challenge is
   issued to an *address*, which may not have an account yet. That is what makes sign-up and
   sign-in the same flow.
3. **Session**
4. **UsageRecord**

The invariant forcing unit 1: an Account and its Devices must never be observable in a state where
a device points at an account that does not exist.

## API resources

```
POST   /auth/otp/request     { email, purpose }        -> 202 always, regardless of account existence
POST   /auth/otp/verify      { email, code, device }   -> 200 { accessToken, refreshToken, account }
POST   /auth/refresh         { refreshToken }          -> 200 { accessToken, refreshToken }
POST   /auth/logout          { refreshToken }          -> 204
GET    /auth/me                                        -> 200 { account, plan, limits }
GET    /auth/sessions                                  -> 200 [ session ]
DELETE /auth/sessions/:id                              -> 204
```

`/auth/otp/request` returns 202 whether or not the address has an account. Returning 404 for an
unknown address turns the endpoint into an account-existence oracle, which is an enumeration
vulnerability, so the response is identical either way and the difference is only in what gets
emailed.

Sign-up and sign-in are the same endpoint. Proving control of an address is the whole of
registration; there is nothing else to collect at that moment.

## Rules that must always hold

1. A plaintext OTP code exists in exactly two places: process memory during issuance, and the email
   body. Never in the database, never in a log, never in a response body.
2. A refresh token is returned exactly once. Only its SHA-256 is persisted.
3. Presenting an already-rotated refresh token revokes its entire family.
4. `/auth/otp/request` is indistinguishable between known and unknown addresses.
5. A suspended or deleted account cannot mint a session, and its existing sessions are revoked at
   the moment of suspension.
6. Role is checked server-side on every admin route. The desktop client's copy of the role is a
   display hint and is never trusted.
7. Rate limits apply per IP and per address independently, so neither alone can brute-force a
   6-digit code.
