import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from html import escape
from typing import Protocol

from app.core.config import Settings, get_settings


class EmailDeliveryError(RuntimeError):
    pass


@dataclass(frozen=True)
class InvitationEmail:
    recipient: str
    inviter_name: str
    profile_name: str
    intended_role: str
    accept_url: str
    expires_hours: int


class EmailProvider(Protocol):
    def send_invitation(self, invitation: InvitationEmail) -> None: ...


def invitation_message(invitation: InvitationEmail, sender: str) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = "You've been invited to CareRelay"
    message["From"] = sender
    message["To"] = invitation.recipient
    context = (
        "the person this profile is about"
        if invitation.intended_role == "subject"
        else invitation.intended_role
    )
    text = (
        f"{invitation.inviter_name} has invited you to join "
        f"{invitation.profile_name}'s CareRelay care circle as {context}.\n\n"
        f"Accept invitation: {invitation.accept_url}\n\n"
        "If the button does not work, copy this link into Safari:\n"
        f"{invitation.accept_url}\n\n"
        f"This invitation expires in {invitation.expires_hours} hours. "
        "Sign in with Apple to accept it."
    )
    message.set_content(text)
    safe_url = escape(invitation.accept_url, quote=True)
    html = (
        f"<p>{escape(invitation.inviter_name)} has invited you to join "
        f"{escape(invitation.profile_name)}'s CareRelay care circle as "
        f"{escape(context)}.</p>"
        f'<p><a href="{safe_url}" style="background:#245c52;border-radius:8px;color:#ffffff;'
        'display:inline-block;font-weight:700;padding:12px 18px;text-decoration:none">'
        "Accept invitation</a></p>"
        "<p>If the button does not work, copy this link into Safari:<br>"
        f'<a href="{safe_url}">{safe_url}</a></p>'
        f"<p>This invitation expires in {invitation.expires_hours} hours. "
        "Sign in with Apple to accept it.</p>"
    )
    message.add_alternative(html, subtype="html")
    return message


class MockEmailProvider:
    def __init__(self) -> None:
        self.sent: list[InvitationEmail] = []

    def send_invitation(self, invitation: InvitationEmail) -> None:
        self.sent.append(invitation)


class GmailSMTPProvider:
    def __init__(self, settings: Settings) -> None:
        self.host = settings.smtp_host
        self.port = settings.smtp_port
        self.username = settings.smtp_username
        self.password = settings.smtp_password
        self.use_tls = settings.smtp_use_tls
        self.sender = settings.email_from
        if not all((self.host, self.username, self.password, self.sender)) or not self.use_tls:
            raise ValueError("Gmail SMTP configuration is incomplete")

    def send_invitation(self, invitation: InvitationEmail) -> None:
        message = invitation_message(invitation, self.sender)
        try:
            with smtplib.SMTP(self.host, self.port, timeout=15) as client:
                client.ehlo()
                client.starttls(context=ssl.create_default_context())
                client.ehlo()
                client.login(self.username, self.password)
                client.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            raise EmailDeliveryError("Invitation email delivery failed") from exc


_mock_provider = MockEmailProvider()


def get_email_provider() -> EmailProvider:
    settings = get_settings()
    if settings.email_provider == "mock":
        return _mock_provider
    return GmailSMTPProvider(settings)
