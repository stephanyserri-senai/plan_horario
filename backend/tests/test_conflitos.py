"""Motor de prevenção de conflitos: regras obrigatórias, concorrência e
integridade transacional (casos 1–11, 24, 27, 28)."""
import threading
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import func, select, text

from app.core.db import SessionLocal
from app.core.deps import carregar_contexto
from app.core.errors import ConflitoConcorrencia, ConflitoValidacao
from app.models import Alocacao, Atividade, Bloqueio, ExcecaoAutorizada, Recurso, UCRecurso, Usuario
from app.services import alocacao as aloc
from tests.conftest import SEG, aula


def regras(exc: ConflitoValidacao) -> set[str]:
    return {o["regra"] for o in exc.detalhes["ocorrencias"] if o["severidade"] == "bloqueio"}


def contar(db, cen_id):
    db.expire_all()
    return db.scalar(select(func.count()).select_from(Alocacao).where(Alocacao.cenario_id == cen_id))


def test_01_duas_turmas_mesma_sala(db, mundo):
    m = mundo
    aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s1))
    db.commit()
    with pytest.raises(ConflitoValidacao) as e:
        aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t2, m.uc_a, instrutor=m.i2, ambiente=m.s1))
    db.rollback()
    assert "AMBIENTE_SOBREPOSICAO" in regras(e.value)
    # alternativas calculadas: a sala S2 está livre no mesmo horário
    assert any(a["codigo"] == "S2" for a in e.value.detalhes["alternativas"]["ambientes"])
    assert contar(db, m.cen.id) == 1


def test_02_instrutor_em_duas_aulas(db, mundo):
    m = mundo
    aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s1))
    db.commit()
    with pytest.raises(ConflitoValidacao) as e:
        aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t2, m.uc_b, instrutor=m.i1, ambiente=m.s2))
    db.rollback()
    assert "INSTRUTOR_SOBREPOSICAO" in regras(e.value)
    assert contar(db, m.cen.id) == 1


def test_03_turma_com_duas_ucs_simultaneas(db, mundo):
    m = mundo
    aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s1))
    db.commit()
    with pytest.raises(ConflitoValidacao) as e:
        aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_b, instrutor=m.i2, ambiente=m.s2))
    db.rollback()
    assert "TURMA_SOBREPOSICAO" in regras(e.value)


def _reservar(mundo_ids, resultados, barreira, instrutor_id, turma_codigo):
    from app.models import Turma, TurmaUC
    from app.services.alocacao import DadosAula
    s = SessionLocal()
    try:
        ctx = carregar_contexto(s, s.get(Usuario, mundo_ids["admin"]))
        turma = s.scalar(select(Turma).where(Turma.codigo == turma_codigo))
        tuc = s.scalar(select(TurmaUC).where(TurmaUC.turma_id == turma.id, TurmaUC.uc_id == mundo_ids["uc_a"]))
        d = DadosAula(turma_uc_id=tuc.id, data=SEG, periodo_inicio_id=mundo_ids["p0"], num_periodos=2, instrutor_id=instrutor_id, ambiente_id=mundo_ids["s1"])
        barreira.wait()
        aloc.criar_aula(s, ctx, mundo_ids["cen"], d)
        s.commit()
        resultados.append("ok")
    except (ConflitoValidacao, ConflitoConcorrencia) as e:
        s.rollback()
        resultados.append(type(e).__name__)
    finally:
        s.close()


def test_04_reservas_concorrentes(db, mundo):
    """Dois usuários tentam reservar a mesma sala no mesmo instante."""
    m = mundo
    ids = {"admin": m.admin.id, "uc_a": m.uc_a.id, "p0": m.periodos[0].id, "s1": m.s1.id, "cen": m.cen.id}
    for _rodada in range(3):
        db.execute(text("DELETE FROM alocacoes"))
        db.commit()
        resultados, barreira = [], threading.Barrier(2)
        th = [threading.Thread(target=_reservar, args=(ids, resultados, barreira, inst, cod)) for inst, cod in ((m.i1.id, "T1"), (m.i2.id, "T2"))]
        [t.start() for t in th]
        [t.join() for t in th]
        assert sorted(resultados)[-1] == "ok" and resultados.count("ok") == 1, resultados
        assert contar(db, m.cen.id) == 1


def test_04b_exclusion_constraint_garante_integridade_sem_validacao(db, mundo):
    """Mesmo inserindo direto no banco (sem o serviço), a sobreposição é rejeitada."""
    m = mundo
    a = aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s1))[0]
    db.commit()
    with pytest.raises(Exception) as e:
        db.execute(text("INSERT INTO alocacoes (cenario_id, turma_uc_id, turma_id, uc_id, grupos, ambiente_id, data, inicio, fim, fim_ambiente, minutos_aula, status, fixa, origem, versao) "
                        "SELECT cenario_id, turma_uc_id, :t2, uc_id, grupos, ambiente_id, data, inicio + interval '30 min', fim + interval '30 min', fim_ambiente + interval '30 min', minutos_aula, status, fixa, origem, 1 FROM alocacoes WHERE id=:id"),
                   {"id": a.id, "t2": m.t2.id})
    db.rollback()
    assert "excl_alocacao_ambiente" in str(e.value)


def test_05_ambiente_incompativel(db, mundo):
    m = mundo
    with pytest.raises(ConflitoValidacao) as e:
        aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_c, instrutor=m.i2, ambiente=m.s1, grupo=1))
    assert "AMBIENTE_INCOMPATIVEL" in regras(e.value)


def test_06_excesso_de_capacidade(db, mundo):
    m = mundo
    # turma inteira (30 alunos) no laboratório de 20 lugares
    m.uc_c.divide_grupos = False
    m.uc_c.capacidade_max = None
    db.commit()
    with pytest.raises(ConflitoValidacao) as e:
        aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t2, m.uc_c, instrutor=m.i2, ambiente=m.lab1))
    assert "CAPACIDADE_FISICA" in regras(e.value)


def test_07_instrutor_sem_habilitacao(db, mundo):
    m = mundo
    with pytest.raises(ConflitoValidacao) as e:
        aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i3, ambiente=m.s1))
    assert "INSTRUTOR_NAO_HABILITADO" in regras(e.value)
    # a alternativa sugerida é um instrutor habilitado e livre
    nomes = {i["nome"] for i in e.value.detalhes["alternativas"]["instrutores"]}
    assert nomes == {"Instrutor 1", "Instrutor 2"}


def test_08_fora_da_disponibilidade(db, mundo):
    m = mundo
    from app.models import DisponibilidadeInstrutor
    db.execute(DisponibilidadeInstrutor.__table__.delete().where(DisponibilidadeInstrutor.instrutor_id == m.i1.id, DisponibilidadeInstrutor.dia_semana == 0))
    db.commit()
    with pytest.raises(ConflitoValidacao) as e:
        aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s1))
    assert "INSTRUTOR_FORA_DISPONIBILIDADE" in regras(e.value)


def test_09_horario_bloqueado_e_feriado(db, mundo):
    m = mundo
    db.add(Bloqueio(alvo_tipo="ambiente", alvo_id=m.s1.id, inicio=datetime(2026, 8, 3, 7, 0), fim=datetime(2026, 8, 3, 12, 0), tipo="manutencao", motivo="pintura"))
    db.commit()
    with pytest.raises(ConflitoValidacao) as e:
        aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s1))
    assert "BLOQUEIO_AMBIENTE" in regras(e.value)
    db.rollback()
    feriado = date(2026, 9, 7)
    with pytest.raises(ConflitoValidacao) as e:
        aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, d=feriado, instrutor=m.i1, ambiente=m.s2))
    assert "DIA_NAO_LETIVO" in regras(e.value)
    db.rollback()
    # com exceção autorizada e documentada, a aula no feriado é aceita (como alerta)
    ex = ExcecaoAutorizada(tipo="feriado_bloqueio", justificativa="Reposição aprovada pela coordenação", autorizado_por_id=m.admin.id)
    db.add(ex)
    db.commit()
    a, oc = aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, d=feriado, instrutor=m.i1, ambiente=m.s2, excecao_id=ex.id))
    db.commit()
    assert a.id and any(o.regra == "EXCECAO_CALENDARIO" for o in oc)


def test_10_sobreposicao_parcial(db, mundo):
    m = mundo
    from datetime import time
    aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s1))  # 07:30–09:10
    db.commit()
    from app.services.alocacao import DadosAula
    d = DadosAula(turma_uc_id=m.tuc(db, m.t2, m.uc_a).id, data=SEG, hora_inicio=time(9, 0), hora_fim=time(10, 0), instrutor_id=m.i2.id, ambiente_id=m.s1.id)
    with pytest.raises(ConflitoValidacao) as e:
        aloc.criar_aula(db, m.ctx, m.cen.id, d)
    assert "AMBIENTE_SOBREPOSICAO" in regras(e.value)
    db.rollback()
    # encostar (09:10) não é sobreposição
    d.hora_inicio, d.hora_fim = time(9, 10), time(10, 0)
    a, _ = aloc.criar_aula(db, m.ctx, m.cen.id, d)
    db.commit()
    assert a.id


def test_11_carga_horaria_excedida(db, mundo):
    m = mundo
    m.uc_a.carga_horaria_total = 3  # 3 h: cabe uma aula de 100 min, a segunda excede
    db.commit()
    aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s1))
    db.commit()
    with pytest.raises(ConflitoValidacao) as e:
        aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, d=SEG + timedelta(days=1), instrutor=m.i1, ambiente=m.s1))
    assert "CARGA_HORARIA_EXCEDIDA" in regras(e.value)
    db.rollback()
    ex = ExcecaoAutorizada(tipo="carga_horaria", justificativa="Reforço aprovado em ata 12/2026", autorizado_por_id=m.admin.id)
    db.add(ex)
    db.commit()
    a, oc = aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, d=SEG + timedelta(days=1), instrutor=m.i1, ambiente=m.s1, excecao_id=ex.id))
    assert any(o.regra == "CH_EXCEDIDA_AUTORIZADA" for o in oc)


def test_24_integridade_apos_falha_de_transacao(db, mundo):
    """Recorrência atômica: se uma data falhar, nenhuma aula nem atividade é gravada."""
    m = mundo
    # ocupa a sala em uma das segundas do semestre
    aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t2, m.uc_b, d=SEG + timedelta(days=28), instrutor=m.i1, ambiente=m.s1))
    db.commit()
    antes = contar(db, m.cen.id)
    with pytest.raises(ConflitoValidacao) as e:
        aloc.criar_recorrente(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i2, ambiente=m.s1), 0, SEG, date(2026, 12, 18))
    db.rollback()
    assert len(e.value.detalhes["falhas"]) == 1
    assert contar(db, m.cen.id) == antes
    assert db.scalar(select(func.count()).select_from(Atividade)) == 0
    # e a edição inválida não substitui a aula válida
    a = db.scalar(select(Alocacao))
    with pytest.raises(ConflitoValidacao):
        aloc.atualizar_aula(db, m.ctx, a.id, aula(m, db, m.t2, m.uc_b, d=a.data, instrutor=m.i3, ambiente=m.s1), a.versao)
    db.rollback()
    db.expire_all()
    a2 = db.get(Alocacao, a.id)
    assert a2.instrutor_id == m.i1.id and a2.versao == a.versao


def test_24b_versao_desatualizada(db, mundo):
    m = mundo
    a, _ = aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s1))
    db.commit()
    aloc.atualizar_aula(db, m.ctx, a.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s2), 1)
    db.commit()
    with pytest.raises(ConflitoConcorrencia):
        aloc.atualizar_aula(db, m.ctx, a.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i2, ambiente=m.s2), 1)


def test_27_equipamentos_compartilhados(db, mundo):
    m = mundo
    kit = Recurso(codigo="KIT", nome="Kit CLP", tipo="kit_clp", unidade_id=m.unidade.id, quantidade_total=8, movel=True)
    db.add(kit)
    db.add(UCRecurso(uc_id=m.uc_a.id, recurso_tipo="kit_clp", quantidade=5))
    db.commit()
    # sem reservar o kit, a UC não pode ocorrer (sala não tem kit fixo)
    with pytest.raises(ConflitoValidacao) as e:
        aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s1))
    assert "RECURSO_AUSENTE" in regras(e.value)
    db.rollback()
    aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s1, recursos=[(kit.id, 5)]))
    db.commit()
    # outra turma no mesmo horário pede mais 5 kits: só restam 3
    with pytest.raises(ConflitoValidacao) as e:
        aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t2, m.uc_a, instrutor=m.i2, ambiente=m.s2, recursos=[(kit.id, 5)]))
    assert "RECURSO_CONFLITO" in regras(e.value)
    db.rollback()
    # em horário diferente, o mesmo acervo está livre
    aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t2, m.uc_a, periodo=2, instrutor=m.i2, ambiente=m.s2, recursos=[(kit.id, 5)]))
    db.commit()


def test_28_divisao_em_grupos(db, mundo):
    m = mundo
    # grupo 1 e grupo 2 em paralelo (ambientes e instrutores distintos) é permitido
    aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_c, instrutor=m.i2, ambiente=m.lab1, grupo=1))
    db.commit()
    # grupo 2 em outro ambiente compatível? só há um laboratório → conflito de ambiente, não de turma
    with pytest.raises(ConflitoValidacao) as e:
        aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_c, instrutor=m.i2, ambiente=m.lab1, grupo=2))
    r = regras(e.value)
    assert "AMBIENTE_SOBREPOSICAO" in r and "TURMA_SOBREPOSICAO" not in r
    db.rollback()
    # aula da turma inteira conflita com a aula do grupo 1
    with pytest.raises(ConflitoValidacao) as e:
        aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s1))
    assert "TURMA_SOBREPOSICAO" in regras(e.value)
    db.rollback()
    # mesmo grupo duas vezes conflita; grupo inexistente é bloqueado
    with pytest.raises(ConflitoValidacao) as e:
        aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_c, instrutor=m.i2, ambiente=m.lab1, grupo=3, d=SEG + timedelta(days=1)))
    assert "GRUPO_INVALIDO" in regras(e.value)
    db.rollback()
    # UC que não prevê grupos não aceita aula por grupo
    with pytest.raises(ConflitoValidacao) as e:
        aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s1, grupo=2))
    assert "GRUPO_NAO_PREVISTO" in regras(e.value)


def test_jornada_e_interjornada(db, mundo):
    m = mundo
    m.i1.max_horas_dia = 3
    db.commit()
    aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s1))
    db.commit()
    with pytest.raises(ConflitoValidacao) as e:
        aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t2, m.uc_b, periodo=2, instrutor=m.i1, ambiente=m.s2))
    assert "JORNADA_DIARIA" in regras(e.value)
