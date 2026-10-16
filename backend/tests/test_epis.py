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
    # turmas já existentes (T1, T2: 30 alunos, início 03/08) recebem o EPI; turma que já começou ganha uma semana de prazo
    itens = db.scalars(select(EpiTurma).where(EpiTurma.turma_id == m.t1.id)).all()
    from datetime import timedelta
    esperado = date(2026, 7, 24) if date.today() < date(2026, 8, 3) else max(date(2026, 7, 24), date.today() + timedelta(days=7))
    assert [(e.nome, e.quantidade, e.prazo) for e in itens] == [("Luva isolante", 60, esperado)]
    # turma nova pelo cadastro também
    base = {"curso_id": m.curso.id, "matriz_id": m.matriz.id, "turno_id": m.manha.id, "qtd_alunos": 12, "data_inicio": "2026-12-01",
            "data_fim": "2026-12-18", "_numero": "9", "_tipo_oferta": "HTC"}
    t = c.post("/api/cadastros/turmas", json=base, headers=h)
    assert t.status_code == 200, t.text
    lista = c.get(f"/api/epis-turmas?turma_id={t.json()['id']}", headers=h).json()["itens"]
    assert len(lista) == 1 and lista[0]["quantidade"] == 24 and lista[0]["prazo"] == "2026-11-21"
    # mudou o número de alunos: a quantidade acompanha (ainda não providenciado)
    assert c.put(f"/api/cadastros/turmas/{t.json()['id']}", json={"qtd_alunos": 15}, headers=h).status_code == 200
    item = c.get(f"/api/epis-turmas?turma_id={t.json()['id']}", headers=h).json()["itens"][0]
    assert item["quantidade"] == 30
    # situação pelo prazo e marcações (entregue implica separado)
    assert epis.listar(db, hoje=date(2026, 11, 16))["resumo"]["proximo"] == 1
    a = epis.avisos(db, hoje=date(2026, 11, 25))
    assert a["atrasados"] == 3
    r = c.put(f"/api/epis-turmas/{item['id']}", json={"entregue": True}, headers=h)
    assert r.status_code == 200 and r.json()["providenciado"] and r.json()["entregue"] and r.json()["situacao"] == "entregue"
    # já separado/entregue: mudar alunos não altera a quantidade registrada
    c.put(f"/api/cadastros/turmas/{t.json()['id']}", json={"qtd_alunos": 20}, headers=h)
    assert c.get(f"/api/epis-turmas?turma_id={t.json()['id']}", headers=h).json()["itens"][0]["quantidade"] == 30
    # aviso em Riscos
    rk = riscos.analisar(db, m.cen.id, None, hoje=date(2026, 11, 25))
    ep = next(x for x in rk["riscos"] if x["codigo"] == "epis")
    assert ep["quantidade"] == 2 and ep["gravidade"] == "alta"
    # retirar o EPI do curso tira das turmas onde ainda não foi providenciado
    eid = c.get(f"/api/cursos/{m.curso.id}/epis", headers=h).json()[0]["id"]
    assert c.put(f"/api/epis-curso/{eid}", json={"ativo": False}, headers=h).status_code == 200
    db.expire_all()
    assert len(db.scalars(select(EpiTurma)).all()) == 1  # só fica o que já foi entregue


def test_epi_incluido_manualmente_na_turma(db, mundo):
    m = mundo
    c = TestClient(app)
    h = _h(c)
    r = c.post("/api/epis-turmas", json={"turma_id": m.t1.id, "nome": "Protetor facial", "quantidade": 5, "prazo": "2026-08-01"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["avulso"] and r.json()["quantidade"] == 5 and r.json()["prazo"] == "2026-08-01"
    # sem quantidade nem prazo: um por aluno, 15 dias antes do início
    r2 = c.post("/api/epis-turmas", json={"turma_id": m.t1.id, "nome": "Máscara PFF2"}, headers=h).json()
    assert r2["quantidade"] == 30 and r2["prazo"] == "2026-07-19"
    assert c.post("/api/epis-turmas", json={"turma_id": m.t1.id, "nome": " "}, headers=h).status_code == 422
    assert c.post("/api/epis-turmas", json={"turma_id": 999999, "nome": "X"}, headers=h).status_code == 404
    # a atualização da turma não apaga o avulso
    assert c.put(f"/api/cadastros/turmas/{m.t1.id}", json={"qtd_alunos": 28}, headers=h).status_code == 200
    nomes = {i["nome"] for i in c.get(f"/api/epis-turmas?turma_id={m.t1.id}", headers=h).json()["itens"]}
    assert {"Protetor facial", "Máscara PFF2"} <= nomes
    assert c.delete(f"/api/epis-turmas/{r.json()['id']}", headers=h).status_code == 200
    assert "Protetor facial" not in {i["nome"] for i in c.get(f"/api/epis-turmas?turma_id={m.t1.id}", headers=h).json()["itens"]}


def test_lista_de_epis_colada_no_curso(db, mundo):
    m = mundo
    c = TestClient(app)
    h = _h(c)
    texto = "Luva isolante; 2; 10\nÓculos de proteção\n\nCapacete;1\nóculos de proteção"
    r = c.post(f"/api/cursos/{m.curso.id}/epis/lista", json={"texto": texto}, headers=h)
    assert r.status_code == 200, r.text
    j = r.json()
    assert [e["nome"] for e in j["criados"]] == ["Luva isolante", "Óculos de proteção", "Capacete"] and j["repetidos"] == ["óculos de proteção"]
    assert j["itens_nas_turmas"] == 6  # 3 EPIs × turmas T1 e T2
    luva = next(e for e in j["criados"] if e["nome"] == "Luva isolante")
    assert luva["quantidade_por_aluno"] == 2 and luva["antecedencia_dias"] == 10
    assert c.post(f"/api/cursos/{m.curso.id}/epis/lista", json={"texto": "X; abc"}, headers=h).status_code == 422
    res = {x["id"]: x for x in c.get("/api/epis-cursos", headers=h).json()}
    assert res[m.curso.id]["epis"] == 3 and res[m.curso.id]["turmas_ativas"] == 2


def test_curso_que_nao_precisa_de_epi(db, mundo):
    m = mundo
    c = TestClient(app)
    h = _h(c)
    assert c.get(f"/api/cursos/{m.curso.id}/epi-config", headers=h).json() == {"dispensa_epi": False}
    assert c.put(f"/api/cursos/{m.curso.id}/epi-config", json={"dispensa_epi": True}, headers=h).json() == {"dispensa_epi": True}
    # marcado: não aceita EPI na lista (um a um ou colado)
    r = c.post(f"/api/cursos/{m.curso.id}/epis", json={"nome": "Luva"}, headers=h)
    assert r.status_code == 422 and "não precisa de EPI" in r.text
    assert c.post(f"/api/cursos/{m.curso.id}/epis/lista", json={"texto": "Luva"}, headers=h).status_code == 422
    assert next(x for x in c.get("/api/epis-cursos", headers=h).json() if x["id"] == m.curso.id)["dispensa_epi"] is True
    # desmarca, inclui um EPI e aí não deixa marcar de novo com a lista cheia
    c.put(f"/api/cursos/{m.curso.id}/epi-config", json={"dispensa_epi": False}, headers=h)
    assert c.post(f"/api/cursos/{m.curso.id}/epis", json={"nome": "Luva"}, headers=h).status_code == 200
    r = c.put(f"/api/cursos/{m.curso.id}/epi-config", json={"dispensa_epi": True}, headers=h)
    assert r.status_code == 422 and "retire" in r.text
