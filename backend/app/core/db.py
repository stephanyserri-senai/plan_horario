from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal = None


def criar_engine(url: str | None = None):
    """Engine compatível com o Supabase:
    - pooler em modo transação (porta 6543 / serverless): NullPool e sem
      prepared statements no servidor (o Supavisor não os mantém entre transações);
    - conexões com SSL obrigatório (normalizado em config.normalizar_url_banco).
    Toda a lógica de concorrência usa recursos com escopo de TRANSAÇÃO
    (pg_advisory_xact_lock, SELECT ... FOR UPDATE), compatíveis com o pooler."""
    from app.core.config import normalizar_url_banco
    s = get_settings()
    alvo = normalizar_url_banco(url) if url else s.url_banco
    kwargs = {"pool_pre_ping": True, "future": True}
    connect_args = {"application_name": "plan_horario"}
    if s.null_pool or ":6543/" in alvo:
        kwargs["poolclass"] = NullPool
        connect_args["prepare_threshold"] = None
    return create_engine(alvo, connect_args=connect_args, **kwargs)


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        _engine = criar_engine()
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, autoflush=False)
    return _engine


def reset_engine(url: str | None = None):
    """Usado pelos testes para apontar para outro banco."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = criar_engine(url)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, autoflush=False)
    return _engine


def SessionLocal() -> Session:
    get_engine()
    return _SessionLocal()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
