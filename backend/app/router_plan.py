from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db import models
from app.auth.deps import get_current_user
from app.core.plan_service import (
    get_current_training_day,
    complete_training,
)

router = APIRouter(prefix="/plan", tags=["plan"])


# =============================================================================
# Helpers
# =============================================================================

def _role(user: models.User) -> str:
    raw = (getattr(user, "role", "") or "").strip().upper()
    ROLE_MAP = {
        "CLIENT": "CLIENTE",
        "CLIENTE": "CLIENTE",
        "PROFE": "ENTRENADOR",
        "ENTRENADOR": "ENTRENADOR",
        "COORDINADOR": "COORDINADOR",
        "ADMIN": "ADMINISTRADOR",
        "ADMINISTRADOR": "ADMINISTRADOR",
    }
    return ROLE_MAP.get(raw, raw)


def _require_role(user: models.User, allowed: tuple[str, ...]) -> None:
    if _role(user) not in allowed:
        raise HTTPException(status_code=403, detail="Permisos insuficientes")


def _get_active_plan_for_client(db: Session, client_user_id: UUID) -> models.RoutinePlan | None:
    return (
        db.query(models.RoutinePlan)
        .filter(
            models.RoutinePlan.client_id == client_user_id,
            models.RoutinePlan.status == "ACTIVE",
        )
        .order_by(models.RoutinePlan.start_date.desc())
        .first()
    )


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/today")
def get_today_client(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_role(current_user, ("CLIENTE",))

    plan = _get_active_plan_for_client(db, current_user.id)
    if not plan:
        raise HTTPException(status_code=404, detail="No hay plan ACTIVE para este cliente")

    try:
        base_day_index = get_current_training_day(db, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "plan_id": str(plan.id),
        "kind": "BASE",
        "base_day_index": base_day_index,
    }


@router.post("/today/complete", status_code=status.HTTP_201_CREATED)
def complete_today_client(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_role(current_user, ("CLIENTE",))

    plan = _get_active_plan_for_client(db, current_user.id)
    if not plan:
        raise HTTPException(status_code=404, detail="No hay plan ACTIVE para este cliente")

    try:
        current_day = get_current_training_day(db, current_user.id)
        new_day = complete_training(db, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    session = models.WorkoutSession(
        plan_id=plan.id,
        session_index=1,  # opcional: si querés mantener histórico real lo ajustamos luego
        session_type="BASE",
        base_day_index=current_day,
        label=None,
        intensity="NORMAL",
        recorded_by_user_id=current_user.id,
    )

    db.add(session)
    db.commit()
    db.refresh(session)

    return {
        "plan_id": str(plan.id),
        "session": {
            "id": str(session.id),
            "base_day_index": current_day,
        },
        "next_base_day_index": new_day,
    }