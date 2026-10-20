"""Índice de aderência do instrutor (curso, área, geral) e PDI."""
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Area, CompetenciaInstrutor, Curso, InstrutorArea, MatrizCurricular, UnidadeCurricular
from app.services import aderencia


def _login(c):
    return {"Authorization": "Bearer " + c.post("/api/auth/login", json={"email": "admin@teste", "senha": "senha-forte-1"}).json()["token"]}


def _area(db, m, codigo="ENE"):
    a = Area(codigo=codigo, nome=f"Área {codigo}", unidade_id=m.unidade.id, ativo=True)
    db.add(a)
    db.flush()
    return a


def _mundo_com_area(db, m):
    area = _area(db, m)
    db.get(Curso, m.curso.id).area_id = area.id
    for i in (m.i1, m.i2, m.i3):
        i.area_id = area.id
    db.get(MatrizCurricular, m.matriz.id).situacao = "vigente"
    db.commit()
    return area


def test_indice_por_curso_pela_carga_horaria(db, mundo):
    m = mundo
    _mundo_com_area(db, m)
    # A = 40 h, B = 40 h, C = 20 h; I1 dá A e B → 80%; I2 dá A e C → 60%; I3 nada
    assert aderencia.indice(db, m.i1.id)["geral"] == 80.0
    assert aderencia.indice(db, m.i2.id)["geral"] == 60.0
    assert aderencia.indice(db, m.i3.id)["geral"] == 0.0
    # "em partes" vale metade
    c = db.scalar(select(CompetenciaInstrutor).where(CompetenciaInstrutor.instrutor_id == m.i2.id, CompetenciaInstrutor.uc_id == m.uc_c.id))
    c.nivel = "parcial"
    db.commit()
    ind = aderencia.indice(db, m.i2.id)
    assert ind["geral"] == 50.0 and ind["areas"][0]["cursos"][0]["ucs_em_partes"] == 1


def test_certificacao_e_transversal(db, mundo):
    m = mundo
    _mundo_com_area(db, m)
    db.get(UnidadeCurricular, m.uc_c.id).certificacao_exigida = "NR-10"
    db.get(UnidadeCurricular, m.uc_b.id).categoria = "transversal"
    db.commit()
    # sem a NR-10, C ainda não conta para I2; B transversal sai do cálculo (A 40 + C 20)
    ind = aderencia.indice(db, m.i2.id)
    assert round(ind["geral"], 1) == round(100 * 40 / 60, 1)
    uc_c = next(u for u in ind["areas"][0]["cursos"][0]["ucs"] if u["codigo"] == "C")
    assert uc_c["situacao"] == "sem_certificacao" and ind["areas"][0]["cursos"][0]["transversais"] == 1
    p = aderencia.propostas(db, m.i2.id)
    assert [(i["uc_codigo"], i["tipo"]) for i in p["itens"]] == [("C", "certificacao")]


def test_varias_areas_e_indice_geral(db, mundo):
    m = mundo
    _mundo_com_area(db, m)
    outra = _area(db, m, "AUT")
    curso2 = Curso(codigo="C2", nome="Curso 2", unidade_id=m.unidade.id, area_id=outra.id)
    db.add(curso2)
    db.flush()
    mat = MatrizCurricular(curso_id=curso2.id, versao="1", situacao="vigente")
    db.add(mat)
    db.flush()
    db.add(UnidadeCurricular(matriz_id=mat.id, codigo="X", nome="UC X", carga_horaria_total=100, duracao_bloco_periodos=2, encontros_semanais=1))
    db.add(InstrutorArea(instrutor_id=m.i1.id, area_id=outra.id))
    db.commit()
    ind = aderencia.indice(db, m.i1.id)
    assert ind["multiarea"] and [a["pct"] for a in ind["areas"]] == [80.0, 0.0]
    assert ind["geral"] == 40.0  # 80 h de 200 h nas duas áreas


def test_pdi_incluir_e_concluir_habilita(db, mundo):
    m = mundo
    _mundo_com_area(db, m)
    c = TestClient(app)
    h = _login(c)
    r = c.get(f"/api/instrutores/{m.i1.id}/pdi", headers=h).json()
    assert [i["uc_codigo"] for i in r["itens"]] == ["C"] and r["projecao"][0]["hoje"] == 80.0
    it = r["itens"][0]
    r = c.post(f"/api/instrutores/{m.i1.id}/pdi", json={"itens": [{"curso_id": it["curso_id"], "uc_codigo": "C", "tipo": "uc", "prazo": it["prazo_sugerido"]}]}, headers=h)
    assert r.status_code == 200 and r.json()["incluidos"] == 1
    pid = r.json()["salvo"][0]["id"]
    # repetir não duplica
    assert c.post(f"/api/instrutores/{m.i1.id}/pdi", json={"curso_id": it["curso_id"], "uc_codigo": "C", "tipo": "uc"}, headers=h).json()["incluidos"] == 0
    assert c.get(f"/api/instrutores/{m.i1.id}/pdi", headers=h).json()["itens"][0]["no_pdi"] is True
    r = c.put(f"/api/pdi/{pid}", json={"situacao": "concluido", "habilitar": True}, headers=h)
    assert r.status_code == 200 and r.json()["habilitou"] == ["C"] and r.json()["geral"] == 100.0
    assert db.scalar(select(CompetenciaInstrutor.nivel).where(CompetenciaInstrutor.instrutor_id == m.i1.id, CompetenciaInstrutor.uc_id == m.uc_c.id)) == "pleno"
    perfil = c.get(f"/api/instrutores/{m.i1.id}/perfil?cenario_id={m.cen.id}", headers=h).json()
    assert perfil["aderencia"]["geral"] == 100.0 and perfil["pdi"][0]["situacao"] == "concluido" and perfil["semestre"]["aulas"] == 0
    e = c.get("/api/aderencia/equipe", headers=h).json()
    assert {x["instrutor_id"] for x in e["instrutores"]} >= {m.i1.id, m.i2.id} and e["cobertura"][0]["ucs"] == 3
    # cobertura: B só tem o I1 e C só o I2 (depois de concluído o PDI, C passa a ter o I1 também)
    cob = e["cobertura"][0]
    assert cob["duas_ou_mais"] + cob["um_so"] + cob["sem_ninguem"] == 3
    assert {(u["uc"], tuple(u["habilitados"])) for u in cob["criticas"]} == {("B", ("Instrutor 1",))}


def test_instrutor_basico_so_conta_cursos_basicos(db, mundo):
    m = mundo
    _mundo_com_area(db, m)
    db.get(Curso, m.curso.id).tipo = "Habilitação técnica"  # sem turma de oferta básica: curso técnico
    db.get(type(m.i1), m.i1.id).nivel = "basico"
    db.commit()
    ind = aderencia.indice(db, m.i1.id)
    assert ind["areas"][0]["cursos"] == [] and ind["areas"][0]["fora_do_nivel"] == ["C1"]
    assert aderencia.propostas(db, m.i1.id)["itens"] == []
    # qualificação: o básico entra
    db.get(Curso, m.curso.id).tipo = "Qualificação profissional"
    db.commit()
    assert aderencia.indice(db, m.i1.id)["geral"] == 80.0


def test_competencias_e_certificacoes_pelo_perfil(db, mundo):
    m = mundo
    _mundo_com_area(db, m)
    db.get(UnidadeCurricular, m.uc_c.id).certificacao_exigida = "NR-10"
    db.commit()
    c = TestClient(app)
    h = _login(c)
    cid = m.curso.id
    # I3 não dá nada: marca A como sim e B em partes → (40 + 20) / 100
    assert c.put(f"/api/instrutores/{m.i3.id}/competencias", json={"curso_id": cid, "uc_codigo": "A", "nivel": "pleno"}, headers=h).status_code == 200
    r = c.put(f"/api/instrutores/{m.i3.id}/competencias", json={"curso_id": cid, "uc_codigo": "B", "nivel": "parcial"}, headers=h).json()
    assert r["geral"] == 60.0
    # C exige NR-10: marcada sem a certificação não conta; registrada a certificação, conta
    assert c.put(f"/api/instrutores/{m.i3.id}/competencias", json={"curso_id": cid, "uc_codigo": "C", "nivel": "pleno"}, headers=h).json()["geral"] == 60.0
    x = c.put(f"/api/instrutores/{m.i3.id}/certificacoes", json={"nome": "NR-10", "valido_ate": "2027-12-31"}, headers=h).json()
    assert x["geral"] == 80.0
    perfil = c.get(f"/api/instrutores/{m.i3.id}/perfil", headers=h).json()
    cert = perfil["dados"]["certificacoes"][0]
    assert cert["nome"] == "NR-10" and cert["id"]
    uc_b = next(u for u in perfil["aderencia"]["areas"][0]["cursos"][0]["ucs"] if u["codigo"] == "B")
    assert uc_b["marcado"] == "parcial"
    # retirar a certificação não apaga (fica inativa) e o índice volta; "não" desmarca a UC
    assert c.post(f"/api/instrutores/{m.i3.id}/certificacoes/{cert['id']}/retirar", headers=h).json()["geral"] == 60.0
    assert c.put(f"/api/instrutores/{m.i3.id}/competencias", json={"curso_id": cid, "uc_codigo": "A", "nivel": "nenhum"}, headers=h).json()["geral"] == 20.0
    assert c.put(f"/api/instrutores/{m.i3.id}/competencias", json={"curso_id": cid, "uc_codigo": "X", "nivel": "pleno"}, headers=h).status_code == 422
