"""Importação (16, 17), autorização (18) e API de ponta a ponta."""
import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import func, select

from app.core.errors import ConflitoValidacao
from app.core.security import hash_senha
from app.main import app
from app.models import Alocacao, Ambiente, HistoricoAuditoria, Instrutor, PermissaoEscopo, Unidade, Usuario
from app.services import importacao


def xlsx(linhas: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for l in linhas:
        ws.append(l)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def test_16_importacao_duplicada_nao_duplica(db, mundo):
    m = mundo
    arq = xlsx([["Matrícula", "Nome do instrutor", "Unidade", "CH contratual", "CH letiva"],
                ["X100", "Fulano", "U1", 40, 20], ["X101", "Beltrano", "U1", 40, 30]])
    imp = importacao.gerar_previa(db, m.ctx, "instrutores.xlsx", arq)
    assert imp.tipo == "instrutores"  # estrutura identificada automaticamente
    assert imp.previa["resumo"]["criar"] == 2
    importacao.confirmar(db, m.ctx, imp.id)
    db.commit()
    total = db.scalar(select(func.count()).select_from(Instrutor))
    # mesmo arquivo novamente: detectado como já processado, nada é duplicado
    imp2 = importacao.gerar_previa(db, m.ctx, "instrutores.xlsx", arq)
    assert imp2.previa["arquivo_ja_processado"]["importacao_id"] == imp.id
    assert imp2.previa["resumo"] == {"criar": 0, "atualizar": 0, "sem_alteracao": 2, "erro": 0}
    importacao.confirmar(db, m.ctx, imp2.id)
    db.commit()
    assert db.scalar(select(func.count()).select_from(Instrutor)) == total
    # duplicidade dentro do mesmo arquivo é apontada
    dup = xlsx([["matricula", "nome", "unidade"], ["X200", "A", "U1"], ["X200", "A de novo", "U1"]])
    imp3 = importacao.gerar_previa(db, m.ctx, "dup.xlsx", dup, tipo="instrutores")
    assert imp3.previa["itens"][1]["acao"] == "erro" and "duplicado" in imp3.previa["itens"][1]["erros"][0]
    # alteração incremental (atualizar) quando o dado muda
    arq_mod = xlsx([["Matrícula", "Nome do instrutor", "Unidade", "CH contratual", "CH letiva"], ["X100", "Fulano de Tal", "U1", 40, 20]])
    imp4 = importacao.gerar_previa(db, m.ctx, "mod.xlsx", arq_mod)
    assert imp4.previa["resumo"]["atualizar"] == 1


def test_17_importacao_com_referencias_invalidas(db, mundo):
    m = mundo
    csv_ = "codigo;nome;unidade;tipo;capacidade\nA9;Sala nova;U1;SALA;30\nA10;Sala fantasma;UX;SALA;30\nA11;Lab;U1;INEXISTENTE;20\n".encode()
    imp = importacao.gerar_previa(db, m.ctx, "ambientes.csv", csv_, tipo="ambientes")
    db.commit()
    acoes = [i["acao"] for i in imp.previa["itens"]]
    assert acoes == ["criar", "erro", "criar"]  # tipo de sala inexistente é criado (com aviso na prévia)
    assert "unidade 'UX'" in imp.previa["itens"][1]["erros"][0]
    assert any("será criado" in a for a in imp.previa["itens"][2]["avisos"])
    with pytest.raises(ConflitoValidacao):
        importacao.confirmar(db, m.ctx, imp.id)
    db.rollback()
    rel = importacao.confirmar(db, m.ctx, imp.id, ignorar_erros=True)
    db.commit()
    assert rel["criados"] == 2 and rel["ignorados_por_erro"] == 1
    assert db.scalar(select(func.count()).select_from(Ambiente).where(Ambiente.codigo == "A9")) == 1


def test_importacao_de_aulas_passa_pela_validacao(db, mundo):
    m = mundo
    arq = xlsx([["Turma", "UC", "Instrutor matricula", "Sala", "Data", "Início", "Fim"],
                ["T1", "A", "I1", "S1", "03/08/2026", "07:30", "09:10"],
                ["T2", "A", "I1", "S2", "03/08/2026", "07:30", "09:10"]])  # mesmo instrutor no mesmo horário
    imp = importacao.gerar_previa(db, m.ctx, "grade_manha.xlsx", arq, tipo="aulas", cenario_id=m.cen.id)
    assert imp.previa["resumo"]["criar"] == 2
    rel = importacao.confirmar(db, m.ctx, imp.id)
    db.commit()
    assert rel["criados"] == 1 and len(rel["aulas_bloqueadas"]) == 1
    assert db.scalar(select(func.count()).select_from(Alocacao)) == 1


@pytest.fixture
def cliente(mundo):
    return TestClient(app)


def login(c, email, senha):
    r = c.post("/api/auth/login", json={"email": email, "senha": senha})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_18_alteracao_sem_autorizacao(db, mundo, cliente):
    m = mundo
    db.add(Usuario(nome="Consulta", email="consulta@teste", senha_hash=hash_senha("senha-forte-2"), perfil="observador"))
    outra = Unidade(codigo="U2", nome="Outra")
    db.add(outra)
    db.flush()
    plan = Usuario(nome="Planejador U2", email="plan2@teste", senha_hash=hash_senha("senha-forte-3"), perfil="planejador")
    db.add(plan)
    db.flush()
    db.add(PermissaoEscopo(usuario_id=plan.id, escopo_tipo="unidade", escopo_id=outra.id))
    db.commit()
    h = login(cliente, "consulta@teste", "senha-forte-2")
    tuc = m.tuc(db, m.t1, m.uc_a)
    corpo = {"cenario_id": m.cen.id, "turma_uc_id": tuc.id, "data": "2026-08-03", "periodo_inicio_id": m.periodos[0].id, "num_periodos": 2,
             "instrutor_id": m.i1.id, "ambiente_id": m.s1.id}
    r = cliente.post("/api/alocacoes", json=corpo, headers=h)
    assert r.status_code == 403
    assert cliente.post("/api/cadastros/unidades", json={"codigo": "Z", "nome": "Z"}, headers=h).status_code == 403
    assert cliente.get("/api/cadastros/unidades", headers=h).status_code == 200
    # planejador de outra unidade não altera turmas fora do escopo
    h2 = login(cliente, "plan2@teste", "senha-forte-3")
    r = cliente.post("/api/alocacoes", json=corpo, headers=h2)
    assert r.status_code == 403
    lista = cliente.get("/api/cadastros/ambientes", headers=h2).json()
    assert lista["total"] == 0  # não enxerga ambientes da U1
    assert cliente.get("/api/cadastros/unidades", headers={"Authorization": "Bearer invalido"}).status_code == 401
    assert db.scalar(select(func.count()).select_from(Alocacao)) == 0


def test_api_fluxo_completo(db, mundo, cliente):
    m = mundo
    h = login(cliente, "admin@teste", "senha-forte-1")
    assert cliente.post("/api/auth/login", json={"email": "admin@teste", "senha": "errada"}).status_code == 403
    meta = cliente.get("/api/meta/entidades", headers=h).json()
    assert any(e["chave"] == "turmas" for e in meta)
    # cadastro: criar, editar, histórico, inativar
    r = cliente.post("/api/cadastros/tipos_ambiente", json={"codigo": "OFI", "nome": "Oficina"}, headers=h)
    assert r.status_code == 200, r.text
    tid = r.json()["id"]
    assert cliente.post("/api/cadastros/tipos_ambiente", json={"codigo": "OFI", "nome": "Dup"}, headers=h).status_code == 409
    cliente.put(f"/api/cadastros/tipos_ambiente/{tid}", json={"nome": "Oficina mecânica"}, headers=h)
    hist = cliente.get(f"/api/cadastros/tipos_ambiente/{tid}/historico", headers=h).json()
    assert [x["acao"] for x in hist] == ["cadastro.alterar", "cadastro.criar"]
    assert cliente.post(f"/api/cadastros/tipos_ambiente/{tid}/inativar", json={}, headers=h).json()["ativo"] is False
    busca = cliente.get("/api/cadastros/ambientes?q=Sala&unidade_id=%d" % m.unidade.id, headers=h).json()
    assert busca["total"] == 2
    # alocação com conflito retorna 409, ocorrências e alternativas
    tuc = m.tuc(db, m.t1, m.uc_a)
    corpo = {"cenario_id": m.cen.id, "turma_uc_id": tuc.id, "data": "2026-08-03", "periodo_inicio_id": m.periodos[0].id, "num_periodos": 2,
             "instrutor_id": m.i1.id, "ambiente_id": m.s1.id}
    r = cliente.post("/api/alocacoes", json=corpo, headers=h)
    assert r.status_code == 200, r.text
    corpo2 = {**corpo, "turma_uc_id": m.tuc(db, m.t2, m.uc_a).id, "instrutor_id": m.i2.id}
    r = cliente.post("/api/alocacoes", json=corpo2, headers=h)
    assert r.status_code == 409
    j = r.json()
    assert j["codigo"] == "RESTRICAO_OBRIGATORIA" and j["detalhes"]["ocorrencias"] and "alternativas" in j["detalhes"]
    assert db.scalar(select(func.count()).select_from(HistoricoAuditoria).where(HistoricoAuditoria.acao == "alocacao.bloqueada")) == 1
    g = cliente.get(f"/api/grade?cenario_id={m.cen.id}&inicio=2026-08-03&fim=2026-08-09", headers=h).json()
    assert len(g) == 1 and g[0]["turma"] == "T1"
    for fmt, tipo in (("xlsx", "spreadsheet"), ("csv", "text/csv"), ("pdf", "pdf")):
        r = cliente.get(f"/api/exportar/grade?cenario_id={m.cen.id}&formato={fmt}", headers=h)
        assert r.status_code == 200 and tipo in r.headers["content-type"]
    r = cliente.get(f"/api/exportar/grade?cenario_id={m.cen.id}&formato=pdf&semana=2026-08-03&filtro=turma&filtro_id={m.t1.id}", headers=h)
    assert r.status_code == 200
    ind = cliente.get(f"/api/indicadores/institucionais?cenario_id={m.cen.id}", headers=h).json()
    assert ind["conflitos_bloqueados"] == 1
    assert cliente.get(f"/api/gargalos?cenario_id={m.cen.id}", headers=h).status_code == 200
    r = cliente.get(f"/api/recomendacoes/nao_alocacao?cenario_id={m.cen.id}&turma_uc_id={m.tuc(db, m.t2, m.uc_a).id}", headers=h)
    assert r.status_code == 200 and r.json()["alternativas"]
    r = cliente.post("/api/otimizacao/executar", json={"cenario_id": m.cen.id, "escopo": {"tipo": "turma", "ids": [m.t2.id]}, "sincrono": True,
                                                       "limite_tempo_s": 15}, headers=h)
    eid = r.json()["execucao_id"]
    ex = cliente.get(f"/api/otimizacao/execucoes/{eid}", headers=h).json()
    assert ex["status"] == "concluida" and ex["status_solver"] in ("OTIMA", "VIAVEL") and ex["pontuacao_por_criterio"]
    aud = cliente.get("/api/auditoria?acao=otimizacao", headers=h).json()
    assert aud["total"] >= 2
