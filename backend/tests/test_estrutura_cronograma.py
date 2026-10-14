"""Unidades e áreas fixas da instituição; área nos cadastros; cronograma (Gantt) com caminho crítico."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.estrutura import AREAS, UNIDADES, garantir_estrutura_fixa
from app.models import Area, Turma, Unidade
from app.services import alocacao as aloc
from app.services.cronograma import cronograma
from tests.conftest import SEG, aula


@pytest.fixture
def cli(db, mundo):
    from app.main import app
    c = TestClient(app)
    c.headers["Authorization"] = "Bearer " + c.post("/api/auth/login", json={"email": "admin@teste", "senha": "senha-forte-1"}).json()["token"]
    garantir_estrutura_fixa(db)
    db.commit()
    return c


def test_estrutura_fixa_criada_e_protegida(db, cli):
    assert {u.codigo for u in db.scalars(select(Unidade))} >= {c for c, _ in UNIDADES}
    assert len(db.scalars(select(Area)).all()) == len(AREAS) == 11
    garantir_estrutura_fixa(db)  # idempotente
    assert len(db.scalars(select(Area)).all()) == 11
    porto = db.scalar(select(Unidade).where(Unidade.codigo == "PORTO"))
    area = db.scalar(select(Area).where(Area.codigo == "LOGISTICA"))
    for metodo, url, corpo in [("post", "/api/cadastros/unidades", {"codigo": "NOVA", "nome": "Nova", "situacao": "ativa", "ativo": True}),
                               ("post", "/api/cadastros/areas", {"codigo": "X", "nome": "X", "unidade_id": porto.id, "ativo": True}),
                               ("put", f"/api/cadastros/unidades/{porto.id}", {"nome": "Outro nome"}),
                               ("put", f"/api/cadastros/areas/{area.id}", {"nome": "OUTRA"}),
                               ("post", f"/api/cadastros/unidades/{porto.id}/inativar", {}),
                               ("delete", f"/api/cadastros/areas/{area.id}", None)]:
        r = getattr(cli, metodo)(url, json=corpo) if corpo is not None else getattr(cli, metodo)(url)
        assert r.status_code == 409 and r.json()["codigo"] == "ESTRUTURA_FIXA", (url, r.text)
    # dados não estruturais da unidade continuam editáveis
    assert cli.put(f"/api/cadastros/unidades/{porto.id}", json={"endereco": "Av. do Porto, 100"}).status_code == 200
    meta = {m["chave"]: m for m in cli.get("/api/meta/entidades").json()}
    assert meta["unidades"]["fixa"] and meta["areas"]["fixa"] and not meta["areas"]["inativavel"]
    assert next(c for c in meta["turmas"]["campos"] if c["nome"] == "area_id")["obrigatorio"]


def test_area_obrigatoria_e_da_mesma_unidade(db, cli, mundo):
    m = mundo
    beira = db.scalar(select(Unidade).where(Unidade.codigo == "BEIRA-MAR"))
    autom = db.scalar(select(Area).where(Area.codigo == "AUTOMACAO"))
    logist = db.scalar(select(Area).where(Area.codigo == "LOGISTICA"))
    base = {"matricula": "X1", "nome": "Instrutor X", "unidade_id": beira.id, "carga_horaria_contratual": 40, "limite_ch_letiva": 20,
            "max_horas_dia": 8, "intervalo_minimo_h": 11, "situacao": "ativo", "ativo": True}
    assert cli.post("/api/cadastros/instrutores", json=base).status_code == 422  # sem área
    r = cli.post("/api/cadastros/instrutores", json={**base, "area_id": logist.id})  # área de outra unidade
    assert r.status_code == 409 and "pertence" in r.json()["erro"]
    assert cli.post("/api/cadastros/instrutores", json={**base, "area_id": autom.id}).status_code == 200
    # curso sem unidade assume a unidade da área; turma herda a área do curso
    c = cli.post("/api/cadastros/cursos", json={"codigo": "CX", "nome": "Curso X", "area_id": autom.id, "situacao": "ativo", "ativo": True}).json()
    assert c["unidade_id"] == beira.id
    mat = cli.post("/api/cadastros/matrizes", json={"curso_id": c["id"], "versao": "1", "situacao": "vigente", "ativo": True}).json()
    t = cli.post("/api/cadastros/turmas", json={"codigo": "TX", "nome": "Turma X", "curso_id": c["id"], "matriz_id": mat["id"], "unidade_id": beira.id,
                                              "qtd_alunos": 20, "data_inicio": "2026-08-03", "data_fim": "2026-12-18", "dias_possiveis": [0, 1, 2, 3, 4],
                                              "num_grupos": 1, "prioridade": 3, "necessidades_acessibilidade": False, "situacao": "planejada", "ativo": True})
    assert t.status_code == 200, t.text
    assert t.json()["area_id"] == autom.id
    opcoes = cli.get("/api/cadastros/areas/opcoes").json()
    assert {o["unidade_id"] for o in opcoes} == {beira.id, db.scalar(select(Unidade.id).where(Unidade.codigo == "PORTO"))}


def test_cronograma_folga_e_caminho_critico(db, cli, mundo):
    m = mundo
    autom = db.scalar(select(Area).where(Area.codigo == "AUTOMACAO"))
    m.curso.area_id = autom.id
    # A termina em 2 semanas; B termina depois (define o fim da turma); C não tem horário (projetada)
    for k in range(2):
        aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, d=SEG + timedelta(days=7 * k), instrutor=m.i1, ambiente=m.s1))
    for k in range(4):
        aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_b, d=SEG + timedelta(days=7 * k + 1), instrutor=m.i1, ambiente=m.s1))
    db.commit()
    r = cronograma(db, m.cen.id, curso_id=m.curso.id, hoje=date(2026, 8, 1))
    por_id = {i["id"]: i for i in r["itens"]}
    t1 = por_id[f"t:{m.t1.id}"]
    ucs = {i["codigo"]: i for i in r["itens"] if i["tipo"] == "uc" and i["pai"] == t1["id"]}
    assert ucs["A"]["fim"] < ucs["B"]["fim"] and ucs["A"]["sem_horario"]  # A ainda tem carga sem horário (40 h)
    assert ucs["C"]["sem_horario"] and ucs["C"]["inicio"] >= "2026-08-01"
    assert por_id[f"a:{autom.id}"]["nome"] == "AUTOMAÇÃO" and por_id[f"c:{m.curso.id}"]["pai"] == f"a:{autom.id}"
    caminho = [c for c, i in ucs.items() if i["caminho_critico"]]
    assert caminho and all(ucs[c]["fim"] == t1["fim"] for c in caminho)
    for i in ucs.values():
        assert i["folga_dias"] == (date.fromisoformat(i["limite"]) - date.fromisoformat(i["fim"])).days
        assert i["critico"] == (i["folga_dias"] <= r["limiar_folga_dias"])
    resp = cli.get(f"/api/cronograma?cenario_id={m.cen.id}&area_id={autom.id}")
    assert resp.status_code == 200 and resp.json()["resumo"]["turmas"] == 2


def test_importacao_com_area_e_unidades_fixas(db, cli, mundo):
    from app.models import Instrutor
    from app.services import importacao
    m = mundo
    csv_ = ("matricula;nome;unidade;area\nM1;Ana;BEIRA-MAR;Automação\nM2;Bia;BEIRA-MAR;LOGÍSTICA\nM3;Caio;PORTO;dds/ti\nM4;Duda;PORTO;\n").encode()
    imp = importacao.gerar_previa(db, m.ctx, "instrutores.csv", csv_, tipo="instrutores")
    db.commit()
    itens = imp.previa["itens"]
    assert [i["acao"] for i in itens] == ["criar", "erro", "criar", "criar"]
    assert "não pertence à unidade" in itens[1]["erros"][0]
    assert any("área não informada" in a for a in itens[3].get("avisos", []))
    importacao.confirmar(db, m.ctx, imp.id, ignorar_erros=True)
    db.commit()
    ana = db.scalar(select(Instrutor).where(Instrutor.matricula == "M1"))
    assert db.get(Area, ana.area_id).codigo == "AUTOMACAO"
    # unidades: não se cria nova pela importação
    imp2 = importacao.gerar_previa(db, m.ctx, "unidades.csv", "codigo;nome\nNOVA;Unidade Nova\nPORTO;Unidade Porto\n".encode(), tipo="unidades")
    db.commit()
    assert [i["acao"] for i in imp2.previa["itens"]][0] == "erro"
