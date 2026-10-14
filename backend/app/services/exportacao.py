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
    linhas = _limpo(linhas)
    buf = io.StringIO()
    if linhas:
        w = csv.DictWriter(buf, fieldnames=list(linhas[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(linhas)
    return ("﻿" + buf.getvalue()).encode("utf-8")


def para_xlsx(abas: dict[str, list[dict]], titulo: str | None = None) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    for nome, linhas in abas.items():
        ws = wb.create_sheet(nome[:31])
        linhas = _limpo(linhas)
        r0 = 1
        if titulo:
            ws.cell(1, 1, titulo).font = Font(bold=True, size=12)
            r0 = 3
        if not linhas:
            ws.cell(r0, 1, "Sem dados para os filtros selecionados.")
            continue
        cols = list(linhas[0].keys())
        for j, c in enumerate(cols, 1):
            cel = ws.cell(r0, j, c)
            cel.font = Font(bold=True, color="FFFFFF")
            cel.fill = PatternFill("solid", fgColor="1F4E79")
        for i, l in enumerate(linhas, r0 + 1):
            for j, c in enumerate(cols, 1):
                v = l[c]
                ws.cell(i, j, v if isinstance(v, (int, float, str)) or v is None else str(v))
        for j, c in enumerate(cols, 1):
            ws.column_dimensions[get_column_letter(j)].width = min(45, max(10, len(c) + 2, *(len(str(l[c])) + 2 for l in linhas[:200])))
        ws.freeze_panes = ws.cell(r0 + 1, 1)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def matriz_semanal(linhas: list[dict], semana: date) -> list[dict]:
    """Grade visual da semana: linhas = horário, colunas = dias."""
    seg = semana - timedelta(days=semana.weekday())
    cel = defaultdict(list)
    horarios = set()
    for l in linhas:
        d = l["_data"]
        if seg <= d < seg + timedelta(days=7):
            h = f"{l['inicio']}–{l['fim']}"
            horarios.add(h)
            cel[(h, d.weekday())].append(f"{l['turma']} | {l['uc'].split(' – ')[0]} | {l['instrutor']} | {l['ambiente']}")
    return [{"horario": h, **{DIAS[k]: "\n".join(cel.get((h, k), [])) for k in range(6)}} for h in sorted(horarios)]


def para_pdf(titulo: str, linhas: list[dict], subtitulo: str | None = None, max_linhas: int = 3000) -> bytes:
    linhas = _limpo(linhas)[:max_linhas]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24, title=titulo)
    st = getSampleStyleSheet()
    pequeno = st["BodyText"].clone("p", fontSize=7, leading=8.5)
    elems = [Paragraph(titulo, st["Title"])]
    if subtitulo:
        elems.append(Paragraph(subtitulo, st["Normal"]))
    elems.append(Spacer(1, 8))
    if not linhas:
        elems.append(Paragraph("Sem dados para os filtros selecionados.", st["Normal"]))
    else:
        cols = list(linhas[0].keys())
        dados = [[Paragraph(f"<b>{c}</b>", pequeno) for c in cols]]
        for l in linhas:
            dados.append([Paragraph(str(l[c]).replace("\n", "<br/>"), pequeno) for c in cols])
        largura = (landscape(A4)[0] - 48) / len(cols)
        t = Table(dados, repeatRows=1, colWidths=[largura] * len(cols))
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                               ("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F6FA")])]))
        elems.append(t)
    doc.build(elems)
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
