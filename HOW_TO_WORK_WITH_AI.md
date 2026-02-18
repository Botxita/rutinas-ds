# Rutinas DS — How To Work With AI Assistants

This document defines how AI assistants (Claude, ChatGPT or others)
should be used when working on this project.

The goal is to maintain architectural consistency and avoid unnecessary refactors.

---

## 1. Read Context First

Before proposing changes, always read:

1. PROJECT_CONTEXT.md
2. ARCHITECTURE_DECISIONS.md
3. CURRENT_STATE.md

These documents define constraints and current implementation status.

Do not assume missing features are design mistakes.

---

## 2. Development Philosophy

The project follows an incremental development approach.

Rules:

- Prefer small, isolated changes.
- Do not redesign working parts.
- Do not refactor unrelated modules.
- Maintain compatibility with existing endpoints.

AI assistants must prioritize stability over elegance.

---

## 3. Forbidden Changes Without Explicit Request

The following must NEVER be changed unless explicitly requested:

- Separation between base routines and snapshots
- Snapshot creation logic
- Role model (CLIENT / TRAINER / COORDINATOR / ADMIN)
- Backend as source of business logic
- Google Sheets as catalog source

---

## 4. How Changes Should Be Proposed

AI responses should:

1. Explain impact before modifying architecture.
2. Modify only required files.
3. Avoid introducing new frameworks or libraries unless necessary.
4. Preserve existing naming conventions.

---

## 5. Backend Rules

- Business logic lives in backend only.
- Endpoints must validate roles.
- Database models must remain consistent with snapshot logic.
- Avoid premature abstraction.

---

## 6. Frontend Rules

- Frontend reflects backend state.
- No independent routine calculations.
- UI logic must not duplicate backend rules.

---

## 7. Preferred AI Interaction Style

Good examples:

? "Add endpoint to assign routine creating snapshot."
? "Extend trainer UI to edit snapshot items."

Bad examples:

? "Refactor entire routine system."
? "Simplify data model."

---

## 8. When Unsure

AI should ask clarification instead of redesigning.

---

## 9. Goal

Maintain a stable system that evolves progressively,
guided by real usage in the gym environment.