"""Turmas modulares: um módulo por semestre; o código da turma leva o módulo e sobe a cada semestre.

- Não modular (modulos vazio): HTC-ELT-12 (tipo de oferta + sigla do curso + número), como sempre.
- Modular: HTC-ELT-2-12 = turma 12 no 2º módulo. Uma turma de 3 módulos que começa em 2026/2 vai até 2027/2:
  HTC-ELT-1-12 (2026/2) → HTC-ELT-2-12 (2027/1) → HTC-ELT-3-12 (2027/2).
- Virada: ao criar o semestre seguinte, as turmas modulares cujo módulo terminou avançam (código, módulo e período).
"""
from __future__ import annotations

import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session


def semestre(d: date) -> int:
    """Índice do semestre: 2026/1 → 4052, 2026/2 → 4053."""
    return d.year * 2 + (1 if d.month >= 7 else 0)


def rotulo(idx: int) -> str:
    return f"{idx // 2}/{idx % 2 + 1}"


def codigo(sigla: str, numero, tipo, modulo: int | None = None) -> str:
    """HTC-ELT-12; modular: HTC-ELT-2-12."""
    return "-".join(str(x).strip().upper() for x in (tipo, sigla, modulo, numero) if x not in (None, ""))


def separar_modulo(resto: str | None) -> tuple[int | None, str | None]:
    """'2-12' → (2, '12'); '12' → (None, '12')."""
    m = re.fullmatch(r"(\d{1,2})-(.+)", resto or "")
    return (int(m.group(1)), m.group(2)) if m else (None, resto)


def previsao(turma) -> dict | None:
    """Até quando a turma modular vai (semestre do último módulo)."""
    if not getattr(turma, "modulos", None) or not turma.data_inicio:
        return None
    atual = turma.modulo_atual or 1
    s = semestre(turma.data_fim or turma.data_inicio)
    return {"modulo": atual, "modulos": turma.modulos, "semestre_atual": rotulo(s), "termina_em": rotulo(s + (turma.modulos - atual))}


def avancar(db: Session, ctx, inicio: date, fim: date | None, unidade_id: int | None = None) -> list[dict]:
    """Novo semestre: turmas modulares cujo módulo terminou antes de `inicio` passam ao próximo módulo
    (código, módulo e período), até o último módulo."""
    from app.models import Curso, Turma
    from app.services import auditoria
    feitas = []
    q = select(Turma).where(Turma.modulos.isnot(None), Turma.ativo.is_(True), Turma.simulacao_id.is_(None),
                            Turma.situacao.notin_(["concluida", "cancelada"]))
    if unidade_id:
        q = q.where(Turma.unidade_id == unidade_id)
    for t in db.scalars(q):
        atual = t.modulo_atual or 1
        if atual >= (t.modulos or 0) or not t.data_fim or t.data_fim >= inicio:
            continue
        passos = semestre(inicio) - semestre(t.data_fim)
        if passos <= 0:
            continue
        novo = min(t.modulos, atual + passos)
        curso = db.get(Curso, t.curso_id)
        antes = {"codigo": t.codigo, "modulo_atual": atual, "data_fim": t.data_fim.isoformat()}
        sigla = (curso.codigo if curso else "").upper()
        i = t.codigo.upper().find("-" + sigla + "-") if sigla else -1
        sem_tipo = bool(sigla) and t.codigo.upper().startswith(sigla + "-")
        if i > 0 or sem_tipo:
            tipo, resto = ("", t.codigo[len(sigla) + 1:]) if sem_tipo and i <= 0 else (t.codigo[:i], t.codigo[i + len(sigla) + 2:])
            _m, numero = separar_modulo(resto)
            t.codigo = codigo(sigla, numero, tipo, novo)
        t.modulo_atual = novo
        if fim and fim > t.data_fim:
            t.data_fim = fim
        db.flush()
        auditoria.registrar(db, ctx, "turma.avancar_modulo", "turmas", t.id, antes=antes,
                            depois={"codigo": t.codigo, "modulo_atual": novo, "data_fim": t.data_fim.isoformat()})
        feitas.append({"turma_id": t.id, "de": antes["codigo"], "para": t.codigo, "modulo": novo})
    return feitas
