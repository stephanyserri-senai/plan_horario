"""Regras de composição das aulas (configuráveis em `configuracoes.regras_aula`).

Padrão da instituição:
- **turno inteiro**: cada UC ocupa o turno completo do dia (todas as aulas do
  turno, ex.: 4 aulas). A única exceção é o *fechamento de carga horária*: quando
  falta menos que um turno para a UC terminar, a última aula pode ser parcial e
  o restante do turno pode ser usado por outra UC que também esteja fechando.
- **hora-aula**: cada aula (período) conta 1 hora de carga horária, independente
  de durar 50 ou 55 minutos.
"""
from __future__ import annotations

import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Configuracao, PeriodoHorario
from app.services.calendario import minutos

PADRAO = {"turno_inteiro": True, "contagem": "hora_aula"}
CHAVE = "regras_aula"


def regras_aula(db: Session) -> dict:
    cfg = db.get(Configuracao, CHAVE)
    return {**PADRAO, **(cfg.valor if cfg and isinstance(cfg.valor, dict) else {})}


def hora_aula(regras: dict) -> bool:
    return regras.get("contagem", "hora_aula") == "hora_aula"


def credito_periodo(regras: dict, p) -> int:
    """Minutos de carga horária que um período vale (60 em hora-aula; duração real caso contrário)."""
    ini, fim = (minutos(p.hora_inicio), minutos(p.hora_fim)) if hasattr(p, "hora_inicio") else (p.ini, p.fim)
    return 60 if hora_aula(regras) else fim - ini


def credito_bloco(regras: dict, bloco) -> int:
    return sum(credito_periodo(regras, p) for p in bloco)


def periodos_do_turno(db: Session, turno_id: int | None, dia_semana: int) -> list[PeriodoHorario]:
    """Períodos regulares (não excepcionais) do turno no dia da semana, em ordem."""
    if not turno_id:
        return []
    ps = db.scalars(select(PeriodoHorario).where(PeriodoHorario.turno_id == turno_id, PeriodoHorario.ativo.is_(True),
                                                 PeriodoHorario.excepcional.is_(False)).order_by(PeriodoHorario.ordem)).all()
    return [p for p in ps if dia_semana in (p.dias_semana or [])]


def periodos_para_fechar(regras: dict, restante_min: float, periodos: list) -> int:
    """Quantas aulas do turno são necessárias para fechar a carga restante."""
    if restante_min <= 0 or not periodos:
        return 0
    cred = credito_periodo(regras, periodos[0])
    return min(len(periodos), max(1, math.ceil(restante_min / cred - 1e-9)))


TURNOS_PADRAO = [
    # código, nome, aulas (início, duração em minutos) — intervalos ficam entre a 2ª e a 3ª aula
    ("M", "Manhã", [(7 * 60 + 30, 55), (8 * 60 + 25, 55), (9 * 60 + 40, 55), (10 * 60 + 35, 55)]),
    ("T", "Tarde", [(13 * 60 + 30, 55), (14 * 60 + 25, 55), (15 * 60 + 40, 55), (16 * 60 + 35, 55)]),
    ("N", "Noite", [(18 * 60 + 20, 50), (19 * 60 + 10, 50), (20 * 60 + 10, 50), (21 * 60, 50)]),
]


HORAS_POR_TURNO = 4  # cada turno = 4 aulas


def turnos_por_dia(max_horas_dia) -> int:
    """Quantos turnos o instrutor pode assumir no mesmo dia: 4 h = 1, 8 h = 2, 12 h = 3."""
    return max(1, int(float(max_horas_dia or HORAS_POR_TURNO) // HORAS_POR_TURNO))


def horas_dia_pela_carga(carga_semanal) -> float:
    """Jornada diária pela carga contratual em 5 dias (40 h/sem = 8 h/dia), limitada a 12 h."""
    return float(min(12, max(1, round(float(carga_semanal) / 5))))
