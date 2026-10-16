"""Semestre completo de demonstração (2026/2, Beira Mar e Porto) para apresentar a plataforma.

Monta cadastros (cursos, UCs, salas e laboratórios, instrutores e turmas das 11 áreas),
gera a grade com o próprio gerador de horários, publica o semestre, marca como realizadas as
aulas já passadas, registra uma substituição e observações de instrutores (com notificações).

Só é usado por scripts/gerar_semestre_demo_sql.py, num banco temporário, para produzir
backend/sql/demo_semestre_completo.sql. Nunca roda no banco real.
"""
from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import func, select, update

from app.services.regras_aula import teto_letivo

from app.models import (Alocacao, Ambiente, AmbienteArea, Area, Calendario, CalendarioExcecao, CenarioPlanejamento, CompetenciaInstrutor,
                        Curso, DisponibilidadeInstrutor, HabilitacaoInstrutor, Instrutor, InstrutorArea, MatrizCurricular, ObservacaoInstrutor,
                        TipoAmbiente, Turma, TurmaUC, Turno, UCTipoAmbiente, Unidade, UnidadeCurricular)

ANO = 2026
INICIO, FIM = date(ANO, 8, 3), date(ANO, 12, 18)
FERIADOS = [(date(ANO, 9, 7), "Independência do Brasil"), (date(ANO, 10, 12), "Nossa Senhora Aparecida"),
            (date(ANO, 11, 2), "Finados"), (date(ANO, 11, 20), "Dia da Consciência Negra")]
HOJE_DEMO = date(ANO, 10, 16)  # aulas antes desta data aparecem como realizadas

TIPOS = [  # código, nome, especializado
    ("SALA", "Sala de aula", False), ("INFO", "Laboratório de informática", True), ("CMD", "Laboratório de comandos elétricos", True),
    ("ELN", "Laboratório de eletrônica", True), ("CLP", "Laboratório de automação e CLP", True), ("HP", "Laboratório de hidráulica e pneumática", True),
    ("INS", "Laboratório de instrumentação", True), ("OMEC", "Oficina mecânica", True), ("OAUT", "Oficina automotiva", True),
    ("LLOG", "Laboratório de logística (armazém simulado)", True), ("CRI", "Estúdio de economia criativa", True),
]

# unidade, código, nome, tipo, áreas (lista ou "TODAS"), lugares, alunos recomendados, bloco
AMBIENTES = [
    ("BEIRA-MAR", "BM-S101", "Sala 101", "SALA", "TODAS", 40, 36, "Bloco A"),
    ("BEIRA-MAR", "BM-S102", "Sala 102", "SALA", "TODAS", 40, 36, "Bloco A"),
    ("BEIRA-MAR", "BM-S103", "Sala 103", "SALA", "TODAS", 40, 36, "Bloco A"),
    ("BEIRA-MAR", "BM-S104", "Sala 104", "SALA", "TODAS", 36, 32, "Bloco A"),
    ("BEIRA-MAR", "BM-LINF1", "Laboratório de Informática 1", "INFO", "TODAS", 32, 32, "Bloco B"),
    ("BEIRA-MAR", "BM-LCMD", "Laboratório de Comandos Elétricos", "CMD", ["ENERGIAS", "AUTOMACAO"], 32, 30, "Bloco C"),
    ("BEIRA-MAR", "BM-LELN", "Laboratório de Eletrônica", "ELN", ["ENERGIAS", "AUTOMACAO", "MECATRONICA", "INSTRUMENTACAO", "AUTOMOTIVA"], 32, 30, "Bloco C"),
    ("BEIRA-MAR", "BM-LCLP", "Laboratório de Automação e CLP", "CLP", ["AUTOMACAO", "MECATRONICA", "INSTRUMENTACAO"], 32, 30, "Bloco C"),
    ("BEIRA-MAR", "BM-LHP", "Laboratório de Hidráulica e Pneumática", "HP", ["MECANICA", "MECATRONICA", "AUTOMACAO"], 32, 30, "Bloco D"),
    ("BEIRA-MAR", "BM-LINS", "Laboratório de Instrumentação", "INS", ["INSTRUMENTACAO", "AUTOMACAO"], 32, 30, "Bloco C"),
    ("BEIRA-MAR", "BM-OMEC", "Oficina de Usinagem", "OMEC", ["MECANICA", "MECATRONICA"], 32, 28, "Galpão 1"),
    ("BEIRA-MAR", "BM-OAUT", "Oficina Automotiva", "OAUT", ["AUTOMOTIVA"], 32, 28, "Galpão 2"),
    ("PORTO", "PT-S201", "Sala 201", "SALA", "TODAS", 40, 36, "Bloco Porto"),
    ("PORTO", "PT-S202", "Sala 202", "SALA", "TODAS", 40, 36, "Bloco Porto"),
    ("PORTO", "PT-S203", "Sala 203", "SALA", "TODAS", 36, 32, "Bloco Porto"),
    ("PORTO", "PT-LINF1", "Laboratório de Informática 1", "INFO", "TODAS", 32, 32, "Bloco Porto"),
    ("PORTO", "PT-LINF2", "Laboratório de Informática 2", "INFO", "TODAS", 32, 32, "Bloco Porto"),
    ("PORTO", "PT-LLOG", "Armazém Simulado", "LLOG", ["LOGISTICA", "PORTOS"], 36, 32, "Galpão Porto"),
    ("PORTO", "PT-LCRI", "Estúdio Criativo", "CRI", ["ECONOMIA-CRIATIVA"], 28, 26, "Bloco Porto"),
]

# sigla, nome, área, tipo de curso, UCs: (código, nome, CH em hora-aula, dias por semana, tipos de sala aceitos, certificação)
CURSOS = [
    ("ELT", "Técnico em Eletrotécnica", "ENERGIAS", "técnico", [
        ("ELT-IEP", "Instalações Elétricas Prediais", 80, 2, ["CMD"], None),
        ("ELT-CMD", "Comandos Elétricos", 96, 2, ["CMD"], "NR-10"),
        ("ELT-ELA", "Eletrônica Analógica", 60, 1, ["ELN"], None)]),
    ("AUT", "Técnico em Automação Industrial", "AUTOMACAO", "aprendizagem industrial", [
        ("AUT-CLP", "Controladores Lógicos Programáveis", 96, 2, ["CLP"], None),
        ("AUT-INB", "Instrumentação Básica", 48, 1, ["INS"], None),
        ("AUT-RDI", "Redes Industriais", 48, 1, ["INFO"], None),
        ("AUT-PNE", "Pneumática", 40, 1, ["HP"], None)]),
    ("MEC", "Técnico em Mecânica", "MECANICA", "técnico", [
        ("MEC-USI", "Usinagem Convencional", 112, 2, ["OMEC"], None),
        ("MEC-DTM", "Desenho Técnico Mecânico", 60, 1, ["INFO", "SALA"], None),
        ("MEC-MET", "Metrologia", 48, 1, ["OMEC", "SALA"], None),
        ("MEC-HID", "Hidráulica Industrial", 40, 1, ["HP"], None)]),
    ("MAU", "Mecânico de Automóveis", "AUTOMOTIVA", "aprendizagem industrial", [
        ("MAU-MCI", "Motores de Combustão Interna", 112, 2, ["OAUT"], None),
        ("MAU-SDF", "Suspensão, Direção e Freios", 96, 2, ["OAUT"], None),
        ("MAU-ELA", "Eletricidade Automotiva", 48, 1, ["OAUT", "ELN"], None)]),
    ("MCT", "Técnico em Mecatrônica", "MECATRONICA", "técnico", [
        ("MCT-ROB", "Robótica Industrial", 80, 2, ["CLP"], None),
        ("MCT-EPN", "Eletropneumática", 56, 1, ["HP"], None),
        ("MCT-MIC", "Microcontroladores", 60, 1, ["ELN"], None),
        ("MCT-CAD", "Modelagem 3D (CAD)", 48, 1, ["INFO"], None)]),
    ("INS", "Técnico em Instrumentação", "INSTRUMENTACAO", "técnico", [
        ("INS-MCV", "Medição e Controle de Variáveis", 96, 2, ["INS"], None),
        ("INS-MCT", "Malhas de Controle", 64, 2, ["INS", "CLP"], None),
        ("INS-CAL", "Calibração de Instrumentos", 48, 1, ["INS"], None)]),
    ("LOG", "Técnico em Logística", "LOGISTICA", "técnico", [
        ("LOG-GAR", "Gestão de Armazenagem", 80, 1, ["LLOG", "SALA"], None),  # 4 encontros na semana: cabe na turma 80-20 (sexta EAD)
        ("LOG-TRD", "Transportes e Distribuição", 56, 1, ["SALA"], None),
        ("LOG-WMS", "Sistemas de Gestão Logística (WMS)", 48, 1, ["INFO"], None),
        ("LOG-CUS", "Custos Logísticos", 40, 1, ["SALA"], None)]),
    ("POR", "Técnico em Portos", "PORTOS", "técnico", [
        ("POR-OPP", "Operações Portuárias", 96, 2, ["SALA", "LLOG"], None),
        ("POR-LPA", "Legislação Portuária e Aduaneira", 48, 1, ["SALA"], None),
        ("POR-SEG", "Segurança do Trabalho Portuário (NR-29)", 40, 1, ["SALA"], "NR-29"),
        ("POR-GCT", "Gestão de Contêineres", 40, 1, ["LLOG"], None)]),
    ("DDS", "Técnico em Desenvolvimento de Sistemas", "DDS-TI", "técnico", [
        ("DDS-LOP", "Lógica de Programação", 96, 1, ["INFO"], None),  # 4 encontros na semana: cabe na turma 80-20 (sexta EAD)
        ("DDS-BDD", "Banco de Dados", 60, 1, ["INFO"], None),
        ("DDS-WEB", "Desenvolvimento Web", 60, 1, ["INFO"], None),
        ("DDS-ANS", "Análise de Sistemas", 40, 1, ["SALA"], None)]),
    ("DGR", "Design Gráfico", "ECONOMIA-CRIATIVA", "qualificação", [
        ("DGR-TIM", "Tratamento de Imagens", 64, 2, ["CRI"], None),
        ("DGR-ILD", "Ilustração Digital", 48, 1, ["CRI"], None),
        ("DGR-IDV", "Identidade Visual", 64, 2, ["CRI"], None)]),
    # cursos do Wagner Prado (único habilitado): carga já é a do semestre (sem ajuste)
    ("ELI", "Eletricista Instalador", "ENERGIAS", "qualificação", [
        ("ELI-NR10", "Segurança em Instalações Elétricas (NR-10)", 204, 3, ["SALA"], "NR-10"),
        ("ELI-INS", "Instalações Elétricas Básicas", 136, 2, ["SALA"], None)]),
    ("MNT", "Manutenção Elétrica Industrial (empresa)", "ENERGIAS", "qualificação", [
        ("MNT-NR10", "NR-10 Aplicada à Manutenção", 136, 2, ["SALA"], "NR-10"),
        ("MNT-MPE", "Manutenção Preventiva Elétrica", 136, 2, ["SALA"], None)]),
    ("NRB", "NR-10 Básico", "ENERGIAS", "qualificação", [
        ("NRB-SEP", "Segurança em Eletricidade – NR-10 Básico", 40, 2, ["SALA"], "NR-10")]),
    ("ADM", "Assistente Administrativo", "GESTAO", "qualificação", [
        ("ADM-ROT", "Rotinas Administrativas", 48, 1, ["SALA"], None),
        ("ADM-PLA", "Planilhas Eletrônicas", 48, 1, ["INFO"], None),
        ("ADM-ATC", "Atendimento ao Cliente", 32, 1, ["SALA"], None)]),
]

# código, curso, nome, turno, alunos, dias (None = seg a sex), prazos especiais {UC: data-limite}
TURMAS = [
    ("HTC-ELT-12", "ELT", "Eletrotécnica 12 – Habilitação técnica", "M", 30, None, {}),
    ("HTC-ELT-13", "ELT", "Eletrotécnica 13 – Habilitação técnica", "N", 28, None, {"ELT-CMD": date(ANO, 12, 4)}),
    ("AIT-AUT-05", "AUT", "Automação Industrial 05 – Aprendizagem industrial técnica", "T", 24, None, {}),
    ("HTC-MEC-08", "MEC", "Mecânica 08 – Habilitação técnica", "N", 26, None, {}),
    ("AIB-MAU-03", "MAU", "Mecânico de Automóveis 03 – Aprendizagem industrial básica", "M", 24, None, {}),
    ("HTC-MCT-04", "MCT", "Mecatrônica 04 – Habilitação técnica", "T", 26, None, {}),
    ("HTC-INS-02", "INS", "Instrumentação 02 – Habilitação técnica", "N", 22, None, {}),
    ("HTC-LOG-21", "LOG", "Logística 21 – Habilitação técnica", "N", 32, None, {}),
    ("AIT-LOG-07", "LOG", "Logística 07 – Aprendizagem industrial técnica", "M", 28, None, {}),
    ("HTC-POR-03", "POR", "Portos 03 – Habilitação técnica", "N", 30, None, {"POR-GCT": date(ANO, 11, 13)}),
    ("HTC-DDS-09", "DDS", "Desenvolvimento de Sistemas 09 – Habilitação técnica", "T", 30, None, {}),
    ("QUA-DGR-01", "DGR", "Design Gráfico 01 – Qualificação profissional", "N", 24, None, {}),
    ("EMP-ADM-02", "ADM", "Assistente Administrativo 02 – Turma para empresa", "T", 20, [0, 2, 4], {}),
    # Wagner Prado: 5 manhãs + 4 tardes = 9 de 10 turnos (teto de 90%)
    ("QUA-ELI-01", "ELI", "Eletricista Instalador 01 – Qualificação", "M", 24, None, {}),
    ("EMP-MNT-01", "MNT", "Manutenção Elétrica 01 – Turma para empresa", "T", 18, [0, 1, 2, 3], {}),
]
CH_SEM_AJUSTE = {"ELI", "MNT", "NRB"}  # carga já calculada para ocupar o semestre

# matrícula, nome, unidade, área principal, outras áreas, turnos de trabalho (M/V/N; 40 h = MV ou VN), UCs (pleno), certificações, formação
INSTRUTORES = [
    ("BM-1001", "Marcos Vieira", "BEIRA-MAR", "ENERGIAS", [], "MV", ["ELT-IEP", "ELT-CMD"], ["NR-10"], "Eng. eletricista; 12 anos em manutenção industrial"),
    ("BM-1002", "Juliana Prates", "BEIRA-MAR", "ENERGIAS", ["AUTOMACAO"], "VN", ["ELT-CMD", "ELT-ELA", "ELT-IEP"], ["NR-10"], "Tecnóloga em automação; comandos e acionamentos"),
    ("BM-1003", "Ricardo Nunes", "BEIRA-MAR", "ENERGIAS", [], "N", ["ELT-IEP", "ELT-CMD"], ["NR-10", "NR-35"], "Técnico em eletrotécnica; instalações prediais e industriais"),
    ("BM-1004", "Patrícia Lemos", "BEIRA-MAR", "ENERGIAS", ["MECATRONICA", "INSTRUMENTACAO"], "MV", ["ELT-ELA", "MCT-MIC"], [], "Eng. eletrônica; sistemas embarcados"),
    ("BM-1005", "Fábio Teixeira", "BEIRA-MAR", "AUTOMACAO", ["MECATRONICA"], "VN", ["AUT-CLP", "MCT-ROB", "INS-MCT"], ["NR-10"], "Eng. de controle e automação; CLP Siemens e Rockwell"),
    ("BM-1006", "Larissa Campos", "BEIRA-MAR", "AUTOMACAO", [], "MV", ["AUT-RDI", "AUT-CLP"], [], "Tecnóloga em redes industriais (Profinet, Modbus)"),
    ("BM-1007", "Henrique Duarte", "BEIRA-MAR", "AUTOMACAO", ["INSTRUMENTACAO"], "VN", ["AUT-INB", "INS-MCV", "INS-CAL"], [], "Técnico em instrumentação; 15 anos em refinaria"),
    ("BM-1008", "Sérgio Andrade", "BEIRA-MAR", "MECANICA", [], "VN", ["MEC-USI", "MEC-MET"], [], "Técnico em mecânica; ferramentaria"),
    ("BM-1009", "Camila Rocha", "BEIRA-MAR", "MECANICA", ["MECATRONICA", "AUTOMACAO"], "VN", ["MEC-DTM", "MCT-CAD", "MEC-HID", "AUT-PNE"], [], "Eng. mecânica; projetos em CAD/CAE"),
    ("BM-1010", "Paulo Mendes", "BEIRA-MAR", "MECANICA", [], "N", ["MEC-USI", "MEC-MET", "MEC-HID"], [], "Técnico em mecânica; usinagem CNC"),
    ("BM-1011", "Rogério Lima", "BEIRA-MAR", "AUTOMOTIVA", [], "MV", ["MAU-MCI", "MAU-SDF"], [], "Mecânico automotivo; 20 anos em concessionária"),
    ("BM-1012", "Tiago Barbosa", "BEIRA-MAR", "AUTOMOTIVA", [], "M", ["MAU-MCI", "MAU-SDF", "MAU-ELA"], [], "Técnico em manutenção automotiva; injeção eletrônica"),
    ("BM-1013", "Elaine Souza", "BEIRA-MAR", "AUTOMOTIVA", ["ENERGIAS"], "MV", ["MAU-ELA", "MAU-SDF"], ["NR-10"], "Tecnóloga em eletrônica automotiva"),
    ("BM-1014", "Gustavo Pires", "BEIRA-MAR", "MECATRONICA", ["AUTOMACAO"], "V", ["MCT-ROB", "MCT-EPN", "AUT-PNE"], [], "Eng. mecatrônico; robótica colaborativa"),
    ("BM-1015", "Renata Alves", "BEIRA-MAR", "MECATRONICA", ["ENERGIAS"], "VN", ["MCT-MIC", "MCT-EPN", "MCT-CAD"], [], "Tecnóloga em mecatrônica; Arduino e ESP32"),
    ("BM-1016", "Leandro Costa", "BEIRA-MAR", "INSTRUMENTACAO", [], "N", ["INS-MCV", "INS-MCT", "INS-CAL"], [], "Técnico em instrumentação; calibração RBC"),
    ("BM-1017", "Vanessa Martins", "BEIRA-MAR", "INSTRUMENTACAO", ["AUTOMACAO"], "VN", ["INS-CAL", "AUT-INB", "INS-MCT"], [], "Eng. química; controle de processos"),
    ("PT-2001", "Aline Ferreira", "PORTO", "LOGISTICA", [], "MV", ["LOG-GAR", "LOG-TRD", "LOG-CUS"], [], "Administradora; gestão de centros de distribuição"),
    ("PT-2002", "Bruno Cardoso", "PORTO", "LOGISTICA", ["PORTOS"], "VN", ["LOG-WMS", "LOG-GAR", "POR-GCT"], [], "Tecnólogo em logística; WMS e TMS"),
    ("PT-2003", "Débora Ramos", "PORTO", "LOGISTICA", ["GESTAO"], "MV", ["LOG-TRD", "LOG-CUS", "ADM-ATC", "LOG-WMS"], [], "Economista; custos e transportes"),
    ("PT-2004", "Eduardo Salles", "PORTO", "PORTOS", [], "N", ["POR-OPP", "POR-GCT", "POR-SEG"], ["NR-29", "NR-35"], "Oficial de náutica; operações em terminal de contêineres"),
    ("PT-2005", "Flávia Moura", "PORTO", "PORTOS", ["LOGISTICA"], "N", ["POR-LPA", "POR-SEG", "POR-OPP", "LOG-TRD"], ["NR-29"], "Advogada; comércio exterior e aduana"),
    ("PT-2006", "Igor Batista", "PORTO", "DDS-TI", [], "V", ["DDS-LOP", "DDS-BDD"], [], "Desenvolvedor back-end; Python e PostgreSQL"),
    ("PT-2007", "Natália Freitas", "PORTO", "DDS-TI", ["GESTAO"], "VN", ["DDS-WEB", "DDS-LOP", "ADM-PLA"], [], "Desenvolvedora front-end; React"),
    ("PT-2008", "Otávio Ribeiro", "PORTO", "DDS-TI", [], "V", ["DDS-BDD", "DDS-ANS", "DDS-WEB"], [], "Analista de sistemas; UML e metodologias ágeis"),
    ("PT-2009", "Priscila Gomes", "PORTO", "ECONOMIA-CRIATIVA", [], "N", ["DGR-TIM", "DGR-IDV"], [], "Designer gráfica; branding"),
    ("PT-2010", "Rafael Torres", "PORTO", "ECONOMIA-CRIATIVA", [], "VN", ["DGR-ILD", "DGR-TIM", "DGR-IDV"], [], "Ilustrador; animação 2D"),
    ("PT-2011", "Sabrina Lopes", "PORTO", "GESTAO", [], "V", ["ADM-ROT", "ADM-ATC", "ADM-PLA"], [], "Administradora; rotinas de RH e financeiro"),
    ("PT-2012", "Thiago Moreira", "PORTO", "GESTAO", ["LOGISTICA"], "VN", ["ADM-ROT", "LOG-CUS"], [], "Contador; custos e orçamento"),
    ("BM-1018", "Wagner Prado", "BEIRA-MAR", "ENERGIAS", [], "MV", ["ELI-NR10", "ELI-INS", "MNT-NR10", "MNT-MPE", "NRB-SEP"], ["NR-10"],
     "Eletrotécnico; instrutor de NR-10 e manutenção elétrica"),
]
LIMITE_NO_TETO = {"BM-1018"}  # aulas até o teto de 90% (36 h); os demais de 40 h ficam com 28 h

# horistas e mensalistas em todos os turnos (a modalidade não depende do turno nem da carga)
HORISTAS = {"BM-1003", "BM-1006", "BM-1012", "BM-1015", "PT-2003", "PT-2005", "PT-2006", "PT-2010"}

# nível: básicos só dão aula em AIB e qualificações (inclui turmas para empresa de cursos de qualificação); os demais são técnicos
BASICOS = {"BM-1011", "BM-1012", "BM-1018", "PT-2011"}
# turmas 80-20: a sexta é de atividades a distância (EAD), sem aula presencial
EAD_SEXTA = {"HTC-LOG-21", "HTC-DDS-09"}

# logins do portal do instrutor na demonstração (senha comum, só para apresentação)
LOGINS_PORTAL = {"BM-1002": "juliana.prates", "BM-1001": "marcos.vieira", "PT-2006": "igor.batista", "PT-2004": "eduardo.salles"}
SENHA_PORTAL = "portal@2026"


def carga_no_semestre(ch: int, enc: int) -> int:
    """Carga que ocupa o semestre até dezembro (com folga): ~14 semanas de encontros, em múltiplos de 4 aulas."""
    if enc >= 2:
        return 112 if ch < 96 else 120
    return 56 if ch <= 48 else 60


def montar(db, ctx, limite_s: float = 120) -> dict:
    """Cria o semestre, gera e publica a grade. Retorna um resumo."""
    from app.services import cenarios, otimizacao, substituicao
    unid = {u.codigo: u for u in db.scalars(select(Unidade))}
    area = {a.codigo: a for a in db.scalars(select(Area))}
    turno = {(t.unidade_id, t.codigo): t for t in db.scalars(select(Turno))}

    cal = {}
    for cod, u in unid.items():
        c = Calendario(unidade_id=u.id, nome=f"Calendário {ANO}/2 – {u.nome}", data_inicio=INICIO, data_fim=FIM)
        db.add(c)
        db.flush()
        for d, desc in FERIADOS:
            db.add(CalendarioExcecao(calendario_id=c.id, data=d, tipo="feriado", descricao=desc))
        cal[cod] = c
    tipos = {}
    for cod, nome, esp in TIPOS:
        tipos[cod] = TipoAmbiente(codigo=cod, nome=nome, especializado=esp)
        db.add(tipos[cod])
    db.flush()
    for un, cod, nome, tp, areas, lug, rec, bloco in AMBIENTES:
        todas = areas == "TODAS"
        a = Ambiente(codigo=cod, nome=nome, unidade_id=unid[un].id, tipo_ambiente_id=tipos[tp].id, todas_areas=todas,
                     area_id=None if todas else area[areas[0]].id, capacidade_fisica=lug, capacidade_operacional=rec, predio=bloco,
                     acessivel=True, tempo_preparacao_min=0 if tp in ("SALA", "INFO") else 10)
        db.add(a)
        db.flush()
        for extra in ([] if todas else areas[1:]):
            db.add(AmbienteArea(ambiente_id=a.id, area_id=area[extra].id))

    ucs, cursos = {}, {}
    for sigla, nome, ar, tipo, lista in CURSOS:
        u_cod = area[ar].unidade_id
        ajuste = (lambda ch, enc: ch) if sigla in CH_SEM_AJUSTE else carga_no_semestre
        c = Curso(codigo=sigla, nome=nome, area_id=area[ar].id, unidade_id=u_cod, modalidade="presencial", tipo=tipo,
                  carga_horaria_total=sum(ajuste(x[2], x[3]) for x in lista) * (4 if tipo == "técnico" else 1))
        db.add(c)
        db.flush()
        m = MatrizCurricular(curso_id=c.id, versao=f"{ANO}.1", situacao="vigente", vigencia_inicio=date(ANO, 1, 1))
        db.add(m)
        db.flush()
        cursos[sigla] = (c, m)
        for seq, (cod, nome_uc, ch, enc, tps, cert) in enumerate(lista, start=1):
            ch = ajuste(ch, enc)
            uc = UnidadeCurricular(matriz_id=m.id, codigo=cod, nome=nome_uc, carga_horaria_total=ch, encontros_semanais=enc,
                                   duracao_bloco_periodos=4, sequencia=seq, certificacao_exigida=cert, modulo="Módulo específico")
            db.add(uc)
            db.flush()
            for t in tps:
                db.add(UCTipoAmbiente(uc_id=uc.id, tipo_ambiente_id=tipos[t].id))
            ucs[cod] = uc

    instrutores = {}
    for mat, nome, un, ar, outras, turnos_i, comps, certs, formacao in INSTRUTORES:
        u = unid[un]
        dois = len(turnos_i) == 2  # MV ou VN = 40 h (8 h por dia); um turno = 20 h (4 h por dia)
        i = Instrutor(matricula=mat, nome=nome, email=f"{LOGINS_PORTAL.get(mat, mat.lower())}@demo.senai.br", unidade_id=u.id,
                      area_id=area[ar].id, carga_horaria_contratual=40 if dois else 20,
                      limite_ch_letiva=teto_letivo(40) if mat in LIMITE_NO_TETO else 28 if dois else teto_letivo(20),
                      max_horas_dia=8 if dois else 4, areas_competencia=formacao, situacao="ativo", ativo=True,
                      modalidade="horista" if mat in HORISTAS else "mensalista", nivel="basico" if mat in BASICOS else "tecnico")
        db.add(i)
        db.flush()
        instrutores[mat] = i
        for o in outras:
            db.add(InstrutorArea(instrutor_id=i.id, area_id=area[o].id))
        for cuc in comps:
            db.add(CompetenciaInstrutor(instrutor_id=i.id, uc_id=ucs[cuc].id, nivel="pleno", ativo=True))
        for cert in certs:
            db.add(HabilitacaoInstrutor(instrutor_id=i.id, nome=cert, ativo=True))
        from app.services.regras_aula import JORNADAS
        for tc in JORNADAS[turnos_i]:
            t = turno[(u.id, tc)]
            for d in range(5):
                db.add(DisponibilidadeInstrutor(instrutor_id=i.id, dia_semana=d, hora_inicio=t.hora_inicio, hora_fim=t.hora_fim))

    for cod, sigla, nome, tc, alunos, dias, prazos in TURMAS:
        c, m = cursos[sigla]
        u_id = area[[x for x in CURSOS if x[0] == sigla][0][2]].unidade_id
        un_cod = next(k for k, v in unid.items() if v.id == u_id)
        t = Turma(codigo=cod, nome=nome, curso_id=c.id, matriz_id=m.id, unidade_id=u_id, area_id=c.area_id, calendario_id=cal[un_cod].id,
                  turno_id=turno[(u_id, tc)].id, qtd_alunos=alunos, data_inicio=INICIO, data_fim=FIM,
                  dias_possiveis=[0, 1, 2, 3] if cod in EAD_SEXTA else (dias or [0, 1, 2, 3, 4]), dias_ead=[4] if cod in EAD_SEXTA else [],
                  num_grupos=1, situacao="em_andamento")
        db.add(t)
        db.flush()
        for uc in db.scalars(select(UnidadeCurricular).where(UnidadeCurricular.matriz_id == m.id)):
            db.add(TurmaUC(turma_id=t.id, uc_id=uc.id, situacao="ofertada", data_limite=prazos.get(uc.codigo)))
    db.flush()

    cen = cenarios.criar(db, ctx, f"Planejamento {ANO}/2", periodo_inicio=INICIO, periodo_fim=FIM,
                         descricao="Semestre de demonstração: Beira Mar e Porto, 13 turmas nos três turnos.")
    db.commit()
    ex = otimizacao.criar_execucao(db, ctx, cen.id, {"tipo": "instituicao"}, limite_tempo_s=limite_s)
    db.commit()
    otimizacao.executar(ex.id, ctx)
    db.expire_all()

    # publicação pelo fluxo normal (validação → aprovação → publicação); avisa os instrutores
    for estado in ("em_validacao", "aguardando_aprovacao", "aprovado", "publicado"):
        cenarios.transicionar(db, ctx, cen.id, estado, motivo="Demonstração")
        db.commit()

    # aulas já passadas aparecem como realizadas
    db.execute(update(Alocacao).where(Alocacao.cenario_id == cen.id, Alocacao.data < HOJE_DEMO).values(status="realizada"))
    db.commit()

    # uma substituição (falta por atestado) numa aula futura da Juliana
    juliana = instrutores["BM-1002"]
    alvo = db.scalars(select(Alocacao).where(Alocacao.cenario_id == cen.id, Alocacao.instrutor_id == juliana.id,
                                             Alocacao.data >= date(ANO, 10, 20)).order_by(Alocacao.inicio)).first()
    sub_info = None
    substituicao.hoje = lambda: HOJE_DEMO  # antecedência contada a partir do "hoje" da demonstração
    if alvo:
        cand = substituicao.candidatos(db, cen.id, [alvo])
        livres = [c for c in cand["instrutores"] if c["grupo"] in ("recomendado", "excecao")]
        if livres:
            r = substituicao.substituir(db, ctx, cen.id, [alvo], livres[0]["id"], "Atestado médico da titular (1 dia)")
            db.commit()
            sub_info = {"data": alvo.data.isoformat(), "substituto": livres[0]["nome"], "substituidas": r["substituidas"]}

    # mensalistas: turnos da jornada sem aula viram planejamento (PL) ou projeto (PJ), toda semana; horistas ficam com dispensa
    from datetime import timedelta
    from app.models import Notificacao
    from app.services import agenda_instrutor
    ref = date(ANO, 10, 19)
    for k, (mat, i) in enumerate(sorted(instrutores.items())):
        if i.modalidade != "mensalista":
            continue
        ag = agenda_instrutor.semana(db, cen.id, i.id, ref)
        vazios = [c for c in ag["celulas"] if c["estado"] == "vazio"]
        for n, c in enumerate(vazios[:2]):  # dois turnos por semana; o resto aparece como "sem atribuição"
            primeiro = INICIO + timedelta(days=(c["dia"] - INICIO.weekday()) % 7)
            sigla = "PJ" if n == 0 and k % 3 == 0 else "PL"
            agenda_instrutor.marcar(db, ctx, cen.id, i.id, primeiro, c["turno_id"], sigla, FIM,
                                    "Projeto: laboratório aberto / apoio a TCC" if sigla == "PJ" else None)
    # só os instrutores com login no portal ficam com o aviso da agenda (os demais não teriam onde ler)
    sem_login = [instrutores[m].id for m in instrutores if m not in LOGINS_PORTAL]
    db.execute(Notificacao.__table__.delete().where(Notificacao.instrutor_id.in_(sem_login), Notificacao.titulo.like("Agenda atualizada%")))
    db.commit()

    substituicao.hoje = date.today
    # observações enviadas pelos instrutores no portal (uma nova, uma já respondida)
    def obs(mat, turma_cod, uc_cod, tipo, texto, resposta=None):
        tuc = db.scalars(select(TurmaUC).join(Turma).join(UnidadeCurricular, UnidadeCurricular.id == TurmaUC.uc_id)
                         .where(Turma.codigo == turma_cod, UnidadeCurricular.codigo == uc_cod)).first()
        o = ObservacaoInstrutor(instrutor_id=instrutores[mat].id, turma_uc_id=tuc.id if tuc else None, tipo=tipo, texto=texto,
                                status="resolvida" if resposta else "nova", resposta=resposta,
                                respondido_por_id=ctx.id if resposta else None, respondido_em=datetime(ANO, 10, 9, 10, 30) if resposta else None)
        db.add(o)
    obs("BM-1001", "HTC-ELT-12", "ELT-CMD", "recurso", "As bancadas 3 e 7 do Laboratório de Comandos estão com contatores danificados. "
        "Peço a troca antes das aulas práticas de partida estrela-triângulo.")
    obs("PT-2006", "HTC-DDS-09", "DDS-LOP", "sugestao", "Sugiro reservar o Laboratório de Informática 2 nas avaliações práticas: o 1 tem 4 máquinas lentas.",
        "Combinado: as avaliações de Lógica de Programação ficam no Laboratório 2 a partir de 20/10.")
    obs("PT-2004", "HTC-POR-03", "POR-GCT", "horario", "A UC de Gestão de Contêineres tem prazo em 13/11. Se possível, incluir mais um encontro semanal.")
    db.commit()

    casos = pendencias(db, ctx, cen, instrutores, unid, area, turno, cursos, cal)

    n_aulas = db.scalar(select(func.count()).select_from(Alocacao).where(Alocacao.cenario_id == cen.id))
    return {"cenario_id": cen.id, "aulas": n_aulas, "execucao": ex.id, "substituicao": sub_info, **casos}


def pendencias(db, ctx, cen, instrutores, unid, area, turno, cursos, cal) -> dict:
    """Situações para testar conflitos e ações (depois da publicação, como acontece no dia a dia).

    No cadastro (valem para o semestre publicado e para a proposta):
    - licença médica de um instrutor com aulas marcadas → conflito, resolver por substituição;
    - laboratório em manutenção numa semana com aulas → conflito, trocar a sala;
    - ponto facultativo no Porto num dia com aulas → dia não letivo, remarcar;
    - turma nova (HTC-ELT-14, início em 19/10) sem nenhuma aula → gerar horários só dela;
    - turma QUA-NRB-01 (início em 03/11) sem instrutor possível: o único habilitado (Wagner Prado) já dá aula
      em 9 de 10 turnos, o teto de 90% → a geração aponta a falta de instrutor (contratar/habilitar alguém).
    Numa proposta de alteração do semestre publicado (em edição):
    - aulas sem instrutor (instrutor remanejado para projeto) → alocar instrutor;
    - aulas sem sala (turma vai mudar de sala) → alocar sala.
    """
    from app.services import cenarios
    from app.models import Bloqueio
    amb = {a.codigo: a for a in db.scalars(select(Ambiente))}
    fabio = instrutores["BM-1005"]
    db.add(Bloqueio(alvo_tipo="instrutor", alvo_id=fabio.id, inicio=datetime(ANO, 10, 26, 0, 0), fim=datetime(ANO, 11, 6, 23, 59),
                    tipo="afastamento", motivo="Licença médica (atestado de 12 dias)", ativo=True))
    db.add(Bloqueio(alvo_tipo="ambiente", alvo_id=amb["BM-LCLP"].id, inicio=datetime(ANO, 11, 3, 0, 0), fim=datetime(ANO, 11, 6, 23, 59),
                    tipo="manutencao", motivo="Troca do quadro de alimentação das bancadas", ativo=True))
    db.add(CalendarioExcecao(calendario_id=cal["PORTO"].id, data=date(ANO, 10, 28), tipo="feriado",
                             descricao="Ponto facultativo – Dia do Servidor Público"))
    c, m = cursos["ELT"]
    u_id = c.unidade_id
    t = Turma(codigo="HTC-ELT-14", nome="Eletrotécnica 14 – Habilitação técnica (início em 19/10, 1ª UC neste semestre)", curso_id=c.id, matriz_id=m.id,
              unidade_id=u_id, area_id=c.area_id, calendario_id=cal["BEIRA-MAR"].id, turno_id=turno[(u_id, "T")].id, qtd_alunos=26,
              data_inicio=date(ANO, 10, 19), data_fim=FIM, dias_possiveis=[0, 1, 2, 3, 4], num_grupos=1, situacao="planejada")
    db.add(t)
    db.flush()
    # começa no meio do semestre: só a primeira UC agora; as demais entram em {ANO + 1}/1
    ela = db.scalar(select(UnidadeCurricular).where(UnidadeCurricular.matriz_id == m.id, UnidadeCurricular.codigo == "ELT-ELA"))
    db.add(TurmaUC(turma_id=t.id, uc_id=ela.id, situacao="ofertada"))
    # turma que vai começar sem instrutor possível: só o Wagner é habilitado em NR-10 e já está no teto de 90%
    c2, m2 = cursos["NRB"]
    nrb = Turma(codigo="QUA-NRB-01", nome="NR-10 Básico 01 – Qualificação (início em 03/11)", curso_id=c2.id, matriz_id=m2.id,
                unidade_id=c2.unidade_id, area_id=c2.area_id, calendario_id=cal["BEIRA-MAR"].id, turno_id=turno[(c2.unidade_id, "T")].id,
                qtd_alunos=20, data_inicio=date(ANO, 11, 3), data_fim=FIM, dias_possiveis=[0, 1, 2, 3, 4], num_grupos=1, situacao="planejada")
    db.add(nrb)
    db.flush()
    for uc in db.scalars(select(UnidadeCurricular).where(UnidadeCurricular.matriz_id == m2.id)):
        db.add(TurmaUC(turma_id=nrb.id, uc_id=uc.id, situacao="ofertada"))
    db.commit()

    prop = cenarios.proposta_alteracao(db, ctx, cen.id, f"Ajustes de novembro {ANO}/2",
                                       "Proposta de alteração do semestre publicado.")
    db.flush()
    # aulas sem instrutor: o instrutor de uma UC da HTC-INS-02 vai para um projeto a partir de 03/11
    ins = db.scalar(select(Turma).where(Turma.codigo == "HTC-INS-02"))
    alvo = db.scalars(select(Alocacao).where(Alocacao.cenario_id == prop.id, Alocacao.turma_id == ins.id, Alocacao.instrutor_id.isnot(None),
                                             Alocacao.data >= date(ANO, 11, 3)).order_by(Alocacao.data)).first()
    sem_instrutor = 0
    if alvo:
        nome = db.get(Instrutor, alvo.instrutor_id).nome
        sem_instrutor = db.execute(update(Alocacao).where(Alocacao.cenario_id == prop.id, Alocacao.turma_uc_id == alvo.turma_uc_id,
                                                          Alocacao.instrutor_id == alvo.instrutor_id, Alocacao.data >= date(ANO, 11, 3))
                                   .values(instrutor_id=None, fixa=False,
                                           observacao="Instrutor remanejado para projeto: definir substituto")).rowcount
        prop.descricao = (f"Proposta de alteração: {nome} remanejado(a) para projeto a partir de 03/11 (HTC-INS-02 sem instrutor) "
                          "e Design Gráfico 01 mudando de sala a partir de 09/11.")
    dgr = db.scalar(select(Turma).where(Turma.codigo == "QUA-DGR-01"))
    sem_sala = db.execute(update(Alocacao).where(Alocacao.cenario_id == prop.id, Alocacao.turma_id == dgr.id, Alocacao.data >= date(ANO, 11, 9))
                          .values(ambiente_id=None, observacao="Turma muda de sala: definir o novo ambiente")).rowcount
    db.commit()
    for cid in (cen.id, prop.id):  # o painel de validação já abre com as ocorrências
        cenarios.validar(db, ctx, cid)
        db.commit()
    return {"proposta_id": prop.id, "aulas_sem_instrutor": sem_instrutor, "aulas_sem_sala": sem_sala}
