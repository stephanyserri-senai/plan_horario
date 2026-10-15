"""Modalidade do instrutor (mensalista/horista) e turnos de planejamento (PL) / projeto (PJ) marcados na grade."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.errors import ConflitoValidacao
from app.main import app
from app.services import agenda_instrutor
from app.services import alocacao as aloc
from tests.conftest import SEG, aula
from tests.test_conflitos import regras


def _login(c):
    r = c.post("/api/auth/login", json={"email": "admin@teste", "senha": "senha-forte-1"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_agenda_pl_pj_e_modalidade(db, mundo):
    m = mundo
    c = TestClient(app)
    h = _login(c)
    ter = SEG + timedelta(days=1)
    url = f"/api/grade/agenda-instrutor?cenario_id={m.cen.id}&instrutor_id={m.i1.id}&semana={SEG}"

    # mensalista (padrão): turno da jornada sem aula é hora paga sem atribuição
    ag = c.get(url, headers=h).json()
    assert ag["instrutor"]["modalidade"] == "mensalista"
    assert {x["estado"] for x in ag["celulas"]} == {"vazio"} and ag["resumo"]["sem_atribuicao_h"] == 20

    # uma aula na segunda; PL toda terça por 4 semanas; PJ só na quarta desta semana
    aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s1))
    db.commit()
    r = c.post(f"/api/instrutores/{m.i1.id}/agenda", json={"cenario_id": m.cen.id, "data": ter.isoformat(), "turno_id": m.manha.id,
                                                          "sigla": "PL", "repetir_ate": (ter + timedelta(days=21)).isoformat()}, headers=h)
    assert r.status_code == 200 and r.json()["marcados"] == 4, r.text
    r = c.post(f"/api/instrutores/{m.i1.id}/agenda", json={"cenario_id": m.cen.id, "data": (SEG + timedelta(days=2)).isoformat(),
                                                          "turno_id": m.manha.id, "sigla": "PJ", "descricao": "Feira de ciências"}, headers=h)
    assert r.json()["marcados"] == 1
    # PL na segunda (que tem aula) não é marcado: a aula fica como está
    r = c.post(f"/api/instrutores/{m.i1.id}/agenda", json={"cenario_id": m.cen.id, "data": SEG.isoformat(), "turno_id": m.manha.id, "sigla": "PL"},
               headers=h).json()
    assert r["marcados"] == 0 and r["com_aula"] == [SEG.isoformat()]

    ag = c.get(url, headers=h).json()
    estados = {x["dia"]: x["estado"] for x in ag["celulas"]}
    assert estados == {0: "aula", 1: "PL", 2: "PJ", 3: "vazio", 4: "vazio"}
    assert ag["resumo"]["pl_h"] == 4 and ag["resumo"]["pj_h"] == 4 and ag["resumo"]["sem_atribuicao_h"] == 8 and ag["resumo"]["dispensa_h"] == 0

    # aula em turno de PL é barrada com mensagem clara
    with pytest.raises(ConflitoValidacao) as e:
        aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t2, m.uc_a, d=ter, instrutor=m.i1, ambiente=m.s2))
    db.rollback()
    assert "BLOQUEIO_INSTRUTOR" in regras(e.value)
    assert any("PL" in o["descricao"] for o in e.value.detalhes["ocorrencias"])

    # o gerador de horários tira o PL semanal da disponibilidade (o PJ de um dia só, não)
    reservas = agenda_instrutor.reservas_semanais(db, m.i1.id, m.cen.periodo_inicio, ter + timedelta(days=21))
    assert [r[0] for r in reservas] == [1]
    disp = agenda_instrutor.subtrair([(1, 7 * 60, 18 * 60), (2, 7 * 60, 18 * 60)], reservas)
    assert (1, 7 * 60, 18 * 60) not in disp and (2, 7 * 60, 18 * 60) in disp and any(d == 1 for d, _, _ in disp)

    # horista: o mesmo turno vazio vira dispensa
    r = c.put(f"/api/cadastros/instrutores/{m.i1.id}", json={"modalidade": "horista"}, headers=h)
    assert r.status_code == 200, r.text
    assert c.put(f"/api/cadastros/instrutores/{m.i1.id}", json={"modalidade": "temporario"}, headers=h).status_code in (400, 409, 422)
    ag = c.get(url, headers=h).json()
    assert ag["instrutor"]["modalidade"] == "horista" and ag["resumo"]["dispensa_h"] == 8 and ag["resumo"]["sem_atribuicao_h"] == 0

    # voltar a vazio remove o PL de todas as semanas
    r = c.post(f"/api/instrutores/{m.i1.id}/agenda", json={"cenario_id": m.cen.id, "data": ter.isoformat(), "turno_id": m.manha.id,
                                                          "sigla": None, "repetir_ate": (ter + timedelta(days=21)).isoformat()}, headers=h).json()
    assert r["removidos"] == 4
    assert c.post(f"/api/instrutores/{m.i1.id}/agenda", json={"cenario_id": m.cen.id, "data": ter.isoformat(), "turno_id": m.manha.id,
                                                             "sigla": "XX"}, headers=h).status_code in (400, 422)
