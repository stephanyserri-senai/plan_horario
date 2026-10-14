"""API genérica de cadastros: consulta paginada com pesquisa e filtros,
inclusão, edição, inativação/reativação, histórico e opções para seleção."""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

from fastapi import APIRouter, Body, Depends, Query, Request
from sqlalchemy import String, cast, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.registro import ENTIDADES, SOMENTE_LEITURA, campos
from app.core.db import get_db
from app.core.deps import Contexto, get_contexto
from app.core.errors import ConflitoConcorrencia, ConflitoValidacao, EntradaInvalida, NaoEncontrado
from app.models import (
    Curso, HistoricoAuditoria, MatrizCurricular, Turma, TurmaUC, UCPrerequisito, UCRecurso, UCTipoAmbiente, Unidade, UnidadeCurricular,
    CompetenciaInstrutor,
)
from app.services import auditoria

router = APIRouter(prefix="/api", tags=["cadastros"])


def _cfg(ent: str) -> dict:
    if ent not in ENTIDADES:
        raise NaoEncontrado(f"Cadastro '{ent}' inexistente.")
    return ENTIDADES[ent]


def serializar(obj, ent: str, ctx: Contexto | None = None) -> dict:
    cfg = ENTIDADES[ent]
    d = auditoria.snapshot(obj)
    for k in cfg.get("ocultar", []):
        d.pop(k, None)
    if ctx is not None and not ctx.pode("dados_pessoais.ler"):
        for k in cfg.get("pessoais", []):
            if k in d:
                d[k] = None
    if ent == "ucs":
        d["tipos_ambiente_ids"] = [t.id for t in obj.tipos_ambiente]
    try:
        d["_rotulo"] = cfg["label"].format(**{k: ("" if v is None else v) for k, v in d.items()})
    except (KeyError, IndexError):
        d["_rotulo"] = str(d.get("id"))
    return d


def converter(ent: str, dados: dict, parcial: bool) -> dict:
    model = ENTIDADES[ent]["model"]
    cols = {c.key: c for c in model.__table__.columns}
    res, erros = {}, []
    for k, v in dados.items():
        if k not in cols or k in SOMENTE_LEITURA or k.startswith("_"):
            continue
        col = cols[k]
        try:
            if v in ("", None):
                v = None
            elif isinstance(col.type, (String,)) or col.type.__class__.__name__ == "Text":
                v = str(v).strip()
            else:
                pt = col.type.python_type
                if pt is bool:
                    v = v if isinstance(v, bool) else str(v).lower() in ("1", "true", "sim", "on")
                elif pt is int:
                    v = int(v)
                elif pt in (float, Decimal):
                    v = float(v)
                elif pt is date:
                    v = date.fromisoformat(str(v)[:10])
                elif pt is datetime:
                    v = datetime.fromisoformat(str(v))
                elif pt is time:
                    v = time.fromisoformat(str(v))
                elif pt is list:
                    v = [int(x) for x in v]
        except (ValueError, TypeError, NotImplementedError):
            erros.append(f"{k}: valor inválido")
            continue
        if v is None and not col.nullable and col.default is None:
            erros.append(f"{k}: obrigatório")
            continue
        res[k] = v
    if not parcial:
        for f in campos(ent):
            # a área é conferida em _regras_especificas (a turma pode herdá-la do curso)
            if f["obrigatorio"] and f["nome"] not in res and f["tipo"] != "multiref" and f["nome"] != "area_id":
                erros.append(f"{f['nome']}: obrigatório")
    if erros:
        raise EntradaInvalida("Dados inválidos: " + "; ".join(erros), detalhes={"erros": erros})
    return res


def _pk(ent: str, id_: str):
    cfg = ENTIDADES[ent]
    if "pk" in cfg:
        partes = id_.split(":")
        model = cfg["model"]
        conv = []
        for nome, p in zip(cfg["pk"], partes):
            conv.append(int(p) if model.__table__.c[nome].type.python_type is int else p)
        return tuple(conv)
    return int(id_)


def _verificar_escopo(ctx: Contexto, ent: str, obj):
    col = ENTIDADES[ent].get("unidade_col")
    if col:
        ctx.exigir_unidade(getattr(obj, col))
    if ent == "turmas" and not ctx.acessa_turma(obj):
        from app.core.errors import AcessoNegado
        raise AcessoNegado("Turma fora do seu escopo de acesso.")


FIXA_MSG = ("As unidades (Beira Mar e Porto) e as áreas tecnológicas são fixas da instituição: não podem ser incluídas, "
            "excluídas, inativadas nem renomeadas pelo sistema.")


def _regras_especificas(db: Session, ent: str, obj, dados: dict, novo: bool):
    """Regras de integridade de negócio dos cadastros."""
    cfg = ENTIDADES[ent]
    if cfg.get("fixa") and novo:
        raise ConflitoValidacao(FIXA_MSG, codigo="ESTRUTURA_FIXA")
    if not novo:
        mudou = [k for k in cfg.get("travados", []) if k in dados and getattr(obj, k) != dados[k]]
        if mudou:
            raise ConflitoValidacao(FIXA_MSG, codigo="ESTRUTURA_FIXA")
    if "area_id" in {c.key for c in cfg["model"].__table__.columns}:
        from app.models import Area
        if ent == "turmas" and novo and not dados.get("area_id"):
            curso = db.get(Curso, dados.get("curso_id") or obj.curso_id) if (dados.get("curso_id") or obj.curso_id) else None
            if curso and curso.area_id:
                obj.area_id = dados["area_id"] = curso.area_id  # turma herda a área do curso
        area_id = dados.get("area_id", obj.area_id)
        if novo and "area_id" in cfg.get("obrigatorios", []) and not area_id:
            raise EntradaInvalida("Informe a área tecnológica (ex.: AUTOMAÇÃO, LOGÍSTICA).")
        if area_id:
            area = db.get(Area, int(area_id))
            if area is None:
                raise EntradaInvalida("Área inexistente.")
            unidade_id = dados.get("unidade_id", obj.unidade_id)
            if ent == "cursos" and not unidade_id:
                obj.unidade_id = dados["unidade_id"] = area.unidade_id  # curso assume a unidade da área
            elif unidade_id and int(unidade_id) != area.unidade_id:
                un = db.get(Unidade, area.unidade_id)
                raise ConflitoValidacao(f"A área {area.nome} pertence à {un.nome if un else 'outra unidade'}; escolha uma área da mesma unidade do cadastro.")
    if ent == "ucs" and not novo:
        em_uso = db.scalar(select(func.count()).select_from(Turma).where(Turma.matriz_id == obj.matriz_id, Turma.simulacao_id.is_(None)))
        estruturais = {"carga_horaria_total", "codigo", "matriz_id", "duracao_bloco_periodos", "ch_teorica", "ch_pratica"}
        if em_uso and estruturais & set(dados) and any(getattr(obj, k) != v for k, v in dados.items() if k in estruturais):
            raise ConflitoValidacao("Esta versão da matriz já é utilizada por turmas. Crie uma nova versão da matriz para alterar a estrutura da UC "
                                    "(alterações retroativas não são permitidas).", codigo="MATRIZ_EM_USO")
    if ent == "turma_ucs" and dados.get("uc_id"):
        turma = db.get(Turma, dados.get("turma_id") or obj.turma_id)
        uc = db.get(UnidadeCurricular, dados["uc_id"])
        if uc and turma and uc.matriz_id != turma.matriz_id:
            raise ConflitoValidacao("A UC não pertence à matriz curricular da turma.")
    if ent == "turmas" and ("matriz_id" in dados or "curso_id" in dados):
        m = db.get(MatrizCurricular, dados.get("matriz_id") or obj.matriz_id)
        if m and m.curso_id != (dados.get("curso_id") or obj.curso_id):
            raise ConflitoValidacao("A matriz curricular informada não pertence ao curso da turma.")
    if ent == "instrutores":
        c = dados.get("carga_horaria_contratual", getattr(obj, "carga_horaria_contratual", None))
        l = dados.get("limite_ch_letiva", getattr(obj, "limite_ch_letiva", None))
        if c is not None and l is not None and float(l) > float(c):
            raise ConflitoValidacao("O limite de carga letiva não pode exceder a carga contratual.")


def _traduzir_integridade(e: IntegrityError):
    msg = str(e.orig)
    if "unique" in msg.lower() or "duplicate key" in msg.lower():
        raise ConflitoValidacao("Já existe um registro com estes identificadores (duplicidade).", detalhes={"banco": msg.split("DETAIL:")[-1].strip()[:300]})
    if "foreign key" in msg.lower():
        raise ConflitoValidacao("Referência inválida ou registro em uso por outros cadastros.", detalhes={"banco": msg.split("DETAIL:")[-1].strip()[:300]})
    if "check constraint" in msg.lower():
        raise ConflitoValidacao("Valores violam uma regra de integridade do cadastro.", detalhes={"banco": msg[:300]})
    raise e


@router.get("/meta/entidades")
def meta(ctx: Contexto = Depends(get_contexto)):
    return [{"chave": k, "rotulo": c["rotulo"], "grupo": c["grupo"], "campos": campos(k), "busca": c["busca"],
             "inativavel": hasattr(c["model"], "ativo") and not c.get("fixa"), "fixa": bool(c.get("fixa")), "pk": c.get("pk", ["id"])}
            for k, c in ENTIDADES.items()]


@router.get("/cadastros/{ent}")
def listar(ent: str, request: Request, q: str | None = None, pagina: int = 1, por_pagina: int = Query(25, le=500), ativo: bool | None = None,
           ordenar: str | None = None, db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    ctx.exigir("cadastros.ler")
    cfg = _cfg(ent)
    M = cfg["model"]
    stmt = select(M)
    if hasattr(M, "simulacao_id"):
        stmt = stmt.where(M.simulacao_id.is_(None))
    if ativo is not None and hasattr(M, "ativo"):
        stmt = stmt.where(M.ativo.is_(ativo))
    col_un = cfg.get("unidade_col")
    if col_un and ctx.unidades is not None:
        stmt = stmt.where(or_(getattr(M, col_un).in_(ctx.unidades), getattr(M, col_un).is_(None)))
    if ent == "turmas":
        if ctx.cursos is not None:
            stmt = stmt.where(M.curso_id.in_(ctx.cursos))
        if ctx.turmas is not None:
            stmt = stmt.where(M.id.in_(ctx.turmas))
    if q and cfg["busca"]:
        stmt = stmt.where(or_(*[cast(getattr(M, c), String).ilike(f"%{q}%") for c in cfg["busca"]]))
    # filtros combináveis: ?campo=valor (igualdade) para qualquer coluna
    cols = {c.key: c for c in M.__table__.columns}
    for k, v in request.query_params.items():
        if k in cols and v != "":
            col = cols[k]
            try:
                pt = col.type.python_type
                if pt is bool:
                    stmt = stmt.where(col == (v.lower() in ("1", "true", "sim")))
                elif pt is list:
                    stmt = stmt.where(col.any(int(v)))
                else:
                    stmt = stmt.where(col == (pt(v) if pt in (int, float) else (date.fromisoformat(v) if pt is date else v)))
            except (ValueError, NotImplementedError):
                raise EntradaInvalida(f"Filtro inválido: {k}={v}")
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    if ordenar:
        desc = ordenar.startswith("-")
        nome = ordenar.lstrip("-")
        if nome in cols:
            stmt = stmt.order_by(cols[nome].desc() if desc else cols[nome])
    else:
        pkcols = list(M.__table__.primary_key.columns)
        stmt = stmt.order_by(*pkcols)
    itens = db.scalars(stmt.offset((pagina - 1) * por_pagina).limit(por_pagina)).all()
    return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "itens": [serializar(o, ent, ctx) for o in itens]}


@router.get("/cadastros/{ent}/opcoes")
def opcoes(ent: str, q: str | None = None, limite: int = 500, db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    ctx.exigir("cadastros.ler")
    cfg = _cfg(ent)
    M = cfg["model"]
    stmt = select(M)
    if hasattr(M, "ativo"):
        stmt = stmt.where(M.ativo.is_(True))
    if hasattr(M, "simulacao_id"):
        stmt = stmt.where(M.simulacao_id.is_(None))
    if q and cfg["busca"]:
        stmt = stmt.where(or_(*[cast(getattr(M, c), String).ilike(f"%{q}%") for c in cfg["busca"]]))
    res = []
    for o in db.scalars(stmt.limit(limite)):
        s = serializar(o, ent, ctx)
        item = {"id": s.get("id"), "rotulo": s["_rotulo"]}
        if "unidade_id" in s:
            item["unidade_id"] = s["unidade_id"]
        if "area_id" in s:
            item["area_id"] = s["area_id"]
        res.append(item)
    return res


@router.get("/cadastros/{ent}/{id_}")
def obter(ent: str, id_: str, db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    ctx.exigir("cadastros.ler")
    obj = db.get(_cfg(ent)["model"], _pk(ent, id_))
    if obj is None:
        raise NaoEncontrado("Registro não encontrado.")
    _verificar_escopo(ctx, ent, obj)
    return serializar(obj, ent, ctx)


def _aplicar_extras(db: Session, ent: str, obj, dados: dict):
    if ent == "ucs" and "tipos_ambiente_ids" in dados and dados["tipos_ambiente_ids"] is not None:
        db.execute(delete(UCTipoAmbiente).where(UCTipoAmbiente.uc_id == obj.id))
        for tid in dados["tipos_ambiente_ids"]:
            db.add(UCTipoAmbiente(uc_id=obj.id, tipo_ambiente_id=int(tid)))
        db.flush()
        db.refresh(obj)


@router.post("/cadastros/{ent}")
def criar(ent: str, dados: dict = Body(...), db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    ctx.exigir("cadastros.editar")
    cfg = _cfg(ent)
    vals = converter(ent, dados, parcial=False)
    obj = cfg["model"](**vals)
    _verificar_escopo(ctx, ent, obj)
    _regras_especificas(db, ent, obj, vals, novo=True)
    try:
        db.add(obj)
        db.flush()
        _aplicar_extras(db, ent, obj, dados)
        if ent == "turmas" and dados.get("criar_ofertas", True):
            for uc in db.scalars(select(UnidadeCurricular).where(UnidadeCurricular.matriz_id == obj.matriz_id, UnidadeCurricular.ativo.is_(True))):
                db.add(TurmaUC(turma_id=obj.id, uc_id=uc.id, situacao="prevista"))
            db.flush()
        auditoria.registrar(db, ctx, "cadastro.criar", cfg["model"].__tablename__, getattr(obj, "id", None), depois=auditoria.snapshot(obj))
        db.commit()
    except IntegrityError as e:
        db.rollback()
        _traduzir_integridade(e)
    return serializar(obj, ent, ctx)


@router.put("/cadastros/{ent}/{id_}")
def atualizar(ent: str, id_: str, dados: dict = Body(...), db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    ctx.exigir("cadastros.editar")
    cfg = _cfg(ent)
    obj = db.get(cfg["model"], _pk(ent, id_), with_for_update=True)
    if obj is None:
        raise NaoEncontrado("Registro não encontrado.")
    _verificar_escopo(ctx, ent, obj)
    # controle otimista: se o cliente enviar atualizado_em, ele deve coincidir
    if dados.get("atualizado_em") and hasattr(obj, "atualizado_em") and obj.atualizado_em and \
            str(obj.atualizado_em.isoformat())[:19] != str(dados["atualizado_em"])[:19]:
        raise ConflitoConcorrencia("Este registro foi alterado por outro usuário. Recarregue antes de salvar.")
    vals = converter(ent, dados, parcial=True)
    _regras_especificas(db, ent, obj, vals, novo=False)
    antes = auditoria.snapshot(obj)
    for k, v in vals.items():
        setattr(obj, k, v)
    _verificar_escopo(ctx, ent, obj)
    try:
        db.flush()
        _aplicar_extras(db, ent, obj, dados)
        auditoria.registrar(db, ctx, "cadastro.alterar", cfg["model"].__tablename__, getattr(obj, "id", id_), antes=antes,
                            depois=auditoria.snapshot(obj), motivo=dados.get("_motivo"))
        db.commit()
    except IntegrityError as e:
        db.rollback()
        _traduzir_integridade(e)
    return serializar(obj, ent, ctx)


@router.post("/cadastros/{ent}/{id_}/inativar")
def inativar(ent: str, id_: str, dados: dict = Body(default={}), db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    return _ativo(ent, id_, False, dados.get("motivo"), db, ctx)


@router.post("/cadastros/{ent}/{id_}/reativar")
def reativar(ent: str, id_: str, dados: dict = Body(default={}), db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    return _ativo(ent, id_, True, dados.get("motivo"), db, ctx)


def _ativo(ent, id_, valor, motivo, db, ctx):
    ctx.exigir("cadastros.editar")
    cfg = _cfg(ent)
    if cfg.get("fixa"):
        raise ConflitoValidacao(FIXA_MSG, codigo="ESTRUTURA_FIXA")
    obj = db.get(cfg["model"], _pk(ent, id_))
    if obj is None or not hasattr(obj, "ativo"):
        raise NaoEncontrado("Registro não encontrado ou não inativável.")
    _verificar_escopo(ctx, ent, obj)
    obj.ativo = valor
    auditoria.registrar(db, ctx, "cadastro.reativar" if valor else "cadastro.inativar", cfg["model"].__tablename__, getattr(obj, "id", id_),
                        depois={"ativo": valor}, motivo=motivo)
    db.commit()
    return serializar(obj, ent, ctx)


@router.delete("/cadastros/{ent}/{id_}")
def excluir(ent: str, id_: str, db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    """Exclusão física apenas para vínculos e registros sem histórico próprio
    (cadastros principais são inativados)."""
    ctx.exigir("cadastros.editar")
    cfg = _cfg(ent)
    M = cfg["model"]
    if cfg.get("fixa"):
        raise ConflitoValidacao(FIXA_MSG, codigo="ESTRUTURA_FIXA")
    if hasattr(M, "ativo") and ent not in ("disponibilidade_ambientes", "disponibilidade_instrutores", "calendario_excecoes", "bloqueios",
                                          "competencias", "habilitacoes", "periodos", "horarios_funcionamento", "deslocamentos"):
        raise ConflitoValidacao("Cadastros principais não são excluídos: utilize a inativação para preservar o histórico.")
    obj = db.get(M, _pk(ent, id_))
    if obj is None:
        raise NaoEncontrado("Registro não encontrado.")
    _verificar_escopo(ctx, ent, obj)
    antes = auditoria.snapshot(obj)
    try:
        db.delete(obj)
        db.flush()
        auditoria.registrar(db, ctx, "cadastro.excluir", M.__tablename__, id_, antes=antes)
        db.commit()
    except IntegrityError as e:
        db.rollback()
        _traduzir_integridade(e)
    return {"ok": True}


@router.get("/cadastros/{ent}/{id_}/historico")
def historico(ent: str, id_: str, db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    ctx.exigir("cadastros.ler")
    M = _cfg(ent)["model"]
    linhas = db.scalars(select(HistoricoAuditoria).where(HistoricoAuditoria.entidade == M.__tablename__, HistoricoAuditoria.entidade_id == str(id_))
                        .order_by(HistoricoAuditoria.em.desc()).limit(200)).all()
    return [{"id": h.id, "em": h.em.isoformat(), "usuario": h.usuario_nome, "acao": h.acao, "antes": h.antes, "depois": h.depois, "motivo": h.motivo,
             "origem": h.origem} for h in linhas]


@router.post("/cadastros/turmas/{id_}/duplicar")
def duplicar_turma(id_: int, dados: dict = Body(...), db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    ctx.exigir("cadastros.editar")
    t = db.get(Turma, id_)
    if t is None:
        raise NaoEncontrado("Turma não encontrada.")
    _verificar_escopo(ctx, "turmas", t)
    base = {k: v for k, v in auditoria.snapshot(t).items() if k not in ("id", "criado_em", "atualizado_em", "simulacao_id")}
    base.update({"codigo": dados["codigo"], "nome": dados.get("nome") or f"{t.nome} (cópia)", "situacao": "planejada"})
    vals = converter("turmas", {**base, **{k: v for k, v in dados.items() if k not in ("codigo", "nome")}}, parcial=False)
    nova = Turma(**vals)
    try:
        db.add(nova)
        db.flush()
        for tuc in db.scalars(select(TurmaUC).where(TurmaUC.turma_id == t.id)):
            db.add(TurmaUC(turma_id=nova.id, uc_id=tuc.uc_id, situacao="prevista"))
        auditoria.registrar(db, ctx, "cadastro.duplicar", "turmas", nova.id, depois={"origem": t.id, **auditoria.snapshot(nova)})
        db.commit()
    except IntegrityError as e:
        db.rollback()
        _traduzir_integridade(e)
    return serializar(nova, "turmas", ctx)


@router.post("/cadastros/matrizes/{id_}/nova_versao")
def nova_versao_matriz(id_: int, dados: dict = Body(...), db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    """Cria nova versão copiando UCs, tipos de ambiente, equipamentos,
    pré-requisitos e competências. A versão antiga permanece intacta."""
    ctx.exigir("cadastros.editar")
    m = db.get(MatrizCurricular, id_)
    if m is None:
        raise NaoEncontrado("Matriz não encontrada.")
    nova = MatrizCurricular(curso_id=m.curso_id, versao=dados["versao"], vigencia_inicio=dados.get("vigencia_inicio"), situacao="rascunho", matriz_origem_id=m.id)
    try:
        db.add(nova)
        db.flush()
        mapa = {}
        for uc in db.scalars(select(UnidadeCurricular).where(UnidadeCurricular.matriz_id == m.id)):
            snap = {k: v for k, v in auditoria.snapshot(uc).items() if k not in ("id", "criado_em", "atualizado_em")}
            snap["matriz_id"] = nova.id
            nu = UnidadeCurricular(**{k: v for k, v in snap.items() if k in UnidadeCurricular.__table__.c})
            db.add(nu)
            db.flush()
            mapa[uc.id] = nu.id
            for t in uc.tipos_ambiente:
                db.add(UCTipoAmbiente(uc_id=nu.id, tipo_ambiente_id=t.id))
            for r in db.scalars(select(UCRecurso).where(UCRecurso.uc_id == uc.id)):
                db.add(UCRecurso(uc_id=nu.id, recurso_tipo=r.recurso_tipo, quantidade=r.quantidade))
            for c in db.scalars(select(CompetenciaInstrutor).where(CompetenciaInstrutor.uc_id == uc.id)):
                db.add(CompetenciaInstrutor(instrutor_id=c.instrutor_id, uc_id=nu.id, nivel=c.nivel, condicoes=c.condicoes, valido_ate=c.valido_ate))
        for p in db.scalars(select(UCPrerequisito).where(UCPrerequisito.uc_id.in_(list(mapa)))):
            db.add(UCPrerequisito(uc_id=mapa[p.uc_id], prerequisito_id=mapa.get(p.prerequisito_id, p.prerequisito_id)))
        auditoria.registrar(db, ctx, "matriz.nova_versao", "matrizes_curriculares", nova.id, depois={"origem": m.id, "versao": nova.versao, "ucs": len(mapa)})
        db.commit()
    except IntegrityError as e:
        db.rollback()
        _traduzir_integridade(e)
    return serializar(nova, "matrizes", ctx)


@router.post("/unidades/{uid}/turnos-padrao")
def criar_turnos_padrao(uid: int, ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)):
    """Cria os turnos da instituição (manhã, tarde e noite, 4 aulas cada) numa unidade que ainda não tem turnos.
    Não altera nem apaga turnos existentes."""
    from app.models import PeriodoHorario, Turno, Unidade
    from app.services.regras_aula import TURNOS_PADRAO
    ctx.exigir("cadastros.editar")
    un = db.get(Unidade, uid)
    if un is None:
        raise NaoEncontrado("Unidade inexistente.")
    if ctx.unidades is not None and uid not in ctx.unidades:
        raise EntradaInvalida("Unidade fora do seu escopo de acesso.")
    if db.scalar(select(func.count()).select_from(Turno).where(Turno.unidade_id == uid)):
        raise EntradaInvalida("Esta unidade já possui turnos cadastrados; ajuste-os em Cadastros → Turnos e horários.")
    hm = lambda m: time(m // 60, m % 60)  # noqa: E731
    criados = []
    for ordem, (cod, nome, aulas) in enumerate(TURNOS_PADRAO, 1):
        t = Turno(unidade_id=uid, codigo=cod, nome=nome, hora_inicio=hm(aulas[0][0]), hora_fim=hm(aulas[-1][0] + aulas[-1][1]), ordem=ordem)
        db.add(t)
        db.flush()
        for i, (ini, dur) in enumerate(aulas, 1):
            db.add(PeriodoHorario(unidade_id=uid, turno_id=t.id, ordem=i, hora_inicio=hm(ini), hora_fim=hm(ini + dur), dias_semana=[0, 1, 2, 3, 4]))
        criados.append(nome)
        auditoria.registrar(db, ctx, "turno.criar_padrao", "turnos", t.id, depois=auditoria.snapshot(t))
    db.commit()
    return {"criados": criados, "mensagem": "Turnos criados: manhã (07:30–11:30), tarde (13:30–17:30) e noite (18:20–21:50), com 4 aulas cada e intervalo no meio."}
