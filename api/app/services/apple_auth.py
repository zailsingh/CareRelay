import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

import jwt
from jwt import InvalidTokenError, PyJWKClient, PyJWKClientError

from app.core.config import get_settings


class AppleVerificationError(ValueError):
    pass


@dataclass(frozen=True)
class AppleIdentity:
    subject: str
    email: str | None


@dataclass(frozen=True)
class AppleNotification:
    subject: str
    event_type: str


class AppleTokenVerifier(Protocol):
    def verify(self, identity_token: str, nonce: str) -> AppleIdentity: ...

    def verify_notification(self, signed_payload: str) -> AppleNotification: ...


class UnconfiguredAppleTokenVerifier:
    def verify(self, identity_token: str, nonce: str) -> AppleIdentity:
        raise RuntimeError("Apple Sign-In is not configured")

    def verify_notification(self, signed_payload: str) -> AppleNotification:
        raise RuntimeError("Apple Sign-In is not configured")


class ProductionAppleTokenVerifier:
    def __init__(self, client_id: str, jwks_url: str) -> None:
        if not client_id:
            raise RuntimeError("Apple Sign-In is not configured")
        self.client_id = client_id
        self.jwks = PyJWKClient(jwks_url, cache_keys=True)

    def _decode(self, token: str, *, required: list[str]) -> dict[str, Any]:
        try:
            signing_key = self.jwks.get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.client_id,
                issuer="https://appleid.apple.com",
                options={"require": ["iss", "aud", "exp", *required]},
            )
        except (InvalidTokenError, PyJWKClientError, ValueError) as exc:
            raise AppleVerificationError("Apple identity verification failed") from exc

    def verify(self, identity_token: str, nonce: str) -> AppleIdentity:
        claims = self._decode(identity_token, required=["sub"])
        expected_nonce = hashlib.sha256(nonce.encode()).hexdigest()
        if claims.get("nonce") != expected_nonce:
            raise AppleVerificationError("Apple identity nonce did not match")
        email = claims.get("email")
        return AppleIdentity(
            subject=str(claims["sub"]),
            email=str(email).lower() if email else None,
        )

    def verify_notification(self, signed_payload: str) -> AppleNotification:
        claims = self._decode(signed_payload, required=["events"])
        events = claims.get("events", {})
        if isinstance(events, str):
            try:
                events = json.loads(events)
            except json.JSONDecodeError as exc:
                raise AppleVerificationError("Apple notification events were invalid") from exc
        if isinstance(events, list):
            events = events[0] if len(events) == 1 else {}
        if not isinstance(events, dict):
            raise AppleVerificationError("Apple notification events were invalid")
        event_type = str(events.get("type", ""))
        subject = str(events.get("sub", ""))
        if not event_type or not subject:
            raise AppleVerificationError("Apple notification was incomplete")
        return AppleNotification(subject=subject, event_type=event_type)


@lru_cache
def get_apple_token_verifier() -> AppleTokenVerifier:
    settings = get_settings()
    if not settings.apple_client_id:
        return UnconfiguredAppleTokenVerifier()
    return ProductionAppleTokenVerifier(settings.apple_client_id, settings.apple_jwks_url)
