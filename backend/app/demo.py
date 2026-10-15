"""DADOS DE DEMONSTRAÇÃO — não usar em produção.

Os dados ficam na unidade oficial Beira Mar (usando os turnos oficiais) e todos os
registros criados usam o prefixo 'DEMO-', para poderem ser removidos sem afetar
os cadastros reais:
    python -m app.demo remover
Carga / recarga:
    python -m app.demo carregar
    python -m app.demo recarregar
"""
import sys
from datetime import date, time

from sqlalchemy import select, text

from app.core.db import SessionLocal
from app.core.estrutura import garantir_estrutura_fixa
from app.models import (
    Ambiente, AmbienteArea, Area, Calendario, CalendarioExcecao, CenarioPlanejamento, CompetenciaInstrutor, Curso, DisponibilidadeInstrutor,
    HabilitacaoInstrutor, Instrutor, InstrutorArea, MatrizCurricular, Recurso, RecursoAmbiente, TipoAmbiente, Turma, TurmaUC, Turno, UCRecurso,
    UCTipoAmbiente, Unidade, UnidadeCurricular,
)

PREFIXO = "DEMO-"

# Remoção somente de registros DEMO- (inclui a unidade DEMO-U1 das versões antigas da demonstração).
REMOCAO = [
    "DELETE FROM cenarios_planejamento WHERE nome LIKE 'DEMO-%' OR unidade_id IN (SELECT id FROM unidades WHERE codigo = 'DEMO-U1')",
    "DELETE FROM turmas WHERE codigo LIKE 'DEMO-%'",
    "DELETE FROM competencias_instrutores WHERE instrutor_id IN (SELECT id FROM instrutores WHERE matricula LIKE 'DEMO-%')",
    "DELETE FROM instrutores WHERE matricula LIKE 'DEMO-%'",
    "DELETE FROM uc_tipos_ambiente WHERE uc_id IN (SELECT id FROM unidades_curriculares WHERE codigo LIKE 'DEMO-%')",
    "DELETE FROM uc_recursos WHERE uc_id IN (SELECT id FROM unidades_curriculares WHERE codigo LIKE 'DEMO-%')",
    "DELETE FROM unidades_curriculares WHERE codigo LIKE 'DEMO-%'",
    "DELETE FROM matrizes_curriculares WHERE curso_id IN (SELECT id FROM cursos WHERE codigo LIKE 'DEMO-%')",
    "DELETE FROM cursos WHERE codigo LIKE 'DEMO-%'",
    "DELETE FROM recursos_ambientes WHERE recurso_id IN (SELECT id FROM recursos WHERE codigo LIKE 'DEMO-%') "
    "OR ambiente_id IN (SELECT id FROM ambientes WHERE codigo LIKE 'DEMO-%')",
    "DELETE FROM recursos WHERE codigo LIKE 'DEMO-%'",
    "DELETE FROM ambientes WHERE codigo LIKE 'DEMO-%'",
    "DELETE FROM tipos_ambiente WHERE codigo LIKE 'DEMO-%'",
    "DELETE FROM calendario_excecoes WHERE calendario_id IN (SELECT id FROM calendarios WHERE nome LIKE 'DEMO-%')",
    "DELETE FROM calendarios WHERE nome LIKE 'DEMO-%'",
    "DELETE FROM periodos_horarios WHERE unidade_id IN (SELECT id FROM unidades WHERE codigo = 'DEMO-U1')",
    "DELETE FROM turnos WHERE unidade_id IN (SELECT id FROM unidades WHERE codigo = 'DEMO-U1')",
    "DELETE FROM unidades WHERE codigo = 'DEMO-U1'",
]


def carregar(db, ano: int = 2026):
    if db.scalar(select(Curso).where(Curso.codigo == f"{PREFIXO}ELT")):
        return "já carregado"
    garantir_estrutura_fixa(db)
    un = db.scalar(select(Unidade).where(Unidade.codigo == "BEIRA-MAR"))
    area = {a.codigo: a for a in db.scalars(select(Area).where(Area.unidade_id == un.id))}
    turno = {t.codigo: t for t in db.scalars(select(Turno).where(Turno.unidade_id == un.id))}
    energ, autom = area["ENERGIAS"], area["AUTOMACAO"]

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
    amb = {
        # salas de aula comuns atendem todas as áreas; laboratórios pertencem a uma área
        "S101": Ambiente(codigo=f"{PREFIXO}S101", nome="Sala 101", unidade_id=un.id, todas_areas=True, tipo_ambiente_id=tipos["SALA"].id,
                         capacidade_fisica=40, capacidade_operacional=36),
        "S102": Ambiente(codigo=f"{PREFIXO}S102", nome="Sala 102", unidade_id=un.id, todas_areas=True, tipo_ambiente_id=tipos["SALA"].id,
                         capacidade_fisica=40, capacidade_operacional=36),
        "LI1": Ambiente(codigo=f"{PREFIXO}LI1", nome="Lab. Informática 1", unidade_id=un.id, area_id=autom.id, tipo_ambiente_id=tipos["INFO"].id,
                        capacidade_fisica=32, capacidade_operacional=30),
        "LC1": Ambiente(codigo=f"{PREFIXO}LC1", nome="Lab. Comandos Elétricos", unidade_id=un.id, area_id=energ.id, tipo_ambiente_id=tipos["CMD"].id,
                        capacidade_fisica=32, capacidade_operacional=30, tempo_preparacao_min=10),
    }
    db.add_all(amb.values())
    db.flush()
    db.add(AmbienteArea(ambiente_id=amb["LI1"].id, area_id=energ.id))  # laboratório compartilhado por duas áreas
    bancada = Recurso(codigo=f"{PREFIXO}BAN", nome="Bancadas de comandos", tipo="bancada_comandos", unidade_id=un.id, quantidade_total=8)
    db.add(bancada)
    db.flush()
    db.add(RecursoAmbiente(recurso_id=bancada.id, ambiente_id=amb["LC1"].id, quantidade=8))

    # Carga horária em hora-aula; cada encontro ocupa o turno inteiro (4 aulas). UCs com carga que não é múltipla
    # de 4 terminam com um "fechamento" de 2 aulas, e o gerador junta dois fechamentos da turma no mesmo turno.
    cursos = [
        ("ELT", "Técnico em Eletrotécnica", energ, [("FEL", "Fundamentos de Eletricidade", 40, ["SALA"], 2),
                                                     ("DTE", "Desenho Técnico", 30, ["SALA", "INFO"], 1),
                                                     ("CMD", "Comandos Elétricos", 60, ["CMD"], 1),
                                                     ("INF", "Informática Aplicada", 18, ["INFO"], 1)]),
        ("AUT", "Técnico em Automação Industrial", autom, [("CLP", "Controladores Lógicos Programáveis", 48, ["INFO"], 2),
                                                            ("INS", "Instrumentação Industrial", 26, ["SALA"], 1),
                                                            ("RED", "Redes Industriais", 22, ["INFO"], 1),
                                                            # sem instrutor habilitado: fica sem horário e aparece como crítica no cronograma
                                                            ("SUP", "Sistemas Supervisórios", 40, ["INFO"], 1)]),
    ]
    por_cod, matrizes = {}, {}
    for cod_c, nome_c, ar, ucs in cursos:
        curso = Curso(codigo=f"{PREFIXO}{cod_c}", nome=nome_c, modalidade="presencial", tipo="técnico", carga_horaria_total=1200,
                      unidade_id=un.id, area_id=ar.id)
        db.add(curso)
        db.flush()
        mat = MatrizCurricular(curso_id=curso.id, versao="2026.1", situacao="vigente")
        db.add(mat)
        db.flush()
        matrizes[cod_c] = (curso, mat, [])
        for cod, nome, ch, tipos_uc, enc in ucs:
            uc = UnidadeCurricular(matriz_id=mat.id, codigo=f"{PREFIXO}{cod}", nome=nome, carga_horaria_total=ch, duracao_bloco_periodos=4,
                                   encontros_semanais=enc, certificacao_exigida="NR-10" if cod == "CMD" else None)
            db.add(uc)
            db.flush()
            for t in tipos_uc:
                db.add(UCTipoAmbiente(uc_id=uc.id, tipo_ambiente_id=tipos[t].id))
            por_cod[cod] = uc
            matrizes[cod_c][2].append(uc)
    db.add(UCRecurso(uc_id=por_cod["CMD"].id, recurso_tipo="bancada_comandos", quantidade=8))

    instrutores = [("DEMO-I01", "Ana (DEMO)", energ, ["FEL", "CMD"], "D"), ("DEMO-I02", "Bruno (DEMO)", energ, ["FEL", "DTE"], "D"),
                   ("DEMO-I03", "Carla (DEMO)", energ, ["INF", "DTE"], "D"), ("DEMO-I04", "Diego (DEMO)", energ, ["CMD"], "D"),
                   ("DEMO-I05", "Eduardo (DEMO)", autom, ["CLP", "RED"], "N"), ("DEMO-I06", "Fernanda (DEMO)", autom, ["INS", "RED", "CLP"], "N")]
    for mat_i, nome, ar, comps, periodo in instrutores:
        noite = periodo == "N"  # turno único (N) = 20 h, 4 h por dia; manhã e tarde (MV) = 40 h
        i = Instrutor(matricula=mat_i, nome=nome, unidade_id=un.id, area_id=ar.id, carga_horaria_contratual=20 if noite else 40,
                      limite_ch_letiva=20 if noite else 24, max_horas_dia=4 if noite else 8)
        db.add(i)
        db.flush()
        if mat_i == "DEMO-I06":
            db.add(InstrutorArea(instrutor_id=i.id, area_id=energ.id))  # atua em duas áreas
        for c in comps:
            db.add(CompetenciaInstrutor(instrutor_id=i.id, uc_id=por_cod[c].id, nivel="pleno"))
        if "CMD" in comps:
            db.add(HabilitacaoInstrutor(instrutor_id=i.id, nome="NR-10"))
        ini, fim = (time(7, 30), time(17, 30)) if periodo == "D" else (time(18, 0), time(22, 0))
        for d in range(5):
            db.add(DisponibilidadeInstrutor(instrutor_id=i.id, dia_semana=d, hora_inicio=ini, hora_fim=fim))

    for cod_t, nome_t, cod_c, t_cod in [("ELT-1", "Eletrotécnica 1", "ELT", "M"), ("ELT-2", "Eletrotécnica 2", "ELT", "T"),
                                         ("AUT-1", "Automação Industrial 1", "AUT", "N")]:
        curso, mat, ucs = matrizes[cod_c]
        t = Turma(codigo=f"{PREFIXO}{cod_t}", nome=f"{nome_t} (DEMO)", curso_id=curso.id, matriz_id=mat.id, unidade_id=un.id, area_id=curso.area_id,
                  calendario_id=cal.id, turno_id=turno[t_cod].id, qtd_alunos=30, data_inicio=date(ano, 8, 3), data_fim=date(ano, 12, 18), num_grupos=1)
        db.add(t)
        db.flush()
        for uc in ucs:
            # prazo apertado (folga de poucos dias) para o cronograma mostrar uma UC crítica
            limite = date(ano, 12, 4) if (cod_t, uc.codigo) == ("ELT-2", f"{PREFIXO}CMD") else None
            db.add(TurmaUC(turma_id=t.id, uc_id=uc.id, situacao="ofertada", data_limite=limite))
    db.add(CenarioPlanejamento(nome=f"{PREFIXO}Planejamento {ano}/2", unidade_id=un.id, periodo_inicio=date(ano, 8, 3), periodo_fim=date(ano, 12, 18)))
    db.commit()
    return "carregado"


def remover(db):
    for sql in REMOCAO:
        db.execute(text(sql))
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
