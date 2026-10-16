"""Resolver riscos: o sistema sugere uma correção por caso e aceitar aplica pela validação central."""
from datetime import timedelta

from app.models import Alocacao, Ambiente
from app.services import resolucoes, sugestoes
from tests.conftest import SEG, aula


def test_sala_em_manutencao_tem_sugestao_que_se_aplica(db, mundo):
    m = mundo
    from app.services import alocacao as aloc
    a, _ = aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, SEG, 0, n=2, instrutor=m.i1, ambiente=m.s1))
    db.commit()
    db.get(Ambiente, m.s1.id).situacao = "manutencao"
    db.commit()
    hoje = SEG - timedelta(days=1)
    r = resolucoes.sugerir(db, m.cen.id, "sala_indisponivel", None, hoje=hoje)
    it = next(i for i in r["itens"] if i["id"] == f"a{a.id}")
    assert it["acao"]["tipo"] in ("trocar_sala", "remarcar")
    sugestoes.aplicar(db, m.ctx, m.cen.id, it["acao"], gerar=False)
    db.commit()
    db.expire_all()
    nova = db.get(Alocacao, a.id)
    assert nova.fixa and (nova.ambiente_id != m.s1.id or nova.inicio != a.inicio)
    assert all(i["id"] != f"a{a.id}" for i in resolucoes.sugerir(db, m.cen.id, "sala_indisponivel", None, hoje=hoje)["itens"])


def test_risco_sem_correcao_automatica_leva_a_pagina(db, mundo):
    r = resolucoes.sugerir(db, mundo.cen.id, "epis", None)
    assert r["automatico"] is False and r["link"] == "/epis"
