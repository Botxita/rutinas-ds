from pydantic import BaseModel
from datetime import date
from typing import Literal, Optional

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
