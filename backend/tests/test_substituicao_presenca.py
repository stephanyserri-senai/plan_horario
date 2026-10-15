"""Quem pode substituir: em PL/PJ (está na escola) assume até no mesmo dia; turno vazio só com 1 dia de antecedência."""
from datetime import timedelta

from sqlalchemy import select

from app.models import Alocacao, Bloqueio
from app.services import agenda_instrutor, substituicao
from app.services import alocacao as aloc
from tests.conftest import SEG, aula


def test_pl_pj_assume_no_mesmo_dia_e_vazio_so_com_antecedencia(db, mundo, monkeypatch):
    m = mundo
    a, _ = aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s1))
    db.commit()
    # i2 está em PL no turno da aula; i3 está com o turno vazio
    agenda_instrutor.marcar(db, m.ctx, m.cen.id, m.i2.id, SEG, m.manha.id, "PL")
    db.commit()
    aulas = [db.get(Alocacao, a.id)]

    # no próprio dia: só quem está na escola (PL/PJ)
    monkeypatch.setattr(substituicao, "hoje", lambda: SEG)
    cand = {c["id"]: c for c in substituicao.candidatos(db, m.cen.id, aulas)["instrutores"]}
    assert cand[m.i2.id]["grupo"] == "recomendado" and cand[m.i2.id]["na_escola"] and cand[m.i2.id]["presenca"] == ["PL"]
    assert cand[m.i3.id]["grupo"] == "indisponivel" and "antecedência" in cand[m.i3.id]["motivos"][0]
    r = substituicao.substituir(db, m.ctx, m.cen.id, aulas, m.i3.id, "Falta do titular no próprio dia")
    assert r["substituidas"] == 0 and "antecedência" in r["falhas"][0]["motivos"][0]
    db.rollback()
    # i2 em PL: o PL vira a aula
    r = substituicao.substituir(db, m.ctx, m.cen.id, [db.get(Alocacao, a.id)], m.i2.id, "Falta do titular no próprio dia")
    db.commit()
    assert r["substituidas"] == 1 and r["pl_pj_convertidos"] == [f"PL de {SEG:%d/%m}"]
    assert db.get(Alocacao, a.id).instrutor_id == m.i2.id
    assert not db.scalars(select(Bloqueio).where(Bloqueio.alvo_id == m.i2.id, Bloqueio.tipo == "planejamento")).all()

    # planejada na véspera: turno vazio pode ser acionado
    substituicao.desfazer(db, m.ctx, [a.id])
    db.commit()
    monkeypatch.setattr(substituicao, "hoje", lambda: SEG - timedelta(days=1))
    cand = {c["id"]: c for c in substituicao.candidatos(db, m.cen.id, [db.get(Alocacao, a.id)])["instrutores"]}
    assert cand[m.i3.id]["grupo"] != "indisponivel" and cand[m.i3.id]["presenca"] == ["vazio"] and not cand[m.i3.id]["na_escola"]
    r = substituicao.substituir(db, m.ctx, m.cen.id, [db.get(Alocacao, a.id)], m.i3.id, "Falta programada do titular (curso)")
    db.commit()
    assert r["substituidas"] == 1
