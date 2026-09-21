# Authentication and authorization

## Model

| Credential | Lifetime | Where it lives | Notes |
|---|---|---|---|
| **Access token** (JWT, HS256) | 15 min (`JWT_ACCESS_EXPIRE`) | JavaScript memory only | `Authorization: Bearer`. Claims: `sub`, `sid` (session), `jti`, `iat`, `exp`, `iss`, `aud`, `type`. **No role, no email.** |
| **Refresh token** (opaque, 256-bit) | 7 days (`JWT_REFRESH_EXPIRE`) | `httpOnly` cookie `sahucodex_refresh`, `Path=/api/auth`, `SameSite=Lax`, `Secure` in production | Only its SHA-256 is stored. Rotates on every use. |
| **Session hint** | same as refresh | readable cookie `sahucodex_session=1` | Not a credential. Lets the Next.js proxy redirect without a round trip. The API never trusts it. |

Because the refresh cookie is scoped to `/api/auth`, the browser sends it *only* to the auth endpoints — not to page
requests and not to any other API route.

## Flows

**Register** → `POST /api/auth/register` creates the user, profile and `USER` role and emails a verification link. It does
not sign the user in; the web app follows with a login using the same credentials.

**Login** → `POST /api/auth/login` (email *or* username). Per-IP and per-account rate limits apply first. Unknown
accounts and wrong passwords return the *same* response and burn the same Argon2 time, so neither the body nor timing
reveals which accounts exist. Success returns the access token in the body and sets the cookies.

**Refresh** → `POST /api/auth/refresh` reads the cookie, rotates it, returns a new access token.

```
token presented ─┬─ unknown ───────────────────────────────────► 401 REFRESH_TOKEN_INVALID
                 ├─ expired ───────────────────────────────────► 401 REFRESH_TOKEN_EXPIRED
                 ├─ revoked (logout / reset / admin) ──────────► 401 REFRESH_TOKEN_INVALID
                 ├─ already rotated
                 │     ├─ < 10 s ago (two tabs raced) ─────────► 401 REFRESH_TOKEN_RACE   (nothing revoked; client retries)
                 │     └─ later (a copy was kept) ─────────────► 401 REFRESH_TOKEN_REUSED (whole session revoked + audited)
                 └─ valid ─────────────────────────────────────► rotate: revoke old (ROTATED), issue new in same family
```

Every definitive failure also clears both cookies so the browser stops believing it is signed in (otherwise `/login` and
`/dashboard` could redirect to each other). `REFRESH_TOKEN_RACE` deliberately does not, because the other tab's response
has just delivered the good cookie.

**Logout** → `POST /api/auth/logout` revokes the whole session family and adds it to a Redis **denylist** for the
lifetime of an access token, so the access token stops working *immediately* rather than at expiry. Idempotent.

**Sessions** → `GET /api/auth/sessions` lists active devices (IP, user agent, last active, "current"); `DELETE
/api/auth/sessions/{id}` signs one out, with the same immediate effect. A user can only see and revoke their own.

**Email verification** → link `/verify-email?token=…`, single use, 24 h. Request another with
`POST /api/auth/verify-email/request`. Verification is recorded and shown but not yet *required*; enforcing it for
specific actions (e.g. posting) is a per-feature decision for later phases.

**Password reset** → `POST /api/auth/password/forgot` always answers `202` with the same body, whether or not the email
exists, and is rate-limited per IP and per address. The emailed link is single use, 1 h, and a newer link invalidates
older ones. A successful reset revokes **every** session of the user.

## Passwords

Argon2id (`argon2-cffi`; defaults t=3, m=64 MiB, p=4, overridable). Hashes are upgraded transparently on login when
parameters change. Minimum 10 characters, maximum 128 (bounds the hashing work one request can force); no composition
rules, following NIST guidance.

## Authorization (RBAC)

Roles: `USER < MODERATOR < ADMIN`; a higher role includes everything below it. Enforced **on the server, per request,
against the database**:

```python
router = APIRouter(prefix="/admin", dependencies=[Depends(require_role(RoleName.ADMIN))])
```

Consequences worth knowing:

* Demoting a user or disabling an account takes effect on their very next request — there is no role in the token to go
  stale.
* Self-service endpoints use `extra="forbid"` schemas, so `PATCH /api/users/me` with `{"roles": ["ADMIN"]}` is a `422`,
  not silently ignored. Registration ignores any client-supplied role.
* Frontend route guards and the disabled "Admin" menu are UX only; removing them reveals nothing.

## CSRF

The only endpoints that authenticate via cookie are `refresh` and `logout`. They reject any request whose `Origin`
header is not in `CORS_ORIGINS`/`FRONTEND_URL` (browsers always send `Origin` on cross-site POSTs), on top of
`SameSite=Lax`. Every other endpoint needs the bearer token, which a cross-site request cannot attach.

## Rate limits (defaults, all configurable)

| Scope | Default |
|---|---|
| Login, per IP | 5/minute |
| Login, per targeted account (all IPs) | 10/hour |
| Registration, per IP | 5/minute |
| Password reset, per IP and per email | 5/hour |
| Every `/api` route, per IP | 300/minute |
| `POST /api/submissions`, per user | 10/minute |
| `POST /api/run`, per user | 20/minute |

The account limit prevents distributed guessing but also lets an attacker lock a *known* account for up to an hour by
failing on purpose; a successful login clears the counter. This is a deliberate, documented trade-off.

## Threat notes

| Threat | Mitigation |
|---|---|
| Stolen refresh token replayed later | Rotation + reuse detection revokes the session and writes an audit entry. |
| XSS reads credentials | No token in web storage; refresh cookie is `httpOnly`; strict nonce-based CSP. |
| Cross-site request forgery | Origin check + `SameSite=Lax`; bearer token elsewhere. |
| Account enumeration | Uniform login errors and timing; uniform forgot-password response. (Registration reports a taken email/username — an accepted UX trade-off, rate-limited.) |
| Credential stuffing / brute force | Per-IP and per-account limits, Argon2id. |
| Forged JWT (`alg: none`, wrong secret, wrong audience/type) | Algorithm pinned; `iss`, `aud`, `type` and required claims verified. Tested. |
| Session survives logout | Redis denylist keyed by session id, checked on every request (fails closed if Redis is down). |
| Stale privileges | Roles read from the database, never from the token. |
