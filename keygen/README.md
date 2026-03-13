# Keygen Service (Stage 5)

Service issues one-time invite tokens, redeems them into Matrix accounts,
and protects admin operations with `RBAC + master key`.

## Endpoints
- `GET /healthz` - healthcheck.
- `GET /auth/me` - validate Matrix access token and return role.
- `POST /token/create` - create invite token (requires role and master key header).
- `POST /token/redeem` - redeem invite token and return `access_token`.
- `GET /admin/master-key` - show active master key metadata.
- `POST /admin/master-key/rotate` - rotate active master key.
- `GET /admin/audit/events` - list audit events for admin actions.

## Environment variables
- `KEYGEN_DATABASE_URL`
- `KEYGEN_MASTER_KEY` (bootstrap master key)
- `KEYGEN_TOKEN_HASH_SECRET` (secret for invite token hashing; separate from master key)
- `KEYGEN_MASTER_KEY_HEADER` (default `X-Master-Key`)
- `KEYGEN_EXPOSE_DOCS` (default `false`; controls `/docs`, `/redoc`, `/openapi.json`)
- `KEYGEN_SYNAPSE_ADMIN_BASE_URL`
- `KEYGEN_SYNAPSE_REGISTRATION_SHARED_SECRET`
- `KEYGEN_DEFAULT_TTL_SECONDS` (default invite token lifetime in seconds; default `900`)
- `KEYGEN_TOKEN_TTL_SECONDS` (effective invite token lifetime in seconds; default = `KEYGEN_DEFAULT_TTL_SECONDS`)
- `KEYGEN_CREATE_MIN_RESPONSE_SECONDS` (minimum response time for `POST /token/create`, default `3`)
- `KEYGEN_MAX_TTL_SECONDS` (upper bound for optional `ttl_seconds` in `POST /token/create`)
- `KEYGEN_USER_PREFIX`
- `KEYGEN_QR_PAYLOAD_PREFIX`
- `KEYGEN_MATRIX_SERVER_NAME`
- `KEYGEN_DEFAULT_ADMIN_USER_ID`
- `KEYGEN_ROLE_SUPER_ADMINS` (comma-separated Matrix user IDs)
- `KEYGEN_ROLE_ADMINS` (comma-separated Matrix user IDs)
- `KEYGEN_ROLE_DEVELOPERS` (comma-separated Matrix user IDs)

## Role model
- `super-admin`
- `admin`
- `developer`
- `user`

Permissions:
- Invite creation: `admin`, `super-admin`, `developer`.
- Master key rotation: `super-admin`, `developer`.
- `developer` is treated as maximum-privilege business role.

## Required admin headers

For protected admin operations send both:
- `Authorization: Bearer <MATRIX_ACCESS_TOKEN>`
- `X-Master-Key: <MASTER_KEY_VALUE>`

## Example: create token

```bash
curl -X POST http://localhost:8080/token/create \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <MATRIX_ACCESS_TOKEN>" \
  -H "X-Master-Key: <MASTER_KEY_VALUE>" \
  -d '{}'
```

## Example: rotate master key

```bash
curl -X POST http://localhost:8080/admin/master-key/rotate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <MATRIX_ACCESS_TOKEN>" \
  -H "X-Master-Key: <CURRENT_MASTER_KEY>" \
  -d '{"reason":"scheduled_rotation"}'
```
