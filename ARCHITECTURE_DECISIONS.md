# Rutinas DS — Architecture Decisions

This document records the architectural decisions taken in the project.
These decisions are intentional and should not be modified unless a full redesign is explicitly planned.

The goal is to preserve consistency across development iterations and AI-assisted coding.

---

## AD-001 — Separation Between Catalog and Snapshot

### Decision
Base routines (catalog) and assigned routines (snapshots) are strictly separated.

### Reason
Base routines evolve over time. Clients must never be affected by catalog changes after assignment.

### Implications
- Base routines are never assigned directly to clients.
- Assigning a routine creates a snapshot copy.
- Synchronization from Google Sheets must never modify existing snapshots.

### Status
NON-NEGOTIABLE

---

## AD-002 — Google Sheets as Source of Truth for Base Routines

### Decision
Google Sheets stores the master definition of exercises and base routines.

### Reason
Allows trainers and coordinators to maintain routines without modifying application code.

### Implications
- Application imports and version-controls routines.
- Changes increment version numbers.
- Database catalog is replaceable via sync.

---

## AD-003 — Backend as Single Source of Business Logic

### Decision
All business rules live in backend (FastAPI).

### Reason
Avoid inconsistencies between frontend and backend logic.

### Implications
- Frontend does not calculate routine logic.
- Role permissions validated server-side.
- Snapshot creation logic only exists in backend.

---

## AD-004 — Snapshot Mutability

### Decision
Assigned routines (snapshots) are editable after creation.

### Reason
Trainers must adapt routines per client without affecting catalog.

### Implications
- Snapshot editing is allowed.
- Catalog remains immutable from client operations.

---

## AD-005 — Single Active Plan Per Client

### Decision
A client can have multiple historical plans but only one ACTIVE.

### Reason
Simplifies execution tracking and progress state.

### Implications
- New assignment archives previous active plan.
- Progress tracking linked to active plan only.

---

## AD-006 — Role-Based Permissions

### Decision
Roles are enforced in backend:

- CLIENT
- TRAINER
- COORDINATOR
- ADMIN

### Reason
Frontend restrictions alone are insufficient for security.

### Implications
- API endpoints validate roles.
- UI visibility is secondary.

---

## AD-007 — Incremental Development Strategy

### Decision
System is built in stages.

### Current priorities
1. Authentication stability
2. Trainer workflow
3. Routine assignment
4. Snapshot editing
5. Progress tracking

### Reason
Avoid premature complexity and keep system usable during development.

---

## AD-008 — Avoid Over-Engineering Early

### Decision
Routine editing structure (routine_days / routine_items) remains simple until real usage requires complexity.

### Reason
Actual gym workflow should guide complexity.

---

## Future Revisions

Any change affecting:

- snapshot behavior
- synchronization logic
- role permissions
- routine lifecycle

must update this document.