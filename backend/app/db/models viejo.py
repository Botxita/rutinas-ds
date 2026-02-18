import uuid

from sqlalchemy import (
    Column,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    func,
    CheckConstraint,
    Integer,
    Date,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


# -------------------------
# APP USERS (DB: public.app_users)
# Roles enforced by DB CHECK: CLIENTE, PROFE, ADMIN
# -------------------------
class User(Base):
    __tablename__ = "app_users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dni = Column(String, nullable=False, unique=True)
    role = Column(String, nullable=False)
    # Nombre para UI (opcional; se completa en Supabase)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        # Nota: el CHECK real lo aplica Postgres en Supabase. Este constraint local es solo para reflejarlo.
        # Aceptamos también roles legacy (PROFE/ADMIN) para no romper datos existentes.
        CheckConstraint(
            "role IN ('CLIENTE','ENTRENADOR','COORDINADOR','ADMINISTRADOR','PROFE','ADMIN')",
            name="app_users_role_check_local",
        ),
    )

    staff_credential = relationship("StaffCredential", back_populates="user", uselist=False)


# -------------------------
# STAFF CREDENTIALS (DB: public.staff_credentials)
# -------------------------
class StaffCredential(Base):
    __tablename__ = "staff_credentials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    app_user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id"), nullable=False, unique=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="staff_credential")


# -------------------------
# CLIENT PLAN STATE (DB: public.client_plan_state)
# Lógica usada por plan_service.py
# -------------------------
class ClientPlanState(Base):
    __tablename__ = "client_plan_state"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # En Rutinas DS, el "cliente" ES app_users (role CLIENTE)
    client_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id"), nullable=False, unique=True)

    # Estado de planificación semanal
    next_base_day_index = Column(Integer, nullable=False, default=1)
    week_start_date = Column(Date, nullable=False)
    bases_done_this_week = Column(Integer, nullable=False, default=0)

    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("client_id", name="uq_client_plan_state_client"),
    )


# -------------------------
# CLIENT PLAN CONFIG HISTORY (DB: public.client_plan_config_history)
# -------------------------
class ClientPlanConfigHistory(Base):
    __tablename__ = "client_plan_config_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    client_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id"), nullable=False)

    # Desde cuándo aplica esta config
    effective_from_date = Column(Date, nullable=False)

    # Días base por semana (2..6 en negocio)
    base_days_per_week = Column(Integer, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


# -------------------------
# ROUTINE PLANS (DB: public.routine_plans)
# -------------------------
class RoutinePlan(Base):
    __tablename__ = "routine_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False)

    frequency = Column(Integer, nullable=False)
    start_date = Column(Date, nullable=False)
    status = Column(String, nullable=False, default="ACTIVE")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("frequency BETWEEN 2 AND 6", name="ck_routine_plans_frequency_2_6"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_routine_plans_status"),
    )


# -------------------------
# WORKOUT SESSIONS (DB: public.workout_sessions)
# -------------------------
class WorkoutSession(Base):
    __tablename__ = "workout_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    plan_id = Column(UUID(as_uuid=True), ForeignKey("routine_plans.id", ondelete="CASCADE"), nullable=False)

    session_index = Column(Integer, nullable=False)  # 1..N incremental dentro del plan
    session_type = Column(String, nullable=False)    # BASE | EXTRA
    base_day_index = Column(Integer, nullable=True)  # 1..frequency (solo BASE)

    label = Column(String, nullable=True)
    intensity = Column(String, nullable=False, default="NORMAL")  # LIGERA|NORMAL|FUERTE

    week_start_date = Column(Date, nullable=True)

    recorded_by_user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("session_type IN ('BASE','EXTRA')", name="ck_workout_sessions_type"),
        CheckConstraint("intensity IN ('LIGERA','NORMAL','FUERTE')", name="ck_workout_sessions_intensity"),
        CheckConstraint("session_index >= 1", name="ck_workout_sessions_session_index"),
    )
