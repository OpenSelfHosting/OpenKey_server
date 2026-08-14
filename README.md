# OpenKey Server

Zero-knowledge sync API for the [OpenKey](https://github.com/OpenSelfHosting) password manager.

The server stores **ciphertext only**. It never receives master passwords and never decrypts vault data. Authentication uses a client-derived `auth_hash` compared in constant time; vault contents, attachment blobs, org names, and share payloads stay encrypted end-to-end on the client.

## Stack

- FastAPI + Uvicorn
- SQLAlchemy 2 (async) + asyncpg
- Alembic migrations
- PostgreSQL 16
- JWT access tokens (PyJWT / HS256) + opaque refresh tokens
- pydantic-settings

## Quick start

```bash
cp .env.example .env
# Required: set a strong secret (min 32 chars, not a placeholder)
openssl rand -hex 32   # paste into JWT_SECRET in .env

docker compose up --build -d
```

API: http://localhost:8000  
Docs: http://localhost:8000/docs (overview) · http://localhost:8000/docs/reference (interactive)  
OpenAPI: http://localhost:8000/openapi.json  
Health: http://localhost:8000/health

Schema is applied via **Alembic** on API startup (`alembic upgrade head`). Existing databases that were bootstrapped with the old `create_all` path are stamped once automatically.

## Migrations

```bash
# Apply (also runs automatically when the API starts)
alembic upgrade head

# Autogenerate after model changes
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://openkey:openkey@db:5432/openkey` | Async SQLAlchemy URL |
| `JWT_SECRET` | *(required)* | Signing secret — **min 32 chars**; placeholders rejected at startup |
| `JWT_ALGORITHM` | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Access JWT TTL |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Opaque refresh token TTL (rotated on use) |
| `CORS_ORIGINS` | localhost:3000/8080 | Comma-separated origins — **no `*`** |
| `AUTH_RATE_LIMIT_REQUESTS` | `10` | Max auth requests per IP per window |
| `AUTH_RATE_LIMIT_WINDOW_SECONDS` | `60` | Auth rate-limit window |
| `TRUST_PROXY_HEADERS` | `false` | Use `X-Forwarded-For` for rate-limit IP (enable only behind a stripping reverse proxy) |

## API overview

### Auth

| Method | Path | Auth | Body |
|--------|------|------|------|
| `POST` | `/auth/register` | No† | `email`, `auth_hash`, `encrypted_vault_key`, `kdf_params`, `salt`, optional `public_key` |
| `POST` | `/auth/prelogin` | No† | `email` → `salt`, `kdf_params` |
| `POST` | `/auth/login` | No† | `email`, `auth_hash` |
| `POST` | `/auth/refresh` | No† | `refresh_token` → new token pair (rotation) |
| `POST` | `/auth/logout` | No | `refresh_token` → revoke |
| `POST` | `/auth/delete` | Yes | `auth_hash` → permanently deletes the account and server-side vault data |
| `GET` | `/auth/me` | Yes | — → `user_id`, `email`, `public_key`, `encrypted_private_key`, `salt`, `encrypted_vault_key`, `kdf_params` |
| `PATCH` | `/auth/me/keys` | Yes | `public_key`, `encrypted_private_key` |
| `POST` | `/auth/rekey` | Yes | `current_auth_hash`, `auth_hash`, `encrypted_vault_key`, optional `salt`, optional `kdf_params` |
| `POST` | `/auth/lookup-public-key` | Yes | `email` → `user_id`, `email`, `public_key` (for wrapping org/share keys) |

† Rate-limited per client IP (see `AUTH_RATE_LIMIT_*`).

Register / login / refresh return:

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "user_id": "...",
  "token_type": "bearer",
  "expires_in": 900
}
```

Refresh tokens are opaque (SHA-256 hashed at rest) and rotated on every `/auth/refresh`. Reuse of an already-rotated refresh token revokes **all** refresh tokens for that user (theft mitigation).

`POST /auth/prelogin` returns the account salt and KDF params so a new client (e.g. browser extension) can derive `auth_hash` before calling login — no one-time paste of vault metadata required. Salt/KDF params are not secrets; the master password and plaintext vault key never leave the client.

`GET /auth/me` returns opaque unlock bootstrap (`salt`, `encrypted_vault_key`, `kdf_params`) so clients can unwrap the vault key after login. The server still never sees the master password or plaintext vault key.

`POST /auth/rekey` rotates the stored `auth_hash` and wrapped vault key after the client changes its master password. Entries are not re-encrypted (the vault key itself stays the same). Existing refresh tokens are revoked so other devices must log in again.

`POST /auth/delete` permanently removes the account and cascaded ciphertext after the client re-proves possession of the current `auth_hash`. Local vaults on devices are unaffected.

Identity keys are opaque blobs stored for sharing/orgs; the server never decrypts them.

### Collections (Bearer JWT)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/collections` | List non-deleted collections (ciphertext) |
| `POST` | `/collections` | Create (`uuid`, `encrypted_name`, `icon`, `color`, `parent_uuid?`, `sort_order`, `revision`) |
| `PATCH` | `/collections/{uuid}` | Update ciphertext fields + `parent_uuid` + revision |
| `DELETE` | `/collections/{uuid}` | Soft delete |

Nested folders use `parent_uuid` (null = top-level), matching the OpenKey app.

### Entries (Bearer JWT)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/entries` | List non-deleted entries |
| `POST` | `/entries` | Create (`uuid`, `collection_uuid?`, `encrypted_payload`, `revision`) |
| `PATCH` | `/entries/{uuid}` | Update |
| `DELETE` | `/entries/{uuid}` | Soft delete |

### Attachments (Bearer JWT)

Ciphertext only. Max size **20 MB**. Dedicated upload uses **multipart/form-data**; download streams raw bytes.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/attachments` | List metadata for current user (no blob) |
| `POST` | `/attachments` | Multipart: form fields `uuid`, `entry_uuid`, `filename`, `size_bytes`, `revision?`, `content_type?` + file field `file` |
| `GET` | `/attachments/{uuid}` | Metadata only |
| `GET` | `/attachments/{uuid}/content` | Stream encrypted bytes (`application/octet-stream`) |
| `DELETE` | `/attachments/{uuid}` | Soft delete |

Batch `/sync` may still carry base64 blobs for offline catch-up; prefer the multipart endpoint for new uploads.

### Orgs & invites (Bearer JWT)

Org display names are stored as `encrypted_name` (zero-knowledge). Members receive a per-user `wrapped_org_key` ciphertext.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/orgs` | Create org (`uuid`, `encrypted_name`, `wrapped_org_key` for creator) |
| `GET` | `/orgs` | List orgs where current user is an active member |
| `POST` | `/orgs/{uuid}/invites` | Invite by email (`email`, `role`, `wrapped_org_key`) |
| `POST` | `/orgs/{uuid}/invites/{id}/revoke` | Revoke a pending invite (owner/admin) |
| `GET` | `/invites/pending` | Pending invites for current user's email |
| `POST` | `/invites/{id}/accept` | Accept invite (optional `wrapped_org_key` override) |
| `GET` | `/orgs/{uuid}/members` | List active members + pending invites (no key material) |
| `PATCH` | `/orgs/{uuid}/members/{id}` | Change role to `admin`/`member` (owner/admin) |
| `DELETE` | `/orgs/{uuid}/members/{id}` | Remove member or revoke invite (owner/admin) |
| `POST` | `/orgs/{uuid}/leave` | Leave org (owner cannot leave) |
| `GET` | `/orgs/{uuid}/collections` | List shared org collections |
| `POST` | `/orgs/{uuid}/collections` | Create shared collection (`uuid`, `encrypted_name`) |
| `PATCH` | `/orgs/{uuid}/collections/{uuid}` | Update shared collection |
| `DELETE` | `/orgs/{uuid}/collections/{uuid}` | Soft-delete shared collection (owner/admin) |
| `GET` | `/orgs/{uuid}/entries` | List shared org entries (ciphertext) |
| `POST` | `/orgs/{uuid}/entries` | Create shared entry (`uuid`, `collection_uuid?`, `encrypted_payload`) |
| `PATCH` | `/orgs/{uuid}/entries/{uuid}` | Update shared entry |
| `DELETE` | `/orgs/{uuid}/entries/{uuid}` | Soft-delete shared entry (any active member) |

### Shares (Bearer JWT)

Item keys and payloads are ciphertext. Status: `pending` → `accepted` / `revoked`.

**Snapshot semantics:** an entry share freezes `encrypted_payload` at create time. Accepting imports that snapshot into the recipient's own vault (new local uuid). Later edits to the owner's original entry are not pushed to recipients. Revoke stops a pending accept; it does not delete an already-imported copy.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/shares` | Create share (recipient + entry/collection uuid + `wrapped_item_key`; entry shares require `encrypted_payload` snapshot) |
| `GET` | `/shares` | List non-revoked shares involving current user |
| `POST` | `/shares/{uuid}/accept` | Accept a pending share addressed to you (imports snapshot) |
| `POST` | `/shares/{uuid}/revoke` | Owner revokes a pending or accepted share |

### Sync (Bearer JWT)

```http
POST /sync
```

```json
{
  "since_revision": 0,
  "collections": [
    {
      "uuid": "...",
      "encrypted_name": "...",
      "icon": "material:folder",
      "color": null,
      "parent_uuid": null,
      "sort_order": 0,
      "revision": 1,
      "is_deleted": false
    }
  ],
  "entries": [ /* … */ ],
  "attachments": [
    {
      "uuid": "...",
      "entry_uuid": "...",
      "filename": "secret.pdf.enc",
      "size_bytes": 1024,
      "content_type": "application/octet-stream",
      "revision": 1,
      "is_deleted": false,
      "encrypted_blob": "<base64>"
    }
  ]
}
```

Pushes local changes (last-write-wins by per-item `revision`) and returns collections/entries/attachments with `updated_at` newer than `since_revision`. The sync cursor (`since_revision` / `server_revision`) is unix microseconds of `updated_at` — pass `0` for a full pull. Nested folder hierarchy is preserved via collection `parent_uuid`. Org memberships and shares use their dedicated endpoints (not included in sync).

### Health

`GET /health` → `{ "status": "ok", "database": "ok" }` (HTTP 503 when Postgres is unreachable).

## Local development (without Docker for the API)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Start Postgres (compose db only)
docker compose up -d db

cp .env.example .env
# Set JWT_SECRET=$(openssl rand -hex 32) in .env
export $(grep -v '^#' .env | xargs)
alembic upgrade head   # optional; also runs on API startup
uvicorn app.main:app --reload --port 8000
```

## Tests

```bash
pip install -r requirements-dev.txt
# Postgres must be reachable (docker compose up -d db)
pytest
```

Unit tests cover settings, JWT helpers, rate limiting, and sync cursors. API tests exercise auth, collections/entries, and sync against PostgreSQL.

## Security model

1. Client derives `auth_hash` and vault keys from the master password (never sent).
2. Server stores `auth_hash`, `encrypted_vault_key`, `salt`, and `kdf_params` for login/unlock bootstrap.
3. Collection names, entry payloads, attachment blobs, org names, and share payloads are opaque ciphertext.
4. Identity `public_key` / `encrypted_private_key` and per-member `wrapped_org_key` / `wrapped_item_key` are stored as opaque blobs for client-side crypto only.
5. Soft deletes bump `revision` so peers learn about tombstones via sync.
6. The server **never decrypts** any vault, attachment, org, or share ciphertext.
7. Access JWTs are short-lived; refresh tokens are hashed at rest and rotated on use. Reuse of a rotated refresh token revokes all sessions for that user.
8. Auth endpoints are rate-limited; CORS is an explicit allow-list. `X-Forwarded-For` is ignored unless `TRUST_PROXY_HEADERS` is enabled.

## License

MIT — see [LICENSE](LICENSE).
