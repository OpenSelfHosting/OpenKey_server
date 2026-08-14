"""OpenAPI metadata and Scalar theming for the docs portal."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

API_VERSION = "0.5.1"

OPENAPI_TAGS: list[dict[str, str]] = [
    {
        "name": "auth",
        "description": (
            "Account lifecycle and session tokens. Clients derive `auth_hash` from the "
            "master password locally; the server stores and compares it in constant time. "
            "Access JWTs are short-lived; refresh tokens rotate on every use."
        ),
    },
    {
        "name": "collections",
        "description": (
            "Encrypted folder hierarchy for a personal vault. Names and metadata are "
            "opaque ciphertext; nested folders use `parent_uuid`."
        ),
    },
    {
        "name": "entries",
        "description": "Encrypted vault items (logins, cards, notes, secrets) stored as opaque payloads.",
    },
    {
        "name": "attachments",
        "description": (
            "Encrypted file blobs (max 20 MB). Prefer multipart upload; sync may carry "
            "base64 for offline catch-up."
        ),
    },
    {
        "name": "orgs",
        "description": (
            "Shared organizations with per-member wrapped org keys. Org display names "
            "and shared vault data remain ciphertext."
        ),
    },
    {
        "name": "shares",
        "description": (
            "Direct item or collection shares between users on the same server. Entry "
            "shares snapshot ciphertext at create time."
        ),
    },
    {
        "name": "sync",
        "description": (
            "Batch push/pull with last-write-wins by per-item `revision`. The cursor "
            "(`since_revision`) is unix microseconds of `updated_at`."
        ),
    },
    {
        "name": "health",
        "description": "Liveness and database readiness probe for operators and load balancers.",
    },
]

API_DESCRIPTION = """
## Zero-knowledge sync

OpenKey Server is the optional sync backend for [OpenKey](https://github.com/OpenSelfHosting).
It stores **ciphertext only** — master passwords and plaintext vault keys never leave the client.

### Typical client flow

1. **`POST /auth/prelogin`** — fetch salt and KDF parameters for the account email.
2. Client derives `auth_hash` and vault keys locally from the master password.
3. **`POST /auth/login`** or **`POST /auth/register`** — receive access + refresh tokens.
4. Send `Authorization: Bearer <access_token>` on vault, org, share, and sync routes.
5. **`POST /auth/refresh`** — rotate refresh tokens before the access JWT expires.

### What the server never sees

- Master passwords
- Plaintext vault keys
- Decrypted collection names, entry payloads, attachments, org names, or share data

### Operator notes

- Terminate **HTTPS** in production and set a strong `JWT_SECRET` (≥ 32 chars).
- Restrict `CORS_ORIGINS` to your clients — wildcards are rejected.
- Auth endpoints are rate-limited per client IP (`AUTH_RATE_LIMIT_*`).
"""

_PUBLIC_AUTH_PATHS = frozenset(
    {
        "/auth/register",
        "/auth/prelogin",
        "/auth/login",
        "/auth/refresh",
        "/auth/logout",
    }
)

_PUBLIC_PATHS = frozenset({"/health"})


def build_openapi_schema(app: FastAPI) -> dict[str, Any]:
    """Return an enriched OpenAPI document with security schemes and tag docs."""
    if app.openapi_schema is not None:
        return app.openapi_schema

    schema = get_openapi(
        title="OpenKey Sync API",
        version=API_VERSION,
        description=API_DESCRIPTION,
        routes=app.routes,
        tags=OPENAPI_TAGS,
        contact={
            "name": "OpenSelfHosting",
            "url": "https://github.com/OpenSelfHosting",
        },
        license_info={
            "name": "MIT",
            "url": "https://opensource.org/licenses/MIT",
        },
    )

    components = schema.setdefault("components", {})
    security_schemes = components.setdefault("securitySchemes", {})
    security_schemes["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": (
            "Short-lived access token from `/auth/login`, `/auth/register`, or "
            "`/auth/refresh`. Prefix requests with `Authorization: Bearer <token>`."
        ),
    }

    for path, path_item in schema.get("paths", {}).items():
        if path.startswith("/docs") or path == "/openapi.json":
            continue
        if path in _PUBLIC_PATHS or path in _PUBLIC_AUTH_PATHS:
            continue
        for method, operation in path_item.items():
            if not isinstance(operation, dict):
                continue
            operation.setdefault("security", [{"BearerAuth": []}])

    app.openapi_schema = schema
    return schema


OPENKEY_SCALAR_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@600;700&family=IBM+Plex+Mono:wght@400;500&family=Source+Sans+3:wght@400;500;600;700&display=swap');

:root {
  --scalar-font: 'Source Sans 3', system-ui, sans-serif;
  --scalar-font-code: 'IBM Plex Mono', ui-monospace, monospace;
}

.light-mode {
  --scalar-color-1: #10241c;
  --scalar-color-2: #4a6358;
  --scalar-color-3: rgba(74, 99, 88, 0.72);
  --scalar-color-accent: #0f5c4c;
  --scalar-background-1: #f3f6f4;
  --scalar-background-2: #e6ece8;
  --scalar-background-3: #dfe8e3;
  --scalar-background-accent: rgba(15, 92, 76, 0.08);
  --scalar-border-color: rgba(16, 36, 28, 0.1);
}

.dark-mode {
  --scalar-color-1: #cfd8d3;
  --scalar-color-2: #8b9a92;
  --scalar-color-3: rgba(139, 154, 146, 0.72);
  --scalar-color-accent: #4a9e8a;
  --scalar-background-1: #121816;
  --scalar-background-2: #1a211e;
  --scalar-background-3: #1c2420;
  --scalar-background-accent: rgba(74, 158, 138, 0.12);
  --scalar-border-color: rgba(190, 205, 196, 0.12);
}

.light-mode .sidebar,
.dark-mode .sidebar {
  --scalar-sidebar-background-1: var(--scalar-background-1);
  --scalar-sidebar-item-hover-background: var(--scalar-background-2);
  --scalar-sidebar-item-active-background: var(--scalar-background-2);
  --scalar-sidebar-border-color: var(--scalar-border-color);
  --scalar-sidebar-color-1: var(--scalar-color-1);
  --scalar-sidebar-color-2: var(--scalar-color-2);
  --scalar-sidebar-search-background: var(--scalar-background-2);
  --scalar-sidebar-search-border-color: var(--scalar-border-color);
}
"""
