"""Cenários de planejamento: criação, cópia, ciclo de aprovação/publicação,
versões (snapshots), comparação, restauração e propostas de alteração."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.core.errors import ConflitoConcorrencia, ConflitoValidacao, EntradaInvalida, NaoEncontrado
from app.models import (
    Alocacao,
    AlocacaoRecurso,
    Atividade,
    CenarioPlanejamento,
    OcorrenciaValidacao,
    RegistroDecisao,
    Turma,
    TurmaUC,
    UnidadeCurricular,
    Validacao,
    VersaoPlanejamento,
)
from app.services import auditoria, indicadores, objetivo
from app.services.validacao import ALERTA, BLOQUEIO, PREFERENCIA, RECOMENDACAO, ocorrencias_pendencias, resumo, validar_cenario

TRANSICOES = {
    "em_elaboracao": {"em_validacao", "arquivado"},
    "em_validacao": {"em_elaboracao", "aguardando_aprovacao", "arquivado"},
    "aguardando_aprovacao": {"aprovado", "em_elaboracao", "arquivado"},
    "aprovado": {"publicado", "em_elaboracao", "arquivado"},
    "publicado": {"arquivado"},
    "arquivado": set(),
    "em_otimizacao": set(),
}
PERMISSAO_TRANSICAO = {
    "em_validacao": "cenarios.editar", "em_elaboracao": "cenarios.editar", "aguardando_aprovacao": "cenarios.editar",
    "aprovado": "cenarios.aprovar", "publicado": "cenarios.publicar", "arquivado": "cenarios.editar",
}

COLS_ALOC = ["turma_uc_id", "turma_id", "uc_id", "grupo", "grupos", "instrutor_id", "ambiente_id", "data", "inicio", "fim",
             "fim_ambiente", "minutos_aula", "status", "fixa", "origem", "observacao", "excecao_id"]


def criar(db: Session, ctx, nome: str, unidade_id=None, periodo_inicio=None, periodo_fim=None, descricao=None, tipo="planejamento",
          origem_id=None) -> CenarioPlanejamento:
    c = CenarioPlanejamento(nome=nome, unidade_id=unidade_id, periodo_inicio=periodo_inicio, periodo_fim=periodo_fim, descricao=descricao,
                            tipo=tipo, estado="em_elaboracao", autor_id=getattr(ctx, "id", None), cenario_origem_id=origem_id)
    db.add(c)
    db.flush()
    auditoria.registrar(db, ctx, "cenario.criar", "cenarios_planejamento", c.id, depois=auditoria.snapshot(c))
    return c


def copiar_aulas(db: Session, origem_id: int, destino_id: int, somente_turmas: set[int] | None = None) -> int:
    """Copia atividades, aulas e reservas de recursos entre cenários."""
    mapa_atv = {}
    for atv in db.scalars(select(Atividade).where(Atividade.cenario_id == origem_id)):
        nova = Atividade(**{c: getattr(atv, c) for c in ("turma_uc_id", "grupo", "instrutor_id", "ambiente_id", "dia_semana", "periodo_inicio_id",
                                                           "num_periodos", "data_inicio", "data_fim", "fixa", "origem")}, cenario_id=destino_id)
        db.add(nova)
        db.flush()
        mapa_atv[atv.id] = nova.id
    q = select(Alocacao).where(Alocacao.cenario_id == origem_id, Alocacao.status != "cancelada")
    if somente_turmas is not None:
        q = q.where(Alocacao.turma_id.in_(somente_turmas))
    origem = db.scalars(q.order_by(Alocacao.id)).all()
    if not origem:
        return 0
    linhas = [{**{c: getattr(a, c) for c in COLS_ALOC}, "cenario_id": destino_id, "atividade_id": mapa_atv.get(a.atividade_id)} for a in origem]
    novos = db.execute(insert(Alocacao).returning(Alocacao.id, sort_by_parameter_order=True), linhas).scalars().all()
    mapa = dict(zip([a.id for a in origem], novos))
    recs = db.scalars(select(AlocacaoRecurso).where(AlocacaoRecurso.alocacao_id.in_(list(mapa)))).all()
    if recs:
        db.execute(insert(AlocacaoRecurso), [{"alocacao_id": mapa[r.alocacao_id], "recurso_id": r.recurso_id, "quantidade": r.quantidade} for r in recs])
    return len(novos)


def copiar(db: Session, ctx, origem_id: int, nome: str, tipo: str = "planejamento") -> CenarioPlanejamento:
    o = db.get(CenarioPlanejamento, origem_id)
    if o is None:
        raise NaoEncontrado("Cenário de origem não encontrado.")
    c = criar(db, ctx, nome, o.unidade_id, o.periodo_inicio, o.periodo_fim, f"Cópia de '{o.nome}' (v{o.versao})", tipo, origem_id)
    c.parametros = o.parametros
    n = copiar_aulas(db, origem_id, c.id)
    auditoria.registrar(db, ctx, "cenario.copiar", "cenarios_planejamento", c.id, depois={"origem": origem_id, "aulas": n})
    return c


def validar(db: Session, ctx, cenario_id: int, incluir_pendencias: bool = True) -> dict:
    cen = db.get(CenarioPlanejamento, cenario_id)
    oc = validar_cenario(db, cenario_id)
    if incluir_pendencias:
        tucs = db.scalars(select(TurmaUC).join(Turma).where(TurmaUC.id.in_(select(Alocacao.turma_uc_id).where(Alocacao.cenario_id == cenario_id)))).all()
        oc += ocorrencias_pendencias(db, cenario_id, tucs)
    r = resumo(oc)
    v = Validacao(cenario_id=cenario_id, total_bloqueios=r["bloqueios"], total_alertas=r["alertas"], total_preferencias=r["preferencias"],
                  total_recomendacoes=r["recomendacoes"], executado_por_id=getattr(ctx, "id", None))
    db.add(v)
    db.flush()
    for o in oc:
        db.add(OcorrenciaValidacao(validacao_id=v.id, severidade=o.severidade, regra=o.regra, descricao=o.descricao, recurso_tipo=o.recurso_tipo,
                                   recurso_id=o.recurso_id, data=o.data, inicio=o.inicio, fim=o.fim, turma_id=o.turma_id, uc_id=o.uc_id,
                                   instrutor_id=o.instrutor_id, ambiente_id=o.ambiente_id, alocacao_id=o.alocacao_id, origem=o.origem))
    cen.resultado_validacao = {"validacao_id": v.id, **r, "em": datetime.now().isoformat()}
    return {"validacao_id": v.id, "resumo": r, "ocorrencias": [o.to_dict() for o in oc]}


def criar_versao(db: Session, ctx, cenario_id: int, motivo: str | None = None) -> VersaoPlanejamento:
    cen = db.get(CenarioPlanejamento, cenario_id)
    aulas = db.scalars(select(Alocacao).where(Alocacao.cenario_id == cenario_id, Alocacao.status != "cancelada").order_by(Alocacao.id)).all()
    recs = {}
    for r in db.scalars(select(AlocacaoRecurso).where(AlocacaoRecurso.alocacao_id.in_([a.id for a in aulas]))):
        recs.setdefault(r.alocacao_id, []).append([r.recurso_id, r.quantidade])
    snap = [{**{c: auditoria._json(getattr(a, c)) for c in COLS_ALOC}, "id": a.id, "recursos": recs.get(a.id, [])} for a in aulas]
    numero = (db.scalar(select(func.max(VersaoPlanejamento.numero)).where(VersaoPlanejamento.cenario_id == cenario_id)) or 0) + 1
    v = VersaoPlanejamento(cenario_id=cenario_id, numero=numero, estado=cen.estado, motivo=motivo, snapshot=snap,
                           indicadores=indicadores.resumo_cenario(db, cenario_id), autor_id=getattr(ctx, "id", None))
    db.add(v)
    cen.versao = numero
    db.flush()
    auditoria.registrar(db, ctx, "cenario.versao", "versoes_planejamento", v.id, depois={"cenario": cenario_id, "numero": numero, "aulas": len(snap)}, motivo=motivo)
    return v


def transicionar(db: Session, ctx, cenario_id: int, novo: str, motivo: str | None = None, lock_version: int | None = None) -> dict:
    cen = db.scalars(select(CenarioPlanejamento).where(CenarioPlanejamento.id == cenario_id).with_for_update()).first()
    if cen is None:
        raise NaoEncontrado("Cenário não encontrado.")
    if lock_version is not None and cen.lock_version != lock_version:
        raise ConflitoConcorrencia("O cenário foi alterado por outro usuário. Recarregue antes de prosseguir.")
    if novo not in TRANSICOES.get(cen.estado, set()):
        raise ConflitoValidacao(f"Transição inválida: '{cen.estado}' → '{novo}'.")
    ctx.exigir(PERMISSAO_TRANSICAO[novo])
    resultado = {}
    if novo in ("aguardando_aprovacao", "aprovado", "publicado"):
        val = validar(db, ctx, cenario_id)
        resultado["validacao"] = val["resumo"]
        if val["resumo"]["bloqueios"]:
            db.flush()
            raise ConflitoValidacao(
                f"O cenário possui {val['resumo']['bloqueios']} violação(ões) de restrições obrigatórias e não pode avançar para '{novo}'.",
                detalhes={"ocorrencias": [o for o in val["ocorrencias"] if o["severidade"] == BLOQUEIO][:200]}, codigo="VALIDACAO_BLOQUEADA")
    if novo == "em_validacao":
        resultado["validacao"] = validar(db, ctx, cenario_id)["resumo"]
    antes = cen.estado
    if novo == "publicado":
        if cen.tipo == "simulacao":
            raise ConflitoValidacao("Cenários de simulação nunca são publicados.")
        anteriores = db.scalars(select(CenarioPlanejamento).where(
            CenarioPlanejamento.estado == "publicado", CenarioPlanejamento.id != cen.id,
            (CenarioPlanejamento.unidade_id == cen.unidade_id) if cen.unidade_id else CenarioPlanejamento.unidade_id.is_(None)).with_for_update()).all()
        for a in anteriores:
            a.estado = "arquivado"
            auditoria.registrar(db, ctx, "cenario.arquivar", "cenarios_planejamento", a.id, depois={"substituido_por": cen.id})
        db.flush()
        cen.publicado_em = datetime.now()
    if novo == "aprovado":
        cen.aprovado_por_id = ctx.id
        db.add(RegistroDecisao(tipo="aprovacao", cenario_id=cen.id, usuario_id=ctx.id, motivo=motivo, dados={"de": antes}))
    if antes == "aguardando_aprovacao" and novo == "em_elaboracao":
        db.add(RegistroDecisao(tipo="reprovacao", cenario_id=cen.id, usuario_id=ctx.id, motivo=motivo, dados={}))
    cen.estado = novo
    cen.lock_version += 1
    if novo == "publicado":
        _avisar_publicacao(db, ctx, cen)
    db.flush()
    versao = criar_versao(db, ctx, cen.id, motivo or f"{antes} → {novo}")
    cen.indicadores = versao.indicadores
    auditoria.registrar(db, ctx, f"cenario.{novo}", "cenarios_planejamento", cen.id, antes={"estado": antes}, depois={"estado": novo, "versao": versao.numero}, motivo=motivo)
    return {"cenario_id": cen.id, "estado": novo, "versao": versao.numero, **resultado}


def _avisar_publicacao(db: Session, ctx, cen: CenarioPlanejamento):
    """Cada instrutor com aulas no semestre publicado recebe um aviso no portal."""
    from sqlalchemy import func as _f
    from app.services.notificacoes import notificar
    for iid, n, t in db.execute(select(Alocacao.instrutor_id, _f.count(), _f.count(_f.distinct(Alocacao.turma_id)))
                                .where(Alocacao.cenario_id == cen.id, Alocacao.instrutor_id.isnot(None), Alocacao.status != "cancelada")
                                .group_by(Alocacao.instrutor_id)):
        notificar(db, iid, "publicacao", f"Horário publicado: {cen.nome}", f"Você tem {n} aula(s) em {t} turma(s). Confira em “Minhas turmas e horários”.",
                  "turmas", ctx)


def proposta_alteracao(db: Session, ctx, publicado_id: int, nome: str, descricao: str | None = None) -> CenarioPlanejamento:
    pub = db.get(CenarioPlanejamento, publicado_id)
    if pub is None or pub.estado not in ("publicado", "aprovado"):
        raise ConflitoValidacao("Propostas de alteração partem de um cenário publicado ou aprovado.")
    c = copiar(db, ctx, publicado_id, nome, tipo="proposta")
    c.descricao = descricao or f"Proposta de alteração do cenário publicado #{publicado_id}"
    return c


def _chave(a: dict):
    return (a["turma_uc_id"], a["grupo"], a["data"], a["inicio"])


def _aulas_dict(db: Session, cenario_id: int) -> list[dict]:
    return [{**{c: auditoria._json(getattr(a, c)) for c in COLS_ALOC}, "id": a.id}
            for a in db.scalars(select(Alocacao).where(Alocacao.cenario_id == cenario_id, Alocacao.status != "cancelada"))]


def diferencas(lista_a: list[dict], lista_b: list[dict], db: Session | None = None) -> dict:
    ia = {_chave(a): a for a in lista_a}
    ib = {_chave(b): b for b in lista_b}
    removidas = [ia[k] for k in ia.keys() - ib.keys()]
    adicionadas = [ib[k] for k in ib.keys() - ia.keys()]
    alteradas = []
    for k in ia.keys() & ib.keys():
        a, b = ia[k], ib[k]
        mud = {c: [a[c], b[c]] for c in ("instrutor_id", "ambiente_id", "fim") if a[c] != b[c]}
        if mud:
            alteradas.append({"turma_uc_id": k[0], "grupo": k[1], "data": k[2], "inicio": k[3], "mudancas": mud})
    afetados = {"turmas": sorted({x["turma_id"] for x in removidas + adicionadas}),
                "instrutores": sorted({x["instrutor_id"] for x in removidas + adicionadas if x["instrutor_id"]}
                                      | {v for x in alteradas for v in x["mudancas"].get("instrutor_id", []) if v}),
                "ambientes": sorted({x["ambiente_id"] for x in removidas + adicionadas if x["ambiente_id"]}
                                    | {v for x in alteradas for v in x["mudancas"].get("ambiente_id", []) if v})}
    return {"adicionadas": len(adicionadas), "removidas": len(removidas), "alteradas": len(alteradas),
            "detalhes": {"adicionadas": adicionadas[:300], "removidas": removidas[:300], "alteradas": alteradas[:300]},
            "recursos_afetados": afetados}


def comparar(db: Session, cenario_ids: list[int], pesos: dict | None = None) -> dict:
    """Compara cenários com a MESMA régua (mesmos pesos) e explica a ordem."""
    if len(cenario_ids) < 2:
        raise EntradaInvalida("Informe ao menos dois cenários.")
    res = []
    for cid in cenario_ids:
        cen = db.get(CenarioPlanejamento, cid)
        if cen is None:
            raise NaoEncontrado(f"Cenário {cid} não encontrado.")
        aval = objetivo.avaliar_cenario(db, cid, pesos)
        ind = indicadores.resumo_cenario(db, cid)
        ult = db.scalars(select(Validacao).where(Validacao.cenario_id == cid).order_by(Validacao.id.desc())).first()
        from app.models import ExecucaoOtimizacao
        exe = db.scalars(select(ExecucaoOtimizacao).where(ExecucaoOtimizacao.cenario_id == cid, ExecucaoOtimizacao.status == "concluida")
                         .order_by(ExecucaoOtimizacao.id.desc())).first()
        tu = indicadores.turmas_ucs(db, cid, cen.periodo_inicio)
        res.append({"cenario": {"id": cid, "nome": cen.nome, "estado": cen.estado, "versao": cen.versao, "tipo": cen.tipo},
                    "avaliacao": aval, "indicadores": ind,
                    "validacao": {"bloqueios": ult.total_bloqueios, "alertas": ult.total_alertas, "preferencias": ult.total_preferencias} if ult else None,
                    "carga_programada_h": tu["resumo"]["ch_programada_h"], "carga_pendente_h": tu["resumo"]["ch_pendente_h"],
                    "ultima_execucao": {"id": exe.id, "status_solver": exe.status_solver, "tempo_s": exe.tempo_s, "parametros": exe.parametros} if exe else None})
    ordem = sorted(res, key=lambda r: (r["validacao"]["bloqueios"] if r["validacao"] else 0, r["carga_pendente_h"], r["avaliacao"]["pontuacao_total"]))
    melhor, segundo = ordem[0], ordem[1]
    explic = []
    for cm, cs in zip(melhor["avaliacao"]["criterios"], segundo["avaliacao"]["criterios"]):
        dif = cs["pontos"] - cm["pontos"]
        if abs(dif) > 1e-6:
            explic.append({"criterio": cm["criterio"], "descricao": cm["descricao"], "melhor": cm["valor_bruto"], "segundo": cs["valor_bruto"],
                           "unidade": cm["unidade"], "diferenca_pontos": round(dif, 3)})
    explic.sort(key=lambda e: -abs(e["diferenca_pontos"]))
    dif = diferencas(_aulas_dict(db, melhor["cenario"]["id"]), _aulas_dict(db, segundo["cenario"]["id"]))
    return {"cenarios": res, "ranking": [r["cenario"]["id"] for r in ordem], "pesos": res[0]["avaliacao"]["pesos"],
            "criterio_ordenacao": "1º menos bloqueios; 2º menor carga pendente; 3º menor pontuação da função objetivo (mesmos pesos para todos).",
            "explicacao": {"melhor": melhor["cenario"]["id"], "segundo": segundo["cenario"]["id"], "por_criterio": explic},
            "diferencas_melhor_vs_segundo": {k: v for k, v in dif.items() if k != "detalhes"}}


def comparar_versoes(db: Session, versao_a_id: int, versao_b_id: int) -> dict:
    a, b = db.get(VersaoPlanejamento, versao_a_id), db.get(VersaoPlanejamento, versao_b_id)
    if not a or not b:
        raise NaoEncontrado("Versão não encontrada.")
    return {"versao_a": {"id": a.id, "numero": a.numero, "estado": a.estado, "indicadores": a.indicadores},
            "versao_b": {"id": b.id, "numero": b.numero, "estado": b.estado, "indicadores": b.indicadores},
            **diferencas(a.snapshot, b.snapshot)}


def impacto_proposta(db: Session, proposta_id: int) -> dict:
    prop = db.get(CenarioPlanejamento, proposta_id)
    if not prop or not prop.cenario_origem_id:
        raise EntradaInvalida("Cenário sem origem para comparar.")
    d = diferencas(_aulas_dict(db, prop.cenario_origem_id), _aulas_dict(db, proposta_id))
    return {"origem_id": prop.cenario_origem_id, "proposta_id": proposta_id, **d}


def restaurar(db: Session, ctx, versao_id: int, como_novo: bool = False) -> dict:
    v = db.get(VersaoPlanejamento, versao_id)
    if v is None:
        raise NaoEncontrado("Versão não encontrada.")
    cen = db.get(CenarioPlanejamento, v.cenario_id)
    if como_novo or cen.estado not in ("em_elaboracao", "em_validacao"):
        alvo = criar(db, ctx, f"{cen.nome} (restaurado v{v.numero})", cen.unidade_id, cen.periodo_inicio, cen.periodo_fim,
                     f"Restaurado da versão {v.numero} do cenário #{cen.id}", "planejamento", cen.id)
    else:
        alvo = db.scalars(select(CenarioPlanejamento).where(CenarioPlanejamento.id == cen.id).with_for_update()).first()
        db.execute(delete(Alocacao).where(Alocacao.cenario_id == alvo.id))
        db.execute(delete(Atividade).where(Atividade.cenario_id == alvo.id))
        db.flush()
    linhas = []
    recursos = []
    for a in v.snapshot:
        linha = {c: a[c] for c in COLS_ALOC}
        for c in ("data",):
            linha[c] = date.fromisoformat(linha[c])
        for c in ("inicio", "fim", "fim_ambiente"):
            linha[c] = datetime.fromisoformat(linha[c])
        linha["cenario_id"] = alvo.id
        linhas.append(linha)
        recursos.append(a.get("recursos", []))
    if linhas:
        novos = db.execute(insert(Alocacao).returning(Alocacao.id, sort_by_parameter_order=True), linhas).scalars().all()
        rr = [{"alocacao_id": nid, "recurso_id": r[0], "quantidade": r[1]} for nid, rs in zip(novos, recursos) for r in rs]
        if rr:
            db.execute(insert(AlocacaoRecurso), rr)
    alvo.lock_version += 1
    auditoria.registrar(db, ctx, "cenario.restaurar", "cenarios_planejamento", alvo.id, depois={"versao_id": v.id, "numero": v.numero, "aulas": len(linhas)})
    val = validar(db, ctx, alvo.id)
    return {"cenario_id": alvo.id, "aulas": len(linhas), "validacao": val["resumo"]}


def excluir(db: Session, ctx, cenario_id: int):
    cen = db.get(CenarioPlanejamento, cenario_id)
    if cen is None:
        raise NaoEncontrado("Cenário não encontrado.")
    if cen.estado in ("publicado", "aprovado"):
        raise ConflitoValidacao("Cenários aprovados ou publicados não podem ser excluídos; arquive-os.")
    auditoria.registrar(db, ctx, "cenario.excluir", "cenarios_planejamento", cen.id, antes=auditoria.snapshot(cen))
    db.delete(cen)


SEVERIDADES = (BLOQUEIO, ALERTA, PREFERENCIA, RECOMENDACAO)
_ = UnidadeCurricular
