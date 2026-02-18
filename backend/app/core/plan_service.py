from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.date_utils import week_monday
from app.db.models import ClientPlanConfigHistory, ClientPlanState

DEFAULT_BASE_DAYS = 3  # fallback si no hay config para el cliente

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

