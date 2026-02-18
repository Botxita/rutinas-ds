"""Compat layer.

Este proyecto usa JWT firmado (core/security.py) + get_current_user (auth/deps.py).
Este archivo existe para no romper imports viejos: `from app.auth.security import get_current_user`.

NO hace decode "sin verificar" (eso era inseguro y causaba bugs).
"""

from app.auth.deps import get_current_user  # re-export
