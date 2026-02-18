# Rutinas DS — Current Project State

This document describes the CURRENT implementation status of the system.
It is intended to prevent incorrect assumptions during development.

This is not a roadmap or design document.
It reflects what is currently implemented and working.

---

## Environment Status

### Backend
- FastAPI running locally
- SQLAlchemy connected to PostgreSQL (Supabase)
- JWT authentication implemented
- Login endpoint working
- Role system implemented

Backend runs on:
http://127.0.0.1:8001

### Frontend
- Next.js App Router
- Login screen implemented
- Protected routes implemented
- Trainer client list UI started
- Client routine view started

Frontend runs on:
http://localhost:3000

---

## Implemented Features

### Authentication
- Login by DNI
- CLIENT login: DNI only
- TRAINER/COORDINATOR/ADMIN: DNI + password
- JWT token generation working
- Protected routes functional

### Users
- User roles defined
- Basic user retrieval working

### Base Structure
- Backend routers separated:
  - router_users
  - router_plan
  - router_routines

- Service layer exists:
  - core/plan_service.py

---

## Partially Implemented

### Trainer Workflow
- Trainer can access client list
- Client detail page exists
- Routine assignment flow not fully completed

### Routine Management
- Conceptual model defined
- Snapshot logic partially implemented
- Editing UI not finished

---

## Not Implemented Yet

### Google Sheets Sync
- Endpoint planned
- Sync logic not yet implemented

### Routine Versioning
- Version field exists conceptually
- Automatic version increment not finalized

### Progress Tracking
- client_plan_state not implemented

### Measurements Tracking
- Not implemented

---

## Known Technical Constraints

- Backend is the only source of business logic.
- Frontend must not implement routine logic independently.
- Snapshot model must be preserved.

---

## Immediate Next Development Targets

1. Complete trainer routine assignment flow
2. Snapshot creation validation
3. Routine editing from trainer UI
4. Active plan management
5. Basic progress tracking

---

## Important Notes for Contributors / AI Assistants

- Do NOT merge catalog and snapshot logic.
- Do NOT simplify routine assignment model.
- Do NOT move business logic to frontend.
- Respect ARCHITECTURE_DECISIONS.md at all times.