"""Mesmo curso (mesma sigla) com versões por público — PAGANTE, SEDU, AIT…: cada versão com a sua lista de UCs e a turma
escolhendo a versão dela; a planilha de estrutura curricular cria as versões pela coluna Público / versão do curso."""
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.estrutura import garantir_estrutura_fixa
from app.main import app
from app.models import Area, Curso, MatrizCurricular, Turma, TurmaUC, UnidadeCurricular, Unidade


def _h(c):
    return {"Authorization": "Bearer " + c.post("/api/auth/login", json={"email": "admin@teste", "senha": "senha-forte-1"}).json()["token"]}


def test_versoes_por_publico_e_turma(db, mundo):
    garantir_estrutura_fixa(db)
    db.commit()
    c = TestClient(app)
    h = _h(c)
    bm = db.scalar(select(Unidade).where(Unidade.codigo == "BEIRA-MAR"))
    energ = db.scalar(select(Area).where(Area.unidade_id == bm.id, Area.codigo == "ENERGIAS"))
    curso = c.post("/api/cadastros/cursos", json={"codigo": "ELT", "nome": "Técnico em Eletrotécnica", "area_id": energ.id}, headers=h).json()
    ids = {}
    for publico, ucs in (("PAGANTE", ["FEL", "CMD"]), ("SEDU", ["FEL", "CMD", "PRJ"])):
        r = c.post("/api/cadastros/matrizes", json={"curso_id": curso["id"], "versao": "2026", "tipo_oferta": publico, "situacao": "rascunho"}, headers=h)
        assert r.status_code == 200, r.text  # mesma versão "2026", públicos diferentes
        ids[publico] = r.json()["id"]
        for k, cod in enumerate(ucs, 1):
            assert c.post("/api/cadastros/ucs", json={"matriz_id": ids[publico], "codigo": cod, "nome": f"UC {cod}", "carga_horaria_total": 40,
                                                       "sequencia": k}, headers=h).status_code == 200
    # a mesma versão para o mesmo público repete: recusada
    assert c.post("/api/cadastros/matrizes", json={"curso_id": curso["id"], "versao": "2026", "tipo_oferta": "SEDU"}, headers=h).status_code >= 400
    # turma SEDU: escolhe a versão; recebe as 3 UCs dela e o nome indica o público
    manha = c.get("/api/cadastros/turnos/opcoes", headers=h).json()
    turno = next(t["id"] for t in manha if "Matutino" in t["rotulo"] and "Beira" in t["rotulo"]) if manha else None
    # sem escolher o público: recusada (cada público tem o seu desenho curricular)
    r = c.post("/api/cadastros/turmas", json={"curso_id": curso["id"], "_numero": "11", "_tipo_oferta": "HTC", "turno_id": turno,
                                              "qtd_alunos": 30, "data_inicio": "2026-08-03", "data_fim": "2026-12-18"}, headers=h)
    assert r.status_code == 422 and "público" in r.json()["erro"]
    r = c.post("/api/cadastros/turmas", json={"curso_id": curso["id"], "matriz_id": ids["SEDU"], "_numero": "12", "_tipo_oferta": "HTC",
                                              "turno_id": turno, "qtd_alunos": 30, "data_inicio": "2026-08-03", "data_fim": "2026-12-18"}, headers=h)
    assert r.status_code == 200, r.text
    t = db.get(Turma, r.json()["id"])
    assert t.codigo == "HTC-ELT-12" and t.matriz_id == ids["SEDU"] and "SEDU" in t.nome
    assert db.query(TurmaUC).filter(TurmaUC.turma_id == t.id).count() == 3


def test_planilha_cria_versao_por_publico(db, mundo):
    from app.services import importacao
    garantir_estrutura_fixa(db)
    db.commit()
    m = mundo
    csv_ = ("Código do curso;Nome do curso;Área;Versão da matriz;Público / versão do curso;Código da UC;Nome da UC;Carga horária da UC (h)\n"
            "ELT;Técnico em Eletrotécnica;ENERGIAS;2026;PAGANTE;FEL;Fundamentos;40\n"
            "ELT;Técnico em Eletrotécnica;ENERGIAS;2026;SEDU;FEL;Fundamentos;40\n"
            "ELT;Técnico em Eletrotécnica;ENERGIAS;2026;SEDU;PRJ;Projeto integrador;60\n").encode()
    imp = importacao.gerar_previa(db, m.ctx, "estrutura.csv", csv_, tipo="estrutura_curricular")
    db.commit()
    assert [i["acao"] for i in imp.previa["itens"]] == ["criar", "criar", "criar"], imp.previa["itens"]
    importacao.confirmar(db, m.ctx, imp.id)
    db.commit()
    curso = db.scalar(select(Curso).where(Curso.codigo == "ELT"))
    ms = {x.tipo_oferta: x for x in db.scalars(select(MatrizCurricular).where(MatrizCurricular.curso_id == curso.id))}
    assert set(ms) == {"PAGANTE", "SEDU"}
    n = {k: db.query(UnidadeCurricular).filter(UnidadeCurricular.matriz_id == v.id).count() for k, v in ms.items()}
    assert n == {"PAGANTE": 1, "SEDU": 2}


def test_importar_turma_sem_versao_e_sem_inicio(db, mundo):
    """Sem a versão da matriz: a vigente do curso; sem o início: o do semestre (com aviso). Sem término continua erro."""
    from app.services import importacao
    m = mundo
    m.matriz.situacao = "vigente"
    db.commit()
    csv_ = ("Código da turma;Nome da turma;Código do curso;Versão da matriz;Público / versão do curso;Unidade;Turno;Alunos;Início;Término\n"
            "T-NOVA;Turma nova;C1;;;U1;;20;;10/12/2026\n"
            "T-SEMFIM;Turma sem fim;C1;;;U1;;20;;\n").encode()
    imp = importacao.gerar_previa(db, m.ctx, "turmas.csv", csv_, tipo="turmas")
    db.commit()
    itens = {i["dados"].get("codigo") if i.get("dados") else i["linha"]: i for i in imp.previa["itens"]}
    nova = next(i for i in imp.previa["itens"] if i["acao"] == "criar")
    assert any("início do semestre (03/08/2026)" in a for a in nova["avisos"]) and any("usada a 1" in a for a in nova["avisos"])
    sem_fim = next(i for i in imp.previa["itens"] if i["acao"] == "erro")
    assert any(e.startswith("Término: obrigatório") for e in sem_fim["erros"])
    assert len(itens) == 2
