"""Termo de horas no perfil: painel com o próximo mês (feito no fim do mês) e a sugestão do que entra nele — o dia em que foi
preciso contar com o horista fora do termo vai para o termo do mês seguinte."""
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models import TermoHoras
from app.services import alocacao as aloc
from app.services import termos
from tests.conftest import SEG, aula


def test_painel_sugere_o_dia_fora_do_termo_para_o_mes_seguinte(db, mundo):
    m = mundo
    m.i1.modalidade = "horista"
    db.add(TermoHoras(instrutor_id=m.i1.id, mes=SEG.replace(day=1), horas_aula=40, horas_outras=0, dias_semana=[1, 2]))
    db.commit()
    # aula numa segunda (fora do termo de agosto: só terça e quarta)
    aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s1))
    db.commit()
    p = termos.painel(db, m.i1, m.cen.id, hoje=SEG + timedelta(days=20))
    ago = next(x for x in p["meses"] if x["mes"] == "2026-08")
    assert ago["situacao"] == "atual" and ago["dias_fora"] == [0] and ago["dias_com_aula"] == [0]
    assert p["proximo"]["mes"] == "2026-09" and p["proximo"]["prazo"] == "2026-08-31" and not p["proximo"]["tem_termo"]
    assert p["proximo"]["sugestao"]["dias_semana"] == [0, 1, 2]
    assert "segunda" in p["proximo"]["sugestao"]["motivos"][0] and "setembro" in p["proximo"]["sugestao"]["motivos"][0]


def test_portal_mostra_o_termo_ao_horista(db, mundo):
    m = mundo
    c = TestClient(app)
    h = {"Authorization": "Bearer " + c.post("/api/auth/login", json={"email": "admin@teste", "senha": "senha-forte-1"}).json()["token"]}
    m.i1.modalidade = "horista"
    db.add(TermoHoras(instrutor_id=m.i1.id, mes=date.today().replace(day=1), horas_aula=30, horas_outras=0))
    db.commit()
    r = c.get(f"/api/instrutores/{m.i1.id}/termos?cenario_id={m.cen.id}", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["proximo"]["prazo"] and any(x["tem_termo"] for x in r.json()["meses"])
