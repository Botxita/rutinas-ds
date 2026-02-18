"""Users router.

Etapa 4: Alta de clientes.

Características:
- Permisos COACH/ADMIN robustos (case-insensitive + aliases comunes).
- DNI único (reporta 409 Conflict).
- Alta de cliente robusta ante distintos constraints de role en la DB.
  Algunas bases usan roles en minúsculas (client/coach/admin) o en español (cliente/profe).
  Este endpoint intenta varias opciones de role y usa la primera que pase el constraint.

Roles canónicos de la API (oficiales):
- CLIENTE
- ENTRENADOR
- COORDINADOR
- ADMINISTRADOR
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db import models
from app.auth.deps import get_current_user

router = APIRouter(prefix="/users", tags=["users"])


class CreateClientRequest(BaseModel):
    dni: str = Field(..., min_length=7, max_length=9)

    @validator("dni")
    def validate_dni(cls, v: str) -> str:
        v = (v or "").strip()
        if not v.isdigit():
            raise ValueError("DNI debe contener solo números")
        if not (7 <= len(v) <= 9):
            raise ValueError("DNI debe tener entre 7 y 9 dígitos")
        return v


def _role_to_str(role) -> str:
    # Soporta Enum (role.value) o string
    return role.value if hasattr(role, "value") else str(role)


def _normalize_role(role) -> str:
    """Normaliza roles alternativos a los roles canónicos (API)."""
    r = _role_to_str(role).strip().upper()

    aliases = {
        # Cliente
        "CLIENTE": "CLIENTE",
        "CLIENT": "CLIENTE",
        "USER": "CLIENTE",
        # Entrenador
        "ENTRENADOR": "ENTRENADOR",
        "COACH": "ENTRENADOR",
        "PROFE": "ENTRENADOR",
        "PROF": "ENTRENADOR",
        "TRAINER": "ENTRENADOR",
        # Coordinador
        "COORDINADOR": "COORDINADOR",
        "COORDINATOR": "COORDINADOR",
        # Admin
        "ADMINISTRADOR": "ADMINISTRADOR",
        "ADMIN": "ADMINISTRADOR",
    }
    return aliases.get(r, r)


def _require_role(current_user: models.User, allowed: set[str]) -> str:
    role_norm = _normalize_role(current_user.role)
    if role_norm not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permisos insuficientes",
        )
    return role_norm


def _set_active_flag(user: models.User, value: bool = True) -> None:
    """Compatibilidad con esquemas: algunas DB usan active, otras is_active."""
    if hasattr(user, "active"):
        setattr(user, "active", value)
    elif hasattr(user, "is_active"):
        setattr(user, "is_active", value)


def _role_candidates_for_client() -> list[str]:
    """Candidatos de valor a persistir en la columna role para un cliente.

    NOTA: la normalización es solo para permisos/response.
    Acá se prueban variantes porque la DB puede tener CHECK/ENUM distinto.
    """
    return [
        "CLIENT",
        "client",
        "CLIENTE",
        "cliente",
        "User",
        "user",
    ]


def _is_dni_unique_violation(msg_lower: str) -> bool:
    # Cubre Postgres y otros drivers.
    # Ejemplos:
    # - 'duplicate key value violates unique constraint ...'
    # - 'UNIQUE constraint failed: users.dni'
    if "unique" in msg_lower and "dni" in msg_lower:
        return True
    if "duplicate" in msg_lower and "dni" in msg_lower:
        return True
    if "constraint failed" in msg_lower and "dni" in msg_lower:
        return True
    return False


def _is_role_constraint_violation(msg_lower: str) -> bool:
    # Violación de check/enum sobre role -> continuar
    if "role" not in msg_lower:
        return False
    if "check" in msg_lower and "constraint" in msg_lower:
        return True
    if "enum" in msg_lower:
        return True
    if "violates" in msg_lower and "constraint" in msg_lower:
        return True
    return False


def _build_response(user: models.User, request: Request | None) -> dict:
    resp = {
        "id": str(user.id),
        "dni": user.dni,
        # devolvemos role canónico para la API
        "role": _normalize_role(user.role),
        "active": getattr(user, "active", getattr(user, "is_active", True)),
    }

    # Solo devolvemos role_db si la app está en debug (FastAPI(debug=True))
    try:
        if request is not None and bool(getattr(request.app, "debug", False)):
            resp["role_db"] = _role_to_str(user.role)
    except Exception:
        pass

    return resp


# Alias: mantenemos /client (no rompe nada) y sumamos /clients (más prolijo)
@router.post("/client", status_code=status.HTTP_201_CREATED)
@router.post("/clients", status_code=status.HTTP_201_CREATED)
def create_client(
    data: CreateClientRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Crea un usuario CLIENTE.

    Reglas:
    - Solo STAFF (ENTRENADOR/COORDINADOR/ADMINISTRADOR).
    - DNI único.
    - Alta robusta ante distintos constraints de role.
    """

    _require_role(current_user, {"ENTRENADOR", "COORDINADOR", "ADMINISTRADOR"})

    existing = db.query(models.User).filter(models.User.dni == data.dni).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="DNI ya registrado")

    last_err: Exception | None = None
    for role_value in _role_candidates_for_client():
        try:
            user = models.User(dni=data.dni, role=role_value)
            _set_active_flag(user, True)

            db.add(user)
            db.commit()
            db.refresh(user)

            return _build_response(user, request)

        except IntegrityError as e:
            db.rollback()
            last_err = e

            msg = str(e.orig) if getattr(e, "orig", None) is not None else str(e)
            low = msg.lower()

            # DNI unique (race condition o pre-check bypass)
            if _is_dni_unique_violation(low):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="DNI ya registrado")

            # Violación de role -> probar siguiente candidato
            if _is_role_constraint_violation(low):
                continue

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error al crear usuario (DB): {msg}",
            )

        except TypeError as e:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error de modelo User: {e}",
            )

    detail = "No se pudo crear el usuario: constraint de role desconocido en la DB"
    if last_err is not None:
        detail += f". Último error: {last_err}"

    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)
