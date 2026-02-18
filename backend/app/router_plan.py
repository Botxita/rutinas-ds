from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db import models
from app.auth.deps import get_current_user
from app.core.plan_service import ensure_state_row, get_today_kind
from app.core.schemas_plan import (
    CreateActivePlanRequest,
    CompleteTodayRequest,
    ActivePlanOut,
)

router = APIRouter(prefix="/plan", tags=["plan"])


# =============================================================================
# Roles / Helpers
# =============================================================================
def _role(user: models.User) -> str:
    """DB role normalized. Canonical (oficial):

    - CLIENTE
    - ENTRENADOR
    - COORDINADOR
    - ADMINISTRADOR

    Se mantiene compatibilidad con roles viejos/ingles.
    """
    raw = (getattr(user, "role", "") or "").strip()
    raw_up = raw.upper()

    ROLE_MAP = {
        # Clientes
        "CLIENT": "CLIENTE",
        "CLIENTE": "CLIENTE",
        # Entrenador
        "COACH": "ENTRENADOR",
        "PROFE": "ENTRENADOR",
        "PROF": "ENTRENADOR",
        "ENTRENADOR": "ENTRENADOR",
        # Coordinador
        "COORDINATOR": "COORDINADOR",
        "COORDINADOR": "COORDINADOR",
        # Admin
        "ADMIN": "ADMINISTRADOR",
        "ADMINISTRADOR": "ADMINISTRADOR",
    }
    return ROLE_MAP.get(raw_up, raw_up)


def _require_role(user: models.User, allowed: tuple[str, ...]) -> None:
    if _role(user) not in allowed:
        raise HTTPException(status_code=403, detail="Permisos insuficientes")


def _validate_dni_or_422(dni: str) -> str:
    dni_norm = (dni or "").strip()
    if not dni_norm.isdigit():
        raise HTTPException(status_code=422, detail="DNI debe contener solo números")
    if not (7 <= len(dni_norm) <= 9):
        raise HTTPException(status_code=422, detail="DNI debe tener entre 7 y 9 dígitos")
    return dni_norm


def _get_user_by_dni(db: Session, dni: str) -> models.User:
    dni_norm = _validate_dni_or_422(dni)
    user = db.query(models.User).filter(models.User.dni == dni_norm).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado (DNI)")
    return user


def _get_client_user_by_dni(db: Session, dni: str) -> models.User:
    user = _get_user_by_dni(db, dni)
    if _role(user) != "CLIENTE":
        raise HTTPException(status_code=400, detail="El DNI no corresponde a un CLIENTE")
    return user


def _get_active_plan_for_client(db: Session, client_user_id: UUID) -> models.RoutinePlan | None:
    return (
        db.query(models.RoutinePlan)
        .filter(models.RoutinePlan.client_id == client_user_id, models.RoutinePlan.status == "ACTIVE")
        .order_by(models.RoutinePlan.start_date.desc())
        .first()
    )


def _ensure_plan_access(plan: models.RoutinePlan, current_user: models.User) -> None:
    # CLIENTE: solo su propio plan
    if _role(current_user) == "CLIENTE":
        # Preferimos comparar por DNI porque el sistema usa DNI como identificador funcional.
        # (En algunos seeds viejos el plan podía tener client_id en vez de client_dni.)
        if getattr(plan, "client_dni", None):
            if str(plan.client_dni) != str(current_user.dni):
                raise HTTPException(status_code=403, detail="No tenés permiso para acceder a este plan")
        else:
            if str(getattr(plan, "client_id", "")) != str(current_user.id):
                raise HTTPException(status_code=403, detail="No tenés permiso para acceder a este plan")


def _next_session_index(db: Session, plan_id: UUID) -> int:
    max_idx = (
        db.query(func.max(models.WorkoutSession.session_index))
        .filter(models.WorkoutSession.plan_id == plan_id)
        .scalar()
    )
    return int(max_idx or 0) + 1


def _archive_existing_active_plans(db: Session, client_user_id: UUID) -> int:
    """
    Archive old ACTIVE plans instead of deleting (safer + avoids flush ordering issues).
    Returns number of rows affected.
    """
    q = (
        db.query(models.RoutinePlan)
        .filter(models.RoutinePlan.client_id == client_user_id, models.RoutinePlan.status == "ACTIVE")
    )
    updated = q.update({models.RoutinePlan.status: "INACTIVE"}, synchronize_session=False)
    return int(updated or 0)


# =============================================================================
# Endpoints
# =============================================================================

# -------------------------
# Aliases “me” (CLIENTE)
# -------------------------
@router.get("/me", response_model=ActivePlanOut)
def get_active_plan_me(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # alias de /active para CLIENT
    return get_active_plan_client(db=db, current_user=current_user)


@router.get("/me/today")
def get_today_me(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # alias de /today para CLIENT
    return get_today_client(db=db, current_user=current_user)


@router.post("/me/today", status_code=status.HTTP_201_CREATED)
def complete_today_me(
    data: CompleteTodayRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # alias de /today POST para CLIENT
    return complete_today_client(data=data, db=db, current_user=current_user)


# -------------------------
# Endpoints existentes
# -------------------------
@router.get("/active", response_model=ActivePlanOut)
def get_active_plan_client(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_role(current_user, ("CLIENTE",))
    plan = _get_active_plan_for_client(db, current_user.id)
    if not plan:
        raise HTTPException(status_code=404, detail="No hay plan ACTIVE para este cliente")

    return {
        "plan_id": str(plan.id),
        "client_id": str(plan.client_id),
        "frequency": plan.frequency,
        "start_date": str(plan.start_date) if plan.start_date else None,
        "status": plan.status,
    }


@router.get("/active/by-dni", response_model=ActivePlanOut)
def get_active_plan_by_dni(
    client_dni: str = Query(..., description="DNI del cliente (solo ENTRENADOR/COORDINADOR/ADMINISTRADOR)"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_role(current_user, ("ENTRENADOR", "COORDINADOR", "ADMINISTRADOR"))
    client_user = _get_client_user_by_dni(db, client_dni)

    plan = _get_active_plan_for_client(db, client_user.id)
    if not plan:
        raise HTTPException(status_code=404, detail="No hay plan ACTIVE para este cliente")

    return {
        "plan_id": str(plan.id),
        "client_id": str(plan.client_id),
        "frequency": plan.frequency,
        "start_date": str(plan.start_date) if plan.start_date else None,
        "status": plan.status,
    }


@router.post("/active", status_code=status.HTTP_201_CREATED)
def create_active_plan(
    data: CreateActivePlanRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    role = _role(current_user)

    # Who is the plan for?
    if role == "CLIENTE":
        client_user = current_user
    else:
        _require_role(current_user, ("ENTRENADOR", "COORDINADOR", "ADMINISTRADOR"))
        if not data.client_dni:
            raise HTTPException(status_code=422, detail="client_dni es requerido para ENTRENADOR/COORDINADOR/ADMINISTRADOR")
        client_user = _get_client_user_by_dni(db, data.client_dni)

    start = data.start_date or date.today()

    # 1) Archive old ACTIVE plans
    _archive_existing_active_plans(db, client_user.id)

    # 2) Create new plan
    plan = models.RoutinePlan(
        client_id=client_user.id,
        status="ACTIVE",
        frequency=data.frequency,
        start_date=start,
    )
    db.add(plan)
    db.flush()  # get plan.id

    # 3) Config history
    hist = models.ClientPlanConfigHistory(
        client_id=client_user.id,
        effective_from_date=start,
        base_days_per_week=data.frequency,
    )
    db.add(hist)

    # 4) Reset/ensure plan state
    ensure_state_row(db, client_user.id, start)

    db.commit()
    db.refresh(plan)

    return {
        "plan_id": str(plan.id),
        "client_dni": client_user.dni,
        "client_id": str(client_user.id),
        "frequency": plan.frequency,
        "start_date": str(plan.start_date),
        "status": plan.status,
    }


@router.get("/today")
def get_today_client(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_role(current_user, ("CLIENTE",))
    plan = _get_active_plan_for_client(db, current_user.id)
    if not plan:
        raise HTTPException(status_code=404, detail="No hay plan ACTIVE para este cliente")

    today = date.today()
    ensure_state_row(db, plan.client_id, today)
    info = get_today_kind(db, plan.client_id, today)
    return {"plan_id": str(plan.id), **info}


@router.get("/today/by-dni")
def get_today_by_dni(
    client_dni: str = Query(..., description="DNI del cliente (solo ENTRENADOR/COORDINADOR/ADMINISTRADOR)"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_role(current_user, ("ENTRENADOR", "COORDINADOR", "ADMINISTRADOR"))
    client_user = _get_client_user_by_dni(db, client_dni)

    plan = _get_active_plan_for_client(db, client_user.id)
    if not plan:
        raise HTTPException(status_code=404, detail="No hay plan ACTIVE para este cliente")

    today = date.today()
    ensure_state_row(db, plan.client_id, today)
    info = get_today_kind(db, plan.client_id, today)
    return {"plan_id": str(plan.id), **info}


@router.post("/today", status_code=status.HTTP_201_CREATED)
def complete_today_client(
    data: CompleteTodayRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_role(current_user, ("CLIENTE",))
    return _complete_today_impl(data, db, current_user, current_user)


@router.post("/today/by-dni", status_code=status.HTTP_201_CREATED)
def complete_today_by_dni(
    data: CompleteTodayRequest,
    client_dni: str = Query(..., description="DNI del cliente (solo ENTRENADOR/COORDINADOR/ADMINISTRADOR)"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_role(current_user, ("ENTRENADOR", "COORDINADOR", "ADMINISTRADOR"))
    client_user = _get_client_user_by_dni(db, client_dni)
    return _complete_today_impl(data, db, current_user, client_user)


def _complete_today_impl(
    data: CompleteTodayRequest,
    db: Session,
    current_user: models.User,
    client_user: models.User,
):
    plan = _get_active_plan_for_client(db, client_user.id)
    if not plan:
        raise HTTPException(status_code=404, detail="No hay plan ACTIVE para este cliente")

    _ensure_plan_access(plan, current_user)

    workout_day = data.workout_date or date.today()

    ensure_state_row(db, plan.client_id, workout_day)
    today_info = get_today_kind(db, plan.client_id, workout_day)
    today_kind = str(today_info.get("kind"))

    # Decide BASE/EXTRA
    if data.kind == "AUTO":
        session_type = "BASE" if today_kind == "BASE" else "EXTRA"
    elif data.kind == "BASE":
        if today_kind != "BASE":
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Hoy no corresponde BASE (kind={today_kind}). "
                    "Usá kind=EXTRA si querés registrar un extra."
                ),
            )
        session_type = "BASE"
    else:
        session_type = "EXTRA"

    # base_day_index for BASE
    base_day_index = None
    if session_type == "BASE":
        st = db.query(models.ClientPlanState).filter(models.ClientPlanState.client_id == plan.client_id).first()
        if st:
            nxt = int(st.next_base_day_index or 1)
            base_day_index = nxt if nxt >= 1 else 1
        else:
            base_day_index = 1

    session = models.WorkoutSession(
        plan_id=plan.id,
        session_index=_next_session_index(db, plan.id),
        session_type=session_type,
        base_day_index=base_day_index,
        label=data.label,
        intensity=data.intensity,
        week_start_date=today_info.get("week_start_date"),
        recorded_by_user_id=current_user.id,
    )
    db.add(session)

    # Advance state if BASE
    st = db.query(models.ClientPlanState).filter(models.ClientPlanState.client_id == plan.client_id).first()
    if st and session_type == "BASE":
        st.bases_done_this_week = int(st.bases_done_this_week or 0) + 1

        nxt = int(st.next_base_day_index or 1)
        nxt = (nxt if nxt >= 1 else 1) + 1

        freq = int(plan.frequency or 2)
        if nxt > freq:
            nxt = 1
        st.next_base_day_index = nxt

    db.commit()
    db.refresh(session)

    ensure_state_row(db, plan.client_id, workout_day)
    today_after = get_today_kind(db, plan.client_id, workout_day)

    return {
        "plan_id": str(plan.id),
        "session": {
            "id": str(session.id),
            "session_index": session.session_index,
            "session_type": session.session_type,
        },
        "today": today_after,
    }
