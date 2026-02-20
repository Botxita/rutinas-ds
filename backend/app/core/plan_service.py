from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.date_utils import week_monday
from app.db.models import (
    BaseRoutine,
    BaseRoutineItem,
    ClientPlanConfigHistory,
    ClientPlanState,
    ClientRoutine,
    ClientRoutineItem,
)

DEFAULT_BASE_DAYS = 3  # fallback si no hay config para el cliente


# =============================================================================
# Helpers internos de estado semanal
# =============================================================================

def get_effective_base_days(db: Session, client_id, day: date) -> int:
    row = (
        db.query(ClientPlanConfigHistory)
        .filter(
            ClientPlanConfigHistory.client_id == client_id,
            ClientPlanConfigHistory.effective_from_date <= day,
        )
        .order_by(desc(ClientPlanConfigHistory.effective_from_date))
        .first()
    )
    return row.base_days_per_week if row else DEFAULT_BASE_DAYS


def get_or_init_state(db: Session, client_id, day: date) -> ClientPlanState:
    monday = week_monday(day)
    st = db.query(ClientPlanState).filter(ClientPlanState.client_id == client_id).first()

    if not st:
        st = ClientPlanState(
            client_id=client_id,
            next_base_day_index=1,
            week_start_date=monday,
            bases_done_this_week=0,
        )
        db.add(st)
        db.flush()
        return st

    # reset semanal
    if st.week_start_date != monday:
        st.week_start_date = monday
        st.bases_done_this_week = 0
        if st.next_base_day_index is None:
            st.next_base_day_index = 1

    return st


def _normalize_next_day(next_day: int, n: int) -> int:
    if not next_day or next_day < 1 or next_day > n:
        return 1
    return next_day


def get_today_kind(db: Session, client_id, day: date) -> dict:
    n = get_effective_base_days(db, client_id, day)
    st = get_or_init_state(db, client_id, day)

    st.next_base_day_index = _normalize_next_day(st.next_base_day_index, n)
    kind = "BASE" if st.bases_done_this_week < n else "EXTRA"

    return {
        "kind": kind,
        "n": n,
        "next_base_day_index": st.next_base_day_index,
        "bases_done_this_week": st.bases_done_this_week,
        "week_start_date": st.week_start_date,
    }


def ensure_state_row(db: Session, client_id, day: date) -> ClientPlanState:
    """Garantiza que exista el estado del cliente (ClientPlanState) y aplica reset semanal si corresponde."""
    return get_or_init_state(db, client_id, day)


# =============================================================================
# Asignación de rutina base a cliente
# =============================================================================

class AssignRoutineResult:
    """Resultado de assign_base_routine_to_client. Usado por el router para armar la response."""

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
    Asigna una rutina base a un cliente creando un snapshot físico completo.

    Contrato:
    - Busca BaseRoutine por sheet_routine_id con active=True.
    - Desactiva cualquier ClientRoutine ACTIVE previa del cliente.
    - Crea nuevo ClientRoutine (snapshot cabecera) con active=True.
    - Copia físicamente todos los BaseRoutineItem a ClientRoutineItem.
    - Crea o reinicializa ClientPlanState:
        next_base_day_index = 1
        bases_done_this_week = 0
        week_start_date = date.today()  (NOT NULL en el modelo; se resetea al asignar)
    - Commit único al final. Rollback ante cualquier excepción.

    Raises:
        ValueError: si la rutina base no existe, no está activa o no tiene items.
        RuntimeError: ante errores de DB inesperados.
    """
    # ------------------------------------------------------------------
    # 1. Buscar rutina base activa
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # 2. Verificar que tiene items
    # ------------------------------------------------------------------
    base_items: list[BaseRoutineItem] = (
        db.query(BaseRoutineItem)
        .filter(BaseRoutineItem.base_routine_id == base.id)
        .order_by(BaseRoutineItem.day_index.asc(), BaseRoutineItem.order_index.asc())
        .all()
    )
    if not base_items:
        raise ValueError(f"La rutina base '{sheet_routine_id}' no tiene items (está vacía)")

    # ------------------------------------------------------------------
    # Transacción
    # ------------------------------------------------------------------
    try:
        # 3. Desactivar ClientRoutines ACTIVE previas del cliente
        db.query(ClientRoutine).filter(
            ClientRoutine.client_id == client_id,
            ClientRoutine.active.is_(True),
        ).update({"active": False}, synchronize_session=False)

        # 4. Crear snapshot cabecera
        cr = ClientRoutine(
            client_id=client_id,
            base_routine_id=base.id,
            active=True,
        )
        db.add(cr)
        db.flush()  # necesario para obtener cr.id antes de insertar items

        # 5. Copiar items físicamente (snapshot independiente del catálogo)
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

        # 6. Crear o reinicializar ClientPlanState
        #    Nota: week_start_date es NOT NULL en el modelo, por lo que se usa
        #    date.today() como valor de reset en lugar de None.
        today = date.today()
        st: ClientPlanState | None = (
            db.query(ClientPlanState)
            .filter(ClientPlanState.client_id == client_id)
            .first()
        )
        if st:
            # Reinicializar: nueva rutina = empezar desde el día 1
            st.next_base_day_index = 1
            st.bases_done_this_week = 0
            st.week_start_date = today
        else:
            db.add(
                ClientPlanState(
                    client_id=client_id,
                    next_base_day_index=1,
                    bases_done_this_week=0,
                    week_start_date=today,
                )
            )

        # 7. Commit único
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
