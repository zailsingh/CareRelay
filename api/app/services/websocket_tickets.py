import secrets
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID


@dataclass(frozen=True)
class WebSocketTicket:
    value: str
    user_id: UUID
    care_profile_id: UUID
    expires_at: datetime


class WebSocketTicketStore:
    """Single-process, one-time tickets for the single-instance chat deployment."""

    def __init__(self, ttl_seconds: int = 45) -> None:
        self.ttl_seconds = ttl_seconds
        self._tickets: dict[str, WebSocketTicket] = {}
        self._lock = threading.Lock()

    def issue(self, user_id: UUID, care_profile_id: UUID) -> WebSocketTicket:
        now = datetime.now(UTC)
        ticket = WebSocketTicket(
            value=secrets.token_urlsafe(32),
            user_id=user_id,
            care_profile_id=care_profile_id,
            expires_at=now + timedelta(seconds=self.ttl_seconds),
        )
        with self._lock:
            self._tickets[ticket.value] = ticket
            self._purge_expired(now)
        return ticket

    def consume(self, value: str, care_profile_id: UUID) -> WebSocketTicket | None:
        now = datetime.now(UTC)
        with self._lock:
            ticket = self._tickets.pop(value, None)
            self._purge_expired(now)
        if ticket is None or ticket.expires_at <= now or ticket.care_profile_id != care_profile_id:
            return None
        return ticket

    def _purge_expired(self, now: datetime) -> None:
        expired = [key for key, ticket in self._tickets.items() if ticket.expires_at <= now]
        for key in expired:
            self._tickets.pop(key, None)


websocket_tickets = WebSocketTicketStore()
