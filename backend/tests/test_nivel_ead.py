"""Nível do instrutor (básico só em AIB e qualificações) e dias EAD das turmas 80-20."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.errors import ConflitoValidacao
from app.main import app
from app.services import alocacao as aloc
from app.services import exportacao
from app.services.planejamento import dias_com_ead, instrutores_elegiveis, nivel_da_turma
from tests.conftest import SEG, aula


def _regras(e):
    return {o["regra"] for o in e.value.detalhes["ocorrencias"] if o["severidade"] == "bloqueio"}


def test_nivel_da_turma_pela_oferta_e_pelo_curso(db, mundo):
    m = mundo
    assert nivel_da_turma(db, m.t1) == "tecnico"  # sem prefixo conhecido e curso sem tipo: exige técnico
    m.curso.tipo = "Qualificação profissional"
    assert nivel_da_turma(db, m.t1) == "basico"
    m.t1.codigo = "HTC-C1-01"
    assert nivel_da_turma(db, m.t1) == "tecnico"  # o tipo de oferta no código prevalece
    m.t1.codigo = "AIB-C1-01"
    assert nivel_da_turma(db, m.t1) == "basico"


def test_instrutor_basico_nao_entra_em_turma_tecnica(db, mundo):
    m = mundo
    m.i1.nivel = "basico"
    db.commit()
    ids = {e["id"] for e in instrutores_elegiveis(db, m.uc_a, m.t1.unidade_id, SEG, nivel=nivel_da_turma(db, m.t1))}
    assert m.i1.id not in ids
    with pytest.raises(ConflitoValidacao) as e:
        aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s1))
    assert "INSTRUTOR_NIVEL" in _regras(e)
    db.rollback()
    # em turma de aprendizagem básica o mesmo instrutor é aceito
    m.t1.codigo = "AIB-C1-01"
    db.commit()
    assert m.i1.id in {e["id"] for e in instrutores_elegiveis(db, m.uc_a, m.t1.unidade_id, SEG, nivel=nivel_da_turma(db, m.t1))}
    aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s1))


def test_dias_com_ead():
    assert dias_com_ead([0, 1, 2, 3, 4], [4]) == [0, 1, 2, 3]
    assert dias_com_ead([0, 1, 2, 3], [], ead_antes=[4]) == [0, 1, 2, 3, 4]  # deixou de ser EAD: volta a ser dia de aula


def test_sexta_ead_pelo_cadastro_bloqueia_aula_e_aparece_na_exportacao(db, mundo):
    m = mundo
    c = TestClient(app)
    h = {"Authorization": "Bearer " + c.post("/api/auth/login", json={"email": "admin@teste", "senha": "senha-forte-1"}).json()["token"]}
    r = c.put(f"/api/cadastros/turmas/{m.t1.id}", json={"dias_ead": [4]}, headers=h)
    assert r.status_code == 200, r.text
    db.expire_all()
    assert m.t1.dias_ead == [4] and 4 not in m.t1.dias_possiveis
    sexta = SEG + timedelta(days=4)
    with pytest.raises(ConflitoValidacao) as e:
        aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, d=sexta, instrutor=m.i1, ambiente=m.s1))
    assert "TURMA_DIA_EAD" in _regras(e)
    db.rollback()
    ops = c.get("/api/cadastros/turmas/opcoes", headers=h).json()
    assert next(o for o in ops if o["id"] == m.t1.id)["dias_ead"] == [4]
    ead = exportacao.linhas_ead(db, SEG, SEG + timedelta(days=13))
    assert {l["_data"] for l in ead if l["turma"] == m.t1.codigo} == {sexta, sexta + timedelta(days=7)}
    # desmarcar: a sexta volta a ser dia de aula presencial
    assert c.put(f"/api/cadastros/turmas/{m.t1.id}", json={"dias_ead": []}, headers=h).status_code == 200
    db.expire_all()
    assert m.t1.dias_ead == [] and 4 in m.t1.dias_possiveis
