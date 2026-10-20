"""Perfil do instrutor (visão geral), índice de aderência aos cursos da área e PDI."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

from fastapi import APIRouter, Body, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import Contexto, requer
from app.core.errors import EntradaInvalida, NaoEncontrado
from app.models import (Alocacao, Ambiente, Bloqueio, CenarioPlanejamento, CompetenciaInstrutor, DisponibilidadeInstrutor,
                        HabilitacaoInstrutor, Instrutor, InstrutorUnidade, PdiItem, Turma, Unidade, UnidadeCurricular)
from app.services import aderencia, auditoria

router = APIRouter(prefix="/api", tags=["instrutores"])

DIAS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
SITUACOES_PDI = ("planejado", "em_andamento", "concluido", "cancelado")


def _instrutor(db: Session, ctx: Contexto, iid: int) -> Instrutor:
    inst = db.get(Instrutor, iid)
    if inst is None:
        raise NaoEncontrado("Instrutor não encontrado.")
    ctx.exigir_unidade(inst.unidade_id)
    return inst


def _pdi_dict(p: PdiItem, cursos: dict) -> dict:
    return {"id": p.id, "curso_id": p.curso_id, "curso": cursos.get(p.curso_id), "uc_codigo": p.uc_codigo, "uc_nome": p.uc_nome, "tipo": p.tipo,
            "certificacao": p.certificacao, "prioridade": p.prioridade, "prazo": p.prazo.isoformat() if p.prazo else None,
            "situacao": p.situacao, "observacao": p.observacao, "concluido_em": p.concluido_em.isoformat() if p.concluido_em else None,
            "atrasado": bool(p.prazo and p.prazo < date.today() and p.situacao in ("planejado", "em_andamento"))}


def _pdi_salvo(db: Session, iid: int) -> list[dict]:
    from app.models import Curso
    itens = db.scalars(select(PdiItem).where(PdiItem.instrutor_id == iid).order_by(PdiItem.situacao == "cancelado", PdiItem.prazo, PdiItem.id)).all()
    cursos = {c.id: c.codigo for c in db.scalars(select(Curso).where(Curso.id.in_({p.curso_id for p in itens if p.curso_id})))} if itens else {}
    return [_pdi_dict(p, cursos) for p in itens]


@router.get("/aderencia/equipe")
def aderencia_equipe(area_id: int | None = None, ctx: Contexto = Depends(requer("cadastros.ler")), db: Session = Depends(get_db)):
    """Índice de aderência de cada instrutor (para a lista) e a cobertura das UCs por área."""
    return aderencia.equipe(db, ctx.unidades, area_id)


@router.get("/instrutores/{iid}/perfil")
def perfil(iid: int, cenario_id: int | None = None, ctx: Contexto = Depends(requer("cadastros.ler")), db: Session = Depends(get_db)):
    """Visão geral do instrutor: dados, áreas, disponibilidade, certificações, turmas e aulas do semestre, aderência e PDI."""
    from app.api.portal import acesso_do_instrutor
    from app.services.agenda_instrutor import TIPO_PARA_SIGLA
    inst = _instrutor(db, ctx, iid)
    base = aderencia.Base(db)
    unidades = [db.get(Unidade, inst.unidade_id)] + [db.get(Unidade, u) for u in db.scalars(
        select(InstrutorUnidade.unidade_id).where(InstrutorUnidade.instrutor_id == inst.id)) if u != inst.unidade_id]
    disp = defaultdict(list)
    for d in db.scalars(select(DisponibilidadeInstrutor).where(DisponibilidadeInstrutor.instrutor_id == inst.id)
                        .order_by(DisponibilidadeInstrutor.dia_semana, DisponibilidadeInstrutor.hora_inicio)):
        disp[d.dia_semana].append(f"{d.hora_inicio:%H:%M}–{d.hora_fim:%H:%M}")
    certs = [{"nome": h.nome, "valido_ate": h.valido_ate.isoformat() if h.valido_ate else None,
              "vencida": bool(h.valido_ate and h.valido_ate < date.today())}
             for h in db.scalars(select(HabilitacaoInstrutor).where(HabilitacaoInstrutor.instrutor_id == inst.id, HabilitacaoInstrutor.ativo.is_(True))
                                 .order_by(HabilitacaoInstrutor.nome))]
    comps = db.scalars(select(CompetenciaInstrutor.nivel).where(CompetenciaInstrutor.instrutor_id == inst.id, CompetenciaInstrutor.ativo.is_(True))).all()
    dados = {"id": inst.id, "matricula": inst.matricula, "nome": inst.nome,
             "email": inst.email if ctx.pode("dados_pessoais.ler") else None,
             "unidade": unidades[0].nome if unidades[0] else None, "outras_unidades": [u.nome for u in unidades[1:] if u],
             "area": base.areas[inst.area_id].nome if inst.area_id in base.areas else None,
             "areas": [base.areas[a].nome for a in base.areas_do(inst)], "todas_areas": inst.todas_areas,
             "nivel": inst.nivel, "modalidade": inst.modalidade, "carga_contratual": float(inst.carga_horaria_contratual or 0),
             "limite_letivo": float(inst.limite_ch_letiva or 0), "situacao": inst.situacao, "ativo": inst.ativo,
             "disponibilidade": [{"dia": DIAS[d], "janelas": j} for d, j in sorted(disp.items())],
             "certificacoes": certs, "ucs_sim": sum(1 for n in comps if n == "pleno"), "ucs_em_partes": sum(1 for n in comps if n == "parcial"),
             "portal": acesso_do_instrutor(db, inst.id), "atualizado_pelo_instrutor_em":
                 inst.atualizado_pelo_instrutor_em.isoformat() if getattr(inst, "atualizado_pelo_instrutor_em", None) else None}
    semestre = None
    cen = db.get(CenarioPlanejamento, cenario_id) if cenario_id else None
    if cen is not None:
        from app.services.indicadores import periodo_padrao
        d0, d1 = periodo_padrao(db, cen)
        aulas = db.scalars(select(Alocacao).where(Alocacao.cenario_id == cen.id, Alocacao.instrutor_id == inst.id, Alocacao.status != "cancelada")
                           .order_by(Alocacao.inicio)).all()
        hoje = date.today()
        por = {}
        for a in aulas:
            k = (a.turma_id, a.uc_id)
            x = por.setdefault(k, {"turma_id": a.turma_id, "uc_id": a.uc_id, "aulas": 0, "horas": 0.0, "realizadas": 0, "proxima": None, "ultima": None})
            x["aulas"] += 1
            x["horas"] += a.minutos_aula / 60
            x["realizadas"] += a.data < hoje
            if a.data >= hoje and not x["proxima"]:
                x["proxima"] = a.data.isoformat()
            x["ultima"] = a.data.isoformat()
        turmas = {t.id: t for t in db.scalars(select(Turma).where(Turma.id.in_({k[0] for k in por})))} if por else {}
        ucs = {u.id: u for u in db.scalars(select(UnidadeCurricular).where(UnidadeCurricular.id.in_({k[1] for k in por})))} if por else {}
        lista = []
        for x in por.values():
            t, u = turmas.get(x["turma_id"]), ucs.get(x["uc_id"])
            lista.append({**x, "horas": round(x["horas"], 1), "turma": t.codigo if t else "?", "turma_nome": t.nome if t else "",
                          "uc": u.codigo if u else "?", "uc_nome": u.nome if u else ""})
        lista.sort(key=lambda x: (x["proxima"] is None, x["proxima"] or "", x["turma"]))
        semanas = max(1.0, ((d1 - d0).days + 1) / 7)
        horas = sum(a.minutos_aula for a in aulas) / 60
        amb = {a.id: a.codigo for a in db.scalars(select(Ambiente).where(Ambiente.id.in_({a.ambiente_id for a in aulas if a.ambiente_id})))} if aulas else {}
        proximas = [{"data": a.data.isoformat(), "inicio": f"{a.inicio:%H:%M}", "fim": f"{a.fim:%H:%M}", "turma": turmas[a.turma_id].codigo if a.turma_id in turmas else "?",
                     "uc": ucs[a.uc_id].codigo if a.uc_id in ucs else "?", "sala": amb.get(a.ambiente_id)} for a in aulas if a.data >= hoje][:6]
        agenda = defaultdict(float)
        for b in db.scalars(select(Bloqueio).where(Bloqueio.alvo_tipo == "instrutor", Bloqueio.alvo_id == inst.id, Bloqueio.ativo.is_(True),
                                                   Bloqueio.inicio >= datetime.combine(d0, datetime.min.time()),
                                                   Bloqueio.inicio <= datetime.combine(d1, datetime.max.time()))):
            agenda[TIPO_PARA_SIGLA.get(b.tipo, "outros")] += (b.fim - b.inicio).total_seconds() / 3600
        media = horas / semanas
        semestre = {"cenario_id": cen.id, "inicio": d0.isoformat(), "fim": d1.isoformat(), "aulas": len(aulas), "horas": round(horas, 1),
                    "realizadas": sum(1 for a in aulas if a.data < hoje), "turmas": len({a.turma_id for a in aulas}),
                    "media_semanal_h": round(media, 1), "pct_limite": round(100 * media / float(inst.limite_ch_letiva or 1), 1),
                    "pct_contrato": round(100 * media / float(inst.carga_horaria_contratual or 1), 1),
                    "agenda_h": {k: round(v, 1) for k, v in agenda.items()}, "por_turma": lista, "proximas": proximas}
    return {"dados": dados, "semestre": semestre, "aderencia": aderencia.indice(db, inst.id, base), "pdi": _pdi_salvo(db, inst.id)}


@router.get("/instrutores/{iid}/pdi")
def pdi(iid: int, ctx: Contexto = Depends(requer("cadastros.ler")), db: Session = Depends(get_db)):
    """Propostas de PDI (o que falta para 100% nos cursos da área, por prioridade) e o PDI já planejado."""
    _instrutor(db, ctx, iid)
    return {**aderencia.propostas(db, iid), "salvo": _pdi_salvo(db, iid)}


@router.post("/instrutores/{iid}/pdi")
def incluir_pdi(iid: int, d: dict = Body(...), ctx: Contexto = Depends(requer("cadastros.editar")), db: Session = Depends(get_db)):
    """Inclui propostas no PDI do instrutor: {"itens": [{curso_id, uc_codigo, tipo, prazo?, prioridade?, observacao?}]}."""
    inst = _instrutor(db, ctx, iid)
    base = aderencia.Base(db)
    novos = []
    for it in d.get("itens") or [d]:
        cid, cod, tipo = it.get("curso_id"), str(it.get("uc_codigo") or "").strip(), it.get("tipo") or "uc"
        uc = base.ucs.get(int(cid) if cid else -1, {}).get(cod)
        if uc is None:
            raise EntradaInvalida(f"UC {cod or '?'} não encontrada no curso.")
        if tipo not in ("uc", "completar", "certificacao"):
            raise EntradaInvalida("Tipo do item: uc, completar ou certificacao.")
        if db.scalar(select(PdiItem.id).where(PdiItem.instrutor_id == inst.id, PdiItem.curso_id == int(cid), PdiItem.uc_codigo == cod,
                                              PdiItem.tipo == tipo, PdiItem.situacao.in_(["planejado", "em_andamento"]))):
            continue  # já está no PDI
        p = PdiItem(instrutor_id=inst.id, curso_id=int(cid), uc_codigo=cod, uc_nome=uc["nome"], tipo=tipo,
                    certificacao=uc["cert"] if tipo == "certificacao" else None, prioridade=it.get("prioridade"),
                    prazo=date.fromisoformat(it["prazo"]) if it.get("prazo") else None, observacao=it.get("observacao"), criado_por_id=ctx.id)
        db.add(p)
        db.flush()
        auditoria.registrar(db, ctx, "pdi.incluir", "pdi_itens", p.id, depois=auditoria.snapshot(p))
        novos.append(p.id)
    db.commit()
    return {"incluidos": len(novos), "salvo": _pdi_salvo(db, inst.id)}


@router.put("/pdi/{pid}")
def atualizar_pdi(pid: int, d: dict = Body(...), ctx: Contexto = Depends(requer("cadastros.editar")), db: Session = Depends(get_db)):
    """Muda situação, prazo ou observação. Concluir com "habilitar": true marca a UC como "sim" no perfil do instrutor
    (ou registra a certificação), e o índice de aderência sobe."""
    p = db.get(PdiItem, pid)
    if p is None:
        raise NaoEncontrado("Item do PDI não encontrado.")
    inst = _instrutor(db, ctx, p.instrutor_id)
    antes = auditoria.snapshot(p)
    if "situacao" in d:
        if d["situacao"] not in SITUACOES_PDI:
            raise EntradaInvalida("Situação: planejado, em_andamento, concluido ou cancelado.")
        p.situacao = d["situacao"]
        p.concluido_em = date.today() if p.situacao == "concluido" else None
    if "prazo" in d:
        p.prazo = date.fromisoformat(d["prazo"]) if d["prazo"] else None
    if "observacao" in d:
        p.observacao = d["observacao"] or None
    habilitou = []
    if p.situacao == "concluido" and d.get("habilitar"):
        base = aderencia.Base(db)
        uc = base.ucs.get(p.curso_id or -1, {}).get(p.uc_codigo)
        if uc is None:
            raise EntradaInvalida("A UC não está mais na matriz do curso; marque a competência pelo cadastro do instrutor.")
        if p.tipo == "certificacao":
            nome = p.certificacao or uc["cert"]
            h = db.scalar(select(HabilitacaoInstrutor).where(HabilitacaoInstrutor.instrutor_id == inst.id, HabilitacaoInstrutor.nome == nome))
            if h is None:
                db.add(HabilitacaoInstrutor(instrutor_id=inst.id, nome=nome, ativo=True))
            else:
                h.ativo, h.valido_ate = True, None if h.valido_ate and h.valido_ate < date.today() else h.valido_ate
            habilitou.append(nome)
        else:
            for uid in sorted(uc["ids"]):
                c = db.scalar(select(CompetenciaInstrutor).where(CompetenciaInstrutor.instrutor_id == inst.id, CompetenciaInstrutor.uc_id == uid))
                if c is None:
                    db.add(CompetenciaInstrutor(instrutor_id=inst.id, uc_id=uid, nivel="pleno", ativo=True))
                else:
                    c.nivel, c.ativo = "pleno", True
            habilitou.append(p.uc_codigo)
    db.flush()
    auditoria.registrar(db, ctx, "pdi.atualizar", "pdi_itens", p.id, antes=antes, depois={**auditoria.snapshot(p), "habilitou": habilitou})
    db.commit()
    return {"item": _pdi_salvo(db, inst.id), "habilitou": habilitou, "geral": aderencia.indice(db, inst.id, detalhe=False)["geral"]}
