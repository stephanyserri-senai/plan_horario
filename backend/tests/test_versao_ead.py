"""Versão da matriz: em rascunho a lista de UCs é montada; depois de cadastrada ela fica fixa (mudanças só numa nova versão).
UC presencial ou EAD: EAD só nos cursos que preveem EAD, e a UC EAD fica fora da grade e da demanda."""
from fastapi.testclient import TestClient

from app.main import app
from app.services import otimizacao


def _cli():
    c = TestClient(app)
    tok = c.post("/api/auth/login", json={"email": "admin@teste", "senha": "senha-forte-1"}).json()["token"]
    c.headers.update({"Authorization": f"Bearer {tok}"})
    return c


def test_lista_de_ucs_fixa_na_versao_cadastrada(db, mundo):
    m = mundo
    c = _cli()
    m.matriz.situacao = "vigente"
    db.commit()
    # versão cadastrada: não inclui, não retira e não muda nome/carga; o resto (ordem, dias por semana) pode
    r = c.post("/api/cadastros/ucs", json={"matriz_id": m.matriz.id, "codigo": "NOVA", "nome": "UC nova", "carga_horaria_total": 20})
    assert r.status_code == 409 and r.json()["codigo"] == "VERSAO_CADASTRADA"
    uc = c.get(f"/api/cadastros/ucs/{m.uc_a.id}").json()
    r = c.put(f"/api/cadastros/ucs/{m.uc_a.id}", json={**uc, "nome": "Outro nome"})
    assert r.status_code == 409 and r.json()["codigo"] == "VERSAO_CADASTRADA"
    r = c.put(f"/api/cadastros/ucs/{m.uc_a.id}", json={**uc, "carga_horaria_total": uc["carga_horaria_total"] + 10})
    assert r.status_code == 409
    r = c.put(f"/api/cadastros/ucs/{m.uc_a.id}", json={**uc, "sequencia": 9, "encontros_semanais": 3})
    assert r.status_code == 200, r.text
    r = c.post(f"/api/cadastros/ucs/{m.uc_a.id}/inativar", json={"motivo": "teste"})
    assert r.status_code == 409 and r.json()["codigo"] == "VERSAO_CADASTRADA"
    # não volta a rascunho
    mat = c.get(f"/api/cadastros/matrizes/{m.matriz.id}").json()
    r = c.put(f"/api/cadastros/matrizes/{m.matriz.id}", json={**mat, "situacao": "rascunho"})
    assert r.status_code == 409 and r.json()["codigo"] == "VERSAO_CADASTRADA"
    # nova versão: copia as UCs, nasce em rascunho e pode ser ajustada; depois de concluída, fica fixa
    nova = c.post(f"/api/cadastros/matrizes/{m.matriz.id}/nova_versao", json={"versao": "2027", "tipo_oferta": "AIT"}).json()
    assert nova["situacao"] == "rascunho"
    ucs = c.get(f"/api/estrutura-curricular/versoes/{nova['id']}").json()["ucs"]
    assert {u["codigo"] for u in ucs} == {m.uc_a.codigo, m.uc_b.codigo, m.uc_c.codigo}
    r = c.post("/api/cadastros/ucs", json={"matriz_id": nova["id"], "codigo": "NOVA", "nome": "UC nova", "carga_horaria_total": 20})
    assert r.status_code == 200, r.text
    u0 = c.get(f"/api/cadastros/ucs/{ucs[0]['id']}").json()
    assert c.put(f"/api/cadastros/ucs/{u0['id']}", json={**u0, "nome": "Nome ajustado"}).status_code == 200
    assert c.post(f"/api/cadastros/ucs/{ucs[1]['id']}/inativar", json={"motivo": "fora da AIT"}).status_code == 200
    mat = c.get(f"/api/cadastros/matrizes/{nova['id']}").json()
    assert c.put(f"/api/cadastros/matrizes/{nova['id']}", json={**mat, "situacao": "vigente"}).status_code == 200
    r = c.post("/api/cadastros/ucs", json={"matriz_id": nova["id"], "codigo": "OUTRA", "nome": "Outra", "carga_horaria_total": 20})
    assert r.status_code == 409
    # a versão antiga ficou intacta
    antigas = c.get(f"/api/estrutura-curricular/versoes/{m.matriz.id}").json()["ucs"]
    assert len(antigas) == 3 and "NOVA" not in {u["codigo"] for u in antigas}


def test_uc_ead_so_em_curso_que_preve_ead_e_fora_da_grade(db, mundo):
    m = mundo
    c = _cli()
    m.matriz.situacao = "rascunho"
    db.commit()
    corpo = {"matriz_id": m.matriz.id, "codigo": "EADX", "nome": "UC a distância", "carga_horaria_total": 20, "modalidade": "ead"}
    r = c.post("/api/cadastros/ucs", json=corpo)
    assert r.status_code == 409 and "não prevê EAD" in r.json()["erro"]
    curso = c.get(f"/api/cadastros/cursos/{m.curso.id}").json()
    assert c.put(f"/api/cadastros/cursos/{m.curso.id}", json={**curso, "preve_ead": True}).status_code == 200
    r = c.post("/api/cadastros/ucs", json=corpo)
    assert r.status_code == 200, r.text
    assert r.json()["modalidade"] == "ead"
    # com UC EAD cadastrada, o curso não pode deixar de prever EAD
    curso = c.get(f"/api/cadastros/cursos/{m.curso.id}").json()
    assert c.put(f"/api/cadastros/cursos/{m.curso.id}", json={**curso, "preve_ead": False}).status_code == 409
    lista = {u["codigo"]: u for u in c.get("/api/estrutura-curricular/ucs").json()}
    assert lista["EADX"]["modalidade"] == "ead" and lista["EADX"]["preve_ead"]
    # a UC A passa a ser EAD: sai do gerador
    ucs_antes = {t.uc_id for t in otimizacao.turma_ucs_do_escopo(db, m.cen, {"tipo": "instituicao"})}
    assert m.uc_a.id in ucs_antes
    ua = c.get(f"/api/cadastros/ucs/{m.uc_a.id}").json()
    assert c.put(f"/api/cadastros/ucs/{m.uc_a.id}", json={**ua, "modalidade": "ead"}).status_code == 200
    db.expire_all()
    ucs_depois = {t.uc_id for t in otimizacao.turma_ucs_do_escopo(db, m.cen, {"tipo": "instituicao"})}
    assert m.uc_a.id not in ucs_depois and m.uc_b.id in ucs_depois
