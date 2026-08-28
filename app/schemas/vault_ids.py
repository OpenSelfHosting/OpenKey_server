"""Client-facing vault identifiers shared by the app, extension, and CLI.

The server treats these as opaque strings. The only normalisation is mapping
the app/extension *root sentinels* to SQL NULL so entries/folders are not
filed under a phantom ``__root__`` collection.
"""

from typing import Any

# Matches openkey_app kVaultRootScope / openkey_extension normalizeFolderId.
_ROOT_SENTINELS = frozenset({"", "__root__", "null"})

# Personal-vault namespaces used by the app, extension, and CLI. Stored as
# ordinary collection rows (encrypted names); the server never decrypts them.
RESERVED_COLLECTION_UUIDS = (
    "__wallets__",
    "__crypto_wallets__",
    "__dev_secrets__",
)

# Custom folder icons are `custom:png:<base64>` (app CustomIcons.maxEncodedBytes).
MAX_COLLECTION_ICON_CHARS = 400_000


def normalize_folder_id(value: Any) -> str | None:
    """Null, blank, ``__root__``, and the string ``null`` mean vault root."""
    if value is None:
        return None
    trimmed = str(value).strip()
    if trimmed in _ROOT_SENTINELS:
        return None
    return trimmed
