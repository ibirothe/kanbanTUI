"""Transport-independent receipts for replay-safe import operations."""

from dataclasses import dataclass
from hashlib import sha256

MAX_IMPORT_RECEIPTS = 128


def digest_idempotency_key(key: str) -> str:
    """Hash a validated client key so its clear text is never persisted."""
    return sha256(key.encode("ascii")).hexdigest()


def digest_import_request(mode: str, body: bytes) -> str:
    """Fingerprint the exact import mode and request body."""
    digest = sha256()
    digest.update(mode.encode("ascii"))
    digest.update(b"\0")
    digest.update(body)
    return digest.hexdigest()


@dataclass(frozen=True)
class ImportReceipt:
    """Durable application result associated with one hashed client key."""

    key_digest: str
    request_digest: str
    mode: str
    changed: bool
    id_mapping: tuple[tuple[int, int], ...] = ()

    def __post_init__(self) -> None:
        for name, value in (
            ("key digest", self.key_digest),
            ("request digest", self.request_digest),
        ):
            if len(value) != 64 or any(
                char not in "0123456789abcdef" for char in value
            ):
                raise ValueError(f"import receipt {name} must be a SHA-256 digest")
        if self.mode not in {"merge", "replace"}:
            raise ValueError("import receipt mode must be merge or replace")
        for source, destination in self.id_mapping:
            if source < 1 or destination < 1:
                raise ValueError("import receipt ID mappings must contain positive IDs")
