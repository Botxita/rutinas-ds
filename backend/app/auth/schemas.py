from pydantic import BaseModel
from typing import Optional

class UserInToken(BaseModel):
    id: Optional[str] = None
    dni: Optional[str] = None
    role: Optional[str] = None
