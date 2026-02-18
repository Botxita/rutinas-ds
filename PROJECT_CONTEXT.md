# Rutinas DS — Project Context

## Overview

Rutinas DS is a gym routine management system used at Deluxe Sports.

The system allows trainers to assign workout routines to clients, track execution and progress, and maintain a centralized catalog of base routines synchronized from Google Sheets.

The architecture is intentionally designed to separate:

1. Base routines (catalog)
2. Assigned routines (snapshots)

This separation is a core rule and must never be broken.

---

## Core Concept (NON-NEGOTIABLE)

There are two independent worlds:

### 1) Base Routines (CATALOG)

- Source of truth: Google Sheets
- Editable and re-synchronizable
- Versioned
- Never assigned directly to clients
- Changes must NOT affect already assigned routines

Examples:
- RB001 – Fullbody Strength
- RB002 – Upper/Lower Hypertrophy
- RB003 – Calisthenics Technique

### 2) Assigned Routines (SNAPSHOT)

- Stored in the database
- Created when a trainer assigns a base routine
- Editable per client
- Frozen copy of base routine at assignment time
- Must remain unchanged even if base routine changes

---

## Roles

### CLIENT
- View active routine (snapshot)
- Mark routine as completed
- View progress and measurements

### TRAINER
- Search clients by DNI
- Assign base routines (creates snapshot)
- Edit assigned routine snapshot
- Record measurements

### COORDINATOR / ADMIN
- All trainer permissions
- Synchronize Google Sheets
- Maintain base routine catalog
- Manage trainers
- Audit access

Only COORDINATOR/ADMIN can synchronize Sheets.

---

## Backend Architecture

### Stack
- FastAPI
- SQLAlchemy
- PostgreSQL (Supabase)
- JWT authentication

### Structure

backend/
??? main.py
??? router_plan.py
??? router_routines.py
??? router_users.py
??? auth/
??? core/
??? db/


Key logic:
- business logic in core/plan_service.py
- database models in db/models.py
- auth handled in auth/

---

## Frontend Architecture

### Stack
- Next.js (App Router)
- React
- Role-based UI rendering

Structure:

frontend/
??? app/
? ??? login/
? ??? (protected)/
? ? ??? cliente/
? ? ??? staff/
??? components/
??? lib/


Frontend consumes backend API only.
No business logic should exist exclusively in frontend.

---

## Data Model (Conceptual)

### Catalog (from Google Sheets)
- exercise_dictionary
- base_routines
- base_routine_items

These tables are re-synchronizable.

### Assignments
- routine_plans
- routines (snapshot)
- routine_days (future)
- routine_items (future)

Rule:
A client may have multiple plans but only ONE ACTIVE.

---

## Synchronization

Endpoint:

POST /admin/sync/sheets

Responsibilities:
- Read exercise dictionary
- Update base routines
- Increment version if changed
- NEVER modify snapshots

---

## Development Rules

1. Never merge base routines with assigned routines.
2. Never modify snapshots during synchronization.
3. Backend is source of truth for business logic.
4. Frontend reflects backend state only.
5. Role permissions must be enforced server-side.

---

## Current Development Stage

- Authentication working
- Trainer UI in progress
- Routine assignment flow under development
- Snapshot model already defined

Next steps involve:
- trainer workflow completion
- routine editing UI
- progress tracking





