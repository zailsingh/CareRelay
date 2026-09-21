from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AppleIdentity:
    subject: str
    email: str


class AppleTokenVerifier(Protocol):
    def verify(self, identity_token: str) -> AppleIdentity: ...


class UnconfiguredAppleTokenVerifier:
    """Phase 1 boundary for a production Apple identity-token verifier."""

    def verify(self, identity_token: str) -> AppleIdentity:
        raise RuntimeError("Apple Sign-In is not configured")


def get_apple_token_verifier() -> AppleTokenVerifier:
    return UnconfiguredAppleTokenVerifier()
