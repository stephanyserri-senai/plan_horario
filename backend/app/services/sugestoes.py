"""Aceitar uma sugestão do sistema e aplicá-la automaticamente.

As sugestões (do diagnóstico de falta de instrutor, das recomendações, das solicitações...) trazem uma
`acao` estruturada. Aceitar = executar essa ação pelos mesmos serviços de sempre (cadastro, validação
central, substituição, gerador), com auditoria; a decisão fica registrada (registros_decisao, tipo
"sugestao") para revisar e calibrar o sistema. Nada aqui contorna uma regra obrigatória: se a ação
não passar na validação, o erro volta explicado e nada é gravado.

Ações:
- habilitar_instrutor {instrutor_id, uc_id, turma_id?}: marca a UC no perfil do instrutor ("sim").
- passar_uc {turma_uc_id, de_instrutor_id, para_instrutor_id, habilitar, turma_id?}: as próximas aulas da UC passam
  para outro instrutor (como substituição registrada; habilita antes, se preciso), liberando o primeiro.
- adiar_uc {turma_uc_id, data_inicio}: a UC passa a começar na data sugerida.
- alocar_aula {turma_uc_id, data, periodo_inicio_id, num_periodos, grupo, instrutor_id, ambiente_id}: cria a aula sugerida.
- substituir {alocacao_ids, substituto_id}: registra a substituição sugerida.
- trocar_sala {alocacao_ids, ambiente_id} / remarcar {alocacao_ids, data, periodo_inicio_id, num_periodos}: ajustes operacionais
  (valem também com o horário publicado), pela validação central (services/resolucoes.ajustar).
- gerar_turma {turma_id}: gera de novo os horários da turma (semestre em edição).
- reposicao_sabado {turma_uc_id, datas, instrutor_id, ambiente_id}: aulas de reposição aos sábados (turma modular).
- passar_proximo_semestre {turma_uc_id}: o restante da UC vai para o próximo semestre (turma não modular).
Depois de habilitar, passar ou adiar, se o semestre está em edição, o gerador roda só para a turma (gerar=True).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflitoValidacao, EntradaInvalida, NaoEncontrado
from app.models import Alocacao, CenarioPlanejamento, CompetenciaInstrutor, Instrutor, RegistroDecisao, Turma, TurmaUC, UnidadeCurricular
from app.services import auditoria

PERMISSOES = {"habilitar_instrutor": "cadastros.editar", "passar_uc": "alocacoes.editar", "adiar_uc": "cadastros.editar",
              "alocar_aula": "alocacoes.editar", "substituir": "alocacoes.editar", "trocar_sala": "alocacoes.editar",
              "remarcar": "alocacoes.editar", "gerar_turma": "otimizacao.executar", "reposicao_sabado": "alocacoes.editar",
              "passar_proximo_semestre": "cadastros.editar"}
EDITAVEIS = ("em_elaboracao", "em_validacao")


def _habilitar(db: Session, ctx, instrutor_id: int, uc_id: int) -> str:
    inst, uc = db.get(Instrutor, instrutor_id), db.get(UnidadeCurricular, uc_id)
    if inst is None or uc is None:
        raise NaoEncontrado("Instrutor ou UC não encontrado.")
    c = db.scalar(select(CompetenciaInstrutor).where(CompetenciaInstrutor.instrutor_id == inst.id, CompetenciaInstrutor.uc_id == uc.id))
    antes = auditoria.snapshot(c) if c else None
    if c is None:
        c = CompetenciaInstrutor(instrutor_id=inst.id, uc_id=uc.id, nivel="pleno", ativo=True)
        db.add(c)
    else:
        c.ativo, c.nivel = True, "pleno"
    db.flush()
    auditoria.registrar(db, ctx, "cadastro.alterar", "competencias_instrutores", c.id, antes=antes, depois=auditoria.snapshot(c), motivo="Sugestão aceita")
    from app.services.notificacoes import notificar
    notificar(db, inst.id, "cadastro", "Você foi habilitado(a) em uma UC", f"{uc.codigo} – {uc.nome} (sugestão do planejamento aceita pela coordenação).", "dados", ctx)
    return f"{inst.nome} habilitado(a) em {uc.codigo}."


def _gerar_turma(db: Session, ctx, cenario_id: int, turma_id: int | None) -> dict | None:
    cen = db.get(CenarioPlanejamento, cenario_id)
    if not turma_id or cen is None:
        return None
    if cen.estado not in EDITAVEIS:
        return {"gerado": False, "aviso": "O semestre não está em edição: para refazer a grade da turma, crie uma proposta de alteração e gere os horários nela."}
    if not ctx.pode("otimizacao.executar"):
        return {"gerado": False, "aviso": "Gere os horários da turma em 'Gerar horários'."}
    from app.services import otimizacao
    ex = otimizacao.criar_execucao(db, ctx, cenario_id, {"tipo": "turma", "ids": [int(turma_id)]}, limite_tempo_s=30)
    db.commit()
    modo = otimizacao.despachar(ex.id, ctx)
    return {"gerado": True, "execucao_id": ex.id, "modo_execucao": modo}


def aplicar(db: Session, ctx, cenario_id: int, acao: dict, motivo: str | None = None, gerar: bool = True) -> dict:
    tipo = (acao or {}).get("tipo")
    if tipo not in PERMISSOES:
        raise EntradaInvalida("Sugestão sem ação aplicável.")
    ctx.exigir(PERMISSOES[tipo])
    cen = db.get(CenarioPlanejamento, cenario_id)
    if cen is None:
        raise NaoEncontrado("Semestre não encontrado.")
    res: dict = {"acao": tipo}
    if tipo == "habilitar_instrutor":
        res["mensagem"] = _habilitar(db, ctx, int(acao["instrutor_id"]), int(acao["uc_id"]))
    elif tipo == "passar_uc":
        from app.services import substituicao
        tuc = db.get(TurmaUC, int(acao["turma_uc_id"]))
        if tuc is None:
            raise NaoEncontrado("Oferta (turma × UC) não encontrada.")
        msgs = []
        if acao.get("habilitar"):
            msgs.append(_habilitar(db, ctx, int(acao["para_instrutor_id"]), tuc.uc_id))
        aulas = list(db.scalars(select(Alocacao).where(Alocacao.cenario_id == cenario_id, Alocacao.turma_uc_id == tuc.id,
                                                       Alocacao.instrutor_id == int(acao["de_instrutor_id"]), Alocacao.status == "programada",
                                                       Alocacao.data >= date.today()).order_by(Alocacao.inicio)))
        if not aulas:
            raise ConflitoValidacao("Não há aulas futuras desta UC com o instrutor indicado.")
        r = substituicao.substituir(db, ctx, cenario_id, aulas, int(acao["para_instrutor_id"]),
                                    motivo or "Sugestão do sistema aceita: passar a UC para liberar turnos do instrutor")
        if not r["substituidas"]:
            raise ConflitoValidacao("A troca não passou na validação: " + "; ".join(m for f in r["falhas"][:3] for m in f["motivos"][:1]))
        msgs.append(f"{r['substituidas']} aula(s) passaram para o novo instrutor" + (f"; {len(r['falhas'])} não puderam" if r["falhas"] else "") + ".")
        res["mensagem"], res["falhas"] = " ".join(msgs), r["falhas"][:10]
    elif tipo == "adiar_uc":
        tuc = db.get(TurmaUC, int(acao["turma_uc_id"]))
        if tuc is None:
            raise NaoEncontrado("Oferta (turma × UC) não encontrada.")
        antes = auditoria.snapshot(tuc)
        tuc.data_inicio = date.fromisoformat(acao["data_inicio"])
        db.flush()
        auditoria.registrar(db, ctx, "cadastro.alterar", "turma_uc", tuc.id, antes=antes, depois=auditoria.snapshot(tuc), motivo="Sugestão aceita: adiar início")
        res["mensagem"] = f"A UC passa a começar em {tuc.data_inicio:%d/%m/%Y}."
    elif tipo == "alocar_aula":
        from app.services import alocacao as aloc
        dados = aloc.DadosAula(turma_uc_id=int(acao["turma_uc_id"]), data=date.fromisoformat(acao["data"]), periodo_inicio_id=int(acao["periodo_inicio_id"]),
                               num_periodos=int(acao["num_periodos"]), grupo=acao.get("grupo"), instrutor_id=acao.get("instrutor_id"),
                               ambiente_id=acao.get("ambiente_id"), origem="sugestao", observacao="Sugestão do sistema aceita")
        a, _oc = aloc.criar_aula(db, ctx, cenario_id, dados)
        res["mensagem"], res["alocacao_id"] = f"Aula criada em {a.data:%d/%m} ({a.inicio:%H:%M}–{a.fim:%H:%M}).", a.id
        gerar = False
    elif tipo == "substituir":
        from app.services import substituicao
        aulas = [a for a in (db.get(Alocacao, int(i)) for i in acao.get("alocacao_ids") or []) if a is not None and a.cenario_id == cenario_id]
        if not aulas:
            raise EntradaInvalida("Nenhuma aula para substituir.")
        r = substituicao.substituir(db, ctx, cenario_id, aulas, int(acao["substituto_id"]), motivo or acao.get("motivo") or "")
        res.update({"mensagem": f"{r['substituidas']} aula(s) substituída(s).", "falhas": r["falhas"][:10]})
        gerar = False
    elif tipo in ("trocar_sala", "remarcar"):
        from app.services import resolucoes
        r = resolucoes.ajustar(db, ctx, cenario_id, acao.get("alocacao_ids") or [], ambiente_id=acao.get("ambiente_id"), data=acao.get("data"),
                               periodo_inicio_id=acao.get("periodo_inicio_id"), num_periodos=acao.get("num_periodos"),
                               motivo=motivo or ("Sala trocada" if tipo == "trocar_sala" else "Aula remarcada") + ": sugestão aceita na análise de riscos")
        res.update({"mensagem": f"{r['ajustadas']} aula(s) " + ("com a sala trocada." if tipo == "trocar_sala" else "remarcada(s)."), "falhas": r["falhas"][:10]})
        gerar = False
    elif tipo == "reposicao_sabado":
        from app.services import resolucoes
        r = resolucoes.reposicao(db, ctx, cenario_id, acao["turma_uc_id"], acao.get("datas") or [], acao["instrutor_id"], acao.get("ambiente_id"), motivo or "")
        res.update({"mensagem": f"{r['criadas']} aula(s) de reposição marcada(s) aos sábados.", "falhas": r["falhas"][:10]})
        gerar = False
    elif tipo == "passar_proximo_semestre":
        from app.services import resolucoes
        r = resolucoes.proximo_semestre(db, ctx, acao["turma_uc_id"])
        res["mensagem"] = f"O restante da UC passa para {r['semestre']} (prazo {date.fromisoformat(r['prazo']):%d/%m/%Y})."
        gerar = False
    elif tipo == "gerar_turma":
        db.add(RegistroDecisao(tipo="sugestao", cenario_id=cenario_id, usuario_id=ctx.id, motivo=motivo, dados={"acao": acao, "aceita": True}))
        db.commit()
        g = _gerar_turma(db, ctx, cenario_id, acao.get("turma_id"))
        if not g or not g.get("gerado"):
            raise ConflitoValidacao((g or {}).get("aviso") or "Não foi possível gerar os horários da turma.")
        return {**res, "mensagem": "Geração dos horários da turma iniciada; acompanhe em Gerar horários.", "geracao": g}
    db.add(RegistroDecisao(tipo="sugestao", cenario_id=cenario_id, usuario_id=ctx.id, motivo=motivo, dados={"acao": acao, "aceita": True}))
    db.flush()
    if gerar and tipo in ("habilitar_instrutor", "passar_uc", "adiar_uc"):
        db.commit()
        res["geracao"] = _gerar_turma(db, ctx, cenario_id, acao.get("turma_id"))
    return res


def recusar(db: Session, ctx, cenario_id: int | None, acao: dict, motivo: str | None = None):
    """Recusa registrada (sem efeito na grade), para o sistema aprender o que não serve."""
    db.add(RegistroDecisao(tipo="rejeicao", cenario_id=cenario_id, usuario_id=ctx.id, motivo=motivo, dados={"acao": acao, "aceita": False}))
