"""Gerador de horários (casos 12–15 e 21)."""
from datetime import date, time

from sqlalchemy import func, select

from app.models import Alocacao, CenarioPlanejamento, ExecucaoOtimizacao, Turma, TurmaUC
from app.services import alocacao as aloc
from app.services import cenarios, gargalos, otimizacao
from app.solver.contrato import AtividadeS, EntradaSolver, InstrutorS, Janela, AmbienteS, Slot
from app.solver.cpsat import resolver
from tests.conftest import SEG, aula


def executar(db, m, escopo=None, **kw):
    ex = otimizacao.criar_execucao(db, m.ctx, m.cen.id, escopo or {"tipo": "instituicao"}, limite_tempo_s=kw.pop("limite", 20), **kw)
    db.commit()
    otimizacao.executar(ex.id, m.ctx)
    db.expire_all()
    return db.get(ExecucaoOtimizacao, ex.id)


def test_13_cenario_viavel_otimizado(db, mundo):
    m = mundo
    ex = executar(db, m)
    assert ex.status == "concluida"
    assert ex.status_solver in ("OTIMA", "VIAVEL")
    assert ex.resultado["aplicacao"]["aulas_criadas"] > 0
    assert ex.parametros["pesos"]["janelas_instrutores"] > 0  # pesos registrados na execução
    # todas as aulas geradas passam pela validação central sem bloqueios
    v = cenarios.validar(db, m.ctx, m.cen.id)
    assert v["resumo"]["bloqueios"] == 0
    # carga horária completa sem duplicar: cada turma×UC (por grupo) recebeu exatamente sua CH
    for tuc in db.scalars(select(TurmaUC)):
        from app.services.planejamento import situacao_carga_horaria
        info = situacao_carga_horaria(db, m.cen.id, tuc)
        assert info["restante_h"] == 0, info
    # o feriado de 07/09 foi pulado
    assert db.scalar(select(func.count()).select_from(Alocacao).where(Alocacao.data == date(2026, 9, 7))) == 0
    # reexecutar somente pendentes não duplica nada
    total = db.scalar(select(func.count()).select_from(Alocacao))
    ex2 = executar(db, m, {"tipo": "pendentes"})
    assert ex2.status_solver == "SEM_DEMANDA"
    assert db.scalar(select(func.count()).select_from(Alocacao)) == total


def test_14_cenario_comprovadamente_inviavel(db, mundo):
    m = mundo
    # 10 encontros semanais de 2 períodos por UC em um turno que comporta 10 blocos/semana por turma
    for uc in (m.uc_a, m.uc_b):
        uc.encontros_semanais = 5
        uc.carga_horaria_total = 160
    db.commit()
    ex = executar(db, m, {"tipo": "turma", "ids": [m.t2.id]})
    assert ex.status_solver == "INVIAVEL"
    assert "provou" in ex.motivo_termino or "comprovadamente" in ex.motivo_termino
    assert db.scalar(select(func.count()).select_from(Alocacao)) == 0
    assert ex.resultado.get("explicacoes") or ex.resultado.get("gargalos")
    cen = db.get(CenarioPlanejamento, m.cen.id)
    assert cen.estado == "em_elaboracao"


def test_15_limite_de_tempo_sem_solucao_comprovada():
    """Atingir o limite sem solução nunca é reportado como inviabilidade."""
    slots = [Slot(i + 1, 1, 1, i, [0, 1, 2, 3, 4], 420 + 50 * i, 470 + 50 * i) for i in range(8)]
    disp = [Janela(d, 0, 1440) for d in range(5)]
    insts = [InstrutorS(i, [1], disp, 40 * 60, 10 * 60) for i in range(1, 9)]
    ambs = [AmbienteS(r, 1, 40, 40, False, []) for r in range(1, 9)]
    ats = [AtividadeS(f"a{k}", turma_id=k % 12, turma_uc_id=k, uc_id=k, grupo=None, grupos=list(range(1, 17)), unidade_id=1, turno_id=1,
                      dias_permitidos=[0, 1, 2, 3, 4], num_periodos=2, encontros=3, instrutores=list(range(1, 9)), ambientes=list(range(1, 9)),
                      tamanho=30, data_ini=1, data_fim=100) for k in range(60)]
    saida = resolver(EntradaSolver(slots, insts, ambs, ats, limite_tempo_s=0.01, threads=1))
    assert saida.status == "SEM_SOLUCAO_NO_LIMITE"
    assert "NÃO prova inviabilidade" in saida.motivo


def test_12_uc_sem_possibilidade_de_conclusao_no_calendario(db, mundo):
    m = mundo
    tuc = m.tuc(db, m.t1, m.uc_a)
    tuc.data_limite = date(2026, 8, 7)  # uma semana para 40 h
    db.commit()
    r = gargalos.analisar(db, m.cen.id, date(2026, 8, 3), date(2026, 12, 18), data_referencia=date(2026, 8, 3))
    cal = [g for g in r["gargalos"] if g["tipo"] == "inviabilidade_calendario" and "A" in g["recurso"]]
    assert cal and "impossível" in cal[0]["descricao"]
    assert cal[0]["deficit_h"] > 0


def test_21_preservacao_de_horarios_fixos(db, mundo):
    m = mundo
    fixa, _ = aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, d=SEG, periodo=2, instrutor=m.i1, ambiente=m.s2, fixa=True))
    flex, _ = aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t2, m.uc_b, d=SEG, periodo=0, instrutor=m.i1, ambiente=m.s1))
    db.commit()
    fixa_id, flex_id = fixa.id, flex.id
    ex = executar(db, m, {"tipo": "instituicao", "regenerar_flexiveis": True})
    assert ex.status_solver in ("OTIMA", "VIAVEL")
    f = db.get(Alocacao, fixa_id)
    assert f is not None and f.instrutor_id == m.i1.id and f.ambiente_id == m.s2.id and f.inicio.time() == time(9, 30)
    assert db.get(Alocacao, flex_id) is None  # flexível foi substituída
    assert cenarios.validar(db, m.ctx, m.cen.id)["resumo"]["bloqueios"] == 0


def test_execucao_em_cenario_publicado_e_bloqueada(db, mundo):
    m = mundo
    m.cen.estado = "publicado"
    db.commit()
    import pytest
    from app.core.errors import ConflitoValidacao
    with pytest.raises(ConflitoValidacao):
        otimizacao.criar_execucao(db, m.ctx, m.cen.id, {"tipo": "instituicao"})


def test_recuperacao_de_execucao_interrompida(db, mundo):
    m = mundo
    ex = otimizacao.criar_execucao(db, m.ctx, m.cen.id, {"tipo": "instituicao"})
    ex.status = "executando"
    db.commit()
    assert otimizacao.recuperar_execucoes_interrompidas(db) == 1
    db.expire_all()
    assert db.get(ExecucaoOtimizacao, ex.id).status == "falha"
    assert db.get(CenarioPlanejamento, m.cen.id).estado == "em_elaboracao"
    _ = Turma
