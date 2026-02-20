from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.core.plan_service import assign_base_routine_to_client
from app.db import models
from app.db.session import get_db

router = APIRouter(prefix="/routines", tags=["routines"])


# =============================================================================
# Helpers de rol
# =============================================================================

def _role_to_str(role) -> str:
    return role.value if hasattr(role, "value") else str(role)


def _normalize_role(role) -> str:
    r = _role_to_str(role).strip().upper()
    aliases = {
        "CLIENTE": "CLIENTE",
        "CLIENT": "CLIENTE",
        "USER": "CLIENTE",
        "ENTRENADOR": "ENTRENADOR",
        "COACH": "ENTRENADOR",
        "PROFE": "ENTRENADOR",
        "PROF": "ENTRENADOR",
        "TRAINER": "ENTRENADOR",
        "COORDINADOR": "COORDINADOR",
        "COORDINATOR": "COORDINADOR",
        "ADMINISTRADOR": "ADMINISTRADOR",
        "ADMIN": "ADMINISTRADOR",
    }
    return aliases.get(r, r)


def _require_role(current_user: models.User, allowed: set[str]) -> str:
    role_norm = _normalize_role(current_user.role)
    if role_norm not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permisos insuficientes")
    return role_norm


def _require_self_or_staff(current_user: models.User, dni: str) -> None:
    role = _normalize_role(current_user.role)
    if role == "CLIENTE":
        if (current_user.dni or "").strip() != (dni or "").strip():
            raise HTTPException(status_code=403, detail="Permisos insuficientes")
    else:
        _require_role(current_user, {"ENTRENADOR", "COORDINADOR", "ADMINISTRADOR"})


def _week_start(d: date) -> date:
    # Lunes como inicio de semana (0=lunes ... 6=domingo)
    return d.fromordinal(d.toordinal() - d.weekday())


# =============================================================================
# Schemas
# =============================================================================

class AssignRoutineRequest(BaseModel):
    client_dni: str = Field(..., min_length=7, max_length=9)
    sheet_routine_id: str = Field(..., min_length=2, max_length=64)

    @validator("client_dni")
    def validate_dni(cls, v: str) -> str:
        v = (v or "").strip()
        if not v.isdigit():
            raise ValueError("DNI debe contener solo números")
        return v

    @validator("sheet_routine_id")
    def normalize_sheet_id(cls, v: str) -> str:
        return (v or "").strip().upper()


class AssignRoutineResponse(BaseModel):
    client_routine_id: str
    client_id: str
    base_routine_id: str
    sheet_routine_id: str
    copied_items: int


class BaseRoutineResponse(BaseModel):
    id: str
    sheet_routine_id: str
    name: str
    version: int
    active: bool


class ClientRoutineItemResponse(BaseModel):
    day_index: int
    order_index: int
    category: str | None
    exercise_key: str
    sets: str | None
    reps: str | None
    rest_seconds: int | None
    weight_base_kg: float | None
    notes: str | None


class ClientRoutineResponse(BaseModel):
    client_routine_id: str
    sheet_routine_id: str
    name: str
    version: int
    items: list[ClientRoutineItemResponse]


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/base", response_model=list[BaseRoutineResponse])
def list_base_routines(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    role = _normalize_role(current_user.role)
    q = db.query(models.BaseRoutine)
    if role == "CLIENTE":
        q = q.filter(models.BaseRoutine.active.is_(True))
    routines = q.order_by(models.BaseRoutine.sheet_routine_id.asc()).all()
    return [
        BaseRoutineResponse(
            id=str(r.id),
            sheet_routine_id=r.sheet_routine_id,
            name=r.name,
            version=int(r.version),
            active=bool(r.active),
        )
        for r in routines
    ]


@router.post("/assign", response_model=AssignRoutineResponse, status_code=status.HTTP_201_CREATED)
def assign_routine_endpoint(
    data: AssignRoutineRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Asigna una rutina base a un cliente.
    - Solo ENTRENADOR / COORDINADOR / ADMINISTRADOR.
    """
    _require_role(current_user, {"ENTRENADOR", "COORDINADOR", "ADMINISTRADOR"})

    client = db.query(models.User).filter(models.User.dni == data.client_dni).first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    if _normalize_role(client.role) != "CLIENTE":
        raise HTTPException(status_code=400, detail="El DNI no corresponde a un CLIENTE")

    try:
        result = assign_base_routine_to_client(
            db=db,
            client_id=client.id,
            sheet_routine_id=data.sheet_routine_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error asignando rutina: {e}")

    return AssignRoutineResponse(
        client_routine_id=str(result.client_routine_id),
        client_id=str(result.client_id),
        base_routine_id=str(result.base_routine_id),
        sheet_routine_id=result.sheet_routine_id,
        copied_items=int(result.copied_items),
    )


@router.get("/client/{dni}", response_model=ClientRoutineResponse)
def get_active_routine_for_client_staff(
    dni: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_role(current_user, {"ENTRENADOR", "COORDINADOR", "ADMINISTRADOR"})

    client = db.query(models.User).filter(models.User.dni == dni).first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    cr = (
        db.query(models.ClientRoutine)
        .filter(models.ClientRoutine.client_id == client.id, models.ClientRoutine.active.is_(True))
        .order_by(models.ClientRoutine.assigned_at.desc())
        .first()
    )
    if not cr:
        raise HTTPException(status_code=404, detail="El cliente no tiene rutina activa")

    base = db.query(models.BaseRoutine).filter(models.BaseRoutine.id == cr.base_routine_id).first()

    items = (
        db.query(models.ClientRoutineItem)
        .filter(models.ClientRoutineItem.client_routine_id == cr.id)
        .order_by(models.ClientRoutineItem.day_index.asc(), models.ClientRoutineItem.order_index.asc())
        .all()
    )

    return ClientRoutineResponse(
        client_routine_id=str(cr.id),
        sheet_routine_id=base.sheet_routine_id if base else "",
        name=base.name if base else "",
        version=int(base.version) if base else 0,
        items=[
            ClientRoutineItemResponse(
                day_index=i.day_index,
                order_index=i.order_index,
                category=i.category,
                exercise_key=i.exercise_key,
                sets=i.sets,
                reps=i.reps,
                rest_seconds=i.rest_seconds,
                weight_base_kg=float(i.weight_base_kg) if i.weight_base_kg is not None else None,
                notes=i.notes,
            )
            for i in items
        ],
    )


@router.get("/me", response_model=ClientRoutineResponse)
def get_my_active_routine(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if _normalize_role(current_user.role) != "CLIENTE":
        raise HTTPException(status_code=403, detail="Solo disponible para CLIENTE")

    cr = (
        db.query(models.ClientRoutine)
        .filter(models.ClientRoutine.client_id == current_user.id, models.ClientRoutine.active.is_(True))
        .order_by(models.ClientRoutine.assigned_at.desc())
        .first()
    )
    if not cr:
        raise HTTPException(status_code=404, detail="No tenés rutina activa")

    base = db.query(models.BaseRoutine).filter(models.BaseRoutine.id == cr.base_routine_id).first()

    items = (
        db.query(models.ClientRoutineItem)
        .filter(models.ClientRoutineItem.client_routine_id == cr.id)
        .order_by(models.ClientRoutineItem.day_index.asc(), models.ClientRoutineItem.order_index.asc())
        .all()
    )

    return ClientRoutineResponse(
        client_routine_id=str(cr.id),
        sheet_routine_id=base.sheet_routine_id if base else "",
        name=base.name if base else "",
        version=int(base.version) if base else 0,
        items=[
            ClientRoutineItemResponse(
                day_index=i.day_index,
                order_index=i.order_index,
                category=i.category,
                exercise_key=i.exercise_key,
                sets=i.sets,
                reps=i.reps,
                rest_seconds=i.rest_seconds,
                weight_base_kg=float(i.weight_base_kg) if i.weight_base_kg is not None else None,
                notes=i.notes,
            )
            for i in items
        ],
    )


@router.post("/complete/{dni}")
def complete_training(
    dni: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_self_or_staff(current_user, dni)

    client = db.query(models.User).filter(models.User.dni == dni).first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    if _normalize_role(client.role) != "CLIENTE":
        raise HTTPException(status_code=400, detail="El DNI no corresponde a un CLIENTE")

    client_routine = (
        db.query(models.ClientRoutine)
        .filter(models.ClientRoutine.client_id == client.id, models.ClientRoutine.active.is_(True))
        .first()
    )
    if not client_routine:
        raise HTTPException(status_code=404, detail="No tiene rutina activa")

    plan_state = (
        db.query(models.ClientPlanState)
        .filter(models.ClientPlanState.client_id == client.id)
        .first()
    )
    if not plan_state:
        raise HTTPException(status_code=404, detail="No tiene estado de plan")

    today = date.today()

    # Reset semanal real por "inicio de semana" (lunes)
    if _week_start(plan_state.week_start_date) != _week_start(today):
        plan_state.bases_done_this_week = 0
        plan_state.week_start_date = today  # mantenemos tu campo como "fecha de referencia"

    day_to_complete = int(plan_state.next_base_day_index)

    log = models.ClientTrainingLog(
        client_id=client.id,
        client_routine_id=client_routine.id,
        day_index=day_to_complete,
        recorded_by=current_user.id,
    )
    db.add(log)

    # Max day en el snapshot asignado
    max_day = (
        db.query(func.max(models.ClientRoutineItem.day_index))
        .filter(models.ClientRoutineItem.client_routine_id == client_routine.id)
        .scalar()
    )
    max_day = int(max_day or 1)

    plan_state.next_base_day_index = 1 if day_to_complete >= max_day else (day_to_complete + 1)
    plan_state.bases_done_this_week = int(plan_state.bases_done_this_week or 0) + 1
    plan_state.updated_at = func.now()

    db.commit()

    return {
        "completed_day": day_to_complete,
        "next_day": int(plan_state.next_base_day_index),
        "bases_done_this_week": int(plan_state.bases_done_this_week),
    }


@router.get("/history/{dni}")
def get_training_history(
    dni: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_self_or_staff(current_user, dni)

    user = db.query(models.User).filter(models.User.dni == dni).first()
    if not user:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    logs = (
        db.query(models.ClientTrainingLog)
        .filter(models.ClientTrainingLog.client_id == user.id)
        .order_by(models.ClientTrainingLog.completed_at.desc())
        .all()
    )

    result: list[dict[str, Any]] = []

    for log in logs:
        routine = db.query(models.ClientRoutine).filter(models.ClientRoutine.id == log.client_routine_id).first()
        base = (
            db.query(models.BaseRoutine).filter(models.BaseRoutine.id == routine.base_routine_id).first()
            if routine else None
        )

        result.append({
            "completed_at": log.completed_at,
            "day_index": int(log.day_index),
            "client_routine_id": str(log.client_routine_id),
            "sheet_routine_id": base.sheet_routine_id if base else None,
            "routine_name": base.name if base else None,
            "recorded_by": str(log.recorded_by) if log.recorded_by else None,
        })

    return result


@router.get("/metrics/{dni}")
def get_training_metrics(
    dni: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_self_or_staff(current_user, dni)

    user = db.query(models.User).filter(models.User.dni == dni).first()
    if not user:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    logs = (
        db.query(models.ClientTrainingLog)
        .filter(models.ClientTrainingLog.client_id == user.id)
        .order_by(models.ClientTrainingLog.completed_at.asc())
        .all()
    )

    total_trainings = len(logs)

    plan_state = (
        db.query(models.ClientPlanState)
        .filter(models.ClientPlanState.client_id == user.id)
        .first()
    )
    trainings_this_week = int(plan_state.bases_done_this_week) if plan_state else 0

    if total_trainings == 0:
        return {
            "total_trainings": 0,
            "trainings_this_week": trainings_this_week,
            "current_streak": 0,
            "last_training_date": None,
            "average_per_week": 0,
        }

    # ====== FRECUENCIA (N días del ciclo) desde la rutina activa ======
    active_routine = (
        db.query(models.ClientRoutine)
        .filter(models.ClientRoutine.client_id == user.id, models.ClientRoutine.active.is_(True))
        .order_by(models.ClientRoutine.assigned_at.desc())
        .first()
    )

    frequency = 1
    if active_routine:
        # Contamos días distintos del snapshot (robusto aunque base cambie)
        frequency = (
            db.query(models.ClientRoutineItem.day_index)
            .filter(models.ClientRoutineItem.client_routine_id == active_routine.id)
            .distinct()
            .count()
        ) or 1

    # ====== RACHA CÍCLICA: 1..N..1..N ======
    current_streak = 0
    expected_day = 1

    for log in logs:
        di = int(log.day_index)
        if di == expected_day:
            current_streak += 1
            expected_day = 1 if expected_day >= frequency else (expected_day + 1)
        else:
            # se corta: nueva racha arrancando en ese día
            current_streak = 1
            # el siguiente esperado es el próximo en el ciclo
            expected_day = 1 if di >= frequency else (di + 1)

    last_training_date = logs[-1].completed_at

    # ====== PROMEDIO SEMANAL ======
    first_date = logs[0].completed_at.date()
    last_date = logs[-1].completed_at.date()
    total_days = (last_date - first_date).days + 1
    total_weeks = max(total_days / 7, 1)

    average_per_week = round(total_trainings / total_weeks, 2)

    return {
        "total_trainings": total_trainings,
        "trainings_this_week": trainings_this_week,
        "current_streak": current_streak,
        "last_training_date": last_training_date,
        "average_per_week": average_per_week,
        "cycle_frequency": int(frequency),
    }