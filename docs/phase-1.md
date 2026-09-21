# Phase 1 — Greenfield foundation

## Delivered

* React Native / Expo / TypeScript shell using Expo Router
* Accessible sign-in screen and five-tab navigation
* Development login with secure native token persistence
* Apple Sign-In verifier boundary that fails closed until configured
* FastAPI application with health and readiness endpoints
* SQLAlchemy 2 models for users, care profiles, and memberships
* Roles: administrator, family, carer, and cared person
* Membership-filtered profile listing and profile reads
* Admin-only member addition
* Initial Alembic migration
* PostgreSQL and API Docker development services
* Backend authorization and API tests plus a mobile component test

## Local workflow

Copy `.env.example` to `.env`, replace `JWT_SECRET`, and run:

```bash
docker compose up --build
```

For the app:

```bash
cd mobile
cp .env.example .env.local
npm install
npm run start
```

The simulator can use the default API URL. A physical phone needs `EXPO_PUBLIC_API_URL` set to an address on the same network.

## Security notes

Care-profile access is denied unless the authenticated user has a membership row for the requested profile. Administrative writes require an administrator membership. Cross-profile tests cover direct profile reads and member listing. Development login is disabled in production mode. Production deployments must use a strong secret, TLS, restrictive CORS origins, and a configured Apple token verifier.

## Intentionally incomplete

* Apple identity-token verification and production client credentials
* Invitation delivery; a user currently signs in before an administrator can add their email
* Profile selection shared across tabs
* Wellbeing, symptoms, care events, chat, medications, AI, and voice
* Production deployment manifests, observability, rate limiting, and token revocation

These are explicit later-phase concerns, not mocked care data.

## Verification at handoff

* Alembic upgrade on PostgreSQL 17: passed
* Alembic model/schema drift check: passed, no new operations detected
* API readiness against PostgreSQL: passed
* Backend pytest suite: 15 passed
* Mobile TypeScript check: passed
* Mobile Jest suite: 1 passed
* Expo iOS production bundle export: passed
* Expo dependency compatibility check: passed

The backend suite emits one upstream Starlette/AnyIO deprecation warning. `npm audit` reports moderate issues in Expo Router and Expo CLI transitive dependencies; npm's proposed forced fixes would downgrade core Expo packages across breaking versions, so they were not applied.
