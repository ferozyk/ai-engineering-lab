"""Authentication primitives: principals and an in-memory session store."""

import hashlib
import hmac
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from mcp_vs_code_mode.banking.errors import AuthenticationError


@dataclass(frozen=True)
class Principal:
    """An authenticated caller and the customers it may access."""

    principal_id: str
    allowed_customer_ids: frozenset[str]


@dataclass
class SessionStore:
    """Maps opaque session tokens to principals. Tokens are never logged."""

    _sessions: dict[str, Principal] = field(default_factory=dict, repr=False)

    def issue(self, principal: Principal) -> str:
        """Issue a new opaque token for ``principal``."""
        token = secrets.token_urlsafe(32)
        self._sessions[token] = principal
        return token

    def authenticate(self, token: str) -> Principal:
        """Resolve a token to its principal using constant-time comparison."""
        match: Principal | None = None
        for stored, principal in self._sessions.items():
            if hmac.compare_digest(stored.encode("utf-8"), token.encode("utf-8")):
                match = principal
        if match is None:
            raise AuthenticationError("Invalid session token")
        return match

    def revoke(self, token: str) -> None:
        """Revoke a token; unknown tokens are ignored."""
        self._sessions.pop(token, None)


def benchmark_principal() -> Principal:
    """Relationship manager allowed to see the four benchmark customers only (not CUST-9999)."""
    return Principal(
        principal_id="rm-001",
        allowed_customer_ids=frozenset({"CUST-0010", "CUST-0050", "CUST-0100", "CUST-0200"}),
    )


KNOWN_PRINCIPALS: Mapping[str, Principal] = MappingProxyType({"rm-001": benchmark_principal()})


def token_fingerprint(token: str) -> str:
    """Return the SHA-256 hex digest of a session token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def authenticate_token(token: str, trusted: Mapping[str, str]) -> Principal:
    """Resolve a token to a known principal via a trusted fingerprint map.

    ``trusted`` maps token fingerprints to principal ids. Fingerprints are compared in
    constant time. The token is never included in error messages.
    """
    candidate = token_fingerprint(token)
    principal_id: str | None = None
    for fingerprint, trusted_id in trusted.items():
        if hmac.compare_digest(fingerprint.encode("utf-8"), candidate.encode("utf-8")):
            principal_id = trusted_id
    if not token or principal_id is None or principal_id not in KNOWN_PRINCIPALS:
        raise AuthenticationError("Invalid session token")
    return KNOWN_PRINCIPALS[principal_id]
