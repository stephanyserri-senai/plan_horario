"""Infraestrutura de testes: banco PostgreSQL real (exclusion constraints,
advisory locks e transações são parte do que está sendo testado).

Banco: PLAN_TEST_DATABASE_URL (padrão: plan_horario_test local). As tabelas
são truncadas antes de cada teste.
"""
import os
from dataclasses import dataclass
from datetime import date, time

import pytest

URL = os.environ.get("PLAN_TEST_DATABASE_URL", "postgresql+psycopg://plan:plan@localhost:5432/plan_horario_test")
os.environ["PLAN_DATABASE_URL"] = URL
os.environ["PLAN_AMBIENTE"] = "teste"
os.environ["PLAN_SOLVER_THREADS"] = "2"

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import Base, SessionLocal, reset_engine  # noqa: E402
from app.core.deps import carregar_contexto  # noqa: E402
from app.models import (  # noqa: E402
    Ambiente, Calendario, CalendarioExcecao, CenarioPlanejamento, CompetenciaInstrutor, Curso, DisponibilidadeInstrutor, Instrutor,
    Configuracao, MatrizCurricular, PeriodoHorario, Recurso, TipoAmbiente, Turma, TurmaUC, Turno, UCTipoAmbiente, Unidade, UnidadeCurricular, Usuario,
)
from app.core.security import hash_senha  # noqa: E402

get_settings.cache_clear()


@pytest.fixture(scope="session", autouse=True)
def banco():
    reset_engine(URL)
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    os.environ["ALEMBIC_DATABASE_URL"] = URL
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def limpar(banco):
    tabelas = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    with SessionLocal() as s:
        s.execute(text(f"TRUNCATE {tabelas} RESTART IDENTITY CASCADE"))
        s.commit()
        from app import seed
        seed.executar(s)
    yield


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


SEG = date(2026, 8, 3)  # segunda-feira


@dataclass
class Mundo:
    unidade: Unidade
    manha: Turno
    periodos: list
    cal: Calendario
    sala: TipoAmbiente
    lab: TipoAmbiente
    s1: Ambiente
    s2: Ambiente
    lab1: Ambiente
    curso: Curso
    matriz: MatrizCurricular
    uc_a: UnidadeCurricular
    uc_b: UnidadeCurricular
    uc_c: UnidadeCurricular
    i1: Instrutor
    i2: Instrutor
    i3: Instrutor
    t1: Turma
    t2: Turma
    cen: CenarioPlanejamento
    admin: Usuario
    ctx: object

    def tuc(self, db, turma, uc):
        from sqlalchemy import select
        return db.scalar(select(TurmaUC).where(TurmaUC.turma_id == turma.id, TurmaUC.uc_id == uc.id))


def criar_mundo(db, regras: dict | None = None) -> Mundo:
    # Os cenários de teste clássicos usam blocos de 2 aulas e minutos reais; os testes da
    # regra "turno inteiro + hora-aula" (padrão da instituição) passam `regras` explicitamente.
    db.merge(Configuracao(chave="regras_aula", valor=regras or {"turno_inteiro": False, "contagem": "relogio"}))
    u = Unidade(codigo="U1", nome="Unidade 1")
    db.add(u)
    db.flush()
    manha = Turno(unidade_id=u.id, codigo="M", nome="Manhã", hora_inicio=time(7, 30), hora_fim=time(11, 40))
    db.add(manha)
    db.flush()
    ps = []
    for i, (hi, hf) in enumerate([(time(7, 30), time(8, 20)), (time(8, 20), time(9, 10)), (time(9, 30), time(10, 20)), (time(10, 20), time(11, 10))], 1):
        p = PeriodoHorario(unidade_id=u.id, turno_id=manha.id, ordem=i, hora_inicio=hi, hora_fim=hf, dias_semana=[0, 1, 2, 3, 4])
        db.add(p)
        ps.append(p)
    cal = Calendario(unidade_id=u.id, nome="2026/2", data_inicio=date(2026, 8, 3), data_fim=date(2026, 12, 18))
    db.add(cal)
    db.flush()
    db.add(CalendarioExcecao(calendario_id=cal.id, data=date(2026, 9, 7), tipo="feriado", descricao="Independência"))
    sala = TipoAmbiente(codigo="SALA", nome="Sala", especializado=False)
    lab = TipoAmbiente(codigo="LAB", nome="Laboratório", especializado=True)
    db.add_all([sala, lab])
    db.flush()
    s1 = Ambiente(codigo="S1", nome="Sala 1", unidade_id=u.id, tipo_ambiente_id=sala.id, capacidade_fisica=40, capacidade_operacional=36)
    s2 = Ambiente(codigo="S2", nome="Sala 2", unidade_id=u.id, tipo_ambiente_id=sala.id, capacidade_fisica=40, capacidade_operacional=36)
    lab1 = Ambiente(codigo="L1", nome="Lab 1", unidade_id=u.id, tipo_ambiente_id=lab.id, capacidade_fisica=20, capacidade_operacional=16)
    db.add_all([s1, s2, lab1])
    curso = Curso(codigo="C1", nome="Curso 1", unidade_id=u.id)
    db.add(curso)
    db.flush()
    m = MatrizCurricular(curso_id=curso.id, versao="1")
    db.add(m)
    db.flush()
    uc_a = UnidadeCurricular(matriz_id=m.id, codigo="A", nome="UC A", carga_horaria_total=40, duracao_bloco_periodos=2, encontros_semanais=1)
    uc_b = UnidadeCurricular(matriz_id=m.id, codigo="B", nome="UC B", carga_horaria_total=40, duracao_bloco_periodos=2, encontros_semanais=1)
    uc_c = UnidadeCurricular(matriz_id=m.id, codigo="C", nome="UC C (lab)", carga_horaria_total=20, duracao_bloco_periodos=2, encontros_semanais=1,
                             divide_grupos=True, capacidade_max=16)
    db.add_all([uc_a, uc_b, uc_c])
    db.flush()
    db.add_all([UCTipoAmbiente(uc_id=uc_a.id, tipo_ambiente_id=sala.id), UCTipoAmbiente(uc_id=uc_b.id, tipo_ambiente_id=sala.id),
                UCTipoAmbiente(uc_id=uc_c.id, tipo_ambiente_id=lab.id)])
    insts = []
    for mat, nome, ucs in (("I1", "Instrutor 1", [uc_a, uc_b]), ("I2", "Instrutor 2", [uc_a, uc_c]), ("I3", "Instrutor 3", [])):
        i = Instrutor(matricula=mat, nome=nome, unidade_id=u.id, carga_horaria_contratual=40, limite_ch_letiva=20, max_horas_dia=8, intervalo_minimo_h=11)
        db.add(i)
        db.flush()
        for uc in ucs:
            db.add(CompetenciaInstrutor(instrutor_id=i.id, uc_id=uc.id, nivel="pleno"))
        for d in range(5):
            db.add(DisponibilidadeInstrutor(instrutor_id=i.id, dia_semana=d, hora_inicio=time(7, 0), hora_fim=time(18, 0)))
        insts.append(i)
    t1 = Turma(codigo="T1", nome="Turma 1", curso_id=curso.id, matriz_id=m.id, unidade_id=u.id, calendario_id=cal.id, turno_id=manha.id, qtd_alunos=30,
               data_inicio=date(2026, 8, 3), data_fim=date(2026, 12, 18), num_grupos=2)
    t2 = Turma(codigo="T2", nome="Turma 2", curso_id=curso.id, matriz_id=m.id, unidade_id=u.id, calendario_id=cal.id, turno_id=manha.id, qtd_alunos=30,
               data_inicio=date(2026, 8, 3), data_fim=date(2026, 12, 18), num_grupos=2)
    db.add_all([t1, t2])
    db.flush()
    for t in (t1, t2):
        for uc in (uc_a, uc_b, uc_c):
            db.add(TurmaUC(turma_id=t.id, uc_id=uc.id, situacao="ofertada"))
    cen = CenarioPlanejamento(nome="Cenário teste", unidade_id=u.id, periodo_inicio=date(2026, 8, 3), periodo_fim=date(2026, 12, 18))
    admin = Usuario(nome="Admin", email="admin@teste", senha_hash=hash_senha("senha-forte-1"), perfil="administrador", acesso_global=True)
    db.add_all([cen, admin])
    db.commit()
    return Mundo(u, manha, ps, cal, sala, lab, s1, s2, lab1, curso, m, uc_a, uc_b, uc_c, *insts, t1, t2, cen, admin, carregar_contexto(db, admin))


@pytest.fixture
def mundo(db):
    return criar_mundo(db)


def aula(m: Mundo, db, turma, uc, d=SEG, periodo=0, n=2, instrutor=None, ambiente=None, grupo=None, **kw):
    from app.services.alocacao import DadosAula
    return DadosAula(turma_uc_id=m.tuc(db, turma, uc).id, data=d, periodo_inicio_id=m.periodos[periodo].id, num_periodos=n,
                     instrutor_id=instrutor.id if instrutor else None, ambiente_id=ambiente.id if ambiente else None, grupo=grupo, **kw)
