from __future__ import annotations

from uuid import UUID as PyUUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import User
from app.db.session import get_db

bearer_scheme = HTTPBearer()


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    token = creds.credentials

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(status_code=401, detail="Token inválido")
        try:
            user_id = PyUUID(str(sub))
        except Exception:
            raise HTTPException(status_code=401, detail="Token inválido")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")

    q = db.query(User).filter(User.id == user_id)

    # User tiene is_active en este proyecto
    if hasattr(User, "is_active"):
        q = q.filter(User.is_active == True)  # noqa: E712

    user = q.first()

    if not user:
        raise HTTPException(status_code=401, detail="Usuario inválido")

    return user


# Alias para imports existentes en otros archivos (ej: app.auth.router)
def get_db() -> Session:
    # Nota: en FastAPI se usa Depends(get_db) donde get_db es un generator.
    # Importamos el generator real desde app.db.session.
    from app.db.session import get_db as _get_db  # local import to avoid cycles
    return _get_db()
