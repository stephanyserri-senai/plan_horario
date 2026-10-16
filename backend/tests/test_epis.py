"""EPIs do curso entram nas turmas (quantidade = alunos × por aluno, prazo = início − antecedência) e o controle
de comprado/separado e entregue gera avisos no Início e em Riscos."""
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import EpiTurma
from app.services import epis, riscos


def _h(c):
    return {"Authorization": "Bearer " + c.post("/api/auth/login", json={"email": "admin@teste", "senha": "senha-forte-1"}).json()["token"]}


def test_epis_do_curso_viram_controle_da_turma(db, mundo):
    from app.models import Area
    m = mundo
    area = Area(codigo="EPI", nome="TESTE EPI", unidade_id=m.unidade.id, ativo=True)
    db.add(area)
    db.flush()
    m.curso.area_id = area.id
    db.commit()
    c = TestClient(app)
    h = _h(c)
    r = c.post(f"/api/cursos/{m.curso.id}/epis", json={"nome": "Luva isolante", "quantidade_por_aluno": 2, "antecedencia_dias": 10}, headers=h)
    assert r.status_code == 200, r.text
    assert c.post(f"/api/cursos/{m.curso.id}/epis", json={"nome": ""}, headers=h).status_code == 422
    # turmas já existentes (T1, T2: 30 alunos, início 03/08) recebem o EPI
    itens = db.scalars(select(EpiTurma).where(EpiTurma.turma_id == m.t1.id)).all()
    assert [(e.nome, e.quantidade, e.prazo) for e in itens] == [("Luva isolante", 60, date(2026, 7, 24))]
    # turma nova pelo cadastro também
    base = {"curso_id": m.curso.id, "matriz_id": m.matriz.id, "turno_id": m.manha.id, "qtd_alunos": 12, "data_inicio": "2026-09-01",
            "data_fim": "2026-12-18", "_numero": "9", "_tipo_oferta": "HTC"}
    t = c.post("/api/cadastros/turmas", json=base, headers=h)
    assert t.status_code == 200, t.text
    lista = c.get(f"/api/epis-turmas?turma_id={t.json()['id']}", headers=h).json()["itens"]
    assert len(lista) == 1 and lista[0]["quantidade"] == 24 and lista[0]["prazo"] == "2026-08-22"
    # mudou o número de alunos: a quantidade acompanha (ainda não providenciado)
    assert c.put(f"/api/cadastros/turmas/{t.json()['id']}", json={"qtd_alunos": 15}, headers=h).status_code == 200
    item = c.get(f"/api/epis-turmas?turma_id={t.json()['id']}", headers=h).json()["itens"][0]
    assert item["quantidade"] == 30
    # situação pelo prazo e marcações (entregue implica separado)
    assert epis.listar(db, hoje=date(2026, 8, 20))["resumo"]["proximo"] == 1
    a = epis.avisos(db, hoje=date(2026, 8, 25))
    assert a["atrasados"] == 3
    r = c.put(f"/api/epis-turmas/{item['id']}", json={"entregue": True}, headers=h)
    assert r.status_code == 200 and r.json()["providenciado"] and r.json()["entregue"] and r.json()["situacao"] == "entregue"
    # já separado/entregue: mudar alunos não altera a quantidade registrada
    c.put(f"/api/cadastros/turmas/{t.json()['id']}", json={"qtd_alunos": 20}, headers=h)
    assert c.get(f"/api/epis-turmas?turma_id={t.json()['id']}", headers=h).json()["itens"][0]["quantidade"] == 30
    # aviso em Riscos
    rk = riscos.analisar(db, m.cen.id, None, hoje=date(2026, 8, 25))
    ep = next(x for x in rk["riscos"] if x["codigo"] == "epis")
    assert ep["quantidade"] == 2 and ep["gravidade"] == "alta"
    # retirar o EPI do curso tira das turmas onde ainda não foi providenciado
    eid = c.get(f"/api/cursos/{m.curso.id}/epis", headers=h).json()[0]["id"]
    assert c.put(f"/api/epis-curso/{eid}", json={"ativo": False}, headers=h).status_code == 200
    db.expire_all()
    assert len(db.scalars(select(EpiTurma)).all()) == 1  # só fica o que já foi entregue
