"""Agendamento de ambientes: grade de disponibilidade (aulas publicadas, bloqueios, pedidos), pedido do instrutor que segura o
horário, confirmação pela supervisão (vira bloqueio do ambiente) e cancelamento."""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.errors import ConflitoValidacao, EntradaInvalida
from app.main import app
from app.models import Bloqueio
from app.services import agendamentos
from app.services import alocacao as aloc
from app.services.validacao import AulaProposta, BaseDados, validar_aula
from tests.conftest import SEG, aula


def test_grade_pedido_confirmacao_e_cancelamento(db, mundo, monkeypatch):
    m = mundo
    monkeypatch.setattr(agendamentos, "hoje", lambda: SEG - timedelta(days=3))
    aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s1))
    m.cen.estado = "publicado"
    db.commit()
    g = agendamentos.grade(db, SEG, SEG + timedelta(days=5), m.unidade.id)
    k = f"{SEG.isoformat()}|{m.manha.id}"
    cel = {a["codigo"]: a["celulas"] for a in g["ambientes"]}
    assert cel["S1"][k]["estado"] == "aula" and cel["S1"][k]["texto"] == "T1"
    assert cel["S2"][k]["estado"] == "livre"
    # instrutor pede a S2 na segunda de manhã: fica pendente e segura o horário
    p = agendamentos.criar(db, m.ctx, m.s2.id, SEG, m.manha.id, "Aula prática de comandos", m.i2)
    db.commit()
    assert p.status == "pendente"
    with pytest.raises(ConflitoValidacao):
        agendamentos.criar(db, m.ctx, m.s2.id, SEG, m.manha.id, "Reunião de área", m.i1)
    db.rollback()
    with pytest.raises(ConflitoValidacao):  # a S1 tem aula publicada nesse horário
        agendamentos.criar(db, m.ctx, m.s1.id, SEG, m.manha.id, "Reunião de área", m.i1)
    db.rollback()
    with pytest.raises(EntradaInvalida):  # data passada
        agendamentos.criar(db, m.ctx, m.s2.id, SEG - timedelta(days=7), m.manha.id, "Reunião de área", m.i1)
    db.rollback()
    g = agendamentos.grade(db, SEG, SEG, m.unidade.id)
    assert {a["codigo"]: a["celulas"] for a in g["ambientes"]}["S2"][k]["estado"] == "pendente"
    # supervisão confirma: vira bloqueio do ambiente e a validação das aulas passa a respeitar
    agendamentos.decidir(db, m.ctx, p.id, "confirmado")
    db.commit()
    assert p.bloqueio_id and db.get(Bloqueio, p.bloqueio_id).ativo
    tuc = m.tuc(db, m.t2, m.uc_a)
    ini = datetime.combine(SEG, m.periodos[0].hora_inicio)
    oc = validar_aula(BaseDados(db, m.cen.id), AulaProposta(turma_uc_id=tuc.id, inicio=ini, fim=ini + timedelta(minutes=100), minutos_aula=100,
                                                          ambiente_id=m.s2.id))
    assert any(o.recurso_tipo == "ambiente" and o.severidade == "bloqueio" for o in oc)
    g = agendamentos.grade(db, SEG, SEG, m.unidade.id)
    assert {a["codigo"]: a["celulas"] for a in g["ambientes"]}["S2"][k]["estado"] == "reservado"
    # cancelado: libera o ambiente
    agendamentos.cancelar(db, m.ctx, p.id, m.i2)
    db.commit()
    assert not db.get(Bloqueio, p.bloqueio_id).ativo
    g = agendamentos.grade(db, SEG, SEG, m.unidade.id)
    assert {a["codigo"]: a["celulas"] for a in g["ambientes"]}["S2"][k]["estado"] == "livre"


def test_api_supervisao(db, mundo, monkeypatch):
    m = mundo
    monkeypatch.setattr(agendamentos, "hoje", lambda: SEG - timedelta(days=3))
    p = agendamentos.criar(db, m.ctx, m.lab1.id, SEG + timedelta(days=1), m.manha.id, "Ensaio no laboratório", m.i1, participantes=12)
    db.commit()
    c = TestClient(app)
    h = {"Authorization": "Bearer " + c.post("/api/auth/login", json={"email": "admin@teste", "senha": "senha-forte-1"}).json()["token"]}
    assert [x["id"] for x in c.get("/api/agendamentos?status=pendente", headers=h).json()] == [p.id]
    assert c.put(f"/api/agendamentos/{p.id}", json={"status": "recusado"}, headers=h).status_code == 422  # sem motivo
    r = c.put(f"/api/agendamentos/{p.id}", json={"status": "recusado", "resposta": "Laboratório em manutenção preventiva"}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "recusado"
    r = c.get(f"/api/ambientes/agenda?unidade_id={m.unidade.id}&inicio={SEG.isoformat()}&fim={(SEG + timedelta(days=5)).isoformat()}", headers=h)
    assert r.status_code == 200 and r.json()["turnos"] and len(r.json()["dias"]) == 6
