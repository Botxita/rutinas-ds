"""Users router.

Roles canónicos de la API:
- CLIENTE
- ENTRENADOR
- COORDINADOR
- ADMINISTRADOR
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, validator
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db import models
from app.auth.deps import get_current_user

router = APIRouter(prefix="/users", tags=["users"])


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
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permisos insuficientes",
        )
    return role_norm


def _set_active_flag(user: models.User, value: bool) -> None:
    if hasattr(user, "is_active"):
        setattr(user, "is_active", value)
    elif hasattr(user, "active"):
        setattr(user, "active", value)


def _get_is_active(user: models.User) -> bool:
    return bool(getattr(user, "is_active", getattr(user, "active", True)))


def _full_name(user: models.User) -> str | None:
    return " ".join(
        [x for x in [user.first_name, user.last_name] if x]
    ).strip() or None


def _build_response(user: models.User, request: Request | None) -> dict:
    resp = {
        "id": str(user.id),
        "dni": user.dni,
        "role": _normalize_role(user.role),
        "is_active": _get_is_active(user),
    }
    try:
        if request is not None and bool(getattr(request.app, "debug", False)):
            resp["role_db"] = _role_to_str(user.role)
    except Exception:
        pass
    return resp


def _role_candidates_for_client() -> list[str]:
    return ["CLIENT", "client", "CLIENTE", "cliente", "User", "user"]


def _is_dni_unique_violation(msg_lower: str) -> bool:
    if "unique" in msg_lower and "dni" in msg_lower:
        return True
    if "duplicate" in msg_lower and "dni" in msg_lower:
        return True
    if "constraint failed" in msg_lower and "dni" in msg_lower:
        return True
    return False


def _is_role_constraint_violation(msg_lower: str) -> bool:
    if "role" not in msg_lower:
        return False
    if "check" in msg_lower and "constraint" in msg_lower:
        return True
    if "enum" in msg_lower:
        return True
    if "violates" in msg_lower and "constraint" in msg_lower:
        return True
    return False


_CLIENT_ROLE_VALUES = ("CLIENTE", "CLIENT", "cliente", "client", "User", "user")


# =============================================================================
# Schemas
# =============================================================================

class CreateClientRequest(BaseModel):
    dni: str = Field(..., min_length=7, max_length=9)
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)

    @validator("dni")
    def validate_dni(cls, v: str) -> str:
        v = (v or "").strip()
        if not v.isdigit():
            raise ValueError("DNI debe contener solo números")
        if not (7 <= len(v) <= 9):
            raise ValueError("DNI debe tener entre 7 y 9 dígitos")
        return v


class UpdateClientRequest(BaseModel):
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    dni: str | None = Field(default=None, min_length=7, max_length=9)

    @validator("dni")
    def validate_new_dni(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v.isdigit():
            raise ValueError("DNI debe contener solo números")
        if not (7 <= len(v) <= 9):
            raise ValueError("DNI debe tener entre 7 y 9 dígitos")
        return v


# =============================================================================
# POST /users/client  y  POST /users/clients  (alias)
# =============================================================================

@router.post("/client", status_code=status.HTTP_201_CREATED)
@router.post("/clients", status_code=status.HTTP_201_CREATED)
def create_client(
    data: CreateClientRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Crea un usuario CLIENTE. Solo ENTRENADOR / COORDINADOR / ADMINISTRADOR."""
    _require_role(current_user, {"ENTRENADOR", "COORDINADOR", "ADMINISTRADOR"})

    existing = db.query(models.User).filter(models.User.dni == data.dni).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="DNI ya registrado")

    last_err: Exception | None = None
    for role_value in _role_candidates_for_client():
        try:
            user = models.User(dni=data.dni, role=role_value)
            if data.first_name and hasattr(user, "first_name"):
                user.first_name = data.first_name.strip()
            if data.last_name and hasattr(user, "last_name"):
                user.last_name = data.last_name.strip()
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
            if _is_dni_unique_violation(low):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="DNI ya registrado")
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


# =============================================================================
# GET /users/clients
# =============================================================================

@router.get("/clients", status_code=status.HTTP_200_OK)
def list_clients(
    search: str | None = None,
    page: int = 1,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Lista paginada de clientes con estado de rutina activa."""
    _require_role(current_user, {"ENTRENADOR", "COORDINADOR", "ADMINISTRADOR"})

    q = db.query(models.User).filter(models.User.role.in_(_CLIENT_ROLE_VALUES))

    if search:
        term = search.strip()
        q = q.filter(
            or_(
                models.User.dni.ilike(f"%{term}%"),
                models.User.first_name.ilike(f"%{term}%"),
                models.User.last_name.ilike(f"%{term}%"),
            )
        )

    total = q.count()
    users = (
        q.order_by(models.User.last_name.asc(), models.User.first_name.asc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    if not users:
        return {"clients": [], "total": total, "page": page, "limit": limit}

    client_ids = [u.id for u in users]
    active_routines: dict = {}

    rows = (
        db.query(models.ClientRoutine, models.BaseRoutine)
        .join(models.BaseRoutine, models.ClientRoutine.base_routine_id == models.BaseRoutine.id)
        .filter(
            models.ClientRoutine.client_id.in_(client_ids),
            models.ClientRoutine.active.is_(True),
        )
        .all()
    )
    for cr, br in rows:
        active_routines[cr.client_id] = (cr, br)

    clients = []
    for u in users:
        row = active_routines.get(u.id)
        clients.append({
            "id": str(u.id),
            "dni": u.dni,
            "full_name": _full_name(u),
            "is_active": _get_is_active(u),
            "has_active_routine": row is not None,
            "routine_name": f"{row[1].sheet_routine_id} – {row[1].name}" if row else None,
        })

    return {"clients": clients, "total": total, "page": page, "limit": limit}


# =============================================================================
# GET /users/client/{dni}
# =============================================================================

@router.get("/client/{dni}", status_code=status.HTTP_200_OK)
def get_client_by_dni(
    dni: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Perfil completo de un cliente por DNI."""
    _require_role(current_user, {"ENTRENADOR", "COORDINADOR", "ADMINISTRADOR"})

    user = db.query(models.User).filter(models.User.dni == dni).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado")
    if _normalize_role(user.role) != "CLIENTE":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado")

    return {
        "id": str(user.id),
        "dni": user.dni,
        "full_name": _full_name(user),
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_active": _get_is_active(user),
    }


# =============================================================================
# PATCH /users/client/{dni}  — editar nombre / DNI
# =============================================================================

@router.patch("/client/{dni}", status_code=status.HTTP_200_OK)
def update_client(
    dni: str,
    data: UpdateClientRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Edita nombre y/o DNI de un cliente.
    PATCH semántico: solo actualiza los campos enviados.
    Si cambia el DNI, verifica que el nuevo no esté en uso.
    """
    _require_role(current_user, {"ENTRENADOR", "COORDINADOR", "ADMINISTRADOR"})

    user = db.query(models.User).filter(models.User.dni == dni).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado")
    if _normalize_role(user.role) != "CLIENTE":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado")

    if data.dni is not None and data.dni != user.dni:
        conflict = db.query(models.User).filter(models.User.dni == data.dni).first()
        if conflict:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ese DNI ya está registrado por otro usuario",
            )
        user.dni = data.dni

    if data.first_name is not None:
        user.first_name = data.first_name.strip() or None
    if data.last_name is not None:
        user.last_name = data.last_name.strip() or None

    try:
        db.commit()
        db.refresh(user)
    except IntegrityError as e:
        db.rollback()
        msg = str(e.orig) if getattr(e, "orig", None) is not None else str(e)
        if _is_dni_unique_violation(msg.lower()):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ese DNI ya está registrado por otro usuario",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar: {msg}",
        )

    return {
        "id": str(user.id),
        "dni": user.dni,
        "full_name": _full_name(user),
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_active": _get_is_active(user),
    }


# =============================================================================
# PATCH /users/client/{dni}/deactivate  — dar de baja (no borra datos)
# PATCH /users/client/{dni}/activate    — reactivar
# =============================================================================

@router.patch("/client/{dni}/deactivate", status_code=status.HTTP_200_OK)
def deactivate_client(
    dni: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Da de baja a un cliente (is_active = False). No borra datos ni historial."""
    _require_role(current_user, {"ENTRENADOR", "COORDINADOR", "ADMINISTRADOR"})

    user = db.query(models.User).filter(models.User.dni == dni).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado")
    if _normalize_role(user.role) != "CLIENTE":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado")

    _set_active_flag(user, False)
    db.commit()
    db.refresh(user)

    return {"dni": user.dni, "is_active": _get_is_active(user)}


@router.patch("/client/{dni}/activate", status_code=status.HTTP_200_OK)
def activate_client(
    dni: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Reactiva un cliente dado de baja."""
    _require_role(current_user, {"ENTRENADOR", "COORDINADOR", "ADMINISTRADOR"})

    user = db.query(models.User).filter(models.User.dni == dni).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado")
    if _normalize_role(user.role) != "CLIENTE":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado")

    _set_active_flag(user, True)
    db.commit()
    db.refresh(user)

    return {"dni": user.dni, "is_active": _get_is_active(user)}
