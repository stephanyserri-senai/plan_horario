"""Consultas: situação no dia, ranking, ocupação no tempo e quadro de instrutores (80% ideal, 90% teto, 5:4)."""
from datetime import timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.services import analise_ocupacao as ao
from tests.conftest import SEG
from tests.test_otimizacao import executar


def test_faixas():
    assert [ao.faixa(p) for p in (30, 60, 75, 85, 95)] == ["ociosa", "baixa", "ideal", "atencao", "acima_teto"]


def test_consultas_e_quadro(db, mundo):
    m = mundo
    assert executar(db, m).status == "concluida"
    c = TestClient(app)
    h = {"Authorization": "Bearer " + c.post("/api/auth/login", json={"email": "admin@teste", "senha": "senha-forte-1"}).json()["token"]}
    cid = m.cen.id
    sit = c.get(f"/api/consultas/situacao?cenario_id={cid}&data={SEG}", headers=h).json()
    estados = {cel["estado"] for l in sit["instrutores"] for cel in l["turnos"].values()}
    assert "aula" in estados and sit["resumo"]["instrutores_em_aula"] >= 1
    assert all(set(l["turnos"]) <= {t["codigo"] for t in sit["turnos"]} for l in sit["salas"])
    rk = c.get(f"/api/consultas/ranking?cenario_id={cid}&inicio={SEG}&fim={SEG + timedelta(days=13)}", headers=h).json()
    pcts = [l["ocupacao_pct"] for l in rk["instrutores_mais"]]
    assert pcts == sorted(pcts, reverse=True) and sum(rk["distribuicao_instrutores"].values()) == rk["total_instrutores"]
    se = c.get(f"/api/consultas/serie?cenario_id={cid}&inicio={SEG}&fim={SEG + timedelta(days=27)}", headers=h).json()
    assert len(se["pontos"]) == 4 and se["pontos"][0]["instrutores_pct"] > 0
    q = ao.quadro_instrutores(db, cid, hoje=SEG)
    assert q["areas"] and q["total"]["turmas"] == 2
    # com 4 turmas a mais a demanda cresce e a proporção 5:4 pede mais instrutores
    linha = q["areas"][0]
    q2 = ao.quadro_instrutores(db, cid, hoje=SEG, turmas_extra={linha["area_id"]: 4} if linha["area_id"] else None)
    l2 = next(a for a in q2["areas"] if a["area_id"] == linha["area_id"])
    if linha["area_id"]:
        assert l2["demanda_semana_h"] > linha["demanda_semana_h"] and l2["ideal_proporcao"] > linha["ideal_proporcao"]
    r = c.get(f"/api/consultas/quadro-instrutores?cenario_id={cid}&extra=x:1", headers=h)
    assert r.status_code == 200
