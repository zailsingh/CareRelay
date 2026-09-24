# Production Identity & Care Circle

## Architecture

CareRelay now separates authentication identity from access to care data:

- `User` is the local account.
- `UserIdentity` maps an authentication provider and stable provider subject to one User. Apple `sub`, not email, is the account key.
- `CareProfile` is the shared care space.
- `CareMembership` grants the `admin`, `family`, or `carer` permissions already used by the API.
- `CareProfile.subject_user_id` is the authoritative identity of the person the profile is about.

The legacy `cared_person` membership role remains in the enum for data compatibility. New subject linking and subject-only authorization do not depend on it. It can be removed in a later, separately planned data migration after existing rows have been inspected.

## Sign in with Apple

The iOS app uses the native Apple button and requests email/name scopes. It creates a cryptographically random nonce, sends the SHA-256 nonce to Apple, validates returned state locally, then sends the Apple identity JWT and raw nonce to the API. The API obtains Apple's public key from the JWKS endpoint and verifies RS256 signature, issuer, audience, expiry, subject, and nonce before resolving `UserIdentity(provider="apple", provider_subject=sub)`.

Apple may supply a real address, a private relay address, or no address on later logins. Initial email/name are retained when available; email is not used to merge accounts and an invitation delivery address need not match the Apple address. Revoked identities cannot log in and their existing bearer sessions are rejected. Shared care history is retained.

`POST /api/v1/auth/apple/notifications` is the validated service boundary for Apple server notifications. Consent revocation and account deletion revoke the identity. Production Apple configuration must register the iOS identifier and server-notification endpoint with Apple.

## Development and production authentication

`APP_ENV=development|test` enables `/auth/dev-login`; `APP_ENV=production` returns 404. The mobile DEV form is shown unless `EXPO_PUBLIC_APP_ENV=production`. Production requires a strong `JWT_SECRET` and `APPLE_CLIENT_ID`. No Apple private key is needed by the implemented identity-token/JWKS verification flow, so unused team/key/private-key settings are intentionally absent.

## First-login onboarding

The root route loads memberships after authentication. A user with none enters onboarding; a returning member enters the app. Creating a profile always makes the creator its admin. “Someone I care for” leaves `subject_user_id` empty; “Me” explicitly links it to the creator. Onboarding then offers subject, family, and carer invitations, but invitations can be skipped.

## Invitations

`CareInvitation` stores profile, delivery email, intended role, subject intent, creator, timestamps, delivery state, and only a SHA-256 token hash. The raw 256-bit random token appears only in the email and, outside production, the creation/resend response for local testing. It is never stored. Invitations are authenticated, single-use, expiring, revocable, and row-locked during acceptance.

An admin can create, resend, or revoke an invitation. Resending rotates the token and expiry; the old token immediately fails. Acceptance requires both the token and a signed-in account. It creates a membership only if one does not exist, preserving an existing role. A subject invitation links `subject_user_id` only when no conflicting subject exists; conflicts return 409 and never overwrite the current subject.

The configured email link is `${INVITE_BASE_URL}/<token>`. For physical-device development, set `INVITE_BASE_URL=http://<LAN-IP>:<API-PORT>/invite`; the backend landing page hands the browser to `carerelay://invite/<token>`. Expo then routes `/invite/[token]`, preserves the token through sign-in, asks for explicit acceptance, refreshes memberships, and opens the app. Production must set `INVITE_BASE_URL=https://<associated-domain>/invite`, serve an Apple App Site Association file for `/invite/*`, and add that host to the iOS `applinks:` entitlement. No production domain is assumed by this repository.

## Email delivery

`EmailProvider` has `MockEmailProvider` and `GmailSMTPProvider` implementations. Gmail uses port 587 by default, STARTTLS, authentication, a 15-second timeout, MIME plain-text/HTML, and clean context-managed shutdown. Use a dedicated Gmail account with two-factor authentication and a Google App Password—never the normal account password.

The message includes inviter name, profile display name, role context, accept link, and expiry. It excludes wellbeing, symptoms, events, medication, reports, chat, and diagnoses. The invitation is committed before delivery. Success sets `email_sent_at`; failure stores a generic retryable delivery error, does not claim success, and never exposes SMTP internals. Resend rotates the token before another delivery attempt. There is no silent provider fallback.

For Apple Private Email Relay delivery in production, configure an authenticated outbound sender and the relevant sender/domain with Apple. SPF and DKIM are required foundations; DMARC is strongly recommended. Gmail SMTP is appropriate for development and small-scale validation but private-relay delivery still needs real-domain testing.

## People, permissions, and account deletion

The People screen shows whether the subject is not invited, pending, or linked; current members and roles; invitation status/delivery state; and admin controls for invite, resend, revoke, role change, and removal. The backend prevents demoting/removing the last admin and prevents removing a linked subject until the subject is changed or unlinked. Existing profile-scoped authorization continues to protect wellbeing, chat, Ask, medications, and reports.

In-app account deletion revokes provider identities, unlinks the user as a profile subject, removes memberships, and records the deletion request while retaining shared care history. A sole admin must first transfer administration. Users who are not the last admin can leave their profiles through deletion; the account row remains as a retention/audit anchor.

## Audit and secret handling

Audit events cover profile/initial-admin creation, invitation creation, email success/failure, resend, revoke, acceptance, membership creation/role/removal, subject link/change, and account deletion requests. Audit state contains only identifiers and safe role/state metadata. Raw invitation tokens, Apple JWTs, SMTP passwords, authorization headers, and full email bodies are not recorded.

## Configuration checklist

Backend:

```dotenv
APP_ENV=production
JWT_SECRET=<unique random value of at least 32 characters>
APPLE_CLIENT_ID=com.carerelay.mobile
APPLE_JWKS_URL=https://appleid.apple.com/auth/keys
EMAIL_PROVIDER=gmail
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=<dedicated CareRelay Gmail address>
SMTP_PASSWORD=<Google App Password>
SMTP_USE_TLS=true
EMAIL_FROM=CareRelay <same-or-authorized-address>
INVITE_BASE_URL=https://<associated-domain>/invite
INVITE_EXPIRE_HOURS=168
```

Mobile/build:

```dotenv
EXPO_PUBLIC_API_URL=https://<api-domain>/api/v1
EXPO_PUBLIC_APP_ENV=production
```

Also enable Sign in with Apple for the Apple identifier, configure the server-notification URL, set up the associated domain/fallback page, and validate Gmail and Apple relay delivery. Secrets belong only in the deployment secret store; never commit `.env`, Apple private keys, or Gmail App Passwords.

## Tests and known limitations

Automated tests use local Apple signing keys, fixture verifiers, and the mock email provider; they do not require live Apple, Gmail, or OpenRouter access. Backend tests cover verification failures, repeat identity resolution, onboarding semantics, invitation lifecycle/security, delivery state, role/admin guardrails, revocation, and account deletion. Mobile tests cover Apple UX, environment gating, both onboarding modes, deep-link acceptance, expiry, care-circle states and actions, and final-admin error handling. The complete earlier-phase suites remain the authorization regression coverage.

Known production follow-ups are operational: live Apple credential validation, live Gmail/App Password delivery, Apple private-relay validation, and hosting/associating the HTTPS invitation fallback. Password auth, other identity providers, SMS, push, voice, OCR, and task/reminder features are intentionally out of scope.
