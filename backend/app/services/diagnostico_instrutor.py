"""Por que nenhum instrutor pode assumir uma turma × UC — e o que mudar no horário para resolver.

Olha a semana de referência (a primeira semana letiva da oferta a partir de hoje) e, para cada instrutor:
- habilitados (matriz de competências + certificação exigida): quantos turnos já têm com aula, o teto de 90%
  (40 h → 9 de 10 turnos; 20 h → 4 de 5) e em quais dias do turno da turma estão livres;
- "quase habilitados" (da área da turma ou com a certificação exigida, mas sem a UC na matriz): o que falta e
  se teriam espaço.
Sugestões calculadas (nenhuma é aplicada automaticamente):
1. habilitar um instrutor que já tem a certificação/área e espaço no turno da turma;
2. liberar o habilitado que está no teto, passando uma das UCs dele para alguém livre naqueles mesmos horários;
3. adiar o início da turma para quando o habilitado tiver turnos livres (fim de outra UC dele);
4. mudar a turma de turno, se algum habilitado tiver espaço em outro turno;
5. contratar/habilitar alguém (quando nada acima resolve).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (Alocacao, Bloqueio, CompetenciaInstrutor, DisponibilidadeInstrutor, HabilitacaoInstrutor, Instrutor, Turma, TurmaUC,
                        Turno, UnidadeCurricular)
from app.services.planejamento import area_da_turma, instrutores_elegiveis, nivel_atende, nivel_da_turma
from app.services.regras_aula import HORAS_POR_TURNO, teto_letivo

DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def _seg(d: date) -> date:
    return d - timedelta(days=d.weekday())


class _Agenda:
    """Turnos ocupados com aula por instrutor (data, turno_id) no cenário."""

    def __init__(self, db: Session, cenario_id: int, unidade_id: int, d0: date, d1: date):
        self.turnos = db.scalars(select(Turno).where(Turno.unidade_id == unidade_id).order_by(Turno.hora_inicio)).all()
        self.aulas = defaultdict(set)  # instrutor → {(data, turno_id)}
        self.bloqueados = defaultdict(set)  # licença, afastamento etc. (PL/PJ não: podem ser remanejados)
        self.uc_do_turno = {}          # (instrutor, data, turno_id) → turma_uc_id
        for a in db.scalars(select(Alocacao).where(Alocacao.cenario_id == cenario_id, Alocacao.instrutor_id.isnot(None),
                                                   Alocacao.status != "cancelada", Alocacao.data >= d0, Alocacao.data <= d1)):
            t = self.turno_de(a.inicio.time())
            if t:
                self.aulas[a.instrutor_id].add((a.data, t.id))
                self.uc_do_turno[(a.instrutor_id, a.data, t.id)] = a.turma_uc_id
        from datetime import datetime
        for b in db.scalars(select(Bloqueio).where(Bloqueio.alvo_tipo == "instrutor", Bloqueio.ativo.is_(True),
                                                   Bloqueio.tipo.notin_(["planejamento", "projeto"]),
                                                   Bloqueio.inicio < datetime.combine(d1 + timedelta(days=1), datetime.min.time()),
                                                   Bloqueio.fim > datetime.combine(d0, datetime.min.time()))):
            d = max(b.inicio.date(), d0)
            while d <= min(b.fim.date(), d1):
                for t in self.turnos:
                    if b.inicio < datetime.combine(d, t.hora_fim) and b.fim > datetime.combine(d, t.hora_inicio):
                        self.bloqueados[b.alvo_id].add((d, t.id))
                d += timedelta(days=1)

    def turno_de(self, h):
        return next((t for t in self.turnos if t.hora_inicio <= h < t.hora_fim), None)

    def na_semana(self, iid: int, seg: date) -> set:
        return {(d, t) for d, t in self.aulas[iid] if seg <= d < seg + timedelta(days=7)}


def _livres(db, ag: _Agenda, inst: Instrutor, seg: date, turno: Turno, dias: list[int]) -> list[int]:
    disp = db.scalars(select(DisponibilidadeInstrutor).where(DisponibilidadeInstrutor.instrutor_id == inst.id)).all()
    ocupados = ag.na_semana(inst.id, seg) | ag.bloqueados[inst.id]
    return [k for k in dias if any(x.dia_semana == k and x.hora_inicio <= turno.hora_inicio and x.hora_fim >= turno.hora_fim for x in disp)
            and (seg + timedelta(days=k), turno.id) not in ocupados]


def _situacao(inst: Instrutor, ocupados: int) -> tuple[int, int, str]:
    teto = int(teto_letivo(inst.carga_horaria_contratual) // HORAS_POR_TURNO)
    total = int(float(inst.carga_horaria_contratual) // HORAS_POR_TURNO)
    return teto, total, f"{ocupados} de {total} turnos com aula (teto de 90%: {teto})"


def analisar(db: Session, cenario_id: int, turma_uc_id: int, hoje: date | None = None) -> dict:
    tuc = db.get(TurmaUC, turma_uc_id)
    turma, uc = db.get(Turma, tuc.turma_id), db.get(UnidadeCurricular, tuc.uc_id)
    turno = db.get(Turno, turma.turno_id) if turma.turno_id else None
    inicio = max(turma.data_inicio or date.today(), hoje or date.today(), tuc.data_inicio or date.min)
    seg0 = _seg(inicio) + (timedelta(days=7) if inicio.weekday() >= 5 else timedelta())
    fim = tuc.data_limite or turma.data_fim
    n_enc = int(uc.encontros_semanais or 1)
    dias = list(turma.dias_possiveis or [0, 1, 2, 3, 4])
    ag = _Agenda(db, cenario_id, turma.unidade_id, seg0 - timedelta(days=7), max(fim, seg0 + timedelta(days=35)))
    # semana típica: a mais cheia das 4 primeiras da oferta (evita semana com feriado parecer mais livre)
    semanas = [seg0 + timedelta(days=7 * k) for k in range(4)]
    sem_de = lambda iid: max(semanas, key=lambda s_: (len(ag.na_semana(iid, s_)), -s_.toordinal()))  # semana mais cheia do instrutor
    seg = seg0
    if turno is None:
        return {"turma": turma.codigo, "uc": uc.codigo, "habilitados": [], "quase": [], "sugestoes": []}
    rot_turno = turno.nome.lower()
    area_id = area_da_turma(db, turma)
    nivel_turma = nivel_da_turma(db, turma)
    elegiveis = {e["id"] for e in instrutores_elegiveis(db, uc, turma.unidade_id, inicio, area_id, nivel=nivel_turma)}
    com_uc = set(db.scalars(select(CompetenciaInstrutor.instrutor_id).where(CompetenciaInstrutor.uc_id == uc.id, CompetenciaInstrutor.ativo.is_(True))))
    cert = (uc.certificacao_exigida or "").strip().lower()
    com_cert = set(db.scalars(select(HabilitacaoInstrutor.instrutor_id).where(HabilitacaoInstrutor.ativo.is_(True),
                                                                              func.lower(HabilitacaoInstrutor.nome) == cert))) if cert else set()
    insts = db.scalars(select(Instrutor).where(Instrutor.ativo.is_(True), Instrutor.situacao == "ativo",
                                               Instrutor.unidade_id == turma.unidade_id).order_by(Instrutor.nome)).all()
    habilitados, quase, sugestoes = [], [], []
    no_teto = []
    for i in insts:
        si = sem_de(i.id)
        ocup = len(ag.na_semana(i.id, si))
        teto, total, txt = _situacao(i, ocup)
        livres = _livres(db, ag, i, si, turno, dias)
        cabe = min(len(livres), max(0, teto - ocup))
        linha = {"id": i.id, "nome": i.nome, "modalidade": i.modalidade, "turnos_com_aula": ocup, "teto_turnos": teto, "turnos_jornada": total,
                 "livres_no_turno": [DIAS[k] for k in livres], "cabe_encontros": cabe}
        if i.id in elegiveis:
            if ocup >= teto:
                linha["motivo"] = f"Já tem {txt}: não pode receber mais aulas."
                no_teto.append(i)
            elif not livres:
                linha["motivo"] = f"Sem {rot_turno} livre nos dias da turma ({txt})."
            elif cabe < n_enc:
                linha["motivo"] = (f"Só cabem {cabe} de {n_enc} encontros semanais: {txt}; "
                                   f"{rot_turno}s livres: {', '.join(linha['livres_no_turno']) or 'nenhuma'}.")
            else:
                linha["motivo"] = f"Tem espaço ({txt}; {rot_turno}s livres: {', '.join(linha['livres_no_turno'])})."
            habilitados.append(linha)
        elif i.area_id == area_id or i.id in com_cert or i.id in com_uc:
            falta = []
            if i.id not in com_uc:
                falta.append(f"habilitação em {uc.codigo}")
            if cert and i.id not in com_cert:
                falta.append(f"certificação {uc.certificacao_exigida}")
            if not nivel_atende(i.nivel, nivel_turma):
                falta.append("nível técnico (é instrutor básico: só AIB e qualificações)")
            linha["falta"] = falta
            linha["motivo"] = (f"Falta {' e '.join(falta) or 'requisito'}; {txt}; "
                               f"{rot_turno}s livres: {', '.join(linha['livres_no_turno']) or 'nenhuma'}.")
            quase.append(linha)

    # 1) habilitar quem já tem a certificação/área e espaço no turno
    area_inst = {i.id: i.area_id for i in insts}
    for q in [q for q in sorted(quase, key=lambda x: (len(x["falta"]), area_inst.get(x["id"]) != area_id, x["turnos_com_aula"]))
              if q["cabe_encontros"] >= n_enc and not any(x.startswith("nível") for x in q["falta"])][:3]:
        if True:
            so_hab = q["falta"] == [f"habilitação em {uc.codigo}"]
            sugestoes.append({"tipo": "habilitar", "prioridade": 1 if so_hab else 3,
                              "acao": {"tipo": "habilitar_instrutor", "instrutor_id": q["id"], "uc_id": uc.id, "turma_id": turma.id} if so_hab else None,
                              "descricao": f"Habilitar {q['nome']} em {uc.codigo}"
                                           f"{'' if so_hab else ' (e providenciar ' + ', '.join(x for x in q['falta'] if 'certificação' in x) + ')'}: "
                                           f"tem {len(q['livres_no_turno'])} {rot_turno}s livres ({', '.join(q['livres_no_turno'])}) e ficaria com "
                                           f"{q['turnos_com_aula'] + n_enc} de {q['turnos_jornada']} turnos (teto {q['teto_turnos']})."})
    # 2) liberar o habilitado que está no teto: passar uma UC dele para alguém livre nos mesmos horários
    for h in no_teto:
        por_tuc = defaultdict(list)
        sh = sem_de(h.id)
        for (d, t) in sorted(ag.na_semana(h.id, sh)):
            por_tuc[ag.uc_do_turno[(h.id, d, t)]].append((d, t))
        teto_h, _x, _y = _situacao(h, 0)
        ocup_h = len(ag.na_semana(h.id, sh))
        livres_h = {k for k in _livres(db, ag, h, sh, turno, dias)}
        for tuc2_id, slots in sorted(por_tuc.items(), key=lambda kv: len(kv[1])):
            t2 = db.get(TurmaUC, tuc2_id)
            if t2 is None or t2.id == tuc.id:
                continue
            # depois da troca: turnos livres no turno da turma e folga até o teto de 90%
            livres_depois = livres_h | {d.weekday() for d, t in slots if t == turno.id and d.weekday() in dias}
            if min(len(livres_depois), teto_h - (ocup_h - len(slots))) < n_enc:
                continue
            uc2, turma2 = db.get(UnidadeCurricular, t2.uc_id), db.get(Turma, t2.turma_id)
            ok2 = {e["id"] for e in instrutores_elegiveis(db, uc2, turma2.unidade_id, inicio, area_da_turma(db, turma2), nivel=nivel_da_turma(db, turma2))} - {h.id}
            cert2 = (uc2.certificacao_exigida or "").strip().lower()
            for c in insts:
                if c.id == h.id:
                    continue
                livres_c = all((d, t) not in ag.na_semana(c.id, sh) and (d, t) not in ag.bloqueados[c.id] and _disponivel(db, c, d.weekday(), ag, t) for d, t in slots)
                teto_c, _tot, _ = _situacao(c, len(ag.na_semana(c.id, sh)))
                if not livres_c or len(ag.na_semana(c.id, sh)) + len(slots) > teto_c or not nivel_atende(c.nivel, nivel_da_turma(db, turma2)):
                    continue
                if c.id in ok2:
                    req = "já é habilitado(a)"
                elif c.area_id == turma2.area_id and (not cert2 or c.id in com_cert or _tem_cert(db, c.id, cert2)):
                    req = f"precisa ser habilitado(a) em {uc2.codigo}"
                else:
                    continue
                dias_txt = ", ".join(f"{DIAS[d.weekday()]} {next(x.nome for x in ag.turnos if x.id == t).lower()}" for d, t in slots)
                sugestoes.append({"tipo": "liberar_instrutor", "prioridade": 2 if c.id in ok2 else 4,
                                  "acao": {"tipo": "passar_uc", "turma_uc_id": t2.id, "de_instrutor_id": h.id, "para_instrutor_id": c.id,
                                           "habilitar": c.id not in ok2, "turma_id": turma.id},
                                  "descricao": f"Passar {uc2.codigo} da {turma2.codigo} ({dias_txt}) de {h.nome} para {c.nome} ({req}): "
                                               f"{h.nome} fica com {ocup_h - len(slots)} de {teto_h} turnos e {rot_turno}s livres em "
                                               f"{', '.join(DIAS[k] for k in sorted(livres_depois))} para a {turma.codigo}."})
                break
    # 3) adiar o início até o habilitado ter espaço
    for h in no_teto:
        teto, _t, _ = _situacao(h, 0)
        s = sem_de(h.id) + timedelta(days=7)
        while s <= fim:
            if teto - len(ag.na_semana(h.id, s)) >= n_enc and len(_livres(db, ag, h, s, turno, dias)) >= n_enc:
                n_sem = max(1, (fim - s).days // 7 + 1)
                cabe_ch = n_sem * n_enc * HORAS_POR_TURNO >= float(uc.carga_horaria_total)
                sugestoes.append({"tipo": "adiar", "prioridade": 3 if cabe_ch else 5,
                                  "acao": {"tipo": "adiar_uc", "turma_uc_id": tuc.id, "data_inicio": s.isoformat(), "turma_id": turma.id} if cabe_ch else None,
                                  "descricao": f"Iniciar a {turma.codigo} em {s:%d/%m}, quando {h.nome} passa a ter {rot_turno}s livres "
                                               f"(fim de outra UC dele/dela)."
                                               + ("" if cabe_ch else f" Para cumprir {float(uc.carga_horaria_total):g} h, o término teria de ser estendido "
                                                  f"para depois de {fim:%d/%m}.")})
                break
            s += timedelta(days=7)
    # 4) outro turno
    for t in ag.turnos:
        if t.id == turno.id:
            continue
        for i in insts:
            if i.id not in elegiveis:
                continue
            teto, _tot, _ = _situacao(i, 0)
            si = sem_de(i.id)
            livres = _livres(db, ag, i, si, t, dias)
            if len(livres) >= n_enc and teto - len(ag.na_semana(i.id, si)) >= n_enc:
                sugestoes.append({"tipo": "turno", "prioridade": 4,
                                  "descricao": f"Mudar a {turma.codigo} para o turno da {t.nome.lower()}: {i.nome} tem {len(livres)} livres "
                                               f"({', '.join(DIAS[k] for k in livres)}). Avalie antes o impacto para os alunos."})
                break
    sugestoes.append({"tipo": "contratar", "prioridade": 9,
                      "descricao": f"Contratar ou habilitar outro instrutor em {uc.codigo}"
                                   f"{' com certificação ' + uc.certificacao_exigida if uc.certificacao_exigida else ''} (a {turma.codigo} precisa de "
                                   f"{n_enc} {rot_turno}(s) por semana)."})
    sugestoes.sort(key=lambda x: x["prioridade"])
    if not elegiveis:
        resumo = f"Ninguém é habilitado em {uc.codigo} na matriz de competências da unidade."
    elif all(h["cabe_encontros"] < n_enc for h in habilitados):
        resumo = (f"Os habilitados em {uc.codigo} ({', '.join(h['nome'] for h in habilitados)}) não têm {n_enc} {rot_turno}(s) livres na semana "
                  f"a partir de {seg:%d/%m}: " + " ".join(f"{h['nome']}: {h['motivo']}" for h in habilitados))
    else:
        resumo = "Há habilitado com espaço; a falta de horário vem da combinação com sala ou dias da turma."
    return {"turma": turma.codigo, "uc": f"{uc.codigo} – {uc.nome}", "turno": turno.nome, "semana_referencia": seg.isoformat(),
            "encontros_semanais": n_enc, "resumo": resumo, "habilitados": habilitados, "quase": quase[:8], "sugestoes": sugestoes[:10]}


def _disponivel(db, inst, dia: int, ag: _Agenda, turno_id: int) -> bool:
    t = next(x for x in ag.turnos if x.id == turno_id)
    return bool(db.scalar(select(DisponibilidadeInstrutor.id).where(DisponibilidadeInstrutor.instrutor_id == inst.id,
                                                                   DisponibilidadeInstrutor.dia_semana == dia,
                                                                   DisponibilidadeInstrutor.hora_inicio <= t.hora_inicio,
                                                                   DisponibilidadeInstrutor.hora_fim >= t.hora_fim).limit(1)))


def _tem_cert(db, iid: int, cert: str) -> bool:
    return bool(db.scalar(select(HabilitacaoInstrutor.id).where(HabilitacaoInstrutor.instrutor_id == iid, HabilitacaoInstrutor.ativo.is_(True),
                                                               func.lower(HabilitacaoInstrutor.nome) == cert).limit(1)))
