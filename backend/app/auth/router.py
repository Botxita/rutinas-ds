from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.session import get_db
from app.db.models import User, StaffCredential
from app.core.security import verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    dni: str
    password: str | None = None


def _normalize_role(raw: str) -> str:
    """Normaliza roles (DB puede tener valores viejos) a los 4 roles oficiales."""
    r = (raw or "").upper().strip()
    if r in ("CLIENT", "CLIENTE"):
        return "CLIENTE"
    if r in ("COACH", "PROFE", "ENTRENADOR"):
        return "ENTRENADOR"
    if r in ("COORDINATOR", "COORDINADOR"):
        return "COORDINADOR"
    if r in ("ADMIN", "ADMINISTRADOR"):
        return "ADMINISTRADOR"
    # fallback seguro
    return "CLIENTE"


def _role_to_str(role) -> str:
    # Supports Enum (role.value) or string
    return role.value if hasattr(role, "value") else str(role)

def _is_staff(norm_role: str) -> bool:
    return norm_role in ("ENTRENADOR", "COORDINADOR", "ADMINISTRADOR")


@router.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    dni = (data.dni or "").strip()
    if not dni:
        raise HTTPException(status_code=422, detail="DNI requerido")

    user = db.query(User).filter(User.dni == dni).first()

    # Keep same behavior: do not leak whether user exists
    if not user or not getattr(user, "is_active", True):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    db_role = _role_to_str(user.role)
    role = _normalize_role(db_role)

    # Staff requires password stored in staff_credentials table
    if _is_staff(role):
        if not data.password:
            raise HTTPException(status_code=401, detail="Credenciales inválidas")

        cred = db.query(StaffCredential).filter(StaffCredential.app_user_id == user.id).first()
        if not cred or not cred.password_hash:
            raise HTTPException(status_code=401, detail="Credenciales inválidas")

        if not verify_password(data.password, cred.password_hash):
            raise HTTPException(status_code=401, detail="Credenciales inválidas")

    # Clients (CLIENTE) login with DNI only
    display_name = " ".join(
        [x for x in [getattr(user, "first_name", None), getattr(user, "last_name", None)] if x]
    ).strip() or None

    token = create_access_token({"sub": str(user.id), "role": role})
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": role,
        "dni": user.dni,
        "displayName": display_name,
    }
