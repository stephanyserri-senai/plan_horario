"""Regra da instituição: cada UC ocupa o turno inteiro (todas as aulas do turno);
aula parcial só no fechamento da carga horária, podendo dividir o turno com outra
UC que também esteja fechando. Carga horária contada em hora-aula."""
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.errors import ConflitoValidacao
from app.models import Alocacao, TurmaUC
from app.services import alocacao as aloc
from tests.conftest import SEG, aula, criar_mundo
from tests.test_otimizacao import executar

REGRAS = {"turno_inteiro": True, "contagem": "hora_aula"}


@pytest.fixture
def mt(db):
    return criar_mundo(db, REGRAS)


def _criar(db, m, uc, d, periodo, n, inst, amb):
    a, oc = aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, uc, d=d, periodo=periodo, n=n, instrutor=inst, ambiente=amb))
    db.commit()
    return a, oc


def test_uc_deve_ocupar_o_turno_inteiro(db, mt):
    m = mt
    with pytest.raises(ConflitoValidacao) as e:
        _criar(db, m, m.uc_a, SEG, 0, 2, m.i1, m.s1)
    assert "TURNO_INCOMPLETO" in str(e.value.detalhes)
    a, _ = _criar(db, m, m.uc_a, SEG, 0, 4, m.i1, m.s1)
    assert a.minutos_aula == 240  # 4 aulas = 4 horas-aula, mesmo com aulas de 50 min


def test_fechamento_da_carga_permite_dividir_o_turno(db, mt):
    m = mt
    m.uc_a.carga_horaria_total, m.uc_b.carga_horaria_total = 6, 2
    db.commit()
    _criar(db, m, m.uc_a, SEG, 0, 4, m.i1, m.s1)               # 4 h; faltam 2
    _criar(db, m, m.uc_a, SEG + timedelta(days=1), 0, 2, m.i1, m.s1)  # fechamento de A (2 aulas)
    _criar(db, m, m.uc_b, SEG + timedelta(days=1), 2, 2, m.i1, m.s1)  # B fecha no mesmo turno
    aulas = db.scalars(select(Alocacao).where(Alocacao.data == SEG + timedelta(days=1))).all()
    assert sorted(a.minutos_aula for a in aulas) == [120, 120]
    # UC que não está fechando não pode ocupar meio turno
    with pytest.raises(ConflitoValidacao) as e:
        _criar(db, m, m.uc_c, SEG + timedelta(days=2), 0, 2, m.i2, m.lab1)
    assert "TURNO_INCOMPLETO" in str(e.value.detalhes)


def test_gerador_usa_turno_inteiro_e_junta_fechamentos(db, mt):
    m = mt
    m.uc_a.carga_horaria_total, m.uc_b.carga_horaria_total = 10, 6  # A: 2 dias + 2 aulas; B: 1 dia + 2 aulas
    for tuc in db.scalars(select(TurmaUC).where(TurmaUC.uc_id == m.uc_c.id)):
        tuc.situacao = "cancelada"
    db.commit()
    ex = executar(db, m, {"tipo": "turma", "ids": [m.t1.id]})
    assert ex.status == "concluida" and ex.status_solver in ("OTIMA", "VIAVEL"), ex.diagnosticos
    aulas = db.scalars(select(Alocacao).where(Alocacao.turma_id == m.t1.id).order_by(Alocacao.data)).all()
    por_uc = {}
    for a in aulas:
        por_uc.setdefault(a.uc_id, []).append(a)
    assert sum(a.minutos_aula for a in por_uc[m.uc_a.id]) == 600 and sum(a.minutos_aula for a in por_uc[m.uc_b.id]) == 360
    completas = [a for a in aulas if a.minutos_aula == 240]
    parciais = [a for a in aulas if a.minutos_aula < 240]
    assert len(completas) == 3 and len(parciais) == 2
    # cada parcial é a última aula da sua UC, e as duas dividem o mesmo turno
    for p in parciais:
        assert p == por_uc[p.uc_id][-1]
    assert parciais[0].data == parciais[1].data and parciais[0].fim <= parciais[1].inicio or parciais[1].fim <= parciais[0].inicio
    assert ex.resultado["aplicacao"]["fechamentos_juntados"] == 1


def test_turnos_padrao_e_configuracao_visivel(db, mt):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.models import PeriodoHorario, Turno, Unidade
    c = TestClient(app)
    h = {"Authorization": "Bearer " + c.post("/api/auth/login", json={"email": "admin@teste", "senha": "senha-forte-1"}).json()["token"]}
    nova = Unidade(codigo="U2", nome="Unidade 2")
    db.add(nova)
    db.commit()
    r = c.post(f"/api/unidades/{nova.id}/turnos-padrao", headers=h)
    assert r.status_code == 200, r.text
    turnos = {t.nome: t for t in db.scalars(select(Turno).where(Turno.unidade_id == nova.id))}
    assert set(turnos) == {"Manhã", "Tarde", "Noite"}
    manha = db.scalars(select(PeriodoHorario).where(PeriodoHorario.turno_id == turnos["Manhã"].id).order_by(PeriodoHorario.ordem)).all()
    assert [(p.hora_inicio.strftime("%H:%M"), p.hora_fim.strftime("%H:%M")) for p in manha] == [
        ("07:30", "08:25"), ("08:25", "09:20"), ("09:40", "10:35"), ("10:35", "11:30")]
    noite = db.scalars(select(PeriodoHorario).where(PeriodoHorario.turno_id == turnos["Noite"].id).order_by(PeriodoHorario.ordem)).all()
    assert noite[0].hora_inicio.strftime("%H:%M") == "18:30" and noite[1].hora_fim.strftime("%H:%M") == "20:10"
    assert noite[2].hora_inicio.strftime("%H:%M") == "20:20" and noite[-1].hora_fim.strftime("%H:%M") == "22:00"
    # não sobrescreve turnos existentes
    assert c.post(f"/api/unidades/{nova.id}/turnos-padrao", headers=h).status_code == 422
    cfg = {x["chave"]: x for x in c.get("/api/configuracoes", headers=h).json()}
    assert cfg["regras_aula"]["valor"]["turno_inteiro"] is True
