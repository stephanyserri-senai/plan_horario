"""DADOS DE DEMONSTRAÇÃO — não usar em produção.

Todos os registros usam o prefixo 'DEMO-' e podem ser removidos com:
    python -m app.demo remover
Carga:
    python -m app.demo carregar
"""
import sys
from datetime import date, time

from sqlalchemy import delete, select, text

from app.core.db import SessionLocal
from app.services.regras_aula import TURNOS_PADRAO
from app.models import (
    Ambiente, Calendario, CalendarioExcecao, CenarioPlanejamento, CompetenciaInstrutor, Curso, DisponibilidadeInstrutor, HabilitacaoInstrutor,
    Instrutor, MatrizCurricular, PeriodoHorario, Recurso, RecursoAmbiente, TipoAmbiente, Turma, TurmaUC, Turno, UCRecurso, UCTipoAmbiente, Unidade,
    UnidadeCurricular,
)

PREFIXO = "DEMO-"


def _hm(m: int) -> time:
    return time(m // 60, m % 60)


def carregar(db, ano: int = 2026):
    if db.scalar(select(Unidade).where(Unidade.codigo == f"{PREFIXO}U1")):
        return "já carregado"
    un = Unidade(codigo=f"{PREFIXO}U1", nome="DEMO – Unidade Centro", cidade="Vitória")
    db.add(un)
    db.flush()
    # Turnos da instituição: 4 aulas por turno (55 min de manhã/tarde, 50 min à noite) com intervalo no meio.
    turnos = {}
    for ordem, (cod, nome, aulas) in enumerate(TURNOS_PADRAO, 1):
        t = Turno(unidade_id=un.id, codigo=f"{PREFIXO}{cod}", nome=nome, hora_inicio=_hm(aulas[0][0]), hora_fim=_hm(aulas[-1][0] + aulas[-1][1]), ordem=ordem)
        db.add(t)
        db.flush()
        for i, (ini, dur) in enumerate(aulas, 1):
            db.add(PeriodoHorario(unidade_id=un.id, turno_id=t.id, ordem=i, hora_inicio=_hm(ini), hora_fim=_hm(ini + dur), dias_semana=[0, 1, 2, 3, 4]))
        turnos[cod] = t
    manha, tarde = turnos["M"], turnos["T"]
    cal = Calendario(unidade_id=un.id, nome=f"{PREFIXO}Calendário {ano}/2", data_inicio=date(ano, 8, 3), data_fim=date(ano, 12, 18))
    db.add(cal)
    db.flush()
    for d, desc in [(date(ano, 9, 7), "Independência"), (date(ano, 10, 12), "N. Sra. Aparecida"), (date(ano, 11, 2), "Finados"),
                    (date(ano, 11, 20), "Consciência Negra")]:
        db.add(CalendarioExcecao(calendario_id=cal.id, data=d, tipo="feriado", descricao=desc))
    tipos = {c: TipoAmbiente(codigo=f"{PREFIXO}{c}", nome=n, especializado=e) for c, n, e in
             [("SALA", "Sala de aula", False), ("INFO", "Laboratório de informática", True), ("CMD", "Laboratório de comandos elétricos", True)]}
    db.add_all(tipos.values())
    db.flush()
    salas = [Ambiente(codigo=f"{PREFIXO}S{n}", nome=f"Sala {n}", unidade_id=un.id, tipo_ambiente_id=tipos["SALA"].id, capacidade_fisica=40,
                      capacidade_operacional=36) for n in (101, 102)]
    info = Ambiente(codigo=f"{PREFIXO}LI1", nome="Lab. Informática 1", unidade_id=un.id, tipo_ambiente_id=tipos["INFO"].id, capacidade_fisica=32, capacidade_operacional=30)
    cmd = Ambiente(codigo=f"{PREFIXO}LC1", nome="Lab. Comandos Elétricos", unidade_id=un.id, tipo_ambiente_id=tipos["CMD"].id, capacidade_fisica=32,
                   capacidade_operacional=30, tempo_preparacao_min=10)
    db.add_all(salas + [info, cmd])
    db.flush()
    bancada = Recurso(codigo=f"{PREFIXO}BAN", nome="Bancadas de comandos", tipo="bancada_comandos", unidade_id=un.id, quantidade_total=8)
    clp = Recurso(codigo=f"{PREFIXO}CLP", nome="Kits CLP (móveis)", tipo="kit_clp", unidade_id=un.id, quantidade_total=8, movel=True)
    db.add_all([bancada, clp])
    db.flush()
    db.add(RecursoAmbiente(recurso_id=bancada.id, ambiente_id=cmd.id, quantidade=8))
    curso = Curso(codigo=f"{PREFIXO}ELT", nome="Técnico em Eletrotécnica", modalidade="presencial", tipo="técnico", carga_horaria_total=1200,
                  eixo_tecnologico="Controle e Processos Industriais", unidade_id=un.id)
    db.add(curso)
    db.flush()
    mat = MatrizCurricular(curso_id=curso.id, versao="2026.1", situacao="vigente")
    db.add(mat)
    db.flush()
    ucs = []
    # Carga horária em hora-aula; cada encontro ocupa o turno inteiro (4 aulas).
    # DTE (30 h) e INF (18 h) não são múltiplos de 4: suas últimas aulas são "fechamentos" de 2 aulas
    # e o gerador as junta no mesmo turno.
    for cod, nome, ch, tipos_uc, enc in [("FEL", "Fundamentos de Eletricidade", 40, ["SALA"], 2), ("DTE", "Desenho Técnico", 30, ["SALA", "INFO"], 1),
                                         ("CMD", "Comandos Elétricos", 60, ["CMD"], 1), ("INF", "Informática Aplicada", 18, ["INFO"], 1)]:
        uc = UnidadeCurricular(matriz_id=mat.id, codigo=f"{PREFIXO}{cod}", nome=nome, carga_horaria_total=ch, duracao_bloco_periodos=4, encontros_semanais=enc,
                               certificacao_exigida="NR-10" if cod == "CMD" else None)
        db.add(uc)
        db.flush()
        for t in tipos_uc:
            db.add(UCTipoAmbiente(uc_id=uc.id, tipo_ambiente_id=tipos[t].id))
        ucs.append(uc)
    db.add(UCRecurso(uc_id=ucs[2].id, recurso_tipo="bancada_comandos", quantidade=8))
    nomes = [("DEMO-I01", "Ana (DEMO)", ["FEL", "CMD"]), ("DEMO-I02", "Bruno (DEMO)", ["FEL", "DTE"]), ("DEMO-I03", "Carla (DEMO)", ["INF", "DTE"]),
             ("DEMO-I04", "Diego (DEMO)", ["CMD"])]
    por_cod = {u.codigo.replace(PREFIXO, ""): u for u in ucs}
    for mat_i, nome, comps in nomes:
        i = Instrutor(matricula=mat_i, nome=nome, unidade_id=un.id, carga_horaria_contratual=40, limite_ch_letiva=24, max_horas_dia=8)
        db.add(i)
        db.flush()
        for c in comps:
            db.add(CompetenciaInstrutor(instrutor_id=i.id, uc_id=por_cod[c].id, nivel="pleno"))
        if "CMD" in comps:
            db.add(HabilitacaoInstrutor(instrutor_id=i.id, nome="NR-10"))
        for d in range(5):
            db.add(DisponibilidadeInstrutor(instrutor_id=i.id, dia_semana=d, hora_inicio=time(7, 30), hora_fim=time(17, 30)))
    for n, turno in ((1, manha), (2, tarde)):
        t = Turma(codigo=f"{PREFIXO}ELT-{n}", nome=f"Eletrotécnica {n} (DEMO)", curso_id=curso.id, matriz_id=mat.id, unidade_id=un.id, calendario_id=cal.id,
                  turno_id=turno.id, qtd_alunos=30, data_inicio=date(ano, 8, 3), data_fim=date(ano, 12, 18), num_grupos=1)
        db.add(t)
        db.flush()
        for uc in ucs:
            db.add(TurmaUC(turma_id=t.id, uc_id=uc.id, situacao="ofertada"))
    db.add(CenarioPlanejamento(nome=f"{PREFIXO}Planejamento {ano}/2", unidade_id=un.id, periodo_inicio=date(ano, 8, 3), periodo_fim=date(ano, 12, 18)))
    db.commit()
    return "carregado"


def remover(db):
    un = db.scalar(select(Unidade).where(Unidade.codigo == f"{PREFIXO}U1"))
    if not un:
        return "nada a remover"
    uid = un.id
    db.execute(delete(CenarioPlanejamento).where(CenarioPlanejamento.unidade_id == uid))
    for sql in [
        "DELETE FROM turmas WHERE unidade_id=:u",
        "DELETE FROM competencias_instrutores WHERE instrutor_id IN (SELECT id FROM instrutores WHERE unidade_id=:u)",
        "DELETE FROM instrutores WHERE unidade_id=:u",
        "DELETE FROM uc_tipos_ambiente WHERE uc_id IN (SELECT u.id FROM unidades_curriculares u JOIN matrizes_curriculares m ON m.id=u.matriz_id JOIN cursos c ON c.id=m.curso_id WHERE c.unidade_id=:u)",
        "DELETE FROM uc_recursos WHERE uc_id IN (SELECT u.id FROM unidades_curriculares u JOIN matrizes_curriculares m ON m.id=u.matriz_id JOIN cursos c ON c.id=m.curso_id WHERE c.unidade_id=:u)",
        "DELETE FROM unidades_curriculares WHERE matriz_id IN (SELECT m.id FROM matrizes_curriculares m JOIN cursos c ON c.id=m.curso_id WHERE c.unidade_id=:u)",
        "DELETE FROM matrizes_curriculares WHERE curso_id IN (SELECT id FROM cursos WHERE unidade_id=:u)",
        "DELETE FROM cursos WHERE unidade_id=:u",
        "DELETE FROM recursos_ambientes WHERE ambiente_id IN (SELECT id FROM ambientes WHERE unidade_id=:u)",
        "DELETE FROM recursos WHERE unidade_id=:u",
        "DELETE FROM ambientes WHERE unidade_id=:u",
        "DELETE FROM tipos_ambiente WHERE codigo LIKE 'DEMO-%'",
        "DELETE FROM calendario_excecoes WHERE calendario_id IN (SELECT id FROM calendarios WHERE unidade_id=:u)",
        "DELETE FROM calendarios WHERE unidade_id=:u",
        "DELETE FROM periodos_horarios WHERE unidade_id=:u",
        "DELETE FROM turnos WHERE unidade_id=:u",
        "DELETE FROM unidades WHERE id=:u",
    ]:
        db.execute(text(sql), {"u": uid})
    db.commit()
    return "removido"


if __name__ == "__main__":
    from app.core.config import get_settings
    acao = sys.argv[1] if len(sys.argv) > 1 else "carregar"
    if acao in ("carregar", "recarregar") and get_settings().producao:
        raise SystemExit("Recusado: dados de demonstração não podem ser carregados com PLAN_AMBIENTE=producao.")
    with SessionLocal() as s:
        if acao == "recarregar":
            print(remover(s), "→", carregar(s))
        else:
            print((carregar if acao == "carregar" else remover)(s))
