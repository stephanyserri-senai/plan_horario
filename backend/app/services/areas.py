"""Compatibilidade de área entre recursos (instrutor, ambiente) e turmas.

Um recurso atende a área da turma quando:
- está marcado para TODAS as áreas (ex.: salas de aula comuns); ou
- a área da turma é a sua área principal ou uma das "outras áreas" cadastradas; ou
- não tem área definida (cadastro incompleto não bloqueia; a tela exige a área nos novos cadastros).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AmbienteArea, Ambiente, Instrutor, InstrutorArea


def areas_do_recurso(db: Session, obj) -> tuple[bool, set[int]]:
    """(atende todas as áreas?, conjunto de áreas)"""
    if obj is None:
        return True, set()
    if isinstance(obj, Instrutor):
        extras = db.scalars(select(InstrutorArea.area_id).where(InstrutorArea.instrutor_id == obj.id)).all()
    elif isinstance(obj, Ambiente):
        extras = db.scalars(select(AmbienteArea.area_id).where(AmbienteArea.ambiente_id == obj.id)).all()
    else:
        extras = []
    areas = set(extras) | ({obj.area_id} if obj.area_id else set())
    return bool(getattr(obj, "todas_areas", False)), areas


def atende_area(todas: bool, areas: set[int], area_turma: int | None) -> bool:
    return area_turma is None or todas or not areas or area_turma in areas


def recurso_atende(db: Session, obj, area_turma: int | None) -> bool:
    return atende_area(*areas_do_recurso(db, obj), area_turma)
