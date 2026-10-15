"""Portal do instrutor e observações dos instrutores.

O usuário com perfil "instrutor" fica ligado a um cadastro de instrutor (usuarios.instrutor_id)
e só enxerga a si mesmo: atualiza áreas adicionais, UCs que ministra, disponibilidade,
certificações e formação (gravados direto no cadastro de instrutores), vê as turmas/UCs e
os horários atribuídos a ele e envia observações sobre cada turma × UC para a coordenação.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

from fastapi import APIRouter, Body, Depends
from fastapi.responses import Response
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.cadastros import _dados_instrutor, _gravar_instrutor, gravar_outras_areas, listar_ucs_por_area
from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import Contexto, get_contexto, requer
from app.core.errors import AcessoNegado, ConflitoValidacao, EntradaInvalida, NaoEncontrado
from app.core.security import hash_senha
from app.models import (Alocacao, Ambiente, Area, CenarioPlanejamento, CompetenciaInstrutor, HabilitacaoInstrutor, Instrutor, InstrutorArea,
                        Notificacao, ObservacaoInstrutor, Turma, TurmaUC, Turno, Unidade, UnidadeCurricular, Usuario)
from app.services import auditoria

router = APIRouter(prefix="/api", tags=["portal do instrutor"])

DIAS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
TIPOS_OBS = {"sugestao": "Sugestão", "dificuldade": "Dificuldade", "recurso": "Recurso ou material", "horario": "Horário", "outro": "Outro"}


def _meu_instrutor(ctx: Contexto, db: Session) -> Instrutor:
    ctx.exigir("portal.instrutor")
    iid = getattr(ctx.usuario, "instrutor_id", None)
    inst = db.get(Instrutor, iid) if iid else None
    if inst is None or not inst.ativo:
        raise AcessoNegado("Seu usuário ainda não está ligado a um cadastro de instrutor ativo. Peça à coordenação para liberar o seu acesso.",
                           codigo="SEM_VINCULO_INSTRUTOR")
    return inst


def _areas_ids(db: Session, inst: Instrutor) -> list[int]:
    return sorted(db.scalars(select(InstrutorArea.area_id).where(InstrutorArea.instrutor_id == inst.id)).all())


# ============================================================================ meus dados
def _eu(db: Session, inst: Instrutor) -> dict:
    un = db.get(Unidade, inst.unidade_id)
    principal = db.get(Area, inst.area_id) if inst.area_id else None
    turnos = db.scalars(select(Turno).where(Turno.unidade_id == inst.unidade_id, Turno.ativo.is_(True)).order_by(Turno.hora_inicio)).all()
    certs = db.scalars(select(HabilitacaoInstrutor.nome).where(HabilitacaoInstrutor.instrutor_id == inst.id, HabilitacaoInstrutor.ativo.is_(True))
                       .order_by(HabilitacaoInstrutor.nome)).all()
    return {
        "id": inst.id, "nome": inst.nome, "matricula": inst.matricula, "email": inst.email,
        "unidade": un.nome if un else None, "unidade_id": inst.unidade_id,
        "area_principal": {"id": principal.id, "nome": principal.nome} if principal else None,
        "todas_areas": inst.todas_areas, "areas_ids": _areas_ids(db, inst),
        "areas_unidade": [{"id": a.id, "nome": a.nome} for a in db.scalars(select(Area).where(Area.unidade_id == inst.unidade_id, Area.ativo.is_(True))
                                                                          .order_by(Area.nome))],
        "carga_horaria_contratual": float(inst.carga_horaria_contratual), "max_horas_dia": float(inst.max_horas_dia),
        "limite_ch_letiva": float(inst.limite_ch_letiva),
        "turnos": [{"id": t.id, "nome": t.nome, "inicio": t.hora_inicio.strftime("%H:%M"), "fim": t.hora_fim.strftime("%H:%M")} for t in turnos],
        "certificacoes": list(certs), "formacao": inst.areas_competencia,
        "atualizado_pelo_instrutor_em": inst.atualizado_pelo_instrutor_em.isoformat() if inst.atualizado_pelo_instrutor_em else None,
        "notificacoes_novas": db.scalar(select(func.count()).select_from(Notificacao).where(Notificacao.instrutor_id == inst.id,
                                                                                          Notificacao.lida.is_(False))) or 0,
        **_dados_instrutor(db, inst),
    }


@router.get("/portal/eu")
def meus_dados(ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)):
    return _eu(db, _meu_instrutor(ctx, db))


@router.get("/portal/ucs")
def minhas_ucs_possiveis(areas: str = "", ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)):
    """UCs dos cursos da área principal e das áreas marcadas (só da unidade do instrutor)."""
    inst = _meu_instrutor(ctx, db)
    da_unidade = set(db.scalars(select(Area.id).where(Area.unidade_id == inst.unidade_id)))
    ids = {inst.area_id} | {int(x) for x in areas.split(",") if x.strip()} if areas else {inst.area_id, *_areas_ids(db, inst)}
    return listar_ucs_por_area(db, sorted(i for i in ids if i in da_unidade), inst.unidade_id, inst.todas_areas)


@router.put("/portal/eu")
def atualizar_meus_dados(dados: dict = Body(...), ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)):
    """Grava direto no cadastro do instrutor (fica no histórico como alteração feita pelo próprio instrutor)."""
    inst = _meu_instrutor(ctx, db)
    antes = {**_dados_instrutor(db, inst), "areas_ids": _areas_ids(db, inst), "formacao": inst.areas_competencia}
    if dados.get("areas_ids") is not None:
        gravar_outras_areas(db, "instrutores", inst, dados["areas_ids"])
    if dados.get("ucs_competencia") is not None:
        # só UCs das áreas dele (ou que ele já tinha): a área principal é definida pela coordenação
        areas = [inst.area_id, *_areas_ids(db, inst)]
        permitidas = {u["id"] for g in listar_ucs_por_area(db, [a for a in areas if a], inst.unidade_id, inst.todas_areas) for u in g["ucs"]}
        permitidas |= set(db.scalars(select(CompetenciaInstrutor.uc_id).where(CompetenciaInstrutor.instrutor_id == inst.id,
                                                                              CompetenciaInstrutor.ativo.is_(True))))
        fora = [x for x in dados["ucs_competencia"] if int(x.get("uc_id") or 0) not in permitidas]
        if fora:
            raise ConflitoValidacao("Há UCs fora das suas áreas. Marque a área correspondente ou fale com a coordenação.")
    _gravar_instrutor(db, inst, {k: dados.get(k) for k in ("ucs_competencia", "jornada", "disp_turnos", "disp_dias")})
    if dados.get("certificacoes") is not None:
        quer = {str(c).strip(): None for c in dados["certificacoes"] if str(c).strip()}
        atuais = {h.nome.lower(): h for h in db.scalars(select(HabilitacaoInstrutor).where(HabilitacaoInstrutor.instrutor_id == inst.id))}
        for nome_l, h in atuais.items():
            h.ativo = nome_l in {q.lower() for q in quer}
        for nome in quer:
            if nome.lower() not in atuais:
                db.add(HabilitacaoInstrutor(instrutor_id=inst.id, nome=nome[:200], ativo=True))
    if "formacao" in dados:
        inst.areas_competencia = (str(dados["formacao"] or "").strip() or None)
    inst.atualizado_pelo_instrutor_em = datetime.now()
    db.flush()
    depois = {**_dados_instrutor(db, inst), "areas_ids": _areas_ids(db, inst), "formacao": inst.areas_competencia}
    auditoria.registrar(db, ctx, "portal.atualizar_dados", "instrutores", inst.id, antes=antes, depois=depois, origem="portal")
    db.commit()
    return _eu(db, inst)


# ============================================================================ minhas turmas e horários
def _semestre(c: CenarioPlanejamento, aulas: list[Alocacao]) -> str:
    d = c.periodo_inicio or min(a.data for a in aulas)
    return f"{d.year}/{1 if d.month <= 6 else 2}"


def _cenarios_do_instrutor(db: Session, inst: Instrutor) -> dict[str, tuple[CenarioPlanejamento, list[Alocacao]]]:
    """Por semestre: a versão publicada; se ainda não houver, a versão mais recente em planejamento."""
    q = (select(Alocacao).join(CenarioPlanejamento, CenarioPlanejamento.id == Alocacao.cenario_id)
         .where(Alocacao.instrutor_id == inst.id, Alocacao.status != "cancelada", CenarioPlanejamento.tipo != "simulacao",
                CenarioPlanejamento.estado != "arquivado"))
    por_cen = defaultdict(list)
    for a in db.scalars(q):
        por_cen[a.cenario_id].append(a)
    por_sem: dict[str, list[tuple[CenarioPlanejamento, list[Alocacao]]]] = defaultdict(list)
    for cid, aulas in por_cen.items():
        c = db.get(CenarioPlanejamento, cid)
        por_sem[_semestre(c, aulas)].append((c, aulas))
    return {s: max(op, key=lambda x: (x[0].estado == "publicado", x[0].id)) for s, op in por_sem.items()}


@router.get("/portal/turmas")
def minhas_turmas(ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)):
    inst = _meu_instrutor(ctx, db)
    res = []
    obs_por_tuc = defaultdict(int)
    for tuc_id, n in db.execute(select(ObservacaoInstrutor.turma_uc_id, func.count()).where(ObservacaoInstrutor.instrutor_id == inst.id)
                                .group_by(ObservacaoInstrutor.turma_uc_id)):
        obs_por_tuc[tuc_id] = n
    for sem, (cen, aulas) in sorted(_cenarios_do_instrutor(db, inst).items(), reverse=True):
        turmas = {t.id: t for t in db.scalars(select(Turma).where(Turma.id.in_({a.turma_id for a in aulas})))}
        ucs = {u.id: u for u in db.scalars(select(UnidadeCurricular).where(UnidadeCurricular.id.in_({a.uc_id for a in aulas})))}
        salas = {s.id: s for s in db.scalars(select(Ambiente).where(Ambiente.id.in_({a.ambiente_id for a in aulas if a.ambiente_id})))}
        turnos = {t.id: t.nome for t in db.scalars(select(Turno))}
        ids_tit = {a.instrutor_titular_id for a in aulas if a.instrutor_titular_id}
        titulares = {x.id: x.nome for x in db.scalars(select(Instrutor).where(Instrutor.id.in_(ids_tit)))} if ids_tit else {}
        grupos = defaultdict(list)
        for a in aulas:
            grupos[a.turma_uc_id].append(a)
        itens = []
        for tuc_id, lista in grupos.items():
            t, u = turmas[lista[0].turma_id], ucs[lista[0].uc_id]
            por_dia = defaultdict(list)
            for a in lista:
                por_dia[a.data].append(a)
            padroes = sorted({(d.weekday(), min(x.inicio for x in xs).strftime("%H:%M"), max(x.fim for x in xs).strftime("%H:%M")) for d, xs in por_dia.items()})
            itens.append({
                "turma_uc_id": tuc_id, "turma_codigo": t.codigo, "turma_nome": t.nome, "turno": turnos.get(t.turno_id), "qtd_alunos": t.qtd_alunos,
                "uc_codigo": u.codigo, "uc_nome": u.nome, "ch_uc": u.carga_horaria_total, "horas_suas": round(sum(a.minutos_aula for a in lista) / 60, 1),
                "dias_de_aula": len(por_dia), "primeira": min(por_dia).isoformat(), "ultima": max(por_dia).isoformat(),
                "horarios": [f"{DIAS[d]} {i}–{f}" for d, i, f in padroes],
                "salas": sorted({salas[a.ambiente_id].nome for a in lista if a.ambiente_id in salas}),
                "observacoes": obs_por_tuc.get(tuc_id, 0),
                "substituindo": sorted({titulares[a.instrutor_titular_id] for a in lista if a.instrutor_titular_id in titulares}),
                "dias_substituicao": sorted({a.data.isoformat() for a in lista if a.instrutor_titular_id}),
            })
        itens.sort(key=lambda x: (x["primeira"], x["turma_codigo"]))
        res.append({
            "semestre": sem, "cenario_id": cen.id, "cenario": cen.nome, "estado": cen.estado, "publicado": cen.estado == "publicado",
            "inicio": (cen.periodo_inicio or min(a.data for a in aulas)).isoformat(), "fim": (cen.periodo_fim or max(a.data for a in aulas)).isoformat(),
            "turmas_ucs": itens,
            "aulas": [{"data": a.data.isoformat(), "inicio": a.inicio.strftime("%H:%M"), "fim": a.fim.strftime("%H:%M"),
                       "turma": turmas[a.turma_id].codigo, "uc": ucs[a.uc_id].codigo, "uc_nome": ucs[a.uc_id].nome,
                       "sala": salas[a.ambiente_id].nome if a.ambiente_id in salas else None, "turno": turnos.get(turmas[a.turma_id].turno_id),
                       "substituindo": titulares.get(a.instrutor_titular_id)}
                      for a in sorted(aulas, key=lambda a: a.inicio)],
        })
    return res


@router.get("/portal/agenda")
def minha_agenda_xlsx(cenario_id: int, ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)):
    inst = _meu_instrutor(ctx, db)
    if cenario_id not in {c.id for c, _ in _cenarios_do_instrutor(db, inst).values()}:
        raise NaoEncontrado("Semestre não encontrado na sua agenda.")
    from app.services import exportacao_planilhas, indicadores
    d0, d1 = indicadores.periodo_padrao(db, db.get(CenarioPlanejamento, cenario_id))
    arq = exportacao_planilhas.agenda_instrutores(db, cenario_id, d0, d1, instrutor_id=inst.id)
    return Response(arq, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="minha_agenda.xlsx"'})


# ============================================================================ notificações
@router.get("/portal/notificacoes")
def minhas_notificacoes(ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)):
    inst = _meu_instrutor(ctx, db)
    return [{"id": n.id, "tipo": n.tipo, "titulo": n.titulo, "texto": n.texto, "aba": n.aba, "lida": n.lida, "criado_em": n.criado_em.isoformat()}
            for n in db.scalars(select(Notificacao).where(Notificacao.instrutor_id == inst.id)
                                .order_by(Notificacao.criado_em.desc(), Notificacao.id.desc()).limit(200))]


@router.post("/portal/notificacoes/lidas")
def marcar_lidas(dados: dict = Body(default={}), ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)):
    """Marca como lidas as notificações informadas (ou todas, sem `ids`)."""
    inst = _meu_instrutor(ctx, db)
    q = select(Notificacao).where(Notificacao.instrutor_id == inst.id, Notificacao.lida.is_(False))
    if dados.get("ids"):
        q = q.where(Notificacao.id.in_([int(x) for x in dados["ids"]]))
    n = 0
    for x in db.scalars(q):
        x.lida, n = True, n + 1
    db.commit()
    return {"marcadas": n}


# ============================================================================ observações
def _obs(db: Session, o: ObservacaoInstrutor, com_instrutor: bool = False) -> dict:
    tuc = db.get(TurmaUC, o.turma_uc_id) if o.turma_uc_id else None
    t = db.get(Turma, tuc.turma_id) if tuc else None
    u = db.get(UnidadeCurricular, tuc.uc_id) if tuc else None
    resp = db.get(Usuario, o.respondido_por_id) if o.respondido_por_id else None
    d = {"id": o.id, "turma_uc_id": o.turma_uc_id, "turma": t.codigo if t else None, "turma_nome": t.nome if t else None,
         "uc": f"{u.codigo} – {u.nome}" if u else None, "tipo": o.tipo, "tipo_rotulo": TIPOS_OBS.get(o.tipo, o.tipo), "texto": o.texto,
         "status": o.status, "resposta": o.resposta, "respondido_por": resp.nome if resp else None,
         "respondido_em": o.respondido_em.isoformat() if o.respondido_em else None, "criado_em": o.criado_em.isoformat() if o.criado_em else None}
    if com_instrutor:
        i = db.get(Instrutor, o.instrutor_id)
        d.update({"instrutor_id": o.instrutor_id, "instrutor": i.nome if i else None})
    return d


@router.get("/portal/observacoes")
def minhas_observacoes(ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)):
    inst = _meu_instrutor(ctx, db)
    return [_obs(db, o) for o in db.scalars(select(ObservacaoInstrutor).where(ObservacaoInstrutor.instrutor_id == inst.id)
                                            .order_by(ObservacaoInstrutor.criado_em.desc(), ObservacaoInstrutor.id.desc()))]


@router.post("/portal/observacoes")
def enviar_observacao(dados: dict = Body(...), ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)):
    inst = _meu_instrutor(ctx, db)
    texto = str(dados.get("texto") or "").strip()
    if len(texto) < 3:
        raise EntradaInvalida("Escreva a observação.")
    if len(texto) > 3000:
        raise EntradaInvalida("A observação pode ter até 3000 caracteres.")
    tipo = dados.get("tipo") or "sugestao"
    if tipo not in TIPOS_OBS:
        raise EntradaInvalida("Tipo de observação inválido.")
    tuc_id = int(dados.get("turma_uc_id") or 0) or None
    if tuc_id:
        # só sobre turmas × UCs atribuídas a ele (em alguma versão da grade) ou em que é o instrutor preferido
        atribuida = db.scalar(select(func.count()).select_from(Alocacao).where(Alocacao.turma_uc_id == tuc_id, Alocacao.instrutor_id == inst.id))
        tuc = db.get(TurmaUC, tuc_id)
        if not atribuida and not (tuc and tuc.instrutor_preferido_id == inst.id):
            raise AcessoNegado("Você só pode comentar turmas e UCs atribuídas a você.")
    o = ObservacaoInstrutor(instrutor_id=inst.id, turma_uc_id=tuc_id, tipo=tipo, texto=texto, status="nova")
    db.add(o)
    db.flush()
    auditoria.registrar(db, ctx, "portal.observacao", "observacoes_instrutor", o.id, depois={"turma_uc_id": tuc_id, "tipo": tipo}, origem="portal")
    db.commit()
    return _obs(db, o)


@router.get("/observacoes-instrutores")
def listar_observacoes(status: str | None = None, instrutor_id: int | None = None, ctx: Contexto = Depends(requer("observacoes.gerenciar")),
                       db: Session = Depends(get_db)):
    q = select(ObservacaoInstrutor).join(Instrutor, Instrutor.id == ObservacaoInstrutor.instrutor_id)
    if ctx.unidades is not None:
        q = q.where(Instrutor.unidade_id.in_(ctx.unidades or [-1]))
    if status:
        q = q.where(ObservacaoInstrutor.status == status)
    if instrutor_id:
        q = q.where(ObservacaoInstrutor.instrutor_id == instrutor_id)
    ordem = {"nova": 0, "lida": 1, "resolvida": 2}
    lista = [_obs(db, o, True) for o in db.scalars(q.order_by(ObservacaoInstrutor.criado_em.desc(), ObservacaoInstrutor.id.desc()).limit(500))]
    return sorted(lista, key=lambda o: ordem.get(o["status"], 9))


def contar_novas(db: Session, unidades=None) -> int:
    q = select(func.count()).select_from(ObservacaoInstrutor).join(Instrutor, Instrutor.id == ObservacaoInstrutor.instrutor_id) \
        .where(ObservacaoInstrutor.status == "nova")
    if unidades is not None:
        q = q.where(Instrutor.unidade_id.in_(unidades or [-1]))
    return db.scalar(q) or 0


@router.put("/observacoes-instrutores/{oid}")
def responder_observacao(oid: int, dados: dict = Body(...), ctx: Contexto = Depends(requer("observacoes.gerenciar")), db: Session = Depends(get_db)):
    o = db.get(ObservacaoInstrutor, oid)
    if o is None:
        raise NaoEncontrado("Observação não encontrada.")
    inst = db.get(Instrutor, o.instrutor_id)
    ctx.exigir_unidade(inst.unidade_id)
    antes = {"status": o.status, "resposta": o.resposta}
    if "status" in dados:
        if dados["status"] not in ("nova", "lida", "resolvida"):
            raise EntradaInvalida("Situação inválida (nova, lida, resolvida).")
        o.status = dados["status"]
    if dados.get("resposta") is not None and str(dados["resposta"]).strip() != (o.resposta or ""):
        o.resposta = str(dados["resposta"]).strip() or None
        o.respondido_por_id, o.respondido_em = ctx.id, datetime.now()
        if o.status == "nova":
            o.status = "lida"
    auditoria.registrar(db, ctx, "observacao.responder", "observacoes_instrutor", o.id, antes=antes, depois={"status": o.status, "resposta": o.resposta})
    if (o.status, o.resposta) != (antes["status"], antes["resposta"]):
        from app.services.notificacoes import notificar
        tuc = db.get(TurmaUC, o.turma_uc_id) if o.turma_uc_id else None
        sobre = f" sobre {db.get(Turma, tuc.turma_id).codigo}" if tuc else ""
        titulo = ("Sua observação foi resolvida" if o.status == "resolvida" else "Sua observação foi respondida" if o.resposta != antes["resposta"]
                  else "Sua observação foi lida")
        notificar(db, o.instrutor_id, "observacao", titulo + sobre, o.resposta, "obs", ctx)
    db.commit()
    return _obs(db, o, True)


# ============================================================================ acesso do instrutor ao portal
def acesso_do_instrutor(db: Session, instrutor_id: int) -> dict | None:
    u = db.scalars(select(Usuario).where(Usuario.instrutor_id == instrutor_id)).first()
    return {"usuario_id": u.id, "email": u.email, "ativo": u.ativo, "ultimo_acesso": u.ultimo_acesso.isoformat() if u.ultimo_acesso else None} if u else None


def _criar_acesso(db: Session, ctx: Contexto, inst: Instrutor, email: str | None, senha: str | None) -> dict:
    supabase = get_settings().auth_modo == "supabase"
    email = (email or inst.email or "").strip().lower()
    if "@" not in email:
        raise EntradaInvalida(f"Informe o e-mail de login de {inst.nome}.")
    if acesso_do_instrutor(db, inst.id):
        raise ConflitoValidacao(f"{inst.nome} já tem acesso ao portal.")
    existente = db.scalars(select(Usuario).where(func.lower(Usuario.email) == email)).first()
    if existente is not None:
        if existente.perfil != "instrutor" or existente.instrutor_id:
            raise ConflitoValidacao(f"Já existe um usuário com o e-mail {email} (perfil {existente.perfil}).")
        existente.instrutor_id, existente.ativo = inst.id, True
        u = existente
    else:
        if not supabase and len(senha or "") < 8:
            raise EntradaInvalida("Defina uma senha inicial com ao menos 8 caracteres (o instrutor pode trocá-la depois).")
        u = Usuario(nome=inst.nome, email=email, senha_hash="!supabase" if supabase else hash_senha(senha), perfil="instrutor",
                    instrutor_id=inst.id, acesso_global=False, ativo=True)
        db.add(u)
    if not inst.email:
        inst.email = email
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ConflitoValidacao("Não foi possível criar o acesso: e-mail ou instrutor já vinculado.")
    auditoria.registrar(db, ctx, "usuario.acesso_instrutor", "usuarios", u.id, depois={"instrutor_id": inst.id, "email": email})
    res = {"usuario_id": u.id, "email": email}
    if supabase:
        from app.core.supabase_auth import convidar_usuario
        res["convite"] = convidar_usuario(email)
    return res


@router.post("/instrutores/{iid}/acesso")
def criar_acesso_instrutor(iid: int, dados: dict = Body(default={}), ctx: Contexto = Depends(requer("usuarios.gerenciar")), db: Session = Depends(get_db)):
    inst = db.get(Instrutor, iid)
    if inst is None:
        raise NaoEncontrado("Instrutor não encontrado.")
    ctx.exigir_unidade(inst.unidade_id)
    res = _criar_acesso(db, ctx, inst, dados.get("email"), dados.get("senha"))
    db.commit()
    return res


@router.post("/instrutores/acessos-em-lote")
def criar_acessos_em_lote(ctx: Contexto = Depends(requer("usuarios.gerenciar")), db: Session = Depends(get_db)):
    """Convida por e-mail todos os instrutores ativos com e-mail e ainda sem acesso (modo Supabase Auth)."""
    if get_settings().auth_modo != "supabase":
        raise EntradaInvalida("No login local, libere o acesso de cada instrutor com uma senha inicial (botão “Acesso ao portal”).")
    vinculados = set(db.scalars(select(Usuario.instrutor_id).where(Usuario.instrutor_id.isnot(None))))
    criados, falhas = [], []
    for inst in db.scalars(select(Instrutor).where(Instrutor.ativo.is_(True), Instrutor.email.isnot(None)).order_by(Instrutor.nome)):
        if inst.id in vinculados or (ctx.unidades is not None and inst.unidade_id not in ctx.unidades):
            continue
        sp = db.begin_nested()
        try:
            criados.append({"instrutor": inst.nome, **_criar_acesso(db, ctx, inst, None, None)})
            sp.commit()
        except (ConflitoValidacao, EntradaInvalida) as e:
            sp.rollback()
            falhas.append({"instrutor": inst.nome, "motivo": e.mensagem})
    db.commit()
    return {"criados": criados, "falhas": falhas}
