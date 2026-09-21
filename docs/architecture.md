# CareRelay architecture

## System shape

CareRelay is a mobile client and stateless API backed by PostgreSQL.

```text
Expo / React Native
        |
        | HTTPS + bearer access token
        v
FastAPI application
  |-- authentication boundary
  |-- membership authorization boundary
  |-- versioned REST routes (/api/v1)
        |
        | SQLAlchemy 2 sessions
        v
PostgreSQL
```

Docker Compose runs PostgreSQL and the API for local development. Redis is deliberately absent. Phase 4 realtime fan-out is in-process for the current single API instance; the connection-manager boundary can adopt shared pub/sub before horizontal scaling.

## API boundaries

The application exposes unversioned liveness/readiness endpoints and versioned product APIs.

* `GET /health/live` proves that the process is serving requests.
* `GET /health/ready` proves that the API can query PostgreSQL.
* `/api/v1/auth/*` owns identity and access-token creation.
* `/api/v1/care-profiles/*` owns care profiles and membership.
* `/api/v1/care-profiles/{id}/chat/*` owns durable profile chat and unread state.
* `/api/v1/care-profiles/{id}/chat/ws` delivers transient realtime chat signals.
* `/api/v1/care-profiles/{id}/ask` orchestrates deterministic care-data tools and a configured AI provider.

The development login creates or reuses a user by normalized email. It exists only when `APP_ENV` is `development` or `test`; production returns 404. Tokens are signed JWTs with a user UUID in `sub` and an expiry. The mobile client stores native tokens in the platform's secure storage.

Apple authentication uses an `AppleTokenVerifier` interface. The endpoint, request shape, account-link field, and dependency boundary exist, while the default verifier fails closed until Apple credentials and claim verification are configured.

## Authorization invariant

Every route with a `care_profile_id` resolves the profile through `require_profile_membership`. The query constrains both profile ID and current user ID in the database. A non-member receives 404 whether or not the target profile exists, reducing profile enumeration.

Administrator operations add a second dependency that checks the membership role. List queries join through membership and never fetch all profiles before filtering. Future care-domain routes must reuse the same dependency (or an equally restrictive service-layer policy), and tests must include cross-profile access attempts.

Self-report authority is a separate identity check: the authenticated member must equal `CareProfile.subject_user_id`. CareEvent authorship uses the authenticated membership, derives its source server-side, and permits mutation only by the author or a profile administrator. These checks preserve the profile tenancy boundary without overloading the single membership role.

Chat REST and WebSocket access query the same membership pair. WebSocket clients first exchange an authenticated REST request for a short-lived, one-time ticket, so long-lived JWTs never appear in WebSocket URLs. The mobile UI may hide unavailable actions for clarity, but it is never an authorization control.

## Evolution

Wellbeing self reports, CareEvents, and chat are separate domain modules beneath the existing profile tenancy boundary. Self reports and CareEvents are merged only for timeline presentation. Chat becomes a CareEvent only through a reviewed, explicitly confirmed copy with provenance. Realtime delivery is an optimization over durable REST recovery. Alembic is the only supported production schema-change mechanism.

Ask CareRelay can read only confirmed self reports and CareEvents through profile-scoped deterministic tools. It cannot query raw chat or execute arbitrary SQL. Numeric results and visualization data are calculated before provider invocation, and record references remain attached to the response.
