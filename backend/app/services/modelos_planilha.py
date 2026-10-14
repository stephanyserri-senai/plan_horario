"""Modelos de planilha para importação (gerados com as listas atuais do banco).

Cada modelo tem: aba "Preencher" (cabeçalhos reconhecidos automaticamente pela
importação, linhas EXEMPLO que a importação ignora, listas de seleção), aba
"Instruções" (o que vai em cada coluna) e aba "Listas" (unidades, áreas, turnos,
tipos de sala).
"""
from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Area, TipoAmbiente, Unidade

FONTE = "Arial"
AZUL = PatternFill("solid", fgColor="1F4E79")
AMARELO = PatternFill("solid", fgColor="FFF2CC")
CINZA = PatternFill("solid", fgColor="EDEDED")
BORDA = Border(*(Side(style="thin", color="BFBFBF"),) * 4)

TIPOS_SALA_PADRAO = ["Sala de aula", "Laboratório de informática", "Laboratório de automação", "Laboratório de elétrica",
                     "Laboratório de comandos elétricos", "Oficina mecânica", "Oficina automotiva", "Laboratório de instrumentação"]

# coluna: (cabeçalho, obrigatório, explicação, lista de seleção ou None, largura, exemplos...)
MODELOS: dict[str, dict] = {
    "estrutura_curricular": {
        "titulo": "Cursos, matrizes e unidades curriculares",
        "resumo": "Uma linha por unidade curricular (UC). Repita os dados do curso em todas as linhas das UCs dele: o curso e a matriz são criados "
                  "ou atualizados automaticamente e as UCs ficam ligadas a eles.",
        "colunas": [
            ("Código do curso", True, "Código único do curso (ex.: ELT-TEC).", None, 16, "EXEMPLO-ELT", "EXEMPLO-ELT"),
            ("Nome do curso", True, "Nome completo do curso.", None, 34, "Técnico em Eletrotécnica", "Técnico em Eletrotécnica"),
            ("Área", True, "Área tecnológica do curso (uma das áreas fixas).", "areas", 20, "ENERGIAS", "ENERGIAS"),
            ("Modalidade", False, "presencial, semipresencial ou EAD.", "modalidades", 14, "presencial", "presencial"),
            ("Tipo do curso", False, "Ex.: técnico, qualificação, aperfeiçoamento, aprendizagem.", "tipos_curso", 18, "técnico", "técnico"),
            ("Carga horária do curso (h)", False, "Carga horária total do curso.", None, 14, 1200, 1200),
            ("Versão da matriz", False, "Versão do currículo (padrão: 1). Para mudar a carga de UCs já usadas por turmas, crie uma versão nova.", None, 14, "2026.1", "2026.1"),
            ("Código da UC", True, "Código da unidade curricular (único dentro da matriz).", None, 14, "FEL", "CMD"),
            ("Nome da UC", True, "Nome da unidade curricular.", None, 34, "Fundamentos de Eletricidade", "Comandos Elétricos"),
            ("Carga horária da UC (h)", True, "Em hora-aula: cada dia de aula tem 4 aulas (um turno inteiro).", None, 12, 40, 60),
            ("Dias de aula por semana", False, "Quantos turnos por semana a UC ocupa (padrão: 1).", None, 12, 2, 1),
            ("Tipo de sala exigido", False, "Um ou mais, separados por ';'. Se não existir, o tipo é criado.", "tipos_sala", 30, "Sala de aula", "Laboratório de comandos elétricos"),
            ("Ordem na matriz", False, "Ordem sugerida da UC no curso (1, 2, 3...).", None, 10, 1, 2),
            ("Pré-requisitos (códigos das UCs)", False, "Códigos de UCs da mesma matriz que precisam terminar antes, separados por ';'.", None, 18, "", "FEL"),
            ("Certificação exigida do instrutor", False, "Ex.: NR-10. O instrutor precisa ter essa certificação para dar a UC.", None, 16, "", "NR-10"),
        ],
    },
    "ambientes": {
        "titulo": "Salas e laboratórios",
        "resumo": "Uma linha por sala, laboratório ou oficina. Salas comuns podem atender TODAS as áreas; laboratórios indicam a(s) área(s) que os usam.",
        "colunas": [
            ("Código da sala", True, "Código único (ex.: BM-S101).", None, 14, "EXEMPLO-S101", "EXEMPLO-LAB-CLP"),
            ("Nome da sala", True, "Nome usado na grade.", None, 28, "Sala 101", "Laboratório de CLP"),
            ("Unidade", True, "BEIRA-MAR ou PORTO.", "unidades", 14, "BEIRA-MAR", "BEIRA-MAR"),
            ("Tipo de ambiente", True, "Se o tipo não existir, ele é criado.", "tipos_sala", 30, "Sala de aula", "Laboratório de automação"),
            ("Laboratório especializado", False, "Sim para laboratórios/oficinas (só recebem UCs que exigem esse tipo).", "sim_nao", 14, "Não", "Sim"),
            ("Áreas", True, "Área(s) que usam o ambiente, separadas por ';', ou TODAS.", "areas_ou_todas", 28, "TODAS", "AUTOMAÇÃO; MECATRÔNICA"),
            ("Capacidade máxima (lugares)", True, "Lugares físicos.", None, 14, 40, 20),
            ("Capacidade recomendada (alunos)", False, "Quantidade ideal de alunos (padrão: igual à máxima).", None, 14, 36, 16),
            ("Prédio/bloco", False, "Localização.", None, 14, "Bloco A", "Bloco B"),
            ("Acessível (PcD)", False, "Sim ou Não.", "sim_nao", 10, "Sim", "Sim"),
            ("Preparação entre aulas (min)", False, "Tempo de arrumação após a aula (laboratórios).", None, 14, 0, 10),
        ],
    },
    "levantamento_instrutores": {
        "titulo": "Levantamento de instrutores e expertise",
        "resumo": "Uma linha por instrutor: áreas, quando pode dar aula e o que sabe ministrar. Envie depois de importar a estrutura curricular, "
                  "pois as UCs informadas precisam existir.",
        "colunas": [
            ("Matrícula ou registro", True, "Identificação institucional única.", None, 14, "EXEMPLO-001", "EXEMPLO-002"),
            ("Nome completo", True, "Nome do instrutor.", None, 28, "Maria Souza", "João Lima"),
            ("E-mail", False, "E-mail institucional.", None, 26, "maria.souza@senai.br", "joao.lima@senai.br"),
            ("Unidade principal", True, "BEIRA-MAR ou PORTO.", "unidades", 14, "BEIRA-MAR", "PORTO"),
            ("Áreas em que atua", True, "A primeira é a principal; outras separadas por ';' (ou TODAS).", "areas_ou_todas", 26, "ENERGIAS; AUTOMAÇÃO", "LOGÍSTICA"),
            ("Carga horária contratual (h/semana)", False, "Jornada contratual.", None, 14, 40, 20),
            ("Limite de aulas por semana (h)", False, "Máximo de horas de aula na semana (≤ contratual).", None, 14, 28, 16),
            ("Máximo de horas por dia", False, "Padrão: 8.", None, 12, 8, 8),
            ("Turnos disponíveis", False, "Manhã, Tarde e/ou Noite, separados por ';'.", "turnos", 20, "Manhã; Tarde", "Noite"),
            ("Dias disponíveis", False, "Ex.: seg a sex; seg;qua;sex.", None, 14, "seg a sex", "seg a qui"),
            ("UCs que ministra (códigos)", False, "Códigos das UCs em que é habilitado, separados por ';'.", None, 22, "FEL; CMD", "LOG01"),
            ("UCs que ministra sob supervisão (códigos)", False, "UCs em que atua acompanhado.", None, 20, "", ""),
            ("Certificações (ex.: NR-10)", False, "Separadas por ';'.", None, 18, "NR-10", ""),
            ("Formação e especialidades", False, "Texto livre: formação, experiência, softwares, equipamentos.", None, 36,
             "Eng. elétrica; 8 anos em manutenção industrial", "Tecnólogo em logística; WMS"),
        ],
    },
    "turmas": {
        "titulo": "Turmas",
        "resumo": "Uma linha por turma. As UCs da matriz são ligadas automaticamente à turma.",
        "colunas": [
            ("Código da turma", True, "Código único.", None, 14, "EXEMPLO-T1", None),
            ("Nome da turma", False, "Nome exibido.", None, 26, "Eletrotécnica 2026/2 Manhã", None),
            ("Código do curso", True, "Curso já cadastrado.", None, 14, "ELT", None),
            ("Versão da matriz", True, "Versão do currículo do curso.", None, 12, "2026.1", None),
            ("Unidade", True, "BEIRA-MAR ou PORTO.", "unidades", 14, "BEIRA-MAR", None),
            ("Turno", False, "Manhã, Tarde ou Noite.", "turnos", 12, "Manhã", None),
            ("Alunos", False, "Quantidade de alunos.", None, 10, 30, None),
            ("Início", True, "Data de início (dd/mm/aaaa).", None, 12, "03/08/2026", None),
            ("Término", True, "Data de término (dd/mm/aaaa).", None, 12, "18/12/2026", None),
            ("Dias de aula", False, "Ex.: seg a sex.", None, 14, "seg a sex", None),
            ("Área", False, "Padrão: a área do curso.", "areas", 18, "ENERGIAS", None),
        ],
    },
}


def gerar_modelo(db: Session, tipo: str) -> bytes:
    cfg = MODELOS[tipo]
    unidades = [u.codigo for u in db.scalars(select(Unidade).where(Unidade.ativo.is_(True)).order_by(Unidade.codigo))]
    areas = [(a.nome, db.get(Unidade, a.unidade_id).codigo) for a in db.scalars(select(Area).where(Area.ativo.is_(True)).order_by(Area.unidade_id, Area.nome))]
    tipos = sorted({*TIPOS_SALA_PADRAO, *(t.nome for t in db.scalars(select(TipoAmbiente).where(TipoAmbiente.ativo.is_(True))) if not t.codigo.startswith("DEMO-"))})
    listas = {
        "unidades": unidades, "areas": [a for a, _ in areas], "areas_ou_todas": ["TODAS"] + [a for a, _ in areas],
        "tipos_sala": tipos, "turnos": ["Manhã", "Tarde", "Noite"], "sim_nao": ["Sim", "Não"],
        "modalidades": ["presencial", "semipresencial", "EAD"],
        "tipos_curso": ["técnico", "qualificação", "aperfeiçoamento", "aprendizagem industrial", "habilitação", "graduação tecnológica"],
    }
    wb = Workbook()
    ws = wb.active
    ws.title = "Preencher"
    cols = cfg["colunas"]
    ws["A1"] = f"Modelo de importação — {cfg['titulo']}"
    ws["A1"].font = Font(name=FONTE, bold=True, size=13)
    ws["A2"] = (cfg["resumo"] + " Preencha a partir da linha 5 (células amarelas). Colunas com * são obrigatórias. "
                "Linhas que começam com EXEMPLO são ignoradas na importação: apague-as ou deixe-as. Envie em Importar planilha.")
    ws["A2"].font = Font(name=FONTE, size=9, italic=True)
    ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(cols))
    ws.row_dimensions[2].height = 48
    lin_cab = 3
    for j, (cab, obrig, _exp, _lista, larg, *_ex) in enumerate(cols, start=1):
        c = ws.cell(row=lin_cab, column=j, value=cab + (" *" if obrig else ""))
        c.font = Font(name=FONTE, bold=True, color="FFFFFF", size=10)
        c.fill = AZUL
        c.alignment = Alignment(wrap_text=True, vertical="center")
        c.border = BORDA
        ws.column_dimensions[get_column_letter(j)].width = larg
    ws.row_dimensions[lin_cab].height = 42
    # exemplos (linha 4 em diante) e área de preenchimento
    n_ex = max(len([x for x in c[5:] if x is not None]) for c in cols)
    for k in range(n_ex):
        for j, col in enumerate(cols, start=1):
            v = col[5 + k] if len(col) > 5 + k else None
            c = ws.cell(row=lin_cab + 1 + k, column=j, value=v)
            c.font = Font(name=FONTE, size=10, italic=True, color="7F7F7F")
            c.fill = CINZA
            c.border = BORDA
    primeira = lin_cab + 1 + n_ex
    for i in range(primeira, primeira + 200):
        for j in range(1, len(cols) + 1):
            c = ws.cell(row=i, column=j)
            c.fill = AMARELO
            c.border = BORDA
            c.font = Font(name=FONTE, size=10)
    ws.freeze_panes = ws.cell(row=lin_cab + 1, column=1)
    # o cabeçalho reconhecido pela importação é a linha 3: o título (linha 1) tem 1 célula e é ignorado
    # Listas
    wl = wb.create_sheet("Listas")
    for j, (nome, valores) in enumerate(listas.items(), start=1):
        wl.cell(row=1, column=j, value=nome).font = Font(name=FONTE, bold=True)
        for i, v in enumerate(valores, start=2):
            wl.cell(row=i, column=j, value=v).font = Font(name=FONTE)
        wl.column_dimensions[get_column_letter(j)].width = 28
    col_lista = {nome: get_column_letter(j) for j, nome in enumerate(listas, start=1)}
    for j, (cab, _o, exp, lista, *_r) in enumerate(cols, start=1):
        if not lista:
            continue
        letra = col_lista[lista]
        livre = lista in ("areas_ou_todas", "tipos_sala", "turnos")  # aceitam vários valores separados por ';'
        dv = DataValidation(type="list", formula1=f"=Listas!${letra}$2:${letra}${len(listas[lista]) + 1}", allow_blank=True,
                            showErrorMessage=not livre, showInputMessage=True, promptTitle=cab[:32], prompt=exp[:250])
        if livre:
            dv.errorStyle = "information"
        ws.add_data_validation(dv)
        dv.add(f"{get_column_letter(j)}{lin_cab + 1}:{get_column_letter(j)}{primeira + 199}")
    # Instruções
    wi = wb.create_sheet("Instruções")
    wi["A1"] = cfg["titulo"]
    wi["A1"].font = Font(name=FONTE, bold=True, size=13)
    wi["A2"] = cfg["resumo"]
    wi["A2"].font = Font(name=FONTE)
    wi["A2"].alignment = Alignment(wrap_text=True)
    wi.merge_cells("A2:C2")
    wi.row_dimensions[2].height = 45
    for j, t in enumerate(("Coluna", "Obrigatória", "O que preencher"), start=1):
        c = wi.cell(row=4, column=j, value=t)
        c.font = Font(name=FONTE, bold=True, color="FFFFFF")
        c.fill = AZUL
    for i, (cab, obrig, exp, *_r) in enumerate(cols, start=5):
        for j, v in enumerate((cab, "Sim" if obrig else "Não", exp), start=1):
            c = wi.cell(row=i, column=j, value=v)
            c.font = Font(name=FONTE)
            c.alignment = Alignment(wrap_text=True, vertical="top")
    if tipo in ("ambientes", "levantamento_instrutores"):
        r = len(cols) + 6
        wi.cell(row=r, column=1, value="Áreas por unidade").font = Font(name=FONTE, bold=True)
        for k, (a, u) in enumerate(areas, start=r + 1):
            wi.cell(row=k, column=1, value=u).font = Font(name=FONTE)
            wi.cell(row=k, column=3, value=a).font = Font(name=FONTE)
    wi.column_dimensions["A"].width = 36
    wi.column_dimensions["B"].width = 12
    wi.column_dimensions["C"].width = 80
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
