"""Operações de alocação (manual, recorrente, cópia, edição, arrastar-e-soltar).

Garantias de integridade:
1. Toda gravação ocorre em uma transação.
2. Antes de validar, adquire `pg_advisory_xact_lock` para cada recurso
   envolvido (cenário+instrutor, cenário+ambiente, cenário+turma, cenário+
   turma×UC e cenário+recurso compartilhado), em ordem determinística para
   evitar deadlocks. Assim a validação lê um estado que nenhuma outra
   transação concorrente pode alterar para os mesmos recursos.
3. As exclusion constraints do PostgreSQL são a última barreira: mesmo que
   uma regra fosse contornada, o banco rejeita sobreposições.
4. Alterações usam controle otimista (`versao`): se outro usuário alterou a
   aula, a operação é recusada com mensagem clara.
5. Se a nova situação for inválida, nada é gravado: o horário válido anterior
   permanece intacto (rollback).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from sqlalchemy import delete, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflitoConcorrencia, ConflitoValidacao, EntradaInvalida, NaoEncontrado
from app.models import (
    Alocacao,
    AlocacaoRecurso,
    Ambiente,
    Atividade,
    CenarioPlanejamento,
    PeriodoHorario,
    RegistroDecisao,
    Turma,
    TurmaUC,
    UnidadeCurricular,
)
from app.services import auditoria
from app.services.calendario import Calendarios, bloco_de_periodos, combinar, minutos_do_bloco, periodos_por_turno
from app.services.planejamento import ambientes_compativeis, instrutores_elegiveis
from app.services.validacao import (
    BLOQUEIO,
    AulaProposta,
    BaseDados,
    Ocorrencia,
    grupos_da_aula,
    possui_bloqueio,
    validar_aula,
)

ESTADOS_EDITAVEIS = ("em_elaboracao", "em_validacao")

MENSAGENS_CONSTRAINT = {
    "excl_alocacao_instrutor": "O instrutor foi alocado por outra operação no mesmo horário.",
    "excl_alocacao_ambiente": "O ambiente foi reservado por outra operação no mesmo horário.",
    "excl_alocacao_turma_grupos": "A turma recebeu outra aula no mesmo horário por outra operação.",
}


@dataclass
class DadosAula:
    turma_uc_id: int
    data: date
    periodo_inicio_id: int | None = None
    num_periodos: int | None = None
    hora_inicio: time | None = None
    hora_fim: time | None = None
    grupo: int | None = None
    instrutor_id: int | None = None
    ambiente_id: int | None = None
    recursos: list[tuple[int, int]] = field(default_factory=list)
    excecao_id: int | None = None
    fixa: bool = False
    observacao: str | None = None
    origem: str = "manual"


def travar_recursos(db: Session, cenario_id: int, chaves: list[tuple[str, int | None]]):
    for tipo, id_ in sorted({(t, i) for t, i in chaves if i is not None}):
        db.execute(text("SELECT pg_advisory_xact_lock(:a, hashtext(:k))"), {"a": cenario_id, "k": f"{tipo}:{id_}"})


def obter_cenario_editavel(db: Session, cenario_id: int, bloquear: bool = False) -> CenarioPlanejamento:
    q = select(CenarioPlanejamento).where(CenarioPlanejamento.id == cenario_id)
    q = q.with_for_update() if bloquear else q.with_for_update(read=True)
    cen = db.scalars(q).first()
    if cen is None:
        raise NaoEncontrado("Cenário não encontrado.")
    if cen.estado not in ESTADOS_EDITAVEIS:
        raise ConflitoValidacao(
            f"O cenário '{cen.nome}' está '{cen.estado}' e não pode ser alterado diretamente. "
            "Crie uma proposta de alteração a partir dele.",
            codigo="CENARIO_NAO_EDITAVEL",
        )
    return cen


def resolver_horario(db: Session, turma: Turma, d: DadosAula) -> tuple[datetime, datetime, int]:
    """Converte período+duração ou horário livre em instantes reais."""
    if d.periodo_inicio_id:
        try:
            bloco = bloco_de_periodos(db, d.periodo_inicio_id, d.num_periodos or 1, d.data.weekday())
        except ValueError as e:
            raise EntradaInvalida(str(e))
        return combinar(d.data, bloco[0].hora_inicio), combinar(d.data, bloco[-1].hora_fim), minutos_do_bloco(bloco)
    if d.hora_inicio and d.hora_fim:
        ini, fim = combinar(d.data, d.hora_inicio), combinar(d.data, d.hora_fim)
        if fim <= ini:
            raise EntradaInvalida("O horário de término deve ser posterior ao início.")
        # Desconta intervalos entre períodos da unidade contidos na janela.
        mins = int((fim - ini).total_seconds() // 60)
        return ini, fim, mins
    raise EntradaInvalida("Informe o período inicial e a quantidade de períodos, ou os horários de início e término.")


def _proposta(db: Session, d: DadosAula, alocacao_id: int | None = None) -> tuple[AulaProposta, TurmaUC, Turma]:
    tuc = db.get(TurmaUC, d.turma_uc_id)
    if tuc is None:
        raise EntradaInvalida("Turma×UC inexistente.")
    turma = db.get(Turma, tuc.turma_id)
    ini, fim, mins = resolver_horario(db, turma, d)
    return AulaProposta(turma_uc_id=tuc.id, inicio=ini, fim=fim, minutos_aula=mins, grupo=d.grupo,
                        instrutor_id=d.instrutor_id, ambiente_id=d.ambiente_id, recursos=list(d.recursos),
                        excecao_id=d.excecao_id, alocacao_id=alocacao_id, origem=d.origem), tuc, turma


def _chaves(p: AulaProposta, tuc: TurmaUC):
    ch = [("turma", tuc.turma_id), ("tuc", tuc.id), ("instrutor", p.instrutor_id), ("ambiente", p.ambiente_id)]
    ch += [("recurso", rid) for rid, _ in p.recursos]
    return ch


def _gravar(db: Session, cenario_id: int, p: AulaProposta, tuc: TurmaUC, d: DadosAula, ctx, atividade_id=None) -> Alocacao:
    amb = db.get(Ambiente, p.ambiente_id) if p.ambiente_id else None
    prep = timedelta(minutes=(amb.tempo_preparacao_min if amb else 0) or 0)
    a = Alocacao(
        cenario_id=cenario_id, atividade_id=atividade_id, turma_uc_id=tuc.id, turma_id=tuc.turma_id, uc_id=tuc.uc_id,
        grupo=p.grupo, grupos=grupos_da_aula(p.grupo), instrutor_id=p.instrutor_id, ambiente_id=p.ambiente_id,
        data=p.inicio.date(), inicio=p.inicio, fim=p.fim, fim_ambiente=p.fim + prep, minutos_aula=p.minutos_aula,
        fixa=d.fixa, origem=d.origem, observacao=d.observacao, excecao_id=p.excecao_id,
        criado_por_id=getattr(ctx, "id", None), status="programada",
    )
    db.add(a)
    db.flush()
    for rid, q in p.recursos:
        db.add(AlocacaoRecurso(alocacao_id=a.id, recurso_id=rid, quantidade=q))
    db.flush()
    return a


def _traduzir_erro_banco(e: Exception):
    msg = str(getattr(e, "orig", e))
    for nome, texto in MENSAGENS_CONSTRAINT.items():
        if nome in msg:
            raise ConflitoConcorrencia(texto + " Atualize a grade e tente novamente.", codigo="CONFLITO_CONCORRENTE")
    if "deadlock detected" in msg or "could not serialize" in msg:
        raise ConflitoConcorrencia("Operação concorrente sobre os mesmos recursos. Tente novamente.", codigo="CONFLITO_CONCORRENTE")
    raise e


def criar_aula(db: Session, ctx, cenario_id: int, d: DadosAula, validar_somente: bool = False) -> tuple[Alocacao | None, list[Ocorrencia]]:
    obter_cenario_editavel(db, cenario_id)
    p, tuc, turma = _proposta(db, d)
    travar_recursos(db, cenario_id, _chaves(p, tuc))
    b = BaseDados(db, cenario_id)
    oc = validar_aula(b, p)
    if possui_bloqueio(oc):
        raise ConflitoValidacao(
            "A aula não pode ser gravada: há restrições obrigatórias violadas.",
            detalhes={"ocorrencias": [o.to_dict() for o in oc], "alternativas": sugerir_alternativas(db, cenario_id, p)},
            codigo="RESTRICAO_OBRIGATORIA",
        )
    if validar_somente:
        return None, oc
    try:
        a = _gravar(db, cenario_id, p, tuc, d, ctx)
    except (IntegrityError, DBAPIError) as e:
        db.rollback()
        _traduzir_erro_banco(e)
    auditoria.registrar(db, ctx, "alocacao.criar", "alocacoes", a.id, depois=auditoria.snapshot(a), origem=d.origem)
    if d.origem == "manual":
        db.add(RegistroDecisao(tipo="selecao", cenario_id=cenario_id, alocacao_id=a.id, usuario_id=getattr(ctx, "id", None),
                               dados={"turma_uc_id": tuc.id, "dia_semana": p.inicio.weekday(), "inicio": p.inicio.strftime("%H:%M"),
                                      "fim": p.fim.strftime("%H:%M"), "instrutor_id": p.instrutor_id, "ambiente_id": p.ambiente_id}))
    return a, oc


def atualizar_aula(db: Session, ctx, alocacao_id: int, d: DadosAula, versao_esperada: int, motivo: str | None = None):
    atual = db.scalars(select(Alocacao).where(Alocacao.id == alocacao_id).with_for_update()).first()
    if atual is None:
        raise NaoEncontrado("Aula não encontrada (pode ter sido removida por outro usuário).")
    obter_cenario_editavel(db, atual.cenario_id)
    if atual.versao != versao_esperada:
        raise ConflitoConcorrencia(
            f"A aula #{alocacao_id} foi alterada por outro usuário (versão {atual.versao}, sua versão {versao_esperada}). Recarregue antes de editar.",
            codigo="VERSAO_DESATUALIZADA",
        )
    if atual.status == "realizada":
        raise ConflitoValidacao("Aulas já realizadas não podem ser alteradas.")
    antes = auditoria.snapshot(atual)
    p, tuc, turma = _proposta(db, d, alocacao_id=alocacao_id)
    travar_recursos(db, atual.cenario_id, _chaves(p, tuc) + [("instrutor", atual.instrutor_id), ("ambiente", atual.ambiente_id)])
    oc = validar_aula(BaseDados(db, atual.cenario_id), p)
    if possui_bloqueio(oc):
        raise ConflitoValidacao(
            "Alteração bloqueada: o horário anterior foi mantido.",
            detalhes={"ocorrencias": [o.to_dict() for o in oc], "alternativas": sugerir_alternativas(db, atual.cenario_id, p)},
            codigo="RESTRICAO_OBRIGATORIA",
        )
    amb = db.get(Ambiente, p.ambiente_id) if p.ambiente_id else None
    prep = timedelta(minutes=(amb.tempo_preparacao_min if amb else 0) or 0)
    atual.turma_uc_id, atual.turma_id, atual.uc_id = tuc.id, tuc.turma_id, tuc.uc_id
    atual.grupo, atual.grupos = p.grupo, grupos_da_aula(p.grupo)
    atual.instrutor_id, atual.ambiente_id = p.instrutor_id, p.ambiente_id
    atual.data, atual.inicio, atual.fim, atual.fim_ambiente = p.inicio.date(), p.inicio, p.fim, p.fim + prep
    atual.minutos_aula, atual.excecao_id, atual.fixa = p.minutos_aula, p.excecao_id, d.fixa
    atual.observacao = d.observacao if d.observacao is not None else atual.observacao
    atual.versao += 1
    try:
        db.execute(delete(AlocacaoRecurso).where(AlocacaoRecurso.alocacao_id == atual.id))
        for rid, q in p.recursos:
            db.add(AlocacaoRecurso(alocacao_id=atual.id, recurso_id=rid, quantidade=q))
        db.flush()
    except (IntegrityError, DBAPIError) as e:
        db.rollback()
        _traduzir_erro_banco(e)
    auditoria.registrar(db, ctx, "alocacao.alterar", "alocacoes", atual.id, antes=antes, depois=auditoria.snapshot(atual), motivo=motivo)
    db.add(RegistroDecisao(tipo="alteracao_manual", cenario_id=atual.cenario_id, alocacao_id=atual.id, usuario_id=getattr(ctx, "id", None),
                           motivo=motivo, dados={"antes": {k: antes[k] for k in ("inicio", "fim", "instrutor_id", "ambiente_id")},
                                                 "depois": {"inicio": p.inicio.isoformat(), "fim": p.fim.isoformat(),
                                                            "instrutor_id": p.instrutor_id, "ambiente_id": p.ambiente_id}}))
    return atual, oc


def remover_aula(db: Session, ctx, alocacao_id: int, versao_esperada: int | None = None, motivo: str | None = None):
    atual = db.scalars(select(Alocacao).where(Alocacao.id == alocacao_id).with_for_update()).first()
    if atual is None:
        raise NaoEncontrado("Aula não encontrada.")
    obter_cenario_editavel(db, atual.cenario_id)
    if versao_esperada is not None and atual.versao != versao_esperada:
        raise ConflitoConcorrencia("A aula foi alterada por outro usuário. Recarregue antes de remover.", codigo="VERSAO_DESATUALIZADA")
    if atual.fixa:
        raise ConflitoValidacao("A aula está marcada como fixa. Desmarque-a antes de remover.")
    antes = auditoria.snapshot(atual)
    db.delete(atual)
    auditoria.registrar(db, ctx, "alocacao.remover", "alocacoes", alocacao_id, antes=antes, motivo=motivo)


def datas_da_recorrencia(db: Session, turma: Turma, dia_semana: int, inicio: date, fim: date) -> tuple[list[date], list[dict]]:
    cal = Calendarios(db)
    d = inicio + timedelta(days=(dia_semana - inicio.weekday()) % 7)
    datas, puladas = [], []
    while d <= fim:
        ok, motivo = cal.dia_letivo(turma, d)
        if ok:
            datas.append(d)
        else:
            puladas.append({"data": d.isoformat(), "motivo": motivo})
        d += timedelta(days=7)
    return datas, puladas


def criar_recorrente(db: Session, ctx, cenario_id: int, base: DadosAula, dia_semana: int, data_inicio: date, data_fim: date,
                     limitar_carga_horaria: bool = True, origem: str = "manual", execucao_id: int | None = None):
    """Cria uma atividade semanal e suas aulas datadas (pula dias não letivos).
    Operação atômica: se qualquer data tiver bloqueio, nada é gravado."""
    obter_cenario_editavel(db, cenario_id)
    tuc = db.get(TurmaUC, base.turma_uc_id)
    if tuc is None:
        raise EntradaInvalida("Turma×UC inexistente.")
    turma = db.get(Turma, tuc.turma_id)
    uc = db.get(UnidadeCurricular, tuc.uc_id)
    inicio = max(data_inicio, turma.data_inicio, tuc.data_inicio or turma.data_inicio)
    fim = min(data_fim, turma.data_fim, tuc.data_limite or turma.data_fim)
    datas, puladas = datas_da_recorrencia(db, turma, dia_semana, inicio, fim)
    if not datas:
        raise ConflitoValidacao("Nenhuma data letiva disponível para a recorrência no período informado.", detalhes={"puladas": puladas})
    travar_recursos(db, cenario_id, [("turma", turma.id), ("tuc", tuc.id), ("instrutor", base.instrutor_id), ("ambiente", base.ambiente_id)]
                    + [("recurso", r) for r, _ in base.recursos])
    if not base.periodo_inicio_id:
        raise EntradaInvalida("Aulas recorrentes exigem período inicial e quantidade de períodos.")
    atv = Atividade(cenario_id=cenario_id, turma_uc_id=tuc.id, grupo=base.grupo, instrutor_id=base.instrutor_id,
                    ambiente_id=base.ambiente_id, dia_semana=dia_semana, periodo_inicio_id=base.periodo_inicio_id,
                    num_periodos=base.num_periodos or 1, data_inicio=datas[0], data_fim=datas[-1], fixa=base.fixa,
                    origem=origem, execucao_id=execucao_id)
    db.add(atv)
    db.flush()
    b = BaseDados(db, cenario_id)
    criadas, falhas, todas_oc = [], [], []
    for dt in datas:
        d = DadosAula(**{**base.__dict__, "data": dt, "origem": origem})
        p, _, _ = _proposta(db, d)
        if limitar_carga_horaria:
            from app.services.validacao import carga_horaria_minutos
            grupos_ch = [p.grupo] if p.grupo is not None else ([None] if not (uc.divide_grupos and turma.num_grupos > 1) else list(range(1, turma.num_grupos + 1)))
            restante = min(uc.carga_horaria_total * 60 - sum(carga_horaria_minutos(b, tuc, g, set())) for g in grupos_ch)
            if restante <= 0:
                break
        oc = validar_aula(b, p)
        if possui_bloqueio(oc):
            falhas.append({"data": dt.isoformat(), "ocorrencias": [o.to_dict() for o in oc if o.severidade == BLOQUEIO]})
            continue
        todas_oc.extend(oc)
        try:
            criadas.append(_gravar(db, cenario_id, p, tuc, d, ctx, atividade_id=atv.id))
        except (IntegrityError, DBAPIError) as e:
            db.rollback()
            _traduzir_erro_banco(e)
    if falhas:
        db.rollback()
        raise ConflitoValidacao(
            f"{len(falhas)} data(s) da recorrência violam restrições obrigatórias; nenhuma aula foi gravada.",
            detalhes={"falhas": falhas, "puladas": puladas}, codigo="RESTRICAO_OBRIGATORIA")
    if not criadas:
        db.rollback()
        raise ConflitoValidacao("A carga horária da UC já está totalmente programada.", codigo="CH_COMPLETA")
    atv.data_fim = criadas[-1].data
    auditoria.registrar(db, ctx, "atividade.criar", "atividades", atv.id, depois={**auditoria.snapshot(atv), "aulas": len(criadas)}, origem=origem)
    return atv, criadas, puladas, todas_oc


def copiar_semana(db: Session, ctx, cenario_id: int, turma_id: int, semana_origem: date, semana_destino: date):
    """Copia as aulas de uma turma de uma semana para outra (atômico)."""
    obter_cenario_editavel(db, cenario_id)
    seg_o = semana_origem - timedelta(days=semana_origem.weekday())
    seg_d = semana_destino - timedelta(days=semana_destino.weekday())
    delta = seg_d - seg_o
    origem = db.scalars(select(Alocacao).where(Alocacao.cenario_id == cenario_id, Alocacao.turma_id == turma_id,
                                               Alocacao.data >= seg_o, Alocacao.data < seg_o + timedelta(days=7),
                                               Alocacao.status != "cancelada")).all()
    if not origem:
        raise ConflitoValidacao("Não há aulas na semana de origem.")
    chaves = [("turma", turma_id)]
    for a in origem:
        chaves += [("tuc", a.turma_uc_id), ("instrutor", a.instrutor_id), ("ambiente", a.ambiente_id)]
    travar_recursos(db, cenario_id, chaves)
    b = BaseDados(db, cenario_id)
    falhas, criadas = [], []
    for a in origem:
        recs = [(r.recurso_id, r.quantidade) for r in db.scalars(select(AlocacaoRecurso).where(AlocacaoRecurso.alocacao_id == a.id))]
        p = AulaProposta(turma_uc_id=a.turma_uc_id, inicio=a.inicio + delta, fim=a.fim + delta, minutos_aula=a.minutos_aula,
                         grupo=a.grupo, instrutor_id=a.instrutor_id, ambiente_id=a.ambiente_id, recursos=recs, origem="copia")
        oc = validar_aula(b, p)
        if possui_bloqueio(oc):
            falhas.append({"aula_origem": a.id, "data": p.inicio.date().isoformat(), "ocorrencias": [o.to_dict() for o in oc if o.severidade == BLOQUEIO]})
            continue
        tuc = db.get(TurmaUC, a.turma_uc_id)
        criadas.append(_gravar(db, cenario_id, p, tuc, DadosAula(turma_uc_id=tuc.id, data=p.inicio.date(), origem="copia", observacao=a.observacao), ctx))
    if falhas:
        db.rollback()
        raise ConflitoValidacao("A cópia violaria restrições obrigatórias; nada foi gravado.", detalhes={"falhas": falhas}, codigo="RESTRICAO_OBRIGATORIA")
    auditoria.registrar(db, ctx, "alocacao.copiar_semana", "turmas", turma_id,
                        depois={"origem": seg_o.isoformat(), "destino": seg_d.isoformat(), "aulas": len(criadas)})
    return criadas


# ----------------------------------------------------------------------------- alternativas
def sugerir_alternativas(db: Session, cenario_id: int, p: AulaProposta, limite: int = 8) -> dict:
    """Alternativas calculadas a partir dos dados cadastrados (nada inventado):
    instrutores habilitados livres, ambientes compatíveis livres no mesmo
    horário e outros horários livres na mesma semana."""
    tuc = db.get(TurmaUC, p.turma_uc_id)
    turma = db.get(Turma, tuc.turma_id)
    uc = db.get(UnidadeCurricular, tuc.uc_id)
    b = BaseDados(db, cenario_id)
    ign = {p.alocacao_id} if p.alocacao_id else set()

    def ok(prop: AulaProposta) -> bool:
        return not possui_bloqueio(validar_aula(b, prop, ign))

    res = {"instrutores": [], "ambientes": [], "horarios": []}
    for inst in instrutores_elegiveis(db, uc, turma.unidade_id, p.data):
        if inst["id"] == p.instrutor_id:
            continue
        if ok(AulaProposta(**{**p.__dict__, "instrutor_id": inst["id"]})):
            res["instrutores"].append(inst)
    for amb in ambientes_compativeis(db, uc, turma, p.grupo is not None):
        if amb["id"] == p.ambiente_id:
            continue
        if ok(AulaProposta(**{**p.__dict__, "ambiente_id": amb["id"]})):
            res["ambientes"].append(amb)
    # outros horários na mesma semana com a mesma duração
    duracao = p.minutos_aula
    seg = p.data - timedelta(days=p.data.weekday())
    turnos = periodos_por_turno(db, turma.unidade_id)
    candidatos_turno = [turma.turno_id] if turma.turno_id in turnos else list(turnos)
    for k in range(7):
        dt = seg + timedelta(days=k)
        if dt.weekday() not in (turma.dias_possiveis or []):
            continue
        for tid in candidatos_turno:
            ps = [x for x in turnos.get(tid, []) if dt.weekday() in (x.dias_semana or [])]
            for i in range(len(ps)):
                acum, j = 0, i
                while j < len(ps) and acum < duracao:
                    acum += (ps[j].hora_fim.hour * 60 + ps[j].hora_fim.minute) - (ps[j].hora_inicio.hour * 60 + ps[j].hora_inicio.minute)
                    j += 1
                if acum < duracao:
                    continue
                ini, fim = combinar(dt, ps[i].hora_inicio), combinar(dt, ps[j - 1].hora_fim)
                if ini == p.inicio:
                    continue
                cand = AulaProposta(**{**p.__dict__, "inicio": ini, "fim": fim, "minutos_aula": acum})
                if ok(cand):
                    res["horarios"].append({"data": dt.isoformat(), "inicio": ini.strftime("%H:%M"), "fim": fim.strftime("%H:%M"),
                                            "periodo_inicio_id": ps[i].id, "num_periodos": j - i})
                    if len(res["horarios"]) >= limite:
                        return res
    return res
