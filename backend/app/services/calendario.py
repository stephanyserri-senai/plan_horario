"""Regras de calendário: dias letivos, exceções, períodos e janelas de tempo."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Calendario, CalendarioExcecao, PeriodoHorario, Turma, Turno


def combinar(d: date, t: time) -> datetime:
    return datetime.combine(d, t)


def minutos(t: time) -> int:
    return t.hour * 60 + t.minute


def sobrepoe(a_ini, a_fim, b_ini, b_fim) -> bool:
    """Intervalos semiabertos [ini, fim): compara instantes reais (inclui
    sobreposição parcial; encostar o fim de um no início do outro não conflita)."""
    return a_ini < b_fim and b_ini < a_fim


def segunda_da_semana(d: date) -> date:
    return d - timedelta(days=d.weekday())


class Calendarios:
    """Cache de calendários e exceções por sessão de banco."""

    def __init__(self, db: Session):
        self.db = db
        self._cal: dict[int, Calendario] = {}
        self._exc: dict[int, dict[date, list[CalendarioExcecao]]] = {}
        self._cal_unidade: dict[int, Calendario | None] = {}

    def calendario_da_turma(self, turma: Turma) -> Calendario | None:
        if turma.calendario_id:
            if turma.calendario_id not in self._cal:
                self._cal[turma.calendario_id] = self.db.get(Calendario, turma.calendario_id)
            return self._cal[turma.calendario_id]
        if turma.unidade_id not in self._cal_unidade:
            self._cal_unidade[turma.unidade_id] = calendario_unidade(self.db, turma.unidade_id)
        return self._cal_unidade[turma.unidade_id]

    def excecoes(self, cal_id: int) -> dict[date, list[CalendarioExcecao]]:
        if cal_id not in self._exc:
            idx: dict[date, list] = {}
            for e in self.db.scalars(
                select(CalendarioExcecao).where(CalendarioExcecao.calendario_id == cal_id, CalendarioExcecao.ativo.is_(True))
            ):
                idx.setdefault(e.data, []).append(e)
            self._exc[cal_id] = idx
        return self._exc[cal_id]

    def dia_letivo_unidade(self, unidade_id: int, d: date) -> tuple[bool, str | None]:
        if unidade_id not in self._cal_unidade:
            self._cal_unidade[unidade_id] = calendario_unidade(self.db, unidade_id)
        cal = self._cal_unidade[unidade_id]
        if cal is None:
            return d.weekday() < 5, None if d.weekday() < 5 else "fim de semana"
        return self._letivo_no_calendario(cal, d, list(range(7)))

    def _letivo_no_calendario(self, cal: Calendario, d: date, dias_turma) -> tuple[bool, str | None]:
        if d < cal.data_inicio or d > cal.data_fim:
            return False, f"fora do calendário '{cal.nome}' ({cal.data_inicio:%d/%m/%Y}–{cal.data_fim:%d/%m/%Y})"
        excs = self.excecoes(cal.id).get(d, [])
        for e in excs:
            if e.tipo in ("feriado", "recesso"):
                return False, f"{e.tipo} — {e.descricao or ''}".strip(" —")
        if any(e.tipo == "dia_letivo_extra" for e in excs):
            return True, None
        if d.weekday() not in (cal.dias_letivos or []):
            return False, "dia da semana não letivo no calendário"
        return True, None

    def dia_letivo(self, turma: Turma, d: date) -> tuple[bool, str | None]:
        """Retorna (é letivo, motivo quando não é)."""
        cal = self.calendario_da_turma(turma)
        if cal is None:
            # Sem calendário cadastrado: considera apenas os dias da semana da turma.
            return True, None
        return self._letivo_no_calendario(cal, d, turma.dias_possiveis)


def calendario_unidade(db: Session, unidade_id: int) -> Calendario | None:
    return db.scalars(select(Calendario).where(Calendario.unidade_id == unidade_id, Calendario.ativo.is_(True))
                      .order_by(Calendario.data_inicio.desc())).first()


def periodos_por_turno(db: Session, unidade_id: int) -> dict[int, list[PeriodoHorario]]:
    res: dict[int, list[PeriodoHorario]] = {}
    for p in db.scalars(
        select(PeriodoHorario)
        .where(PeriodoHorario.unidade_id == unidade_id, PeriodoHorario.ativo.is_(True))
        .order_by(PeriodoHorario.turno_id, PeriodoHorario.ordem)
    ):
        res.setdefault(p.turno_id, []).append(p)
    return res


def bloco_de_periodos(db: Session, periodo_inicio_id: int, num_periodos: int, dia_semana: int | None = None) -> list[PeriodoHorario]:
    """Períodos consecutivos (mesmo turno) a partir do período inicial."""
    p0 = db.get(PeriodoHorario, periodo_inicio_id)
    if p0 is None:
        raise ValueError("Período inicial inexistente.")
    seq = db.scalars(
        select(PeriodoHorario)
        .where(PeriodoHorario.turno_id == p0.turno_id, PeriodoHorario.ordem >= p0.ordem, PeriodoHorario.ativo.is_(True))
        .order_by(PeriodoHorario.ordem)
    ).all()
    if dia_semana is not None:
        seq = [p for p in seq if dia_semana in (p.dias_semana or [])]
    bloco = seq[:num_periodos]
    if len(bloco) < num_periodos or bloco[0].id != p0.id:
        raise ValueError("Não há períodos consecutivos suficientes no turno para a duração solicitada.")
    return bloco


def minutos_do_bloco(bloco: list[PeriodoHorario]) -> int:
    """Minutos de aula efetiva (soma dos períodos; intervalos não contam)."""
    return sum(minutos(p.hora_fim) - minutos(p.hora_inicio) for p in bloco)


def turno_de(db: Session, turno_id: int | None) -> Turno | None:
    return db.get(Turno, turno_id) if turno_id else None
