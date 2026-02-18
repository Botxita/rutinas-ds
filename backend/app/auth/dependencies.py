from typing import Callable
from fastapi import Depends, HTTPException, status

from app.auth.deps import get_current_user
from app.db.models import User


def _db_role(user: User) -> str:
    # user.role viene de DB: CLIENTE | PROFE | ADMIN
    return (getattr(user, "role", "") or "").strip().upper()


def require_role(*allowed_roles_db: str) -> Callable:
    """Dependency para proteger endpoints por rol DB.

    allowed_roles_db: roles tal como están en DB (CLIENTE, PROFE, ADMIN).
    """

    allowed = tuple(r.strip().upper() for r in allowed_roles_db)

    def _dep(current_user: User = Depends(get_current_user)) -> User:
        if _db_role(current_user) not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tenés permiso para acceder a este recurso",
            )
        return current_user

    return _dep
