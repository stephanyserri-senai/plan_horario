"""Solicitações do instrutor (portal): folga ou substituição, com justificativa, decididas pelo coordenador.

- FOLGA: o instrutor não estará disponível no período (o dia todo ou só alguns turnos). Aprovada, vira bloqueio
  na agenda dele (o gerador e a validação passam a respeitar) e as aulas que ele tinha no período são
  substituídas pelo substituto escolhido pelo coordenador — ou pela sugestão do sistema, se o coordenador aceitar.
- SUBSTITUIÇÃO: o instrutor continua disponível, mas pede que outro assuma as aulas do período.
  Aprovada, as aulas passam para o substituto (escolhido ou sugerido).
Toda decisão avisa o instrutor no portal e fica na auditoria.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflitoValidacao, EntradaInvalida, NaoEncontrado
from app.models import Alocacao, Bloqueio, CenarioPlanejamento, Instrutor, SolicitacaoInstrutor, Turno
from app.services import auditoria, substituicao
from app.services.notificacoes import notificar

TIPOS = {"folga": "Folga", "substituicao": "Substituição"}
STATUS = {"pendente": "Aguardando o coordenador", "aprovada": "Aprovada", "recusada": "Recusada", "cancelada": "Cancelada"}
ORDEM_ESTADOS = ["publicado", "aprovado", "aguardando_aprovacao", "em_validacao", "em_elaboracao"]


def _turnos(db: Session, s: SolicitacaoInstrutor) -> list[Turno]:
    return [t for t in (db.get(Turno, i) for i in (s.turnos or [])) if t is not None]


def _janelas(db: Session, s: SolicitacaoInstrutor) -> list[tuple[datetime, datetime]]:
    """Intervalos do pedido: cada dia do período, inteiro ou só nos turnos escolhidos."""
    turnos = _turnos(db, s)
    res, d = [], s.data_inicio
    while d <= s.data_fim:
        if turnos:
            res += [(datetime.combine(d, t.hora_inicio), datetime.combine(d, t.hora_fim)) for t in turnos]
        else:
            res.append((datetime.combine(d, time(0, 0)), datetime.combine(d + timedelta(days=1), time(0, 0))))
        d += timedelta(days=1)
    return res


def aulas_afetadas(db: Session, s: SolicitacaoInstrutor) -> tuple[CenarioPlanejamento | None, list[Alocacao]]:
    """Aulas do instrutor no período, no semestre vigente (publicado; senão a versão mais adiantada que tenha aulas)."""
    janelas = _janelas(db, s)
    cens = db.scalars(select(CenarioPlanejamento).where(CenarioPlanejamento.tipo != "simulacao",
                                                        CenarioPlanejamento.estado.in_(ORDEM_ESTADOS))).all()
    for estado in ORDEM_ESTADOS:
        for c in [c for c in cens if c.estado == estado]:
            aulas = [a for a in db.scalars(select(Alocacao).where(
                Alocacao.cenario_id == c.id, Alocacao.instrutor_id == s.instrutor_id, Alocacao.status == "programada",
                Alocacao.data >= s.data_inicio, Alocacao.data <= s.data_fim).order_by(Alocacao.inicio))
                if any(a.inicio < f and a.fim > i for i, f in janelas)]
            if aulas:
                return c, aulas
    return None, []


def serializar(db: Session, s: SolicitacaoInstrutor, detalhes: bool = False) -> dict:
    inst = db.get(Instrutor, s.instrutor_id)
    turnos = _turnos(db, s)
    r = {"id": s.id, "instrutor_id": s.instrutor_id, "instrutor": inst.nome if inst else None, "tipo": s.tipo, "tipo_rotulo": TIPOS[s.tipo],
         "data_inicio": s.data_inicio.isoformat(), "data_fim": s.data_fim.isoformat(), "turnos": [t.nome for t in turnos] or ["dia todo"],
         "turnos_ids": list(s.turnos or []), "justificativa": s.justificativa, "status": s.status, "status_rotulo": STATUS[s.status],
         "resposta": s.resposta, "decidido_em": s.decidido_em.isoformat() if s.decidido_em else None, "efeitos": s.efeitos,
         "criado_em": s.criado_em.isoformat() if s.criado_em else None}
    if detalhes:
        cen, aulas = aulas_afetadas(db, s)
        r["cenario_id"] = cen.id if cen else None
        r["aulas_afetadas"] = len(aulas)
        r["resumo_aulas"] = substituicao._descrever(db, aulas) if aulas else ""
        if aulas and s.status == "pendente":
            cand = substituicao.candidatos(db, cen.id, aulas)
            r["candidatos"] = cand["instrutores"][:12]
            r["sugestao"] = sugerir(cand["instrutores"])
    return r


def sugerir(candidatos: list[dict]) -> dict | None:
    """Sugestão do sistema: o primeiro recomendado (livre, da área e com a UC; mensalista antes do horista e, entre eles,
    quem está na escola);
    sem recomendado, o primeiro que assume com exceção justificada."""
    for g in ("recomendado", "excecao"):
        c = next((x for x in candidatos if x["grupo"] == g), None)
        if c:
            return {"id": c["id"], "nome": c["nome"], "grupo": g,
                    "motivo": "livre em todas as aulas, da área e com a UC" if g == "recomendado" else "livre, mas de outra área ou sem a UC (exceção justificada)"}
    return None


def hoje() -> date:
    return date.today()


def criar(db: Session, ctx, inst: Instrutor, dados: dict) -> SolicitacaoInstrutor:
    tipo = (dados.get("tipo") or "").strip()
    if tipo not in TIPOS:
        raise EntradaInvalida("Escolha o tipo: folga ou substituição.")
    try:
        d0 = date.fromisoformat(str(dados.get("data_inicio")))
        d1 = date.fromisoformat(str(dados.get("data_fim") or dados.get("data_inicio")))
    except ValueError:
        raise EntradaInvalida("Informe as datas do pedido.")
    if d1 < d0:
        raise EntradaInvalida("A data final deve ser igual ou posterior à inicial.")
    if d0 < hoje():
        raise EntradaInvalida("Não é possível pedir folga ou substituição para datas passadas.")
    if (d1 - d0).days > 120:
        raise EntradaInvalida("Período longo demais: para afastamentos, fale direto com a coordenação.")
    just = (dados.get("justificativa") or "").strip()
    if len(just) < 10:
        raise EntradaInvalida("Explique o motivo do pedido (mínimo de 10 caracteres).")
    turnos = [int(t) for t in (dados.get("turnos") or [])]
    validos = {t.id for t in db.scalars(select(Turno).where(Turno.unidade_id == inst.unidade_id))}
    if any(t not in validos for t in turnos):
        raise EntradaInvalida("Turno inválido.")
    s = SolicitacaoInstrutor(instrutor_id=inst.id, tipo=tipo, data_inicio=d0, data_fim=d1, turnos=turnos, justificativa=just[:3000], status="pendente")
    db.add(s)
    db.flush()
    auditoria.registrar(db, ctx, "solicitacao.criar", "solicitacoes_instrutor", s.id, depois=auditoria.snapshot(s), origem="portal")
    return s


def cancelar(db: Session, ctx, inst: Instrutor, sid: int) -> SolicitacaoInstrutor:
    s = db.get(SolicitacaoInstrutor, sid)
    if s is None or s.instrutor_id != inst.id:
        raise NaoEncontrado("Solicitação não encontrada.")
    if s.status != "pendente":
        raise ConflitoValidacao("Só dá para cancelar pedido que ainda não foi decidido.")
    s.status = "cancelada"
    auditoria.registrar(db, ctx, "solicitacao.cancelar", "solicitacoes_instrutor", s.id, origem="portal")
    return s


def decidir(db: Session, ctx, sid: int, aprovar: bool, resposta: str | None = None, substituto_id: int | None = None,
            aceitar_sugestao: bool = False) -> dict:
    """Aprova (aplicando os efeitos) ou recusa. Na aprovação, as aulas afetadas vão para o substituto escolhido
    ou para a sugestão do sistema (aceitar_sugestao); sem substituto, ficam com o titular e aparecem como pendência."""
    s = db.get(SolicitacaoInstrutor, sid)
    if s is None:
        raise NaoEncontrado("Solicitação não encontrada.")
    if s.status != "pendente":
        raise ConflitoValidacao(f"Esta solicitação já foi {STATUS[s.status].lower()}.")
    resposta = (resposta or "").strip() or None
    antes = auditoria.snapshot(s)
    efeitos: dict = {}
    if not aprovar:
        if not resposta or len(resposta) < 5:
            raise EntradaInvalida("Explique ao instrutor por que o pedido foi recusado.")
        s.status = "recusada"
    else:
        cen, aulas = aulas_afetadas(db, s)
        if aulas and (substituto_id or aceitar_sugestao):
            if aceitar_sugestao and not substituto_id:
                sug = sugerir(substituicao.candidatos(db, cen.id, aulas)["instrutores"])
                if sug is None:
                    raise ConflitoValidacao("O sistema não encontrou substituto disponível para essas aulas. Escolha alguém ou aprove sem substituto.")
                substituto_id = sug["id"]
                efeitos["sugestao_aceita"] = sug
            motivo = f"Solicitação #{s.id} de {TIPOS[s.tipo].lower()} aprovada: {s.justificativa}"
            r = substituicao.substituir(db, ctx, cen.id, aulas, int(substituto_id), motivo)
            sub = db.get(Instrutor, int(substituto_id))
            efeitos.update({"substituto": sub.nome if sub else None, "substituidas": r["substituidas"], "falhas": r["falhas"][:10], "cenario_id": cen.id})
        else:
            efeitos.update({"substituidas": 0, "aulas_sem_substituto": len(aulas)})
        if s.tipo == "folga":
            ids = []
            for i, f in _janelas(db, s):
                b = Bloqueio(alvo_tipo="instrutor", alvo_id=s.instrutor_id, inicio=i, fim=f, tipo="folga", motivo=f"Folga aprovada (solicitação #{s.id})"[:300])
                db.add(b)
                db.flush()
                ids.append(b.id)
            efeitos["bloqueios"] = ids
        s.status = "aprovada"
    s.resposta, s.decidido_por_id, s.decidido_em, s.efeitos = resposta, ctx.id, datetime.now(), efeitos or None
    db.flush()
    auditoria.registrar(db, ctx, "solicitacao.decidir", "solicitacoes_instrutor", s.id, antes=antes, depois=auditoria.snapshot(s), motivo=resposta)
    if efeitos.get("sugestao_aceita"):
        from app.models import RegistroDecisao
        db.add(RegistroDecisao(tipo="sugestao", usuario_id=ctx.id, motivo="Sugestão de substituto aceita na aprovação de solicitação",
                               dados={"origem": "solicitacao", "solicitacao_id": s.id, "aceita": True, **efeitos["sugestao_aceita"]}))
    periodo = f"{s.data_inicio:%d/%m}" + (f" a {s.data_fim:%d/%m}" if s.data_fim != s.data_inicio else "")
    if aprovar:
        extra = (f" {efeitos['substituidas']} aula(s) com {efeitos['substituto']}." if efeitos.get("substituidas")
                 else " A coordenação vai definir quem assume as suas aulas." if efeitos.get("aulas_sem_substituto") else "")
        notificar(db, s.instrutor_id, "solicitacao", f"{TIPOS[s.tipo]} aprovada ({periodo})", ((resposta + ".") if resposta else "") + extra, "solic", ctx)
    else:
        notificar(db, s.instrutor_id, "solicitacao", f"{TIPOS[s.tipo]} recusada ({periodo})", resposta, "solic", ctx)
    return serializar(db, s)


def pendentes(db: Session, unidades=None) -> int:
    q = select(func.count()).select_from(SolicitacaoInstrutor).join(Instrutor, Instrutor.id == SolicitacaoInstrutor.instrutor_id) \
        .where(SolicitacaoInstrutor.status == "pendente")
    if unidades is not None:
        q = q.where(Instrutor.unidade_id.in_(unidades))
    return db.scalar(q) or 0
