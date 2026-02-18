from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Lee variables desde un archivo .env en la raíz de /backend
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Si no hay .env / variable, usa este valor por defecto (local)
    DATABASE_URL: str = "postgresql+psycopg2://postgres:422913@localhost:5432/rutinas_ds"

    SECRET_KEY: str = "CAMBIAR_ESTE_SECRET_LARGO"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24h

settings = Settings()
