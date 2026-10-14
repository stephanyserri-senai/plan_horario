"""Registro de auditoria. Sempre gravado na mesma transação da operação
auditada: se a operação falhar, o registro também é desfeito."""
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.models import HistoricoAuditoria


def _json(v):
    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (list, tuple)):
        return [_json(x) for x in v]
    if isinstance(v, dict):
        return {k: _json(x) for k, x in v.items()}
    return v


def snapshot(obj, ocultar: tuple[str, ...] = ("senha_hash", "intervalo", "intervalo_ambiente")) -> dict:
    if obj is None:
        return None
    mapper = inspect(obj).mapper
    return {c.key: _json(getattr(obj, c.key)) for c in mapper.column_attrs if c.key not in ocultar}


def registrar(db: Session, ctx, acao: str, entidade: str, entidade_id=None, antes=None, depois=None, motivo=None, origem="api"):
    usuario = getattr(ctx, "usuario", None)
    db.add(
        HistoricoAuditoria(
            usuario_id=getattr(usuario, "id", None),
            usuario_nome=getattr(usuario, "nome", None) or (ctx if isinstance(ctx, str) else None),
            acao=acao,
            entidade=entidade,
            entidade_id=None if entidade_id is None else str(entidade_id),
            antes=_json(antes),
            depois=_json(depois),
            motivo=motivo,
            origem=origem,
        )
    )
