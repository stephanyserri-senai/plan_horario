"""Regras institucionais (dias da turma, sábado), UC transversal e competência "em partes",
solicitações do instrutor decididas pelo coordenador e o aceite automático de sugestões."""
from datetime import time, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import hash_senha
from app.main import app
from app.models import (Alocacao, Bloqueio, CompetenciaInstrutor, Notificacao, PeriodoHorario, RegistroDecisao, SolicitacaoInstrutor, Turno,
                        Usuario)
from app.services import alocacao as aloc
from app.services import regras_institucionais as ri
from app.services import solicitacoes, substituicao
from app.services.planejamento import instrutores_elegiveis
from tests.conftest import SEG, aula


def _login(c, email, senha):
    r = c.post("/api/auth/login", json={"email": email, "senha": senha})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_padrao_de_dias_da_turma():
    assert ri.erro_padrao_dias([0, 1, 2, 3, 4], [], "M", False) is None          # 5 presenciais
    assert ri.erro_padrao_dias([0, 1, 2, 3], [4], "N", False) is None            # 4 + 1 EAD (80-20)
    assert ri.erro_padrao_dias([5], [], "S", False) is None                      # sábado: só o sábado
    assert ri.erro_padrao_dias([0, 2, 4], [], "T", False)                        # 3 dias: só aperfeiçoamento/empresa
    assert ri.erro_padrao_dias([0, 2, 4], [], "T", True) is None
    assert ri.erro_padrao_dias([0, 1, 2, 3, 4, 5], [], "M", True)                # sábado só no turno de sábado
    assert ri.erro_padrao_dias([0, 1, 2, 3, 4], [], "S", False)                  # turma de sábado não usa a semana


def test_regras_documentadas_em_dia():
    """docs/REGRAS_DE_NEGOCIO.md é a memória das regras: tem de bater com o catálogo."""
    doc = Path(__file__).resolve().parents[2] / "docs" / "REGRAS_DE_NEGOCIO.md"
    assert doc.read_text(encoding="utf-8") == ri.para_markdown(), "rode: python scripts/gerar_regras_md.py"
    codigos = {r["codigo"] for r in ri.catalogo()}
    assert {"TURMA_DIAS", "TURMA_SABADO", "TURMA_FLEXIVEL", "TETO_90", "NIVEL", "UC_TRANSVERSAL", "SOLICITACOES", "SUGESTOES"} <= codigos


def test_cadastro_de_turma_segue_o_padrao_e_o_sabado(db, mundo):
    m = mundo
    sab = Turno(unidade_id=m.unidade.id, codigo="S", nome="Sábado", hora_inicio=time(9), hora_fim=time(13), ordem=4, ativo=True)
    db.add(sab)
    db.flush()
    db.add(PeriodoHorario(unidade_id=m.unidade.id, turno_id=sab.id, ordem=1, hora_inicio=time(9), hora_fim=time(13), dias_semana=[5], excepcional=False, ativo=True))
    from app.models import Area
    area = Area(codigo="TST", nome="TESTE", unidade_id=m.unidade.id, ativo=True)
    db.add(area)
    db.flush()
    m.curso.area_id = area.id
    db.commit()
    c = TestClient(app)
    h = _login(c, "admin@teste", "senha-forte-1")
    base = {"curso_id": m.curso.id, "matriz_id": m.matriz.id, "turno_id": m.manha.id, "qtd_alunos": 20, "data_inicio": "2026-08-03",
            "data_fim": "2026-12-18"}
    r = c.post("/api/cadastros/turmas", json={**base, "_numero": "90", "_tipo_oferta": "HTC", "dias_possiveis": [0, 2, 4]}, headers=h)
    assert r.status_code == 422 and "5 dias presenciais" in r.text
    r = c.post("/api/cadastros/turmas", json={**base, "_numero": "91", "_tipo_oferta": "EMP", "dias_possiveis": [0, 2, 4]}, headers=h)
    assert r.status_code == 200, r.text  # turma para empresa pode ter menos dias
    r = c.post("/api/cadastros/turmas", json={**base, "_numero": "92", "_tipo_oferta": "HTC", "turno_id": sab.id, "dias_possiveis": [0, 1, 2, 3, 4]}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["dias_possiveis"] == [5] and r.json()["dias_ead"] == []  # sábado: só o sábado é presencial
    assert c.get("/api/regras", headers=h).status_code == 200


def test_uc_transversal_e_competencia_em_partes(db, mundo):
    m = mundo
    # i3 não tem a UC A: com a UC técnica não é elegível; transversal, qualquer instrutor da unidade é
    tem = {c.instrutor_id for c in db.scalars(select(CompetenciaInstrutor).where(CompetenciaInstrutor.uc_id == m.uc_a.id))}
    sem = next(i for i in (m.i1, m.i2, m.i3) if i.id not in tem)
    assert sem.id not in {e["id"] for e in instrutores_elegiveis(db, m.uc_a, m.unidade.id, SEG)}
    m.uc_a.categoria = "transversal"
    db.commit()
    assert sem.id in {e["id"] for e in instrutores_elegiveis(db, m.uc_a, m.unidade.id, SEG)}
    aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=sem, ambiente=m.s1))
    db.commit()
    # técnica com "em partes": pode, com alerta
    m.uc_b.categoria = "tecnica"
    comp = db.scalar(select(CompetenciaInstrutor).where(CompetenciaInstrutor.uc_id == m.uc_b.id))
    comp.nivel = "parcial"
    db.commit()
    _a, oc = aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_b, periodo=2, instrutor=db.get(type(m.i1), comp.instrutor_id), ambiente=m.s1))
    assert any(o.regra == "INSTRUTOR_PARCIAL" for o in oc)


def test_solicitacao_de_folga_aprovada_com_a_sugestao(db, mundo, monkeypatch):
    m = mundo
    a, _ = aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s1))
    db.add(Usuario(nome="Prof", email="prof@teste", senha_hash=hash_senha("senha-prof-123"), perfil="instrutor", instrutor_id=m.i1.id, ativo=True))
    db.add(Usuario(nome="Coord", email="coord@teste", senha_hash=hash_senha("senha-coord-123"), perfil="coordenador", acesso_global=True, ativo=True))
    db.commit()
    monkeypatch.setattr(solicitacoes, "hoje", lambda: SEG - timedelta(days=3))
    monkeypatch.setattr(substituicao, "hoje", lambda: SEG - timedelta(days=3))
    c = TestClient(app)
    prof, coord = _login(c, "prof@teste", "senha-prof-123"), _login(c, "coord@teste", "senha-coord-123")
    r = c.post("/api/portal/solicitacoes", json={"tipo": "folga", "data_inicio": SEG.isoformat(), "justificativa": "curto"}, headers=prof)
    assert r.status_code == 422  # justificativa obrigatória
    r = c.post("/api/portal/solicitacoes", json={"tipo": "folga", "data_inicio": SEG.isoformat(), "justificativa": "Consulta médica agendada"}, headers=prof)
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    assert r.json()["aulas_afetadas"] == 1
    # o instrutor não decide; o coordenador vê o pedido com a sugestão de substituto
    assert c.get("/api/solicitacoes-instrutores", headers=prof).status_code == 403
    d = c.get(f"/api/solicitacoes-instrutores/{sid}", headers=coord).json()
    assert d["aulas_afetadas"] == 1 and d["sugestao"] and d["sugestao"]["id"] != m.i1.id
    r = c.put(f"/api/solicitacoes-instrutores/{sid}", json={"aprovar": True, "aceitar_sugestao": True, "resposta": "Aprovado"}, headers=coord)
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(Alocacao, a.id).instrutor_id == d["sugestao"]["id"]
    s = db.get(SolicitacaoInstrutor, sid)
    assert s.status == "aprovada" and s.efeitos["substituidas"] == 1 and s.efeitos["bloqueios"]
    assert db.scalars(select(Bloqueio).where(Bloqueio.alvo_id == m.i1.id, Bloqueio.tipo == "folga")).first()
    assert db.scalars(select(Notificacao).where(Notificacao.instrutor_id == m.i1.id, Notificacao.tipo == "solicitacao")).first()
    assert db.scalars(select(RegistroDecisao).where(RegistroDecisao.tipo == "sugestao")).first()
    # já decidida: não muda mais; recusa exige resposta
    assert c.put(f"/api/solicitacoes-instrutores/{sid}", json={"aprovar": False}, headers=coord).status_code == 409
    with pytest.raises(Exception):
        solicitacoes.decidir(db, m.ctx, sid, False, None)


def test_aceitar_sugestao_aplica_e_registra(db, mundo):
    m = mundo
    c = TestClient(app)
    h = _login(c, "admin@teste", "senha-forte-1")
    tem = {x.instrutor_id for x in db.scalars(select(CompetenciaInstrutor).where(CompetenciaInstrutor.uc_id == m.uc_c.id, CompetenciaInstrutor.ativo.is_(True)))}
    sem = next(i for i in (m.i1, m.i2, m.i3) if i.id not in tem)
    r = c.post("/api/sugestoes/aplicar", json={"cenario_id": m.cen.id, "gerar": False,
                                                "acao": {"tipo": "habilitar_instrutor", "instrutor_id": sem.id, "uc_id": m.uc_c.id}}, headers=h)
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.scalar(select(CompetenciaInstrutor).where(CompetenciaInstrutor.instrutor_id == sem.id, CompetenciaInstrutor.uc_id == m.uc_c.id)).nivel == "pleno"
    # alocar a aula sugerida (passa pela validação central)
    from app.models import TurmaUC
    tuc = db.scalar(select(TurmaUC).where(TurmaUC.turma_id == m.t1.id, TurmaUC.uc_id == m.uc_a.id))
    p = db.scalars(select(PeriodoHorario).where(PeriodoHorario.turno_id == m.manha.id).order_by(PeriodoHorario.ordem)).first()
    acao = {"tipo": "alocar_aula", "turma_uc_id": tuc.id, "data": SEG.isoformat(), "periodo_inicio_id": p.id, "num_periodos": 2,
            "instrutor_id": m.i1.id, "ambiente_id": m.s1.id}
    r = c.post("/api/sugestoes/aplicar", json={"cenario_id": m.cen.id, "acao": acao}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["alocacao_id"]
    r = c.post("/api/sugestoes/aplicar", json={"cenario_id": m.cen.id, "acao": acao}, headers=h)
    assert r.status_code == 409  # a mesma aula de novo: conflito, nada é gravado
    assert c.post("/api/sugestoes/recusar", json={"cenario_id": m.cen.id, "acao": acao, "motivo": "não serve"}, headers=h).status_code == 200
    db.expire_all()
    tipos = {x.tipo for x in db.scalars(select(RegistroDecisao))}
    assert {"sugestao", "rejeicao"} <= tipos
