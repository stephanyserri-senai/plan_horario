"""Ninguém trabalha mais de 44 h por semana: cadastro, termo de horas, validação das aulas e gerador."""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.errors import EntradaInvalida
from app.main import app
from app.models import Bloqueio
from app.services import termos
from app.services.regras_aula import MAX_HORAS_SEMANA, limite_letivo_efetivo
from app.services.validacao import AulaProposta, BaseDados, validar_aula
from tests.conftest import SEG


def test_cadastro_nao_passa_de_44h(db, mundo):
    m = mundo
    c = TestClient(app)
    h = {"Authorization": "Bearer " + c.post("/api/auth/login", json={"email": "admin@teste", "senha": "senha-forte-1"}).json()["token"]}
    i = c.get(f"/api/cadastros/instrutores/{m.i1.id}", headers=h).json()
    r = c.put(f"/api/cadastros/instrutores/{m.i1.id}", json={**i, "carga_horaria_contratual": 48, "limite_ch_letiva": 40}, headers=h)
    assert r.status_code == 409 and "44 h" in r.json()["erro"]
    assert MAX_HORAS_SEMANA == 44 and limite_letivo_efetivo(type("I", (), {"carga_horaria_contratual": 44, "limite_ch_letiva": 60})()) <= 44


def test_termo_nao_passa_de_44h_na_semana(db, mundo):
    m = mundo
    m.i1.modalidade = "horista"
    db.commit()
    # 6 dias × manhã e tarde de 4 h = 48 h na semana: recusado
    grade = {(SEG + timedelta(days=k)).isoformat(): ({"S": {"tipo": "aula", "ini": "08:00", "fim": "12:00"}} if k == 5 else
             {"M": {"tipo": "aula", "ini": "08:00", "fim": "12:00"}, "V": {"tipo": "pl", "ini": "13:00", "fim": "17:00"}}) for k in range(6)}
    grade[(SEG + timedelta(days=4)).isoformat()]["N"] = {"tipo": "pj", "ini": "18:00", "fim": "22:00"}
    with pytest.raises(EntradaInvalida) as e:
        termos.salvar(db, m.ctx, m.i1, "2026-08", 40, 8, agenda=grade)
    assert "44 h" in str(e.value)
    db.rollback()


def test_aula_que_passaria_de_44h_com_pl_pj_bloqueia(db, mundo):
    m = mundo
    m.i1.limite_ch_letiva = 40
    m.i1.carga_horaria_contratual = 44
    # 43 h de PL/PJ na semana: uma aula de 1h40 passaria de 44 h
    for k in range(5):
        dia = datetime.combine(SEG + timedelta(days=k), datetime.min.time())
        db.add(Bloqueio(alvo_tipo="instrutor", alvo_id=m.i1.id, tipo="planejamento", inicio=dia + timedelta(hours=6),
                        fim=dia + timedelta(hours=14, minutes=36), motivo="PL", ativo=True))
    db.commit()
    tuc = m.tuc(db, m.t1, m.uc_a)
    ini = datetime.combine(SEG + timedelta(days=1), m.periodos[0].hora_inicio) + timedelta(hours=8)
    oc = validar_aula(BaseDados(db, m.cen.id), AulaProposta(turma_uc_id=tuc.id, inicio=ini, fim=ini + timedelta(minutes=100),
                                                          minutos_aula=100, instrutor_id=m.i1.id))
    assert "LIMITE_44H" in [o.regra for o in oc]
