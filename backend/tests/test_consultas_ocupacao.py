"""Consultas: situação no dia, ranking, ocupação no tempo e quadro de instrutores (80% ideal, 90% teto, 5:4)."""
from datetime import time, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models import Turno
from app.services import analise_ocupacao as ao
from tests.conftest import SEG
from tests.test_otimizacao import executar


def test_faixas():
    assert [ao.faixa(p) for p in (30, 60, 75, 85, 95)] == ["ociosa", "baixa", "ideal", "atencao", "acima_teto"]


def test_encaixe_nova_turma_prefere_3_2():
    assert ao.divisao_nova_turma(5) == [3, 2] and ao.divisao_nova_turma(4) == [2, 2]
    r = ao.encaixe_nova_turma({"Ana": 3, "Bia": 2, "Caio": 1}, 5)
    assert r["cabe"] and r["modo"] == "divisao_preferida" and sorted(p["turnos"] for p in r["plano"]) == [2, 3]
    # sem um par 3 + 2, divide entre vários instrutores se a soma der
    r = ao.encaixe_nova_turma({"Ana": 2, "Bia": 2, "Caio": 1}, 5)
    assert r["cabe"] and r["modo"] == "dividida" and sum(p["turnos"] for p in r["plano"]) == 5
    r = ao.encaixe_nova_turma({"Ana": 2, "Bia": 1}, 5)
    assert not r["cabe"] and r["modo"] == "nao_cabe"


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
    # sem coluna da PFP; sábado por último e "sem turno" num dia útil
    from app.models import PeriodoHorario
    for cod, dias, ordem in (("I", [0, 1, 2, 3, 4], 8), ("S", [5], 9)):
        t = Turno(unidade_id=m.unidade.id, codigo=cod, nome=cod, hora_inicio=time(8), hora_fim=time(12), ordem=ordem, ativo=True)
        db.add(t)
        db.flush()
        db.add(PeriodoHorario(unidade_id=m.unidade.id, turno_id=t.id, ordem=1, hora_inicio=time(8), hora_fim=time(12), dias_semana=dias, excepcional=False, ativo=True))
    db.commit()
    sit = c.get(f"/api/consultas/situacao?cenario_id={cid}&data={SEG}", headers=h).json()
    cods = [t["codigo"] for t in sit["turnos"]]
    assert "I" not in cods and cods[-1] == "S" and not sit["turnos"][-1]["no_dia"]
    assert {l["turnos"]["S"]["estado"] for l in sit["instrutores"]} == {"sem_turno"}
    rk = c.get(f"/api/consultas/ranking?cenario_id={cid}&inicio={SEG}&fim={SEG + timedelta(days=13)}", headers=h).json()
    pcts = [l["ocupacao_pct"] for l in rk["instrutores_mais"]]
    assert pcts == sorted(pcts, reverse=True) and sum(rk["distribuicao_instrutores"].values()) == rk["total_instrutores"]
    se = c.get(f"/api/consultas/serie?cenario_id={cid}&inicio={SEG}&fim={SEG + timedelta(days=27)}", headers=h).json()
    assert len(se["pontos"]) == 4 and se["pontos"][0]["instrutores_pct"] > 0
    q = ao.quadro_instrutores(db, cid, hoje=SEG)
    assert q["areas"] and q["total"]["turmas"] == 2
    for a in q["areas"]:
        assert "cabe" in a["nova_turma"] and a["instrutores_equivalentes"] >= 0
    # com 4 turmas a mais a demanda cresce; a proporção 5:4 vira aviso e não, sozinha, contratação
    linha = q["areas"][0]
    q2 = ao.quadro_instrutores(db, cid, hoje=SEG, turmas_extra={linha["area_id"]: 4} if linha["area_id"] else None)
    l2 = next(a for a in q2["areas"] if a["area_id"] == linha["area_id"])
    if linha["area_id"]:
        assert l2["demanda_semana_h"] > linha["demanda_semana_h"] and l2["ideal_proporcao"] > linha["ideal_proporcao"]
        assert l2["aviso_proporcao"] and l2["aviso_proporcao"]["faltam"] > 0
        assert l2["contratar_recomendado"] == l2["contratar_por_ocupacao"] or l2["situacao"] not in ("contratar", "sem_instrutor")
    r = c.get(f"/api/consultas/quadro-instrutores?cenario_id={cid}&extra=x:1", headers=h)
    assert r.status_code == 200
