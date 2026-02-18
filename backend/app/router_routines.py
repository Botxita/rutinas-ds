from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, validator
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db import models
from app.auth.deps import get_current_user

router = APIRouter(prefix="/routines", tags=["routines"])


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
            version=r.version,
            active=bool(r.active),
        )
        for r in routines
    ]


@router.post("/assign", response_model=AssignRoutineResponse, status_code=status.HTTP_201_CREATED)
def assign_base_routine_to_client(
    data: AssignRoutineRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_role(current_user, {"ENTRENADOR", "COORDINADOR", "ADMINISTRADOR"})

    client = db.query(models.User).filter(models.User.dni == data.client_dni).first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    if _normalize_role(client.role) != "CLIENTE":
        raise HTTPException(status_code=400, detail="El DNI no corresponde a un CLIENTE")

    base = (
        db.query(models.BaseRoutine)
        .filter(models.BaseRoutine.sheet_routine_id == data.sheet_routine_id)
        .first()
    )
    if not base:
        raise HTTPException(status_code=404, detail="Rutina base no encontrada")

    base_items = (
        db.query(models.BaseRoutineItem)
        .filter(models.BaseRoutineItem.base_routine_id == base.id)
        .order_by(models.BaseRoutineItem.day_index.asc(), models.BaseRoutineItem.order_index.asc())
        .all()
    )
    if not base_items:
        raise HTTPException(status_code=400, detail="La rutina base no tiene items (vacía)")

    try:
        # 1) Desactivar rutinas previas
        db.query(models.ClientRoutine).filter(
            models.ClientRoutine.client_id == client.id,
            models.ClientRoutine.active.is_(True),
        ).update({"active": False})

        # 2) Crear cabecera nueva
        cr = models.ClientRoutine(client_id=client.id, base_routine_id=base.id, active=True)
        db.add(cr)
        db.flush()

        # 3) Copiar items
        copied = 0
        for it in base_items:
            db.add(
                models.ClientRoutineItem(
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
            copied += 1

        db.commit()

        return AssignRoutineResponse(
            client_routine_id=str(cr.id),
            client_id=str(client.id),
            base_routine_id=str(base.id),
            sheet_routine_id=base.sheet_routine_id,
            copied_items=copied,
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error asignando rutina: {e}")


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
