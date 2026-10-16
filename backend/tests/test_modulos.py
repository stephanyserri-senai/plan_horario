"""Turmas modulares (código sobe a cada semestre), reposição aos sábados e restante para o próximo semestre."""
from datetime import date, time, timedelta

import pytest
from sqlalchemy import select
from fastapi.testclient import TestClient

from app.main import app
from app.models import Alocacao, PeriodoHorario, Turma, TurmaUC, Turno
from app.services import cenarios, modulos, resolucoes, sugestoes


def _login(c, email, senha):
    return {"Authorization": "Bearer " + c.post("/api/auth/login", json={"email": email, "senha": senha}).json()["token"]}


def test_codigo_modular():
    assert modulos.codigo("ELT", "12", "HTC") == "HTC-ELT-12"
    assert modulos.codigo("ELT", "12", "HTC", 2) == "HTC-ELT-2-12"
    assert modulos.separar_modulo("2-12") == (2, "12") and modulos.separar_modulo("12") == (None, "12")
    assert modulos.rotulo(modulos.semestre(date(2026, 8, 3))) == "2026/2"


def test_turma_de_3_modulos_vai_ate_2027_2_com_o_codigo_subindo(db, mundo):
    m = mundo
    from app.models import Area
    area = Area(codigo="TST", nome="TESTE", unidade_id=m.unidade.id, ativo=True)
    db.add(area)
    db.flush()
    m.curso.area_id = area.id
    db.commit()
    c = TestClient(app)
    h = _login(c, "admin@teste", "senha-forte-1")
    base = {"curso_id": m.curso.id, "matriz_id": m.matriz.id, "turno_id": m.manha.id, "qtd_alunos": 20, "data_inicio": "2026-08-03",
            "data_fim": "2026-12-18", "_numero": "34", "_tipo_oferta": "EMP", "dias_possiveis": [0, 1, 2, 3, 4]}
    r = c.post("/api/cadastros/turmas", json={**base, "modulos": 3}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["codigo"] == "EMP-C1-1-34" and r.json()["modulo_atual"] == 1
    p = c.get("/api/cadastros-apoio/codigo-turma", params={"curso_id": m.curso.id, "numero": "34", "tipo": "EMP", "modulos": 3,
                                                          "data_inicio": "2026-08-03"}, headers=h).json()
    assert p["modular"]["termina_em"] == "2027/2"
    tid = r.json()["id"]
    # não modular: padrão de sempre
    r2 = c.post("/api/cadastros/turmas", json={**base, "_numero": "35"}, headers=h)
    assert r2.json()["codigo"] == "EMP-C1-35"
    codigos = []
    for ini, fim in ((date(2027, 2, 1), date(2027, 6, 30)), (date(2027, 8, 2), date(2027, 12, 17)), (date(2028, 2, 1), date(2028, 6, 30))):
        cenarios.criar(db, m.ctx, f"Semestre {ini.year}", m.unidade.id, ini, fim)
        db.commit()
        db.expire_all()
        codigos.append(db.get(Turma, tid).codigo)
    assert codigos == ["EMP-C1-2-34", "EMP-C1-3-34", "EMP-C1-3-34"]  # para no último módulo
    assert db.get(Turma, tid).data_fim == date(2027, 12, 17)
    assert db.get(Turma, r2.json()["id"]).codigo == "EMP-C1-35"


def _sabado(db, m):
    sab = Turno(unidade_id=m.unidade.id, codigo="S", nome="Sábado", hora_inicio=time(8), hora_fim=time(9, 40), ordem=4, ativo=True)
    db.add(sab)
    db.flush()
    db.add(PeriodoHorario(unidade_id=m.unidade.id, turno_id=sab.id, ordem=1, hora_inicio=time(8), hora_fim=time(9, 40), dias_semana=[5],
                          excepcional=False, ativo=True))
    db.commit()


def test_reposicao_aos_sabados_so_com_a_excecao(db, mundo):
    m = mundo
    _sabado(db, m)
    t = db.get(Turma, m.t1.id)
    t.modulos, t.modulo_atual = 2, 1
    db.commit()
    tuc = db.scalar(select(TurmaUC).where(TurmaUC.turma_id == t.id, TurmaUC.uc_id == m.uc_a.id))
    hoje = date(2026, 11, 20)
    s = resolucoes._prazo(db, m.cen, t, "A", 40, 10, date(2026, 12, 18), hoje)
    assert s["acao"]["tipo"] == "reposicao_sabado" and all(date.fromisoformat(d).weekday() == 5 for d in s["acao"]["datas"])
    sugestoes.aplicar(db, m.ctx, m.cen.id, s["acao"], gerar=False)
    db.commit()
    aulas = db.query(Alocacao).filter(Alocacao.cenario_id == m.cen.id, Alocacao.turma_uc_id == tuc.id, Alocacao.origem == "reposicao").all()
    assert len(aulas) == len(s["acao"]["datas"]) and all(a.data.weekday() == 5 and a.excecao_id for a in aulas)
    # sem a exceção, a validação central não aceita a turma (seg–sex) no sábado
    from app.services.calendario import combinar
    from app.services.validacao import AulaProposta, BaseDados, possui_bloqueio, validar_aula
    p = AulaProposta(turma_uc_id=tuc.id, inicio=combinar(date(2026, 12, 12), time(8)), fim=combinar(date(2026, 12, 12), time(9, 40)),
                     minutos_aula=100, grupo=None, instrutor_id=m.i1.id, ambiente_id=m.s1.id)
    oc = validar_aula(BaseDados(db, m.cen.id), p)
    assert possui_bloqueio(oc) and any(o.regra == "TURMA_FORA_DIAS" for o in oc)


def test_nao_modular_passa_o_restante_para_o_proximo_semestre(db, mundo):
    m = mundo
    t = db.get(Turma, m.t1.id)
    s = resolucoes._prazo(db, m.cen, t, "A", 40, 10, date(2026, 12, 18), date(2026, 11, 20))
    assert s["acao"]["tipo"] == "passar_proximo_semestre" and "2027/1" in s["sugestao"]
    r = sugestoes.aplicar(db, m.ctx, m.cen.id, s["acao"], gerar=False)
    db.commit()
    db.expire_all()
    tuc = db.get(TurmaUC, s["acao"]["turma_uc_id"])
    assert tuc.data_limite == date(2027, 6, 30) and db.get(Turma, t.id).data_fim == date(2027, 6, 30) and "2027/1" in r["mensagem"]
    # turma modular não usa esse caminho
    t.modulos = 2
    db.commit()
    with pytest.raises(Exception):
        resolucoes.proximo_semestre(db, m.ctx, tuc.id)


def test_remanejar_o_habilitado(db, mundo):
    """B só tem I1; I1 dá A na T2, que I2 também pode dar: remanejar I2 para A e liberar I1."""
    m = mundo
    from app.services import alocacao as aloc
    from tests.conftest import aula
    seg = date(2026, 12, 7)  # semanas à frente (a substituição exige antecedência)
    for k in range(2):
        aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t2, m.uc_a, seg + timedelta(days=7 * k), 0, n=2, instrutor=m.i1, ambiente=m.s2))
    db.commit()
    t = db.get(Turma, m.t1.id)
    r = resolucoes._remanejar(db, m.cen.id, t, m.uc_b, date(2026, 11, 1))
    assert r["acao"]["tipo"] == "passar_uc" and r["acao"]["para_instrutor_id"] == m.i2.id and r["acao"]["de_instrutor_id"] == m.i1.id
