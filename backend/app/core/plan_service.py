from datetime import date
from uuid import UUID

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.db.models import (
    BaseRoutine,
    BaseRoutineItem,
    ClientPlanState,
    ClientRoutine,
    ClientRoutineItem,
)


# =============================================================================
# State management
# =============================================================================

def get_or_init_state(db: Session, client_id) -> ClientPlanState:
    """Ensures a ClientPlanState row exists for the client. Defaults next_base_day_index to 1."""
    st = db.query(ClientPlanState).filter(ClientPlanState.client_id == client_id).first()
    if not st:
        st = ClientPlanState(
            client_id=client_id,
            next_base_day_index=1,
            week_start_date=date.today(),  # schema requires NOT NULL; not used for logic
        )
        db.add(st)
        db.flush()
    return st


def _get_total_routine_days(db: Session, client_id) -> int:
    """Returns max(day_index) from the active ClientRoutine snapshot."""
    cr = (
        db.query(ClientRoutine)
        .filter(ClientRoutine.client_id == client_id, ClientRoutine.active.is_(True))
        .first()
    )
    if not cr:
        raise ValueError("El cliente no tiene una rutina activa asignada")

    top_item = (
        db.query(ClientRoutineItem)
        .filter(ClientRoutineItem.client_routine_id == cr.id)
        .order_by(desc(ClientRoutineItem.day_index))
        .first()
    )
    if not top_item:
        raise ValueError("La rutina activa no tiene ejercicios")

    return top_item.day_index


# =============================================================================
# Public API
# =============================================================================

def get_current_training_day(db: Session, client_id) -> int:
    """Returns the current training day index for the client."""
    st = get_or_init_state(db, client_id)
    return st.next_base_day_index


def complete_training(db: Session, client_id) -> int:
    """
    Advances the client to the next training day.
    Wraps back to 1 after the last day of the routine.
    Returns the new next_base_day_index.
    """
    total = _get_total_routine_days(db, client_id)
    st = get_or_init_state(db, client_id)

    next_day = st.next_base_day_index + 1
    if next_day > total:
        next_day = 1

    st.next_base_day_index = next_day
    db.commit()
    return next_day


# =============================================================================
# Assign routine
# =============================================================================

class AssignRoutineResult:
    """Result of assign_base_routine_to_client. Used by the router to build the response."""

    def __init__(
        self,
        client_routine_id: UUID,
        client_id: UUID,
        base_routine_id: UUID,
        sheet_routine_id: str,
        copied_items: int,
    ):
        self.client_routine_id = client_routine_id
        self.client_id = client_id
        self.base_routine_id = base_routine_id
        self.sheet_routine_id = sheet_routine_id
        self.copied_items = copied_items


def assign_base_routine_to_client(
    db: Session,
    client_id: UUID,
    sheet_routine_id: str,
) -> AssignRoutineResult:
    """
    Assigns a base routine to a client by creating a full physical snapshot.

    - Looks up BaseRoutine by sheet_routine_id where active=True.
    - Deactivates any existing active ClientRoutine for the client.
    - Creates a new ClientRoutine (snapshot header) with active=True.
    - Copies all BaseRoutineItem rows to ClientRoutineItem.
    - Resets ClientPlanState with next_base_day_index = 1.
    - Single commit at the end; rollback on any exception.

    Raises:
        ValueError: if the base routine doesn't exist, isn't active, or has no items.
    """
    base: BaseRoutine | None = (
        db.query(BaseRoutine)
        .filter(
            BaseRoutine.sheet_routine_id == sheet_routine_id,
            BaseRoutine.active.is_(True),
        )
        .first()
    )
    if not base:
        raise ValueError(f"Rutina base '{sheet_routine_id}' no encontrada o no está activa")

    base_items: list[BaseRoutineItem] = (
        db.query(BaseRoutineItem)
        .filter(BaseRoutineItem.base_routine_id == base.id)
        .order_by(BaseRoutineItem.day_index.asc(), BaseRoutineItem.order_index.asc())
        .all()
    )
    if not base_items:
        raise ValueError(f"La rutina base '{sheet_routine_id}' no tiene items (está vacía)")

    try:
        # Deactivate previous active routines
        db.query(ClientRoutine).filter(
            ClientRoutine.client_id == client_id,
            ClientRoutine.active.is_(True),
        ).update({"active": False}, synchronize_session=False)

        # Create snapshot header
        cr = ClientRoutine(
            client_id=client_id,
            base_routine_id=base.id,
            active=True,
        )
        db.add(cr)
        db.flush()

        # Copy items as independent snapshot
        for it in base_items:
            db.add(
                ClientRoutineItem(
                    client_routine_id=cr.id,
                    day_index=it.day_index,
                    order_index=it.order_index,
                    category=it.category,
                    exercise_key=it.exercise_key,
                    sets=it.sets,
                    reps=it.reps,
                    rest_seconds=it.rest_seconds,
                    weight_base_kg=it.weight_base_kg,
                    notes=it.notes,
                )
            )

        # Reset or create ClientPlanState
        st: ClientPlanState | None = (
            db.query(ClientPlanState)
            .filter(ClientPlanState.client_id == client_id)
            .first()
        )
        if st:
            st.next_base_day_index = 1
        else:
            db.add(
                ClientPlanState(
                    client_id=client_id,
                    next_base_day_index=1,
                    week_start_date=date.today(),  # schema requires NOT NULL; not used for logic
                )
            )

        db.commit()

        return AssignRoutineResult(
            client_routine_id=cr.id,
            client_id=client_id,
            base_routine_id=base.id,
            sheet_routine_id=base.sheet_routine_id,
            copied_items=len(base_items),
        )

    except Exception:
        db.rollback()
        raise
