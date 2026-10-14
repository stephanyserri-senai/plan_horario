"""Versionamento, publicação, indicadores e simulador (casos 19, 20, 22, 23, 25, 26)."""
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select, text

from app.core.errors import ConflitoValidacao
from app.models import Alocacao, CenarioPlanejamento, Turma
from app.services import alocacao as aloc
from app.services import cenarios, indicadores, simulador
from tests.conftest import SEG, aula

SEXTA = SEG + timedelta(days=4)


def taxa(db, m, ambiente):
    r = indicadores.ocupacao_ambientes(db, m.cen.id, SEG, SEXTA)
    return next(a for a in r["ambientes"] if a["ambiente_id"] == ambiente.id)


def test_25_ocupacao_por_turno(db, mundo):
    m = mundo
    aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s1))  # 100 min
    db.commit()
    r = indicadores.ocupacao_ambientes(db, m.cen.id, SEG, SEXTA)
    s1 = next(a for a in r["ambientes"] if a["ambiente_id"] == m.s1.id)
    # 5 dias letivos × 4 períodos × 50 min = 1000 min disponíveis
    assert s1["horas_disponiveis"] == pytest.approx(1000 / 60, abs=0.01)
    assert s1["horas_ocupadas"] == pytest.approx(100 / 60, abs=0.01)
    assert s1["taxa_ocupacao_pct"] == pytest.approx(10.0)
    manha = next(t for t in r["por_turno"] if t["turno_id"] == m.manha.id)
    # 3 ambientes × 1000 min disponíveis; 100 min ocupados
    assert manha["taxa_ocupacao_pct"] == pytest.approx(round(100 * 100 / 3000, 1))
    # semana com feriado: segunda 07/09 não conta como disponível
    r2 = indicadores.ocupacao_ambientes(db, m.cen.id, date(2026, 9, 7), date(2026, 9, 11))
    assert next(a for a in r2["ambientes"] if a["ambiente_id"] == m.s1.id)["horas_disponiveis"] == pytest.approx(800 / 60, abs=0.01)


def test_26_carga_horaria_dos_instrutores(db, mundo):
    m = mundo
    aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s1))
    aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t2, m.uc_b, d=SEG + timedelta(days=1), instrutor=m.i1, ambiente=m.s1))
    db.commit()
    r = indicadores.ocupacao_instrutores(db, m.cen.id, SEG, SEXTA)
    i1 = next(i for i in r["instrutores"] if i["instrutor_id"] == m.i1.id)
    assert i1["alocada_total_h"] == pytest.approx(200 / 60, abs=0.01)
    # capacidade efetiva = min(limite letivo 20 h, disponibilidade 55 h) — não a jornada contratual de 40 h
    assert i1["capacidade_efetiva_h"] == 20
    assert i1["ocupacao_pct"] == pytest.approx(round(100 * (200 / 60) / 20, 1))
    assert i1["turmas"] == 2 and i1["ucs"] == 2


def test_20_indicadores_atualizados_apos_mudanca(db, mundo):
    m = mundo
    assert taxa(db, m, m.s1)["horas_ocupadas"] == 0
    a, _ = aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s1))
    db.commit()
    assert taxa(db, m, m.s1)["taxa_ocupacao_pct"] == pytest.approx(10.0)
    aloc.atualizar_aula(db, m.ctx, a.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s2), a.versao)
    db.commit()
    assert taxa(db, m, m.s1)["horas_ocupadas"] == 0
    assert taxa(db, m, m.s2)["taxa_ocupacao_pct"] == pytest.approx(10.0)


def test_19_comparacao_e_restauracao_de_versoes(db, mundo):
    m = mundo
    aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s1))
    db.commit()
    v1 = cenarios.criar_versao(db, m.ctx, m.cen.id, "v1")
    aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t2, m.uc_a, instrutor=m.i2, ambiente=m.s2))
    db.commit()
    v2 = cenarios.criar_versao(db, m.ctx, m.cen.id, "v2")
    db.commit()
    d = cenarios.comparar_versoes(db, v1.id, v2.id)
    assert d["adicionadas"] == 1 and d["removidas"] == 0
    assert m.t2.id in d["recursos_afetados"]["turmas"]
    r = cenarios.restaurar(db, m.ctx, v1.id)
    db.commit()
    assert db.scalar(select(func.count()).select_from(Alocacao).where(Alocacao.cenario_id == m.cen.id)) == 1
    assert r["validacao"]["bloqueios"] == 0


def _publicar(db, m, cid):
    for estado in ("em_validacao", "aguardando_aprovacao", "aprovado", "publicado"):
        cenarios.transicionar(db, m.ctx, cid, estado)
        db.commit()


def test_publicacao_exige_validacao_e_bloqueia_edicao(db, mundo):
    m = mundo
    aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s1))
    db.commit()
    # força uma violação diretamente no banco (instrutor sem habilitação)
    db.execute(text("UPDATE alocacoes SET instrutor_id=:i"), {"i": m.i3.id})
    db.commit()
    cenarios.transicionar(db, m.ctx, m.cen.id, "em_validacao")
    db.commit()
    with pytest.raises(ConflitoValidacao) as e:
        cenarios.transicionar(db, m.ctx, m.cen.id, "aguardando_aprovacao")
    db.rollback()
    assert e.value.codigo == "VALIDACAO_BLOQUEADA"
    db.execute(text("UPDATE alocacoes SET instrutor_id=:i"), {"i": m.i1.id})
    db.commit()
    for estado in ("aguardando_aprovacao", "aprovado", "publicado"):
        cenarios.transicionar(db, m.ctx, m.cen.id, estado)
        db.commit()
    assert db.get(CenarioPlanejamento, m.cen.id).estado == "publicado"
    with pytest.raises(ConflitoValidacao):
        aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t2, m.uc_a, instrutor=m.i2, ambiente=m.s2))
    db.rollback()
    # alteração do publicado: proposta → validação → impacto
    p = cenarios.proposta_alteracao(db, m.ctx, m.cen.id, "Troca de sala")
    db.commit()
    a = db.scalars(select(Alocacao).where(Alocacao.cenario_id == p.id)).first()
    aloc.atualizar_aula(db, m.ctx, a.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s2), a.versao)
    db.commit()
    imp = cenarios.impacto_proposta(db, p.id)
    assert imp["alteradas"] == 1 and m.s2.id in imp["recursos_afetados"]["ambientes"]
    _publicar(db, m, p.id)
    db.expire_all()
    assert db.get(CenarioPlanejamento, m.cen.id).estado == "arquivado"
    assert db.get(CenarioPlanejamento, p.id).estado == "publicado"


def _params(m):
    return {"curso_id": m.curso.id, "matriz_id": m.matriz.id, "unidade_id": m.unidade.id, "quantidade_turmas": 1, "alunos_por_turma": 16,
            "data_inicio": "2026-08-03", "data_fim": "2026-12-18", "turno_id": m.manha.id, "dias_semana": [0, 1, 2, 3, 4],
            "calendario_id": m.cal.id, "ucs_sequenciais": False}


def test_22_23_simulacao_nao_altera_vigente_e_compara(db, mundo):
    m = mundo
    aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s1))
    db.commit()
    _publicar(db, m, m.cen.id)
    antes = db.execute(text("SELECT id, inicio, instrutor_id, ambiente_id FROM alocacoes WHERE cenario_id=:c ORDER BY id"), {"c": m.cen.id}).all()
    turmas_antes = db.scalar(select(func.count()).select_from(Turma).where(Turma.simulacao_id.is_(None)))
    ag = simulador.simular_agregada(db, _params(m), m.cen.id)
    assert ag["carga_horaria_adicional_semanal_h"] > 0 and ag["viabilidade_estimada"] in ("provavel", "condicionada", "inviavel_sem_novos_recursos")
    sim = simulador.simular_completa(db, m.ctx, _params(m), m.cen.id, "Nova turma", limite_tempo_s=15)
    db.expire_all()
    depois = db.execute(text("SELECT id, inicio, instrutor_id, ambiente_id FROM alocacoes WHERE cenario_id=:c ORDER BY id"), {"c": m.cen.id}).all()
    assert antes == depois  # planejamento vigente intacto
    assert db.get(CenarioPlanejamento, m.cen.id).estado == "publicado"
    assert db.scalar(select(func.count()).select_from(Turma).where(Turma.simulacao_id.is_(None))) == turmas_antes
    r = sim.resultado
    assert r["completa"]["status_solver"] in ("OTIMA", "VIAVEL"), r["completa"]
    assert r["viabilidade"] == "viavel"
    comp = r["comparacao"]
    assert comp["com_novas_turmas"]["aulas"] > comp["atual"]["aulas"]
    sim_cen = db.get(CenarioPlanejamento, sim.cenario_simulado_id)
    assert sim_cen.tipo == "simulacao"
    with pytest.raises(ConflitoValidacao):
        _publicar(db, m, sim_cen.id)
    db.rollback()
    simulador.remover_simulacao(db, m.ctx, sim.id)
    db.commit()
    assert db.scalar(select(func.count()).select_from(Turma).where(Turma.simulacao_id.isnot(None))) == 0


def test_comparacao_entre_cenarios_usa_mesmos_pesos(db, mundo):
    m = mundo
    aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s1))
    aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_b, periodo=2, instrutor=m.i1, ambiente=m.s1))
    db.commit()
    c2 = cenarios.copiar(db, m.ctx, m.cen.id, "Alternativo")
    db.commit()
    # no cenário 2, uma janela para o instrutor
    a = db.scalars(select(Alocacao).where(Alocacao.cenario_id == c2.id, Alocacao.uc_id == m.uc_b.id)).first()
    aloc.atualizar_aula(db, m.ctx, a.id, aula(m, db, m.t1, m.uc_b, periodo=2, instrutor=m.i1, ambiente=m.s1, d=SEG + timedelta(days=0)), a.versao)
    db.commit()
    r = cenarios.comparar(db, [m.cen.id, c2.id], {"janelas_instrutores": 10})
    assert r["cenarios"][0]["avaliacao"]["pesos"] == r["cenarios"][1]["avaliacao"]["pesos"]
    assert set(r["ranking"]) == {m.cen.id, c2.id}
