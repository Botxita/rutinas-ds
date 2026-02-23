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
@router.get("/clients", status_code=200)
def list_clients(
    search: str = None,
    page: int = 1,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Lista de clientes con estado de rutina activa.
    Solo ENTRENADOR / COORDINADOR / ADMINISTRADOR.
    """
    _require_role(current_user, {"ENTRENADOR", "COORDINADOR", "ADMINISTRADOR"})

    q = db.query(models.User).filter(
        models.User.role.in_(["CLIENTE", "CLIENT", "cliente", "client"])
    )

    if search:
        term = search.strip()
        q = q.filter(
            models.User.dni.ilike(f"%{term}%") |
            models.User.first_name.ilike(f"%{term}%") |
            models.User.last_name.ilike(f"%{term}%")
        )

    total = q.count()
    users = q.order_by(models.User.last_name.asc(), models.User.first_name.asc()) \
             .offset((page - 1) * limit) \
             .limit(limit) \
             .all()

    clients = []
    for u in users:
        # Buscar rutina activa
        active_routine = (
            db.query(models.ClientRoutine)
            .filter(
                models.ClientRoutine.client_id == u.id,
                models.ClientRoutine.active.is_(True),
            )
            .join(models.BaseRoutine, models.ClientRoutine.base_routine_id == models.BaseRoutine.id)
            .add_entity(models.BaseRoutine)
            .first()
        )

        has_active = active_routine is not None
        routine_name = None
        if active_routine:
            _, base = active_routine
            routine_name = f"{base.sheet_routine_id} – {base.name}"

        full_name = " ".join(
            [x for x in [u.first_name, u.last_name] if x]
        ).strip() or None

        clients.append({
            "id": str(u.id),
            "dni": u.dni,
            "full_name": full_name,
            "is_active": bool(u.is_active),
            "has_active_routine": has_active,
            "routine_name": routine_name,
        })

    return {
        "clients": clients,
        "total": total,
        "page": page,
    }

@router.get("/client/{dni}", status_code=200)
def get_client_by_dni(
    dni: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Perfil básico de un cliente por DNI.
    Solo ENTRENADOR / COORDINADOR / ADMINISTRADOR.
    """
    _require_role(current_user, {"ENTRENADOR", "COORDINADOR", "ADMINISTRADOR"})

    user = db.query(models.User).filter(models.User.dni == dni).first()

    if not user:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    if _normalize_role(user.role) != "CLIENTE":
        raise HTTPException(status_code=400, detail="El DNI no corresponde a un CLIENTE")

    full_name = " ".join(
        [x for x in [user.first_name, user.last_name] if x]
    ).strip() or None

    return {
        "id": str(user.id),
        "dni": user.dni,
        "full_name": full_name,
        "is_active": bool(user.is_active),
    }

 # =============================================================================
# Helpers internos de rutinas (evita N+1 en lista de clientes)
# =============================================================================

def _get_active_routine_for_client_id(
    db: Session,
    client_id,
) -> tuple[models.ClientRoutine, models.BaseRoutine] | None:
    """Devuelve (ClientRoutine, BaseRoutine) activa del cliente, o None.

    Centralizado aquí para facilitar futura migración de active -> status.
    """
    row = (
        db.query(models.ClientRoutine, models.BaseRoutine)
        .join(models.BaseRoutine, models.ClientRoutine.base_routine_id == models.BaseRoutine.id)
        .filter(
            models.ClientRoutine.client_id == client_id,
            models.ClientRoutine.active.is_(True),
        )
        .first()
    )
    return row  # (ClientRoutine, BaseRoutine) o None


def _full_name(user: models.User) -> str | None:
    return " ".join(
        [x for x in [user.first_name, user.last_name] if x]
    ).strip() or None


# =============================================================================
# Roles de cliente válidos en DB (varios por compatibilidad histórica)
# =============================================================================
_CLIENT_ROLE_VALUES = ("CLIENTE", "CLIENT", "cliente", "client", "User", "user")


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
    """Lista paginada de clientes con estado de rutina activa.
    Solo ENTRENADOR / COORDINADOR / ADMINISTRADOR.
    Un único JOIN evita N+1 queries.
    """
    from sqlalchemy import or_, outerjoin
    from sqlalchemy.orm import aliased

    _require_role(current_user, {"ENTRENADOR", "COORDINADOR", "ADMINISTRADOR"})

    # Base query: solo usuarios con role de cliente
    q = db.query(models.User).filter(
        models.User.role.in_(_CLIENT_ROLE_VALUES)
    )

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

    # Un solo query para todas las rutinas activas del batch
    client_ids = [u.id for u in users]
    active_routines: dict = {}  # client_id -> (ClientRoutine, BaseRoutine)

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
        has_active = row is not None
        routine_name = f"{row[1].sheet_routine_id} – {row[1].name}" if row else None

        clients.append({
            "id": str(u.id),
            "dni": u.dni,
            "full_name": _full_name(u),
            "is_active": bool(u.is_active),
            "has_active_routine": has_active,
            "routine_name": routine_name,
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
    """Perfil básico de un cliente por DNI.
    Solo ENTRENADOR / COORDINADOR / ADMINISTRADOR.
    """
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
        "is_active": bool(user.is_active),
    }   