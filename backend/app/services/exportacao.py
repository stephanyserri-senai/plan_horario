"""Exportação de grades e relatórios em XLSX, CSV e PDF."""
from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date, timedelta

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alocacao, Ambiente, CenarioPlanejamento, Instrutor, Turma, Turno, UnidadeCurricular

DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


def linhas_grade(db: Session, cenario_id: int, filtro: str | None = None, filtro_id: int | None = None, d0: date | None = None,
                 d1: date | None = None, unidades_permitidas=None) -> list[dict]:
    q = select(Alocacao).where(Alocacao.cenario_id == cenario_id, Alocacao.status != "cancelada")
    if filtro == "turma":
        q = q.where(Alocacao.turma_id == filtro_id)
    elif filtro == "instrutor":
        q = q.where(Alocacao.instrutor_id == filtro_id)
    elif filtro == "ambiente":
        q = q.where(Alocacao.ambiente_id == filtro_id)
    elif filtro == "turno":
        q = q.join(Turma, Turma.id == Alocacao.turma_id).where(Turma.turno_id == filtro_id)
    if d0:
        q = q.where(Alocacao.data >= d0)
    if d1:
        q = q.where(Alocacao.data <= d1)
    aulas = db.scalars(q.order_by(Alocacao.data, Alocacao.inicio)).all()
    turmas = {t.id: t for t in db.scalars(select(Turma))}
    ucs = {u.id: u for u in db.scalars(select(UnidadeCurricular).where(UnidadeCurricular.id.in_({a.uc_id for a in aulas})))} if aulas else {}
    insts = {i.id: i for i in db.scalars(select(Instrutor))}
    ambs = {a.id: a for a in db.scalars(select(Ambiente))}
    turnos = {t.id: t for t in db.scalars(select(Turno))}
    res = []
    for a in aulas:
        t = turmas[a.turma_id]
        if unidades_permitidas is not None and t.unidade_id not in unidades_permitidas:
            continue
        res.append({
            "data": a.data.strftime("%d/%m/%Y"), "dia": DIAS[a.data.weekday()], "inicio": a.inicio.strftime("%H:%M"), "fim": a.fim.strftime("%H:%M"),
            "turma": t.codigo, "turno": turnos[t.turno_id].nome if t.turno_id in turnos else "", "uc": f"{ucs[a.uc_id].codigo} – {ucs[a.uc_id].nome}",
            "grupo": a.grupo or "", "instrutor": insts[a.instrutor_id].nome if a.instrutor_id in insts else "(pendente)",
            "ambiente": ambs[a.ambiente_id].codigo if a.ambiente_id in ambs else "(pendente)", "horas": round(a.minutos_aula / 60, 2),
            "situacao": a.status, "fixa": "sim" if a.fixa else "", "_data": a.data, "_ini": a.inicio,
        })
    return res


def _limpo(linhas):
    return [{k: v for k, v in l.items() if not k.startswith("_")} for l in linhas]


def para_csv(linhas: list[dict]) -> bytes:
    """CSV (;) mantido por compatibilidade com integrações; a tela oferece só Excel e PDF."""
    linhas = _limpo(linhas)
    buf = io.StringIO()
    if linhas:
        cols = []
        for l in linhas:
            cols += [k for k in l if k not in cols]
        w = csv.DictWriter(buf, fieldnames=cols, delimiter=";")
        w.writeheader()
        w.writerows(linhas)
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


# ----------------------------------------------------------------------------- colunas dos relatórios
# (chave, título, largura no Excel, vai para o PDF?) — só o que interessa a quem lê, na ordem de leitura
COLUNAS: dict[str, list[tuple[str, str, int, bool]]] = {
    "grade": [("data", "Data", 11, True), ("dia", "Dia", 10, True), ("inicio", "Início", 8, True), ("fim", "Fim", 8, True),
              ("turno", "Turno", 9, True), ("turma", "Turma", 13, True), ("uc", "Unidade curricular", 38, True), ("grupo", "Grupo", 7, False),
              ("instrutor", "Instrutor", 22, True), ("ambiente", "Sala / laboratório", 14, True), ("horas", "Horas", 7, True),
              ("situacao", "Situação", 11, True), ("fixa", "Fixa", 6, False)],
    "ambientes": [("codigo", "Código", 11, True), ("nome", "Sala / laboratório", 30, True), ("tipo", "Tipo", 22, True),
                  ("especializado", "Especializado", 12, False), ("situacao", "Situação", 12, False), ("capacidade_fisica", "Lugares", 9, True),
                  ("capacidade_operacional", "Capacidade operacional", 12, False), ("horas_disponiveis", "Horas disponíveis", 11, True),
                  ("horas_bloqueadas", "Horas bloqueadas", 11, False), ("horas_ocupadas", "Horas ocupadas", 11, True),
                  ("horas_ociosas", "Horas livres", 11, True), ("taxa_ocupacao_pct", "Ocupação (%)", 10, True),
                  ("utilizacao_capacidade_fisica_pct", "Uso dos lugares (%)", 11, True), ("aulas", "Aulas", 8, True),
                  ("classificacao", "Classificação", 14, True)],
    "por_turno": [("turno", "Turno", 24, True), ("horas_ocupadas", "Horas ocupadas", 14, True), ("horas_disponiveis", "Horas disponíveis", 14, True),
                  ("taxa_ocupacao_pct", "Ocupação (%)", 12, True)],
    "por_dia": [("dia", "Dia da semana", 16, True), ("horas_ocupadas", "Horas ocupadas", 14, True), ("horas_disponiveis", "Horas disponíveis", 14, True),
                ("taxa_ocupacao_pct", "Ocupação (%)", 12, True)],
    "instrutores": [("nome", "Instrutor", 26, True), ("matricula", "Matrícula", 11, True), ("carga_contratual_h", "Carga contratual (h/sem)", 11, True),
                    ("limite_letivo_h", "Limite de aulas (h/sem)", 11, True), ("capacidade_efetiva_h", "Capacidade efetiva (h/sem)", 11, False),
                    ("alocada_media_semanal_h", "Aulas por semana (média, h)", 12, True), ("maior_semana_h", "Maior semana (h)", 10, True),
                    ("restante_semanal_h", "Folga (h/sem)", 9, True), ("ocupacao_pct", "Ocupação (%)", 10, True),
                    ("alocada_total_h", "Total no período (h)", 11, False), ("turmas_lista", "Turmas", 26, True), ("ucs_lista", "UCs", 30, False),
                    ("por_turno_h", "Horas por turno", 26, False), ("por_dia_semana_h", "Horas por dia", 30, False), ("janelas_h", "Janelas (h)", 9, False),
                    ("semanas_acima_limite", "Semanas acima do limite", 11, True), ("critico", "Atenção", 9, True)],
    "turmas_ucs": [("turma_codigo", "Turma", 13, True), ("turma_nome", "Nome da turma", 30, False), ("uc_codigo", "UC", 11, True),
                   ("uc_nome", "Unidade curricular", 32, True), ("total_h", "CH total (h)", 10, True), ("realizada_h", "Realizada (h)", 11, True),
                   ("programada_h", "Programada (h)", 12, True), ("restante_h", "Falta (h)", 9, True), ("percentual_conclusao", "Concluído (%)", 12, True),
                   ("percentual_programado", "Programado (%)", 10, False), ("encontros_semanais", "Encontros por semana", 10, False),
                   ("data_inicio", "Início", 11, False), ("data_limite", "Prazo", 11, True), ("proxima_aula", "Próxima aula", 11, False),
                   ("ultima_aula", "Última aula", 11, True), ("instrutores", "Instrutores", 26, True), ("ambientes_utilizados", "Salas", 18, False),
                   ("aulas_sem_instrutor", "Aulas sem instrutor", 10, False), ("aulas_sem_ambiente", "Aulas sem sala", 10, False),
                   ("risco_atraso", "Risco de atraso", 12, True), ("estado_planejamento", "Situação", 14, True)],
    "gargalos": [("tipo", "Tipo", 22, True), ("recurso", "Onde falta", 34, True), ("turno", "Turno", 12, True), ("demanda_h", "Demanda (h/sem)", 11, True),
                 ("oferta_h", "Oferta (h/sem)", 11, True), ("atendivel_h", "Atendível (h/sem)", 11, False), ("deficit_h", "Falta (h/sem)", 10, True),
                 ("descricao", "Descrição", 60, True), ("alternativas", "O que fazer", 50, True), ("instrutores_habilitados", "Instrutores habilitados", 30, False)],
    "semana": [("horario", "Horário", 16, True)] + [(d, d, 30, True) for d in DIAS[:6]],
    "periodo": [("semana", "Semana", 14, True), ("horario", "Horário", 13, True)] + [(d, d, 30, True) for d in DIAS[:6]],
    "importacao": [("linha", "Linha", 8, True), ("acao", "Resultado", 22, True), ("erros", "Erros", 60, True), ("avisos", "Avisos", 50, True)],
}
NOMES_ABA = {"dados": "Dados", "ambientes": "Salas e laboratórios", "por_turno": "Por turno", "por_dia": "Por dia da semana",
             "instrutores": "Instrutores", "turmas_ucs": "Turmas e UCs", "gargalos": "Gargalos", "semana": "Semana", "aulas": "Aulas"}
VALORES = {"tipo": {"deficit_capacidade_total": "Falta de salas (todos os turnos)", "deficit_turno": "Falta de salas no turno",
                    "deficit_habilitacao": "Falta de instrutor habilitado", "conflito_distribuicao": "Distribuição da turma",
                    "indisponibilidade_equipamentos": "Falta de equipamentos", "inviabilidade_calendario": "Prazo / calendário"},
           "situacao": {"programada": "Programada", "realizada": "Realizada", "cancelada": "Cancelada", "operacional": "Operacional",
                        "manutencao": "Manutenção", "interditado": "Interditado"},
           "risco_atraso": {"sem_risco": "Sem risco", "baixo": "Baixo", "medio": "Médio", "alto": "Alto"},
           "estado_planejamento": {"programada_integralmente": "Toda programada", "parcialmente_programada": "Parcialmente programada",
                                   "em_execucao": "Em execução", "pendente_alocacao": "Sem horário", "concluida": "Concluída",
                                   "cancelada": "Cancelada", "prevista": "Prevista", "ofertada": "Ofertada"},
           "classificacao": {"subutilizado": "Pouco usado", "adequado": "Adequado", "demanda_excessiva": "Sobrecarregado",
                             "sem_disponibilidade": "Sem horário disponível"},
           "acao": {"criar": "Novo", "atualizar": "Atualizado", "sem_alteracao": "Sem alteração", "erro": "Erro",
                    "bloqueada_na_gravacao": "Bloqueada na gravação"}}
_SIGLAS = {"uc": "UC", "ucs": "UCs", "ch": "CH", "id": "ID", "pct": "(%)", "h": "(h)"}


def _rotulo_generico(k: str) -> str:
    if " " in k or k[:1].isupper():
        return k  # já é um título legível
    partes = [_SIGLAS.get(p, p) for p in k.split("_") if p]
    txt = " ".join(partes)
    return txt[:1].upper() + txt[1:]


def _valor(k: str, v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "Sim" if v else "Não"
    if k in VALORES and isinstance(v, str):
        return VALORES[k].get(v, v)
    if isinstance(v, str) and len(v) == 10 and v[4] == "-" and v[7] == "-":
        try:
            return date.fromisoformat(v).strftime("%d/%m/%Y")
        except ValueError:
            return v
    if isinstance(v, (date,)):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, float):
        return round(v, 1)
    if isinstance(v, (int, str)):
        return v
    return str(v)


def colunas(aba: str, linhas: list[dict]) -> list[tuple[str, str, int, bool]]:
    """Colunas do relatório: as definidas para a aba (só as presentes) ou, sem definição, todas com rótulo legível."""
    presentes = []
    for l in linhas:
        for k in l:
            if not k.startswith("_") and k not in presentes:
                presentes.append(k)
    if aba in COLUNAS:
        return [c for c in COLUNAS[aba] if c[0] in presentes]
    return [(k, _rotulo_generico(k), min(40, max(11, len(_rotulo_generico(k)) // 2 + 4)), True) for k in presentes if not (k == "id" or k.endswith("_id"))]


# ----------------------------------------------------------------------------- XLSX
AZUL, AZUL_CLARO, CINZA = "1F4E79", "F2F6FA", "D9D9D9"
INSTITUICAO = "SENAI-ES · Planejamento Acadêmico"


def para_xlsx(abas: dict[str, list[dict]], titulo: str | None = None, meta: list[str] | None = None, tipos: dict[str, str] | None = None,
              titulos: dict[str, str] | None = None) -> bytes:
    """Planilha com cabeçalho institucional, colunas com nome em português, faixas alternadas, filtro e impressão em paisagem."""
    from openpyxl.styles import Border, Side
    from openpyxl.worksheet.properties import PageSetupProperties
    borda = Border(*(Side(style="thin", color=CINZA),) * 4)
    wb = Workbook()
    wb.remove(wb.active)
    for nome, linhas in abas.items():
        ws = wb.create_sheet(NOMES_ABA.get(nome, nome)[:31])
        tipo = (tipos or {}).get(nome, nome)  # aba com nome livre (ex.: uma por turma) usa as colunas de um tipo conhecido
        cols = colunas(tipo, linhas)
        n = max(1, len(cols))
        ws.cell(1, 1, INSTITUICAO).font = Font(name="Arial", size=9, color="595959")
        ws.cell(2, 1, (titulos or {}).get(nome) or titulo or NOMES_ABA.get(nome, nome)).font = Font(name="Arial", bold=True, size=14, color=AZUL)
        r = 3
        for m in (meta or []):
            ws.cell(r, 1, m).font = Font(name="Arial", size=9, italic=True, color="595959")
            r += 1
        r0 = r + 1
        ws.sheet_view.showGridLines = False
        if not linhas:
            ws.cell(r0, 1, "Sem dados para os filtros selecionados.").font = Font(name="Arial", italic=True)
            continue
        for j, (k, t, w, _pdf) in enumerate(cols, 1):
            cel = ws.cell(r0, j, t)
            cel.font = Font(name="Arial", bold=True, color="FFFFFF", size=10)
            cel.fill = PatternFill("solid", fgColor=AZUL)
            cel.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cel.border = borda
            ws.column_dimensions[get_column_letter(j)].width = w
        ws.row_dimensions[r0].height = 32
        zebra = PatternFill("solid", fgColor=AZUL_CLARO)
        for i, l in enumerate(linhas, r0 + 1):
            for j, (k, _t, w, _pdf) in enumerate(cols, 1):
                v = _valor(k, l.get(k))
                cel = ws.cell(i, j, v)
                cel.font = Font(name="Arial", size=10)
                cel.border = borda
                num = isinstance(v, (int, float)) and not isinstance(v, bool)
                cel.alignment = Alignment(vertical="top", wrap_text=not num and isinstance(v, str) and (len(v) > w or "\n" in v),
                                          horizontal="right" if num else "left")
                if isinstance(v, float):
                    cel.number_format = "0.0"
                if (i - r0) % 2 == 0:
                    cel.fill = zebra
        for i, l in enumerate(linhas, r0 + 1):  # altura pelas quebras (manuais e automáticas): o Excel não ajusta sozinho
            n_linhas = 1
            for k, _t, w, _p in cols:
                v = l.get(k)
                if isinstance(v, str) and v:
                    n_linhas = max(n_linhas, sum(max(1, -(-len(parte) // max(1, int(w * 1.1)))) for parte in v.split("\n")))
            if n_linhas > 1:
                ws.row_dimensions[i].height = min(400, 13 * n_linhas + 2)
        ultima = r0 + len(linhas)
        ws.freeze_panes = ws.cell(r0 + 1, 1)
        ws.auto_filter.ref = f"A{r0}:{get_column_letter(n)}{ultima}"
        # impressão: paisagem, cabe na largura, cabeçalho da tabela repetido, rodapé com página
        ws.page_setup.orientation = "landscape"
        ws.page_setup.paperSize = ws.PAPERSIZE_A4
        ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
        ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
        ws.print_title_rows = f"{r0}:{r0}"
        ws.oddFooter.center.text = "Página &P de &N"
        ws.oddFooter.right.text = INSTITUICAO
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def matriz_semanal(linhas: list[dict], semana: date, sem_turma: bool = False) -> list[dict]:
    """Grade visual da semana: linhas = horário, colunas = dias (sem_turma: para a aba de uma turma só)."""
    seg = semana - timedelta(days=semana.weekday())
    cel = defaultdict(list)
    horarios = set()
    for l in linhas:
        d = l["_data"]
        if seg <= d < seg + timedelta(days=7):
            h = f"{l['inicio']}–{l['fim']}"
            horarios.add(h)
            partes = ([] if sem_turma else [l["turma"]]) + [l["uc"] if sem_turma else l["uc"].split(" – ")[0], l["instrutor"], l["ambiente"]]
            cel[(h, d.weekday())].append(("\n" if sem_turma else " | ").join(partes))
    dias = [k for k in range(6) if k < 5 or any(dk == k for (_h, dk) in cel)]  # sábado só se houver aula
    sep = "\n\n" if sem_turma else "\n"
    return [{"horario": h, **{DIAS[k]: sep.join(cel.get((h, k), [])) for k in dias}} for h in sorted(horarios)]


def matriz_periodo(linhas: list[dict], d0: date, d1: date, sem_turma: bool = False) -> list[dict]:
    """Quadro horário × dia semana após semana (mês ou semestre): cada linha leva a semana e o horário."""
    linhas = [l for l in linhas if d0 <= l["_data"] <= d1]
    usa_sab = any(l["_data"].weekday() == 5 for l in linhas)
    res, seg = [], d0 - timedelta(days=d0.weekday())
    while seg <= d1:
        da_semana = [l for l in linhas if seg <= l["_data"] < seg + timedelta(days=7)]
        if da_semana:
            rot = f"{max(seg, d0):%d/%m} a {min(seg + timedelta(days=5 if usa_sab else 4), d1):%d/%m}"
            for r in matriz_semanal(da_semana, seg, sem_turma):
                if usa_sab:
                    r.setdefault(DIAS[5], "")
                res.append({"semana": rot, **r})
        seg += timedelta(days=7)
    return res


def para_pdf(titulo: str, linhas: list[dict] | None = None, subtitulo: str | None = None, max_linhas: int = 3000,
             abas: dict[str, list[dict]] | None = None, meta: list[str] | None = None, aba: str = "dados") -> bytes:
    """PDF A4 paisagem: faixa de título em todas as páginas, rodapé com página e data, tabelas com nomes em português."""
    secoes = abas if abas else {aba: linhas or []}
    st = getSampleStyleSheet()
    cel = st["BodyText"].clone("cel", fontName="Helvetica", fontSize=7.4, leading=9)
    cel_num = cel.clone("num", alignment=2)
    cab = cel.clone("cab", fontName="Helvetica-Bold", textColor=colors.white, alignment=1)
    h2 = st["Heading2"].clone("h2", fontSize=11, textColor=colors.HexColor("#1F4E79"), spaceBefore=6, spaceAfter=4)
    nota = st["Normal"].clone("nota", fontSize=8, textColor=colors.HexColor("#595959"))
    largura_util = landscape(A4)[0] - 48
    elems = []
    for m in ([subtitulo] if subtitulo else []) + (meta or []):
        elems.append(Paragraph(m, nota))
    elems.append(Spacer(1, 6))
    for nome, ls in secoes.items():
        ls = (ls or [])[:max_linhas]
        if len(secoes) > 1:
            elems.append(Paragraph(NOMES_ABA.get(nome, nome), h2))
        if not ls:
            elems.append(Paragraph("Sem dados para os filtros selecionados.", st["Normal"]))
            continue
        cols = [c for c in colunas(nome, ls) if c[3]] or colunas(nome, ls)
        pesos = [max(5, w) for _k, _t, w, _p in cols]
        larguras = [largura_util * p / sum(pesos) for p in pesos]
        dados = [[Paragraph(t, cab) for _k, t, _w, _p in cols]]
        for l in ls:
            linha = []
            for k, _t, _w, _p in cols:
                v = _valor(k, l.get(k))
                num = isinstance(v, (int, float)) and not isinstance(v, bool)
                txt = (f"{v:.1f}" if isinstance(v, float) else str(v)).replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br/>")
                linha.append(Paragraph(txt, cel_num if num else cel))
            dados.append(linha)
        t = Table(dados, repeatRows=1, colWidths=larguras)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("VALIGN", (0, 0), (-1, 0), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#D9D9D9")),
                               ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#BFBFBF")),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F6FA")]),
                               ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        elems.append(t)
        if len(ls) >= max_linhas:
            elems.append(Paragraph(f"Mostrando as primeiras {max_linhas} linhas; a planilha (Excel) traz todas.", nota))
    return montar_pdf(titulo, elems)


def montar_pdf(titulo: str, elems: list) -> bytes:
    """Documento A4 paisagem com faixa de título e rodapé (página X de Y) em todas as páginas."""
    from datetime import datetime
    from reportlab.platypus.doctemplate import PageTemplate, BaseDocTemplate
    from reportlab.platypus.frames import Frame
    buf = io.BytesIO()
    larg, alt = landscape(A4)
    gerado = datetime.now().strftime("%d/%m/%Y %H:%M")

    class _Doc(BaseDocTemplate):
        pass

    def faixa(c, doc):
        c.saveState()
        c.setFillColor(colors.HexColor("#1F4E79"))
        c.rect(0, alt - 46, larg, 46, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica", 8)
        c.drawString(24, alt - 16, INSTITUICAO)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(24, alt - 34, titulo[:120])
        c.setFillColor(colors.HexColor("#595959"))
        c.setFont("Helvetica", 7.5)
        c.drawString(24, 14, f"Gerado em {gerado}")
        c.drawRightString(larg - 24, 14, f"Página {doc.page}")
        c.restoreState()

    doc = _Doc(buf, pagesize=(larg, alt), leftMargin=24, rightMargin=24, topMargin=58, bottomMargin=30, title=titulo, author=INSTITUICAO)
    doc.addPageTemplates([PageTemplate(id="p", frames=[Frame(24, 30, larg - 48, alt - 88, id="f")], onPage=faixa)])
    doc.build(elems or [Spacer(1, 1)])
    return buf.getvalue()


def achatar(itens: list[dict]) -> list[dict]:
    """Converte dicionários aninhados em colunas simples para planilhas."""
    res = []
    for i in itens:
        l = {}
        for k, v in i.items():
            if isinstance(v, dict):
                l[k] = "; ".join(f"{a}: {b}" for a, b in v.items())
            elif isinstance(v, list):
                l[k] = "; ".join(str(x) if not isinstance(x, dict) else ", ".join(f"{a}={b}" for a, b in x.items()) for x in v)
            else:
                l[k] = v
        res.append(l)
    return res


def nome_cenario(db: Session, cenario_id: int) -> str:
    c = db.get(CenarioPlanejamento, cenario_id)
    return f"{c.nome} (v{c.versao}, {c.estado})" if c else str(cenario_id)


def planilha_para_pdf(conteudo_xlsx: bytes, titulo: str, meta: list[str] | None = None, max_linhas_tabela: int = 400) -> bytes:
    """PDF a partir de uma planilha formatada: cada aba vira uma seção; linhas de título viram texto e cada bloco que
    começa num cabeçalho azul vira uma tabela, com as cores de fundo das células e larguras proporcionais."""
    from openpyxl import load_workbook
    from reportlab.platypus import CondPageBreak, KeepTogether
    wb = load_workbook(io.BytesIO(conteudo_xlsx))
    st = getSampleStyleSheet()
    cel = st["BodyText"].clone("pc", fontName="Helvetica", fontSize=7, leading=8.6)
    cab = cel.clone("pcab", fontName="Helvetica-Bold", textColor=colors.white, alignment=1)
    h2 = st["Heading2"].clone("ph2", fontSize=11.5, textColor=colors.HexColor("#1F4E79"), spaceBefore=4, spaceAfter=3)
    txt = st["Normal"].clone("ptx", fontSize=8.5, leading=10.5)
    nota = txt.clone("pnota", fontSize=8, textColor=colors.HexColor("#595959"))
    largura_util = landscape(A4)[0] - 48
    elems = [Paragraph(m, nota) for m in (meta or [])] + [Spacer(1, 4)]

    def esc(v):
        if v is None:
            return ""
        if isinstance(v, float):
            v = f"{v:.1f}"
        elif hasattr(v, "strftime"):
            v = v.strftime("%d/%m/%Y")
        return str(v).replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br/>")

    def azul(c):
        f = c.fill
        return f is not None and f.fill_type == "solid" and str(f.fgColor.rgb or "").upper().endswith(AZUL)

    abas = [ws for ws in wb.worksheets if ws.sheet_state == "visible"]
    for n_aba, ws in enumerate(abas):
        if n_aba:
            elems.append(CondPageBreak(160))
        if len(abas) > 1:
            elems.append(Paragraph(esc(ws.title), h2))
        r, max_r = 1, ws.max_row
        while r <= max_r:
            valores = [ws.cell(r, j).value for j in range(1, ws.max_column + 1)]
            if all(v in (None, "") for v in valores):
                r += 1
                continue
            if azul(ws.cell(r, 1)):
                ncols = max(j for j in range(1, ws.max_column + 1) if ws.cell(r, j).value not in (None, ""))
                larg = [ws.column_dimensions[get_column_letter(j)].width or 10 for j in range(1, ncols + 1)]
                larg = [largura_util * w / sum(larg) for w in larg]
                dados = [[Paragraph(esc(ws.cell(r, j).value), cab) for j in range(1, ncols + 1)]]
                estilo = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                          ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#BFBFBF")),
                          ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]
                r += 1
                while r <= max_r and any(ws.cell(r, j).value not in (None, "") for j in range(1, ncols + 1)) and not azul(ws.cell(r, 1)):
                    if len(dados) <= max_linhas_tabela:
                        linha = []
                        for j in range(1, ncols + 1):
                            c = ws.cell(r, j)
                            linha.append(Paragraph(("<b>%s</b>" % esc(c.value)) if c.font and c.font.b else esc(c.value), cel))
                            f = c.fill
                            rgb = str(f.fgColor.rgb or "") if f is not None and f.fill_type == "solid" else ""
                            if len(rgb) >= 6 and rgb[-6:].upper() not in ("FFFFFF", "000000"):
                                estilo.append(("BACKGROUND", (j - 1, len(dados)), (j - 1, len(dados)), colors.HexColor("#" + rgb[-6:])))
                        dados.append(linha)
                    r += 1
                t = Table(dados, repeatRows=1, colWidths=larg)
                t.setStyle(TableStyle(estilo))
                elems.append(t)
                if len(dados) > max_linhas_tabela:
                    elems.append(Paragraph(f"Tabela resumida às primeiras {max_linhas_tabela} linhas; a planilha (Excel) traz todas.", nota))
                elems.append(Spacer(1, 6))
                continue
            # linha de texto (títulos e observações da aba)
            texto = " · ".join(esc(v) for v in valores if v not in (None, ""))
            c1 = ws.cell(r, 1)
            if r == 1 and len(abas) > 1 and str(c1.value or "") == ws.title:
                r += 1
                continue
            grande = c1.font is not None and (c1.font.sz or 10) >= 12
            elems.append(Paragraph(texto, h2 if grande and len(abas) == 1 else (txt.clone("b", fontName="Helvetica-Bold") if c1.font and c1.font.b else nota)))
            r += 1
    return montar_pdf(titulo, elems)
