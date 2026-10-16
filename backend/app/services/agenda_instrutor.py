"""Agenda semanal do instrutor: aulas, planejamento (PL), projeto/outra atividade (PJ) e turnos vazios.

Modalidades:
- MENSALISTA: 40 h ou 20 h garantidas. Cada turno da jornada é aula, PL ou PJ; turno vazio = "sem atribuição".
- HORISTA: 40 h ou 20 h não garantidas. Turno sem aula pode ficar vazio (dispensa); PL e PJ são opcionais.
PL e PJ são bloqueios do instrutor (tipos "planejamento" e "projeto"): a validação e o gerador de horários
não colocam aula nesses turnos.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import EntradaInvalida, NaoEncontrado
from app.models import Alocacao, Bloqueio, DisponibilidadeInstrutor, Instrutor, Turma, Turno, UnidadeCurricular
from app.services import auditoria
from app.services.regras_aula import HORAS_POR_TURNO

TIPOS = {"PL": ("planejamento", "Planejamento"), "PJ": ("projeto", "Projeto / outra atividade")}
TIPO_PARA_SIGLA = {v[0]: k for k, v in TIPOS.items()}
DIAS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]


def _turnos_da_jornada(db: Session, inst: Instrutor) -> list[Turno]:
    # o turno integral (PFP) não é linha da agenda: a aula de dia inteiro aparece na manhã e na tarde
    turnos = [t for t in db.scalars(select(Turno).where(Turno.unidade_id == inst.unidade_id, Turno.ativo.is_(True)).order_by(Turno.hora_inicio))
              if t.codigo != "I"]
    disp = db.scalars(select(DisponibilidadeInstrutor).where(DisponibilidadeInstrutor.instrutor_id == inst.id)).all()
    # sábado (turno S) só com janela no sábado; os demais turnos pelas janelas de segunda a sexta
    da_jornada = [t for t in turnos if any(((d.dia_semana == 5) == (t.codigo == "S")) and d.hora_inicio <= t.hora_inicio and d.hora_fim >= t.hora_fim
                                           for d in disp)]
    return da_jornada or list(turnos)


def _dias(db: Session, inst: Instrutor) -> list[int]:
    dias = sorted({d.dia_semana for d in db.scalars(select(DisponibilidadeInstrutor).where(DisponibilidadeInstrutor.instrutor_id == inst.id))})
    return dias or [0, 1, 2, 3, 4]


def _janela(d: date, t: Turno) -> tuple[datetime, datetime]:
    return datetime.combine(d, t.hora_inicio), datetime.combine(d, t.hora_fim)


def semana(db: Session, cenario_id: int, instrutor_id: int, inicio: date) -> dict:
    from app.services.calendario import Calendarios
    inst = db.get(Instrutor, instrutor_id)
    if inst is None:
        raise NaoEncontrado("Instrutor não encontrado.")
    seg = inicio - timedelta(days=inicio.weekday())
    fim_sem = seg + timedelta(days=7)
    turnos = _turnos_da_jornada(db, inst)
    dias = _dias(db, inst)
    aulas = db.scalars(select(Alocacao).where(Alocacao.cenario_id == cenario_id, Alocacao.instrutor_id == inst.id, Alocacao.status != "cancelada",
                                              Alocacao.data >= seg, Alocacao.data < fim_sem)).all()
    turmas = {t.id: t.codigo for t in db.scalars(select(Turma).where(Turma.id.in_({a.turma_id for a in aulas})))} if aulas else {}
    ucs = {u.id: u.codigo for u in db.scalars(select(UnidadeCurricular).where(UnidadeCurricular.id.in_({a.uc_id for a in aulas})))} if aulas else {}
    bloqs = db.scalars(select(Bloqueio).where(Bloqueio.alvo_tipo == "instrutor", Bloqueio.alvo_id == inst.id, Bloqueio.ativo.is_(True),
                                              Bloqueio.inicio < datetime.combine(fim_sem, datetime.min.time()),
                                              Bloqueio.fim > datetime.combine(seg, datetime.min.time()))).all()
    cal = Calendarios(db)
    celulas, resumo = [], defaultdict(float)
    for di in dias:
        d = seg + timedelta(days=di)
        letivo, motivo = cal.dia_letivo_unidade(inst.unidade_id, d)
        for t in turnos:
            if (t.codigo == "S") != (di == 5):
                continue  # turno de sábado só no sábado; os da semana, só de segunda a sexta
            ini, fim = _janela(d, t)
            da = [a for a in aulas if a.inicio < fim and a.fim > ini]
            bs = [b for b in bloqs if b.inicio < fim and b.fim > ini]
            cel = {"data": d.isoformat(), "dia": di, "turno_id": t.id, "turno": t.nome, "horario": f"{t.hora_inicio:%H:%M}–{t.hora_fim:%H:%M}"}
            if da:
                cel.update(estado="aula", horas=round(sum(a.minutos_aula for a in da) / 60, 1),
                           aulas=[{"id": a.id, "turma": turmas.get(a.turma_id), "uc": ucs.get(a.uc_id)} for a in da])
                resumo["aula_h"] += cel["horas"]
            elif any(b.tipo in TIPO_PARA_SIGLA for b in bs):
                b = next(b for b in bs if b.tipo in TIPO_PARA_SIGLA)
                cel.update(estado=TIPO_PARA_SIGLA[b.tipo], descricao=b.motivo, horas=HORAS_POR_TURNO)
                resumo[f"{TIPO_PARA_SIGLA[b.tipo].lower()}_h"] += HORAS_POR_TURNO
            elif bs:
                cel.update(estado="indisponivel", descricao=f"{bs[0].tipo}: {bs[0].motivo or ''}".strip(": "))
            elif not letivo:
                cel.update(estado="nao_letivo", descricao=motivo)
            else:
                cel.update(estado="vazio")
                resumo["vazio_turnos"] += 1
            celulas.append(cel)
    carga = float(inst.carga_horaria_contratual)
    ocupadas = resumo["aula_h"] + resumo["pl_h"] + resumo["pj_h"]
    mensalista = inst.modalidade == "mensalista"
    return {
        "instrutor": {"id": inst.id, "nome": inst.nome, "modalidade": inst.modalidade, "carga_semanal_h": carga},
        "semana": seg.isoformat(), "dias": [{"dia": di, "data": (seg + timedelta(days=di)).isoformat(), "rotulo": DIAS[di]} for di in dias],
        "turnos": [{"id": t.id, "nome": t.nome, "horario": f"{t.hora_inicio:%H:%M}–{t.hora_fim:%H:%M}"} for t in turnos],
        "celulas": celulas,
        "resumo": {"aula_h": round(resumo["aula_h"], 1), "pl_h": resumo["pl_h"], "pj_h": resumo["pj_h"], "ocupadas_h": round(ocupadas, 1),
                   "vazios": int(resumo["vazio_turnos"]),
                   # mensalista: turno vazio é hora paga sem destino; horista: é dispensa
                   "sem_atribuicao_h": int(resumo["vazio_turnos"]) * HORAS_POR_TURNO if mensalista else 0,
                   "dispensa_h": 0 if mensalista else int(resumo["vazio_turnos"]) * HORAS_POR_TURNO,
                   "excede_carga": ocupadas > carga + 0.01},
    }


def marcar(db: Session, ctx, cenario_id: int, instrutor_id: int, data: date, turno_id: int, sigla: str | None,
           repetir_ate: date | None = None, descricao: str | None = None) -> dict:
    """Marca o turno como PL ou PJ (ou deixa vazio, com sigla None) na data e, se pedido, toda semana até `repetir_ate`."""
    from app.services.calendario import Calendarios
    from app.services.notificacoes import notificar
    inst = db.get(Instrutor, instrutor_id)
    t = db.get(Turno, turno_id)
    if inst is None or t is None:
        raise NaoEncontrado("Instrutor ou turno não encontrado.")
    if t.unidade_id != inst.unidade_id:
        raise EntradaInvalida("O turno é de outra unidade.")
    if sigla not in (None, "", *TIPOS):
        raise EntradaInvalida("Use PL (planejamento), PJ (projeto/outra atividade) ou vazio.")
    if repetir_ate and repetir_ate < data:
        raise EntradaInvalida("A data final da repetição é anterior ao dia escolhido.")
    cal = Calendarios(db)
    datas, d = [], data
    while d <= (repetir_ate or data):
        if cal.dia_letivo_unidade(inst.unidade_id, d)[0]:
            datas.append(d)
        d += timedelta(days=7)
    feitos, removidos, com_aula = 0, 0, []
    for d in datas:
        ini, fim = _janela(d, t)
        r = db.execute(delete(Bloqueio).where(Bloqueio.alvo_tipo == "instrutor", Bloqueio.alvo_id == inst.id,
                                              Bloqueio.tipo.in_([v[0] for v in TIPOS.values()]), Bloqueio.inicio < fim, Bloqueio.fim > ini))
        removidos += r.rowcount or 0
        if not sigla:
            continue
        if db.scalar(select(Alocacao.id).where(Alocacao.cenario_id == cenario_id, Alocacao.instrutor_id == inst.id, Alocacao.status != "cancelada",
                                               Alocacao.inicio < fim, Alocacao.fim > ini).limit(1)):
            com_aula.append(d.isoformat())
            continue
        db.add(Bloqueio(alvo_tipo="instrutor", alvo_id=inst.id, inicio=ini, fim=fim, tipo=TIPOS[sigla][0],
                        motivo=(descricao or TIPOS[sigla][1])[:300], ativo=True))
        feitos += 1
    db.flush()
    auditoria.registrar(db, ctx, "instrutor.agenda", "instrutores", inst.id,
                        depois={"turno": t.nome, "sigla": sigla or "vazio", "datas": [x.isoformat() for x in datas], "com_aula": com_aula})
    if feitos or removidos:
        rot = TIPOS[sigla][1] if sigla else "turno livre"
        quando = f"{DIAS[data.weekday()]} ({t.nome})" + (f", toda semana até {repetir_ate:%d/%m}" if repetir_ate else f" em {data:%d/%m}")
        notificar(db, inst.id, "cadastro", f"Agenda atualizada: {rot}", f"{quando}.", "turmas", ctx)
    return {"marcados": feitos, "removidos": removidos, "datas": len(datas), "com_aula": com_aula}


def reservas_semanais(db: Session, instrutor_id: int, inicio: date | None, fim: date | None) -> list[tuple[int, int, int]]:
    """Janelas (dia da semana, min início, min fim) que o instrutor tem como PL/PJ em pelo menos metade das semanas do período.
    O gerador de horários monta um padrão semanal: essas janelas saem da disponibilidade para o padrão não cair nelas."""
    q = select(Bloqueio).where(Bloqueio.alvo_tipo == "instrutor", Bloqueio.alvo_id == instrutor_id, Bloqueio.ativo.is_(True),
                               Bloqueio.tipo.in_([v[0] for v in TIPOS.values()]))
    if inicio:
        q = q.where(Bloqueio.fim > datetime.combine(inicio, datetime.min.time()))
    if fim:
        q = q.where(Bloqueio.inicio < datetime.combine(fim + timedelta(days=1), datetime.min.time()))
    bloqs = db.scalars(q).all()
    if not bloqs:
        return []
    semanas = max(1, ((fim - inicio).days + 1) // 7) if inicio and fim else 1
    cont = defaultdict(int)
    for b in bloqs:
        if b.inicio.date() == b.fim.date():
            cont[(b.inicio.weekday(), b.inicio.hour * 60 + b.inicio.minute, b.fim.hour * 60 + b.fim.minute)] += 1
    return [k for k, n in cont.items() if n >= max(2, semanas / 2) or (semanas <= 2 and n >= 1)]


def subtrair(janelas: list[tuple[int, int, int]], reservas: list[tuple[int, int, int]]) -> list[tuple[int, int, int]]:
    """Disponibilidade menos as reservas (todas como (dia, ini, fim) em minutos)."""
    out = list(janelas)
    for rd, ri, rf in reservas:
        novo = []
        for d, i, f in out:
            if d != rd or rf <= i or ri >= f:
                novo.append((d, i, f))
                continue
            if i < ri:
                novo.append((d, i, ri))
            if rf < f:
                novo.append((d, rf, f))
        out = novo
    return out
