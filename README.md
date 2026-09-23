# CareRelay

CareRelay is a mobile-first family care coordination application. The current Phase 7 build provides canonical profile subjects, membership-scoped care profiles, self-reported wellbeing, structured care observations, private family chat, evidence-backed Ask CareRelay answers, timezone-safe medication plans with explicit dose tracking, and evidence-backed appointment reports with private PDF sharing.

## Quick start

Prerequisites: Docker Desktop, Node.js 22+, and npm.

```bash
cp .env.example .env
docker compose up --build
```

If ports 5432 or 8000 are occupied, set `POSTGRES_PORT` or `API_PORT` in `.env`. Container-to-container database connectivity is unchanged.

The API is then available at `http://localhost:8000`, with interactive docs at `http://localhost:8000/docs`.

In a second terminal:

```bash
cd mobile
cp .env.example .env.local
npm install
npm run start
```

For a physical device, set `EXPO_PUBLIC_API_URL` in `mobile/.env.local` to the computer's LAN address, for example `http://192.168.1.20:8000/api/v1`.

The development sign-in accepts an email and display name. It is disabled whenever `APP_ENV=production`. Apple sign-in boundaries are present on the API and mobile app, but provider verification is intentionally not configured in Phase 1.

## Validation

```bash
docker compose run --rm api pytest
docker compose run --rm api ruff check app tests alembic
docker compose run --rm api alembic upgrade head
cd mobile && npm test -- --runInBand
cd mobile && npm run typecheck
```

See [architecture](docs/architecture.md), [data model](docs/data-model.md), the [Phase 6 handoff](docs/phase-6.md), and the [Phase 7 handoff](docs/phase-7.md).
