# API reference

Base URL: `http://localhost:8080` in development. All bodies are JSON. All errors share one shape.

## Error shape

```json
{ "error": { "code": "otp_rejected", "message": "That code is not correct. Check the email and try again.", "retryAfterSeconds": 42 } }
```

`retryAfterSeconds` is present only on rate-limited responses. Messages are written for the person
reading them and name a way forward, not a dead end.

| Code | HTTP | Meaning |
|---|---|---|
| `invalid_request` | 400 | body failed schema validation |
| `invalid_email` | 400 | the address could not be parsed |
| `otp_rejected` | 401 | wrong, expired, already-used, or no pending code |
| `otp_locked` | 429 | attempt cap reached; request a new code |
| `resend_too_soon` | 429 | inside the resend cooldown |
| `refresh_rejected` | 401 | unknown, rotated, revoked or expired refresh token |
| `account_not_eligible` | 403 | suspended or deleted account |
| `invalid_access_token` | 401 | missing, malformed, expired or wrongly signed |
| `session_not_found` | 404 | that session is not on this account |
| `email_not_delivered` | 502 | SMTP refused the message |
| `internal_error` | 500 | unexpected |

---

## `POST /auth/otp/request`

Issues a sign-in code and emails it. **This is also the sign-up endpoint** — proving control of an
address is the whole of registration.

```json
{ "email": "you@company.com", "purpose": "signIn" }
```

`202 Accepted`

```json
{ "expiresInSeconds": 600, "resendAvailableInSeconds": 60 }
```

The response is identical whether or not the address has an account. Returning 404 for an unknown
address would turn this into an account-existence oracle.

The code never appears in the response body and is never stored in plaintext. Only its Argon2id hash
is persisted.

## `POST /auth/otp/verify`

Redeems the code, creating the account on first use, and opens a session for this device.

```json
{
  "email": "you@company.com",
  "code": "418207",
  "device": { "name": "DESKTOP-A1B2C3", "platform": "windows", "appVersion": "0.1.0" }
}
```

`200 OK`

```json
{
  "accessToken": "eyJhbGciOiJIUzI1NiJ9...",
  "refreshToken": "0mQ7...",
  "accessTokenExpiresInSeconds": 900,
  "account": {
    "id": "…", "email": "you@company.com", "displayName": "you",
    "status": "active", "role": "member", "plan": "beta",
    "createdAt": "…", "lastSeenAt": "…"
  }
}
```

The refresh token is returned exactly once. Only its SHA-256 is stored.

Five wrong attempts lock the challenge, after which even the correct code returns `429`.

## `POST /auth/refresh`

Rotates the refresh token.

```json
{ "refreshToken": "0mQ7..." }
```

`200 OK` → `{ "accessToken": "…", "refreshToken": "…", "accessTokenExpiresInSeconds": 900 }`

**Reuse detection.** Presenting a token that has already been rotated revokes the entire session
family, including the successor token. Both the thief and the legitimate holder are signed out,
which is the correct outcome: it converts silent account shadowing into a visible sign-out.

## `POST /auth/logout`

```json
{ "refreshToken": "0mQ7..." }
```

`204 No Content`. Revokes the whole family. Returns 204 even for an unknown token, so it is not an
oracle either.

## `GET /auth/me`

Requires `Authorization: Bearer <accessToken>`.

```json
{
  "account": { "…": "…" },
  "limits": {
    "dailyRequests": 100, "monthlyRequests": 1000, "monthlyTokens": 500000,
    "storageBytes": 2147483648, "maxWorkspaces": 10, "memoryRetentionDays": 180,
    "byokAllowed": true, "allowedModelTiers": ["economy", "standard"]
  }
}
```

## `GET /auth/sessions`

Requires a bearer token. Lists active sessions with their devices; the caller's own is flagged
`isCurrent`.

## `DELETE /auth/sessions/:id`

Requires a bearer token. Revokes that session's family. `404` if the session is not on the caller's
account, so it cannot be used to probe other accounts' session ids.

## `GET /health`

```json
{ "status": "ok", "database": true, "version": "0.1.0" }
```

---

## Tauri commands (desktop, local only)

Invoked from the renderer over Tauri IPC. None of these reach the network.

| Command | Returns | Notes |
|---|---|---|
| `vault_status` | `{ path, tables, encrypted }` | metadata only, never content |
| `hardware_profile` | CPU, cores, memory, OS, recommended mode | drives first-run setup |
| `vault_key_exists` | `boolean` | whether a master key is present |
| `session_save` | — | stores the refresh token inside the encrypted vault |
| `session_load` | `string \| null` | |
| `session_clear` | — | |

There is deliberately **no command that returns a redaction map**. The mapping from placeholder to
original value has no path out of the Rust process, which is what makes the privacy claim
structural rather than procedural.

---

## Not yet implemented

Designed and specified, but not built at this stage. Listed so nobody integrates against them
expecting a response:

`/documents/*`, `/workspaces/*`, `/memory/*`, `/chat/*`, `/gateway/*`, `/byok/*`, `/admin/*`.
