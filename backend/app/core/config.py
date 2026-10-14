"""Configuração da aplicação lida de variáveis de ambiente (nunca do código)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PLAN_", extra="ignore")

    ambiente: str = "desenvolvimento"  # desenvolvimento | producao | teste
    database_url: str = "postgresql+psycopg://plan:plan@localhost:5432/plan_horario"
    # Em produção PLAN_JWT_SECRET é obrigatório (verificado em main.py).
    jwt_secret: str = "dev-secret-altere-em-producao"
    jwt_expira_minutos: int = 480
    cors_origens: str = "http://localhost:5173"
    solver_threads: int = 4
    solver_limite_padrao_s: int = 30
    max_jobs_simultaneos: int = 2
    log_level: str = "INFO"

    @property
    def producao(self) -> bool:
        return self.ambiente == "producao"


@lru_cache
def get_settings() -> Settings:
    return Settings()
