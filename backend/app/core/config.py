"""Configuração da aplicação lida de variáveis de ambiente (nunca do código).

Os nomes oficiais usam o prefixo PLAN_. Para facilitar o uso da integração
Supabase da Vercel, alguns nomes padrão também são aceitos como alternativa
(DATABASE_URL/POSTGRES_URL, SUPABASE_URL, SUPABASE_ANON_KEY etc.).
"""
import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_RAIZ = Path(__file__).resolve().parents[3]


def normalizar_url_banco(url: str) -> str:
    """Aceita as URLs no formato do Supabase (postgres://, postgresql://) e
    garante o driver psycopg 3 e SSL obrigatório para hosts do Supabase."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    # Senha com '@' não codificado: o último '@' separa credenciais do host; os anteriores pertencem à senha.
    esquema, sep, resto = url.partition("://")
    if sep:
        autoridade, barra, caminho = resto.partition("/")
        if autoridade.count("@") > 1:
            cred, _, host = autoridade.rpartition("@")
            usuario, dois_pontos, senha = cred.partition(":")
            cred = usuario + dois_pontos + senha.replace("@", "%40")
            url = f"{esquema}://{cred}@{host}{barra}{caminho}"
    try:
        partes = urlsplit(url)
        host = partes.hostname
    except ValueError:
        raise ValueError("PLAN_DATABASE_URL inválida: a parte da senha contém '[' ou ']' (os colchetes de "
                         "[YOUR-PASSWORD] devem ser removidos; caracteres especiais da senha precisam ser codificados).") from None
    if host and "supabase" in host:
        q = dict(parse_qsl(partes.query))
        q.setdefault("sslmode", "require")
        # parâmetros específicos de outros drivers que o libpq não aceita
        for k in ("pgbouncer", "supa"):
            q.pop(k, None)
        url = urlunsplit(partes._replace(query=urlencode(q)))
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(str(_RAIZ / ".env"), ".env"), env_prefix="PLAN_", extra="ignore", populate_by_name=True)

    ambiente: str = "desenvolvimento"  # desenvolvimento | homologacao | producao | teste
    database_url: str = Field("postgresql+psycopg://plan:plan@localhost:5432/plan_horario",
                              validation_alias=AliasChoices("PLAN_DATABASE_URL", "DATABASE_URL", "POSTGRES_URL"))
    # Conexão para migrações (direta ou pooler em modo sessão); vazio = usa database_url.
    database_url_migracoes: str = ""
    # "auto": NullPool em ambiente serverless (Vercel) ou quando a URL aponta para o pooler em modo transação (porta 6543).
    db_pool: str = "auto"  # auto | padrao | null

    # Autenticação: "local" (usuários/senhas próprios, JWT HS256) ou "supabase" (Supabase Auth).
    auth_modo: str = "local"
    jwt_secret: str = "dev-secret-altere-em-producao-0123456789"
    jwt_expira_minutos: int = 480
    supabase_url: str = Field("", validation_alias=AliasChoices("PLAN_SUPABASE_URL", "SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL"))
    # Chave pública (anon/publishable): pode ir para o navegador. Protegida por RLS.
    supabase_anon_key: str = Field("", validation_alias=AliasChoices("PLAN_SUPABASE_ANON_KEY", "SUPABASE_ANON_KEY", "SUPABASE_PUBLISHABLE_KEY",
                                                                     "NEXT_PUBLIC_SUPABASE_ANON_KEY"))
    # Segredos exclusivos do servidor (NUNCA expor no frontend):
    supabase_jwt_secret: str = Field("", validation_alias=AliasChoices("PLAN_SUPABASE_JWT_SECRET", "SUPABASE_JWT_SECRET"))
    supabase_service_role_key: str = Field("", validation_alias=AliasChoices("PLAN_SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_ROLE_KEY",
                                                                             "SUPABASE_SECRET_KEY"))

    cors_origens: str = "http://localhost:5173"
    url_publica: str = ""  # URL do site (redirecionamento de convites/recuperação de senha)

    # Execução do otimizador: thread (processo local), fila (worker externo) ou sincrono (na própria requisição).
    executor: str = "auto"
    solver_threads: int = 4
    solver_limite_padrao_s: int = 30
    solver_limite_max_s: int = 600
    max_jobs_simultaneos: int = 2
    worker_intervalo_s: float = 5.0
    worker_heartbeat_expira_s: int = 300

    limite_upload_mb: float = 20.0
    log_level: str = "INFO"

    @property
    def producao(self) -> bool:
        return self.ambiente == "producao"

    @property
    def serverless(self) -> bool:
        return bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))

    @property
    def url_banco(self) -> str:
        return normalizar_url_banco(self.database_url)

    @property
    def usa_pooler_transacao(self) -> bool:
        return urlsplit(self.url_banco).port == 6543

    @property
    def null_pool(self) -> bool:
        if self.db_pool == "auto":
            return self.serverless or self.usa_pooler_transacao
        return self.db_pool == "null"

    @property
    def modo_executor(self) -> str:
        if self.executor != "auto":
            return self.executor
        # Em serverless não há processo persistente para threads em segundo plano.
        return "fila" if self.serverless else "thread"

    @property
    def limite_upload_bytes(self) -> int:
        mb = min(self.limite_upload_mb, 4.0) if self.serverless else self.limite_upload_mb  # Vercel: corpo máx. 4,5 MB
        return int(mb * 1024 * 1024)

    def validar(self) -> list[str]:
        """Erros de configuração que impedem a execução segura."""
        erros = []
        if self.auth_modo not in ("local", "supabase"):
            erros.append("PLAN_AUTH_MODO deve ser 'local' ou 'supabase'.")
        if self.modo_executor not in ("thread", "fila", "sincrono"):
            erros.append("PLAN_EXECUTOR deve ser 'auto', 'thread', 'fila' ou 'sincrono'.")
        if self.producao:
            if self.auth_modo == "local" and (self.jwt_secret.startswith("dev-") or len(self.jwt_secret) < 32):
                erros.append("Defina PLAN_JWT_SECRET (32+ caracteres) em produção.")
            if "localhost" in self.database_url or "127.0.0.1" in self.database_url:
                erros.append("PLAN_DATABASE_URL aponta para localhost em produção.")
        if self.auth_modo == "supabase":
            if not self.supabase_url:
                erros.append("PLAN_SUPABASE_URL é obrigatório com PLAN_AUTH_MODO=supabase.")
            if not self.supabase_anon_key:
                erros.append("PLAN_SUPABASE_ANON_KEY é obrigatório com PLAN_AUTH_MODO=supabase.")
        return erros


@lru_cache
def get_settings() -> Settings:
    return Settings()
