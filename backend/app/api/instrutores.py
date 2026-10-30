"""Perfil do instrutor (visão geral), índice de aderência aos cursos da área e PDI."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Body, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import Contexto, requer
from app.core.errors import EntradaInvalida, NaoEncontrado
from app.models import (Alocacao, Ambiente, Bloqueio, CenarioPlanejamento, CompetenciaInstrutor, DisponibilidadeInstrutor,
                        HabilitacaoInstrutor, Instrutor, InstrutorUnidade, PdiItem, TermoHoras, Turma, Unidade, UnidadeCurricular)
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
    """Visão geral do instrutor: dados, áreas, disponibilidade, certificações, turmas e aulas do semestre, ocupação, aderência e PDI."""
    return montar_perfil(db, _instrutor(db, ctx, iid), cenario_id, ctx.pode("dados_pessoais.ler"))


def montar_perfil(db: Session, inst: Instrutor, cenario_id: int | None, ver_email: bool) -> dict:
    """O mesmo perfil para a coordenação (lista de instrutores) e para o próprio instrutor (portal)."""
    from app.api.portal import acesso_do_instrutor
    from app.services.agenda_instrutor import TIPO_PARA_SIGLA
    base = aderencia.Base(db)
    unidades = [db.get(Unidade, inst.unidade_id)] + [db.get(Unidade, u) for u in db.scalars(
        select(InstrutorUnidade.unidade_id).where(InstrutorUnidade.instrutor_id == inst.id)) if u != inst.unidade_id]
    disp = defaultdict(list)
    for d in db.scalars(select(DisponibilidadeInstrutor).where(DisponibilidadeInstrutor.instrutor_id == inst.id)
                        .order_by(DisponibilidadeInstrutor.dia_semana, DisponibilidadeInstrutor.hora_inicio)):
        disp[d.dia_semana].append(f"{d.hora_inicio:%H:%M}–{d.hora_fim:%H:%M}")
    certs = [{"id": h.id, "nome": h.nome, "valido_ate": h.valido_ate.isoformat() if h.valido_ate else None,
              "vencida": bool(h.valido_ate and h.valido_ate < date.today())}
             for h in db.scalars(select(HabilitacaoInstrutor).where(HabilitacaoInstrutor.instrutor_id == inst.id, HabilitacaoInstrutor.ativo.is_(True))
                                 .order_by(HabilitacaoInstrutor.nome))]
    comps = db.scalars(select(CompetenciaInstrutor.nivel).where(CompetenciaInstrutor.instrutor_id == inst.id, CompetenciaInstrutor.ativo.is_(True))).all()
    dados = {"id": inst.id, "matricula": inst.matricula, "nome": inst.nome,
             "email": inst.email if ver_email else None,
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
        # ocupação semana a semana (sobre o contrato) e por turno
        from app.services.regras_aula import limite_letivo_efetivo
        carga = float(inst.carga_horaria_contratual or 0)
        por_sem = defaultdict(float)
        por_turno = defaultdict(float)
        for a in aulas:
            if d0 <= a.data <= d1:
                por_sem[a.data - timedelta(days=a.data.weekday())] += a.minutos_aula / 60
                por_turno["Manhã" if a.inicio.hour < 12 else "Tarde" if a.inicio.hour < 18 else "Noite"] += a.minutos_aula / 60
        seg, serie = d0 - timedelta(days=d0.weekday()), []
        while seg <= d1:
            h = por_sem.get(seg, 0.0)
            serie.append({"semana": f"{seg:%d/%m}", "inicio": seg.isoformat(), "horas": round(h, 1), "pct": round(100 * h / carga, 1) if carga else 0,
                          "passada": seg + timedelta(days=6) < hoje})
            seg += timedelta(days=7)
        pico = max(serie, key=lambda x: x["horas"]) if serie else None
        ocupacao = {"carga_semanal": carga, "limite_letivo": limite_letivo_efetivo(inst), "semanas": serie,
                    "pico": pico, "por_turno": {k: round(v, 1) for k, v in sorted(por_turno.items(), key=lambda x: ["Manhã", "Tarde", "Noite"].index(x[0]))},
                    "semanas_acima_teto": sum(1 for x in serie if x["horas"] > limite_letivo_efetivo(inst) + 1e-6)}
        semestre = {"ocupacao": ocupacao, "cenario_id": cen.id, "inicio": d0.isoformat(), "fim": d1.isoformat(), "aulas": len(aulas), "horas": round(horas, 1),
                    "realizadas": sum(1 for a in aulas if a.data < hoje), "turmas": len({a.turma_id for a in aulas}),
                    "media_semanal_h": round(media, 1), "pct_limite": round(100 * media / float(inst.limite_ch_letiva or 1), 1),
                    "pct_contrato": round(100 * media / float(inst.carga_horaria_contratual or 1), 1),
                    "agenda_h": {k: round(v, 1) for k, v in agenda.items()}, "por_turma": lista, "proximas": proximas}
    termos = None
    if inst.modalidade == "horista":
        from app.services import termos as termos_svc
        hoje_m = termos_svc.mes_de(date.today())
        d0, d1 = (date.fromisoformat(semestre["inicio"]), date.fromisoformat(semestre["fim"])) if semestre else (hoje_m, termos_svc.fim_do_mes(hoje_m))
        meses = termos_svc.listar(db, inst, cen.id if cen is not None else None, d0, d1)
        atual = next((m for m in meses if m["mes"] == hoje_m.isoformat()[:7]), meses[0] if meses else None)
        termos = {"meses": meses, "atual": atual}
    return {"dados": dados, "semestre": semestre, "termos": termos, "aderencia": aderencia.indice(db, inst.id, base), "pdi": _pdi_salvo(db, inst.id)}


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


# ============================================================================ disponibilidade (uma linha por instrutor) e termo de horas
TURNOS_QUADRO = ("M", "T", "V", "N", "S")


def _mesclar(janelas: list[tuple[int, int]]) -> list[tuple[int, int]]:
    res: list[list[int]] = []
    for a, b in sorted(janelas):
        if res and a <= res[-1][1]:
            res[-1][1] = max(res[-1][1], b)
        else:
            res.append([a, b])
    return [(a, b) for a, b in res]


@router.get("/instrutores/disponibilidade")
def quadro_disponibilidade(q: str = "", modalidade: str = "", cenario_id: int | None = None, mes: str | None = None,
                           ctx: Contexto = Depends(requer("cadastros.ler")), db: Session = Depends(get_db)):
    """Uma linha por instrutor: em que turnos de cada dia ele pode dar aula, horas por semana e a carga conforme a
    modalidade — mensalista (jornada semanal fixa, teto de 90%) ou horista (termo de horas do mês)."""
    from app.models import Turno
    from app.services import termos as termos_svc
    from app.services.regras_aula import limite_letivo_efetivo
    ref = termos_svc._mes_param(mes) if mes else termos_svc.mes_de(date.today())
    qi = select(Instrutor).where(Instrutor.ativo.is_(True))
    if ctx.unidades is not None:
        qi = qi.where(Instrutor.unidade_id.in_(ctx.unidades))
    if modalidade in ("mensalista", "horista"):
        qi = qi.where(Instrutor.modalidade == modalidade)
    if q.strip():
        qi = qi.where(Instrutor.nome.ilike(f"%{q.strip()}%") | Instrutor.matricula.ilike(f"%{q.strip()}%"))
    insts = db.scalars(qi.order_by(Instrutor.nome)).all()
    ids = [i.id for i in insts]
    turnos = defaultdict(list)
    for t in db.scalars(select(Turno).where(Turno.ativo.is_(True), Turno.codigo.in_(TURNOS_QUADRO)).order_by(Turno.hora_inicio)):
        turnos[t.unidade_id].append(t)
    janelas = defaultdict(lambda: defaultdict(list))
    for d in db.scalars(select(DisponibilidadeInstrutor).where(DisponibilidadeInstrutor.instrutor_id.in_(ids))) if ids else []:
        janelas[d.instrutor_id][d.dia_semana].append((d.hora_inicio.hour * 60 + d.hora_inicio.minute, d.hora_fim.hour * 60 + d.hora_fim.minute))
    cen = db.get(CenarioPlanejamento, cenario_id) if cenario_id else None
    termos = termos_svc.termos_do(db, [i.id for i in insts if i.modalidade == "horista"], ref, termos_svc.fim_do_mes(ref))
    semestre = {}
    if cen is not None:
        from app.services.indicadores import periodo_padrao
        d0, d1 = periodo_padrao(db, cen)
        semestre = {"inicio": d0.isoformat(), "fim": d1.isoformat()}
        n_termos = defaultdict(int)
        for t in db.scalars(select(TermoHoras).where(TermoHoras.instrutor_id.in_(ids), TermoHoras.mes >= termos_svc.mes_de(d0), TermoHoras.mes <= d1)) if ids else []:
            n_termos[t.instrutor_id] += 1
        meses_sem = len(termos_svc.meses_entre(d0, d1))
    linhas = []
    for i in insts:
        dias = []
        total = 0
        for dia in range(6):
            js = _mesclar(janelas[i.id].get(dia, []))
            total += sum(b - a for a, b in js)
            cods = []
            for t in turnos.get(i.unidade_id, []):
                if (t.codigo == "S") != (dia == 5):
                    continue
                ti, tf = t.hora_inicio.hour * 60 + t.hora_inicio.minute, t.hora_fim.hour * 60 + t.hora_fim.minute
                sob = sum(max(0, min(b, tf) - max(a, ti)) for a, b in js)
                if sob >= 0.5 * (tf - ti):
                    cods.append("V" if t.codigo == "T" else t.codigo)
            dias.append({"dia": dia, "turnos": cods, "janelas": [f"{a // 60:02d}:{a % 60:02d}–{b // 60:02d}:{b % 60:02d}" for a, b in js]})
        linha = {"id": i.id, "nome": i.nome, "matricula": i.matricula, "modalidade": i.modalidade, "nivel": i.nivel,
                 "carga_semanal": float(i.carga_horaria_contratual or 0), "limite_letivo": limite_letivo_efetivo(i),
                 "disponivel_semana_h": round(total / 60, 1), "dias": dias, "sem_disponibilidade": total == 0}
        if i.modalidade == "horista":
            t = termos.get(i.id, {}).get(ref)
            prog = termos_svc.horas_programadas(db, cen.id, i.id, ref) if cen is not None else None
            linha["termo"] = {**termos_svc.termo_dict(t, prog), "tem_termo": True} if t else {"tem_termo": False, "mes": ref.isoformat()[:7],
                                                                                              "rotulo": termos_svc.rotulo_mes(ref), "programadas_h": prog}
            if cen is not None:
                linha["termos_no_semestre"] = {"com_termo": n_termos[i.id], "meses": meses_sem}
        elif cen is not None:
            d0, d1 = date.fromisoformat(semestre["inicio"]), date.fromisoformat(semestre["fim"])
            mins = db.scalar(select(func.coalesce(func.sum(Alocacao.minutos_aula), 0)).where(
                Alocacao.cenario_id == cen.id, Alocacao.instrutor_id == i.id, Alocacao.status != "cancelada",
                Alocacao.data >= d0, Alocacao.data <= d1)) or 0
            media = float(mins) / 60 / max(1.0, ((d1 - d0).days + 1) / 7)
            linha["ocupacao"] = {"media_semanal_h": round(media, 1), "pct_jornada": round(100 * media / linha["carga_semanal"], 1) if linha["carga_semanal"] else 0}
        linhas.append(linha)
    sem_termo = sum(1 for l in linhas if l["modalidade"] == "horista" and not l["termo"]["tem_termo"])
    return {"mes": ref.isoformat()[:7], "rotulo_mes": termos_svc.rotulo_mes(ref), "semestre": semestre, "instrutores": linhas,
            "resumo": {"total": len(linhas), "mensalistas": sum(1 for l in linhas if l["modalidade"] != "horista"),
                       "horistas": sum(1 for l in linhas if l["modalidade"] == "horista"), "horistas_sem_termo": sem_termo,
                       "sem_disponibilidade": sum(1 for l in linhas if l["sem_disponibilidade"])}}


@router.get("/instrutores/{iid}/termos")
def termos_instrutor(iid: int, cenario_id: int | None = None, ctx: Contexto = Depends(requer("cadastros.ler")), db: Session = Depends(get_db)):
    """Termo de horas do horista: do mês passado ao fim do semestre (ou ao próximo mês), com as horas e os dias de aula já
    programados em cada mês, e o termo do próximo mês (feito no fim do mês) com a sugestão do que precisa entrar nele."""
    from app.services import termos as termos_svc
    inst = _instrutor(db, ctx, iid)
    cen = db.get(CenarioPlanejamento, cenario_id) if cenario_id else None
    desde = ate = None
    if cen is not None:
        from app.services.indicadores import periodo_padrao
        desde, ate = periodo_padrao(db, cen)
    return termos_svc.painel(db, inst, cen.id if cen else None, ate=ate, desde=desde)


@router.put("/instrutores/{iid}/termos/{mes}")
def salvar_termo(iid: int, mes: str, d: dict = Body(...), cenario_id: int | None = None, ctx: Contexto = Depends(requer("cadastros.editar")),
                 db: Session = Depends(get_db)):
    """Registra ou altera o termo de horas do mês (AAAA-MM): {"horas_aula", "horas_outras"?, "observacao"?}."""
    from app.services import termos as termos_svc
    inst = _instrutor(db, ctx, iid)
    r = termos_svc.salvar(db, ctx, inst, mes, d.get("horas_aula"), d.get("horas_outras") or 0, d.get("observacao"), cenario_id,
                          dias_semana=d.get("dias_semana"), agenda=d.get("agenda"))
    db.commit()
    return r


@router.post("/instrutores/{iid}/termos/{mes}/ajuste")
def ajustar_termo(iid: int, mes: str, d: dict = Body(...), cenario_id: int | None = None, ctx: Contexto = Depends(requer("cadastros.editar")),
                  db: Session = Depends(get_db)):
    """Ajuste do termo por urgência: {"horas_aula"?, "incluir_dias"?, "motivo", "concordancia": true}. Sem a concordância do
    instrutor, o ajuste é recusado."""
    from app.services import termos as termos_svc
    inst = _instrutor(db, ctx, iid)
    r = termos_svc.ajustar(db, ctx, inst, mes, d.get("motivo") or "", bool(d.get("concordancia")), horas_aula=d.get("horas_aula"),
                           incluir_dias=d.get("incluir_dias"), cenario_id=cenario_id, incluir_turnos=d.get("incluir_turnos"))
    db.commit()
    return r


# ============================================================================ competências (pelo perfil)


@router.put("/instrutores/{iid}/competencias")
def marcar_competencia(iid: int, d: dict = Body(...), ctx: Contexto = Depends(requer("cadastros.editar")), db: Session = Depends(get_db)):
    """Marca a UC no perfil do instrutor: {"curso_id", "uc_codigo", "nivel": "pleno" | "parcial" | "nenhum"}. Vale para todas as
    versões da matriz do curso (a UC é a mesma pelo código)."""
    inst = _instrutor(db, ctx, iid)
    r = aderencia.marcar_competencia(db, ctx, inst, d.get("curso_id"), d.get("uc_codigo"), d.get("nivel"))
    db.commit()
    return {**r, "geral": aderencia.indice(db, inst.id, detalhe=False)["geral"]}


@router.put("/instrutores/{iid}/certificacoes")
def salvar_certificacao(iid: int, d: dict = Body(...), ctx: Contexto = Depends(requer("cadastros.editar")), db: Session = Depends(get_db)):
    """Registra ou atualiza uma certificação/habilitação do instrutor (ex.: NR-10): {"nome", "valido_ate"?}."""
    inst = _instrutor(db, ctx, iid)
    h = aderencia.registrar_certificacao(db, ctx, inst, d.get("nome"), d.get("valido_ate"))
    db.commit()
    return {"id": h.id, "nome": h.nome, "valido_ate": h.valido_ate.isoformat() if h.valido_ate else None,
            "geral": aderencia.indice(db, inst.id, detalhe=False)["geral"]}


@router.post("/instrutores/{iid}/certificacoes/{hid}/retirar")
def retirar_certificacao(iid: int, hid: int, ctx: Contexto = Depends(requer("cadastros.editar")), db: Session = Depends(get_db)):
    """Retira a certificação do perfil (fica inativa no histórico; não é apagada)."""
    inst = _instrutor(db, ctx, iid)
    h = db.get(HabilitacaoInstrutor, hid)
    if h is None or h.instrutor_id != inst.id:
        raise NaoEncontrado("Certificação não encontrada.")
    antes = auditoria.snapshot(h)
    h.ativo = False
    db.flush()
    auditoria.registrar(db, ctx, "certificacao.retirar", "habilitacoes_instrutores", h.id, antes=antes, depois=auditoria.snapshot(h))
    db.commit()
    return {"retirada": h.nome, "geral": aderencia.indice(db, inst.id, detalhe=False)["geral"]}


# ============================================================================ resumo para os cartões da lista
@router.get("/instrutores/resumo")
def resumo_instrutores(cenario_id: int | None = None, ctx: Contexto = Depends(requer("cadastros.ler")), db: Session = Depends(get_db)):
    """Tudo o que o cartão de cada instrutor mostra, de uma vez: UCs que dá, certificações, PDI, disponibilidade, ocupação no
    semestre (sobre o contrato), termo do mês do horista e alertas (certificação vencida, sem termo, sem disponibilidade...)."""
    from app.services import termos as termos_svc
    from app.services.regras_aula import limite_letivo_efetivo
    hoje = date.today()
    q = select(Instrutor)
    if ctx.unidades is not None:
        q = q.where(Instrutor.unidade_id.in_(ctx.unidades))
    insts = db.scalars(q).all()
    ids = [i.id for i in insts]
    if not ids:
        return {}
    unidades = {u.id: u.nome for u in db.scalars(select(Unidade))}
    comps = defaultdict(lambda: {"pleno": 0, "parcial": 0})
    for iid, nivel, n in db.execute(select(CompetenciaInstrutor.instrutor_id, CompetenciaInstrutor.nivel, func.count()).where(
            CompetenciaInstrutor.instrutor_id.in_(ids), CompetenciaInstrutor.ativo.is_(True)).group_by(CompetenciaInstrutor.instrutor_id, CompetenciaInstrutor.nivel)):
        if nivel in ("pleno", "parcial"):
            comps[iid][nivel] = n
    certs = defaultdict(list)
    for h in db.scalars(select(HabilitacaoInstrutor).where(HabilitacaoInstrutor.instrutor_id.in_(ids), HabilitacaoInstrutor.ativo.is_(True))
                        .order_by(HabilitacaoInstrutor.nome)):
        certs[h.instrutor_id].append({"nome": h.nome, "vencida": bool(h.valido_ate and h.valido_ate < hoje),
                                      "vence_em_30": bool(h.valido_ate and hoje <= h.valido_ate <= hoje + timedelta(days=30))})
    pdi = defaultdict(lambda: {"abertos": 0, "atrasados": 0, "concluidos": 0})
    for p in db.scalars(select(PdiItem).where(PdiItem.instrutor_id.in_(ids))):
        if p.situacao in ("planejado", "em_andamento"):
            pdi[p.instrutor_id]["abertos"] += 1
            pdi[p.instrutor_id]["atrasados"] += bool(p.prazo and p.prazo < hoje)
        elif p.situacao == "concluido":
            pdi[p.instrutor_id]["concluidos"] += 1
    com_disp = set(db.scalars(select(DisponibilidadeInstrutor.instrutor_id).where(DisponibilidadeInstrutor.instrutor_id.in_(ids)).distinct()))
    cen = db.get(CenarioPlanejamento, cenario_id) if cenario_id else None
    horas, proxima, turmas = defaultdict(float), {}, defaultdict(set)
    semanas = 1.0
    if cen is not None:
        from app.services.indicadores import periodo_padrao
        d0, d1 = periodo_padrao(db, cen)
        semanas = max(1.0, ((d1 - d0).days + 1) / 7)
        for iid, data, mins, tid in db.execute(select(Alocacao.instrutor_id, Alocacao.data, Alocacao.minutos_aula, Alocacao.turma_id).where(
                Alocacao.cenario_id == cen.id, Alocacao.instrutor_id.in_(ids), Alocacao.status != "cancelada", Alocacao.data >= d0, Alocacao.data <= d1)):
            horas[iid] += mins / 60
            turmas[iid].add(tid)
            if data >= hoje and (iid not in proxima or data < proxima[iid]):
                proxima[iid] = data
    mes = termos_svc.mes_de(hoje)
    termos = termos_svc.termos_do(db, [i.id for i in insts if i.modalidade == "horista"], mes, termos_svc.fim_do_mes(mes))
    res = {}
    for i in insts:
        carga = float(i.carga_horaria_contratual or 0)
        media = horas[i.id] / semanas
        alertas = []
        if i.id not in com_disp:
            alertas.append(("bloqueio", "sem disponibilidade cadastrada"))
        if any(c["vencida"] for c in certs[i.id]):
            alertas.append(("bloqueio", "certificação vencida"))
        if pdi[i.id]["atrasados"]:
            alertas.append(("alerta", f"{pdi[i.id]['atrasados']} item(ns) do PDI com prazo vencido"))
        termo = None
        if i.modalidade == "horista":
            t = termos.get(i.id, {}).get(mes)
            termo = {"rotulo": termos_svc.rotulo_mes(mes), "horas_aula": float(t.horas_aula) if t else None}
            if t is None:
                alertas.append(("alerta", f"sem termo de {termos_svc.rotulo_mes(mes)}"))
        if cen is not None and media > limite_letivo_efetivo(i) + 1e-6:
            alertas.append(("alerta", "acima do limite semanal do contrato"))
        res[i.id] = {"unidade": unidades.get(i.unidade_id), "ucs_sim": comps[i.id]["pleno"], "ucs_em_partes": comps[i.id]["parcial"],
                     "certificacoes": certs[i.id], "pdi": pdi[i.id], "termo": termo,
                     "semestre": {"media_semanal_h": round(media, 1), "pct_contrato": round(100 * media / carga, 1) if carga else 0,
                                  "turmas": len(turmas[i.id]), "proxima_aula": proxima[i.id].isoformat() if i.id in proxima else None} if cen else None,
                     "alertas": [{"tipo": t, "texto": x} for t, x in alertas]}
    return res
