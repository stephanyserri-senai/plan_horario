"""Cenários, grade horária, alocações, exceções e geração de horários."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal, get_db
from app.core.deps import Contexto, get_contexto, requer
from app.core.errors import AcessoNegado, ConflitoValidacao, EntradaInvalida, NaoEncontrado
from app.models import (
    Alocacao, AlocacaoRecurso, Ambiente, CenarioPlanejamento, ExcecaoAutorizada, ExecucaoOtimizacao, HistoricoAuditoria, Instrutor,
    ParametrosOtimizacao, PeriodoHorario, RegistroDecisao, ResultadoOtimizacao, Turma, TurmaUC, Turno, UnidadeCurricular, Validacao,
    OcorrenciaValidacao, VersaoPlanejamento,
)
from app.services import alocacao as aloc
from app.services import auditoria, cenarios, objetivo, otimizacao
from app.services.calendario import combinar, minutos
from app.services.planejamento import matriz_oferta
from app.solver.criterios import descricao_criterios, normalizar_pesos

router = APIRouter(prefix="/api", tags=["planejamento"])


def _cenario_dict(c: CenarioPlanejamento, db: Session) -> dict:
    n = db.scalar(select(func.count()).select_from(Alocacao).where(Alocacao.cenario_id == c.id, Alocacao.status != "cancelada"))
    d = auditoria.snapshot(c)
    d["aulas"] = n
    return d


# ============================================================================ cenários
@router.get("/cenarios")
def listar_cenarios(tipo: str | None = None, estado: str | None = None, ctx: Contexto = Depends(requer("alocacoes.ler")), db: Session = Depends(get_db)):
    q = select(CenarioPlanejamento).order_by(CenarioPlanejamento.id.desc())
    if tipo:
        q = q.where(CenarioPlanejamento.tipo == tipo)
    if estado:
        q = q.where(CenarioPlanejamento.estado == estado)
    if ctx.unidades is not None:
        q = q.where(or_(CenarioPlanejamento.unidade_id.in_(ctx.unidades), CenarioPlanejamento.unidade_id.is_(None)))
    return [_cenario_dict(c, db) for c in db.scalars(q)]


@router.post("/cenarios")
def criar_cenario(d: dict = Body(...), ctx: Contexto = Depends(requer("cenarios.criar")), db: Session = Depends(get_db)):
    ctx.exigir_unidade(d.get("unidade_id"))
    if d.get("copiar_de"):
        c = cenarios.copiar(db, ctx, int(d["copiar_de"]), d["nome"])
    else:
        c = cenarios.criar(db, ctx, d["nome"], d.get("unidade_id"), d.get("periodo_inicio") and date.fromisoformat(d["periodo_inicio"]),
                           d.get("periodo_fim") and date.fromisoformat(d["periodo_fim"]), d.get("descricao"))
    db.commit()
    return _cenario_dict(c, db)


@router.get("/cenarios/{cid}")
def obter_cenario(cid: int, ctx: Contexto = Depends(requer("alocacoes.ler")), db: Session = Depends(get_db)):
    c = db.get(CenarioPlanejamento, cid)
    if c is None:
        raise NaoEncontrado("Cenário não encontrado.")
    ctx.exigir_unidade(c.unidade_id)
    return _cenario_dict(c, db)


@router.put("/cenarios/{cid}")
def atualizar_cenario(cid: int, d: dict = Body(...), ctx: Contexto = Depends(requer("cenarios.editar")), db: Session = Depends(get_db)):
    c = aloc.obter_cenario_editavel(db, cid, bloquear=True)
    antes = auditoria.snapshot(c)
    for k in ("nome", "descricao"):
        if k in d:
            setattr(c, k, d[k])
    for k in ("periodo_inicio", "periodo_fim"):
        if k in d:
            setattr(c, k, date.fromisoformat(d[k]) if d[k] else None)
    c.lock_version += 1
    auditoria.registrar(db, ctx, "cenario.alterar", "cenarios_planejamento", cid, antes=antes, depois=auditoria.snapshot(c))
    db.commit()
    return _cenario_dict(c, db)


@router.delete("/cenarios/{cid}")
def excluir_cenario(cid: int, ctx: Contexto = Depends(requer("cenarios.editar")), db: Session = Depends(get_db)):
    cenarios.excluir(db, ctx, cid)
    db.commit()
    return {"ok": True}


@router.post("/cenarios/{cid}/transicao")
def transicao(cid: int, d: dict = Body(...), ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)):
    try:
        r = cenarios.transicionar(db, ctx, cid, d["estado"], d.get("motivo"), d.get("lock_version"))
        db.commit()
        return r
    except ConflitoValidacao:
        db.commit()  # mantém o registro da validação que motivou o bloqueio
        raise


@router.post("/cenarios/{cid}/validar")
def validar_cenario(cid: int, ctx: Contexto = Depends(requer("alocacoes.ler")), db: Session = Depends(get_db)):
    r = cenarios.validar(db, ctx, cid)
    db.commit()
    return r


@router.get("/cenarios/{cid}/validacoes")
def validacoes(cid: int, ctx: Contexto = Depends(requer("alocacoes.ler")), db: Session = Depends(get_db)):
    v = db.scalars(select(Validacao).where(Validacao.cenario_id == cid).order_by(Validacao.id.desc())).first()
    if not v:
        return None
    oc = db.scalars(select(OcorrenciaValidacao).where(OcorrenciaValidacao.validacao_id == v.id)).all()
    return {"validacao": auditoria.snapshot(v), "ocorrencias": [auditoria.snapshot(o) for o in oc]}


@router.get("/cenarios/{cid}/versoes")
def versoes(cid: int, ctx: Contexto = Depends(requer("alocacoes.ler")), db: Session = Depends(get_db)):
    return [{"id": v.id, "numero": v.numero, "estado": v.estado, "motivo": v.motivo, "criado_em": v.criado_em.isoformat(), "aulas": len(v.snapshot),
             "indicadores": v.indicadores} for v in db.scalars(select(VersaoPlanejamento).where(VersaoPlanejamento.cenario_id == cid).order_by(VersaoPlanejamento.numero.desc()))]


@router.post("/cenarios/{cid}/versoes")
def nova_versao(cid: int, d: dict = Body(default={}), ctx: Contexto = Depends(requer("cenarios.editar")), db: Session = Depends(get_db)):
    v = cenarios.criar_versao(db, ctx, cid, d.get("motivo"))
    db.commit()
    return {"id": v.id, "numero": v.numero}


@router.get("/versoes/comparar")
def comparar_versoes(a: int, b: int, ctx: Contexto = Depends(requer("alocacoes.ler")), db: Session = Depends(get_db)):
    return cenarios.comparar_versoes(db, a, b)


@router.post("/versoes/{vid}/restaurar")
def restaurar(vid: int, d: dict = Body(default={}), ctx: Contexto = Depends(requer("cenarios.restaurar")), db: Session = Depends(get_db)):
    r = cenarios.restaurar(db, ctx, vid, bool(d.get("como_novo")))
    db.commit()
    return r


@router.post("/cenarios/comparar")
def comparar(d: dict = Body(...), ctx: Contexto = Depends(requer("indicadores.ler")), db: Session = Depends(get_db)):
    return cenarios.comparar(db, [int(x) for x in d["cenarios"]], d.get("pesos"))


@router.get("/cenarios/{cid}/avaliacao")
def avaliacao(cid: int, ctx: Contexto = Depends(requer("indicadores.ler")), db: Session = Depends(get_db)):
    return objetivo.avaliar_cenario(db, cid)


@router.post("/cenarios/{cid}/proposta")
def proposta(cid: int, d: dict = Body(...), ctx: Contexto = Depends(requer("cenarios.criar")), db: Session = Depends(get_db)):
    c = cenarios.proposta_alteracao(db, ctx, cid, d.get("nome") or "Proposta de alteração", d.get("descricao"))
    db.commit()
    return _cenario_dict(c, db)


@router.get("/cenarios/{cid}/impacto")
def impacto(cid: int, ctx: Contexto = Depends(requer("alocacoes.ler")), db: Session = Depends(get_db)):
    return cenarios.impacto_proposta(db, cid)


# ============================================================================ grade
def _filtrar_aulas(db, ctx, cenario_id, inicio, fim, turma_id=None, instrutor_id=None, ambiente_id=None, turno_id=None, curso_id=None,
                   unidade_id=None, uc_id=None, q=None):
    stmt = (select(Alocacao, Turma, UnidadeCurricular, Instrutor, Ambiente)
            .join(Turma, Turma.id == Alocacao.turma_id).join(UnidadeCurricular, UnidadeCurricular.id == Alocacao.uc_id)
            .outerjoin(Instrutor, Instrutor.id == Alocacao.instrutor_id).outerjoin(Ambiente, Ambiente.id == Alocacao.ambiente_id)
            .where(Alocacao.cenario_id == cenario_id, Alocacao.status != "cancelada"))
    if inicio:
        stmt = stmt.where(Alocacao.data >= inicio)
    if fim:
        stmt = stmt.where(Alocacao.data <= fim)
    for col, v in ((Alocacao.turma_id, turma_id), (Alocacao.instrutor_id, instrutor_id), (Alocacao.ambiente_id, ambiente_id),
                   (Turma.turno_id, turno_id), (Turma.curso_id, curso_id), (Turma.unidade_id, unidade_id), (Alocacao.uc_id, uc_id)):
        if v:
            stmt = stmt.where(col == v)
    if q:
        stmt = stmt.where(or_(Turma.codigo.ilike(f"%{q}%"), UnidadeCurricular.codigo.ilike(f"%{q}%"), UnidadeCurricular.nome.ilike(f"%{q}%"),
                              Instrutor.nome.ilike(f"%{q}%"), Ambiente.codigo.ilike(f"%{q}%")))
    if ctx.unidades is not None:
        stmt = stmt.where(Turma.unidade_id.in_(ctx.unidades))
    if ctx.cursos is not None:
        stmt = stmt.where(Turma.curso_id.in_(ctx.cursos))
    if ctx.turmas is not None:
        stmt = stmt.where(Turma.id.in_(ctx.turmas))
    return db.execute(stmt.order_by(Alocacao.data, Alocacao.inicio).limit(5000)).all()


@router.get("/grade")
def grade(cenario_id: int, inicio: date | None = None, fim: date | None = None, turma_id: int | None = None, instrutor_id: int | None = None,
          ambiente_id: int | None = None, turno_id: int | None = None, curso_id: int | None = None, unidade_id: int | None = None,
          uc_id: int | None = None, q: str | None = None, ctx: Contexto = Depends(requer("alocacoes.ler")), db: Session = Depends(get_db)):
    linhas = _filtrar_aulas(db, ctx, cenario_id, inicio, fim, turma_id, instrutor_id, ambiente_id, turno_id, curso_id, unidade_id, uc_id, q)
    return [{"id": a.id, "versao": a.versao, "data": a.data.isoformat(), "inicio": a.inicio.strftime("%H:%M"), "fim": a.fim.strftime("%H:%M"),
             "minutos_aula": a.minutos_aula, "turma_id": t.id, "turma": t.codigo, "turno_id": t.turno_id, "turma_uc_id": a.turma_uc_id,
             "uc_id": u.id, "uc": u.codigo, "uc_nome": u.nome, "grupo": a.grupo, "instrutor_id": a.instrutor_id, "instrutor": i.nome if i else None,
             "ambiente_id": a.ambiente_id, "ambiente": amb.codigo if amb else None, "status": a.status, "fixa": a.fixa, "origem": a.origem,
             "observacao": a.observacao, "atividade_id": a.atividade_id}
            for a, t, u, i, amb in linhas]


@router.get("/grade/livres")
def horarios_livres(cenario_id: int, semana: date, turma_id: int | None = None, instrutor_id: int | None = None, ambiente_id: int | None = None,
                    unidade_id: int | None = None, ctx: Contexto = Depends(requer("alocacoes.ler")), db: Session = Depends(get_db)):
    """Períodos livres na semana para os recursos informados (simultaneamente)."""
    if not unidade_id:
        if turma_id:
            unidade_id = db.get(Turma, turma_id).unidade_id
        elif ambiente_id:
            unidade_id = db.get(Ambiente, ambiente_id).unidade_id
        elif instrutor_id:
            unidade_id = db.get(Instrutor, instrutor_id).unidade_id
        else:
            raise EntradaInvalida("Informe turma, instrutor, ambiente ou unidade.")
    seg = semana - timedelta(days=semana.weekday())
    periodos = db.scalars(select(PeriodoHorario).where(PeriodoHorario.unidade_id == unidade_id, PeriodoHorario.ativo.is_(True))
                          .order_by(PeriodoHorario.turno_id, PeriodoHorario.ordem)).all()
    conds = []
    if turma_id:
        conds.append(Alocacao.turma_id == turma_id)
    if instrutor_id:
        conds.append(Alocacao.instrutor_id == instrutor_id)
    if ambiente_id:
        conds.append(Alocacao.ambiente_id == ambiente_id)
    ocupadas = db.scalars(select(Alocacao).where(Alocacao.cenario_id == cenario_id, Alocacao.status != "cancelada", Alocacao.data >= seg,
                                                 Alocacao.data < seg + timedelta(days=7), or_(*conds) if conds else True)).all()
    turma = db.get(Turma, turma_id) if turma_id else None
    livres = []
    for k in range(7):
        d = seg + timedelta(days=k)
        if turma and d.weekday() not in (turma.dias_possiveis or []):
            continue
        for p in periodos:
            if d.weekday() not in (p.dias_semana or []):
                continue
            if turma and turma.turno_id and p.turno_id != turma.turno_id:
                continue
            ini, fimp = combinar(d, p.hora_inicio), combinar(d, p.hora_fim)
            if not any(a.data == d and a.inicio < fimp and ini < a.fim for a in ocupadas):
                livres.append({"data": d.isoformat(), "periodo_id": p.id, "turno_id": p.turno_id, "ordem": p.ordem,
                               "inicio": p.hora_inicio.strftime("%H:%M"), "fim": p.hora_fim.strftime("%H:%M")})
    return livres


@router.get("/periodos")
def periodos(unidade_id: int, ctx: Contexto = Depends(requer("alocacoes.ler")), db: Session = Depends(get_db)):
    turnos = {t.id: t for t in db.scalars(select(Turno).where(Turno.unidade_id == unidade_id))}
    return [{"id": p.id, "turno_id": p.turno_id, "turno": turnos[p.turno_id].nome if p.turno_id in turnos else None, "ordem": p.ordem,
             "inicio": p.hora_inicio.strftime("%H:%M"), "fim": p.hora_fim.strftime("%H:%M"), "dias_semana": p.dias_semana, "excepcional": p.excepcional}
            for p in db.scalars(select(PeriodoHorario).where(PeriodoHorario.unidade_id == unidade_id, PeriodoHorario.ativo.is_(True))
                                .order_by(PeriodoHorario.turno_id, PeriodoHorario.ordem))]


def _dados_aula(d: dict) -> aloc.DadosAula:
    try:
        return aloc.DadosAula(
            turma_uc_id=int(d["turma_uc_id"]), data=date.fromisoformat(d["data"]),
            periodo_inicio_id=int(d["periodo_inicio_id"]) if d.get("periodo_inicio_id") else None,
            num_periodos=int(d["num_periodos"]) if d.get("num_periodos") else None,
            hora_inicio=time.fromisoformat(d["hora_inicio"]) if d.get("hora_inicio") else None,
            hora_fim=time.fromisoformat(d["hora_fim"]) if d.get("hora_fim") else None,
            grupo=int(d["grupo"]) if d.get("grupo") not in (None, "", 0, "0") else None,
            instrutor_id=int(d["instrutor_id"]) if d.get("instrutor_id") else None,
            ambiente_id=int(d["ambiente_id"]) if d.get("ambiente_id") else None,
            recursos=[(int(r["recurso_id"]), int(r.get("quantidade", 1))) for r in d.get("recursos", [])],
            excecao_id=int(d["excecao_id"]) if d.get("excecao_id") else None, fixa=bool(d.get("fixa")), observacao=d.get("observacao"))
    except (KeyError, ValueError) as e:
        raise EntradaInvalida(f"Dados da aula inválidos: {e}")


def _exigir_turma(db, ctx, turma_uc_id):
    tuc = db.get(TurmaUC, turma_uc_id)
    if tuc is None:
        raise EntradaInvalida("Turma×UC inexistente.")
    t = db.get(Turma, tuc.turma_id)
    if not ctx.acessa_turma(t):
        raise AcessoNegado("Turma fora do seu escopo de acesso.")


def _registrar_bloqueio(ctx, cenario_id, dados, erro):
    """Registra a tentativa bloqueada em transação própria (indicador de conflitos evitados)."""
    with SessionLocal() as s:
        auditoria.registrar(s, ctx, "alocacao.bloqueada", "alocacoes", None, depois={"cenario_id": cenario_id, "dados": dados,
                                                                                     "regras": [o["regra"] for o in (erro.detalhes or {}).get("ocorrencias", [])]},
                            motivo=erro.mensagem)
        s.commit()


@router.post("/alocacoes")
def criar_alocacao(d: dict = Body(...), ctx: Contexto = Depends(requer("alocacoes.editar")), db: Session = Depends(get_db)):
    cid = int(d["cenario_id"])
    dados = _dados_aula(d)
    _exigir_turma(db, ctx, dados.turma_uc_id)
    try:
        if d.get("recorrente"):
            atv, criadas, puladas, oc = aloc.criar_recorrente(db, ctx, cid, dados, int(d["dia_semana"]), date.fromisoformat(d["data_inicio"]),
                                                              date.fromisoformat(d["data_fim"]), bool(d.get("limitar_carga_horaria", True)))
            db.commit()
            return {"atividade_id": atv.id, "aulas_criadas": len(criadas), "datas_puladas": puladas,
                    "alertas": [o.to_dict() for o in oc if o.severidade != "bloqueio"][:100]}
        a, oc = aloc.criar_aula(db, ctx, cid, dados, validar_somente=bool(d.get("somente_validar")))
        db.commit()
        if a is None:
            return {"valida": True, "ocorrencias": [o.to_dict() for o in oc]}
        return {"id": a.id, "versao": a.versao, "ocorrencias": [o.to_dict() for o in oc]}
    except ConflitoValidacao as e:
        db.rollback()
        _registrar_bloqueio(ctx, cid, d, e)
        raise


@router.put("/alocacoes/{aid}")
def atualizar_alocacao(aid: int, d: dict = Body(...), ctx: Contexto = Depends(requer("alocacoes.editar")), db: Session = Depends(get_db)):
    atual = db.get(Alocacao, aid)
    if atual is None:
        raise NaoEncontrado("Aula não encontrada.")
    base = {"turma_uc_id": atual.turma_uc_id, "data": atual.data.isoformat(), "hora_inicio": atual.inicio.strftime("%H:%M"),
            "hora_fim": atual.fim.strftime("%H:%M"), "grupo": atual.grupo, "instrutor_id": atual.instrutor_id, "ambiente_id": atual.ambiente_id,
            "fixa": atual.fixa, "excecao_id": atual.excecao_id,
            "recursos": [{"recurso_id": r.recurso_id, "quantidade": r.quantidade} for r in db.scalars(select(AlocacaoRecurso).where(AlocacaoRecurso.alocacao_id == aid))]}
    if d.get("periodo_inicio_id"):
        base.pop("hora_inicio")
        base.pop("hora_fim")
    merged = {**base, **{k: v for k, v in d.items() if k not in ("versao", "motivo")}}
    dados = _dados_aula(merged)
    _exigir_turma(db, ctx, dados.turma_uc_id)
    try:
        a, oc = aloc.atualizar_aula(db, ctx, aid, dados, int(d["versao"]), d.get("motivo"))
        db.commit()
        return {"id": a.id, "versao": a.versao, "ocorrencias": [o.to_dict() for o in oc]}
    except ConflitoValidacao as e:
        db.rollback()
        _registrar_bloqueio(ctx, atual.cenario_id, d, e)
        raise


@router.delete("/alocacoes/{aid}")
def remover_alocacao(aid: int, versao: int | None = None, motivo: str | None = None, ctx: Contexto = Depends(requer("alocacoes.editar")),
                     db: Session = Depends(get_db)):
    a = db.get(Alocacao, aid)
    if a:
        _exigir_turma(db, ctx, a.turma_uc_id)
    aloc.remover_aula(db, ctx, aid, versao, motivo)
    db.commit()
    return {"ok": True}


@router.post("/alocacoes/alternativas")
def alternativas(d: dict = Body(...), ctx: Contexto = Depends(requer("alocacoes.ler")), db: Session = Depends(get_db)):
    dados = _dados_aula(d)
    p, _tuc, _t = aloc._proposta(db, dados, alocacao_id=d.get("alocacao_id"))
    return aloc.sugerir_alternativas(db, int(d["cenario_id"]), p)


@router.post("/alocacoes/copiar_semana")
def copiar_semana(d: dict = Body(...), ctx: Contexto = Depends(requer("alocacoes.editar")), db: Session = Depends(get_db)):
    t = db.get(Turma, int(d["turma_id"]))
    if not t or not ctx.acessa_turma(t):
        raise AcessoNegado("Turma fora do seu escopo.")
    criadas = aloc.copiar_semana(db, ctx, int(d["cenario_id"]), t.id, date.fromisoformat(d["semana_origem"]), date.fromisoformat(d["semana_destino"]))
    db.commit()
    return {"aulas_criadas": len(criadas)}


@router.get("/alocacoes/{aid}/historico")
def historico_alocacao(aid: int, ctx: Contexto = Depends(requer("alocacoes.ler")), db: Session = Depends(get_db)):
    return [{"em": h.em.isoformat(), "usuario": h.usuario_nome, "acao": h.acao, "antes": h.antes, "depois": h.depois, "motivo": h.motivo}
            for h in db.scalars(select(HistoricoAuditoria).where(HistoricoAuditoria.entidade == "alocacoes", HistoricoAuditoria.entidade_id == str(aid))
                                .order_by(HistoricoAuditoria.em.desc()))]


@router.post("/alocacoes/sugestao/rejeitar")
def rejeitar_sugestao(d: dict = Body(...), ctx: Contexto = Depends(requer("alocacoes.ler")), db: Session = Depends(get_db)):
    """Registra alternativa rejeitada (insumo para aprendizado de preferências)."""
    db.add(RegistroDecisao(tipo="rejeicao", cenario_id=d.get("cenario_id"), usuario_id=ctx.id, motivo=d.get("motivo"), dados=d.get("sugestao") or {}))
    db.commit()
    return {"ok": True}


@router.post("/excecoes")
def autorizar_excecao(d: dict = Body(...), ctx: Contexto = Depends(requer("excecoes.autorizar")), db: Session = Depends(get_db)):
    if d.get("tipo") not in ("feriado_bloqueio", "carga_horaria") or len(d.get("justificativa", "").strip()) < 10:
        raise EntradaInvalida("Informe o tipo (feriado_bloqueio | carga_horaria) e uma justificativa (mín. 10 caracteres).")
    e = ExcecaoAutorizada(tipo=d["tipo"], justificativa=d["justificativa"].strip(), autorizado_por_id=ctx.id)
    db.add(e)
    db.flush()
    auditoria.registrar(db, ctx, "excecao.autorizar", "excecoes_autorizadas", e.id, depois=auditoria.snapshot(e))
    db.commit()
    return auditoria.snapshot(e)


@router.get("/excecoes")
def listar_excecoes(ctx: Contexto = Depends(requer("alocacoes.ler")), db: Session = Depends(get_db)):
    return [auditoria.snapshot(e) for e in db.scalars(select(ExcecaoAutorizada).order_by(ExcecaoAutorizada.id.desc()))]


# ============================================================================ matriz de oferta
@router.get("/planejamento/oferta")
def oferta(cenario_id: int, turma_id: int | None = None, curso_id: int | None = None, detalhar: bool = True,
           ctx: Contexto = Depends(requer("alocacoes.ler")), db: Session = Depends(get_db)):
    q = select(Turma.id).where(Turma.ativo.is_(True), Turma.simulacao_id.is_(None))
    if turma_id:
        q = q.where(Turma.id == turma_id)
    if curso_id:
        q = q.where(Turma.curso_id == curso_id)
    if ctx.unidades is not None:
        q = q.where(Turma.unidade_id.in_(ctx.unidades))
    return matriz_oferta(db, cenario_id, list(db.scalars(q)), detalhar)


# ============================================================================ otimização
@router.get("/otimizacao/criterios")
def criterios(ctx: Contexto = Depends(get_contexto)):
    return descricao_criterios()


@router.get("/otimizacao/parametros")
def listar_parametros(ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)):
    return [auditoria.snapshot(p) for p in db.scalars(select(ParametrosOtimizacao).order_by(ParametrosOtimizacao.id))]


@router.post("/otimizacao/parametros")
def salvar_parametros(d: dict = Body(...), ctx: Contexto = Depends(requer("configuracoes.editar")), db: Session = Depends(get_db)):
    p = db.get(ParametrosOtimizacao, d["id"]) if d.get("id") else None
    antes = auditoria.snapshot(p) if p else None
    pesos = normalizar_pesos(d.get("pesos"))
    if any(v < 0 for v in pesos.values()):
        raise EntradaInvalida("Pesos não podem ser negativos.")
    if p is None:
        p = ParametrosOtimizacao(nome=d["nome"], pesos=pesos, limite_tempo_s=int(d.get("limite_tempo_s", 30)), padrao=bool(d.get("padrao")))
        db.add(p)
    else:
        p.nome, p.pesos, p.limite_tempo_s = d.get("nome", p.nome), pesos, int(d.get("limite_tempo_s", p.limite_tempo_s))
        p.versao += 1
        if "padrao" in d:
            p.padrao = bool(d["padrao"])
    if p.padrao:
        for o in db.scalars(select(ParametrosOtimizacao).where(ParametrosOtimizacao.padrao.is_(True))):
            if o is not p:
                o.padrao = False
    db.flush()
    auditoria.registrar(db, ctx, "pesos.alterar", "parametros_otimizacao", p.id, antes=antes, depois=auditoria.snapshot(p))
    db.commit()
    return auditoria.snapshot(p)


@router.post("/otimizacao/executar")
def executar(d: dict = Body(...), ctx: Contexto = Depends(requer("otimizacao.executar")), db: Session = Depends(get_db)):
    escopo = d.get("escopo") or {"tipo": "instituicao"}
    if escopo.get("tipo") not in ("turma", "curso", "turno", "unidade", "instituicao", "pendentes", "simulacao"):
        raise EntradaInvalida("Escopo inválido.")
    ex = otimizacao.criar_execucao(db, ctx, int(d["cenario_id"]), escopo, d.get("parametros_id"), d.get("pesos"), d.get("limite_tempo_s"),
                                   d.get("modo", "completo"), bool(d.get("aplicar", True)))
    db.commit()
    if d.get("sincrono"):
        otimizacao.executar(ex.id, ctx)
    else:
        otimizacao.submeter(ex.id)
    return {"execucao_id": ex.id}


def _exec_dict(e: ExecucaoOtimizacao, db: Session, completo=False) -> dict:
    d = {k: v for k, v in auditoria.snapshot(e).items() if completo or k not in ("resultado", "diagnosticos")}
    if completo:
        d["pontuacao_por_criterio"] = [auditoria.snapshot(r) for r in db.scalars(select(ResultadoOtimizacao).where(ResultadoOtimizacao.execucao_id == e.id))]
    return d


@router.get("/otimizacao/execucoes")
def listar_execucoes(cenario_id: int | None = None, ctx: Contexto = Depends(requer("alocacoes.ler")), db: Session = Depends(get_db)):
    q = select(ExecucaoOtimizacao).order_by(ExecucaoOtimizacao.id.desc()).limit(100)
    if cenario_id:
        q = q.where(ExecucaoOtimizacao.cenario_id == cenario_id)
    return [_exec_dict(e, db) for e in db.scalars(q)]


@router.get("/otimizacao/execucoes/{eid}")
def obter_execucao(eid: int, ctx: Contexto = Depends(requer("alocacoes.ler")), db: Session = Depends(get_db)):
    e = db.get(ExecucaoOtimizacao, eid)
    if e is None:
        raise NaoEncontrado("Execução não encontrada.")
    return _exec_dict(e, db, completo=True)


_ = (minutos, Query, datetime)
