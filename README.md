# Cognivault AI MVP

Cognivault AI is a secure, auditable AI agent prototype for enterprise workflows. This MVP demonstrates one fully implemented business flow: a bilingual appointment-booking agent that can chat in Turkish and English, gather missing details step by step, enforce role boundaries, call backend tools, and return a structured confirmation.

## What is included

- `frontend/`: React + TypeScript dashboard with login, conversation list, chat workspace, metrics, and audit log viewer
- `backend/`: FastAPI service with layered architecture, SQLAlchemy models, PostgreSQL integration, RBAC, agent orchestration, and seed data
- `docker-compose.yml`: PostgreSQL + backend + frontend stack
- `.env.example`: local-first environment variables for easy setup on a laptop
- `references/DocsGPT/`: pulled reference repository used as a product/architecture benchmark
- `scripts/`: local setup and run helpers

## MVP scenario

The implemented workflow is **appointment booking** for enterprise service teams:

- Onboarding Desk
- Technical Support
- Billing Operations
- Compliance Advisory

The AI agent:

- greets the user in Turkish or English
- keeps the conversation inside a controlled appointment workflow
- asks for missing information one step at a time
- checks permissions before creating records
- calls backend tools like `check_available_slots()` and `create_appointment()`
- logs every important action to the audit trail

The code is structured so an **application submission** flow can be added later with a parallel tool/service path.

## Architecture summary

The backend follows a clean layered design:

- API layer: FastAPI routes in `backend/app/api/routes`
- Service layer: business logic in `backend/app/services`
- Agent layer: orchestration and prompt logic in `backend/app/agent`
- Tool layer: enterprise tool registry in `backend/app/tools`
- Database layer: SQLAlchemy models and session management in `backend/app/db` and `backend/app/models`

Core domain models:

- `users`
- `roles`
- `chat_sessions`
- `chat_messages`
- `appointment_slots`
- `appointments`
- `audit_logs`

## Authentication and roles

The MVP uses mock role-based authentication with seeded users:

| Role | Email | Password | Permissions |
| --- | --- | --- | --- |
| Customer | `ayse@cognivault.local` | `demo123` | Can create and view only her own appointments and logs |
| Customer | `john@cognivault.local` | `demo123` | Can create and view only his own appointments and logs |
| Operator | `operator@cognivault.local` | `demo123` | Can manage requests and view operational records |
| Admin | `admin@cognivault.local` | `demo123` | Can view all records, logs, and users |

## Bilingual behavior

The agent supports Turkish and English in the same chat interface.

- With `OPENAI_API_KEY` set, the backend uses OpenAI tool/function calling.
- Without an API key, the app falls back to a local guided workflow engine so the MVP remains demoable offline.

## API overview

Main endpoints:

- `POST /api/auth/login`
- `GET /api/auth/me`
- `GET /api/users`
- `GET /api/users/roles`
- `GET /api/chat/sessions`
- `POST /api/chat/sessions`
- `GET /api/chat/sessions/{id}`
- `POST /api/chat/sessions/{id}/messages`
- `GET /api/appointments`
- `POST /api/appointments`
- `GET /api/appointments/slots`
- `GET /api/audit-logs`
- `GET /api/audit-logs/metrics`

## Local run on a laptop

This repo now supports a **local-first dev mode** for machines without Docker or PostgreSQL.

- Local development uses SQLite by default so the MVP can be demoed quickly.
- Docker deployment still uses PostgreSQL to preserve the intended production-style stack.

### Fastest setup

```bash
./scripts/setup_local.sh
```

Then start the app in two terminals:

```bash
./scripts/run_backend.sh
```

```bash
./scripts/run_frontend.sh
```

Frontend: [http://localhost:5173](http://localhost:5173)  
Backend: [http://localhost:8000](http://localhost:8000)

## Running locally without Docker

### 1. Prepare environment

Copy the example environment:

```bash
cp .env.example .env
```

For local backend development, the default `.env.example` already points to a SQLite file:

```env
DATABASE_URL=sqlite:////Users/ec/Desktop/cognivaultAi/backend/data/cognivault.db
VITE_API_URL=http://localhost:8000/api
```

### 2. Run the backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

On startup the backend creates tables and seeds sample users, slots, a past chat session, and audit records.

### 3. Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend: [http://localhost:5173](http://localhost:5173)  
Backend: [http://localhost:8000](http://localhost:8000)

## Running with Docker

Docker mode still uses PostgreSQL inside containers even if your root `.env` is configured for local SQLite.

```bash
cp .env.example .env
docker compose up --build
```

Services:

- Frontend: [http://localhost:8080](http://localhost:8080)
- Backend: [http://localhost:8000](http://localhost:8000)
- PostgreSQL: `localhost:5432`

## Sample demo flow

Customer demo in Turkish:

1. Sign in as `ayse@cognivault.local`
2. Open a new session
3. Send: `Teknik destek için randevu almak istiyorum.`
4. Let the agent collect the purpose and phone number
5. Pick one of the proposed slots
6. Observe the confirmation card and audit trail update

Customer demo in English:

1. Sign in as `john@cognivault.local`
2. Send: `I need an appointment with billing operations.`
3. Complete the guided steps
4. Review the confirmation code and recent records

Admin demo:

1. Sign in as `admin@cognivault.local`
2. Inspect conversations, metrics, and audit activity
3. Export the audit log JSON from the right-side panel

## OpenAI integration

Set these values in `.env` to enable tool/function calling:

```env
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4.1-mini
```

The orchestration code lives in:

- `backend/app/agent/orchestrator.py`
- `backend/app/tools/registry.py`

## Future improvements

- Add the application submission flow with shared policy controls
- Replace mock auth with SSO or OAuth2
- Add approval steps for higher-risk actions
- Introduce Alembic migrations
- Add streaming responses and richer agent traces
- Add connectors for CRM/ERP systems
- Add granular policy rules beyond basic role checks
- Add test suites for API, services, and frontend behavior
