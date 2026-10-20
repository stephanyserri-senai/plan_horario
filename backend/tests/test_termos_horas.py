"""Horista: termo de horas mensal (ajustável numa urgência, com a concordância do instrutor); mensalista: jornada semanal fixa.
Na simulação e na previsão de turmas o termo não conta: só a ocupação e a carga máxima do contrato."""
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models import Instrutor
from app.services import alocacao as aloc
import pytest

from app.core.errors import EntradaInvalida
from app.services import analise_ocupacao, resolucoes, riscos, sugestoes, termos
from app.services.validacao import BaseDados, possui_bloqueio, validar_aula
from tests.conftest import SEG, aula


def _login(c):
    return {"Authorization": "Bearer " + c.post("/api/auth/login", json={"email": "admin@teste", "senha": "senha-forte-1"}).json()["token"]}


def _horista(db, m):
    i = db.get(Instrutor, m.i1.id)
    i.modalidade = "horista"
    db.commit()
    return i


def test_aula_acima_do_termo_e_alerta_e_o_termo_se_ajusta_com_concordancia(db, mundo):
    m = mundo
    i = _horista(db, m)
    # termo de agosto: 3 h de aula, só às segundas (cada bloco de 2 aulas = 100 min)
    termos.salvar(db, m.ctx, i, "2026-08", 3, dias_semana=[0])
    db.commit()
    aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, SEG, 0, n=2, instrutor=m.i1, ambiente=m.s1))
    db.commit()
    p = aula(m, db, m.t1, m.uc_a, SEG + timedelta(days=8), 0, n=2, instrutor=m.i1, ambiente=m.s1)  # terça, acima das 3 h
    oc = validar_aula(BaseDados(db, m.cen.id), aloc._proposta(db, p)[0])
    regras = {o.regra: o.severidade for o in oc}
    assert regras.get("TERMO_HORAS_MES") == "alerta" and regras.get("TERMO_FORA_DOS_DIAS") == "alerta" and not possui_bloqueio(oc)
    # o ajuste exige a concordância do instrutor e o motivo
    with pytest.raises(EntradaInvalida):
        termos.ajustar(db, m.ctx, i, "2026-08", "Substituição urgente", False, horas_aula=6)
    r = termos.ajustar(db, m.ctx, i, "2026-08", "Substituição urgente na T1", True, horas_aula=6, incluir_dias=[1], cenario_id=m.cen.id)
    db.commit()
    assert r["horas_aula"] == 6.0 and r["dias_semana"] == [0, 1] and "instrutor de acordo" in r["observacao"]
    assert not {o.regra for o in validar_aula(BaseDados(db, m.cen.id), aloc._proposta(db, p)[0])} & {"TERMO_HORAS_MES", "TERMO_FORA_DOS_DIAS"}
    # o limite real continua sendo o contrato (limite semanal do cadastro)
    i.limite_ch_letiva = 1
    db.commit()
    assert any(o.regra == "LIMITE_SEMANAL" and o.severidade == "bloqueio" for o in validar_aula(BaseDados(db, m.cen.id), aloc._proposta(db, p)[0]))


def test_termo_menor_que_o_programado_vira_risco_com_sugestao_de_ajuste(db, mundo):
    m = mundo
    i = _horista(db, m)
    seg = date(2026, 11, 2)
    for k in range(3):
        aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, seg + timedelta(days=7 * k), 0, n=2, instrutor=m.i1, ambiente=m.s1))
    db.commit()
    r = termos.salvar(db, m.ctx, i, "2026-11", 2, cenario_id=m.cen.id)
    db.commit()
    assert "acima do novo termo" in r["aviso"]
    pend = termos.pendencias(db, m.cen.id, None, date(2026, 10, 20), date(2026, 12, 18))
    assert [(p["mes"], p["termo_h"]) for p in pend] == [("novembro/2026", 2.0)]
    rk = riscos.analisar(db, m.cen.id, hoje=date(2026, 10, 20))
    assert next(x for x in rk["riscos"] if x["codigo"] == "termo_horas")["quantidade"] == 1
    s = resolucoes.sugerir(db, m.cen.id, "termo_horas", None, hoje=date(2026, 10, 20))
    acao = s["itens"][0]["acao"]
    assert acao["tipo"] == "ajustar_termo" and acao["horas_aula"] == 5 and acao["requer_concordancia"]
    with pytest.raises(EntradaInvalida):  # sem a concordância do instrutor, não ajusta
        sugestoes.aplicar(db, m.ctx, m.cen.id, acao, gerar=False)
    sugestoes.aplicar(db, m.ctx, m.cen.id, {**acao, "concordancia": True}, gerar=False)
    db.commit()
    assert termos.pendencias(db, m.cen.id, None, date(2026, 10, 20), date(2026, 12, 18)) == []


def test_simulacao_ignora_o_termo(db, mundo):
    m = mundo
    i = _horista(db, m)
    for mes in range(8, 13):
        termos.salvar(db, m.ctx, i, f"2026-{mes:02d}", 4)
    db.commit()
    from app.services import otimizacao
    from app.services.regras_aula import limite_letivo_efetivo
    cen = db.get(type(m.cen), m.cen.id)
    lim = {x.id: x for x in otimizacao.montar_entrada(db, cen, {"tipo": "instituicao"}, {}, 5, "completo")[0].instrutores}
    sim = {x.id: x for x in otimizacao.montar_entrada(db, cen, {"tipo": "simulacao"}, {}, 5, "completo")[0].instrutores}
    contrato = int(limite_letivo_efetivo(i) * 60)
    assert lim[m.i1.id].limite_semanal_min < contrato  # geração do semestre: dentro do termo, de preferência
    assert sim[m.i1.id].limite_semanal_min == contrato  # simulação: só ocupação e carga máxima do contrato


def test_mensalista_nao_tem_termo_e_ocupacao_pelo_contrato(db, mundo):
    m = mundo
    with pytest.raises(EntradaInvalida):
        termos.salvar(db, m.ctx, db.get(Instrutor, m.i2.id), "2026-08", 40)
    i = _horista(db, m)
    for mes in range(8, 13):
        termos.salvar(db, m.ctx, i, f"2026-{mes:02d}", 20)
    db.commit()
    rk = analise_ocupacao.ranking(db, m.cen.id, date(2026, 8, 3), date(2026, 12, 18))
    li = next(x for x in rk["instrutores_mais"] + rk["instrutores_menos"] if x["id"] == m.i1.id)
    assert li["carga_h"] == 40.0  # horista ou mensalista: a ocupação é medida sobre o contrato


def test_quadro_uma_linha_por_instrutor_e_api_dos_termos(db, mundo):
    m = mundo
    _horista(db, m)
    c = TestClient(app)
    h = _login(c)
    r = c.get(f"/api/instrutores/disponibilidade?cenario_id={m.cen.id}&mes=2026-08", headers=h).json()
    assert len(r["instrutores"]) == 3 and len({x["id"] for x in r["instrutores"]}) == 3
    l1 = next(x for x in r["instrutores"] if x["id"] == m.i1.id)
    assert [d["turnos"] for d in l1["dias"][:5]] == [["M"]] * 5 and l1["dias"][5]["turnos"] == []
    assert l1["termo"]["tem_termo"] is False and r["resumo"]["horistas_sem_termo"] == 1
    assert "ocupacao" in next(x for x in r["instrutores"] if x["id"] == m.i2.id)
    x = c.put(f"/api/instrutores/{m.i1.id}/termos/2026-08?cenario_id={m.cen.id}", json={"horas_aula": 60, "horas_outras": 4, "observacao": "turmas T1"}, headers=h)
    assert x.status_code == 200 and x.json()["horas_aula"] == 60.0
    assert c.put(f"/api/instrutores/{m.i2.id}/termos/2026-08", json={"horas_aula": 60}, headers=h).status_code == 422
    t = c.get(f"/api/instrutores/{m.i1.id}/termos?cenario_id={m.cen.id}", headers=h).json()
    assert [mm["tem_termo"] for mm in t["meses"]] == [True, False, False, False, False]
    perfil = c.get(f"/api/instrutores/{m.i1.id}/perfil?cenario_id={m.cen.id}", headers=h).json()
    assert perfil["termos"]["meses"][0]["horas_aula"] == 60.0
