"""Um instrutor por UC (turma × UC) — outro só por substituição ou exceção justificada — e substituição por horista fora
do termo ou da disponibilidade, com a aprovação da supervisão e a concordância dele."""
from datetime import timedelta

import pytest
from sqlalchemy import delete, select

from app.core.errors import ConflitoValidacao
from app.models import Alocacao, DisponibilidadeInstrutor, TermoHoras
from app.services import alocacao as aloc
from app.services import cenarios, substituicao
from tests.conftest import SEG, aula


def test_outra_aula_da_uc_com_outro_instrutor_bloqueia(db, mundo, monkeypatch):
    m = mundo
    monkeypatch.setattr(substituicao, "hoje", lambda: SEG - timedelta(days=3))
    aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s1))
    db.commit()
    # i2 também é habilitado na UC A, mas a UC A da T1 é do i1
    with pytest.raises(ConflitoValidacao) as e:
        aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, d=SEG + timedelta(days=7), instrutor=m.i2, ambiente=m.s1))
    assert "UM_INSTRUTOR_POR_UC" in str(e.value.detalhes) or "um só instrutor" in str(e.value)
    db.rollback()
    a2, _ = aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, d=SEG + timedelta(days=7), instrutor=m.i1, ambiente=m.s1))
    db.commit()
    # outra turma: outra UC na prática, pode ser outro instrutor
    aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t2, m.uc_a, instrutor=m.i2, ambiente=m.s2))
    db.commit()
    # a substituição continua valendo (o titular segue sendo o i1) e o semestre valida sem bloqueio
    r = substituicao.substituir(db, m.ctx, m.cen.id, [db.get(Alocacao, a2.id)], m.i2.id, "Falta do titular por motivo de saúde")
    db.commit()
    assert r["substituidas"] == 1
    assert cenarios.validar(db, m.ctx, m.cen.id)["resumo"]["bloqueios"] == 0


def test_horista_fora_do_termo_e_da_disponibilidade_com_aprovacao(db, mundo, monkeypatch):
    m = mundo
    monkeypatch.setattr(substituicao, "hoje", lambda: SEG - timedelta(days=3))
    a, _ = aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s1))
    # i2 é horista: o termo de agosto só tem terça e a disponibilidade cadastrada também; a aula é numa segunda
    m.i2.modalidade = "horista"
    db.execute(delete(DisponibilidadeInstrutor).where(DisponibilidadeInstrutor.instrutor_id == m.i2.id, DisponibilidadeInstrutor.dia_semana != 1))
    db.add(TermoHoras(instrutor_id=m.i2.id, mes=SEG.replace(day=1), horas_aula=8, horas_outras=0, dias_semana=[1]))
    db.commit()
    aulas = [db.get(Alocacao, a.id)]
    cand = {c["id"]: c for c in substituicao.candidatos(db, m.cen.id, aulas)["instrutores"]}
    assert cand[m.i2.id]["grupo"] == "aprovacao" and cand[m.i2.id]["ajustar_termo"]
    # sem a aprovação: não troca e diz o que falta
    r = substituicao.substituir(db, m.ctx, m.cen.id, aulas, m.i2.id, "Falta do titular por motivo de saúde")
    db.rollback()
    assert r["substituidas"] == 0 and "aprovação da supervisão" in " ".join(r["falhas"][0]["motivos"])
    # com a aprovação da supervisão e a concordância dele: troca e o termo de agosto passa a ter a segunda
    r = substituicao.substituir(db, m.ctx, m.cen.id, [db.get(Alocacao, a.id)], m.i2.id, "Falta do titular por motivo de saúde",
                                aprovado_supervisao=True, concordancia=True)
    db.commit()
    assert r["substituidas"] == 1 and r["termos_ajustados"]
    t = db.scalar(select(TermoHoras).where(TermoHoras.instrutor_id == m.i2.id))
    assert 0 in t.dias_semana and "instrutor de acordo" in t.observacao
    assert db.get(Alocacao, a.id).instrutor_id == m.i2.id
    assert cenarios.validar(db, m.ctx, m.cen.id)["resumo"]["bloqueios"] == 0


def test_aulas_do_instrutor_mostra_o_que_ele_faz(db, mundo):
    m = mundo
    a, _ = aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s1))
    aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t2, m.uc_b, d=SEG + timedelta(days=1), instrutor=m.i1, ambiente=m.s2))
    db.commit()
    r = substituicao.aulas_do_instrutor(db, m.cen.id, m.i1.id, SEG, SEG + timedelta(days=6))
    assert [(b["turma"], b["data"]) for b in r["blocos"]] == [("T1", SEG.isoformat()), ("T2", (SEG + timedelta(days=1)).isoformat())]
    assert r["blocos"][0]["sala"] == "S1" and r["blocos"][0]["ids"] == [a.id]
    # escolher aulas uma a uma
    escolhidas = substituicao.aulas_alvo(db, m.cen.id, alocacao_ids=r["blocos"][1]["ids"])
    assert [x.turma_id for x in escolhidas] == [m.t2.id]


def test_gerador_mantem_o_instrutor_que_ja_da_a_uc(db, mundo):
    from tests.test_otimizacao import executar
    m = mundo
    # a UC A da T1 já começou com o i2 (também habilitado, mas não o preferido): o gerador completa a UC com ele
    aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i2, ambiente=m.s1))
    db.commit()
    ex = executar(db, m)
    assert ex.status == "concluida", ex.motivo_termino
    tuc = m.tuc(db, m.t1, m.uc_a)
    assert {a.instrutor_id for a in db.scalars(select(Alocacao).where(Alocacao.turma_uc_id == tuc.id))} == {m.i2.id}
