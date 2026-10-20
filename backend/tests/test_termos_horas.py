"""Horista: termo de horas mensal (limite das aulas do mês, ocupação e riscos); mensalista: jornada semanal fixa."""
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models import Instrutor
from app.services import alocacao as aloc
from app.services import analise_ocupacao, riscos, termos
from app.services.validacao import BaseDados, possui_bloqueio, validar_aula
from tests.conftest import SEG, aula


def _login(c):
    return {"Authorization": "Bearer " + c.post("/api/auth/login", json={"email": "admin@teste", "senha": "senha-forte-1"}).json()["token"]}


def _horista(db, m):
    i = db.get(Instrutor, m.i1.id)
    i.modalidade = "horista"
    db.commit()
    return i


def test_termo_limita_as_aulas_do_mes(db, mundo):
    m = mundo
    i = _horista(db, m)
    # termo de agosto: 3 h de aula (cada bloco de 2 aulas = 100 min) → cabem 1 bloco, o 2º passa do termo
    termos.salvar(db, m.ctx, i, "2026-08", 3)
    db.commit()
    aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, SEG, 0, n=2, instrutor=m.i1, ambiente=m.s1))
    db.commit()
    p = aula(m, db, m.t1, m.uc_a, SEG + timedelta(days=7), 0, n=2, instrutor=m.i1, ambiente=m.s1)
    oc = validar_aula(BaseDados(db, m.cen.id), aloc._proposta(db, p)[0])
    assert possui_bloqueio(oc) and any(o.regra == "TERMO_HORAS_MES" for o in oc)
    # o termo muda: com 4 h no mês, cabe
    r = termos.salvar(db, m.ctx, i, "2026-08", 4, cenario_id=m.cen.id)
    db.commit()
    assert r["programadas_h"] > 0 and "aviso" not in r
    assert not any(o.regra == "TERMO_HORAS_MES" for o in validar_aula(BaseDados(db, m.cen.id), aloc._proposta(db, p)[0]))
    # sem termo em setembro: vale só o limite semanal do cadastro
    p2 = aula(m, db, m.t1, m.uc_a, date(2026, 9, 14), 0, n=2, instrutor=m.i1, ambiente=m.s1)
    assert not any(o.regra == "TERMO_HORAS_MES" for o in validar_aula(BaseDados(db, m.cen.id), aloc._proposta(db, p2)[0]))


def test_termo_menor_que_o_programado_vira_risco_e_aviso(db, mundo):
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


def test_mensalista_nao_tem_termo_e_ocupacao_pelo_termo(db, mundo):
    m = mundo
    import pytest
    from app.core.errors import EntradaInvalida
    with pytest.raises(EntradaInvalida):
        termos.salvar(db, m.ctx, db.get(Instrutor, m.i2.id), "2026-08", 40)
    i = _horista(db, m)
    for mes in range(8, 13):
        termos.salvar(db, m.ctx, i, f"2026-{mes:02d}", 20)
    db.commit()
    rk = analise_ocupacao.ranking(db, m.cen.id, date(2026, 8, 3), date(2026, 12, 18))
    li = next(x for x in rk["instrutores_mais"] + rk["instrutores_menos"] if x["id"] == m.i1.id)
    assert li["base"] == "termo de horas" and li["teto_pct"] == 100.0 and li["carga_h"] < 6
    l2 = next(x for x in rk["instrutores_mais"] + rk["instrutores_menos"] if x["id"] == m.i2.id)
    assert l2["base"] == "jornada semanal" and l2["carga_h"] == 40.0


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
