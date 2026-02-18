from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, validator


def _validate_dni_value(v: str) -> str:
    v = (v or "").strip()
    if not v.isdigit():
        raise ValueError("DNI debe contener solo números")
    if not (7 <= len(v) <= 9):
        raise ValueError("DNI debe tener entre 7 y 9 dígitos")
    return v


# -------------------------
# Requests
# -------------------------
class CreateActivePlanRequest(BaseModel):
    frequency: int = Field(..., ge=2, le=6)
    start_date: Optional[date] = None
    # Staff only (COACH/ADMIN)
    client_dni: Optional[str] = None

    @validator("client_dni")
    def validate_client_dni(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return _validate_dni_value(v)


class CompleteTodayRequest(BaseModel):
    kind: Literal["AUTO", "BASE", "EXTRA"] = Field(
        default="AUTO",
        description="AUTO usa la lógica del plan para decidir BASE/EXTRA",
    )
    workout_date: Optional[date] = Field(
        default=None,
        description="Fecha del entrenamiento. Si no se envía, usa hoy.",
    )
    label: Optional[str] = Field(default=None, description="Etiqueta libre (ej: 'Piernas', 'Torso', etc.)")
    intensity: Literal["LIGERA", "NORMAL", "FUERTE"] = Field(default="NORMAL", description="Intensidad percibida")


# -------------------------
# Responses
# -------------------------
class ActivePlanOut(BaseModel):
    plan_id: str
    client_id: str
    frequency: int
    start_date: Optional[str]
    status: str


class TodayOut(BaseModel):
    plan_id: str
    kind: Literal["BASE", "EXTRA"]
    n: int
    next_base_day_index: int
    bases_done_this_week: int
    week_start_date: date


class SessionOut(BaseModel):
    id: str
    session_index: int
    session_type: Literal["BASE", "EXTRA"]


class CompleteTodayOut(BaseModel):
    plan_id: str
    session: SessionOut
    today: dict  # lo dejamos así porque get_today_kind devuelve un dict estable ya usado en tu router


# Mantengo tus modelos previos por compatibilidad si ya los usás en otro lado
class TodayPlanOut(BaseModel):
    kind: Literal["BASE", "EXTRA"]
    n: int
    next_base_day_index: int
    bases_done_this_week: int
    week_start_date: date


class RegisterSessionIn(BaseModel):
    override_kind: Optional[Literal["BASE", "EXTRA"]] = None
    label: Optional[str] = None
    intensity: Optional[str] = None
