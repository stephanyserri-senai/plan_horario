"""Agendamento de ambientes (salas e laboratórios) — substitui a planilha de ambientes × datas × turnos.

O instrutor vê, por semana, os ambientes da unidade em cada dia e turno (livre, com aula da grade publicada, bloqueado
— manutenção, evento —, reservado ou aguardando confirmação) e pede um horário livre pelo portal. O pedido fica pendente
e já segura o horário; a supervisão confirma (vira um bloqueio do ambiente: o gerador e a validação passam a respeitá-lo)
ou recusa com o motivo. A supervisão também agenda direto (já confirmado). Instrutor e supervisão podem cancelar.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflitoValidacao, EntradaInvalida, NaoEncontrado
from app.models import (AgendamentoAmbiente, Alocacao, Ambiente, Area, Bloqueio, Calendario, CalendarioExcecao, CenarioPlanejamento,
                        Instrutor, TipoAmbiente, Turma, Turno, Unidade)
from app.services import auditoria
from app.services.notificacoes import notificar

STATUS = {"pendente": "Aguardando a supervisão", "confirmado": "Confirmado", "recusado": "Recusado", "cancelado": "Cancelado"}
ATIVOS = ("pendente", "confirmado")
MAX_DIAS = 62  # janela da grade


def hoje() -> date:
    return date.today()


def turnos_da_unidade(db: Session, unidade_id: int) -> list[Turno]:
    """Turnos de aula da unidade (manhã, tarde, noite e o de sábado); o turno oculto do PFP (I) fica de fora."""
    ts = db.scalars(select(Turno).where(Turno.unidade_id == unidade_id, Turno.ativo.is_(True))).all()
    return sorted([t for t in ts if (t.codigo or "").upper() != "I"], key=lambda t: (t.hora_inicio, t.ordem or 0))


def _sabado(t: Turno) -> bool:
    return (t.codigo or "").upper() == "S" or "sáb" in (t.nome or "").lower() or "sab" in (t.nome or "").lower()


def turno_vale_no_dia(t: Turno, d: date) -> bool:
    """O turno de sábado só no sábado; os demais de segunda a sexta. Domingo, nenhum."""
    if d.weekday() == 6:
        return False
    return _sabado(t) == (d.weekday() == 5)


def _janela(t: Turno, d: date) -> tuple[datetime, datetime]:
    return datetime.combine(d, t.hora_inicio), datetime.combine(d, t.hora_fim)


def _sobrepoe(a0, a1, b0, b1) -> bool:
    return a0 < b1 and b0 < a1


def serializar(db: Session, a: AgendamentoAmbiente) -> dict:
    amb = db.get(Ambiente, a.ambiente_id)
    inst = db.get(Instrutor, a.instrutor_id) if a.instrutor_id else None
    t = db.get(Turma, a.turma_id) if a.turma_id else None
    tn = db.get(Turno, a.turno_id) if a.turno_id else None
    return {"id": a.id, "ambiente_id": a.ambiente_id, "ambiente": amb.codigo if amb else None, "ambiente_nome": amb.nome if amb else None,
            "instrutor_id": a.instrutor_id, "instrutor": inst.nome if inst else None, "turma": t.codigo if t else None, "turma_id": a.turma_id,
            "turno_id": a.turno_id, "turno": tn.nome if tn else None, "data": a.data.isoformat(),
            "inicio": a.inicio.strftime("%H:%M"), "fim": a.fim.strftime("%H:%M"), "finalidade": a.finalidade,
            "participantes": a.participantes, "status": a.status, "status_rotulo": STATUS[a.status], "resposta": a.resposta,
            "criado_em": a.criado_em.isoformat() if a.criado_em else None}


def grade(db: Session, inicio: date, fim: date, unidade_id: int, area_id: int | None = None, tipo_ambiente_id: int | None = None,
          q: str | None = None) -> dict:
    """Ambientes × dias × turnos: livre, aula (grade publicada), bloqueado, reservado (agendamento confirmado),
    pendente (aguardando a supervisão), feriado ou indisponível (ambiente fora de operação)."""
    if fim < inicio:
        raise EntradaInvalida("O fim do período vem antes do início.")
    if (fim - inicio).days > MAX_DIAS:
        raise EntradaInvalida(f"Escolha um período de até {MAX_DIAS} dias.")
    un = db.get(Unidade, unidade_id)
    if un is None:
        raise NaoEncontrado("Unidade não encontrada.")
    turnos = turnos_da_unidade(db, unidade_id)
    dias = [inicio + timedelta(days=k) for k in range((fim - inicio).days + 1)]
    dias = [d for d in dias if d.weekday() != 6]
    qa = select(Ambiente).where(Ambiente.unidade_id == unidade_id, Ambiente.ativo.is_(True))
    if tipo_ambiente_id:
        qa = qa.where(Ambiente.tipo_ambiente_id == tipo_ambiente_id)
    ambs = db.scalars(qa.order_by(Ambiente.codigo)).all()
    if area_id:
        from app.models import AmbienteArea
        extras = set(db.scalars(select(AmbienteArea.ambiente_id).where(AmbienteArea.area_id == area_id)))
        ambs = [a for a in ambs if a.todas_areas or a.area_id == area_id or a.id in extras]
    if q:
        termo = q.strip().lower()
        ambs = [a for a in ambs if termo in f"{a.codigo} {a.nome}".lower()]
    ids = [a.id for a in ambs]
    ini_dt, fim_dt = datetime.combine(inicio, datetime.min.time()), datetime.combine(fim + timedelta(days=1), datetime.min.time())
    # aulas da grade publicada (versões publicadas dos semestres)
    pub = [c.id for c in db.scalars(select(CenarioPlanejamento).where(CenarioPlanejamento.estado == "publicado",
                                                                       CenarioPlanejamento.tipo != "simulacao"))]
    aulas = defaultdict(list)
    if ids and pub:
        turmas = {}
        for a in db.scalars(select(Alocacao).where(Alocacao.cenario_id.in_(pub), Alocacao.ambiente_id.in_(ids), Alocacao.status != "cancelada",
                                                   Alocacao.data >= inicio, Alocacao.data <= fim)):
            if a.turma_id not in turmas:
                tt = db.get(Turma, a.turma_id)
                turmas[a.turma_id] = tt.codigo if tt else "aula"
            aulas[a.ambiente_id].append((a.inicio, a.fim, turmas[a.turma_id]))
    agds = defaultdict(list)
    bloq_de_agd = set()
    nomes = {}
    if ids:
        for g in db.scalars(select(AgendamentoAmbiente).where(AgendamentoAmbiente.ambiente_id.in_(ids), AgendamentoAmbiente.status.in_(ATIVOS),
                                                              AgendamentoAmbiente.data >= inicio, AgendamentoAmbiente.data <= fim)):
            if g.instrutor_id and g.instrutor_id not in nomes:
                i = db.get(Instrutor, g.instrutor_id)
                nomes[g.instrutor_id] = i.nome if i else ""
            agds[g.ambiente_id].append(g)
            if g.bloqueio_id:
                bloq_de_agd.add(g.bloqueio_id)
    bloqs = defaultdict(list)
    if ids:
        for b in db.scalars(select(Bloqueio).where(Bloqueio.alvo_tipo == "ambiente", Bloqueio.alvo_id.in_(ids), Bloqueio.ativo.is_(True),
                                                   Bloqueio.inicio < fim_dt, Bloqueio.fim > ini_dt)):
            if b.id not in bloq_de_agd:
                bloqs[b.alvo_id].append(b)
    # feriados e recessos dos calendários da unidade
    cal_ids = [c.id for c in db.scalars(select(Calendario).where(Calendario.unidade_id == unidade_id))]
    feriados = {e.data: e.descricao or e.tipo for e in db.scalars(select(CalendarioExcecao).where(
        CalendarioExcecao.calendario_id.in_(cal_ids), CalendarioExcecao.tipo.in_(["feriado", "recesso"]),
        CalendarioExcecao.data >= inicio, CalendarioExcecao.data <= fim))} if cal_ids else {}
    tipos = {t.id: t.nome for t in db.scalars(select(TipoAmbiente))}
    areas = {a.id: a.nome for a in db.scalars(select(Area))}
    linhas = []
    livres = 0
    for amb in ambs:
        cel = {}
        operacional = (amb.situacao or "operacional") == "operacional"
        for d in dias:
            for t in turnos:
                if not turno_vale_no_dia(t, d):
                    continue
                j0, j1 = _janela(t, d)
                k = f"{d.isoformat()}|{t.id}"
                if not operacional:
                    cel[k] = {"estado": "indisponivel", "texto": amb.situacao}
                elif d in feriados:
                    cel[k] = {"estado": "feriado", "texto": feriados[d]}
                elif (x := next((x for x in aulas[amb.id] if _sobrepoe(x[0], x[1], j0, j1)), None)):
                    cel[k] = {"estado": "aula", "texto": x[2]}
                elif (g := next((g for g in agds[amb.id] if _sobrepoe(g.inicio, g.fim, j0, j1)), None)):
                    cel[k] = {"estado": "reservado" if g.status == "confirmado" else "pendente", "texto": nomes.get(g.instrutor_id) or g.finalidade[:40],
                              "agendamento_id": g.id, "instrutor_id": g.instrutor_id}
                elif (b := next((b for b in bloqs[amb.id] if _sobrepoe(b.inicio, b.fim, j0, j1)), None)):
                    cel[k] = {"estado": "bloqueado", "texto": b.motivo or b.tipo}
                else:
                    cel[k] = {"estado": "livre"}
                    if d >= hoje():
                        livres += 1
        linhas.append({"id": amb.id, "codigo": amb.codigo, "nome": amb.nome, "tipo": tipos.get(amb.tipo_ambiente_id), "capacidade": amb.capacidade_fisica,
                       "area": "todas as áreas" if amb.todas_areas else areas.get(amb.area_id), "predio": amb.predio, "celulas": cel})
    return {"unidade": {"id": un.id, "nome": un.nome}, "inicio": inicio.isoformat(), "fim": fim.isoformat(), "hoje": hoje().isoformat(),
            "dias": [d.isoformat() for d in dias],
            "turnos": [{"id": t.id, "codigo": t.codigo, "nome": t.nome, "inicio": t.hora_inicio.strftime("%H:%M"), "fim": t.hora_fim.strftime("%H:%M"),
                        "sabado": _sabado(t)} for t in turnos],
            "ambientes": linhas, "livres": livres}


def _ocupado(db: Session, amb: Ambiente, ini: datetime, fim: datetime, ignorar_agendamento: int | None = None) -> str | None:
    """Motivo de o horário não estar livre (aula publicada, bloqueio, outro agendamento), ou None."""
    pub = [c.id for c in db.scalars(select(CenarioPlanejamento).where(CenarioPlanejamento.estado == "publicado",
                                                                       CenarioPlanejamento.tipo != "simulacao"))]
    if pub:
        a = db.scalars(select(Alocacao).where(Alocacao.cenario_id.in_(pub), Alocacao.ambiente_id == amb.id, Alocacao.status != "cancelada",
                                              Alocacao.inicio < fim, Alocacao.fim > ini)).first()
        if a is not None:
            t = db.get(Turma, a.turma_id)
            return f"já tem aula da turma {t.codigo if t else ''} nesse horário"
    g = db.scalars(select(AgendamentoAmbiente).where(AgendamentoAmbiente.ambiente_id == amb.id, AgendamentoAmbiente.status.in_(ATIVOS),
                                                     AgendamentoAmbiente.inicio < fim, AgendamentoAmbiente.fim > ini,
                                                     AgendamentoAmbiente.id != (ignorar_agendamento or 0))).first()
    if g is not None:
        return "já foi pedido por outra pessoa nesse horário" if g.status == "pendente" else "já está reservado nesse horário"
    proprios = {x for x in db.scalars(select(AgendamentoAmbiente.bloqueio_id).where(AgendamentoAmbiente.id == (ignorar_agendamento or 0))) if x}
    b = db.scalars(select(Bloqueio).where(Bloqueio.alvo_tipo == "ambiente", Bloqueio.alvo_id == amb.id, Bloqueio.ativo.is_(True),
                                          Bloqueio.inicio < fim, Bloqueio.fim > ini)).all()
    b = [x for x in b if x.id not in proprios]
    if b:
        return f"está bloqueado ({b[0].motivo or b[0].tipo})"
    if (amb.situacao or "operacional") != "operacional":
        return f"está '{amb.situacao}'"
    return None


def criar(db: Session, ctx, ambiente_id: int, data_: str | date, turno_id: int, finalidade: str, instrutor: Instrutor | None = None,
          turma_id: int | None = None, participantes: int | None = None, confirmar_ja: bool = False) -> AgendamentoAmbiente:
    amb = db.get(Ambiente, int(ambiente_id))
    if amb is None or not amb.ativo:
        raise NaoEncontrado("Ambiente não encontrado.")
    try:
        d = data_ if isinstance(data_, date) else date.fromisoformat(str(data_)[:10])
    except ValueError:
        raise EntradaInvalida("Data inválida.")
    if d < hoje():
        raise EntradaInvalida("Não dá para agendar uma data que já passou.")
    t = db.get(Turno, int(turno_id)) if turno_id else None
    if t is None or t.unidade_id != amb.unidade_id:
        raise EntradaInvalida("Escolha um turno da unidade do ambiente.")
    if not turno_vale_no_dia(t, d):
        raise EntradaInvalida(f"O turno {t.nome} não vale em {d:%d/%m} ({'só aos sábados' if _sabado(t) else 'de segunda a sexta'}).")
    finalidade = (finalidade or "").strip()
    if len(finalidade) < 5:
        raise EntradaInvalida("Diga para que é o ambiente (ex.: aula prática da turma HTC-ELT-12; reunião; avaliação).")
    if participantes not in (None, ""):
        try:
            participantes = int(participantes)
        except (TypeError, ValueError):
            raise EntradaInvalida("Participantes: informe um número.")
        if participantes > (amb.capacidade_fisica or 0):
            raise EntradaInvalida(f"{amb.codigo} comporta {amb.capacidade_fisica} pessoas; o pedido é para {participantes}.")
    else:
        participantes = None
    ini, fim = _janela(t, d)
    motivo = _ocupado(db, amb, ini, fim)
    if motivo:
        raise ConflitoValidacao(f"{amb.codigo} em {d:%d/%m} ({t.nome}) {motivo}. Escolha outro horário ou ambiente.", codigo="AMBIENTE_OCUPADO")
    g = AgendamentoAmbiente(ambiente_id=amb.id, instrutor_id=instrutor.id if instrutor else None, solicitado_por_id=getattr(ctx, "id", None),
                            turma_id=int(turma_id) if turma_id else None, turno_id=t.id, data=d, inicio=ini, fim=fim,
                            finalidade=finalidade[:2000], participantes=participantes, status="pendente")
    db.add(g)
    db.flush()
    auditoria.registrar(db, ctx, "agendamento.solicitar", "agendamentos_ambiente", g.id, depois=auditoria.snapshot(g))
    if confirmar_ja:
        decidir(db, ctx, g.id, "confirmado", None)
    return g


def decidir(db: Session, ctx, gid: int, status: str, resposta: str | None = None) -> AgendamentoAmbiente:
    """Supervisão: confirma (vira bloqueio do ambiente) ou recusa (com o motivo). O instrutor é avisado no portal."""
    g = db.get(AgendamentoAmbiente, gid)
    if g is None:
        raise NaoEncontrado("Agendamento não encontrado.")
    if status not in ("confirmado", "recusado"):
        raise EntradaInvalida("Use confirmado ou recusado.")
    if g.status != "pendente":
        raise ConflitoValidacao(f"O agendamento já está '{STATUS[g.status].lower()}'.")
    resposta = (resposta or "").strip() or None
    if status == "recusado" and not resposta:
        raise EntradaInvalida("Diga o motivo da recusa (o instrutor recebe o retorno).")
    amb = db.get(Ambiente, g.ambiente_id)
    if status == "confirmado":
        motivo = _ocupado(db, amb, g.inicio, g.fim, ignorar_agendamento=g.id)
        if motivo:
            raise ConflitoValidacao(f"{amb.codigo} {motivo}: não dá para confirmar.", codigo="AMBIENTE_OCUPADO")
        inst = db.get(Instrutor, g.instrutor_id) if g.instrutor_id else None
        b = Bloqueio(alvo_tipo="ambiente", alvo_id=amb.id, inicio=g.inicio, fim=g.fim, tipo="evento", ativo=True,
                     motivo=f"Agendamento: {g.finalidade}"[:280] + (f" ({inst.nome})" if inst else ""))
        db.add(b)
        db.flush()
        g.bloqueio_id = b.id
    antes = auditoria.snapshot(g)
    g.status, g.decidido_por_id, g.decidido_em = status, getattr(ctx, "id", None), datetime.now()
    if resposta:
        g.resposta = resposta
    db.flush()
    auditoria.registrar(db, ctx, "agendamento.decidir", "agendamentos_ambiente", g.id, antes=antes, depois=auditoria.snapshot(g))
    tn = db.get(Turno, g.turno_id) if g.turno_id else None
    notificar(db, g.instrutor_id, "agendamento", f"{'✅ Ambiente confirmado' if status == 'confirmado' else 'Agendamento recusado'}: {amb.codigo} em {g.data:%d/%m}",
              (resposta or STATUS[status]) + f" ({tn.nome if tn else ''}, {g.inicio:%H:%M}–{g.fim:%H:%M}).", "ambientes", ctx)
    return g


def cancelar(db: Session, ctx, gid: int, instrutor: Instrutor | None = None, motivo: str | None = None) -> AgendamentoAmbiente:
    g = db.get(AgendamentoAmbiente, gid)
    if g is None or (instrutor is not None and g.instrutor_id != instrutor.id):
        raise NaoEncontrado("Agendamento não encontrado.")
    if g.status not in ATIVOS:
        raise ConflitoValidacao("Este agendamento não está ativo.")
    g.status = "cancelado"
    if motivo:
        g.resposta = motivo
    if g.bloqueio_id:
        b = db.get(Bloqueio, g.bloqueio_id)
        if b is not None:
            b.ativo = False
    db.flush()
    auditoria.registrar(db, ctx, "agendamento.cancelar", "agendamentos_ambiente", g.id)
    if instrutor is None:
        amb = db.get(Ambiente, g.ambiente_id)
        notificar(db, g.instrutor_id, "agendamento", f"Agendamento cancelado: {amb.codigo if amb else ''} em {g.data:%d/%m}", motivo or "Cancelado pela supervisão.",
                  "ambientes", ctx)
    return g


def listar(db: Session, instrutor_id: int | None = None, status: str | None = None, unidades=None, desde: date | None = None) -> list[dict]:
    q = select(AgendamentoAmbiente).join(Ambiente, Ambiente.id == AgendamentoAmbiente.ambiente_id)
    if instrutor_id:
        q = q.where(AgendamentoAmbiente.instrutor_id == instrutor_id)
    if status:
        q = q.where(AgendamentoAmbiente.status == status)
    if unidades is not None:
        q = q.where(Ambiente.unidade_id.in_(unidades or [-1]))
    if desde:
        q = q.where(AgendamentoAmbiente.data >= desde)
    ordem = {"pendente": 0, "confirmado": 1, "recusado": 2, "cancelado": 3}
    lista = [serializar(db, g) for g in db.scalars(q.order_by(AgendamentoAmbiente.data, AgendamentoAmbiente.inicio).limit(500))]
    return sorted(lista, key=lambda x: (ordem.get(x["status"], 9), x["data"], x["inicio"]))
